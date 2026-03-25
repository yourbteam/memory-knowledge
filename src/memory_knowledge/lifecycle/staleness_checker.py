from __future__ import annotations

from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger()


async def check_staleness(
    pool: asyncpg.Pool,
    repository_id: int,
    current_revision_id: int,
) -> list[dict[str, Any]]:
    """Find active learned records whose valid_to_revision_id is before the current revision."""
    rows = await pool.fetch(
        """
        SELECT lr.id, lr.entity_id, e.entity_key, lr.title,
               lr.valid_from_revision_id, lr.valid_to_revision_id
        FROM memory.learned_records lr
        JOIN catalog.entities e ON lr.entity_id = e.id
        WHERE e.repository_id = $1
          AND lr.is_active = TRUE
          AND lr.valid_to_revision_id IS NOT NULL
          AND lr.valid_to_revision_id < $2
        """,
        repository_id,
        current_revision_id,
    )
    stale = [dict(r) for r in rows]
    if stale:
        logger.info("stale_records_found", count=len(stale))
    return stale


async def mark_stale(
    pool: asyncpg.Pool,
    learned_record_ids: list[int],
) -> int:
    """Deactivate stale learned records. Returns count deactivated."""
    if not learned_record_ids:
        return 0
    result = await pool.execute(
        "UPDATE memory.learned_records SET is_active = FALSE WHERE id = ANY($1::bigint[])",
        learned_record_ids,
    )
    count = int(result.split()[-1]) if result else 0
    logger.info("stale_records_marked", count=count)
    return count
