"""Workspace-scoped access to independent paper and experiment tasks."""

from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import DemoIdentity
from app.db.models import (
    Membership,
    Project,
    ReproductionTask,
    Workspace,
    WorkspaceMembership,
)
from app.errors import AppError
from app.services.workspace_catalog import ensure_identity_workspace


ReproductionKind = Literal["paper", "experiment"]
ReproductionStatus = Literal[
    "preparation",
    "insufficient_conditions",
    "ready_to_run",
    "running",
    "awaiting_review",
    "conforms",
    "differs",
    "undetermined",
]


def list_reproduction_tasks(
    session: Session,
    identity: DemoIdentity,
    *,
    kind: ReproductionKind | None = None,
    status: ReproductionStatus | None = None,
    linked_project_id: UUID | None = None,
) -> list[ReproductionTask]:
    """List tasks only in workspaces where the caller has membership."""
    statement = (
        select(ReproductionTask)
        .join(
            WorkspaceMembership,
            WorkspaceMembership.workspace_id == ReproductionTask.workspace_id,
        )
        .where(WorkspaceMembership.user_id == identity.user_id)
    )
    if kind is not None:
        statement = statement.where(ReproductionTask.kind == kind)
    if status is not None:
        statement = statement.where(ReproductionTask.status == status)
    if linked_project_id is not None:
        statement = statement.where(ReproductionTask.linked_project_id == linked_project_id)

    rows = session.scalars(
        statement.order_by(ReproductionTask.updated_at.desc(), ReproductionTask.id)
    )
    return list(rows)


def get_reproduction_task(
    session: Session, identity: DemoIdentity, task_id: UUID
) -> ReproductionTask:
    """Hide missing and unauthorized tasks behind the same not-found response."""
    task = session.scalar(
        select(ReproductionTask)
        .join(
            WorkspaceMembership,
            WorkspaceMembership.workspace_id == ReproductionTask.workspace_id,
        )
        .where(
            ReproductionTask.id == task_id,
            WorkspaceMembership.user_id == identity.user_id,
        )
    )
    if task is None:
        raise AppError(404, "REPRODUCTION_TASK_NOT_FOUND")
    return task


def create_reproduction_task(
    session: Session,
    identity: DemoIdentity,
    *,
    title: str,
    kind: ReproductionKind,
    source: str,
    claim: str,
    baseline: dict[str, Any] | None,
    criteria_version: str | None,
    linked_project_id: UUID | None,
    workspace_id: UUID | None,
) -> ReproductionTask:
    """Create a preparation task; creation never asserts a research result."""
    if identity.role != "operator":
        raise AppError(403, "OPERATOR_REQUIRED")

    linked_project = None
    if linked_project_id is not None:
        linked_project = session.scalar(
            select(Project)
            .join(Membership, Membership.project_id == Project.id)
            .where(
                Project.id == linked_project_id,
                Project.workspace_id == workspace.id,
                Membership.user_id == identity.user_id,
            )
        )
        if linked_project is None:
            raise AppError(404, "PROJECT_NOT_FOUND")

    if workspace_id is not None:
        membership = session.get(WorkspaceMembership, (workspace_id, identity.user_id))
        if membership is None:
            raise AppError(404, "WORKSPACE_NOT_FOUND")
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            raise AppError(404, "WORKSPACE_NOT_FOUND")
    elif linked_project is not None:
        # A selected project determines the task workspace when no workspace was chosen.
        workspace = session.get(Workspace, linked_project.workspace_id)
        membership = session.get(
            WorkspaceMembership, (linked_project.workspace_id, identity.user_id)
        )
    else:
        workspace = ensure_identity_workspace(session, identity)
        membership = session.get(
            WorkspaceMembership, (workspace.id, identity.user_id)
        )

    if workspace is None or membership is None:
        raise AppError(404, "WORKSPACE_NOT_FOUND")
    if membership.role != "operator":
        raise AppError(403, "OPERATOR_REQUIRED")
    if linked_project is not None and linked_project.workspace_id != workspace.id:
        raise AppError(404, "PROJECT_NOT_FOUND")

    task = ReproductionTask(
        id=uuid4(),
        workspace_id=workspace.id,
        linked_project_id=linked_project_id,
        title=title,
        kind=kind,
        source=source,
        claim=claim,
        baseline=baseline,
        criteria_version=criteria_version,
        status="preparation",
        created_by=identity.user_id,
        updated_by=identity.user_id,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task
