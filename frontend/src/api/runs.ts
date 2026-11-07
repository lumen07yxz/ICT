import { ProjectApiError, type ApiConfig } from './projects'

export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface ProjectRun {
  id: string
  project_id: string
  pipeline_template: string
  status: RunStatus
  trace_id: string
  created_at: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseRun(value: unknown): ProjectRun {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.project_id !== 'string' ||
      typeof value.pipeline_template !== 'string' || typeof value.trace_id !== 'string' ||
      typeof value.created_at !== 'string' ||
      !['queued', 'running', 'succeeded', 'failed'].includes(String(value.status))) {
    throw new Error('Invalid run response')
  }

  return {
    id: value.id,
    project_id: value.project_id,
    pipeline_template: value.pipeline_template,
    status: value.status as RunStatus,
    trace_id: value.trace_id,
    created_at: value.created_at,
  }
}

export async function listProjectRuns(config: ApiConfig, projectId: string, signal?: AbortSignal): Promise<ProjectRun[]> {
  const baseUrl = config.baseUrl.trim().replace(/\/$/, '')
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (config.token.trim()) headers.Authorization = `Bearer ${config.token.trim()}`

  const response = await fetch(`${baseUrl}/api/v1/runs?project_id=${encodeURIComponent(projectId)}`, {
    headers,
    signal,
  })
  if (!response.ok) throw new ProjectApiError(response.status)

  const value: unknown = await response.json()
  if (!Array.isArray(value)) throw new Error('Invalid run list response')
  return value.map(parseRun)
}
