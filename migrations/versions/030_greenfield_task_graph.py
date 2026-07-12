"""Add canonical greenfield graph-task storage.

Revision ID: 030_greenfield_task_graph
Revises: 029_work_memory_trust
"""
from typing import Sequence, Union

from alembic import op

revision: str = "030_greenfield_task_graph"
down_revision: Union[str, None] = "029_work_memory_trust"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    statements = [
        "ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS task_type VARCHAR(100)",
        "ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS parent_task_id BIGINT",
        "ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS feature_task_id BIGINT",
        "ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS graph_node_id VARCHAR(255)",
        "ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS is_runnable BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS task_metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE planning.tasks ADD CONSTRAINT fk_tasks_parent_task FOREIGN KEY (parent_task_id) REFERENCES planning.tasks(id) ON DELETE SET NULL",
        "ALTER TABLE planning.tasks ADD CONSTRAINT fk_tasks_feature_task FOREIGN KEY (feature_task_id) REFERENCES planning.tasks(id) ON DELETE SET NULL",
        "ALTER TABLE planning.tasks ADD CONSTRAINT ck_tasks_graph_node_requires_feature CHECK (graph_node_id IS NULL OR feature_id IS NOT NULL)",
        "ALTER TABLE planning.tasks ADD CONSTRAINT ck_tasks_metadata_object CHECK (jsonb_typeof(task_metadata) = 'object')",
        "CREATE UNIQUE INDEX uq_tasks_project_feature_graph_node ON planning.tasks(project_id, feature_id, graph_node_id) WHERE graph_node_id IS NOT NULL",
        """
        CREATE TABLE planning.task_dependencies (
            task_id BIGINT NOT NULL,
            depends_on_task_id BIGINT NOT NULL,
            CONSTRAINT pk_task_dependencies PRIMARY KEY (task_id, depends_on_task_id),
            CONSTRAINT fk_task_dependencies_task FOREIGN KEY (task_id) REFERENCES planning.tasks(id) ON DELETE CASCADE,
            CONSTRAINT fk_task_dependencies_depends_on FOREIGN KEY (depends_on_task_id) REFERENCES planning.tasks(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE planning.task_blockers (
            task_id BIGINT NOT NULL,
            blocked_by_task_id BIGINT NOT NULL,
            CONSTRAINT pk_task_blockers PRIMARY KEY (task_id, blocked_by_task_id),
            CONSTRAINT fk_task_blockers_task FOREIGN KEY (task_id) REFERENCES planning.tasks(id) ON DELETE CASCADE,
            CONSTRAINT fk_task_blockers_blocked_by FOREIGN KEY (blocked_by_task_id) REFERENCES planning.tasks(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE planning.task_coordination (
            task_id BIGINT NOT NULL,
            coordination_task_id BIGINT NOT NULL,
            CONSTRAINT pk_task_coordination PRIMARY KEY (task_id, coordination_task_id),
            CONSTRAINT fk_task_coordination_task FOREIGN KEY (task_id) REFERENCES planning.tasks(id) ON DELETE CASCADE,
            CONSTRAINT fk_task_coordination_coordination FOREIGN KEY (coordination_task_id) REFERENCES planning.tasks(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE planning.task_related_repositories (
            task_id BIGINT NOT NULL,
            repository_id BIGINT NOT NULL,
            CONSTRAINT pk_task_related_repositories PRIMARY KEY (task_id, repository_id),
            CONSTRAINT fk_task_related_repositories_task FOREIGN KEY (task_id) REFERENCES planning.tasks(id) ON DELETE CASCADE,
            CONSTRAINT fk_task_related_repositories_repository FOREIGN KEY (repository_id) REFERENCES catalog.repositories(id) ON DELETE CASCADE
        )
        """,
    ]
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    for statement in (
        "DROP TABLE IF EXISTS planning.task_related_repositories",
        "DROP TABLE IF EXISTS planning.task_coordination",
        "DROP TABLE IF EXISTS planning.task_blockers",
        "DROP TABLE IF EXISTS planning.task_dependencies",
        "DROP INDEX IF EXISTS planning.uq_tasks_project_feature_graph_node",
        "ALTER TABLE planning.tasks DROP CONSTRAINT IF EXISTS ck_tasks_metadata_object",
        "ALTER TABLE planning.tasks DROP CONSTRAINT IF EXISTS ck_tasks_graph_node_requires_feature",
        "ALTER TABLE planning.tasks DROP CONSTRAINT IF EXISTS fk_tasks_feature_task",
        "ALTER TABLE planning.tasks DROP CONSTRAINT IF EXISTS fk_tasks_parent_task",
        "ALTER TABLE planning.tasks DROP COLUMN IF EXISTS task_metadata",
        "ALTER TABLE planning.tasks DROP COLUMN IF EXISTS is_runnable",
        "ALTER TABLE planning.tasks DROP COLUMN IF EXISTS graph_node_id",
        "ALTER TABLE planning.tasks DROP COLUMN IF EXISTS feature_task_id",
        "ALTER TABLE planning.tasks DROP COLUMN IF EXISTS parent_task_id",
        "ALTER TABLE planning.tasks DROP COLUMN IF EXISTS task_type",
    ):
        op.execute(statement)
