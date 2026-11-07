import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

const projectId = 'local-project-sync-1'
const workflowId = 'local-workflow-sync-1'
const platformProjectId = 'platform-project-sync-1'
const platformWorkflowId = 'platform-workflow-sync-1'
const emptyGraph = { schema_version: 'ict.workflow.v1', nodes: [], edges: [] }
const timestamp = '2026-11-03T00:00:00Z'
const localProject = {
  id: projectId,
  name: '离线项目同步验收',
  domain: '数据分析',
  role: 'operator',
  visibility: 'private',
  created_at: timestamp,
  updated_at: timestamp,
  description: '本机项目说明',
  workflow_count: 1,
  dataset_version_count: 0,
  recent_run_status: null,
  last_activity_at: timestamp,
  datasets: [],
  pipeline_templates: [],
  source: 'local',
  sync_state: 'local_only',
}
const localWorkflow = {
  id: workflowId,
  workspace_id: 'local',
  owner_type: 'project',
  owner_id: projectId,
  project_id: projectId,
  reproduction_task_id: null,
  name: '离线工作流',
  description: '保留本机定义',
  revision: 1,
  current_version: 0,
  created_at: timestamp,
  updated_at: timestamp,
  graph: emptyGraph,
  can_edit: true,
  source: 'local',
  sync_state: 'local_only',
}

function response(payload: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: vi.fn().mockResolvedValue(payload) }
}

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  window.history.replaceState(null, '', '#settings/service')
  vi.unstubAllGlobals()
})

it('requires a desktop confirmation before syncing and keeps the local project after confirmation', async () => {
  let projectSync = {
    project_id: projectId,
    status: 'local_only',
    platform_project_id: null as string | null,
    error_code: null as string | null,
    updated_at: null as string | null,
    workflows: [{
      workflow_id: workflowId,
      status: 'local_only',
      platform_workflow_id: null as string | null,
      synced_revision: null as number | null,
      source_revision: null as number | null,
      error_code: null as string | null,
      updated_at: null as string | null,
    }],
  }
  const platformRequests: Array<{ method: string; path: string; body: Record<string, unknown> | null }> = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input))
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) as Record<string, unknown> : null
    if (url.hostname === 'platform.test') platformRequests.push({ method, path: url.pathname, body })

    if (url.pathname.endsWith('/api/v1/local/session')) return response({ token: 'local-session', expires_in_seconds: 900 })
    if (url.pathname === '/api/v1/local/projects' && method === 'GET') return response([localProject])
    if (url.pathname === `/api/v1/local/projects/${projectId}` && method === 'GET') return response(localProject)
    if (url.pathname === `/api/v1/local/projects/${projectId}/workflows` && method === 'GET') return response([localWorkflow])
    if (url.pathname === `/api/v1/local/projects/${projectId}/sync-state` && method === 'GET') return response(projectSync)
    if (url.pathname === `/api/v1/local/projects/${projectId}/sync-state/start` && method === 'POST') {
      projectSync = { ...projectSync, status: 'pending' }
      return response(projectSync)
    }
    if (url.pathname === `/api/v1/local/projects/${projectId}/sync-state` && method === 'PUT') {
      projectSync = {
        ...projectSync,
        ...(body as { status: string; platform_project_id?: string | null; error_code?: string | null }),
      }
      return response(projectSync)
    }
    if (url.pathname === `/api/v1/local/projects/${projectId}/workflows/${workflowId}/sync-state` && method === 'PUT') {
      projectSync = {
        ...projectSync,
        workflows: projectSync.workflows.map((item) => item.workflow_id === workflowId ? {
          ...item,
          ...(body as Record<string, unknown>),
        } : item),
      }
      return response(projectSync)
    }
    if (url.pathname === `/api/v1/local/workflows/${workflowId}` && method === 'GET') return response(localWorkflow)
    if (url.pathname === '/api/v1/projects' && method === 'GET') return response([])
    if (url.pathname === '/api/v1/projects' && method === 'POST') {
      const projectPayload = body as { name: string; domain: string; description: string }
      return response({
        id: platformProjectId,
        ...projectPayload,
        role: 'owner',
        visibility: 'private',
        created_at: timestamp,
        datasets: [],
        pipeline_templates: [],
      }, 201)
    }
    if (url.pathname === `/api/v1/projects/${platformProjectId}/workflows` && method === 'POST') {
      return response({
        id: platformWorkflowId,
        workspace_id: 'workspace-sync-test',
        owner_type: 'project',
        owner_id: platformProjectId,
        project_id: platformProjectId,
        reproduction_task_id: null,
        name: localWorkflow.name,
        description: localWorkflow.description,
        revision: 1,
        current_version: 0,
        created_at: timestamp,
        updated_at: timestamp,
        graph: emptyGraph,
        can_edit: true,
      }, 201)
    }
    if (url.pathname === `/api/v1/workflows/${platformWorkflowId}` && method === 'PATCH') {
      return response({
        id: platformWorkflowId,
        workspace_id: 'workspace-sync-test',
        owner_type: 'project',
        owner_id: platformProjectId,
        project_id: platformProjectId,
        reproduction_task_id: null,
        name: localWorkflow.name,
        description: localWorkflow.description,
        revision: 2,
        current_version: 0,
        created_at: timestamp,
        updated_at: timestamp,
        graph: (body as { graph: typeof emptyGraph }).graph,
        can_edit: true,
      })
    }
    return response({ error: { code: 'MOCK_ROUTE_NOT_FOUND' } }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState(null, '', '#settings/service')

  render(<App />)
  fireEvent.change(screen.getByPlaceholderText('例如 http://127.0.0.1:8765'), { target: { value: 'http://platform.test' } })
  fireEvent.change(screen.getByPlaceholderText('输入服务管理员提供的令牌'), { target: { value: 'test-token' } })
  fireEvent.click(screen.getByRole('button', { name: '验证并连接' }))
  await screen.findByText('项目服务已连接')

  window.history.replaceState(null, '', `#workbench/projects/${projectId}`)
  fireEvent(window, new Event('hashchange'))
  expect(await screen.findByRole('heading', { level: 1, name: localProject.name })).toBeInTheDocument()
  const syncButton = await screen.findByRole('button', { name: '同步到平台' })
  fireEvent.click(syncButton)

  let dialog = await screen.findByRole('dialog', { name: '同步项目到科研平台？' })
  expect(within(dialog).getByText(/同步正文不包含/)).toBeInTheDocument()
  expect(platformRequests.filter((item) => item.method === 'POST' && item.path === '/api/v1/projects')).toHaveLength(0)
  expect(platformRequests.some((item) => item.path.endsWith('/sync-state/start'))).toBe(false)

  fireEvent.click(within(dialog).getByRole('button', { name: '取消' }))
  await waitFor(() => expect(screen.queryByRole('dialog', { name: '同步项目到科研平台？' })).not.toBeInTheDocument())
  expect(platformRequests.filter((item) => item.method === 'POST' && item.path === '/api/v1/projects')).toHaveLength(0)

  fireEvent.click(screen.getByRole('button', { name: '同步到平台' }))
  dialog = await screen.findByRole('dialog', { name: '同步项目到科研平台？' })
  fireEvent.click(within(dialog).getByRole('button', { name: '确认同步' }))
  expect(await screen.findByText(/平台副本已同步/)).toBeInTheDocument()
  expect(platformRequests.filter((item) => item.method === 'POST' && item.path === '/api/v1/projects')).toHaveLength(1)
  expect(projectSync.status).toBe('synced')
  expect(projectSync.platform_project_id).toBe(platformProjectId)
  expect(localProject.id).toBe(projectId)
})
