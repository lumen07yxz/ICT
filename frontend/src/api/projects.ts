export interface ProjectSummary {
  id: string
  name: string
  domain: string
  role: string
  visibility: 'private' | 'demo'
  created_at: string
}

export interface ProjectListItem extends ProjectSummary {
  description: string
  workflow_count: number
  dataset_version_count: number
  recent_run_status: 'queued' | 'running' | 'succeeded' | 'failed' | null
  last_activity_at: string | null
}

export interface DatasetResource {
  id: string
  version: string
  source: string
  license_status: string
  research_ready: boolean
}

export interface ProjectDetail extends ProjectSummary {
  description: string
  datasets: DatasetResource[]
  pipeline_templates: string[]
}

export interface TemplateFieldContract {
  type: 'string' | 'integer' | 'boolean'
  required: boolean
  minimum: number | null
  maximum: number | null
  const: string | number | boolean | null
}

export interface TemplateContract {
  template_id: string
  version: string
  manifest_sha256: string
  executor: string
  dataset_version: string
  permission_scope: string
  resource_limits: {
    max_concurrent_runs: number
    soft_timeout_seconds: number
    hard_timeout_seconds: number
  }
  inputs: Record<string, TemplateFieldContract>
  parameters: Record<string, TemplateFieldContract>
  outputs: Record<string, TemplateFieldContract>
  states: string[]
  error_codes: string[]
}

// Retained for callers of the project-scoped contract endpoint.
export type ProjectTemplateContract = TemplateContract

export interface ProjectCreateInput {
  name: string
  domain: string
  description: string
}

export interface ApiConfig {
  baseUrl: string
  token: string
}

export class ProjectApiError extends Error {
  readonly status: number
  readonly responseContentType: string

  constructor(status: number, responseContentType = '') {
    super('Project API request failed (' + status + ')')
    this.status = status
    this.responseContentType = responseContentType
    this.name = 'ProjectApiError'
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseProjectSummary(value: unknown): ProjectSummary {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.name !== 'string' ||
      typeof value.domain !== 'string' || typeof value.role !== 'string' ||
      (value.visibility !== 'private' && value.visibility !== 'demo') || typeof value.created_at !== 'string') {
    throw new Error('Invalid project response')
  }
  return {
    id: value.id,
    name: value.name,
    domain: value.domain,
    role: value.role,
    visibility: value.visibility,
    created_at: value.created_at,
  }
}

function parseProjectListItem(value: unknown): ProjectListItem {
  const summary = parseProjectSummary(value)
  if (!isRecord(value) || typeof value.description !== 'string' ||
      typeof value.workflow_count !== 'number' || !Number.isInteger(value.workflow_count) || value.workflow_count < 0 ||
      typeof value.dataset_version_count !== 'number' || !Number.isInteger(value.dataset_version_count) || value.dataset_version_count < 0 ||
      (value.recent_run_status !== null && !['queued', 'running', 'succeeded', 'failed'].includes(String(value.recent_run_status))) ||
      (value.last_activity_at !== null && typeof value.last_activity_at !== 'string')) {
    throw new Error('Invalid project list response')
  }
  return {
    ...summary,
    description: value.description,
    workflow_count: value.workflow_count as number,
    dataset_version_count: value.dataset_version_count as number,
    recent_run_status: value.recent_run_status as ProjectListItem['recent_run_status'],
    last_activity_at: value.last_activity_at as string | null,
  }
}

function parseProjectDetail(value: unknown): ProjectDetail {
  const summary = parseProjectSummary(value)
  if (!isRecord(value) || typeof value.description !== 'string' || !Array.isArray(value.datasets) ||
      !value.datasets.every((dataset) => isRecord(dataset) && typeof dataset.id === 'string' &&
        typeof dataset.version === 'string' && typeof dataset.source === 'string' &&
        typeof dataset.license_status === 'string' && typeof dataset.research_ready === 'boolean') ||
      !Array.isArray(value.pipeline_templates) || !value.pipeline_templates.every((item) => typeof item === 'string')) {
    throw new Error('Invalid project response')
  }
  return {
    ...summary,
    description: value.description,
    datasets: value.datasets.map((dataset) => ({
      id: (dataset as Record<string, string | boolean>).id as string,
      version: (dataset as Record<string, string | boolean>).version as string,
      source: (dataset as Record<string, string | boolean>).source as string,
      license_status: (dataset as Record<string, string | boolean>).license_status as string,
      research_ready: (dataset as Record<string, string | boolean>).research_ready as boolean,
    })),
    pipeline_templates: value.pipeline_templates,
  }
}

function parseTemplateFieldContract(value: unknown): TemplateFieldContract {
  if (!isRecord(value) || !['string', 'integer', 'boolean'].includes(String(value.type)) || typeof value.required !== 'boolean') {
    throw new Error('Invalid template field contract')
  }
  const minimum = value.minimum
  const maximum = value.maximum
  const constValue = value.const
  if ((minimum !== null && (typeof minimum !== 'number' || !Number.isInteger(minimum))) ||
      (maximum !== null && (typeof maximum !== 'number' || !Number.isInteger(maximum))) ||
      (constValue !== null && typeof constValue !== 'string' && typeof constValue !== 'number' && typeof constValue !== 'boolean')) {
    throw new Error('Invalid template field constraints')
  }
  return {
    type: value.type as TemplateFieldContract['type'],
    required: value.required,
    minimum: minimum as number | null,
    maximum: maximum as number | null,
    const: constValue as TemplateFieldContract['const'],
  }
}

function parseTemplateFieldMap(value: unknown): Record<string, TemplateFieldContract> {
  if (!isRecord(value)) throw new Error('Invalid template field map')
  return Object.fromEntries(Object.entries(value).map(([key, field]) => [key, parseTemplateFieldContract(field)]))
}

function parseStringArray(value: unknown, name: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) throw new Error(`Invalid template ${name}`)
  return value
}

export function parseTemplateContract(value: unknown): TemplateContract {
  if (!isRecord(value) || typeof value.template_id !== 'string' || typeof value.version !== 'string' ||
      typeof value.manifest_sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(value.manifest_sha256) ||
      typeof value.executor !== 'string' || typeof value.dataset_version !== 'string' ||
      typeof value.permission_scope !== 'string' || !isRecord(value.resource_limits)) {
    throw new Error('Invalid template contract')
  }
  const limits = value.resource_limits
  if (!Number.isInteger(limits.max_concurrent_runs) || !Number.isInteger(limits.soft_timeout_seconds) ||
      !Number.isInteger(limits.hard_timeout_seconds)) {
    throw new Error('Invalid template resource limits')
  }
  return {
    template_id: value.template_id,
    version: value.version,
    manifest_sha256: value.manifest_sha256,
    executor: value.executor,
    dataset_version: value.dataset_version,
    permission_scope: value.permission_scope,
    resource_limits: {
      max_concurrent_runs: limits.max_concurrent_runs as number,
      soft_timeout_seconds: limits.soft_timeout_seconds as number,
      hard_timeout_seconds: limits.hard_timeout_seconds as number,
    },
    inputs: parseTemplateFieldMap(value.inputs),
    parameters: parseTemplateFieldMap(value.parameters),
    outputs: parseTemplateFieldMap(value.outputs),
    states: parseStringArray(value.states, 'states'),
    error_codes: parseStringArray(value.error_codes, 'error codes'),
  }
}

async function request<T>(path: string, config: ApiConfig, signal?: AbortSignal, body?: ProjectCreateInput): Promise<T> {
  const baseUrl = config.baseUrl.trim().replace(/\/$/, '')
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (config.token.trim()) headers.Authorization = `Bearer ${config.token.trim()}`
  if (body) headers['Content-Type'] = 'application/json'

  const response = await fetch(`${baseUrl}${path}`, {
    method: body ? 'POST' : 'GET',
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  })
  if (!response.ok) {
    // Preserve the response shape so callers can distinguish API errors from a frontend host's HTML 404 page.
    throw new ProjectApiError(response.status, response.headers.get('content-type') ?? '')
  }
  return await response.json() as T
}

export async function listProjects(config: ApiConfig, signal?: AbortSignal): Promise<ProjectListItem[]> {
  const value = await request<unknown>('/api/v1/projects', config, signal)
  if (!Array.isArray(value)) throw new Error('Invalid project list response')
  // Keep development fixtures out of the user-facing research project directory.
  return value.map(parseProjectListItem).filter((project) => project.visibility === 'private')
}

export async function getProject(config: ApiConfig, projectId: string, signal?: AbortSignal): Promise<ProjectDetail> {
  const value = await request<unknown>(`/api/v1/projects/${encodeURIComponent(projectId)}`, config, signal)
  const project = parseProjectDetail(value)
  if (project.visibility === 'demo') throw new Error('合成演示项目不属于科研项目目录。')
  return project
}

export async function getProjectTemplateContract(config: ApiConfig, projectId: string, templateId: string, signal?: AbortSignal): Promise<ProjectTemplateContract> {
  const value = await request<unknown>(`/api/v1/projects/${encodeURIComponent(projectId)}/templates/${encodeURIComponent(templateId)}`, config, signal)
  return parseTemplateContract(value)
}

export async function createProject(config: ApiConfig, payload: ProjectCreateInput): Promise<ProjectDetail> {
  const value = await request<unknown>('/api/v1/projects', config, undefined, payload)
  return parseProjectDetail(value)
}
