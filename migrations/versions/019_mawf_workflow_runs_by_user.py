"""Add MAWF workflow run user listing support

Revision ID: 019_mawf_workflow_runs_by_user
Revises: 018_mawf_artifact_ref_keys
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "019_mawf_workflow_runs_by_user"
down_revision: Union[str, None] = "018_mawf_artifact_ref_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ops.workflow_runs
        ADD COLUMN IF NOT EXISTS updated_utc TIMESTAMPTZ
        """
    )
    op.execute(
        """
        UPDATE ops.workflow_runs
        SET updated_utc = COALESCE(completed_utc, started_utc, NOW())
        WHERE updated_utc IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE ops.workflow_runs
        ALTER COLUMN updated_utc SET DEFAULT NOW()
        """
    )
    op.execute(
        """
        ALTER TABLE ops.workflow_runs
        ALTER COLUMN updated_utc SET NOT NULL
        """
    )

    op.execute(
        """
        INSERT INTO core.reference_values (
            reference_type_id, internal_code, mawf_code, display_name,
            description, sort_order, is_terminal
        )
        SELECT rt.id, v.internal_code, v.mawf_code, v.display_name,
               v.description, v.sort_order, FALSE
        FROM core.reference_types rt
        JOIN (
            VALUES
              ('RUN_WAITING_FOR_FEEDBACK', 'waiting_for_feedback', 'Waiting For Feedback', 'Workflow run is waiting for feedback', 35),
              ('RUN_RESUME_PENDING', 'resume_pending', 'Resume Pending', 'Workflow run is pending resume', 36)
        ) AS v(internal_code, mawf_code, display_name, description, sort_order)
          ON rt.internal_code = 'WORKFLOW_RUN_STATUS'
        ON CONFLICT (internal_code) DO UPDATE SET
            mawf_code = COALESCE(core.reference_values.mawf_code, EXCLUDED.mawf_code),
            display_name = EXCLUDED.display_name,
            description = COALESCE(core.reference_values.description, EXCLUDED.description),
            is_terminal = FALSE,
            updated_utc = NOW()
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_runs_status_updated_started
        ON ops.workflow_runs(status_id, updated_utc DESC, started_utc DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_workflow_runs_status_updated_started")
    op.execute(
        """
        DELETE FROM core.reference_values
        WHERE internal_code IN (
            'RUN_WAITING_FOR_FEEDBACK',
            'RUN_RESUME_PENDING'
        )
        """
    )
    op.execute("ALTER TABLE ops.workflow_runs DROP COLUMN IF EXISTS updated_utc")
