import { afterEach, expect, it, vi } from 'vitest'
import {
  clearLocalRuntimeSession,
  createLocalProject,
  createLocalProjectWorkflow,
  getLocalProjectSyncState,
  getLocalWorkflowRun,
  importLocalCsv,
  listLocalWorkflowRuns,
  saveLocalWorkflowDraft,
  submitLocalWorkflowRun,
} from './localRuntime'
import { syncLocalProjectToPlatform } from './localProjectSync'
import type { WorkflowGraph } from './workflows'

const enabled = import.meta.env.VITE_LOCAL_SYNC_E2E === '1'
const runtimeOrigin = import.meta.env.VITE_LOCAL_RUNTIME_URL?.replace(/\/$/, '') ?? 'http://127.0.0.1:18791'
const platformConfig = { baseUrl: 'http://platform.test', token: 'test-token' }
const csvContent = 'sample_id,group,label\ns1,train,A\ns2,test,B\n'
const emptyGraph = { schema_version: 'ict.workflow.v1', nodes: [], edges: [] }

afterEach(() => {
  clearLocalRuntimeSession()
  vi.unstubAllGlobals()
})

it.skipIf(!enabled)('persists local runs while an explicit sync sends only definitions to a mock platform', async () => {
  const nativeFetch = globalThis.fetch.bind(globalThis)
  const platformRequests: Array<{ method: string; path: string; body: string; authorization: string | null }> = []
  const platformProjectId = 'platform-project-e2e'
  const platformWorkflowId = 'platform-workflow-e2e'
  const timestamp = '2026-11-03T00:00:00Z'
  let remoteWorkflow = {
    id: platformWorkflowId,
    workspace_id: 'workspace-e2e',
    owner_type: 'project',
    owner_id: platformProjectId,
    project_id: platformProjectId,
    reproduction_task_id: null,
    name: '离线 CSV 验收',
    description: '本机组件运行与显式同步',
    revision: 1,
    current_version: 0,
    created_at: timestamp,
    updated_at: timestamp,
    graph: emptyGraph,
    can_edit: true,
  }

  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const requestUrl = input instanceof Request ? input.url : String(input)
    const url = new URL(requestUrl)
    if (url.origin === runtimeOrigin) {
      const headers = new Headers(init.headers)
      headers.set('Origin', runtimeOrigin)
      headers.set('Sec-Fetch-Site', 'same-origin')
      return nativeFetch(input, { ...init, headers })
    }
    if (url.origin !== platformConfig.baseUrl) {
      throw new Error(`Unexpected non-loopback request: ${url.origin}`)
    }

    const method = (init.method ?? 'GET').toUpperCase()
    const body = typeof init.body === 'string' ? init.body : ''
    const headers = new Headers(init.headers)
    platformRequests.push({ method, path: url.pathname, body, authorization: headers.get('Authorization') })
    if (method === 'POST' && url.pathname === '/api/v1/projects') {
      const payload = JSON.parse(body) as { name: string; domain: string; description: string }
      return Response.json({
        id: platformProjectId,
        ...payload,
        role: 'owner',
        visibility: 'private',
        created_at: timestamp,
        datasets: [],
        pipeline_templates: [],
      }, { status: 201 })
    }
    if (method === 'POST' && url.pathname === `/api/v1/projects/${platformProjectId}/workflows`) {
      return Response.json(remoteWorkflow, { status: 201 })
    }
    if (method === 'PATCH' && url.pathname === `/api/v1/workflows/${platformWorkflowId}`) {
      const payload = JSON.parse(body) as { name: string; description: string; graph: typeof emptyGraph }
      remoteWorkflow = {
        ...remoteWorkflow,
        ...payload,
        revision: 2,
        updated_at: timestamp,
      }
      return Response.json(remoteWorkflow)
    }
    return Response.json({ error: { code: 'MOCK_ROUTE_NOT_FOUND' } }, { status: 404 })
  })

  const localProject = await createLocalProject({
    name: '离线 CSV 验收',
    domain: '数据分析',
    description: '本机文件和运行必须留在本机',
  })
  const localWorkflow = await createLocalProjectWorkflow(localProject.id, {
    name: '离线 CSV 验收',
    description: '本机组件运行与显式同步',
  })
  const file = new Blob([csvContent], { type: 'text/csv' }) as Blob & { name: string }
  Object.defineProperty(file, 'name', { value: 'private-synthetic.csv' })
  const artifact = await importLocalCsv(file)
  const graph: WorkflowGraph = {
    schema_version: 'ict.workflow.v1',
    nodes: [{
      id: 'csv-source',
      type: 'research',
      position: { x: 20, y: 20 },
      data: {
        component_id: 'ict.data.csv_artifact_source',
        component_version: '1.0.0',
        parameters: { artifact_id: artifact.artifact_id },
      },
    }],
    edges: [],
  }
  await saveLocalWorkflowDraft(localWorkflow.id, localWorkflow.revision + 1, graph)
  const submitted = await submitLocalWorkflowRun(localWorkflow.id, ['csv-source'])

  let localRun = await getLocalWorkflowRun(submitted.run_id)
  for (let attempt = 0; attempt < 60 && !['succeeded', 'partially_succeeded', 'failed', 'cancelled'].includes(localRun.status); attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 50))
    localRun = await getLocalWorkflowRun(submitted.run_id)
  }
  expect(localRun.status).toBe('succeeded')
  expect(await listLocalWorkflowRuns(localWorkflow.id)).toHaveLength(1)
  expect(platformRequests).toEqual([])

  const result = await syncLocalProjectToPlatform(platformConfig, localProject.id, {
    confirmUncertainRetry: false,
  })
  expect(result).toEqual({ platformProjectId, synchronizedWorkflows: 1, unchangedWorkflows: 0 })

  const outbox = await getLocalProjectSyncState(localProject.id)
  expect(outbox.status).toBe('synced')
  expect(outbox.platform_project_id).toBe(platformProjectId)
  expect(outbox.workflows[0]).toMatchObject({
    workflow_id: localWorkflow.id,
    status: 'synced',
    platform_workflow_id: platformWorkflowId,
    source_revision: 2,
    synced_revision: 2,
  })
  expect(platformRequests.map(({ method, path }) => `${method} ${path}`)).toEqual([
    'POST /api/v1/projects',
    `POST /api/v1/projects/${platformProjectId}/workflows`,
    `PATCH /api/v1/workflows/${platformWorkflowId}`,
  ])
  expect(platformRequests.every((request) => request.authorization === 'Bearer test-token')).toBe(true)
  const sentBodies = platformRequests.map((request) => request.body).join('\n')
  expect(sentBodies).toContain(artifact.artifact_id)
  expect(sentBodies).not.toContain(csvContent)
  expect(sentBodies).not.toContain('test-token')
  expect(sentBodies).not.toContain(submitted.run_id)
  expect(sentBodies).not.toContain('report_content')

  // A sync must leave the original file and run readable from the local runtime.
  expect((await getLocalWorkflowRun(submitted.run_id)).status).toBe('succeeded')
})
