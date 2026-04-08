"""Make tasks project-scoped and feature-optional

Revision ID: 006_task_project_scope
Revises: 005_planning_schema
Create Date: 2026-04-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "006_task_project_scope"
down_revision: Union[str, None] = "005_planning_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE planning.tasks "
        "ADD COLUMN IF NOT EXISTS project_id BIGINT REFERENCES planning.projects(id) ON DELETE CASCADE"
    )
    op.execute(
        """
        UPDATE planning.tasks t
        SET project_id = f.project_id
        FROM planning.features f
        WHERE t.feature_id = f.id
          AND t.project_id IS NULL
        """
    )
    op.execute("ALTER TABLE planning.tasks ALTER COLUMN project_id SET NOT NULL")
    op.execute("ALTER TABLE planning.tasks ALTER COLUMN feature_id DROP NOT NULL")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tasks_project_status "
        "ON planning.tasks(project_id, task_status_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tasks_project_priority "
        "ON planning.tasks(project_id, priority_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tasks_project_priority")
    op.execute("DROP INDEX IF EXISTS ix_tasks_project_status")
    op.execute("ALTER TABLE planning.tasks ALTER COLUMN feature_id SET NOT NULL")
    op.execute("ALTER TABLE planning.tasks DROP COLUMN IF EXISTS project_id")
