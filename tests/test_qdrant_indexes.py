"""Guards the Qdrant payload-index set created by ensure_collections.

Regression: incremental ingestion deactivates a changed/deleted file's old
points via a filter on file_path. Without a file_path payload index, Qdrant
rejects the filter (400) and every changed file is dropped (0 chunks written)
while the run still "completes" — silently stalling incremental freshness.
"""
import pytest

from memory_knowledge.db import qdrant


class _FakeCollections:
    def __init__(self, names):
        self.collections = [type("C", (), {"name": n})() for n in names]


class _FakeClient:
    """Captures create_payload_index calls per collection."""

    def __init__(self, existing=()):
        self._existing = list(existing)
        self.created_indexes: list[tuple[str, str]] = []
        self.created_collections: list[str] = []

    async def get_collections(self):
        return _FakeCollections(self._existing)

    async def create_collection(self, collection_name, vectors_config):
        self.created_collections.append(collection_name)

    async def create_payload_index(self, collection_name, field_name, field_schema):
        self.created_indexes.append((collection_name, field_name))


@pytest.mark.asyncio
async def test_ensure_collections_indexes_file_path():
    client = _FakeClient(existing=[])
    settings = type("Settings", (), {"embedding_dimensions": 768})()

    await qdrant.ensure_collections(client, settings)

    indexed_fields = {field for _coll, field in client.created_indexes}
    # The fields incremental/delete filters depend on must all be indexed.
    for required in ("file_path", "repository_key", "branch_name", "commit_sha", "is_active"):
        assert required in indexed_fields, f"missing payload index: {required}"

    # file_path must be indexed for every collection that gets indexes.
    coll_with_file_path = {c for c, f in client.created_indexes if f == "file_path"}
    assert "code_chunks" in coll_with_file_path
