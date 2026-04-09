"""Add workflow analytics schema support

Revision ID: 008_analytics_schema
Revises: 007_task_single_repository
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op

revision: str = "008_analytics_schema"
down_revision: Union[str, None] = "007_task_single_repository"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO core.reference_types (internal_code, name, description)
        VALUES (
            'WORKFLOW_VALIDATOR_STATUS',
            'Workflow Validator Status',
            'Lifecycle states for workflow validator results'
        )
        ON CONFLICT (internal_code) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO core.reference_values (
            reference_type_id, internal_code, display_name, sort_order, is_terminal
        )
        SELECT rt.id, v.internal_code, v.display_name, v.sort_order, v.is_terminal
        FROM core.reference_types rt
        JOIN (
            VALUES
                ('VAL_PENDING', 'Pending', 10, FALSE),
                ('VAL_PASSED', 'Passed', 20, TRUE),
                ('VAL_FAILED', 'Failed', 30, TRUE),
                ('VAL_SKIPPED', 'Skipped', 40, TRUE),
                ('VAL_ERROR', 'Error', 50, TRUE)
        ) AS v(internal_code, display_name, sort_order, is_terminal)
          ON rt.internal_code = 'WORKFLOW_VALIDATOR_STATUS'
        ON CONFLICT (internal_code) DO NOTHING
        """
    )

    op.execute(
        "ALTER TABLE ops.workflow_phase_states ALTER COLUMN attempts SET DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE ops.workflow_phase_states "
        "ADD COLUMN IF NOT EXISTS created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )
    op.execute(
        "ALTER TABLE ops.workflow_phase_states "
        "ADD COLUMN IF NOT EXISTS updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.workflow_validator_results (
            id BIGSERIAL PRIMARY KEY,
            workflow_run_id BIGINT NOT NULL REFERENCES ops.workflow_runs(id) ON DELETE CASCADE,
            phase_id VARCHAR(100) NOT NULL,
            validator_code VARCHAR(100) NOT NULL,
            validator_name VARCHAR(255) NOT NULL,
            attempt_number INT NOT NULL,
            status_id BIGINT NOT NULL REFERENCES core.reference_values(id),
            failure_reason_code VARCHAR(100),
            failure_reason TEXT,
            details_json JSONB,
            correlation_id UUID,
            started_utc TIMESTAMPTZ,
            completed_utc TIMESTAMPTZ,
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_workflow_validator_result UNIQUE (
                workflow_run_id, phase_id, validator_code, attempt_number
            )
        )
        """
    )

    op.execute(
        """
        DELETE FROM planning.task_workflow_runs twr
        USING planning.tasks t, ops.workflow_runs wr
        WHERE twr.task_id = t.id
          AND twr.workflow_run_id = wr.id
          AND wr.repository_id <> t.repository_id
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_runs_started_utc "
        "ON ops.workflow_runs(started_utc)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_phase_states_started_utc "
        "ON ops.workflow_phase_states(started_utc)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_validator_results_started_utc "
        "ON ops.workflow_validator_results(started_utc)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_validator_results_run "
        "ON ops.workflow_validator_results(workflow_run_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_workflow_validator_results_run")
    op.execute("DROP INDEX IF EXISTS ix_workflow_validator_results_started_utc")
    op.execute("DROP INDEX IF EXISTS ix_workflow_phase_states_started_utc")
    op.execute("DROP INDEX IF EXISTS ix_workflow_runs_started_utc")
    op.execute("DROP TABLE IF EXISTS ops.workflow_validator_results CASCADE")
    op.execute(
        """
        DELETE FROM core.reference_values
        WHERE reference_type_id = (
            SELECT id FROM core.reference_types
            WHERE internal_code = 'WORKFLOW_VALIDATOR_STATUS'
        )
        """
    )
    op.execute(
        "DELETE FROM core.reference_types WHERE internal_code = 'WORKFLOW_VALIDATOR_STATUS'"
    )
    op.execute(
        "ALTER TABLE ops.workflow_phase_states DROP COLUMN IF EXISTS updated_utc"
    )
    op.execute(
        "ALTER TABLE ops.workflow_phase_states DROP COLUMN IF EXISTS created_utc"
    )
    op.execute(
        "ALTER TABLE ops.workflow_phase_states ALTER COLUMN attempts SET DEFAULT 0"
    )
