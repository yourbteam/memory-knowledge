"""T1: failed jobs self-heal via the retry/dead-letter sweep instead of being terminal."""

import asyncio

import pytest

from memory_knowledge.jobs import dispatcher as disp_mod
from memory_knowledge.jobs.dispatcher import JobDispatcher
from memory_knowledge.jobs.job_retry_manager import sweep_failed_jobs


class _SweepPool:
    def __init__(self, dead_rows: int, retry_rows: int):
        self.dead_rows = dead_rows
        self.retry_rows = retry_rows
        self.calls: list[tuple[str, tuple]] = []

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        if "dead_letter" in query:
            return [{"job_id": i} for i in range(self.dead_rows)]
        if "retrying" in query:
            return [{"job_id": i} for i in range(self.retry_rows)]
        return []


_SETTINGS = type("S", (), {"max_job_retries": 3, "job_retry_backoff_seconds": 60.0})()


@pytest.mark.asyncio
async def test_sweep_returns_counts_and_issues_both_updates():
    pool = _SweepPool(dead_rows=2, retry_rows=3)
    retried, dead = await sweep_failed_jobs(pool, _SETTINGS)
    assert (retried, dead) == (3, 2)
    queries = [q for q, _ in pool.calls]
    assert any("dead_letter" in q for q in queries)
    assert any("retrying" in q for q in queries)
    # retry update is parameterised by (max_job_retries, backoff_seconds)
    retry_args = [a for q, a in pool.calls if "retrying" in q][0]
    assert retry_args == (3, 60.0)
    # dead-letter update is parameterised by max_job_retries
    dead_args = [a for q, a in pool.calls if "dead_letter" in q][0]
    assert dead_args == (3,)


class _IdlePool:
    async def fetch(self, *args, **kwargs):
        return []  # nothing to claim

    async def execute(self, *args, **kwargs):
        return "UPDATE 0"


async def _run_dispatcher_once(monkeypatch, enabled: bool) -> int:
    calls = {"n": 0}

    async def fake_sweep(pool, settings):
        calls["n"] += 1
        return 0, 0

    monkeypatch.setattr(disp_mod, "sweep_failed_jobs", fake_sweep)
    d = JobDispatcher(poll_interval=0.01, max_concurrent=1)
    settings = type(
        "S",
        (),
        {
            "job_retry_sweep_enabled": enabled,
            "reclaim_stale_running_jobs_on_start": False,
        },
    )()
    await d.start(_IdlePool(), settings)
    await asyncio.sleep(0.06)
    await d.stop()
    return calls["n"]


@pytest.mark.asyncio
async def test_dispatcher_runs_sweep_when_enabled(monkeypatch):
    assert await _run_dispatcher_once(monkeypatch, enabled=True) >= 1


@pytest.mark.asyncio
async def test_dispatcher_skips_sweep_when_disabled(monkeypatch):
    assert await _run_dispatcher_once(monkeypatch, enabled=False) == 0
