import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

const localProject = {
  id: 'local-project-offline-1',
  name: '离线实验项目',
  domain: '数据分析',
  description: '本机合成清单检查',
  role: 'operator',
  visibility: 'private',
  created_at: '2026-11-03T00:00:00Z',
  updated_at: '2026-11-03T00:00:00Z',
  workflow_count: 0,
  dataset_version_count: 0,
  recent_run_status: null,
  last_activity_at: '2026-11-03T00:00:00Z',
  datasets: [],
  pipeline_templates: [],
  source: 'local',
  sync_state: 'local_only',
}
function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(payload),
  }
}

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  window.history.replaceState(null, '', '#workbench/projects')
  vi.unstubAllGlobals()
})

it('creates a local-only project from a cold disconnected workbench', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.endsWith('/api/v1/local/session')) return jsonResponse({ token: 'local-token', expires_in_seconds: 900 })
    if (url.endsWith('/api/v1/local/projects') && method === 'GET') return jsonResponse([])
    if (url.endsWith('/api/v1/local/projects') && method === 'POST') return jsonResponse(localProject)
    if (url.endsWith(`/api/v1/local/projects/${localProject.id}`)) return jsonResponse(localProject)
    if (url.endsWith(`/api/v1/local/projects/${localProject.id}/workflows`)) return jsonResponse([])
    return jsonResponse({ detail: 'not found' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState(null, '', '#workbench/projects')

  render(<App />)

  fireEvent.click(await screen.findByRole('button', { name: '新建本机项目' }))
  expect(screen.getByText('仅保存在此设备')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('项目名称'), { target: { value: localProject.name } })
  fireEvent.change(screen.getByLabelText('研究领域'), { target: { value: localProject.domain } })
  fireEvent.click(screen.getByRole('button', { name: '创建本机项目' }))

  expect(await screen.findByRole('heading', { level: 1, name: localProject.name })).toBeInTheDocument()
  expect(await screen.findByText('仅保存在此设备')).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8767/api/v1/local/projects',
    expect.objectContaining({ method: 'POST' }),
  )

  expect(fetchMock.mock.calls.every(([url]) => String(url).startsWith('http://127.0.0.1:8767/'))).toBe(true)
})
