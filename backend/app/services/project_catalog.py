"""Project queries and creation with membership-based visibility."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import DemoIdentity
from app.db.models import Membership, Project
from app.errors import AppError
from app.services.workspace_catalog import ensure_identity_workspace


def list_projects(session: Session, identity: DemoIdentity) -> list[tuple[Project, str]]:
    """Return only projects that have an explicit membership for the caller."""
    rows = session.execute(
        select(Project, Membership.role)
        .join(Membership, Membership.project_id == Project.id)
        .where(Membership.user_id == identity.user_id)
        .order_by(Project.created_at, Project.id)
    )
    return list(rows.tuples())


def get_project(session: Session, identity: DemoIdentity, project_id: UUID) -> tuple[Project, str]:
    """Hide both missing and unowned projects behind the same not-found response."""
    row = session.execute(
        select(Project, Membership.role)
        .options(selectinload(Project.dataset_versions))
        .join(Membership, Membership.project_id == Project.id)
        .where(Project.id == project_id, Membership.user_id == identity.user_id)
    ).one_or_none()
    if row is None:
        raise AppError(404, "PROJECT_NOT_FOUND")
    return row[0], row[1]


def create_project(
    session: Session,
    identity: DemoIdentity,
    *,
    name: str,
    domain: str,
    description: str,
) -> tuple[Project, str]:
    """Create one project owned by the authenticated demo operator."""
    if identity.role != "operator":
        raise AppError(403, "OPERATOR_REQUIRED")

    workspace = ensure_identity_workspace(session, identity)
    project = Project(
        id=uuid4(),
        workspace_id=workspace.id,
        name=name,
        domain=domain,
        description=description,
        visibility="private",
    )
    session.add(project)
    session.add(Membership(project_id=project.id, user_id=identity.user_id, role="operator"))
    session.commit()
    session.refresh(project)
    return project, "operator"
