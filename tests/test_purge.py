"""purge_repository must isolate each store and surface the real (repr) error.

Regression: a store raising an empty-message exception (e.g. TimeoutError()) previously
aborted the whole purge and reached the MCP client as a blank "Error executing tool" string.
"""

import pytest

from memory_knowledge.admin import purge as P


class FakePool:
    async def fetchrow(self, query, *args):
        return {"id": 7}


@pytest.mark.asyncio
async def test_purge_isolates_failing_store_and_reprs_error(monkeypatch):
    async def ok_pg(pool, rk, rid):
        return {"deleted_files": 1}

    async def ok_qd(client, rk):
        return {"code_chunks": 2}

    async def boom_neo(driver, rk):
        raise TimeoutError()  # empty message — the class of error that was being swallowed

    monkeypatch.setattr(P, "_purge_postgres", ok_pg)
    monkeypatch.setattr(P, "_purge_qdrant", ok_qd)
    monkeypatch.setattr(P, "_purge_neo4j", boom_neo)

    res = await P.purge_repository(
        pool=FakePool(), qdrant_client=object(), neo4j_driver=object(), repository_key="r"
    )
    # the two healthy stores still purged (not aborted by neo4j)
    assert res["postgres"] == {"deleted_files": 1}
    assert res["qdrant"] == {"code_chunks": 2}
    # the failing store is captured with its type visible via repr (no more blank error)
    assert "errors" in res and "neo4j" in res["errors"]
    assert "TimeoutError" in res["errors"]["neo4j"]


@pytest.mark.asyncio
async def test_purge_clean_has_no_errors_key(monkeypatch):
    async def ok_pg(pool, rk, rid):
        return {"deleted_files": 0}

    async def ok_qd(client, rk):
        return {"code_chunks": 0}

    async def ok_neo(driver, rk):
        return {"nodes": 0}

    monkeypatch.setattr(P, "_purge_postgres", ok_pg)
    monkeypatch.setattr(P, "_purge_qdrant", ok_qd)
    monkeypatch.setattr(P, "_purge_neo4j", ok_neo)

    res = await P.purge_repository(
        pool=FakePool(), qdrant_client=object(), neo4j_driver=object(), repository_key="r"
    )
    assert "errors" not in res
    assert res["postgres"] == {"deleted_files": 0}


@pytest.mark.asyncio
async def test_purge_unknown_repo_raises(monkeypatch):
    class NoRepoPool:
        async def fetchrow(self, query, *args):
            return None

    with pytest.raises(ValueError):
        await P.purge_repository(
            pool=NoRepoPool(), qdrant_client=object(), neo4j_driver=object(), repository_key="nope"
        )
