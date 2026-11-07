"""Add workspace isolation and project/reproduction workflow ownership."""

from typing import Sequence, Union
from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op
import sqlalchemy as sa


revision: str = "0007_workspace_reproduction_ownership"
down_revision: Union[str, None] = "0006_project_workflows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_workspaces(connection) -> None:
    """Give each existing user a workspace and retain every project's membership scope."""
    projects = sa.table(
        "projects",
        sa.column("id", sa.Uuid()),
        sa.column("workspace_id", sa.Uuid()),
    )
    memberships = sa.table(
        "memberships",
        sa.column("project_id", sa.Uuid()),
        sa.column("user_id", sa.String(80)),
        sa.column("role", sa.String(16)),
    )
    workspaces = sa.table(
        "workspaces",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String(160)),
        sa.column("created_by", sa.String(80)),
    )
    workspace_memberships = sa.table(
        "workspace_memberships",
        sa.column("workspace_id", sa.Uuid()),
        sa.column("user_id", sa.String(80)),
        sa.column("role", sa.String(16)),
    )

    member_rows = connection.execute(
        sa.select(memberships.c.project_id, memberships.c.user_id, memberships.c.role)
        .order_by(memberships.c.project_id, memberships.c.user_id)
    ).all()
    roles_by_user: dict[str, str] = {}
    members_by_project: dict[UUID, list[tuple[str, str]]] = {}
    for project_id, user_id, role in member_rows:
        roles_by_user[user_id] = (
            "operator" if role == "operator" or roles_by_user.get(user_id) == "operator" else "viewer"
        )
        members_by_project.setdefault(project_id, []).append((user_id, role))

    workspace_by_user: dict[str, UUID] = {}
    for user_id in sorted(roles_by_user):
        workspace_id = uuid5(NAMESPACE_URL, f"ict/workspaces/{user_id}")
        workspace_by_user[user_id] = workspace_id
        connection.execute(
            workspaces.insert().values(
                id=workspace_id,
                name="默认工作空间",
                created_by=user_id,
            )
        )

    workspace_role_by_member: dict[tuple[UUID, str], str] = {
        (workspace_by_user[user_id], user_id): role for user_id, role in roles_by_user.items()
    }
    project_rows = connection.execute(sa.select(projects.c.id)).scalars().all()
    for project_id in project_rows:
        project_members = members_by_project.get(project_id, [])
        if project_members:
            owner_user_id = min(
                project_members,
                key=lambda member: (member[1] != "operator", member[0]),
            )[0]
            workspace_id = workspace_by_user[owner_user_id]
            for user_id, role in project_members:
                key = (workspace_id, user_id)
                if role == "operator" or workspace_role_by_member.get(key) == "operator":
                    workspace_role_by_member[key] = "operator"
                else:
                    workspace_role_by_member.setdefault(key, "viewer")
        else:
            # Keep orphaned legacy projects isolated instead of assigning them to an unrelated user.
            workspace_id = uuid5(NAMESPACE_URL, f"ict/orphan-project-workspace/{project_id}")
            connection.execute(
                workspaces.insert().values(
                    id=workspace_id,
                    name="归档项目工作空间",
                    created_by="migration",
                )
            )
        connection.execute(
            projects.update().where(projects.c.id == project_id).values(workspace_id=workspace_id)
        )

    if workspace_role_by_member:
        connection.execute(
            workspace_memberships.insert(),
            [
                {"workspace_id": workspace_id, "user_id": user_id, "role": role}
                for (workspace_id, user_id), role in sorted(
                    workspace_role_by_member.items(), key=lambda item: (str(item[0][0]), item[0][1])
                )
            ],
        )


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "workspace_memberships",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('operator', 'viewer')", name="ck_workspace_memberships_role"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
    )

    op.add_column("projects", sa.Column("workspace_id", sa.Uuid(), nullable=True))
    connection = op.get_bind()
    _backfill_workspaces(connection)
    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("workspace_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.create_foreign_key(
            "fk_projects_workspace", "workspaces", ["workspace_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_unique_constraint("uq_projects_id_workspace", ["id", "workspace_id"])

    op.create_table(
        "reproduction_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("linked_project_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("source", sa.Text(), server_default="", nullable=False),
        sa.Column("claim", sa.Text(), server_default="", nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=True),
        sa.Column("criteria_version", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="preparation", nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('paper', 'experiment')", name="ck_reproduction_tasks_kind"),
        sa.CheckConstraint(
            "status IN ('preparation', 'insufficient_conditions', 'ready_to_run', 'running', "
            "'awaiting_review', 'conforms', 'differs', 'undetermined')",
            name="ck_reproduction_tasks_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["linked_project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_reproduction_tasks_id_workspace"),
    )

    op.add_column("workflows", sa.Column("workspace_id", sa.Uuid(), nullable=True))
    op.add_column("workflows", sa.Column("owner_type", sa.String(length=16), nullable=True))
    op.add_column("workflows", sa.Column("reproduction_task_id", sa.Uuid(), nullable=True))
    connection.execute(
        sa.text(
            "UPDATE workflows SET owner_type = 'project', workspace_id = "
            "(SELECT projects.workspace_id FROM projects WHERE projects.id = workflows.project_id)"
        )
    )
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.alter_column("project_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.alter_column("workspace_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.alter_column("owner_type", existing_type=sa.String(length=16), nullable=False)
        batch_op.create_foreign_key(
            "fk_workflows_workspace", "workspaces", ["workspace_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_foreign_key(
            "fk_workflows_project_workspace",
            "projects",
            ["project_id", "workspace_id"],
            ["id", "workspace_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_workflows_reproduction_workspace",
            "reproduction_tasks",
            ["reproduction_task_id", "workspace_id"],
            ["id", "workspace_id"],
            ondelete="CASCADE",
        )
        batch_op.create_check_constraint(
            "ck_workflows_exactly_one_owner",
            "(owner_type = 'project' AND project_id IS NOT NULL AND reproduction_task_id IS NULL) OR "
            "(owner_type = 'reproduction' AND reproduction_task_id IS NOT NULL AND project_id IS NULL)",
        )
        batch_op.create_index(
            "ix_workflows_reproduction_updated", ["reproduction_task_id", "updated_at"]
        )


def downgrade() -> None:
    connection = op.get_bind()
    reproduction_tasks = sa.table("reproduction_tasks", sa.column("id", sa.Uuid()))
    workflow_owner = sa.table(
        "workflows",
        sa.column("reproduction_task_id", sa.Uuid()),
    )
    has_tasks = connection.execute(sa.select(sa.func.count()).select_from(reproduction_tasks)).scalar_one()
    has_reproduction_workflows = connection.execute(
        sa.select(sa.func.count())
        .select_from(workflow_owner)
        .where(workflow_owner.c.reproduction_task_id.is_not(None))
    ).scalar_one()
    if has_tasks or has_reproduction_workflows:
        raise RuntimeError(
            "Cannot downgrade workspace ownership while reproduction tasks or workflows exist."
        )

    with op.batch_alter_table("workflows") as batch_op:
        batch_op.drop_index("ix_workflows_reproduction_updated")
        batch_op.drop_constraint("ck_workflows_exactly_one_owner", type_="check")
        batch_op.drop_constraint("fk_workflows_reproduction_workspace", type_="foreignkey")
        batch_op.drop_constraint("fk_workflows_project_workspace", type_="foreignkey")
        batch_op.drop_constraint("fk_workflows_workspace", type_="foreignkey")
        batch_op.drop_column("reproduction_task_id")
        batch_op.drop_column("owner_type")
        batch_op.drop_column("workspace_id")
        batch_op.alter_column("project_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_table("reproduction_tasks")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("uq_projects_id_workspace", type_="unique")
        batch_op.drop_constraint("fk_projects_workspace", type_="foreignkey")
        batch_op.drop_column("workspace_id")
    op.drop_table("workspace_memberships")
    op.drop_table("workspaces")
