import type { ApiConfig } from './projects'

export type ReproductionKind = 'paper' | 'experiment'
export type ReproductionStatus =
  | 'preparation'
  | 'insufficient_conditions'
  | 'ready_to_run'
  | 'running'
  | 'awaiting_review'
  | 'conforms'
  | 'differs'
  | 'undetermined'

export interface ReproductionTask {
  id: string
  workspace_id: string
  linked_project_id: string | null
  title: string
  kind: ReproductionKind
  source: string
  claim: string
  baseline: Record<string, unknown> | null
  criteria_version: string | null
  status: ReproductionStatus
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
}

export interface ReproductionTaskCreateInput {
  title: string
  kind: ReproductionKind
  source: string
  claim: string
  baseline: Record<string, unknown> | null
  criteria_version: string | null
  linked_project_id: string | null
}

export interface ReproductionTaskFilters {
  kind?: ReproductionKind
  status?: ReproductionStatus
  linked_project_id?: string
}

export class ReproductionApiError extends Error {
  readonly status: number

  constructor(status: number) {
    super('Reproduction API request failed (' + status + ')')
    this.status = status
    this.name = 'ReproductionApiError'
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isKind(value: unknown): value is ReproductionKind {
  return value === 'paper' || value === 'experiment'
}

function isStatus(value: unknown): value is ReproductionStatus {
  return value === 'preparation' || value === 'insufficient_conditions' ||
    value === 'ready_to_run' || value === 'running' || value === 'awaiting_review' ||
    value === 'conforms' || value === 'differs' || value === 'undetermined'
}

function parseTask(value: unknown): ReproductionTask {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.workspace_id !== 'string' ||
      !(typeof value.linked_project_id === 'string' || value.linked_project_id === null) ||
      typeof value.title !== 'string' || !isKind(value.kind) || typeof value.source !== 'string' ||
      typeof value.claim !== 'string' || !(value.baseline === null || isRecord(value.baseline)) ||
      !(typeof value.criteria_version === 'string' || value.criteria_version === null) ||
      !isStatus(value.status) || typeof value.created_by !== 'string' ||
      typeof value.updated_by !== 'string' || typeof value.created_at !== 'string' ||
      typeof value.updated_at !== 'string') {
    throw new Error('Invalid reproduction task response')
  }

  return {
    id: value.id,
    workspace_id: value.workspace_id,
    linked_project_id: value.linked_project_id,
    title: value.title,
    kind: value.kind,
    source: value.source,
    claim: value.claim,
    baseline: value.baseline,
    criteria_version: value.criteria_version,
    status: value.status,
    created_by: value.created_by,
    updated_by: value.updated_by,
    created_at: value.created_at,
    updated_at: value.updated_at,
  }
}

async function request(
  path: string,
  config: ApiConfig,
  options: { signal?: AbortSignal; body?: ReproductionTaskCreateInput } = {},
): Promise<unknown> {
  const baseUrl = config.baseUrl.trim().replace(/\/+$/, '')
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (config.token.trim()) headers.Authorization = `Bearer ${config.token.trim()}`
  if (options.body) headers['Content-Type'] = 'application/json'

  const response = await fetch(`${baseUrl}${path}`, {
    method: options.body ? 'POST' : 'GET',
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  })
  if (!response.ok) throw new ReproductionApiError(response.status)
  return await response.json() as unknown
}

export async function listReproductionTasks(
  config: ApiConfig,
  filters: ReproductionTaskFilters = {},
  signal?: AbortSignal,
): Promise<ReproductionTask[]> {
  const query = new URLSearchParams()
  if (filters.kind) query.set('kind', filters.kind)
  if (filters.status) query.set('status', filters.status)
  if (filters.linked_project_id) query.set('linked_project_id', filters.linked_project_id)
  const suffix = query.size > 0 ? `?${query.toString()}` : ''
  const value = await request(`/api/v1/reproductions${suffix}`, config, { signal })
  if (!Array.isArray(value)) throw new Error('Invalid reproduction task list response')
  return value.map(parseTask)
}

export async function getReproductionTask(
  config: ApiConfig,
  taskId: string,
  signal?: AbortSignal,
): Promise<ReproductionTask> {
  const value = await request(`/api/v1/reproductions/${encodeURIComponent(taskId)}`, config, { signal })
  return parseTask(value)
}

export async function createReproductionTask(
  config: ApiConfig,
  payload: ReproductionTaskCreateInput,
): Promise<ReproductionTask> {
  const value = await request('/api/v1/reproductions', config, { body: payload })
  return parseTask(value)
}
