"""Add MAWF task execution leases

Revision ID: 017_mawf_task_execution_leases
Revises: 016_mawf_contract
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "017_mawf_task_execution_leases"
down_revision: Union[str, None] = "016_mawf_contract"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        INSERT INTO core.reference_types (internal_code, name, description)
        VALUES
          ('TASK_EXECUTION_LEASE_STATUS', 'Task Execution Lease Status', 'MAWF task execution lease lifecycle states'),
          ('TASK_EXECUTION_LEASE_RELEASE_REASON', 'Task Execution Lease Release Reason', 'MAWF task execution lease release reasons')
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
              ('TASK_EXECUTION_LEASE_STATUS', 'LEASE_ACTIVE', 'active', 'Active', 'Lease is active', 10, FALSE),
              ('TASK_EXECUTION_LEASE_STATUS', 'LEASE_RELEASED', 'released', 'Released', 'Lease was released normally', 20, TRUE),
              ('TASK_EXECUTION_LEASE_STATUS', 'LEASE_EXPIRED', 'expired', 'Expired', 'Lease expired or was reclaimed as stale', 30, TRUE),
              ('TASK_EXECUTION_LEASE_STATUS', 'LEASE_FAILED', 'failed', 'Failed', 'Lease ended with failure', 40, TRUE),
              ('TASK_EXECUTION_LEASE_RELEASE_REASON', 'LEASE_REASON_COMPLETED', 'completed', 'Completed', 'Execution completed', 10, TRUE),
              ('TASK_EXECUTION_LEASE_RELEASE_REASON', 'LEASE_REASON_FAILED', 'failed', 'Failed', 'Execution failed', 20, TRUE),
              ('TASK_EXECUTION_LEASE_RELEASE_REASON', 'LEASE_REASON_CANCELLED', 'cancelled', 'Cancelled', 'Execution was cancelled', 30, TRUE),
              ('TASK_EXECUTION_LEASE_RELEASE_REASON', 'LEASE_REASON_OPERATOR_CANCELLED', 'operator_cancelled', 'Operator Cancelled', 'Execution was cancelled by an operator', 40, TRUE),
              ('TASK_EXECUTION_LEASE_RELEASE_REASON', 'LEASE_REASON_SERVER_SHUTDOWN', 'server_shutdown', 'Server Shutdown', 'Execution lease released during server shutdown', 50, TRUE),
              ('TASK_EXECUTION_LEASE_RELEASE_REASON', 'LEASE_REASON_STALE_RECLAIMED', 'stale_reclaimed', 'Stale Reclaimed', 'Expired lease was reclaimed by another worker', 60, TRUE)
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
        CREATE TABLE IF NOT EXISTS ops.mawf_task_execution_leases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_id BIGINT NOT NULL REFERENCES planning.tasks(id) ON DELETE CASCADE,
            workflow_run_id BIGINT NULL REFERENCES ops.workflow_runs(id) ON DELETE SET NULL,
            lease_token UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            owner_user_id UUID NULL REFERENCES core.users(id) ON DELETE SET NULL,
            owner_instance_id TEXT NOT NULL,
            owner_host TEXT NULL,
            owner_process_id TEXT NULL,
            status_value_id BIGINT NOT NULL REFERENCES core.reference_values(id),
            acquired_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_heartbeat_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_utc TIMESTAMPTZ NOT NULL,
            released_utc TIMESTAMPTZ NULL,
            release_reason_value_id BIGINT NULL REFERENCES core.reference_values(id),
            metadata_json JSONB NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_mawf_task_execution_leases_open_task
        ON ops.mawf_task_execution_leases(task_id)
        WHERE released_utc IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mawf_task_execution_leases_task_id
        ON ops.mawf_task_execution_leases(task_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mawf_task_execution_leases_workflow_run_id
        ON ops.mawf_task_execution_leases(workflow_run_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mawf_task_execution_leases_owner_user_id
        ON ops.mawf_task_execution_leases(owner_user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mawf_task_execution_leases_status_expires
        ON ops.mawf_task_execution_leases(status_value_id, expires_utc)
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION ops.enforce_mawf_task_execution_lease_workflow_task()
        RETURNS trigger AS $$
        DECLARE
            ok boolean;
        BEGIN
            IF NEW.workflow_run_id IS NOT NULL THEN
                SELECT EXISTS (
                    SELECT 1
                    FROM planning.task_workflow_runs twr
                    WHERE twr.task_id = NEW.task_id
                      AND twr.workflow_run_id = NEW.workflow_run_id
                ) INTO ok;
                IF NOT ok THEN
                    RAISE EXCEPTION 'workflow_run_id % is not linked to task_id %',
                        NEW.workflow_run_id, NEW.task_id;
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_mawf_task_execution_leases_reference_types ON ops.mawf_task_execution_leases")
    op.execute(
        """
        CREATE TRIGGER trg_mawf_task_execution_leases_reference_types
        BEFORE INSERT OR UPDATE ON ops.mawf_task_execution_leases
        FOR EACH ROW EXECUTE FUNCTION core.enforce_reference_value_types(
            'status_value_id', 'TASK_EXECUTION_LEASE_STATUS',
            'release_reason_value_id', 'TASK_EXECUTION_LEASE_RELEASE_REASON'
        )
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_mawf_task_execution_leases_workflow_task ON ops.mawf_task_execution_leases")
    op.execute(
        """
        CREATE TRIGGER trg_mawf_task_execution_leases_workflow_task
        BEFORE INSERT OR UPDATE ON ops.mawf_task_execution_leases
        FOR EACH ROW EXECUTE FUNCTION ops.enforce_mawf_task_execution_lease_workflow_task()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_mawf_task_execution_leases_workflow_task ON ops.mawf_task_execution_leases")
    op.execute("DROP TRIGGER IF EXISTS trg_mawf_task_execution_leases_reference_types ON ops.mawf_task_execution_leases")
    op.execute("DROP FUNCTION IF EXISTS ops.enforce_mawf_task_execution_lease_workflow_task()")
    op.execute("DROP TABLE IF EXISTS ops.mawf_task_execution_leases CASCADE")
    op.execute(
        """
        DELETE FROM core.reference_values
        WHERE internal_code IN (
            'LEASE_ACTIVE', 'LEASE_RELEASED', 'LEASE_EXPIRED', 'LEASE_FAILED',
            'LEASE_REASON_COMPLETED', 'LEASE_REASON_FAILED', 'LEASE_REASON_CANCELLED',
            'LEASE_REASON_OPERATOR_CANCELLED', 'LEASE_REASON_SERVER_SHUTDOWN',
            'LEASE_REASON_STALE_RECLAIMED'
        )
        """
    )
    op.execute(
        """
        DELETE FROM core.reference_types
        WHERE internal_code IN (
            'TASK_EXECUTION_LEASE_STATUS',
            'TASK_EXECUTION_LEASE_RELEASE_REASON'
        )
        """
    )
