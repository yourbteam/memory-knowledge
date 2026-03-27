from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from memory_knowledge.config import Settings
from memory_knowledge.jobs.manifest_writer import update_job_state
from memory_knowledge.observability.failure_classifier import classify_error
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()


async def execute_job(
    manifest_pool: asyncpg.Pool,
    job_id: uuid.UUID,
    job_fn: Callable[..., Awaitable[WorkflowResult]],
    worker_settings: Settings,
    **kwargs: Any,
) -> WorkflowResult:
    """Execute a job with manifest tracking and tenacity retry for transient errors.

    manifest_pool/worker_settings are for the job system's own use.
    **kwargs are forwarded directly to job_fn (the workflow function).
    """
    # Transition pending → running
    await update_job_state(manifest_pool, job_id, "running")

    try:
        # Inner retry for transient errors (connection timeouts, rate limits)
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(
                multiplier=worker_settings.job_retry_delay_seconds, min=1, max=60
            ),
            retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
            reraise=True,
        )
        async def _run_with_retry() -> WorkflowResult:
            return await job_fn(**kwargs)

        result = await _run_with_retry()

        # Store result in checkpoint_data for check_job_status retrieval
        result_json = result.model_dump_json()
        await update_job_state(
            manifest_pool, job_id, "completed",
            checkpoint_data=result_json,
        )
        return result

    except Exception as exc:
        error_code = classify_error(exc)
        await update_job_state(
            manifest_pool,
            job_id,
            "failed",
            error_code=error_code,
            error_text=str(exc)[:2000],
        )
        logger.error(
            "job_failed",
            job_id=str(job_id),
            error_code=error_code,
            error=str(exc),
        )
        return WorkflowResult(
            run_id=str(job_id),
            tool_name="job_worker",
            status="error",
            error=str(exc),
        )
