"""Regression tests for the `list_repositories` active-status filter (Gap #6).

`list_repositories` historically returned every repository regardless of status,
so soft-deactivated test/clutter repos still surfaced. The tool now excludes
repositories whose `REPOSITORY_STATUS` is ``inactive`` by default, with an
additive ``include_inactive`` flag to restore the legacy "return everything"
behaviour.

These are unit tests in the repo's stub-pool style: the fake pool cannot execute
SQL, so they assert the contract that drives Postgres-side filtering — the status
join, the filter clause, and the bound ``include_inactive`` argument. The actual
row exclusion is enforced by Postgres via that clause.
"""

import json

import pytest

from memory_knowledge import server


class FakePool:
    def __init__(self, rows=None):
        self.fetch_calls: list[tuple[str, tuple]] = []
        self._rows = rows or []

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self._rows


@pytest.mark.asyncio
async def test_list_repositories_excludes_inactive_by_default(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)

    result = await server.list_repositories()
    data = json.loads(result)

    assert data["status"] == "success"
    assert len(pool.fetch_calls) == 1
    query, args = pool.fetch_calls[0]
    # Status join + filter clause must be present, and bound to the default (hide inactive).
    assert "LEFT JOIN core.reference_values rstat ON rstat.id = r.status_id" in query
    assert "rstat.internal_code IS DISTINCT FROM 'REPO_INACTIVE'" in query
    assert args == (False,)


@pytest.mark.asyncio
async def test_list_repositories_includes_inactive_when_requested(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)

    result = await server.list_repositories(include_inactive=True)
    data = json.loads(result)

    assert data["status"] == "success"
    _, args = pool.fetch_calls[0]
    assert args == (True,)


@pytest.mark.asyncio
async def test_list_repositories_default_signature_is_backward_compatible(monkeypatch):
    """Existing callers passing only correlation_id (or nothing) still work."""
    pool = FakePool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)

    result = await server.list_repositories(correlation_id="abc-123")
    data = json.loads(result)

    assert data["status"] == "success"
    _, args = pool.fetch_calls[0]
    assert args == (False,)
