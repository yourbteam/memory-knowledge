import uuid
from types import SimpleNamespace

import pytest

from memory_knowledge.integrity import repair_drift
from memory_knowledge.workflows import repair_rebuild


class FakePool:
    async def fetchrow(self, query, *args):
        if "ORDER BY rr.created_utc DESC" in query:
            return {
                "repo_id": 1,
                "rev_id": 2,
                "commit_sha": "abc123",
                "branch_name": "main",
            }
        return {
            "repo_id": 1,
            "rev_id": 2,
            "branch_name": "main",
        }

    async def fetch(self, query, *args):
        return []


@pytest.mark.asyncio
async def test_repair_ensures_qdrant_collections_before_qdrant_scope(monkeypatch):
    calls: list[str] = []

    async def fake_ensure_collections(client, settings):
        calls.append("ensure")

    monkeypatch.setattr(repair_drift, "ensure_collections", fake_ensure_collections)

    report = await repair_drift.repair(
        pool=FakePool(),
        qdrant_client=object(),
        neo4j_driver=object(),
        settings=SimpleNamespace(),
        repository_key="repo-a",
        repair_scope="qdrant",
    )

    assert report.errors == []
    assert calls == ["ensure"]


@pytest.mark.asyncio
async def test_rebuild_revision_ensures_qdrant_collections_before_qdrant_scope(monkeypatch):
    calls: list[str] = []

    async def fake_ensure_collections(client, settings):
        calls.append("ensure")

    monkeypatch.setattr(repair_drift, "ensure_collections", fake_ensure_collections)

    report = await repair_drift.rebuild_revision(
        pool=FakePool(),
        qdrant_client=object(),
        neo4j_driver=object(),
        settings=SimpleNamespace(),
        repository_key="repo-a",
        commit_sha="abc123",
        repair_scope="qdrant",
    )

    assert report.errors == []
    assert calls == ["ensure"]


@pytest.mark.asyncio
async def test_repair_reprojects_all_canonical_chunks_and_summaries(monkeypatch):
    class Pool:
        async def fetchrow(self, query, *args):
            return {
                "repo_id": 1,
                "rev_id": 2,
                "commit_sha": "abc123",
                "branch_name": "main",
            }

        async def fetch(self, query, *args):
            if "FROM catalog.chunks" in query:
                return [
                    {"entity_key": "chunk-1", "content_text": "a", "chunk_type": "file", "file_path": "a.py", "title": "file:a"},
                    {"entity_key": "chunk-2", "content_text": "b", "chunk_type": "symbol", "file_path": "b.py", "title": "symbol:fn[b.py]"},
                ]
            if "FROM catalog.summaries" in query:
                return [
                    {"entity_key": "sum-1", "summary_text": "one", "summary_level": "file"},
                    {"entity_key": "sum-2", "summary_text": "two", "summary_level": "symbol"},
                ]
            if "SELECT e.entity_key AS file_entity_key, f.file_path" in query:
                return [{"file_entity_key": "file-1", "file_path": "a.py"}]
            if "SELECT e_file.entity_key AS file_entity_key" in query:
                return [{"file_entity_key": "file-1", "symbol_entity_key": "sym-1", "symbol_name": "fn", "symbol_kind": "function"}]
            return []

    captured: dict[str, object] = {}

    async def fake_ensure_collections(client, settings):
        return None

    async def fake_embed_chunks(texts, settings):
        captured["chunk_texts"] = list(texts)
        return [[0.1], [0.2]]

    async def fake_upsert_points(client, chunks, repository_key, commit_sha, branch_name):
        captured["upserted_chunks"] = list(chunks)

    async def fake_embed_and_upsert_summaries(client, summaries, repository_key, commit_sha, settings):
        captured["upserted_summaries"] = list(summaries)

    async def fake_project_repository_graph(driver, repository_key, commit_sha, branch_name, file_symbols):
        captured["projected_files"] = list(file_symbols)

    monkeypatch.setattr(repair_drift, "ensure_collections", fake_ensure_collections)
    monkeypatch.setattr(repair_drift, "embed_chunks", fake_embed_chunks)
    monkeypatch.setattr(repair_drift, "upsert_points", fake_upsert_points)
    monkeypatch.setattr(repair_drift, "embed_and_upsert_summaries", fake_embed_and_upsert_summaries)
    monkeypatch.setattr(repair_drift, "project_repository_graph", fake_project_repository_graph)

    report = await repair_drift.repair(
        pool=Pool(),
        qdrant_client=object(),
        neo4j_driver=object(),
        settings=SimpleNamespace(),
        repository_key="repo-a",
        repair_scope="full",
    )

    assert report.errors == []
    assert report.qdrant_points_repaired == 2
    assert report.summary_points_repaired == 2
    assert report.neo4j_nodes_repaired == 1
    assert captured["chunk_texts"] == ["a", "b"]
    assert len(captured["upserted_chunks"]) == 2
    assert len(captured["upserted_summaries"]) == 2


@pytest.mark.asyncio
async def test_rebuild_revision_reprojects_all_revision_chunks(monkeypatch):
    class Pool:
        async def fetchrow(self, query, *args):
            return {"repo_id": 1, "rev_id": 2, "branch_name": "main"}

        async def fetch(self, query, *args):
            if "FROM catalog.chunks" in query:
                return [
                    {"entity_key": "chunk-1", "content_text": "a", "chunk_type": "file", "file_path": "a.py", "title": "file:a"},
                    {"entity_key": "chunk-2", "content_text": "b", "chunk_type": "symbol", "file_path": "b.py", "title": "symbol:fn[b.py]"},
                ]
            if "SELECT e.entity_key AS file_entity_key, f.file_path" in query:
                return []
            if "SELECT e_file.entity_key AS file_entity_key" in query:
                return []
            return []

    captured: dict[str, object] = {}

    async def fake_ensure_collections(client, settings):
        return None

    async def fake_embed_chunks(texts, settings):
        captured["texts"] = list(texts)
        return [[0.1], [0.2]]

    async def fake_upsert_points(client, chunks, repository_key, commit_sha, branch_name):
        captured["chunks"] = list(chunks)

    monkeypatch.setattr(repair_drift, "ensure_collections", fake_ensure_collections)
    monkeypatch.setattr(repair_drift, "embed_chunks", fake_embed_chunks)
    monkeypatch.setattr(repair_drift, "upsert_points", fake_upsert_points)

    report = await repair_drift.rebuild_revision(
        pool=Pool(),
        qdrant_client=object(),
        neo4j_driver=object(),
        settings=SimpleNamespace(),
        repository_key="repo-a",
        commit_sha="abc123",
        repair_scope="qdrant",
    )

    assert report.errors == []
    assert report.qdrant_points_repaired == 2
    assert captured["texts"] == ["a", "b"]
    assert len(captured["chunks"]) == 2


@pytest.mark.asyncio
async def test_repair_reprojects_triage_cases_and_tracks_skipped_rows(monkeypatch):
    class Pool:
        async def fetchrow(self, query, *args):
            return {
                "repo_id": 1,
                "rev_id": 2,
                "commit_sha": "abc123",
                "branch_name": "main",
            }

        async def fetch(self, query, *args):
            return []

    async def fake_ensure_collections(client, settings):
        return None

    async def fake_reproject_triage_cases(pool, qdrant_client, settings, repository_key):
        return {"repaired": 3, "skipped": 1, "errors": ["row skipped"]}

    monkeypatch.setattr(repair_drift, "ensure_collections", fake_ensure_collections)
    monkeypatch.setattr(repair_drift._triage_memory, "reproject_triage_cases", fake_reproject_triage_cases)

    report = await repair_drift.repair(
        pool=Pool(),
        qdrant_client=object(),
        neo4j_driver=object(),
        settings=SimpleNamespace(),
        repository_key="repo-a",
        repair_scope="qdrant",
    )

    assert report.errors == []
    assert report.triage_cases_repaired == 3
    assert report.triage_cases_skipped == 1


@pytest.mark.asyncio
async def test_rebuild_revision_reprojects_triage_cases(monkeypatch):
    class Pool:
        async def fetchrow(self, query, *args):
            return {"repo_id": 1, "rev_id": 2, "branch_name": "main"}

        async def fetch(self, query, *args):
            return []

    async def fake_ensure_collections(client, settings):
        return None

    async def fake_reproject_triage_cases(pool, qdrant_client, settings, repository_key):
        return {"repaired": 2, "skipped": 0, "errors": []}

    monkeypatch.setattr(repair_drift, "ensure_collections", fake_ensure_collections)
    monkeypatch.setattr(repair_drift._triage_memory, "reproject_triage_cases", fake_reproject_triage_cases)

    report = await repair_drift.rebuild_revision(
        pool=Pool(),
        qdrant_client=object(),
        neo4j_driver=object(),
        settings=SimpleNamespace(),
        repository_key="repo-a",
        commit_sha="abc123",
        repair_scope="qdrant",
    )

    assert report.errors == []
    assert report.triage_cases_repaired == 2
    assert report.triage_cases_skipped == 0


@pytest.mark.asyncio
async def test_repair_rebuild_returns_partial_when_triage_rows_are_skipped(monkeypatch):
    async def fake_repair(pool, qdrant_client, neo4j_driver, settings, repository_key, repair_scope):
        return repair_drift.RepairReport(
            scope=repair_scope,
            triage_cases_repaired=4,
            triage_cases_skipped=1,
        )

    monkeypatch.setattr(repair_rebuild, "repair", fake_repair)

    result = await repair_rebuild.run(
        repository_key="repo-a",
        run_id=uuid.uuid4(),
        repair_scope="qdrant",
        pool=object(),
        qdrant_client=object(),
        neo4j_driver=object(),
        settings=SimpleNamespace(),
    )

    assert result.status == "partial"
    assert result.data["triage_cases_repaired"] == 4
    assert result.data["triage_cases_skipped"] == 1
