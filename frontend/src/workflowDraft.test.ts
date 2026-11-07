import { expect, it } from 'vitest'
import type { WorkflowComponent, WorkflowGraph } from './api/workflows'
import { workflowDraftSnapshot } from './workflowDraft'

const graphWithoutMaterializedDefaults: WorkflowGraph = {
  schema_version: 'ict.workflow.v1',
  nodes: [{
    id: 'quality-node',
    type: 'research',
    position: { x: 80, y: 210 },
    data: {
      category: '数据检验',
      title: 'CSV 质量检查',
      description: '逐文件检查',
      component_id: 'ict.data.quality_check',
      component_version: '2.0.0',
      parameters: { required_columns: '', unique_key_columns: '' },
    },
  }],
  edges: [],
}

const qualityComponent = {
  component_id: 'ict.data.quality_check',
  parameter_schema: {
    properties: { max_missing_rate: { default: '0.05' } },
  },
} as unknown as WorkflowComponent

it('treats schema defaults added while loading as unchanged saved workflow data', () => {
  const hydratedGraph: WorkflowGraph = {
    ...graphWithoutMaterializedDefaults,
    nodes: graphWithoutMaterializedDefaults.nodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        parameters: {
          ...(node.data.parameters as Record<string, unknown>),
          max_missing_rate: '0.05',
        },
      },
    })),
  }

  expect(workflowDraftSnapshot('CSV 检查', '', graphWithoutMaterializedDefaults, [qualityComponent]))
    .toBe(workflowDraftSnapshot('CSV 检查', '', hydratedGraph, [qualityComponent]))
})

it('keeps an explicit parameter edit dirty after applying schema defaults', () => {
  const editedGraph: WorkflowGraph = {
    ...graphWithoutMaterializedDefaults,
    nodes: graphWithoutMaterializedDefaults.nodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        parameters: {
          ...(node.data.parameters as Record<string, unknown>),
          max_missing_rate: '0.10',
        },
      },
    })),
  }

  expect(workflowDraftSnapshot('CSV 检查', '', graphWithoutMaterializedDefaults, [qualityComponent]))
    .not.toBe(workflowDraftSnapshot('CSV 检查', '', editedGraph, [qualityComponent]))
})

it('treats editor display defaults for legacy node fields and edge types as unchanged', () => {
  const legacyGraph: WorkflowGraph = {
    schema_version: 'ict.workflow.v1',
    nodes: [{
      id: 'quality-node',
      type: 'research',
      position: { x: 80, y: 210 },
      data: { component_id: 'ict.data.quality_check', component_version: '2.0.0' },
    }],
    edges: [{ id: 'edge-1', source: 'source-node', target: 'quality-node' }],
  }
  const editorLoadedGraph: WorkflowGraph = {
    ...legacyGraph,
    nodes: legacyGraph.nodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        category: '科研组件',
        title: '未命名节点',
        description: '',
        parameters: { max_missing_rate: '0.05' },
      },
    })),
    edges: legacyGraph.edges.map((edge) => ({
      ...edge,
      sourceHandle: null,
      targetHandle: null,
      type: 'smoothstep',
    })),
  }

  expect(workflowDraftSnapshot('旧工作流', '', legacyGraph, [qualityComponent]))
    .toBe(workflowDraftSnapshot('旧工作流', '', editorLoadedGraph, [qualityComponent]))
})
