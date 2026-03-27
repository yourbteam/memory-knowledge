from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg
import structlog

from memory_knowledge.config import Settings
from memory_knowledge.jobs.job_worker import execute_job
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

JOB_TYPE_REGISTRY: dict[str, Callable[..., Awaitable[WorkflowResult]]] = {}


def register_job_type(
    job_type: str, workflow_fn: Callable[..., Awaitable[WorkflowResult]]
) -> None:
    """Register a workflow function for a given job type."""
    JOB_TYPE_REGISTRY[job_type] = workflow_fn


class JobDispatcher:
    """Async polling dispatcher for pending/retrying jobs."""

    def __init__(
        self,
        poll_interval: float = 15.0,
        max_concurrent: int = 3,
    ):
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running = False
        self._task: asyncio.Task | None = None
        self._pool: asyncpg.Pool | None = None
        self._settings: Settings | None = None
        self._dispatched: set[uuid.UUID] = set()  # prevent duplicate dispatch

    async def start(self, pool: asyncpg.Pool, settings: Settings) -> None:
        """Start the polling loop."""
        self._running = True
        self._pool = pool
        self._settings = settings
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("job_dispatcher_started", poll_interval=self.poll_interval)

    async def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("job_dispatcher_stopped")

    async def _poll_loop(self) -> None:
        """Poll for pending/retrying jobs and dispatch them."""
        while self._running:
            try:
                if self._pool is None:
                    break
                rows = await self._pool.fetch(
                    """
                    SELECT job_id, job_type, repository_key, commit_sha,
                           branch_name, checkpoint_data
                    FROM ops.job_manifests
                    WHERE state_code IN ('pending', 'retrying')
                    ORDER BY created_utc
                    LIMIT $1
                    """,
                    self.max_concurrent,
                )
                for row in rows:
                    job_id = row["job_id"]
                    if job_id in self._dispatched:
                        continue  # already dispatched, skip
                    job_type = row["job_type"]
                    workflow_fn = JOB_TYPE_REGISTRY.get(job_type)
                    if workflow_fn is None:
                        logger.warning("unknown_job_type", job_type=job_type)
                        continue
                    self._dispatched.add(job_id)
                    asyncio.create_task(self._dispatch_job(row, workflow_fn))
            except Exception as exc:
                logger.error("dispatcher_poll_error", error=str(exc))

            await asyncio.sleep(self.poll_interval)

    async def _dispatch_job(
        self, row: Any, workflow_fn: Callable[..., Awaitable[WorkflowResult]]
    ) -> None:
        """Dispatch a single job with concurrency limiting."""
        async with self._semaphore:
            job_id = row["job_id"]
            params: dict[str, Any] = {}
            if row["checkpoint_data"]:
                try:
                    cp = row["checkpoint_data"]
                    params = json.loads(cp) if isinstance(cp, str) else dict(cp)
                except (json.JSONDecodeError, TypeError):
                    pass

            from memory_knowledge.db.neo4j import get_neo4j_driver
            from memory_knowledge.db.qdrant import get_qdrant_client

            run_id = uuid.uuid4()
            kwargs: dict[str, Any] = {
                "repository_key": row["repository_key"],
                "run_id": run_id,
                "pool": self._pool,
                "qdrant_client": get_qdrant_client(),
                "neo4j_driver": get_neo4j_driver(),
                "settings": self._settings,
            }
            if row["commit_sha"]:
                kwargs["commit_sha"] = row["commit_sha"]
            if row["branch_name"]:
                kwargs["branch_name"] = row["branch_name"]
            kwargs.update(params)

            if self._pool is None or self._settings is None:
                return

            try:
                await execute_job(
                    manifest_pool=self._pool,
                    job_id=job_id,
                    job_fn=workflow_fn,
                    worker_settings=self._settings,
                    **kwargs,
                )
            finally:
                self._dispatched.discard(job_id)
