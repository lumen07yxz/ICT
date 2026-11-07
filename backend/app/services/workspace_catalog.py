"""Workspace membership helpers shared by project creation and demo seeding."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import DemoIdentity
from app.db.models import Workspace, WorkspaceMembership


def ensure_identity_workspace(session: Session, identity: DemoIdentity) -> Workspace:
    """Return the caller's first workspace, creating a personal one when absent."""
    row = session.execute(
        select(Workspace, WorkspaceMembership)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == identity.user_id)
        .order_by(Workspace.created_at, Workspace.id)
    ).first()
    if row is not None:
        workspace, membership = row
        if identity.role == "operator" and membership.role != "operator":
            membership.role = "operator"
        return workspace

    workspace = Workspace(
        id=uuid4(),
        name="默认工作空间",
        created_by=identity.user_id,
    )
    session.add(workspace)
    session.flush()
    session.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=identity.user_id,
            role=identity.role if identity.role in {"operator", "viewer"} else "viewer",
        )
    )
    session.flush()
    return workspace


def ensure_workspace_member(
    session: Session, *, workspace_id, user_id: str, role: str
) -> WorkspaceMembership:
    """Add a workspace member or upgrade its role without downgrading access."""
    membership = session.get(WorkspaceMembership, (workspace_id, user_id))
    if membership is None:
        membership = WorkspaceMembership(workspace_id=workspace_id, user_id=user_id, role=role)
        session.add(membership)
        return membership
    if role == "operator":
        membership.role = "operator"
    return membership
