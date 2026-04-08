"""Make tasks belong to exactly one repository

Revision ID: 007_task_single_repository
Revises: 006_task_project_scope
Create Date: 2026-04-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007_task_single_repository"
down_revision: Union[str, None] = "006_task_project_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE planning.tasks "
        "ADD COLUMN IF NOT EXISTS repository_id BIGINT REFERENCES catalog.repositories(id)"
    )
    op.execute(
        """
        UPDATE planning.tasks t
        SET repository_id = tr.repository_id
        FROM (
            SELECT task_id, MIN(repository_id) AS repository_id
            FROM planning.task_repositories
            GROUP BY task_id
        ) tr
        WHERE t.id = tr.task_id
          AND t.repository_id IS NULL
        """
    )
    op.execute("ALTER TABLE planning.tasks ALTER COLUMN repository_id SET NOT NULL")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tasks_repository_status "
        "ON planning.tasks(repository_id, task_status_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tasks_repository_priority "
        "ON planning.tasks(repository_id, priority_id)"
    )
    op.execute("DROP TABLE IF EXISTS planning.task_repositories CASCADE")


def downgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.task_repositories (
        task_id BIGINT NOT NULL REFERENCES planning.tasks(id) ON DELETE CASCADE,
        repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id) ON DELETE CASCADE,
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (task_id, repository_id)
    )""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_task_repositories_repository_id "
        "ON planning.task_repositories(repository_id)"
    )
    op.execute("DROP INDEX IF EXISTS ix_tasks_repository_priority")
    op.execute("DROP INDEX IF EXISTS ix_tasks_repository_status")
    op.execute("ALTER TABLE planning.tasks DROP COLUMN IF EXISTS repository_id")
