from __future__ import annotations

import time
import uuid
from typing import Any

import asyncpg
import structlog

from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

TOOL_NAME = "run_route_intelligence_workflow"


async def run(
    repository_key: str,
    query: str,
    run_id: uuid.UUID,
    pool: asyncpg.Pool | None = None,
    **kwargs,
) -> WorkflowResult:
    start = time.monotonic()

    try:
        if pool is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=TOOL_NAME,
                status="error",
                error="Missing required dependency: pool.",
            )

        # Resolve repository
        row = await pool.fetchrow(
            "SELECT id FROM catalog.repositories WHERE repository_key = $1",
            repository_key,
        )
        if row is None:
            raise ValueError(f"Repository not found: {repository_key}")
        repository_id = row["id"]

        # Classify the query to determine prompt_class
        from memory_knowledge.workflows.retrieval import classify_prompt

        prompt_class = classify_prompt(query)

        # Query recent route executions
        recent_rows = await pool.fetch(
            """
            SELECT prompt_class, first_store_queried, fanout_used,
                   graph_expansion_used, result_count, duration_ms
            FROM routing.route_executions
            WHERE repository_id = $1 AND prompt_class = $2
            ORDER BY created_utc DESC
            LIMIT 50
            """,
            repository_id,
            prompt_class,
        )

        # Compute execution metrics
        total_execs = len(recent_rows)
        avg_result_count = 0.0
        avg_duration_ms = 0.0
        fanout_count = 0
        graph_expansion_count = 0

        if total_execs > 0:
            avg_result_count = sum(
                r["result_count"] or 0 for r in recent_rows
            ) / total_execs
            avg_duration_ms = sum(
                r["duration_ms"] or 0 for r in recent_rows
            ) / total_execs
            fanout_count = sum(1 for r in recent_rows if r["fanout_used"])
            graph_expansion_count = sum(
                1 for r in recent_rows if r["graph_expansion_used"]
            )

        # Query feedback metrics
        feedback_row = await pool.fetchrow(
            """
            SELECT AVG(rf.usefulness_score) AS avg_usefulness,
                   AVG(rf.precision_score) AS avg_precision,
                   COUNT(*) AS feedback_count
            FROM routing.route_feedback rf
            JOIN routing.route_executions re ON rf.route_execution_id = re.id
            WHERE re.repository_id = $1 AND re.prompt_class = $2
            """,
            repository_id,
            prompt_class,
        )

        duration_ms = int((time.monotonic() - start) * 1000)

        data: dict[str, Any] = {
            "prompt_class": prompt_class,
            "total_executions": total_execs,
            "avg_result_count": round(avg_result_count, 1),
            "avg_duration_ms": round(avg_duration_ms, 1),
            "route_patterns": {
                "fanout_rate": round(fanout_count / total_execs, 2) if total_execs else 0,
                "graph_expansion_rate": round(
                    graph_expansion_count / total_execs, 2
                ) if total_execs else 0,
            },
            "feedback": {
                "avg_usefulness": (
                    round(float(feedback_row["avg_usefulness"]), 2)
                    if feedback_row and feedback_row["avg_usefulness"]
                    else None
                ),
                "avg_precision": (
                    round(float(feedback_row["avg_precision"]), 2)
                    if feedback_row and feedback_row["avg_precision"]
                    else None
                ),
                "feedback_count": (
                    feedback_row["feedback_count"] if feedback_row else 0
                ),
            },
        }

        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="success",
            data=data,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("route_intelligence_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
