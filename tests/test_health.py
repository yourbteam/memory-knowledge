from unittest.mock import AsyncMock

import pytest

from memory_knowledge.db import health


class BlankNeo4jError(Exception):
    def __str__(self) -> str:
        return ""


@pytest.mark.asyncio
async def test_readiness_reports_exception_type_when_message_is_blank(monkeypatch):
    pool = AsyncMock()
    pool.fetchval.return_value = 1

    qdrant = AsyncMock()
    qdrant.get_collections.return_value = {"collections": []}

    neo4j = AsyncMock()
    neo4j.verify_connectivity.side_effect = BlankNeo4jError()

    monkeypatch.setattr(health, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(health, "get_qdrant_client", lambda: qdrant)
    monkeypatch.setattr(health, "get_neo4j_driver", lambda: neo4j)

    result = await health.readiness_check()

    assert result["status"] == "not_ready"
    assert result["postgres"] == "ok"
    assert result["qdrant"] == "ok"
    assert result["neo4j"].startswith("error: BlankNeo4jError:")
    assert result["neo4j"] != "error: "
