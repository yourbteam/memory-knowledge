"""WS5: server-side get_scheduler_heartbeat tool + the upkeep_heartbeat stamp check."""

import datetime as dt
import importlib.util
import json as _json
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_knowledge import server

_HB_PATH = Path(__file__).resolve().parent.parent / "working-agreement" / "upkeep_heartbeat.py"
_spec = importlib.util.spec_from_file_location("upkeep_heartbeat", _HB_PATH)
hb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hb)


# --- server tool: get_scheduler_heartbeat --------------------------------------


class _HeartbeatPool:
    def __init__(self, last_tick):
        self.last_tick = last_tick

    async def fetchrow(self, query, *args):
        assert "ops.job_manifests" in query and "integrity_audit" in query
        return {"last_tick": self.last_tick}


@pytest.mark.asyncio
async def test_heartbeat_returns_age_for_recent_tick(monkeypatch):
    recent = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
    monkeypatch.setattr(server, "get_pg_pool", lambda: _HeartbeatPool(recent))
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace(maintenance_interval_seconds=604800))

    out = _json.loads(await server.get_scheduler_heartbeat())
    assert out["status"] == "success"
    d = out["data"]
    assert d["last_maintenance_tick_utc"] == recent.isoformat()
    assert 7000 < d["age_seconds"] < 7400  # ~2h
    assert d["maintenance_interval_seconds"] == 604800


@pytest.mark.asyncio
async def test_heartbeat_null_when_never_ticked(monkeypatch):
    monkeypatch.setattr(server, "get_pg_pool", lambda: _HeartbeatPool(None))
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace(maintenance_interval_seconds=604800))
    out = _json.loads(await server.get_scheduler_heartbeat())
    assert out["status"] == "success"
    assert out["data"]["last_maintenance_tick_utc"] is None
    assert out["data"]["age_seconds"] is None  # → dead-man's-switch trips


# --- upkeep_heartbeat: stamp age -----------------------------------------------


def test_stamp_age_days_fresh_and_stale():
    today = dt.date(2026, 6, 21)
    fresh = "<!-- Last reviewed: 2026-06-20 -->"
    stale = "<!-- Last reviewed: 2026-06-01 -->"
    assert hb.stamp_age_days(fresh, today=today) == 1
    assert hb.stamp_age_days(stale, today=today) == 20
    assert hb.stamp_age_days("no stamp here", today=today) is None  # missing → treated as stale by main()
