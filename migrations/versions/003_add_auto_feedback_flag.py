"""Add is_auto flag to route_feedback

Revision ID: 003
Revises: 002
Create Date: 2026-04-01

Distinguishes auto-generated heuristic feedback from manual submissions.
The route_intelligence workflow reads both equally; the flag is for
observability and future weighting.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE routing.route_feedback
        ADD COLUMN is_auto BOOLEAN NOT NULL DEFAULT FALSE
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE routing.route_feedback
        DROP COLUMN is_auto
    """)
