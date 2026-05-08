"""Add MAWF external task id support

Revision ID: 021_mawf_external_task_id
Revises: 020_mawf_recoverable_workflow_runs
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "021_mawf_external_task_id"
down_revision: Union[str, None] = "020_mawf_recoverable_workflow_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE planning.tasks
        ADD COLUMN IF NOT EXISTS external_task_id TEXT
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_tasks_external_task_id
        ON planning.tasks(external_task_id)
        WHERE external_task_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_tasks_external_task_id")
    op.execute("ALTER TABLE planning.tasks DROP COLUMN IF EXISTS external_task_id")
