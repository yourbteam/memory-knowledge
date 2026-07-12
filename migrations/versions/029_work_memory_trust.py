"""Add work-memory trust metadata and import report tables.

Revision ID: 029_work_memory_trust
Revises: 028_learned_records_nullable_evidence
"""

from __future__ import annotations

from alembic import op

revision: str = "029_work_memory_trust"
down_revision: str | None = "028_learned_records_nullable_evidence"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE memory.learned_records ADD COLUMN content_kind VARCHAR(50)")
    op.execute("ALTER TABLE memory.learned_records ADD COLUMN evidence_refs JSONB")
    op.execute("ALTER TABLE memory.learned_records ADD COLUMN evidence_resolution_errors JSONB")
    op.execute(
        """
        CREATE TABLE memory.learned_import_reports (
            import_id UUID PRIMARY KEY,
            repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id) ON DELETE CASCADE,
            cursor_secret BYTEA,
            unresolved_total INTEGER NOT NULL CHECK (unresolved_total >= 0),
            created_utc TIMESTAMPTZ NOT NULL,
            expires_utc TIMESTAMPTZ NOT NULL,
            expired_utc TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE memory.learned_import_unresolved (
            import_id UUID NOT NULL REFERENCES memory.learned_import_reports(import_id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            entity_key UUID NOT NULL,
            reason_codes JSONB NOT NULL,
            PRIMARY KEY (import_id, ordinal),
            UNIQUE (import_id, entity_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_learned_import_reports_repository_expiry "
        "ON memory.learned_import_reports (repository_id, expires_utc, import_id)"
    )
    op.execute(
        """
        CREATE INDEX idx_learned_records_operator_note_review
        ON memory.learned_records (created_utc, id)
        WHERE memory_type = 'operator_note'
          AND (verification_status = 'unverified' OR content_kind IS NULL OR evidence_refs IS NULL)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE memory.learned_import_unresolved")
    op.execute("DROP TABLE memory.learned_import_reports")
    op.execute("DROP INDEX memory.idx_learned_records_operator_note_review")
    op.execute("ALTER TABLE memory.learned_records DROP COLUMN evidence_resolution_errors")
    op.execute("ALTER TABLE memory.learned_records DROP COLUMN evidence_refs")
    op.execute("ALTER TABLE memory.learned_records DROP COLUMN content_kind")
