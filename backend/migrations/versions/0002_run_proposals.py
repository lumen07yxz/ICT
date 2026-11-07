"""Add inert run proposals for the fixed synthetic pipeline."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_run_proposals"
down_revision: Union[str, None] = "0001_project_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("pipeline_template", sa.String(length=64), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending_approval", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'expired', 'cancelled')",
            name="ck_run_proposals_status",
        ),
        sa.CheckConstraint("length(config_sha256) = 64", name="ck_run_proposals_config_sha256_length"),
        sa.CheckConstraint("length(idempotency_key) = 64", name="ck_run_proposals_idempotency_key_length"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_run_proposals_idempotency_key"),
    )
    op.create_index(
        "ix_run_proposals_project_created",
        "run_proposals",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_proposals_project_created", table_name="run_proposals")
    op.drop_table("run_proposals")
