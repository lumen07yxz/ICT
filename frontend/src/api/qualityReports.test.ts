import { afterEach, expect, it, vi } from 'vitest'
import { getSyntheticDatasetQualityReport } from './qualityReports'

afterEach(() => vi.unstubAllGlobals())

const reportFixture = {
  dataset_version: 'dataset-synthetic-v1',
  status: 'success',
  rule_set_version: 'generic-manifest-v1',
  manifest_sha256: 'a'.repeat(64),
  row_count: 4,
  split_counts: { train: 2, validation: 1, test: 1 },
  label_category_count: 2,
  issues: [],
  synthetic_only: true,
  research_ready: false,
  checked_at: '2026-10-31T10:00:00Z',
}

it('reads the fixed synthetic manifest report with the configured bearer token', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => reportFixture })
  vi.stubGlobal('fetch', fetchMock)
  const controller = new AbortController()

  const report = await getSyntheticDatasetQualityReport(
    { baseUrl: 'http://127.0.0.1:8765/', token: 'operator-test-token' },
    controller.signal,
  )

  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8765/api/v1/projects/demo/demo-research/datasets/dataset-synthetic-v1/quality-report',
    {
      headers: { Accept: 'application/json', Authorization: 'Bearer operator-test-token' },
      signal: controller.signal,
    },
  )
  expect(report.dataset_version).toBe('dataset-synthetic-v1')
  expect(report.row_count).toBe(4)
  expect(report.synthetic_only).toBe(true)
  expect(report.research_ready).toBe(false)
})

it('rejects a response that mislabels the synthetic report as research-ready', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ...reportFixture, research_ready: true }),
  }))

  await expect(getSyntheticDatasetQualityReport({ baseUrl: '', token: '' }))
    .rejects.toThrow('Invalid synthetic quality report')
})

it('rejects reports that include malformed aggregate counts or an invalid digest', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ...reportFixture, row_count: -1, manifest_sha256: 'not-a-digest' }),
  }))

  await expect(getSyntheticDatasetQualityReport({ baseUrl: '', token: '' }))
    .rejects.toThrow('Invalid synthetic quality report')
})

it('preserves an API failure as a typed status error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))

  await expect(getSyntheticDatasetQualityReport({ baseUrl: '', token: '' }))
    .rejects.toMatchObject({ status: 401 })
})
