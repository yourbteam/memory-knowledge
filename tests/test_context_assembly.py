from __future__ import annotations

import uuid

import pytest

from memory_knowledge.integrity import reembed_collections
from memory_knowledge.workflows.context_assembly import _fetch_applicable_learned_rules
from tests.test_retrieval import rows as trust_rows


def complete_rows():
    result = []
    for row in trust_rows():
        result.append({
            **row, "entity_key": uuid.uuid4(), "body_text": row["title"],
            "confidence": 0.8, "applicability_mode": "repository",
            "scope_entity_key": uuid.uuid4(),
        })
    return result


class Pool:
    async def fetch(self, query, *args):
        return complete_rows()


@pytest.mark.asyncio
async def test_context_assembly_rehydrates_graph_keys_and_filters_pg_truth():
    result = await _fetch_applicable_learned_rules(Pool(), None, [], 7)
    assert [row["title"] for row in result] == ["verified rule", "confirmed note"]
    assert all(row["source"] == "postgres" for row in result)


@pytest.mark.asyncio
async def test_reembed_projects_exactly_the_same_eligible_rows(monkeypatch):
    captured = {}

    async def fake_upsert(client, settings, collection, payload_rows):
        captured["rows"] = payload_rows
        return len(payload_rows)

    monkeypatch.setattr(reembed_collections, "_embed_and_upsert", fake_upsert)
    count = await reembed_collections.reembed_learned(
        Pool(), object(), object(), 7, "repo"
    )
    assert count == 2
    assert [row["text"] for row in captured["rows"]] == ["verified rule", "confirmed note"]
