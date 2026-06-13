"""Add Tier-2 working-agreement corpus

Revision ID: 027_corpus_schema
Revises: 026_qa_pairs
Create Date: 2026-06-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "027_corpus_schema"
down_revision: Union[str, None] = "026_qa_pairs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Global (not repository-scoped) Tier-2 corpus: directive rationale, playbook detail,
    # examples, reference. Written directly (no propose->commit); PG is the source of truth,
    # Qdrant holds the searchable projection (collection registered in db/qdrant.py).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory.corpus_entries (
            id              BIGSERIAL PRIMARY KEY,
            entry_key       UUID NOT NULL,
            kind            TEXT NOT NULL,
            title           TEXT NOT NULL,
            body_text       TEXT NOT NULL,
            tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
            link_slug       TEXT,
            confidence      REAL,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            supersedes_key  UUID,
            created_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_corpus_entries_entry_key UNIQUE (entry_key),
            CONSTRAINT ck_corpus_entries_kind CHECK (
                kind IN ('directive_rationale', 'playbook_detail', 'example', 'reference')
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_corpus_entries_link_slug "
        "ON memory.corpus_entries(link_slug)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_corpus_entries_kind "
        "ON memory.corpus_entries(kind)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_corpus_entries_kind")
    op.execute("DROP INDEX IF EXISTS ix_corpus_entries_link_slug")
    op.execute("DROP TABLE IF EXISTS memory.corpus_entries CASCADE")
