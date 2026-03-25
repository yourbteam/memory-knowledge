from __future__ import annotations

import time
import uuid

import structlog

from memory_knowledge.config import Settings
from memory_knowledge.llm.complete import llm_complete
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

TOOL_NAME = "run_blueprint_refinement_workflow"

SYSTEM_PROMPT = (
    "You are a technical editor. Refine the following artifact based on "
    "the provided findings. Preserve the existing structure. Fix only "
    "what the findings specify. Do not add new sections or remove "
    "existing ones unless explicitly requested."
)


async def run(
    repository_key: str,
    query: str,
    run_id: uuid.UUID,
    settings: Settings | None = None,
    **kwargs,
) -> WorkflowResult:
    start = time.monotonic()

    try:
        if settings is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name=TOOL_NAME,
                status="error",
                error="Missing required dependency: settings.",
            )

        refined_text = await llm_complete(
            prompt=query,
            settings=settings,
            system_prompt=SYSTEM_PROMPT,
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("blueprint_refinement_complete", duration_ms=duration_ms)

        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="success",
            data={"refined_text": refined_text},
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("blueprint_refinement_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id),
            tool_name=TOOL_NAME,
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
