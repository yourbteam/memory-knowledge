"""Add MAWF recoverable workflow run listing support

Revision ID: 020_mawf_recoverable_workflow_runs
Revises: 019_mawf_workflow_runs_by_user
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "020_mawf_recoverable_workflow_runs"
down_revision: Union[str, None] = "019_mawf_workflow_runs_by_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_runs_recovery_priority
        ON ops.workflow_runs(status_id, updated_utc ASC, started_utc ASC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_workflow_runs_recovery_priority")
