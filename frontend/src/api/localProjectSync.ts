import { createProject, getProject, ProjectApiError, type ApiConfig } from './projects'
import {
  beginLocalProjectSync,
  getLocalProject,
  getLocalProjectSyncState,
  listLocalProjectWorkflows,
  getLocalWorkflow,
  saveLocalProjectSyncState,
  saveLocalWorkflowSyncState,
  LocalRuntimeApiError,
  type LocalProjectSyncState,
} from './localRuntime'
import {
  createProjectWorkflow,
  getWorkflow,
  saveWorkflowDraft,
  WorkflowApiError,
  type WorkflowGraph,
  type WorkflowDetail,
} from './workflows'

export interface LocalProjectSyncProgress {
  message: string
  completed: number
  total: number
}

export interface LocalProjectSyncResult {
  platformProjectId: string
  synchronizedWorkflows: number
  unchangedWorkflows: number
}

export class LocalProjectSyncError extends Error {
  readonly code: string
  readonly status: LocalProjectSyncState['status']

  constructor(message: string, code: string, status: LocalProjectSyncState['status']) {
    super(message)
    this.name = 'LocalProjectSyncError'
    this.code = code
    this.status = status
  }
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`
  if (typeof value === 'object' && value !== null) {
    const record = value as Record<string, unknown>
    return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${stableJson(record[key])}`).join(',')}}`
  }
  return JSON.stringify(value) ?? String(value)
}

function workflowMatchesLocal(
  remote: { name: string; description: string; graph: WorkflowGraph },
  local: { name: string; description: string; graph: WorkflowGraph },
): boolean {
  return remote.name === local.name && remote.description === local.description &&
    stableJson(remote.graph) === stableJson(local.graph)
}

function errorCode(error: unknown): string {
  if (error instanceof LocalRuntimeApiError) return error.code
  if (error instanceof WorkflowApiError) return error.code
  if (error instanceof ProjectApiError) return `HTTP_${error.status}`
  return 'NETWORK_OR_UNEXPECTED'
}

function createOutcomeNeedsReview(error: unknown): boolean {
  if (error instanceof ProjectApiError || error instanceof WorkflowApiError) return error.status >= 500
  // A dropped connection can happen after the server committed its create request.
  return !(error instanceof LocalRuntimeApiError)
}

function syncConflict(message: string): LocalProjectSyncError {
  return new LocalProjectSyncError(message, 'PLATFORM_REVISION_MOVED', 'conflict')
}

export async function syncLocalProjectToPlatform(
  config: ApiConfig,
  projectId: string,
  options: {
    confirmUncertainRetry: boolean
    adoptExistingPlatformProjectId?: string
    adoptExistingPlatformWorkflowIds?: Record<string, string>
    onProgress?: (progress: LocalProjectSyncProgress) => void
  },
): Promise<LocalProjectSyncResult> {
  if (!config.baseUrl.trim() || !config.token.trim()) {
    throw new LocalProjectSyncError('请先连接有权限的科研平台账号。', 'PLATFORM_AUTH_REQUIRED', 'failed')
  }

  const localProject = await getLocalProject(projectId)
  const workflowSummaries = await listLocalProjectWorkflows(projectId)
  let syncState = await getLocalProjectSyncState(projectId)
  const total = workflowSummaries.length + 1
  let completed = 0
  let synchronizedWorkflows = 0
  let unchangedWorkflows = 0
  let activeWorkflowId: string | null = null
  let activePlatformWorkflowId: string | null = null
  let activePlatformWorkflowBaseline: number | null = null
  const progress = (message: string) => options.onProgress?.({ message, completed, total })

  const hasUncertainProjectCreate = syncState.status === 'needs_review' || syncState.status === 'pending' ||
    (syncState.status === 'conflict' && !syncState.platform_project_id)
  const hasUncertainWorkflowCreate = syncState.workflows.some((item) =>
    item.status === 'needs_review' || item.status === 'pending' || (item.status === 'conflict' && !item.platform_workflow_id),
  )
  if ((hasUncertainProjectCreate || hasUncertainWorkflowCreate) && !options.confirmUncertainRetry) {
    throw new LocalProjectSyncError(
      '上次请求的创建结果不确定。请先检查平台是否已有对应对象，再明确确认是否重试。',
      'SYNC_OUTCOME_NEEDS_REVIEW',
      'needs_review',
    )
  }

  try {
    syncState = await beginLocalProjectSync(projectId, options.confirmUncertainRetry)
  } catch (error) {
    if (error instanceof LocalRuntimeApiError && error.code === 'LOCAL_SYNC_ALREADY_RUNNING') {
      throw new LocalProjectSyncError(
        '此项目已有同步任务或尚未核对的中断任务。请先确认没有其他同步仍在运行，再决定是否恢复。',
        error.code,
        'pending',
      )
    }
    throw error
  }

  let platformProjectId = syncState.platform_project_id
  const adoptedExistingProjectId = options.adoptExistingPlatformProjectId?.trim() ?? ''
  let adoptedExistingProjectForThisRun = false
  try {
    if (!platformProjectId && adoptedExistingProjectId) {
      const candidate = await getProject(config, adoptedExistingProjectId)
      if (candidate.name !== localProject.name || candidate.domain !== localProject.domain || candidate.description !== localProject.description) {
        throw syncConflict('所填平台项目与本机项目名称、领域或说明不一致；未建立关联。')
      }
      platformProjectId = candidate.id
      adoptedExistingProjectForThisRun = true
      syncState = await saveLocalProjectSyncState(projectId, {
        status: 'pending',
        platform_project_id: platformProjectId,
        error_code: null,
      })
    }

    if (platformProjectId) {
      progress('核对已创建的平台项目…')
      const platformProject = adoptedExistingProjectForThisRun
        ? { visibility: 'private' as const }
        : await getProject(config, platformProjectId)
      if (platformProject.visibility !== 'private') {
        throw syncConflict('关联的平台项目不属于当前私有工作区；已停止同步。')
      }
    } else {
      progress('创建平台项目副本…')
      try {
        const platformProject = await createProject(config, {
          name: localProject.name,
          domain: localProject.domain,
          description: localProject.description,
        })
        platformProjectId = platformProject.id
        await saveLocalProjectSyncState(projectId, {
          status: 'pending',
          platform_project_id: platformProjectId,
          error_code: null,
        })
      } catch (error) {
        if (createOutcomeNeedsReview(error)) {
          await saveLocalProjectSyncState(projectId, { status: 'needs_review', error_code: errorCode(error) })
          throw new LocalProjectSyncError(
            '平台项目创建请求中断，无法确认平台是否已创建副本。检查平台项目列表后再决定是否重试。',
            'PROJECT_CREATE_OUTCOME_UNCONFIRMED',
            'needs_review',
          )
        }
        throw error
      }
    }

    if (!platformProjectId) throw new Error('平台项目创建响应缺少标识。')
    completed = 1

    for (const summary of workflowSummaries) {
      activeWorkflowId = summary.id
      progress(`同步工作流：${summary.name}`)
      const localWorkflow = await getLocalWorkflow(summary.id)
      const knownState = syncState.workflows.find((item) => item.workflow_id === summary.id)
      let platformWorkflowId = knownState?.platform_workflow_id ?? null
      let baselineRevision = knownState?.synced_revision ?? null
      const adoptedWorkflowId = options.adoptExistingPlatformWorkflowIds?.[summary.id]?.trim() ?? ''
      activePlatformWorkflowId = platformWorkflowId
      activePlatformWorkflowBaseline = baselineRevision

      await saveLocalWorkflowSyncState(projectId, summary.id, {
        status: 'pending',
        source_revision: localWorkflow.revision,
        error_code: null,
      })

      let platformWorkflow: WorkflowDetail
      if (platformWorkflowId) {
        platformWorkflow = await getWorkflow(config, platformWorkflowId)
      } else if (adoptedWorkflowId) {
        let candidate: WorkflowDetail
        try {
          candidate = await getWorkflow(config, adoptedWorkflowId)
        } catch (error) {
          await saveLocalWorkflowSyncState(projectId, summary.id, {
            status: 'needs_review',
            error_code: errorCode(error),
          })
          throw new LocalProjectSyncError(
            `无法核对工作流“${localWorkflow.name}”对应的平台 ID。请重新核对后再继续。`,
            'PLATFORM_WORKFLOW_ID_UNVERIFIED',
            'needs_review',
          )
        }
        if (candidate.project_id !== platformProjectId || candidate.name !== localWorkflow.name || candidate.description !== localWorkflow.description) {
          await saveLocalWorkflowSyncState(projectId, summary.id, {
            status: 'conflict',
            error_code: 'PLATFORM_WORKFLOW_IDENTITY_MISMATCH',
          })
          throw syncConflict(`所填平台工作流与“${localWorkflow.name}”不属于同一项目或元数据不一致；未建立关联。`)
        }
        platformWorkflow = candidate
        platformWorkflowId = candidate.id
        baselineRevision = candidate.revision
        activePlatformWorkflowId = platformWorkflowId
        activePlatformWorkflowBaseline = baselineRevision
        syncState = await saveLocalWorkflowSyncState(projectId, summary.id, {
          status: 'pending',
          platform_workflow_id: platformWorkflowId,
          synced_revision: baselineRevision,
          source_revision: localWorkflow.revision,
          error_code: null,
        })
      } else {
        try {
          platformWorkflow = await createProjectWorkflow(
            config,
            platformProjectId,
            localWorkflow.name,
            localWorkflow.description,
          )
          platformWorkflowId = platformWorkflow.id
          baselineRevision = platformWorkflow.revision
          activePlatformWorkflowId = platformWorkflowId
          activePlatformWorkflowBaseline = baselineRevision
          // Save the remote ID immediately so an interrupted graph update resumes in place.
          syncState = await saveLocalWorkflowSyncState(projectId, summary.id, {
            status: 'pending',
            platform_workflow_id: platformWorkflowId,
            synced_revision: baselineRevision,
            source_revision: localWorkflow.revision,
            error_code: null,
          })
        } catch (error) {
          if (createOutcomeNeedsReview(error)) {
            await saveLocalWorkflowSyncState(projectId, summary.id, { status: 'needs_review', error_code: errorCode(error) })
            throw new LocalProjectSyncError(
              `工作流“${localWorkflow.name}”的创建结果不确定。检查平台项目后再决定是否重试。`,
              'WORKFLOW_CREATE_OUTCOME_UNCONFIRMED',
              'needs_review',
            )
          }
          throw error
        }
      }

      if (!platformWorkflowId) throw new Error('平台工作流创建响应缺少标识。')
      if (platformWorkflow.project_id !== platformProjectId) {
        await saveLocalWorkflowSyncState(projectId, summary.id, {
          status: 'conflict',
          platform_workflow_id: platformWorkflowId,
          error_code: 'PLATFORM_OWNER_MISMATCH',
        })
        throw syncConflict(`平台工作流“${localWorkflow.name}”不属于此项目副本；已停止覆盖。`)
      }

      if (workflowMatchesLocal(platformWorkflow, localWorkflow)) {
        syncState = await saveLocalWorkflowSyncState(projectId, summary.id, {
          status: 'synced',
          platform_workflow_id: platformWorkflowId,
          synced_revision: platformWorkflow.revision,
          source_revision: localWorkflow.revision,
          error_code: null,
        })
        unchangedWorkflows += 1
      } else {
        if (baselineRevision === null || platformWorkflow.revision !== baselineRevision) {
          await saveLocalWorkflowSyncState(projectId, summary.id, {
            status: 'conflict',
            platform_workflow_id: platformWorkflowId,
            error_code: 'PLATFORM_REVISION_MOVED',
          })
          throw syncConflict(`平台工作流“${localWorkflow.name}”已在本机上次同步后发生变化；已保留双方内容。`)
        }
        try {
          const saved = await saveWorkflowDraft(config, {
            id: platformWorkflow.id,
            revision: platformWorkflow.revision,
            name: localWorkflow.name,
            description: localWorkflow.description,
            graph: localWorkflow.graph,
          })
          syncState = await saveLocalWorkflowSyncState(projectId, summary.id, {
            status: 'synced',
            platform_workflow_id: platformWorkflowId,
            synced_revision: saved.revision,
            source_revision: localWorkflow.revision,
            error_code: null,
          })
          synchronizedWorkflows += 1
        } catch (error) {
          const isConflict = error instanceof WorkflowApiError && error.status === 409
          await saveLocalWorkflowSyncState(projectId, summary.id, {
            status: isConflict ? 'conflict' : 'failed',
            platform_workflow_id: platformWorkflowId,
            error_code: errorCode(error),
          })
          if (isConflict) throw syncConflict(`平台工作流“${localWorkflow.name}”的修订发生变化；已保留双方内容。`)
          throw error
        }
      }
      completed += 1
      activeWorkflowId = null
      activePlatformWorkflowId = null
      activePlatformWorkflowBaseline = null
    }

    syncState = await saveLocalProjectSyncState(projectId, {
      status: 'synced',
      platform_project_id: platformProjectId,
      error_code: null,
    })
    if (syncState.status !== 'synced') {
      throw new LocalProjectSyncError(
        '同步期间本机新增或修改了工作流；已保存的部分仍在平台，继续同步即可补齐。',
        'LOCAL_WORKFLOW_CHANGED_DURING_SYNC',
        'partial',
      )
    }
    progress('平台副本已同步；本机项目和数据仍保留在此设备。')
    return { platformProjectId, synchronizedWorkflows, unchangedWorkflows }
  } catch (error) {
    let latestState = await getLocalProjectSyncState(projectId).catch(() => syncState)
    if (activeWorkflowId) {
      const activeState = latestState.workflows.find((item) => item.workflow_id === activeWorkflowId)
      if (activeState?.status === 'pending') {
        await saveLocalWorkflowSyncState(projectId, activeWorkflowId, {
          status: 'failed',
          ...(activePlatformWorkflowId ? { platform_workflow_id: activePlatformWorkflowId } : {}),
          ...(activePlatformWorkflowBaseline !== null ? { synced_revision: activePlatformWorkflowBaseline } : {}),
          error_code: errorCode(error),
        }).catch((stateError) => console.error('保存工作流同步失败状态也失败。', stateError))
        latestState = await getLocalProjectSyncState(projectId).catch(() => latestState)
      }
    }
    const hasUncertain = latestState.status === 'needs_review' || latestState.workflows.some((item) => item.status === 'needs_review')
    const hasConflict = latestState.status === 'conflict' || latestState.workflows.some((item) => item.status === 'conflict') ||
      error instanceof LocalProjectSyncError && error.status === 'conflict'
    const status = hasUncertain ? 'needs_review' : hasConflict ? 'conflict' : platformProjectId ? 'partial' : 'failed'
    await saveLocalProjectSyncState(projectId, {
      status,
      ...(platformProjectId ? { platform_project_id: platformProjectId } : {}),
      error_code: errorCode(error),
    }).catch((stateError) => {
      console.error('保存项目同步失败状态也失败。', stateError)
    })
    if (error instanceof LocalProjectSyncError) throw error
    throw new LocalProjectSyncError(
      '同步未完成。本机项目、工作流和文件保持不变；可查看失败状态后继续。',
      errorCode(error),
      status,
    )
  }
}
