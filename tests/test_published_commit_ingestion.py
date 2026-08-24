from __future__ import annotations

import pytest

from scripts import published_commit_ingestion


class ToolStub:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def __call__(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_ingestion_submission_uses_exact_published_shape_and_waits_for_memory_head() -> None:
    tool = ToolStub([
        {"status": "success", "data": {"repositories": []}},
        {"status": "submitted", "data": {"job_id": "job-1"}},
        {"status": "success", "data": {
            "job_id": "job-1", "state_code": "running",
            "repository_key": "memory-knowledge", "commit_sha": "abc123",
            "branch_name": "main",
        }},
        {"status": "success", "data": {
            "job_id": "job-1", "state_code": "completed",
            "repository_key": "memory-knowledge", "commit_sha": "abc123",
            "branch_name": "main",
            "checkpoint_data": {"status": "success"},
        }},
        {"status": "success", "data": {"repositories": [{
            "repository_key": "memory-knowledge", "latest_commit": "abc123",
            "latest_branch": "main", "last_ingestion_status": "success",
        }]}},
    ])

    result = await published_commit_ingestion.verify(
        tool,
        repository_key="memory-knowledge",
        branch_name="main",
        commit_sha="abc123",
        poll_interval_seconds=0,
        timeout_seconds=1,
    )

    assert tool.calls[1] == (
        "run_repo_ingestion_workflow",
        {
            "repository_key": "memory-knowledge",
            "branch_name": "main",
            "commit_sha": "abc123",
        },
    )
    assert [name for name, _ in tool.calls] == [
        "list_repositories",
        "run_repo_ingestion_workflow",
        "check_job_status",
        "check_job_status",
        "list_repositories",
    ]
    assert result["verified"] is True
    assert result["jobId"] == "job-1"
    assert result["memoryCommit"] == "abc123"


@pytest.mark.asyncio
async def test_already_ingested_commit_does_not_start_duplicate_ingestion() -> None:
    tool = ToolStub([{
        "status": "success", "data": {"repositories": [{
            "repository_key": "memory-knowledge", "latest_commit": "abc123",
            "latest_branch": "main", "last_ingestion_status": "success",
        }]},
    }])

    result = await published_commit_ingestion.verify(
        tool,
        repository_key="memory-knowledge",
        branch_name="main",
        commit_sha="abc123",
        poll_interval_seconds=0,
        timeout_seconds=1,
    )

    assert [name for name, _ in tool.calls] == ["list_repositories"]
    assert result["verified"] is True
    assert result["alreadyReady"] is True


@pytest.mark.asyncio
async def test_completed_partial_ingestion_is_not_accepted() -> None:
    tool = ToolStub([
        {"status": "success", "data": {"repositories": []}},
        {"status": "submitted", "data": {"job_id": "job-1"}},
        {"status": "success", "data": {
            "job_id": "job-1", "state_code": "completed",
            "repository_key": "memory-knowledge", "commit_sha": "abc123",
            "branch_name": "main",
            "checkpoint_data": {"status": "partial"},
        }},
    ])

    with pytest.raises(
        published_commit_ingestion.IngestionVerificationError,
        match="ingestion-workflow-status:partial",
    ):
        await published_commit_ingestion.verify(
            tool,
            repository_key="memory-knowledge",
            branch_name="main",
            commit_sha="abc123",
            poll_interval_seconds=0,
            timeout_seconds=1,
        )


@pytest.mark.asyncio
async def test_completed_job_with_wrong_shape_is_not_accepted() -> None:
    tool = ToolStub([
        {"status": "success", "data": {"repositories": []}},
        {"status": "submitted", "data": {"job_id": "job-1"}},
        {"status": "success", "data": {
            "job_id": "job-1", "state_code": "completed",
            "repository_key": "memory-knowledge", "commit_sha": "different",
            "branch_name": "main", "checkpoint_data": {"status": "success"},
        }},
    ])

    with pytest.raises(
        published_commit_ingestion.IngestionVerificationError,
        match="ingestion-job-shape-mismatch",
    ):
        await published_commit_ingestion.verify(
            tool,
            repository_key="memory-knowledge",
            branch_name="main",
            commit_sha="abc123",
            poll_interval_seconds=0,
            timeout_seconds=1,
        )


@pytest.mark.asyncio
async def test_completed_job_is_not_enough_when_memory_head_is_another_commit() -> None:
    tool = ToolStub([
        {"status": "success", "data": {"repositories": []}},
        {"status": "submitted", "data": {"job_id": "job-1"}},
        {"status": "success", "data": {
            "job_id": "job-1", "state_code": "completed",
            "repository_key": "memory-knowledge", "commit_sha": "abc123",
            "branch_name": "main", "checkpoint_data": {"status": "success"},
        }},
        {"status": "success", "data": {"repositories": [{
            "repository_key": "memory-knowledge", "latest_commit": "older",
            "latest_branch": "main", "last_ingestion_status": "success",
        }]}},
    ])

    with pytest.raises(
        published_commit_ingestion.IngestionVerificationError,
        match="published-commit-not-memory-visible",
    ):
        await published_commit_ingestion.verify(
            tool,
            repository_key="memory-knowledge",
            branch_name="main",
            commit_sha="abc123",
            poll_interval_seconds=0,
            timeout_seconds=1,
        )
