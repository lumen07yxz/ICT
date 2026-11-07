"""Preserve workflow names and descriptions in new immutable versions."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_workflow_version_metadata"
down_revision: Union[str, None] = "0007_workspace_reproduction_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable fields so existing graph-only versions stay valid."""
    op.add_column("workflow_versions", sa.Column("name", sa.String(length=160), nullable=True))
    op.add_column("workflow_versions", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove metadata fields while retaining all version graph records."""
    op.drop_column("workflow_versions", "description")
    op.drop_column("workflow_versions", "name")
