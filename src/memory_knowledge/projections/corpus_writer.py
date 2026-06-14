from __future__ import annotations

import json
import uuid

import asyncpg
import structlog

logger = structlog.get_logger()


async def upsert_corpus_entry(
    pool: asyncpg.Pool,
    *,
    entry_key: uuid.UUID,
    kind: str,
    title: str,
    body_text: str,
    tags: list[str] | None = None,
    link_slug: str | None = None,
    confidence: float | None = None,
    is_active: bool = True,
    supersedes_key: uuid.UUID | None = None,
) -> int:
    """Upsert a Tier-2 corpus entry into memory.corpus_entries. Returns the row id.

    Keyed on entry_key (deterministic), so re-writing the same logical entry updates in place.
    PG is the source of truth; the Qdrant projection is written separately.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO memory.corpus_entries
            (entry_key, kind, title, body_text, tags, link_slug, confidence,
             is_active, supersedes_key)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9)
        ON CONFLICT (entry_key) DO UPDATE
            SET kind = EXCLUDED.kind,
                title = EXCLUDED.title,
                body_text = EXCLUDED.body_text,
                tags = EXCLUDED.tags,
                link_slug = EXCLUDED.link_slug,
                confidence = EXCLUDED.confidence,
                is_active = EXCLUDED.is_active,
                supersedes_key = EXCLUDED.supersedes_key,
                updated_utc = NOW()
        RETURNING id
        """,
        entry_key,
        kind,
        title,
        body_text,
        json.dumps(tags if tags is not None else []),
        link_slug,
        confidence,
        is_active,
        supersedes_key,
    )
    logger.info("corpus_entry_upserted", entry_key=str(entry_key), kind=kind, is_active=is_active)
    return row["id"]


async def deactivate_corpus_entry(pool: asyncpg.Pool, entry_key: uuid.UUID) -> bool:
    """Soft-delete: set is_active=FALSE on a corpus entry. Returns True if a row existed."""
    status = await pool.execute(
        "UPDATE memory.corpus_entries SET is_active = FALSE, updated_utc = NOW() WHERE entry_key = $1",
        entry_key,
    )
    try:
        affected = int(str(status).split()[-1])
    except (ValueError, IndexError, AttributeError):
        affected = 0
    logger.info("corpus_entry_deactivated", entry_key=str(entry_key), affected=affected)
    return affected > 0


async def supersede_corpus_entry(pool: asyncpg.Pool, old_entry_key: uuid.UUID) -> None:
    """Deactivate the superseded entry. The new entry records the link via its supersedes_key."""
    await deactivate_corpus_entry(pool, old_entry_key)
    logger.info("corpus_entry_superseded", old_entry_key=str(old_entry_key))
