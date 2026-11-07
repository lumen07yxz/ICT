import { describe, expect, it } from 'vitest'
import * as workflowApi from './workflows'

const { parseWorkflowComponent } = workflowApi

function componentWithProperty(property: Record<string, unknown>) {
  return {
    schema_version: 'ict.component.v1',
    component_id: 'ict.paper.crossref_metadata',
    version: '1.0.0',
    category: '文献与证据',
    title: 'Crossref DOI 元数据',
    description: '读取公开书目信息。',
    inputs: [],
    outputs: [],
    parameter_schema: {
      type: 'object',
      properties: { doi: property },
      required: ['doi'],
      additionalProperties: false,
    },
    executor_binding: 'ict.network.crossref',
    executor_version: '1.0.0',
    implementation_digest: 'a'.repeat(64),
    execution_target: 'network',
    dependencies: [],
    permissions: ['network:crossref:metadata:read'],
    resource_limits: {},
    cache_policy: 'not_configured',
    error_types: [],
    execution_available: true,
  }
}

describe('parseWorkflowComponent parameter constraints', () => {
  it('preserves the declared maximum string length', () => {
    const component = parseWorkflowComponent(componentWithProperty({
      type: 'string',
      title: 'DOI',
      description: '填写 DOI。',
      default: '',
      minLength: 1,
      maxLength: 300,
    }))

    expect((component.parameter_schema.properties.doi as unknown as { maxLength?: number }).maxLength).toBe(300)
  })

  it('rejects a non-integer or negative maximum string length', () => {
    for (const maxLength of [1.5, -1, '300']) {
      expect(() => parseWorkflowComponent(componentWithProperty({
        type: 'string',
        title: 'DOI',
        description: '填写 DOI。',
        default: '',
        minLength: 1,
        maxLength,
      }))).toThrow('Invalid workflow component parameter: doi')
    }
  })

  it('limits input by Unicode characters without splitting surrogate pairs', () => {
    const limit = (workflowApi as unknown as {
      limitWorkflowParameterValue?: (value: string, maxLength?: number) => string
    }).limitWorkflowParameterValue

    expect(typeof limit).toBe('function')
    if (!limit) return
    expect(limit('ab😀cd', 3)).toBe('ab😀')
    expect(limit('abc', undefined)).toBe('abc')
    expect(limit('abc', 0)).toBe('')
  })
})
