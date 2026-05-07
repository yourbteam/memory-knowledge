"""Add MCP agents workflow contract schema

Revision ID: 016_mawf_contract
Revises: 015_intake_sessions
Create Date: 2026-05-07
"""
from typing import Sequence, Union

from alembic import op

revision: str = "016_mawf_contract"
down_revision: Union[str, None] = "015_intake_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        ALTER TABLE core.reference_values
        ADD COLUMN IF NOT EXISTS mawf_code VARCHAR(100)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_reference_values_type_mawf_code
        ON core.reference_values(reference_type_id, mawf_code)
        WHERE mawf_code IS NOT NULL
        """
    )

    op.execute(
        """
        INSERT INTO core.reference_types (internal_code, name, description)
        VALUES
          ('USER_ROLE', 'User Role', 'MAWF user role values'),
          ('USER_STATUS', 'User Status', 'MAWF user status values'),
          ('REPOSITORY_STATUS', 'Repository Status', 'MAWF repository status values'),
          ('ARTIFACT_ROLE', 'Artifact Role', 'MAWF task artifact roles'),
          ('ARTIFACT_PERSIST_STATUS', 'Artifact Persist Status', 'MAWF artifact persistence states')
        ON CONFLICT (internal_code) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO core.reference_values (
            reference_type_id, internal_code, mawf_code, display_name,
            description, sort_order, is_terminal
        )
        SELECT rt.id, v.internal_code, v.mawf_code, v.display_name,
               v.description, v.sort_order, v.is_terminal
        FROM core.reference_types rt
        JOIN (
            VALUES
              ('USER_ROLE', 'USER_ROLE_ADMIN', 'admin', 'Admin', 'Administrator user', 10, FALSE),
              ('USER_ROLE', 'USER_ROLE_EMPLOYEE', 'employee', 'Employee', 'Employee user', 20, FALSE),
              ('USER_STATUS', 'USER_ACTIVE', 'active', 'Active', 'Active user', 10, FALSE),
              ('USER_STATUS', 'USER_INACTIVE', 'inactive', 'Inactive', 'Inactive user', 20, TRUE),
              ('REPOSITORY_STATUS', 'REPO_ACTIVE', 'active', 'Active', 'Active repository', 10, FALSE),
              ('REPOSITORY_STATUS', 'REPO_INACTIVE', 'inactive', 'Inactive', 'Inactive repository', 20, TRUE),
              ('ARTIFACT_ROLE', 'ARTIFACT_INITIAL_PROMPT', 'initial_prompt', 'Initial Prompt', 'Initial prompt artifact', 10, FALSE),
              ('ARTIFACT_ROLE', 'ARTIFACT_NORMALIZED_PROMPT', 'normalized_prompt', 'Normalized Prompt', 'Normalized prompt artifact', 20, FALSE),
              ('ARTIFACT_ROLE', 'ARTIFACT_TASK_LEDGER', 'task_ledger', 'Task Ledger', 'Task ledger artifact', 30, FALSE),
              ('ARTIFACT_PERSIST_STATUS', 'ARTIFACT_LOCAL_ONLY', 'local_only', 'Local Only', 'Artifact exists only locally', 10, FALSE),
              ('ARTIFACT_PERSIST_STATUS', 'ARTIFACT_PERSIST_PENDING', 'persist_pending', 'Persist Pending', 'Artifact persistence is pending', 20, FALSE),
              ('ARTIFACT_PERSIST_STATUS', 'ARTIFACT_PERSISTED', 'persisted', 'Persisted', 'Artifact has been persisted', 30, TRUE),
              ('ARTIFACT_PERSIST_STATUS', 'ARTIFACT_PERSIST_FAILED', 'persist_failed', 'Persist Failed', 'Artifact persistence failed', 40, TRUE),
              ('TASK_STATUS', 'TASK_FAILED', 'failed', 'Failed', 'Failed task', 70, TRUE)
        ) AS v(type_code, internal_code, mawf_code, display_name, description, sort_order, is_terminal)
          ON rt.internal_code = v.type_code
        ON CONFLICT (internal_code) DO UPDATE SET
            mawf_code = COALESCE(core.reference_values.mawf_code, EXCLUDED.mawf_code),
            description = COALESCE(core.reference_values.description, EXCLUDED.description),
            updated_utc = NOW()
        """
    )

    op.execute(
        """
        UPDATE core.reference_values rv
        SET mawf_code = v.mawf_code,
            updated_utc = NOW()
        FROM core.reference_types rt
        JOIN (
            VALUES
              ('PROJECT_STATUS', 'PROJ_ACTIVE', 'active'),
              ('PROJECT_STATUS', 'PROJ_ARCHIVED', 'inactive'),
              ('TASK_STATUS', 'TASK_TODO', 'active'),
              ('TASK_STATUS', 'TASK_DONE', 'completed'),
              ('TASK_STATUS', 'TASK_CANCELLED', 'cancelled'),
              ('TASK_STATUS', 'TASK_FAILED', 'failed')
        ) AS v(type_code, internal_code, mawf_code)
          ON rt.internal_code = v.type_code
        WHERE rv.reference_type_id = rt.id
          AND rv.internal_code = v.internal_code
          AND rv.mawf_code IS DISTINCT FROM v.mawf_code
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS core.users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT NOT NULL UNIQUE,
            display_name TEXT,
            role_id BIGINT NOT NULL REFERENCES core.reference_values(id),
            status_id BIGINT NOT NULL REFERENCES core.reference_values(id),
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_role ON core.users(role_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_status ON core.users(status_id)")

    op.execute("ALTER TABLE planning.projects ADD COLUMN IF NOT EXISTS mawf_project_key TEXT")
    op.execute("UPDATE planning.projects SET mawf_project_key = project_key::text WHERE mawf_project_key IS NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_projects_mawf_project_key ON planning.projects(mawf_project_key)")

    op.execute("ALTER TABLE catalog.repositories ADD COLUMN IF NOT EXISTS mawf_repository_id UUID")
    op.execute("ALTER TABLE catalog.repositories ADD COLUMN IF NOT EXISTS provider TEXT")
    op.execute("ALTER TABLE catalog.repositories ADD COLUMN IF NOT EXISTS owner TEXT")
    op.execute("ALTER TABLE catalog.repositories ADD COLUMN IF NOT EXISTS repo_name TEXT")
    op.execute("ALTER TABLE catalog.repositories ADD COLUMN IF NOT EXISTS status_id BIGINT REFERENCES core.reference_values(id)")
    op.execute("UPDATE catalog.repositories SET mawf_repository_id = gen_random_uuid() WHERE mawf_repository_id IS NULL")
    op.execute(
        """
        UPDATE catalog.repositories
        SET status_id = (
            SELECT rv.id
            FROM core.reference_values rv
            JOIN core.reference_types rt ON rt.id = rv.reference_type_id
            WHERE rt.internal_code = 'REPOSITORY_STATUS'
              AND rv.mawf_code = 'active'
            LIMIT 1
        )
        WHERE status_id IS NULL
        """
    )
    op.execute("ALTER TABLE catalog.repositories ALTER COLUMN mawf_repository_id SET NOT NULL")
    op.execute("ALTER TABLE catalog.repositories ALTER COLUMN status_id SET NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_repositories_mawf_repository_id ON catalog.repositories(mawf_repository_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_repositories_status_id ON catalog.repositories(status_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.mawf_prompts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            normalized_hash TEXT NOT NULL UNIQUE,
            original_prompt_ref TEXT NOT NULL,
            normalized_prompt_ref TEXT NOT NULL,
            created_by_user_id UUID NOT NULL REFERENCES core.users(id),
            supersedes_prompt_id UUID REFERENCES ops.mawf_prompts(id),
            correction_note TEXT,
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mawf_prompts_created_by ON ops.mawf_prompts(created_by_user_id)")

    op.execute("ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS mawf_task_id TEXT")
    op.execute("ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES core.users(id)")
    op.execute("ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS prompt_id UUID REFERENCES ops.mawf_prompts(id)")
    op.execute("ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS task_ledger_ref TEXT")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_tasks_mawf_task_id ON planning.tasks(mawf_task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tasks_owner_updated ON planning.tasks(owner_user_id, updated_utc DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tasks_prompt_id ON planning.tasks(prompt_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS planning.mawf_artifact_refs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            mawf_task_id TEXT NOT NULL REFERENCES planning.tasks(mawf_task_id) ON DELETE CASCADE,
            role_id BIGINT NOT NULL REFERENCES core.reference_values(id),
            artifact_path TEXT NOT NULL,
            content_hash TEXT,
            persist_status_id BIGINT NOT NULL REFERENCES core.reference_values(id),
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_mawf_artifact_refs_task_role UNIQUE (mawf_task_id, role_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mawf_artifact_refs_task ON planning.mawf_artifact_refs(mawf_task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mawf_artifact_refs_role ON planning.mawf_artifact_refs(role_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mawf_artifact_refs_persist_status ON planning.mawf_artifact_refs(persist_status_id)")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION core.enforce_reference_value_types()
        RETURNS trigger AS $$
        DECLARE
            idx integer := 0;
            column_name text;
            type_code text;
            value_id bigint;
            ok boolean;
        BEGIN
            WHILE idx < TG_NARGS LOOP
                column_name := TG_ARGV[idx];
                type_code := TG_ARGV[idx + 1];
                value_id := NULLIF(to_jsonb(NEW)->>column_name, '')::bigint;
                IF value_id IS NOT NULL THEN
                    SELECT EXISTS (
                        SELECT 1
                        FROM core.reference_values rv
                        JOIN core.reference_types rt ON rt.id = rv.reference_type_id
                        WHERE rv.id = value_id
                          AND rt.internal_code = type_code
                    ) INTO ok;
                    IF NOT ok THEN
                        RAISE EXCEPTION 'reference value % in %.% must belong to type %',
                            value_id, TG_TABLE_NAME, column_name, type_code;
                    END IF;
                END IF;
                idx := idx + 2;
            END LOOP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    _create_reference_trigger("core", "users", "role_id", "USER_ROLE", "status_id", "USER_STATUS")
    _create_reference_trigger("planning", "projects", "project_status_id", "PROJECT_STATUS")
    _create_reference_trigger("catalog", "repositories", "status_id", "REPOSITORY_STATUS")
    _create_reference_trigger("planning", "tasks", "task_status_id", "TASK_STATUS")
    _create_reference_trigger(
        "planning",
        "mawf_artifact_refs",
        "role_id",
        "ARTIFACT_ROLE",
        "persist_status_id",
        "ARTIFACT_PERSIST_STATUS",
    )


def _create_reference_trigger(schema: str, table: str, *args: str) -> None:
    trigger_name = f"trg_{table}_reference_types"
    quoted_args = ", ".join(f"'{arg}'" for arg in args)
    op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {schema}.{table}")
    op.execute(
        f"""
        CREATE TRIGGER {trigger_name}
        BEFORE INSERT OR UPDATE ON {schema}.{table}
        FOR EACH ROW EXECUTE FUNCTION core.enforce_reference_value_types({quoted_args})
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_mawf_artifact_refs_reference_types ON planning.mawf_artifact_refs")
    op.execute("DROP TRIGGER IF EXISTS trg_tasks_reference_types ON planning.tasks")
    op.execute("DROP TRIGGER IF EXISTS trg_repositories_reference_types ON catalog.repositories")
    op.execute("DROP TRIGGER IF EXISTS trg_projects_reference_types ON planning.projects")
    op.execute("DROP TRIGGER IF EXISTS trg_users_reference_types ON core.users")
    op.execute("DROP FUNCTION IF EXISTS core.enforce_reference_value_types()")
    op.execute("DROP TABLE IF EXISTS planning.mawf_artifact_refs CASCADE")
    op.execute("DROP INDEX IF EXISTS ix_tasks_prompt_id")
    op.execute("DROP INDEX IF EXISTS ix_tasks_owner_updated")
    op.execute("DROP INDEX IF EXISTS ux_tasks_mawf_task_id")
    op.execute("ALTER TABLE planning.tasks DROP COLUMN IF EXISTS task_ledger_ref")
    op.execute("ALTER TABLE planning.tasks DROP COLUMN IF EXISTS prompt_id")
    op.execute("ALTER TABLE planning.tasks DROP COLUMN IF EXISTS owner_user_id")
    op.execute("ALTER TABLE planning.tasks DROP COLUMN IF EXISTS mawf_task_id")
    op.execute("DROP TABLE IF EXISTS ops.mawf_prompts CASCADE")
    op.execute("DROP INDEX IF EXISTS ix_repositories_status_id")
    op.execute("DROP INDEX IF EXISTS ux_repositories_mawf_repository_id")
    op.execute("ALTER TABLE catalog.repositories DROP COLUMN IF EXISTS status_id")
    op.execute("ALTER TABLE catalog.repositories DROP COLUMN IF EXISTS repo_name")
    op.execute("ALTER TABLE catalog.repositories DROP COLUMN IF EXISTS owner")
    op.execute("ALTER TABLE catalog.repositories DROP COLUMN IF EXISTS provider")
    op.execute("ALTER TABLE catalog.repositories DROP COLUMN IF EXISTS mawf_repository_id")
    op.execute("DROP INDEX IF EXISTS ux_projects_mawf_project_key")
    op.execute("ALTER TABLE planning.projects DROP COLUMN IF EXISTS mawf_project_key")
    op.execute("DROP TABLE IF EXISTS core.users CASCADE")
    op.execute("DROP INDEX IF EXISTS ux_reference_values_type_mawf_code")
    op.execute("ALTER TABLE core.reference_values DROP COLUMN IF EXISTS mawf_code")
