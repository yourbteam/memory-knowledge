"""Add triage policy artifact storage

Revision ID: 013_triage_policy_artifacts
Revises: 012_triage_decision_lifecycle_state
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "013_triage_policy_artifacts"
down_revision: Union[str, None] = "012_triage_decision_lifecycle_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.triage_policy_artifacts (
            id BIGSERIAL PRIMARY KEY,
            repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id) ON DELETE CASCADE,
            project_key VARCHAR(255),
            policy_kind VARCHAR(100) NOT NULL,
            policy_key VARCHAR(255) NOT NULL,
            version VARCHAR(100) NOT NULL,
            confidence DOUBLE PRECISION,
            case_count INTEGER NOT NULL DEFAULT 0,
            evidence_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_triage_policy_artifacts_scope
        ON ops.triage_policy_artifacts(repository_id, project_key, policy_kind, created_utc DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_triage_policy_artifacts_policy_key
        ON ops.triage_policy_artifacts(policy_key, version)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_triage_policy_artifacts_policy_key")
    op.execute("DROP INDEX IF EXISTS ix_triage_policy_artifacts_scope")
    op.execute("DROP TABLE IF EXISTS ops.triage_policy_artifacts CASCADE")
