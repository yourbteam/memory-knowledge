from __future__ import annotations

from typing import Any

import asyncpg
import neo4j
import structlog
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient

logger = structlog.get_logger()

BATCH_SIZE = 100


class EntityCheckReport(BaseModel):
    total_entities: int = 0
    missing_in_qdrant: list[str] = []
    missing_in_neo4j: list[str] = []


async def check_entities(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient,
    neo4j_driver: neo4j.AsyncDriver,
    repository_key: str,
) -> EntityCheckReport:
    """Check that all PG entities have corresponding Qdrant points or Neo4j nodes."""
    report = EntityCheckReport()
    offset = 0

    while True:
        rows = await pool.fetch(
            """
            SELECT e.entity_key, e.entity_type
            FROM catalog.entities e
            JOIN catalog.repositories r ON e.repository_id = r.id
            WHERE r.repository_key = $1
            ORDER BY e.id
            LIMIT $2 OFFSET $3
            """,
            repository_key,
            BATCH_SIZE,
            offset,
        )
        if not rows:
            break

        report.total_entities += len(rows)

        # Group by entity type
        chunk_keys = [str(r["entity_key"]) for r in rows if r["entity_type"] == "chunk"]
        file_keys = [str(r["entity_key"]) for r in rows if r["entity_type"] == "file"]
        symbol_keys = [str(r["entity_key"]) for r in rows if r["entity_type"] == "symbol"]

        # Check chunks in Qdrant
        if chunk_keys:
            try:
                found = await qdrant_client.retrieve(
                    collection_name="code_chunks",
                    ids=chunk_keys,
                )
                found_ids = {str(p.id) for p in found}
                for key in chunk_keys:
                    if key not in found_ids:
                        report.missing_in_qdrant.append(key)
            except Exception as exc:
                logger.error("qdrant_check_failed", error=str(exc))

        # Check files in Neo4j
        if file_keys:
            try:
                records, _, _ = await neo4j_driver.execute_query(
                    "UNWIND $keys AS k MATCH (n:File {entity_key: k}) RETURN n.entity_key AS ek",
                    keys=file_keys,
                )
                found_keys = {r["ek"] for r in records}
                for key in file_keys:
                    if key not in found_keys:
                        report.missing_in_neo4j.append(key)
            except Exception as exc:
                logger.error("neo4j_file_check_failed", error=str(exc))

        # Check symbols in Neo4j
        if symbol_keys:
            try:
                records, _, _ = await neo4j_driver.execute_query(
                    "UNWIND $keys AS k MATCH (n:Symbol {entity_key: k}) RETURN n.entity_key AS ek",
                    keys=symbol_keys,
                )
                found_keys = {r["ek"] for r in records}
                for key in symbol_keys:
                    if key not in found_keys:
                        report.missing_in_neo4j.append(key)
            except Exception as exc:
                logger.error("neo4j_symbol_check_failed", error=str(exc))

        offset += BATCH_SIZE

    logger.info(
        "entity_check_complete",
        total=report.total_entities,
        missing_qdrant=len(report.missing_in_qdrant),
        missing_neo4j=len(report.missing_in_neo4j),
    )
    return report
