import types
from datetime import datetime, timezone

import pytest

import memory_knowledge.auth.github_auth as gh_mod
import memory_knowledge.git.clone as clone_mod
import memory_knowledge.jobs.ingestion_scheduler as sched_mod
import memory_knowledge.jobs.manifest_reader as mr_mod
import memory_knowledge.jobs.manifest_writer as mw_mod
from memory_knowledge.jobs.ingestion_scheduler import IngestionScheduler
from memory_knowledge.jobs.ingestion_scheduler import next_daily_run_utc


def _settings(**kw):
    d = dict(
        ingestion_scheduler_repo_allowlist="",
        ingestion_scheduler_max_per_tick=5,
        ingestion_scheduler_interval_seconds=3600,
        ingestion_scheduler_daily_at="",
        ingestion_scheduler_timezone="Europe/Sofia",
    )
    d.update(kw)
    return types.SimpleNamespace(**d)


class FakePool:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, sql, *args):
        return self._rows


def _row(rk, origin="https://github.com/x/y.git", branch="main", commit="old", updated=None):
    return {
        "repository_key": rk,
        "origin_url": origin,
        "branch_name": branch,
        "commit_sha": commit,
        "updated_utc": updated,
    }


def _patch_common(monkeypatch, *, head=None, default=None, active=None, resume=None, created=None):
    async def fake_create_job(pool, run_id, job_type, tool, rk, commit=None, branch=None, **kw):
        if created is not None:
            created.append((rk, commit, branch, job_type))
        return "jobid"

    async def fake_active(pool, **kw):
        return active

    async def fake_resume(pool, **kw):
        return resume

    monkeypatch.setattr(mw_mod, "create_job", fake_create_job)
    monkeypatch.setattr(mr_mod, "get_active_job_for_shape", fake_active)
    monkeypatch.setattr(mr_mod, "get_latest_resume_checkpoint", fake_resume)
    if head is not None:

        async def fake_head(origin, branch, settings):
            return head(origin, branch) if callable(head) else head

        monkeypatch.setattr(clone_mod, "resolve_remote_head", fake_head)
    if default is not None:

        async def fake_default(origin, settings):
            return default

        monkeypatch.setattr(clone_mod, "resolve_default_branch", fake_default)


@pytest.mark.asyncio
async def test_tick_enqueues_on_change(monkeypatch):
    created = []
    _patch_common(monkeypatch, head="newsha", created=created)
    sch = IngestionScheduler()
    sch._pool = FakePool([_row("a", commit="old")])
    sch._settings = _settings()
    await sch._tick()
    assert created == [("a", "newsha", "main", "ingestion")]


@pytest.mark.asyncio
async def test_tick_skips_unchanged(monkeypatch):
    created = []
    _patch_common(monkeypatch, head="same", created=created)
    sch = IngestionScheduler()
    sch._pool = FakePool([_row("a", commit="same")])
    sch._settings = _settings()
    await sch._tick()
    assert created == []


@pytest.mark.asyncio
async def test_tick_skips_when_shape_active(monkeypatch):
    created = []
    _patch_common(monkeypatch, head="newsha", active={"job_id": "existing"}, created=created)
    sch = IngestionScheduler()
    sch._pool = FakePool([_row("a", commit="old")])
    sch._settings = _settings()
    await sch._tick()
    assert created == []


@pytest.mark.asyncio
async def test_tick_bootstraps_null_branch(monkeypatch):
    created = []
    _patch_common(monkeypatch, default=("develop", "bootsha"), created=created)
    sch = IngestionScheduler()
    sch._pool = FakePool([_row("a", branch=None, commit=None)])
    sch._settings = _settings()
    await sch._tick()
    assert created == [("a", "bootsha", "develop", "ingestion")]


@pytest.mark.asyncio
async def test_tick_caps_enqueues_and_isolates_errors(monkeypatch):
    created = []
    calls = {"n": 0}

    def head(origin, branch):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")  # one repo errors → must not abort the tick
        return f"new{calls['n']}"

    _patch_common(monkeypatch, head=head, created=created)
    rows = [_row(f"r{i}", commit="old") for i in range(10)]
    sch = IngestionScheduler()
    sch._pool = FakePool(rows)
    sch._settings = _settings(ingestion_scheduler_max_per_tick=3)
    await sch._tick()
    assert len(created) == 3  # capped at 3 enqueues despite 10 repos + 1 error


def test_next_daily_run_utc_uses_europe_sofia_midnight_winter():
    now = datetime(2026, 1, 1, 21, 30, tzinfo=timezone.utc)  # 23:30 Europe/Sofia
    next_run = next_daily_run_utc("00:00", "Europe/Sofia", now)
    assert next_run == datetime(2026, 1, 1, 22, 0, tzinfo=timezone.utc)


def test_next_daily_run_utc_uses_europe_sofia_midnight_summer():
    now = datetime(2026, 6, 17, 20, 30, tzinfo=timezone.utc)  # 23:30 Europe/Sofia
    next_run = next_daily_run_utc("00:00", "Europe/Sofia", now)
    assert next_run == datetime(2026, 6, 17, 21, 0, tzinfo=timezone.utc)


def test_next_daily_run_utc_rolls_to_tomorrow_after_target_time():
    now = datetime(2026, 6, 17, 21, 1, tzinfo=timezone.utc)  # 00:01 Europe/Sofia
    next_run = next_daily_run_utc("00:00", "Europe/Sofia", now)
    assert next_run == datetime(2026, 6, 18, 21, 0, tzinfo=timezone.utc)


def test_scheduler_does_not_import_run_ingestion_background():
    # Enqueue-contract guard: the scheduler must rely on the dispatcher (single executor),
    # never the direct background runner (which would double-run).
    src = open(sched_mod.__file__).read()
    assert "_run_ingestion_background" not in src


@pytest.mark.asyncio
async def test_maintenance_enqueues_audit_and_compaction(monkeypatch):
    from memory_knowledge.jobs.maintenance_scheduler import MaintenanceScheduler

    created = []

    async def fake_create_job(pool, run_id, job_type, tool, rk, **kw):
        created.append((rk, tool, kw.get("job_params")))
        return "j"

    monkeypatch.setattr(mw_mod, "create_job", fake_create_job)

    class P:
        async def fetch(self, sql, *a):
            return [{"repository_key": "a"}]

        async def fetchval(self, sql, *a):
            return None  # nothing active

    sch = MaintenanceScheduler()
    sch._pool = P()
    sch._settings = types.SimpleNamespace(maintenance_interval_seconds=1, compaction_enabled=False)
    await sch._tick()
    assert ("a", "run_integrity_audit_workflow", None) in created
    assert ("a", "run_compaction_workflow", {"dry_run": True}) in created


@pytest.mark.asyncio
async def test_maintenance_dedups_active(monkeypatch):
    from memory_knowledge.jobs.maintenance_scheduler import MaintenanceScheduler

    created = []

    async def fake_create_job(pool, run_id, job_type, tool, rk, **kw):
        created.append(tool)
        return "j"

    monkeypatch.setattr(mw_mod, "create_job", fake_create_job)

    class P:
        async def fetch(self, sql, *a):
            return [{"repository_key": "a"}]

        async def fetchval(self, sql, *a):
            return "existing-job"  # active → skip both

    sch = MaintenanceScheduler()
    sch._pool = P()
    sch._settings = types.SimpleNamespace(maintenance_interval_seconds=1, compaction_enabled=True)
    await sch._tick()
    assert created == []


@pytest.mark.asyncio
async def test_resolve_remote_head_parses_sha(monkeypatch):
    async def fake_authed(url, settings):
        return url

    monkeypatch.setattr(gh_mod, "get_authenticated_git_url", fake_authed)

    class FakeGit:
        def ls_remote(self, *a):
            return "abc123def\trefs/heads/main"

    import git

    monkeypatch.setattr(git, "Git", lambda: FakeGit())
    sha = await clone_mod.resolve_remote_head("https://github.com/x/y.git", "main", object())
    assert sha == "abc123def"


@pytest.mark.asyncio
async def test_resolve_default_branch_parses_symref(monkeypatch):
    async def fake_authed(url, settings):
        return url

    monkeypatch.setattr(gh_mod, "get_authenticated_git_url", fake_authed)

    class FakeGit:
        def ls_remote(self, *a):
            return "ref: refs/heads/trunk\tHEAD\nzzz999\tHEAD"

    import git

    monkeypatch.setattr(git, "Git", lambda: FakeGit())
    res = await clone_mod.resolve_default_branch("https://github.com/x/y.git", object())
    assert res == ("trunk", "zzz999")
