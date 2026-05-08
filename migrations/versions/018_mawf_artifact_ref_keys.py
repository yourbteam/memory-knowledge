"""Add MAWF artifact reference keys

Revision ID: 018_mawf_artifact_ref_keys
Revises: 017_mawf_task_execution_leases
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "018_mawf_artifact_ref_keys"
down_revision: Union[str, None] = "017_mawf_task_execution_leases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
              ('ARTIFACT_WORKFLOW_LEDGER', 'workflow_ledger', 'Workflow Ledger', 'Workflow ledger durable reference', 40),
              ('ARTIFACT_WORKFLOW_STATE', 'workflow_state', 'Workflow State', 'Workflow state durable reference', 50),
              ('ARTIFACT_PHASE_LEDGER', 'phase_ledger', 'Phase Ledger', 'Phase ledger durable reference', 60),
              ('ARTIFACT_TELEMETRY_JSONL', 'telemetry_jsonl', 'Telemetry JSONL', 'Telemetry JSONL durable reference', 70),
              ('ARTIFACT_TELEMETRY_SUMMARY', 'telemetry_summary', 'Telemetry Summary', 'Telemetry summary durable reference', 80),
              ('ARTIFACT_GENERATED_ARTIFACT', 'generated_artifact', 'Generated Artifact', 'Generated artifact durable reference', 90),
              ('ARTIFACT_FEEDBACK_PAYLOAD', 'feedback_payload', 'Feedback Payload', 'Feedback payload durable reference', 100)
        ) AS v(internal_code, mawf_code, display_name, description, sort_order)
          ON rt.internal_code = 'ARTIFACT_ROLE'
        ON CONFLICT (internal_code) DO UPDATE SET
            mawf_code = COALESCE(core.reference_values.mawf_code, EXCLUDED.mawf_code),
            description = COALESCE(core.reference_values.description, EXCLUDED.description),
            updated_utc = NOW()
        """
    )

    op.execute("ALTER TABLE planning.mawf_artifact_refs ADD COLUMN IF NOT EXISTS artifact_key TEXT")
    op.execute(
        """
        UPDATE planning.mawf_artifact_refs ar
        SET artifact_key = COALESCE(role.mawf_code, role.internal_code)
        FROM core.reference_values role
        WHERE ar.role_id = role.id
          AND ar.artifact_key IS NULL
        """
    )
    op.execute("ALTER TABLE planning.mawf_artifact_refs ALTER COLUMN artifact_key SET NOT NULL")
    op.execute("ALTER TABLE planning.mawf_artifact_refs DROP CONSTRAINT IF EXISTS uq_mawf_artifact_refs_task_role")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_mawf_artifact_refs_task_artifact_key
        ON planning.mawf_artifact_refs(mawf_task_id, artifact_key)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_mawf_artifact_refs_task_role
        ON planning.mawf_artifact_refs(mawf_task_id, role_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_mawf_artifact_refs_task_role")
    op.execute("DROP INDEX IF EXISTS ux_mawf_artifact_refs_task_artifact_key")
    op.execute(
        """
        ALTER TABLE planning.mawf_artifact_refs
        ADD CONSTRAINT uq_mawf_artifact_refs_task_role UNIQUE (mawf_task_id, role_id)
        """
    )
    op.execute("ALTER TABLE planning.mawf_artifact_refs DROP COLUMN IF EXISTS artifact_key")
    op.execute(
        """
        DELETE FROM core.reference_values
        WHERE internal_code IN (
            'ARTIFACT_WORKFLOW_LEDGER',
            'ARTIFACT_WORKFLOW_STATE',
            'ARTIFACT_PHASE_LEDGER',
            'ARTIFACT_TELEMETRY_JSONL',
            'ARTIFACT_TELEMETRY_SUMMARY',
            'ARTIFACT_GENERATED_ARTIFACT',
            'ARTIFACT_FEEDBACK_PAYLOAD'
        )
        """
    )
