"""Ingestion freshness scheduler.

Periodically checks each in-scope repo's remote HEAD and, only when it changed,
enqueues an incremental ingestion job. The JobDispatcher (which has "ingestion"
registered) is the sole executor, so enqueue is exactly-once. See
docs/FRESHNESS_AND_MAINTENANCE_PLAN.md (Workstream A).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import asyncpg
import structlog

from memory_knowledge.config import Settings
from memory_knowledge.observability.metrics import repo_surface_age_seconds

logger = structlog.get_logger()

_TOOL = "run_repo_ingestion_workflow"

_ENUMERATE_SQL = """
    SELECT r.repository_key, r.origin_url, bh.branch_name, rr.commit_sha, bh.updated_utc
    FROM catalog.repositories r
    LEFT JOIN catalog.branch_heads bh ON bh.repository_id = r.id
    LEFT JOIN catalog.repo_revisions rr ON rr.id = bh.repo_revision_id
    WHERE r.origin_url IS NOT NULL
      AND r.repository_key NOT LIKE 'mawf%'
      AND r.repository_key NOT LIKE 'repo-%'
      AND r.repository_key NOT LIKE 'idx-%'
      AND (cardinality($1::text[]) = 0 OR r.repository_key = ANY($1::text[]))
    ORDER BY bh.updated_utc ASC NULLS FIRST
"""


def _parse_daily_at(value: str) -> time:
    raw = (value or "").strip()
    try:
        hour_s, minute_s = raw.split(":", 1)
        hour, minute = int(hour_s), int(minute_s)
    except ValueError as exc:
        raise ValueError("ingestion_scheduler_daily_at must use HH:MM format") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("ingestion_scheduler_daily_at must be a valid 24-hour HH:MM time")
    return time(hour=hour, minute=minute)


def next_daily_run_utc(daily_at: str, timezone_name: str, now_utc: datetime | None = None) -> datetime:
    """Return the next UTC instant for a local wall-clock daily scheduler."""
    target_time = _parse_daily_at(daily_at)
    tz = ZoneInfo(timezone_name or "UTC")
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local_now = now.astimezone(tz)
    local_target = datetime.combine(local_now.date(), target_time, tzinfo=tz)
    if local_target <= local_now:
        local_target += timedelta(days=1)
    return local_target.astimezone(timezone.utc)


class IngestionScheduler:
    """In-app periodic scheduler (managed start/stop, mirrors JobDispatcher/CodexTokenManager)."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        self._settings: Settings | None = None
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self, pool: asyncpg.Pool, settings: Settings) -> None:
        self._pool = pool
        self._settings = settings
        daily_at = getattr(settings, "ingestion_scheduler_daily_at", "") or ""
        timezone_name = getattr(settings, "ingestion_scheduler_timezone", "UTC") or "UTC"
        if daily_at:
            next_daily_run_utc(daily_at, timezone_name)
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "ingestion_scheduler_started",
            mode="daily" if daily_at else "interval",
            interval=settings.ingestion_scheduler_interval_seconds,
            daily_at=daily_at or None,
            timezone=timezone_name,
            max_per_tick=settings.ingestion_scheduler_max_per_tick,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ingestion_scheduler_stopped")

    async def _loop(self) -> None:
        daily_at = getattr(self._settings, "ingestion_scheduler_daily_at", "") or ""
        if daily_at:
            await self._daily_loop(daily_at)
            return
        interval = self._settings.ingestion_scheduler_interval_seconds
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception as exc:
                logger.error("ingestion_scheduler_tick_error", error=str(exc))
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass  # interval elapsed → next tick

    async def _daily_loop(self, daily_at: str) -> None:
        timezone_name = getattr(self._settings, "ingestion_scheduler_timezone", "UTC") or "UTC"
        while not self._stop_event.is_set():
            next_run = next_daily_run_utc(daily_at, timezone_name)
            delay = max((next_run - datetime.now(timezone.utc)).total_seconds(), 0.0)
            logger.info(
                "ingestion_scheduler_next_daily_tick",
                daily_at=daily_at,
                timezone=timezone_name,
                next_run_utc=next_run.isoformat(),
                delay_seconds=round(delay, 3),
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                continue
            except asyncio.TimeoutError:
                pass
            try:
                await self._tick()
            except Exception as exc:
                logger.error("ingestion_scheduler_tick_error", error=str(exc))

    async def _tick(self) -> None:
        s = self._settings
        allowlist = [x.strip() for x in s.ingestion_scheduler_repo_allowlist.split(",") if x.strip()]
        rows = await self._pool.fetch(_ENUMERATE_SQL, allowlist)
        now = datetime.now(timezone.utc)
        for row in rows:
            updated = row["updated_utc"]
            age = (now - updated).total_seconds() if updated is not None else -1.0
            repo_surface_age_seconds.labels(repository_key=row["repository_key"]).set(age)
        enqueued = 0
        for row in rows:
            if enqueued >= s.ingestion_scheduler_max_per_tick:
                break  # cap enqueues (the expensive part); stalest-first ordering → no starvation
            try:
                if await self._process_repo(row):
                    enqueued += 1
            except Exception as exc:
                logger.warning(
                    "ingestion_scheduler_repo_error",
                    repository_key=row["repository_key"],
                    error=str(exc),
                )
        logger.info("ingestion_scheduler_tick_complete", checked=len(rows), enqueued=enqueued)

    async def _process_repo(self, row: asyncpg.Record) -> bool:
        """Resolve the target commit, dedup, and enqueue. Returns True if a job was enqueued."""
        from memory_knowledge.git.clone import resolve_default_branch, resolve_remote_head
        from memory_knowledge.jobs.manifest_reader import (
            get_active_job_for_shape,
            get_latest_resume_checkpoint,
        )
        from memory_knowledge.jobs.manifest_writer import create_job

        pool, s = self._pool, self._settings
        rk = row["repository_key"]
        origin = row["origin_url"]
        branch = row["branch_name"]

        if branch is None:
            # Bootstrap: registered but never ingested → resolve the default branch (full ingest).
            resolved = await resolve_default_branch(origin, s)
            if resolved is None:
                logger.warning("scheduler_bootstrap_resolve_failed", repository_key=rk)
                return False
            branch, commit = resolved
        else:
            remote = await resolve_remote_head(origin, branch, s)
            if remote is None:
                logger.warning("scheduler_resolve_head_failed", repository_key=rk, branch=branch)
                return False
            if remote == row["commit_sha"]:
                logger.info("scheduler_skipped_unchanged", repository_key=rk, branch=branch)
                return False
            commit = remote

        active = await get_active_job_for_shape(
            pool, repository_key=rk, commit_sha=commit, branch_name=branch, tool_name=_TOOL
        )
        if active is not None:
            logger.info(
                "scheduler_skip_in_progress",
                repository_key=rk,
                commit_sha=commit,
                job_id=str(active["job_id"]),
            )
            return False

        resume = await get_latest_resume_checkpoint(
            pool, repository_key=rk, commit_sha=commit, branch_name=branch, tool_name=_TOOL
        )
        await create_job(
            pool,
            uuid.uuid4(),
            "ingestion",
            _TOOL,
            rk,
            commit,
            branch,
            job_params={"checkpoint": resume} if resume else None,
        )
        logger.info("ingestion_scheduled", repository_key=rk, branch=branch, commit_sha=commit)
        return True
