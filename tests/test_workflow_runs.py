import json
import uuid
from types import SimpleNamespace

import pytest

from memory_knowledge import server


class FakePool:
    def __init__(self):
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.fetch_calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "FROM catalog.repositories WHERE repository_key = $1" in query:
            return {"id": 7}
        if "SELECT workflow_name FROM ops.workflow_runs WHERE run_id = $1" in query:
            return None
        if "FROM core.reference_values rv" in query and "WHERE rt.internal_code = $1 AND rv.internal_code = $2" in query:
            type_code, value_code = args
            if type_code == server.WORKFLOW_RUN_STATUS_TYPE and value_code == "RUN_RUNNING":
                return {
                    "id": 11,
                    "internal_code": "RUN_RUNNING",
                    "display_name": "Running",
                    "is_terminal": False,
                }
            if type_code == server.WORKFLOW_RUN_STATUS_TYPE and value_code == server.DEFAULT_WORKFLOW_RUN_STATUS:
                return {
                    "id": 10,
                    "internal_code": server.DEFAULT_WORKFLOW_RUN_STATUS,
                    "display_name": "Pending",
                    "is_terminal": False,
                }
            return None
        if "INSERT INTO ops.workflow_runs" in query:
            return {"id": 1, "is_insert": True, "status_id": args[4] or args[12]}
        if "SELECT wr.id, wr.repository_id, wr.run_id" in query:
            return {"id": 1, "repository_id": 7, "run_id": uuid.UUID(str(args[0])) if isinstance(args[0], str) else args[0]}
        if "FROM ops.workflow_phase_states" in query and "SELECT 1" in query:
            return {"exists": 1}
        if "INSERT INTO ops.workflow_phase_states" in query:
            return {"phase_id": args[1]}
        if "INSERT INTO ops.workflow_validator_results" in query:
            return {"phase_id": args[1], "validator_code": args[2], "attempt_number": args[4]}
        if "FROM core.reference_types WHERE internal_code = $1" in query:
            return {"id": 101} if args[0] == "WORKFLOW_RUN_STATUS" else None
        return None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        if "FROM core.reference_values rv" in query and "WHERE rv.reference_type_id = $1" in query:
            return [
                {
                    "id": 10,
                    "internal_code": "RUN_PENDING",
                    "display_name": "Pending",
                    "description": None,
                    "sort_order": 10,
                    "is_active": True,
                    "is_terminal": False,
                },
                {
                    "id": 11,
                    "internal_code": "RUN_RUNNING",
                    "display_name": "Running",
                    "description": None,
                    "sort_order": 20,
                    "is_active": True,
                    "is_terminal": False,
                },
            ]
        if "FROM ops.workflow_runs wr" in query and "WHERE wr.actor_email = $1" in query:
            actor_email, include_terminal, _limit = args
            rows = [
                {
                    "workflow_run_id": 1,
                    "run_id": uuid.uuid4(),
                    "repository_key": "repo-a",
                    "workflow_name": "wf-a",
                    "task_description": "recover me",
                    "status_id": 11,
                    "status_code": "RUN_RUNNING",
                    "status_display_name": "Running",
                    "is_terminal": False,
                    "current_phase": "phase-a",
                    "iteration_count": 2,
                    "started_utc": None,
                    "completed_utc": None,
                    "artifact_count": 3,
                },
                {
                    "workflow_run_id": 2,
                    "run_id": uuid.uuid4(),
                    "repository_key": "repo-a",
                    "workflow_name": "wf-b",
                    "task_description": "done",
                    "status_id": 12,
                    "status_code": "RUN_SUCCESS",
                    "status_display_name": "Success",
                    "is_terminal": True,
                    "current_phase": "phase-b",
                    "iteration_count": 1,
                    "started_utc": None,
                    "completed_utc": None,
                    "artifact_count": 1,
                },
            ]
            return rows if include_terminal else [r for r in rows if not r["is_terminal"]]
        if "FROM planning.task_workflow_runs twr" in query and "WHERE twr.workflow_run_id = ANY" in query:
            return [
                {
                    "workflow_run_id": 1,
                    "task_key": uuid.uuid4(),
                    "task_title": "Recover task",
                    "feature_key": uuid.uuid4(),
                    "feature_title": "Recover feature",
                    "project_key": uuid.uuid4(),
                    "project_name": "Recover project",
                }
            ]
        if "FROM ops.workflow_phase_states" in query and "ORDER BY id" in query:
            return [
                {
                    "phase_id": "phase-a",
                    "status": "running",
                    "decision": "continue",
                    "attempts": 1,
                    "started_utc": None,
                    "completed_utc": None,
                    "error_text": None,
                    "metrics_json": {"tokens": 3},
                }
            ]
        if "FROM ops.workflow_artifacts" in query and "ORDER BY id" in query:
            return [
                {
                    "artifact_name": "analysis.md",
                    "artifact_type": "markdown",
                    "iteration": 1,
                    "is_final": True,
                    "updated_utc": None,
                }
            ]
        if "FROM ops.workflow_validator_results wvr" in query:
            return [
                {
                    "phase_id": "validate",
                    "validator_code": "OUTPUT_CONTRACT",
                    "validator_name": "Output Contract",
                    "attempt_number": 1,
                    "status_code": "VAL_PASSED",
                    "failure_reason_code": None,
                    "failure_reason": None,
                    "details_json": {"ok": True},
                    "started_utc": None,
                    "completed_utc": None,
                    "created_utc": None,
                }
            ]
        return []


@pytest.fixture
def fake_pool(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)
    return pool


@pytest.mark.asyncio
async def test_save_workflow_run_resolves_status_code_and_actor_email(fake_pool):
    result = await server.save_workflow_run(
        repository_key="repo-a",
        run_id=str(uuid.uuid4()),
        workflow_name="wf-a",
        status_code="RUN_RUNNING",
        actor_email="user@example.com",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["status"] == "running"
    assert payload["data"]["status_code"] == "RUN_RUNNING"
    insert_query, insert_args = next(
        (q, a) for q, a in fake_pool.fetchrow_calls if "INSERT INTO ops.workflow_runs" in q
    )
    assert "status_id, actor_email" in insert_query
    assert insert_args[5] == "user@example.com"


@pytest.mark.asyncio
async def test_save_workflow_run_accepts_legacy_status_input(fake_pool):
    result = await server.save_workflow_run(
        repository_key="repo-a",
        run_id=str(uuid.uuid4()),
        workflow_name="wf-a",
        status="running",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["status"] == "running"
    assert payload["data"]["status_code"] == "RUN_RUNNING"


@pytest.mark.asyncio
async def test_save_workflow_run_does_not_reset_status_on_partial_update(fake_pool):
    original_fetchrow = fake_pool.fetchrow

    async def fake_fetchrow(query, *args):
        if "SELECT workflow_name FROM ops.workflow_runs WHERE run_id = $1" in query:
            return {"workflow_name": "wf-existing"}
        return await original_fetchrow(query, *args)

    fake_pool.fetchrow = fake_fetchrow
    result = await server.save_workflow_run(
        repository_key="repo-a",
        run_id=str(uuid.uuid4()),
        current_phase="phase-b",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    insert_query, insert_args = next(
        (q, a) for q, a in fake_pool.fetchrow_calls if "INSERT INTO ops.workflow_runs" in q
    )
    assert "COALESCE($5::bigint, $13::bigint)" in insert_query
    assert insert_args[4] is None
    assert insert_args[12] == 10
    assert payload["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_save_workflow_run_requires_workflow_name_on_first_write(fake_pool):
    result = await server.save_workflow_run(
        repository_key="repo-a",
        run_id=str(uuid.uuid4()),
        current_phase="phase-a",
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "workflow_name is required on first workflow-run write" in payload["error"]


@pytest.mark.asyncio
async def test_list_reference_values_returns_lookup_rows(fake_pool):
    result = await server.list_reference_values("WORKFLOW_RUN_STATUS")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["count"] == 2
    assert payload["data"]["values"][0]["internal_code"] == "RUN_PENDING"


@pytest.mark.asyncio
async def test_list_workflow_runs_by_actor_filters_terminal_by_default(fake_pool):
    result = await server.list_workflow_runs_by_actor("user@example.com")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["count"] == 1
    assert payload["data"]["runs"][0]["status_code"] == "RUN_RUNNING"
    assert payload["data"]["runs"][0]["planning_context"]["tasks"][0]["task_title"] == "Recover task"
    assert payload["data"]["runs"][0]["planning_context"]["features"][0]["feature_title"] == "Recover feature"
    assert payload["data"]["runs"][0]["planning_context"]["projects"][0]["project_name"] == "Recover project"


@pytest.mark.asyncio
async def test_list_workflow_runs_by_actor_can_include_terminal(fake_pool):
    result = await server.list_workflow_runs_by_actor("user@example.com", include_terminal=True)
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["count"] == 2


@pytest.mark.asyncio
async def test_list_workflow_runs_by_actor_dedupes_nested_planning_context_by_key(fake_pool):
    original_fetch = fake_pool.fetch

    async def fake_fetch(query, *args):
        if "FROM planning.task_workflow_runs twr" in query and "WHERE twr.workflow_run_id = ANY" in query:
            task_key = uuid.uuid4()
            feature_key = uuid.uuid4()
            project_key = uuid.uuid4()
            return [
                {
                    "workflow_run_id": 1,
                    "task_key": task_key,
                    "task_title": "Recover task",
                    "feature_key": feature_key,
                    "feature_title": "Recover feature",
                    "project_key": project_key,
                    "project_name": "Recover project",
                },
                {
                    "workflow_run_id": 1,
                    "task_key": task_key,
                    "task_title": "Recover task",
                    "feature_key": feature_key,
                    "feature_title": "Recover feature",
                    "project_key": project_key,
                    "project_name": "Recover project",
                },
            ]
        return await original_fetch(query, *args)

    fake_pool.fetch = fake_fetch
    result = await server.list_workflow_runs_by_actor("user@example.com")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["count"] == 1
    planning_context = payload["data"]["runs"][0]["planning_context"]
    assert len(planning_context["tasks"]) == 1
    assert len(planning_context["features"]) == 1
    assert len(planning_context["projects"]) == 1


@pytest.mark.asyncio
async def test_list_workflow_runs_preserves_legacy_status_field(fake_pool):
    async def fake_fetch(query, *args):
        return [
            {
                "run_id": uuid.uuid4(),
                "workflow_name": "wf-a",
                "status_code": "RUN_RUNNING",
                "status_display_name": "Running",
                "is_terminal": False,
                "iteration_count": 1,
                "started_utc": None,
                "completed_utc": None,
                "artifact_count": 0,
            }
        ]

    fake_pool.fetch = fake_fetch
    result = await server.list_workflow_runs("repo-a")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["runs"][0]["status"] == "running"
    assert payload["data"]["runs"][0]["status_code"] == "RUN_RUNNING"


@pytest.mark.asyncio
async def test_save_workflow_phase_state_persists_sparse_upsert(fake_pool):
    result = await server.save_workflow_phase_state(
        run_id=str(uuid.uuid4()),
        phase_id="validate",
        status="running",
        attempts=1,
        metrics_json={"tokens": 5},
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["phase_id"] == "validate"
    insert_query, insert_args = next(
        (q, a) for q, a in fake_pool.fetchrow_calls if "INSERT INTO ops.workflow_phase_states" in q
    )
    assert "COALESCE($6, 1)" in insert_query
    assert json.loads(insert_args[9]) == {"tokens": 5}


@pytest.mark.asyncio
async def test_save_workflow_validator_result_rejects_unknown_validator(fake_pool):
    result = await server.save_workflow_validator_result(
        run_id=str(uuid.uuid4()),
        phase_id="validate",
        validator_code="UNKNOWN",
        validator_name="Unknown",
        attempt_number=1,
        status_code="VAL_PASSED",
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "Invalid validator_code" in payload["error"]


@pytest.mark.asyncio
async def test_get_workflow_run_includes_validator_results(fake_pool):
    async def fake_fetchrow(query, *args):
        if "FROM ops.workflow_runs wr" in query:
            return {
                "run_id": uuid.uuid4(),
                "repository_key": "repo-a",
                "workflow_name": "wf-a",
                "task_description": "task",
                "status_code": "RUN_RUNNING",
                "status_display_name": "Running",
                "is_terminal": False,
                "actor_email": "user@example.com",
                "current_phase": "validate",
                "iteration_count": 1,
                "context_json": None,
                "started_utc": None,
                "completed_utc": None,
                "error_text": None,
            }
        return await FakePool().fetchrow(query, *args)

    fake_pool.fetchrow = fake_fetchrow
    result = await server.get_workflow_run(str(uuid.uuid4()))
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["validator_results"][0]["validator_code"] == "OUTPUT_CONTRACT"
    assert payload["data"]["phases"][0]["metrics_json"] == {"tokens": 3}
