import {
  createWorkflowVersion,
  getWorkflow,
  saveWorkflowDraft,
  WorkflowApiError,
  type WorkflowDetail,
} from './api/workflows'
import type { ApiConfig } from './api/projects'

export class WorkflowRevisionMovedError extends Error {
  readonly latest: WorkflowDetail

  constructor(latest: WorkflowDetail) {
    super('The platform workflow changed while resolving the local draft conflict.')
    this.name = 'WorkflowRevisionMovedError'
    this.latest = latest
  }
}

export function isWorkflowRevisionConflict(error: unknown): error is WorkflowApiError {
  return error instanceof WorkflowApiError && error.status === 409 && error.code === 'WORKFLOW_REVISION_CONFLICT'
}

/** Preserve the reviewed platform metadata and graph before explicitly applying the local draft. */
export async function syncConflictedWorkflowToPlatform(
  config: ApiConfig,
  localDraft: Pick<WorkflowDetail, 'id' | 'name' | 'description' | 'graph'>,
  expectedPlatformRevision: number,
): Promise<WorkflowDetail> {
  const current = await getWorkflow(config, localDraft.id)
  if (current.revision !== expectedPlatformRevision) throw new WorkflowRevisionMovedError(current)

  // The immutable snapshot ensures the platform's current draft remains available after an explicit sync.
  const snapshot = await createWorkflowVersion(config, localDraft.id)
  if (snapshot.workflow.revision !== expectedPlatformRevision) {
    throw new WorkflowRevisionMovedError(await getWorkflow(config, localDraft.id))
  }
  if (snapshot.version.name !== current.name || snapshot.version.description !== current.description) {
    throw new Error('The platform version snapshot does not contain its reviewed metadata.')
  }

  try {
    return await saveWorkflowDraft(config, {
      ...localDraft,
      revision: expectedPlatformRevision,
    })
  } catch (error) {
    if (!isWorkflowRevisionConflict(error)) throw error
    throw new WorkflowRevisionMovedError(await getWorkflow(config, localDraft.id))
  }
}
