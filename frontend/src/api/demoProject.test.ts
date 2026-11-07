import { afterEach, expect, it, vi } from 'vitest'
import { getDemoProjectOverview } from './demoProject'

afterEach(() => vi.unstubAllGlobals())

it('rejects a response that claims the synthetic project is research-ready', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      project_id: 'demo-research',
      purpose: 'synthetic fixture',
      data_status: 'synthetic_only',
      research_ready: true,
      dataset_versions: [],
      pipeline_templates: [],
      recent_public_runs: [],
    }),
  }))

  await expect(getDemoProjectOverview()).rejects.toThrow('Invalid project response')
})
