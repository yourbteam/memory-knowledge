from __future__ import annotations

from typing import Any

import asyncpg
import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.llm.openai_client import embed

logger = structlog.get_logger()

BATCH_SIZE = 50


async def backfill_embeddings(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    settings: Settings,
    repository_key: str,
) -> dict[str, Any]:
    """Compare PG entities against Qdrant points and embed/upsert missing ones."""
    stats: dict[str, int] = {
        "chunks_checked": 0, "chunks_backfilled": 0,
        "summaries_checked": 0, "summaries_backfilled": 0,
        "learned_checked": 0, "learned_backfilled": 0,
    }

    await _backfill_collection(
        pool, qdrant_client, settings, repository_key,
        collection="code_chunks",
        text_query="""
            SELECT e.entity_key, c.content_text
            FROM catalog.chunks c
            JOIN catalog.entities e ON c.entity_id = e.id
            JOIN catalog.repositories r ON e.repository_id = r.id
            WHERE r.repository_key = $1
        """,
        stats_prefix="chunks", stats=stats,
    )

    await _backfill_collection(
        pool, qdrant_client, settings, repository_key,
        collection="summary_units",
        text_query="""
            SELECT e.entity_key, s.summary_text AS content_text
            FROM catalog.summaries s
            JOIN catalog.entities e ON s.entity_id = e.id
            JOIN catalog.repositories r ON e.repository_id = r.id
            WHERE r.repository_key = $1
        """,
        stats_prefix="summaries", stats=stats,
    )

    await _backfill_collection(
        pool, qdrant_client, settings, repository_key,
        collection="learned_memory",
        text_query="""
            SELECT e.entity_key, lr.body_text AS content_text
            FROM memory.learned_records lr
            JOIN catalog.entities e ON lr.entity_id = e.id
            JOIN catalog.repositories r ON e.repository_id = r.id
            WHERE r.repository_key = $1 AND lr.is_active = TRUE
              AND lr.verification_status = 'verified'
        """,
        stats_prefix="learned", stats=stats,
    )

    logger.info("backfill_complete", stats=stats)
    return stats


async def _backfill_collection(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    settings: Settings,
    repository_key: str,
    collection: str,
    text_query: str,
    stats_prefix: str,
    stats: dict[str, int],
) -> None:
    rows = await pool.fetch(text_query, repository_key)
    if not rows:
        return

    entity_keys = [str(r["entity_key"]) for r in rows]
    stats[f"{stats_prefix}_checked"] = len(entity_keys)

    # Check which exist in Qdrant (batched to avoid request size limits)
    found_ids: set[str] = set()
    try:
        for i in range(0, len(entity_keys), BATCH_SIZE):
            batch_ids = entity_keys[i : i + BATCH_SIZE]
            found = await qdrant_client.retrieve(
                collection_name=collection, ids=batch_ids,
            )
            found_ids.update(str(p.id) for p in found)
    except Exception:
        logger.warning("backfill_retrieve_failed", collection=collection)

    missing = [
        (str(r["entity_key"]), r["content_text"])
        for r in rows
        if str(r["entity_key"]) not in found_ids and r["content_text"]
    ]
    if not missing:
        return

    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i : i + BATCH_SIZE]
        texts = [text for _, text in batch]
        embeddings = await embed(texts, settings)
        points = [
            models.PointStruct(
                id=ek,
                vector=emb,
                payload={
                    "entity_key": ek,
                    "repository_key": repository_key,
                    "is_active": True,
                },
            )
            for (ek, _), emb in zip(batch, embeddings)
        ]
        await qdrant_client.upsert(collection_name=collection, points=points)

    stats[f"{stats_prefix}_backfilled"] = len(missing)
    logger.info(f"{stats_prefix}_backfill_complete", count=len(missing))
