import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  beginLocalProjectSync: vi.fn(),
  getLocalProject: vi.fn(),
  getLocalProjectSyncState: vi.fn(),
  listLocalProjectWorkflows: vi.fn(),
  getLocalWorkflow: vi.fn(),
  saveLocalProjectSyncState: vi.fn(),
  saveLocalWorkflowSyncState: vi.fn(),
  createProject: vi.fn(),
  getProject: vi.fn(),
  createProjectWorkflow: vi.fn(),
  getWorkflow: vi.fn(),
  saveWorkflowDraft: vi.fn(),
}))

vi.mock('./localRuntime', () => ({
  ...api,
  LocalRuntimeApiError: class LocalRuntimeApiError extends Error {
    readonly code: string
    readonly status: number
    constructor(code: string, status: number) {
      super(code)
      this.code = code
      this.status = status
    }
  },
}))

vi.mock('./projects', () => ({
  ...api,
  ProjectApiError: class ProjectApiError extends Error {
    readonly status: number
    constructor(status: number) {
      super(`Project API ${status}`)
      this.status = status
    }
  },
}))

vi.mock('./workflows', () => ({
  ...api,
  WorkflowApiError: class WorkflowApiError extends Error {
    readonly status: number
    readonly code: string
    constructor(status: number, code: string) {
      super(code)
      this.status = status
      this.code = code
    }
  },
}))

import { LocalProjectSyncError, syncLocalProjectToPlatform } from './localProjectSync'
import { WorkflowApiError } from './workflows'

const config = { baseUrl: 'http://platform.test', token: 'test-token' }
const projectId = 'local-project-1'
const workflowId = 'local-workflow-1'
const emptyGraph = { schema_version: 'ict.workflow.v1', nodes: [], edges: [] }
const localGraph = {
  schema_version: 'ict.workflow.v1',
  nodes: [{
    id: 'csv-source',
    type: 'ict.data.csv_artifact_source',
    position: { x: 0, y: 0 },
    data: { artifact_id: 'local-artifact-1' },
  }],
  edges: [],
}
const localProject = {
  id: projectId,
  name: '本机项目',
  domain: '数据分析',
  description: '离线研究草稿',
}
const localWorkflow = {
  id: workflowId,
  project_id: projectId,
  name: '本机工作流',
  description: 'CSV 探索流程',
  revision: 3,
  graph: localGraph,
}

let syncState: {
  project_id: string
  status: string
  platform_project_id: string | null
  error_code: string | null
  updated_at: string | null
  workflows: Array<{
    workflow_id: string
    status: string
    platform_workflow_id: string | null
    synced_revision: number | null
    source_revision: number | null
    error_code: string | null
    updated_at: string | null
  }>
}

function cloneState() {
  return JSON.parse(JSON.stringify(syncState))
}

function updateWorkflowState(id: string, update: Record<string, unknown>) {
  const item = syncState.workflows.find((workflow) => workflow.workflow_id === id)
  if (!item) throw new Error(`Missing local workflow sync state: ${id}`)
  Object.assign(item, update)
  return cloneState()
}

beforeEach(() => {
  vi.clearAllMocks()
  syncState = {
    project_id: projectId,
    status: 'local_only',
    platform_project_id: null,
    error_code: null,
    updated_at: null,
    workflows: [{
      workflow_id: workflowId,
      status: 'local_only',
      platform_workflow_id: null,
      synced_revision: null,
      source_revision: null,
      error_code: null,
      updated_at: null,
    }],
  }

  api.getLocalProject.mockResolvedValue(localProject)
  api.listLocalProjectWorkflows.mockResolvedValue([localWorkflow])
  api.getLocalWorkflow.mockResolvedValue(localWorkflow)
  api.getLocalProjectSyncState.mockImplementation(async () => cloneState())
  api.beginLocalProjectSync.mockImplementation(async (_id: string, allowPendingRetry: boolean) => {
    if (syncState.status === 'pending' && !allowPendingRetry) {
      const { LocalRuntimeApiError } = await import('./localRuntime')
      throw new LocalRuntimeApiError(409, 'LOCAL_SYNC_ALREADY_RUNNING')
    }
    syncState.status = 'pending'
    return cloneState()
  })
  api.saveLocalProjectSyncState.mockImplementation(async (_id: string, update: Record<string, unknown>) => {
    Object.assign(syncState, update)
    if (update.platform_project_id) syncState.platform_project_id = String(update.platform_project_id)
    if (update.status === 'synced' && syncState.workflows.some((workflow) => workflow.status !== 'synced')) {
      syncState.status = 'partial'
    }
    return cloneState()
  })
  api.saveLocalWorkflowSyncState.mockImplementation(async (_projectId: string, id: string, update: Record<string, unknown>) => {
    return updateWorkflowState(id, update)
  })
})

afterEach(() => vi.clearAllMocks())

describe('syncLocalProjectToPlatform', () => {
  it('creates a private project copy and syncs only project metadata and workflow definition', async () => {
    api.createProject.mockResolvedValue({ id: 'platform-project-1' })
    api.createProjectWorkflow.mockResolvedValue({
      id: 'platform-workflow-1',
      project_id: 'platform-project-1',
      name: localWorkflow.name,
      description: localWorkflow.description,
      revision: 1,
      graph: emptyGraph,
    })
    api.saveWorkflowDraft.mockResolvedValue({ revision: 2 })

    const result = await syncLocalProjectToPlatform(config, projectId, { confirmUncertainRetry: false })

    expect(result).toEqual({ platformProjectId: 'platform-project-1', synchronizedWorkflows: 1, unchangedWorkflows: 0 })
    expect(api.createProject).toHaveBeenCalledWith(config, {
      name: localProject.name,
      domain: localProject.domain,
      description: localProject.description,
    })
    expect(api.createProjectWorkflow).toHaveBeenCalledWith(
      config,
      'platform-project-1',
      localWorkflow.name,
      localWorkflow.description,
    )
    expect(api.saveWorkflowDraft).toHaveBeenCalledWith(config, {
      id: 'platform-workflow-1',
      revision: 1,
      name: localWorkflow.name,
      description: localWorkflow.description,
      graph: localGraph,
    })
    expect(api.saveLocalProjectSyncState).toHaveBeenLastCalledWith(projectId, {
      status: 'synced',
      platform_project_id: 'platform-project-1',
      error_code: null,
    })

    const platformPayloads = JSON.stringify({
      projectMetadata: api.createProject.mock.calls.map(([, body]) => body),
      workflowMetadata: api.createProjectWorkflow.mock.calls.map(([, ...body]) => body),
      workflowDefinitions: api.saveWorkflowDraft.mock.calls.map(([, body]) => body),
    })
    expect(platformPayloads).not.toContain('test-token')
    expect(platformPayloads).not.toContain('run_id')
    expect(platformPayloads).not.toContain('report_content')
    expect(platformPayloads).not.toContain('file_bytes')
    expect(platformPayloads).toContain('local-artifact-1')
  })

  it('resumes a partial sync using the saved remote IDs without creating duplicates', async () => {
    syncState = {
      ...syncState,
      status: 'partial',
      platform_project_id: 'platform-project-1',
      workflows: [{
        ...syncState.workflows[0],
        status: 'failed',
        platform_workflow_id: 'platform-workflow-1',
        synced_revision: 1,
        source_revision: 3,
        error_code: 'HTTP_503',
      }],
    }
    api.getProject.mockResolvedValue({ visibility: 'private' })
    api.getWorkflow.mockResolvedValue({
      id: 'platform-workflow-1',
      project_id: 'platform-project-1',
      name: localWorkflow.name,
      description: localWorkflow.description,
      revision: 1,
      graph: emptyGraph,
    })
    api.saveWorkflowDraft.mockResolvedValue({ revision: 2 })

    const result = await syncLocalProjectToPlatform(config, projectId, { confirmUncertainRetry: false })

    expect(result.synchronizedWorkflows).toBe(1)
    expect(api.createProject).not.toHaveBeenCalled()
    expect(api.createProjectWorkflow).not.toHaveBeenCalled()
    expect(api.getWorkflow).toHaveBeenCalledWith(config, 'platform-workflow-1')
    expect(api.saveLocalProjectSyncState).toHaveBeenLastCalledWith(projectId, {
      status: 'synced',
      platform_project_id: 'platform-project-1',
      error_code: null,
    })
  })

  it('stops on a moved platform revision and keeps the local draft without overwriting', async () => {
    syncState = {
      ...syncState,
      status: 'synced',
      platform_project_id: 'platform-project-1',
      workflows: [{
        ...syncState.workflows[0],
        status: 'synced',
        platform_workflow_id: 'platform-workflow-1',
        synced_revision: 1,
        source_revision: 2,
      }],
    }
    api.getProject.mockResolvedValue({ visibility: 'private' })
    api.getWorkflow.mockResolvedValue({
      id: 'platform-workflow-1',
      project_id: 'platform-project-1',
      name: '平台侧工作流',
      description: '平台已更新',
      revision: 2,
      graph: emptyGraph,
    })

    await expect(syncLocalProjectToPlatform(config, projectId, { confirmUncertainRetry: false }))
      .rejects.toMatchObject<Partial<LocalProjectSyncError>>({ code: 'PLATFORM_REVISION_MOVED', status: 'conflict' })

    expect(api.saveWorkflowDraft).not.toHaveBeenCalled()
    expect(api.saveLocalWorkflowSyncState).toHaveBeenCalledWith(projectId, workflowId, expect.objectContaining({
      status: 'conflict',
      error_code: 'PLATFORM_REVISION_MOVED',
    }))
    expect(syncState.status).toBe('conflict')
  })

  it('requires explicit review before retrying an uncertain create outcome', async () => {
    syncState.status = 'needs_review'
    syncState.error_code = 'PROJECT_CREATE_OUTCOME_UNCONFIRMED'

    await expect(syncLocalProjectToPlatform(config, projectId, { confirmUncertainRetry: false }))
      .rejects.toMatchObject<Partial<LocalProjectSyncError>>({ code: 'SYNC_OUTCOME_NEEDS_REVIEW', status: 'needs_review' })

    expect(api.beginLocalProjectSync).not.toHaveBeenCalled()
    expect(api.createProject).not.toHaveBeenCalled()
    expect(api.createProjectWorkflow).not.toHaveBeenCalled()
  })

  it('does not retry an ambiguous workflow create until explicitly confirmed', async () => {
    syncState = {
      ...syncState,
      status: 'needs_review',
      platform_project_id: 'platform-project-1',
      workflows: [{
        ...syncState.workflows[0],
        status: 'needs_review',
        error_code: 'WORKFLOW_CREATE_OUTCOME_UNCONFIRMED',
      }],
    }

    await expect(syncLocalProjectToPlatform(config, projectId, { confirmUncertainRetry: false }))
      .rejects.toMatchObject<Partial<LocalProjectSyncError>>({ code: 'SYNC_OUTCOME_NEEDS_REVIEW', status: 'needs_review' })

    expect(api.beginLocalProjectSync).not.toHaveBeenCalled()
    expect(api.createProjectWorkflow).not.toHaveBeenCalled()
  })

  it('records a partial failure and can safely retry when the platform did not commit the draft', async () => {
    api.createProject.mockResolvedValue({ id: 'platform-project-1' })
    api.createProjectWorkflow.mockResolvedValue({
      id: 'platform-workflow-1',
      project_id: 'platform-project-1',
      name: localWorkflow.name,
      description: localWorkflow.description,
      revision: 1,
      graph: emptyGraph,
    })
    api.saveWorkflowDraft
      .mockRejectedValueOnce(new WorkflowApiError(503, 'REMOTE_UNAVAILABLE'))
      .mockResolvedValueOnce({ revision: 2 })

    await expect(syncLocalProjectToPlatform(config, projectId, { confirmUncertainRetry: false }))
      .rejects.toMatchObject<Partial<LocalProjectSyncError>>({ status: 'partial' })
    expect(syncState.status).toBe('partial')
    expect(syncState.platform_project_id).toBe('platform-project-1')
    expect(syncState.workflows[0].platform_workflow_id).toBe('platform-workflow-1')

    api.getProject.mockResolvedValue({ visibility: 'private' })
    api.getWorkflow.mockResolvedValue({
      id: 'platform-workflow-1',
      project_id: 'platform-project-1',
      name: localWorkflow.name,
      description: localWorkflow.description,
      revision: 1,
      graph: emptyGraph,
    })

    const result = await syncLocalProjectToPlatform(config, projectId, { confirmUncertainRetry: false })

    expect(result.synchronizedWorkflows).toBe(1)
    expect(api.createProject).toHaveBeenCalledTimes(1)
    expect(api.createProjectWorkflow).toHaveBeenCalledTimes(1)
    expect(api.saveWorkflowDraft).toHaveBeenCalledTimes(2)
    expect(syncState.status).toBe('synced')
  })
})
