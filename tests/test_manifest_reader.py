import json

import pytest

from memory_knowledge.jobs import manifest_reader


@pytest.mark.asyncio
async def test_get_latest_resume_checkpoint_returns_nested_checkpoint():
    class Pool:
        async def fetchrow(self, query, *args):
            assert "ORDER BY created_utc DESC" in query
            assert args == ("repo-a", "abc123", "main", "run_repo_ingestion_workflow")
            return {
                "checkpoint_data": json.dumps(
                    {
                        "checkpoint": {
                            "phase": "chunk_embeddings_complete",
                            "files_processed": 42,
                        }
                    }
                )
            }

    checkpoint = await manifest_reader.get_latest_resume_checkpoint(
        Pool(),
        repository_key="repo-a",
        commit_sha="abc123",
        branch_name="main",
        tool_name="run_repo_ingestion_workflow",
    )

    assert checkpoint == {
        "phase": "chunk_embeddings_complete",
        "files_processed": 42,
    }


@pytest.mark.asyncio
async def test_get_active_job_for_shape_returns_pending_or_running_job():
    class Pool:
        def __init__(self):
            self.query = None
            self.args = None

        async def fetchrow(self, query, *args):
            self.query = query
            self.args = args
            return {"job_id": "job-1", "state_code": "running"}

    pool = Pool()

    result = await manifest_reader.get_active_job_for_shape(
        pool,
        repository_key="millennium-wp",
        commit_sha="abc",
        branch_name="main",
        tool_name="run_repo_ingestion_workflow",
    )

    assert result == {"job_id": "job-1", "state_code": "running"}
    assert "state_code IN ('pending', 'running')" in pool.query
    assert pool.args == (
        "millennium-wp",
        "abc",
        "main",
        "run_repo_ingestion_workflow",
    )
