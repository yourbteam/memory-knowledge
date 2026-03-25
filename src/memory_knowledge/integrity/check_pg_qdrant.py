from __future__ import annotations

import uuid

import asyncpg
import structlog
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient, models

logger = structlog.get_logger()

BATCH_SIZE = 100


class PgQdrantReport(BaseModel):
    total_pg_chunks: int = 0
    total_qdrant_points: int = 0
    missing_points: list[str] = []
    orphaned_points: list[str] = []


async def check_pg_qdrant(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    repository_key: str,
) -> PgQdrantReport:
    """Check alignment between PG chunk entities and Qdrant code_chunks points."""
    report = PgQdrantReport()

    # Forward check: PG chunks → Qdrant points
    offset = 0
    while True:
        rows = await pool.fetch(
            """
            SELECT e.entity_key
            FROM catalog.entities e
            JOIN catalog.repositories r ON e.repository_id = r.id
            WHERE r.repository_key = $1 AND e.entity_type = 'chunk'
            ORDER BY e.id
            LIMIT $2 OFFSET $3
            """,
            repository_key,
            BATCH_SIZE,
            offset,
        )
        if not rows:
            break

        report.total_pg_chunks += len(rows)
        keys = [str(r["entity_key"]) for r in rows]

        try:
            found = await qdrant_client.retrieve(
                collection_name="code_chunks",
                ids=keys,
            )
            found_ids = {str(p.id) for p in found}
            for key in keys:
                if key not in found_ids:
                    report.missing_points.append(key)
        except Exception as exc:
            logger.error("forward_check_failed", error=str(exc))

        offset += BATCH_SIZE

    # Reverse check: Qdrant points → PG entities (orphan detection)
    scroll_offset = None
    while True:
        results, next_offset = await qdrant_client.scroll(
            collection_name="code_chunks",
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="repository_key",
                        match=models.MatchValue(value=repository_key),
                    ),
                ]
            ),
            limit=BATCH_SIZE,
            offset=scroll_offset,
            with_payload=True,
        )

        report.total_qdrant_points += len(results)

        if results:
            point_entity_keys = []
            for p in results:
                ek = p.payload.get("entity_key") if p.payload else None
                if ek:
                    point_entity_keys.append(ek)

            if point_entity_keys:
                # Check which entity_keys exist in PG
                try:
                    valid_keys = []
                    for ek in point_entity_keys:
                        try:
                            uuid.UUID(ek)
                            valid_keys.append(ek)
                        except ValueError:
                            continue
                    if valid_keys:
                        pg_rows = await pool.fetch(
                            "SELECT entity_key FROM catalog.entities WHERE entity_key = ANY($1::uuid[])",
                            valid_keys,
                        )
                        pg_found = {str(r["entity_key"]) for r in pg_rows}
                        for ek in valid_keys:
                            if ek not in pg_found:
                                report.orphaned_points.append(ek)
                except Exception as exc:
                    logger.error("reverse_check_failed", error=str(exc))

        if next_offset is None:
            break
        scroll_offset = next_offset

    logger.info(
        "pg_qdrant_check_complete",
        pg_chunks=report.total_pg_chunks,
        qdrant_points=report.total_qdrant_points,
        missing=len(report.missing_points),
        orphaned=len(report.orphaned_points),
    )
    return report
