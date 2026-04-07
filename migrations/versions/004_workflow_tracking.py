"""Add workflow tracking tables to ops schema

Revision ID: 004
Revises: 003
Create Date: 2026-04-07

Adds ops.workflow_runs, ops.workflow_artifacts, ops.workflow_phase_states
to persist workflow execution state and artifacts across container restarts.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE ops.workflow_runs (
            id              BIGSERIAL PRIMARY KEY,
            run_id          UUID NOT NULL UNIQUE,
            repository_id   BIGINT NOT NULL REFERENCES catalog.repositories(id),
            workflow_name   VARCHAR(100) NOT NULL,
            task_description TEXT,
            status          VARCHAR(50) NOT NULL DEFAULT 'pending',
            current_phase   VARCHAR(100),
            iteration_count INT NOT NULL DEFAULT 0,
            context_json    JSONB,
            started_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_utc   TIMESTAMPTZ,
            error_text      TEXT,
            correlation_id  UUID
        );

        CREATE INDEX ix_workflow_runs_repository ON ops.workflow_runs(repository_id);
        CREATE INDEX ix_workflow_runs_status ON ops.workflow_runs(status);
        CREATE INDEX ix_workflow_runs_run_id ON ops.workflow_runs(run_id);
    """)

    op.execute("""
        CREATE TABLE ops.workflow_artifacts (
            id              BIGSERIAL PRIMARY KEY,
            workflow_run_id BIGINT NOT NULL REFERENCES ops.workflow_runs(id) ON DELETE CASCADE,
            artifact_name   VARCHAR(255) NOT NULL,
            artifact_type   VARCHAR(50) NOT NULL,
            content_text    TEXT NOT NULL,
            content_tsv     TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content_text)) STORED,
            phase_id        VARCHAR(100),
            iteration       INT NOT NULL DEFAULT 1,
            is_final        BOOLEAN NOT NULL DEFAULT FALSE,
            created_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT uq_workflow_artifact_name UNIQUE (workflow_run_id, artifact_name)
        );

        CREATE INDEX ix_workflow_artifacts_run ON ops.workflow_artifacts(workflow_run_id);
        CREATE INDEX ix_workflow_artifacts_tsv ON ops.workflow_artifacts USING GIN(content_tsv);
    """)

    op.execute("""
        CREATE TABLE ops.workflow_phase_states (
            id              BIGSERIAL PRIMARY KEY,
            workflow_run_id BIGINT NOT NULL REFERENCES ops.workflow_runs(id) ON DELETE CASCADE,
            phase_id        VARCHAR(100) NOT NULL,
            status          VARCHAR(50) NOT NULL DEFAULT 'pending',
            decision        VARCHAR(50),
            handoff_text    TEXT,
            attempts        INT NOT NULL DEFAULT 0,
            started_utc     TIMESTAMPTZ,
            completed_utc   TIMESTAMPTZ,
            error_text      TEXT,
            metrics_json    JSONB,

            CONSTRAINT uq_workflow_phase_state UNIQUE (workflow_run_id, phase_id)
        );

        CREATE INDEX ix_workflow_phase_states_run ON ops.workflow_phase_states(workflow_run_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.workflow_phase_states CASCADE")
    op.execute("DROP TABLE IF EXISTS ops.workflow_artifacts CASCADE")
    op.execute("DROP TABLE IF EXISTS ops.workflow_runs CASCADE")
