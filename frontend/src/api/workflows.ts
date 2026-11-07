import type { ApiConfig } from './projects'

export interface WorkflowGraphNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: Record<string, unknown>
}

export interface WorkflowGraphEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
  type?: string | null
}

export interface WorkflowGraph {
  schema_version: 'ict.workflow.v1'
  nodes: WorkflowGraphNode[]
  edges: WorkflowGraphEdge[]
}

export interface WorkflowSummary {
  id: string
  workspace_id: string
  owner_type: 'project' | 'reproduction'
  owner_id: string
  project_id: string | null
  reproduction_task_id: string | null
  name: string
  description: string
  revision: number
  current_version: number
  created_at: string
  updated_at: string
}

export interface WorkflowDetail extends WorkflowSummary {
  graph: WorkflowGraph
  can_edit: boolean
}

export interface WorkflowValidationIssue {
  scope: 'structure' | 'component'
  code: string
  message: string
  severity?: 'blocker' | 'warning' | 'info'
  title?: string
  reason?: string
  impact?: string
  guidance?: string
  node_id: string | null
  edge_id: string | null
}

export interface WorkflowValidation {
  workflow_id: string
  revision: number
  structural_status: 'valid' | 'invalid'
  contract_status: 'valid' | 'invalid'
  executable: false
  execution_blockers: string[]
  issues: WorkflowValidationIssue[]
}

export interface WorkflowComponentPort {
  id: string
  label: string
  data_type: string
  required: boolean
  multiple: boolean
}

export interface WorkflowComponentParameter {
  type: 'string'
  title: string
  description: string
  default: string
  minLength: number
  maxLength?: number
}

export interface WorkflowComponent {
  schema_version: string
  component_id: string
  version: string
  category: string
  title: string
  description: string
  inputs: WorkflowComponentPort[]
  outputs: WorkflowComponentPort[]
  parameter_schema: {
    type: 'object'
    properties: Record<string, WorkflowComponentParameter>
    required: string[]
    additionalProperties: false
  }
  executor_binding: string | null
  executor_version: string | null
  implementation_digest: string | null
  execution_target: 'local' | 'network' | 'platform'
  dependencies: string[]
  permissions: string[]
  resource_limits: Record<string, number | null>
  cache_policy: string
  error_types: string[]
  execution_available: boolean
  execution_blockers?: string[]
}

/** Apply a schema character limit without splitting UTF-16 surrogate pairs. */
export function limitWorkflowParameterValue(value: string, maxLength?: number): string {
  if (maxLength === undefined || !Number.isInteger(maxLength) || maxLength < 0) return value
  return Array.from(value).slice(0, maxLength).join('')
}

export interface WorkflowVersionSummary {
  id: string
  workflow_id: string
  version: number
  // Null means this historical record predates metadata snapshots.
  name: string | null
  description: string | null
  schema_version: string
  content_hash: string
  created_by: string
  created_at: string
}

export interface WorkflowVersionCreated {
  created: boolean
  workflow: WorkflowSummary
  version: WorkflowVersionSummary
}

export interface WorkflowVersionDetail extends WorkflowVersionSummary {
  graph: WorkflowGraph
}

export class WorkflowApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string) {
    super(`Workflow API request failed (${status}: ${code})`)
    this.status = status
    this.code = code
    this.name = 'WorkflowApiError'
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseWorkflowSummary(value: unknown): WorkflowSummary {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.workspace_id !== 'string' ||
      (value.owner_type !== 'project' && value.owner_type !== 'reproduction') ||
      typeof value.owner_id !== 'string' ||
      !(typeof value.project_id === 'string' || value.project_id === null) ||
      !(typeof value.reproduction_task_id === 'string' || value.reproduction_task_id === null) ||
      typeof value.name !== 'string' || typeof value.description !== 'string' ||
      !Number.isInteger(value.revision) || !Number.isInteger(value.current_version) ||
      typeof value.created_at !== 'string' || typeof value.updated_at !== 'string') {
    throw new Error('Invalid workflow response')
  }
  return {
    id: value.id,
    workspace_id: value.workspace_id,
    owner_type: value.owner_type,
    owner_id: value.owner_id,
    project_id: value.project_id,
    reproduction_task_id: value.reproduction_task_id,
    name: value.name,
    description: value.description,
    revision: value.revision as number,
    current_version: value.current_version as number,
    created_at: value.created_at,
    updated_at: value.updated_at,
  }
}

function parseWorkflowGraph(value: unknown): WorkflowGraph {
  if (!isRecord(value) || value.schema_version !== 'ict.workflow.v1' ||
      !Array.isArray(value.nodes) || !Array.isArray(value.edges)) {
    throw new Error('Invalid workflow graph response')
  }
  const nodes = value.nodes.map((node): WorkflowGraphNode => {
    if (!isRecord(node) || typeof node.id !== 'string' || typeof node.type !== 'string' ||
        !isRecord(node.position) || typeof node.position.x !== 'number' ||
        typeof node.position.y !== 'number' || !isRecord(node.data)) {
      throw new Error('Invalid workflow node response')
    }
    return {
      id: node.id,
      type: node.type,
      position: { x: node.position.x, y: node.position.y },
      data: node.data,
    }
  })
  const edges = value.edges.map((edge): WorkflowGraphEdge => {
    if (!isRecord(edge) || typeof edge.id !== 'string' || typeof edge.source !== 'string' ||
        typeof edge.target !== 'string' ||
        (edge.sourceHandle !== null && edge.sourceHandle !== undefined && typeof edge.sourceHandle !== 'string') ||
        (edge.targetHandle !== null && edge.targetHandle !== undefined && typeof edge.targetHandle !== 'string') ||
        (edge.type !== null && edge.type !== undefined && typeof edge.type !== 'string')) {
      throw new Error('Invalid workflow edge response')
    }
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle as string | null | undefined,
      targetHandle: edge.targetHandle as string | null | undefined,
      type: edge.type as string | null | undefined,
    }
  })
  return { schema_version: 'ict.workflow.v1', nodes, edges }
}

function parseWorkflowDetail(value: unknown): WorkflowDetail {
  const summary = parseWorkflowSummary(value)
  if (!isRecord(value) || typeof value.can_edit !== 'boolean') throw new Error('Invalid workflow response')
  return { ...summary, graph: parseWorkflowGraph(value.graph), can_edit: value.can_edit }
}

function parseWorkflowVersion(value: unknown): WorkflowVersionSummary {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.workflow_id !== 'string' ||
      !Number.isInteger(value.version) || typeof value.schema_version !== 'string' ||
      typeof value.content_hash !== 'string' || typeof value.created_by !== 'string' ||
      typeof value.created_at !== 'string' ||
      (value.name !== undefined && value.name !== null && typeof value.name !== 'string') ||
      (value.description !== undefined && value.description !== null && typeof value.description !== 'string')) {
    throw new Error('Invalid workflow version response')
  }
  return {
    id: value.id,
    workflow_id: value.workflow_id,
    version: value.version as number,
    name: typeof value.name === 'string' ? value.name : null,
    description: typeof value.description === 'string' ? value.description : null,
    schema_version: value.schema_version,
    content_hash: value.content_hash,
    created_by: value.created_by,
    created_at: value.created_at,
  }
}

function parseWorkflowVersionDetail(value: unknown): WorkflowVersionDetail {
  const summary = parseWorkflowVersion(value)
  if (!isRecord(value)) throw new Error('Invalid workflow version response')
  return { ...summary, graph: parseWorkflowGraph(value.graph) }
}

export function parseWorkflowValidation(value: unknown): WorkflowValidation {
  if (!isRecord(value) || typeof value.workflow_id !== 'string' || !Number.isInteger(value.revision) ||
      (value.structural_status !== 'valid' && value.structural_status !== 'invalid') ||
      (value.contract_status !== 'valid' && value.contract_status !== 'invalid') ||
      value.executable !== false || !Array.isArray(value.execution_blockers) ||
      !value.execution_blockers.every((item) => typeof item === 'string') || !Array.isArray(value.issues)) {
    throw new Error('Invalid workflow validation response')
  }
  const issues = value.issues.map((issue): WorkflowValidationIssue => {
    const optionalTextFields = ['title', 'reason', 'impact', 'guidance'] as const
    if (!isRecord(issue) || (issue.scope !== 'structure' && issue.scope !== 'component') ||
        typeof issue.code !== 'string' || typeof issue.message !== 'string' ||
        (issue.severity !== undefined && issue.severity !== 'blocker' && issue.severity !== 'warning' && issue.severity !== 'info') ||
        optionalTextFields.some((field) => issue[field] !== undefined && typeof issue[field] !== 'string') ||
        (issue.node_id !== null && typeof issue.node_id !== 'string') ||
        (issue.edge_id !== null && typeof issue.edge_id !== 'string')) {
      throw new Error('Invalid workflow validation issue')
    }
    return {
      scope: issue.scope,
      code: issue.code,
      message: issue.message,
      severity: issue.severity as WorkflowValidationIssue['severity'],
      title: typeof issue.title === 'string' ? issue.title : undefined,
      reason: typeof issue.reason === 'string' ? issue.reason : undefined,
      impact: typeof issue.impact === 'string' ? issue.impact : undefined,
      guidance: typeof issue.guidance === 'string' ? issue.guidance : undefined,
      node_id: issue.node_id as string | null,
      edge_id: issue.edge_id as string | null,
    }
  })
  return {
    workflow_id: value.workflow_id,
    revision: value.revision as number,
    structural_status: value.structural_status,
    contract_status: value.contract_status,
    executable: false,
    execution_blockers: value.execution_blockers,
    issues,
  }
}

function parseWorkflowPort(value: unknown): WorkflowComponentPort {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.label !== 'string' ||
      typeof value.data_type !== 'string' || typeof value.required !== 'boolean' ||
      typeof value.multiple !== 'boolean') {
    throw new Error('Invalid workflow component port response')
  }
  return {
    id: value.id,
    label: value.label,
    data_type: value.data_type,
    required: value.required,
    multiple: value.multiple,
  }
}

export function parseWorkflowComponent(value: unknown): WorkflowComponent {
  if (!isRecord(value) || value.schema_version !== 'ict.component.v1' ||
      typeof value.component_id !== 'string' || typeof value.version !== 'string' ||
      typeof value.category !== 'string' || typeof value.title !== 'string' ||
      typeof value.description !== 'string' || !Array.isArray(value.inputs) || !Array.isArray(value.outputs) ||
      !isRecord(value.parameter_schema) || value.parameter_schema.type !== 'object' ||
      !isRecord(value.parameter_schema.properties) || !Array.isArray(value.parameter_schema.required) ||
      !value.parameter_schema.required.every((item) => typeof item === 'string') ||
      value.parameter_schema.additionalProperties !== false ||
      (value.executor_binding !== null && typeof value.executor_binding !== 'string') ||
      (value.executor_version !== null && typeof value.executor_version !== 'string') ||
      (value.implementation_digest !== null && typeof value.implementation_digest !== 'string') ||
      (value.execution_target !== 'local' && value.execution_target !== 'network' && value.execution_target !== 'platform') ||
      !Array.isArray(value.dependencies) || !value.dependencies.every((item) => typeof item === 'string') ||
      !Array.isArray(value.permissions) || !value.permissions.every((item) => typeof item === 'string') ||
      !isRecord(value.resource_limits) || typeof value.cache_policy !== 'string' ||
      !Array.isArray(value.error_types) || !value.error_types.every((item) => typeof item === 'string') ||
      (value.execution_blockers !== undefined &&
        (!Array.isArray(value.execution_blockers) || !value.execution_blockers.every((item) => typeof item === 'string'))) ||
      typeof value.execution_available !== 'boolean') {
    throw new Error('Invalid workflow component response')
  }
  const properties: Record<string, WorkflowComponentParameter> = {}
  for (const [key, property] of Object.entries(value.parameter_schema.properties)) {
    if (!isRecord(property) || property.type !== 'string' || typeof property.title !== 'string' ||
        typeof property.description !== 'string' || typeof property.default !== 'string' ||
        !Number.isInteger(property.minLength) ||
        (property.maxLength !== undefined &&
          (!Number.isInteger(property.maxLength) || (property.maxLength as number) < 0))) {
      throw new Error(`Invalid workflow component parameter: ${key}`)
    }
    properties[key] = {
      type: 'string',
      title: property.title,
      description: property.description,
      default: property.default,
      minLength: property.minLength as number,
      ...(property.maxLength !== undefined ? { maxLength: property.maxLength as number } : {}),
    }
  }
  const resourceLimits: Record<string, number | null> = {}
  for (const [key, limit] of Object.entries(value.resource_limits)) {
    if (limit !== null && typeof limit !== 'number') throw new Error(`Invalid workflow resource limit: ${key}`)
    resourceLimits[key] = limit as number | null
  }
  return {
    schema_version: 'ict.component.v1',
    component_id: value.component_id,
    version: value.version,
    category: value.category,
    title: value.title,
    description: value.description,
    inputs: value.inputs.map(parseWorkflowPort),
    outputs: value.outputs.map(parseWorkflowPort),
    parameter_schema: {
      type: 'object',
      properties,
      required: value.parameter_schema.required as string[],
      additionalProperties: false,
    },
    executor_binding: value.executor_binding as string | null,
    executor_version: value.executor_version as string | null,
    implementation_digest: value.implementation_digest as string | null,
    execution_target: value.execution_target,
    dependencies: value.dependencies as string[],
    permissions: value.permissions as string[],
    resource_limits: resourceLimits,
    cache_policy: value.cache_policy,
    error_types: value.error_types as string[],
    execution_available: value.execution_available,
    ...(Array.isArray(value.execution_blockers)
      ? { execution_blockers: value.execution_blockers as string[] }
      : {}),
  }
}

async function request(path: string, config: ApiConfig, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<unknown> {
  const baseUrl = config.baseUrl.trim().replace(/\/$/, '')
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (config.token.trim()) headers.Authorization = `Bearer ${config.token.trim()}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  if (!response.ok) {
    let code = 'REQUEST_FAILED'
    try {
      const payload: unknown = await response.json()
      if (isRecord(payload) && isRecord(payload.error) && typeof payload.error.code === 'string') code = payload.error.code
    } catch (error) {
      console.warn('工作流 API 错误响应无法解析，将使用 HTTP 状态码。', error)
    }
    throw new WorkflowApiError(response.status, code)
  }
  return await response.json() as unknown
}

export async function listProjectWorkflows(config: ApiConfig, projectId: string, signal?: AbortSignal): Promise<WorkflowSummary[]> {
  const value = await request(`/api/v1/projects/${encodeURIComponent(projectId)}/workflows`, config, 'GET', undefined, signal)
  if (!Array.isArray(value)) throw new Error('Invalid workflow list response')
  return value.map(parseWorkflowSummary)
}

export async function listReproductionWorkflows(config: ApiConfig, taskId: string, signal?: AbortSignal): Promise<WorkflowSummary[]> {
  const value = await request(`/api/v1/reproductions/${encodeURIComponent(taskId)}/workflows`, config, 'GET', undefined, signal)
  if (!Array.isArray(value)) throw new Error('Invalid reproduction workflow list response')
  return value.map(parseWorkflowSummary)
}

export async function listWorkflowComponents(config: ApiConfig, signal?: AbortSignal): Promise<WorkflowComponent[]> {
  const value = await request('/api/v1/workflow-components', config, 'GET', undefined, signal)
  if (!Array.isArray(value)) throw new Error('Invalid workflow component catalog response')
  return value.map(parseWorkflowComponent)
}

export async function createProjectWorkflow(config: ApiConfig, projectId: string, name: string, description = ''): Promise<WorkflowDetail> {
  const value = await request(
    `/api/v1/projects/${encodeURIComponent(projectId)}/workflows`, config, 'POST', { name, description },
  )
  return parseWorkflowDetail(value)
}

export async function createReproductionWorkflow(config: ApiConfig, taskId: string, name: string, description = ''): Promise<WorkflowDetail> {
  const value = await request(
    `/api/v1/reproductions/${encodeURIComponent(taskId)}/workflows`, config, 'POST', { name, description },
  )
  return parseWorkflowDetail(value)
}

export async function getWorkflow(config: ApiConfig, workflowId: string, signal?: AbortSignal): Promise<WorkflowDetail> {
  const value = await request(`/api/v1/workflows/${encodeURIComponent(workflowId)}`, config, 'GET', undefined, signal)
  return parseWorkflowDetail(value)
}

export async function saveWorkflowDraft(
  config: ApiConfig,
  workflow: Pick<WorkflowDetail, 'id' | 'revision'> & { name: string; description: string; graph: WorkflowGraph },
): Promise<WorkflowDetail> {
  const value = await request(`/api/v1/workflows/${encodeURIComponent(workflow.id)}`, config, 'PATCH', {
    revision: workflow.revision,
    name: workflow.name,
    description: workflow.description,
    graph: workflow.graph,
  })
  return parseWorkflowDetail(value)
}

export async function validateWorkflow(config: ApiConfig, workflowId: string, signal?: AbortSignal): Promise<WorkflowValidation> {
  const value = await request(`/api/v1/workflows/${encodeURIComponent(workflowId)}/validations`, config, 'POST', {}, signal)
  return parseWorkflowValidation(value)
}

export async function createWorkflowVersion(config: ApiConfig, workflowId: string): Promise<WorkflowVersionCreated> {
  const value = await request(`/api/v1/workflows/${encodeURIComponent(workflowId)}/versions`, config, 'POST', {})
  if (!isRecord(value) || typeof value.created !== 'boolean') throw new Error('Invalid workflow version response')
  return {
    created: value.created,
    workflow: parseWorkflowSummary(value.workflow),
    version: parseWorkflowVersion(value.version),
  }
}

export async function listWorkflowVersions(config: ApiConfig, workflowId: string, signal?: AbortSignal): Promise<WorkflowVersionSummary[]> {
  const value = await request(`/api/v1/workflows/${encodeURIComponent(workflowId)}/versions`, config, 'GET', undefined, signal)
  if (!Array.isArray(value)) throw new Error('Invalid workflow version list response')
  return value.map(parseWorkflowVersion)
}

export async function getWorkflowVersion(
  config: ApiConfig,
  workflowId: string,
  versionNumber: number,
  signal?: AbortSignal,
): Promise<WorkflowVersionDetail> {
  const value = await request(
    `/api/v1/workflows/${encodeURIComponent(workflowId)}/versions/${versionNumber}`,
    config,
    'GET',
    undefined,
    signal,
  )
  return parseWorkflowVersionDetail(value)
}

export async function restoreWorkflowVersion(
  config: ApiConfig,
  workflowId: string,
  versionNumber: number,
  revision: number,
): Promise<WorkflowDetail> {
  const value = await request(
    `/api/v1/workflows/${encodeURIComponent(workflowId)}/versions/${versionNumber}/restore`,
    config,
    'POST',
    { revision },
  )
  return parseWorkflowDetail(value)
}
