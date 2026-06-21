"""Dispatcher startup reclaim of orphaned 'running' jobs + serialized concurrency.

Regression: when a container is killed mid-job (e.g. OOM under load on the
shared B3), the job is left in 'running' forever — the poll loop only claims
'pending'/'retrying'. On (single-instance) startup nothing is legitimately
running, so the dispatcher resets stale 'running' rows to 'failed'.
"""

import pytest

from memory_knowledge.jobs.dispatcher import JobDispatcher


class _RecordingPool:
    def __init__(self):
        self.executed: list[str] = []

    async def execute(self, query, *args):
        self.executed.append(query)
        return "UPDATE 3"

    async def fetch(self, *args, **kwargs):
        return []  # keep the poll loop harmless


@pytest.mark.asyncio
async def test_reclaim_marks_running_jobs_failed():
    d = JobDispatcher(poll_interval=15.0, max_concurrent=1)
    pool = _RecordingPool()
    d._pool = pool

    await d._reclaim_stale_running()

    assert any("state_code = 'failed'" in q and "WHERE state_code = 'running'" in q for q in pool.executed), (
        pool.executed
    )


@pytest.mark.asyncio
async def test_start_runs_reclaim_when_enabled():
    d = JobDispatcher(poll_interval=0.01, max_concurrent=1)
    settings = type("S", (), {"reclaim_stale_running_jobs_on_start": True})()
    calls = {"n": 0}

    async def fake_reclaim():
        calls["n"] += 1

    d._reclaim_stale_running = fake_reclaim
    await d.start(_RecordingPool(), settings)
    await d.stop()

    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_start_skips_reclaim_when_disabled():
    d = JobDispatcher(poll_interval=0.01, max_concurrent=1)
    settings = type("S", (), {"reclaim_stale_running_jobs_on_start": False})()
    calls = {"n": 0}

    async def fake_reclaim():
        calls["n"] += 1

    d._reclaim_stale_running = fake_reclaim
    await d.start(_RecordingPool(), settings)
    await d.stop()

    assert calls["n"] == 0


class _ArgRecordingPool:
    def __init__(self):
        self.last = None

    async def execute(self, query, *args):
        self.last = (query, args)
        return "UPDATE 0"

    async def fetch(self, *a, **k):
        return []


@pytest.mark.asyncio
async def test_reclaim_is_age_gated():
    # B2: only reclaim 'running' jobs older than the configured grace window.
    d = JobDispatcher(poll_interval=15.0, max_concurrent=1)
    d._pool = _ArgRecordingPool()
    d._settings = type("S", (), {"reclaim_running_min_age_seconds": 600})()
    await d._reclaim_stale_running()
    q, args = d._pool.last
    assert "started_utc <" in q and "INTERVAL '1 second'" in q  # age predicate present
    assert args == (600,)  # binds the configured threshold


def test_reclaim_min_age_default_is_300():
    from memory_knowledge.config import Settings
    assert Settings.model_fields["reclaim_running_min_age_seconds"].default == 300


def test_dispatcher_honors_max_concurrent():
    # server.py wires this from settings.job_dispatcher_max_concurrent (default 1).
    d = JobDispatcher(poll_interval=15.0, max_concurrent=1)
    assert d.max_concurrent == 1
    assert d._semaphore._value == 1
