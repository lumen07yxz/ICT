import type { ProjectCreateInput, ProjectDetail, ProjectListItem } from './projects'
import { parseWorkflowComponent, parseWorkflowValidation, type WorkflowComponent, type WorkflowDetail, type WorkflowGraph, type WorkflowSummary, type WorkflowValidation } from './workflows'
import type { ReproductionTask, ReproductionTaskCreateInput } from './reproductions'

export type LocalSyncStatus = 'local_only' | 'pending' | 'partial' | 'synced' | 'failed' | 'conflict' | 'needs_review'

export interface LocalProject extends ProjectListItem {
  source: 'local'
  sync_state: LocalSyncStatus
  platform_project_id?: string | null
}

export interface LocalWorkflowTemplate {
  template_id: string
  version: string
  name: string
  category: string
  summary: string
  description: string
  component_ids: string[]
  workflow_preview?: LocalWorkflowTemplatePreview
  execution_target: 'local'
  requires_network: false
}

export interface LocalWorkflowTemplatePreviewNode {
  id: string
  title: string
  category: string
  position: { x: number; y: number }
}

export interface LocalWorkflowTemplatePreviewEdge {
  source: string
  target: string
}

export interface LocalWorkflowTemplatePreview {
  nodes: LocalWorkflowTemplatePreviewNode[]
  edges: LocalWorkflowTemplatePreviewEdge[]
}

export interface LocalProjectDetail extends ProjectDetail {
  updated_at: string
  workflow_count: number
  dataset_version_count: number
  recent_run_status: ProjectListItem['recent_run_status']
  last_activity_at: string | null
  source: 'local'
  sync_state: LocalSyncStatus
  platform_project_id?: string | null
}

export interface LocalWorkflowSyncState {
  workflow_id: string
  status: LocalSyncStatus
  platform_workflow_id: string | null
  synced_revision: number | null
  source_revision: number | null
  error_code: string | null
  updated_at: string | null
}

export interface LocalProjectSyncState {
  project_id: string
  status: LocalSyncStatus
  platform_project_id: string | null
  error_code: string | null
  updated_at: string | null
  workflows: LocalWorkflowSyncState[]
}

export type LocalSyncWriteStatus = Exclude<LocalSyncStatus, 'local_only'>

export interface LocalWorkflowSummary extends WorkflowSummary {
  source: 'local'
  sync_state: 'local_only'
}

export interface LocalWorkflowDetail extends WorkflowDetail {
  source: 'local'
  sync_state: 'local_only'
}

export interface LocalReproductionTask extends ReproductionTask {
  assessment_state: 'not_assessed'
  sync_state: 'local_only'
}

export type LocalReproductionCreateInput = ReproductionTaskCreateInput

export interface LocalRuntimeHealth {
  status: 'ok'
  mode: 'local'
  platform_required: false
}

export interface LocalArtifactHandle {
  artifact_id: string
  sha256: string
  file_name: string
  media_type: string
  size_bytes: number
  storage_key: string
  provenance: string
  authorization_status: string
  created_at: string
}

export interface LocalCsvPreflightReport {
  report_type: 'csv_manifest_structural_preflight'
  label: '结构预检，非科研结果'
  research_result: false
  status: 'success' | 'warning' | 'blocker'
  input: {
    artifact_id: string
    sha256: string
    size_bytes: number
    provenance: string
    authorization_status: string
  }
  row_count: number
  columns: string[]
  split_counts: Record<string, number>
  label_category_count: number
  issues: Array<{
    code: string
    message: string
    count: number
    line_numbers: number[]
    field: string | null
    severity: 'blocker' | 'warning'
    guidance: string
  }>
}

export interface LocalCsvDescriptiveSummaryReport {
  report_type: 'csv_descriptive_summary'
  label: '探索性描述统计摘要，非科研结论'
  research_result: false
  summary_method: 'ict.csv-descriptive-summary.v1'
  missing_definition: string
  input: {
    artifact_id: string
    sha256: string
    size_bytes: number
    provenance: string
    authorization_status: string
  }
  row_count: number
  column_count: number
  columns: Array<{
    name: string
    kind: 'numeric' | 'categorical' | 'all_missing'
    row_count: number
    missing_count: number
    missing_rate: number
    numeric_summary: { minimum: number; maximum: number; mean: number } | null
    category_summary: {
      distinct_value_count: number | null
      top_values: Array<{ value: string; count: number }>
      truncated: boolean
    } | null
  }>
  limitations: string[]
}

export interface LocalCsvFolderQualityReport {
  report_type: 'csv_folder_quality_v1'
  label: '本机 CSV 文件夹质量检查报告，非科研结果'
  research_result: false
  rules_version: 'ict.csv-folder-quality.v1'
  collection: {
    folder_name: string
    collection_sha256: string
    file_count: number
    ignored_file_count: number
    total_size_bytes: number
  }
  rules: {
    required_columns: string[]
    unique_key_columns: string[]
    max_missing_rate: number
  }
  summary: {
    status: 'passed' | 'warning' | 'blocked'
    file_count: number
    passed_count: number
    warning_count: number
    blocked_count: number
  }
  files: Array<{
    relative_path: string
    artifact_id: string
    sha256: string
    size_bytes: number
    row_count: number
    column_count: number
    columns: string[]
    missing_counts: Array<{ field: string; count: number; rate: number }>
    duplicate_key_count: number
    status: 'passed' | 'warning' | 'blocked'
    issues: Array<{ code: string; severity: 'warning' | 'blocker'; count: number; fields: string[] }>
  }>
}

export interface LocalCrossrefMetadataReport {
  report_type: 'crossref_doi_metadata'
  label: 'Crossref 公开文献元数据，非科研结果'
  research_result: false
  source_name: 'Crossref REST API'
  source_url: string
  retrieved_at: string
  doi: string
  title: string | null
  authors: Array<{ name: string; orcid?: string }>
  container_title: string | null
  publisher: string | null
  published_date: string | null
  work_type: string | null
  landing_page: string | null
  verification_note: string
}

export interface LocalWorkflowRunSummary {
  run_id: string
  workflow_id: string
  status: 'queued' | 'running' | 'waiting_external' | 'succeeded' | 'partially_succeeded' | 'failed' | 'cancelled'
  plan_hash: string
  recovered_from_run_id?: string | null
  target_node_ids: string[]
  error_code?: string | null
  created_at?: string
  started_at?: string | null
  finished_at?: string | null
}

export interface LocalWorkflowNodeRun {
  node_id: string
  component_id: string
  status: string
  error_code: string | null
  output: Record<string, unknown> | null
  updated_at: string
}

export interface LocalExecutionPlanNode {
  id: string
  component_id: string
  parameters: Record<string, unknown>
}

export interface LocalExecutionPlan {
  schema_version: string
  workflow_schema_version: string
  plan_hash: string
  target_node_ids: string[]
  nodes: LocalExecutionPlanNode[]
  edges?: Array<{ source: string; target: string; source_handle: string; target_handle: string }>
}

export interface LocalWorkflowRunDetail extends LocalWorkflowRunSummary {
  execution_plan: LocalExecutionPlan
  error_code: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  node_runs: LocalWorkflowNodeRun[]
  events: Array<{
    sequence: number
    node_id: string | null
    status: string
    error_code: string | null
    occurred_at: string
  }>
}

export class LocalRuntimeApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string) {
    super(`Local runtime request failed (${status}: ${code})`)
    this.status = status
    this.code = code
    this.name = 'LocalRuntimeApiError'
  }
}

interface Session {
  token: string
  expiresAt: number
}

let currentSession: Session | null = null

function localRuntimeBaseUrl(): string {
  const configured = import.meta.env.VITE_LOCAL_RUNTIME_URL
  const loopbackHosts = new Set(['127.0.0.1', 'localhost', '[::1]'])
  // Packaged desktop UI and local runtime share one origin; Vite preview overrides this via env.
  const fallback = !import.meta.env.DEV && loopbackHosts.has(window.location.hostname)
    ? window.location.origin
    : 'http://127.0.0.1:8767'
  return (configured?.trim() || fallback).replace(/\/$/, '')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isLocalSyncStatus(value: unknown): value is LocalSyncStatus {
  return typeof value === 'string' && ['local_only', 'pending', 'partial', 'synced', 'failed', 'conflict', 'needs_review'].includes(value)
}

function parseLocalProject(value: unknown): LocalProject {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.name !== 'string' ||
      typeof value.domain !== 'string' || typeof value.role !== 'string' || value.visibility !== 'private' ||
      typeof value.created_at !== 'string' || typeof value.updated_at !== 'string' ||
      typeof value.description !== 'string' || !Number.isInteger(value.workflow_count) ||
      !Number.isInteger(value.dataset_version_count) ||
      !(value.recent_run_status === null || ['queued', 'running', 'succeeded', 'failed'].includes(String(value.recent_run_status))) ||
      !(value.last_activity_at === null || typeof value.last_activity_at === 'string') ||
      value.source !== 'local' || !isLocalSyncStatus(value.sync_state) ||
      !(value.platform_project_id === undefined || value.platform_project_id === null || typeof value.platform_project_id === 'string')) {
    throw new Error('Invalid local project response')
  }
  return value as unknown as LocalProject
}

function parseLocalProjectDetail(value: unknown): LocalProjectDetail {
  const project = parseLocalProject(value)
  if (!isRecord(value) || !Array.isArray(value.datasets) || !Array.isArray(value.pipeline_templates)) {
    throw new Error('Invalid local project detail response')
  }
  return project as LocalProjectDetail
}

function isLocalReproductionStatus(value: unknown): value is ReproductionTask['status'] {
  return typeof value === 'string' && [
    'preparation', 'insufficient_conditions', 'ready_to_run', 'running',
    'awaiting_review', 'conforms', 'differs', 'undetermined',
  ].includes(value)
}

function parseLocalReproductionTask(value: unknown): LocalReproductionTask {
  if (!isRecord(value) || typeof value.id !== 'string' || !value.id.startsWith('local-reproduction-') ||
      value.workspace_id !== 'local' || !(typeof value.linked_project_id === 'string' || value.linked_project_id === null) ||
      typeof value.title !== 'string' || (value.kind !== 'paper' && value.kind !== 'experiment') ||
      typeof value.source !== 'string' || typeof value.claim !== 'string' ||
      !(value.baseline === null || isRecord(value.baseline)) ||
      !(typeof value.criteria_version === 'string' || value.criteria_version === null) ||
      !isLocalReproductionStatus(value.status) || value.assessment_state !== 'not_assessed' ||
      value.sync_state !== 'local_only' || typeof value.created_by !== 'string' ||
      typeof value.updated_by !== 'string' || typeof value.created_at !== 'string' ||
      typeof value.updated_at !== 'string') {
    throw new Error('Invalid local reproduction task response')
  }
  return value as unknown as LocalReproductionTask
}

function parseLocalWorkflow(value: unknown, projectId?: string): LocalWorkflowSummary {
  const projectOwner = isRecord(value) && value.owner_type === 'project' &&
    typeof value.project_id === 'string' && value.project_id === value.owner_id && value.reproduction_task_id === null
  const reproductionOwner = isRecord(value) && value.owner_type === 'reproduction' &&
    value.project_id === null && typeof value.reproduction_task_id === 'string' &&
    value.reproduction_task_id === value.owner_id
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.workspace_id !== 'string' ||
      typeof value.owner_id !== 'string' || (!projectOwner && !reproductionOwner) ||
      (projectId !== undefined && (!projectOwner || value.project_id !== projectId)) ||
      typeof value.name !== 'string' || typeof value.description !== 'string' ||
      !Number.isInteger(value.revision) || !Number.isInteger(value.current_version) ||
      typeof value.created_at !== 'string' || typeof value.updated_at !== 'string' ||
      value.source !== 'local' || value.sync_state !== 'local_only') {
    throw new Error('Invalid local workflow response')
  }
  return value as unknown as LocalWorkflowSummary
}

function parseLocalWorkflowDetail(value: unknown): LocalWorkflowDetail {
  const workflow = parseLocalWorkflow(value)
  if (!isRecord(value) || !isRecord(value.graph) || value.graph.schema_version !== 'ict.workflow.v1' ||
      !Array.isArray(value.graph.nodes) || !Array.isArray(value.graph.edges) || typeof value.can_edit !== 'boolean') {
    throw new Error('Invalid local workflow detail response')
  }
  return workflow as LocalWorkflowDetail
}

function parseLocalWorkflowTemplatePreview(value: unknown): LocalWorkflowTemplatePreview {
  if (!isRecord(value) || !Array.isArray(value.nodes) || value.nodes.length === 0 || !Array.isArray(value.edges)) {
    throw new Error('Invalid local workflow template preview')
  }

  const nodeIds = new Set<string>()
  const nodes = value.nodes.map((item) => {
    if (!isRecord(item) || typeof item.id !== 'string' || !item.id.trim() || nodeIds.has(item.id) ||
        typeof item.title !== 'string' || typeof item.category !== 'string' || !isRecord(item.position) ||
        typeof item.position.x !== 'number' || !Number.isFinite(item.position.x) ||
        typeof item.position.y !== 'number' || !Number.isFinite(item.position.y)) {
      throw new Error('Invalid local workflow template preview node')
    }
    nodeIds.add(item.id)
    return {
      id: item.id,
      title: item.title,
      category: item.category,
      position: { x: item.position.x, y: item.position.y },
    }
  })

  const edges = value.edges.map((item) => {
    if (!isRecord(item) || typeof item.source !== 'string' || typeof item.target !== 'string' ||
        item.source === item.target || !nodeIds.has(item.source) || !nodeIds.has(item.target)) {
      throw new Error('Invalid local workflow template preview edge')
    }
    return { source: item.source, target: item.target }
  })
  return { nodes, edges }
}

function parseLocalWorkflowTemplate(value: unknown): LocalWorkflowTemplate {
  if (!isRecord(value) || typeof value.template_id !== 'string' || typeof value.version !== 'string' ||
      typeof value.name !== 'string' || typeof value.category !== 'string' ||
      typeof value.summary !== 'string' || typeof value.description !== 'string' ||
      !Array.isArray(value.component_ids) || !value.component_ids.every((id) => typeof id === 'string') ||
      value.execution_target !== 'local' || value.requires_network !== false) {
    throw new Error('Invalid local workflow template response')
  }
  const workflowPreview = value.workflow_preview === undefined
    ? undefined
    : parseLocalWorkflowTemplatePreview(value.workflow_preview)
  return { ...value, workflow_preview: workflowPreview } as unknown as LocalWorkflowTemplate
}

async function responseError(response: Response): Promise<LocalRuntimeApiError> {
  let code = 'LOCAL_REQUEST_FAILED'
  try {
    const payload: unknown = await response.json()
    if (isRecord(payload) && isRecord(payload.error) && typeof payload.error.code === 'string') {
      code = payload.error.code
    }
  } catch (error) {
    console.warn('本机运行时错误响应无法解析，将使用 HTTP 状态码。', error)
  }
  return new LocalRuntimeApiError(response.status, code)
}

async function openLocalSession(): Promise<Session> {
  const response = await fetch(`${localRuntimeBaseUrl()}/api/v1/local/session`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw await responseError(response)
  const payload: unknown = await response.json()
  if (!isRecord(payload) || typeof payload.token !== 'string' ||
      !Number.isInteger(payload.expires_in_seconds) || (payload.expires_in_seconds as number) < 1) {
    throw new Error('Invalid local runtime session response')
  }
  const expiresAt = Date.now() + (payload.expires_in_seconds as number) * 1000
  currentSession = { token: payload.token, expiresAt }
  return currentSession
}

async function localSession(forceRefresh = false): Promise<Session> {
  if (!forceRefresh && currentSession && currentSession.expiresAt - Date.now() > 30_000) return currentSession
  return openLocalSession()
}

async function localRequest(path: string, init: RequestInit = {}, retried = false): Promise<unknown> {
  const session = await localSession()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  headers.set('X-ICT-Local-Token', session.token)
  if (init.body !== undefined && !(init.body instanceof Blob) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${localRuntimeBaseUrl()}${path}`, { ...init, headers })
  if (response.status === 401 && !retried) {
    currentSession = null
    await localSession(true)
    return localRequest(path, init, true)
  }
  if (!response.ok) throw await responseError(response)
  return await response.json() as unknown
}

export async function getLocalRuntimeHealth(): Promise<LocalRuntimeHealth> {
  const response = await fetch(`${localRuntimeBaseUrl()}/health`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw await responseError(response)
  const value: unknown = await response.json()
  if (!isRecord(value) || value.status !== 'ok' || value.mode !== 'local' || value.platform_required !== false) {
    throw new Error('Invalid local runtime health response')
  }
  return { status: 'ok', mode: 'local', platform_required: false }
}

export async function listLocalWorkflowComponents(): Promise<WorkflowComponent[]> {
  const value = await localRequest('/api/v1/local/workflow-components')
  if (!Array.isArray(value)) throw new Error('Invalid local workflow component catalog response')
  return value.map(parseWorkflowComponent)
}

export async function listLocalWorkflowTemplates(): Promise<LocalWorkflowTemplate[]> {
  const value = await localRequest('/api/v1/local/workflow-templates')
  if (!Array.isArray(value)) throw new Error('Invalid local workflow template catalog response')
  return value.map(parseLocalWorkflowTemplate)
}

export async function listLocalProjects(): Promise<LocalProject[]> {
  const value = await localRequest('/api/v1/local/projects')
  if (!Array.isArray(value)) throw new Error('Invalid local project list response')
  return value.map(parseLocalProject)
}

export async function createLocalProject(input: ProjectCreateInput): Promise<LocalProjectDetail> {
  const value = await localRequest('/api/v1/local/projects', {
    method: 'POST',
    body: JSON.stringify(input),
  })
  return parseLocalProjectDetail(value)
}

export async function getLocalProject(projectId: string): Promise<LocalProjectDetail> {
  const value = await localRequest(`/api/v1/local/projects/${encodeURIComponent(projectId)}`)
  return parseLocalProjectDetail(value)
}

function parseLocalProjectSyncState(value: unknown): LocalProjectSyncState {
  if (!isRecord(value) || typeof value.project_id !== 'string' || !isLocalSyncStatus(value.status) ||
      !(value.platform_project_id === null || typeof value.platform_project_id === 'string') ||
      !(value.error_code === null || typeof value.error_code === 'string') ||
      !(value.updated_at === null || typeof value.updated_at === 'string') || !Array.isArray(value.workflows)) {
    throw new Error('Invalid local project sync state response')
  }
  const workflows = value.workflows.map((item): LocalWorkflowSyncState => {
    if (!isRecord(item) || typeof item.workflow_id !== 'string' || !isLocalSyncStatus(item.status) ||
        !(item.platform_workflow_id === null || typeof item.platform_workflow_id === 'string') ||
        !(item.synced_revision === null || Number.isInteger(item.synced_revision)) ||
        !(item.source_revision === null || Number.isInteger(item.source_revision)) ||
        !(item.error_code === null || typeof item.error_code === 'string') ||
        !(item.updated_at === null || typeof item.updated_at === 'string')) {
      throw new Error('Invalid local workflow sync state response')
    }
    return item as unknown as LocalWorkflowSyncState
  })
  return { ...value, workflows } as unknown as LocalProjectSyncState
}

export async function getLocalProjectSyncState(projectId: string): Promise<LocalProjectSyncState> {
  const value = await localRequest(`/api/v1/local/projects/${encodeURIComponent(projectId)}/sync-state`)
  return parseLocalProjectSyncState(value)
}

export async function beginLocalProjectSync(projectId: string, allowPendingRetry: boolean): Promise<LocalProjectSyncState> {
  const value = await localRequest(`/api/v1/local/projects/${encodeURIComponent(projectId)}/sync-state/start`, {
    method: 'POST',
    body: JSON.stringify({ allow_pending_retry: allowPendingRetry }),
  })
  return parseLocalProjectSyncState(value)
}

export async function saveLocalProjectSyncState(
  projectId: string,
  update: { status: LocalSyncWriteStatus; platform_project_id?: string | null; error_code?: string | null },
): Promise<LocalProjectSyncState> {
  const value = await localRequest(`/api/v1/local/projects/${encodeURIComponent(projectId)}/sync-state`, {
    method: 'PUT',
    body: JSON.stringify(update),
  })
  return parseLocalProjectSyncState(value)
}

export async function saveLocalWorkflowSyncState(
  projectId: string,
  workflowId: string,
  update: {
    status: Exclude<LocalSyncWriteStatus, 'partial'>
    platform_workflow_id?: string | null
    synced_revision?: number | null
    source_revision?: number | null
    error_code?: string | null
  },
): Promise<LocalProjectSyncState> {
  const value = await localRequest(
    `/api/v1/local/projects/${encodeURIComponent(projectId)}/workflows/${encodeURIComponent(workflowId)}/sync-state`,
    { method: 'PUT', body: JSON.stringify(update) },
  )
  return parseLocalProjectSyncState(value)
}

export async function listLocalProjectWorkflows(projectId: string): Promise<LocalWorkflowSummary[]> {
  const value = await localRequest(`/api/v1/local/projects/${encodeURIComponent(projectId)}/workflows`)
  if (!Array.isArray(value)) throw new Error('Invalid local project workflow list response')
  return value.map((item) => parseLocalWorkflow(item, projectId))
}

export async function createLocalProjectWorkflow(
  projectId: string,
  input: Pick<ProjectCreateInput, 'name' | 'description'>,
): Promise<LocalWorkflowDetail> {
  const value = await localRequest(`/api/v1/local/projects/${encodeURIComponent(projectId)}/workflows`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
  const workflow = parseLocalWorkflowDetail(value)
  if (workflow.project_id !== projectId) throw new Error('Local workflow belongs to a different project')
  return workflow
}

export async function createLocalProjectWorkflowFromTemplate(
  projectId: string,
  template: Pick<LocalWorkflowTemplate, 'template_id' | 'version'>,
): Promise<LocalWorkflowDetail> {
  // The catalog object also contains display metadata; send only fields accepted by the runtime contract.
  const requestBody = { template_id: template.template_id, version: template.version }
  const value = await localRequest(
    `/api/v1/local/projects/${encodeURIComponent(projectId)}/workflows/from-template`,
    { method: 'POST', body: JSON.stringify(requestBody) },
  )
  const workflow = parseLocalWorkflowDetail(value)
  if (workflow.project_id !== projectId || workflow.graph.nodes.length === 0) {
    throw new Error('Invalid local workflow template instance')
  }
  return workflow
}

export async function listLocalReproductionTasks(): Promise<LocalReproductionTask[]> {
  const value = await localRequest('/api/v1/local/reproductions')
  if (!Array.isArray(value)) throw new Error('Invalid local reproduction task list response')
  return value.map(parseLocalReproductionTask)
}

export async function createLocalReproductionTask(
  input: LocalReproductionCreateInput,
): Promise<LocalReproductionTask> {
  const value = await localRequest('/api/v1/local/reproductions', {
    method: 'POST',
    body: JSON.stringify(input),
  })
  return parseLocalReproductionTask(value)
}

export async function getLocalReproductionTask(taskId: string): Promise<LocalReproductionTask> {
  const value = await localRequest(`/api/v1/local/reproductions/${encodeURIComponent(taskId)}`)
  return parseLocalReproductionTask(value)
}

export async function listLocalReproductionWorkflows(taskId: string): Promise<LocalWorkflowSummary[]> {
  const value = await localRequest(`/api/v1/local/reproductions/${encodeURIComponent(taskId)}/workflows`)
  if (!Array.isArray(value)) throw new Error('Invalid local reproduction workflow list response')
  return value.map((item) => parseLocalWorkflow(item))
}

export async function createLocalReproductionWorkflow(
  taskId: string,
  input: Pick<ProjectCreateInput, 'name' | 'description'>,
): Promise<LocalWorkflowDetail> {
  const value = await localRequest(`/api/v1/local/reproductions/${encodeURIComponent(taskId)}/workflows`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
  const workflow = parseLocalWorkflowDetail(value)
  if (workflow.owner_type !== 'reproduction' || workflow.reproduction_task_id !== taskId) {
    throw new Error('Local workflow belongs to a different reproduction task')
  }
  return workflow
}

export async function getLocalWorkflow(workflowId: string): Promise<LocalWorkflowDetail> {
  const value = await localRequest(`/api/v1/local/workflows/${encodeURIComponent(workflowId)}`)
  return parseLocalWorkflowDetail(value)
}

export async function importLocalCsv(file: Blob & { name: string }): Promise<LocalArtifactHandle> {
  const value = await localRequest('/api/v1/local/artifacts', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/octet-stream',
      'X-Artifact-File-Name': encodeURIComponent(file.name),
      'X-ICT-Local-Consent': 'confirmed',
    },
    body: file,
  })
  if (!isRecord(value) || typeof value.artifact_id !== 'string' || typeof value.sha256 !== 'string' ||
      typeof value.size_bytes !== 'number' || value.provenance !== 'user_selected_local_file') {
    throw new Error('Invalid local artifact response')
  }
  return value as unknown as LocalArtifactHandle
}

export async function getLocalCsvPreflightReport(artifactId: string): Promise<LocalCsvPreflightReport> {
  const value = await localRequest(
    `/api/v1/local/artifacts/${encodeURIComponent(artifactId)}/csv-preflight-report`,
  )
  if (!isRecord(value) || value.report_type !== 'csv_manifest_structural_preflight' ||
      value.research_result !== false || value.label !== '结构预检，非科研结果' ||
      !Array.isArray(value.columns) || !Array.isArray(value.issues) || !isRecord(value.split_counts) ||
      typeof value.row_count !== 'number') {
    throw new Error('Invalid local CSV preflight report response')
  }
  return value as unknown as LocalCsvPreflightReport
}

export async function getLocalCsvDescriptiveSummaryReport(artifactId: string): Promise<LocalCsvDescriptiveSummaryReport> {
  const value = await localRequest(
    `/api/v1/local/artifacts/${encodeURIComponent(artifactId)}/csv-descriptive-summary`,
  )
  if (!isRecord(value) || value.report_type !== 'csv_descriptive_summary' ||
      value.research_result !== false || value.label !== '探索性描述统计摘要，非科研结论' ||
      value.summary_method !== 'ict.csv-descriptive-summary.v1' ||
      typeof value.missing_definition !== 'string' || typeof value.row_count !== 'number' ||
      typeof value.column_count !== 'number' || !Array.isArray(value.columns) ||
      !Array.isArray(value.limitations)) {
    throw new Error('Invalid local CSV descriptive summary response')
  }
  return value as unknown as LocalCsvDescriptiveSummaryReport
}

export async function getLocalCsvFolderQualityReport(artifactId: string): Promise<LocalCsvFolderQualityReport> {
  const value = await localRequest(
    `/api/v1/local/artifacts/${encodeURIComponent(artifactId)}/csv-folder-quality-report`,
  )
  if (!isRecord(value) || value.report_type !== 'csv_folder_quality_v1' ||
      value.research_result !== false || value.label !== '本机 CSV 文件夹质量检查报告，非科研结果' ||
      value.rules_version !== 'ict.csv-folder-quality.v1' || !isRecord(value.collection) ||
      !isRecord(value.rules) || !isRecord(value.summary) || !Array.isArray(value.files)) {
    throw new Error('Invalid local CSV folder quality report response')
  }
  return value as unknown as LocalCsvFolderQualityReport
}

export async function getLocalCrossrefMetadataReport(artifactId: string): Promise<LocalCrossrefMetadataReport> {
  const value = await localRequest(
    `/api/v1/local/artifacts/${encodeURIComponent(artifactId)}/crossref-metadata`,
  )
  if (!isRecord(value) || value.report_type !== 'crossref_doi_metadata' ||
      value.research_result !== false || value.label !== 'Crossref 公开文献元数据，非科研结果' ||
      value.source_name !== 'Crossref REST API' || typeof value.source_url !== 'string' ||
      typeof value.doi !== 'string' || typeof value.retrieved_at !== 'string' ||
      !Array.isArray(value.authors) || typeof value.verification_note !== 'string') {
    throw new Error('Invalid local Crossref metadata response')
  }
  return value as unknown as LocalCrossrefMetadataReport
}

export async function saveLocalWorkflowDraft(
  workflowId: string,
  revision: number,
  graph: WorkflowGraph,
  metadata?: Pick<ProjectCreateInput, 'name' | 'description'>,
): Promise<{ workflow_id: string; revision: number }> {
  const value = await localRequest(`/api/v1/local/workflows/${encodeURIComponent(workflowId)}/draft`, {
    method: 'PUT',
    body: JSON.stringify({ revision, graph, ...metadata }),
  })
  if (!isRecord(value) || value.workflow_id !== workflowId || value.revision !== revision) {
    throw new Error('Invalid local workflow draft response')
  }
  return { workflow_id: workflowId, revision }
}

export async function getLocalWorkflowDraft(workflowId: string): Promise<{ revision: number; graph: WorkflowGraph }> {
  const value = await localRequest(`/api/v1/local/workflows/${encodeURIComponent(workflowId)}/draft`)
  if (!isRecord(value) || !Number.isInteger(value.revision) || !isRecord(value.graph)) {
    throw new Error('Invalid local workflow draft response')
  }
  return { revision: value.revision as number, graph: value.graph as unknown as WorkflowGraph }
}

export async function validateLocalWorkflow(
  workflowId: string,
  revision: number,
  graph: WorkflowGraph,
): Promise<WorkflowValidation> {
  const value = await localRequest(`/api/v1/local/workflows/${encodeURIComponent(workflowId)}/validations`, {
    method: 'POST',
    body: JSON.stringify({ revision, graph }),
  })
  return parseWorkflowValidation(value)
}

export async function submitLocalWorkflowRun(
  workflowId: string,
  targetNodeIds: string[],
  expectedRevision?: number,
): Promise<LocalWorkflowRunSummary> {
  const value = await localRequest(`/api/v1/local/workflows/${encodeURIComponent(workflowId)}/runs`, {
    method: 'POST',
    body: JSON.stringify({ target_node_ids: targetNodeIds, expected_revision: expectedRevision }),
  })
  if (!isRecord(value) || typeof value.run_id !== 'string' || typeof value.workflow_id !== 'string' ||
      typeof value.plan_hash !== 'string' || !Array.isArray(value.target_node_ids)) {
    throw new Error('Invalid local workflow run response')
  }
  return value as unknown as LocalWorkflowRunSummary
}

export async function getLocalWorkflowRun(runId: string): Promise<LocalWorkflowRunDetail> {
  const value = await localRequest(`/api/v1/local/runs/${encodeURIComponent(runId)}`)
  if (!isRecord(value) || typeof value.run_id !== 'string' || !Array.isArray(value.node_runs) || !Array.isArray(value.events)) {
    throw new Error('Invalid local workflow run detail response')
  }
  return value as unknown as LocalWorkflowRunDetail
}

export async function listLocalWorkflowRuns(workflowId: string): Promise<LocalWorkflowRunSummary[]> {
  const value = await localRequest(`/api/v1/local/workflows/${encodeURIComponent(workflowId)}/runs`)
  if (!Array.isArray(value)) throw new Error('Invalid local workflow run list response')
  return value as LocalWorkflowRunSummary[]
}

export interface LocalWorkflowRecoveryResult extends LocalWorkflowRunSummary {
  recovered_from_run_id: string
  restored_node_ids: string[]
  rerun_node_ids: string[]
}

export async function recoverLocalWorkflowRun(runId: string): Promise<LocalWorkflowRecoveryResult> {
  const value = await localRequest(`/api/v1/local/runs/${encodeURIComponent(runId)}/recover`, { method: 'POST' })
  if (!isRecord(value) || typeof value.run_id !== 'string' || typeof value.workflow_id !== 'string' ||
      typeof value.plan_hash !== 'string' || typeof value.recovered_from_run_id !== 'string' ||
      !Array.isArray(value.target_node_ids) || !Array.isArray(value.restored_node_ids) ||
      !Array.isArray(value.rerun_node_ids)) {
    throw new Error('Invalid local workflow recovery response')
  }
  return value as unknown as LocalWorkflowRecoveryResult
}

export async function cancelLocalWorkflowRun(runId: string): Promise<void> {
  await localRequest(`/api/v1/local/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' })
}

export function clearLocalRuntimeSession(): void {
  currentSession = null
}
