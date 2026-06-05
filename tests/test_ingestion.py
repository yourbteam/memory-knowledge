from types import SimpleNamespace

import pytest

from memory_knowledge.integrity import backfill_is_active
from memory_knowledge.projections import neo4j_projector, pg_writer, summary_writer
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
    assert (
        ingestion._checkpoint_phase_at_or_beyond({"phase": "summary_embeddings_complete"}, "chunk_embeddings_complete")
        is True
    )
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

    assert saved == [
        {
            "entity_id": 11,
            "file_id": 22,
            "file_path": "src/example.py",
            "entity_key": "b4324b95-7175-47fa-9e3a-830c66f6e488",
        }
    ]
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
        [
            {
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
            }
        ],
    )

    assert len(pool.fetch_queries) == 1
    assert "UNNEST" in pool.fetch_queries[0]
    assert len(pool.execute_queries) == 1
    assert "UNNEST" in pool.execute_queries[0]


@pytest.mark.asyncio
async def test_bulk_upsert_symbols_dedupes_duplicate_entity_keys():
    class Pool:
        def __init__(self):
            self.fetch_calls: list[tuple[str, tuple]] = []

        async def fetch(self, query, *args):
            self.fetch_calls.append((query, args))
            if "INSERT INTO catalog.entities" in query:
                return [{"id": 55, "entity_key": args[0][0]}]
            return [{"id": 66, "entity_id": args[0][0]}]

    pool = Pool()
    rows = [
        {
            "entity_key": "91e7812e-eb28-4dae-80e3-e9172553fa0b",
            "repository_id": 1,
            "repo_revision_id": 2,
            "file_id": 3,
            "file_path": "scripts/libraries/pdf.js",
            "symbol_name": "_classCallCheck",
            "symbol_kind": "function",
            "line_start": 10,
            "line_end": 10,
            "signature": "function _classCallCheck()",
            "external_hash": "hash-a",
        },
        {
            "entity_key": "91e7812e-eb28-4dae-80e3-e9172553fa0b",
            "repository_id": 1,
            "repo_revision_id": 2,
            "file_id": 3,
            "file_path": "scripts/libraries/pdf.js",
            "symbol_name": "_classCallCheck",
            "symbol_kind": "function",
            "line_start": 25,
            "line_end": 25,
            "signature": "function _classCallCheck()",
            "external_hash": "hash-b",
        },
    ]

    saved = await entity_registrar.bulk_upsert_symbols(pool, rows)

    assert saved == [
        {
            "entity_id": 55,
            "symbol_id": 66,
            "entity_key": "91e7812e-eb28-4dae-80e3-e9172553fa0b",
            "file_path": "scripts/libraries/pdf.js",
            "symbol_name": "_classCallCheck",
        }
    ]
    entity_query, entity_args = pool.fetch_calls[0]
    symbol_query, symbol_args = pool.fetch_calls[1]
    assert "UNNEST" in entity_query
    assert "UNNEST" in symbol_query
    assert entity_args[0] == ["91e7812e-eb28-4dae-80e3-e9172553fa0b"]
    assert symbol_args[0] == [55]


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
        [
            {
                "entity_key": "3d17cf84-6321-4dc6-a6ca-fb1fdbd2d64f",
                "repository_id": 1,
                "repo_revision_id": 2,
                "parent_entity_id": 9,
                "summary_level": "file",
                "summary_text": "summary",
            }
        ],
    )

    assert len(pool.fetch_queries) == 1
    assert "UNNEST" in pool.fetch_queries[0]
    assert len(pool.execute_queries) == 1
    assert "UNNEST" in pool.execute_queries[0]


class _ExecPool:
    def __init__(self, status="UPDATE 0"):
        self.calls: list[tuple[str, tuple]] = []
        self._status = status

    async def execute(self, query, *args):
        self.calls.append((query, args))
        return self._status


@pytest.mark.asyncio
async def test_deactivate_file_chunks_targets_repo_and_path():
    pool = _ExecPool("UPDATE 3")
    await pg_writer.deactivate_file_chunks(pool, 7, "src/x.py")
    query, args = pool.calls[0]
    assert "UPDATE catalog.chunks" in query
    assert "is_active = FALSE" in query
    assert "f.file_path = $2" in query
    assert args == (7, "src/x.py")


@pytest.mark.asyncio
async def test_deactivate_old_chunks_filters_branch_and_other_commits():
    pool = _ExecPool()
    await pg_writer.deactivate_old_chunks(pool, 1, "main", "sha-new")
    query, args = pool.calls[0]
    assert "UPDATE catalog.chunks" in query
    assert "rr.branch_name = $2" in query
    assert "rr.commit_sha <> $3" in query
    assert args == (1, "main", "sha-new")


@pytest.mark.asyncio
async def test_deactivate_old_summaries_filters_repo_and_other_commits():
    pool = _ExecPool()
    await pg_writer.deactivate_old_summaries(pool, 1, "sha-new")
    query, args = pool.calls[0]
    assert "UPDATE catalog.summaries" in query
    assert "rr.commit_sha <> $2" in query
    assert "branch_name" not in query
    assert args == (1, "sha-new")


@pytest.mark.asyncio
async def test_backfill_deactivate_filters_invalid_uuids_and_counts():
    pool = _ExecPool("UPDATE 2")
    n = await backfill_is_active._deactivate_pg_rows(
        pool,
        backfill_is_active._UPDATE_CHUNKS_SQL,
        [
            "b4324b95-7175-47fa-9e3a-830c66f6e488",
            "not-a-uuid",
            "df7ec4ec-ae0a-437f-97d7-53e47402dd0c",
        ],
    )
    assert n == 2
    _, args = pool.calls[0]
    assert args[0] == [
        "b4324b95-7175-47fa-9e3a-830c66f6e488",
        "df7ec4ec-ae0a-437f-97d7-53e47402dd0c",
    ]


@pytest.mark.asyncio
async def test_backfill_deactivate_no_valid_ids_skips_execute():
    pool = _ExecPool()
    n = await backfill_is_active._deactivate_pg_rows(pool, backfill_is_active._UPDATE_SUMMARIES_SQL, ["nope"])
    assert n == 0
    assert pool.calls == []


@pytest.mark.asyncio
async def test_delete_file_subgraph_detach_deletes_file_and_symbols():
    class Driver:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        async def execute_query(self, query, **params):
            self.calls.append((query, params))
            return ([], None, None)

    driver = Driver()
    await neo4j_projector.delete_file_subgraph(driver, "ek-file-1")
    query, params = driver.calls[0]
    assert "DETACH DELETE" in query
    assert "File {entity_key: $ek}" in query
    assert params == {"ek": "ek-file-1"}
