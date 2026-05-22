"""Add MAWF task artifact branch metadata.

Revision ID: 022_mawf_task_artifact_branch_metadata
Revises: 021_mawf_external_task_id
Create Date: 2026-05-22
"""

from alembic import op


revision = "022_mawf_task_artifact_branch_metadata"
down_revision = "021_mawf_external_task_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE planning.tasks
        ADD COLUMN IF NOT EXISTS task_artifact_branch TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE planning.mawf_artifact_refs
        ADD COLUMN IF NOT EXISTS artifact_branch TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE planning.mawf_artifact_refs
        ADD COLUMN IF NOT EXISTS artifact_key TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE planning.mawf_artifact_refs
        ALTER COLUMN artifact_key DROP NOT NULL
        """
    )
    op.execute(
        """
        UPDATE planning.mawf_artifact_refs ar
        SET artifact_key = NULL
        FROM core.reference_values role
        WHERE role.id = ar.role_id
          AND ar.artifact_key IS NOT NULL
          AND (
              ar.artifact_key = COALESCE(role.mawf_code, role.internal_code)
              OR ar.artifact_key = role.internal_code
          )
        """
    )
    op.execute("DROP INDEX IF EXISTS planning.ux_mawf_artifact_refs_task_artifact_key")
    op.execute(
        """
        ALTER TABLE planning.mawf_artifact_refs
        DROP CONSTRAINT IF EXISTS uq_mawf_artifact_refs_task_role
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_mawf_artifact_refs_task_artifact_key_keyed
        ON planning.mawf_artifact_refs(mawf_task_id, artifact_key)
        WHERE artifact_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_mawf_artifact_refs_task_role_legacy
        ON planning.mawf_artifact_refs(mawf_task_id, role_id)
        WHERE artifact_key IS NULL
        """
    )


def downgrade() -> None:
    # Best-effort downgrade: do not fabricate role-derived artifact_key values or
    # restore the pre-022 non-null key semantic contract.
    op.execute("DROP INDEX IF EXISTS planning.ux_mawf_artifact_refs_task_artifact_key_keyed")
    op.execute("DROP INDEX IF EXISTS planning.ux_mawf_artifact_refs_task_role_legacy")
    op.execute(
        """
        ALTER TABLE planning.mawf_artifact_refs
        DROP COLUMN IF EXISTS artifact_branch
        """
    )
    op.execute(
        """
        ALTER TABLE planning.tasks
        DROP COLUMN IF EXISTS task_artifact_branch
        """
    )
