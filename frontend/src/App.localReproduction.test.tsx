import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'
import { clearLocalRuntimeSession } from './api/localRuntime'

const taskId = 'local-reproduction-offline-1'
const workflowId = 'local-reproduction-workflow-offline-1'
const runId = 'local-run-offline-1'
const timestamp = '2026-11-03T00:00:00Z'
const task = {
  id: taskId,
  workspace_id: 'local',
  linked_project_id: null,
  title: '离线论文复现任务',
  kind: 'paper',
  source: 'DOI:10.0000/example',
  claim: '核对预先记录的论文主张',
  baseline: { reported_result_or_expected_value: '论文报告值待补充' },
  criteria_version: null,
  status: 'awaiting_review',
  created_by: 'local-user',
  updated_by: 'local-user',
  created_at: timestamp,
  updated_at: timestamp,
  assessment_state: 'not_assessed',
  sync_state: 'local_only',
}
const workflow = {
  id: workflowId,
  workspace_id: 'local',
  owner_type: 'reproduction',
  owner_id: taskId,
  project_id: null,
  reproduction_task_id: taskId,
  name: '离线论文复现任务 工作流',
  description: '',
  revision: 2,
  current_version: 0,
  created_at: timestamp,
  updated_at: timestamp,
  source: 'local',
  sync_state: 'local_only',
}
const artifact = {
  artifact_id: 'local-artifact-report-1',
  sha256: 'a'.repeat(64),
  file_name: 'preflight.json',
  media_type: 'application/json',
  size_bytes: 128,
  storage_key: 'artifacts/preflight.json',
  provenance: 'generated_by_local_workflow',
  authorization_status: 'local_only',
  created_at: timestamp,
}
const run = {
  run_id: runId,
  workflow_id: workflowId,
  status: 'succeeded',
  plan_hash: 'b'.repeat(64),
  target_node_ids: ['preflight-node'],
  created_at: timestamp,
  started_at: timestamp,
  finished_at: timestamp,
  execution_plan: {
    schema_version: 'ict.execution-plan.v1',
    workflow_schema_version: 'ict.workflow.v1',
    plan_hash: 'b'.repeat(64),
    target_node_ids: ['preflight-node'],
    nodes: [{ id: 'preflight-node', component_id: 'ict.data.csv_manifest_preflight', parameters: {} }],
  },
  error_code: null,
  node_runs: [{
    node_id: 'preflight-node',
    component_id: 'ict.data.csv_manifest_preflight',
    status: 'succeeded',
    error_code: null,
    output: { report: artifact },
    updated_at: timestamp,
  }],
  events: [
    { sequence: 1, node_id: null, status: 'QUEUED', error_code: null, occurred_at: timestamp },
    { sequence: 2, node_id: null, status: 'RUNNING', error_code: null, occurred_at: timestamp },
    { sequence: 3, node_id: 'preflight-node', status: 'SUCCEEDED', error_code: null, occurred_at: timestamp },
  ],
}
const report = {
  report_type: 'csv_manifest_structural_preflight',
  label: '结构预检，非科研结果',
  research_result: false,
  status: 'success',
  input: { artifact_id: artifact.artifact_id, sha256: artifact.sha256, size_bytes: 128, provenance: artifact.provenance, authorization_status: artifact.authorization_status },
  row_count: 5,
  columns: ['sample_id', 'label'],
  split_counts: { train: 5 },
  label_category_count: 2,
  issues: [],
}

function response(payload: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: vi.fn().mockResolvedValue(payload) }
}

afterEach(() => {
  cleanup()
  clearLocalRuntimeSession()
  window.localStorage.clear()
  window.history.replaceState(null, '', '#workbench/reproductions')
  vi.unstubAllGlobals()
})

it('shows local-only task execution and structural report while disconnected from the platform', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/local/session')) return response({ token: 'local-token', expires_in_seconds: 900 })
    if (url.endsWith('/api/v1/local/projects')) return response([])
    if (url.endsWith('/api/v1/local/reproductions')) return response([task])
    if (url.endsWith(`/api/v1/local/reproductions/${taskId}`)) return response(task)
    if (url.endsWith(`/api/v1/local/reproductions/${taskId}/workflows`)) return response([workflow])
    if (url.endsWith(`/api/v1/local/workflows/${workflowId}/runs`)) return response([run])
    if (url.endsWith(`/api/v1/local/runs/${runId}`)) return response(run)
    if (url.endsWith(`/api/v1/local/artifacts/${artifact.artifact_id}/csv-preflight-report`)) return response(report)
    return response({ detail: 'not found' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState(null, '', `#workbench/reproductions/${taskId}`)

  render(<App />)

  expect(await screen.findByRole('heading', { level: 1, name: task.title })).toBeInTheDocument()
  expect(await screen.findByText('本机 · 不自动同步')).toBeInTheDocument()
  expect(await screen.findAllByText('待复核')).toHaveLength(2)
  expect(await screen.findByText('排队中')).toBeInTheDocument()
  expect(await screen.findAllByText('成功')).toHaveLength(3)
  expect(screen.queryByText('QUEUED')).not.toBeInTheDocument()
  expect(screen.queryByText('SUCCEEDED')).not.toBeInTheDocument()
  expect(screen.queryByText('符合预设规则')).not.toBeInTheDocument()
  expect(screen.queryByText('存在差异')).not.toBeInTheDocument()
  expect(await screen.findByText('ExecutionPlan 哈希')).toBeInTheDocument()
  fireEvent.click(await screen.findByRole('button', { name: '查看报告' }))
  expect(await screen.findByText('结构预检，非科研结果')).toBeInTheDocument()
  expect(screen.getByText('5', { selector: 'dd' })).toBeInTheDocument()
  expect(screen.getByText(/不验证实验设计、数据真实性或科研结论/)).toBeInTheDocument()
  expect(fetchMock.mock.calls.every(([url]) => String(url).startsWith('http://127.0.0.1:8767/'))).toBe(true)
})

it('creates a reproduction task on the local runtime without a platform connection', async () => {
  const createdTask = { ...task, status: 'preparation', baseline: null }
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method ?? 'GET').toUpperCase()
    if (url.endsWith('/api/v1/local/session')) return response({ token: 'local-token', expires_in_seconds: 900 })
    if (url.endsWith('/api/v1/local/projects')) return response([])
    if (url.endsWith('/api/v1/local/reproductions') && method === 'GET') return response([])
    if (url.endsWith('/api/v1/local/reproductions') && method === 'POST') return response(createdTask, 201)
    if (url.endsWith(`/api/v1/local/reproductions/${taskId}`)) return response(createdTask)
    if (url.endsWith(`/api/v1/local/reproductions/${taskId}/workflows`)) return response([])
    return response({ detail: 'not found' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState(null, '', '#workbench/reproductions')

  render(<App />)

  fireEvent.click(await screen.findByRole('button', { name: '本机新建任务' }))
  expect(await screen.findByText('仅保存在本机，不会自动同步')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('论文标题'), { target: { value: '离线论文复现任务' } })
  fireEvent.change(screen.getByLabelText('论文来源（DOI / URL）'), { target: { value: 'DOI:10.0000/example' } })
  fireEvent.change(screen.getByLabelText('待核查的具体主张'), { target: { value: '核对预先记录的论文主张' } })
  fireEvent.click(screen.getByRole('button', { name: '创建复现任务' }))

  expect(await screen.findByRole('heading', { level: 1, name: createdTask.title })).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8767/api/v1/local/reproductions', expect.objectContaining({ method: 'POST' }))
  expect(fetchMock.mock.calls.every(([url]) => String(url).startsWith('http://127.0.0.1:8767/'))).toBe(true)
})
