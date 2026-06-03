"""Maintenance scheduler — periodically enqueues integrity-audit + compaction jobs
for the real repos, bounded by the JobDispatcher's concurrency. See
docs/FRESHNESS_AND_MAINTENANCE_PLAN.md (Workstream B.2).
"""
from __future__ import annotations

import asyncio
import uuid

import asyncpg
import structlog

from memory_knowledge.config import Settings

logger = structlog.get_logger()

# Real (non-test) repos. Maintenance operates on stored data, so origin_url is not required.
_REAL_REPOS_SQL = """
    SELECT repository_key FROM catalog.repositories
    WHERE repository_key NOT LIKE 'mawf%'
      AND repository_key NOT LIKE 'repo-%'
      AND repository_key NOT LIKE 'idx-%'
    ORDER BY repository_key
"""

_ACTIVE_BY_TOOL_SQL = """
    SELECT job_id FROM ops.job_manifests
    WHERE repository_key = $1 AND tool_name = $2 AND state_code IN ('pending', 'running')
    LIMIT 1
"""


class MaintenanceScheduler:
    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        self._settings: Settings | None = None
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self, pool: asyncpg.Pool, settings: Settings) -> None:
        self._pool = pool
        self._settings = settings
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("maintenance_scheduler_started", interval=settings.maintenance_interval_seconds)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("maintenance_scheduler_stopped")

    async def _loop(self) -> None:
        interval = self._settings.maintenance_interval_seconds
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception as exc:
                logger.error("maintenance_scheduler_tick_error", error=str(exc))
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        dry_run = not self._settings.compaction_enabled
        rows = await self._pool.fetch(_REAL_REPOS_SQL)
        enq = 0
        for row in rows:
            rk = row["repository_key"]
            try:
                enq += await self._enqueue_if_absent(rk, "integrity_audit", "run_integrity_audit_workflow", None)
                enq += await self._enqueue_if_absent(rk, "compaction", "run_compaction_workflow", {"dry_run": dry_run})
            except Exception as exc:
                logger.warning("maintenance_scheduler_repo_error", repository_key=rk, error=str(exc))
        logger.info("maintenance_scheduler_tick_complete", repos=len(rows), enqueued=enq, compaction_dry_run=dry_run)

    async def _enqueue_if_absent(self, rk: str, job_type: str, tool: str, job_params: dict | None) -> int:
        from memory_knowledge.jobs.manifest_writer import create_job

        existing = await self._pool.fetchval(_ACTIVE_BY_TOOL_SQL, rk, tool)
        if existing is not None:
            logger.info("maintenance_skip_active", repository_key=rk, tool=tool, job_id=str(existing))
            return 0
        await create_job(self._pool, uuid.uuid4(), job_type, tool, rk, job_params=job_params)
        logger.info("maintenance_enqueued", repository_key=rk, tool=tool)
        return 1
