"""Allow evidence-free learned records (human-asserted repo notes)

Revision ID: 028_learned_records_nullable_evidence
Revises: 027_corpus_schema
Create Date: 2026-06-20

Migration 001 set memory.learned_records.evidence_entity_id and evidence_chunk_id to
NOT NULL (evidence-by-default for agent proposals). Human-asserted repo-level notes
(author_repo_note, source_kind='operator_note', verification_status='human_asserted')
legitimately have no code evidence — the system's guardrail exempts human-confirmed
memory from evidence-by-default. Relax both columns to nullable so such notes can be
stored; agent proposals still supply evidence by their own code path.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "028_learned_records_nullable_evidence"
down_revision: Union[str, None] = "027_corpus_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE memory.learned_records ALTER COLUMN evidence_entity_id DROP NOT NULL")
    op.execute("ALTER TABLE memory.learned_records ALTER COLUMN evidence_chunk_id DROP NOT NULL")


def downgrade() -> None:
    # Re-assert NOT NULL (fails if any evidence-free rows exist — expected for a downgrade).
    op.execute("ALTER TABLE memory.learned_records ALTER COLUMN evidence_chunk_id SET NOT NULL")
    op.execute("ALTER TABLE memory.learned_records ALTER COLUMN evidence_entity_id SET NOT NULL")
