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
