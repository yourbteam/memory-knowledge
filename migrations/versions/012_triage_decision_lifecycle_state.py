"""Add triage decision lifecycle projection

Revision ID: 012_triage_decision_lifecycle_state
Revises: 011_triage_outcome_status_reference_values
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "012_triage_decision_lifecycle_state"
down_revision: Union[str, None] = "011_triage_outcome_status_reference_values"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO core.reference_types (internal_code, name, description)
        VALUES (
            'TRIAGE_DECISION_LIFECYCLE_STATE',
            'Triage Decision Lifecycle State',
            'Canonical case-level lifecycle state for triage decisions'
        )
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
                ('TRIAGE_LIFECYCLE_PROPOSED', 'Proposed', 10, FALSE),
                ('TRIAGE_LIFECYCLE_FEEDBACK_RECORDED', 'Feedback Recorded', 20, FALSE),
                ('TRIAGE_LIFECYCLE_VALIDATED', 'Validated', 30, TRUE),
                ('TRIAGE_LIFECYCLE_NEEDS_RETRIAGE', 'Needs Retriage', 40, FALSE),
                ('TRIAGE_LIFECYCLE_HUMAN_REJECTED', 'Human Rejected', 50, TRUE),
                ('TRIAGE_LIFECYCLE_SUPERSEDED', 'Superseded', 60, TRUE)
        ) AS v(internal_code, display_name, sort_order, is_terminal)
          ON rt.internal_code = 'TRIAGE_DECISION_LIFECYCLE_STATE'
        ON CONFLICT (internal_code) DO NOTHING
        """
    )

    op.execute(
        """
        ALTER TABLE ops.triage_cases
        ADD COLUMN IF NOT EXISTS lifecycle_state_id BIGINT REFERENCES core.reference_values(id)
        """
    )
    op.execute(
        """
        ALTER TABLE ops.triage_cases
        ADD COLUMN IF NOT EXISTS lifecycle_updated_utc TIMESTAMPTZ
        """
    )
    op.execute(
        """
        ALTER TABLE ops.triage_cases
        ADD COLUMN IF NOT EXISTS superseded_by_case_id UUID REFERENCES ops.triage_cases(triage_case_id)
        """
    )

    op.execute(
        """
        UPDATE ops.triage_cases tc
        SET lifecycle_state_id = state_map.lifecycle_state_id,
            lifecycle_updated_utc = state_map.lifecycle_updated_utc
        FROM (
            SELECT
                tc_inner.triage_case_id,
                rv_state.id AS lifecycle_state_id,
                COALESCE(fb.created_utc, tc_inner.created_utc) AS lifecycle_updated_utc
            FROM ops.triage_cases tc_inner
            LEFT JOIN LATERAL (
                SELECT
                    fb.outcome_status,
                    fb.human_override,
                    fb.created_utc,
                    rv.internal_code AS outcome_internal_code
                FROM ops.triage_case_feedback fb
                LEFT JOIN core.reference_values rv ON rv.id = fb.status_id
                WHERE fb.triage_case_id = tc_inner.triage_case_id
                ORDER BY fb.created_utc DESC, fb.id DESC
                LIMIT 1
            ) fb ON TRUE
            JOIN core.reference_values rv_state ON rv_state.internal_code = CASE
                WHEN fb.outcome_status IS NULL THEN 'TRIAGE_LIFECYCLE_PROPOSED'
                WHEN fb.human_override IS TRUE OR fb.outcome_internal_code = 'TRIAGE_OUTCOME_OVERRIDDEN_BY_HUMAN' THEN 'TRIAGE_LIFECYCLE_HUMAN_REJECTED'
                WHEN fb.outcome_internal_code = 'TRIAGE_OUTCOME_CONFIRMED_CORRECT' THEN 'TRIAGE_LIFECYCLE_VALIDATED'
                WHEN fb.outcome_internal_code = 'TRIAGE_OUTCOME_CORRECTED' THEN 'TRIAGE_LIFECYCLE_NEEDS_RETRIAGE'
                ELSE 'TRIAGE_LIFECYCLE_FEEDBACK_RECORDED'
            END
        ) state_map
        WHERE tc.triage_case_id = state_map.triage_case_id
          AND tc.lifecycle_state_id IS NULL
        """
    )

    op.execute(
        """
        UPDATE ops.triage_cases tc
        SET lifecycle_updated_utc = COALESCE(tc.lifecycle_updated_utc, tc.created_utc)
        WHERE tc.lifecycle_updated_utc IS NULL
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_triage_cases_lifecycle_state_id
        ON ops.triage_cases(lifecycle_state_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_triage_cases_superseded_by_case_id
        ON ops.triage_cases(superseded_by_case_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_triage_cases_superseded_by_case_id")
    op.execute("DROP INDEX IF EXISTS ix_triage_cases_lifecycle_state_id")
    op.execute(
        "ALTER TABLE ops.triage_cases DROP COLUMN IF EXISTS superseded_by_case_id"
    )
    op.execute(
        "ALTER TABLE ops.triage_cases DROP COLUMN IF EXISTS lifecycle_updated_utc"
    )
    op.execute(
        "ALTER TABLE ops.triage_cases DROP COLUMN IF EXISTS lifecycle_state_id"
    )
    op.execute(
        """
        DELETE FROM core.reference_values
        WHERE reference_type_id = (
            SELECT id FROM core.reference_types
            WHERE internal_code = 'TRIAGE_DECISION_LIFECYCLE_STATE'
        )
        """
    )
    op.execute(
        "DELETE FROM core.reference_types WHERE internal_code = 'TRIAGE_DECISION_LIFECYCLE_STATE'"
    )
