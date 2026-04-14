"""Add triage policy governance metadata

Revision ID: 014_triage_policy_governance
Revises: 013_triage_policy_artifacts
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "014_triage_policy_governance"
down_revision: Union[str, None] = "013_triage_policy_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ops.triage_policy_artifacts
        ADD COLUMN IF NOT EXISTS rollout_stage VARCHAR(50) NOT NULL DEFAULT 'advisory'
        """
    )
    op.execute(
        """
        ALTER TABLE ops.triage_policy_artifacts
        ADD COLUMN IF NOT EXISTS confidence_threshold DOUBLE PRECISION
        """
    )
    op.execute(
        """
        ALTER TABLE ops.triage_policy_artifacts
        ADD COLUMN IF NOT EXISTS minimum_evidence_threshold INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE ops.triage_policy_artifacts
        ADD COLUMN IF NOT EXISTS drift_state VARCHAR(50) NOT NULL DEFAULT 'stable'
        """
    )
    op.execute(
        """
        ALTER TABLE ops.triage_policy_artifacts
        ADD COLUMN IF NOT EXISTS is_suppressed BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        """
        ALTER TABLE ops.triage_policy_artifacts
        ADD COLUMN IF NOT EXISTS last_reviewed_utc TIMESTAMPTZ
        """
    )
    op.execute(
        """
        ALTER TABLE ops.triage_policy_artifacts
        ADD COLUMN IF NOT EXISTS governance_notes TEXT
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_triage_policy_artifacts_governance
        ON ops.triage_policy_artifacts(repository_id, project_key, rollout_stage, drift_state, is_suppressed)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_triage_policy_artifacts_governance")
    op.execute("ALTER TABLE ops.triage_policy_artifacts DROP COLUMN IF EXISTS governance_notes")
    op.execute("ALTER TABLE ops.triage_policy_artifacts DROP COLUMN IF EXISTS last_reviewed_utc")
    op.execute("ALTER TABLE ops.triage_policy_artifacts DROP COLUMN IF EXISTS is_suppressed")
    op.execute("ALTER TABLE ops.triage_policy_artifacts DROP COLUMN IF EXISTS drift_state")
    op.execute("ALTER TABLE ops.triage_policy_artifacts DROP COLUMN IF EXISTS minimum_evidence_threshold")
    op.execute("ALTER TABLE ops.triage_policy_artifacts DROP COLUMN IF EXISTS confidence_threshold")
    op.execute("ALTER TABLE ops.triage_policy_artifacts DROP COLUMN IF EXISTS rollout_stage")
