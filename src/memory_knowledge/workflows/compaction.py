"""Workflow adapter exposing integrity.compaction.compact_repository as a job/MCP tool.

Wraps the CompactionReport in a WorkflowResult so it runs through the job dispatcher
and the MCP tool surface like the other workflows. dry_run flows in via job_params.
"""

from __future__ import annotations

import uuid

import asyncpg
import neo4j
import structlog
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings
from memory_knowledge.integrity.compaction import compact_repository
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

TOOL_NAME = "run_compaction_workflow"


async def run(
    repository_key: str,
    run_id: uuid.UUID,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    settings: Settings | None = None,
    dry_run: bool = True,
) -> WorkflowResult:
    if pool is None or qdrant_client is None or settings is None:
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="error",
            error="Missing required dependencies (pool, qdrant_client, settings).",
        )
    report = await compact_repository(pool, qdrant_client, neo4j_driver, settings, repository_key, dry_run=dry_run)
    status = "error" if report.errors else "success"
    return WorkflowResult(
        run_id=str(run_id),
        tool_name=TOOL_NAME,
        status=status,
        data=report.model_dump(),
        error="; ".join(report.errors) if report.errors else None,
    )
