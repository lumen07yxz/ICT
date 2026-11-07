import { describe, expect, it } from 'vitest'
import { workflowRunErrorDetails } from './workflowRunErrors'

describe('workflow run error explanations', () => {
  it('explains external wait timeouts and their downstream scope', () => {
    const details = workflowRunErrorDetails('EXTERNAL_WAIT_TIMEOUT')

    expect(details.reason).toContain('外部')
    expect(details.impact).toContain('下游')
    expect(details.nextStep).toContain('重试')
  })

  it('distinguishes a failed dependency from the original failed node', () => {
    const details = workflowRunErrorDetails('DEPENDENCY_FAILED')

    expect(details.reason).toContain('上游')
    expect(details.impact).toContain('未运行')
    expect(details.nextStep).toContain('失败节点')
  })

  it('localizes stable CSV, artifact, report, and Crossref run failures', () => {
    const knownRunErrorCodes = [
      'CSV_ARTIFACT_REQUIRED', 'CSV_COLUMNS_INVALID', 'CSV_COLUMNS_NOT_FOUND', 'CSV_ROW_WIDTH_MISMATCH',
      'ARTIFACT_AUTHORIZATION_REQUIRED', 'ARTIFACT_CONTENT_HASH_MISMATCH', 'ARTIFACT_CSV_REQUIRED',
      'ARTIFACT_EMPTY', 'ARTIFACT_FILE_MISSING', 'ARTIFACT_FILE_NAME_INVALID', 'ARTIFACT_NOT_FOUND',
      'ARTIFACT_PRODUCER_INVALID', 'ARTIFACT_RUN_INVALID', 'ARTIFACT_SIZE_MISMATCH', 'ARTIFACT_SOURCE_REQUIRED',
      'ARTIFACT_STORAGE_KEY_INVALID', 'ARTIFACT_STREAM_INVALID', 'ARTIFACT_TOO_LARGE',
      'ARTIFACT_REPORT_TOO_LARGE', 'ARTIFACT_REPORT_TYPE_UNSUPPORTED', 'ARTIFACT_REPORT_UNREADABLE',
      'LOCAL_CHECKER_UNAVAILABLE', 'LOCAL_STORE_UNAVAILABLE', 'LOCAL_ARTIFACT_WRITE_FAILED',
      'REPORT_NOT_SERIALIZABLE', 'REPORT_EMPTY', 'REPORT_TOO_LARGE', 'REPORT_PRODUCER_INVALID',
      'REPORT_RUN_INVALID', 'REPORT_FILE_NAME_INVALID', 'REPORT_AUTHORIZATION_INVALID',
      'NETWORK_HTTP_ERROR', 'NETWORK_REDIRECT_REJECTED', 'NETWORK_RESPONSE_INVALID',
      'NETWORK_RESPONSE_TOO_LARGE', 'NETWORK_RESULT_PERSIST_FAILED',
      'manifest_unreadable', 'manifest_header_missing', 'manifest_header_duplicate',
      'missing_required_columns', 'invalid_encoding', 'invalid_csv', 'manifest_changed',
    ]

    for (const code of knownRunErrorCodes) {
      const details = workflowRunErrorDetails(code)

      expect(details.reason, `${code} reason`).not.toBe('运行未能完成')
      expect(details.impact, `${code} impact`).not.toBe('节点没有生成成功结果；依赖它的下游可能未运行。')
      expect(details.nextStep.trim(), `${code} next step`).not.toBe('')
    }
  })

  it.each([
    ['CSV_COLUMNS_NOT_FOUND', '字段'],
    ['ARTIFACT_CONTENT_HASH_MISMATCH', '校验'],
    ['NETWORK_REDIRECT_REJECTED', '重定向'],
    ['NETWORK_RESPONSE_INVALID', '元数据'],
    ['NETWORK_RESULT_PERSIST_FAILED', '保存'],
    ['ARTIFACT_REPORT_TOO_LARGE', '超过'],
    ['ARTIFACT_REPORT_TYPE_UNSUPPORTED', '不受支持'],
    ['ARTIFACT_REPORT_UNREADABLE', '无法读取'],
    ['manifest_unreadable', '无法读取'],
    ['manifest_header_missing', '表头'],
    ['manifest_header_duplicate', '重复'],
    ['missing_required_columns', '必需列'],
    ['invalid_encoding', '编码'],
    ['invalid_csv', 'CSV'],
    ['manifest_changed', '发生变化'],
  ])('gives %s a specific explanation', (code, expectedText) => {
    expect(workflowRunErrorDetails(code).reason).toContain(expectedText)
  })

  it('provides a safe explanation for error codes that have no mapping yet', () => {
    const details = workflowRunErrorDetails('FUTURE_COMPONENT_ERROR')

    expect(details.reason).toBe('运行未能完成')
    expect(details.impact).toContain('成功结果')
    expect(details.nextStep).toContain('运行时日志')
  })
})
