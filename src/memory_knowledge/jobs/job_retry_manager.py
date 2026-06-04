from __future__ import annotations

import uuid

import asyncpg
import structlog

from memory_knowledge.config import Settings

logger = structlog.get_logger()


async def retry_failed_jobs(
    pool: asyncpg.Pool, repository_key: str, settings: Settings
) -> list[uuid.UUID]:
    """Find failed jobs and mark them for retry. Returns list of re-queued job_ids."""
    rows = await pool.fetch(
        """
        SELECT job_id, attempt_number
        FROM ops.job_manifests
        WHERE repository_key = $1 AND state_code = 'failed'
          AND attempt_number < $2
        ORDER BY created_utc
        """,
        repository_key,
        settings.max_job_retries,
    )

    requeued: list[uuid.UUID] = []
    for row in rows:
        job_id = row["job_id"]
        new_attempt = row["attempt_number"] + 1
        await pool.execute(
            """
            UPDATE ops.job_manifests
            SET state_code = 'retrying', attempt_number = $2, completed_utc = NULL
            WHERE job_id = $1
            """,
            job_id,
            new_attempt,
        )
        requeued.append(job_id)
        logger.info(
            "job_requeued",
            job_id=str(job_id),
            attempt=new_attempt,
        )

    return requeued


async def sweep_failed_jobs(
    pool: asyncpg.Pool, settings: Settings
) -> tuple[int, int]:
    """Dead-letter exhausted failures and promote retryable ones to 'retrying'.

    Set-based, backoff-gated, repo-agnostic. Returns (retried, dead_lettered).
    Both transitions are valid in the state-transition guard
    (failed -> dead_letter, failed -> retrying). Promoting to 'retrying' makes
    the dispatcher re-claim the job on its next poll; bumping attempt_number
    each time bounds it at max_job_retries before dead-lettering.
    """
    dead = await pool.fetch(
        """
        UPDATE ops.job_manifests
        SET state_code = 'dead_letter', completed_utc = NOW()
        WHERE state_code = 'failed' AND attempt_number >= $1
        RETURNING job_id
        """,
        settings.max_job_retries,
    )
    retried = await pool.fetch(
        """
        UPDATE ops.job_manifests
        SET state_code = 'retrying',
            attempt_number = attempt_number + 1,
            completed_utc = NULL,
            error_code = NULL,
            error_text = NULL
        WHERE state_code = 'failed'
          AND attempt_number < $1
          AND (completed_utc IS NULL OR completed_utc < NOW() - ($2 * INTERVAL '1 second'))
        RETURNING job_id
        """,
        settings.max_job_retries,
        settings.job_retry_backoff_seconds,
    )
    if dead:
        logger.info("jobs_dead_lettered", count=len(dead))
    if retried:
        logger.info("jobs_retried", count=len(retried))
    return len(retried), len(dead)
