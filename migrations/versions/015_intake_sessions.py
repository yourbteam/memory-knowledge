"""Add durable intake session state

Revision ID: 015_intake_sessions
Revises: 014_triage_policy_governance
Create Date: 2026-04-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "015_intake_sessions"
down_revision: Union[str, None] = "014_triage_policy_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.intake_sessions (
            id BIGSERIAL PRIMARY KEY,
            session_key VARCHAR(100) NOT NULL UNIQUE,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            mode VARCHAR(30) NOT NULL,
            title TEXT,
            actor_email TEXT,
            actor_id TEXT,
            repository_key VARCHAR(255),
            project_key VARCHAR(255),
            feature_key VARCHAR(255),
            task_key VARCHAR(255),
            final_draft_revision INTEGER,
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finalized_utc TIMESTAMPTZ,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT ck_intake_sessions_status
                CHECK (status IN ('active', 'finalized', 'cancelled', 'expired')),
            CONSTRAINT ck_intake_sessions_mode
                CHECK (mode IN ('full', 'quick'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.intake_events (
            id BIGSERIAL PRIMARY KEY,
            event_key VARCHAR(100) NOT NULL UNIQUE,
            session_key VARCHAR(100) NOT NULL REFERENCES ops.intake_sessions(session_key) ON DELETE CASCADE,
            sequence INTEGER NOT NULL,
            role VARCHAR(30) NOT NULL,
            event_type VARCHAR(80) NOT NULL,
            content_text TEXT,
            content_json JSONB,
            attachment_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
            source VARCHAR(80),
            model_provider VARCHAR(80),
            model_name VARCHAR(160),
            idempotency_key VARCHAR(255),
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT ck_intake_events_role
                CHECK (role IN ('user', 'assistant', 'system', 'tool')),
            CONSTRAINT ux_intake_events_session_sequence UNIQUE (session_key, sequence)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.intake_distilled_context (
            session_key VARCHAR(100) PRIMARY KEY REFERENCES ops.intake_sessions(session_key) ON DELETE CASCADE,
            revision INTEGER NOT NULL,
            updated_from_sequence INTEGER NOT NULL,
            distilled_context JSONB NOT NULL,
            source_event_range JSONB NOT NULL,
            updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.intake_draft_revisions (
            id BIGSERIAL PRIMARY KEY,
            draft_revision_key VARCHAR(100) NOT NULL UNIQUE,
            session_key VARCHAR(100) NOT NULL REFERENCES ops.intake_sessions(session_key) ON DELETE CASCADE,
            revision INTEGER NOT NULL,
            status VARCHAR(30) NOT NULL,
            draft_json JSONB NOT NULL,
            draft_markdown TEXT,
            source_distilled_revision INTEGER,
            source_event_range JSONB NOT NULL,
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT ck_intake_draft_revisions_status
                CHECK (status IN ('draft', 'verified', 'final', 'rejected')),
            CONSTRAINT ux_intake_draft_revisions_session_revision UNIQUE (session_key, revision)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.intake_asset_refs (
            id BIGSERIAL PRIMARY KEY,
            asset_ref_key VARCHAR(100) NOT NULL UNIQUE,
            session_key VARCHAR(100) NOT NULL REFERENCES ops.intake_sessions(session_key) ON DELETE CASCADE,
            event_key VARCHAR(100) NOT NULL REFERENCES ops.intake_events(event_key) ON DELETE CASCADE,
            asset_type VARCHAR(80) NOT NULL,
            display_name TEXT NOT NULL,
            uri TEXT NOT NULL,
            mime_type VARCHAR(160),
            description TEXT,
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.intake_workflow_links (
            id BIGSERIAL PRIMARY KEY,
            link_key VARCHAR(100) NOT NULL UNIQUE,
            session_key VARCHAR(100) NOT NULL REFERENCES ops.intake_sessions(session_key) ON DELETE CASCADE,
            run_id UUID NOT NULL,
            workflow_name VARCHAR(255) NOT NULL,
            link_type VARCHAR(80) NOT NULL,
            repository_key VARCHAR(255),
            project_key VARCHAR(255),
            feature_key VARCHAR(255),
            task_key VARCHAR(255),
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_intake_events_session_idempotency
        ON ops.intake_events(session_key, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_sessions_actor_status_updated ON ops.intake_sessions(actor_email, status, updated_utc DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_sessions_repository ON ops.intake_sessions(repository_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_sessions_project ON ops.intake_sessions(project_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_sessions_feature ON ops.intake_sessions(feature_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_sessions_task ON ops.intake_sessions(task_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_events_session_sequence ON ops.intake_events(session_key, sequence)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_asset_refs_session ON ops.intake_asset_refs(session_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_workflow_links_session ON ops.intake_workflow_links(session_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_workflow_links_run ON ops.intake_workflow_links(run_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_intake_workflow_links_run")
    op.execute("DROP INDEX IF EXISTS ix_intake_workflow_links_session")
    op.execute("DROP INDEX IF EXISTS ix_intake_asset_refs_session")
    op.execute("DROP INDEX IF EXISTS ix_intake_events_session_sequence")
    op.execute("DROP INDEX IF EXISTS ix_intake_sessions_task")
    op.execute("DROP INDEX IF EXISTS ix_intake_sessions_feature")
    op.execute("DROP INDEX IF EXISTS ix_intake_sessions_project")
    op.execute("DROP INDEX IF EXISTS ix_intake_sessions_repository")
    op.execute("DROP INDEX IF EXISTS ix_intake_sessions_actor_status_updated")
    op.execute("DROP INDEX IF EXISTS ux_intake_events_session_idempotency")
    op.execute("DROP TABLE IF EXISTS ops.intake_workflow_links")
    op.execute("DROP TABLE IF EXISTS ops.intake_asset_refs")
    op.execute("DROP TABLE IF EXISTS ops.intake_draft_revisions")
    op.execute("DROP TABLE IF EXISTS ops.intake_distilled_context")
    op.execute("DROP TABLE IF EXISTS ops.intake_events")
    op.execute("DROP TABLE IF EXISTS ops.intake_sessions")
