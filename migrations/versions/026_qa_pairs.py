"""qa_pairs: standalone per-repo Q&A knowledge store."""

from alembic import op

revision = "026_qa_pairs"
down_revision = "025_ingestion_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory.qa_pairs (
            qa_pair_id      UUID PRIMARY KEY,
            repository_id   BIGINT NOT NULL REFERENCES catalog.repositories(id),
            feature_key     VARCHAR(255),
            task_key        VARCHAR(255),
            question        TEXT NOT NULL,
            answer          TEXT NOT NULL,
            question_hash   TEXT NOT NULL,
            question_tsv    TSVECTOR,
            source          JSONB NOT NULL DEFAULT '{}'::jsonb,
            confidence      NUMERIC(3,2) NOT NULL DEFAULT 0.80,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            superseded_by   UUID REFERENCES memory.qa_pairs(qa_pair_id),
            created_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_qa_pairs_repo_qhash
            ON memory.qa_pairs(repository_id, question_hash);
        CREATE INDEX IF NOT EXISTS ix_qa_pairs_repo_active
            ON memory.qa_pairs(repository_id) WHERE is_active;
        CREATE INDEX IF NOT EXISTS ix_qa_pairs_qtsv
            ON memory.qa_pairs USING GIN (question_tsv);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory.qa_pairs;")
