"""T4: repair reconciles Qdrant to the active PG set instead of resurrecting drift.

deactivate_unbacked_points must set is_active=False only on currently-active
points whose entity_key isn't in the active PG set, and must NEVER wipe when the
active set is empty (safety valve).
"""
import pytest

from memory_knowledge.projections.qdrant_projector import deactivate_unbacked_points


class _Point:
    def __init__(self, pid):
        self.id = pid


class _FakeQdrant:
    def __init__(self, active_point_ids):
        # represents the repo's currently-active points in Qdrant
        self._points = [_Point(p) for p in active_point_ids]
        self.set_payload_calls: list[dict] = []

    async def scroll(self, collection_name, scroll_filter, limit, offset, with_payload, with_vectors):
        return self._points, None  # single page

    async def set_payload(self, collection_name, payload, points):
        self.set_payload_calls.append({"payload": payload, "points": list(points)})


@pytest.mark.asyncio
async def test_deactivates_only_unbacked_active_points():
    # Qdrant has 4 active points; PG active backs only k1, k2 → k3 + orphan are unbacked.
    client = _FakeQdrant(["K1", "K2", "K3", "orphan-x"])
    n = await deactivate_unbacked_points(
        client, "code_chunks", "repo", active_entity_keys={"k1", "k2"}
    )
    assert n == 2
    assert len(client.set_payload_calls) == 1
    call = client.set_payload_calls[0]
    assert call["payload"] == {"is_active": False}
    assert set(str(p).lower() for p in call["points"]) == {"k3", "orphan-x"}


@pytest.mark.asyncio
async def test_empty_active_set_is_a_noop_not_a_wipe():
    client = _FakeQdrant(["K1", "K2"])
    n = await deactivate_unbacked_points(client, "code_chunks", "repo", active_entity_keys=set())
    assert n == 0
    assert client.set_payload_calls == []  # never wipes


@pytest.mark.asyncio
async def test_all_backed_deactivates_nothing():
    client = _FakeQdrant(["k1", "k2"])
    n = await deactivate_unbacked_points(client, "code_chunks", "repo", active_entity_keys={"k1", "k2"})
    assert n == 0
    assert client.set_payload_calls == []
