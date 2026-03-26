from __future__ import annotations

import uuid

import asyncpg
import structlog

logger = structlog.get_logger()


async def upsert_summary(
    pool: asyncpg.Pool,
    entity_key: uuid.UUID,
    parent_entity_id: int,
    summary_level: str,
    summary_text: str,
) -> int:
    """Upsert a summary with inline tsvector computation. Returns summary id."""
    # Ensure summary entity exists
    ent_row = await pool.fetchrow(
        """
        INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id)
        SELECT $1, 'summary', e.repository_id, e.repo_revision_id
        FROM catalog.entities e
        WHERE e.id = $2
        ON CONFLICT (entity_key) DO UPDATE
            SET repo_revision_id = EXCLUDED.repo_revision_id
        RETURNING id
        """,
        entity_key,
        parent_entity_id,
    )
    summary_entity_id = ent_row["id"]

    row = await pool.fetchrow(
        """
        INSERT INTO catalog.summaries
            (entity_id, summary_level, summary_text, summary_tsv)
        VALUES ($1, $2, $3, to_tsvector('english', $3))
        ON CONFLICT (entity_id, summary_level) DO UPDATE
            SET summary_text = EXCLUDED.summary_text,
                summary_tsv = to_tsvector('english', EXCLUDED.summary_text)
        RETURNING id
        """,
        summary_entity_id,
        summary_level,
        summary_text,
    )
    logger.info(
        "summary_upserted",
        entity_key=str(entity_key),
        summary_level=summary_level,
    )
    return row["id"]
