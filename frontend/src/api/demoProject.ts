export interface DemoProjectOverview {
  project_id: 'demo-research'
  purpose: string
  data_status: 'synthetic_only'
  research_ready: false
  dataset_versions: string[]
  pipeline_templates: string[]
  recent_public_runs: string[]
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const overviewPath = '/api/v1/demo/projects/demo-research/overview'

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function parseDemoProjectOverview(value: unknown): DemoProjectOverview {
  if (!value || typeof value !== 'object') throw new Error('Invalid project response')
  const candidate = value as Record<string, unknown>

  // Restrict the client to the same synthetic project and readiness boundary as the server.
  if (
    candidate.project_id !== 'demo-research' ||
    typeof candidate.purpose !== 'string' ||
    candidate.data_status !== 'synthetic_only' ||
    candidate.research_ready !== false ||
    !isStringArray(candidate.dataset_versions) ||
    !isStringArray(candidate.pipeline_templates) ||
    !isStringArray(candidate.recent_public_runs)
  ) {
    throw new Error('Invalid project response')
  }

  return {
    project_id: 'demo-research',
    purpose: candidate.purpose,
    data_status: 'synthetic_only',
    research_ready: false,
    dataset_versions: candidate.dataset_versions,
    pipeline_templates: candidate.pipeline_templates,
    recent_public_runs: candidate.recent_public_runs,
  }
}

export async function getDemoProjectOverview(signal?: AbortSignal): Promise<DemoProjectOverview> {
  const response = await fetch(`${apiBaseUrl}${overviewPath}`, {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) throw new Error('Project overview request failed')
  return parseDemoProjectOverview(await response.json())
}
