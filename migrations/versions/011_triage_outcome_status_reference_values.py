"""Normalize triage outcome statuses through reference values

Revision ID: 011_triage_outcome_status_reference_values
Revises: 010_triage_memory
Create Date: 2026-04-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "011_triage_outcome_status_reference_values"
down_revision: Union[str, None] = "010_triage_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO core.reference_types (internal_code, name, description)
        VALUES (
            'TRIAGE_OUTCOME_STATUS',
            'Triage Outcome Status',
            'Canonical triage feedback outcomes for normalized triage-memory analytics'
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
                ('TRIAGE_OUTCOME_PENDING', 'Pending', 10, FALSE),
                ('TRIAGE_OUTCOME_CONFIRMED_CORRECT', 'Confirmed Correct', 20, TRUE),
                ('TRIAGE_OUTCOME_EXECUTION_FAILED_AFTER_ROUTE', 'Execution Failed After Route', 30, TRUE),
                ('TRIAGE_OUTCOME_INSUFFICIENT_CONTEXT', 'Insufficient Context', 40, TRUE),
                ('TRIAGE_OUTCOME_CORRECTED', 'Corrected', 50, TRUE),
                ('TRIAGE_OUTCOME_OVERRIDDEN_BY_HUMAN', 'Overridden By Human', 60, TRUE)
        ) AS v(internal_code, display_name, sort_order, is_terminal)
          ON rt.internal_code = 'TRIAGE_OUTCOME_STATUS'
        ON CONFLICT (internal_code) DO NOTHING
        """
    )

    op.execute(
        """
        ALTER TABLE ops.triage_case_feedback
        ADD COLUMN IF NOT EXISTS status_id BIGINT REFERENCES core.reference_values(id)
        """
    )

    op.execute(
        """
        UPDATE ops.triage_case_feedback fb
        SET status_id = rv.id
        FROM core.reference_values rv
        JOIN core.reference_types rt ON rt.id = rv.reference_type_id
        WHERE rt.internal_code = 'TRIAGE_OUTCOME_STATUS'
          AND rv.internal_code = CASE lower(btrim(fb.outcome_status))
              WHEN 'pending' THEN 'TRIAGE_OUTCOME_PENDING'
              WHEN 'confirmed_correct' THEN 'TRIAGE_OUTCOME_CONFIRMED_CORRECT'
              WHEN 'execution_failed_after_route' THEN 'TRIAGE_OUTCOME_EXECUTION_FAILED_AFTER_ROUTE'
              WHEN 'insufficient_context' THEN 'TRIAGE_OUTCOME_INSUFFICIENT_CONTEXT'
              WHEN 'corrected' THEN 'TRIAGE_OUTCOME_CORRECTED'
              WHEN 'overridden_by_human' THEN 'TRIAGE_OUTCOME_OVERRIDDEN_BY_HUMAN'
              ELSE NULL
          END
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_triage_case_feedback_status_id
        ON ops.triage_case_feedback(status_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_triage_case_feedback_status_id")
    op.execute(
        "ALTER TABLE ops.triage_case_feedback DROP COLUMN IF EXISTS status_id"
    )
    op.execute(
        """
        DELETE FROM core.reference_values
        WHERE reference_type_id = (
            SELECT id FROM core.reference_types
            WHERE internal_code = 'TRIAGE_OUTCOME_STATUS'
        )
        """
    )
    op.execute(
        "DELETE FROM core.reference_types WHERE internal_code = 'TRIAGE_OUTCOME_STATUS'"
    )
