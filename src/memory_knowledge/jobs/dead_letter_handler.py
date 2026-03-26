from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

from memory_knowledge.config import Settings

logger = structlog.get_logger()


async def move_to_dead_letter(
    pool: asyncpg.Pool, job_id: uuid.UUID
) -> None:
    """Move a failed job to dead-letter state."""
    await pool.execute(
        """
        UPDATE ops.job_manifests
        SET state_code = 'dead_letter', completed_utc = NOW()
        WHERE job_id = $1 AND state_code = 'failed'
        """,
        job_id,
    )
    logger.info("job_dead_lettered", job_id=str(job_id))


async def list_dead_letters(
    pool: asyncpg.Pool, repository_key: str
) -> list[dict[str, Any]]:
    """List all dead-lettered jobs for a repository."""
    rows = await pool.fetch(
        """
        SELECT job_id, job_type, tool_name, error_code, error_text,
               attempt_number, created_utc
        FROM ops.job_manifests
        WHERE repository_key = $1 AND state_code = 'dead_letter'
        ORDER BY created_utc DESC
        """,
        repository_key,
    )
    return [dict(r) for r in rows]


async def requeue_dead_letter(
    pool: asyncpg.Pool, job_id: uuid.UUID
) -> None:
    """Admin reset: move dead-lettered job back to pending for manual retry."""
    # Intentionally bypasses state_transition_guard — this is an admin override
    await pool.execute(
        """
        UPDATE ops.job_manifests
        SET state_code = 'pending', attempt_number = 1,
            completed_utc = NULL, error_code = NULL, error_text = NULL
        WHERE job_id = $1 AND state_code = 'dead_letter'
        """,
        job_id,
    )
    logger.info("dead_letter_requeued", job_id=str(job_id))
