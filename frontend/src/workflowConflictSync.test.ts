import { afterEach, describe, expect, it, vi } from 'vitest'
import { createWorkflowVersion, getWorkflow, saveWorkflowDraft, WorkflowApiError, type WorkflowDetail } from './api/workflows'
import { isWorkflowRevisionConflict, syncConflictedWorkflowToPlatform, WorkflowRevisionMovedError } from './workflowConflictSync'

vi.mock('./api/workflows', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workflows')>()
  return {
    ...actual,
    createWorkflowVersion: vi.fn(),
    getWorkflow: vi.fn(),
    saveWorkflowDraft: vi.fn(),
  }
})

const config = { baseUrl: 'http://127.0.0.1:8765', token: 'test-token' }
const graph: WorkflowDetail['graph'] = { schema_version: 'ict.workflow.v1', nodes: [], edges: [] }

function workflow(revision: number): WorkflowDetail {
  return {
    id: 'workflow-1',
    workspace_id: 'workspace-1',
    owner_type: 'project',
    owner_id: 'project-1',
    project_id: 'project-1',
    reproduction_task_id: null,
    name: `平台修订 ${revision}`,
    description: '',
    revision,
    current_version: Math.max(0, revision - 1),
    created_at: '2026-11-03T00:00:00Z',
    updated_at: '2026-11-03T00:00:00Z',
    graph,
    can_edit: true,
  }
}

function createdVersion(revision: number) {
  const current = workflow(revision)
  return {
    created: true,
    workflow: {
      id: current.id,
      workspace_id: current.workspace_id,
      owner_type: current.owner_type,
      owner_id: current.owner_id,
      project_id: current.project_id,
      reproduction_task_id: current.reproduction_task_id,
      name: current.name,
      description: current.description,
      revision: current.revision,
      current_version: current.current_version,
      created_at: current.created_at,
      updated_at: current.updated_at,
    },
    version: {
      id: 'version-1',
      workflow_id: current.id,
      version: current.current_version,
      name: current.name,
      description: current.description,
      schema_version: 'ict.workflow.v1',
      content_hash: 'workflow-hash',
      created_by: 'operator-1',
      created_at: current.updated_at,
    },
  }
}

afterEach(() => vi.clearAllMocks())

describe('workflow revision conflict recovery', () => {
  it('snapshots the reviewed platform draft before saving local content against its revision', async () => {
    const calls: string[] = []
    const current = workflow(2)
    const saved = workflow(3)
    vi.mocked(getWorkflow).mockImplementation(async () => { calls.push('read'); return current })
    vi.mocked(createWorkflowVersion).mockImplementation(async () => { calls.push('snapshot'); return createdVersion(2) })
    vi.mocked(saveWorkflowDraft).mockImplementation(async (_config, payload) => { calls.push('save'); expect(payload.revision).toBe(2); return saved })

    const result = await syncConflictedWorkflowToPlatform(config, {
      id: current.id,
      name: '本机草稿',
      description: '本机修改',
      graph: { ...graph, nodes: [{ id: 'local-node', type: 'default', position: { x: 0, y: 0 }, data: {} }] },
    }, 2)

    expect(calls).toEqual(['read', 'snapshot', 'save'])
    expect(vi.mocked(saveWorkflowDraft).mock.calls[0][1]).toMatchObject({ name: '本机草稿', description: '本机修改' })
    expect(result.revision).toBe(3)
  })

  it('does not create a snapshot or save when the platform revision already moved', async () => {
    vi.mocked(getWorkflow).mockResolvedValue(workflow(3))

    await expect(syncConflictedWorkflowToPlatform(config, {
      id: 'workflow-1', name: '本机草稿', description: '', graph,
    }, 2)).rejects.toMatchObject({ name: 'WorkflowRevisionMovedError', latest: { revision: 3 } })

    expect(createWorkflowVersion).not.toHaveBeenCalled()
    expect(saveWorkflowDraft).not.toHaveBeenCalled()
  })

  it('rechecks the platform if another revision appears while its snapshot is being created', async () => {
    vi.mocked(getWorkflow).mockResolvedValueOnce(workflow(2)).mockResolvedValueOnce(workflow(3))
    vi.mocked(createWorkflowVersion).mockResolvedValue(createdVersion(3))

    await expect(syncConflictedWorkflowToPlatform(config, {
      id: 'workflow-1', name: '本机草稿', description: '', graph,
    }, 2)).rejects.toMatchObject({ name: 'WorkflowRevisionMovedError', latest: { revision: 3 } })

    expect(saveWorkflowDraft).not.toHaveBeenCalled()
  })

  it('refreshes the latest platform revision when an optimistic save races with another edit', async () => {
    vi.mocked(getWorkflow).mockResolvedValueOnce(workflow(2)).mockResolvedValueOnce(workflow(3))
    vi.mocked(createWorkflowVersion).mockResolvedValue(createdVersion(2))
    vi.mocked(saveWorkflowDraft).mockRejectedValue(new WorkflowApiError(409, 'WORKFLOW_REVISION_CONFLICT'))

    await expect(syncConflictedWorkflowToPlatform(config, {
      id: 'workflow-1', name: '本机草稿', description: '', graph,
    }, 2)).rejects.toMatchObject({ name: 'WorkflowRevisionMovedError', latest: { revision: 3 } })
  })

  it('recognizes only the workflow revision conflict response', () => {
    expect(isWorkflowRevisionConflict(new WorkflowApiError(409, 'WORKFLOW_REVISION_CONFLICT'))).toBe(true)
    expect(isWorkflowRevisionConflict(new WorkflowApiError(409, 'WORKFLOW_NOT_FOUND'))).toBe(false)
    expect(isWorkflowRevisionConflict(new WorkflowApiError(500, 'WORKFLOW_REVISION_CONFLICT'))).toBe(false)
    expect(isWorkflowRevisionConflict(new Error('WORKFLOW_REVISION_CONFLICT'))).toBe(false)
  })

  it('exposes the current platform copy when the expected revision has changed', async () => {
    const latest = workflow(4)
    vi.mocked(getWorkflow).mockResolvedValue(latest)

    const error = await syncConflictedWorkflowToPlatform(config, {
      id: 'workflow-1', name: '本机草稿', description: '', graph,
    }, 3).catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(WorkflowRevisionMovedError)
    expect((error as WorkflowRevisionMovedError).latest).toBe(latest)
  })
})
