import { afterEach, expect, it, vi } from 'vitest'

afterEach(() => vi.unstubAllGlobals())

const localProject = {
  id: 'local-project-1',
  name: '离线清单检查',
  domain: '数据分析',
  role: 'operator',
  visibility: 'private',
  created_at: '2026-11-03T00:00:00Z',
  updated_at: '2026-11-03T00:00:00Z',
  description: '本机项目',
  workflow_count: 0,
  dataset_version_count: 0,
  recent_run_status: null,
  last_activity_at: '2026-11-03T00:00:00Z',
  source: 'local',
  sync_state: 'local_only',
}

const localWorkflow = {
  id: 'local-workflow-1',
  workspace_id: 'local',
  owner_type: 'project',
  owner_id: localProject.id,
  project_id: localProject.id,
  reproduction_task_id: null,
  name: '清单结构预检',
  description: '',
  revision: 1,
  current_version: 0,
  created_at: '2026-11-03T00:00:00Z',
  updated_at: '2026-11-03T00:00:00Z',
  graph: { schema_version: 'ict.workflow.v1', nodes: [], edges: [] },
  can_edit: true,
  source: 'local',
  sync_state: 'local_only',
}

it('lists locally persisted projects through the local runtime session', async () => {
  vi.resetModules()
  const { listLocalProjects } = await import('./localRuntime')
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ token: 'local-token', expires_in_seconds: 900 }) })
    .mockResolvedValueOnce({ ok: true, json: async () => [localProject] })
  vi.stubGlobal('fetch', fetchMock)

  await expect(listLocalProjects()).resolves.toEqual([localProject])
  expect(fetchMock.mock.calls[1][0]).toBe('http://127.0.0.1:8767/api/v1/local/projects')
})

it('creates a local project workflow with local-only ownership metadata', async () => {
  vi.resetModules()
  const { createLocalProjectWorkflow } = await import('./localRuntime')
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ token: 'local-token', expires_in_seconds: 900 }) })
    .mockResolvedValueOnce({ ok: true, json: async () => localWorkflow })
  vi.stubGlobal('fetch', fetchMock)

  await expect(createLocalProjectWorkflow(localProject.id, { name: '清单结构预检', description: '' }))
    .resolves.toEqual(localWorkflow)
  const [url, options] = fetchMock.mock.calls[1] as [string, RequestInit]
  expect(url).toBe(`http://127.0.0.1:8767/api/v1/local/projects/${localProject.id}/workflows`)
  expect(options.method).toBe('POST')
  expect(JSON.parse(String(options.body))).toEqual({ name: '清单结构预检', description: '' })
})
