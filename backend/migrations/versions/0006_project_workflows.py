"""Add project-owned workflow drafts and immutable snapshots."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_project_workflows"
down_revision: Union[str, None] = "0005_run_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create drafts and snapshots with project/workflow foreign-key ownership."""
    op.create_table(
        "workflows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("graph", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("current_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_workflows_revision_positive"),
        sa.CheckConstraint("current_version >= 0", name="ck_workflows_current_version_nonnegative"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflows_project_updated", "workflows", ["project_id", "updated_at"])

    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("graph", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_workflow_versions_version_positive"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_workflow_versions_hash_length"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_workflow_version"),
    )
    op.create_index(
        "ix_workflow_versions_workflow_created", "workflow_versions", ["workflow_id", "created_at"]
    )


def downgrade() -> None:
    """Remove workflow snapshots before their owning draft rows."""
    op.drop_index("ix_workflow_versions_workflow_created", table_name="workflow_versions")
    op.drop_table("workflow_versions")
    op.drop_index("ix_workflows_project_updated", table_name="workflows")
    op.drop_table("workflows")
