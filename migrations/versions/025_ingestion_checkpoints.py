"""Stable per-(repo, commit, branch) ingestion checkpoint store.

Revision ID: 025_ingestion_checkpoints
Revises: 024_route_policy_recalibrate
Create Date: 2026-06-05

Dispatcher jobs checkpoint on ops.job_manifests (keyed by job_id). Offline /
manual ingestion runs have no job_id, so their progress was never persisted and
an interrupted heavy rebuild restarted from scratch. This table gives those runs
a stable resume key (repository_id, commit_sha, branch_name). The dispatcher
path is unaffected.
"""
from alembic import op

revision = "025_ingestion_checkpoints"
down_revision = "024_route_policy_recalibrate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.ingestion_checkpoints (
            repository_id   BIGINT NOT NULL REFERENCES catalog.repositories(id),
            commit_sha      VARCHAR(40)  NOT NULL,
            branch_name     VARCHAR(255) NOT NULL,
            checkpoint_data JSONB        NOT NULL,
            updated_utc     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            PRIMARY KEY (repository_id, commit_sha, branch_name)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.ingestion_checkpoints")
