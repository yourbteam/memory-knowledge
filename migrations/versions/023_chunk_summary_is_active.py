"""Add is_active to chunks and summaries.

Revision ID: 023_chunk_summary_is_active
Revises: 022_mawf_task_artifact_branch_metadata
Create Date: 2026-06-02
"""

from alembic import op

revision = "023_chunk_summary_is_active"
down_revision = "022_mawf_task_artifact_branch_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Soft-delete flag, mirroring Qdrant payload is_active. Existing rows default TRUE;
    #    historical stale rows are corrected by the one-time backfill (Step 1.6).
    op.execute(
        "ALTER TABLE catalog.chunks ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute(
        "ALTER TABLE catalog.summaries ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"
    )

    # 2. Partial GIN indexes: retrieval now always filters is_active = TRUE, so index only
    #    active rows on the tsvector that full-text search hits.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_tsv_active "
        "ON catalog.chunks USING GIN (content_tsv) WHERE is_active"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_summaries_tsv_active "
        "ON catalog.summaries USING GIN (summary_tsv) WHERE is_active"
    )

    # 3. Drop the now-superseded full GIN indexes (nothing reads these without the is_active filter).
    op.execute("DROP INDEX IF EXISTS catalog.idx_chunks_content_tsv")
    op.execute("DROP INDEX IF EXISTS catalog.idx_summaries_tsv")


def downgrade() -> None:
    # Recreate the original full GIN indexes from migration 001.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_content_tsv ON catalog.chunks USING GIN (content_tsv)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_summaries_tsv ON catalog.summaries USING GIN (summary_tsv)"
    )
    op.execute("DROP INDEX IF EXISTS catalog.idx_chunks_tsv_active")
    op.execute("DROP INDEX IF EXISTS catalog.idx_summaries_tsv_active")
    op.execute("ALTER TABLE catalog.summaries DROP COLUMN IF EXISTS is_active")
    op.execute("ALTER TABLE catalog.chunks DROP COLUMN IF EXISTS is_active")
