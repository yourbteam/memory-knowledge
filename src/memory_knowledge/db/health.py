from __future__ import annotations

import asyncio
from typing import Any

import structlog

from memory_knowledge.db.postgres import get_pg_pool
from memory_knowledge.db.qdrant import get_qdrant_client
from memory_knowledge.db.neo4j import get_neo4j_driver

logger = structlog.get_logger()


def _format_dependency_error(exc: Exception) -> str:
    error_type = exc.__class__.__name__
    message = str(exc).strip()
    if message:
        return f"error: {error_type}: {message}"
    return f"error: {error_type}: {repr(exc)}"


async def health_check() -> dict[str, str]:
    return {"status": "ok"}


async def readiness_check() -> dict[str, Any]:
    results: dict[str, Any] = {"status": "ready", "degraded": []}

    _TIMEOUT = 5.0  # seconds per store check

    # PostgreSQL
    try:
        pool = get_pg_pool()
        val = await asyncio.wait_for(pool.fetchval("SELECT 1"), timeout=_TIMEOUT)
        results["postgres"] = "ok" if val == 1 else "error"
    except Exception as exc:
        logger.warning("readiness_postgres_failed", error=_format_dependency_error(exc))
        results["postgres"] = _format_dependency_error(exc)
        results["status"] = "not_ready"

    # Qdrant
    try:
        client = get_qdrant_client()
        await asyncio.wait_for(client.get_collections(), timeout=_TIMEOUT)
        results["qdrant"] = "ok"
    except Exception as exc:
        logger.warning("readiness_qdrant_failed", error=_format_dependency_error(exc))
        results["qdrant"] = _format_dependency_error(exc)
        results["status"] = "not_ready"

    # Neo4j
    try:
        driver = get_neo4j_driver()
        await asyncio.wait_for(driver.verify_connectivity(), timeout=_TIMEOUT)
        results["neo4j"] = "ok"
    except Exception as exc:
        logger.warning("readiness_neo4j_failed", error=_format_dependency_error(exc))
        results["neo4j"] = f"degraded: {_format_dependency_error(exc)}"
        results["degraded"].append("neo4j")

    return results
