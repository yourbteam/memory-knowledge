"""Connection-resilience kwargs + batch dedup-before-upsert.

Regression coverage for two grounded fragilities:
- init_qdrant must bound HTTP calls (timeout); init_postgres must recycle idle
  pooled connections — the same connection-fragility class fixed for Neo4j.
- bulk upserts must de-dup conflict keys within a batch, else Postgres raises
  "ON CONFLICT DO UPDATE command cannot affect row a second time".
"""

import pytest

from memory_knowledge.db import postgres as pg_mod
from memory_knowledge.db import qdrant as qdrant_mod
from memory_knowledge.projections.pg_writer import _dedup_last as dedup_pg
from memory_knowledge.projections.summary_writer import _dedup_last as dedup_sum


@pytest.mark.asyncio
async def test_init_qdrant_passes_timeout(monkeypatch):
    captured: dict = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(qdrant_mod, "AsyncQdrantClient", FakeClient)
    settings = type(
        "S",
        (),
        {
            "qdrant_url": "http://localhost:6333",
            "qdrant_api_key": "k",
            "qdrant_timeout_seconds": 60.0,
        },
    )()

    await qdrant_mod.init_qdrant(settings)
    assert captured["timeout"] == 60.0


@pytest.mark.asyncio
async def test_init_postgres_passes_idle_recycle(monkeypatch):
    captured: dict = {}

    async def fake_create_pool(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(pg_mod.asyncpg, "create_pool", fake_create_pool)
    settings = type(
        "S",
        (),
        {
            "database_url": "postgresql://localhost/db",
            "pg_ssl": False,
            "pg_command_timeout": 30,
            "pg_pool_min_size": 5,
            "pg_pool_max_size": 20,
            "pg_max_inactive_connection_lifetime_seconds": 300.0,
        },
    )()

    await pg_mod.init_postgres(settings)
    assert captured["max_inactive_connection_lifetime"] == 300.0


def test_dedup_last_single_key_keeps_last():
    rows = [("k1", "a"), ("k2", "b"), ("k1", "c")]
    # key appears in first-seen position, value is the LAST occurrence
    assert dedup_pg(rows, lambda r: r[0]) == [("k1", "c"), ("k2", "b")]


def test_dedup_last_composite_key():
    rows = [(1, "file", "x"), (1, "symbol", "y"), (1, "file", "z")]
    assert dedup_sum(rows, lambda r: (r[0], r[1])) == [(1, "file", "z"), (1, "symbol", "y")]


def test_dedup_last_noop_when_unique():
    rows = [("a", 1), ("b", 2), ("c", 3)]
    assert dedup_pg(rows, lambda r: r[0]) == rows
