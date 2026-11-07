"""Add operator approval metadata and persistent synthetic run records."""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "0003_runs_and_proposal_approval"
down_revision: Union[str, None] = "0002_run_proposals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("run_proposals", sa.Column("trace_id", sa.String(length=36), nullable=True))
    op.add_column("run_proposals", sa.Column("approved_by", sa.String(length=80), nullable=True))
    op.add_column("run_proposals", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))

    connection = op.get_bind()
    proposal_ids = connection.execute(sa.text("SELECT id FROM run_proposals")).scalars().all()
    for proposal_id in proposal_ids:
        connection.execute(
            sa.text("UPDATE run_proposals SET trace_id = :trace_id WHERE id = :proposal_id"),
            {"trace_id": str(uuid4()), "proposal_id": proposal_id},
        )

    with op.batch_alter_table("run_proposals") as batch:
        batch.alter_column("trace_id", existing_type=sa.String(length=36), nullable=False)
        batch.create_unique_constraint("uq_run_proposals_trace_id", ["trace_id"])

    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_template", sa.String(length=64), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_runs_status",
        ),
        sa.CheckConstraint("length(config_sha256) = 64", name="ck_runs_config_sha256_length"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposal_id"], ["run_proposals.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id", name="uq_runs_proposal_id"),
        sa.UniqueConstraint("trace_id", name="uq_runs_trace_id"),
    )
    op.create_index("ix_runs_project_created", "runs", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_project_created", table_name="runs")
    op.drop_table("runs")
    with op.batch_alter_table("run_proposals") as batch:
        batch.drop_constraint("uq_run_proposals_trace_id", type_="unique")
        batch.drop_column("approved_at")
        batch.drop_column("approved_by")
        batch.drop_column("trace_id")
