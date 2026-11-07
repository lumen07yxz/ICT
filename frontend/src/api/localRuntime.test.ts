import { afterEach, expect, it, vi } from 'vitest'
import { getLocalRuntimeHealth, listLocalWorkflowComponents, LocalRuntimeApiError } from './localRuntime'

afterEach(() => vi.unstubAllGlobals())

it('checks the standalone runtime without depending on the platform API', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', mode: 'local', platform_required: false }) })
  vi.stubGlobal('fetch', fetchMock)

  await expect(getLocalRuntimeHealth()).resolves.toEqual({ status: 'ok', mode: 'local', platform_required: false })
  expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8767/health', expect.objectContaining({ method: 'GET' }))
})

it('pairs a short local session and reads the locally available component contracts', async () => {
  const catalog = [{
    schema_version: 'ict.component.v1',
    component_id: 'ict.data.csv_manifest_preflight',
    version: '1.0.0',
    category: '数据检验',
    title: '本机 CSV 结构预检',
    description: '读取本机 CSV 并生成结构报告。',
    inputs: [],
    outputs: [],
    parameter_schema: { type: 'object', properties: {}, required: [], additionalProperties: false },
    executor_binding: 'ict.local.csv_manifest_preflight',
    executor_version: '1.0.0',
    implementation_digest: 'a'.repeat(64),
    execution_target: 'local',
    dependencies: [],
    permissions: ['local:artifact:read'],
    resource_limits: { cpu_millicores: 500, memory_mb: 512, gpu_count: 0, gpu_memory_mb: 0, timeout_seconds: 120, max_input_bytes: 1024 },
    cache_policy: 'not_configured',
    error_types: [],
    execution_available: true,
  }]
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ token: 'short-lived-token', expires_in_seconds: 900 }) })
    .mockResolvedValueOnce({ ok: true, json: async () => catalog })
  vi.stubGlobal('fetch', fetchMock)

  await expect(listLocalWorkflowComponents()).resolves.toEqual(catalog)

  expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://127.0.0.1:8767/api/v1/local/session', expect.objectContaining({ method: 'POST' }))
  const requestOptions = fetchMock.mock.calls[1][1] as RequestInit
  expect(fetchMock.mock.calls[1][0]).toBe('http://127.0.0.1:8767/api/v1/local/workflow-components')
  expect((requestOptions.headers as Headers).get('X-ICT-Local-Token')).toBe('short-lived-token')
})

it('keeps local service failures as typed errors without leaking request values', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false,
    status: 503,
    json: async () => ({ error: { code: 'LOCAL_STORE_UNAVAILABLE' } }),
  }))

  await expect(getLocalRuntimeHealth()).rejects.toBeInstanceOf(LocalRuntimeApiError)
})
