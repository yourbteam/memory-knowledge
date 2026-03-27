from __future__ import annotations

import asyncio
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

    _TIMEOUT = 5.0  # seconds per store check

    # PostgreSQL
    try:
        pool = get_pg_pool()
        val = await asyncio.wait_for(pool.fetchval("SELECT 1"), timeout=_TIMEOUT)
        results["postgres"] = "ok" if val == 1 else "error"
    except Exception as exc:
        results["postgres"] = f"error: {exc}"
        results["status"] = "not_ready"

    # Qdrant
    try:
        client = get_qdrant_client()
        await asyncio.wait_for(client.get_collections(), timeout=_TIMEOUT)
        results["qdrant"] = "ok"
    except Exception as exc:
        results["qdrant"] = f"error: {exc}"
        results["status"] = "not_ready"

    # Neo4j
    try:
        driver = get_neo4j_driver()
        await asyncio.wait_for(driver.verify_connectivity(), timeout=_TIMEOUT)
        results["neo4j"] = "ok"
    except Exception as exc:
        results["neo4j"] = f"error: {exc}"
        results["status"] = "not_ready"

    return results
