import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'
import { clearLocalRuntimeSession } from './api/localRuntime'

const project = {
  id: 'project-local-e2e',
  name: '离线工作流项目',
  domain: '生命科学',
  description: '用于验证当前项目目录页面。',
  role: 'operator',
  visibility: 'private',
  created_at: '2026-11-03T00:00:00Z',
  workflow_count: 0,
  dataset_version_count: 0,
  recent_run_status: null,
  last_activity_at: null,
}

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: vi.fn().mockResolvedValue(payload),
  }
}

afterEach(() => {
  cleanup()
  clearLocalRuntimeSession()
  window.localStorage.clear()
  window.history.replaceState(null, '', '#workbench/projects')
  vi.unstubAllGlobals()
})

it('shows the real disconnected project state without synthetic project data', async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/local/session')) {
      return Promise.resolve(jsonResponse({ token: 'local-token', expires_in_seconds: 900 }))
    }
    if (url.endsWith('/api/v1/local/projects')) return Promise.resolve(jsonResponse([]))
    return Promise.resolve(jsonResponse({ error: { code: 'LOCAL_NOT_FOUND' } }, 404))
  })
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState(null, '', '#workbench/projects')

  render(<App />)

  // Keep the local project entry usable while the platform project catalog is disconnected.
  expect(await screen.findByRole('heading', { name: '本机项目' })).toBeInTheDocument()
  expect(screen.getByText('平台项目服务未连接')).toBeInTheDocument()
  expect(await screen.findByText('还没有本机项目')).toBeInTheDocument()
  expect(screen.queryByText('合成研究演示项目')).not.toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8767/api/v1/local/session', expect.any(Object))
  expect(fetchMock.mock.calls.every(([url]) => String(url).startsWith('http://127.0.0.1:8767/'))).toBe(true)

  fireEvent.click(screen.getByRole('button', { name: '连接平台项目服务' }))
  expect(window.location.hash).toBe('#settings/service')
})

it('retries the actual project-list connection after a service error', async () => {
  let platformAttempts = 0
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/local/session')) return Promise.resolve(jsonResponse({ token: 'local-token', expires_in_seconds: 900 }))
    if (url.endsWith('/api/v1/local/projects')) return Promise.resolve(jsonResponse([]))
    if (url === 'http://127.0.0.1:8765/api/v1/projects') {
      platformAttempts += 1
      return Promise.resolve(platformAttempts === 1
        ? jsonResponse({ error: { code: 'BACKEND_AUTH_NOT_CONFIGURED', message: 'internal connection details' } }, 503)
        : jsonResponse([project]))
    }
    return Promise.resolve(jsonResponse({ detail: 'not found' }, 404))
  })
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState(null, '', '#workbench/projects')

  render(<App />)

  fireEvent.click(screen.getByRole('button', { name: '连接平台项目服务' }))
  expect(await screen.findByLabelText(/API 地址/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText(/API 地址/), { target: { value: 'http://127.0.0.1:8765' } })
  fireEvent.change(screen.getByLabelText(/访问令牌/), { target: { value: 'test-token' } })
  fireEvent.click(screen.getByRole('button', { name: '验证并连接' }))

  expect(await screen.findByText('后端账号认证尚未配置，请联系服务管理员。')).toBeInTheDocument()
  expect(screen.queryByText('internal connection details')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '验证并连接' }))

  expect(await screen.findByText('已读取 1 个项目。')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '工作台' }))
  expect(await screen.findByText('离线工作流项目')).toBeInTheDocument()
  expect(platformAttempts).toBe(2)
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8765/api/v1/projects',
    expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer test-token' }) }),
  )
})
