from __future__ import annotations

from typing import Any

import structlog

from memory_knowledge.db.postgres import get_pg_pool
from memory_knowledge.db.qdrant import get_qdrant_client
from memory_knowledge.db.neo4j import get_neo4j_driver

logger = structlog.get_logger()


async def health_check() -> dict[str, str]:
    return {"status": "ok"}


async def readiness_check() -> dict[str, Any]:
    results: dict[str, Any] = {"status": "ready"}

    # PostgreSQL
    try:
        pool = get_pg_pool()
        val = await pool.fetchval("SELECT 1")
        results["postgres"] = "ok" if val == 1 else "error"
    except Exception as exc:
        results["postgres"] = f"error: {exc}"
        results["status"] = "not_ready"

    # Qdrant
    try:
        client = get_qdrant_client()
        await client.get_collections()
        results["qdrant"] = "ok"
    except Exception as exc:
        results["qdrant"] = f"error: {exc}"
        results["status"] = "not_ready"

    # Neo4j
    try:
        driver = get_neo4j_driver()
        await driver.verify_connectivity()
        results["neo4j"] = "ok"
    except Exception as exc:
        results["neo4j"] = f"error: {exc}"
        results["status"] = "not_ready"

    return results
