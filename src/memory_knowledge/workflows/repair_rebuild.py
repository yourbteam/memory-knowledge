from __future__ import annotations

import time
import uuid

import asyncpg
import neo4j
import structlog
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings
from memory_knowledge.integrity.repair_drift import repair
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

TOOL_NAME = "run_repair_rebuild_workflow"


async def run(
    repository_key: str,
    run_id: uuid.UUID,
    repair_scope: str = "full",
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    start = time.monotonic()

    try:
        if pool is None or qdrant_client is None or neo4j_driver is None or settings is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=TOOL_NAME,
                status="error",
                error="Missing required dependencies.",
            )

        if repair_scope not in ("full", "qdrant", "neo4j"):
            raise ValueError(
                f"Invalid repair_scope: {repair_scope}. Must be full, qdrant, or neo4j."
            )

        report = await repair(
            pool, qdrant_client, neo4j_driver, settings,
            repository_key, repair_scope,
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        status = "success" if not report.errors else "error"

        logger.info(
            "repair_complete",
            scope=repair_scope,
            qdrant=report.qdrant_points_repaired,
            neo4j=report.neo4j_nodes_repaired,
            errors=len(report.errors),
            duration_ms=duration_ms,
        )

        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status=status,
            data=report.model_dump(),
            error="; ".join(report.errors) if report.errors else None,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("repair_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
