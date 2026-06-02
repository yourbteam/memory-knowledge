from __future__ import annotations

import time
import uuid

import asyncpg
import structlog
from qdrant_client import AsyncQdrantClient, models

from memory_knowledge.config import Settings
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

TOOL_NAME = "run_backfill_is_active_workflow"
BATCH_SIZE = 256

_UPDATE_CHUNKS_SQL = """
    UPDATE catalog.chunks t SET is_active = FALSE
    FROM catalog.entities e
    WHERE t.entity_id = e.id AND e.entity_key = ANY($1::uuid[]) AND t.is_active = TRUE
"""
_UPDATE_SUMMARIES_SQL = """
    UPDATE catalog.summaries t SET is_active = FALSE
    FROM catalog.entities e
    WHERE t.entity_id = e.id AND e.entity_key = ANY($1::uuid[]) AND t.is_active = TRUE
"""


async def _deactivate_pg_rows(
    pool: asyncpg.Pool, sql: str, point_ids: list[str]
) -> int:
    valid = []
    for pid in point_ids:
        try:
            uuid.UUID(pid)
            valid.append(pid)
        except (ValueError, TypeError):
            continue
    if not valid:
        return 0
    status = await pool.execute(sql, valid)  # e.g. "UPDATE 5"
    try:
        return int(status.split()[-1])
    except (ValueError, IndexError):
        return 0


async def run(
    repository_key: str,
    run_id: uuid.UUID,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    """Mirror Qdrant is_active=False into catalog.chunks/summaries (one-time reconcile)."""
    start = time.monotonic()
    try:
        if pool is None or qdrant_client is None:
            return WorkflowResult(
                run_id=str(run_id), tool_name=TOOL_NAME, status="error",
                error="Missing required dependencies (pool, qdrant_client).",
            )

        counts: dict[str, dict[str, int]] = {}
        for collection, sql in (
            ("code_chunks", _UPDATE_CHUNKS_SQL),
            ("summary_units", _UPDATE_SUMMARIES_SQL),
        ):
            scanned = 0
            deactivated = 0
            scroll_offset = None
            while True:
                results, next_offset = await qdrant_client.scroll(
                    collection_name=collection,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="repository_key",
                                match=models.MatchValue(value=repository_key),
                            ),
                            models.FieldCondition(
                                key="is_active",
                                match=models.MatchValue(value=False),
                            ),
                        ]
                    ),
                    limit=BATCH_SIZE,
                    offset=scroll_offset,
                    with_payload=False,
                )
                if results:
                    scanned += len(results)
                    deactivated += await _deactivate_pg_rows(
                        pool, sql, [str(p.id) for p in results]
                    )
                if next_offset is None:
                    break
                scroll_offset = next_offset

            counts[collection] = {
                "inactive_points_scanned": scanned,
                "pg_rows_deactivated": deactivated,
            }
            logger.info(
                "backfill_is_active_collection_done",
                collection=collection, **counts[collection],
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("backfill_is_active_complete", duration_ms=duration_ms)
        return WorkflowResult(
            run_id=str(run_id), tool_name=TOOL_NAME, status="success",
            data={
                "repository_key": repository_key,
                "counts": counts,
                "note": "PG rows with no matching inactive Qdrant point are left active.",
            },
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("backfill_is_active_failed", error=str(exc), duration_ms=duration_ms)
        return WorkflowResult(
            run_id=str(run_id), tool_name=TOOL_NAME, status="error",
            error=str(exc), duration_ms=duration_ms,
        )
