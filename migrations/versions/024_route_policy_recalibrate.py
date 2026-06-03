"""Recalibrate route_policies confidence thresholds for bge-base; drop dead columns.

Revision ID: 024_route_policy_recalibrate
Revises: 023_chunk_summary_is_active
Create Date: 2026-06-03

The seeded confidence thresholds (0.40-0.80) were calibrated for
text-embedding-3-small cosine scores. bge-base scores are compressed into a
~0.45 (noise) .. ~0.71 (strong match) band, so the thresholds are remapped into
that band. Also drops three route_policies columns that retrieval never reads
(third_store, fusion_strategy, rerank_strategy).
"""
from alembic import op

revision = "024_route_policy_recalibrate"
down_revision = "023_chunk_summary_is_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE routing.route_policies SET confidence_threshold = CASE prompt_class
            WHEN 'exact_lookup'      THEN 0.55
            WHEN 'impact_analysis'   THEN 0.52
            WHEN 'conceptual_lookup' THEN 0.50
            WHEN 'pattern_search'    THEN 0.50
            WHEN 'decision_history'  THEN 0.50
            WHEN 'mixed'             THEN 0.48
            ELSE confidence_threshold
        END
        """
    )
    op.execute("ALTER TABLE routing.route_policies DROP COLUMN IF EXISTS third_store")
    op.execute("ALTER TABLE routing.route_policies DROP COLUMN IF EXISTS fusion_strategy")
    op.execute("ALTER TABLE routing.route_policies DROP COLUMN IF EXISTS rerank_strategy")


def downgrade() -> None:
    op.execute("ALTER TABLE routing.route_policies ADD COLUMN IF NOT EXISTS third_store VARCHAR(50)")
    op.execute("ALTER TABLE routing.route_policies ADD COLUMN IF NOT EXISTS fusion_strategy VARCHAR(50)")
    op.execute("ALTER TABLE routing.route_policies ADD COLUMN IF NOT EXISTS rerank_strategy VARCHAR(50)")
    op.execute(
        """
        UPDATE routing.route_policies SET confidence_threshold = CASE prompt_class
            WHEN 'exact_lookup'      THEN 0.80
            WHEN 'impact_analysis'   THEN 0.60
            WHEN 'conceptual_lookup' THEN 0.50
            WHEN 'pattern_search'    THEN 0.50
            WHEN 'decision_history'  THEN 0.50
            WHEN 'mixed'             THEN 0.40
            ELSE confidence_threshold
        END
        """
    )
