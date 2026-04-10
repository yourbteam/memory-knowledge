import json
import uuid

import pytest

from memory_knowledge.jobs import job_worker
from memory_knowledge.workflows.base import WorkflowResult


@pytest.mark.asyncio
async def test_execute_job_marks_failed_when_workflow_returns_error(monkeypatch):
    transitions: list[tuple[str, dict[str, str | None]]] = []

    async def fake_update_job_state(pool, job_id, state_code, checkpoint_data=None, error_code=None, error_text=None):
        transitions.append(
            (
                state_code,
                {
                    "checkpoint_data": checkpoint_data,
                    "error_code": error_code,
                    "error_text": error_text,
                },
            )
        )

    async def fake_job_fn(**kwargs):
        return WorkflowResult(
            run_id=str(uuid.uuid4()),
            tool_name="run_repo_ingestion_workflow",
            status="error",
            error="clone failed",
        )

    monkeypatch.setattr(job_worker, "update_job_state", fake_update_job_state)

    result = await job_worker.execute_job(
        manifest_pool=object(),
        job_id=uuid.uuid4(),
        job_fn=fake_job_fn,
        worker_settings=type("Settings", (), {"job_retry_delay_seconds": 0.01})(),
    )

    assert result.status == "error"
    assert [state for state, _meta in transitions] == ["running", "failed"]
    failed_meta = transitions[-1][1]
    assert failed_meta["error_text"] == "clone failed"
    assert json.loads(failed_meta["checkpoint_data"])["status"] == "error"
