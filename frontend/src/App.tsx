import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { createProject, getProject, listProjects, ProjectApiError, type ApiConfig, type DatasetResource, type ProjectCreateInput, type ProjectDetail, type ProjectListItem, type ProjectSummary, type TemplateContract } from './api/projects'
import { createReproductionTask, getReproductionTask, listReproductionTasks, ReproductionApiError, type ReproductionKind, type ReproductionStatus, type ReproductionTask, type ReproductionTaskCreateInput } from './api/reproductions'
import { getSyntheticDatasetQualityReport, QualityReportApiError, type SyntheticDatasetQualityReport } from './api/qualityReports'
import { listTemplateCatalog } from './api/templates'
import { createProjectWorkflow, createReproductionWorkflow, createWorkflowVersion, getWorkflow, getWorkflowVersion, limitWorkflowParameterValue, listProjectWorkflows, listReproductionWorkflows, listWorkflowComponents, listWorkflowVersions, restoreWorkflowVersion, saveWorkflowDraft, validateWorkflow, WorkflowApiError, type WorkflowComponent, type WorkflowComponentPort, type WorkflowDetail, type WorkflowGraph, type WorkflowSummary, type WorkflowValidation, type WorkflowVersionDetail, type WorkflowVersionSummary } from './api/workflows'
import { recoverLocalWorkflowRun, cancelLocalWorkflowRun, createLocalProject, createLocalProjectWorkflow, createLocalProjectWorkflowFromTemplate, createLocalReproductionTask, createLocalReproductionWorkflow, getLocalCrossrefMetadataReport, getLocalCsvDescriptiveSummaryReport, getLocalCsvFolderQualityReport, getLocalCsvPreflightReport, getLocalProject, getLocalProjectSyncState, getLocalReproductionTask, getLocalRuntimeHealth, getLocalWorkflow, getLocalWorkflowDraft, getLocalWorkflowRun, importLocalCsv, listLocalProjectWorkflows, listLocalProjects, listLocalReproductionTasks, listLocalReproductionWorkflows, listLocalWorkflowComponents, listLocalWorkflowRuns, listLocalWorkflowTemplates, LocalRuntimeApiError, saveLocalWorkflowDraft, submitLocalWorkflowRun, validateLocalWorkflow, type LocalArtifactHandle, type LocalCrossrefMetadataReport, type LocalCsvDescriptiveSummaryReport, type LocalCsvFolderQualityReport, type LocalCsvPreflightReport, type LocalProject, type LocalProjectDetail, type LocalProjectSyncState, type LocalRuntimeHealth, type LocalSyncStatus, type LocalWorkflowRunDetail, type LocalWorkflowRunSummary, type LocalWorkflowSummary, type LocalWorkflowTemplate } from './api/localRuntime'
import type { LocalWorkflowTemplatePreview, LocalWorkflowTemplatePreviewNode } from './api/localRuntime'
import { LocalProjectSyncError, syncLocalProjectToPlatform } from './api/localProjectSync'
import { workflowRunErrorDetails } from './workflowRunErrors'
import { minimalViewportPanForNode } from './workflowViewport'
import { isWorkflowRevisionConflict, syncConflictedWorkflowToPlatform, WorkflowRevisionMovedError } from './workflowConflictSync'
import { workflowDraftSnapshot } from './workflowDraft'
import { addEdge, Background, BackgroundVariant, Controls, Handle, MiniMap, Panel, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesInitialized, useNodesState, useReactFlow, type Connection, type Edge, type FinalConnectionState, type Node, type NodeProps, type OnEdgesChange, type OnNodesChange, type XYPosition } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import './App.css'
import { WorkbenchHero } from './visual/WorkbenchHero'

type Page = 'workbench' | 'templates' | 'agent' | 'settings'
type DeskTab = 'projects' | 'reproductions'
type SettingsTab = 'profile' | 'preferences' | 'notifications' | 'security' | 'workspace' | 'service'
type NotificationPreferenceKey = 'runFailed' | 'runCompleted' | 'approvalRequired' | 'reviewRequired'
type LocalPreferences = {
  density: 'comfortable' | 'compact'
  reduceMotion: boolean
  notifications: Record<NotificationPreferenceKey, boolean>
}
type ProjectTab = 'overview' | 'workflows' | 'resources' | 'settings'
type IconName = 'home' | 'template' | 'repo' | 'agent' | 'compute' | 'user' | 'help' | 'folder' | 'workflow' | 'book' | 'database' | 'users' | 'server' | 'bell' | 'clock' | 'plus' | 'arrow' | 'refresh' | 'shield' | 'search' | 'file' | 'attachment' | 'send' | 'sliders' | 'key' | 'close' | 'panel' | 'map' | 'layout' | 'check'
type State<T> = { status: 'idle' } | { status: 'loading' } | { status: 'error'; message: string; code?: string; unavailable?: boolean } | { status: 'ready'; data: T; cached?: boolean; partial?: boolean; localUnsynced?: boolean }
type Status = 'disconnected' | 'connecting' | 'connected' | 'error'

function localSyncStatusLabel(status: LocalSyncStatus): string {
  switch (status) {
    case 'pending': return '待同步'
    case 'partial': return '部分同步'
    case 'synced': return '平台副本已同步'
    case 'failed': return '同步失败'
    case 'conflict': return '平台版本有冲突'
    case 'needs_review': return '待核对平台创建状态'
    default: return '仅保存在此设备'
  }
}

function displayPlatformOrigin(baseUrl: string): string {
  try { return new URL(baseUrl).origin } catch { return baseUrl.trim() }
}
type TemplateCatalogItem = { contract: TemplateContract }
type AgentProjectContext = Pick<ProjectSummary, 'id' | 'name'>
type AgentWorkflowContext = { id: string; name: string }
type AgentDatasetContext = Pick<DatasetResource, 'id' | 'version'>
type WorkflowOwnerContext = { type: 'project' | 'reproduction'; id: string; name: string }
type RecentWorkflowReference = { projectId: string; workflowId: string; openedAt: string }
type RecentWorkflowRow = { project: Pick<ProjectSummary, 'id' | 'name'>; workflow: Pick<WorkflowSummary, 'id' | 'project_id' | 'name'>; openedAt: string }
type DashboardLocalRunRow = { project: Pick<LocalProject, 'id' | 'name'>; workflow: Pick<LocalWorkflowSummary, 'id' | 'project_id' | 'name'>; run: LocalWorkflowRunSummary }
type WorkflowComponentEntry = {
  id: string
  category: string
  title: string
  description: string
  icon: IconName
  definition?: WorkflowComponent
}
type WorkflowNodeData = {
  category: string
  title: string
  description: string
  component_id?: string
  component_version?: string
  input_ports?: WorkflowComponentPort[]
  output_ports?: WorkflowComponentPort[]
  parameter_schema?: WorkflowComponent['parameter_schema']
  parameters?: Record<string, unknown>
  executor_binding?: string | null
  execution_target?: WorkflowComponent['execution_target']
  execution_available?: boolean
  execution_blockers?: string[]
  run_status?: string | null
  previewTopTarget?: boolean
  previewBottomSource?: boolean
  [key: string]: unknown
}
type WorkflowNode = Node<WorkflowNodeData, 'research'>
type WorkflowEditorSnapshot = { name: string; description: string; nodes: WorkflowNode[]; edges: Edge[] }
type WorkflowRevisionSnapshot = Pick<WorkflowDetail, 'revision' | 'current_version' | 'name' | 'description' | 'graph'>
type WorkflowRevisionConflict = { workflowId: string; local: WorkflowRevisionSnapshot; platform: WorkflowRevisionSnapshot }
type WorkflowCanvasFocus = { kind: 'node' | 'edge'; id: string; request: number } | null
type WorkflowDockTab = '校验' | '运行历史' | '日志' | '产物'
const workflowDockTabs: Array<{ id: string; label: WorkflowDockTab }> = [
  { id: 'validation', label: '校验' },
  { id: 'history', label: '运行历史' },
  { id: 'logs', label: '日志' },
  { id: 'artifacts', label: '产物' },
]

const localPreferencesKey = 'ict-research-workbench-preferences'
const localTemplateFavoritesKey = 'ict-research-workbench-template-favorites'
const localWorkflowComponentFavoritesKey = 'ict-research-workbench-workflow-component-favorites'
const localRecentWorkflowComponentIdsKey = 'ict-research-workbench-recent-workflow-components'
const localRecentProjectsKey = 'ict-research-workbench-recent-projects'
const localRecentWorkflowsKey = 'ict-research-workbench-recent-workflows'
const localProjectListCacheKey = 'ict-research-workbench-project-list-cache'
const localProjectDetailCachePrefix = 'ict-research-workbench-project-detail:'
const localProjectWorkflowCachePrefix = 'ict-research-workbench-project-workflows:'
const localProjectLocalListCacheKey = 'ict-research-workbench-local-project-list-cache'
const localProjectLocalDetailCachePrefix = 'ict-research-workbench-local-project-detail:'
const localWorkflowDetailCachePrefix = 'ict-research-workbench-workflow-detail:'
const localWorkflowPendingSyncPrefix = 'ict-research-workbench-workflow-pending-sync:'
const defaultLocalPreferences: LocalPreferences = {
  density: 'comfortable',
  reduceMotion: false,
  notifications: { runFailed: true, runCompleted: true, approvalRequired: true, reviewRequired: true },
}

function readLocalCache<T>(key: string, validate: (value: unknown) => value is T, description: string): T | null {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const value: unknown = JSON.parse(raw)
    return validate(value) ? value : null
  } catch (error) {
    console.error(`读取本机${description}缓存失败。`, error)
    return null
  }
}

function writeLocalCache(key: string, value: unknown, description: string): boolean {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
    return true
  } catch (error) {
    console.error(`保存本机${description}缓存失败。`, error)
    return false
  }
}

function isProjectListCache(value: unknown): value is ProjectListItem[] {
  return Array.isArray(value) && value.every((candidate) => {
    if (typeof candidate !== 'object' || candidate === null) return false
    const item = candidate as Record<string, unknown>
    return typeof item.id === 'string' && typeof item.name === 'string' && typeof item.domain === 'string' &&
      typeof item.role === 'string' && (item.visibility === 'private' || item.visibility === 'demo') &&
      typeof item.created_at === 'string' && typeof item.description === 'string' &&
      Number.isInteger(item.workflow_count) && Number.isInteger(item.dataset_version_count)
  })
}

function isLocalProjectListCache(value: unknown): value is LocalProject[] {
  const syncStates: LocalSyncStatus[] = ['local_only', 'pending', 'partial', 'synced', 'failed', 'conflict', 'needs_review']
  return isProjectListCache(value) && value.every((item) => {
    const localItem = item as LocalProject
    return localItem.source === 'local' && syncStates.includes(localItem.sync_state) &&
      (localItem.platform_project_id === undefined || localItem.platform_project_id === null || typeof localItem.platform_project_id === 'string')
  })
}

function cachedLocalProjectList(): LocalProject[] | null {
  return readLocalCache(localProjectLocalListCacheKey, isLocalProjectListCache, '本机项目目录')
}

function cacheLocalProjectList(projects: LocalProject[]): void {
  writeLocalCache(localProjectLocalListCacheKey, projects, '本机项目目录')
}

function isLocalProjectDetailCache(value: unknown): value is LocalProjectDetail {
  if (!isProjectDetailCache(value)) return false
  const item = value as LocalProjectDetail
  return item.source === 'local' && typeof item.updated_at === 'string' &&
    Number.isInteger(item.workflow_count) && Number.isInteger(item.dataset_version_count) &&
    (item.sync_state === undefined || ['local_only', 'pending', 'partial', 'synced', 'failed', 'conflict', 'needs_review'].includes(item.sync_state))
}

function cacheLocalProjectDetail(project: LocalProjectDetail): void {
  writeLocalCache(`${localProjectLocalDetailCachePrefix}${encodeURIComponent(project.id)}`, project, '本机项目详情')
}

function cachedLocalProjectDetail(projectId: string): LocalProjectDetail | null {
  const value = readLocalCache(`${localProjectLocalDetailCachePrefix}${encodeURIComponent(projectId)}`, isLocalProjectDetailCache, '本机项目详情')
  return value?.id === projectId ? value : null
}

function cachedLocalProjectSummaryDetail(projectId: string, currentProject?: LocalProject | null): LocalProjectDetail | null {
  // Prefer the directory item already loaded by the workbench when browser storage is unavailable.
  const project = currentProject?.id === projectId
    ? currentProject
    : cachedLocalProjectList()?.find((item) => item.id === projectId)
  if (!project) return null
  // The list snapshot can open the project shell, but it does not claim to contain data or workflow details.
  return {
    ...project,
    updated_at: project.last_activity_at ?? project.created_at,
    datasets: [],
    pipeline_templates: [],
  }
}

function canFallbackToLocalProjectCache(error: unknown): boolean {
  // Keep authoritative client errors such as 403/404 visible instead of reviving stale project data.
  return !(error instanceof LocalRuntimeApiError) || error.status >= 500
}

function cachedProjectList(): ProjectListItem[] | null {
  return readLocalCache(localProjectListCacheKey, isProjectListCache, '项目列表')
}

function isProjectDetailCache(value: unknown): value is ProjectDetail {
  if (typeof value !== 'object' || value === null) return false
  const item = value as Record<string, unknown>
  return typeof item.id === 'string' && typeof item.name === 'string' && typeof item.domain === 'string' &&
    typeof item.role === 'string' && (item.visibility === 'private' || item.visibility === 'demo') &&
    typeof item.created_at === 'string' && typeof item.description === 'string' &&
    Array.isArray(item.datasets) && Array.isArray(item.pipeline_templates)
}

function cachedProjectDetail(projectId: string): ProjectDetail | null {
  const value = readLocalCache(`${localProjectDetailCachePrefix}${encodeURIComponent(projectId)}`, isProjectDetailCache, '项目详情')
  return value?.id === projectId ? value : null
}

function cachedProjectSummaryDetail(projectId: string, currentProject?: ProjectListItem | null): ProjectDetail | null {
  // The visible directory item is already an authorized summary; do not require a second storage read to open it.
  const project = currentProject?.id === projectId
    ? currentProject
    : cachedProjectList()?.find((item) => item.id === projectId)
  if (!project) return null
  // The list snapshot contains only project-level metadata; keep the partial cache state visible in the UI.
  return { ...project, datasets: [], pipeline_templates: [] }
}

function canFallbackToPlatformProjectCache(error: unknown): boolean {
  // Do not use stale snapshots after an authoritative authorization or not-found response.
  return isPlatformServiceUnavailable(error)
}

function isPlatformServiceUnavailable(error: unknown, projectCatalogRequest = false): boolean {
  if (error instanceof ProjectApiError) {
    if (error.status === 401 || error.status === 403) return false
    if (error.status >= 500) return true
    // A missing project catalog route means the configured server is not a compatible platform API.
    // On a detail route, only a static-host HTML 404 is a routing failure; JSON 404 stays authoritative.
    return error.status === 404 && (projectCatalogRequest || error.responseContentType.toLowerCase().includes('text/html'))
  }
  return error instanceof TypeError
}

function isWorkflowDetailCache(value: unknown): value is WorkflowDetail {
  if (typeof value !== 'object' || value === null) return false
  const item = value as Record<string, unknown>
  if (typeof item.graph !== 'object' || item.graph === null) return false
  const graph = item.graph as Record<string, unknown>
  return typeof item.id === 'string' && typeof item.owner_type === 'string' && typeof item.owner_id === 'string' &&
    typeof item.name === 'string' && typeof item.description === 'string' &&
    Number.isInteger(item.revision) && Number.isInteger(item.current_version) &&
    typeof item.can_edit === 'boolean' && graph.schema_version === 'ict.workflow.v1' &&
    Array.isArray(graph.nodes) && Array.isArray(graph.edges)
}

function cachedWorkflowDetail(workflowId: string): WorkflowDetail | null {
  const value = readLocalCache(`${localWorkflowDetailCachePrefix}${encodeURIComponent(workflowId)}`, isWorkflowDetailCache, '工作流')
  return value?.id === workflowId ? value : null
}

function cachedProjectWorkflowDetail(projectId: string, workflowId: string): WorkflowDetail | null {
  // Only expose an offline canvas when its full cached graph belongs to this project.
  const workflow = cachedWorkflowDetail(workflowId)
  return workflow?.owner_type === 'project' && workflow.owner_id === projectId ? workflow : null
}

function cachedRecentWorkflowRows(references: RecentWorkflowReference[]): RecentWorkflowRow[] {
  const projects = cachedProjectList() ?? []
  return references.slice(0, 5).flatMap((reference) => {
    const projectFromList = projects.find((item) => item.id === reference.projectId && item.visibility === 'private')
    const projectFromDetail = cachedProjectDetail(reference.projectId)
    const projectName = projectFromList?.name ??
      (projectFromDetail?.visibility === 'private' ? projectFromDetail.name : null)
    const workflow = cachedWorkflowDetail(reference.workflowId)
    if (!projectName || !workflow || workflow.owner_type !== 'project' ||
        workflow.owner_id !== reference.projectId || workflow.project_id !== reference.projectId) return []
    return [{
      project: { id: reference.projectId, name: projectName },
      workflow: { id: workflow.id, project_id: workflow.project_id, name: workflow.name },
      openedAt: reference.openedAt,
    }]
  })
}

function workflowPendingPlatformSync(workflowId: string): boolean {
  try {
    return window.localStorage.getItem(`${localWorkflowPendingSyncPrefix}${encodeURIComponent(workflowId)}`) === 'true'
  } catch (error) {
    console.error('读取本机工作流同步状态失败。', error)
    return false
  }
}

function setWorkflowPendingPlatformSync(workflowId: string, pending: boolean): void {
  const key = `${localWorkflowPendingSyncPrefix}${encodeURIComponent(workflowId)}`
  try {
    if (pending) window.localStorage.setItem(key, 'true')
    else window.localStorage.removeItem(key)
  } catch (error) {
    console.error('保存本机工作流同步状态失败。', error)
  }
}

function cacheProjectWorkflows(projectId: string, workflows: WorkflowSummary[]): void {
  writeLocalCache(`${localProjectWorkflowCachePrefix}${encodeURIComponent(projectId)}`, workflows, '项目工作流列表')
}

function cachedProjectWorkflows(projectId: string): WorkflowSummary[] | null {
  const value = readLocalCache(`${localProjectWorkflowCachePrefix}${encodeURIComponent(projectId)}`, (candidate): candidate is WorkflowSummary[] =>
    Array.isArray(candidate) && candidate.every((entry) => {
      if (typeof entry !== 'object' || entry === null) return false
      const item = entry as Record<string, unknown>
      return typeof item.id === 'string' && typeof item.owner_type === 'string' && typeof item.owner_id === 'string' &&
        typeof item.name === 'string' && typeof item.description === 'string' &&
        Number.isInteger(item.revision) && Number.isInteger(item.current_version)
    }), '项目工作流列表')
  return value
}

function cachedLocalProjectWorkflows(projectId: string): WorkflowSummary[] | null {
  const value = cachedProjectWorkflows(projectId)
  return value && value.every((workflow) => workflow.owner_type === 'project' && workflow.owner_id === projectId) ? value : null
}

function readLocalPreferences(): LocalPreferences {
  try {
    const saved = JSON.parse(window.localStorage.getItem(localPreferencesKey) || '{}') as Partial<LocalPreferences>
    const savedNotifications = saved.notifications || defaultLocalPreferences.notifications
    return {
      density: saved.density === 'compact' ? 'compact' : 'comfortable',
      reduceMotion: saved.reduceMotion === true,
      notifications: {
        runFailed: savedNotifications.runFailed !== false,
        runCompleted: savedNotifications.runCompleted !== false,
        approvalRequired: savedNotifications.approvalRequired !== false,
        reviewRequired: savedNotifications.reviewRequired !== false,
      },
    }
  } catch (error) {
    console.warn('无法读取科研工作台的本地界面偏好，已使用默认设置。', error)
    return defaultLocalPreferences
  }
}

function readTemplateFavorites(): string[] {
  try {
    const saved: unknown = JSON.parse(window.localStorage.getItem(localTemplateFavoritesKey) || '[]')
    return Array.isArray(saved) ? saved.filter((id): id is string => typeof id === 'string') : []
  } catch (error) {
    console.error('读取本机模板收藏失败。', error)
    return []
  }
}

function readLocalWorkflowComponentIds(storageKey: string, label: string): string[] {
  try {
    const saved: unknown = JSON.parse(window.localStorage.getItem(storageKey) || '[]')
    if (!Array.isArray(saved)) return []
    return [...new Set(saved.filter((id): id is string => typeof id === 'string' && id.trim().length > 0))].slice(0, 20)
  } catch (error) {
    console.error(`读取本机${label}失败。`, error)
    return []
  }
}

function readLocalRecentProjectIds(): string[] {
  try {
    const saved: unknown = JSON.parse(window.localStorage.getItem(localRecentProjectsKey) || '[]')
    if (!Array.isArray(saved)) return []
    return [...new Set(saved.filter((id): id is string => typeof id === 'string' && id.trim().length > 0))].slice(0, 20)
  } catch (error) {
    console.error('读取本机最近打开项目记录失败。', error)
    return []
  }
}

function recentWorkflowIdentity(reference: Pick<RecentWorkflowReference, 'projectId' | 'workflowId'>): string {
  return reference.projectId + '\u0000' + reference.workflowId
}

function readLocalRecentWorkflowRefs(): RecentWorkflowReference[] {
  try {
    const saved: unknown = JSON.parse(window.localStorage.getItem(localRecentWorkflowsKey) || '[]')
    if (!Array.isArray(saved)) return []
    const seen = new Set<string>()
    const references: RecentWorkflowReference[] = []
    for (const item of saved) {
      if (typeof item !== 'object' || item === null || Array.isArray(item)) continue
      const value = item as Record<string, unknown>
      if (typeof value.projectId !== 'string' || !value.projectId.trim() ||
          typeof value.workflowId !== 'string' || !value.workflowId.trim() ||
          typeof value.openedAt !== 'string' || Number.isNaN(Date.parse(value.openedAt))) continue
      const reference = { projectId: value.projectId, workflowId: value.workflowId, openedAt: value.openedAt }
      const key = recentWorkflowIdentity(reference)
      if (seen.has(key)) continue
      seen.add(key)
      references.push(reference)
      if (references.length >= 20) break
    }
    return references
  } catch (error) {
    console.error('读取本机最近打开工作流记录失败。', error)
    return []
  }
}

const workflowComponents: WorkflowComponentEntry[] = [
  { id: 'data', category: '数据资源', title: '数据输入', description: '引用项目或任务中的数据版本', icon: 'database' },
  { id: 'literature-search', category: '文献与证据', title: '论文检索（示意）', description: '按研究主题查找并整理文献依据', icon: 'book' },
  { id: 'model-inference', category: '模型推理', title: '模型推理（示意）', description: '展示模型输入与输出信息的节点布局', icon: 'workflow' },
  { id: 'evaluation', category: '评价与比较', title: '结果评价', description: '关联指标与判定规则', icon: 'check' },
  { id: 'visualization', category: '可视化', title: '结果可视化', description: '组织图表和表格产物', icon: 'panel' },
  { id: 'output', category: '导出与报告', title: '文件输出', description: '整理报告和可追溯产物', icon: 'file' },
]

function workflowComponentIcon(category: string): IconName {
  if (category === '数据输入' || category === '数据处理') return 'database'
  if (category === '文献与证据') return 'book'
  if (category === '评价与比较') return 'check'
  if (category === '导出与报告') return 'file'
  return 'workflow'
}

function formatComponentResourceLimit(key: string, value: number | null): string {
  if (value === null) return '未设置'
  if (key === 'timeout_seconds') return `${value} 秒`
  if (key === 'cpu_millicores') return `${value} mCPU`
  if (key === 'memory_mb') return `${value} MB`
  return String(value)
}

function localCapabilityMessage(code: string): string {
  const messages: Record<string, string> = {
    LOCAL_EXECUTION_TARGET_UNAVAILABLE: '此节点需要网络或平台执行端。',
    NETWORK_EXECUTION_TARGET_UNAVAILABLE: '此节点没有可用的网络执行目标。',
    EXECUTION_TARGET_UNAVAILABLE: '此节点的网络或平台执行器当前不可用；它及依赖它的下游节点会阻断，独立本机分支仍可继续。',
    LOCAL_EXECUTOR_UNAVAILABLE: '本机没有此节点的已登记执行器。',
    NETWORK_EXECUTOR_UNAVAILABLE: '本机没有此网络节点的已登记执行器。',
    LOCAL_PERMISSION_UNAVAILABLE: '本机执行器没有组件声明所需的权限。',
    NETWORK_PERMISSION_UNAVAILABLE: '网络节点的访问权限未获批准。',
    NETWORK_DEPENDENCY_UNAVAILABLE: '本机缺少网络节点所需的精确版本依赖。',
    PLATFORM_EXECUTION_TARGET_UNAVAILABLE: '平台执行器尚未接入；此节点及其依赖下游会阻断。',
    COMPONENT_PERMISSION_INVALID: '组件权限声明格式无效。',
    COMPONENT_DEPENDENCY_INVALID: '组件依赖声明格式无效。',
    COMPONENT_DEPENDENCY_UNAVAILABLE: '组件依赖未安装、接口不兼容或版本不匹配。',
    ARTIFACT_AUTHORIZATION_REQUIRED: '输入文件缺少有效的本机授权记录，请重新确认并导入。',
    LOCAL_RESOURCE_BUDGET_EXCEEDED: '组件声明的资源需求超过本机准入上限。',
    LOCAL_INPUT_SIZE_LIMIT_EXCEEDED: '输入文件超过此组件的大小上限。',
    NETWORK_RATE_LIMITED: 'Crossref 公开服务已限流，请稍后再运行。',
    NETWORK_TIMEOUT: 'Crossref 请求超时；本机节点失败，其依赖下游会阻断。',
    NETWORK_UNAVAILABLE: '无法连接 Crossref；本机节点失败，其依赖下游会阻断。',
    CROSSREF_DOI_REQUIRED: '请在 Crossref 节点中填写 DOI。',
    CROSSREF_DOI_INVALID: 'DOI 格式无效，请检查 DOI 前缀和字符。',
    CROSSREF_DOI_NOT_FOUND: 'Crossref 中没有找到此 DOI。',
  }
  return messages[code] ?? `本机运行未启动（${code}）。请检查输出目标、本机依赖和运行时日志。`
}

function WorkflowRunErrorNotice({ code, className = '' }: { code: string; className?: string }) {
  const details = workflowRunErrorDetails(code)
  return <div className={`workflow-run-error ${className}`.trim()} role="group" aria-label={`运行问题：${details.reason}`}>
    <strong>{details.reason}</strong>
    <span>{details.impact}</span>
    <span>{details.nextStep}</span>
    <code>错误码：{code}</code>
  </div>
}

function componentUnavailableMessage(component: Pick<WorkflowComponent, 'execution_target' | 'execution_blockers'>): string {
  const blocker = component.execution_blockers?.[0]
  if (blocker) return localCapabilityMessage(blocker)
  if (component.execution_target === 'platform') return '需要平台执行端。'
  if (component.execution_target === 'network') return '需要网络连接；此组件只访问固定的公开 Crossref 元数据端点。'
  return '本机执行器未安装或不可用。'
}

function componentExecutionAvailabilityMessage(component: Pick<WorkflowComponent, 'execution_target' | 'execution_available' | 'execution_blockers'>): string {
  if (component.execution_target === 'platform') {
    return component.execution_available ? '平台执行器已接入；本机离线运行仍需要平台服务。' : '需要平台服务。'
  }
  if (component.execution_target === 'network') {
    return component.execution_available
      ? '固定 Crossref 执行器已接入；运行时会先请求你的确认，并只读取公开 DOI 元数据。'
      : componentUnavailableMessage(component)
  }
  return component.execution_available ? '本机执行器可用。' : componentUnavailableMessage(component)
}

function workflowNodeAvailability(data: WorkflowNodeData): { label: string; tone: 'local' | 'network' | 'platform' | 'blocked' | 'unknown'; message: string } | null {
  if (!data.component_id) return null
  if (typeof data.execution_available !== 'boolean' || !data.execution_target) {
    return { label: '状态待读取', tone: 'unknown', message: '组件目录读取后才能确认该节点的执行能力。' }
  }
  const execution = {
    execution_target: data.execution_target,
    execution_available: data.execution_available,
    execution_blockers: data.execution_blockers ?? [],
  }
  const label = data.execution_available
    ? data.execution_target === 'local' ? '本机可用' : data.execution_target === 'network' ? '需网络' : '需平台服务'
    : data.execution_target === 'platform' ? '平台未接入' : data.execution_target === 'network' ? '网络不可用' : '本机不可用'
  const tone = !data.execution_available
    ? 'blocked'
    : data.execution_target === 'local' ? 'local' : data.execution_target === 'network' ? 'network' : 'platform'
  return { label, tone, message: componentExecutionAvailabilityMessage(execution) }
}

function workflowNodeAvailabilityShortLabel(tone: NonNullable<ReturnType<typeof workflowNodeAvailability>>['tone']): string {
  switch (tone) {
    case 'local': return '本机✓'
    case 'network': return '需网络'
    case 'platform': return '需平台'
    case 'blocked': return '不可用'
    case 'unknown': return '待读'
  }
}

function componentExecutionTargetLabel(target: WorkflowComponent['execution_target']): string {
  if (target === 'local') return '本机'
  if (target === 'network') return '网络'
  return '平台'
}

// Static nodes are layout aids; their placeholder labels do not imply registered components.
const workflowEditorPreviewNodes: WorkflowNode[] = [
  { id: 'preview-data', type: 'research', position: { x: 80, y: 100 }, data: { category: '数据资源', title: '数据输入', description: '引用项目或任务中的数据版本' } },
  { id: 'preview-literature', type: 'research', position: { x: 80, y: 340 }, data: { category: '文献与证据', title: '论文检索（示意）', description: '按研究主题查找并整理文献依据' } },
  { id: 'preview-inference', type: 'research', position: { x: 380, y: 100 }, data: { category: '模型推理', title: '模型推理（示意）', description: '展示模型输入与输出信息的节点布局', previewBottomSource: true }, selected: true },
  { id: 'preview-evaluation', type: 'research', position: { x: 380, y: 340 }, data: { category: '评价与比较', title: '结果评价', description: '关联指标与判定规则', previewTopTarget: true } },
  { id: 'preview-visualization', type: 'research', position: { x: 680, y: 100 }, data: { category: '可视化', title: '结果可视化', description: '组织图表和表格产物', previewBottomSource: true } },
  { id: 'preview-output', type: 'research', position: { x: 680, y: 340 }, data: { category: '导出与报告', title: '文件输出', description: '整理报告和可追溯产物', previewTopTarget: true } },
]
const workflowEditorPreviewEdges: Edge[] = [
  { id: 'preview-data-inference', source: 'preview-data', target: 'preview-inference', type: 'smoothstep' },
  { id: 'preview-literature-evaluation', source: 'preview-literature', target: 'preview-evaluation', type: 'smoothstep' },
  { id: 'preview-inference-evaluation', source: 'preview-inference', sourceHandle: 'preview-bottom-source', target: 'preview-evaluation', targetHandle: 'preview-top-target', type: 'smoothstep' },
  { id: 'preview-evaluation-visualization', source: 'preview-evaluation', target: 'preview-visualization', type: 'smoothstep' },
  { id: 'preview-visualization-output', source: 'preview-visualization', sourceHandle: 'preview-bottom-source', target: 'preview-output', targetHandle: 'preview-top-target', type: 'smoothstep' },
]
const desktopVerticalPreviewEdgeIds = new Set(['preview-inference-evaluation', 'preview-visualization-output'])

// This fixture exists only so the unconnected editor layout can be reviewed in development.
const workflowEditorPreviewProject: ProjectDetail = {
  id: 'local-ui-preview',
  name: '工作流编辑器界面预览',
  domain: '本地预览',
  role: '预览',
  visibility: 'private',
  created_at: '',
  description: '此预览不关联真实项目，不保存工作流或运行记录。',
  datasets: [],
  pipeline_templates: [],
}

function serializeWorkflowGraph(nodes: WorkflowNode[], edges: Edge[]): WorkflowGraph {
  // Persist component identity and user configuration; registry contracts are reloaded from the server.
  return {
    schema_version: 'ict.workflow.v1',
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.type || 'research',
      position: { x: node.position.x, y: node.position.y },
      data: {
        category: node.data.category,
        title: node.data.title,
        description: node.data.description,
        ...(node.data.component_id ? { component_id: node.data.component_id } : {}),
        ...(node.data.component_version ? { component_version: node.data.component_version } : {}),
        ...(node.data.parameters ? { parameters: { ...node.data.parameters } } : {}),
      },
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? null,
      targetHandle: edge.targetHandle ?? null,
      type: edge.type ?? null,
    })),
  }
}

function restoreWorkflowNodes(graph: WorkflowGraph): WorkflowNode[] {
  return graph.nodes.map((node) => ({
    id: node.id,
    type: 'research',
    position: { ...node.position },
    data: {
      ...node.data,
      category: typeof node.data.category === 'string' ? node.data.category : '科研组件',
      title: typeof node.data.title === 'string' ? node.data.title : '未命名节点',
      description: typeof node.data.description === 'string' ? node.data.description : '',
    } as WorkflowNodeData,
  }))
}

function cloneWorkflowEditorSnapshot(snapshot: WorkflowEditorSnapshot): WorkflowEditorSnapshot {
  return {
    name: snapshot.name,
    description: snapshot.description,
    nodes: snapshot.nodes.map((node) => {
      const copy = { ...node }
      delete copy.selected
      delete copy.dragging
      delete copy.resizing
      delete copy.measured
      delete copy.width
      delete copy.height
      return {
        ...copy,
        position: { ...node.position },
        data: {
          ...node.data,
          input_ports: node.data.input_ports?.map((port) => ({ ...port })),
          output_ports: node.data.output_ports?.map((port) => ({ ...port })),
          parameter_schema: node.data.parameter_schema ? {
            ...node.data.parameter_schema,
            required: [...node.data.parameter_schema.required],
            properties: Object.fromEntries(Object.entries(node.data.parameter_schema.properties).map(([key, property]) => [key, { ...property }])),
          } : undefined,
          parameters: node.data.parameters ? { ...node.data.parameters } : undefined,
        },
      }
    }),
    edges: snapshot.edges.map((edge) => {
      const copy = { ...edge }
      delete copy.selected
      return copy
    }),
  }
}

// Arrange a valid workflow DAG left-to-right; stable ordering keeps sibling nodes predictable.
function layoutWorkflowNodes(nodes: WorkflowNode[], edges: Edge[], maxColumns: number): WorkflowNode[] {
  if (nodes.length < 2) return nodes

  const nodeOrder = new Map(nodes.map((node, index) => [node.id, index]))
  const indegree = new Map(nodes.map((node) => [node.id, 0]))
  const successors = new Map(nodes.map((node) => [node.id, new Set<string>()]))
  for (const edge of edges) {
    if (!nodeOrder.has(edge.source) || !nodeOrder.has(edge.target)) continue
    const targets = successors.get(edge.source)
    if (!targets || targets.has(edge.target)) continue
    targets.add(edge.target)
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1)
  }

  const layerById = new Map(nodes.map((node) => [node.id, 0]))
  const ready = nodes.filter((node) => indegree.get(node.id) === 0).map((node) => node.id)
  for (let cursor = 0; cursor < ready.length; cursor += 1) {
    const sourceId = ready[cursor]
    const nextLayer = (layerById.get(sourceId) ?? 0) + 1
    for (const targetId of successors.get(sourceId) ?? []) {
      layerById.set(targetId, Math.max(layerById.get(targetId) ?? 0, nextLayer))
      const remaining = (indegree.get(targetId) ?? 0) - 1
      indegree.set(targetId, remaining)
      if (remaining === 0) ready.push(targetId)
    }
  }

  // Invalid cyclic drafts remain visible in one final column; validation still reports the cycle.
  const finalLayer = Math.max(0, ...layerById.values()) + 1
  for (const node of nodes) {
    if (indegree.get(node.id) !== 0) layerById.set(node.id, finalLayer)
  }

  const maxLayer = Math.max(0, ...layerById.values())
  const maxColumn = Math.max(0, Math.min(maxColumns - 1, maxLayer))
  const columnById = new Map(nodes.map((node) => [
    node.id,
    maxLayer > maxColumn ? Math.round((layerById.get(node.id) ?? 0) * maxColumn / maxLayer) : layerById.get(node.id) ?? 0,
  ]))
  const columns = new Map<number, WorkflowNode[]>()
  for (const node of nodes) {
    const columnIndex = columnById.get(node.id) ?? 0
    const column = columns.get(columnIndex) ?? []
    column.push(node)
    columns.set(columnIndex, column)
  }

  const positions = new Map<string, XYPosition>()
  for (const [columnIndex, column] of columns) {
    column.sort((left, right) => (layerById.get(left.id) ?? 0) - (layerById.get(right.id) ?? 0)
      || (nodeOrder.get(left.id) ?? 0) - (nodeOrder.get(right.id) ?? 0))
    let y = 72
    for (const node of column) {
      positions.set(node.id, { x: 72 + columnIndex * 356, y })
      y += (node.measured?.height ?? node.height ?? 160) + 64
    }
  }

  return nodes.map((node) => ({ ...node, position: positions.get(node.id) ?? node.position }))
}

type WorkflowGuidedLayer = { index: number; nodes: WorkflowNode[]; unresolved: boolean }

// Group nodes by their actual dependency depth; this view never rewrites the workflow graph.
function getWorkflowGuidedLayers(nodes: WorkflowNode[], edges: Edge[]): WorkflowGuidedLayer[] {
  if (nodes.length === 0) return []

  const nodeOrder = new Map(nodes.map((node, index) => [node.id, index]))
  const indegree = new Map(nodes.map((node) => [node.id, 0]))
  const successors = new Map(nodes.map((node) => [node.id, new Set<string>()]))
  for (const edge of edges) {
    if (!nodeOrder.has(edge.source) || !nodeOrder.has(edge.target)) continue
    const targets = successors.get(edge.source)
    if (!targets || targets.has(edge.target)) continue
    targets.add(edge.target)
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1)
  }

  const layerById = new Map(nodes.map((node) => [node.id, 0]))
  const ready = nodes.filter((node) => indegree.get(node.id) === 0).map((node) => node.id)
  for (let cursor = 0; cursor < ready.length; cursor += 1) {
    const sourceId = ready[cursor]
    const nextLayer = (layerById.get(sourceId) ?? 0) + 1
    for (const targetId of successors.get(sourceId) ?? []) {
      layerById.set(targetId, Math.max(layerById.get(targetId) ?? 0, nextLayer))
      const remaining = (indegree.get(targetId) ?? 0) - 1
      indegree.set(targetId, remaining)
      if (remaining === 0) ready.push(targetId)
    }
  }

  // Keep cyclic nodes and anything blocked behind them visible in a final review layer.
  const unresolvedIds = new Set(nodes.filter((node) => (indegree.get(node.id) ?? 0) > 0).map((node) => node.id))
  const finalLayer = Math.max(0, ...layerById.values()) + 1
  for (const nodeId of unresolvedIds) layerById.set(nodeId, finalLayer)

  const layers = new Map<number, WorkflowNode[]>()
  for (const node of nodes) {
    const index = layerById.get(node.id) ?? 0
    const layer = layers.get(index) ?? []
    layer.push(node)
    layers.set(index, layer)
  }

  return [...layers.entries()]
    .sort(([left], [right]) => left - right)
    .map(([index, layerNodes]) => ({
      index,
      nodes: layerNodes.sort((left, right) => (nodeOrder.get(left.id) ?? 0) - (nodeOrder.get(right.id) ?? 0)),
      unresolved: layerNodes.some((node) => unresolvedIds.has(node.id)),
    }))
}

function hydrateWorkflowNodes(nodes: WorkflowNode[], components: WorkflowComponent[]): WorkflowNode[] {
  const byId = new Map(components.map((component) => [component.component_id, component]))
  return nodes.map((node) => {
    const component = node.data.component_id ? byId.get(node.data.component_id) : undefined
    if (!component) return node
    const defaults = Object.fromEntries(Object.entries(component.parameter_schema.properties).map(
      ([key, property]) => [key, property.default],
    ))
    return {
      ...node,
      data: {
        ...node.data,
        input_ports: component.inputs,
        output_ports: component.outputs,
        parameter_schema: component.parameter_schema,
        executor_binding: component.executor_binding,
        execution_target: component.execution_target,
        execution_available: component.execution_available,
        execution_blockers: component.execution_blockers,
        parameters: { ...defaults, ...(node.data.parameters ?? {}) },
      },
    }
  })
}

function workflowSinkNodeIds(nodes: WorkflowNode[], edges: Edge[]): string[] {
  const sources = new Set(edges.map((edge) => edge.source))
  return nodes.filter((node) => !sources.has(node.id)).map((node) => node.id)
}

function workflowTargetClosureIds(edges: Edge[], targetNodeIds: string[]): Set<string> {
  const ancestors = new Set(targetNodeIds)
  const pending = [...targetNodeIds]
  while (pending.length > 0) {
    const targetId = pending.pop()
    if (!targetId) continue
    for (const edge of edges) {
      if (edge.target === targetId && !ancestors.has(edge.source)) {
        ancestors.add(edge.source)
        pending.push(edge.source)
      }
    }
  }
  return ancestors
}

const runStatusLabels: Record<string, string> = {
  queued: '排队中', running: '运行中', waiting_external: '等待外部服务',
  succeeded: '成功', partially_succeeded: '部分完成', failed: '失败', cancelled: '已取消',
  WAITING: '等待依赖', READY: '就绪', RUNNING: '运行中', WAITING_EXTERNAL: '等待外部服务',
  SUCCEEDED: '成功', RESTORED: '从中断运行恢复', FAILED: '失败', BLOCKED: '被依赖阻断', CACHED: '使用缓存', SKIPPED: '未请求', CANCELLED: '已取消',
}

function runStatusLabel(status: string | null | undefined): string {
  return status ? runStatusLabels[status] ?? runStatusLabels[status.toLowerCase()] ?? status : '未运行'
}

function workflowNodeRunTone(status: string | null | undefined): 'success' | 'active' | 'waiting' | 'failed' | 'neutral' {
  switch (status?.toUpperCase()) {
    case 'SUCCEEDED':
    case 'RESTORED':
    case 'CACHED':
      return 'success'
    case 'READY':
    case 'RUNNING':
      return 'active'
    case 'WAITING':
    case 'WAITING_EXTERNAL':
      return 'waiting'
    case 'FAILED':
    case 'BLOCKED':
      return 'failed'
    default:
      return 'neutral'
  }
}

function isCsvPreflightComponent(componentId: string): boolean {
  return componentId === 'ict.data.csv_manifest_preflight' ||
    componentId === 'ict.data.csv_manifest_preflight_input'
}

function isCsvDescriptiveSummaryComponent(componentId: string): boolean {
  return componentId === 'ict.data.csv_descriptive_summary'
}

function isCsvFolderQualityComponent(componentId: string): boolean {
  return componentId === 'ict.data.quality_check'
}

function supportsLocalCsvFolderImport(componentId: string | undefined): boolean {
  return componentId === 'ict.data.csv_folder_source'
}

function parseCsvFolderManifest(value: unknown): {
  folder_name: string
  ignored_file_count: number
  files: Array<{ relative_path: string; artifact_id: string; sha256: string; size_bytes: number }>
} | null {
  if (typeof value !== 'string' || !value) return null
  try {
    const parsed: unknown = JSON.parse(value)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null
    const manifest = parsed as Record<string, unknown>
    if (typeof manifest.folder_name !== 'string' || !Array.isArray(manifest.files)) return null
    const files = manifest.files.filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null && !Array.isArray(item))
      .filter((item): item is { relative_path: string; artifact_id: string; sha256: string; size_bytes: number } =>
        typeof item.relative_path === 'string' && typeof item.artifact_id === 'string' &&
        typeof item.sha256 === 'string' && typeof item.size_bytes === 'number')
    return {
      folder_name: manifest.folder_name,
      ignored_file_count: typeof manifest.ignored_file_count === 'number' ? manifest.ignored_file_count : 0,
      files,
    }
  } catch {
    return null
  }
}

const CSV_FOLDER_MAX_FILES = 200
const CSV_FOLDER_MAX_TOTAL_BYTES = 100 * 1024 * 1024

// Keep the ArtifactHandle source and legacy quick-preflight node on one local file-import path.
function supportsLocalCsvImport(componentId: string | undefined): boolean {
  return componentId === 'ict.data.csv_artifact_source' ||
    componentId === 'ict.data.csv_manifest_preflight'
}

// Place newly added cards in free grid slots so the catalog can be used without manual untangling.
function nextWorkflowNodePosition(nodes: WorkflowNode[]): XYPosition {
  const columns = 2
  const columnGap = 330
  const rowGap = 300
  const nodeWidth = 260
  const nodeHeight = 250
  const padding = 32

  for (let slot = 0; slot < 1000; slot += 1) {
    const candidate = {
      x: 110 + (slot % columns) * columnGap,
      y: 90 + Math.floor(slot / columns) * rowGap,
    }
    const overlapsExistingNode = nodes.some((node) =>
      candidate.x < node.position.x + nodeWidth + padding &&
      node.position.x < candidate.x + nodeWidth + padding &&
      candidate.y < node.position.y + nodeHeight + padding &&
      node.position.y < candidate.y + nodeHeight + padding)
    if (!overlapsExistingNode) return candidate
  }

  return { x: 110, y: 90 + nodes.length * rowGap }
}

function collectArtifactHandles(value: unknown): LocalArtifactHandle[] {
  if (Array.isArray(value)) return value.flatMap(collectArtifactHandles)
  if (typeof value !== 'object' || value === null) return []
  const item = value as Record<string, unknown>
  // A folder source contains many input handles; render its collection summary
  // instead of duplicating every source file in the derived-artifact list.
  if (typeof item.collection_sha256 === 'string' && Array.isArray(item.files)) return []
  if (typeof item.artifact_id === 'string' && typeof item.sha256 === 'string') {
    return [item as unknown as LocalArtifactHandle]
  }
  return Object.values(item).flatMap(collectArtifactHandles)
}

function Icon({ name, size = 18, className }: { name: IconName; size?: number; className?: string }) {
  const p = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true as const, className }
  switch (name) {
    case 'home': return <svg {...p}><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" /></svg>
    case 'template': return <svg {...p}><path d="M4 5.5h16M4 12h10M4 18.5h7m-1-2 3 3 3-3" /></svg>
    case 'repo': return <svg {...p}><path d="M4 5.5h6l2 2h8v11H4zM4 9h16" /></svg>
    case 'agent': return <svg {...p}><path d="M8 9.5h8M8 13h5M20 11.5a7.5 7.5 0 0 1-11.7 6.2L4 19l1.3-3.8A7.5 7.5 0 1 1 20 11.5Z" /></svg>
    // The global icon denotes the platform's cloud GPU and model-compute support.
    case 'compute': return <svg {...p}><rect x="7" y="7" width="10" height="10" rx="1.5" /><path d="M9.5 2.5v3m5-3v3m-5 13v3m5-3v3m-12.5-9h3m-3 5h3m13-5h3m-3 5h3M10 10h4v4h-4z" /></svg>
    case 'user': return <svg {...p}><circle cx="12" cy="8" r="3" /><path d="M5 20c.8-3.4 3.1-5.2 7-5.2s6.2 1.8 7 5.2" /></svg>
    case 'help': return <svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M9.8 9a2.3 2.3 0 1 1 3.9 1.7c-.9.8-1.7 1.2-1.7 2.8m0 3h.01" /></svg>
    case 'folder': return <svg {...p}><path d="M3.5 6.5h6l2 2h9v9.8a1.7 1.7 0 0 1-1.7 1.7H5.2a1.7 1.7 0 0 1-1.7-1.7Z M3.5 9h17" /></svg>
    case 'workflow': return <svg {...p}><rect x="3.5" y="4" width="6" height="5" rx="1.2" /><rect x="14.5" y="15" width="6" height="5" rx="1.2" /><rect x="14.5" y="4" width="6" height="5" rx="1.2" /><path d="M9.5 6.5h5m-8 2.5v8.5h8" /></svg>
    case 'book': return <svg {...p}><path d="M4 5.5c3.2-1.2 5.9-.8 8 1v13c-2.1-1.8-4.8-2.2-8-1zM20 5.5c-3.2-1.2-5.9-.8-8 1v13c2.1-1.8 4.8-2.2 8-1z" /></svg>
    case 'database': return <svg {...p}><ellipse cx="12" cy="5.5" rx="7.5" ry="3" /><path d="M4.5 5.5v13c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-13M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3" /></svg>
    case 'users': return <svg {...p}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20v-1.5A3.5 3.5 0 0 1 6 15h6a3.5 3.5 0 0 1 3.5 3.5V20m.5-15a3.5 3.5 0 0 1 0 6.8m1 3.8a3.5 3.5 0 0 1 3 3.4V20" /></svg>
    case 'server': return <svg {...p}><rect x="4" y="4" width="16" height="6" rx="1.4" /><rect x="4" y="14" width="16" height="6" rx="1.4" /><path d="M7.5 7h.01M7.5 17h.01M11 7h5m-5 10h5" /></svg>
    case 'bell': return <svg {...p}><path d="M18 9a6 6 0 0 0-12 0c0 7-2.5 7-2.5 8.5h17C20.5 16 18 16 18 9Zm-8 12h4" /></svg>
    case 'clock': return <svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3 2" /></svg>
    case 'plus': return <svg {...p}><path d="M12 5v14M5 12h14" /></svg>
    case 'arrow': return <svg {...p}><path d="M4 12h15m-6-7 7 7-7 7" /></svg>
    case 'refresh': return <svg {...p}><path d="M19 8a7.5 7.5 0 0 0-13.2-2L4 8M4 4v4h4m-3 8a7.5 7.5 0 0 0 13.2 2L20 16m0 4v-4h-4" /></svg>
    case 'shield': return <svg {...p}><path d="M12 3.5 19 6v5c0 4.5-2.8 7.5-7 9.5-4.2-2-7-5-7-9.5V6z" /><path d="m9 12 2 2 4-4" /></svg>
    case 'search': return <svg {...p}><circle cx="10.8" cy="10.8" r="6.3" /><path d="m15.5 15.5 4.2 4.2" /></svg>
    case 'file': return <svg {...p}><path d="M6 3.5h8l4 4V20H6zM14 3.5v4h4M9 12h6m-6 3.5h6" /></svg>
    case 'attachment': return <svg {...p}><path d="m8.5 12.8 6.9-6.9a3.2 3.2 0 0 1 4.5 4.5l-8.4 8.4a5 5 0 0 1-7.1-7.1l8.2-8.2" /></svg>
    case 'send': return <svg {...p}><path d="m21 3-7.2 18-3.7-7.1L3 10.2zM10.1 13.9 21 3" /></svg>
    case 'sliders': return <svg {...p}><path d="M4 6h7m4 0h5M4 12h3m4 0h9M4 18h8m4 0h4" /><circle cx="13" cy="6" r="2" /><circle cx="9" cy="12" r="2" /></svg>
    case 'key': return <svg {...p}><circle cx="8.5" cy="12" r="4.5" /><path d="m12 12 8.5 0m-3 0v3m-3-3v2" /></svg>
    case 'close': return <svg {...p}><path d="m6 6 12 12M18 6 6 18" /></svg>
    case 'panel': return <svg {...p}><rect x="3.5" y="4" width="17" height="16" rx="2" /><path d="M8.5 4v16" /></svg>
    case 'map': return <svg {...p}><path d="m3.5 6 5.2-2 6.6 2 5.2-2v14l-5.2 2-6.6-2-5.2 2zM8.7 4v14m6.6-12v14" /></svg>
    case 'layout': return <svg {...p}><rect x="3.5" y="4" width="6" height="6" rx="1" /><rect x="14.5" y="14" width="6" height="6" rx="1" /><path d="M9.5 7h4a2 2 0 0 1 2 2v5m-3-3 3 3 3-3" /></svg>
    case 'check': return <svg {...p}><path d="m5 12 4.2 4.2L19 6.5" /></svg>
  }
}

function Heading({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="page-heading"><div><h1>{title}</h1>{description ? <p>{description}</p> : null}</div>{action && <div>{action}</div>}</div>
}

function App() {
  const [page, setPage] = useState<Page>(readPageFromHash)
  const [deskTab, setDeskTab] = useState<DeskTab>(readDeskTabFromHash)
  const [projectId, setProjectId] = useState<string | null>(() => readProjectRouteFromHash().projectId)
  const [recentProjectIds, setRecentProjectIds] = useState<string[]>(readLocalRecentProjectIds)
  const [recentWorkflowRefs, setRecentWorkflowRefs] = useState<RecentWorkflowReference[]>(readLocalRecentWorkflowRefs)
  const [agentProjectContext, setAgentProjectContext] = useState<AgentProjectContext | null>(null)
  const [agentWorkflowContext, setAgentWorkflowContext] = useState<AgentWorkflowContext | null>(null)
  const [agentDatasetContext, setAgentDatasetContext] = useState<AgentDatasetContext | null>(null)
  const [settingsTab, setSettingsTab] = useState<SettingsTab>(readSettingsTabFromHash)
  const [notice, setNotice] = useState<'repo' | 'support' | 'help' | null>(null)
  const [projects, setProjects] = useState<State<ProjectListItem[]>>(() => {
    const cached = cachedProjectList()
    return cached ? { status: 'ready', data: cached, cached: true } : { status: 'idle' }
  })
  const [localProjects, setLocalProjects] = useState<State<LocalProject[]>>({ status: 'loading' })
  const [config, setConfig] = useState<ApiConfig>({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? '', token: '' })
  const [status, setStatus] = useState<Status>('disconnected')
  const [platformUnavailable, setPlatformUnavailable] = useState(false)
  const [preferences, setPreferences] = useState<LocalPreferences>(readLocalPreferences)
  const [preferencesSaveFailed, setPreferencesSaveFailed] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [projectCreateMode, setProjectCreateMode] = useState<'platform' | 'local'>('platform')
  const [searchOpen, setSearchOpen] = useState(false)
  const [reproductionPreviewRoute, setReproductionPreviewRoute] = useState(() => window.location.hash.replace(/\/+$/, ''))
  const searchButtonRef = useRef<HTMLButtonElement>(null)
  const localProjectSnapshotPrefetch = useRef(new Set<string>())
  const showWorkflowEditorPreview = import.meta.env.DEV && window.location.hash === '#__preview/workflow-editor'
  const showWorkflowEditorUnavailable = import.meta.env.DEV && window.location.hash === '#__preview/workflow-editor-unavailable'
  const showWorkflowRunDetailPreview = import.meta.env.DEV && reproductionPreviewRoute === '#__preview/workflow-run-detail'
  const showProjectUploadPreview = import.meta.env.DEV && reproductionPreviewRoute === '#__preview/project-upload'
  // Keep the non-persistent form available by direct dev URL without exposing preview controls in the user-facing task list.
  const showReproductionFormPreview = import.meta.env.DEV && reproductionPreviewRoute.startsWith('#workbench/reproductions/__preview/form')
  const showReproductionDetailPreview = import.meta.env.DEV && reproductionPreviewRoute.startsWith('#workbench/reproductions/__preview/detail')
  const showReproductionReportPreview = import.meta.env.DEV && reproductionPreviewRoute.startsWith('#workbench/reproductions/__preview/report')
  const showQualityReportPreview = import.meta.env.DEV && reproductionPreviewRoute === '#__preview/quality-report'
  const showProjectOverviewPreview = import.meta.env.DEV && reproductionPreviewRoute === '#__preview/project-overview'
  const showProjectSettingsPreview = import.meta.env.DEV && reproductionPreviewRoute === '#__preview/project-settings'
  const showProjectWorkflowPreview = import.meta.env.DEV && reproductionPreviewRoute === '#__preview/project-workflows'
  const showProjectResourcesPreview = import.meta.env.DEV && reproductionPreviewRoute === '#__preview/project-resources'
  const showProjectDatasetDetailPreview = import.meta.env.DEV && reproductionPreviewRoute === '#__preview/project-dataset-detail'
  const showProjectListEmptyPreview = import.meta.env.DEV && reproductionPreviewRoute === '#__preview/project-list-empty'
  const reproductionPreviewKind: 'paper' | 'experiment' = reproductionPreviewRoute.endsWith('/experiment') ? 'experiment' : 'paper'
  const hasProjectContext = page === 'workbench' && deskTab === 'projects' && projectId !== null
  // Keep the project switcher limited to objects returned by the access-controlled project API.
  const availableProjects = projects.status === 'ready' ? projects.data : []
  const currentProject = projectId ? availableProjects.find((project) => project.id === projectId) : undefined
  const projectContextOptionCount = availableProjects.length + (projectId && !currentProject ? 1 : 0)
  const canSwitchProject = projects.status === 'ready' && projectContextOptionCount > 1
  const appShellClassName = ['app-shell', preferences.density === 'compact' ? 'is-compact' : '', preferences.reduceMotion ? 'is-reduced-motion' : '', hasProjectContext ? 'has-project-context' : ''].filter(Boolean).join(' ')
  const markPlatformServiceUnavailable = useCallback(() => {
    setPlatformUnavailable(true)
    setStatus('error')
  }, [])

  useEffect(() => {
    let active = true
    listLocalProjects()
      .then((items) => {
        cacheLocalProjectList(items)
        if (active) setLocalProjects({ status: 'ready', data: items })
        // Keep a compact local snapshot so a later runtime outage does not hide projects already opened on this device.
        for (const item of items) {
          if (cachedLocalProjectDetail(item.id) && cachedProjectWorkflows(item.id)) continue
          if (localProjectSnapshotPrefetch.current.has(item.id)) continue
          localProjectSnapshotPrefetch.current.add(item.id)
          void Promise.all([getLocalProject(item.id), listLocalProjectWorkflows(item.id)])
            .then(([detail, workflows]) => {
              cacheLocalProjectDetail(detail)
              cacheProjectWorkflows(item.id, workflows)
            })
            .catch((error) => console.warn(`预缓存本机项目 ${item.id} 失败；运行时恢复后会重试。`, error))
            .finally(() => localProjectSnapshotPrefetch.current.delete(item.id))
        }
      })
      .catch((error) => {
        console.error('读取本机项目目录失败。', error)
        const cached = cachedLocalProjectList()
        if (active && cached && canFallbackToLocalProjectCache(error)) {
          console.warn('本机运行时不可用，已回退到本机项目目录缓存。')
          setLocalProjects({ status: 'ready', data: cached, cached: true })
        } else if (active) {
          const message = error instanceof LocalRuntimeApiError
            ? `本机项目目录请求失败（${error.status} · ${error.code}）。`
            : cached
              ? '本机项目目录暂不可用，且当前错误不适合回退缓存。'
              : '本机运行时未连接，且没有可用的项目缓存；请启动本机运行时后重试。'
          setLocalProjects({ status: 'error', message })
        }
      })
    return () => { active = false }
  }, [page, projectId])

  useEffect(() => {
    try {
      window.localStorage.setItem(localPreferencesKey, JSON.stringify(preferences))
      setPreferencesSaveFailed(false)
    } catch (error) {
      console.error('保存科研工作台的本地界面偏好失败。', error)
      setPreferencesSaveFailed(true)
    }
  }, [preferences])

  useEffect(() => {
    try {
      // Store only project IDs; visible project data still comes from the access-controlled API.
      window.localStorage.setItem(localRecentProjectsKey, JSON.stringify(recentProjectIds))
    } catch (error) {
      console.error('保存本机最近打开项目记录失败。', error)
    }
  }, [recentProjectIds])

  useEffect(() => {
    try {
      // Only identifiers and the local open time are stored; names and access are reloaded from APIs.
      window.localStorage.setItem(localRecentWorkflowsKey, JSON.stringify(recentWorkflowRefs))
    } catch (error) {
      console.error('保存本机最近打开工作流记录失败。', error)
    }
  }, [recentWorkflowRefs])

  useEffect(() => {
    const syncPage = () => {
      const nextPage = readPageFromHash()
      const projectRoute = readProjectRouteFromHash()
      setPage(nextPage)
      setProjectId(projectRoute.projectId)
      setReproductionPreviewRoute(window.location.hash.replace(/\/+$/, ''))
      // Browser history can leave Agent without going through the in-app navigation handlers.
      if (nextPage !== 'agent') {
        setAgentProjectContext(null)
        setAgentWorkflowContext(null)
        setAgentDatasetContext(null)
      }
      setDeskTab(readDeskTabFromHash())
      setSettingsTab(readSettingsTabFromHash())
    }
    window.addEventListener('hashchange', syncPage)
    return () => window.removeEventListener('hashchange', syncPage)
  }, [])

  useEffect(() => {
    if (!projectId || status === 'connected' || localProjects.status !== 'ready') return
    const linkedLocalProject = localProjects.data.find((item) => item.platform_project_id === projectId)
    if (!linkedLocalProject) return

    // Offline navigation must enter the local working copy instead of a platform-only project shell.
    console.info('平台服务不可用，已将项目路由切换到关联的本机工作副本。', {
      platformProjectId: projectId,
      localProjectId: linkedLocalProject.id,
      syncState: linkedLocalProject.sync_state,
    })
    setProjectId(linkedLocalProject.id)
    window.location.hash = `workbench/projects/${encodeURIComponent(linkedLocalProject.id)}`
  }, [localProjects, projectId, status])

  useEffect(() => {
    const handleGlobalShortcuts = (event: KeyboardEvent) => {
      const target = event.target
      const isEditingText = target instanceof HTMLElement && target.matches('input, textarea, [contenteditable="true"]')
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k' && !isEditingText) {
        event.preventDefault()
        setSearchOpen((open) => !open)
        setNotice(null)
      }
      if (event.key === 'Escape') {
        setSearchOpen(false)
        setNotice(null)
      }
    }
    window.addEventListener('keydown', handleGlobalShortcuts)
    return () => window.removeEventListener('keydown', handleGlobalShortcuts)
  }, [])

  useEffect(() => {
    // Keep the selected top-level destination visible when the mobile nav overflows.
    const nav = document.querySelector<HTMLElement>('.primary-nav')
    const activeItem = nav?.querySelector<HTMLElement>('.nav-item.active')
    if (!nav || !activeItem) return
    const navBounds = nav.getBoundingClientRect()
    const itemBounds = activeItem.getBoundingClientRect()
    const offset = itemBounds.right > navBounds.right
      ? itemBounds.right - navBounds.right
      : itemBounds.left < navBounds.left
        ? itemBounds.left - navBounds.left
        : 0
    if (offset !== 0) nav.scrollBy({ left: offset, behavior: preferences.reduceMotion ? 'auto' : 'smooth' })
  }, [page, preferences.reduceMotion])

  const connect = async (next: ApiConfig) => {
    const clean = { baseUrl: next.baseUrl.trim(), token: next.token.trim() }
    setConfig(clean)
    if (!clean.token) {
      setStatus('error')
      setPlatformUnavailable(true)
      const cached = cachedProjectList()
      setProjects(cached ? { status: 'ready', data: cached, cached: true } : { status: 'error', message: '请填写服务访问令牌。' })
      return
    }
    setStatus('connecting'); setProjects({ status: 'loading' })
    try {
      const data = await listProjects(clean)
      writeLocalCache(localProjectListCacheKey, data, '项目列表')
      setProjects({ status: 'ready', data })
      setPlatformUnavailable(false)
      setStatus('connected')
    } catch (error) {
      const cached = cachedProjectList()
      setProjects(cached ? { status: 'ready', data: cached, cached: true } : { status: 'error', message: explainError(error) })
      setPlatformUnavailable(isPlatformServiceUnavailable(error, true))
      setStatus('error')
    }
  }
  const refresh = async () => {
    if (!config.token) {
      setStatus('disconnected')
      setPlatformUnavailable(true)
      const cached = cachedProjectList()
      setProjects(cached ? { status: 'ready', data: cached, cached: true } : { status: 'idle' })
      return
    }
    setStatus('connecting'); setProjects({ status: 'loading' })
    try {
      const data = await listProjects(config)
      writeLocalCache(localProjectListCacheKey, data, '项目列表')
      setProjects({ status: 'ready', data })
      setPlatformUnavailable(false)
      setStatus('connected')
    } catch (error) {
      const cached = cachedProjectList()
      setProjects(cached ? { status: 'ready', data: cached, cached: true } : { status: 'error', message: explainError(error) })
      setPlatformUnavailable(isPlatformServiceUnavailable(error, true))
      setStatus('error')
    }
  }
  const recordProjectOpen = (id: string) => {
    if (!id.trim()) return
    setRecentProjectIds((current) => [id, ...current.filter((recentId) => recentId !== id)].slice(0, 20))
  }
  const recordWorkflowOpen = useCallback((ownerProjectId: string, workflowId: string) => {
    const project = ownerProjectId.trim()
    const workflow = workflowId.trim()
    if (!project || !workflow) return
    const reference = { projectId: project, workflowId: workflow, openedAt: new Date().toISOString() }
    const identity = recentWorkflowIdentity(reference)
    setRecentWorkflowRefs((current) => [reference, ...current.filter((item) => recentWorkflowIdentity(item) !== identity)].slice(0, 20))
  }, [])
  const removeRecentWorkflowRefs = useCallback((references: Array<Pick<RecentWorkflowReference, 'projectId' | 'workflowId'>>) => {
    const identities = new Set(references.map(recentWorkflowIdentity))
    if (identities.size === 0) return
    setRecentWorkflowRefs((current) => current.filter((item) => !identities.has(recentWorkflowIdentity(item))))
  }, [])
  const resolveProjectIdForCurrentConnection = (id: string) => {
    if (status === 'connected') return id
    const localProject = localProjects.status === 'ready'
      ? localProjects.data.find((item) => item.id === id || item.platform_project_id === id)
      : undefined
    return localProject?.id ?? id
  }
  const openProject = (id: string) => {
    const resolvedId = resolveProjectIdForCurrentConnection(id)
    recordProjectOpen(resolvedId)
    setProjectId(resolvedId)
    setDeskTab('projects')
    window.location.hash = `workbench/projects/${encodeURIComponent(resolvedId)}`
  }
  const openRecentWorkflow = (ownerProjectId: string, workflowId: string) => {
    recordWorkflowOpen(ownerProjectId, workflowId)
    recordProjectOpen(ownerProjectId)
    setDeskTab('projects')
    setPage('workbench')
    setProjectId(ownerProjectId)
    setAgentProjectContext(null)
    setAgentWorkflowContext(null)
    setAgentDatasetContext(null)
    setNotice(null)
    setSearchOpen(false)
    window.location.hash = `workbench/projects/${encodeURIComponent(ownerProjectId)}/workflows/${encodeURIComponent(workflowId)}`
  }
  const clearAgentContext = () => { setAgentProjectContext(null); setAgentWorkflowContext(null); setAgentDatasetContext(null) }
  const navigate = (next: Page) => { window.location.hash = next; setPage(next); setNotice(null); setSearchOpen(false); if (next !== 'workbench') setProjectId(null); if (next !== 'agent') clearAgentContext() }
  const navigateToWorkbenchTab = (tab: DeskTab) => { setDeskTab(tab); setPage('workbench'); setProjectId(null); clearAgentContext(); setNotice(null); setSearchOpen(false); window.location.hash = tab === 'reproductions' ? 'workbench/reproductions' : 'workbench/projects' }
  const navigateToSettingsTab = (tab: SettingsTab) => { setSettingsTab(tab); setPage('settings'); setProjectId(null); clearAgentContext(); setNotice(null); setSearchOpen(false); window.location.hash = 'settings/' + tab }
  const openProjectFromSearch = (id: string) => { setDeskTab('projects'); setPage('workbench'); openProject(id); clearAgentContext(); setNotice(null); setSearchOpen(false) }
  const openServiceSettings = () => { setSettingsTab('service'); setPage('settings'); clearAgentContext(); setNotice(null); setSearchOpen(false); setProjectId(null); window.location.hash = 'settings/service' }
  const openAgentWithProjectContext = (project: AgentProjectContext) => {
    // Stage the real project identity in this view only; no Agent service receives or saves it yet.
    setAgentProjectContext(project)
    setAgentWorkflowContext(null)
    setAgentDatasetContext(null)
    setPage('agent')
    setProjectId(null)
    setNotice(null)
    setSearchOpen(false)
    window.location.hash = 'agent'
  }
  const openAgentWithWorkflowContext = (project: AgentProjectContext, workflow: AgentWorkflowContext) => {
    // Keep the containing project and workflow together as local, unsent context references.
    setAgentProjectContext(project)
    setAgentWorkflowContext(workflow)
    setAgentDatasetContext(null)
    setPage('agent')
    setProjectId(null)
    setNotice(null)
    setSearchOpen(false)
    window.location.hash = 'agent'
  }
  const openAgentWithDatasetContext = (project: AgentProjectContext, dataset: AgentDatasetContext) => {
    // Stage the real dataset version alongside its owning project; references remain local and unsent.
    setAgentProjectContext(project)
    setAgentWorkflowContext(null)
    setAgentDatasetContext(dataset)
    setPage('agent')
    setProjectId(null)
    setNotice(null)
    setSearchOpen(false)
    window.location.hash = 'agent'
  }
  const disconnect = () => {
    setConfig((old) => ({ baseUrl: old.baseUrl, token: '' }))
    setStatus('disconnected')
    setPlatformUnavailable(true)
    // Keep the last real project list available so cached projects remain openable offline.
    const cached = cachedProjectList()
    setProjects(cached ? { status: 'ready', data: cached, cached: true } : { status: 'idle' })
    setProjectId(null)
    clearAgentContext()
    window.location.hash = 'workbench/projects'
  }
  const openCreatePlatformProject = () => { setProjectCreateMode('platform'); setCreateOpen(true) }
  const openCreateLocalProject = () => { setProjectCreateMode('local'); setCreateOpen(true) }
  const createProject = async (input: ProjectCreateInput): Promise<ProjectDetail | LocalProjectDetail> => {
    if (projectCreateMode === 'local') {
      const result = await createLocalProject(input)
      const summary: LocalProject = {
        id: result.id,
        name: result.name,
        domain: result.domain,
        description: result.description,
        role: result.role,
        visibility: result.visibility,
        created_at: result.created_at,
        workflow_count: result.workflow_count,
        dataset_version_count: result.dataset_version_count,
        recent_run_status: result.recent_run_status,
        last_activity_at: result.last_activity_at,
        source: 'local',
        sync_state: result.sync_state,
        platform_project_id: result.platform_project_id,
      }
      cacheLocalProjectDetail(result)
      cacheProjectWorkflows(result.id, [])
      setLocalProjects((current) => {
        const data = [summary, ...(current.status === 'ready' ? current.data.filter((item) => item.id !== result.id) : [])]
        cacheLocalProjectList(data)
        return { status: 'ready', data }
      })
      setCreateOpen(false)
      openProject(result.id)
      return result
    }
    const result = await createProjectRequest(config, input)
    const summary: ProjectListItem = { id: result.id, name: result.name, domain: result.domain, description: result.description, role: result.role, visibility: result.visibility, created_at: result.created_at, workflow_count: 0, dataset_version_count: 0, recent_run_status: null, last_activity_at: result.created_at }
    setProjects((old) => old.status === 'ready' ? { status: 'ready', data: [summary, ...old.data.filter((item) => item.id !== result.id)] } : old)
    setPlatformUnavailable(false); setStatus('connected'); setCreateOpen(false); openProject(result.id)
    return result
  }

  if (showWorkflowEditorPreview || showWorkflowEditorUnavailable) return <div className={appShellClassName}><main className="page-content"><WorkflowEditor key={showWorkflowEditorPreview ? 'layout-preview' : 'unavailable'} owner={{ type: 'project', id: workflowEditorPreviewProject.id, name: workflowEditorPreviewProject.name }} preview={showWorkflowEditorPreview} backLabel="工作台" onBack={() => { window.location.hash = 'workbench' }} /></main></div>
  if (showWorkflowRunDetailPreview) return <div className={appShellClassName}><main className="page-content"><WorkflowRunDetailPreview onBack={() => { window.location.hash = '__preview/workflow-editor' }} /></main></div>
  if (showProjectUploadPreview) return <div className={appShellClassName}><main className="page-content"><ProjectUploadFlowPreview projectName={null} onBack={() => { window.location.hash = 'workbench' }} /></main></div>

  return <div className={appShellClassName}>
    <header className="global-header">
      <a className="brand" href="#workbench" onClick={(event) => { event.preventDefault(); navigate('workbench') }} aria-label="ICT 科研工作台"><span className="brand__mark"><Icon name="workflow" size={21} /></span><span><strong>ICT</strong><small>科研工作台</small></span></a>
      <nav className="primary-nav" aria-label="一级导航">
        <button type="button" aria-current={page === 'workbench' ? 'page' : undefined} className={'nav-item' + (page === 'workbench' ? ' active' : '')} onClick={() => navigate('workbench')}><Icon name="home" size={17} />工作台</button>
        <button type="button" aria-current={page === 'templates' ? 'page' : undefined} className={'nav-item' + (page === 'templates' ? ' active' : '')} onClick={() => navigate('templates')}><Icon name="template" size={17} />模板市场</button>
        <button className={'nav-icon' + (notice === 'repo' ? ' active' : '')} aria-label="仓库" title="仓库" onClick={() => setNotice(notice === 'repo' ? null : 'repo')}><Icon name="repo" /></button>
        <button type="button" aria-current={page === 'agent' ? 'page' : undefined} className={'nav-item' + (page === 'agent' ? ' active' : '')} onClick={() => navigate('agent')}><Icon name="agent" size={17} />Agent 对话</button>
        <button className={'nav-icon' + (notice === 'support' ? ' active' : '')} aria-label="科研支持" title="科研支持" onClick={() => setNotice(notice === 'support' ? null : 'support')}><Icon name="compute" /></button>
        <button type="button" aria-current={page === 'settings' ? 'page' : undefined} className={'nav-item' + (page === 'settings' ? ' active' : '')} onClick={() => navigate('settings')}><Icon name="user" size={17} />个人信息与设置</button>
      </nav>
      <div className="global-tools" aria-label="全局工具">
        {hasProjectContext && <label className="project-context-switcher" title={currentProject?.name || '当前项目'}>
          <Icon name="folder" size={16} />
          <select aria-label={`当前项目：${currentProject?.name || '当前项目'}`} value={currentProject?.id || '__current-project__'} disabled={!canSwitchProject} onChange={(event) => { openProject(event.currentTarget.value); setNotice(null) }}>
            {!currentProject && <option value="__current-project__" disabled>当前项目</option>}
            {availableProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </label>}
        <button ref={searchButtonRef} className="global-search-trigger" aria-label="搜索页面和项目" aria-keyshortcuts="Control+K Meta+K" onClick={() => { setSearchOpen(true); setNotice(null) }}><Icon name="search" size={17} /><span>搜索页面和项目</span><kbd>Ctrl K</kbd></button>
        <button className="header-icon-button" aria-label="帮助与快捷键" aria-expanded={notice === 'help'} aria-controls={notice === 'help' ? 'global-help-popover' : undefined} title="帮助与快捷键" onClick={() => setNotice(notice === 'help' ? null : 'help')}><Icon name="help" /></button>
        <button className="header-profile" aria-label="个人信息与设置" title="个人信息与设置" onClick={() => navigate('settings')}><span><Icon name="user" size={17} /></span></button>
      </div>
      {notice && <div className={'entry-popover' + (notice === 'help' ? ' help-popover' : '')} id={notice === 'help' ? 'global-help-popover' : 'global-entry-popover'} role={notice === 'help' ? 'dialog' : 'status'} aria-labelledby={notice === 'help' ? 'global-help-title' : 'global-entry-title'}>
        <span><Icon name={notice === 'repo' ? 'repo' : notice === 'support' ? 'compute' : 'help'} /></span>
        <div>
          <strong id={notice === 'help' ? 'global-help-title' : 'global-entry-title'}>{notice === 'repo' ? '仓库' : notice === 'support' ? '科研支持' : '帮助与快捷键'}</strong>
          {notice === 'help' ? <><p><kbd>Ctrl</kbd> + <kbd>K</kbd> 打开全局搜索</p><p><kbd>Esc</kbd> 关闭搜索或快捷浮层</p></> : <p>{notice === 'repo' ? '仓库入口已预留，当前版本尚未开放。' : '科研支持面向云显卡与大模型算力，当前尚未接入服务。'}</p>}
        </div>
        <button aria-label="关闭提示" onClick={() => setNotice(null)}><Icon name="close" size={15} /></button>
      </div>}
    </header>
    <main className="page-content">
      {showProjectSettingsPreview
        ? <ProjectSettingsPreview />
        : showProjectOverviewPreview
        ? <ProjectOverviewPreview />
        : showProjectResourcesPreview
        ? <ProjectResourcesPreview />
        : showProjectDatasetDetailPreview
          ? <ProjectDatasetDetailPreview onBack={() => { window.location.hash = '__preview/project-resources' }} config={config} />
        : showProjectWorkflowPreview
          ? <ProjectWorkflowListPreview />
          : showQualityReportPreview
            ? <ProjectQualityReport projectName={null} dataset={null} config={config} onBack={() => { window.location.hash = 'workbench/projects' }} preview />
            : showReproductionDetailPreview
              ? <ReproductionTaskDetailPreview kind={reproductionPreviewKind} onBack={() => { window.location.hash = 'workbench/reproductions' }} onOpenReport={(kind) => { window.location.hash = `workbench/reproductions/__preview/report/${kind}` }} />
              : showReproductionReportPreview
                ? <ReproductionReportPreview kind={reproductionPreviewKind} onBack={() => { window.location.hash = `workbench/reproductions/__preview/detail/${reproductionPreviewKind}` }} />
                : showProjectListEmptyPreview
                  ? <><div className="workflow-preview-banner" role="status"><Icon name="server" size={16} /><span><strong>开发态布局预览 · 项目列表空态</strong><small>可打开新建表单检查布局；不模拟服务连接或提交项目数据。</small></span></div><Workbench tab="projects" setTab={(tab) => { setDeskTab(tab); setProjectId(null); window.location.hash = tab === 'reproductions' ? 'workbench/reproductions' : 'workbench/projects' }} projects={{ status: 'ready', data: [] }} localProjects={{ status: 'ready', data: [] }} projectId={null} setProjectId={setProjectId} recentProjectIds={[]} recentWorkflowRefs={[]} onRecordWorkflowOpen={recordWorkflowOpen} onOpenRecentWorkflow={openRecentWorkflow} onRemoveRecentWorkflowRefs={removeRecentWorkflowRefs} onOpenProject={openProject} config={config} onPlatformUnavailable={markPlatformServiceUnavailable} onRefresh={refresh} onSettings={openServiceSettings} onCreate={openCreatePlatformProject} onCreateLocal={openCreateLocalProject} onNavigate={navigate} onDiscussProject={openAgentWithProjectContext} onDiscussWorkflow={openAgentWithWorkflowContext} onDiscussDataset={openAgentWithDatasetContext} layoutPreview  reduceMotion={preferences.reduceMotion} /></>
                  : page === 'workbench' && <Workbench tab={deskTab} setTab={(tab) => { setDeskTab(tab); setProjectId(null); window.location.hash = tab === 'reproductions' ? 'workbench/reproductions' : 'workbench/projects' }} projects={projects} localProjects={localProjects} projectId={projectId} setProjectId={setProjectId} recentProjectIds={recentProjectIds} recentWorkflowRefs={recentWorkflowRefs} onRecordWorkflowOpen={recordWorkflowOpen} onOpenRecentWorkflow={openRecentWorkflow} onRemoveRecentWorkflowRefs={removeRecentWorkflowRefs} onOpenProject={openProject} config={config} platformUnavailable={platformUnavailable} onPlatformUnavailable={markPlatformServiceUnavailable} onRefresh={refresh} onSettings={openServiceSettings} onCreate={openCreatePlatformProject} onCreateLocal={openCreateLocalProject} onNavigate={navigate} onDiscussProject={openAgentWithProjectContext} onDiscussWorkflow={openAgentWithWorkflowContext} onDiscussDataset={openAgentWithDatasetContext} reproductionPreview={showReproductionFormPreview} reproductionPreviewKind={reproductionPreviewKind}  reduceMotion={preferences.reduceMotion} />}
      {page === 'templates' && <Templates config={config} onOpenServiceSettings={openServiceSettings} onOpenWorkflow={openRecentWorkflow} onOpenWorkbench={() => navigateToWorkbenchTab('projects')} />}
      {page === 'agent' && <Agent projectContext={agentProjectContext} workflowContext={agentWorkflowContext} datasetContext={agentDatasetContext} onClearProjectContext={() => setAgentProjectContext(null)} onClearWorkflowContext={() => setAgentWorkflowContext(null)} onClearDatasetContext={() => setAgentDatasetContext(null)} onOpenServiceSettings={openServiceSettings} />}
      {page === 'settings' && <Settings section={settingsTab} setSection={(tab) => { setSettingsTab(tab); window.location.hash = 'settings/' + tab }} config={config} status={status} projects={projects} onConnect={connect} onDisconnect={disconnect} preferences={preferences} onPreferencesChange={setPreferences} preferencesSaveFailed={preferencesSaveFailed} />}
    </main>
    <GlobalSearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} projects={projects} onNavigate={navigate} onNavigateToWorkbenchTab={navigateToWorkbenchTab} onNavigateToSettingsTab={navigateToSettingsTab} onOpenProject={openProjectFromSearch} onOpenServiceSettings={openServiceSettings} />
    {createOpen && <CreateProjectDialog onClose={() => setCreateOpen(false)} onCreate={createProject} localOnly={projectCreateMode === 'local'} preview={showProjectListEmptyPreview} />}
  </div>
}

function GlobalSearchDialog({ open, onClose, projects, onNavigate, onNavigateToWorkbenchTab, onNavigateToSettingsTab, onOpenProject, onOpenServiceSettings }: {
  open: boolean
  onClose: () => void
  projects: State<ProjectListItem[]>
  onNavigate: (page: Page) => void
  onNavigateToWorkbenchTab: (tab: DeskTab) => void
  onNavigateToSettingsTab: (tab: SettingsTab) => void
  onOpenProject: (id: string) => void
  onOpenServiceSettings: () => void
}) {
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) {
      previousFocusRef.current?.focus()
      return
    }
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setQuery('')
    const focusFrame = window.requestAnimationFrame(() => inputRef.current?.focus())
    return () => window.cancelAnimationFrame(focusFrame)
  }, [open])

  if (!open) return null

  const destinations: { id: string; title: string; detail: string; keywords: string; icon: IconName; onSelect: () => void }[] = [
    { id: 'workbench', title: '工作台', detail: '项目与论文复现', keywords: '研究 项目', icon: 'home', onSelect: () => onNavigateToWorkbenchTab('projects') },
    { id: 'reproductions', title: '论文复现', detail: '复现论文并核验实验结果', keywords: '检验 实验 核验', icon: 'book', onSelect: () => onNavigateToWorkbenchTab('reproductions') },
    { id: 'templates', title: '模板市场', detail: '浏览科研工作流模板', keywords: '工作流 组件', icon: 'template', onSelect: () => onNavigate('templates') },
    { id: 'agent', title: 'Agent 对话', detail: '与科研 Agent 对话', keywords: '智能体 聊天', icon: 'agent', onSelect: () => onNavigate('agent') },
    { id: 'settings', title: '个人信息与设置', detail: '账号、偏好、安全与服务', keywords: '用户 账户 偏好 安全 服务', icon: 'user', onSelect: () => onNavigateToSettingsTab('profile') },
    { id: 'workspace-settings', title: '工作空间与权限', detail: '工作空间、团队与访问范围', keywords: '成员 角色 权限 团队', icon: 'users', onSelect: () => onNavigateToSettingsTab('workspace') },
  ]
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const pageResults = destinations.filter((destination) => `${destination.title} ${destination.detail} ${destination.keywords}`.toLocaleLowerCase().includes(normalizedQuery))
  const projectResults = projects.status === 'ready'
    ? projects.data.filter((project) => [project.name, project.id, project.domain, projectPermissionLabel(project.role)].join(' ').toLocaleLowerCase().includes(normalizedQuery)).slice(0, 6)
    : []
  const hasResults = pageResults.length > 0 || projectResults.length > 0

  return <div className="global-search-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="global-search-dialog" role="dialog" aria-modal="true" aria-labelledby="global-search-title" aria-describedby="global-search-hint">
      <div className="global-search-heading">
        <div><span className="global-search-heading__icon"><Icon name="search" size={18} /></span><div><h2 id="global-search-title">全局搜索</h2><p>搜索平台入口和已载入的项目</p></div></div>
        <button className="header-icon-button" aria-label="关闭搜索" onClick={onClose}><Icon name="close" size={17} /></button>
      </div>
      <label className="global-search-field"><Icon name="search" size={18} /><input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入页面名称或项目名称" aria-label="搜索页面和项目" /><kbd>Esc</kbd></label>
      <div className="global-search-results" aria-live="polite">
        {pageResults.length > 0 && <section className="global-search-group" aria-label="平台入口"><h3>平台入口</h3>{pageResults.map((destination) => <button key={destination.id} className="global-search-result" onClick={destination.onSelect}><span className="global-search-result__icon"><Icon name={destination.icon} size={17} /></span><span><strong>{destination.title}</strong><small>{destination.detail}</small></span><Icon className="global-search-result__arrow" name="arrow" size={15} /></button>)}</section>}
        {projectResults.length > 0 && <section className="global-search-group" aria-label="项目"><h3>项目</h3>{projectResults.map((project) => <button key={project.id} className="global-search-result" onClick={() => onOpenProject(project.id)}><span className="global-search-result__icon"><Icon name="folder" size={17} /></span><span><strong>{project.name}</strong><small>{[project.domain, projectPermissionLabel(project.role), project.id].filter(Boolean).join(' · ')}</small></span><Icon className="global-search-result__arrow" name="arrow" size={15} /></button>)}</section>}
        {!hasResults && <p className="global-search-empty">没有找到匹配的页面或项目。</p>}
      </div>
      <div className="global-search-footer" id="global-search-hint">
        {projects.status === 'loading' || projects.status === 'idle'
          ? <span>{projects.status === 'loading' ? '正在读取项目目录…' : '连接项目服务后可搜索项目。'}</span>
          : projects.status === 'error'
            ? <span>项目目录暂不可用：{projects.message}</span>
            : projects.data.length === 0 && <span>当前项目目录为空。</span>}
        {projects.status !== 'ready' && <button onClick={onOpenServiceSettings}>连接项目服务</button>}
      </div>
    </section>
  </div>
}

function Workbench({ tab, setTab, projects, localProjects, projectId, setProjectId, recentProjectIds, recentWorkflowRefs, onRecordWorkflowOpen, onOpenRecentWorkflow, onRemoveRecentWorkflowRefs, onOpenProject, config, platformUnavailable = false, onPlatformUnavailable, onRefresh, onSettings, onCreate, onCreateLocal, onNavigate, onDiscussProject, onDiscussWorkflow, onDiscussDataset, layoutPreview = false, reproductionPreview = false, reproductionPreviewKind = 'paper', reduceMotion = false }: {
  tab: DeskTab; setTab: (tab: DeskTab) => void; projects: State<ProjectListItem[]>; localProjects: State<LocalProject[]>; projectId: string | null; setProjectId: (id: string | null) => void
  recentProjectIds: string[]; onOpenProject: (id: string) => void
  recentWorkflowRefs: RecentWorkflowReference[]
  onRecordWorkflowOpen: (projectId: string, workflowId: string) => void
  onOpenRecentWorkflow: (projectId: string, workflowId: string) => void
  onRemoveRecentWorkflowRefs: (references: Array<Pick<RecentWorkflowReference, 'projectId' | 'workflowId'>>) => void
  config: ApiConfig; platformUnavailable?: boolean; onPlatformUnavailable: () => void; onRefresh: () => void; onSettings: () => void; onCreate: () => void; onCreateLocal: () => void; onNavigate: (page: Page) => void; onDiscussProject: (project: AgentProjectContext) => void
  onDiscussWorkflow: (project: AgentProjectContext, workflow: AgentWorkflowContext) => void
  onDiscussDataset: (project: AgentProjectContext, dataset: AgentDatasetContext) => void
  layoutPreview?: boolean; reproductionPreview?: boolean; reproductionPreviewKind?: 'paper' | 'experiment'; reduceMotion?: boolean
}) {
  const name = projectId
    ? (localProjects.status === 'ready' ? localProjects.data.find((item) => item.id === projectId)?.name : undefined) ??
      (projects.status === 'ready' ? projects.data.find((item) => item.id === projectId)?.name : undefined)
    : undefined
  const localProjectSummary = projectId && localProjects.status === 'ready'
    ? localProjects.data.find((item) => item.id === projectId) ?? null
    : null
  const platformProjectSummary = projectId && projects.status === 'ready'
    ? projects.data.find((item) => item.id === projectId) ?? null
    : null
  const projectCount = (projects.status === 'ready' ? projects.data.length : 0) + (localProjects.status === 'ready' ? localProjects.data.length : 0)
  const heroVariant = readWorkbenchHeroVariant()
  return <>
    {!projectId && <div className={'workbench-hero-band' + (heroVariant !== 'fluid' ? ' workbench-hero-band--image' : '')}><WorkbenchHero variant={heroVariant} reduceMotion={reduceMotion} /><Heading title="工作台" /></div>}
    <div className={'workbench-shell' + (!projectId && (tab === 'projects' || tab === 'reproductions') ? ' workbench-shell--object-home' : '')}>
      <aside className="workbench-sidebar">
        <nav className="workbench-tabs" role="tablist" aria-label="工作台研究对象">
          <span className="workbench-sidebar__label">研究空间</span>
          <button role="tab" aria-selected={tab === 'projects'} className={tab === 'projects' ? 'active' : ''} onClick={() => { setProjectId(null); setTab('projects') }}><Icon name="folder" />项目{!layoutPreview && projectCount > 0 && <small>{projectCount}</small>}</button>
          <button role="tab" aria-selected={tab === 'reproductions'} className={tab === 'reproductions' ? 'active' : ''} onClick={() => { setProjectId(null); setTab('reproductions') }}><Icon name="book" />论文复现</button>
        </nav>
      </aside>
      <div className="workbench-view">
        {projectId ? <ProjectDetailPage key={projectId} id={projectId} name={name} localProjectSummary={localProjectSummary} platformProjectSummary={platformProjectSummary} workflowId={readProjectRouteFromHash().workflowId} config={config} platformUnavailable={platformUnavailable} onPlatformUnavailable={onPlatformUnavailable} onRecordWorkflowOpen={onRecordWorkflowOpen} onBack={() => { setProjectId(null); window.location.hash = 'workbench/projects' }} onDiscussProject={onDiscussProject} onDiscussWorkflow={onDiscussWorkflow} onDiscussDataset={onDiscussDataset} onOpenReproductions={(taskId, linkedProjectId) => { setProjectId(null); setTab('reproductions'); window.location.hash = taskId ? `workbench/reproductions/${encodeURIComponent(taskId)}` : linkedProjectId ? `workbench/reproductions?project=${encodeURIComponent(linkedProjectId)}` : 'workbench/reproductions' }} /> : tab === 'projects' ? <ProjectDashboard state={projects} localProjects={localProjects} config={config} platformUnavailable={platformUnavailable} recentProjectIds={recentProjectIds} recentWorkflowRefs={recentWorkflowRefs} onOpenRecentWorkflow={onOpenRecentWorkflow} onRemoveRecentWorkflowRefs={onRemoveRecentWorkflowRefs} onSettings={onSettings} onRefresh={onRefresh} onCreate={onCreate} onCreateLocal={onCreateLocal} onOpen={onOpenProject} onNavigate={onNavigate} onReproduce={() => setTab('reproductions')} layoutPreview={layoutPreview} /> : <Reproduction key={reproductionPreview ? 'form-preview' : 'task-list'} config={config} projects={projects} localProjects={localProjects} onSettings={onSettings} layoutPreview={reproductionPreview} previewKind={reproductionPreviewKind} />}
      </div>
    </div>
  </>
}

function ProjectDashboard({ state, localProjects, config, platformUnavailable, recentProjectIds, recentWorkflowRefs, onOpenRecentWorkflow, onRemoveRecentWorkflowRefs, onSettings, onRefresh, onCreate, onCreateLocal, onOpen, onNavigate, onReproduce, layoutPreview = false }: { state: State<ProjectListItem[]>; localProjects: State<LocalProject[]>; config: ApiConfig; platformUnavailable: boolean; recentProjectIds: string[]; recentWorkflowRefs: RecentWorkflowReference[]; onOpenRecentWorkflow: (projectId: string, workflowId: string) => void; onRemoveRecentWorkflowRefs: (references: Array<Pick<RecentWorkflowReference, 'projectId' | 'workflowId'>>) => void; onSettings: () => void; onRefresh: () => void; onCreate: () => void; onCreateLocal: () => void; onOpen: (id: string) => void; onNavigate: (page: Page) => void; onReproduce: () => void; layoutPreview?: boolean }) {
  const [preferredView, setPreferredView] = useState<'cards' | 'table' | null>(null)
  const [query, setQuery] = useState('')
  const [domainFilter, setDomainFilter] = useState('')
  const [prioritizeRecent, setPrioritizeRecent] = useState(true)
  const availableProjects = state.status === 'ready' ? state.data : []
  const availableProjectIds = new Set(availableProjects.map((project) => project.id))
  const visibleRecentProjectIds = recentProjectIds.filter((id) => availableProjectIds.has(id))
  const recentProjectRanks = new Map<string, number>(visibleRecentProjectIds.map((id, index): [string, number] => [id, index]))
  const orderedProjects = prioritizeRecent && recentProjectRanks.size > 0
    ? [...availableProjects].sort((left, right) => (recentProjectRanks.get(left.id) ?? Number.MAX_SAFE_INTEGER) - (recentProjectRanks.get(right.id) ?? Number.MAX_SAFE_INTEGER))
    : availableProjects
  const availableDomains = [...new Set(orderedProjects.map((project) => project.domain.trim()).filter(Boolean))].sort((left, right) => left.localeCompare(right, 'zh-CN'))
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const filteredProjects = orderedProjects.filter((project) => {
    const searchText = [project.name, project.domain, projectPermissionLabel(project.role), project.id].join(' ').toLocaleLowerCase()
    return searchText.includes(normalizedQuery) && (!domainFilter || project.domain.trim() === domainFilter)
  })
  // Larger real lists start in the denser view; an explicit user choice takes precedence.
  const activeView = preferredView ?? (availableProjects.length >= 8 ? 'table' : 'cards')
  const showLocalProjectsFirst = !layoutPreview && (state.status !== 'ready' || state.cached === true)

  return <div className="dashboard-grid">
    <div className="dashboard-main">
      {showLocalProjectsFirst && <LocalProjectCatalog state={localProjects} onCreate={onCreateLocal} onOpen={onOpen} />}
      <section className="dashboard-projects-panel" aria-labelledby="project-list-heading">
        <div className="section-heading"><div><h2 id="project-list-heading">平台项目</h2></div><div>{state.status === 'ready' && state.data.length > 0 && <span className="count">{state.data.length} 个项目</span>}{state.status === 'ready' && state.data.length > 0 && <button className="button primary" onClick={onCreate} disabled={state.cached} title={state.cached ? '平台离线时不能创建平台项目' : undefined}><Icon name="plus" size={16} />新建项目</button>}</div></div>
        {state.status === 'ready' && state.cached && <p className="project-offline-cache-note" role="status">当前显示此浏览器上次读取的项目副本。权限和平台数据可能已变化；离线工作流修改只保存在本机。</p>}
        {state.status === 'idle' && <div className="workspace-empty"><span className="workspace-empty__symbol"><Icon name="server" size={18} /></span><div className="workspace-empty__copy"><span className="kicker">平台项目服务未连接</span><h3>平台目录暂不可用</h3></div><button className="button primary" onClick={onSettings}>连接平台项目服务 <Icon name="arrow" size={16} /></button></div>}
        {state.status === 'loading' && <div className="project-skeleton" aria-label="正在加载项目列表"><i /><i /><i /></div>}
        {state.status === 'error' && <div className="error-state" role="alert"><span className="state-icon warning"><Icon name="server" /></span><div><h3>暂时无法读取项目</h3><p>{state.message}</p><button className="link-button" onClick={onSettings}>检查服务配置 <Icon name="arrow" size={14} /></button></div><button className="button secondary" onClick={onRefresh}><Icon name="refresh" size={16} />重新加载</button></div>}
        {availableProjects.length > 0 && availableDomains.length > 0 && <div className="project-domain-tabs" role="group" aria-label="项目研究领域分区">
          <button type="button" className={domainFilter === '' ? 'active' : ''} aria-pressed={domainFilter === ''} onClick={() => setDomainFilter('')}>全部项目 <small>{availableProjects.length}</small></button>
          {availableDomains.map((domain) => {
            const projectCount = orderedProjects.filter((project) => project.domain.trim() === domain).length
            return <button type="button" key={domain} className={domainFilter === domain ? 'active' : ''} aria-pressed={domainFilter === domain} onClick={() => setDomainFilter(domain)}>{domain} <small>{projectCount}</small></button>
          })}
        </div>}
        {availableProjects.length > 0 && <div className="project-list-toolbar">
          <div className="project-list-toolbar__filters">
            <label className="project-list-search"><Icon name="search" size={16} /><input type="search" aria-label="搜索项目名称、领域或 ID" placeholder="搜索项目名称、领域或 ID" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          </div>
          <div className="project-list-toolbar__controls">
            {(normalizedQuery || domainFilter) && <span className="project-list-result-count">显示 {filteredProjects.length} / {availableProjects.length} 个项目</span>}
            {visibleRecentProjectIds.length > 0 && <button type="button" className={'project-recent-order' + (prioritizeRecent ? ' active' : '')} aria-label="本机最近打开项目优先排序" aria-pressed={prioritizeRecent} title="按本浏览器最近打开的项目优先排列" onClick={() => setPrioritizeRecent((enabled) => !enabled)}>最近打开</button>}
            <div className="project-view-switch" role="group" aria-label="项目显示方式"><button type="button" className={activeView === 'cards' ? 'active' : ''} aria-pressed={activeView === 'cards'} onClick={() => setPreferredView('cards')}>卡片</button><button type="button" className={activeView === 'table' ? 'active' : ''} aria-pressed={activeView === 'table'} onClick={() => setPreferredView('table')}>表格</button></div>
          </div>
        </div>}
        <ProjectResults state={state} projects={filteredProjects} view={activeView} onCreate={onCreate} onOpen={onOpen} onResetFilters={() => { setQuery(''); setDomainFilter('') }} layoutPreview={layoutPreview} />
      </section>
      {!layoutPreview && !showLocalProjectsFirst && <LocalProjectCatalog state={localProjects} onCreate={onCreateLocal} onOpen={onOpen} />}
      <DashboardRecentWorkflows projects={state} localProjects={localProjects} config={config} platformUnavailable={platformUnavailable} references={recentWorkflowRefs} onOpen={onOpenRecentWorkflow} onOpenSettings={onSettings} onRefreshProjects={onRefresh} onRemoveInvalid={onRemoveRecentWorkflowRefs} />
    </div>
    <aside className="dashboard-rail" aria-label="工作台辅助区域">
      <DashboardRecentRuns localProjects={localProjects} references={recentWorkflowRefs} onOpen={onOpenRecentWorkflow} />
      <section className="dashboard-quick-card"><div className="dashboard-card-heading"><span className="kicker">快捷入口</span></div>
        <button className="quick-entry" onClick={onReproduce}><span className="quick-entry__icon"><Icon name="book" size={17} /></span><span><strong>论文复现</strong></span><Icon name="arrow" size={15} /></button>
        <button className="quick-entry" onClick={() => onNavigate('templates')}><span className="quick-entry__icon"><Icon name="template" size={17} /></span><span><strong>模板市场</strong></span><Icon name="arrow" size={15} /></button>
        <button className="quick-entry" onClick={() => onNavigate('agent')}><span className="quick-entry__icon"><Icon name="agent" size={17} /></span><span><strong>Agent 对话</strong></span><Icon name="arrow" size={15} /></button>
      </section>
    </aside>
  </div>
}

function LocalProjectCatalog({ state, onCreate, onOpen }: { state: State<LocalProject[]>; onCreate: () => void; onOpen: (id: string) => void }) {
  const cacheOnly = state.status === 'ready' && state.cached === true
  const runtimeUnavailable = state.status === 'error' || cacheOnly
  return <section className="local-project-catalog" aria-labelledby="local-project-heading">
    <div className="local-project-catalog__heading">
      <div><h2 id="local-project-heading">本机项目</h2></div>
      <button type="button" className="button secondary" onClick={onCreate} disabled={runtimeUnavailable} title={runtimeUnavailable ? '启动本机运行时后可创建本机项目。' : undefined}><Icon name="plus" size={16} />新建本机项目</button>
    </div>
    {state.status === 'ready' && state.cached && <p className="project-offline-cache-note" role="status">本机运行时暂不可用，当前显示此前保存到此浏览器的项目目录；打开已缓存项目可继续查看。</p>}
    {state.status === 'loading' && <div className="local-project-catalog__state" role="status">正在读取本机项目目录…</div>}
    {state.status === 'error' && <div className="local-project-catalog__state local-project-catalog__state--error" role="status">{state.message}启动本机运行时后可创建新项目。</div>}
    {state.status === 'ready' && state.data.length === 0 && <div className="local-project-catalog__state">还没有本机项目</div>}
    {state.status === 'ready' && state.data.length > 0 && <div className="local-project-catalog__list">{state.data.map((project) => <button className="local-project-catalog__item" key={project.id} type="button" onClick={() => onOpen(project.id)}>
      <span className="local-project-catalog__icon"><Icon name="folder" size={17} /></span>
      <span className="local-project-catalog__copy"><strong>{project.name}</strong><small>{project.domain || '未设置研究领域'} · {project.workflow_count} 个工作流 · {localSyncStatusLabel(project.sync_state)}</small></span>
      <Icon className="local-project-catalog__arrow" name="arrow" size={15} />
    </button>)}</div>}
  </section>
}

function DashboardRecentWorkflows({ projects, localProjects, config, platformUnavailable, references, onOpen, onOpenSettings, onRefreshProjects, onRemoveInvalid }: {
  projects: State<ProjectListItem[]>
  localProjects: State<LocalProject[]>
  config: ApiConfig
  platformUnavailable: boolean
  references: RecentWorkflowReference[]
  onOpen: (projectId: string, workflowId: string) => void
  onOpenSettings: () => void
  onRefreshProjects: () => void
  onRemoveInvalid: (references: Array<Pick<RecentWorkflowReference, 'projectId' | 'workflowId'>>) => void
}) {
  const [state, setState] = useState<State<RecentWorkflowRow[]>>({ status: 'loading' })
  const [retry, setRetry] = useState(0)
  // Local project IDs are outside the platform catalog; keep them out of its stale-reference cleanup.
  const localProjectIds = useMemo(() => new Set(localProjects.status === 'ready' ? localProjects.data.map((project) => project.id) : []), [localProjects])
  const platformReferences = useMemo(() => references.filter((reference) => !localProjectIds.has(reference.projectId)), [localProjectIds, references])

  useEffect(() => {
    if (platformReferences.length === 0) {
      setState({ status: 'ready', data: [] })
      return
    }
    const showLocalCopies = () => {
      setState({ status: 'ready', data: cachedRecentWorkflowRows(platformReferences), cached: true })
    }
    if (platformUnavailable || !config.token.trim() || projects.status === 'idle' || projects.status === 'error') {
      showLocalCopies()
      return
    }
    if (projects.status !== 'ready') {
      setState({ status: 'loading' })
      return
    }

    const projectById = new Map(projects.data.map((project) => [project.id, project]))
    const inaccessible = platformReferences.filter((reference) => !projectById.has(reference.projectId))
    if (inaccessible.length > 0 && localProjects.status === 'ready') onRemoveInvalid(inaccessible)

    const accessibleReferences = platformReferences.filter((reference) => projectById.has(reference.projectId)).slice(0, 5)
    const projectIds = [...new Set(accessibleReferences.map((reference) => reference.projectId))]
    if (projectIds.length === 0) {
      setState({ status: 'ready', data: [] })
      return
    }

    const controller = new AbortController()
    setState({ status: 'loading' })
    Promise.all(projectIds.map(async (projectId) => [
      projectId,
      await listProjectWorkflows(config, projectId, controller.signal),
    ] as const))
      .then((workflowLists) => {
        const workflowsByProject = new Map(workflowLists)
        const rows: RecentWorkflowRow[] = []
        const invalid: RecentWorkflowReference[] = []
        for (const reference of accessibleReferences) {
          const project = projectById.get(reference.projectId)
          const workflow = workflowsByProject.get(reference.projectId)?.find((item) => item.id === reference.workflowId && item.project_id === reference.projectId)
          if (!project || !workflow) {
            invalid.push(reference)
            continue
          }
          rows.push({
            project: { id: project.id, name: project.name },
            workflow: { id: workflow.id, project_id: workflow.project_id, name: workflow.name },
            openedAt: reference.openedAt,
          })
        }
        if (invalid.length > 0) onRemoveInvalid(invalid)
        setState({ status: 'ready', data: rows })
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        const canUseLocalCopy = error instanceof TypeError || error instanceof WorkflowApiError && error.status >= 500
        if (canUseLocalCopy) showLocalCopies()
        else setState({ status: 'error', message: explainWorkflowError(error) })
      })
    return () => controller.abort()
  }, [config.baseUrl, config.token, localProjects, onRemoveInvalid, platformReferences, platformUnavailable, projects, retry])

  const hasRecentReferences = platformReferences.length > 0
  // Local workflow runs are shown in their own runtime-backed summary in the workbench rail.
  if (!hasRecentReferences && references.length > 0) return null
  return <section className="dashboard-recent-workflows" aria-labelledby="dashboard-recent-workflows-title">
    <div className="section-heading dashboard-recent-workflows__heading">
      <div><h2 id="dashboard-recent-workflows-title">最近打开的工作流</h2></div>
      {state.status === 'ready' && state.data.length > 0 && <span className="dashboard-recent-workflows__count">{state.data.length} 条</span>}
    </div>
    {!hasRecentReferences && <div className="dashboard-recent-workflows__empty">
      <span className="dashboard-recent-workflows__icon"><Icon name="workflow" size={16} /></span>
      <p>暂无记录</p>
    </div>}
    {hasRecentReferences && state.status === 'ready' && state.cached && state.data.length > 0 && <div className="dashboard-recent-workflows__notice" role="status">
      <span>平台权限未验证。以下为本机缓存副本；离线时只能使用已安装的本机组件，平台同步与版本操作需重新连接。</span>
    </div>}
    {hasRecentReferences && state.status === 'ready' && state.cached && state.data.length === 0 && <div className="dashboard-recent-workflows__notice" role="status">
      <span>本机没有完整缓存的项目与工作流副本。连接平台项目服务后可重新验证这些记录。</span>
      {/* The project panel already owns a reconnect action while disconnected or in error; retain this link for cached/loading states. */}
      {projects.status !== 'idle' && projects.status !== 'error' && <button type="button" className="link-button" onClick={onOpenSettings}>连接项目服务<Icon name="arrow" size={14} /></button>}
    </div>}
    {hasRecentReferences && projects.status === 'loading' && <div className="dashboard-recent-workflows__notice" role="status">正在读取项目目录以验证最近工作流…</div>}
    {hasRecentReferences && projects.status === 'error' && state.status !== 'ready' && <div className="dashboard-recent-workflows__notice" role="alert">
      <span>项目目录暂不可用：{projects.message}</span><button type="button" className="link-button" onClick={onRefreshProjects}>重新加载<Icon name="refresh" size={14} /></button>
    </div>}
    {hasRecentReferences && projects.status === 'ready' && config.token.trim() && state.status === 'loading' && <div className="dashboard-recent-workflows__notice" role="status">正在验证最近打开的工作流…</div>}
    {hasRecentReferences && projects.status === 'ready' && state.status === 'error' && <div className="dashboard-recent-workflows__notice" role="alert">
      <span>最近工作流暂时无法验证：{state.message}</span><button type="button" className="link-button" onClick={() => setRetry((value) => value + 1)}>重试<Icon name="refresh" size={14} /></button>
    </div>}
    {hasRecentReferences && projects.status === 'ready' && state.status === 'ready' && state.data.length === 0 && <div className="dashboard-recent-workflows__empty">
      <span className="dashboard-recent-workflows__icon"><Icon name="workflow" size={16} /></span>
      <p>暂无记录</p>
    </div>}
    {hasRecentReferences && state.status === 'ready' && state.data.length > 0 && <ul className="project-workflow-list dashboard-recent-workflows__list">
      {state.data.map(({ project, workflow, openedAt }) => <li key={recentWorkflowIdentity({ projectId: project.id, workflowId: workflow.id })}>
        <div className="project-workflow-list__icon"><Icon name="workflow" size={16} /></div>
        <div className="project-workflow-list__copy"><strong>{workflow.name}</strong><small>{project.name} · 最近打开 {dateTime(openedAt)}{state.cached ? ' · 本机缓存副本' : ''}</small></div>
        <button type="button" className="link-button" onClick={() => onOpen(project.id, workflow.id)}>{state.cached ? '本机打开' : '继续'}<Icon name="arrow" size={14} /></button>
      </li>)}
    </ul>}
  </section>
}

function DashboardRecentRuns({ localProjects, references, onOpen }: {
  localProjects: State<LocalProject[]>
  references: RecentWorkflowReference[]
  onOpen: (projectId: string, workflowId: string) => void
}) {
  const [state, setState] = useState<State<DashboardLocalRunRow[]>>({ status: 'loading' })
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    if (localProjects.status !== 'ready') {
      setState({ status: 'ready', data: [] })
      return
    }
    // Cached project metadata is not evidence that the runtime can still read its run history.
    if (localProjects.cached) {
      setState({ status: 'error', message: '本机运行时未连接，暂不展示缓存的运行状态。' })
      return
    }
    if (localProjects.data.length === 0) {
      setState({ status: 'ready', data: [] })
      return
    }

    const projectsById = new Map(localProjects.data.map((project) => [project.id, project]))
    // Recent open references bound the lookup so the dashboard doesn't scan every workflow in a workspace.
    const localReferences = references.filter((reference) => projectsById.has(reference.projectId)).slice(0, 10)
    if (localReferences.length === 0) {
      setState({ status: 'ready', data: [] })
      return
    }
    let active = true
    const projectIds = [...new Set(localReferences.map((reference) => reference.projectId))]
    setState({ status: 'loading' })
    Promise.all(projectIds.map(async (projectId) => [
      projectId,
      await listLocalProjectWorkflows(projectId),
    ] as const))
      .then(async (workflowLists) => {
        const workflowsByProject = new Map(workflowLists)
        const localWorkflows = localReferences.flatMap((reference) => {
          const project = projectsById.get(reference.projectId)
          const workflow = workflowsByProject.get(reference.projectId)?.find((item) => item.id === reference.workflowId && item.project_id === reference.projectId)
          return project && workflow ? [{ project, workflow }] : []
        })
        const runGroups = await Promise.all(localWorkflows.map(async ({ project, workflow }) => {
          const runs = await listLocalWorkflowRuns(workflow.id)
          const run = runs.find((item) => item.workflow_id === workflow.id)
          return run ? [{ project, workflow, run }] : []
        }))
        return runGroups.flat().sort((left, right) => {
          const leftTime = Date.parse(left.run.created_at ?? left.run.started_at ?? '')
          const rightTime = Date.parse(right.run.created_at ?? right.run.started_at ?? '')
          return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
        }).slice(0, 5)
      })
      .then((rows) => {
        if (active) setState({ status: 'ready', data: rows })
      })
      .catch((error: unknown) => {
        console.error('读取工作台本机最近运行摘要失败。', {
          projectIds,
          workflowReferenceCount: localReferences.length,
          error,
        })
        if (active) setState({ status: 'error', message: '暂时无法读取本机运行历史。确认本机运行时可用后重试。' })
      })
    return () => { active = false }
  }, [localProjects, references, retry])

  if (localProjects.status !== 'ready') return null
  return <section className="dashboard-recent-runs" aria-labelledby="dashboard-recent-runs-title">
    <div className="dashboard-card-heading"><span id="dashboard-recent-runs-title" className="kicker">本机最近运行</span>{state.status === 'ready' && state.data.length > 0 && <span>{state.data.length} 次</span>}</div>
    {state.status === 'loading' && <p className="dashboard-recent-runs__state" role="status">正在读取运行记录…</p>}
    {state.status === 'error' && <p className="dashboard-recent-runs__state" role="status">{state.message}{!localProjects.cached && <button type="button" className="link-button" onClick={() => setRetry((value) => value + 1)}>重试<Icon name="refresh" size={14} /></button>}</p>}
    {state.status === 'ready' && state.data.length === 0 && <p className="dashboard-recent-runs__state">暂无运行记录</p>}
    {state.status === 'ready' && state.data.length > 0 && <ul className="dashboard-recent-runs__list">
      {state.data.map(({ project, workflow, run }) => <li key={run.run_id}>
        <button type="button" className="dashboard-recent-run" onClick={() => onOpen(project.id, workflow.id)} aria-label={`打开 ${project.name} 中工作流 ${workflow.name} 的最近一次运行（${runStatusLabel(run.status)}）`} title="打开工作流并查看最近一次运行">
          <span className="dashboard-recent-run__main">
            <span className="dashboard-recent-run__heading"><strong className={`dashboard-recent-run__status dashboard-recent-run__status--${dashboardRecentRunTone(run.status)}`}>{runStatusLabel(run.status)}</strong><time>{run.created_at ? dateTime(run.created_at) : '时间未提供'}</time></span>
            <span className="dashboard-recent-run__workflow">{workflow.name}</span>
            <small>{project.name}{run.error_code ? ` · ${run.error_code}` : ''}</small>
          </span>
          <Icon name="arrow" size={14} />
        </button>
      </li>)}
    </ul>}
  </section>
}

function dashboardRecentRunTone(status: LocalWorkflowRunSummary['status']): 'success' | 'active' | 'attention' | 'failed' | 'neutral' {
  if (status === 'succeeded') return 'success'
  if (status === 'queued' || status === 'running') return 'active'
  if (status === 'waiting_external' || status === 'partially_succeeded') return 'attention'
  if (status === 'failed') return 'failed'
  return 'neutral'
}

function ProjectResults({ state, projects, view, onCreate, onOpen, onResetFilters, layoutPreview = false }: {
  state: State<ProjectListItem[]>
  projects: ProjectListItem[]
  view: 'cards' | 'table'
  onCreate: () => void
  onOpen: (id: string) => void
  onResetFilters: () => void
  layoutPreview?: boolean
}) {
  if (state.status !== 'ready') return null
  if (state.data.length === 0) return <div className="empty-list">
    <div className="empty-list__intro"><span className="state-icon"><Icon name="folder" /></span><div><h3>还没有项目</h3></div><button className="button primary" onClick={onCreate} title={layoutPreview ? '仅打开表单预览，不会创建项目' : undefined}><Icon name="plus" size={16} />新建项目</button></div>
  </div>
  if (projects.length === 0) return <div className="project-filter-empty"><h3>没有匹配的项目</h3><p>调整关键词或研究领域筛选条件。</p><button type="button" className="link-button" onClick={onResetFilters}>清除筛选</button></div>
  if (view === 'cards') return <div className="project-list">{projects.map((item) => <div className="project-card-shell" key={item.id}>
    <button type="button" className="project-card" onClick={() => onOpen(item.id)}>
      <span className="project-card__icon"><Icon name="folder" /></span>
      <span className="project-card__body">
        <span className="project-card__head"><span className="project-card__copy"><strong>{item.name}</strong><small>{item.domain || '未设置研究领域'}</small></span><span className="project-card__meta">{projectPermissionLabel(item.role)}</span></span>
        <span className="project-card__description">{item.description || '尚未填写研究目标'}</span>
        <span className="project-card__stats"><span>{item.workflow_count} 个工作流</span><span>{item.dataset_version_count} 个数据集版本</span><span>最近运行：{projectRunStatusLabel(item.recent_run_status)}</span></span>
        <span className="project-card__activity">最近更新：{item.last_activity_at ? date(item.last_activity_at) : '暂无活动'}</span>
      </span><Icon className="project-card__arrow" name="arrow" size={16} />
    </button>
    <div className="project-card__tools"><ProjectActionsMenu projectName={item.name} /></div>
  </div>)}</div>
  return <div className="project-table-wrap" role="region" aria-label="项目表格" tabIndex={0}><table className="project-table"><thead><tr><th scope="col">项目</th><th scope="col">研究目标</th><th scope="col">研究领域</th><th scope="col">工作流 / 数据集版本</th><th scope="col">最近运行</th><th scope="col">最近更新</th><th scope="col">我的权限</th><th className="project-table__actions-heading" scope="col">操作</th></tr></thead><tbody>{projects.map((item) => <tr key={item.id}><td><button type="button" className="project-table__name" onClick={() => onOpen(item.id)}><span className="project-table__icon"><Icon name="folder" size={16} /></span><span><strong>{item.name}</strong><small>{item.id}</small></span><Icon name="arrow" size={15} /></button></td><td className="project-table__goal">{item.description || '尚未填写研究目标'}</td><td>{item.domain || '未设置'}</td><td>{item.workflow_count} / {item.dataset_version_count}</td><td>{projectRunStatusLabel(item.recent_run_status)}</td><td>{item.last_activity_at ? date(item.last_activity_at) : '暂无活动'}</td><td>{projectPermissionLabel(item.role)}</td><td className="project-table__actions"><ProjectActionsMenu projectName={item.name} /></td></tr>)}</tbody></table></div>
}

// Keep the V4.0 project action affordance visible without implying unsupported mutations.
function ProjectActionsMenu({ projectName }: { projectName: string }) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const closeMenu = () => setOpen(false)
    const onPointerDown = (event: PointerEvent) => {
      if (!(event.target instanceof Node)) return
      if (triggerRef.current?.contains(event.target) || menuRef.current?.contains(event.target)) return
      closeMenu()
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      closeMenu()
      triggerRef.current?.focus()
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('scroll', closeMenu, true)
    window.addEventListener('resize', closeMenu)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('scroll', closeMenu, true)
      window.removeEventListener('resize', closeMenu)
    }
  }, [open])

  const toggleMenu = () => {
    if (open) {
      setOpen(false)
      return
    }
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const panelWidth = 224
    const panelHeight = 230
    const top = window.innerHeight - rect.bottom < panelHeight + 12
      ? Math.max(8, rect.top - panelHeight - 6)
      : rect.bottom + 6
    const left = Math.max(8, Math.min(window.innerWidth - panelWidth - 8, rect.right - panelWidth))
    setPosition({ top, left })
    setOpen(true)
  }

  return <>
    <button ref={triggerRef} type="button" className="project-actions-menu__trigger" aria-label={`更多项目操作：${projectName}`} aria-haspopup="true" aria-expanded={open} title="更多项目操作" onClick={toggleMenu}><span aria-hidden="true">•••</span></button>
    {open && position && createPortal(<div ref={menuRef} className="project-actions-menu__panel" role="group" aria-label={`${projectName}的项目操作`} style={{ top: position.top, left: position.left }}>
      <div className="project-actions-menu__status" role="status"><strong>项目操作暂不可用</strong><small>项目管理接口尚未接入</small></div>
      {['重命名项目', '复制项目', '归档项目', '删除项目'].map((action) => <button key={action} type="button" className={action === '删除项目' ? 'project-actions-menu__item is-danger' : 'project-actions-menu__item'} disabled title="项目操作接口尚未接入">{action}<span>未开放</span></button>)}
    </div>, document.body)}
  </>
}

const reproductionStatusLabels: Record<ReproductionStatus, string> = {
  preparation: '待准备',
  insufficient_conditions: '条件不足',
  ready_to_run: '待运行',
  running: '运行中',
  awaiting_review: '待复核',
  conforms: '符合预设规则',
  differs: '存在差异',
  undetermined: '无法判定',
}

function reproductionErrorMessage(error: unknown, action: 'load' | 'create') {
  if (error instanceof ReproductionApiError) {
    if (error.status === 401) return '服务访问令牌无效或已过期，请重新连接服务。'
    if (error.status === 403) return action === 'create' ? '当前账号没有创建复现任务的权限。' : '当前账号没有读取该复现任务的权限。'
    if (error.status === 404) return action === 'create' ? '关联项目不存在或当前账号无权访问。' : '任务不存在，或当前账号无权访问。'
    if (error.status === 503) return '复现任务服务或数据库尚未就绪。'
    if (error.status === 422) return '提交内容未通过服务端校验，请检查必填项和字段长度。'
  }
  return action === 'create' ? '任务未能保存，请检查服务连接后重试。' : '暂时无法读取复现任务，请检查服务连接后重试。'
}

function reproductionStatusLabel(status: ReproductionStatus) {
  return reproductionStatusLabels[status]
}

function Reproduction({ config, projects, localProjects, onSettings, layoutPreview = false, previewKind = 'paper' }: {
  config: ApiConfig
  projects: State<ProjectListItem[]>
  localProjects: State<LocalProject[]>
  onSettings: () => void
  layoutPreview?: boolean
  previewKind?: ReproductionKind
}) {
  const [kind, setKind] = useState<ReproductionKind>(previewKind)
  const [statusFilter, setStatusFilter] = useState<ReproductionStatus | ''>('')
  const [projectFilter, setProjectFilter] = useState(readReproductionProjectFilterFromHash)
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(layoutPreview)
  const [createMode, setCreateMode] = useState<'platform' | 'local'>('platform')
  const [reloadKey, setReloadKey] = useState(0)
  const [tasks, setTasks] = useState<State<ReproductionTask[]>>({ status: 'idle' })
  const { taskId, workflowId } = readReproductionTaskRouteFromHash()

  useEffect(() => {
    if (layoutPreview || taskId) {
      setTasks({ status: 'idle' })
      return
    }
    const controller = new AbortController()
    setTasks({ status: 'loading' })
    const platformTasks = config.token.trim()
      ? listReproductionTasks(config, {}, controller.signal)
      : Promise.resolve([] as ReproductionTask[])
    Promise.allSettled([platformTasks, listLocalReproductionTasks()]).then(([platformResult, localResult]) => {
      if (controller.signal.aborted) return
      const platformData = platformResult.status === 'fulfilled' ? platformResult.value : []
      const localData = localResult.status === 'fulfilled' ? localResult.value : []
      if (platformResult.status === 'rejected' && localResult.status === 'rejected') {
        setTasks({ status: 'error', message: reproductionErrorMessage(platformResult.reason, 'load') })
        return
      }
      const combined = [...localData, ...platformData].sort(
        (left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at),
      )
      setTasks({ status: 'ready', data: combined })
    })
    return () => controller.abort()
  }, [config.baseUrl, config.token, reloadKey, layoutPreview, taskId])

  const cancelDraft = () => {
    setCreating(false)
    setCreateMode('platform')
    if (layoutPreview) window.location.hash = 'workbench/reproductions'
  }
  const saveTask = async (input: ReproductionTaskCreateInput) => {
    const task = createMode === 'local'
      ? await createLocalReproductionTask(input)
      : await createReproductionTask(config, input)
    setCreating(false)
    setCreateMode('platform')
    setReloadKey((value) => value + 1)
    window.location.hash = `workbench/reproductions/${encodeURIComponent(task.id)}`
  }
  const visibleTasks = tasks.status === 'ready'
    ? tasks.data.filter((task) => task.kind === kind && (!statusFilter || task.status === statusFilter) &&
      (projectFilter !== '__independent__' || task.linked_project_id === null) &&
      (!projectFilter || projectFilter === '__independent__' || task.linked_project_id === projectFilter) &&
      [task.title, task.source, task.claim].join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
    : []
  const hasTasksForKind = tasks.status === 'ready' && tasks.data.some((task) => task.kind === kind)
  const hasActiveFilters = Boolean(query.trim() || statusFilter || projectFilter)
  // Keep search controls contextual; a true empty list only needs a refresh action.
  const showReproductionFilters = !layoutPreview && (tasks.status !== 'ready' || hasTasksForKind || hasActiveFilters)
  const projectNames = new Map<string, string>([
    ...(projects.status === 'ready' ? projects.data.map((project) => [project.id, project.name] as const) : []),
    ...(localProjects.status === 'ready' ? localProjects.data.map((project) => [project.id, project.name] as const) : []),
  ])

  if (taskId) return <ReproductionTaskDetail config={config} projects={projects} localProjects={localProjects} taskId={taskId} workflowId={workflowId} onBack={() => { window.location.hash = 'workbench/reproductions' }} onSettings={onSettings} />

  return <div className="reproduction-grid">
    <section className="content-panel">
      {creating ? <ReproductionDraftForm kind={kind} onKindChange={setKind} onCancel={cancelDraft} onSubmit={saveTask} projects={createMode === 'local' ? localProjects : projects} preview={layoutPreview} localOnly={createMode === 'local'} config={config} /> : <>
        <div className="section-heading">
          <div><h2>复现与核验任务</h2></div>
          <div className="reproduction-preview__actions">
            {/* Keep the platform action useful when disconnected by routing to its existing setup page. */}
            {config.token.trim()
              ? <button className="button secondary" type="button" onClick={() => { setCreateMode('platform'); setCreating(true) }}><Icon name="plus" size={16} />新建平台任务</button>
              : <button className="button secondary" type="button" onClick={onSettings}><Icon name="server" size={16} />连接平台服务</button>}
            <button className="button primary" type="button" onClick={() => { setCreateMode('local'); setCreating(true) }}><Icon name="plus" size={16} />本机新建任务</button>
          </div>
        </div>
        <div className="type-tabs" role="tablist" aria-label="检验类型">
          <button type="button" role="tab" aria-selected={kind === 'paper'} className={kind === 'paper' ? 'active' : ''} onClick={() => setKind('paper')}>论文复现</button>
          <button type="button" role="tab" aria-selected={kind === 'experiment'} className={kind === 'experiment' ? 'active' : ''} onClick={() => setKind('experiment')}>实验核验</button>
        </div>
        {showReproductionFilters && <div className="reproduction-filter-row">
          <label className="reproduction-search"><span className="sr-only">搜索任务</span><Icon name="search" size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索任务、主张或依据" disabled={tasks.status !== 'ready'} /></label>
          <label><span className="sr-only">按任务状态筛选</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as ReproductionStatus | '')} disabled={tasks.status !== 'ready'}><option value="">全部状态</option>{Object.entries(reproductionStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label><span className="sr-only">按关联项目筛选</span><select value={projectFilter} onChange={(event) => setProjectFilter(event.target.value)} disabled={tasks.status !== 'ready'}><option value="">全部项目</option><option value="__independent__">仅独立任务</option>{projects.status === 'ready' && projects.data.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}{localProjects.status === 'ready' && localProjects.data.map((project) => <option key={project.id} value={project.id}>{project.name}（本机）</option>)}</select></label>
          <button className="button secondary reproduction-refresh" type="button" onClick={() => setReloadKey((value) => value + 1)} disabled={tasks.status === 'loading'} aria-label="刷新复现任务"><Icon name="refresh" size={15} /></button>
        </div>}
        {layoutPreview ? <div className="reproduction-empty" role="status"><span className="reproduction-empty__mark"><Icon name="book" size={21} /></span><div><h3>当前没有任务记录</h3></div></div>
          : tasks.status === 'loading' || tasks.status === 'idle' ? <div className="reproduction-empty" role="status"><span className="reproduction-empty__mark"><Icon name="clock" size={21} /></span><div><h3>正在读取任务</h3></div></div>
          : tasks.status === 'error' ? <div className="reproduction-empty" role="alert"><span className="reproduction-empty__mark"><Icon name="server" size={21} /></span><div><h3>任务列表读取失败</h3><p>{tasks.message}</p><button className="button secondary" type="button" onClick={() => setReloadKey((value) => value + 1)}>重试</button></div></div>
          : visibleTasks.length > 0 ? <div className="reproduction-task-table-wrap"><table className="reproduction-task-table"><thead><tr><th scope="col">核验对象</th><th scope="col">状态</th><th scope="col">关联项目</th><th scope="col">更新时间</th></tr></thead><tbody>{visibleTasks.map((task) => <tr key={task.id}>
            <th scope="row"><button type="button" className="reproduction-task-link" onClick={() => { window.location.hash = `workbench/reproductions/${encodeURIComponent(task.id)}` }}><strong>{task.title}</strong><small>{task.claim || task.source || '尚未填写主张或来源'}</small><span>{task.kind === 'paper' ? '论文复现' : '实验核验'}{'sync_state' in task && task.sync_state === 'local_only' ? ' · 本机' : ''}</span></button></th>
            <td><span className={`reproduction-status-badge reproduction-status-badge--${task.status}`}>{reproductionStatusLabel(task.status)}</span></td>
            <td>{task.linked_project_id ? projectNames.get(task.linked_project_id) ?? '关联项目详情未加载' : '独立任务'}</td>
            <td><time dateTime={task.updated_at}>{dateTime(task.updated_at)}</time></td>
          </tr>)}</tbody></table></div>
          : <div className="reproduction-empty" role="status"><span className="reproduction-empty__mark"><Icon name="book" size={21} /></span><div><h3>{hasTasksForKind && hasActiveFilters ? '没有符合筛选条件的任务' : '还没有任务'}</h3>{hasActiveFilters ? <button className="link-button" type="button" onClick={() => { setQuery(''); setStatusFilter(''); setProjectFilter(''); window.location.hash = 'workbench/reproductions' }}>清除筛选</button> : tasks.status === 'ready' && <button className="link-button" type="button" onClick={() => setReloadKey((value) => value + 1)}><Icon name="refresh" size={14} />刷新任务</button>}</div></div>}
      </>}
    </section>
  </div>
}

function ReproductionDraftForm({ kind, onKindChange, onCancel, onSubmit, projects, preview, localOnly, config }: {
  kind: ReproductionKind
  onKindChange: (kind: ReproductionKind) => void
  onCancel: () => void
  onSubmit: (input: ReproductionTaskCreateInput) => Promise<void>
  projects: State<ProjectListItem[]>
  preview: boolean
  localOnly: boolean
  config: ApiConfig
}) {
  const [title, setTitle] = useState('')
  const [source, setSource] = useState('')
  const [claim, setClaim] = useState('')
  const [referenceResult, setReferenceResult] = useState('')
  const [methodMaterials, setMethodMaterials] = useState('')
  const [decisionRule, setDecisionRule] = useState('')
  const [limitations, setLimitations] = useState('')
  const [linkedProjectId, setLinkedProjectId] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    if (!title.trim()) { setError('请填写任务名称。'); return }
    if (preview || (!localOnly && !config.token.trim())) return
    setSaving(true)
    const baselineValues = {
      reported_result_or_expected_value: referenceResult.trim(),
      method_and_materials: methodMaterials.trim(),
      decision_rule: decisionRule.trim(),
      limitations: limitations.trim(),
    }
    const baselineEntries = Object.entries(baselineValues).filter(([, value]) => value)
    try {
      await onSubmit({
        title: title.trim(),
        kind,
        source: source.trim(),
        claim: claim.trim(),
        baseline: baselineEntries.length ? Object.fromEntries(baselineEntries) : null,
        criteria_version: null,
        linked_project_id: linkedProjectId || null,
      })
    } catch (saveError) {
      setError(reproductionErrorMessage(saveError, 'create'))
    } finally {
      setSaving(false)
    }
  }

  return <form className="reproduction-draft" onSubmit={submit}>
    <div className="section-heading reproduction-draft__heading"><div><h2>{kind === 'paper' ? '新建论文复现任务' : '新建实验核验任务'}</h2></div><button className="button secondary" type="button" onClick={onCancel}>返回任务列表</button></div>
    <div className="reproduction-draft__notice" id="reproduction-draft-notice" role="status"><Icon name={preview ? 'server' : 'shield'} size={17} /><span><strong>{preview ? '此处为布局预览' : localOnly ? '仅保存在本机，不会自动同步' : '任务创建不会启动科研运行'}</strong><small>{preview ? '表单内容不会发送或保存。' : localOnly ? '联网后也不会自动上传；当前只保存任务定义，真实比较与科研结论仍未生成。' : '任务会先以“待准备”状态保存；运行结果与结论需由后续真实工作流产生。'}</small></span></div>
    <div className="type-tabs" role="tablist" aria-label="复现任务类型">
      <button type="button" role="tab" aria-selected={kind === 'paper'} className={kind === 'paper' ? 'active' : ''} onClick={() => onKindChange('paper')}>论文复现</button>
      <button type="button" role="tab" aria-selected={kind === 'experiment'} className={kind === 'experiment' ? 'active' : ''} onClick={() => onKindChange('experiment')}>实验核验</button>
    </div>
    <div className="reproduction-form">
      <section className="reproduction-form__section"><h3>{kind === 'paper' ? '论文依据' : '实验目标与依据'}</h3><div className="reproduction-form__grid">
        <label>{kind === 'paper' ? '论文标题' : '任务名称'}<input required maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} placeholder={kind === 'paper' ? '填写论文标题' : '填写实验核验任务名称'} /></label>
        <label>{kind === 'paper' ? '论文来源（DOI / URL）' : '实验方案或数据来源'}<input maxLength={20_000} value={source} onChange={(event) => setSource(event.target.value)} placeholder={kind === 'paper' ? '填写 DOI、链接或文献编号' : '填写实验方案、数据或协议来源'} /></label>
        <label className="reproduction-form__wide">{kind === 'paper' ? '待核查的具体主张' : '实验目标与可判定范围'}<textarea rows={3} maxLength={20_000} value={claim} onChange={(event) => setClaim(event.target.value)} placeholder={kind === 'paper' ? '描述论文中希望复现的主张及其范围' : '说明需要核验的实验问题和可判定范围'} /></label>
      </div></section>
      <section className="reproduction-form__section"><h3>参考结果与预设口径</h3><div className="reproduction-form__grid">
        <label className="reproduction-form__wide">{kind === 'paper' ? '文献报告值或图表位置' : '预期指标、单位或基准值'}<textarea rows={2} value={referenceResult} onChange={(event) => setReferenceResult(event.target.value)} placeholder={kind === 'paper' ? '填写指标、数值、单位和原文页码 / 图表编号' : '填写预期指标、数值、单位或已有基准'} /></label>
        <label className="reproduction-form__wide">方法、材料或实验参数<textarea rows={3} value={methodMaterials} onChange={(event) => setMethodMaterials(event.target.value)} placeholder="记录方法、数据/代码材料、关键参数或随机种子" /></label>
        <label className="reproduction-form__wide">预设比较规则<textarea rows={2} value={decisionRule} onChange={(event) => setDecisionRule(event.target.value)} placeholder="填写计算方法、指标单位、容差或判定规则；留空时不自动判定结果" /></label>
        <label className="reproduction-form__wide">许可、访问限制或缺失条件<textarea rows={2} value={limitations} onChange={(event) => setLimitations(event.target.value)} placeholder="记录材料许可、数据访问要求或尚缺少的条件" /></label>
      </div></section>
      <section className="reproduction-form__section"><h3>关联项目（可选）</h3><div className="reproduction-form__grid">
        <label>项目<select value={linkedProjectId} onChange={(event) => setLinkedProjectId(event.target.value)} disabled={projects.status !== 'ready' || preview}><option value="">独立创建，不关联项目</option>{projects.status === 'ready' && projects.data.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
        <p className="reproduction-form__hint">{projects.status === 'ready' ? '任务可以独立存在。选中项目时，服务会将任务放入该项目所属工作空间并核对你的访问权限。' : '项目目录尚未加载，本次仍可独立创建；连接项目服务后可选择关联项目。'}</p>
      </div></section>
      <ReproductionWorkflowField preview={preview} />
    </div>
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="reproduction-draft__actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" type="submit" disabled={saving || preview || (!localOnly && !config.token.trim())} aria-describedby="reproduction-draft-notice">{saving ? '正在保存…' : kind === 'paper' ? '创建复现任务' : '创建核验任务'}</button></div>
  </form>
}

function ReproductionWorkflowField({ preview }: { preview: boolean }) {
  return <section className="reproduction-form__section reproduction-workflow">
    <h3>任务工作流</h3>
    <div className="reproduction-workflow__actions">
      <button type="button" className="button secondary" disabled title="模板复制到复现任务的服务尚未接入"><Icon name="template" size={15} />从模板创建</button>
      <button type="button" className="button secondary" disabled title="请先保存任务，再从任务详情创建工作流"><Icon name="workflow" size={15} />创建空白工作流</button>
    </div>
    <p className="reproduction-workflow__status" role="status">{preview ? '开发态布局预览；此表单不会保存数据。' : '本机任务保存后可创建归属工作流，并使用已安装的本机组件运行。'}</p>
  </section>
}

function ReproductionTaskDetail({ config, projects, localProjects, taskId, workflowId, onBack, onSettings }: {
  config: ApiConfig
  projects: State<ProjectListItem[]>
  localProjects: State<LocalProject[]>
  taskId: string
  workflowId: string | null
  onBack: () => void
  onSettings: () => void
}) {
  const isLocalTask = taskId.startsWith('local-reproduction-')
  const [state, setState] = useState<State<ReproductionTask>>({ status: 'idle' })
  const [reloadKey, setReloadKey] = useState(0)
  const [workflowsState, setWorkflowsState] = useState<State<WorkflowSummary[]>>({ status: 'idle' })
  const [workflowReloadKey, setWorkflowReloadKey] = useState(0)
  const [localRunState, setLocalRunState] = useState<State<Array<{ workflow: LocalWorkflowSummary; run: LocalWorkflowRunDetail }>>>({ status: 'idle' })
  const [recoveringRunId, setRecoveringRunId] = useState<string | null>(null)
  const [recoveryNotice, setRecoveryNotice] = useState<string | null>(null)
  const [recoveryError, setRecoveryError] = useState<string | null>(null)
  const [localReportState, setLocalReportState] = useState<State<LocalCsvPreflightReport | LocalCsvDescriptiveSummaryReport>>({ status: 'idle' })
  const [creatingWorkflow, setCreatingWorkflow] = useState(false)
  const [workflowCreateError, setWorkflowCreateError] = useState<string | null>(null)
  const previousWorkflowId = useRef<string | null>(workflowId)
  useEffect(() => {
    if (!isLocalTask && !config.token.trim()) { setState({ status: 'idle' }); return }
    const controller = new AbortController()
    setState({ status: 'loading' })
    const taskRequest = isLocalTask
      ? getLocalReproductionTask(taskId)
      : getReproductionTask(config, taskId, controller.signal)
    taskRequest
      .then((task) => setState({ status: 'ready', data: task }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({ status: 'error', message: reproductionErrorMessage(error, 'load') })
      })
    return () => controller.abort()
  }, [config.baseUrl, config.token, taskId, reloadKey, isLocalTask])
  useEffect(() => {
    if (!isLocalTask && !config.token.trim()) { setWorkflowsState({ status: 'idle' }); return }
    const controller = new AbortController()
    setWorkflowsState({ status: 'loading' })
    const workflowsRequest = isLocalTask
      ? listLocalReproductionWorkflows(taskId)
      : listReproductionWorkflows(config, taskId, controller.signal)
    workflowsRequest
      .then((workflows) => setWorkflowsState({ status: 'ready', data: workflows }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setWorkflowsState({ status: 'error', message: explainWorkflowError(error) })
      })
    return () => controller.abort()
  }, [config.baseUrl, config.token, taskId, workflowReloadKey, isLocalTask])
  useEffect(() => {
    if (!isLocalTask || workflowsState.status !== 'ready') {
      setLocalRunState({ status: 'idle' })
      return
    }
    let active = true
    setLocalRunState({ status: 'loading' })
    const loadRuns = async () => {
      try {
        const grouped = await Promise.all(workflowsState.data.map(async (workflow) => ({
          workflow: workflow as LocalWorkflowSummary,
          runs: await listLocalWorkflowRuns(workflow.id),
        })))
        const recentRuns = grouped.flatMap(({ workflow, runs }) => runs.map((run) => ({ workflow, summary: run })))
          .sort((left, right) => Date.parse(right.summary.created_at ?? '') - Date.parse(left.summary.created_at ?? ''))
          .slice(0, 20)
        const details = await Promise.all(recentRuns.map(async ({ workflow, summary }) => ({
          workflow,
          run: await getLocalWorkflowRun(summary.run_id),
        })))
        if (active) setLocalRunState({ status: 'ready', data: details })
      } catch (error) {
        if (active) setLocalRunState({ status: 'error', message: error instanceof LocalRuntimeApiError ? `本机运行记录读取失败（${error.code}）。` : '本机运行记录暂时无法读取。' })
      }
    }
    void loadRuns()
    return () => { active = false }
  }, [isLocalTask, workflowsState, workflowReloadKey])
  useEffect(() => {
    if (previousWorkflowId.current && !workflowId) {
      setWorkflowReloadKey((value) => value + 1)
      setReloadKey((value) => value + 1)
    }
    previousWorkflowId.current = workflowId
  }, [workflowId])

  if (!isLocalTask && !config.token.trim()) return <div className="reproduction-detail-unavailable" role="status"><span className="kicker">任务详情</span><h2>尚未连接服务</h2><p>连接服务后才能读取平台任务；本机任务可以离线打开。</p><button type="button" className="button secondary" onClick={onSettings}>打开服务设置</button><button type="button" className="link-button" onClick={onBack}>返回任务列表</button></div>
  if (state.status === 'idle' || state.status === 'loading') return <div className="reproduction-detail-unavailable" role="status"><span className="kicker">任务详情</span><h2>正在读取任务</h2><p>正在读取本机或平台任务记录。</p></div>
  if (state.status === 'error') return <div className="reproduction-detail-unavailable" role="alert"><span className="kicker">任务详情</span><h2>无法读取任务</h2><p>{state.message}</p><div className="reproduction-preview__actions"><button type="button" className="button secondary" onClick={() => setReloadKey((value) => value + 1)}>重试</button><button type="button" className="link-button" onClick={onBack}>返回任务列表</button></div></div>

  const task = state.data
  const createTaskWorkflow = async () => {
    if (creatingWorkflow) return
    setCreatingWorkflow(true)
    setWorkflowCreateError(null)
    try {
      const workflowName = `${Array.from(task.title).slice(0, 156).join('')} 工作流`
      const workflow = isLocalTask
        ? await createLocalReproductionWorkflow(task.id, { name: workflowName, description: '' })
        : await createReproductionWorkflow(config, task.id, workflowName)
      setWorkflowsState((current) => ({
        status: 'ready',
        data: current.status === 'ready'
          ? [workflow, ...current.data.filter((item) => item.id !== workflow.id)]
          : [workflow],
      }))
      window.location.hash = `workbench/reproductions/${encodeURIComponent(task.id)}/workflows/${encodeURIComponent(workflow.id)}`
    } catch (error) {
      setWorkflowCreateError(explainWorkflowError(error))
    } finally {
      setCreatingWorkflow(false)
    }
  }
  const recoverRun = async (run: LocalWorkflowRunDetail) => {
    if (recoveringRunId) return
    setRecoveringRunId(run.run_id)
    setRecoveryNotice(null)
    setRecoveryError(null)
    try {
      const recovery = await recoverLocalWorkflowRun(run.run_id)
      const restoredCount = recovery.restored_node_ids.length
      const rerunCount = recovery.rerun_node_ids.length
      setRecoveryNotice(`恢复运行已提交：复用 ${restoredCount} 个节点结果，待调度 ${rerunCount} 个节点。`)
      setWorkflowReloadKey((value) => value + 1)
    } catch (error) {
      setRecoveryError(error instanceof LocalRuntimeApiError
        ? `恢复失败（${error.code}）。原运行记录未更改。`
        : '恢复请求失败。原运行记录未更改。')
    } finally {
      setRecoveringRunId(null)
    }
  }
  if (workflowId) return <WorkflowEditor
    key={workflowId}
    owner={{ type: 'reproduction', id: task.id, name: task.title }}
    config={config}
    workflowId={workflowId}
    backLabel="复现任务"
    onBack={() => { window.location.hash = `workbench/reproductions/${encodeURIComponent(task.id)}` }}
  />
  const projectName = task.linked_project_id && projects.status === 'ready'
    ? projects.data.find((project) => project.id === task.linked_project_id)?.name
    : undefined
  const resolvedProjectName = projectName ?? (task.linked_project_id && localProjects.status === 'ready'
    ? localProjects.data.find((project) => project.id === task.linked_project_id)?.name
    : undefined)
  const readLocalReport = async (componentId: string, artifactId: string) => {
    setLocalReportState({ status: 'loading' })
    try {
      const report = isCsvPreflightComponent(componentId)
        ? await getLocalCsvPreflightReport(artifactId)
        : isCsvDescriptiveSummaryComponent(componentId)
          ? await getLocalCsvDescriptiveSummaryReport(artifactId)
          : null
      setLocalReportState(report ? { status: 'ready', data: report } : { status: 'error', message: '此产物没有本机可读的报告类型。' })
    } catch (error) {
      setLocalReportState({ status: 'error', message: error instanceof LocalRuntimeApiError ? `报告读取失败（${error.code}）。` : '报告读取失败。' })
    }
  }
  const baselineEntries = Object.entries(task.baseline ?? {}).filter(([, value]) => value !== '' && value !== null && value !== undefined)
  const baselineLabels: Record<string, string> = {
    reported_result_or_expected_value: task.kind === 'paper' ? '文献报告值' : '预期结果或基准值',
    method_and_materials: '方法、材料或实验参数',
    decision_rule: '预设比较规则',
    limitations: '许可、访问限制或缺失条件',
  }

  return <div className="reproduction-task-preview">
    <div className="reproduction-preview__toolbar"><button type="button" className="link-button" onClick={onBack}><Icon name="arrow" size={14} className="reproduction-preview__back-icon" />返回论文复现</button><span className={`reproduction-status-badge reproduction-status-badge--${task.status}`}>{reproductionStatusLabel(task.status)}</span></div>
    <header className="reproduction-preview__heading"><div><span className="kicker">工作台 / 论文复现 / 任务详情</span><h1>{task.title}</h1><p>{task.kind === 'paper' ? '论文复现任务' : '实验核验任务'} · {isLocalTask ? '仅保存在本机，不自动同步' : '平台任务'}。</p></div><div className="reproduction-preview__actions"><span className="reproduction-preview__plain-state">{isLocalTask ? '本机 · 不自动同步' : '平台'}</span><button type="button" className="button secondary" disabled title="任务更新接口尚未接入">编辑任务</button></div></header>
    <div className="reproduction-preview__notice" role="status"><Icon name="shield" size={17} /><span><strong>{isLocalTask ? '本机任务已保存；联网后需显式同步' : '任务记录已保存；当前没有复现结论'}</strong><small>{isLocalTask ? '任务、工作流草稿、运行记录与本机报告保留在本机，不会自动上传；复现任务的显式同步入口尚未接入。下方输出仅为结构预检或探索性描述，不构成科研结论。' : '运行结果、符合性判定和人工复核必须来自真实工作流、基准规则与证据。创建任务本身不会生成科研结果。'}</small></span></div>
    <div className="reproduction-detail-grid">
      <main className="reproduction-detail-main">
        <section className="reproduction-detail-section" aria-labelledby="reproduction-task-scope">
          <div className="reproduction-detail-section__heading"><div><span className="kicker">核验对象</span><h2 id="reproduction-task-scope">研究依据与可判定范围</h2></div><span className="reproduction-preview__plain-state">{task.kind === 'paper' ? '论文复现' : '实验核验'}</span></div>
          <dl className="reproduction-detail-fields"><div><dt>{task.kind === 'paper' ? '论文来源' : '实验依据'}</dt><dd>{task.source || '尚未填写'}</dd></div><div><dt>{task.kind === 'paper' ? '待核查主张' : '实验目标'}</dt><dd>{task.claim || '尚未填写'}</dd></div></dl>
        </section>
        <section className="reproduction-detail-section" aria-labelledby="reproduction-task-baseline">
          <div className="reproduction-detail-section__heading"><div><span className="kicker">基准与规则</span><h2 id="reproduction-task-baseline">已保存的参考信息</h2></div></div>
          {baselineEntries.length > 0 ? <dl className="reproduction-detail-fields">{baselineEntries.map(([key, value]) => <div key={key}><dt>{baselineLabels[key] ?? key}</dt><dd>{typeof value === 'string' ? value : JSON.stringify(value)}</dd></div>)}</dl> : <p className="reproduction-preview__plain-state">当前任务没有记录基准结果或比较规则。</p>}
          {task.criteria_version && <p className="reproduction-detail-footnote">规则版本：{task.criteria_version}</p>}
        </section>
        <section className="reproduction-detail-section" id="reproduction-task-workflows" aria-labelledby="reproduction-task-workflows-heading">
          <div className="reproduction-detail-section__heading"><div><span className="kicker">任务工作流</span><h2 id="reproduction-task-workflows-heading">复现流程草稿</h2></div><button type="button" className="button secondary" onClick={() => void createTaskWorkflow()} disabled={creatingWorkflow}>{creatingWorkflow ? '正在创建…' : <><Icon name="plus" size={15} />创建空白工作流</>}</button></div>
          {workflowCreateError && <p className="project-workflow-error" role="alert">{workflowCreateError}</p>}
          {workflowsState.status === 'idle' || workflowsState.status === 'loading'
            ? <div className="project-workflow-state" role="status"><Icon name="clock" size={18} /><span>正在读取此任务所属的工作流。</span></div>
            : workflowsState.status === 'error'
              ? <div className="project-workflow-state project-workflow-state--error" role="alert"><span>{workflowsState.message}</span><button type="button" className="button secondary" onClick={() => setWorkflowReloadKey((value) => value + 1)}>重试</button></div>
              : workflowsState.data.length > 0
                ? <ul className="project-workflow-list">{workflowsState.data.map((workflow) => <li key={workflow.id}><span className="project-workflow-list__icon"><Icon name="workflow" size={16} /></span><span className="project-workflow-list__copy"><strong>{workflow.name}</strong><small>{workflow.description || `草稿修订 ${workflow.revision} · ${workflow.current_version > 0 ? `已创建 v${workflow.current_version}` : '尚无不可变版本'}`}</small></span><button type="button" className="link-button" onClick={() => { window.location.hash = `workbench/reproductions/${encodeURIComponent(task.id)}/workflows/${encodeURIComponent(workflow.id)}` }}>打开画布<Icon name="arrow" size={14} /></button></li>)}</ul>
                : <div className="project-workflow-state project-workflow-state--empty" role="status"><Icon name="workflow" size={19} /><span><strong>此任务还没有工作流</strong><small>创建后会归属于当前复现任务，可在共用画布中编辑并保存草稿。</small></span></div>}
        </section>
        <section className="reproduction-detail-section" aria-labelledby="reproduction-task-evidence">
          <div className="reproduction-detail-section__heading"><div><span className="kicker">运行与证据</span><h2 id="reproduction-task-evidence">运行、产物与复核</h2></div></div>
          {isLocalTask ? <>
            {recoveryNotice && <p className="reproduction-local-run__recovery-note" role="status">{recoveryNotice}</p>}
            {recoveryError && <p className="reproduction-local-run__error" role="alert">{recoveryError}</p>}
            {localRunState.status === 'idle' || localRunState.status === 'loading'
              ? <div className="reproduction-detail-empty" role="status"><Icon name="clock" size={18} /><span><strong>正在读取本机运行记录</strong><small>按当前任务所属工作流汇总本机最近 20 条运行及其节点事件。</small></span></div>
              : localRunState.status === 'error'
                ? <div className="reproduction-detail-empty" role="alert"><Icon name="server" size={18} /><span><strong>本机运行记录暂不可用</strong><small>{localRunState.message}</small></span><button type="button" className="link-button" onClick={() => setWorkflowReloadKey((value) => value + 1)}>重试</button></div>
                : localRunState.data.length === 0
                  ? <div className="reproduction-detail-empty" role="status"><Icon name="workflow" size={18} /><span><strong>暂无本机运行</strong></span></div>
                  : <div className="reproduction-local-runs">{localRunState.data.map(({ workflow, run }) => <article className="reproduction-local-run" key={run.run_id}>
                    <header className="reproduction-local-run__header"><div><span className="kicker">{workflow.name}</span><strong>{runStatusLabel(run.status)}</strong><small>{dateTime(run.created_at)} · {run.target_node_ids.length} 个目标节点{run.recovered_from_run_id ? ` · 恢复自 ${run.recovered_from_run_id}` : ''}</small></div><div className="reproduction-local-run__actions">{run.status === 'failed' && run.error_code === 'LOCAL_WORKER_RESTARTED' && <button type="button" className="button secondary" disabled={recoveringRunId !== null} onClick={() => void recoverRun(run)}>{recoveringRunId === run.run_id ? '正在提交…' : '恢复运行'}</button>}<button type="button" className="link-button" onClick={() => { window.location.hash = `workbench/reproductions/${encodeURIComponent(task.id)}/workflows/${encodeURIComponent(workflow.id)}` }}>打开工作流<Icon name="arrow" size={14} /></button></div></header>{run.status === 'failed' && run.error_code === 'LOCAL_WORKER_RESTARTED' && <p className="reproduction-local-run__recovery-note">恢复会创建新运行并保留这条记录，沿用原执行计划；未完成的节点（包括外部服务节点）会在点击后重新调度。</p>}{run.recovered_from_run_id && <p className="reproduction-local-run__recovery-note">本次运行从 {run.recovered_from_run_id} 恢复，复用了 {run.node_runs.filter((nodeRun) => nodeRun.status === 'RESTORED').length} 个已完成节点结果。</p>}
                    <dl className="reproduction-local-run__meta"><div><dt>运行 ID</dt><dd><code>{run.run_id}</code></dd></div><div><dt>ExecutionPlan 哈希</dt><dd><code>{run.plan_hash}</code></dd></div><div><dt>目标节点</dt><dd>{run.target_node_ids.join('、') || '未提供'}</dd></div></dl>
                    {run.error_code && <p className="reproduction-local-run__error" role="alert">运行错误：{run.error_code}</p>}
                    <details className="reproduction-local-run__details"><summary>节点状态、事件与产物（{run.node_runs.length} 个节点 · {run.events.length} 条事件）</summary>
                      {run.node_runs.length > 0 && <ul className="reproduction-local-run__nodes">{run.node_runs.map((nodeRun) => <li key={nodeRun.node_id}><div><strong>{runStatusLabel(nodeRun.status)}</strong><code>{nodeRun.node_id}</code><small>{nodeRun.component_id}{nodeRun.error_code ? ` · ${nodeRun.error_code}` : ''}</small></div>{collectArtifactHandles(nodeRun.output).map((artifact) => <div className="reproduction-local-run__artifact" key={artifact.artifact_id}><span><strong>{isCsvPreflightComponent(nodeRun.component_id) ? '结构预检报告 · 非科研结果' : isCsvDescriptiveSummaryComponent(nodeRun.component_id) ? '探索性描述统计 · 非科研结论' : artifact.file_name || '运行产物'}</strong><code>{artifact.artifact_id}</code><small>SHA-256 · {artifact.sha256}</small></span>{(isCsvPreflightComponent(nodeRun.component_id) || isCsvDescriptiveSummaryComponent(nodeRun.component_id)) && <button type="button" className="link-button" onClick={() => void readLocalReport(nodeRun.component_id, artifact.artifact_id)}>查看报告<Icon name="arrow" size={14} /></button>}</div>)}</li>)}</ul>}
                      {run.events.length > 0 && <ol className="reproduction-local-run__events">{run.events.map((event) => <li key={event.sequence}><time dateTime={event.occurred_at}>{dateTime(event.occurred_at)}</time><strong>{runStatusLabel(event.status)}</strong><span>{event.node_id ?? '工作流'}</span>{event.error_code && <code>{event.error_code}</code>}</li>)}</ol>}
                    </details>
                  </article>)}</div>}
            {localReportState.status === 'loading' && <div className="reproduction-local-report" role="status">正在读取本机报告…</div>}
            {localReportState.status === 'error' && <div className="reproduction-local-report" role="alert">{localReportState.message}</div>}
            {localReportState.status === 'ready' && <article className="reproduction-local-report" aria-live="polite"><div><span className="kicker">本机产物报告</span><strong>{localReportState.data.label}</strong></div>{localReportState.data.report_type === 'csv_manifest_structural_preflight' ? <><dl><div><dt>结构状态</dt><dd>{localReportState.data.status === 'success' ? '通过' : localReportState.data.status === 'warning' ? '有提示' : '存在阻断项'}</dd></div><div><dt>数据行数</dt><dd>{localReportState.data.row_count.toLocaleString('zh-CN')}</dd></div><div><dt>字段数</dt><dd>{localReportState.data.columns.length}</dd></div><div><dt>问题数</dt><dd>{localReportState.data.issues.length}</dd></div></dl><p>字段：{localReportState.data.columns.join('、') || '未提供'}</p><p>只检查 CSV 清单结构，不验证实验设计、数据真实性或科研结论。</p></> : <><dl><div><dt>数据行数</dt><dd>{localReportState.data.row_count.toLocaleString('zh-CN')}</dd></div><div><dt>字段数</dt><dd>{localReportState.data.column_count}</dd></div><div><dt>摘要方法</dt><dd>{localReportState.data.summary_method}</dd></div></dl><p>字段：{localReportState.data.columns.slice(0, 20).map((column) => column.name).join('、') || '未提供'}{localReportState.data.columns.length > 20 ? ` 等共 ${localReportState.data.columns.length} 个字段` : ''}</p><p>探索性描述统计摘要，不验证实验设计、数据真实性或科研结论。</p></>}</article>}
          </> : <div className="reproduction-detail-empty" role="status"><Icon name="server" size={18} /><span><strong>平台运行与比较尚未接入</strong><small>当前不会伪造运行记录、图表、文件、差异结果或复核意见；连接本机运行时不影响平台任务状态。</small></span></div>}
        </section>
      </main>
      <aside className="rail-card reproduction-detail-rail"><section><span className="kicker">当前状态</span><strong className="reproduction-detail-rail__state">{reproductionStatusLabel(task.status)}</strong></section><section><span className="kicker">关联项目</span><p>{task.linked_project_id ? resolvedProjectName ?? '关联项目名称未加载' : '独立任务'}</p></section><section><span className="kicker">时间</span><dl><div><dt>创建</dt><dd>{dateTime(task.created_at)}</dd></div><div><dt>更新</dt><dd>{dateTime(task.updated_at)}</dd></div></dl></section><section><span className="kicker">任务工作流</span><strong className="reproduction-detail-rail__state">{workflowsState.status === 'ready' ? `${workflowsState.data.length} 条` : workflowsState.status === 'loading' || workflowsState.status === 'idle' ? '正在读取' : '暂不可用'}</strong></section></aside>
    </div>
  </div>
}

// Keep paper recomputation values distinct from experiment workflow run results in both detail and report tables.
function reproductionActualResultLabel(kind: 'paper' | 'experiment') {
  return kind === 'paper' ? '系统实际复算值' : '系统实际运行结果'
}

// These development-only screens expose the V4.0 detail/report layouts without inventing task data.
function ReproductionTaskDetailPreview({ kind, onBack, onOpenReport }: { kind: 'paper' | 'experiment'; onBack: () => void; onOpenReport: (kind: 'paper' | 'experiment') => void }) {
  const [activeKind, setActiveKind] = useState(kind)
  const subjectLabel = activeKind === 'paper' ? '论文主张' : '实验目标'
  const baselineLabel = activeKind === 'paper' ? '文献报告值' : '实验基准值'
  const actualResultLabel = reproductionActualResultLabel(activeKind)

  return <div className="reproduction-task-preview">
    <div className="reproduction-preview__toolbar"><button type="button" className="link-button" onClick={onBack}><Icon name="arrow" size={14} className="reproduction-preview__back-icon" />返回论文复现</button><span className="reproduction-preview__badge">开发态布局预览</span></div>
    <header className="reproduction-preview__heading"><div><span className="kicker">工作台 / 论文复现 / 任务详情</span><h1>{activeKind === 'paper' ? '论文复现任务详情' : '实验核验任务详情'}</h1><p>用于检查任务详情的信息层级；当前没有任务服务、任务记录或运行结果。</p></div><div className="reproduction-preview__actions"><button type="button" className="button secondary" disabled title="复现任务服务尚未接入">编辑任务</button><button type="button" className="button primary" onClick={() => onOpenReport(activeKind)}>查看报告阅读布局</button></div></header>
    <div className="reproduction-preview__notice" role="status"><Icon name="server" size={17} /><span><strong>无真实任务数据</strong><small>所有字段、状态和比较结果均为空；此开发预览不会创建或保存任务。</small></span></div>
    <nav className="reproduction-preview__kind" role="tablist" aria-label="预览任务类型"><button role="tab" aria-selected={activeKind === 'paper'} className={activeKind === 'paper' ? 'active' : ''} onClick={() => setActiveKind('paper')}>论文复现</button><button role="tab" aria-selected={activeKind === 'experiment'} className={activeKind === 'experiment' ? 'active' : ''} onClick={() => setActiveKind('experiment')}>实验核验</button></nav>
    <div className="reproduction-detail-grid">
      <main className="reproduction-detail-main">
        <section className="reproduction-detail-section" aria-labelledby="reproduction-detail-scope">
          <div className="reproduction-detail-section__heading"><div><span className="kicker">核验对象</span><h2 id="reproduction-detail-scope">研究依据与可判定范围</h2></div><span className="reproduction-preview__plain-state">未创建</span></div>
          <dl className="reproduction-detail-fields"><div><dt>{activeKind === 'paper' ? '论文来源' : '实验基准'}</dt><dd>服务接入后显示</dd></div><div><dt>{subjectLabel}</dt><dd>尚无任务数据</dd></div><div><dt>{activeKind === 'paper' ? '文献报告位置' : '实验条件'}</dt><dd>尚无任务数据</dd></div><div><dt>方法与材料</dt><dd>尚无任务数据</dd></div></dl>
        </section>
        <section className="reproduction-detail-section" aria-labelledby="reproduction-detail-evidence">
          <div className="reproduction-detail-section__heading"><div><span className="kicker">依据与来源</span><h2 id="reproduction-detail-evidence">关联证据</h2></div><span className="reproduction-preview__plain-state">无证据实例</span></div>
          <div className="reproduction-evidence-zone">
            <div className="reproduction-evidence-empty" role="status"><span className="reproduction-evidence-empty__icon"><Icon name="file" size={17} /></span><div><strong>尚无关联证据</strong></div><button type="button" className="button secondary" disabled title="证据服务尚未接入">关联证据</button></div>
            <div className="reproduction-evidence-types" aria-label="证据来源类型"><span>文献报告结果</span><span>系统实际复算结果</span><span>运行代码结果</span><span>解释性推断</span></div>
            <p className="reproduction-evidence-note">真实证据卡将显示主张、来源、类型、核查状态和关联对象；限制或强度说明只依据明确规则呈现。</p>
          </div>
        </section>
        <section className="reproduction-detail-section" aria-labelledby="reproduction-detail-comparison">
          <div className="reproduction-detail-section__heading"><div><span className="kicker">结果对比</span><h2 id="reproduction-detail-comparison">{baselineLabel}与实际结果</h2></div><span className="reproduction-preview__plain-state">尚无运行</span></div>
          <div className="reproduction-comparison-table-wrap"><table className="reproduction-comparison-table"><thead><tr><th scope="col">指标</th><th scope="col">{baselineLabel}</th><th scope="col">{actualResultLabel}</th><th scope="col">差异</th><th scope="col">判定</th></tr></thead><tbody><tr><td colSpan={5}>暂无对比数据</td></tr></tbody></table></div>
          <p className="reproduction-detail-footnote">运行成功只表示执行完成；是否符合预设规则需依据已记录的指标、单位和容差判断。</p>
        </section>
        <section className="reproduction-detail-section" aria-labelledby="reproduction-detail-runs">
          <div className="reproduction-detail-section__heading"><div><span className="kicker">执行溯源</span><h2 id="reproduction-detail-runs">任务工作流与运行记录</h2></div></div>
          <div className="reproduction-detail-empty"><Icon name="workflow" size={18} /><span><strong>尚未创建任务工作流</strong></span><div className="reproduction-detail-empty__actions"><button type="button" className="button secondary" disabled title="工作流服务尚未接入">从模板创建</button><button type="button" className="button secondary" disabled title="工作流服务尚未接入">创建空白工作流</button></div></div>
          <div className="reproduction-detail-empty"><Icon name="clock" size={18} /><span><strong>尚无运行记录</strong><small>运行记录将关联工作流版本、参数快照、环境说明、日志和产物。</small></span></div>
        </section>
        <section className="reproduction-detail-section" aria-labelledby="reproduction-detail-review">
          <div className="reproduction-detail-section__heading"><div><span className="kicker">复核记录</span><h2 id="reproduction-detail-review">限制、偏差与人工意见</h2></div></div>
          <div className="reproduction-detail-empty"><Icon name="file" size={18} /><span><strong>尚无复核记录</strong></span></div>
        </section>
      </main>
      <aside className="reproduction-detail-rail" aria-label="任务状态与关联信息">
        <section><span className="kicker">任务状态</span><strong className="reproduction-detail-rail__state">无任务实例</strong><p>此页仅用于核对详情布局。</p></section>
        <section><span className="kicker">预设判定规则</span><p>暂无规则；没有规则时不生成符合或不符合的自动结论。</p></section>
        <section><span className="kicker">关联对象</span><dl><div><dt>项目</dt><dd>可选，当前未关联</dd></div><div><dt>任务数据</dt><dd>无任务实例</dd></div><div><dt>任务工作流</dt><dd>尚未创建</dd></div><div><dt>检验报告</dt><dd>尚未生成</dd></div></dl></section>
      </aside>
    </div>
  </div>
}

// The report preview uses a document reading column and shows structure only, never example findings.
function ReproductionReportPreview({ kind, onBack }: { kind: 'paper' | 'experiment'; onBack: () => void }) {
  const baselineLabel = kind === 'paper' ? '论文报告值' : '实验基准值'
  const actualResultLabel = reproductionActualResultLabel(kind)
  const scopeDescription = kind === 'paper'
    ? '任务建立后显示论文主张、研究范围、方法边界，以及当前可判定的条件。'
    : '任务建立后显示实验目标、核验范围、实验条件，以及当前可判定的条件。'
  const methodDescription = kind === 'paper'
    ? '显示预先设定的指标、单位、计算方法、容差和复现步骤。未设置规则时只展示结果，不自动判定复现成功。'
    : '显示预先设定的指标、单位、计算方法、容差和核验步骤。未设置规则时只展示实际运行结果，不自动判定实验准确。'
  return <div className="reproduction-report-preview">
    <div className="reproduction-preview__toolbar"><button type="button" className="link-button" onClick={onBack}><Icon name="arrow" size={14} className="reproduction-preview__back-icon" />返回任务详情</button><span className="reproduction-preview__badge">开发态布局预览</span></div>
    <article className="reproduction-report-document">
      <header className="reproduction-report-document__header"><span className="kicker">工作台 / 论文复现 / 报告</span><h1>{kind === 'paper' ? '论文复现报告' : '实验核验报告'}</h1><p>报告阅读布局预览</p><div className="reproduction-report-meta"><div><span>报告状态</span><strong>未生成</strong></div><div><span>报告版本</span><strong>未生成</strong></div><div><span>生成时间</span><strong>无</strong></div></div></header>
      <div className="reproduction-report-notice" role="status"><Icon name="server" size={17} /><span><strong>没有可读取的报告</strong><small>检验服务尚未接入；以下仅展示报告章节结构，不包含数据、图表或结论。</small></span></div>
      <section className="reproduction-report-section"><span className="reproduction-report-section__number">01</span><div><h2>核验问题与范围</h2><p>{scopeDescription}</p></div></section>
      <section className="reproduction-report-section"><span className="reproduction-report-section__number">02</span><div><h2>判定规则与方法</h2><p>{methodDescription}</p></div></section>
      <section className="reproduction-report-section reproduction-report-section--comparison"><span className="reproduction-report-section__number">03</span><div><h2>{baselineLabel}与实际结果</h2><div className="reproduction-comparison-table-wrap"><table className="reproduction-comparison-table"><thead><tr><th scope="col">比较项</th><th scope="col">{baselineLabel}</th><th scope="col">{actualResultLabel}</th><th scope="col">差异 / 判定</th></tr></thead><tbody><tr><td colSpan={4}>真实任务运行后显示带来源的比较结果；当前没有报告数据。</td></tr></tbody></table></div></div></section>
      <section className="reproduction-report-section"><span className="reproduction-report-section__number">04</span><div><h2>数据、方法与版本</h2><p>报告将列出数据来源与版本、许可限制、工作流与组件版本、参数、随机种子及环境信息。</p></div></section>
      <section className="reproduction-report-section"><span className="reproduction-report-section__number">05</span><div><h2>差异、限制与人工复核</h2><p>偏差解释、不确定性、条件不足和授权人员的复核意见将在有真实记录后呈现。</p></div></section>
      <section className="reproduction-report-section"><span className="reproduction-report-section__number">06</span><div><h2>运行与产物溯源</h2><p>报告关联的运行 ID、日志、图表、表格、模型或文件在服务接入后按对象来源展示。</p></div></section>
      <footer className="reproduction-report-document__footer">导出能力会在实际报告与格式实现后开放；当前没有可导出的报告。</footer>
    </article>
  </div>
}

type ProjectDetailPageProps = { id: string; name?: string; localProjectSummary?: LocalProject | null; platformProjectSummary?: ProjectListItem | null; workflowId: string | null; config: ApiConfig; platformUnavailable: boolean; onPlatformUnavailable: () => void; onRecordWorkflowOpen: (projectId: string, workflowId: string) => void; onBack: () => void; onDiscussProject: (project: AgentProjectContext) => void; onDiscussWorkflow: (project: AgentProjectContext, workflow: AgentWorkflowContext) => void; onDiscussDataset: (project: AgentProjectContext, dataset: AgentDatasetContext) => void; onOpenReproductions: (taskId?: string, linkedProjectId?: string) => void }

function ProjectDetailPage(props: ProjectDetailPageProps) {
  return props.id.startsWith('local-project-')
    ? <LocalProjectDetailPage {...props} />
    : <PlatformProjectDetailPage {...props} />
}

function LocalProjectDetailPage({ id, name, localProjectSummary, workflowId, config, onRecordWorkflowOpen, onBack }: ProjectDetailPageProps) {
  const [project, setProject] = useState<State<LocalProjectDetail>>({ status: 'loading' })
  const [workflows, setWorkflows] = useState<State<Array<WorkflowSummary & { source?: 'local'; sync_state?: 'local_only' }>>>({ status: 'loading' })
  const [syncState, setSyncState] = useState<State<LocalProjectSyncState>>({ status: 'loading' })
  const [checkingRuntime, setCheckingRuntime] = useState(false)
  const [retry, setRetry] = useState(0)
  const [createOpen, setCreateOpen] = useState(false)
  const [workflowName, setWorkflowName] = useState('')
  const [createBusy, setCreateBusy] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [syncConfirmOpen, setSyncConfirmOpen] = useState(false)
  const [syncBusy, setSyncBusy] = useState(false)
  const [confirmUncertainRetry, setConfirmUncertainRetry] = useState(false)
  const [adoptPlatformProjectId, setAdoptPlatformProjectId] = useState('')
  const [adoptPlatformWorkflowIds, setAdoptPlatformWorkflowIds] = useState<Record<string, string>>({})
  const [syncProgress, setSyncProgress] = useState<string | null>(null)
  const [syncNotice, setSyncNotice] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)

  useEffect(() => {
    let active = true
    setCheckingRuntime(true)
    const cachedProjectDetail = cachedLocalProjectDetail(id)
    const cachedProjectSummary = cachedProjectDetail ? null : cachedLocalProjectSummaryDetail(id, localProjectSummary)
    const cachedProject = cachedProjectDetail ?? cachedProjectSummary
    const cachedWorkflows = cachedLocalProjectWorkflows(id)
    setProject(cachedProject ? { status: 'ready', data: cachedProject, cached: true, partial: cachedProjectSummary !== null } : { status: 'loading' })
    setWorkflows(cachedWorkflows ? { status: 'ready', data: cachedWorkflows, cached: true } : { status: 'loading' })
    setSyncState({ status: 'loading' })
    Promise.all([getLocalProject(id), listLocalProjectWorkflows(id)])
      .then(([projectDetail, items]) => {
        if (!active) return
        cacheLocalProjectDetail(projectDetail)
        cacheProjectWorkflows(id, items)
        setProject({ status: 'ready', data: projectDetail })
        setWorkflows({ status: 'ready', data: items })
        setCheckingRuntime(false)
        getLocalProjectSyncState(id)
          .then((savedSyncState) => { if (active) setSyncState({ status: 'ready', data: savedSyncState }) })
          .catch((error) => {
            console.error('读取本机同步 outbox 失败。', error)
            if (active) setSyncState({ status: 'error', message: '同步状态暂不可用；本机项目和工作流仍可继续使用。' })
          })
      })
      .catch((error) => {
        console.error('读取本机项目或工作流失败。', error)
        if (!active) return
        if (!canFallbackToLocalProjectCache(error)) {
          const message = error instanceof LocalRuntimeApiError
            ? `本机项目请求失败（${error.status} · ${error.code}）。`
            : '本机项目请求失败，未使用缓存覆盖当前状态。'
          setProject({ status: 'error', message })
          setWorkflows({ status: 'error', message: '本机工作流请求失败，未使用缓存覆盖当前状态。' })
          setSyncState({ status: 'error', message })
          setCheckingRuntime(false)
          return
        }
        const cachedProjectDetail = cachedLocalProjectDetail(id)
        const cachedProjectSummary = cachedProjectDetail ? null : cachedLocalProjectSummaryDetail(id, localProjectSummary)
        const cachedProject = cachedProjectDetail ?? cachedProjectSummary
        const cachedWorkflows = cachedLocalProjectWorkflows(id)
        if (cachedProject) setProject({ status: 'ready', data: cachedProject, cached: true, partial: cachedProjectSummary !== null })
        else setProject({ status: 'error', message: '本机运行时暂不可用，且此项目没有可用的目录缓存；运行时恢复后即可读取。' })
        if (cachedWorkflows) setWorkflows({ status: 'ready', data: cachedWorkflows, cached: true })
        else setWorkflows({ status: 'error', message: '本机运行时暂不可用，且此项目的工作流目录没有缓存。' })
        setSyncState({ status: 'error', message: '本机运行时暂不可用；当前仅能查看已缓存的项目内容。' })
        setCheckingRuntime(false)
      })
    return () => { active = false }
  }, [id, localProjectSummary, retry, workflowId])

  const openWorkflow = (workflowId: string) => {
    onRecordWorkflowOpen(id, workflowId)
    window.location.hash = `workbench/projects/${encodeURIComponent(id)}/workflows/${encodeURIComponent(workflowId)}`
  }
  const createWorkflow = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (createBusy || !workflowName.trim()) return
    setCreateBusy(true)
    setCreateError(null)
    try {
      const workflow = await createLocalProjectWorkflow(id, { name: workflowName.trim(), description: '' })
      setWorkflows((current) => {
        const data = [workflow, ...(current.status === 'ready' ? current.data : [])]
        cacheProjectWorkflows(id, data)
        return { status: 'ready', data }
      })
      setWorkflowName('')
      setCreateOpen(false)
      openWorkflow(workflow.id)
    } catch (error) {
      console.error('创建本机空白工作流失败。', error)
      setCreateError(error instanceof LocalRuntimeApiError ? `创建失败（${error.code}）。` : '本机工作流创建失败，请检查运行时日志。')
    } finally {
      setCreateBusy(false)
    }
  }

  const needsUncertainRetryConfirmation = syncState.status === 'ready' && (
    syncState.data.status === 'needs_review' || syncState.data.status === 'pending' ||
    (syncState.data.status === 'conflict' && !syncState.data.platform_project_id) ||
    syncState.data.workflows.some((item) => item.status === 'needs_review' || item.status === 'pending' || (item.status === 'conflict' && !item.platform_workflow_id))
  )
  const syncTargetExists = syncState.status === 'ready' && Boolean(syncState.data.platform_project_id)
  const workflowsNeedingManualLink = workflows.status === 'ready' && syncState.status === 'ready'
    ? workflows.data.filter((workflow) => {
      const record = syncState.data.workflows.find((item) => item.workflow_id === workflow.id)
      return Boolean(record && !record.platform_workflow_id && ['needs_review', 'pending', 'conflict'].includes(record.status))
    })
    : []
  const hasPendingLocalRevision = workflows.status === 'ready' && syncState.status === 'ready' && workflows.data.some((workflow) => {
    const record = syncState.data.workflows.find((item) => item.workflow_id === workflow.id)
    return record?.status === 'pending' || (record?.status === 'synced' && record.source_revision !== workflow.revision)
  })
  const projectSyncLabel = hasPendingLocalRevision ? '本机修订待同步' : localSyncStatusLabel(project.status === 'ready' ? project.data.sync_state : 'local_only')
  const handleSyncProject = async () => {
    if (syncBusy || !config.baseUrl.trim() || !config.token.trim()) return
    setSyncConfirmOpen(false)
    setSyncBusy(true)
    setSyncNotice(null)
    setSyncProgress('准备同步本机项目…')
    try {
      const result = await syncLocalProjectToPlatform(config, id, {
        confirmUncertainRetry,
        adoptExistingPlatformProjectId: adoptPlatformProjectId,
        adoptExistingPlatformWorkflowIds: adoptPlatformWorkflowIds,
        onProgress: (progress) => setSyncProgress(progress.message),
      })
      setSyncNotice({
        kind: 'success',
        message: `平台副本已同步；新增同步 ${result.synchronizedWorkflows} 个工作流，已有 ${result.unchangedWorkflows} 个无需更新。`,
      })
      setConfirmUncertainRetry(false)
      setAdoptPlatformProjectId('')
      setAdoptPlatformWorkflowIds({})
      setRetry((value) => value + 1)
    } catch (error) {
      console.error('本机项目显式同步失败。', error)
      const message = error instanceof LocalProjectSyncError
        ? `${error.message}（${error.code}）`
        : '同步未完成。本机内容仍保留；请查看运行日志后重试。'
      setSyncNotice({ kind: 'error', message })
      setRetry((value) => value + 1)
    } finally {
      setSyncBusy(false)
      setSyncProgress(null)
    }
  }

  const getWorkflowSyncLabel = (workflowId: string, revision: number) => {
    if (syncState.status !== 'ready') return '同步状态读取中'
    const record = syncState.data.workflows.find((item) => item.workflow_id === workflowId)
    if (!record || record.status === 'local_only') return '仅本机'
    if (record.status === 'synced' && record.source_revision !== revision) return '本机有新修订待同步'
    return localSyncStatusLabel(record.status)
  }

  if (project.status === 'idle' || project.status === 'loading') return <><div className="breadcrumb"><button onClick={onBack}>工作台</button><span>/</span>{name || '本机项目'}</div><div className="loading-card">正在读取本机项目…</div></>
  if (project.status === 'error') return <><div className="breadcrumb"><button onClick={onBack}>工作台</button><span>/</span>{name || '本机项目'}</div><div className="error-state" role="alert"><div><h3>无法读取本机项目</h3><p>{project.message}</p></div><button className="button secondary" onClick={() => setRetry((value) => value + 1)}>重试</button></div></>
  const isCachedSnapshot = project.cached === true || (workflows.status === 'ready' && workflows.cached === true)
  const isCheckingCachedSnapshot = checkingRuntime && isCachedSnapshot
  if (workflowId && (!isCachedSnapshot || cachedProjectWorkflowDetail(id, workflowId))) return <WorkflowEditor key={workflowId} owner={{ type: 'project', id, name: project.data.name }} config={config} workflowId={workflowId} backLabel={project.data.name} onBack={() => { window.location.hash = `workbench/projects/${encodeURIComponent(id)}` }} />
  const canOpenCachedWorkflow = (cachedWorkflowId: string) => Boolean(cachedProjectWorkflowDetail(id, cachedWorkflowId))

  return <div className="local-project-detail">
    <div className="breadcrumb"><button onClick={onBack}>工作台</button><span>/</span>{project.data.name}</div>
    <header className="local-project-detail__header">
      <div><span className="kicker">项目工作区</span><h1>{project.data.name}</h1><p>{project.data.description || '尚未填写研究目标'} · {project.data.domain || '未设置研究领域'}</p></div>
      <div className="local-project-detail__sync-actions">
        <span className="local-only-badge"><Icon name={projectSyncLabel === '平台副本已同步' ? 'check' : 'server'} size={14} />{projectSyncLabel}</span>
        <button type="button" className="button secondary" onClick={() => { setConfirmUncertainRetry(false); setSyncConfirmOpen(true) }} disabled={!config.baseUrl.trim() || !config.token.trim() || syncBusy || syncState.status !== 'ready'} title={!config.token.trim() ? '连接平台后可手动同步；本机功能仍可离线使用。' : '明确确认后创建或更新平台项目副本。'}>
          {syncBusy ? '正在同步…' : syncTargetExists && !hasPendingLocalRevision ? '继续同步' : syncTargetExists ? '同步本机更新' : '同步到平台'}
        </button>
      </div>
    </header>
    {isCheckingCachedSnapshot && <p className="project-offline-cache-note" role="status">正在连接本机运行时并校验缓存。项目内容已打开，校验期间可继续查看；确认运行时不可用后会保留缓存只读视图。</p>}
    {isCachedSnapshot && !isCheckingCachedSnapshot && <p className="project-offline-cache-note" role="status">{project.partial
      ? '已根据此设备保存的项目目录摘要打开。本机运行时恢复后才能读取完整项目详情、工作流和数据目录；当前不会把缺失内容显示成空项目。'
      : workflows.status === 'ready' && workflows.cached
        ? '本机运行时暂不可用，当前显示此设备上次读取的项目详情和工作流目录缓存。已有完整画布缓存的工作流可离线打开；创建和运行仍需本机运行时。'
        : '项目详情来自此设备上次保存的缓存；工作流目录当前不可用或尚未缓存。本机运行时恢复后可读取完整内容。'}</p>}
    {syncNotice && <div className={`local-sync-notice local-sync-notice--${syncNotice.kind}`} role={syncNotice.kind === 'error' ? 'alert' : 'status'}>{syncNotice.message}</div>}
    {syncBusy && syncProgress && <div className="local-sync-progress" role="status">{syncProgress}</div>}
    {syncState.status === 'error' && <div className="local-sync-notice local-sync-notice--error" role="status">{syncState.message}缓存项目仍可查看；编辑和运行能力取决于本机运行时是否可用。</div>}
    {syncState.status === 'ready' && ['partial', 'failed', 'conflict', 'needs_review'].includes(syncState.data.status) && <div className="local-sync-notice local-sync-notice--error" role="status">
      {syncState.data.status === 'conflict' ? '平台修订发生变化；本机和平台内容均保留，本次没有覆盖平台内容。' : syncState.data.status === 'needs_review' ? '上次请求结果需要核对；可填入已创建的平台对象 ID，确认无对象后再重试。' : syncState.data.status === 'partial' ? '部分内容已同步；未完成部分保留在本机，可继续同步。' : '同步未完成；本机原件未改变，可检查状态后重试。'}
      {syncState.data.error_code && <small>错误码：{syncState.data.error_code}</small>}
    </div>}
    {syncState.status === 'ready' && syncState.data.platform_project_id && <p className="local-sync-target-note">平台副本 ID：{syncState.data.platform_project_id}。本机项目仍是本地工作副本。<button type="button" className="link-button" onClick={() => { window.location.hash = `workbench/projects/${encodeURIComponent(syncState.data.platform_project_id!)}` }}>打开平台副本</button></p>}
    <section className="local-project-workflows" aria-labelledby="local-workflows-heading">
      <div className="section-heading"><div><span className="kicker">项目组件</span><h2 id="local-workflows-heading">工作流</h2></div><button type="button" className="button primary" onClick={() => setCreateOpen((open) => !open)} disabled={isCachedSnapshot} title={isCachedSnapshot ? isCheckingCachedSnapshot ? '正在校验本机运行时；确认离线后，缓存项目仍可查看。' : '本机运行时不可用时可查看缓存；连接运行时后可创建工作流。' : undefined}><Icon name="plus" size={16} />新建空白工作流</button></div>
      {createOpen && <form className="local-workflow-create" onSubmit={(event) => void createWorkflow(event)}><label>工作流名称<input autoFocus maxLength={120} required value={workflowName} onChange={(event) => setWorkflowName(event.target.value)} placeholder="例如：CSV 清单结构预检" /></label><button type="submit" className="button primary" disabled={createBusy || !workflowName.trim()}>{createBusy ? '创建中…' : '创建并打开画布'}</button></form>}
      {createError && <p className="form-error" role="alert">{createError}</p>}
      {workflows.status === 'loading' && <div className="local-project-catalog__state" role="status">正在读取本机工作流…</div>}
      {workflows.status === 'error' && <div className="local-project-catalog__state local-project-catalog__state--error" role="alert">{workflows.message}<button className="link-button" type="button" onClick={() => setRetry((value) => value + 1)}>重试</button></div>}
      {workflows.status === 'ready' && workflows.data.length === 0 && <div className="local-project-catalog__state">这个本机项目还没有工作流。创建空白画布后，可添加已安装的本机组件。</div>}
      {workflows.status === 'ready' && workflows.data.length > 0 && <ul className="local-workflow-list">{workflows.data.map((workflow) => {
        const cachedCanvasAvailable = canOpenCachedWorkflow(workflow.id)
        const canOpen = !isCachedSnapshot || cachedCanvasAvailable
        return <li key={workflow.id}><span><strong>{workflow.name}</strong><small>草稿修订 {workflow.revision} · {getWorkflowSyncLabel(workflow.id, workflow.revision)}</small></span><button type="button" className="link-button" onClick={() => openWorkflow(workflow.id)} disabled={!canOpen} title={!canOpen ? '此工作流画布未缓存在本机；本机运行时恢复后可打开。' : isCachedSnapshot ? '打开此设备缓存的工作流画布；运行需要本机运行时。' : undefined}>打开画布<Icon name="arrow" size={14} /></button></li>
      })}</ul>}
    </section>
    {syncConfirmOpen && <div className="local-sync-confirm-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !syncBusy) setSyncConfirmOpen(false) }}>
      <section className="local-sync-confirm" role="dialog" aria-modal="true" aria-labelledby="local-sync-confirm-title" aria-describedby="local-sync-confirm-description">
        <button type="button" className="local-sync-confirm__close" aria-label="关闭" onClick={() => setSyncConfirmOpen(false)} disabled={syncBusy}><Icon name="close" size={17} /></button>
        <span className="kicker">显式同步</span><h2 id="local-sync-confirm-title">同步项目到科研平台？</h2>
        <div id="local-sync-confirm-description" className="local-sync-confirm__body">
          <p className="local-sync-confirm__route">来源：本机项目“{project.data.name}” · 目标：{displayPlatformOrigin(config.baseUrl)}（当前配置账号）</p>
          <p>{syncTargetExists ? '这会更新已关联的平台项目副本中的工作流定义' : '这会创建一个新的平台项目副本'}，并同步项目名称、研究领域、说明，以及 {workflows.status === 'ready' ? workflows.data.length : '当前'} 个工作流的名称、说明、画布结构和参数。工作流变化会检查平台修订；发现冲突时停止覆盖。</p>
          <p><strong>同步正文不包含</strong>本机文件、数据集内容、运行记录、报告、日志或访问令牌，也不会启动工作流。平台 API 鉴权仍使用当前配置账号；令牌不会写入项目/工作流内容或本机 outbox。本机原件会保留。画布若引用本机文件，该引用在平台端可能不可用。</p>
          {needsUncertainRetryConfirmation && <p>如果上次请求已经在平台创建了对象，请填入它的平台 ID 以继续；若确认平台没有对应对象，ID 留空后再确认重试。</p>}
        </div>
        {needsUncertainRetryConfirmation && syncState.status === 'ready' && !syncState.data.platform_project_id && <label className="local-sync-confirm__field">已有平台项目 ID<input value={adoptPlatformProjectId} onChange={(event) => setAdoptPlatformProjectId(event.target.value)} placeholder="若平台已创建副本，请粘贴项目 ID" /></label>}
        {workflowsNeedingManualLink.map((workflow) => <label className="local-sync-confirm__field" key={workflow.id}>“{workflow.name}”已有平台工作流 ID<input value={adoptPlatformWorkflowIds[workflow.id] ?? ''} onChange={(event) => setAdoptPlatformWorkflowIds((current) => ({ ...current, [workflow.id]: event.target.value }))} placeholder="若平台已创建工作流，请粘贴工作流 ID" /></label>)}
        {needsUncertainRetryConfirmation && <label className="local-sync-confirm__review"><input type="checkbox" checked={confirmUncertainRetry} onChange={(event) => setConfirmUncertainRetry(event.target.checked)} />我已确认没有其他同步任务正在运行，并核对平台目录；已填入可能已创建对象的 ID，或确认平台没有对应对象。</label>}
        <div className="local-sync-confirm__actions"><button type="button" className="button secondary" onClick={() => setSyncConfirmOpen(false)}>取消</button><button type="button" className="button primary" disabled={syncBusy || (needsUncertainRetryConfirmation && !confirmUncertainRetry)} onClick={() => void handleSyncProject()}>{syncBusy ? '正在同步…' : '确认同步'}</button></div>
      </section>
    </div>}
  </div>
}

function PlatformProjectDetailPage({ id, name, platformProjectSummary, workflowId, config, platformUnavailable, onPlatformUnavailable, onRecordWorkflowOpen, onBack, onDiscussProject, onDiscussWorkflow, onDiscussDataset, onOpenReproductions }: ProjectDetailPageProps) {
  const [state, setState] = useState<State<ProjectDetail>>({ status: 'loading' })
  const [tab, setTab] = useState<ProjectTab>('overview')
  const [datasetDetail, setDatasetDetail] = useState<DatasetResource | null>(null)
  const [retry, setRetry] = useState(0)
  const [relatedReproductions, setRelatedReproductions] = useState<State<ReproductionTask[]>>({ status: 'idle' })
  const [reproductionRetry, setReproductionRetry] = useState(0)
  // A cached project shell is viewable offline but must not unlock platform-only child queries.
  const projectDetailIsCached = state.status === 'ready' && state.cached === true
  useEffect(() => {
    const controller = new AbortController()
    const cachedDetail = cachedProjectDetail(id)
    const cachedSummary = cachedDetail ? null : cachedProjectSummaryDetail(id, platformProjectSummary)
    const cached = cachedDetail ?? cachedSummary
    const cachedState: State<ProjectDetail> | null = cached
      ? { status: 'ready', data: cached, cached: true, partial: cachedSummary !== null }
      : null
    if (!config.token.trim() || platformUnavailable) {
      const unavailableMessage = platformUnavailable
        ? '平台服务当前不可用，且此项目没有本机缓存；连接平台后即可载入。'
        : '平台服务未连接，且此项目没有本机缓存；连接平台后即可载入。'
      setState(cachedState ?? { status: 'error', message: unavailableMessage })
      return () => controller.abort()
    }
    setState(cachedState ?? { status: 'loading' })
    getProject(config, id, controller.signal)
      .then((data) => {
        writeLocalCache(`${localProjectDetailCachePrefix}${encodeURIComponent(id)}`, data, '项目详情')
        setState({ status: 'ready', data })
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        if (isPlatformServiceUnavailable(error)) onPlatformUnavailable()
        if (!canFallbackToPlatformProjectCache(error)) {
          setState({ status: 'error', message: explainError(error) })
          return
        }
        const latestDetail = cachedProjectDetail(id)
        const latestSummary = latestDetail ? null : cachedProjectSummaryDetail(id, platformProjectSummary)
        const fallback = latestDetail ?? latestSummary
        if (fallback) console.warn('平台项目详情不可用，已回退到本机缓存。', { projectId: id, error })
        setState(fallback
          ? { status: 'ready', data: fallback, cached: true, partial: latestSummary !== null }
          : { status: 'error', message: explainError(error) })
      })
    return () => controller.abort()
  }, [config.baseUrl, config.token, id, onPlatformUnavailable, platformProjectSummary, platformUnavailable, retry])
  useEffect(() => {
    if (tab !== 'overview') {
      setRelatedReproductions({ status: 'idle' })
      return
    }
    if (state.status !== 'ready') {
      setRelatedReproductions({ status: 'idle' })
      return
    }
    if (!config.token.trim() || platformUnavailable || projectDetailIsCached) {
      setRelatedReproductions({ status: 'error', unavailable: true, message: '平台服务未连接或暂不可用；关联论文复现目录未缓存。' })
      return
    }
    const controller = new AbortController()
    setRelatedReproductions({ status: 'loading' })
    listReproductionTasks(config, { linked_project_id: id }, controller.signal)
      .then((data) => setRelatedReproductions({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setRelatedReproductions({ status: 'error', message: reproductionErrorMessage(error, 'load') })
      })
    return () => controller.abort()
  }, [config.baseUrl, config.token, id, platformUnavailable, tab, reproductionRetry, state.status, projectDetailIsCached])
  const openWorkflow = (workflowId: string) => {
    onRecordWorkflowOpen(id, workflowId)
    window.location.hash = `workbench/projects/${encodeURIComponent(id)}/workflows/${encodeURIComponent(workflowId)}`
  }
  if (workflowId && state.status === 'ready') return <WorkflowEditor key={workflowId} owner={{ type: 'project', id: state.data.id, name: state.data.name }} config={config} workflowId={workflowId} onDiscussWorkflow={onDiscussWorkflow} onBack={() => { window.location.hash = `workbench/projects/${encodeURIComponent(id)}` }} />
  if (state.status === 'idle' || state.status === 'loading') return <><div className="breadcrumb"><button onClick={onBack}>工作台</button><span>/</span>{name || '项目详情'}</div><div className="loading-card">正在读取项目详情…</div></>
  if (state.status === 'error') return <><div className="breadcrumb"><button onClick={onBack}>工作台</button><span>/</span>{name || '项目详情'}</div><div className="error-state"><div><h3>暂时无法读取项目详情</h3><p>{state.message}</p></div><button className="button secondary" onClick={() => setRetry((v) => v + 1)}>重试</button></div></>
  const project = state.data
  const tabs: [ProjectTab, string, IconName][] = [['overview', '概览', 'panel'], ['workflows', '工作流', 'workflow'], ['resources', '数据', 'database'], ['settings', '项目设置', 'user']]
  return <>
    <div className="breadcrumb"><button onClick={onBack}>工作台</button><span>/</span><strong>{project.name}</strong>{state.cached && <span className="offline-cache-badge">本机副本</span>}</div>
    <div className="project-title"><span className="project-mark"><Icon name="folder" size={22} /></span><div><span className="kicker">项目空间</span><h1>{project.name}</h1><p>{project.domain || '未设置研究领域'} <i>·</i> 我的权限：{projectPermissionLabel(project.role)}</p></div><button className="button secondary" onClick={onBack}>返回项目列表</button><ProjectActionsMenu projectName={project.name} /></div>
    {state.cached && <p className="project-offline-cache-note" role="status">{state.partial
      ? '平台服务未连接或暂不可用。此页面根据最近一次读取的项目目录摘要打开；工作流和数据目录尚未缓存，连接平台后可载入完整内容。'
      : '平台服务未连接或暂不可用。此页面显示此设备上次成功读取的项目详情；可用工作流和数据内容以本机缓存为准。'}</p>}
    {/* 保持项目内导航视觉不变，同时支持单一焦点顺序与键盘标签切换。 */}
    <div className="project-tabs" role="tablist" aria-label="项目导航" onKeyDown={(event) => {
      const items = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
      const currentIndex = items.indexOf(document.activeElement as HTMLButtonElement)
      if (currentIndex < 0) return
      const nextIndex = event.key === 'ArrowRight' ? (currentIndex + 1) % items.length : event.key === 'ArrowLeft' ? (currentIndex - 1 + items.length) % items.length : event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : -1
      if (nextIndex < 0) return
      event.preventDefault()
      items[nextIndex].focus()
      items[nextIndex].click()
    }}>{tabs.map(([id, label, icon]) => <button key={id} id={`project-tab-${id}`} type="button" role="tab" aria-controls={`project-tabpanel-${id}`} aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} className={tab === id ? 'active' : ''} onClick={() => { setTab(id); if (id !== 'resources') setDatasetDetail(null) }}><Icon name={icon} size={16} />{label}</button>)}</div>
    <div className="project-tabpanel" role="tabpanel" id={`project-tabpanel-${tab}`} aria-labelledby={`project-tab-${tab}`} tabIndex={0}>
    {tab === 'overview' && <div className="project-detail-grid">
      <div className="detail-main">
        <section className="content-panel">
          <span className="kicker">项目概览</span><h2>项目说明</h2><p>{project.description || '还没有填写项目说明。'}</p>
          <div className="project-facts"><span>研究领域<strong>{project.domain || '未设置'}</strong></span><span>创建时间<strong>{date(project.created_at)}</strong></span></div>
          <div className="project-overview__actions"><button className="button secondary" onClick={() => onDiscussProject({ id: project.id, name: project.name })}><Icon name="agent" size={16} />在 Agent 对话中引用项目<Icon name="arrow" size={15} /></button></div>
        </section>
        <section className="content-panel">
          <div className="section-heading"><div><h2>最近工作流</h2></div><button className="link-button" type="button" onClick={() => setTab('workflows')}>查看全部<Icon name="arrow" size={14} /></button></div>
          <ProjectWorkflowOverview projectId={project.id} config={config} projectCached={state.cached === true} platformUnavailable={platformUnavailable} onOpen={openWorkflow} onViewAll={() => setTab('workflows')} />
        </section>
      </div>
      <aside className="project-overview-rail">
        <ProjectDatasetOverview datasets={project.datasets} onOpen={(dataset) => { setDatasetDetail(dataset); setTab('resources') }} onViewAll={() => setTab('resources')} partial={state.partial} />
        <ProjectReproductionSummary state={relatedReproductions} onRetry={() => setReproductionRetry((value) => value + 1)} onOpenTask={(taskId) => onOpenReproductions(taskId)} onViewAll={() => onOpenReproductions(undefined, project.id)} />
      </aside>
    </div>}
    {tab === 'workflows' && <div className="project-detail-grid"><section className="content-panel"><div className="section-heading"><div><h2>工作流</h2></div></div><ProjectWorkflowPanel project={project} config={config} projectCached={state.cached === true} platformUnavailable={platformUnavailable} onOpen={openWorkflow} /></section></div>}
    {tab === 'resources' && (datasetDetail
      ? <ProjectDatasetDetail projectName={project.name} dataset={datasetDetail} config={config} onBack={() => setDatasetDetail(null)} onDiscussDataset={(dataset) => onDiscussDataset({ id: project.id, name: project.name }, dataset)} />
      : <ProjectResources project={project} projectName={project.name} onOpenDatasetDetail={setDatasetDetail} partial={state.partial} />)}
    {tab === 'settings' && <ProjectSettingsPanel project={project} />}
    </div>
  </>
}

function ProjectReproductionSummary({ state, onRetry, onOpenTask, onViewAll }: {
  state: State<ReproductionTask[]>
  onRetry: () => void
  onOpenTask: (taskId: string) => void
  onViewAll: () => void
}) {
  const tasks = state.status === 'ready' ? state.data : []
  return <section className="rail-card project-inspection-summary" aria-labelledby="project-reproduction-heading">
    <div className="project-reproduction-summary__heading"><div><span className="kicker">项目检验</span><h3 id="project-reproduction-heading">关联论文复现</h3></div><span className="project-reproduction-summary__count">{state.status === 'ready' ? tasks.length : '—'}</span></div>
    {state.status === 'idle' && <p role="status">服务未连接</p>}
    {state.status === 'loading' && <p role="status">正在读取关联任务…</p>}
    {state.status === 'error' && <div className={state.unavailable ? '' : 'project-reproduction-summary__error'} role={state.unavailable ? 'status' : 'alert'}><p>{state.message}</p>{!state.unavailable && <button className="link-button" type="button" onClick={onRetry}>重试</button>}</div>}
    {state.status === 'ready' && tasks.length === 0 && <p role="status">暂无关联任务</p>}
    {state.status === 'ready' && tasks.length > 0 && <>
      <ul className="project-reproduction-list">{tasks.slice(0, 3).map((task) => <li key={task.id}><button className="project-reproduction-list__item" type="button" onClick={() => onOpenTask(task.id)}><span><strong>{task.title}</strong><small>{task.kind === 'paper' ? '论文复现' : '实验核验'} · 更新于 {date(task.updated_at)}</small></span><span className={`reproduction-status-badge reproduction-status-badge--${task.status}`}>{reproductionStatusLabel(task.status)}</span></button></li>)}</ul>
      <button className="link-button project-reproduction-summary__all" type="button" onClick={onViewAll}>查看全部关联任务<Icon name="arrow" size={14} /></button>
    </>}
    {state.status === 'ready' && tasks.length === 0 && <button className="link-button project-reproduction-summary__all" type="button" onClick={onViewAll}>打开论文复现模块<Icon name="arrow" size={14} /></button>}
  </section>
}

function ProjectSettingsPanel({ project, preview = false }: { project: ProjectDetail | null; preview?: boolean }) {
  // The preview deliberately uses unloaded labels; it never substitutes demo project or member data.
  const name = preview ? '未加载' : project?.name ?? '未提供'
  const domain = preview ? '未加载' : project?.domain || '未设置'
  const createdAt = preview ? '未加载' : project ? date(project.created_at) : '未提供'

  return <section className="content-panel project-settings-panel">
    <div className="project-settings-layout">
      <div className="project-settings-basic">
        <div className="section-heading"><div><h2>基本信息</h2></div></div>
        <dl className="settings-facts"><dt>项目名称</dt><dd>{name}</dd><dt>研究领域</dt><dd>{domain}</dd><dt>创建时间</dt><dd>{createdAt}</dd></dl>
      </div>
      <div className="settings-page-section project-settings-members">
        <div className="settings-section-title"><div><h3>成员与权限</h3></div><span className="settings-state-chip"><i />成员服务未接入</span></div>
        <div className="settings-field-list">
          <SettingInfoRow label="我的权限" value={preview ? '未加载' : project ? projectPermissionLabel(project.role) : '未提供'} />
          <SettingInfoRow label="成员名单" value={preview ? '未加载' : '—'} />
          <SettingInfoRow label="成员管理" value={preview ? '未加载' : '—'} />
        </div>
        <div className="settings-service-hint" role="status"><Icon name="users" size={17} /><div><strong>成员目录与管理服务尚未接入</strong></div></div>
      </div>
    </div>
  </section>
}

function ProjectPreviewContext({ activeTab, projectName = '项目名称未加载', subtitle = '研究领域与项目角色尚未加载' }: { activeTab: ProjectTab; projectName?: string; subtitle?: string }) {
  const tabs: [ProjectTab, string, IconName][] = [['overview', '概览', 'panel'], ['workflows', '工作流', 'workflow'], ['resources', '数据', 'database'], ['settings', '项目设置', 'user']]
  const destinations: Record<ProjectTab, string> = {
    overview: '#__preview/project-overview',
    workflows: '#__preview/project-workflows',
    resources: '#__preview/project-resources',
    settings: '#__preview/project-settings',
  }

  return <>
    <div className="breadcrumb"><button onClick={() => { window.location.hash = 'workbench/projects' }}>工作台</button><span>/</span><strong>{projectName}</strong></div>
    <div className="project-title"><span className="project-mark"><Icon name="folder" size={22} /></span><div><span className="kicker">项目空间</span><h1>{projectName}</h1><p>{subtitle}</p></div><button className="button secondary" onClick={() => { window.location.hash = 'workbench/projects' }}>返回项目列表</button><ProjectActionsMenu projectName={projectName} /></div>
    <div className="project-tabs" role="tablist" aria-label="项目内导航">{tabs.map(([id, label, icon]) => <button key={id} type="button" role="tab" aria-selected={id === activeTab} className={id === activeTab ? 'active' : ''} onClick={() => { window.location.hash = destinations[id] }}><Icon name={icon} size={16} />{label}</button>)}</div>
  </>
}

function ProjectSettingsPreview() {
  return <div className="project-settings-preview">
    <div className="workflow-preview-banner" role="status"><Icon name="server" size={16} /><span><strong>开发态布局预览 · 项目设置数据未加载</strong><small>此页不读取或创建项目；基本信息、成员名单与当前权限均未加载。</small></span></div>
    <ProjectPreviewContext activeTab="settings" />
    <ProjectSettingsPanel project={null} preview />
  </div>
}

const datasetSourceLabels: Record<string, string> = { synthetic: '合成数据' }
const datasetLicenseStatusLabels: Record<string, string> = { not_applicable: '不适用' }

function datasetSourceLabel(source: string) {
  const normalized = source.trim()
  return normalized ? datasetSourceLabels[normalized] ?? normalized : '未提供'
}

function datasetLicenseStatusLabel(status: string) {
  const normalized = status.trim()
  return normalized ? datasetLicenseStatusLabels[normalized] ?? normalized : '未提供'
}

function datasetSourceAndLicenseLabel(dataset: DatasetResource) {
  return `${datasetSourceLabel(dataset.source)} · 授权 ${datasetLicenseStatusLabel(dataset.license_status)}`
}

function ProjectDatasetOverview({ datasets, onOpen, onViewAll, preview = false, partial = false }: { datasets: DatasetResource[]; onOpen: (dataset: DatasetResource) => void; onViewAll: () => void; preview?: boolean; partial?: boolean }) {
  return <section className="rail-card project-dataset-overview" aria-labelledby="project-dataset-overview-title">
    <div className="project-dataset-overview__heading"><div><span className="kicker">项目数据</span><h3 id="project-dataset-overview-title">数据集版本</h3></div><small>{preview ? '未加载' : partial ? '目录未缓存' : `${datasets.length} 个版本`}</small></div>
    {datasets.length > 0 ? <ul className="project-dataset-overview__list">{datasets.slice(0, 3).map((dataset) => <li key={dataset.id}>
      <button className="project-dataset-overview__item" type="button" onClick={() => onOpen(dataset)} aria-label={`查看数据集版本 ${dataset.version}`}>
        <span className="project-dataset-overview__copy"><strong title={dataset.version}>{dataset.version}</strong><small title={dataset.id}>{dataset.id}</small><small title={datasetSourceAndLicenseLabel(dataset)}>{datasetSourceAndLicenseLabel(dataset)}</small></span>
        <span className={dataset.research_ready ? 'ready-chip' : 'blocked-chip'}>{dataset.research_ready ? '科研可用' : '不可用于科研'}</span>
      </button>
    </li>)}</ul> : <div className="project-dataset-overview__empty" role="status">{preview ? '项目数据尚未加载。' : partial ? '项目数据目录尚未缓存；连接平台后可读取。' : '当前项目没有返回数据集版本。'}</div>}
    <button className="link-button" type="button" onClick={onViewAll}>{datasets.length > 3 ? `查看全部 ${datasets.length} 个版本` : '查看数据'}<Icon name="arrow" size={14} /></button>
  </section>
}

function ProjectWorkflowUnavailable() {
  return <div className="workflow-start-state">
    <div className="workflow-start-state__lead"><span className="workflow-start-state__mark"><Icon name="workflow" size={19} /></span><div><span className="kicker">工作流服务未接入</span><h3>接入服务后查看或创建项目工作流</h3><p>当前无法读取已保存的流程；列表为空不代表项目没有工作流。</p></div></div>
    <div className="workflow-start-state__choices" aria-label="工作流起步方式">
      <button type="button" className="workflow-start-option" disabled title="模板使用目标选择与副本创建服务尚未接入"><span className="workflow-start-option__icon"><Icon name="template" size={17} /></span><span className="workflow-start-option__copy"><strong>从模板创建</strong><small>选择模板并创建到当前项目</small></span><em>服务未接入</em></button>
      <button type="button" className="workflow-start-option" disabled title="工作流保存服务尚未接入"><span className="workflow-start-option__icon"><Icon name="workflow" size={17} /></span><span className="workflow-start-option__copy"><strong>新建空白工作流</strong><small>在项目内的画布中开始编排</small></span><em>服务未接入</em></button>
    </div>
  </div>
}

function ProjectWorkflowOverview({ projectId, config, projectCached, platformUnavailable, onOpen, onViewAll }: { projectId: string; config: ApiConfig; projectCached: boolean; platformUnavailable: boolean; onOpen: (workflowId: string) => void; onViewAll: () => void }) {
  const [state, setState] = useState<State<WorkflowSummary[]>>({ status: 'loading' })
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    if (platformUnavailable || projectCached || !config.token.trim()) {
      const cached = cachedProjectWorkflows(projectId)
      setState(cached
        ? { status: 'ready', data: cached, cached: true }
        : { status: 'error', unavailable: true, message: '平台服务未连接或暂不可用；此项目的工作流目录未缓存。' })
      return () => controller.abort()
    }
    setState({ status: 'loading' })
    listProjectWorkflows(config, projectId, controller.signal)
      .then((workflows) => { cacheProjectWorkflows(projectId, workflows); setState({ status: 'ready', data: workflows }) })
      .catch((error) => {
        if (controller.signal.aborted) return
        const cached = cachedProjectWorkflows(projectId)
        setState(cached ? { status: 'ready', data: cached, cached: true } : { status: 'error', message: explainWorkflowError(error) })
      })
    return () => controller.abort()
  }, [config.baseUrl, config.token, platformUnavailable, projectCached, projectId, retry])

  return <div className="project-workflow-panel">
    <div className="project-workflow-toolbar"><span>{state.status === 'ready' ? `${state.data.length} 个已保存工作流${state.cached ? ' · 本机缓存' : ''}` : '按最近更新时间排列'}</span></div>
    {state.status === 'ready' && state.cached && <p className="project-offline-cache-note" role="status">列表来自本机缓存；打开后可编辑已缓存工作流，并使用已安装的本机组件。</p>}
    {state.status === 'loading' && <div className="project-workflow-state" role="status">正在读取项目工作流…</div>}
    {state.status === 'error' && <div className={'project-workflow-state' + (state.unavailable ? '' : ' project-workflow-state--error')} role={state.unavailable ? 'status' : 'alert'}><span>{state.message}</span>{!state.unavailable && <button className="link-button" type="button" onClick={() => setRetry((value) => value + 1)}>重试</button>}</div>}
    {state.status === 'ready' && state.data.length === 0 && <div className="project-workflow-state project-workflow-state--empty" role="status"><Icon name="workflow" size={18} /><span><strong>这个项目还没有工作流</strong><small>可在当前项目内从空白画布开始，或使用可用模板。</small></span><button className="link-button" type="button" onClick={onViewAll}>查看项目工作流<Icon name="arrow" size={14} /></button></div>}
    {state.status === 'ready' && state.data.length > 0 && <ul className="project-workflow-list">{state.data.slice(0, 3).map((workflow) => <li key={workflow.id}>
      <div className="project-workflow-list__icon"><Icon name="workflow" size={17} /></div>
      <div className="project-workflow-list__copy"><strong>{workflow.name}</strong><small>{workflow.description || '尚无说明'} · 草稿修订 {workflow.revision} · {workflow.current_version > 0 ? `版本 v${workflow.current_version}` : '尚无版本'} · 更新于 {dateTime(workflow.updated_at)}</small></div>
      <button className="link-button" type="button" onClick={() => onOpen(workflow.id)}>继续编辑<Icon name="arrow" size={14} /></button>
    </li>)}</ul>}
  </div>
}

function ProjectWorkflowPanel({ project, config, projectCached, platformUnavailable, onOpen }: { project: ProjectDetail; config: ApiConfig; projectCached: boolean; platformUnavailable: boolean; onOpen: (workflowId: string) => void }) {
  const [state, setState] = useState<State<WorkflowSummary[]>>({ status: 'loading' })
  const [retry, setRetry] = useState(0)
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const canCreate = project.role === 'operator'

  useEffect(() => {
    const controller = new AbortController()
    if (platformUnavailable || projectCached || !config.token.trim()) {
      const cached = cachedProjectWorkflows(project.id)
      setState(cached
        ? { status: 'ready', data: cached, cached: true }
        : { status: 'error', unavailable: true, message: '平台服务未连接或暂不可用；此项目的工作流目录未缓存。' })
      return () => controller.abort()
    }
    setState({ status: 'loading' })
    listProjectWorkflows(config, project.id, controller.signal)
      .then((items) => { cacheProjectWorkflows(project.id, items); setState({ status: 'ready', data: items }) })
      .catch((error) => {
        if (controller.signal.aborted) return
        const cached = cachedProjectWorkflows(project.id)
        setState(cached ? { status: 'ready', data: cached, cached: true } : { status: 'error', message: explainWorkflowError(error) })
      })
    return () => controller.abort()
  }, [config.baseUrl, config.token, platformUnavailable, projectCached, project.id, retry])

  const submitCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!canCreate || platformUnavailable || !config.token.trim() || isCreating || !name.trim()) return
    setIsCreating(true)
    setActionError(null)
    try {
      const workflow = await createProjectWorkflow(config, project.id, name.trim())
      setState((current) => current.status === 'ready'
        ? { status: 'ready', data: [workflow, ...current.data] }
        : current)
      setName('')
      setCreateOpen(false)
      onOpen(workflow.id)
    } catch (error) {
      setActionError(explainWorkflowError(error))
    } finally {
      setIsCreating(false)
    }
  }

  return <div className="project-workflow-panel">
    <div className="project-workflow-toolbar">
      <span>{state.status === 'ready' ? `${state.data.length} 个已保存工作流` : '项目内的工作流草稿与版本'}</span>
      <button type="button" className="button secondary" onClick={() => { setCreateOpen((open) => !open); setActionError(null) }} disabled={!canCreate || platformUnavailable || !config.token.trim() || state.status === 'ready' && state.cached} title={!canCreate ? '当前项目成员角色无权创建工作流' : platformUnavailable || !config.token.trim() ? '连接平台项目服务后才能创建平台工作流' : state.status === 'ready' && state.cached ? '平台离线时不能在平台创建工作流' : undefined}>
        <Icon name="plus" size={15} />新建工作流
      </button>
    </div>
    {!canCreate && <p className="project-workflow-permission">当前账号可查看项目工作流；创建和保存需要项目操作权限。</p>}
    {state.status === 'ready' && state.cached && <p className="project-offline-cache-note" role="status">工作流列表来自本机缓存。离线时只能修改已缓存的工作流；更改保存在本机，恢复连接后需手动同步。</p>}
    {createOpen && <form className="project-workflow-create" onSubmit={submitCreate}>
      <label><span>工作流名称</span><input autoFocus required minLength={1} maxLength={160} value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：数据核验流程" /></label>
      <button className="button primary" type="submit" disabled={isCreating || !name.trim()}>{isCreating ? '创建中…' : '创建并打开'}</button>
    </form>}
    {actionError && <div className="project-workflow-error" role="alert">{actionError}</div>}
    {state.status === 'loading' && <div className="project-workflow-state" role="status">正在读取项目工作流…</div>}
    {state.status === 'error' && <div className={'project-workflow-state' + (state.unavailable ? '' : ' project-workflow-state--error')} role={state.unavailable ? 'status' : 'alert'}><span>{state.message}</span>{!state.unavailable && <button className="link-button" type="button" onClick={() => setRetry((value) => value + 1)}>重试</button>}</div>}
    {state.status === 'ready' && state.data.length === 0 && <div className="project-workflow-state project-workflow-state--empty" role="status"><Icon name="workflow" size={18} /><span><strong>这个项目还没有工作流</strong><small>创建后会保存为项目草稿；尚未接入的科研组件和运行能力会单独标示。</small></span></div>}
    {state.status === 'ready' && state.data.length > 0 && <ul className="project-workflow-list">{state.data.map((workflow) => <li key={workflow.id}>
      <div className="project-workflow-list__icon"><Icon name="workflow" size={17} /></div>
      <div className="project-workflow-list__copy"><strong>{workflow.name}</strong><small>{workflow.description || '尚无说明'} · 草稿修订 {workflow.revision} · {workflow.current_version > 0 ? `版本 v${workflow.current_version}` : '尚无版本'} · 更新于 {dateTime(workflow.updated_at)}</small></div>
      <button className="link-button" type="button" onClick={() => onOpen(workflow.id)}>打开画布<Icon name="arrow" size={14} /></button>
    </li>)}</ul>}
  </div>
}

function ProjectOverviewPreview() {
  return <div className="project-overview-preview">
    <div className="workflow-preview-banner" role="status"><Icon name="server" size={16} /><span><strong>开发态布局预览 · 无项目数据</strong><small>此预览不创建项目、工作流或运行；名称、ID、时间和统计值均未加载。</small></span></div>
    <ProjectPreviewContext activeTab="overview" />
    <div className="project-detail-grid">
      <div className="detail-main">
        <section className="content-panel">
          <span className="kicker">项目概览</span><h2>项目说明</h2><p>项目说明尚未加载。</p>
          <div className="project-facts"><span>研究领域<strong>未加载</strong></span><span>创建时间<strong>未加载</strong></span></div>
          <div className="project-overview__actions"><button className="button secondary" disabled title="引用项目需要真实项目上下文"><Icon name="agent" size={16} />在 Agent 对话中引用项目<Icon name="arrow" size={15} /></button></div>
        </section>
        <section className="content-panel">
          <div className="section-heading"><div><h2>最近工作流</h2></div><button className="link-button" type="button" onClick={() => { window.location.hash = '__preview/project-workflows' }}>查看全部<Icon name="arrow" size={14} /></button></div>
          <div className="project-workflow-state project-workflow-state--empty" role="status"><Icon name="workflow" size={18} /><span><strong>工作流尚未加载</strong></span></div>
        </section>
      </div>
      <aside className="project-overview-rail">
        <ProjectDatasetOverview datasets={[]} preview onOpen={() => undefined} onViewAll={() => { window.location.hash = '__preview/project-resources' }} />
        <section className="rail-card project-inspection-summary"><span className="kicker">关联论文复现</span><p>论文复现任务在工作台独立管理；项目关联信息尚未加载。</p><button className="link-button" onClick={() => { window.location.hash = 'workbench/reproductions' }}>打开论文复现模块<Icon name="arrow" size={14} /></button></section>
      </aside>
    </div>
  </div>
}

function ProjectWorkflowListPreview() {
  return <div className="project-workflow-preview">
    <div className="workflow-preview-banner" role="status"><Icon name="server" size={16} /><span><strong>开发态布局预览 · 项目工作流数据未加载</strong><small>本页不会创建或保存工作流。</small></span></div>
    <ProjectPreviewContext activeTab="workflows" />
    <div className="project-detail-grid"><section className="content-panel"><div className="section-heading"><div><h2>工作流</h2></div><button className="button secondary" title="只检查布局，不创建或启动工作流" onClick={() => { window.location.hash = '__preview/workflow-editor' }}>预览工作流编辑器</button></div><ProjectWorkflowUnavailable /></section></div>
  </div>
}

function ProjectResources({ project, projectName, onOpenDatasetDetail, preview = false, partial = false }: { project: ProjectDetail | null; projectName: string | null; onOpenDatasetDetail: (dataset: DatasetResource) => void; preview?: boolean; partial?: boolean }) {
  const [query, setQuery] = useState('')
  const [readiness, setReadiness] = useState<'all' | 'ready' | 'blocked'>('all')
  const [sourceFilter, setSourceFilter] = useState('')
  const [view, setView] = useState<'cards' | 'table'>('cards')
  const [uploadPreviewOpen, setUploadPreviewOpen] = useState(false)
  const datasets = project?.datasets ?? []
  const hasDatasets = datasets.length > 0
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const sourceOptions = [...new Set(datasets.map((dataset) => dataset.source.trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'))
  const visibleDatasets = datasets.filter((dataset) => {
    const matchesQuery = `${dataset.id} ${dataset.version} ${dataset.source} ${datasetSourceLabel(dataset.source)} ${dataset.license_status} ${datasetLicenseStatusLabel(dataset.license_status)}`.toLocaleLowerCase().includes(normalizedQuery)
    const matchesReadiness = readiness === 'all' || (readiness === 'ready' ? dataset.research_ready : !dataset.research_ready)
    const matchesSource = sourceFilter === '' || dataset.source === sourceFilter
    return matchesQuery && matchesReadiness && matchesSource
  })
  // An empty directory has nothing to filter; keep the view switch only in the layout preview.
  const resourceViewToggle = <div className="resource-view-toggle" role="group" aria-label="数据集版本视图"><button className={view === 'cards' ? 'active' : ''} aria-pressed={view === 'cards'} onClick={() => setView('cards')} disabled={!hasDatasets && !preview}>卡片</button><button className={view === 'table' ? 'active' : ''} aria-pressed={view === 'table'} onClick={() => setView('table')} disabled={!hasDatasets && !preview}>表格</button></div>

  const changeUploadPreview = (open: boolean) => {
    setUploadPreviewOpen(open)
  }

  if (uploadPreviewOpen) return <ProjectUploadFlowPreview projectName={projectName} onBack={() => changeUploadPreview(false)} />

  return <section className={'content-panel resources-panel' + (hasDatasets ? '' : ' resources-panel--empty')}>
    <div className="section-heading resources-heading">
      <div><h2>数据集与版本</h2></div>
      <div className="resources-heading__actions"><span className="count">{partial ? '数据目录未缓存' : project ? `${datasets.length} 个数据集版本` : '未加载项目'}</span><button className="button secondary" disabled aria-describedby="resource-service-status" title="数据上传接口尚未接入"><Icon name="plus" size={15} />上传数据</button>{import.meta.env.DEV && <button type="button" className="link-button resources-preview-link" onClick={() => changeUploadPreview(true)}>预览上传流程</button>}</div>
    </div>
    <p className="resource-service-note" id="resource-service-status"><Icon name="server" size={15} />{preview ? '此开发态预览未加载项目或数据版本；只用于检查目录空态，不代表项目服务已接入。' : partial ? '当前打开的是项目目录摘要，不包含数据集明细；连接平台服务后可读取完整数据目录。' : '数据上传与质量检查服务尚未接入；本页只展示项目服务返回的真实版本信息，不以演示报告替代检查结果。'}</p>
    {hasDatasets && <div className="resource-toolbar">
      <label className={'resource-search' + (!hasDatasets ? ' is-disabled' : '')}><Icon name="search" size={16} /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索数据集 ID、版本或来源" aria-label="搜索项目数据集与版本" disabled={!hasDatasets} /></label>
      {/* Keep V4.0 filters visible on desktop while disabling fields the project API does not provide. */}
      <select className="resource-toolbar__desktop-filter" aria-label="按数据类型筛选" title="当前项目接口未提供数据类型信息" disabled><option>全部类型</option></select>
      <select value={readiness} onChange={(event) => setReadiness(event.target.value as typeof readiness)} aria-label="按科研可用性筛选" disabled={!hasDatasets}><option value="all">全部状态</option><option value="ready">科研可用</option><option value="blocked">不可用于科研</option></select>
      <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} aria-label="按数据来源筛选" disabled={!hasDatasets}><option value="">全部来源</option>{sourceOptions.map((source) => <option key={source} value={source}>{datasetSourceLabel(source)}</option>)}</select>
      <select className="resource-toolbar__desktop-filter" aria-label="按质量状态筛选" title="项目级质量报告接口尚未接入" disabled><option>质量状态未提供</option></select>
      <select className="resource-toolbar__desktop-filter" aria-label="按更新时间筛选" title="当前项目接口未提供更新时间" disabled><option>更新时间未提供</option></select>
      {resourceViewToggle}
    </div>}
    {!hasDatasets && preview && <div className="resource-toolbar resource-toolbar--empty">{resourceViewToggle}</div>}
    {hasDatasets ? visibleDatasets.length === 0 ? <div className="resource-filter-empty"><Icon name="search" size={18} /><span>没有匹配的数据集版本。</span><button className="link-button" onClick={() => { setQuery(''); setReadiness('all'); setSourceFilter('') }}>清除搜索和筛选</button></div> : view === 'cards' ? <div className="resource-card-grid">
      {visibleDatasets.map((dataset) => <article className="resource-card" key={dataset.id}>
        <div className="resource-card__heading"><span className="resource-card__icon"><Icon name="database" size={18} /></span><span className={dataset.research_ready ? 'ready-chip' : 'blocked-chip'}>{dataset.research_ready ? '科研可用' : '不可用于科研'}</span></div>
        <h3 title={dataset.id}>{dataset.id}</h3>
        <dl><div><dt>版本</dt><dd>{dataset.version}</dd></div><div><dt>来源</dt><dd>{datasetSourceLabel(dataset.source)}</dd></div><div><dt>授权状态</dt><dd>{datasetLicenseStatusLabel(dataset.license_status)}</dd></div></dl>
        <button type="button" className="link-button resource-card__report" onClick={() => onOpenDatasetDetail(dataset)}>查看数据详情<Icon name="arrow" size={14} /></button>
      </article>)}
    </div> : <div className="resource-table-wrap"><table className="resource-table resource-table--quality"><thead><tr><th>数据集 ID</th><th>版本</th><th>来源</th><th>授权状态</th><th>科研可用性</th><th>操作</th></tr></thead><tbody>
      {visibleDatasets.map((dataset) => <tr key={dataset.id}><td title={dataset.id}>{dataset.id}</td><td>{dataset.version}</td><td>{datasetSourceLabel(dataset.source)}</td><td>{datasetLicenseStatusLabel(dataset.license_status)}</td><td><span className={dataset.research_ready ? 'ready-chip' : 'blocked-chip'}>{dataset.research_ready ? '科研可用' : '不可用于科研'}</span></td><td><button type="button" className="link-button" onClick={() => onOpenDatasetDetail(dataset)}>查看详情</button></td></tr>)}
    </tbody></table></div> : view === 'cards' ? <div className="resource-empty" role="status"><span className="state-icon"><Icon name="database" /></span><div><h3>{partial ? '数据目录未缓存' : project ? '暂无数据集版本' : '未加载项目数据'}</h3></div></div> : <div className="resource-table-wrap"><table className="resource-table resource-table--quality"><thead><tr><th>数据集 ID</th><th>版本</th><th>来源</th><th>授权状态</th><th>科研可用性</th><th>质量报告</th></tr></thead><tbody><tr><td colSpan={6}><div className="resource-table-empty" role="status"><Icon name="database" size={20} /><strong>{partial ? '数据目录未缓存' : project ? '当前项目暂无数据集版本' : '预览未加载项目或数据'}</strong></div></td></tr></tbody></table></div>}
  </section>
}

type DatasetDetailTab = 'overview' | 'files' | 'versions' | 'quality' | 'usage' | 'metadata'

function ProjectDatasetDetail({ projectName, dataset, config, onBack, onDiscussDataset, preview = false }: { projectName: string; dataset: DatasetResource; config: ApiConfig; onBack: () => void; onDiscussDataset?: (dataset: AgentDatasetContext) => void; preview?: boolean }) {
  const [activeTab, setActiveTab] = useState<DatasetDetailTab>('overview')
  const tabs: [DatasetDetailTab, string][] = [
    ['overview', '概览'],
    ['files', '文件与样本'],
    ['versions', '版本历史'],
    ['quality', '质量报告'],
    ['usage', '使用记录'],
    ['metadata', '元数据'],
  ]
  const readinessLabel = dataset.research_ready ? '科研可用' : '不可用于科研'

  return <div className="dataset-detail-page">
    {preview && <div className="dataset-detail-preview-banner" role="status"><Icon name="database" size={16} /><span><strong>固定合成数据布局预览</strong><small>数据与后端固定演示种子一致，只用于界面检查，不代表真实科研项目或科研结果。</small></span></div>}
    <div className="dataset-detail-toolbar"><button type="button" className="link-button" onClick={onBack}><Icon name="arrow" size={14} className="quality-report-back-icon" />返回数据目录</button><span>{projectName} / 数据集详情</span></div>
    <header className="dataset-detail-header">
      <div className="dataset-detail-heading">
        <span className="kicker">项目数据 / 数据集详情</span>
        <h2>{dataset.version}</h2>
        <div className="dataset-detail-version"><span>数据集 ID <code>{dataset.id}</code></span><span className={dataset.research_ready ? 'ready-chip' : 'blocked-chip'}>{readinessLabel}</span></div>
        {!preview && onDiscussDataset && <button type="button" className="link-button dataset-detail-agent-action" onClick={() => onDiscussDataset({ id: dataset.id, version: dataset.version })}><Icon name="agent" size={15} />在 Agent 对话中引用此数据版本<Icon name="arrow" size={14} /></button>}
      </div>
      <dl className="dataset-detail-summary">
        <div><dt>所属项目</dt><dd>{projectName}</dd></div>
        <div><dt>数据来源</dt><dd>{datasetSourceLabel(dataset.source)}</dd></div>
        <div><dt>授权状态</dt><dd>{datasetLicenseStatusLabel(dataset.license_status)}</dd></div>
      </dl>
    </header>
    <div className="dataset-detail-tabs" role="tablist" aria-label="数据集详情">
      {tabs.map(([id, label]) => <button key={id} type="button" role="tab" id={`dataset-tab-${id}`} aria-selected={activeTab === id} aria-controls="dataset-detail-panel" className={activeTab === id ? 'active' : ''} onClick={() => setActiveTab(id)}>{label}</button>)}
    </div>
    <section className="dataset-detail-tab-panel" id="dataset-detail-panel" role="tabpanel" aria-labelledby={`dataset-tab-${activeTab}`}>
      {activeTab === 'overview' && <div className="dataset-detail-overview-grid">
        <section className="dataset-detail-overview-block">
          <span className="kicker">版本摘要</span><h3>当前数据版本</h3>
          <dl className="dataset-detail-facts">
            <div><dt>数据集 ID</dt><dd><code>{dataset.id}</code></dd></div>
            <div><dt>明确版本</dt><dd><code>{dataset.version}</code></dd></div>
            <div><dt>科研可用性</dt><dd>{readinessLabel}</dd></div>
            <div><dt>授权状态</dt><dd>{datasetLicenseStatusLabel(dataset.license_status)}</dd></div>
          </dl>
        </section>
        <aside className="dataset-detail-guidance">
          <span className="kicker">版本引用</span><h3>工作流应绑定明确版本</h3>
          <p>选择此数据集时使用 <code>{dataset.version}</code>。当前详情不会把引用静默切换到“最新版本”。</p>
          <small>文件清单、版本历史和使用记录请通过上方标签查看；若接口未返回对应数据，会在标签中说明。</small>
        </aside>
      </div>}
      {activeTab === 'files' && <DatasetDetailUnavailable icon="database" kicker="文件与样本" title="当前接口未返回文件清单" detail="项目数据接口没有提供文件列表、样本数量或文件格式，因此这里不展示推测的文件和统计值。" />}
      {activeTab === 'versions' && <DatasetDetailUnavailable icon="clock" kicker="版本历史" title="当前接口未返回版本历史" detail={`本页只读取到所选版本 ${dataset.version}；没有版本历史列表，无法据此判断是否存在其他版本。`} />}
      {activeTab === 'quality' && <ProjectQualityReport projectName={projectName} dataset={dataset} config={config} onBack={() => setActiveTab('overview')} backLabel="返回数据集概览" preview={preview} />}
      {activeTab === 'usage' && <DatasetDetailUnavailable icon="workflow" kicker="使用记录" title="当前接口未返回使用记录" detail="工作流、运行和论文复现任务对该数据版本的引用记录尚未提供。" />}
      {activeTab === 'metadata' && <section className="dataset-detail-metadata">
        <div><span className="kicker">接口已返回字段</span><h3>数据集元数据</h3><p>仅列出当前项目数据接口实际返回的信息。</p></div>
        <dl className="dataset-detail-facts dataset-detail-facts--metadata">
          <div><dt>数据集 ID</dt><dd><code>{dataset.id}</code></dd></div>
          <div><dt>版本</dt><dd><code>{dataset.version}</code></dd></div>
          <div><dt>来源</dt><dd>{datasetSourceLabel(dataset.source)}</dd></div>
          <div><dt>授权状态</dt><dd>{datasetLicenseStatusLabel(dataset.license_status)}</dd></div>
          <div><dt>科研可用性</dt><dd>{dataset.research_ready ? '是' : '否'}</dd></div>
        </dl>
      </section>}
    </section>
  </div>
}

function DatasetDetailUnavailable({ icon, kicker, title, detail }: { icon: IconName; kicker: string; title: string; detail: string }) {
  return <div className="dataset-detail-unavailable" role="status">
    <span className="dataset-detail-unavailable__icon"><Icon name={icon} size={20} /></span>
    <div><span className="kicker">{kicker}</span><h3>{title}</h3><p>{detail}</p></div>
  </div>
}

function ProjectDatasetDetailPreview({ onBack, config }: { onBack: () => void; config: ApiConfig }) {
  // This development-only fixture mirrors the fixed seed in backend/app/db/seed_demo.py.
  const dataset: DatasetResource = { id: 'bf678556-c95c-51ac-886b-a9fae260efdb', version: 'dataset-synthetic-v1', source: 'synthetic', license_status: 'not_applicable', research_ready: false }
  return <div className="project-resources-preview"><ProjectPreviewContext activeTab="resources" projectName="科研软件合成演示项目" subtitle="固定演示种子项目 · 非科研结果" /><ProjectDatasetDetail projectName="科研软件合成演示项目" dataset={dataset} config={config} onBack={onBack} preview /></div>
}

function ProjectResourcesPreview() {
  return <div className="project-resources-preview">
    <ProjectPreviewContext activeTab="resources" />
    <ProjectResources project={null} projectName={null} onOpenDatasetDetail={() => {
      // The empty layout preview contains no datasets to open.
    }} preview />
  </div>
}

function ProjectUploadFlowPreview({ projectName, onBack }: { projectName: string | null; onBack: () => void }) {
  const steps = ['选择文件或数据源', '识别格式与元数据', '上传进度', '基础校验', '质量检查', '确认创建数据版本']
  return <div className="project-upload-preview">
    <div className="project-upload-preview__toolbar"><button type="button" className="link-button" onClick={onBack}><Icon name="arrow" size={14} className="reproduction-preview__back-icon" />返回数据目录</button><span className="reproduction-preview__badge">开发态布局预览 · 无上传任务</span></div>
    <header className="project-upload-preview__heading"><div><span className="kicker">项目数据 / 数据导入</span><h1>导入数据</h1><p>先选择文件或已授权数据源，再检查元数据、质量状态并确认创建版本。</p></div></header>
    <div className="reproduction-preview__notice project-upload-preview__notice" role="status"><Icon name="server" size={17} /><span><strong>数据上传服务尚未接入</strong><small>当前没有选择文件、上传任务、校验结果或质量报告；此页只预览导入步骤和页面布局。</small></span></div>
    <ol className="project-upload-steps" aria-label="数据导入步骤">{steps.map((step, index) => <li key={step}><span>{String(index + 1).padStart(2, '0')}</span><div><strong>{step}</strong><small>未启动</small></div></li>)}</ol>
    <div className="project-upload-preview__layout">
      <section className="project-upload-card" aria-labelledby="project-upload-select">
        <div className="project-upload-card__heading"><div><span className="kicker">第 1 步</span><h2 id="project-upload-select">选择文件或数据源</h2></div><span className="project-upload-card__state">等待服务接入</span></div>
        <div className="project-upload-dropzone"><span className="project-upload-dropzone__icon"><Icon name="database" size={22} /></span><strong>选择本地文件或已授权的数据源</strong><button type="button" className="button secondary" disabled title="数据上传接口尚未接入"><Icon name="plus" size={15} />选择文件</button></div>
      </section>
      <aside className="project-upload-card project-upload-summary" aria-label="导入信息摘要">
        <span className="kicker">导入信息</span><h2>尚未创建版本</h2>
        <dl><div><dt>所属项目</dt><dd>{projectName ?? '未提供'}</dd></div><div><dt>文件或数据源</dt><dd>未选择</dd></div><div><dt>基础校验</dt><dd>未执行</dd></div><div><dt>质量检查</dt><dd>未提供</dd></div><div><dt>新建数据版本</dt><dd>未确认</dd></div></dl>
        <p className="project-upload-summary__note">只有上传完成后才能呈现校验结果；质量不通过会与上传失败分开说明。</p>
      </aside>
    </div>
    <footer className="project-upload-preview__footer"><button type="button" className="button secondary" onClick={onBack}>返回数据目录</button><button type="button" className="button primary" disabled title="数据上传服务尚未接入">继续</button></footer>
  </div>
}

function ProjectQualityReport({ projectName, dataset, config, onBack, preview = false, backLabel = '返回数据目录' }: { projectName: string | null; dataset: DatasetResource | null; config: ApiConfig; onBack: () => void; preview?: boolean; backLabel?: string }) {
  const [reportState, setReportState] = useState<State<SyntheticDatasetQualityReport>>({ status: 'idle' })
  const [checkRequest, setCheckRequest] = useState(0)
  const sections = [
    ['quality-report-summary', '检查总览'],
    ['quality-report-dimensions', '维度分析'],
    ['quality-report-findings', '检查明细'],
    ['quality-report-method', '方法与溯源'],
  ] as const
  const report = preview && reportState.status === 'ready' ? reportState.data : null
  // Summary counts issue types; each issue's count can use a different unit and stays in its detail row.
  const blockerCount = report?.issues.filter((issue) => issue.severity === 'blocker').length ?? 0
  const warningCount = report?.issues.filter((issue) => issue.severity === 'warning').length ?? 0
  const reportStatusLabel = report
    ? report.status === 'success' ? '检查完成' : report.status === 'warning' ? '存在提醒' : '存在阻断项'
    : reportState.status === 'loading' ? '检查中'
      : reportState.status === 'error' ? '检查失败'
        : preview ? '尚未检查' : '服务未接入'
  const reportStatusClass = report?.status ?? (reportState.status === 'loading' ? 'loading' : reportState.status === 'error' ? 'error' : preview ? 'empty' : 'unavailable')
  const splitOrder = ['train', 'validation', 'test']
  const splitLabels: Record<string, string> = { train: '训练集', validation: '验证集', test: '测试集' }
  // Keep this desktop visualization tied to returned split counts; it does not infer research quality.
  const splitEntries = report
    ? Object.entries(report.split_counts).sort(([left], [right]) => {
      const leftRank = splitOrder.indexOf(left)
      const rightRank = splitOrder.indexOf(right)
      if (leftRank < 0 && rightRank < 0) return left.localeCompare(right)
      if (leftRank < 0) return 1
      if (rightRank < 0) return -1
      return leftRank - rightRank
    })
    : []
  const splitTotal = splitEntries.reduce((total, [, count]) => total + count, 0)
  const splitClass = (split: string) => splitOrder.includes(split) ? split : 'other'
  const splitShare = (count: number) => splitTotal > 0 ? `${((count / splitTotal) * 100).toFixed(1)}%` : '—'
  const summaryItems = report
    ? [['检查状态', reportStatusLabel], ['记录数', report.row_count.toLocaleString('zh-CN')], ['拆分数', String(Object.keys(report.split_counts).length)], ['标签类别', String(report.label_category_count)], ['警告类型', String(warningCount)], ['阻断类型', String(blockerCount)]]
    : []
  const summaryEmptyMessage = reportState.status === 'loading'
    ? '正在等待服务端返回检查汇总。'
    : reportState.status === 'error'
      ? '本次未取得报告；请查看上方错误说明。'
      : preview
        ? '运行检查后显示服务端返回的汇总。'
        : '项目质量报告服务接入后显示该数据版本的真实指标。'
  const needsServiceToken = preview && !config.token.trim()
  const qualityReportNotice = preview
    ? needsServiceToken
      ? '当前没有服务访问令牌。连接后仅读取服务端登记的固定合成 manifest；该数据不含真实研究样本，科研就绪状态固定为否。'
      : '仅检查服务端登记的固定合成 manifest；该数据不含真实研究样本，科研就绪状态固定为否。'
    : '接入项目质量检查服务后，这里将显示对应数据版本的真实指标、明细和溯源；不以合成报告代替项目结果。'

  useEffect(() => {
    if (!preview || checkRequest === 0) return
    const controller = new AbortController()
    setReportState({ status: 'loading' })
    getSyntheticDatasetQualityReport(config, controller.signal)
      .then((data) => setReportState({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        console.error('读取合成清单质量报告失败。', error)
        setReportState({ status: 'error', message: explainQualityReportError(error) })
      })
    return () => controller.abort()
  }, [checkRequest, config.baseUrl, config.token, preview])

  const runSyntheticCheck = () => setCheckRequest((attempt) => attempt + 1)
  const issueRows = report?.issues ?? []

  return <div className="quality-report-page">
    <div className="quality-report-toolbar"><button type="button" className="link-button" onClick={onBack}><Icon name="arrow" size={14} className="quality-report-back-icon" />{backLabel}</button><span className="quality-report-state">{preview ? '合成数据联调 · 不是科研结果' : '项目质量报告'}</span></div>
    <header className="quality-report-heading"><div><span className="kicker">{preview ? '合成数据联调 / 质量检查' : '项目数据 / 质量报告'}</span><h2>{preview ? '固定合成清单' : dataset?.id ?? '数据质量报告'}</h2><p>{preview ? 'dataset-synthetic-v1 · 仅用于验证质量检查流程' : dataset ? `${dataset.version} · ${projectName ?? '当前项目'}` : '未加载项目或数据版本'}</p></div><div className="quality-report-heading__actions">{preview && <button className="button primary" type="button" onClick={runSyntheticCheck} disabled={reportState.status === 'loading' || needsServiceToken} aria-busy={reportState.status === 'loading'} aria-describedby="quality-report-service-state" title={needsServiceToken ? '请先在个人信息与设置中连接服务访问令牌' : undefined}>{reportState.status === 'loading' ? '检查中…' : report ? '重新运行检查' : '运行合成清单检查'}</button>}<button className="button secondary" type="button" disabled title="质量报告导出服务尚未接入">导出报告</button></div></header>
    <div className="quality-report-notice" id="quality-report-service-state" role="status"><Icon name={preview ? 'database' : 'server'} size={17} /><span><strong>{preview ? '合成数据联调：检查结果不代表科研结果' : '当前项目数据接口未提供质量报告'}</strong><small>{qualityReportNotice}</small></span>{needsServiceToken && <button className="link-button quality-report-notice__action" type="button" onClick={() => { window.location.hash = 'settings/service' }}>打开服务设置<Icon name="arrow" size={14} /></button>}</div>
    {preview && reportState.status === 'error' && <div className="quality-report-error" role="alert"><span>{reportState.message}</span><button className="link-button" type="button" onClick={runSyntheticCheck}>重试</button></div>}
    {preview && reportState.status === 'loading' && <div className="quality-report-loading" role="status">正在检查服务端固定合成清单…</div>}
    <div className="quality-report-layout">
      <nav className="quality-report-nav" aria-label="报告目录"><span className="kicker">报告目录</span>{sections.map(([id, label]) => <button type="button" key={id} onClick={() => document.getElementById(id)?.scrollIntoView({ block: 'start' })}>{label}</button>)}</nav>
      <div className="quality-report-content">
        <section className="quality-report-section" id="quality-report-summary">
          <div className="quality-report-section__heading"><span>01</span><div><h3>检查总览</h3><p>{report ? '以下摘要来自本次质量检查响应。' : '指标仅在服务端报告返回后显示。'}</p></div></div>
          {report ? <dl className="quality-report-summary">
            {summaryItems.map(([label, value], index) => <div key={label}>
              <dt>{label}</dt>
              <dd className={index === 0 ? `quality-report-summary__status quality-report-summary__status--${reportStatusClass}` : undefined}>{value}</dd>
            </div>)}
          </dl> : <div className="quality-report-summary-empty" role="status">
            <span className={`quality-report-summary__status quality-report-summary__status--${reportStatusClass}`}>{reportStatusLabel}</span>
            <p className="quality-report-summary-empty__message">{summaryEmptyMessage}</p>
          </div>}
        </section>
        <section className="quality-report-section" id="quality-report-dimensions">
          <div className="quality-report-section__heading"><span>02</span><div><h3>数据拆分摘要</h3><p>只展示清单中实际返回的拆分计数和标签类别数，不推断科研表现。</p></div></div>
          {report && splitEntries.length > 0 ? <>
            <div className="quality-report-split-chart" aria-hidden="true">
              {splitEntries.filter(([, count]) => count > 0 && splitTotal > 0).map(([split, count]) => <span
                key={split}
                className={`quality-report-split-chart__segment quality-report-split-chart__segment--${splitClass(split)}`}
                style={{ width: `${(count / splitTotal) * 100}%` }}
              />)}
            </div>
            <div className="quality-report-dimensions quality-report-dimensions--empty" role="list" aria-label="清单拆分计数">
              {splitEntries.map(([split, count]) => <span
                key={split}
                className={`quality-report-split-item quality-report-split-item--${splitClass(split)}`}
                role="listitem"
              >
                <i aria-hidden="true" />{splitLabels[split] ?? split}<strong>{count.toLocaleString('zh-CN')}</strong><small>{splitShare(count)}</small>
              </span>)}
            </div>
            <p className="quality-report-dimension-note">标签类别数：{report.label_category_count.toLocaleString('zh-CN')} · 比例按拆分计数合计计算；不返回具体标签值。</p>
          </> : <div className="quality-report-dimensions quality-report-dimensions--empty" role="status">
            <span>{report ? '检查已完成，但服务端未返回拆分计数。' : preview ? reportState.status === 'loading' ? '等待检查结果…' : '运行检查后显示拆分统计' : '尚无质量检查摘要'}</span>
          </div>}
        </section>
        <section className="quality-report-section" id="quality-report-findings"><div className="quality-report-section__heading"><span>03</span><div><h3>检查明细</h3><p>{preview ? '仅呈现服务端返回的问题类型、数量和处理建议；不暴露清单行内容。' : '按检查项、状态和建议展示服务端报告。'}</p></div></div><div className="quality-report-table-wrap"><table className="quality-report-table quality-report-table--live"><thead><tr><th>问题类型</th><th>级别</th><th>数量</th><th>建议</th></tr></thead><tbody>{issueRows.length > 0 ? issueRows.map((issue) => <tr key={issue.code}><td><strong>{issue.message}</strong><small>{issue.code}{issue.line_numbers.length > 0 ? ` · 清单行 ${issue.line_numbers.join(', ')}` : ''}</small></td><td><span className={issue.severity === 'blocker' ? 'quality-report-severity quality-report-severity--blocker' : 'quality-report-severity quality-report-severity--warning'}>{issue.severity === 'blocker' ? '阻断' : '警告'}</span></td><td>{issue.count.toLocaleString('zh-CN')}</td><td>{issue.guidance}</td></tr>) : <tr><td colSpan={4}>{report ? '本次检查未返回阻断项或警告项。' : preview ? '尚未运行检查；暂无质量问题明细。' : '当前没有可读取的质量检查明细。'}</td></tr>}</tbody></table></div></section>
        <section className="quality-report-section" id="quality-report-method"><div className="quality-report-section__heading"><span>04</span><div><h3>方法与溯源</h3><p>报告明确绑定数据版本、规则版本和清单校验摘要。</p></div></div><dl className="quality-report-method">{[['数据版本', report?.dataset_version ?? dataset?.version ?? (preview ? 'dataset-synthetic-v1' : '未选择')], ['规则版本', report?.rule_set_version ?? '未运行'], ['检查时间', report ? dateTime(report.checked_at) : '未运行'], ['运行来源', report ? '固定合成清单检查' : preview ? '尚未执行' : '未提供'], ['清单 SHA-256', report?.manifest_sha256 ?? '未运行']].map(([label, value]) => <div key={label}><dt>{label}</dt><dd aria-label={value === '未运行' ? '尚无报告数据' : undefined}>{value}</dd></div>)}</dl></section>
      </div>
      <aside className="quality-report-meta"><span className="kicker">{preview ? '数据范围' : '数据版本'}</span>{preview ? <dl><div><dt>数据集</dt><dd>dataset-synthetic-v1</dd></div><div><dt>来源</dt><dd>服务端合成清单</dd></div><div><dt>检查规则</dt><dd>{report?.rule_set_version ?? '运行后读取'}</dd></div><div><dt>清单摘要</dt><dd>{report ? report.manifest_sha256.slice(0, 12) : '未运行'}</dd></div></dl> : dataset ? <dl><div><dt>所属项目</dt><dd>{projectName ?? '当前项目'}</dd></div><div><dt>数据集 ID</dt><dd>{dataset.id}</dd></div><div><dt>版本</dt><dd>{dataset.version}</dd></div><div><dt>来源</dt><dd>{datasetSourceLabel(dataset.source)}</dd></div><div><dt>授权状态</dt><dd>{datasetLicenseStatusLabel(dataset.license_status)}</dd></div></dl> : <p>选择项目中的数据版本后，这里显示其来源、授权和科研可用状态。</p>}<div className="quality-report-meta__status"><span className={preview ? 'blocked-chip' : !dataset ? 'status-neutral' : dataset.research_ready ? 'ready-chip' : 'blocked-chip'}>{preview ? '合成数据 · 非科研' : dataset ? (dataset.research_ready ? '科研可用' : '不可用于科研') : '未选择版本'}</span><small>{preview ? `检查状态：${reportStatusLabel} · 科研就绪：否` : '报告状态：尚无可读取的检查结果'}</small></div></aside>
    </div>
  </div>
}

function explainQualityReportError(error: unknown): string {
  if (error instanceof QualityReportApiError) {
    if (error.status === 401 || error.status === 403) return '服务已拒绝当前凭据，请在个人信息与设置的服务配置中确认操作员权限。'
    if (error.status === 404) return '服务端未登记固定合成清单；请先完成后端迁移与合成数据初始化。'
    if (error.status >= 500) return '质量检查服务暂时不可用，请稍后重试。'
    return `质量检查请求失败（HTTP ${error.status}）。`
  }
  return '无法连接质量检查服务，请检查 API 地址和服务状态后重试。'
}

function ResearchNode({ data, selected }: NodeProps<WorkflowNode>) {
  const inputPorts = data.input_ports ?? []
  const outputPorts = data.output_ports ?? []
  const isLayoutPreview = !data.component_id
  const availability = workflowNodeAvailability(data)
  return <div className={'research-node' + (selected ? ' selected' : '')} data-category={data.category}>
    <div className="research-node__head"><span className="research-node__category">{data.category}</span>{availability && <span className={`research-node__execution-state research-node__execution-state--${availability.tone}`} aria-label={`执行能力：${availability.label}`} title={availability.message}>{availability.label}</span>}{data.run_status && <span className={`research-node__run-status research-node__run-status--${data.run_status.toLowerCase()}`}>{runStatusLabel(data.run_status)}</span>}</div>
    <strong>{data.title}</strong>
    <p>{data.description}</p>
    {isLayoutPreview && <><Handle type="target" position={Position.Left} /><Handle type="source" position={Position.Right} /></>}
    {isLayoutPreview && data.previewTopTarget && <Handle id="preview-top-target" type="target" position={Position.Top} />}
    {isLayoutPreview && data.previewBottomSource && <Handle id="preview-bottom-source" type="source" position={Position.Bottom} />}
    {inputPorts.length > 0 && <div className="research-node__ports research-node__ports--input" aria-label="输入端口">{inputPorts.map((port) => <div className="research-node__port" key={port.id} title={`${port.label} · ${port.data_type}`}><Handle id={`in:${port.id}`} type="target" position={Position.Left} /><span>{port.label}</span><small>{port.data_type}</small></div>)}</div>}
    {outputPorts.length > 0 && <div className="research-node__ports research-node__ports--output" aria-label="输出端口">{outputPorts.map((port) => <div className="research-node__port" key={port.id} title={`${port.label} · ${port.data_type}`}><span>{port.label}</span><small>{port.data_type}</small><Handle id={`out:${port.id}`} type="source" position={Position.Right} /></div>)}</div>}
    <div className="research-node__foot"><span>{data.component_version ? `v${data.component_version}` : '布局示意'}</span><span>{data.executor_binding ?? (data.component_id ? '执行器未接入' : '仅预览')}</span></div>
  </div>
}

function getWorkflowConnectionIssue(connection: {
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
}, nodes: WorkflowNode[]): string | null {
  if (!connection.sourceHandle?.startsWith('out:')) return '连线需要从节点的输出端口拖出。'
  if (!connection.targetHandle?.startsWith('in:')) return '连线需要落在节点的输入端口上。'
  if (connection.source === connection.target) return '不能将节点连接到自身。请把输出连接到另一个节点的输入端口。'
  const source = nodes.find((node) => node.id === connection.source)
  const target = nodes.find((node) => node.id === connection.target)
  if (!source || !target) return '连线端点对应的节点未加载。请重新读取工作流后再连接。'
  const sourcePort = source.data.output_ports?.find((port) => port.id === connection.sourceHandle?.slice(4))
  const targetPort = target.data.input_ports?.find((port) => port.id === connection.targetHandle?.slice(3))
  if (!sourcePort) return `节点“${source.data.title}”的输出端口契约未加载，无法确认连线类型。`
  if (!targetPort) return `节点“${target.data.title}”的输入端口契约未加载，无法确认连线类型。`
  if (sourcePort.data_type !== targetPort.data_type) {
    return `数据类型不兼容：输出“${sourcePort.label}”（${sourcePort.data_type}）不能连接到输入“${targetPort.label}”（${targetPort.data_type}）。`
  }
  return null
}

function isWorkflowConnectionCompatible(connection: {
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
}, nodes: WorkflowNode[]): boolean {
  return getWorkflowConnectionIssue(connection, nodes) === null
}

function workflowConnectionFromFinalState(state: FinalConnectionState): Connection | null {
  if (!state.fromHandle || !state.toHandle) return null
  // Users may start from either side; normalize the attempt to source -> target before explaining it.
  const startsAtOutput = state.fromHandle.type === 'source'
  const sourceHandle = startsAtOutput ? state.fromHandle : state.toHandle
  const targetHandle = startsAtOutput ? state.toHandle : state.fromHandle
  return {
    source: sourceHandle.nodeId,
    sourceHandle: sourceHandle.id ?? null,
    target: targetHandle.nodeId,
    targetHandle: targetHandle.id ?? null,
  }
}

const workflowNodeTypes = { research: ResearchNode }
const workflowNodeMime = 'application/x-ict-workflow-component'
// Fitting a small graph should keep node text at its natural size; manual zoom remains available.
const workflowFitViewOptions = { padding: 0.16, maxZoom: 1 }
const workflowDesktopFitViewOptions = { padding: 0.08, maxZoom: 1 }
const workflowCompactDesktopFitViewOptions = { padding: 0.08, maxZoom: 0.68 }

// Development-only layout reference for the run detail page; no run or node data is fabricated.
function WorkflowRunDetailPreview({ onBack }: { onBack: () => void }) {
  const [activeTab, setActiveTab] = useState<'graph' | 'config' | 'logs'>('graph')
  const [nodeDrawerOpen, setNodeDrawerOpen] = useState(false)

  return <div className="workflow-run-detail-preview">
    <div className="workflow-run-detail-preview__toolbar">
      <button type="button" className="link-button" onClick={onBack}><Icon name="arrow" size={14} className="reproduction-preview__back-icon" />返回工作流</button>
      <span className="reproduction-preview__badge">开发态布局预览 · 无运行实例</span>
    </div>
    <header className="workflow-run-detail-preview__heading">
      <div><span className="kicker">项目工作流 / 运行详情</span><h1>工作流运行详情</h1><p>运行详情归属于具体工作流；当前仅展示页面结构。</p></div>
      <div className="workflow-run-preview-actions" role="group" aria-label="运行操作布局预览"><button type="button" className="button secondary" disabled title="无运行实例；取消前将说明受影响节点">取消运行</button><button type="button" className="button secondary" disabled title="无失败节点可重试">重试失败节点</button><button type="button" className="button primary" disabled title="工作流运行服务尚未接入">重新运行工作流</button></div>
    </header>
    <div className="reproduction-preview__notice workflow-run-detail-preview__notice" role="status">
      <Icon name="server" size={17} />
      <span><strong>无运行实例</strong><small>运行服务尚未接入。节点状态、执行进度、失败原因、日志与产物均无可读取数据。</small></span>
    </div>
    <dl className="workflow-run-summary">
      <div><dt>所属工作流</dt><dd>未提供</dd></div>
      <div><dt>工作流版本</dt><dd>未提供</dd></div>
      <div><dt>运行状态</dt><dd>无运行实例</dd></div>
      <div><dt>开始时间</dt><dd>未提供</dd></div>
      <div><dt>执行时长</dt><dd>未提供</dd></div>
    </dl>
    <nav className="workflow-run-detail-tabs" aria-label="运行详情内容">
      <button type="button" className={activeTab === 'graph' ? 'active' : ''} aria-pressed={activeTab === 'graph'} onClick={() => setActiveTab('graph')}>执行图</button>
      <button type="button" className={activeTab === 'config' ? 'active' : ''} aria-pressed={activeTab === 'config'} onClick={() => setActiveTab('config')}>配置与版本</button>
      <button type="button" className={activeTab === 'logs' ? 'active' : ''} aria-pressed={activeTab === 'logs'} onClick={() => setActiveTab('logs')}>日志与产物</button>
    </nav>
    <div className={`workflow-run-detail-layout workflow-run-detail-layout--${activeTab}`}>
      <div className="workflow-run-detail-main">
        <section className="workflow-run-detail-section workflow-run-detail-section--graph" aria-labelledby="run-preview-graph">
          <div className="workflow-run-detail-section__heading"><div><span className="kicker">执行状态</span><h2 id="run-preview-graph">工作流执行图</h2></div><span className="workflow-run-detail__plain-state">无运行实例</span></div>
          <div className="workflow-run-detail-empty"><Icon name="workflow" size={21} /><strong>没有可展示的执行图</strong><p>载入真实运行记录后，在此查看执行图、节点状态、进度及失败节点的依赖影响。</p><button type="button" className="link-button workflow-run-detail-empty__action" onClick={() => setNodeDrawerOpen(true)}>预览节点详情抽屉布局<Icon name="arrow" size={14} /></button></div>
        </section>
        <section className="workflow-run-detail-section workflow-run-detail-section--events" aria-labelledby="run-preview-events">
          <div className="workflow-run-detail-section__heading"><div><span className="kicker">执行事件</span><h2 id="run-preview-events">运行日志</h2></div></div>
          <div className="workflow-run-detail-empty workflow-run-detail-empty--compact"><Icon name="file" size={17} /><span><strong>没有可读取的日志</strong></span></div>
        </section>
        <section className="workflow-run-detail-section workflow-run-detail-section--artifacts" aria-labelledby="run-preview-artifacts">
          <div className="workflow-run-detail-section__heading"><div><span className="kicker">运行输出</span><h2 id="run-preview-artifacts">产物摘要</h2></div></div>
          <div className="workflow-run-detail-empty workflow-run-detail-empty--compact"><Icon name="database" size={17} /><span><strong>无运行产物</strong><small>运行实例创建后，按节点来源列出授权可见的文件、图表、表格或模型。</small></span></div>
        </section>
      </div>
      <aside className="workflow-run-detail-rail" aria-label="运行配置与版本信息">
        <section className="workflow-run-detail-section workflow-run-detail-section--config" aria-labelledby="run-preview-config">
          <div className="workflow-run-detail-section__heading"><div><span className="kicker">执行上下文</span><h2 id="run-preview-config">运行配置</h2></div></div>
          <dl className="workflow-run-detail-fields"><div><dt>配置快照</dt><dd>未提供</dd></div><div><dt>数据版本</dt><dd>未提供</dd></div><div><dt>关键指标</dt><dd>未提供</dd></div><div><dt>执行器版本</dt><dd>未提供</dd></div></dl>
        </section>
        <section className="workflow-run-detail-section workflow-run-detail-section--metrics" aria-labelledby="run-preview-trace">
          <div className="workflow-run-detail-section__heading"><div><span className="kicker">版本溯源</span><h2 id="run-preview-trace">快照与溯源</h2></div></div>
          <p className="workflow-run-detail__supporting-copy">工作流图、参数和数据版本将在真实运行记录中固定保存，供复现与排错。复用产物会标记来源，失败时保留已完成分支的产物。</p>
          <div className="workflow-run-detail__unavailable"><Icon name="server" size={15} /><span>运行详情服务尚未接入</span></div>
        </section>
      </aside>
    </div>
    {nodeDrawerOpen && <aside className="workflow-run-node-drawer" aria-label="节点运行详情布局预览">
      <header className="workflow-run-node-drawer__header"><div><span className="kicker">节点运行详情 · 布局预览</span><h2>无节点记录</h2></div><button type="button" className="workflow-run-node-drawer__close" aria-label="关闭节点详情抽屉" onClick={() => setNodeDrawerOpen(false)}><Icon name="close" size={17} /></button></header>
      <div className="reproduction-preview__notice workflow-run-node-drawer__notice" role="status"><Icon name="server" size={16} /><span><strong>无运行实例</strong><small>以下字段用于展示详情结构，当前没有节点输入、参数或执行记录。</small></span></div>
      <section className="workflow-run-node-drawer__section"><h3>输入与参数</h3><dl><div><dt>输入数据引用</dt><dd>未提供</dd></div><div><dt>参数快照</dt><dd>未提供</dd></div><div><dt>开始 / 结束时间</dt><dd>未提供</dd></div><div><dt>执行耗时</dt><dd>未提供</dd></div></dl></section>
      <section className="workflow-run-node-drawer__section"><h3>输出产物</h3><p>没有可读取的节点产物。</p></section>
      <section className="workflow-run-node-drawer__section"><h3>错误摘要与修复方向</h3><p>当前没有节点错误；真实失败记录接入后优先显示可理解的摘要和处理建议。</p><span className="workflow-run-node-drawer__error-code">错误代码：未提供</span></section>
      <section className="workflow-run-node-drawer__section"><h3>运行日志</h3><p>没有可读取的日志摘要。</p><details><summary>查看原始日志</summary><p>无运行记录。</p></details></section>
      <footer className="workflow-run-node-drawer__actions"><button type="button" className="button secondary" disabled title="当前没有失败节点可重试">重试失败节点</button><button type="button" className="link-button" disabled title="运行图未提供">查看上游节点</button></footer>
    </aside>}
  </div>
}

function WorkflowRevisionSnapshotCard({ label, snapshot }: { label: string; snapshot: WorkflowRevisionSnapshot }) {
  const nodeTitles = snapshot.graph.nodes.slice(0, 4).map((node) =>
    typeof node.data.title === 'string' && node.data.title.trim() ? node.data.title : node.id,
  )
  const hiddenNodeCount = Math.max(0, snapshot.graph.nodes.length - nodeTitles.length)

  return <article className="workflow-revision-conflict__snapshot" aria-label={label}>
    <header><span>{label}</span><strong>修订 {snapshot.revision}</strong></header>
    <h3>{snapshot.name || '未命名工作流'}</h3>
    <p>{snapshot.description.trim() || '暂无工作流说明。'}</p>
    <dl>
      <div><dt>不可变版本</dt><dd>{snapshot.current_version > 0 ? `v${snapshot.current_version}` : '未创建'}</dd></div>
      <div><dt>图结构</dt><dd>{snapshot.graph.nodes.length} 个节点 · {snapshot.graph.edges.length} 条连线</dd></div>
    </dl>
    {nodeTitles.length > 0 ? <ul aria-label={`${label}节点摘要`}>
      {nodeTitles.map((title, index) => <li key={`${index}-${title}`}>{title}</li>)}
      {hiddenNodeCount > 0 && <li>另有 {hiddenNodeCount} 个节点</li>}
    </ul> : <p className="workflow-revision-conflict__empty">当前修订没有节点。</p>}
  </article>
}

function WorkflowRevisionConflictNotice({ local, platform, canOpenHistory, canSyncLocalDraft, syncBusy, onOpenHistory, onSyncLocalDraft }: {
  local: WorkflowRevisionSnapshot
  platform: WorkflowRevisionSnapshot
  canOpenHistory: boolean
  canSyncLocalDraft: boolean
  syncBusy: boolean
  onOpenHistory: () => void
  onSyncLocalDraft: () => void
}) {
  const revisionMessage = platform.revision > local.revision
    ? `平台已更新到修订 ${platform.revision}；本机草稿仍基于修订 ${local.revision}。`
    : platform.revision === local.revision
      ? '两侧修订号相同，但工作流内容不同；请核对后再继续。'
      : `本机草稿基于修订 ${local.revision}，平台当前为修订 ${platform.revision}。`

  return <section className="workflow-revision-conflict" role="alert" aria-labelledby="workflow-revision-conflict-title">
    <div className="workflow-revision-conflict__header">
      <div className="workflow-revision-conflict__message">
        <Icon name="shield" size={17} />
        <div><strong id="workflow-revision-conflict-title">工作流版本冲突</strong><p>{revisionMessage}</p></div>
      </div>
      <div className="workflow-revision-conflict__actions">
        <button type="button" onClick={onOpenHistory} disabled={!canOpenHistory} title={canOpenHistory ? '查看平台版本历史' : '重新连接平台后可查看'}>版本历史</button>
        <button type="button" className="workflow-revision-conflict__sync" onClick={onSyncLocalDraft} disabled={!canSyncLocalDraft || syncBusy} title={canSyncLocalDraft ? '保留平台版本后同步本机草稿' : '连接平台并确认编辑权限后可同步'}>{syncBusy ? '同步中…' : '同步本机草稿'}</button>
      </div>
    </div>
    <div className="workflow-revision-conflict__comparison">
      <WorkflowRevisionSnapshotCard label="本机草稿" snapshot={local} />
      <WorkflowRevisionSnapshotCard label="平台修订" snapshot={platform} />
    </div>
  </section>
}

function WorkflowEditor({ owner, config, workflowId, preview = false, backLabel = '项目', onDiscussWorkflow, onBack }: { owner: WorkflowOwnerContext; config?: ApiConfig; workflowId?: string; preview?: boolean; backLabel?: string; onDiscussWorkflow?: (project: AgentProjectContext, workflow: AgentWorkflowContext) => void; onBack: () => void }) {
  const [editorMode, setEditorMode] = useState<'guided' | 'canvas'>('canvas')
  const [tab, setTab] = useState<WorkflowDockTab>('校验')
  const [dockExpanded, setDockExpanded] = useState(false)
  const [search, setSearch] = useState('')
  const [componentScope, setComponentScope] = useState<'all' | 'recent' | 'favorites'>('all')
  const [componentCategory, setComponentCategory] = useState('全部类别')
  const [favoriteComponentIds, setFavoriteComponentIds] = useState<string[]>(() => readLocalWorkflowComponentIds(localWorkflowComponentFavoritesKey, '工作流组件收藏'))
  const [recentComponentIds, setRecentComponentIds] = useState<string[]>(() => readLocalWorkflowComponentIds(localRecentWorkflowComponentIdsKey, '最近使用的工作流组件'))
  const [componentDetail, setComponentDetail] = useState<WorkflowComponentEntry | null>(null)
  const componentDetailTriggerRef = useRef<HTMLButtonElement | null>(null)
  const componentDetailCloseRef = useRef<HTMLButtonElement | null>(null)
  const componentDetailCanvasRef = useRef<HTMLElement | null>(null)
  const componentDetailFocusTarget = useRef<'trigger' | 'canvas' | null>(null)
  useEffect(() => {
    try {
      window.localStorage.setItem(localWorkflowComponentFavoritesKey, JSON.stringify(favoriteComponentIds))
    } catch (error) {
      console.error('保存本机工作流组件收藏失败。', error)
    }
  }, [favoriteComponentIds])
  useEffect(() => {
    // Static editor previews must not become a user's persistent component history.
    if (preview) return
    try {
      window.localStorage.setItem(localRecentWorkflowComponentIdsKey, JSON.stringify(recentComponentIds))
    } catch (error) {
      console.error('保存本机最近使用的工作流组件失败。', error)
    }
  }, [preview, recentComponentIds])
  useEffect(() => {
    if (componentDetail) {
      componentDetailCloseRef.current?.focus()
      return
    }
    // Closing returns to the opener; adding continues in the canvas, including mobile views.
    if (componentDetailFocusTarget.current === 'trigger') componentDetailTriggerRef.current?.focus()
    if (componentDetailFocusTarget.current === 'canvas') componentDetailCanvasRef.current?.focus()
    componentDetailFocusTarget.current = null
  }, [componentDetail])
  const closeComponentDetail = (focusTarget: 'trigger' | 'canvas' = 'trigger') => {
    componentDetailFocusTarget.current = focusTarget
    setComponentDetail(null)
  }
  // Keep each rail independently collapsible so the canvas can reclaim its space.
  const [libraryOpen, setLibraryOpen] = useState(true)
  // Medium desktop layouts prioritize the graph; users can still pin the inspector open.
  const [mediumEditorViewport, setMediumEditorViewport] = useState(() => typeof window !== 'undefined' && window.matchMedia('(min-width: 761px) and (max-width: 1150px)').matches)
  const [inspectorOverride, setInspectorOverride] = useState<boolean | null>(null)
  const inspectorOpen = inspectorOverride ?? !mediumEditorViewport
  useEffect(() => {
    const mediumViewport = window.matchMedia('(min-width: 761px) and (max-width: 1150px)')
    const syncViewport = () => setMediumEditorViewport(mediumViewport.matches)
    syncViewport()
    mediumViewport.addEventListener('change', syncViewport)
    return () => mediumViewport.removeEventListener('change', syncViewport)
  }, [])
  const toggleInspector = () => setInspectorOverride((current) => !(current ?? !mediumEditorViewport))
  // Keep the map available for larger graphs without covering nodes in the initial view.
  const [miniMapOpen, setMiniMapOpen] = useState(false)
  // Narrow screens switch between the component catalog, canvas, and inspector as full views.
  const [mobileEditorView, setMobileEditorView] = useState<'components' | 'canvas' | 'inspection'>('canvas')
  const [nodes, setNodes, onNodesChange] = useNodesState<WorkflowNode>(preview ? workflowEditorPreviewNodes : [])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(preview ? workflowEditorPreviewEdges : [])
  const [selectedId, setSelectedId] = useState<string | null>(preview ? 'preview-inference' : null)
  const [pendingNodeRevealId, setPendingNodeRevealId] = useState<string | null>(null)
  // Show contract feedback after the user leaves a parameter, then update it as they type.
  const [touchedParameterFields, setTouchedParameterFields] = useState<Set<string>>(() => new Set())
  const guidedLayers = useMemo(() => getWorkflowGuidedLayers(nodes, edges), [nodes, edges])
  const [validationFocus, setValidationFocus] = useState<WorkflowCanvasFocus>(null)
  const validationFocusRequestRef = useRef(0)
  const [workflowState, setWorkflowState] = useState<State<WorkflowDetail>>(workflowId && !preview ? { status: 'loading' } : { status: 'idle' })
  const [revisionConflict, setRevisionConflict] = useState<WorkflowRevisionConflict | null>(null)
  const [catalogState, setCatalogState] = useState<State<WorkflowComponent[]>>({ status: 'idle' })
  const [localRuntimeState, setLocalRuntimeState] = useState<State<LocalRuntimeHealth>>(preview ? { status: 'idle' } : { status: 'loading' })
  const [localCatalogState, setLocalCatalogState] = useState<State<WorkflowComponent[]>>({ status: 'idle' })
  const [runHistory, setRunHistory] = useState<LocalWorkflowRunSummary[]>([])
  const [runDetail, setRunDetail] = useState<LocalWorkflowRunDetail | null>(null)
  const [csvReportState, setCsvReportState] = useState<State<LocalCsvPreflightReport>>({ status: 'idle' })
  const [csvDescriptiveSummaryState, setCsvDescriptiveSummaryState] = useState<State<LocalCsvDescriptiveSummaryReport>>({ status: 'idle' })
  const [csvFolderQualityState, setCsvFolderQualityState] = useState<State<LocalCsvFolderQualityReport>>({ status: 'idle' })
  const [crossrefReportState, setCrossrefReportState] = useState<State<LocalCrossrefMetadataReport>>({ status: 'idle' })
  const csvReportHandle = useMemo(() => {
    const reportNode = runDetail?.node_runs.find((item) => isCsvPreflightComponent(item.component_id))
    return reportNode
      ? collectArtifactHandles(reportNode.output).find((artifact) => artifact.media_type === 'application/json') ?? null
      : null
  }, [runDetail])
  const csvDescriptiveSummaryHandle = useMemo(() => {
    const reportNode = runDetail?.node_runs.find((item) => isCsvDescriptiveSummaryComponent(item.component_id))
    return reportNode
      ? collectArtifactHandles(reportNode.output).find((artifact) => artifact.media_type === 'application/json') ?? null
      : null
  }, [runDetail])
  const csvFolderQualityHandle = useMemo(() => {
    const reportNode = runDetail?.node_runs.find((item) => isCsvFolderQualityComponent(item.component_id))
    return reportNode
      ? collectArtifactHandles(reportNode.output).find((artifact) => artifact.file_name === 'csv-folder-quality-report.json') ?? null
      : null
  }, [runDetail])
  const crossrefReportHandle = useMemo(() => {
    const reportNode = runDetail?.node_runs.find((item) => item.component_id === 'ict.paper.crossref_metadata')
    return reportNode
      ? collectArtifactHandles(reportNode.output).find((artifact) => artifact.media_type === 'application/json') ?? null
      : null
  }, [runDetail])
  const [runBusy, setRunBusy] = useState(false)
  const [runCancelBusy, setRunCancelBusy] = useState(false)
  const [runRecoveryBusy, setRunRecoveryBusy] = useState(false)
  const [runRecoveryNotice, setRunRecoveryNotice] = useState<string | null>(null)
  const [runRecoveryError, setRunRecoveryError] = useState<string | null>(null)
  const [selectedRunTargets, setSelectedRunTargets] = useState<string[]>([])
  const [runTargetsTouched, setRunTargetsTouched] = useState(false)
  const [artifactImportBusy, setArtifactImportBusy] = useState(false)
  const [folderImportProgress, setFolderImportProgress] = useState<{ completed: number; total: number } | null>(null)
  const [importedArtifact, setImportedArtifact] = useState<LocalArtifactHandle | null>(null)
  const csvFileInputRef = useRef<HTMLInputElement>(null)
  const csvFolderInputRef = useRef<HTMLInputElement>(null)
  const [workflowName, setWorkflowName] = useState(preview ? '工作流布局示例' : '')
  const [workflowDescription, setWorkflowDescription] = useState('')
  const [saveBusy, setSaveBusy] = useState(false)
  const [validationBusy, setValidationBusy] = useState(false)
  const [versionBusy, setVersionBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionNotice, setActionNotice] = useState<string | null>(null)
  const [validation, setValidation] = useState<WorkflowValidation | null>(null)
  const [currentVersion, setCurrentVersion] = useState(0)
  const [versionHistoryOpen, setVersionHistoryOpen] = useState(false)
  const [versionHistoryState, setVersionHistoryState] = useState<State<WorkflowVersionSummary[]>>({ status: 'idle' })
  const [selectedVersionNumber, setSelectedVersionNumber] = useState<number | null>(null)
  const [selectedVersionState, setSelectedVersionState] = useState<State<WorkflowVersionDetail>>({ status: 'idle' })
  const [versionHistoryBusy, setVersionHistoryBusy] = useState(false)
  const [restoreBusy, setRestoreBusy] = useState(false)
  const registeredComponents = useMemo(() => {
    const merged = new Map<string, WorkflowComponent>()
    if (catalogState.status === 'ready') for (const item of catalogState.data) merged.set(item.component_id, item)
    if (localCatalogState.status === 'ready') for (const item of localCatalogState.data) {
      const current = merged.get(item.component_id)
      merged.set(item.component_id, current?.execution_available ? current : item)
    }
    return [...merged.values()]
  }, [catalogState, localCatalogState])
  const currentGraph = serializeWorkflowGraph(nodes, edges)
  const currentSnapshot = workflowDraftSnapshot(workflowName, workflowDescription, currentGraph, registeredComponents)
  const savedSnapshot = workflowState.status === 'ready'
    ? workflowDraftSnapshot(workflowState.data.name, workflowState.data.description, workflowState.data.graph, registeredComponents)
    : ''
  const isDirty = workflowState.status === 'ready' && currentSnapshot !== savedSnapshot
  const canEditGraph = preview || (workflowState.status === 'ready' && workflowState.data.can_edit)
  const isLocalWorkflow = Boolean(workflowId?.startsWith('local-workflow-') || workflowId?.startsWith('local-reproduction-workflow-'))
  const canPersist = Boolean(!preview && workflowId && canEditGraph && workflowState.status === 'ready' && (isLocalWorkflow || config?.token.trim()))
  const canReadWorkflow = Boolean(!preview && workflowId && workflowState.status === 'ready' && (isLocalWorkflow || config?.token.trim()))
  const canValidateWorkflow = Boolean(!preview && workflowId && canEditGraph && workflowState.status === 'ready' &&
    (localRuntimeState.status === 'ready' || (config?.token.trim() && workflowState.localUnsynced !== true)))
  const workflowUndoHistoryRef = useRef<WorkflowEditorSnapshot[]>([])
  const workflowRedoHistoryRef = useRef<WorkflowEditorSnapshot[]>([])
  // Keep copied graph fragments in memory and scoped to this owner/workflow only.
  const workflowClipboardRef = useRef<{ scope: string; nodes: WorkflowNode[]; edges: Edge[]; pasteCount: number } | null>(null)
  const workflowEditorScope = `${preview ? 'preview' : 'workflow'}:${owner.type}:${owner.id}:${workflowId ?? ''}`
  const workflowTextEditRef = useRef<{ key: string; initialValue: string; snapshot: WorkflowEditorSnapshot } | null>(null)
  const [workflowHistoryRevision, setWorkflowHistoryRevision] = useState(0)
  const canUndo = useMemo(() => workflowUndoHistoryRef.current.length > 0, [workflowHistoryRevision])
  const canRedo = useMemo(() => workflowRedoHistoryRef.current.length > 0, [workflowHistoryRevision])

  const captureWorkflowEditorSnapshot = useCallback(() => cloneWorkflowEditorSnapshot({
    name: workflowName,
    description: workflowDescription,
    nodes,
    edges,
  }), [edges, nodes, workflowDescription, workflowName])

  const clearWorkflowHistory = useCallback(() => {
    workflowUndoHistoryRef.current = []
    workflowRedoHistoryRef.current = []
    workflowTextEditRef.current = null
    setWorkflowHistoryRevision((revision) => revision + 1)
  }, [])

  const pushWorkflowUndoSnapshot = useCallback((snapshot: WorkflowEditorSnapshot) => {
    workflowUndoHistoryRef.current.push(cloneWorkflowEditorSnapshot(snapshot))
    if (workflowUndoHistoryRef.current.length > 50) workflowUndoHistoryRef.current.shift()
    workflowRedoHistoryRef.current = []
    setWorkflowHistoryRevision((revision) => revision + 1)
  }, [])

  const recordWorkflowUndoPoint = useCallback(() => {
    pushWorkflowUndoSnapshot(captureWorkflowEditorSnapshot())
  }, [captureWorkflowEditorSnapshot, pushWorkflowUndoSnapshot])

  const beginWorkflowTextEdit = useCallback((key: string, initialValue: string) => {
    if (!canEditGraph) return
    workflowTextEditRef.current = { key, initialValue, snapshot: captureWorkflowEditorSnapshot() }
  }, [canEditGraph, captureWorkflowEditorSnapshot])

  const finishWorkflowTextEdit = useCallback((key: string, finalValue: string) => {
    const pending = workflowTextEditRef.current
    if (!pending || pending.key !== key) return
    workflowTextEditRef.current = null
    if (pending.initialValue !== finalValue) pushWorkflowUndoSnapshot(pending.snapshot)
  }, [pushWorkflowUndoSnapshot])

  const applyWorkflowEditorSnapshot = useCallback((snapshot: WorkflowEditorSnapshot) => {
    const restored = cloneWorkflowEditorSnapshot(snapshot)
    workflowTextEditRef.current = null
    setWorkflowName(restored.name)
    setWorkflowDescription(restored.description)
    setNodes(restored.nodes)
    setEdges(restored.edges)
    setSelectedId(null)
    setValidation(null)
    setValidationFocus(null)
    setActionError(null)
    setActionNotice(null)
  }, [setEdges, setNodes])

  const undoWorkflowEdit = useCallback(() => {
    if (!canEditGraph || saveBusy || restoreBusy) return
    const previous = workflowUndoHistoryRef.current.pop()
    if (!previous) return
    workflowRedoHistoryRef.current.push(captureWorkflowEditorSnapshot())
    setWorkflowHistoryRevision((revision) => revision + 1)
    applyWorkflowEditorSnapshot(previous)
  }, [applyWorkflowEditorSnapshot, canEditGraph, captureWorkflowEditorSnapshot, restoreBusy, saveBusy])

  const redoWorkflowEdit = useCallback(() => {
    if (!canEditGraph || saveBusy || restoreBusy) return
    const next = workflowRedoHistoryRef.current.pop()
    if (!next) return
    workflowUndoHistoryRef.current.push(captureWorkflowEditorSnapshot())
    if (workflowUndoHistoryRef.current.length > 50) workflowUndoHistoryRef.current.shift()
    setWorkflowHistoryRevision((revision) => revision + 1)
    applyWorkflowEditorSnapshot(next)
  }, [applyWorkflowEditorSnapshot, canEditGraph, captureWorkflowEditorSnapshot, restoreBusy, saveBusy])

  const copyWorkflowSelection = useCallback(() => {
    const selectedNodes = nodes.filter((node) => node.selected)
    if (!canEditGraph || selectedNodes.length === 0) return false
    const selectedIds = new Set(selectedNodes.map((node) => node.id))
    const fragment = cloneWorkflowEditorSnapshot({
      name: workflowName,
      description: workflowDescription,
      nodes: selectedNodes,
      edges: edges.filter((edge) => selectedIds.has(edge.source) && selectedIds.has(edge.target)),
    })
    workflowClipboardRef.current = { scope: workflowEditorScope, nodes: fragment.nodes, edges: fragment.edges, pasteCount: 0 }
    setActionNotice(`已复制 ${selectedNodes.length} 个节点及 ${fragment.edges.length} 条内部连线；可在当前画布粘贴。`)
    return true
  }, [canEditGraph, edges, nodes, workflowDescription, workflowEditorScope, workflowName])

  const pasteWorkflowSelection = useCallback(() => {
    const clipboard = workflowClipboardRef.current
    if (!canEditGraph || saveBusy || restoreBusy || !clipboard || clipboard.scope !== workflowEditorScope || clipboard.nodes.length === 0) return false
    const fragment = cloneWorkflowEditorSnapshot({ name: '', description: '', nodes: clipboard.nodes, edges: clipboard.edges })
    clipboard.pasteCount += 1
    const offset = clipboard.pasteCount * 48
    const idMap = new Map(fragment.nodes.map((node) => [
      node.id,
      preview ? `local-node-${++nodeSerial.current}` : `node-${crypto.randomUUID()}`,
    ]))
    const pastedNodes = fragment.nodes.map((node) => ({
      ...node,
      id: idMap.get(node.id)!,
      position: { x: node.position.x + offset, y: node.position.y + offset },
      selected: true,
    }))
    const pastedEdges = fragment.edges.map((edge) => ({
      ...edge,
      id: `edge-${crypto.randomUUID()}`,
      source: idMap.get(edge.source)!,
      target: idMap.get(edge.target)!,
      selected: false,
    }))

    recordWorkflowUndoPoint()
    setNodes((current) => [...current.map((node) => ({ ...node, selected: false })), ...pastedNodes])
    setEdges((current) => [...current.map((edge) => ({ ...edge, selected: false })), ...pastedEdges])
    setSelectedId(pastedNodes[0].id)
    setActionNotice(`已粘贴 ${pastedNodes.length} 个节点及 ${pastedEdges.length} 条内部连线；保存草稿后写入工作流。`)
    return true
  }, [canEditGraph, recordWorkflowUndoPoint, restoreBusy, saveBusy, setEdges, setNodes, workflowEditorScope, preview])

  useEffect(() => {
    const handleEditorShortcut = (event: KeyboardEvent) => {
      if ((!event.ctrlKey && !event.metaKey) || event.altKey || versionHistoryOpen) return
      if (event.target instanceof HTMLElement && (
        event.target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)
      )) return
      const key = event.key.toLowerCase()
      const targetIsCanvas = event.target instanceof Element && Boolean(event.target.closest('.react-flow'))
      if ((key === 'c' || key === 'v') && targetIsCanvas && window.matchMedia('(min-width: 761px)').matches) {
        const handled = key === 'c' ? copyWorkflowSelection() : pasteWorkflowSelection()
        if (handled) event.preventDefault()
      } else if (key === 'z' && event.shiftKey && canRedo) {
        event.preventDefault()
        redoWorkflowEdit()
      } else if (key === 'z' && !event.shiftKey && canUndo) {
        event.preventDefault()
        undoWorkflowEdit()
      } else if (key === 'y' && !event.shiftKey && canRedo) {
        event.preventDefault()
        redoWorkflowEdit()
      }
    }
    window.addEventListener('keydown', handleEditorShortcut)
    return () => window.removeEventListener('keydown', handleEditorShortcut)
  }, [canRedo, canUndo, copyWorkflowSelection, pasteWorkflowSelection, redoWorkflowEdit, undoWorkflowEdit, versionHistoryOpen])

  useEffect(() => {
    clearWorkflowHistory()
    workflowClipboardRef.current = null
    if (preview || !workflowId) return
    const controller = new AbortController()
    setWorkflowState({ status: 'loading' })
    const applyWorkflow = (workflow: WorkflowDetail, cached: boolean, localUnsynced = false) => {
      if (workflow.owner_type !== owner.type || workflow.owner_id !== owner.id) {
        setWorkflowState({ status: 'error', message: '此工作流不属于当前项目或复现任务。请返回所属对象后重新打开。' })
        return
      }
      if (!cached) writeLocalCache(`${localWorkflowDetailCachePrefix}${encodeURIComponent(workflowId)}`, workflow, '工作流')
      setWorkflowState({ status: 'ready', data: workflow, ...(cached ? { cached: true } : {}), ...(localUnsynced ? { localUnsynced: true } : {}) })
      setWorkflowName(workflow.name)
      setWorkflowDescription(workflow.description)
      setCurrentVersion(workflow.current_version)
      const restoredNodes = restoreWorkflowNodes(workflow.graph)
      const restoredEdges = workflow.graph.edges.map((edge) => ({ ...edge, type: edge.type ?? 'smoothstep' })) as Edge[]
      setNodes(restoredNodes)
      setEdges(restoredEdges)
      setValidation(null)
      setValidationFocus(null)
      setActionError(null)
    }
    const loadCachedWorkflow = async (reason: unknown) => {
      let workflow = cachedWorkflowDetail(workflowId)
      if (workflow && workflow.owner_type === owner.type && workflow.owner_id === owner.id) {
        try {
          const localDraft = await getLocalWorkflowDraft(workflowId)
          if (!controller.signal.aborted) workflow = { ...workflow, graph: localDraft.graph }
        } catch (localError) {
          if (!(localError instanceof LocalRuntimeApiError && localError.status === 404)) {
            console.warn('本机工作流副本读取失败，继续使用浏览器缓存。', localError)
          }
        }
      }
      if (controller.signal.aborted) return
      if (workflow) {
        applyWorkflow(workflow, true, workflowPendingPlatformSync(workflowId))
        return
      }
      setWorkflowState({ status: 'error', message: explainWorkflowError(reason) })
    }
    if (isLocalWorkflow) {
      getLocalWorkflow(workflowId)
        .then((workflow) => { if (!controller.signal.aborted) applyWorkflow(workflow, false) })
        .catch((error) => { if (!controller.signal.aborted) void loadCachedWorkflow(error) })
      return () => controller.abort()
    }
    if (!config?.token.trim()) {
      void loadCachedWorkflow(new TypeError('Platform workflow service is not connected'))
      return () => controller.abort()
    }
    getWorkflow(config, workflowId, controller.signal)
      .then(async (workflow) => {
        if (controller.signal.aborted) return
        const cached = cachedWorkflowDetail(workflowId)
        const cachedBelongsToOwner = cached && cached.owner_type === owner.type && cached.owner_id === owner.id
        const localChangesPending = workflowPendingPlatformSync(workflowId)
        const cachedContentDiffers = cachedBelongsToOwner && (
          cached.name !== workflow.name || cached.description !== workflow.description ||
          JSON.stringify(cached.graph) !== JSON.stringify(workflow.graph)
        )
        if (cachedBelongsToOwner && localChangesPending && cachedContentDiffers) {
          const localSnapshot: WorkflowRevisionSnapshot = {
            revision: cached.revision,
            current_version: cached.current_version,
            name: cached.name,
            description: cached.description,
            graph: cached.graph,
          }
          const platformSnapshot: WorkflowRevisionSnapshot = {
            revision: workflow.revision,
            current_version: workflow.current_version,
            name: workflow.name,
            description: workflow.description,
            graph: workflow.graph,
          }
          // Keep the local optimistic revision so a sync cannot silently overwrite a newer platform draft.
          applyWorkflow({
            ...workflow,
            revision: cached.revision,
            name: cached.name,
            description: cached.description,
            graph: cached.graph,
          }, true, true)
          setRevisionConflict({ workflowId, local: localSnapshot, platform: platformSnapshot })
          return
        }
        if (cachedBelongsToOwner && localChangesPending && !cachedContentDiffers) setWorkflowPendingPlatformSync(workflowId, false)
        setRevisionConflict(null)
        applyWorkflow(workflow, false)
      })
      .catch((error) => {
        if (!controller.signal.aborted) void loadCachedWorkflow(error)
      })
    return () => controller.abort()
  }, [clearWorkflowHistory, config?.baseUrl, config?.token, workflowId, owner.id, owner.type, preview, setNodes, setEdges])

  useEffect(() => {
    if (preview) {
      setLocalRuntimeState({ status: 'idle' })
      setLocalCatalogState({ status: 'idle' })
      return
    }
    let active = true
    setLocalRuntimeState({ status: 'loading' })
    setLocalCatalogState({ status: 'loading' })
    getLocalRuntimeHealth()
      .then((health) => {
        if (active) setLocalRuntimeState({ status: 'ready', data: health })
        return listLocalWorkflowComponents().then((components) => {
          if (active) setLocalCatalogState({ status: 'ready', data: components })
        }).catch((error) => {
          if (!active) return
          console.warn('读取本机工作流组件目录失败。', error)
          setLocalCatalogState({ status: 'error', message: error instanceof LocalRuntimeApiError ? error.code : '本机组件目录不可用' })
        })
      })
      .catch((error) => {
        if (!active) return
        console.warn('本机工作流运行时不可用。', error)
        setLocalRuntimeState({ status: 'error', message: error instanceof LocalRuntimeApiError ? error.code : '本机运行时未启动' })
        setLocalCatalogState({ status: 'error', message: '本机运行时未启动' })
      })
    return () => { active = false }
  }, [preview])

  useEffect(() => {
    if (preview || !config?.token.trim()) {
      setCatalogState({ status: 'idle' })
      return
    }
    const controller = new AbortController()
    setCatalogState({ status: 'loading' })
    listWorkflowComponents(config, controller.signal)
      .then((components) => {
        if (!controller.signal.aborted) setCatalogState({ status: 'ready', data: components })
      })
      .catch((error) => {
        if (!controller.signal.aborted) setCatalogState({ status: 'error', message: explainWorkflowError(error) })
      })
    return () => controller.abort()
  }, [config?.baseUrl, config?.token, preview])

  useEffect(() => {
    if (workflowState.status !== 'ready' || registeredComponents.length === 0) return
    setNodes((current) => hydrateWorkflowNodes(current, registeredComponents))
  }, [registeredComponents, workflowState.status, setNodes])

  useEffect(() => {
    if (preview || !workflowId || localRuntimeState.status !== 'ready') {
      setRunHistory([])
      setRunDetail(null)
      setRunBusy(false)
      return
    }
    let active = true
    listLocalWorkflowRuns(workflowId)
      .then(async (runs) => {
        if (!active) return
        setRunHistory(runs)
        if (runs.length > 0) {
          const detail = await getLocalWorkflowRun(runs[0].run_id)
          if (active) {
            setRunDetail(detail)
            setRunBusy(['queued', 'running', 'waiting_external'].includes(detail.status))
          }
        }
      })
      .catch((error) => {
        if (active) console.error('读取本机工作流运行历史失败。', error)
      })
    return () => { active = false }
  }, [preview, workflowId, localRuntimeState.status])

  useEffect(() => {
    if (!runDetail || !['queued', 'running', 'waiting_external'].includes(runDetail.status)) return
    let active = true
    let timer = 0
    const poll = async () => {
      try {
        const latest = await getLocalWorkflowRun(runDetail.run_id)
        if (!active) return
        setRunDetail(latest)
        setRunHistory((current) => [latest, ...current.filter((item) => item.run_id !== latest.run_id)])
        setRunBusy(['queued', 'running', 'waiting_external'].includes(latest.status))
        if (['queued', 'running', 'waiting_external'].includes(latest.status)) timer = window.setTimeout(poll, 700)
      } catch (error) {
        if (!active) return
        console.error('读取本机工作流运行状态失败。', error)
        setRunBusy(false)
        setActionError('本机运行已提交，但读取运行状态失败。请检查本机运行时日志。')
      }
    }
    timer = window.setTimeout(poll, 350)
    return () => { active = false; window.clearTimeout(timer) }
  }, [runDetail?.run_id, runDetail?.status])

  useEffect(() => {
    if (tab !== '产物' || !csvReportHandle) {
      setCsvReportState({ status: 'idle' })
      return
    }
    let active = true
    setCsvReportState({ status: 'loading' })
    getLocalCsvPreflightReport(csvReportHandle.artifact_id)
      .then((report) => {
        if (active) setCsvReportState({ status: 'ready', data: report })
      })
      .catch((error) => {
        console.error('读取本机 CSV 结构预检报告失败。', error)
        if (active) setCsvReportState({
          status: 'error',
          message: error instanceof LocalRuntimeApiError ? `无法读取报告（${error.code}）。` : '本机结构预检报告无法读取。',
          ...(error instanceof LocalRuntimeApiError ? { code: error.code } : {}),
        })
      })
    return () => { active = false }
  }, [tab, csvReportHandle?.artifact_id])

  useEffect(() => {
    if (tab !== '产物' || !csvDescriptiveSummaryHandle) {
      setCsvDescriptiveSummaryState({ status: 'idle' })
      return
    }
    let active = true
    setCsvDescriptiveSummaryState({ status: 'loading' })
    getLocalCsvDescriptiveSummaryReport(csvDescriptiveSummaryHandle.artifact_id)
      .then((report) => {
        if (active) setCsvDescriptiveSummaryState({ status: 'ready', data: report })
      })
      .catch((error) => {
        console.error('读取本机 CSV 描述统计报告失败。', error)
        if (active) setCsvDescriptiveSummaryState({
          status: 'error',
          message: error instanceof LocalRuntimeApiError ? `无法读取报告（${error.code}）。` : '本机描述统计报告无法读取。',
          ...(error instanceof LocalRuntimeApiError ? { code: error.code } : {}),
        })
      })
    return () => { active = false }
  }, [tab, csvDescriptiveSummaryHandle?.artifact_id])

  useEffect(() => {
    if (tab !== '产物' || !csvFolderQualityHandle) {
      setCsvFolderQualityState({ status: 'idle' })
      return
    }
    let active = true
    setCsvFolderQualityState({ status: 'loading' })
    getLocalCsvFolderQualityReport(csvFolderQualityHandle.artifact_id)
      .then((report) => {
        if (active) setCsvFolderQualityState({ status: 'ready', data: report })
      })
      .catch((error) => {
        console.error('读取本机 CSV 文件夹质量报告失败。', error)
        if (active) setCsvFolderQualityState({
          status: 'error',
          message: error instanceof LocalRuntimeApiError ? `无法读取文件夹质量报告（${error.code}）。` : '本机 CSV 文件夹质量报告无法读取。',
          ...(error instanceof LocalRuntimeApiError ? { code: error.code } : {}),
        })
      })
    return () => { active = false }
  }, [tab, csvFolderQualityHandle?.artifact_id])

  useEffect(() => {
    if (tab !== '产物' || !crossrefReportHandle) {
      setCrossrefReportState({ status: 'idle' })
      return
    }
    let active = true
    setCrossrefReportState({ status: 'loading' })
    getLocalCrossrefMetadataReport(crossrefReportHandle.artifact_id)
      .then((report) => {
        if (active) setCrossrefReportState({ status: 'ready', data: report })
      })
      .catch((error) => {
        console.error('读取本机 Crossref 元数据失败。', error)
        if (active) setCrossrefReportState({
          status: 'error',
          message: error instanceof LocalRuntimeApiError ? `无法读取元数据（${error.code}）。` : '本机文献元数据无法读取。',
          ...(error instanceof LocalRuntimeApiError ? { code: error.code } : {}),
        })
      })
    return () => { active = false }
  }, [tab, crossrefReportHandle?.artifact_id])

  useEffect(() => {
    if (!runDetail) return
    const statusByNode = new Map(runDetail.node_runs.map((item) => [item.node_id, item.status]))
    setNodes((current) => current.map((node) => ({
      ...node,
      data: { ...node.data, run_status: statusByNode.get(node.id) ?? null },
    })))
  }, [runDetail?.run_id, runDetail?.node_runs, setNodes])

  const nodeSerial = useRef(0)
  const selectedNode = nodes.find((node) => node.id === selectedId)
  const selectedNodeRun = selectedNode ? runDetail?.node_runs.find((item) => item.node_id === selectedNode.id) : undefined
  const selectedParameterEntries = selectedNode?.data.parameter_schema
    ? Object.entries(selectedNode.data.parameter_schema.properties)
    : []
  // Reflect the current graph's inbound edges in the selected node inspector.
  const selectedUpstreamConnections = selectedNode
    ? edges.filter((edge) => edge.target === selectedNode.id)
    : []
  // Merge server schemas with the independently installed local catalog; local availability wins for execution.
  const availableComponents: WorkflowComponentEntry[] = preview
    ? workflowComponents
    : registeredComponents.length > 0
      ? registeredComponents.map((definition) => ({
        id: definition.component_id,
        category: definition.category,
        title: definition.title,
        description: definition.description,
        icon: workflowComponentIcon(definition.category),
        definition,
      }))
      : []
  const componentCategories = [...new Set(availableComponents.map((item) => item.category))]
  const defaultRunTargets = useMemo(() => workflowSinkNodeIds(nodes, edges), [nodes, edges])
  const activeRunTargets = runTargetsTouched
    ? selectedRunTargets.filter((id) => nodes.some((node) => node.id === id))
    : defaultRunTargets
  const runClosureIds = workflowTargetClosureIds(edges, activeRunTargets)
  const executableNodeIds = new Set(registeredComponents
    .filter((component) => (component.execution_target === 'local' || component.execution_target === 'network') && component.execution_available)
    .map((component) => component.component_id))
  const runClosureHasExecutor = nodes.some((node) => runClosureIds.has(node.id) &&
    node.data.component_id && executableNodeIds.has(node.data.component_id))
  // Count only selected output dependencies; unrelated branches must not create a warning.
  const localUnavailableNodeCount = localCatalogState.status === 'ready'
    ? nodes.filter((node) => runClosureIds.has(node.id) &&
      !executableNodeIds.has(typeof node.data.component_id === 'string' ? node.data.component_id : '')).length
    : 0
  const runClosureNetworkNodes = nodes.filter((node) => runClosureIds.has(node.id) &&
    node.data.component_id === 'ict.paper.crossref_metadata')
  const missingCsvArtifactNodeIds = nodes.filter((node) => runClosureIds.has(node.id) &&
    node.data.component_id === 'ict.data.csv_manifest_preflight' &&
    !String(node.data.parameters?.artifact_id ?? '').trim()).map((node) => node.id)
  const canLocalSave = localRuntimeState.status === 'ready' && Boolean(workflowId) &&
    workflowState.status === 'ready' && canEditGraph
  const canSaveDraft = canPersist || canLocalSave
  const canRunLocal = !preview && Boolean(workflowId) && workflowState.status === 'ready' &&
    canEditGraph && localRuntimeState.status === 'ready' && localCatalogState.status === 'ready' &&
    activeRunTargets.length > 0 && runClosureHasExecutor && missingCsvArtifactNodeIds.length === 0 && !runBusy
  const runBlocker = preview ? '布局预览不会创建本机运行。'
    : localRuntimeState.status !== 'ready' ? '本机运行时未启动；启动本机运行时后可离线运行已安装组件。'
      : workflowState.status !== 'ready' ? '工作流尚未读取，无法提交运行。'
        : !canEditGraph ? '当前工作流为只读权限，不能启动运行。'
          : localCatalogState.status !== 'ready' ? '本机组件目录不可用，无法确认可运行组件。'
            : activeRunTargets.length === 0 ? '请选择至少一个输出目标。'
              : !runClosureHasExecutor ? '所选输出依赖图中没有已接入的本机或网络执行组件。'
                : missingCsvArtifactNodeIds.length > 0 ? '先为 CSV 结构预检节点选择本机文件。'
                  : runBusy ? '本机运行正在执行。' : '由本机调度器执行已选择的输出目标。网络节点会在运行前单独请求确认。'
  const favoriteComponentSet = new Set(favoriteComponentIds)
  const recentComponentSet = new Set(recentComponentIds)
  const filteredComponents = availableComponents
    .filter((item) => (componentScope === 'all'
      || componentScope === 'recent' && recentComponentSet.has(item.id)
      || componentScope === 'favorites' && favoriteComponentSet.has(item.id))
      && (componentCategory === '全部类别' || item.category === componentCategory)
      && `${item.category} ${item.title} ${item.description}`.toLowerCase().includes(search.toLowerCase()))
    .sort((left, right) => componentScope === 'recent'
      ? recentComponentIds.indexOf(left.id) - recentComponentIds.indexOf(right.id)
      : 0)

  const toggleComponentFavorite = (componentId: string) => setFavoriteComponentIds((current) => current.includes(componentId)
    ? current.filter((id) => id !== componentId)
    : [componentId, ...current].slice(0, 20))

  // Preview nodes stay local; registered project nodes carry stable identity and versioned parameters.
  // Catalog additions may request a visibility check; canvas drops keep their exact drop point and viewport.
  const addNode = (componentId: string, position?: XYPosition, revealIfObscured = false) => {
    if (!preview && !canEditGraph) return
    const component = availableComponents.find((item) => item.id === componentId)
    if (!component) return
    recordWorkflowUndoPoint()
    const definition = component.definition
    if (!preview && !definition) return
    setRecentComponentIds((current) => [componentId, ...current.filter((id) => id !== componentId)].slice(0, 20))
    const serial = ++nodeSerial.current
    const id = preview ? `local-node-${serial}` : `node-${crypto.randomUUID()}`
    const parameters = definition
      ? Object.fromEntries(Object.entries(definition.parameter_schema.properties).map(([key, property]) => [key, property.default]))
      : undefined
    if (definition?.component_id === 'ict.data.csv_artifact_source' && parameters && importedArtifact) {
      parameters.artifact_id = importedArtifact.artifact_id
    }
    const node: WorkflowNode = {
      id,
      type: 'research',
      position: position ?? nextWorkflowNodePosition(nodes),
      data: {
        category: component.category,
        title: component.title,
        description: component.description,
        ...(definition ? {
          component_id: definition.component_id,
          component_version: definition.version,
          input_ports: definition.inputs,
          output_ports: definition.outputs,
          parameter_schema: definition.parameter_schema,
          parameters,
          executor_binding: definition.executor_binding,
          execution_target: definition.execution_target,
          execution_available: definition.execution_available,
        } : {}),
      },
      selected: true,
    }
    if (revealIfObscured) setPendingNodeRevealId(id)
    setNodes((current) => [...current.map((item) => ({ ...item, selected: false })), node])
    setSelectedId(id)
    setMobileEditorView('canvas')
  }

  const handleNodeRevealHandled = useCallback((nodeId: string) => {
    setPendingNodeRevealId((current) => current === nodeId ? null : current)
  }, [])

  const onConnect = useCallback((connection: Connection) => {
    if (!canEditGraph) return
    const issue = getWorkflowConnectionIssue(connection, nodes)
    if (issue) {
      setActionError(issue)
      setActionNotice(null)
      setTab('校验')
      setDockExpanded(true)
      return
    }
    setActionError(null)
    setActionNotice(null)
    recordWorkflowUndoPoint()
    setEdges((current) => addEdge({ ...connection, type: 'smoothstep' }, current))
  }, [canEditGraph, nodes, recordWorkflowUndoPoint, setEdges])

  const onConnectEnd = useCallback((connectionState: FinalConnectionState) => {
    if (preview || connectionState.isValid !== false) return
    const connection = workflowConnectionFromFinalState(connectionState)
    if (!connection) return
    const issue = getWorkflowConnectionIssue(connection, nodes)
    if (!issue) return
    setActionError(issue)
    setActionNotice(null)
    setTab('校验')
    setDockExpanded(true)
  }, [nodes, preview])

  const handleNodeDragStart = useCallback(() => {
    if (canEditGraph) recordWorkflowUndoPoint()
  }, [canEditGraph, recordWorkflowUndoPoint])

  const handleAutoLayout = useCallback((maxColumns: number) => {
    const arranged = layoutWorkflowNodes(nodes, edges, maxColumns)
    if (arranged === nodes) return
    recordWorkflowUndoPoint()
    setNodes(arranged)
  }, [edges, nodes, recordWorkflowUndoPoint, setNodes])

  const updateWorkflowName = (name: string) => {
    if (!canEditGraph || name === workflowName) return
    setWorkflowName(name)
  }

  const updateSelectedTitle = (title: string) => {
    if (!selectedNode || !canEditGraph || title === selectedNode.data.title) return
    setNodes((current) => current.map((node) => node.id === selectedNode.id ? { ...node, data: { ...node.data, title } } : node))
  }

  const locateValidationIssue = (kind: 'node' | 'edge', id: string) => {
    const targetExists = kind === 'node' ? nodes.some((node) => node.id === id) : edges.some((edge) => edge.id === id)
    if (!targetExists) return
    setSelectedId(kind === 'node' ? id : null)
    // A request counter lets repeated clicks on the same issue recenter the canvas.
    setValidationFocus({ kind, id, request: ++validationFocusRequestRef.current })
  }

  useEffect(() => {
    if (!isDirty || !validation) return
    // Validation belongs to the saved revision; editing the draft makes its issue locations stale.
    setValidation(null)
    setValidationFocus(null)
  }, [isDirty, validation])

  const updateSelectedParameter = (key: string, value: string) => {
    if (!selectedNode || !canEditGraph) return
    if (Object.is(selectedNode.data.parameters?.[key], value)) return
    setNodes((current) => current.map((node) => node.id === selectedNode.id
      ? { ...node, data: { ...node.data, parameters: { ...(node.data.parameters ?? {}), [key]: value } } }
      : node))
  }

  const handleImportCsv = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0]
    event.currentTarget.value = ''
    if (!file || !selectedNode || !supportsLocalCsvImport(selectedNode.data.component_id)) return
    if (!file.name.toLocaleLowerCase().endsWith('.csv')) {
      setActionError('请选择 .csv 文件。')
      return
    }
    if (localRuntimeState.status !== 'ready') {
      setActionError('本机运行时未启动，无法导入文件。')
      return
    }
    setArtifactImportBusy(true)
    setActionError(null)
    try {
      const artifact = await importLocalCsv(file)
      updateSelectedParameter('artifact_id', artifact.artifact_id)
      setImportedArtifact(artifact)
      setActionNotice(`已将 ${artifact.file_name} 导入本机。文件不会上传到平台。`)
      setTab('校验')
      setDockExpanded(true)
    } catch (error) {
      console.error('导入本机 CSV 文件失败。', error)
      setActionError(error instanceof LocalRuntimeApiError ? `本机导入失败（${error.code}）。` : '本机 CSV 导入失败，请检查文件和运行时日志。')
    } finally {
      setArtifactImportBusy(false)
    }
  }

  const handleImportCsvFolder = async (event: ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(event.currentTarget.files ?? [])
    event.currentTarget.value = ''
    if (!selectedFiles.length || !selectedNode || !supportsLocalCsvFolderImport(selectedNode.data.component_id)) return
    if (localRuntimeState.status !== 'ready') {
      setActionError('本机运行时未启动，无法导入文件夹。')
      return
    }

    const csvFiles = selectedFiles
      .filter((file) => file.name.toLocaleLowerCase().endsWith('.csv'))
      .sort((left, right) => {
        const leftPath = (left as File & { webkitRelativePath?: string }).webkitRelativePath || left.name
        const rightPath = (right as File & { webkitRelativePath?: string }).webkitRelativePath || right.name
        return leftPath.localeCompare(rightPath, 'zh-CN')
      })
    const ignoredFileCount = selectedFiles.length - csvFiles.length
    const totalSize = csvFiles.reduce((sum, file) => sum + file.size, 0)
    if (csvFiles.length === 0) {
      setActionError('所选文件夹中没有 CSV 文件。')
      return
    }
    if (csvFiles.length > CSV_FOLDER_MAX_FILES) {
      setActionError(`首版每个文件夹最多处理 ${CSV_FOLDER_MAX_FILES} 个 CSV；当前选择了 ${csvFiles.length} 个。`)
      return
    }
    if (totalSize > CSV_FOLDER_MAX_TOTAL_BYTES) {
      setActionError('所选 CSV 文件总大小超过本机 100 MiB 限制，请拆分目录后再导入。')
      return
    }

    const firstRelativePath = (csvFiles[0] as File & { webkitRelativePath?: string }).webkitRelativePath || csvFiles[0].name
    const folderName = firstRelativePath.replace(/\\/g, '/').split('/')[0] || '所选文件夹'
    const relativePaths = csvFiles.map((file) => {
      const browserPath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || `${folderName}/${file.name}`
      return browserPath.replace(/\\/g, '/')
    })
    if (folderName.length > 120 || relativePaths.some((path) => path.length > 500 || path.startsWith('/') || path.split('/')[0] !== folderName || path.split('/').some((part) => part === '' || part === '.' || part === '..') || path.includes('\0') || path.split('/')[0].includes(':'))) {
      setActionError('浏览器返回了无效的文件夹相对路径，请重新选择目录。')
      return
    }

    const totalMiB = (totalSize / (1024 * 1024)).toLocaleString('zh-CN', { maximumFractionDigits: 1 })
    const confirmation = [
      `将把 ${csvFiles.length} 个 CSV（${totalMiB} MiB）复制到本机运行时。`,
      ignoredFileCount ? `另有 ${ignoredFileCount} 个非 CSV 文件会跳过。` : '',
      '文件不会上传到平台。继续导入吗？',
    ].filter(Boolean).join('\n')
    if (!window.confirm(confirmation)) return

    setArtifactImportBusy(true)
    setFolderImportProgress({ completed: 0, total: csvFiles.length })
    setActionError(null)
    setActionNotice(null)
    const importedFiles: Array<{ relative_path: string; artifact_id: string; sha256: string; size_bytes: number }> = []
    let failingPath = ''
    try {
      for (let index = 0; index < csvFiles.length; index += 1) {
        const file = csvFiles[index]
        failingPath = relativePaths[index]
        const artifact = await importLocalCsv(file)
        importedFiles.push({
          relative_path: relativePaths[index],
          artifact_id: artifact.artifact_id,
          sha256: artifact.sha256,
          size_bytes: artifact.size_bytes,
        })
        setFolderImportProgress({ completed: index + 1, total: csvFiles.length })
      }
      const manifest = JSON.stringify({
        folder_name: folderName,
        ignored_file_count: ignoredFileCount,
        files: importedFiles,
      })
      updateSelectedParameter('files_json', manifest)
      setActionNotice(`已将 ${importedFiles.length} 个 CSV 导入本机文件夹集合${ignoredFileCount ? `；跳过 ${ignoredFileCount} 个非 CSV 文件` : ''}。保存工作流后即可离线运行。`)
      setTab('校验')
      setDockExpanded(true)
    } catch (error) {
      console.error('导入本机 CSV 文件夹失败。', {
        failing_relative_path: failingPath,
        imported_count: importedFiles.length,
        expected_count: csvFiles.length,
        error,
      })
      const errorCode = error instanceof LocalRuntimeApiError ? `（${error.code}）` : ''
      setActionError(`文件夹导入在 ${importedFiles.length}/${csvFiles.length} 个文件后失败${errorCode}：${failingPath}。已导入文件留在本机产物库，未写入工作流集合；请处理失败文件后重试。`)
    } finally {
      setArtifactImportBusy(false)
      setFolderImportProgress(null)
    }
  }

  const removeSelectedNode = useCallback(() => {
    if (!selectedNode || !canEditGraph) return
    recordWorkflowUndoPoint()
    const removedId = selectedNode.id
    setNodes((current) => current.filter((node) => node.id !== removedId))
    setEdges((current) => current.filter((edge) => edge.source !== removedId && edge.target !== removedId))
    setSelectedId(null)
  }, [canEditGraph, recordWorkflowUndoPoint, selectedNode, setEdges, setNodes])

  useEffect(() => {
    const handleCanvasDelete = (event: KeyboardEvent) => {
      if ((event.key !== 'Delete' && event.key !== 'Backspace') || event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
      if (!window.matchMedia('(min-width: 761px)').matches || !canEditGraph || !selectedId || saveBusy || restoreBusy) return
      if (!(event.target instanceof Element) || !event.target.closest('.react-flow__node')) return
      event.preventDefault()
      removeSelectedNode()
    }
    window.addEventListener('keydown', handleCanvasDelete)
    return () => window.removeEventListener('keydown', handleCanvasDelete)
  }, [canEditGraph, removeSelectedNode, restoreBusy, saveBusy, selectedId])

  const saveCurrentDraftLocally = async () => {
    if (!workflowId || workflowState.status !== 'ready' || !canEditGraph) throw new Error('本机工作流保存条件不满足。')
    const localWorkflowBase = {
      ...workflowState.data,
      name: workflowName.trim(),
      description: workflowDescription,
      graph: currentGraph,
    }
    const browserSaved = writeLocalCache(`${localWorkflowDetailCachePrefix}${encodeURIComponent(workflowId)}`, localWorkflowBase, '工作流')
    if (!isLocalWorkflow) setWorkflowPendingPlatformSync(workflowId, true)
    let runtimeSaved = false
    let savedRevision = workflowState.data.revision
    if (localRuntimeState.status === 'ready') {
      try {
        let previousRevision = 0
        try {
          previousRevision = (await getLocalWorkflowDraft(workflowId)).revision
        } catch (error) {
          if (!(error instanceof LocalRuntimeApiError && error.status === 404)) throw error
        }
        savedRevision = Math.max(workflowState.data.revision, previousRevision) + 1
        await saveLocalWorkflowDraft(workflowId, savedRevision, currentGraph, isLocalWorkflow ? { name: workflowName.trim(), description: workflowDescription } : undefined)
        runtimeSaved = true
      } catch (error) {
        console.error('本机运行时副本保存失败；浏览器缓存仍会保留当前草稿。', error)
      }
    }
    const localWorkflow = { ...localWorkflowBase, revision: savedRevision }
    setWorkflowState({ status: 'ready', data: localWorkflow, cached: true, ...(!isLocalWorkflow ? { localUnsynced: true } : {}) })
    if (isLocalWorkflow) setWorkflowPendingPlatformSync(workflowId, false)
    setValidation(null)
    setValidationFocus(null)
    return { browserSaved, runtimeSaved }
  }

  const hasUnsyncedLocalChanges = workflowState.status === 'ready' && workflowState.localUnsynced === true
  const activeRevisionConflict = revisionConflict?.workflowId === workflowId ? revisionConflict : null
  const handleSaveDraft = async () => {
    if (!canSaveDraft || !workflowId || workflowState.status !== 'ready' || saveBusy ||
        (!isDirty && !(hasUnsyncedLocalChanges && Boolean(config?.token.trim())))) return
    setSaveBusy(true)
    setActionError(null)
    setActionNotice(null)
    setTab('校验')
    setDockExpanded(true)
    try {
      if (activeRevisionConflict) {
        const persistence = await saveCurrentDraftLocally()
        setActionNotice(persistence.runtimeSaved
          ? '本机草稿已更新；平台修订冲突仍待处理。'
          : persistence.browserSaved
            ? '本机草稿已更新到浏览器缓存；平台修订冲突仍待处理。'
            : '本机草稿仍保留在当前页面；浏览器缓存写入失败，平台修订冲突仍待处理。')
        return
      }
      if (isLocalWorkflow) {
        const persistence = await saveCurrentDraftLocally()
        setActionNotice(persistence.runtimeSaved
          ? '本机工作流已保存；仅保存在此设备。'
          : '工作流已保留在浏览器缓存；本机运行时未能保存，请检查运行时日志。')
        return
      }
      if (config?.token.trim()) {
        try {
          const saved = await saveWorkflowDraft(config, {
            id: workflowId,
            revision: workflowState.data.revision,
            name: workflowName.trim(),
            description: workflowDescription,
            graph: currentGraph,
          })
          setWorkflowState({ status: 'ready', data: saved })
          setWorkflowPendingPlatformSync(workflowId, false)
          setRevisionConflict(null)
          setWorkflowName(saved.name)
          setWorkflowDescription(saved.description)
          setCurrentVersion(saved.current_version)
          setValidation(null)
          setValidationFocus(null)
          writeLocalCache(`${localWorkflowDetailCachePrefix}${encodeURIComponent(workflowId)}`, saved, '工作流')
          if (localRuntimeState.status === 'ready') {
            try {
              let previousRevision = 0
              try { previousRevision = (await getLocalWorkflowDraft(workflowId)).revision }
              catch (error) { if (!(error instanceof LocalRuntimeApiError && error.status === 404)) throw error }
              await saveLocalWorkflowDraft(workflowId, Math.max(saved.revision, previousRevision) + 1, currentGraph)
            } catch (localError) {
              console.error('平台草稿已保存，但本机副本未同步。', localError)
              setActionNotice('平台草稿已保存；本机副本未同步，暂不能离线运行此更新。')
              return
            }
          }
          setActionNotice('草稿已保存')
          return
        } catch (error) {
          if (isWorkflowRevisionConflict(error)) {
            const persistence = await saveCurrentDraftLocally()
            const localSnapshot: WorkflowRevisionSnapshot = {
              revision: workflowState.data.revision,
              current_version: workflowState.data.current_version,
              name: workflowName.trim(),
              description: workflowDescription,
              graph: currentGraph,
            }
            try {
              const platform = await getWorkflow(config, workflowId)
              if (platform.owner_type !== owner.type || platform.owner_id !== owner.id) {
                throw new Error('工作流最新修订与当前项目或复现任务不匹配。')
              }
              setRevisionConflict({
                workflowId,
                local: localSnapshot,
                platform: {
                  revision: platform.revision,
                  current_version: platform.current_version,
                  name: platform.name,
                  description: platform.description,
                  graph: platform.graph,
                },
              })
              setActionNotice(persistence.runtimeSaved
                ? `保存遇到修订冲突；本机草稿已保留。平台当前为修订 ${platform.revision}，请核对两侧后选择是否同步。`
                : persistence.browserSaved
                  ? `保存遇到修订冲突；草稿已保存在浏览器缓存。平台当前为修订 ${platform.revision}，请核对两侧后选择是否同步。`
                  : `保存遇到修订冲突；草稿仍在当前页面。平台当前为修订 ${platform.revision}，请先确认本机副本可用。`)
            } catch (refreshError) {
              console.error('保存遇到修订冲突，但读取平台最新修订失败。', refreshError)
              setActionError(persistence.runtimeSaved || persistence.browserSaved
                ? '本机草稿已保留，但暂时无法读取平台最新修订。重连后重新打开工作流并核对版本。'
                : '检测到修订冲突；本机副本未能持久化，当前页面仍保留编辑内容。请勿关闭页面，恢复服务后重试。')
            }
            return
          }
          const canFallBackToLocal = error instanceof TypeError || error instanceof WorkflowApiError && error.status >= 500
          if (!canFallBackToLocal || !canLocalSave) throw error
          console.warn('平台不可用，改为保存本机工作流副本。', error)
        }
      }
      if (isDirty) {
        const persistence = await saveCurrentDraftLocally()
        setActionNotice(persistence.runtimeSaved
          ? '本机草稿已保存；平台副本尚未同步。'
          : persistence.browserSaved
            ? '本机草稿已保存到浏览器缓存；本机运行时副本暂不可用。'
            : '本机副本未能持久化；当前页面仍保留编辑内容。')
      } else {
        setActionNotice('本机副本仍未同步到平台；连接恢复后可再次尝试。')
      }
    } catch (error) {
      console.error('保存工作流草稿失败。', error)
      setActionError(error instanceof LocalRuntimeApiError ? `本机保存失败（${error.code}）。` : explainWorkflowError(error))
    } finally {
      setSaveBusy(false)
    }
  }

  const handleSyncConflictedDraft = async () => {
    if (!activeRevisionConflict || !config?.token.trim() || workflowState.status !== 'ready' || saveBusy || !canEditGraph) return
    const approved = window.confirm(
      `即将先将平台当前草稿（修订 ${activeRevisionConflict.platform.revision}）保存为不可变版本，再把本机草稿保存为新的平台修订。平台当前内容会留在版本历史中；本机草稿不会自动合并。请先核对两侧内容，是否继续？`,
    )
    if (!approved) return

    setSaveBusy(true)
    setActionError(null)
    setActionNotice(null)
    try {
      const localPersistence = await saveCurrentDraftLocally()
      const saved = await syncConflictedWorkflowToPlatform(config, {
        id: workflowId!,
        name: workflowName.trim(),
        description: workflowDescription,
        graph: currentGraph,
      }, activeRevisionConflict.platform.revision)
      setWorkflowState({ status: 'ready', data: saved })
      setWorkflowPendingPlatformSync(saved.id, false)
      setRevisionConflict(null)
      setWorkflowName(saved.name)
      setWorkflowDescription(saved.description)
      setCurrentVersion(saved.current_version)
      setValidation(null)
      setValidationFocus(null)
      const browserSaved = writeLocalCache(`${localWorkflowDetailCachePrefix}${encodeURIComponent(saved.id)}`, saved, '工作流')
      let runtimeSaved = false
      if (localRuntimeState.status === 'ready') {
        try {
          let previousRevision = 0
          try { previousRevision = (await getLocalWorkflowDraft(saved.id)).revision }
          catch (error) { if (!(error instanceof LocalRuntimeApiError && error.status === 404)) throw error }
          await saveLocalWorkflowDraft(saved.id, Math.max(saved.revision, previousRevision) + 1, saved.graph)
          runtimeSaved = true
        } catch (error) {
          console.error('平台冲突已解决，但本机 runtime 副本未更新。', error)
        }
      }
      if (!runtimeSaved) setWorkflowPendingPlatformSync(saved.id, !browserSaved && !localPersistence.browserSaved)
      setActionNotice(runtimeSaved
        ? `已同步：平台原草稿保留在不可变版本 v${saved.current_version}，本机草稿已保存为修订 ${saved.revision}。`
        : browserSaved || localPersistence.browserSaved
          ? `平台已保存为修订 ${saved.revision}；浏览器中的本机副本已保留，本机 runtime 副本待更新。`
          : `平台已保存为修订 ${saved.revision}；本机副本未能更新，请保持联网并重新打开工作流。`)
    } catch (error) {
      if (error instanceof WorkflowRevisionMovedError) {
        const persistence = await saveCurrentDraftLocally()
        setRevisionConflict({
          workflowId: error.latest.id,
          local: {
            revision: workflowState.status === 'ready' ? workflowState.data.revision : activeRevisionConflict.local.revision,
            current_version: workflowState.status === 'ready' ? workflowState.data.current_version : activeRevisionConflict.local.current_version,
            name: workflowName.trim(),
            description: workflowDescription,
            graph: currentGraph,
          },
          platform: {
            revision: error.latest.revision,
            current_version: error.latest.current_version,
            name: error.latest.name,
            description: error.latest.description,
            graph: error.latest.graph,
          },
        })
        setActionNotice(persistence.runtimeSaved || persistence.browserSaved
          ? `平台在同步期间又产生修订 ${error.latest.revision}；本机草稿已保留，请重新核对。`
          : `平台在同步期间又产生修订 ${error.latest.revision}；本机草稿仍在当前页面，请勿关闭页面。`)
      } else {
        console.error('同步冲突中的本机工作流失败。', error)
        setActionError('本机草稿仍已保留；平台快照或同步未完成。请检查错误后重试，平台修订不会被自动覆盖。')
      }
    } finally {
      setSaveBusy(false)
    }
  }

  const handleRunWorkflowLocally = async () => {
    if (!canRunLocal || !workflowId || workflowState.status !== 'ready' || runBusy) return
    if (runClosureNetworkNodes.length > 0) {
      const doiList = runClosureNetworkNodes.map((node) =>
        `${node.data.title} · ${String(node.data.parameters?.doi ?? '未填写 DOI')}`,
      ).join('\n')
      const approved = window.confirm(
        `所选输出依赖图包含网络节点。确认后，本机将通过 HTTPS 向固定的 api.crossref.org 端点请求以下 DOI 的公开书目信息：\n\n${doiList}\n\n不会上传本机文件。是否继续运行？`,
      )
      if (!approved) return
    }
    setRunBusy(true)
    setActionError(null)
    setActionNotice(null)
    setTab('运行历史')
    setDockExpanded(true)
    try {
      let previousRevision = 0
      try {
        previousRevision = (await getLocalWorkflowDraft(workflowId)).revision
      } catch (error) {
        if (!(error instanceof LocalRuntimeApiError && error.status === 404)) throw error
      }
      const nextRevision = Math.max(workflowState.data.revision, previousRevision) + 1
      await saveLocalWorkflowDraft(workflowId, nextRevision, currentGraph, isLocalWorkflow ? { name: workflowName.trim(), description: workflowDescription } : undefined)
      const localWorkflow = { ...workflowState.data, revision: nextRevision, name: workflowName.trim(), description: workflowDescription, graph: currentGraph }
      const localUnsynced = !isLocalWorkflow && (workflowState.localUnsynced === true || isDirty)
      setWorkflowState({ status: 'ready', data: localWorkflow, ...(workflowState.cached || localUnsynced ? { cached: true } : {}), ...(localUnsynced ? { localUnsynced: true } : {}) })
      writeLocalCache(`${localWorkflowDetailCachePrefix}${encodeURIComponent(workflowId)}`, localWorkflow, '工作流')
      if (localUnsynced) setWorkflowPendingPlatformSync(workflowId, true)
      const submitted = await submitLocalWorkflowRun(workflowId, activeRunTargets)
      const detail = await getLocalWorkflowRun(submitted.run_id)
      setRunDetail(detail)
      setRunHistory((current) => [detail, ...current.filter((item) => item.run_id !== detail.run_id)])
      setRunBusy(['queued', 'running', 'waiting_external'].includes(detail.status))
      setActionNotice(isLocalWorkflow
        ? `本机运行已提交（${detail.run_id}）；项目和运行记录仅保存在此设备。`
        : isDirty || workflowState.localUnsynced
        ? `本机运行已提交（${detail.run_id}）；运行使用本机草稿，平台副本尚未同步。`
        : `本机运行已提交（${detail.run_id}）。`)
    } catch (error) {
      console.error('提交本机工作流运行失败。', error)
      setRunBusy(false)
      if (error instanceof LocalRuntimeApiError) {
        setActionError(localCapabilityMessage(error.code))
      } else {
        setActionError('本机运行未启动。请检查工作流结构并查看本机运行时日志。')
      }
    }
  }

  const handleCancelLocalRun = async () => {
    if (!runDetail || runCancelBusy || !['queued', 'running', 'waiting_external'].includes(runDetail.status)) return
    setRunCancelBusy(true)
    setActionError(null)
    try {
      await cancelLocalWorkflowRun(runDetail.run_id)
      setActionNotice('已请求取消本机运行；正在等待节点停止并保存状态。')
    } catch (error) {
      console.error('取消本机工作流运行失败。', error)
      setActionError(error instanceof LocalRuntimeApiError ? `取消运行失败（${error.code}）。` : '取消运行失败，请检查本机运行时日志。')
    } finally {
      setRunCancelBusy(false)
    }
  }

  const handleRecoverLocalRun = async () => {
    const sourceRun = runDetail
    if (!sourceRun || sourceRun.status !== 'failed' || sourceRun.error_code !== 'LOCAL_WORKER_RESTARTED' || runRecoveryBusy) return
    setRunRecoveryBusy(true)
    setRunRecoveryNotice(null)
    setRunRecoveryError(null)
    try {
      const recovery = await recoverLocalWorkflowRun(sourceRun.run_id)
      // Recovery creates a new run; preserve the interrupted source record in history.
      setRunRecoveryNotice(`已提交新运行 ${recovery.run_id}：复用 ${recovery.restored_node_ids.length} 个节点结果，重新调度 ${recovery.rerun_node_ids.length} 个节点。`)
      setRunHistory((current) => [recovery, ...current.filter((item) => item.run_id !== recovery.run_id)])
      setRunBusy(['queued', 'running', 'waiting_external'].includes(recovery.status))
      try {
        const detail = await getLocalWorkflowRun(recovery.run_id)
        setRunDetail(detail)
        setRunHistory((current) => [detail, ...current.filter((item) => item.run_id !== detail.run_id)])
        setRunBusy(['queued', 'running', 'waiting_external'].includes(detail.status))
      } catch (error) {
        console.error('恢复运行已提交，但读取新运行详情失败。', error)
        setRunRecoveryError('恢复已提交，但暂时无法读取新运行详情；原运行记录保持不变。')
      }
    } catch (error) {
      console.error('恢复本机工作流运行失败。', error)
      setRunRecoveryError(error instanceof LocalRuntimeApiError
        ? `恢复失败（${error.code}）。原运行记录未更改。`
        : '恢复请求失败。原运行记录未更改。')
    } finally {
      setRunRecoveryBusy(false)
    }
  }

  const handleValidate = async () => {
    if (!canValidateWorkflow || !workflowId || workflowState.status !== 'ready' || isDirty || validationBusy) return
    setValidationBusy(true)
    setActionError(null)
    setActionNotice(null)
    setValidationFocus(null)
    setTab('校验')
    setDockExpanded(true)
    try {
      const result = localRuntimeState.status === 'ready'
        ? await validateLocalWorkflow(workflowId, workflowState.data.revision, currentGraph)
        : config?.token.trim()
          ? await validateWorkflow(config, workflowId)
          : null
      if (!result) throw new Error('本机运行时和平台校验服务均不可用。')
      // The panel derives its heading from this result; save/version notices must not mask validation failures.
      setValidation(result)
    } catch (error) {
      setActionError(explainWorkflowError(error))
    } finally {
      setValidationBusy(false)
    }
  }

  const handleCreateVersion = async () => {
    if (!canPersist || !config || !workflowId || isDirty || versionBusy) return
    setVersionBusy(true)
    setActionError(null)
    setActionNotice(null)
    setTab('校验')
    setDockExpanded(true)
    try {
      const result = await createWorkflowVersion(config, workflowId)
      setCurrentVersion(result.workflow.current_version)
      setWorkflowState((current) => current.status === 'ready'
        ? { status: 'ready', data: { ...current.data, current_version: result.workflow.current_version } }
        : current)
      setActionNotice(result.created ? `已创建不可变版本 v${result.version.version}` : `内容未改变，继续使用版本 v${result.version.version}`)
    } catch (error) {
      setActionError(explainWorkflowError(error))
    } finally {
      setVersionBusy(false)
    }
  }

  const handleOpenVersionHistory = async () => {
    if (!config || !workflowId || !canReadWorkflow || versionHistoryBusy) return
    setVersionHistoryOpen(true)
    setVersionHistoryBusy(true)
    setActionError(null)
    setVersionHistoryState({ status: 'loading' })
    setSelectedVersionNumber(null)
    setSelectedVersionState({ status: 'idle' })
    try {
      const versions = await listWorkflowVersions(config, workflowId)
      setVersionHistoryState({ status: 'ready', data: versions })
      if (versions.length > 0) {
        const newest = versions[versions.length - 1]
        setSelectedVersionNumber(newest.version)
        setSelectedVersionState({ status: 'loading' })
        try {
          const detail = await getWorkflowVersion(config, workflowId, newest.version)
          setSelectedVersionState({ status: 'ready', data: detail })
        } catch (error) {
          setSelectedVersionState({ status: 'error', message: explainWorkflowError(error) })
        }
      }
    } catch (error) {
      setVersionHistoryState({ status: 'error', message: explainWorkflowError(error) })
    } finally {
      setVersionHistoryBusy(false)
    }
  }

  const handleSelectVersion = async (versionNumber: number) => {
    if (!config || !workflowId) return
    setSelectedVersionNumber(versionNumber)
    setSelectedVersionState({ status: 'loading' })
    try {
      const detail = await getWorkflowVersion(config, workflowId, versionNumber)
      setSelectedVersionState({ status: 'ready', data: detail })
    } catch (error) {
      setSelectedVersionState({ status: 'error', message: explainWorkflowError(error) })
    }
  }

  const handleRestoreSelectedVersion = async () => {
    if (!canPersist || !config || !workflowId || workflowState.status !== 'ready' ||
        selectedVersionState.status !== 'ready' || restoreBusy) return
    const versionNumber = selectedVersionState.data.version
    if (isDirty && !window.confirm('当前草稿有未保存修改。恢复会用历史版本覆盖当前草稿，历史版本本身不会改变。继续吗？')) return

    setRestoreBusy(true)
    setActionError(null)
    setActionNotice(null)
    try {
      const restored = await restoreWorkflowVersion(
        config,
        workflowId,
        versionNumber,
        workflowState.data.revision,
      )
      recordWorkflowUndoPoint()
      const draftNodes = restoreWorkflowNodes(restored.graph)
      const readyNodes = registeredComponents.length > 0
        ? hydrateWorkflowNodes(draftNodes, registeredComponents)
        : draftNodes
      const draftEdges = restored.graph.edges.map((edge) => ({ ...edge, type: edge.type ?? 'smoothstep' })) as Edge[]
      setWorkflowState({ status: 'ready', data: restored })
      setWorkflowName(restored.name)
      setWorkflowDescription(restored.description)
      setCurrentVersion(restored.current_version)
      setNodes(readyNodes)
      setEdges(draftEdges)
      setSelectedId(null)
      setValidation(null)
      setValidationFocus(null)
      setVersionHistoryOpen(false)
      setActionNotice(`已将 v${versionNumber} 恢复到当前草稿；历史版本保持不变`)
    } catch (error) {
      setActionError(explainWorkflowError(error))
    } finally {
      setRestoreBusy(false)
    }
  }

  const handleSelectLocalRun = async (runId: string) => {
    setRunRecoveryNotice(null)
    setRunRecoveryError(null)
    try {
      const detail = await getLocalWorkflowRun(runId)
      setRunDetail(detail)
      // Selecting a completed history item must clear the busy state of the previously selected run.
      setRunBusy(['queued', 'running', 'waiting_external'].includes(detail.status))
      setTab('运行历史')
      setDockExpanded(true)
    } catch (error) {
      console.error('打开本机运行记录失败。', error)
      setActionError(error instanceof LocalRuntimeApiError ? `无法读取运行记录（${error.code}）。` : '无法读取本机运行记录。')
    }
  }

  const panelCopies: Record<WorkflowDockTab, { title: string; detail: string; icon: IconName }> = preview
    ? {
      校验: { title: '校验未执行', detail: '', icon: 'shield' },
      运行历史: { title: '没有运行实例', detail: '', icon: 'clock' },
      日志: { title: '没有执行日志', detail: '', icon: 'file' },
      产物: { title: '没有生成产物', detail: '', icon: 'attachment' },
    }
    : {
      校验: actionError
        ? { title: '操作未完成', detail: actionError, icon: 'shield' }
        : actionNotice
          ? { title: actionNotice.startsWith('已复制 ') || actionNotice.startsWith('已粘贴 ') ? '画布操作完成' : '工作流已更新', detail: actionNotice, icon: 'check' }
          : validation
            ? {
              title: validation.issues.length === 0
                ? validation.structural_status === 'valid' && validation.contract_status === 'valid' ? '图结构与组件契约通过' : '校验未通过'
                : [
                  ['blocker', '阻断'], ['warning', '警告'], ['info', '提示'],
                ].map(([severity, label]) => {
                  const count = validation.issues.filter((issue) => issue.severity === severity).length
                  return count > 0 ? `${label} ${count} 项` : ''
                }).filter(Boolean).concat(
                  validation.issues.some((issue) => !issue.severity)
                    ? [`级别未提供 ${validation.issues.filter((issue) => !issue.severity).length} 项`]
                    : [],
                ).join(' · '),
              detail: '',
              icon: validation.issues.length === 0 && validation.structural_status === 'valid' && validation.contract_status === 'valid' ? 'check' : 'shield',
            }
            : { title: workflowState.status === 'error' ? '工作流读取失败' : workflowState.status === 'loading' ? '正在读取工作流' : '尚未执行校验', detail: workflowState.status === 'error' ? workflowState.message : '', icon: 'shield' },
      运行历史: runDetail
        ? { title: runStatusLabel(runDetail.status), detail: `运行 ${runDetail.run_id} · 目标 ${runDetail.target_node_ids.length} 个`, icon: 'clock' }
        : localRuntimeState.status === 'ready'
          ? { title: runHistory.length ? `${runHistory.length} 条本机运行记录` : '暂无本机运行记录', detail: '', icon: 'clock' }
          : { title: '本机运行时未连接', detail: '', icon: 'server' },
      日志: runDetail
        ? { title: `${runDetail.events.length} 条状态事件`, detail: '', icon: 'file' }
        : { title: '暂无执行日志', detail: '', icon: 'file' },
      产物: runDetail
        ? { title: `${runDetail.node_runs.flatMap((item) => collectArtifactHandles(item.output)).length} 个产物引用`, detail: '', icon: 'attachment' }
        : { title: '暂无运行产物', detail: '', icon: 'attachment' },
    }
  const panelCopy = actionError
    ? { title: '操作未完成', detail: actionError, icon: 'shield' as IconName }
    : actionNotice
      ? { title: '工作流已更新', detail: actionNotice, icon: 'check' as IconName }
      : panelCopies[tab]
  const activeDockTab = workflowDockTabs.find((item) => item.label === tab) ?? workflowDockTabs[0]
  const workflowAccessReason = !workflowId
    ? `请先从${owner.type === 'project' ? '项目' : '复现任务'}工作区选择一个工作流。`
    : workflowState.status === 'loading'
      ? '正在读取工作流；载入后才能操作。'
      : workflowState.status === 'error'
        ? '工作流读取失败；请重新读取后再操作。'
        : workflowState.status !== 'ready'
          ? '工作流尚未载入。'
          : !canEditGraph
            ? '当前对象权限为只读，不能修改工作流。'
            : undefined
  const historyTitle = preview
    ? '布局预览不读取真实工作流历史。'
    : !workflowId
      ? workflowAccessReason
      : workflowState.status === 'loading'
        ? workflowAccessReason
        : workflowState.status === 'error'
          ? workflowAccessReason
          : versionHistoryBusy ? '正在读取工作流历史…' : '查看此工作流的不可变历史快照'
  const persistTitle = preview
    ? '布局预览不会保存或创建版本。'
    : workflowAccessReason
      ?? (versionBusy ? '正在创建工作流版本…' : isDirty ? '请先保存草稿。' : nodes.length === 0 ? '至少添加一个节点后才能创建版本。' : '保存当前结构的不可变快照。')
  const saveTitle = preview
    ? '布局预览不会写入项目。'
    : workflowAccessReason
      ?? (saveBusy ? '正在保存工作流草稿…' : hasUnsyncedLocalChanges && config?.token.trim() ? '把本机副本同步到平台工作流。' : hasUnsyncedLocalChanges ? '本机副本尚未同步；连接平台后可同步。' : isDirty && canLocalSave && !config?.token.trim() ? '将当前草稿保存到本机；平台副本保持不变。' : isDirty ? '保存当前工作流草稿。' : '当前草稿没有未保存更改。')
  const validateTitle = preview
    ? '静态布局示例没有真实组件契约，不执行校验。'
    : workflowAccessReason
      ?? (validationBusy ? '正在校验工作流…' : isDirty ? '请先保存草稿，再执行结构与组件校验。' : localRuntimeState.status === 'ready' ? '使用本机组件注册表校验，不依赖平台服务。' : '通过平台服务校验工作流结构和组件契约。')
  const runTitle = canRunLocal && localUnavailableNodeCount > 0
    ? `所选输出有 ${localUnavailableNodeCount} 个节点没有本机执行器；运行后这些节点及其下游会被阻断。`
    : runBlocker
  const undoTitle = preview
    ? canUndo ? '撤销上一步操作；只影响当前预览，不会写入项目。快捷键 Ctrl+Z / ⌘Z。' : '当前预览没有可撤销的操作。'
    : workflowAccessReason ?? (saveBusy ? '保存完成前暂不能撤销。' : restoreBusy ? '版本恢复完成前暂不能撤销。' : canUndo ? '撤销上一步工作流编辑。快捷键 Ctrl+Z / ⌘Z。' : '没有可撤销的工作流编辑。')
  const redoTitle = preview
    ? canRedo ? '重做上一步操作；只影响当前预览，不会写入项目。快捷键 Ctrl+Shift+Z / ⌘Shift+Z。' : '当前预览没有可重做的操作。'
    : workflowAccessReason ?? (saveBusy ? '保存完成前暂不能重做。' : restoreBusy ? '版本恢复完成前暂不能重做。' : canRedo ? '重做上一步工作流编辑。快捷键 Ctrl+Shift+Z / ⌘Shift+Z。' : '没有可重做的工作流编辑。')
  const editorStatus = preview ? '仅当前页面' : workflowState.status === 'loading' ? '读取中' : workflowState.status === 'error' ? '读取失败' : workflowState.status === 'ready' ? saveBusy ? '保存中' : isLocalWorkflow ? isDirty ? '有未保存更改 · 仅本机' : '仅保存在此设备' : isDirty ? '有未保存更改' : workflowState.cached ? '本机副本' : '已保存' : '工作流 ID 未提供'

  return <section className={'workflow-editor' + (editorMode === 'guided' ? ' workflow-editor--guided' : '')}>
    <header className="editor-bar">
      <div className="editor-bar__identity">
        <button className="back-link" onClick={onBack}>← {backLabel}</button>
        <span className="editor-bar__divider" />
        <div className="editor-bar__copy">
          <strong><Icon name="workflow" />{workflowId && workflowState.status === 'ready'
            ? <input className="editor-workflow-name" aria-label="工作流名称" title={workflowName} maxLength={160} value={workflowName} onFocus={(event) => beginWorkflowTextEdit('workflow-name', event.currentTarget.value)} onChange={(event) => updateWorkflowName(event.target.value)} onBlur={(event) => finishWorkflowTextEdit('workflow-name', event.currentTarget.value)} disabled={!canEditGraph} />
            : preview ? '工作流布局示例' : '项目工作流'}</strong>
          <span>{owner.name}{preview ? '' : workflowId ? ` · 草稿修订 ${workflowState.status === 'ready' ? workflowState.data.revision : '—'}` : ' · 尚未选择工作流'}</span>
        </div>
      </div>
      <div className="editor-bar__tools"><button type="button" onClick={undoWorkflowEdit} disabled={!canEditGraph || !canUndo || saveBusy || restoreBusy} title={undoTitle} aria-keyshortcuts="Control+Z Meta+Z">撤销</button><button type="button" onClick={redoWorkflowEdit} disabled={!canEditGraph || !canRedo || saveBusy || restoreBusy} title={redoTitle} aria-keyshortcuts="Control+Shift+Z Meta+Shift+Z Control+Y">重做</button><button type="button" onClick={handleOpenVersionHistory} disabled={!canReadWorkflow || versionHistoryBusy} title={historyTitle}>历史</button><button type="button" onClick={handleCreateVersion} disabled={!canPersist || isDirty || versionBusy || nodes.length === 0} title={persistTitle}>{versionBusy ? '创建中…' : `创建 v${currentVersion + 1}`}</button></div>
      <div className="editor-bar__actions"><span className={'editor-local-state' + (preview ? ' is-preview' : '') + (isDirty || hasUnsyncedLocalChanges ? ' is-dirty' : '') + (workflowState.status === 'error' ? ' is-error' : '')}><i />{editorStatus}</span><button type="button" onClick={handleSaveDraft} disabled={!canSaveDraft || (activeRevisionConflict ? !isDirty : !isDirty && !(hasUnsyncedLocalChanges && Boolean(config?.token.trim()))) || saveBusy || !workflowName.trim()} title={activeRevisionConflict ? '只更新本机副本；平台同步请先核对冲突并明确确认' : saveTitle}>{saveBusy ? '保存中…' : activeRevisionConflict ? '保存本机草稿' : isLocalWorkflow ? '保存到本机' : hasUnsyncedLocalChanges && config?.token.trim() ? '同步到平台' : workflowState.status === 'ready' && workflowState.cached ? '保存到本机' : '保存'}</button><button type="button" onClick={handleValidate} disabled={!canValidateWorkflow || isDirty || (hasUnsyncedLocalChanges && localRuntimeState.status !== 'ready') || validationBusy} title={validateTitle}>{validationBusy ? '校验中…' : '校验'}</button><button className="run-button" onClick={() => void handleRunWorkflowLocally()} disabled={!canRunLocal} title={runTitle}>{runBusy ? '运行中…' : '本机运行'}</button></div>
    </header>
    <nav className="workflow-mobile-tabs" aria-label="工作流编辑区域">
      <button type="button" className={mobileEditorView === 'components' ? 'active' : ''} aria-pressed={mobileEditorView === 'components'} aria-controls="workflow-component-panel" onClick={() => setMobileEditorView('components')}>组件</button>
      <button type="button" className={mobileEditorView === 'canvas' ? 'active' : ''} aria-pressed={mobileEditorView === 'canvas'} aria-controls="workflow-canvas-panel" onClick={() => setMobileEditorView('canvas')}>画布</button>
      <button type="button" className={mobileEditorView === 'inspection' ? 'active' : ''} aria-pressed={mobileEditorView === 'inspection'} aria-controls="workflow-inspector-panel" onClick={() => setMobileEditorView('inspection')}>检查</button>
      <button type="button" onClick={handleOpenVersionHistory} disabled={!canReadWorkflow || versionHistoryBusy} title={historyTitle}>历史</button>
      <button type="button" onClick={handleCreateVersion} disabled={!canPersist || isDirty || versionBusy || nodes.length === 0} title={persistTitle} aria-label={`创建不可变版本 v${currentVersion + 1}`}>{versionBusy ? '创建中' : '新版本'}</button>
    </nav>
    <div className={'editor-grid editor-grid--mobile-' + mobileEditorView + (libraryOpen ? '' : ' editor-grid--library-collapsed') + (inspectorOpen ? '' : ' editor-grid--inspector-collapsed') + (dockExpanded ? ' editor-grid--dock-expanded' : ' editor-grid--dock-collapsed')}>
      {revisionConflict && revisionConflict.workflowId === workflowId && workflowState.status === 'ready' && <WorkflowRevisionConflictNotice
        local={{ ...revisionConflict.local, name: workflowName, graph: currentGraph }}
        platform={revisionConflict.platform}
        canOpenHistory={canReadWorkflow}
        canSyncLocalDraft={Boolean(canPersist && hasUnsyncedLocalChanges && !saveBusy)}
        syncBusy={saveBusy}
        onOpenHistory={() => void handleOpenVersionHistory()}
        onSyncLocalDraft={() => void handleSyncConflictedDraft()}
      />}
      {canRunLocal && localUnavailableNodeCount > 0 && <section className="workflow-local-partial-run" role="status" aria-live="polite">
        <Icon name="shield" size={17} />
        <div><strong>{localUnavailableNodeCount} 个节点无本机执行器</strong></div>
      </section>}
      <aside className="node-library" id="workflow-component-panel" aria-label="工作流组件目录">
        <div className="node-library__heading"><div><h2>组件目录</h2></div>{preview ? <span>{workflowComponents.length}</span> : registeredComponents.length > 0 ? <span className="node-library__state">{registeredComponents.length}</span> : <span className="node-library__state">{catalogState.status === 'loading' || localCatalogState.status === 'loading' ? '读取中' : '—'}</span>}</div>
        {preview || availableComponents.length > 0 ? <>
          <label className="component-search"><Icon name="search" size={15} /><input aria-label="搜索工作流组件" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={preview ? '搜索组件示意' : '搜索已登记组件'} /></label>
          <div className="component-scope-tabs" role="group" aria-label="组件目录范围">
            <button type="button" className={componentScope === 'all' ? 'active' : ''} aria-pressed={componentScope === 'all'} onClick={() => setComponentScope('all')}>全部</button>
            <button type="button" className={componentScope === 'recent' ? 'active' : ''} aria-pressed={componentScope === 'recent'} title="按最近添加到工作流的顺序筛选" onClick={() => setComponentScope('recent')}>最近使用</button>
            <button type="button" className={componentScope === 'favorites' ? 'active' : ''} aria-pressed={componentScope === 'favorites'} title="只显示已收藏的组件" onClick={() => setComponentScope('favorites')}>收藏</button>
          </div>
          <div className="component-category-tabs" role="group" aria-label="按组件类别筛选">
            <button type="button" className={componentCategory === '全部类别' ? 'active' : ''} aria-pressed={componentCategory === '全部类别'} onClick={() => setComponentCategory('全部类别')}>全部类别</button>
            {componentCategories.map((category) => <button type="button" key={category} className={componentCategory === category ? 'active' : ''} aria-pressed={componentCategory === category} onClick={() => setComponentCategory(category)}>{category}</button>)}
          </div>
          <div className="node-library__items">{filteredComponents.map((item) => {
            // Keep execution eligibility scannable; the details drawer retains the full port contract.
            const availability = item.definition ? workflowNodeAvailability({
              category: item.category,
              title: item.title,
              description: item.description,
              component_id: item.id,
              execution_target: item.definition.execution_target,
              execution_available: item.definition.execution_available,
              execution_blockers: item.definition.execution_blockers ?? [],
            }) : null
            const availabilityLabel = availability ? workflowNodeAvailabilityShortLabel(availability.tone) : preview ? '预览' : '未知'
            return <div className="node-entry" key={item.id}>
              <button type="button" className="node-entry__summary" aria-label={`查看 ${item.title} 组件详情`} title={preview || canEditGraph ? '查看组件详情；可拖动到画布' : '查看组件详情'} aria-expanded={componentDetail?.id === item.id} aria-controls="workflow-component-detail" draggable={preview || canEditGraph} onClick={(event) => { componentDetailTriggerRef.current = event.currentTarget; componentDetailFocusTarget.current = null; setComponentDetail(item) }} onDragStart={(event) => { event.dataTransfer.setData(workflowNodeMime, item.id); event.dataTransfer.effectAllowed = 'move' }}>
                <span className="node-entry__icon"><Icon name={item.icon} size={16} /></span><span className="node-entry__content"><strong title={item.title}>{item.title}</strong><span className="node-entry__summary-meta" title={item.category}><span className={`node-entry__availability node-entry__availability--${availability?.tone ?? 'unknown'}`} title={availability?.label ?? (preview ? '预览' : '待读')} aria-label={availability ? `执行能力：${availability.label}` : preview ? '预览' : '待读'}>{availabilityLabel}</span><small>{item.category}</small></span></span>
              </button>
              <button type="button" className="node-entry__add-button" aria-label={`${preview ? '添加到预览画布' : '添加到工作流'}：${item.title}`} title={preview ? '添加到预览画布' : canEditGraph ? '添加到工作流' : '当前工作流不可编辑'} disabled={!preview && !canEditGraph} onClick={() => addNode(item.id, undefined, true)}><Icon name="plus" size={15} /></button>
            </div>
          })}</div>
          {filteredComponents.length === 0 && <p className="node-library__empty">{search.trim() || componentCategory !== '全部类别'
            ? '没有匹配的组件'
            : componentScope === 'recent' ? '暂无最近使用'
                : componentScope === 'favorites' ? '暂无收藏'
                : '暂无组件'}</p>}
        </> : <div className="node-catalog-unavailable" role="status"><Icon name="server" size={19} /><strong>{localCatalogState.status === 'loading' || catalogState.status === 'loading' ? '正在读取组件目录' : '组件目录暂不可用'}</strong>{(localCatalogState.status === 'error' || catalogState.status === 'error' || localRuntimeState.status === 'error') && <p>{localRuntimeState.status === 'error' ? localRuntimeState.message : localCatalogState.status === 'error' ? localCatalogState.message : catalogState.status === 'error' ? catalogState.message : null}</p>}</div>}
      </aside>
        <main ref={componentDetailCanvasRef} className="canvas-column" id="workflow-canvas-panel" tabIndex={-1} aria-label="工作流画布">
        <div className="canvas-toolbar">
          <div><strong>{editorMode === 'guided' ? '工作流引导' : '工作流画布'}</strong></div>
          <div className="canvas-toolbar__actions">
            <div className="workflow-mode-switch" role="group" aria-label="工作流编辑模式">
              <button type="button" className={editorMode === 'guided' ? 'active' : ''} aria-pressed={editorMode === 'guided'} onClick={() => setEditorMode('guided')} title="按当前节点依赖关系组织任务清单">引导模式</button>
              <button type="button" className={editorMode === 'canvas' ? 'active' : ''} aria-pressed={editorMode === 'canvas'} onClick={() => setEditorMode('canvas')}>自由画布</button>
            </div>
            <span>{preview ? `${nodes.length} 个节点 · ${edges.length} 条连线` : workflowState.status === 'ready' ? `${nodes.length} 个节点 · ${edges.length} 条连线` : workflowState.status === 'loading' ? '正在读取画布' : '等待工作流服务'}</span>
            <div className="canvas-toolbar__panel-toggles" role="group" aria-label="画布视图与侧栏">
              <button className={libraryOpen ? 'active' : ''} type="button" aria-pressed={libraryOpen} aria-label={libraryOpen ? '收起组件目录' : '展开组件目录'} aria-controls="workflow-component-panel" title={libraryOpen ? '收起组件目录' : '展开组件目录'} onClick={() => setLibraryOpen((open) => !open)}><Icon name="panel" size={15} /><span>组件</span></button>
              <button className={miniMapOpen ? 'active' : ''} type="button" disabled={nodes.length === 0} aria-pressed={miniMapOpen} aria-label={miniMapOpen ? '隐藏缩略图' : '显示缩略图'} title={nodes.length === 0 ? '有节点后可显示缩略图' : miniMapOpen ? '隐藏缩略图' : '显示缩略图'} onClick={() => setMiniMapOpen((open) => !open)}><Icon name="map" size={15} /><span>缩略图</span></button>
              <button className={(inspectorOpen ? 'active ' : '') + 'canvas-toolbar__panel-toggle--inspector'} type="button" aria-pressed={inspectorOpen} aria-label={inspectorOpen ? '收起属性检查' : '展开属性检查'} aria-controls="workflow-inspector-panel" title={inspectorOpen ? '收起属性检查' : '展开属性检查'} onClick={toggleInspector}><Icon name="panel" size={15} className="canvas-toolbar__panel-icon--right" /><span>检查</span></button>
            </div>
          </div>
        </div>
        <div className="workflow-guided" aria-label="工作流引导任务清单">
          <header className="workflow-guided__header"><div><h2>当前工作流任务</h2></div><span className="workflow-guided__count">{nodes.length} 个节点 · {edges.length} 条依赖</span></header>
          {!preview && workflowState.status === 'loading' && <div className="workflow-guided__state" role="status">正在读取…</div>}
          {!preview && workflowState.status === 'error' && <div className="workflow-guided__state is-error" role="alert">读取失败：{workflowState.message}</div>}
          {!preview && workflowState.status === 'idle' && <div className="workflow-guided__state" role="status">尚未选择工作流</div>}
          {(preview || workflowState.status === 'ready') && nodes.length === 0 && <div className="workflow-guided__state" role="status"><strong>还没有节点</strong></div>}
          {(preview || workflowState.status === 'ready') && guidedLayers.map((layer) => <section className={'workflow-guided__layer' + (layer.unresolved ? ' is-unresolved' : '')} key={layer.index}>
            <header><div><span>依赖层 {String(layer.index + 1).padStart(2, '0')}</span><strong>{layer.nodes.length} 个节点</strong></div>{layer.unresolved && <small>依赖未完全解析</small>}</header>
            {layer.unresolved && <p className="workflow-guided__layer-warning">包含循环依赖，请在自由画布检查连线。</p>}
            <div className="workflow-guided__nodes">{layer.nodes.map((node) => {
              const upstream = edges.filter((edge) => edge.target === node.id).map((edge) => nodes.find((item) => item.id === edge.source)?.data.title).filter((title): title is string => Boolean(title))
              const downstream = edges.filter((edge) => edge.source === node.id).map((edge) => nodes.find((item) => item.id === edge.target)?.data.title).filter((title): title is string => Boolean(title))
              return <button type="button" key={node.id} className={'workflow-guided-node' + (selectedId === node.id ? ' is-selected' : '')} aria-pressed={selectedId === node.id} onClick={() => setSelectedId(node.id)}>
                <span className="workflow-guided-node__category">{node.data.category}</span><strong>{node.data.title}</strong>
                <span className="workflow-guided-node__links"><span>上游：{upstream.length ? upstream.join('、') : '无'}</span><span>下游：{downstream.length ? downstream.join('、') : '无'}</span></span>
              </button>
            })}</div>
          </section>)}
        </div>
        <div className="workflow-canvas-surface">
          <ReactFlowProvider><WorkflowCanvas owner={owner} editable={canEditGraph} allowPreviewAdd={preview} workflowLoaded={preview || workflowState.status === 'ready'} miniMapOpen={miniMapOpen} nodes={nodes} edges={edges} validationFocus={validationFocus} pendingNodeRevealId={pendingNodeRevealId} onNodeRevealHandled={handleNodeRevealHandled} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onConnectEnd={onConnectEnd} onNodeDragStart={handleNodeDragStart} onAddNode={addNode} onSelectNode={setSelectedId} onAutoLayout={handleAutoLayout} /></ReactFlowProvider>
        </div>
        <section className="editor-dock" aria-label="当前工作流运行面板">
          <div className="editor-dock__bar">
            <div className="editor-dock__tabs" role="tablist" aria-label="运行面板内容">
              {workflowDockTabs.map(({ id, label }) => <button type="button" role="tab" id={`workflow-dock-tab-${id}`} aria-controls="workflow-dock-panel" aria-selected={tab === label} className={tab === label ? 'active editor-dock__tab' : 'editor-dock__tab'} key={id} onClick={() => { setTab(label); setDockExpanded(true) }}>{label}</button>)}
            </div>
            {!dockExpanded && <span className="editor-dock__compact-state"><Icon name={panelCopy.icon} size={14} />{panelCopy.title}</span>}
            <button type="button" className="editor-dock__toggle" aria-label={dockExpanded ? '收起运行面板' : '展开运行面板'} aria-expanded={dockExpanded} aria-controls="workflow-dock-panel" title={dockExpanded ? '收起运行面板' : '展开运行面板'} onClick={() => setDockExpanded((expanded) => !expanded)}><span aria-hidden="true">{dockExpanded ? '⌄' : '⌃'}</span></button>
          </div>
          <div className="editor-dock__content" id="workflow-dock-panel" role="tabpanel" aria-labelledby={`workflow-dock-tab-${activeDockTab.id}`} hidden={!dockExpanded}>
            <div className={'editor-dock__message' + (actionError ? ' is-error' : '')} role={actionError ? 'alert' : 'status'}><span className="editor-dock__icon"><Icon name={panelCopy.icon} size={17} /></span><div><strong>{panelCopy.title}</strong>{panelCopy.detail ? <p>{panelCopy.detail}</p> : null}</div></div>
            {!preview && tab === '校验' && validation && validation.issues.length > 0 && <ul className="workflow-validation-issues">{validation.issues.map((issue, index) => {
              const targetNode = issue.node_id ? nodes.find((node) => node.id === issue.node_id) : undefined
              const targetEdge = !targetNode && issue.edge_id ? edges.find((edge) => edge.id === issue.edge_id) : undefined
              const targetKind = targetNode ? 'node' : targetEdge ? 'edge' : null
              const targetId = targetNode?.id ?? targetEdge?.id ?? null
              const edgeSource = targetEdge ? nodes.find((node) => node.id === targetEdge.source)?.data.title : undefined
              const edgeTarget = targetEdge ? nodes.find((node) => node.id === targetEdge.target)?.data.title : undefined
              const location = targetNode ? `节点 · ${targetNode.data.title}`
                : targetEdge ? `连线 · ${edgeSource ?? '未知节点'} → ${edgeTarget ?? '未知节点'}`
                  : issue.node_id ? '关联节点已不在当前画布'
                    : issue.edge_id ? '关联连线已不在当前画布' : '未关联节点或连线'
              const severityLabel = issue.severity === 'blocker' ? '阻断'
                : issue.severity === 'warning' ? '警告'
                  : issue.severity === 'info' ? '提示' : '级别未提供'
              return <li key={`${issue.code}-${issue.node_id ?? issue.edge_id ?? index}`}>
                <button type="button" className="workflow-validation-issue" disabled={!targetKind || !targetId} title={issue.code} onClick={() => targetKind && targetId && locateValidationIssue(targetKind, targetId)}>
                  <span className={`workflow-validation-issue__severity workflow-validation-issue__severity--${issue.severity ?? 'unknown'}`}><Icon name="shield" size={12} />{severityLabel}</span>
                  <strong className="workflow-validation-issue__title">{issue.title ?? issue.message}</strong>
                  <span className="workflow-validation-issue__action">{targetKind ? `定位${targetKind === 'node' ? '节点' : '连线'} →` : '无法定位'}</span>
                  <small className="workflow-validation-issue__location">{issue.scope === 'structure' ? '图结构' : '组件契约'} · {location}</small>
                  <span className="workflow-validation-issue__details">
                    {(issue.reason || issue.message) && <span><b>原因</b><span>{issue.reason ?? issue.message}</span></span>}
                    {issue.impact && <span><b>影响</b><span>{issue.impact}</span></span>}
                    {issue.guidance && <span><b>建议</b><span>{issue.guidance}</span></span>}
                  </span>
                </button>
              </li>
            })}</ul>}
            {!preview && tab === '校验' && validation && validation.execution_blockers.length > 0 && <p className="workflow-validation-limit">{validation.execution_blockers.length} 项运行阻断</p>}
            {!preview && tab === '校验' && workflowState.status === 'ready' && nodes.length > 0 && <section className="workflow-run-targets" aria-labelledby="workflow-run-targets-heading">
              <div><h3 id="workflow-run-targets-heading">输出目标</h3></div>
              <div className="workflow-run-targets__list">{nodes.map((node) => <label key={node.id}>
                <input type="checkbox" checked={activeRunTargets.includes(node.id)} onChange={(event) => {
                  setRunTargetsTouched(true)
                  setSelectedRunTargets((current) => event.target.checked
                    ? [...new Set([...current, node.id])]
                    : current.filter((id) => id !== node.id))
                }} disabled={!canEditGraph || runBusy} />
                <span><strong>{node.data.title}</strong><small>{node.data.output_ports?.map((port) => port.label).join('、') || node.data.component_id || '未登记组件'}{defaultRunTargets.includes(node.id) ? ' · 当前末端' : ''}</small></span>
              </label>)}</div>
              {runBlocker && <p className="workflow-run-targets__status" role="status">{runBlocker}</p>}
              {runClosureHasExecutor && missingCsvArtifactNodeIds.length === 0 && localRuntimeState.status === 'ready' && <p className="workflow-run-targets__status" role="status">依赖闭包 {runClosureIds.size} 个节点</p>}
              {runClosureHasExecutor && nodes.some((node) => runClosureIds.has(node.id) && node.data.component_id && !executableNodeIds.has(node.data.component_id)) && <p className="workflow-run-targets__warning">含无执行端组件，相关下游会阻断</p>}
            </section>}
            {!preview && tab === '运行历史' && <section className="workflow-run-history" aria-label="当前工作流本机运行历史">
              {runHistory.length > 0 && <ul>{runHistory.map((run) => <li key={run.run_id}><button type="button" className={runDetail?.run_id === run.run_id ? 'active' : ''} onClick={() => void handleSelectLocalRun(run.run_id)}><strong>{runStatusLabel(run.status)}</strong><code>{run.run_id}</code><small>{run.created_at ? dateTime(run.created_at) : '时间未提供'} · 目标 {run.target_node_ids.length} 个</small></button></li>}</ul>}
              {runDetail && <div className="workflow-run-history__detail">
                <div><strong>{runStatusLabel(runDetail.status)}</strong><code>计划 SHA-256 · {runDetail.plan_hash}</code></div>
                <p>目标：{runDetail.target_node_ids.map((id) => nodes.find((node) => node.id === id)?.data.title ?? id).join('、')}</p>
                <section className="workflow-run-history__steps" aria-label="本次运行的节点执行过程">
                  <div className="workflow-run-history__steps-heading"><strong>执行步骤</strong><small>{runDetail.execution_plan.nodes.length} 个计划节点 · {runDetail.node_runs.length} 条节点状态记录</small></div>
                  {runDetail.execution_plan.nodes.length > 0 ? <ol>{runDetail.execution_plan.nodes.map((step, index) => {
                    // A missing node record is left explicitly unrecorded; the UI never infers success or a pending state.
                    const nodeRun = runDetail.node_runs.find((item) => item.node_id === step.id)
                    const graphNode = nodes.find((node) => node.id === step.id && node.data.component_id === step.component_id)
                    const title = graphNode?.data.title ?? step.component_id
                    const artifactCount = nodeRun ? collectArtifactHandles(nodeRun.output).length : 0
                    const statusLabel = nodeRun ? runStatusLabel(nodeRun.status) : '无节点状态记录'
                    return <li key={step.id}>
                      <button type="button" className={'workflow-run-history__step' + (selectedId === step.id ? ' is-selected' : '')} disabled={!graphNode} title={graphNode ? '在右侧属性面板查看此节点' : '此步骤不在当前画布中，只能查看历史记录'} aria-label={`${title}，${statusLabel}${artifactCount ? `，${artifactCount} 项产物` : ''}`} onClick={() => {
                        if (!graphNode) return
                        setSelectedId(step.id)
                        setNodes((current) => current.map((node) => ({ ...node, selected: node.id === step.id })))
                        setInspectorOverride(true)
                      }}>
                        <span className="workflow-run-history__step-number" aria-hidden="true">{index + 1}</span>
                        <span className="workflow-run-history__step-copy"><strong>{title}</strong><small><code>{step.component_id}</code> · 节点 {step.id}{artifactCount ? ` · ${artifactCount} 项产物` : ''}{nodeRun?.error_code ? ` · ${nodeRun.error_code}` : ''}</small></span>
                        <span className={`workflow-run-history__step-status workflow-run-history__step-status--${workflowNodeRunTone(nodeRun?.status)}`}>{statusLabel}</span>
                      </button>
                    </li>
                  })}</ol> : <p>冻结执行计划没有可显示的节点。</p>}
                </section>
                {runDetail.recovered_from_run_id && <p className="workflow-run-history__recovery-note">恢复来源：<code>{runDetail.recovered_from_run_id}</code> · 已复用 {runDetail.node_runs.filter((nodeRun) => nodeRun.status === 'RESTORED').length} 个节点结果。</p>}
                {runDetail.error_code && <WorkflowRunErrorNotice code={runDetail.error_code} className="workflow-run-error--history" />}
                {runDetail.status === 'failed' && runDetail.error_code === 'LOCAL_WORKER_RESTARTED' && <>
                  <p className="workflow-run-history__recovery-note">本机 Runtime 重启中断</p>
                  <button type="button" className="button secondary" onClick={() => void handleRecoverLocalRun()} disabled={runRecoveryBusy}>{runRecoveryBusy ? '正在提交恢复…' : '恢复本机运行'}</button>
                </>}
                {runRecoveryNotice && <p className="workflow-run-history__recovery-note" role="status">{runRecoveryNotice}</p>}
                {runRecoveryError && <p className="workflow-run-history__recovery-note workflow-run-history__recovery-note--error" role="alert">{runRecoveryError}</p>}
                {runBusy && <button type="button" className="button secondary" onClick={() => void handleCancelLocalRun()} disabled={runCancelBusy}>{runCancelBusy ? '正在取消…' : '取消本机运行'}</button>}
              </div>}
            </section>}
            {!preview && tab === '日志' && runDetail?.events.length ? <section className="workflow-run-events" aria-label="本机运行事件">
              <ol>{runDetail.events.map((event) => <li key={event.sequence}><time>{dateTime(event.occurred_at)}</time><strong>{runStatusLabel(event.status)}</strong><span>{event.node_id ? nodes.find((node) => node.id === event.node_id)?.data.title ?? event.node_id : '工作流'}</span>{event.error_code && <WorkflowRunErrorNotice code={event.error_code} className="workflow-run-error--event" />}</li>)}</ol>
            </section> : null}
            {!preview && tab === '产物' && runDetail ? <section className="workflow-run-artifacts" aria-label="本机运行产物">
              <>
                {runDetail.execution_plan.nodes.filter((item) => item.component_id === 'ict.data.csv_artifact_source').map((item) => <article key={`source-${item.id}`}><span className="kicker">本机输入 · {nodes.find((node) => node.id === item.id)?.data.title ?? item.id}</span><strong>CSV ArtifactHandle</strong><code>{String(item.parameters.artifact_id ?? '未提供')}</code></article>)}
                {runDetail.execution_plan.nodes.filter((item) => item.component_id === 'ict.data.csv_folder_source').map((item) => {
                  const manifest = parseCsvFolderManifest(item.parameters.files_json)
                  return <article key={`folder-source-${item.id}`}><span className="kicker">本机输入 · {nodes.find((node) => node.id === item.id)?.data.title ?? item.id}</span><strong>{manifest ? `${manifest.folder_name} · ${manifest.files.length} 个 CSV` : 'CSV 文件夹未配置'}</strong>{manifest && manifest.ignored_file_count > 0 && <p>忽略非 CSV {manifest.ignored_file_count} 个</p>}{manifest && <details><summary>查看目录文件清单</summary><ul>{manifest.files.slice(0, 100).map((file) => <li key={`${file.relative_path}-${file.artifact_id}`}><code>{file.relative_path}</code><small>SHA-256 · {file.sha256}</small></li>)}</ul>{manifest.files.length > 100 && <small>共 {manifest.files.length} 个文件，清单仅展示前 100 个。</small>}</details>}</article>
                })}
                {runDetail.execution_plan.nodes.filter((item) => item.component_id === 'ict.data.csv_manifest_preflight').map((item) => <article key={`input-${item.id}`}><span className="kicker">本机输入 · {nodes.find((node) => node.id === item.id)?.data.title ?? item.id}</span><strong>CSV 产物 ID</strong><code>{String(item.parameters.artifact_id ?? '未提供')}</code></article>)}
                {runDetail.node_runs.flatMap((nodeRun) => collectArtifactHandles(nodeRun.output).map((artifact) => <article key={artifact.artifact_id}><span className="kicker">节点产物 · {nodes.find((node) => node.id === nodeRun.node_id)?.data.title ?? nodeRun.node_id}</span><strong>{isCsvPreflightComponent(nodeRun.component_id) ? '结构预检报告 · 非科研结果' : isCsvDescriptiveSummaryComponent(nodeRun.component_id) ? '探索性描述统计 · 非科研结论' : isCsvFolderQualityComponent(nodeRun.component_id) ? 'CSV 文件夹质量报告 · 非科研结果' : artifact.file_name || '运行产物'}</strong><code>{artifact.artifact_id}</code><small>SHA-256 · {artifact.sha256}</small><p>{artifact.provenance} · {artifact.authorization_status} · {artifact.size_bytes} 字节</p></article>))}
                {csvReportHandle && <article className="workflow-run-report">
                  <div className="workflow-run-report__heading"><div><span className="kicker">本机报告内容</span><strong>CSV 结构预检摘要</strong></div><span className="workflow-run-report__label">非科研结果</span></div>
                  {csvReportState.status === 'loading' && <p role="status">正在读取本机报告…</p>}
                  {csvReportState.status === 'error' && (csvReportState.code
                    ? <div role="alert"><WorkflowRunErrorNotice code={csvReportState.code} className="workflow-run-error--report" /></div>
                    : <p role="alert">{csvReportState.message}</p>)}
                  {csvReportState.status === 'ready' && <>
                    <dl className="workflow-run-report__summary">
                      <div><dt>结构状态</dt><dd>{csvReportState.data.status === 'success' ? '通过' : csvReportState.data.status === 'warning' ? '有提示' : '存在阻断项'}</dd></div>
                      <div><dt>数据行数</dt><dd>{csvReportState.data.row_count}</dd></div>
                      <div><dt>标签类别</dt><dd>{csvReportState.data.label_category_count}</dd></div>
                      <div><dt>问题数量</dt><dd>{csvReportState.data.issues.length}</dd></div>
                    </dl>
                    <div className="workflow-run-report__section"><strong>字段</strong><p>{csvReportState.data.columns.join('、') || '未提供'}</p></div>
                    <div className="workflow-run-report__section"><strong>数据拆分</strong><p>{Object.entries(csvReportState.data.split_counts).map(([name, count]) => `${name} ${count}`).join(' · ') || '未提供'}</p></div>
                    {csvReportState.data.issues.length > 0 && <div className="workflow-run-report__section"><strong>检查问题</strong><ul>{csvReportState.data.issues.slice(0, 12).map((issue, index) => <li key={`${issue.code}-${index}`}><b>{issue.severity === 'blocker' ? '阻断' : '提示'} · {issue.code}</b><span>{issue.message}（{issue.count} 项{issue.field ? ` · 字段 ${issue.field}` : ''}）</span>{issue.guidance && <small>{issue.guidance}</small>}</li>)}</ul>{csvReportState.data.issues.length > 12 && <small>另有 {csvReportState.data.issues.length - 12} 项未展开。</small>}</div>}
                  </>}
                </article>}
                {csvDescriptiveSummaryHandle && <article className="workflow-run-report">
                  <div className="workflow-run-report__heading"><div><span className="kicker">本机报告内容</span><strong>CSV 描述统计摘要</strong></div><span className="workflow-run-report__label">非科研结论</span></div>
                  {csvDescriptiveSummaryState.status === 'loading' && <p role="status">正在读取本机描述统计报告…</p>}
                  {csvDescriptiveSummaryState.status === 'error' && (csvDescriptiveSummaryState.code
                    ? <div role="alert"><WorkflowRunErrorNotice code={csvDescriptiveSummaryState.code} className="workflow-run-error--report" /></div>
                    : <p role="alert">{csvDescriptiveSummaryState.message}</p>)}
                  {csvDescriptiveSummaryState.status === 'ready' && <>
                    <dl className="workflow-run-report__summary">
                      <div><dt>数据行数</dt><dd>{csvDescriptiveSummaryState.data.row_count.toLocaleString('zh-CN')}</dd></div>
                      <div><dt>字段数量</dt><dd>{csvDescriptiveSummaryState.data.column_count.toLocaleString('zh-CN')}</dd></div>
                      <div><dt>摘要类型</dt><dd>探索性描述</dd></div>
                      <div><dt>方法版本</dt><dd>{csvDescriptiveSummaryState.data.summary_method}</dd></div>
                    </dl>
                    <div className="workflow-run-report__section"><strong>缺失值口径</strong><p>{csvDescriptiveSummaryState.data.missing_definition}</p></div>
                    <div className="workflow-run-summary-table-wrap">
                      <table className="workflow-run-summary-table" aria-label="CSV 字段描述统计">
                        <thead><tr><th>字段</th><th>类型</th><th>缺失</th><th>摘要</th></tr></thead>
                        <tbody>{csvDescriptiveSummaryState.data.columns.slice(0, 100).map((column) => {
                          const summary = column.kind === 'numeric' && column.numeric_summary
                            ? `最小 ${column.numeric_summary.minimum.toLocaleString('zh-CN', { maximumFractionDigits: 4 })} · 均值 ${column.numeric_summary.mean.toLocaleString('zh-CN', { maximumFractionDigits: 4 })} · 最大 ${column.numeric_summary.maximum.toLocaleString('zh-CN', { maximumFractionDigits: 4 })}`
                            : column.kind === 'categorical' && column.category_summary
                              ? column.category_summary.truncated
                                ? '类别值过多或过长，已省略频数'
                                : column.category_summary.top_values.map((item) => `${item.value}（${item.count}）`).join('、') || '无非空取值'
                              : '全部为空'
                          return <tr key={column.name}><th scope="row">{column.name}</th><td>{column.kind === 'numeric' ? '数值' : column.kind === 'categorical' ? '类别 / 文本' : '全缺失'}</td><td>{(column.missing_rate * 100).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}% · {column.missing_count}</td><td>{summary}</td></tr>
                        })}</tbody>
                      </table>
                      {csvDescriptiveSummaryState.data.columns.length > 100 && <small>报告共 {csvDescriptiveSummaryState.data.columns.length} 个字段，页面展示前 100 个。</small>}
                    </div>
                    <div className="workflow-run-report__section"><strong>适用限制</strong><ul>{csvDescriptiveSummaryState.data.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></div>
                  </>}
                </article>}
                {csvFolderQualityHandle && <article className="workflow-run-report">
                  <div className="workflow-run-report__heading"><div><span className="kicker">本机文件夹运行报告</span><strong>CSV 逐文件质量检查</strong></div><span className="workflow-run-report__label">非科研结果</span></div>
                  {csvFolderQualityState.status === 'loading' && <p role="status">正在读取逐文件质量报告…</p>}
                  {csvFolderQualityState.status === 'error' && (csvFolderQualityState.code
                    ? <div role="alert"><WorkflowRunErrorNotice code={csvFolderQualityState.code} className="workflow-run-error--report" /></div>
                    : <p role="alert">{csvFolderQualityState.message}</p>)}
                  {csvFolderQualityState.status === 'ready' && <>
                    <dl className="workflow-run-report__summary">
                      <div><dt>文件夹</dt><dd>{csvFolderQualityState.data.collection.folder_name}</dd></div>
                      <div><dt>CSV 文件</dt><dd>{csvFolderQualityState.data.summary.file_count}</dd></div>
                      <div><dt>通过 / 警告</dt><dd>{csvFolderQualityState.data.summary.passed_count} / {csvFolderQualityState.data.summary.warning_count}</dd></div>
                      <div><dt>阻断文件</dt><dd>{csvFolderQualityState.data.summary.blocked_count}</dd></div>
                    </dl>
                    <div className="workflow-run-report__section"><strong>整体检查状态：{csvFolderQualityState.data.summary.status === 'passed' ? '通过' : csvFolderQualityState.data.summary.status === 'warning' ? '有警告' : '存在阻断项'}</strong><p>规则版本 {csvFolderQualityState.data.rules_version} · 缺失率阈值 {(csvFolderQualityState.data.rules.max_missing_rate * 100).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}% · 忽略非 CSV 文件 {csvFolderQualityState.data.collection.ignored_file_count} 个</p><small>文件集合 SHA-256 · {csvFolderQualityState.data.collection.collection_sha256}</small></div>
                    <div className="workflow-run-summary-table-wrap">
                      <table className="workflow-run-summary-table" aria-label="CSV 文件夹逐文件质量检查结果">
                        <thead><tr><th>相对路径</th><th>状态</th><th>行 × 列</th><th>缺失单元格</th><th>重复键</th><th>问题</th></tr></thead>
                        <tbody>{csvFolderQualityState.data.files.slice(0, 100).map((file) => {
                          const missingCellCount = file.missing_counts.reduce((sum, item) => sum + item.count, 0)
                          const statusLabel = file.status === 'passed' ? '通过' : file.status === 'warning' ? '警告' : '阻断'
                          return <tr key={`${file.relative_path}-${file.artifact_id}`}>
                            <th scope="row">{file.relative_path}<small>SHA-256 · {file.sha256}</small></th>
                            <td>{statusLabel}</td><td>{file.row_count.toLocaleString('zh-CN')} × {file.column_count}</td>
                            <td>{missingCellCount.toLocaleString('zh-CN')}</td><td>{file.duplicate_key_count.toLocaleString('zh-CN')}</td>
                            <td>{file.issues.length ? <details><summary>{file.issues.length} 项</summary><ul>{file.issues.map((issue, index) => <li key={`${issue.code}-${index}`}><b>{issue.severity === 'blocker' ? '阻断' : '警告'} · {issue.code}</b><span>{issue.count} 项{issue.fields.length ? ` · ${issue.fields.join('、')}` : ''}</span></li>)}</ul></details> : '无'}</td>
                          </tr>
                        })}</tbody>
                      </table>
                      {csvFolderQualityState.data.files.length > 100 && <small>共 {csvFolderQualityState.data.files.length} 个 CSV，页面展示前 100 个。</small>}
                    </div>
                  </>}
                </article>}
                {crossrefReportHandle && <article className="workflow-run-report">
                  <div className="workflow-run-report__heading"><div><span className="kicker">公开来源元数据</span><strong>Crossref DOI 书目信息</strong></div><span className="workflow-run-report__label">非科研结果</span></div>
                  {crossrefReportState.status === 'loading' && <p role="status">正在读取本机文献元数据…</p>}
                  {crossrefReportState.status === 'error' && (crossrefReportState.code
                    ? <div role="alert"><WorkflowRunErrorNotice code={crossrefReportState.code} className="workflow-run-error--report" /></div>
                    : <p role="alert">{crossrefReportState.message}</p>)}
                  {crossrefReportState.status === 'ready' && <>
                    <dl className="workflow-run-report__summary">
                      <div><dt>DOI</dt><dd>{crossrefReportState.data.doi}</dd></div>
                      <div><dt>题名</dt><dd>{crossrefReportState.data.title ?? '未提供'}</dd></div>
                      <div><dt>期刊 / 载体</dt><dd>{crossrefReportState.data.container_title ?? '未提供'}</dd></div>
                      <div><dt>出版日期</dt><dd>{crossrefReportState.data.published_date ?? '未提供'}</dd></div>
                    </dl>
                    <div className="workflow-run-report__section"><strong>作者</strong><p>{crossrefReportState.data.authors.map((author) => author.name).join('、') || '未提供'}</p></div>
                    <div className="workflow-run-report__section"><strong>来源与抓取时间</strong><p>{crossrefReportState.data.source_name} · {dateTime(crossrefReportState.data.retrieved_at)}</p><small>{crossrefReportState.data.source_url}</small></div>
                    {crossrefReportState.data.verification_note && <p className="workflow-run-report__disclaimer">{crossrefReportState.data.verification_note}</p>}
                  </>}
                </article>}
                {!runDetail.node_runs.some((item) => collectArtifactHandles(item.output).length > 0) && !runDetail.execution_plan.nodes.some((item) => isCsvPreflightComponent(item.component_id) || isCsvDescriptiveSummaryComponent(item.component_id) || isCsvFolderQualityComponent(item.component_id) || item.component_id === 'ict.data.csv_artifact_source' || item.component_id === 'ict.data.csv_folder_source' || item.component_id === 'ict.paper.crossref_metadata') && <p>暂无产物</p>}
              </>
            </section> : null}
            {preview && tab === '运行历史' && <button type="button" className="editor-dock__preview-link" onClick={() => { window.location.hash = '__preview/workflow-run-detail' }}>查看运行详情布局</button>}
          </div>
        </section>
      </main>
      <aside className="inspector" id="workflow-inspector-panel" aria-label="工作流属性检查">
        <div className="inspector-tabs"><button className={!selectedNode ? 'active' : ''} onClick={() => setSelectedId(null)}>工作流概览</button><button className={selectedNode ? 'active' : ''} disabled={!selectedNode}>组件属性</button><button disabled title="运行配置服务尚未接入">运行配置</button></div>
        {selectedNode ? <section className="inspector-node">
          <div className="inspector-node__meta"><span className="kicker">{selectedNode.data.category}</span><span className="inspector-node__state">{preview ? '预览草稿 · 未运行' : selectedNode.data.run_status ? runStatusLabel(selectedNode.data.run_status) : selectedNode.data.execution_available ? selectedNode.data.execution_target === 'network' ? '网络执行器已接入' : '本机执行器已安装' : selectedNode.data.executor_binding ? '执行器未在本机安装' : '草稿节点 · 未运行'}</span></div>
          <h2>组件属性</h2>
          <label>节点名称<input value={selectedNode.data.title} onFocus={(event) => beginWorkflowTextEdit(`node-title:${selectedNode.id}`, event.currentTarget.value)} onChange={(event) => updateSelectedTitle(event.target.value)} onBlur={(event) => finishWorkflowTextEdit(`node-title:${selectedNode.id}`, event.currentTarget.value)} disabled={!canEditGraph} /></label>
          {selectedNode.data.description && <section className="inspector-node__purpose"><h3>用途</h3><p>{selectedNode.data.description}</p></section>}
          {/* Layout fixtures have no registry contract; do not present missing port data as zero ports. */}
          {preview ? <div className="inspector-contract" role="status" aria-label="组件端口契约"><div className="inspector-contract__row"><span>端口契约</span><b>未加载</b></div></div> : <div className="inspector-contract" aria-label="组件输入端口">
            <div className="inspector-contract__row"><span>输入端口</span><b>{selectedNode.data.input_ports?.length ?? 0}</b></div>
            {(selectedNode.data.input_ports ?? []).map((port) => <div className="inspector-contract__row" key={`input-${port.id}`}><span>{port.label}</span><b>{port.data_type}</b></div>)}
          </div>}
          <section className="inspector-upstream" aria-label="上游连接">
            <div className="inspector-upstream__heading"><span>上游连接</span><b>{selectedUpstreamConnections.length}</b></div>
            {selectedUpstreamConnections.length > 0 ? selectedUpstreamConnections.map((edge) => {
              const sourceNode = nodes.find((node) => node.id === edge.source)
              const sourcePortId = edge.sourceHandle?.startsWith('out:') ? edge.sourceHandle.slice(4) : null
              const targetPortId = edge.targetHandle?.startsWith('in:') ? edge.targetHandle.slice(3) : null
              const sourcePort = sourceNode?.data.output_ports?.find((port) => port.id === sourcePortId)
              const targetPort = selectedNode.data.input_ports?.find((port) => port.id === targetPortId)
              const hasResolvedPortContract = Boolean(sourcePort && targetPort)
              return <article className="inspector-upstream__item" key={edge.id}>
                <strong>{sourceNode?.data.title ?? '来源节点不可用'}</strong>
                {preview ? <small>布局示意连线 · 节点端口契约未加载</small> : hasResolvedPortContract ? <>
                  <div className="inspector-upstream__route"><span>{sourcePort?.label}</span><span aria-hidden="true">→</span><span>{targetPort?.label}</span></div>
                  <small>{sourcePort?.data_type} → {targetPort?.data_type}</small>
                </> : <small>节点连线存在，端口契约未加载。</small>}
              </article>
            }) : <p className="inspector-upstream__empty">无上游连接</p>}
          </section>
          {selectedParameterEntries.length > 0 && <section className="inspector-node__parameters"><h3>参数配置</h3>{selectedParameterEntries.map(([key, property], index) => {
            const required = selectedNode.data.parameter_schema?.required.includes(key) ?? false
            const fieldId = `workflow-parameter-${encodeURIComponent(selectedNode.id)}-${index}`
            const value = String(selectedNode.data.parameters?.[key] ?? property.default)
            const currentLength = Array.from(value).length
            const defaultHint = property.default === '' ? '留空' : `“${property.default}”`
            const constraintHints = [
              property.minLength > 0 ? `最少 ${property.minLength} 个字符` : null,
              property.maxLength !== undefined ? `最多 ${property.maxLength} 个字符` : null,
            ].filter((hint): hint is string => hint !== null)
            const constraintHint = constraintHints.length > 0 ? constraintHints.join(' · ') : '可留空'
            const parameterError = required && value.length === 0
              ? '这是必填参数，请填写后再继续。'
              : currentLength > 0 && currentLength < property.minLength
                ? `至少输入 ${property.minLength} 个字符（当前 ${currentLength} 个）。`
                : property.maxLength !== undefined && currentLength > property.maxLength
                  ? `最多输入 ${property.maxLength} 个字符（当前 ${currentLength} 个）。`
                : ''
            const showParameterError = touchedParameterFields.has(fieldId) && Boolean(parameterError)
            const characterCountHint = property.maxLength !== undefined ? ` · ${currentLength}/${property.maxLength} 个字符` : ''
            const localCsvArtifactField = supportsLocalCsvImport(selectedNode.data.component_id) && key === 'artifact_id'
            const localCsvFolderField = supportsLocalCsvFolderImport(selectedNode.data.component_id) && key === 'files_json'
            const selectedFolder = localCsvFolderField ? parseCsvFolderManifest(value) : null
            return <label key={key}>{property.title}{required && <span aria-label="必填" title="该参数为必填项"> *</span>}
              {localCsvFolderField ? <div className="workflow-local-file-picker">
                <input id={fieldId} type="text" value={selectedFolder ? `${selectedFolder.folder_name} · ${selectedFolder.files.length} 个 CSV` : ''} readOnly aria-readonly="true" aria-describedby={`${fieldId}-help`} placeholder="尚未选择本机 CSV 文件夹" />
                <button type="button" className="button secondary" onClick={() => csvFolderInputRef.current?.click()} disabled={!canEditGraph || localRuntimeState.status !== 'ready' || artifactImportBusy}>{folderImportProgress ? `正在导入 ${folderImportProgress.completed}/${folderImportProgress.total}…` : selectedFolder ? '更换文件夹' : '选择 CSV 文件夹'}</button>
                <input ref={(element) => {
                  csvFolderInputRef.current = element
                  if (element) element.setAttribute('webkitdirectory', '')
                }} className="workflow-local-file-picker__input" type="file" multiple accept=".csv,text/csv" onChange={(event) => void handleImportCsvFolder(event)} aria-label="选择包含 CSV 数据的本机文件夹" />
                {folderImportProgress && <small role="status">已导入 {folderImportProgress.completed}/{folderImportProgress.total} 个文件；数据只写入本机。</small>}
                <small id={`${fieldId}-help`}>{selectedFolder ? `${selectedFolder.files.length} 个 CSV${selectedFolder.ignored_file_count ? ` · 跳过非 CSV ${selectedFolder.ignored_file_count}` : ''}` : property.description}</small>
              </div> : localCsvArtifactField ? <div className="workflow-local-file-picker">
                <input id={fieldId} type="text" value={value} readOnly aria-readonly="true" aria-describedby={`${fieldId}-help`} placeholder="尚未选择本机 CSV" />
                <button type="button" className="button secondary" onClick={() => csvFileInputRef.current?.click()} disabled={!canEditGraph || localRuntimeState.status !== 'ready' || artifactImportBusy}>{artifactImportBusy ? '正在导入…' : importedArtifact?.artifact_id === value ? importedArtifact.file_name : '选择本机 CSV'}</button>
                <input ref={csvFileInputRef} className="workflow-local-file-picker__input" type="file" accept=".csv,text/csv" onChange={(event) => void handleImportCsv(event)} aria-label="选择要导入本机的 CSV 文件" />
                <small id={`${fieldId}-help`}>{property.description}</small>
              </div> : <>
                <input id={fieldId} type="text" value={value} onFocus={(event) => beginWorkflowTextEdit(`parameter:${selectedNode.id}:${key}`, event.currentTarget.value)} onChange={(event) => updateSelectedParameter(key, limitWorkflowParameterValue(event.target.value, property.maxLength))} onBlur={(event) => { finishWorkflowTextEdit(`parameter:${selectedNode.id}:${key}`, event.currentTarget.value); setTouchedParameterFields((current) => current.has(fieldId) ? current : new Set(current).add(fieldId)) }} disabled={!canEditGraph} required={required} minLength={property.minLength > 0 ? property.minLength : undefined} aria-invalid={showParameterError || undefined} aria-describedby={showParameterError ? `${fieldId}-help ${fieldId}-error` : `${fieldId}-help`} />
                <small id={`${fieldId}-help`}>{property.description} · {constraintHint}{characterCountHint} · 默认值：{defaultHint}</small>
              </>}
              {showParameterError && <small id={`${fieldId}-error`} className="inspector-node__parameter-error" role="alert">{parameterError}</small>}
            </label>
          })}</section>}
          {!preview && <div className="inspector-contract" aria-label="组件输出端口">
            <div className="inspector-contract__row"><span>输出端口</span><b>{selectedNode.data.output_ports?.length ?? 0}</b></div>
            {(selectedNode.data.output_ports ?? []).map((port) => <div className="inspector-contract__row" key={`output-${port.id}`}><span>{port.label}</span><b>{port.data_type}</b></div>)}
          </div>}
          {selectedNode.data.executor_binding && <details className="inspector-advanced"><summary>执行器</summary><p>{selectedNode.data.executor_binding}</p></details>}
          <div className="inspector-node__records">
            <section><h3>最近运行</h3><p>{preview ? '—' : selectedNodeRun ? `${runStatusLabel(selectedNodeRun.status)} · ${runDetail?.run_id}` : '暂无'}</p>{selectedNodeRun?.error_code && <WorkflowRunErrorNotice code={selectedNodeRun.error_code} className="workflow-run-error--inspector" />}</section>
            {selectedNode.data.component_version && <section><h3>版本</h3><p>v{selectedNode.data.component_version}</p></section>}
          </div>
          <button className="remove-node-button" onClick={removeSelectedNode} disabled={!canEditGraph} aria-keyshortcuts="Delete Backspace" title="Delete / Backspace 删除">从画布移除</button>
        </section> : <section className="inspector-overview">
          <h2>{owner.name}</h2>
          {preview ? <dl><dt>节点</dt><dd>{nodes.length}</dd><dt>连线</dt><dd>{edges.length}</dd></dl> : workflowState.status === 'ready' ? <dl><dt>节点</dt><dd>{nodes.length}</dd><dt>连线</dt><dd>{edges.length}</dd><dt>草稿修订</dt><dd>{workflowState.data.revision}</dd><dt>版本</dt><dd>{currentVersion > 0 ? `v${currentVersion}` : '未创建'}</dd></dl> : <dl><dt>工作流</dt><dd>{workflowState.status === 'loading' ? '正在读取' : workflowState.status === 'error' ? '读取失败' : '未选择'}</dd><dt>组件目录</dt><dd>{catalogState.status === 'ready' ? catalogState.data.length : catalogState.status === 'loading' ? '正在读取' : catalogState.status === 'error' ? '读取失败' : '—'}</dd></dl>}
          {!preview && owner.type === 'project' && workflowId && workflowState.status === 'ready' && onDiscussWorkflow && <button type="button" className="inspector-overview__agent-action" disabled={isDirty} title={isDirty ? '先保存当前工作流草稿，避免离开时丢失更改' : '在 Agent 对话中临时引用当前项目和工作流'} onClick={() => onDiscussWorkflow({ id: owner.id, name: owner.name }, { id: workflowId, name: workflowName.trim() || workflowState.data.name })}><Icon name="agent" size={15} />在 Agent 对话中引用此工作流<Icon name="arrow" size={14} /></button>}
        </section>}
      </aside>
      {componentDetail && <aside className="component-detail-drawer" id="workflow-component-detail" role="dialog" aria-modal="false" aria-labelledby="component-detail-title" onKeyDown={(event) => { if (event.key === 'Escape') { event.preventDefault(); closeComponentDetail() } }}>
        <header className="component-detail-drawer__header"><div><span className="kicker">工作流组件</span><strong>组件详情</strong></div><div className="component-detail-drawer__actions"><button type="button" className={'component-detail-drawer__favorite' + (favoriteComponentSet.has(componentDetail.id) ? ' is-favorite' : '')} aria-label={favoriteComponentSet.has(componentDetail.id) ? `取消收藏 ${componentDetail.title}` : `收藏 ${componentDetail.title}`} aria-pressed={favoriteComponentSet.has(componentDetail.id)} title={favoriteComponentSet.has(componentDetail.id) ? '从收藏中移除' : '收藏此组件'} onClick={() => toggleComponentFavorite(componentDetail.id)}>{favoriteComponentSet.has(componentDetail.id) ? '★' : '☆'}</button><button ref={componentDetailCloseRef} type="button" aria-label="关闭组件详情" onClick={() => closeComponentDetail()}><Icon name="close" size={17} /></button></div></header>
        <div className="component-detail-drawer__body">
          <div className="component-detail__identity"><span className="component-detail__category">{componentDetail.category}</span><code>{componentDetail.definition?.component_id ?? componentDetail.id}</code><h2 id="component-detail-title">{componentDetail.title}</h2>
            <div className="component-detail__badges"><span>{componentDetail.definition ? `v${componentDetail.definition.version}` : '未载入契约'}</span>{componentDetail.definition && <span className={componentDetail.definition.execution_available ? 'is-available' : 'is-unavailable'}>{componentDetail.definition.execution_available ? (componentDetail.definition.execution_target === 'local' ? '本机可用' : componentDetail.definition.execution_target === 'network' ? '需网络' : '需平台') : '不可用'}</span>}</div>
          </div>
          {!componentDetail.definition ? <>
            <p className="component-detail__empty">契约未载入</p>
          </> : <>
            <section className="component-detail__section"><h3>输入端口 <span>{componentDetail.definition.inputs.length}</span></h3>{componentDetail.definition.inputs.length ? <ul className="component-detail__ports">{componentDetail.definition.inputs.map((port) => <li key={`input-${port.id}`}><strong>{port.label}</strong><code>{port.data_type}</code><small>{port.required ? '必需' : '可选'} · {port.multiple ? '支持多个' : '单值'}</small></li>)}</ul> : <p className="component-detail__empty">此组件未声明输入端口。</p>}</section>
            <section className="component-detail__section"><h3>输出端口 <span>{componentDetail.definition.outputs.length}</span></h3>{componentDetail.definition.outputs.length ? <ul className="component-detail__ports">{componentDetail.definition.outputs.map((port) => <li key={`output-${port.id}`}><strong>{port.label}</strong><code>{port.data_type}</code><small>{port.required ? '必需' : '可选'} · {port.multiple ? '支持多个' : '单值'}</small></li>)}</ul> : <p className="component-detail__empty">此组件未声明输出端口。</p>}</section>
            <section className="component-detail__section"><h3>参数说明 <span>{Object.keys(componentDetail.definition.parameter_schema.properties).length}</span></h3>{Object.entries(componentDetail.definition.parameter_schema.properties).length ? <ul className="component-detail__parameters">{Object.entries(componentDetail.definition.parameter_schema.properties).map(([key, property]) => <li key={key}><div><strong>{property.title}</strong>{componentDetail.definition?.parameter_schema.required.includes(key) && <span>必填</span>}</div><code>{key}</code><p>{property.description}</p><small>类型 {property.type} · 默认值 {property.default === '' ? '空字符串' : property.default}{property.minLength > 0 ? ` · 最少 ${property.minLength} 个字符` : ''}{property.maxLength !== undefined ? ` · 最多 ${property.maxLength} 个字符` : ''}</small></li>)}</ul> : <p className="component-detail__empty">当前契约未声明参数。</p>}</section>
            <section className="component-detail__section"><h3>依赖与运行环境</h3><dl className="component-detail__facts">
              <div><dt>执行位置</dt><dd>{componentExecutionTargetLabel(componentDetail.definition.execution_target)}</dd></div>
              <div><dt>执行器</dt><dd>{componentDetail.definition.executor_binding ?? '未绑定'}</dd></div>
              <div><dt>执行器版本</dt><dd>{componentDetail.definition.executor_version ?? '未绑定'}</dd></div>
              <div><dt>依赖版本</dt><dd>{componentDetail.definition.dependencies.length ? componentDetail.definition.dependencies.join('、') : '无额外依赖'}</dd></div>
            </dl></section>
            <section className="component-detail__section"><h3>权限与资源要求</h3><dl className="component-detail__facts">
              {Object.entries(componentDetail.definition.resource_limits).map(([key, value]) => <div key={key}><dt>{key === 'timeout_seconds' ? '运行时限' : key === 'cpu_millicores' ? 'CPU' : key === 'memory_mb' ? '内存' : key}</dt><dd>{formatComponentResourceLimit(key, value)}</dd></div>)}
              <div><dt>缓存策略</dt><dd>{componentDetail.definition.cache_policy === 'not_configured' ? '未配置' : componentDetail.definition.cache_policy}</dd></div>
              <div><dt>错误类型</dt><dd>{componentDetail.definition.error_types.length ? componentDetail.definition.error_types.join('、') : '未登记'}</dd></div>
            </dl><div className="component-detail__permissions"><strong>权限声明</strong>{componentDetail.definition.permissions.length ? componentDetail.definition.permissions.map((permission) => <code key={permission}>{permission}</code>) : <span>未声明</span>}</div></section>
          </>}
        </div>
        <footer className="component-detail-drawer__footer"><button type="button" className="button primary" disabled={!preview && !canEditGraph} title={!preview && !canEditGraph ? '当前工作流尚未加载或没有编辑权限' : undefined} onClick={() => { addNode(componentDetail.id, undefined, true); closeComponentDetail('canvas') }}>{preview ? '添加到预览画布' : '添加到工作流'}<Icon name="plus" size={15} /></button></footer>
      </aside>}
    </div>
    {versionHistoryOpen && <div className="workflow-version-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setVersionHistoryOpen(false) }}>
      <section className="workflow-version-dialog" role="dialog" aria-modal="true" aria-labelledby="workflow-version-title">
        <header className="workflow-version-dialog__header"><div><h2 id="workflow-version-title">版本历史</h2></div><button type="button" aria-label="关闭版本历史" onClick={() => setVersionHistoryOpen(false)}>×</button></header>
        <div className="workflow-version-dialog__body">
          {actionError && <p className="workflow-version-state is-error" role="alert">{actionError}</p>}
          <aside className="workflow-version-list" aria-label="历史版本列表">
            {versionHistoryState.status === 'loading' && <p className="workflow-version-state">正在读取版本历史…</p>}
            {versionHistoryState.status === 'error' && <p className="workflow-version-state is-error">{versionHistoryState.message}</p>}
            {versionHistoryState.status === 'ready' && versionHistoryState.data.length === 0 && <p className="workflow-version-state">此工作流还没有不可变版本。</p>}
            {versionHistoryState.status === 'ready' && versionHistoryState.data.map((version) => <button type="button" key={version.id} className={selectedVersionNumber === version.version ? 'workflow-version-item active' : 'workflow-version-item'} onClick={() => handleSelectVersion(version.version)}>
              <span><strong>版本 v{version.version}</strong>{version.version === currentVersion && <em>最新</em>}</span>{version.name !== null && <small>{version.name}</small>}<small>{dateTime(version.created_at)}</small><small>创建者：{version.created_by}</small>
            </button>)}
          </aside>
          <section className="workflow-version-detail" aria-label="所选版本详情">
            {selectedVersionState.status === 'loading' && <p className="workflow-version-state">正在读取所选快照…</p>}
            {selectedVersionState.status === 'error' && <p className="workflow-version-state is-error">{selectedVersionState.message}</p>}
            {selectedVersionState.status === 'ready' && <>
              <div className="workflow-version-detail__heading"><span className="kicker">不可变快照</span><h3>版本 v{selectedVersionState.data.version}</h3><p>创建于 {dateTime(selectedVersionState.data.created_at)}</p></div>
              <h4>{selectedVersionState.data.name ?? '未命名版本'}</h4>{selectedVersionState.data.description ? <p>{selectedVersionState.data.description}</p> : null}
              <dl><div><dt>节点</dt><dd>{selectedVersionState.data.graph.nodes.length}</dd></div><div><dt>连线</dt><dd>{selectedVersionState.data.graph.edges.length}</dd></div><div><dt>图协议</dt><dd>{selectedVersionState.data.schema_version}</dd></div><div><dt>创建者</dt><dd>{selectedVersionState.data.created_by}</dd></div></dl>
              <div className="workflow-version-hash"><span>内容 SHA-256</span><code>{selectedVersionState.data.content_hash}</code></div>
              {isDirty && <p className="workflow-version-warning is-caution">草稿有未保存修改</p>}
              <button type="button" className="workflow-version-restore" onClick={handleRestoreSelectedVersion} disabled={!canPersist || restoreBusy}>{restoreBusy ? '恢复中…' : `恢复 v${selectedVersionState.data.version} 到当前草稿`}</button>
            </>}
            {selectedVersionState.status === 'idle' && <p className="workflow-version-state">选择一个历史版本查看内容摘要。</p>}
          </section>
        </div>
      </section>
    </div>}
  </section>
}

function WorkflowCanvas({ owner, editable, allowPreviewAdd, workflowLoaded, miniMapOpen, nodes, edges, validationFocus, pendingNodeRevealId, onNodeRevealHandled, onNodesChange, onEdgesChange, onConnect, onConnectEnd, onNodeDragStart, onAddNode, onSelectNode, onAutoLayout }: {
  owner: WorkflowOwnerContext
  editable: boolean
  allowPreviewAdd: boolean
  workflowLoaded: boolean
  miniMapOpen: boolean
  validationFocus: WorkflowCanvasFocus
  pendingNodeRevealId: string | null
  onNodeRevealHandled: (nodeId: string) => void
  nodes: WorkflowNode[]; edges: Edge[]; onNodesChange: OnNodesChange<WorkflowNode>
  onEdgesChange: OnEdgesChange<Edge>; onConnect: (connection: Connection) => void
  onConnectEnd: (connectionState: FinalConnectionState) => void
  onNodeDragStart: () => void
  onAddNode: (componentId: string, position?: XYPosition) => void; onSelectNode: (id: string | null) => void
  onAutoLayout: (maxColumns: number) => void
}) {
  const { fitView, getViewport, screenToFlowPosition, setViewport } = useReactFlow<WorkflowNode, Edge>()
  const nodesInitialized = useNodesInitialized()
  const [desktopPreviewLayout, setDesktopPreviewLayout] = useState(() => window.matchMedia('(min-width: 761px)').matches)
  const [compactDesktopPreviewLayout, setCompactDesktopPreviewLayout] = useState(() => window.matchMedia('(min-width: 761px) and (max-width: 920px)').matches)
  const viewportFitOptions = desktopPreviewLayout
    ? compactDesktopPreviewLayout ? workflowCompactDesktopFitViewOptions : workflowDesktopFitViewOptions
    : workflowFitViewOptions
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const didUserManuallyMoveViewport = useRef(false)
  const didApplyInitialDesktopFit = useRef(false)
  const didFocusInitialMobileNode = useRef(false)
  const knownNodeIds = useRef(new Set(nodes.map((node) => node.id)))
  const addedNodeToFocus = useRef<string | null>(null)
  const appliedValidationFocusRequest = useRef(0)

  useEffect(() => {
    const desktopViewport = window.matchMedia('(min-width: 761px)')
    const compactDesktopViewport = window.matchMedia('(min-width: 761px) and (max-width: 920px)')
    const syncPreviewPorts = () => {
      setDesktopPreviewLayout(desktopViewport.matches)
      setCompactDesktopPreviewLayout(compactDesktopViewport.matches)
    }
    syncPreviewPorts()
    desktopViewport.addEventListener('change', syncPreviewPorts)
    compactDesktopViewport.addEventListener('change', syncPreviewPorts)
    return () => {
      desktopViewport.removeEventListener('change', syncPreviewPorts)
      compactDesktopViewport.removeEventListener('change', syncPreviewPorts)
    }
  }, [])

  useEffect(() => {
    if (!desktopPreviewLayout || !nodesInitialized || didApplyInitialDesktopFit.current) return

    let firstFrame = 0
    let secondFrame = 0
    firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => {
        didApplyInitialDesktopFit.current = true
        if (didUserManuallyMoveViewport.current) return
        void fitView({ ...viewportFitOptions, duration: 0 })
      })
    })

    return () => {
      cancelAnimationFrame(firstFrame)
      cancelAnimationFrame(secondFrame)
    }
  }, [desktopPreviewLayout, fitView, nodesInitialized, viewportFitOptions])

  // Keep this observer mounted across node measurements; nodesInitialized toggles whenever a node is added.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!desktopPreviewLayout || !canvas) return

    let previousSize = { width: canvas.clientWidth, height: canvas.clientHeight }
    let pendingFitFrame = 0
    const resizeObserver = new ResizeObserver(([entry]) => {
      if (!window.matchMedia('(min-width: 761px)').matches) return
      const nextSize = { width: entry.contentRect.width, height: entry.contentRect.height }
      const widthDelta = nextSize.width - previousSize.width
      const heightDelta = nextSize.height - previousSize.height
      previousSize = nextSize
      if (Math.abs(widthDelta) < 1 && Math.abs(heightDelta) < 1) return

      // Preserve manual zoom and pan while untouched graphs refit to the new canvas size.
      const viewport = getViewport()
      // Refit an untouched viewport after panel or window changes so narrow desktop layouts use their available canvas width.
      if (!didUserManuallyMoveViewport.current) {
        cancelAnimationFrame(pendingFitFrame)
        pendingFitFrame = requestAnimationFrame(() => {
          void fitView({ ...viewportFitOptions, duration: 0 })
        })
        return
      }

      void setViewport({
        x: viewport.x + widthDelta / 2,
        y: viewport.y + heightDelta / 2,
        zoom: viewport.zoom,
      }, { duration: 0 })
    })

    resizeObserver.observe(canvas)
    return () => {
      resizeObserver.disconnect()
      cancelAnimationFrame(pendingFitFrame)
    }
  }, [desktopPreviewLayout, fitView, getViewport, setViewport, viewportFitOptions])

  useEffect(() => {
    if (!pendingNodeRevealId) return
    if (!desktopPreviewLayout) {
      onNodeRevealHandled(pendingNodeRevealId)
      return
    }
    if (!nodes.some((node) => node.id === pendingNodeRevealId)) return
    if (!nodesInitialized) return

    const canvas = canvasRef.current
    const nodeElement = canvas?.querySelector<HTMLElement>(`.react-flow__node[data-id="${pendingNodeRevealId}"]`)
    if (!canvas || !nodeElement) return

    // Reveal only catalog-added nodes clipped by the canvas; preserve zoom and the graph's node coordinates.
    const pan = minimalViewportPanForNode(nodeElement.getBoundingClientRect(), canvas.getBoundingClientRect())
    if (pan.x !== 0 || pan.y !== 0) {
      const viewport = getViewport()
      void setViewport({ x: viewport.x + pan.x, y: viewport.y + pan.y, zoom: viewport.zoom }, { duration: 180 })
    }
    onNodeRevealHandled(pendingNodeRevealId)
  }, [desktopPreviewLayout, getViewport, nodes, nodesInitialized, onNodeRevealHandled, pendingNodeRevealId, setViewport])

  useEffect(() => {
    if (!validationFocus || !nodesInitialized || appliedValidationFocusRequest.current === validationFocus.request) return
    if (validationFocus.kind === 'node') {
      const target = nodes.find((node) => node.id === validationFocus.id)
      if (!target) return
      void fitView({ nodes: [target], padding: 0.2, minZoom: 0.55, maxZoom: 1, duration: 280 })
    } else {
      const edge = edges.find((item) => item.id === validationFocus.id)
      if (!edge) return
      const relatedNodes = nodes.filter((node) => node.id === edge.source || node.id === edge.target)
      if (relatedNodes.length === 0) return
      void fitView({ nodes: relatedNodes, padding: 0.2, minZoom: 0.35, maxZoom: 1, duration: 280 })
    }
    appliedValidationFocusRequest.current = validationFocus.request
  }, [edges, fitView, nodes, nodesInitialized, validationFocus])

  useEffect(() => {
    const addedSelectedNode = nodes.find((node) => node.selected && !knownNodeIds.current.has(node.id))
    knownNodeIds.current = new Set(nodes.map((node) => node.id))
    if (addedSelectedNode) addedNodeToFocus.current = addedSelectedNode.id
    if (!window.matchMedia('(max-width: 620px)').matches) {
      addedNodeToFocus.current = null
      return
    }
    if (!nodesInitialized || nodes.length === 0 || (didFocusInitialMobileNode.current && !addedNodeToFocus.current)) return
    // Wait for new node measurements, then reveal it once. Pan, zoom, and drag keep the user's viewport.
    const focusNode = addedNodeToFocus.current
      ? nodes.find((node) => node.id === addedNodeToFocus.current)
      : nodes.find((node) => node.selected) ?? nodes[0]
    if (!focusNode) {
      addedNodeToFocus.current = null
      return
    }
    void fitView({ nodes: [focusNode], padding: 0.16, minZoom: 0.75, maxZoom: 1, duration: 0 })
    didFocusInitialMobileNode.current = true
    addedNodeToFocus.current = null
  }, [fitView, nodes, nodesInitialized])

  const handleNodeClick = useCallback((node: WorkflowNode) => {
    onSelectNode(node.id)
    if (window.matchMedia('(max-width: 620px)').matches) {
      void fitView({ nodes: [node], padding: 0.16, minZoom: 0.75, maxZoom: 1, duration: 180 })
    }
  }, [fitView, onSelectNode])

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    if (!editable) return
    const componentId = event.dataTransfer.getData(workflowNodeMime)
    if (!componentId) return
    onAddNode(componentId, screenToFlowPosition({ x: event.clientX, y: event.clientY }))
  }
  const handleAutoLayout = () => {
    if (!editable || nodes.length < 2) return
    const canvasWidth = canvasRef.current?.clientWidth ?? 900
    const maxColumns = Math.max(3, Math.min(4, Math.floor((canvasWidth - 128) / 356)))
    onAutoLayout(maxColumns)
    // Let React Flow commit the new positions before measuring the graph for the viewport.
    requestAnimationFrame(() => void fitView({ ...viewportFitOptions, minZoom: 0.25, duration: 0 }))
  }
  // Desktop preview routes vertical dependencies through top/bottom handles; mobile keeps its existing side-port graph.
  const canvasNodes = useMemo(() => nodes.map((node) => ({
    ...node,
    data: allowPreviewAdd && !desktopPreviewLayout
      ? { ...node.data, previewTopTarget: false, previewBottomSource: false }
      : node.data,
    className: validationFocus?.kind === 'node' && validationFocus.id === node.id
      ? [node.className, 'workflow-validation-target'].filter(Boolean).join(' ')
      : node.className,
  })), [allowPreviewAdd, desktopPreviewLayout, nodes, validationFocus])
  const canvasEdges = useMemo(() => edges.map((edge) => ({
    ...edge,
    sourceHandle: allowPreviewAdd && !desktopPreviewLayout && desktopVerticalPreviewEdgeIds.has(edge.id) ? null : edge.sourceHandle,
    targetHandle: allowPreviewAdd && !desktopPreviewLayout && desktopVerticalPreviewEdgeIds.has(edge.id) ? null : edge.targetHandle,
    className: validationFocus?.kind === 'edge' && validationFocus.id === edge.id
      ? [edge.className, 'workflow-validation-target'].filter(Boolean).join(' ')
      : edge.className,
  })), [allowPreviewAdd, desktopPreviewLayout, edges, validationFocus])
  return <div ref={canvasRef} className="canvas" onDrop={editable ? handleDrop : undefined} onDragOver={editable ? (event) => event.preventDefault() : undefined} onPointerDownCapture={(event) => {
    if (event.target instanceof Element && event.target.closest('.react-flow')) didUserManuallyMoveViewport.current = true
  }} onWheelCapture={() => { didUserManuallyMoveViewport.current = true }}>
    <ReactFlow nodes={canvasNodes} edges={canvasEdges} nodeTypes={workflowNodeTypes} nodesDraggable={editable} nodesConnectable={editable} elementsSelectable={editable} isValidConnection={(connection) => editable && isWorkflowConnectionCompatible(connection, nodes)} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onConnectEnd={(_, connectionState) => onConnectEnd(connectionState)} onNodeDragStart={onNodeDragStart} onNodeClick={(_, node) => handleNodeClick(node)} onPaneClick={() => onSelectNode(null)} fitView fitViewOptions={viewportFitOptions} deleteKeyCode={null}>
      <Background variant={BackgroundVariant.Dots} gap={28} size={1} color="#9AA6B4" style={{ opacity: 0.6 }} />
      <Controls position="top-left" showInteractive={false} fitViewOptions={viewportFitOptions} />
      {desktopPreviewLayout && <Panel position="top-right" className="workflow-auto-layout-panel"><button type="button" className="workflow-auto-layout" disabled={!editable || nodes.length < 2} aria-label="按依赖关系自动布局节点" title={!editable ? '当前工作流不可编辑' : nodes.length < 2 ? '至少需要 2 个节点才可自动布局' : allowPreviewAdd ? '只调整当前预览画布，不会写入项目' : '按节点依赖关系重排；布局变更需保存工作流'} onClick={handleAutoLayout}><Icon name="layout" size={14} /><span>自动布局</span></button></Panel>}
      {nodes.length > 0 && miniMapOpen && <MiniMap className="editor-minimap" position="bottom-left" pannable zoomable nodeColor="#2563EB" maskColor="rgba(248, 250, 252, .72)" />}
    </ReactFlow>
        {nodes.length === 0 && <div className={'canvas-empty' + (workflowLoaded ? '' : ' canvas-empty--unavailable')}><span className="canvas-empty__mark"><Icon name={workflowLoaded ? 'workflow' : 'server'} size={24} /></span><h2>{allowPreviewAdd ? '从组件目录添加节点' : workflowLoaded ? '从目录添加节点' : '工作流服务未接入'}</h2>{allowPreviewAdd && <button onClick={() => onAddNode('data')}><Icon name="plus" size={15} />添加预览节点</button>}</div>}
  </div>
}

interface LocalWorkflowPreviewLayoutNode extends LocalWorkflowTemplatePreviewNode {
  depth: number
  x: number
  y: number
}

function layoutLocalWorkflowPreview(preview: LocalWorkflowTemplatePreview): {
  nodes: LocalWorkflowPreviewLayoutNode[]
  edges: LocalWorkflowTemplatePreview['edges']
  width: number
  height: number
  nodeWidth: number
  nodeHeight: number
} | null {
  const outgoing = new Map<string, string[]>(preview.nodes.map((node) => [node.id, []] as const))
  const incomingCount = new Map<string, number>(preview.nodes.map((node) => [node.id, 0] as const))
  const depths = new Map<string, number>(preview.nodes.map((node) => [node.id, 0] as const))
  for (const edge of preview.edges) {
    outgoing.get(edge.source)?.push(edge.target)
    incomingCount.set(edge.target, (incomingCount.get(edge.target) ?? 0) + 1)
  }

  // Topological depth forms columns; source canvas positions keep sibling branches in a stable order.
  const ready = preview.nodes.filter((node) => incomingCount.get(node.id) === 0).map((node) => node.id)
  let visitedCount = 0
  while (ready.length > 0) {
    const sourceId = ready.shift()
    if (!sourceId) continue
    visitedCount += 1
    for (const targetId of outgoing.get(sourceId) ?? []) {
      depths.set(targetId, Math.max(depths.get(targetId) ?? 0, (depths.get(sourceId) ?? 0) + 1))
      const remaining = (incomingCount.get(targetId) ?? 0) - 1
      incomingCount.set(targetId, remaining)
      if (remaining === 0) ready.push(targetId)
    }
  }
  if (visitedCount !== preview.nodes.length) return null

  const width = 520
  const height = 96
  const nodeWidth = 136
  const nodeHeight = 28
  const paddingX = 12
  const maxDepth = Math.max(...depths.values())
  const horizontalStep = maxDepth > 0 ? (width - (paddingX * 2) - nodeWidth) / maxDepth : 0
  const byDepth = new Map<number, LocalWorkflowTemplatePreview['nodes']>()
  for (const node of preview.nodes) {
    const depth = depths.get(node.id) ?? 0
    byDepth.set(depth, [...(byDepth.get(depth) ?? []), node])
  }

  const nodes: LocalWorkflowPreviewLayoutNode[] = []
  for (const [depth, group] of byDepth) {
    const ordered = [...group].sort((left, right) => left.position.y - right.position.y || left.id.localeCompare(right.id))
    ordered.forEach((node, index) => {
      const centerY = ordered.length === 1 ? height / 2 : 24 + (index * ((height - 48) / (ordered.length - 1)))
      nodes.push({
        ...node,
        depth,
        x: maxDepth > 0 ? paddingX + (depth * horizontalStep) : (width - nodeWidth) / 2,
        y: centerY - (nodeHeight / 2),
      })
    })
  }
  return { nodes, edges: preview.edges, width, height, nodeWidth, nodeHeight }
}

function LocalWorkflowGraphPreview({ templateName, preview, layout }: {
  templateName: string
  preview: LocalWorkflowTemplatePreview
  layout: NonNullable<ReturnType<typeof layoutLocalWorkflowPreview>>
}) {
  const nodesById = new Map(layout.nodes.map((node) => [node.id, node]))
  const accessibleDescription = `${templateName}工作流缩略图：${preview.nodes.map((node) => `${node.category}，${node.title}`).join('；')}。${preview.edges.length} 条连线。`

  return <svg className="local-template-card__diagram" viewBox={`0 0 ${layout.width} ${layout.height}`} role="img" aria-label={accessibleDescription} focusable="false">
    <title>{accessibleDescription}</title>
    <g aria-hidden="true">
      {layout.edges.map((edge, index) => {
        const source = nodesById.get(edge.source)
        const target = nodesById.get(edge.target)
        if (!source || !target) return null
        const startX = source.x + layout.nodeWidth
        const startY = source.y + (layout.nodeHeight / 2)
        const endX = target.x
        const endY = target.y + (layout.nodeHeight / 2)
        const bendX = startX + ((endX - startX) / 2)
        return <g key={`${edge.source}-${edge.target}-${index}`}>
          <path className="local-template-card__diagram-edge" d={`M ${startX} ${startY} C ${bendX} ${startY}, ${bendX} ${endY}, ${endX} ${endY}`} />
          {/* Leave a small gap before the target box so direction stays clear at thumbnail scale. */}
          <path className="local-template-card__diagram-arrow" d={`M ${endX - 7} ${endY - 3} L ${endX - 1} ${endY} L ${endX - 7} ${endY + 3}`} />
        </g>
      })}
      {layout.nodes.map((node) => {
        const label = node.title.length > 10 ? `${node.title.slice(0, 9)}…` : node.title
        return <g key={node.id}>
          <title>{node.category}：{node.title}</title>
          <rect className="local-template-card__diagram-node" x={node.x} y={node.y} width={layout.nodeWidth} height={layout.nodeHeight} rx="7" />
          <circle className="local-template-card__diagram-node-mark" cx={node.x + 12} cy={node.y + (layout.nodeHeight / 2)} r="3" />
          <text className="local-template-card__diagram-label" x={node.x + 21} y={node.y + (layout.nodeHeight / 2)} dominantBaseline="middle">{label}</text>
        </g>
      })}
    </g>
  </svg>
}

function Templates({ config, onOpenServiceSettings, onOpenWorkflow, onOpenWorkbench }: {
  config: ApiConfig
  onOpenServiceSettings: () => void
  onOpenWorkflow: (projectId: string, workflowId: string) => void
  onOpenWorkbench: () => void
}) {
  const [catalog, setCatalog] = useState<State<TemplateCatalogItem[]>>({ status: 'idle' })
  const [localTemplates, setLocalTemplates] = useState<State<LocalWorkflowTemplate[]>>({ status: 'idle' })
  const [localProjects, setLocalProjects] = useState<State<LocalProject[]>>({ status: 'idle' })
  const [selectedLocalProjectId, setSelectedLocalProjectId] = useState('')
  const [creatingLocalTemplate, setCreatingLocalTemplate] = useState(false)
  const [localTemplateActionError, setLocalTemplateActionError] = useState('')
  const [query, setQuery] = useState('')
  const [sourceFilter, setSourceFilter] = useState<'all' | 'local' | 'platform'>('all')
  const [filter, setFilter] = useState<'all' | 'favorites'>('all')
  const [datasetVersionFilter, setDatasetVersionFilter] = useState('')
  const [executorFilter, setExecutorFilter] = useState('')
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null)
  const [favorites, setFavorites] = useState<string[]>(readTemplateFavorites)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    try {
      window.localStorage.setItem(localTemplateFavoritesKey, JSON.stringify(favorites))
    } catch (error) {
      console.error('保存本机模板收藏失败。', error)
    }
  }, [favorites])

  useEffect(() => {
    let active = true
    setLocalTemplates({ status: 'loading' })
    void listLocalWorkflowTemplates().then((templates) => {
      if (active) setLocalTemplates({ status: 'ready', data: templates })
    }).catch((error: unknown) => {
      console.error('读取本机内置工作流模板失败。', error)
      const message = error instanceof LocalRuntimeApiError
        ? `本机运行时请求失败（${error.code}）。请检查本机服务后重试。`
        : error instanceof TypeError
          ? '无法连接本机运行时，请启动本机运行时后重试。'
          : '无法读取本机模板目录，请检查本机运行时。'
      if (active) setLocalTemplates({ status: 'error', message })
    })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    setLocalProjects({ status: 'loading' })
    void listLocalProjects().then((projects) => {
      if (!active) return
      setLocalProjects({ status: 'ready', data: projects })
      setSelectedLocalProjectId((current) => current && projects.some((project) => project.id === current) ? current : projects[0]?.id ?? '')
    }).catch((error: unknown) => {
      console.error('读取模板目标本机项目失败。', error)
      if (active) setLocalProjects({ status: 'error', message: explainError(error, '无法读取本机项目；请检查本机运行时。') })
    })
    return () => { active = false }
  }, [])

  useEffect(() => {
    // An empty base URL uses the current site's API proxy, just like project requests.
    if (!config.token.trim()) {
      setCatalog({ status: 'idle' })
      return
    }

    const controller = new AbortController()
    setCatalog({ status: 'loading' })
    const readCatalog = async () => {
      try {
        // The registered catalog is global; project membership is checked only when a template is used.
        const contracts = await listTemplateCatalog(config, controller.signal)
        if (!controller.signal.aborted) {
          const items = contracts.map((contract) => ({ contract }))
          setCatalog({ status: 'ready', data: items.sort((a, b) => a.contract.template_id.localeCompare(b.contract.template_id)) })
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error('读取全局模板目录失败。', error)
          const message = error instanceof ProjectApiError && error.status === 404
            ? '当前服务尚未提供全局模板目录接口。'
            : error instanceof ProjectApiError && error.status === 503
              ? '模板注册表暂不可用，请稍后重试。'
              : explainError(error, '读取全局模板目录失败，请检查服务地址和访问凭据。')
          setCatalog({ status: 'error', message })
        }
      }
    }
    void readCatalog()
    return () => controller.abort()
  }, [config, retry])

  const registeredTemplates = catalog.status === 'ready' ? catalog.data : []
  // The registered synthetic smoke executor is for service integration only, not research use.
  const allTemplates = registeredTemplates.filter((item) => item.contract.executor !== 'synthetic_smoke_v1')
  const excludedSyntheticTemplateCount = registeredTemplates.length - allTemplates.length
  const datasetVersions = [...new Set(allTemplates.map((item) => item.contract.dataset_version))].sort((left, right) => left.localeCompare(right))
  const executors = [...new Set(allTemplates.map((item) => item.contract.executor))].sort((left, right) => left.localeCompare(right))
  const showLocalTemplates = sourceFilter !== 'platform'
  const showPlatformTemplates = sourceFilter !== 'local'
  const normalizedQuery = query.trim().toLowerCase()
  const readyLocalTemplates = localTemplates.status === 'ready' ? localTemplates.data : []
  // Keep platform contract filters scoped to remote templates so offline templates remain searchable.
  const visibleLocalTemplates = showLocalTemplates ? readyLocalTemplates.filter((template) => {
    const text = [template.template_id, template.version, template.name, template.category, template.summary, template.description, ...template.component_ids].join(' ').toLowerCase()
    const matchesQuery = text.includes(normalizedQuery)
    const matchesFilter = filter === 'all' || favorites.includes(template.template_id)
    return matchesQuery && matchesFilter
  }) : []
  const visibleTemplates = showPlatformTemplates ? allTemplates.filter((item) => {
    const { contract } = item
    const text = [contract.template_id, contract.version, contract.dataset_version, contract.executor].join(' ').toLowerCase()
    const matchesQuery = text.includes(normalizedQuery)
    const matchesFilter = filter === 'all' || (filter === 'favorites' && favorites.includes(contract.template_id))
    const matchesDatasetVersion = !datasetVersionFilter || contract.dataset_version === datasetVersionFilter
    const matchesExecutor = !executorFilter || contract.executor === executorFilter
    return matchesQuery && matchesFilter && matchesDatasetVersion && matchesExecutor
  }) : []
  const selectedTemplate = visibleTemplates.find((item) => item.contract.template_id === selectedTemplateId) ?? visibleTemplates[0]
  const hasAvailableLocalTemplates = localTemplates.status === 'ready' && localTemplates.data.length > 0
  const hasAvailablePlatformTemplates = catalog.status === 'ready' && allTemplates.length > 0
  const hasVisibleTemplates = visibleLocalTemplates.length > 0 || visibleTemplates.length > 0
  const canSearchTemplates = (showLocalTemplates && (localTemplates.status === 'loading' || hasAvailableLocalTemplates))
    || (showPlatformTemplates && (catalog.status === 'loading' || hasAvailablePlatformTemplates))
  const hasPlatformFilters = showPlatformTemplates && catalog.status === 'ready' && allTemplates.length > 0
  const showFullPlatformState = sourceFilter === 'platform' || (sourceFilter === 'all' && localTemplates.status === 'ready' && localTemplates.data.length === 0)
  const platformCatalogUnavailable = showPlatformTemplates && catalog.status !== 'ready' && visibleLocalTemplates.length === 0
  const localFavoriteCount = readyLocalTemplates.filter((template) => favorites.includes(template.template_id)).length
  const platformFavoriteCount = catalog.status === 'ready' ? allTemplates.filter((item) => favorites.includes(item.contract.template_id)).length : 0
  const scopedFavoriteCount = (showLocalTemplates ? localFavoriteCount : 0) + (showPlatformTemplates ? platformFavoriteCount : 0)
  const favoriteCountIsComplete = (!showLocalTemplates || localTemplates.status === 'ready') && (!showPlatformTemplates || catalog.status === 'ready')
  const allSourceCount = localTemplates.status === 'ready' && catalog.status === 'ready' ? localTemplates.data.length + allTemplates.length : undefined
  const localSourceCount = localTemplates.status === 'ready' ? localTemplates.data.length : undefined
  const platformSourceCount = catalog.status === 'ready' ? allTemplates.length : undefined
  const visibleTemplateCount = visibleLocalTemplates.length + visibleTemplates.length
  const hasRemoteTemplateDetail = Boolean(selectedTemplate)
  const templateControlsDisabledReason = sourceFilter === 'local'
    ? localTemplates.status === 'error' ? '本机运行时未连接，无法搜索本机模板' : '当前没有本机模板可搜索'
    : sourceFilter === 'platform'
      ? catalog.status === 'idle' ? '平台模板服务未连接' : catalog.status === 'error' ? '平台模板目录暂不可用' : '当前没有平台模板可搜索'
      : '当前没有可搜索模板源，请查看下方来源状态'
  const localTemplateAvailability = localTemplates.status === 'error'
    ? '本机运行时不可用'
    : localTemplates.status === 'loading' || localTemplates.status === 'idle'
      ? '正在读取本机模板'
      : localTemplates.data.length === 0
        ? '本机模板目录为空'
        : '本机模板可在平台服务断开时使用'
  // In the unified view, show both source states when neither source can provide a result.
  const showCombinedSourceEmpty = sourceFilter === 'all'
    && localTemplates.status === 'error'
    && catalog.status !== 'loading'
    && !hasAvailablePlatformTemplates
  const showLocalSourceEmpty = sourceFilter === 'local'
    && (localTemplates.status === 'error' || (localTemplates.status === 'ready' && localTemplates.data.length === 0))
  const platformSourceEmptyStatus = catalog.status === 'idle'
    ? '平台服务未连接'
    : catalog.status === 'error'
      ? '平台目录读取失败'
      : excludedSyntheticTemplateCount > 0
        ? '暂无可用于科研的模板'
        : '暂无已发布模板'
  const platformSourceEmptyDetail = catalog.status === 'idle'
    ? '从左侧配置平台服务后，可浏览已发布模板。'
    : catalog.status === 'error'
      ? `${catalog.message} 可从左侧重试。`
      : excludedSyntheticTemplateCount > 0
        ? '目录当前仅包含合成联调条目，不会作为科研模板展示。'
        : '平台目录当前没有已发布模板。'
  const toggleFavorite = (templateId: string) => setFavorites((current) => current.includes(templateId)
    ? current.filter((id) => id !== templateId)
    : [...current, templateId])
  const addLocalTemplateToProject = async (template: LocalWorkflowTemplate) => {
    if (creatingLocalTemplate || !selectedLocalProjectId) return
    setCreatingLocalTemplate(true)
    setLocalTemplateActionError('')
    try {
      const workflow = await createLocalProjectWorkflowFromTemplate(selectedLocalProjectId, template)
      onOpenWorkflow(selectedLocalProjectId, workflow.id)
    } catch (error) {
      console.error('从本机内置模板创建工作流失败。', error)
      setLocalTemplateActionError(error instanceof LocalRuntimeApiError
        ? `创建失败（${error.code}）。工作流未同步到平台。`
        : explainError(error, '创建本机工作流失败；请检查本机运行时后重试。'))
    } finally {
      setCreatingLocalTemplate(false)
    }
  }

  return <>
    <Heading title="模板市场" />
    <section className={'template-browser template-browser--library' + (hasVisibleTemplates ? '' : ' template-browser--empty') + (platformCatalogUnavailable ? ' template-browser--catalog-unavailable' : '')} aria-label="统一模板浏览区">
      <aside className="template-library__rail" aria-label="模板目录导航">
        <div className="template-library__rail-heading"><span className="kicker">工作流模板</span><h2>来源与筛选</h2></div>
        <div className="template-library__sources" role="group" aria-label="模板来源">
          <button type="button" aria-pressed={sourceFilter === 'all'} className={sourceFilter === 'all' ? 'active' : ''} onClick={() => setSourceFilter('all')}><Icon name="template" size={16} /><span>全部来源</span>{allSourceCount !== undefined && <small>{allSourceCount}</small>}</button>
          <button type="button" aria-pressed={sourceFilter === 'local'} className={sourceFilter === 'local' ? 'active' : ''} onClick={() => setSourceFilter('local')}><Icon name="folder" size={16} /><span>本机内置</span>{localSourceCount !== undefined && <small>{localSourceCount}</small>}</button>
          <button type="button" aria-pressed={sourceFilter === 'platform'} className={sourceFilter === 'platform' ? 'active' : ''} onClick={() => setSourceFilter('platform')}><Icon name="server" size={16} /><span>平台目录</span>{platformSourceCount !== undefined && <small>{platformSourceCount}</small>}</button>
        </div>
        <div className="template-library__nav" role="group" aria-label="收藏筛选">
          <button type="button" aria-pressed={filter === 'all'} className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}><Icon name="template" size={16} /><span>全部模板</span></button>
          <button type="button" aria-pressed={filter === 'favorites'} className={filter === 'favorites' ? 'active' : ''} onClick={() => setFilter('favorites')}><span className="template-library__star" aria-hidden="true">☆</span><span>已收藏</span>{favoriteCountIsComplete && <small>{scopedFavoriteCount}</small>}</button>
        </div>
        <div className="template-library__connection">
          <span className={'template-library__connection-dot template-library__connection-dot--' + catalog.status} />
          <span><strong>{catalog.status === 'idle' ? '平台服务未连接' : catalog.status === 'loading' ? '正在读取平台目录' : catalog.status === 'error' ? '平台目录读取失败' : '平台目录已连接'}</strong><small id="template-platform-state" role="status">{catalog.status === 'idle' ? localTemplateAvailability : catalog.status === 'ready' ? '仅展示真实注册模板' : catalog.status === 'error' ? '平台模板暂不可用' : '正在获取已发布版本'}</small></span>
          {catalog.status === 'idle' && <button type="button" className="link-button" onClick={onOpenServiceSettings}>配置服务</button>}
          {catalog.status === 'error' && <button type="button" className="link-button" onClick={() => setRetry((value) => value + 1)}>重试</button>}
        </div>
      </aside>
      <div className={'template-browser__main' + (hasPlatformFilters ? ' template-browser__main--with-filters' : '')}>
        <header className="template-browser__toolbar">
          <div className="template-browser__title"><div><h2>{filter === 'favorites' ? '已收藏模板' : sourceFilter === 'local' ? '本机模板' : sourceFilter === 'platform' ? '平台模板' : '全部模板'}</h2>{(sourceFilter === 'local' ? localSourceCount : sourceFilter === 'platform' ? platformSourceCount : allSourceCount) !== undefined && <span>{filter === 'favorites' ? scopedFavoriteCount : sourceFilter === 'local' ? localSourceCount : sourceFilter === 'platform' ? platformSourceCount : allSourceCount} 个模板</span>}</div></div>
          <label className={'template-search' + (!canSearchTemplates ? ' is-disabled' : '')}><Icon name="search" size={16} /><input aria-label="搜索模板名称、标识、版本或组件" aria-describedby={!canSearchTemplates ? 'template-catalog-state' : undefined} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、标识、版本或组件" disabled={!canSearchTemplates} title={!canSearchTemplates ? templateControlsDisabledReason : undefined} /></label>
        </header>
        {hasPlatformFilters && <div className="template-browser__filters" role="group" aria-label="平台模板筛选">
          <span className="template-browser__filters-label"><Icon name="sliders" size={15} /><span>平台筛选</span></span>
          <select aria-label="按平台模板数据版本筛选" value={datasetVersionFilter} title="仅筛选平台登记模板的数据版本" onChange={(event) => setDatasetVersionFilter(event.target.value)}>
            <option value="">全部数据版本</option>
            {datasetVersions.map((version) => <option key={version} value={version}>{version}</option>)}
          </select>
          <select aria-label="按平台模板执行器筛选" title="仅筛选平台登记模板的执行器" value={executorFilter} onChange={(event) => setExecutorFilter(event.target.value)}>
            <option value="">全部执行器</option>
            {executors.map((executor) => <option key={executor} value={executor}>{executor}</option>)}
          </select>
          <span className="template-browser__filters-hint" aria-live="polite">{visibleTemplateCount} 个匹配模板</span>
        </div>}
        <div className={'template-browser__body' + (hasRemoteTemplateDetail ? '' : ' template-browser__body--without-detail')}>
          <section className="template-results" aria-label="模板列表">
            {showLocalTemplates && localTemplates.status === 'loading' && <div className="template-source-state" role="status"><span className="template-loading-lines"><i /><i /><i /></span><span><strong>正在读取本机模板</strong><small>模板与工作流保存在此设备。</small></span></div>}
            {showLocalTemplates && localTemplates.status === 'error' && !showCombinedSourceEmpty && !showLocalSourceEmpty && <div className="template-source-state template-source-state--error" role="alert"><Icon name="folder" size={18} /><span><strong id="template-catalog-state">本机模板目录暂不可用</strong><small>{localTemplates.message}</small></span></div>}
            {showCombinedSourceEmpty && <div className="template-source-empty" role="status">
              <div className="template-source-empty__intro">
                <span className="template-market-empty__mark"><Icon name="template" size={20} /></span>
                <h3 id="template-catalog-state">{filter === 'favorites' ? '当前没有可显示的收藏模板' : '当前没有可浏览的模板'}</h3>
              </div>
              <div className="template-source-empty__sources" aria-label="模板来源状态">
                <article className="template-source-empty__source">
                  <Icon name="folder" size={18} />
                  <div><div className="template-source-empty__source-heading"><strong>本机内置</strong><span>运行时未连接</span></div></div>
                </article>
                <article className="template-source-empty__source">
                  <Icon name="server" size={18} />
                  <div><div className="template-source-empty__source-heading"><strong>平台目录</strong><span>{platformSourceEmptyStatus}</span></div>{platformSourceEmptyDetail ? <p>{platformSourceEmptyDetail}</p> : null}</div>
                </article>
              </div>
            </div>}
            {showLocalSourceEmpty && <div className="template-source-empty template-source-empty--single" role={localTemplates.status === 'error' ? 'alert' : 'status'}>
              <div className="template-source-empty__intro">
                <span className="template-market-empty__mark"><Icon name="folder" size={20} /></span>
                <h3 id="template-catalog-state">{localTemplates.status === 'error' ? '本机模板目录暂不可用' : '当前没有本机内置模板'}</h3>
              </div>
              <div className="template-source-empty__sources" aria-label="本机模板来源状态">
                <article className="template-source-empty__source">
                  <Icon name="folder" size={18} />
                  <div><div className="template-source-empty__source-heading"><strong>本机内置</strong><span>{localTemplates.status === 'error' ? '运行时未连接' : '目录为空'}</span></div>{localTemplates.status === 'error' ? <p>{localTemplates.message}</p> : null}</div>
                </article>
              </div>
            </div>}
            {visibleLocalTemplates.map((template) => {
              const isFolderQualityTemplate = template.template_id === 'ict.local.csv_folder_quality'
              const previewLayout = template.workflow_preview ? layoutLocalWorkflowPreview(template.workflow_preview) : null
              const hasWorkflowPreview = Boolean(previewLayout)
              const isFavorite = favorites.includes(template.template_id)
              const targetProjectSelectId = `local-template-target-project-${template.template_id.replace(/[^A-Za-z0-9_-]/g, '-')}`
              return <article className={'local-template-card' + (hasWorkflowPreview ? ' local-template-card--has-preview' : '')} key={`${template.template_id}@${template.version}`}>
                <div className="local-template-card__main">
                  <div className="local-template-card__title"><div><span className="kicker">{template.category} · v{template.version}</span><h3>{template.name}</h3><p>{template.summary}</p></div><span className="local-template-card__badges"><button type="button" className="template-favorite-button" aria-label={isFavorite ? `取消收藏 ${template.name}` : `收藏 ${template.name}`} aria-pressed={isFavorite} onClick={() => toggleFavorite(template.template_id)}>{isFavorite ? '★' : '☆'}</button><span className="local-template-card__offline"><Icon name="folder" size={14} />本机内置</span></span></div>
                  {template.workflow_preview && previewLayout && <LocalWorkflowGraphPreview templateName={template.name} preview={template.workflow_preview} layout={previewLayout} />}
                  <div className="local-template-card__flow" aria-label={isFolderQualityTemplate ? '选择本机文件夹，递归导入 CSV，逐文件检查并生成汇总报告' : 'CSV 来源连接到字段选择，再分别连接结构预检和描述统计'}>
                    {isFolderQualityTemplate ? <><span>选择本机文件夹</span><b aria-hidden="true">→</b><span>递归导入 CSV</span><b aria-hidden="true">→</b><span>逐文件检查</span><b aria-hidden="true">→</b><span>汇总报告</span></> : <><span>CSV 来源</span><b aria-hidden="true">→</b><span>字段选择</span><b aria-hidden="true">→</b><span>结构预检</span><i aria-hidden="true">＋</i><span>描述统计</span></>}
                  </div>
                  {template.description ? <p className="local-template-card__note">{template.description}</p> : null}
                </div>
                <div className="local-template-card__install">
                  {localProjects.status === 'loading' && <p role="status">正在读取本机项目…</p>}
                  {localProjects.status === 'error' && <div className="local-template-card__error" role="alert"><strong>无法读取目标项目</strong><span>{localProjects.message}</span><button type="button" className="button secondary" onClick={onOpenWorkbench}>打开工作台</button></div>}
                  {localProjects.status === 'ready' && localProjects.data.length > 0 && <>
                    <label htmlFor={targetProjectSelectId}>添加到本机项目</label>
                    <select id={targetProjectSelectId} value={selectedLocalProjectId} onChange={(event) => { setSelectedLocalProjectId(event.target.value); setLocalTemplateActionError('') }}>
                      {localProjects.data.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
                    </select>
                    <button type="button" className="button primary" disabled={creatingLocalTemplate || !selectedLocalProjectId} onClick={() => void addLocalTemplateToProject(template)}>{creatingLocalTemplate ? '正在创建…' : '添加并打开工作流'}</button>
                    {localTemplateActionError && <p className="local-template-card__error" role="alert">{localTemplateActionError}</p>}
                  </>}
                  {localProjects.status === 'ready' && localProjects.data.length === 0 && <div className="local-template-card__empty"><strong>暂无本机项目</strong><button type="button" className="button secondary" onClick={onOpenWorkbench}>前往工作台创建项目</button></div>}
                </div>
              </article>
            })}
            {showPlatformTemplates && showFullPlatformState && catalog.status === 'idle' && <div className="template-market-empty" role="status"><div className="template-market-empty__copy"><span className="template-market-empty__mark"><Icon name="server" size={20} /></span><h3 id="template-catalog-state">平台服务未连接</h3><button className="button primary" onClick={onOpenServiceSettings}>配置服务</button></div></div>}
            {showPlatformTemplates && showFullPlatformState && catalog.status === 'loading' && <div className="template-market-empty" role="status"><span className="template-market-empty__mark"><span className="template-loading-lines"><i /><i /><i /></span></span><h3 id="template-catalog-state">正在读取平台模板</h3></div>}
            {showPlatformTemplates && showFullPlatformState && catalog.status === 'error' && <div className="template-market-empty template-market-empty--error" role="alert"><span className="template-market-empty__mark"><Icon name="refresh" size={20} /></span><h3 id="template-catalog-state">无法读取平台模板目录</h3><p>{catalog.message}</p><button className="button secondary" onClick={() => setRetry((value) => value + 1)}>重试读取</button></div>}
            {showPlatformTemplates && showFullPlatformState && catalog.status === 'ready' && allTemplates.length === 0 && <div className="template-market-empty" role="status"><div className="template-market-empty__copy"><span className="template-market-empty__mark"><Icon name="template" size={20} /></span><h3 id="template-catalog-state">{excludedSyntheticTemplateCount > 0 ? '暂无可用于科研的工作流模板' : '暂无已注册平台模板'}</h3><button className="button secondary" onClick={() => setRetry((value) => value + 1)}>重新读取</button></div></div>}
            {showPlatformTemplates && catalog.status === 'ready' && allTemplates.length > 0 && visibleTemplates.map((item) => {
              const { contract } = item
              const isFavorite = favorites.includes(contract.template_id)
              const isSelected = selectedTemplate?.contract.template_id === contract.template_id
              return <article className={'template-catalog-card' + (isSelected ? ' selected' : '')} key={contract.template_id}>
                <button className="template-catalog-card__select" aria-pressed={isSelected} onClick={() => setSelectedTemplateId(contract.template_id)}>
                  <span className="template-card-preview" aria-label="执行契约摘要，不代表工作流节点拓扑"><span>数据版本 <code>{contract.dataset_version}</code></span><i /><span>执行器 <code>{contract.executor}</code></span><i /><span>输出字段 <code>{Object.keys(contract.outputs).length} 项</code></span></span>
                  <span className="template-card-copy"><span className="template-card-copy__meta"><span>已注册</span><span>v{contract.version}</span></span><strong>{contract.template_id}</strong><small>{Object.keys(contract.inputs).length} 个输入字段 · {Object.keys(contract.outputs).length} 个输出字段</small></span>
                </button>
                <button className="template-favorite-button" aria-label={isFavorite ? `取消收藏 ${contract.template_id}` : `收藏 ${contract.template_id}`} aria-pressed={isFavorite} onClick={() => toggleFavorite(contract.template_id)}>{isFavorite ? '★' : '☆'}</button>
              </article>
            })}
            {((showLocalTemplates && localTemplates.status === 'ready' && localTemplates.data.length > 0) || (showPlatformTemplates && catalog.status === 'ready' && allTemplates.length > 0)) && !hasVisibleTemplates && <div className="template-results__empty"><Icon name="search" size={19} /><strong>没有匹配的模板</strong><button className="link-button" onClick={() => { setQuery(''); setFilter('all'); setDatasetVersionFilter(''); setExecutorFilter('') }}>清除搜索和筛选</button></div>}
          </section>
          {selectedTemplate && <aside className="template-detail-column" aria-label="平台模板详情">
            <TemplateContractDetail item={selectedTemplate} favorite={favorites.includes(selectedTemplate.contract.template_id)} onToggleFavorite={() => toggleFavorite(selectedTemplate.contract.template_id)} />
          </aside>}
        </div>
      </div>
    </section>
  </>
}

function TemplateContractDetail({ item, favorite, onToggleFavorite }: { item: TemplateCatalogItem; favorite: boolean; onToggleFavorite: () => void }) {
  const { contract } = item
  return <article className="template-detail" aria-labelledby="template-detail-title">
    <header className="template-detail__heading"><div><span className="kicker">平台注册模板 · 版本契约</span><h2 id="template-detail-title">{contract.template_id}</h2><p>版本 {contract.version} <span>·</span> 全局注册目录</p></div><button className="template-favorite-button" aria-label={favorite ? `取消收藏 ${contract.template_id}` : `收藏 ${contract.template_id}`} aria-pressed={favorite} onClick={onToggleFavorite}>{favorite ? '★' : '☆'}</button></header>
    <section className="template-contract-preview" aria-label="模板版本契约">
      <div className="template-contract-preview__label"><span>执行契约摘要</span><span>当前目录未提供流程拓扑</span></div>
      <div className="template-contract-preview__facts" aria-label="已登记契约信息">
        <div><small>数据版本</small><code>{contract.dataset_version}</code></div>
        <div><small>执行器</small><code>{contract.executor}</code></div>
        <div><small>输出字段</small><strong>{Object.keys(contract.outputs).length} 项</strong></div>
      </div>
      <p className="template-contract-preview__topology-note">当前目录响应只包含执行契约，没有节点与连线数据，因此暂时无法预览实际工作流结构。</p>
    </section>
    <dl className="template-detail__facts"><div><dt>授权范围</dt><dd><code>{contract.permission_scope}</code></dd></div><div><dt>并发上限</dt><dd>{contract.resource_limits.max_concurrent_runs} 个运行</dd></div><div><dt>软 / 硬超时</dt><dd>{contract.resource_limits.soft_timeout_seconds}s / {contract.resource_limits.hard_timeout_seconds}s</dd></div><div><dt>清单摘要</dt><dd><code>{contract.manifest_sha256.slice(0, 16)}…</code></dd></div></dl>
    <div className="template-contract-sections"><TemplateContractSection title="输入" fields={contract.inputs} /><TemplateContractSection title="参数" fields={contract.parameters} /><TemplateContractSection title="输出" fields={contract.outputs} /></div>
    <details className="template-runtime-details"><summary>运行状态与错误码</summary><div><section><h3>状态</h3><p>{contract.states.join(' · ')}</p></section><section><h3>错误码</h3><p>{contract.error_codes.join(' · ')}</p></section></div></details>
    <footer className="template-detail__actions"><button className="button primary" disabled title="模板使用目标和副本创建服务尚未接入">使用模板</button><p>使用目标选择与模板副本创建服务尚未接入。</p></footer>
  </article>
}

function TemplateContractSection({ title, fields }: { title: string; fields: Record<string, TemplateContract['inputs'][string]> }) {
  const entries = Object.entries(fields)
  return <section className="template-contract-group"><header><h3>{title}</h3><span>{entries.length} 项</span></header>{entries.length > 0 ? <ul>{entries.map(([name, field]) => <li key={name}><div className="template-contract-group__name"><code>{name}</code><span>{field.type}</span></div><small>{field.required ? '必填' : '可选'}{field.const !== null ? ` · 固定值 ${String(field.const)}` : ''}{field.minimum !== null || field.maximum !== null ? ` · 范围 ${field.minimum ?? '—'}–${field.maximum ?? '—'}` : ''}</small></li>)}</ul> : <p className="template-contract-group__empty">无声明字段</p>}</section>
}

function Agent({ projectContext, workflowContext, datasetContext, onClearProjectContext, onClearWorkflowContext, onClearDatasetContext, onOpenServiceSettings }: { projectContext: AgentProjectContext | null; workflowContext: AgentWorkflowContext | null; datasetContext: AgentDatasetContext | null; onClearProjectContext: () => void; onClearWorkflowContext: () => void; onClearDatasetContext: () => void; onOpenServiceSettings: () => void }) {
  // Keep the conversation focused when the current viewport cannot comfortably fit the context rail.
  const [contextOpen, setContextOpen] = useState(() => window.innerWidth > 1150)
  const stagedContextCount = Number(Boolean(projectContext)) + Number(Boolean(workflowContext)) + Number(Boolean(datasetContext))
  return <><Heading title="Agent 对话" /><div className={'agent-layout' + (contextOpen ? '' : ' agent-layout--context-collapsed')}>
    <aside className="conversation-list"><div><strong>对话历史</strong></div><section><Icon name="agent" /><strong>暂无对话</strong></section></aside>
    <section className="chat-area"><div className="chat-header"><span className="chat-header__title"><i className="live-dot" />新对话</span><div className="chat-header__actions"><span id="agent-service-state" className="chat-service-state" role="status" title="Agent 对话服务、引用和工具调用尚未接入">Agent 服务未接入</span><button className="chat-context-toggle chat-service-status-link" type="button" aria-label="查看 Agent 与模型服务状态" title="查看 Agent 与模型服务状态" onClick={onOpenServiceSettings}><Icon name="server" size={15} /><span>查看服务状态</span></button><button className="chat-context-toggle" type="button" aria-label={contextOpen ? '收起上下文侧栏' : '展开上下文侧栏'} aria-expanded={contextOpen} aria-controls="agent-context-rail" title={contextOpen ? '收起上下文侧栏' : '展开上下文侧栏'} onClick={() => setContextOpen((open) => !open)}><Icon name="panel" size={15} /><span>{contextOpen ? '收起上下文' : '展开上下文'}</span></button></div></div>
      <div className="chat-empty-compose">
        <div className="chat-composer chat-composer--disabled" aria-label="对话输入区"><textarea aria-label="研究问题" aria-describedby="agent-service-state" disabled placeholder="输入研究问题…" /><div className="chat-composer__toolbar"><div className="chat-composer__tools"><button type="button" disabled title="Agent 服务接入后可用" aria-label="添加附件"><Icon name="attachment" size={16} /><span>添加附件</span></button><button type="button" disabled title="Agent 服务接入后可用" aria-label="引用对象"><Icon name="plus" size={16} /><span>引用对象</span></button></div><button className="chat-composer__send" type="button" disabled title="Agent 服务接入后可用" aria-label="发送消息"><Icon name="send" size={17} /></button></div></div>
      </div>
    </section>
    <aside className="context-rail" id="agent-context-rail" aria-label="当前对话上下文" tabIndex={0} hidden={!contextOpen}>
      <section>
        <div className="context-rail__heading"><h2>当前上下文</h2><span>{stagedContextCount > 0 ? `${stagedContextCount} 项` : '未添加'}</span></div>
        <dl className="context-object-list" aria-label="研究对象引用">
          <div><dt>项目</dt><dd>{projectContext ? <div className="agent-project-reference"><div className="agent-project-reference__main"><Icon name="folder" size={16} /><span><strong>{projectContext.name}</strong><code>{projectContext.id}</code></span></div><button type="button" className="agent-project-reference__remove" aria-label={`移除项目引用 ${projectContext.name}`} onClick={onClearProjectContext}>移除</button></div> : <span>未引用</span>}</dd></div>
          <div><dt>论文复现任务</dt><dd>未引用</dd></div>
          <div><dt>工作流</dt><dd>{workflowContext ? <div className="agent-project-reference"><div className="agent-project-reference__main"><Icon name="workflow" size={16} /><span><strong>{workflowContext.name}</strong><code>{workflowContext.id}</code></span></div><button type="button" className="agent-project-reference__remove" aria-label={`移除工作流引用 ${workflowContext.name}`} onClick={onClearWorkflowContext}>移除</button></div> : <span>未引用</span>}</dd></div>
          <div><dt>数据集</dt><dd>{datasetContext ? <div className="agent-project-reference"><div className="agent-project-reference__main"><Icon name="database" size={16} /><span><strong>{datasetContext.version}</strong><code>{datasetContext.id}</code></span></div><button type="button" className="agent-project-reference__remove" aria-label={`移除数据集引用 ${datasetContext.version}`} onClick={onClearDatasetContext}>移除</button></div> : <span>未引用</span>}</dd></div>
          <div><dt>相关运行</dt><dd>暂无关联</dd></div>
          <div><dt>检验任务</dt><dd>暂无关联</dd></div>
        </dl>
      </section>
    </aside>
  </div></>
}

function Settings({ section, setSection, config, status, projects, onConnect, onDisconnect, preferences, onPreferencesChange, preferencesSaveFailed }: {
  section: SettingsTab; setSection: (tab: SettingsTab) => void; config: ApiConfig; status: Status; projects: State<ProjectListItem[]>; onConnect: (config: ApiConfig) => Promise<void>; onDisconnect: () => void
  preferences: LocalPreferences; onPreferencesChange: (next: LocalPreferences) => void; preferencesSaveFailed: boolean
}) {
  const tabs: [SettingsTab, string, IconName][] = [['profile', '个人资料', 'user'], ['preferences', '偏好设置', 'sliders'], ['notifications', '通知设置', 'bell'], ['security', '账号安全', 'key'], ['workspace', '工作空间与权限', 'users'], ['service', '服务配置', 'server']]
  const selectedLabel = tabs.find(([id]) => id === section)?.[1] || '个人资料'
  const updateNotification = (key: NotificationPreferenceKey, value: boolean) => onPreferencesChange({ ...preferences, notifications: { ...preferences.notifications, [key]: value } })
  return <><Heading title="个人信息与设置" /><div className="settings-layout"><nav className="settings-nav" aria-label="设置分类"><span>个人与工作空间</span>{tabs.map(([id, label, icon]) => <button type="button" aria-current={section === id ? 'page' : undefined} className={section === id ? 'active' : ''} key={id} onClick={() => setSection(id)}><Icon name={icon} size={17} />{label}</button>)}</nav><section className="settings-content"><div className="settings-content__heading"><h2>{selectedLabel}</h2></div>
    {section === 'profile' && <div className="settings-page-section"><div className="settings-section-title"><div><h3>账号信息</h3></div><span className="settings-state-chip"><i />账号服务未接入</span></div><div className="settings-field-list"><SettingInfoRow label="显示名称" value="—" /><SettingInfoRow label="电子邮箱" value="—" /><SettingInfoRow label="所属机构" value="—" /></div></div>}
    {section === 'preferences' && <div className="settings-page-section"><div className="settings-section-title"><div><h3>显示方式</h3></div><span className={'settings-save-state' + (preferencesSaveFailed ? ' is-error' : '')}><i />{preferencesSaveFailed ? '本地保存失败' : '已保存在此浏览器'}</span></div><div className="settings-form-group"><div className="settings-form-copy"><strong>内容密度</strong></div><div className="segmented-control" role="radiogroup" aria-label="内容密度"><button role="radio" aria-checked={preferences.density === 'comfortable'} className={preferences.density === 'comfortable' ? 'active' : ''} onClick={() => onPreferencesChange({ ...preferences, density: 'comfortable' })}>舒适</button><button role="radio" aria-checked={preferences.density === 'compact'} className={preferences.density === 'compact' ? 'active' : ''} onClick={() => onPreferencesChange({ ...preferences, density: 'compact' })}>紧凑</button></div></div><SettingToggle title="减少界面动效" description="关闭非必要的过渡和动态效果。" checked={preferences.reduceMotion} onChange={(value) => onPreferencesChange({ ...preferences, reduceMotion: value })} /></div>}
    {section === 'notifications' && <div className="settings-page-section"><div className="settings-section-title"><div><h3>研究过程提醒</h3></div><span className="settings-state-chip">本机偏好</span></div><div className="settings-toggle-list"><SettingToggle title="运行失败" description="工作流运行异常或中断时提醒。" checked={preferences.notifications.runFailed} onChange={(value) => updateNotification('runFailed', value)} /><SettingToggle title="运行完成" description="工作流执行结束后提醒。" checked={preferences.notifications.runCompleted} onChange={(value) => updateNotification('runCompleted', value)} /><SettingToggle title="需要审批" description="有待确认的操作或运行提案时提醒。" checked={preferences.notifications.approvalRequired} onChange={(value) => updateNotification('approvalRequired', value)} /><SettingToggle title="检验待复核" description="论文复现或实验核验需要人工复核时提醒。" checked={preferences.notifications.reviewRequired} onChange={(value) => updateNotification('reviewRequired', value)} /></div></div>}
    {section === 'security' && <div className="settings-page-section"><div className="settings-section-title"><div><h3>登录与验证</h3></div><span className="settings-state-chip"><i />账号服务未接入</span></div><div className="settings-field-list"><SettingInfoRow label="登录方式" value="—" /><SettingInfoRow label="多因素验证" value="—" /><SettingInfoRow label="活跃会话" value="—" /></div></div>}
    {section === 'workspace' && <div className="settings-page-section"><div className="settings-section-title"><div><h3>工作空间信息</h3></div><span className="settings-state-chip"><i />组织服务未接入</span></div><div className="settings-field-list"><SettingInfoRow label="当前工作空间" value="—" /><SettingInfoRow label="所属团队" value="—" /><SettingInfoRow label="访问权限" value="—" /></div></div>}
    {section === 'service' && <div className="settings-page-section"><div id="agent-service-connection-state" className="settings-service-hint settings-service-hint--agent" role="status"><Icon name="agent" size={17} /><div><strong>Agent 与模型服务尚未接入</strong></div></div><ServiceForm config={config} status={status} projects={projects} onConnect={onConnect} onDisconnect={onDisconnect} /></div>}
  </section></div></>
}

function SettingInfoRow({ label, value }: { label: string; value: string }) {
  // Keep unavailable values concise while making their meaning clear to screen readers.
  const unavailable = value === '—'
  return <div className="settings-info-row"><span>{label}</span><strong aria-label={unavailable ? `${label}暂不可用` : undefined}>{value}</strong></div>
}

function SettingToggle({ title, description, checked, onChange }: { title: string; description: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <div className="settings-toggle-row"><div><strong>{title}</strong><span>{description}</span></div><button type="button" className={'settings-switch' + (checked ? ' is-on' : '')} role="switch" aria-checked={checked} aria-label={title} onClick={() => onChange(!checked)}><i /></button></div>
}

function ServiceForm({ config, status, projects, onConnect, onDisconnect }: { config: ApiConfig; status: Status; projects: State<ProjectListItem[]>; onConnect: (config: ApiConfig) => Promise<void>; onDisconnect: () => void }) {
  const [baseUrl, setBaseUrl] = useState(config.baseUrl)
  const [token, setToken] = useState(config.token)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { setBaseUrl(config.baseUrl); setToken(config.token) }, [config.baseUrl, config.token])
  const submit = async (event: FormEvent) => { event.preventDefault(); setError(''); if (!token.trim()) { setError('请填写服务访问令牌。'); return }; setBusy(true); await onConnect({ baseUrl, token }); setBusy(false) }
  return <><div className="connection-summary"><Icon name="server" /><div><strong>{status === 'connected' ? '项目服务已连接' : status === 'connecting' ? '正在验证服务' : status === 'error' ? '服务连接失败' : '尚未连接项目服务'}</strong>{status === 'connected' && projects.status === 'ready' ? <p>已读取 {projects.data.length} 个项目。</p> : status === 'error' && projects.status === 'error' ? <p>{projects.message}</p> : null}</div><StatusBadge status={status} /></div><form className="service-form" onSubmit={submit}><label>API 地址<span>本地开发可留空并使用当前站点代理</span><input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="例如 http://127.0.0.1:8765" /></label><label>访问令牌<span>只保留在当前页面会话内</span>{/* Keep validation feedback associated with the credential field for assistive technology. */}<input id="service-access-token" type="password" autoComplete="new-password" aria-invalid={error ? true : undefined} aria-describedby={error ? 'service-token-error' : undefined} value={token} onChange={(event) => { setToken(event.target.value); if (error) setError('') }} placeholder="输入服务管理员提供的令牌" /></label>{error && <p id="service-token-error" className="form-error" role="alert">{error}</p>}<div className="form-actions"><button className="button primary" disabled={busy}>{busy ? '正在验证…' : '验证并连接'}</button>{status === 'connected' && <button className="button secondary" type="button" onClick={onDisconnect}>断开连接</button>}</div></form><p className="privacy-note"><Icon name="shield" size={15} />令牌不会写入浏览器本地存储，刷新页面后需要重新输入。</p></>
}

function CreateProjectDialog({ onClose, onCreate, localOnly = false, preview = false }: { onClose: () => void; onCreate: (input: ProjectCreateInput) => Promise<ProjectDetail | LocalProjectDetail>; localOnly?: boolean; preview?: boolean }) {
  const [name, setName] = useState('')
  const [domain, setDomain] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (busy || preview) return
    setError('')
    setBusy(true)
    try {
      await onCreate({ name: name.trim(), domain: domain.trim(), description: description.trim() })
    } catch (cause) {
      setError(explainError(cause, '项目创建失败，请检查必填项和账号权限。'))
      setBusy(false)
    }
  }
  const updateField = (setter: (value: string) => void) => (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setter(event.target.value)
    if (error) setError('')
  }
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose() }}>
    <section className="create-dialog" role="dialog" aria-modal="true" aria-labelledby="create-project-title" aria-describedby="create-project-description">
      <div className="create-dialog__header">
        <div className="create-dialog__heading">
          <span className="kicker">工作台 / 项目</span>
          <h2 id="create-project-title">{localOnly ? '创建本机项目' : '创建研究项目'}</h2>
          <p id="create-project-description">{localOnly ? '先建立本机研究空间；项目和后续运行记录仅保存在此设备。' : '先建立研究空间；数据与工作流可以在项目中继续添加。'}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="关闭" disabled={busy}><Icon name="close" /></button>
      </div>
      <form onSubmit={submit}>
        <label>项目名称<input required maxLength={120} autoFocus value={name} onChange={updateField(setName)} placeholder="为这项研究取一个便于识别的名称" /></label>
        <label>研究领域<input required maxLength={80} value={domain} onChange={updateField(setDomain)} placeholder="例如：医学、生命科学或材料科学" /></label>
        <label><span className="create-dialog__label-title">研究目标与项目说明 <i>选填</i></span><textarea maxLength={4000} value={description} onChange={updateField(setDescription)} placeholder="概括要回答的研究问题、研究对象和范围" rows={3} /></label>
        {localOnly && <p className="local-only-notice" role="note"><Icon name="server" size={15} /><span><strong>仅保存在此设备</strong><small>不会自动上传；平台服务恢复后也不会自动同步。</small></span></p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {preview && <p className="create-dialog__preview-note" role="status">开发态表单预览，不会向项目服务提交信息。</p>}
        <footer><button type="button" className="button secondary" onClick={onClose} disabled={busy}>取消</button><button className="button primary" disabled={busy || preview} title={preview ? '预览模式不会创建项目' : undefined}>{busy ? '正在创建…' : preview ? '仅供预览' : localOnly ? '创建本机项目' : '创建并进入项目'}</button></footer>
      </form>
      <aside className="create-dialog__next" aria-label="项目创建后的起步路径">
        <span className="kicker">创建后继续</span>
        <h3>把研究过程组织在同一个项目里</h3>
        <p>项目建立后，可按课题需要逐步完善，不必一次完成所有配置。</p>
        <ol>
          <li><span>01</span><div><strong>准备数据</strong><small>导入项目数据或选择已有资源</small></div></li>
          <li><span>02</span><div><strong>构建工作流</strong><small>从可用模板开始，或使用自由画布</small></div></li>
          <li><span>03</span><div><strong>运行与检验</strong><small>在所属工作流运行并查看可追溯产物</small></div></li>
        </ol>
      </aside>
    </section>
  </div>
}

function StatusBadge({ status }: { status: Status }) {
  const label = status === 'connected' ? '已连接' : status === 'connecting' ? '正在连接' : status === 'error' ? '连接异常' : '未连接'
  return <span className={'status-badge status-' + status}><i />{label}</span>
}
function explainError(error: unknown, fallback = '项目服务暂时不可用，请检查服务配置。') {
  if (error instanceof ProjectApiError) {
    if (error.status === 401) return '访问令牌无效或已过期。'
    if (error.status === 403) return '当前账号没有执行此操作的权限。'
    if (error.status === 503) return '后端账号认证尚未配置，请联系服务管理员。'
    if (error.status === 404) return '项目不存在，或当前账号无权访问。'
  }
  if (error instanceof TypeError) return '无法连接项目服务，请检查 API 地址与网络状态。'
  return fallback
}
function explainWorkflowError(error: unknown) {
  if (error instanceof WorkflowApiError) {
    if (error.code === 'WORKFLOW_REVISION_CONFLICT') return '此工作流已被其他操作更新。请返回所属对象重新打开，再处理未保存的修改。'
    if (error.code === 'WORKFLOW_VALIDATION_BLOCKED') return '当前工作流含有结构问题，修复并保存后才能创建版本。'
    if (error.status === 401) return '访问令牌无效或已过期。'
    if (error.status === 403) return '当前对象成员没有创建或保存工作流的权限。'
    if (error.status === 404) return '工作流不存在，或当前账号无权访问。'
    if (error.status === 503) return '工作流服务或账号认证尚未配置。'
    if (error.status === 422) return '工作流数据未通过请求校验，请检查名称、画布结构或版本要求。'
  }
  if (error instanceof TypeError) return '无法连接工作流服务，请检查 API 地址与网络状态。'
  return '工作流操作失败，请稍后重试并检查服务日志。'
}
function projectRunStatusLabel(status: ProjectListItem['recent_run_status']) {
  if (!status) return '暂无运行'
  return ({ queued: '排队中', running: '运行中', succeeded: '成功', failed: '失败' } as const)[status]
}
function projectPermissionLabel(role: string) {
  if (role === 'operator') return '可编辑'
  if (role === 'viewer') return '只读'
  return '权限未说明'
}
function date(value: string) {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '时间未提供' : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' }).format(parsed)
}
function dateTime(value: string) {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '时间未提供' : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(parsed)
}
async function createProjectRequest(config: ApiConfig, input: ProjectCreateInput) { return createProject(config, input) }
function readPageFromHash(): Page {
  const route = window.location.hash.replace(/^#\/?/, '').split('/')[0]
  return route === 'templates' || route === 'agent' || route === 'settings' ? route : 'workbench'
}
function readDeskTabFromHash(): DeskTab { return window.location.hash.includes('/reproductions') ? 'reproductions' : 'projects' }
function readWorkbenchHeroVariant(): 'fluid' | 'lab' | 'molecule' | 'data' {
  const query = window.location.hash.split('?')[1] || ''
  const value = new URLSearchParams(query).get('hero')
  return value === 'lab' || value === 'molecule' || value === 'data' || value === 'fluid' ? value : 'fluid'
}
function readProjectRouteFromHash() {
  const route = window.location.hash.split('?')[0]
  const match = route.match(/^#\/?workbench\/projects\/([^/]+)(?:\/workflows\/([^/]+))?\/?$/)
  if (!match || match[1].startsWith('__preview')) return { projectId: null, workflowId: null }
  try {
    return {
      projectId: decodeURIComponent(match[1]),
      workflowId: match[2] ? decodeURIComponent(match[2]) : null,
    }
  } catch {
    return { projectId: null, workflowId: null }
  }
}
function readReproductionTaskRouteFromHash() {
  const route = window.location.hash.split('?')[0]
  const match = route.match(/^#\/?workbench\/reproductions\/([^/]+)(?:\/workflows\/([^/]+))?\/?$/)
  if (!match || match[1].startsWith('__preview')) return { taskId: null, workflowId: null }
  try {
    return {
      taskId: decodeURIComponent(match[1]),
      workflowId: match[2] ? decodeURIComponent(match[2]) : null,
    }
  } catch {
    return { taskId: null, workflowId: null }
  }
}
function readReproductionProjectFilterFromHash() {
  const query = window.location.hash.split('?')[1] ?? ''
  return new URLSearchParams(query).get('project') ?? ''
}
function readSettingsTabFromHash(): SettingsTab {
  const route = window.location.hash.replace(/^#\/?/, '').split('/')[1]
  return route === 'preferences' || route === 'notifications' || route === 'security' || route === 'workspace' || route === 'service' ? route : 'profile'
}

export default App
