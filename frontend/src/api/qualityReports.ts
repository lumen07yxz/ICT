import type { ApiConfig } from './projects'

export type QualityReportStatus = 'success' | 'warning' | 'blocker'

export interface QualityReportIssue {
  code: string
  severity: 'warning' | 'blocker'
  message: string
  count: number
  line_numbers: number[]
  guidance: string
}

export interface SyntheticDatasetQualityReport {
  dataset_version: 'dataset-synthetic-v1'
  status: QualityReportStatus
  rule_set_version: string
  manifest_sha256: string
  row_count: number
  split_counts: Record<string, number>
  label_category_count: number
  issues: QualityReportIssue[]
  synthetic_only: true
  research_ready: false
  checked_at: string
}

export class QualityReportApiError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`Quality report request failed (${status})`)
    this.name = 'QualityReportApiError'
    this.status = status
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 0
}

function parseIssue(value: unknown): QualityReportIssue {
  if (!isRecord(value) || typeof value.code !== 'string' ||
      (value.severity !== 'warning' && value.severity !== 'blocker') ||
      typeof value.message !== 'string' || !isNonNegativeInteger(value.count) ||
      !Array.isArray(value.line_numbers) || !value.line_numbers.every(isNonNegativeInteger) ||
      typeof value.guidance !== 'string') {
    throw new Error('Invalid synthetic quality report')
  }

  return {
    code: value.code,
    severity: value.severity,
    message: value.message,
    count: value.count,
    line_numbers: value.line_numbers,
    guidance: value.guidance,
  }
}

function parseSyntheticDatasetQualityReport(value: unknown): SyntheticDatasetQualityReport {
  if (!isRecord(value) || value.dataset_version !== 'dataset-synthetic-v1' ||
      (value.status !== 'success' && value.status !== 'warning' && value.status !== 'blocker') ||
      typeof value.rule_set_version !== 'string' ||
      typeof value.manifest_sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(value.manifest_sha256) ||
      !isNonNegativeInteger(value.row_count) || !isRecord(value.split_counts) ||
      !Object.entries(value.split_counts).every(([name, count]) => name.length > 0 && isNonNegativeInteger(count)) ||
      !isNonNegativeInteger(value.label_category_count) || !Array.isArray(value.issues) ||
      value.synthetic_only !== true || value.research_ready !== false ||
      typeof value.checked_at !== 'string' || Number.isNaN(Date.parse(value.checked_at))) {
    throw new Error('Invalid synthetic quality report')
  }

  return {
    dataset_version: 'dataset-synthetic-v1',
    status: value.status,
    rule_set_version: value.rule_set_version,
    manifest_sha256: value.manifest_sha256,
    row_count: value.row_count,
    split_counts: value.split_counts as Record<string, number>,
    label_category_count: value.label_category_count,
    issues: value.issues.map(parseIssue),
    synthetic_only: true,
    research_ready: false,
    checked_at: value.checked_at,
  }
}

export async function getSyntheticDatasetQualityReport(
  config: ApiConfig,
  signal?: AbortSignal,
): Promise<SyntheticDatasetQualityReport> {
  const baseUrl = config.baseUrl.trim().replace(/\/$/, '')
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (config.token.trim()) headers.Authorization = `Bearer ${config.token.trim()}`

  const response = await fetch(
    `${baseUrl}/api/v1/projects/demo/demo-research/datasets/dataset-synthetic-v1/quality-report`,
    { headers, signal },
  )
  if (!response.ok) throw new QualityReportApiError(response.status)
  return parseSyntheticDatasetQualityReport(await response.json())
}
