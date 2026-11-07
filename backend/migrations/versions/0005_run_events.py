"""Add append-only status events for synthetic runs and backfill provable history."""

from typing import Sequence, Union
from uuid import UUID, uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "0005_run_events"
down_revision: Union[str, None] = "0004_generic_quality_gate"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create constrained lifecycle rows and backfill only known timestamps."""
    op.create_table(
        "run_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(sequence = 1 AND status = 'queued') OR "
            "(sequence = 2 AND status = 'running') OR "
            "(sequence = 3 AND status IN ('succeeded', 'failed'))",
            name="ck_run_events_sequence_status",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code IN ('QUEUE_UNAVAILABLE', 'WORKER_EXECUTION_FAILED')",
            name="ck_run_events_error_code",
        ),
        sa.CheckConstraint(
            "status = 'failed' OR error_code IS NULL",
            name="ck_run_events_error_only_on_failure",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_events_run_sequence"),
    )
    op.create_index("ix_run_events_run_sequence", "run_events", ["run_id", "sequence"])

    connection = op.get_bind()
    metadata = sa.MetaData()
    runs = sa.Table("runs", metadata, autoload_with=connection)
    run_events = sa.table(
        "run_events",
        sa.column("id", sa.Uuid()),
        sa.column("run_id", sa.Uuid()),
        sa.column("sequence", sa.Integer()),
        sa.column("status", sa.String(length=16)),
        sa.column("error_code", sa.String(length=64)),
        sa.column("occurred_at", sa.DateTime(timezone=True)),
    )
    historical_runs = connection.execute(
        sa.select(
            runs.c.id,
            runs.c.status,
            runs.c.error_code,
            runs.c.created_at,
            runs.c.started_at,
            runs.c.finished_at,
        )
    ).mappings()

    for row in historical_runs:
        raw_run_id = row["id"]
        run_id = raw_run_id if isinstance(raw_run_id, UUID) else UUID(str(raw_run_id))
        entries = [(1, "queued", row["created_at"], None)]
        if row["started_at"] is not None:
            entries.append((2, "running", row["started_at"], None))
        if row["status"] in ("succeeded", "failed") and row["finished_at"] is not None:
            error_code = row["error_code"] if row["error_code"] in (
                "QUEUE_UNAVAILABLE",
                "WORKER_EXECUTION_FAILED",
            ) else None
            entries.append((3, row["status"], row["finished_at"], error_code))

        for sequence, status, occurred_at, error_code in entries:
            connection.execute(
                run_events.insert().values(
                    id=uuid4(),
                    run_id=run_id,
                    sequence=sequence,
                    status=status,
                    error_code=error_code,
                    occurred_at=occurred_at,
                )
            )


def downgrade() -> None:
    """Drop run lifecycle history when reverting this schema version."""
    op.drop_index("ix_run_events_run_sequence", table_name="run_events")
    op.drop_table("run_events")
