"""Record the exact generic manifest check used to create each new run."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_generic_quality_gate"
down_revision: Union[str, None] = "0003_runs_and_proposal_approval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable snapshot fields so historical W4 smoke runs remain honest."""
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("quality_status", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("quality_rule_set_version", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("quality_report_sha256", sa.String(length=64), nullable=True))
        batch.create_check_constraint(
            "ck_runs_quality_status",
            "quality_status IS NULL OR quality_status IN ('success', 'warning')",
        )
        batch.create_check_constraint(
            "ck_runs_quality_report_sha256_length",
            "quality_report_sha256 IS NULL OR length(quality_report_sha256) = 64",
        )
        batch.create_check_constraint(
            "ck_runs_quality_snapshot_complete",
            "(quality_status IS NULL AND quality_rule_set_version IS NULL AND quality_report_sha256 IS NULL) "
            "OR (quality_status IS NOT NULL AND quality_rule_set_version IS NOT NULL AND quality_report_sha256 IS NOT NULL)",
        )


def downgrade() -> None:
    """Remove quality snapshot metadata without changing historical run results."""
    with op.batch_alter_table("runs") as batch:
        batch.drop_constraint("ck_runs_quality_snapshot_complete", type_="check")
        batch.drop_constraint("ck_runs_quality_report_sha256_length", type_="check")
        batch.drop_constraint("ck_runs_quality_status", type_="check")
        batch.drop_column("quality_report_sha256")
        batch.drop_column("quality_rule_set_version")
        batch.drop_column("quality_status")
