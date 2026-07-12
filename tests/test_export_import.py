from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from memory_knowledge.admin.export_import import (
    _encode_import_cursor,
    list_import_unresolved,
    order_learned_insert_items,
)


def item(entity_key: str, supersedes: str | None = None):
    return {"row": {"_entity_key": entity_key, "_supersedes_entity_key": supersedes}}


def test_learned_import_topologically_orders_forward_supersession_chain():
    old, middle, newest = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    ordered = order_learned_insert_items([
        item(newest, middle), item(middle, old), item(old),
    ], set())
    assert [value["row"]["_entity_key"] for value in ordered] == [old, middle, newest]


def test_learned_import_rejects_missing_or_cyclic_supersession():
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    with pytest.raises(ValueError, match="missing-or-cyclic"):
        order_learned_insert_items([item(first, second), item(second, first)], set())


class ReportPool:
    def __init__(self):
        self.import_id = uuid.uuid4(); self.secret = os.urandom(32)
        self.expires = datetime.now(UTC) + timedelta(days=1)
        self.rows = [
            {"ordinal": index, "entity_key": uuid.uuid4(), "reason_codes": [{"reason_code": "unresolved-evidence"}]}
            for index in range(3)
        ]

    async def fetchrow(self, query, *args):
        if "learned_import_reports" in query:
            return {"import_id": self.import_id, "repository_key": "repo",
                    "cursor_secret": self.secret, "unresolved_total": 3,
                    "expires_utc": self.expires, "expired_utc": None}
        if "ordinal=$2" in query:
            return {"exists": 1} if any(row["ordinal"] == args[1] for row in self.rows) else None
        raise AssertionError(query)

    async def fetch(self, query, *args):
        after, limit = args[1], args[2]
        return [row for row in self.rows if row["ordinal"] > after][:limit]


@pytest.mark.asyncio
async def test_unresolved_cursor_is_replayable_and_exhausts_without_cursor():
    pool = ReportPool()
    first = await list_import_unresolved(pool, "repo", str(pool.import_id), limit=2)
    assert first["truncated"] and first["next_cursor"] and len(first["items"]) == 2
    second = await list_import_unresolved(
        pool, "repo", str(pool.import_id), limit=2, cursor=first["next_cursor"]
    )
    replay = await list_import_unresolved(
        pool, "repo", str(pool.import_id), limit=2, cursor=first["next_cursor"]
    )
    assert second == replay
    assert not second["truncated"] and second["next_cursor"] is None and len(second["items"]) == 1


@pytest.mark.asyncio
async def test_unresolved_cursor_rejects_forgery():
    pool = ReportPool()
    cursor = _encode_import_cursor(pool.secret, pool.import_id, "repo", 0, pool.expires)
    with pytest.raises(ValueError, match="invalid-import-cursor"):
        await list_import_unresolved(pool, "repo", str(pool.import_id), cursor=cursor + "x")
