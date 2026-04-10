from types import SimpleNamespace

import pytest

from memory_knowledge.projections import pg_writer, summary_writer
from memory_knowledge.structure import entity_registrar
from memory_knowledge.workflows import ingestion


class FakePool:
    def __init__(self):
        self.fetch_calls: list[tuple[str, tuple]] = []

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return [{"entity_key": "ek-1"}, {"entity_key": "ek-2"}]


@pytest.mark.asyncio
async def test_determine_diff_files_forces_full_run_when_old_sha_matches_commit(monkeypatch):
    changed_calls: list[tuple[object, str, str, tuple[str, ...]]] = []

    def fake_changed_files(repo, old_sha, commit_sha, extensions):
        changed_calls.append((repo, old_sha, commit_sha, tuple(extensions)))
        return ["src/example.py"]

    monkeypatch.setattr(ingestion, "changed_files", fake_changed_files)

    result = await ingestion._determine_diff_files(
        old_sha="abc123",
        commit_sha="abc123",
        repo=object(),
        settings=SimpleNamespace(supported_languages=["python"]),
    )

    assert result is None
    assert changed_calls == []


@pytest.mark.asyncio
async def test_determine_diff_files_uses_incremental_diff_when_sha_changes(monkeypatch):
    changed_calls: list[tuple[object, str, str, tuple[str, ...]]] = []

    def fake_changed_files(repo, old_sha, commit_sha, extensions):
        changed_calls.append((repo, old_sha, commit_sha, tuple(extensions)))
        return ["src/example.py"]

    monkeypatch.setattr(ingestion, "changed_files", fake_changed_files)

    repo = object()
    result = await ingestion._determine_diff_files(
        old_sha="old-sha",
        commit_sha="new-sha",
        repo=repo,
        settings=SimpleNamespace(supported_languages=["python"]),
    )

    assert result == ["src/example.py"]
    assert changed_calls == [(repo, "old-sha", "new-sha", (".py",))]


@pytest.mark.asyncio
async def test_fetch_existing_summary_keys_scopes_to_current_revision():
    pool = FakePool()

    result = await ingestion._fetch_existing_summary_keys(
        pool,
        repository_id=7,
        repo_revision_id=42,
    )

    assert result == {"ek-1", "ek-2"}
    query, args = pool.fetch_calls[0]
    assert "WHERE e.repository_id = $1 AND e.repo_revision_id = $2" in query
    assert args == (7, 42)


def test_checkpoint_phase_at_or_beyond_orders_resume_stages():
    assert ingestion._checkpoint_phase_at_or_beyond({"phase": "canonical_complete"}, "canonical_complete") is True
    assert ingestion._checkpoint_phase_at_or_beyond({"phase": "summary_embeddings_complete"}, "chunk_embeddings_complete") is True
    assert ingestion._checkpoint_phase_at_or_beyond({"phase": "canonical_complete"}, "neo4j_complete") is False
    assert ingestion._checkpoint_phase_at_or_beyond(None, "canonical_complete") is False


@pytest.mark.asyncio
async def test_bulk_upsert_files_uses_set_based_queries():
    class Pool:
        def __init__(self):
            self.fetch_queries: list[str] = []

        async def fetch(self, query, *args):
            self.fetch_queries.append(query)
            if "INSERT INTO catalog.entities" in query:
                return [{"id": 11, "entity_key": args[0][0]}]
            return [{"id": 22, "entity_id": 11, "file_path": args[2][0]}]

    pool = Pool()
    rows = [
        {
            "entity_key": "b4324b95-7175-47fa-9e3a-830c66f6e488",
            "repository_id": 1,
            "repo_revision_id": 2,
            "file_path": "src/example.py",
            "language": "python",
            "size_bytes": 10,
            "checksum": "abc",
            "external_hash": "abc",
        }
    ]

    saved = await entity_registrar.bulk_upsert_files(pool, rows)

    assert saved == [{
        "entity_id": 11,
        "file_id": 22,
        "file_path": "src/example.py",
        "entity_key": "b4324b95-7175-47fa-9e3a-830c66f6e488",
    }]
    assert len(pool.fetch_queries) == 2
    assert "UNNEST" in pool.fetch_queries[0]
    assert "UNNEST" in pool.fetch_queries[1]


@pytest.mark.asyncio
async def test_bulk_upsert_chunks_uses_set_based_queries():
    class Pool:
        def __init__(self):
            self.fetch_queries: list[str] = []
            self.execute_queries: list[str] = []

        async def fetch(self, query, *args):
            self.fetch_queries.append(query)
            return [{"id": 33, "entity_key": args[0][0]}]

        async def execute(self, query, *args):
            self.execute_queries.append(query)

    pool = Pool()
    await pg_writer.bulk_upsert_chunks(
        pool,
        [{
            "entity_key": "df7ec4ec-ae0a-437f-97d7-53e47402dd0c",
            "repository_id": 1,
            "repo_revision_id": 2,
            "file_id": 3,
            "title": "chunk",
            "content_text": "print('x')",
            "chunk_type": "file",
            "line_start": 1,
            "line_end": 1,
            "checksum": "sum",
        }],
    )

    assert len(pool.fetch_queries) == 1
    assert "UNNEST" in pool.fetch_queries[0]
    assert len(pool.execute_queries) == 1
    assert "UNNEST" in pool.execute_queries[0]


@pytest.mark.asyncio
async def test_bulk_upsert_summaries_uses_set_based_queries():
    class Pool:
        def __init__(self):
            self.fetch_queries: list[str] = []
            self.execute_queries: list[str] = []

        async def fetch(self, query, *args):
            self.fetch_queries.append(query)
            return [{"id": 44, "entity_key": args[0][0]}]

        async def execute(self, query, *args):
            self.execute_queries.append(query)

    pool = Pool()
    await summary_writer.bulk_upsert_summaries(
        pool,
        [{
            "entity_key": "3d17cf84-6321-4dc6-a6ca-fb1fdbd2d64f",
            "repository_id": 1,
            "repo_revision_id": 2,
            "parent_entity_id": 9,
            "summary_level": "file",
            "summary_text": "summary",
        }],
    )

    assert len(pool.fetch_queries) == 1
    assert "UNNEST" in pool.fetch_queries[0]
    assert len(pool.execute_queries) == 1
    assert "UNNEST" in pool.execute_queries[0]
