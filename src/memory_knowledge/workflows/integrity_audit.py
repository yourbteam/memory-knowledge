from __future__ import annotations

import time
import uuid
from typing import Any

import asyncpg
import neo4j
import structlog
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings
from memory_knowledge.integrity.check_entities import check_entities
from memory_knowledge.integrity.check_pg_neo4j import check_pg_neo4j
from memory_knowledge.integrity.check_pg_qdrant import check_pg_qdrant
from memory_knowledge.integrity.freshness_audit import check_freshness
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

TOOL_NAME = "run_integrity_audit_workflow"


async def run(
    repository_key: str,
    run_id: uuid.UUID,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    start = time.monotonic()

    try:
        if pool is None or qdrant_client is None or neo4j_driver is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=TOOL_NAME,
                status="error",
                error="Missing required dependencies.",
            )

        data: dict[str, Any] = {"repository_key": repository_key}

        # Run each check independently — failures don't abort the audit
        try:
            entity_report = await check_entities(
                pool, qdrant_client, neo4j_driver, repository_key
            )
            data["entity_check"] = entity_report.model_dump()
        except Exception as exc:
            data["entity_check"] = {"error": str(exc)}
            logger.error("entity_check_failed", error=str(exc))

        try:
            pg_qdrant_report = await check_pg_qdrant(pool, qdrant_client, repository_key)
            data["pg_qdrant_check"] = pg_qdrant_report.model_dump()
        except Exception as exc:
            data["pg_qdrant_check"] = {"error": str(exc)}
            logger.error("pg_qdrant_check_failed", error=str(exc))

        try:
            pg_neo4j_report = await check_pg_neo4j(pool, neo4j_driver, repository_key)
            data["pg_neo4j_check"] = pg_neo4j_report.model_dump()
        except Exception as exc:
            data["pg_neo4j_check"] = {"error": str(exc)}
            logger.error("pg_neo4j_check_failed", error=str(exc))

        try:
            freshness_report = await check_freshness(pool, qdrant_client, repository_key)
            data["freshness_check"] = freshness_report.model_dump()
        except Exception as exc:
            data["freshness_check"] = {"error": str(exc)}
            logger.error("freshness_check_failed", error=str(exc))

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("integrity_audit_complete", duration_ms=duration_ms)

        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="success",
            data=data,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("integrity_audit_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
