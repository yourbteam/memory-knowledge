"""Add workflow findings and critic decisions

Revision ID: 009_workflow_findings
Revises: 008_analytics_schema
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "009_workflow_findings"
down_revision: Union[str, None] = "008_analytics_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO core.reference_types (internal_code, name, description)
        VALUES
            ('WORKFLOW_FINDING_KIND', 'Workflow Finding Kind', 'Canonical finding categories for verifier and reviewer findings'),
            ('WORKFLOW_FINDING_DECISION_BUCKET', 'Workflow Finding Decision Bucket', 'Canonical critic decision buckets for workflow findings'),
            ('WORKFLOW_FINDING_SUPPRESSION_SCOPE', 'Workflow Finding Suppression Scope', 'Canonical suppression scopes for workflow findings'),
            ('WORKFLOW_FINDING_STATUS', 'Workflow Finding Status', 'Lifecycle states for workflow findings')
        ON CONFLICT (internal_code) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO core.reference_values (
            reference_type_id, internal_code, display_name, sort_order, is_terminal
        )
        SELECT rt.id, v.internal_code, v.display_name, v.sort_order, v.is_terminal
        FROM core.reference_types rt
        JOIN (
            VALUES
                ('WORKFLOW_FINDING_KIND', 'HALLUCINATED_REFERENCE', 'Hallucinated Reference', 10, FALSE),
                ('WORKFLOW_FINDING_KIND', 'FALSE_POSITIVE', 'False Positive', 20, FALSE),
                ('WORKFLOW_FINDING_KIND', 'MISSING_REQUIREMENT', 'Missing Requirement', 30, FALSE),
                ('WORKFLOW_FINDING_KIND', 'LOGIC_GAP', 'Logic Gap', 40, FALSE),
                ('WORKFLOW_FINDING_KIND', 'DUPLICATE', 'Duplicate', 50, FALSE),
                ('WORKFLOW_FINDING_KIND', 'UNVERIFIABLE', 'Unverifiable', 60, FALSE),
                ('WORKFLOW_FINDING_KIND', 'LOW_PRIORITY_IMPROVEMENT', 'Low Priority Improvement', 70, FALSE),
                ('WORKFLOW_FINDING_KIND', 'SCOPE_LEAK', 'Scope Leak', 80, FALSE),
                ('WORKFLOW_FINDING_KIND', 'UNKNOWN', 'Unknown', 90, FALSE),
                ('WORKFLOW_FINDING_DECISION_BUCKET', 'FIX_NOW', 'Fix Now', 10, FALSE),
                ('WORKFLOW_FINDING_DECISION_BUCKET', 'FIX_NOW_PROMOTED', 'Fix Now Promoted', 20, FALSE),
                ('WORKFLOW_FINDING_DECISION_BUCKET', 'VALID', 'Valid', 30, FALSE),
                ('WORKFLOW_FINDING_DECISION_BUCKET', 'ACKNOWLEDGE_OK', 'Acknowledge OK', 40, FALSE),
                ('WORKFLOW_FINDING_DECISION_BUCKET', 'DISMISS', 'Dismiss', 50, FALSE),
                ('WORKFLOW_FINDING_DECISION_BUCKET', 'FILTERED', 'Filtered', 60, FALSE),
                ('WORKFLOW_FINDING_SUPPRESSION_SCOPE', 'RUN_LOCAL', 'Run Local', 10, FALSE),
                ('WORKFLOW_FINDING_STATUS', 'OPEN', 'Open', 10, FALSE),
                ('WORKFLOW_FINDING_STATUS', 'RESOLVED', 'Resolved', 20, TRUE),
                ('WORKFLOW_FINDING_STATUS', 'SUPPRESSED', 'Suppressed', 30, TRUE)
        ) AS v(type_code, internal_code, display_name, sort_order, is_terminal)
          ON rt.internal_code = v.type_code
        ON CONFLICT (internal_code) DO NOTHING
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.workflow_findings (
            id BIGSERIAL PRIMARY KEY,
            repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id) ON DELETE CASCADE,
            workflow_run_id BIGINT NOT NULL REFERENCES ops.workflow_runs(id) ON DELETE CASCADE,
            workflow_name VARCHAR(255) NOT NULL,
            phase_id VARCHAR(255) NOT NULL,
            agent_name VARCHAR(255) NOT NULL,
            attempt_number INT NOT NULL,
            artifact_name VARCHAR(255),
            artifact_iteration INT,
            artifact_hash VARCHAR(255),
            finding_fingerprint VARCHAR(255) NOT NULL,
            finding_title TEXT NOT NULL,
            finding_message TEXT NOT NULL,
            location TEXT,
            evidence_text TEXT,
            finding_kind_id BIGINT NOT NULL REFERENCES core.reference_values(id),
            severity VARCHAR(50),
            source_kind VARCHAR(100),
            status_id BIGINT NOT NULL REFERENCES core.reference_values(id),
            actor_email VARCHAR(255),
            context_json JSONB,
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_workflow_finding UNIQUE (
                workflow_run_id, phase_id, attempt_number, finding_fingerprint
            )
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.workflow_finding_decisions (
            id BIGSERIAL PRIMARY KEY,
            repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id) ON DELETE CASCADE,
            workflow_run_id BIGINT NOT NULL REFERENCES ops.workflow_runs(id) ON DELETE CASCADE,
            workflow_finding_id BIGINT NOT NULL REFERENCES ops.workflow_findings(id) ON DELETE CASCADE,
            workflow_name VARCHAR(255) NOT NULL,
            critic_phase_id VARCHAR(255) NOT NULL,
            critic_agent_name VARCHAR(255) NOT NULL,
            attempt_number INT NOT NULL,
            finding_fingerprint VARCHAR(255) NOT NULL,
            decision_bucket_id BIGINT NOT NULL REFERENCES core.reference_values(id),
            actionable BOOLEAN NOT NULL,
            reason_text TEXT,
            evidence_text TEXT,
            suppression_scope_id BIGINT NOT NULL REFERENCES core.reference_values(id),
            suppress_on_rerun BOOLEAN NOT NULL DEFAULT FALSE,
            artifact_name VARCHAR(255),
            artifact_iteration INT,
            artifact_hash VARCHAR(255),
            actor_email VARCHAR(255),
            context_json JSONB,
            created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_workflow_finding_decision UNIQUE (
                workflow_finding_id, critic_phase_id, critic_agent_name, attempt_number,
                decision_bucket_id, created_utc
            )
        )
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_findings_repo_run "
        "ON ops.workflow_findings(repository_id, workflow_run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_findings_run_identity "
        "ON ops.workflow_findings(workflow_run_id, phase_id, attempt_number, finding_fingerprint)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_findings_repo_created "
        "ON ops.workflow_findings(repository_id, created_utc)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_findings_repo_agent_created "
        "ON ops.workflow_findings(repository_id, agent_name, created_utc)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_findings_repo_kind_created "
        "ON ops.workflow_findings(repository_id, finding_kind_id, created_utc)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_finding_decisions_repo_run "
        "ON ops.workflow_finding_decisions(repository_id, workflow_run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_finding_decisions_finding_created "
        "ON ops.workflow_finding_decisions(workflow_finding_id, created_utc)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_finding_decisions_repo_bucket_created "
        "ON ops.workflow_finding_decisions(repository_id, decision_bucket_id, created_utc)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_finding_decisions_repo_suppress_created "
        "ON ops.workflow_finding_decisions(repository_id, suppress_on_rerun, created_utc)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workflow_finding_decisions_repo_phase_created "
        "ON ops.workflow_finding_decisions(repository_id, critic_phase_id, created_utc)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_workflow_finding_decisions_repo_phase_created")
    op.execute("DROP INDEX IF EXISTS ix_workflow_finding_decisions_repo_suppress_created")
    op.execute("DROP INDEX IF EXISTS ix_workflow_finding_decisions_repo_bucket_created")
    op.execute("DROP INDEX IF EXISTS ix_workflow_finding_decisions_finding_created")
    op.execute("DROP INDEX IF EXISTS ix_workflow_finding_decisions_repo_run")
    op.execute("DROP INDEX IF EXISTS ix_workflow_findings_repo_kind_created")
    op.execute("DROP INDEX IF EXISTS ix_workflow_findings_repo_agent_created")
    op.execute("DROP INDEX IF EXISTS ix_workflow_findings_repo_created")
    op.execute("DROP INDEX IF EXISTS ix_workflow_findings_run_identity")
    op.execute("DROP INDEX IF EXISTS ix_workflow_findings_repo_run")
    op.execute("DROP TABLE IF EXISTS ops.workflow_finding_decisions CASCADE")
    op.execute("DROP TABLE IF EXISTS ops.workflow_findings CASCADE")
    op.execute(
        """
        DELETE FROM core.reference_values
        WHERE reference_type_id IN (
            SELECT id FROM core.reference_types
            WHERE internal_code IN (
                'WORKFLOW_FINDING_KIND',
                'WORKFLOW_FINDING_DECISION_BUCKET',
                'WORKFLOW_FINDING_SUPPRESSION_SCOPE',
                'WORKFLOW_FINDING_STATUS'
            )
        )
        """
    )
    op.execute(
        """
        DELETE FROM core.reference_types
        WHERE internal_code IN (
            'WORKFLOW_FINDING_KIND',
            'WORKFLOW_FINDING_DECISION_BUCKET',
            'WORKFLOW_FINDING_SUPPRESSION_SCOPE',
            'WORKFLOW_FINDING_STATUS'
        )
        """
    )
