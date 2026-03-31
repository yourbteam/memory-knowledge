"""Enable fanout for conceptual_lookup route policy

Revision ID: 002
Revises: 001
Create Date: 2026-03-31

Existing databases have allow_fanout=FALSE for conceptual_lookup, which
prevents PG full-text search from supplementing poor Qdrant results.
This migration enables fanout so config files and exact-match content
can be found via PG when semantic search returns sparse results.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE routing.route_policies
        SET allow_fanout = TRUE
        WHERE prompt_class = 'conceptual_lookup'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE routing.route_policies
        SET allow_fanout = FALSE
        WHERE prompt_class = 'conceptual_lookup'
    """)
