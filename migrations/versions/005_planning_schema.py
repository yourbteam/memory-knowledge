"""Add planning schema, reference tables, external links, and normalized workflow run status

Revision ID: 005_planning_schema
Revises: 004
Create Date: 2026-04-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005_planning_schema"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute("CREATE SCHEMA IF NOT EXISTS planning")

    op.execute("""
    CREATE TABLE IF NOT EXISTS core.reference_types (
        id BIGSERIAL PRIMARY KEY,
        internal_code VARCHAR(100) NOT NULL UNIQUE,
        name VARCHAR(100) NOT NULL,
        description TEXT,
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS core.reference_values (
        id BIGSERIAL PRIMARY KEY,
        reference_type_id BIGINT NOT NULL REFERENCES core.reference_types(id) ON DELETE CASCADE,
        internal_code VARCHAR(100) NOT NULL UNIQUE,
        display_name VARCHAR(100) NOT NULL,
        description TEXT,
        sort_order INT NOT NULL DEFAULT 0,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        is_terminal BOOLEAN NOT NULL DEFAULT FALSE,
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_reference_values_type_sort "
        "ON core.reference_values(reference_type_id, sort_order)"
    )

    op.execute("""
    INSERT INTO core.reference_types (internal_code, name, description)
    VALUES
      ('PROJECT_STATUS', 'Project Status', 'Lifecycle states for projects'),
      ('FEATURE_STATUS', 'Feature Status', 'Lifecycle states for features'),
      ('TASK_STATUS', 'Task Status', 'Lifecycle states for tasks'),
      ('ROADMAP_STATUS', 'Roadmap Status', 'Lifecycle states for roadmaps'),
      ('PRIORITY', 'Priority', 'Priority values'),
      ('WORKFLOW_RUN_STATUS', 'Workflow Run Status', 'Lifecycle states for workflow runs')
    ON CONFLICT (internal_code) DO NOTHING
    """)

    op.execute("""
    INSERT INTO core.reference_values (reference_type_id, internal_code, display_name, sort_order, is_terminal)
    SELECT rt.id, v.internal_code, v.display_name, v.sort_order, v.is_terminal
    FROM core.reference_types rt
    JOIN (VALUES
      ('PROJECT_STATUS','PROJ_ACTIVE','Active',10,FALSE),
      ('PROJECT_STATUS','PROJ_PAUSED','Paused',20,FALSE),
      ('PROJECT_STATUS','PROJ_ARCHIVED','Archived',30,TRUE),

      ('FEATURE_STATUS','FEAT_IDEA','Idea',10,FALSE),
      ('FEATURE_STATUS','FEAT_BACKLOG','Backlog',20,FALSE),
      ('FEATURE_STATUS','FEAT_PLANNED','Planned',30,FALSE),
      ('FEATURE_STATUS','FEAT_IN_PROGRESS','In Progress',40,FALSE),
      ('FEATURE_STATUS','FEAT_DONE','Done',50,TRUE),
      ('FEATURE_STATUS','FEAT_CANCELLED','Cancelled',60,TRUE),

      ('TASK_STATUS','TASK_TODO','To Do',10,FALSE),
      ('TASK_STATUS','TASK_READY','Ready',20,FALSE),
      ('TASK_STATUS','TASK_IN_PROGRESS','In Progress',30,FALSE),
      ('TASK_STATUS','TASK_BLOCKED','Blocked',40,FALSE),
      ('TASK_STATUS','TASK_DONE','Done',50,TRUE),
      ('TASK_STATUS','TASK_CANCELLED','Cancelled',60,TRUE),

      ('ROADMAP_STATUS','ROADMAP_PLANNED','Planned',10,FALSE),
      ('ROADMAP_STATUS','ROADMAP_ACTIVE','Active',20,FALSE),
      ('ROADMAP_STATUS','ROADMAP_ARCHIVED','Archived',30,TRUE),

      ('PRIORITY','PRIO_LOW','Low',10,FALSE),
      ('PRIORITY','PRIO_MEDIUM','Medium',20,FALSE),
      ('PRIORITY','PRIO_HIGH','High',30,FALSE),
      ('PRIORITY','PRIO_CRITICAL','Critical',40,FALSE),

      ('WORKFLOW_RUN_STATUS','RUN_PENDING','Pending',10,FALSE),
      ('WORKFLOW_RUN_STATUS','RUN_SUBMITTED','Submitted',20,FALSE),
      ('WORKFLOW_RUN_STATUS','RUN_RUNNING','Running',30,FALSE),
      ('WORKFLOW_RUN_STATUS','RUN_SUCCESS','Success',40,TRUE),
      ('WORKFLOW_RUN_STATUS','RUN_PARTIAL','Partial',50,TRUE),
      ('WORKFLOW_RUN_STATUS','RUN_ERROR','Error',60,TRUE),
      ('WORKFLOW_RUN_STATUS','RUN_CANCELLED','Cancelled',70,TRUE)
    ) AS v(type_code, internal_code, display_name, sort_order, is_terminal)
      ON rt.internal_code = v.type_code
    ON CONFLICT (internal_code) DO NOTHING
    """)

    op.execute(
        "ALTER TABLE ops.workflow_runs "
        "ADD COLUMN IF NOT EXISTS status_id BIGINT REFERENCES core.reference_values(id)"
    )
    op.execute(
        "ALTER TABLE ops.workflow_runs "
        "ADD COLUMN IF NOT EXISTS actor_email VARCHAR(255)"
    )

    op.execute("""
    UPDATE ops.workflow_runs wr
    SET status_id = rv.id
    FROM core.reference_values rv
    WHERE rv.internal_code = CASE wr.status
      WHEN 'pending' THEN 'RUN_PENDING'
      WHEN 'submitted' THEN 'RUN_SUBMITTED'
      WHEN 'running' THEN 'RUN_RUNNING'
      WHEN 'success' THEN 'RUN_SUCCESS'
      WHEN 'partial' THEN 'RUN_PARTIAL'
      WHEN 'error' THEN 'RUN_ERROR'
      WHEN 'failed' THEN 'RUN_ERROR'
      WHEN 'completed' THEN 'RUN_SUCCESS'
      WHEN 'cancelled' THEN 'RUN_CANCELLED'
      ELSE 'RUN_PENDING'
    END
    """)

    op.execute("""
    UPDATE ops.workflow_runs
    SET status_id = (
      SELECT rv.id
      FROM core.reference_values rv
      WHERE rv.internal_code = 'RUN_PENDING'
    )
    WHERE status_id IS NULL
    """)

    op.execute("ALTER TABLE ops.workflow_runs ALTER COLUMN status_id SET NOT NULL")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_runs_status_id "
        "ON ops.workflow_runs(status_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_runs_actor_email "
        "ON ops.workflow_runs(actor_email)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_runs_actor_email_status_id "
        "ON ops.workflow_runs(actor_email, status_id)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.projects (
        id BIGSERIAL PRIMARY KEY,
        project_key UUID NOT NULL UNIQUE,
        name VARCHAR(255) NOT NULL UNIQUE,
        description TEXT,
        project_status_id BIGINT NOT NULL REFERENCES core.reference_values(id),
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.project_repositories (
        project_id BIGINT NOT NULL REFERENCES planning.projects(id) ON DELETE CASCADE,
        repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id) ON DELETE CASCADE,
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (project_id, repository_id)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.features (
        id BIGSERIAL PRIMARY KEY,
        feature_key UUID NOT NULL UNIQUE,
        project_id BIGINT NOT NULL REFERENCES planning.projects(id) ON DELETE CASCADE,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        feature_status_id BIGINT NOT NULL REFERENCES core.reference_values(id),
        priority_id BIGINT NOT NULL REFERENCES core.reference_values(id),
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_features_project_status "
        "ON planning.features(project_id, feature_status_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_features_project_priority "
        "ON planning.features(project_id, priority_id)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.feature_repositories (
        feature_id BIGINT NOT NULL REFERENCES planning.features(id) ON DELETE CASCADE,
        repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id) ON DELETE CASCADE,
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (feature_id, repository_id)
    )""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_feature_repositories_repository_id "
        "ON planning.feature_repositories(repository_id)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.tasks (
        id BIGSERIAL PRIMARY KEY,
        task_key UUID NOT NULL UNIQUE,
        feature_id BIGINT NOT NULL REFERENCES planning.features(id) ON DELETE CASCADE,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        task_status_id BIGINT NOT NULL REFERENCES core.reference_values(id),
        priority_id BIGINT NOT NULL REFERENCES core.reference_values(id),
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tasks_feature_status "
        "ON planning.tasks(feature_id, task_status_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tasks_feature_priority "
        "ON planning.tasks(feature_id, priority_id)"
    )

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

    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.task_workflow_runs (
        task_id BIGINT NOT NULL REFERENCES planning.tasks(id) ON DELETE CASCADE,
        workflow_run_id BIGINT NOT NULL REFERENCES ops.workflow_runs(id) ON DELETE CASCADE,
        relation_type VARCHAR(50) NOT NULL DEFAULT 'implements',
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (task_id, workflow_run_id, relation_type)
    )""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_task_workflow_runs_workflow_run_id "
        "ON planning.task_workflow_runs(workflow_run_id)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.roadmaps (
        id BIGSERIAL PRIMARY KEY,
        roadmap_key UUID NOT NULL UNIQUE,
        project_id BIGINT NOT NULL REFERENCES planning.projects(id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        roadmap_status_id BIGINT NOT NULL REFERENCES core.reference_values(id),
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_roadmaps_project_status "
        "ON planning.roadmaps(project_id, roadmap_status_id)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.roadmap_features (
        roadmap_id BIGINT NOT NULL REFERENCES planning.roadmaps(id) ON DELETE CASCADE,
        feature_id BIGINT NOT NULL REFERENCES planning.features(id) ON DELETE CASCADE,
        position INT NOT NULL,
        target_start_utc TIMESTAMPTZ,
        target_end_utc TIMESTAMPTZ,
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (roadmap_id, feature_id),
        UNIQUE (roadmap_id, position)
    )""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_roadmap_features_feature_id "
        "ON planning.roadmap_features(feature_id)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.project_external_links (
        id BIGSERIAL PRIMARY KEY,
        project_id BIGINT NOT NULL REFERENCES planning.projects(id) ON DELETE CASCADE,
        external_system VARCHAR(50) NOT NULL,
        external_object_type VARCHAR(50) NOT NULL,
        external_id VARCHAR(255) NOT NULL,
        external_parent_id VARCHAR(255),
        external_url TEXT,
        last_synced_utc TIMESTAMPTZ,
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (external_system, external_object_type, external_id),
        UNIQUE (project_id, external_system, external_object_type)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS catalog.repository_external_links (
        id BIGSERIAL PRIMARY KEY,
        repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id) ON DELETE CASCADE,
        external_system VARCHAR(50) NOT NULL,
        external_object_type VARCHAR(50) NOT NULL,
        external_id VARCHAR(255) NOT NULL,
        external_parent_id VARCHAR(255),
        external_url TEXT,
        last_synced_utc TIMESTAMPTZ,
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (external_system, external_object_type, external_id),
        UNIQUE (repository_id, external_system, external_object_type)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.feature_external_links (
        id BIGSERIAL PRIMARY KEY,
        feature_id BIGINT NOT NULL REFERENCES planning.features(id) ON DELETE CASCADE,
        external_system VARCHAR(50) NOT NULL,
        external_object_type VARCHAR(50) NOT NULL,
        external_id VARCHAR(255) NOT NULL,
        external_parent_id VARCHAR(255),
        external_url TEXT,
        last_synced_utc TIMESTAMPTZ,
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (external_system, external_object_type, external_id),
        UNIQUE (feature_id, external_system, external_object_type)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS planning.task_external_links (
        id BIGSERIAL PRIMARY KEY,
        task_id BIGINT NOT NULL REFERENCES planning.tasks(id) ON DELETE CASCADE,
        external_system VARCHAR(50) NOT NULL,
        external_object_type VARCHAR(50) NOT NULL,
        external_id VARCHAR(255) NOT NULL,
        external_parent_id VARCHAR(255),
        external_url TEXT,
        last_synced_utc TIMESTAMPTZ,
        created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (external_system, external_object_type, external_id),
        UNIQUE (task_id, external_system, external_object_type)
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS planning.task_external_links CASCADE")
    op.execute("DROP TABLE IF EXISTS planning.feature_external_links CASCADE")
    op.execute("DROP TABLE IF EXISTS catalog.repository_external_links CASCADE")
    op.execute("DROP TABLE IF EXISTS planning.project_external_links CASCADE")
    op.execute("DROP TABLE IF EXISTS planning.roadmap_features CASCADE")
    op.execute("DROP TABLE IF EXISTS planning.roadmaps CASCADE")
    op.execute("DROP TABLE IF EXISTS planning.task_workflow_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS planning.task_repositories CASCADE")
    op.execute("DROP TABLE IF EXISTS planning.tasks CASCADE")
    op.execute("DROP TABLE IF EXISTS planning.feature_repositories CASCADE")
    op.execute("DROP TABLE IF EXISTS planning.features CASCADE")
    op.execute("DROP TABLE IF EXISTS planning.project_repositories CASCADE")
    op.execute("DROP TABLE IF EXISTS planning.projects CASCADE")

    op.execute("DROP INDEX IF EXISTS ix_workflow_runs_actor_email_status_id")
    op.execute("DROP INDEX IF EXISTS ix_workflow_runs_actor_email")
    op.execute("DROP INDEX IF EXISTS ix_workflow_runs_status_id")
    op.execute("ALTER TABLE ops.workflow_runs DROP COLUMN IF EXISTS actor_email")
    op.execute("ALTER TABLE ops.workflow_runs DROP COLUMN IF EXISTS status_id")

    op.execute("DROP TABLE IF EXISTS core.reference_values CASCADE")
    op.execute("DROP TABLE IF EXISTS core.reference_types CASCADE")
    op.execute("DROP SCHEMA IF EXISTS planning")
    op.execute("DROP SCHEMA IF EXISTS core")
