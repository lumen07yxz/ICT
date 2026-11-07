import type { WorkflowComponent, WorkflowGraph } from './api/workflows'

// Compare saved and loaded graphs using the same registry defaults. A newly
// added component default should not make an unchanged older draft look edited.
export function workflowDraftSnapshot(
  name: string,
  description: string,
  graph: WorkflowGraph,
  components: WorkflowComponent[] = [],
): string {
  const componentsById = new Map(components.map((component) => [component.component_id, component]))
  const normalizedGraph: WorkflowGraph = {
    schema_version: 'ict.workflow.v1',
    nodes: graph.nodes.map((node) => {
      const componentId = typeof node.data.component_id === 'string' ? node.data.component_id : undefined
      const component = componentId ? componentsById.get(componentId) : undefined
      const defaults = component
        ? Object.fromEntries(Object.entries(component.parameter_schema.properties).map(
          ([key, property]) => [key, property.default],
        ))
        : undefined
      const storedParameters = node.data.parameters
      const parameters = typeof storedParameters === 'object' && storedParameters !== null && !Array.isArray(storedParameters)
        ? storedParameters as Record<string, unknown>
        : {}
      const data = {
        category: typeof node.data.category === 'string' ? node.data.category : '科研组件',
        title: typeof node.data.title === 'string' ? node.data.title : '未命名节点',
        description: typeof node.data.description === 'string' ? node.data.description : '',
        ...(componentId ? { component_id: componentId } : {}),
        ...(typeof node.data.component_version === 'string' ? { component_version: node.data.component_version } : {}),
        ...(defaults || node.data.parameters !== undefined ? { parameters: { ...defaults, ...parameters } } : {}),
      }
      return { id: node.id, type: node.type || 'research', position: { x: node.position.x, y: node.position.y }, data }
    }),
    edges: graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? null,
      targetHandle: edge.targetHandle ?? null,
      // The editor restores missing edge types as smoothstep before saving.
      type: edge.type ?? 'smoothstep',
    })),
  }
  return JSON.stringify({ name, description, graph: normalizedGraph })
}
