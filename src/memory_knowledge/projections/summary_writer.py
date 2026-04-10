from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger()
BATCH_SIZE = 100


def _column_arrays(rows: list[tuple[Any, ...]]) -> list[list[Any]]:
    if not rows:
        return []
    return [list(col) for col in zip(*rows)]


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


async def bulk_upsert_summaries(
    pool: asyncpg.Pool,
    rows: list[dict[str, Any]],
) -> None:
    """Batch upsert summary entities and summaries."""
    if not rows:
        return

    entity_rows = [
        (
            row["entity_key"],
            "summary",
            row["repository_id"],
            row["repo_revision_id"],
        )
        for row in rows
    ]
    entity_ids_by_key: dict[str, int] = {}
    for i in range(0, len(entity_rows), BATCH_SIZE):
        batch = entity_rows[i : i + BATCH_SIZE]
        arrays = _column_arrays(batch)
        results = await pool.fetch(
            """
            INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id)
            SELECT * FROM UNNEST($1::uuid[], $2::text[], $3::bigint[], $4::bigint[])
            ON CONFLICT (entity_key) DO UPDATE
                SET repo_revision_id = EXCLUDED.repo_revision_id
            RETURNING id, entity_key
            """,
            *arrays,
        )
        entity_ids_by_key.update({str(result["entity_key"]): result["id"] for result in results})

    summary_rows = [
        (
            entity_ids_by_key[str(row["entity_key"])],
            row["summary_level"],
            row["summary_text"],
        )
        for row in rows
    ]
    for i in range(0, len(summary_rows), BATCH_SIZE):
        batch = summary_rows[i : i + BATCH_SIZE]
        arrays = _column_arrays(batch)
        await pool.execute(
            """
            INSERT INTO catalog.summaries
                (entity_id, summary_level, summary_text, summary_tsv)
            SELECT entity_id, summary_level, summary_text, to_tsvector('english', summary_text)
            FROM UNNEST($1::bigint[], $2::text[], $3::text[])
                AS t(entity_id, summary_level, summary_text)
            ON CONFLICT (entity_id, summary_level) DO UPDATE
                SET summary_text = EXCLUDED.summary_text,
                    summary_tsv = to_tsvector('english', EXCLUDED.summary_text)
            """,
            *arrays,
        )
