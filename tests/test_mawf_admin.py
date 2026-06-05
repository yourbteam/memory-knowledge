import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from memory_knowledge.admin import mawf


class MawfAdminPool:
    def __init__(self):
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "FROM core.reference_values rv" in query and "rt.internal_code = $1" in query:
            type_code, value_code = args
            values = {
                ("TASK_STATUS", "active"): {
                    "id": 10,
                    "internal_code": "TASK_TODO",
                    "mawf_code": "active",
                    "display_name": "Active",
                    "description": None,
                    "sort_order": 10,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("PRIORITY", "PRIO_MEDIUM"): {
                    "id": 11,
                    "internal_code": "PRIO_MEDIUM",
                    "mawf_code": None,
                    "display_name": "Medium",
                    "description": None,
                    "sort_order": 10,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("ARTIFACT_ROLE", "task_ledger"): {
                    "id": 12,
                    "internal_code": "ARTIFACT_TASK_LEDGER",
                    "mawf_code": "task_ledger",
                    "display_name": "Task Ledger",
                    "description": None,
                    "sort_order": 10,
                    "is_active": True,
                    "is_terminal": False,
                },
            }
            return values.get((type_code, value_code))
        if "SELECT id FROM core.reference_types WHERE internal_code = $1" in query:
            return {"id": 77}
        if "SELECT id FROM catalog.repositories WHERE mawf_repository_id = $1::uuid" in query:
            return {"id": 200}
        if "FROM planning.projects p" in query and "p.project_key = $1::uuid" in query:
            return {
                "id": 100,
                "project_key": args[0],
                "mawf_project_key": "proj-a",
                "name": "Project A",
                "project_status_id": 1,
                "created_utc": None,
                "updated_utc": None,
                "status_code": "active",
            }
        if "WHERE external_task_id = $1" in query:
            return None
        if "UPDATE planning.tasks" in query and "WHERE mawf_task_id = $1" in query:
            return None
        if "INSERT INTO planning.tasks" in query:
            return {"id": 300}
        if "FROM planning.tasks t" in query and "t.mawf_task_id = $1" in query:
            return {
                "mawf_task_id": args[0] or "task-a",
                "external_task_id": "ABC-123",
                "owner_user_id": uuid.uuid4(),
                "project_key": uuid.uuid4(),
                "mawf_repository_id": uuid.uuid4(),
                "prompt_id": uuid.uuid4(),
                "title": "Task A",
                "task_status_id": 10,
                "task_ledger_ref": "ledger://task-a",
                "task_artifact_branch": "artifact/task-a",
                "created_utc": None,
                "updated_utc": None,
                "status_code": "active",
            }
        return None

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class ArtifactAdminPool:
    def __init__(self, *, role_rows=None):
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.fetch_calls: list[tuple[str, tuple]] = []
        self.role_rows = role_rows or []
        self.artifact_id = uuid.uuid4()
        self.existing_ref_task_id = "task-a"
        self.raise_unique_on_insert = False
        self.update_after_conflict = False

    def acquire(self):
        return self

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "FROM core.reference_values rv" in query and "rt.internal_code = $1" in query:
            values = {
                ("ARTIFACT_ROLE", "task_ledger"): {
                    "id": 12,
                    "internal_code": "ARTIFACT_TASK_LEDGER",
                    "mawf_code": "task_ledger",
                    "display_name": "Task Ledger",
                    "description": None,
                    "sort_order": 10,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("ARTIFACT_ROLE", "workflow_ledger"): {
                    "id": 13,
                    "internal_code": "ARTIFACT_WORKFLOW_LEDGER",
                    "mawf_code": "workflow_ledger",
                    "display_name": "Workflow Ledger",
                    "description": None,
                    "sort_order": 20,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("ARTIFACT_PERSIST_STATUS", "local_only"): {
                    "id": 60,
                    "internal_code": "ARTIFACT_LOCAL_ONLY",
                    "mawf_code": "local_only",
                    "display_name": "Local Only",
                    "description": None,
                    "sort_order": 10,
                    "is_active": True,
                    "is_terminal": False,
                },
            }
            return values.get((args[0], args[1]))
        if "SELECT id, mawf_task_id" in query and "FROM planning.mawf_artifact_refs" in query:
            return {"id": args[0], "mawf_task_id": self.existing_ref_task_id}
        if "UPDATE planning.mawf_artifact_refs" in query and "WHERE id = $1::uuid" in query:
            return {"id": args[0]}
        if "UPDATE planning.mawf_artifact_refs" in query and "AND artifact_key = $2" in query:
            if self.update_after_conflict:
                return {"id": self.artifact_id}
            return None
        if "UPDATE planning.mawf_artifact_refs" in query and "AND artifact_key IS NULL" in query:
            if self.update_after_conflict:
                return {"id": self.artifact_id}
            return None
        if "INSERT INTO planning.mawf_artifact_refs" in query:
            if self.raise_unique_on_insert:
                self.raise_unique_on_insert = False
                self.update_after_conflict = True
                raise mawf.asyncpg.UniqueViolationError("duplicate")
            return {"id": self.artifact_id}
        if "WHERE ar.id = $1::uuid" in query:
            return {
                "id": args[0],
                "mawf_task_id": "task-a",
                "artifact_key": "workflow:run-a:ledger",
                "artifact_branch": "artifact/task-a",
                "role_id": 13,
                "role_code": "workflow_ledger",
                "artifact_path": "repo://workflow-ledger.json",
                "content_hash": None,
                "persist_status_id": 60,
                "persist_status_code": "local_only",
                "created_utc": None,
                "updated_utc": None,
            }
        if "WHERE ar.mawf_task_id = $1" in query and "AND ar.artifact_key = $2" in query:
            return {
                "id": self.artifact_id,
                "mawf_task_id": args[0],
                "artifact_key": args[1],
                "artifact_branch": "artifact/task-a",
                "role_id": 13,
                "role_code": "workflow_ledger",
                "artifact_path": "repo://workflow-ledger.json",
                "content_hash": None,
                "persist_status_id": 60,
                "persist_status_code": "local_only",
                "created_utc": None,
                "updated_utc": None,
            }
        return None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self.role_rows


class WorkflowRunsByUserPool:
    def __init__(self, *, user_exists=True, run_rows=None):
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.fetch_calls: list[tuple[str, tuple]] = []
        self.user_exists = user_exists
        self.run_rows = run_rows or []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "SELECT id FROM core.users WHERE id = $1::uuid" in query:
            return {"id": args[0]} if self.user_exists else None
        if "FROM core.reference_values rv" in query and "rt.internal_code = $1" in query:
            values = {
                ("WORKFLOW_RUN_STATUS", "RUN_PENDING"): {
                    "id": 900,
                    "internal_code": "RUN_PENDING",
                    "mawf_code": "queued",
                    "display_name": "Queued",
                    "description": None,
                    "sort_order": 10,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("WORKFLOW_RUN_STATUS", "queued"): {
                    "id": 900,
                    "internal_code": "RUN_PENDING",
                    "mawf_code": "queued",
                    "display_name": "Queued",
                    "description": None,
                    "sort_order": 10,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("WORKFLOW_RUN_STATUS", "RUN_RUNNING"): {
                    "id": 901,
                    "internal_code": "RUN_RUNNING",
                    "mawf_code": "running",
                    "display_name": "Running",
                    "description": None,
                    "sort_order": 30,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("WORKFLOW_RUN_STATUS", "running"): {
                    "id": 901,
                    "internal_code": "RUN_RUNNING",
                    "mawf_code": "running",
                    "display_name": "Running",
                    "description": None,
                    "sort_order": 30,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("WORKFLOW_RUN_STATUS", "RUN_WAITING_FOR_FEEDBACK"): {
                    "id": 902,
                    "internal_code": "RUN_WAITING_FOR_FEEDBACK",
                    "mawf_code": "waiting_for_feedback",
                    "display_name": "Waiting For Feedback",
                    "description": None,
                    "sort_order": 35,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("WORKFLOW_RUN_STATUS", "waiting_for_feedback"): {
                    "id": 902,
                    "internal_code": "RUN_WAITING_FOR_FEEDBACK",
                    "mawf_code": "waiting_for_feedback",
                    "display_name": "Waiting For Feedback",
                    "description": None,
                    "sort_order": 35,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("WORKFLOW_RUN_STATUS", "RUN_RESUME_PENDING"): {
                    "id": 903,
                    "internal_code": "RUN_RESUME_PENDING",
                    "mawf_code": "resume_pending",
                    "display_name": "Resume Pending",
                    "description": None,
                    "sort_order": 36,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("WORKFLOW_RUN_STATUS", "resume_pending"): {
                    "id": 903,
                    "internal_code": "RUN_RESUME_PENDING",
                    "mawf_code": "resume_pending",
                    "display_name": "Resume Pending",
                    "description": None,
                    "sort_order": 36,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("WORKFLOW_RUN_STATUS", "RUN_SUCCESS"): {
                    "id": 904,
                    "internal_code": "RUN_SUCCESS",
                    "mawf_code": "completed",
                    "display_name": "Success",
                    "description": None,
                    "sort_order": 80,
                    "is_active": True,
                    "is_terminal": True,
                },
                ("WORKFLOW_RUN_STATUS", "completed"): {
                    "id": 904,
                    "internal_code": "RUN_SUCCESS",
                    "mawf_code": "completed",
                    "display_name": "Success",
                    "description": None,
                    "sort_order": 80,
                    "is_active": True,
                    "is_terminal": True,
                },
            }
            return values.get((args[0], args[1]))
        return None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self.run_rows


class WorkflowRunUpsertPool:
    def __init__(self):
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []
        self.context_json = {}
        self.run_uuid = None

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "FROM planning.tasks t" in query and "WHERE t.mawf_task_id = $1" in query:
            return {
                "id": 300,
                "mawf_task_id": args[0],
                "repository_id": 200,
                "title": "Task A",
                "actor_email": "user@example.com",
            }
        if "FROM core.reference_values rv" in query and "rt.internal_code = $1" in query:
            return {
                "id": 900,
                "internal_code": "RUN_PENDING",
                "mawf_code": "queued",
                "display_name": "Queued",
                "description": None,
                "sort_order": 10,
                "is_active": True,
                "is_terminal": False,
            }
        if "INSERT INTO ops.workflow_runs" in query:
            self.run_uuid = args[0]
            self.context_json = json.loads(args[9])
            return {"id": 400}
        if "FROM ops.workflow_runs wr" in query and "WHERE wr.run_id = $1" in query:
            return {
                "run_id": args[0],
                "mawf_task_id": "task-a",
                "workflow_name": "full-task-workflow",
                "context_json": self.context_json,
                "status_code": "RUN_PENDING",
                "status_display_name": "Queued",
                "is_terminal": False,
                "actor_email": "user@example.com",
                "current_phase": None,
                "iteration_count": 0,
                "started_utc": None,
                "completed_utc": None,
                "error_text": None,
                "relation_type": "implements",
            }
        return None

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


def _workflow_run_user_row(*, status_code="RUN_RUNNING", is_terminal=False):
    now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
    return {
        "run_id": mawf._workflow_run_uuid("run-a"),
        "mawf_task_id": "task-a",
        "task_title": "Task A",
        "owner_user_id": uuid.UUID("00000000-0000-0000-0000-000000000123"),
        "task_ledger_ref": "repo://task-ledger.json",
        "workflow_name": "full-task-workflow",
        "context_json": {
            "mawf_workflow_run_id": "run-a",
            "mawf_attempt": 2,
            "workflow_ledger_ref": "repo://ledger.json",
            "workflow_state_ref": "repo://state.json",
            "task_artifact_branch": "artifact/task-a",
        },
        "status_code": status_code,
        "status_display_name": "Running",
        "is_terminal": is_terminal,
        "actor_email": "user@example.com",
        "started_utc": now - timedelta(minutes=10),
        "completed_utc": None,
        "updated_utc": now,
        "last_heartbeat_utc": now - timedelta(minutes=1),
    }


@pytest.mark.asyncio
async def test_deactivate_catalog_value_preserves_catalog_type_id():
    pool = MawfAdminPool()
    result = await mawf.deactivate_catalog_value(pool, "ARTIFACT_ROLE", "task_ledger")
    assert result["catalog_type_id"] == 77
    assert result["catalog_type_code"] == "ARTIFACT_ROLE"
    assert result["is_active"] is False


@pytest.mark.asyncio
async def test_upsert_task_links_project_repository_before_task_write():
    pool = MawfAdminPool()
    await mawf.upsert_task(
        pool,
        task_id="task-a",
        owner_user_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt_id=str(uuid.uuid4()),
        title="Task A",
        task_ledger_ref="ledger://task-a",
    )
    link_calls = [call for call in pool.execute_calls if "INSERT INTO planning.project_repositories" in call[0]]
    assert link_calls
    assert link_calls[0][1] == (100, 200)


@pytest.mark.asyncio
async def test_upsert_task_accepts_external_task_id_and_normalizes_blank():
    pool = MawfAdminPool()
    result = await mawf.upsert_task(
        pool,
        task_id="task-a",
        owner_user_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt_id=str(uuid.uuid4()),
        title="Task A",
        task_ledger_ref="ledger://task-a",
        external_task_id=" ABC-123 ",
        task_artifact_branch=" artifact/task-a ",
    )

    duplicate_query, duplicate_args = next(
        (query, args) for query, args in pool.fetchrow_calls if "WHERE external_task_id = $1" in query
    )
    assert "mawf_task_id IS DISTINCT FROM $2" in duplicate_query
    assert duplicate_args == ("ABC-123", "task-a")
    update_query, update_args = next(
        (query, args) for query, args in pool.fetchrow_calls if "UPDATE planning.tasks" in query
    )
    assert "external_task_id = $10" in update_query
    assert "task_artifact_branch = $11" in update_query
    assert update_args[9] == "ABC-123"
    assert update_args[10] == "artifact/task-a"
    assert result["external_task_id"] == "ABC-123"
    assert result["task_artifact_branch"] == "artifact/task-a"
    assert result["taskArtifactBranch"] == "artifact/task-a"

    blank_pool = MawfAdminPool()
    await mawf.upsert_task(
        blank_pool,
        task_id="task-a",
        owner_user_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        prompt_id=str(uuid.uuid4()),
        title="Task A",
        task_ledger_ref="ledger://task-a",
        external_task_id=" ",
        task_artifact_branch=" ",
    )
    assert not any("WHERE external_task_id = $1" in query for query, _ in blank_pool.fetchrow_calls)
    blank_update_args = next(args for query, args in blank_pool.fetchrow_calls if "UPDATE planning.tasks" in query)
    assert blank_update_args[9] is None
    assert blank_update_args[10] is None


@pytest.mark.asyncio
async def test_upsert_task_rejects_duplicate_external_task_id():
    class DuplicateExternalTaskPool(MawfAdminPool):
        async def fetchrow(self, query, *args):
            if "WHERE external_task_id = $1" in query:
                return {"mawf_task_id": "other-task"}
            return await super().fetchrow(query, *args)

    with pytest.raises(ValueError, match="external_task_id already belongs"):
        await mawf.upsert_task(
            DuplicateExternalTaskPool(),
            task_id="task-a",
            owner_user_id=str(uuid.uuid4()),
            project_id=str(uuid.uuid4()),
            repository_id=str(uuid.uuid4()),
            prompt_id=str(uuid.uuid4()),
            title="Task A",
            task_ledger_ref="ledger://task-a",
            external_task_id="ABC-123",
        )


@pytest.mark.asyncio
async def test_get_task_can_lookup_by_external_task_id():
    pool = MawfAdminPool()

    result = await mawf.get_task(pool, external_task_id=" ABC-123 ")

    query, args = pool.fetchrow_calls[-1]
    assert "t.external_task_id = $2" in query
    assert args == (None, "ABC-123")
    assert result["external_task_id"] == "ABC-123"
    assert result["task_artifact_branch"] == "artifact/task-a"
    assert result["taskArtifactBranch"] == "artifact/task-a"

    with pytest.raises(ValueError, match="task_id or external_task_id"):
        await mawf.get_task(pool)


@pytest.mark.asyncio
async def test_upsert_artifact_ref_uses_artifact_key_for_conflict_identity():
    pool = ArtifactAdminPool()
    result = await mawf.upsert_artifact_ref(
        pool,
        task_id="task-a",
        role_code="workflow_ledger",
        artifact_path="repo://workflow-ledger.json",
        artifact_key="workflow:run-a:ledger",
        artifact_branch="artifact/task-a",
    )

    update_query, update_args = [
        call
        for call in pool.fetchrow_calls
        if "UPDATE planning.mawf_artifact_refs" in call[0] and "AND artifact_key = $2" in call[0]
    ][0]
    assert "WHERE mawf_task_id = $1" in update_query
    assert update_args[0] == "task-a"
    assert update_args[1] == "workflow:run-a:ledger"
    insert_query, insert_args = [
        call for call in pool.fetchrow_calls if "INSERT INTO planning.mawf_artifact_refs" in call[0]
    ][0]
    assert "artifact_key" in insert_query
    assert "ON CONFLICT" not in insert_query
    assert insert_args[1] == "workflow:run-a:ledger"
    assert insert_args[2] == "artifact/task-a"
    assert result["artifact_key"] == "workflow:run-a:ledger"
    assert result["artifactKey"] == "workflow:run-a:ledger"
    assert result["artifact_branch"] == "artifact/task-a"
    assert result["artifactBranch"] == "artifact/task-a"


@pytest.mark.asyncio
async def test_upsert_artifact_ref_keeps_omitted_artifact_key_null():
    pool = ArtifactAdminPool()
    await mawf.upsert_artifact_ref(
        pool,
        task_id="task-a",
        role_code="task_ledger",
        artifact_path="repo://task-ledger.json",
        artifact_key=" ",
    )

    update_query, update_args = [
        call
        for call in pool.fetchrow_calls
        if "UPDATE planning.mawf_artifact_refs" in call[0] and "AND artifact_key IS NULL" in call[0]
    ][0]
    assert update_args[0] == "task-a"
    assert update_args[1] == 12
    _, insert_args = [call for call in pool.fetchrow_calls if "INSERT INTO planning.mawf_artifact_refs" in call[0]][0]
    assert insert_args[1] is None


@pytest.mark.asyncio
async def test_get_artifact_ref_role_lookup_filters_to_legacy_null_keys():
    row = {
        "id": uuid.uuid4(),
        "mawf_task_id": "task-a",
        "artifact_key": None,
        "artifact_branch": None,
        "role_id": 13,
        "role_code": "workflow_ledger",
        "artifact_path": "repo://workflow-ledger.json",
        "content_hash": None,
        "persist_status_id": 60,
        "persist_status_code": "local_only",
        "created_utc": None,
        "updated_utc": None,
    }
    pool = ArtifactAdminPool(role_rows=[row])

    result = await mawf.get_artifact_ref(pool, task_id="task-a", role_code="workflow_ledger")

    query, _ = pool.fetch_calls[0]
    assert "AND ar.artifact_key IS NULL" in query
    assert result["artifact_key"] is None


@pytest.mark.asyncio
async def test_upsert_artifact_ref_validates_id_task_before_update():
    pool = ArtifactAdminPool()
    pool.existing_ref_task_id = "other-task"

    with pytest.raises(ValueError, match="task_id does not match"):
        await mawf.upsert_artifact_ref(
            pool,
            task_id="task-a",
            role_code="workflow_ledger",
            artifact_path="repo://workflow-ledger.json",
            artifact_ref_id=str(uuid.uuid4()),
        )

    assert any("SELECT id, mawf_task_id" in query for query, _ in pool.fetchrow_calls)
    assert not any("UPDATE planning.mawf_artifact_refs" in query for query, _ in pool.fetchrow_calls)


@pytest.mark.asyncio
async def test_upsert_artifact_ref_retries_unique_race_by_updating_identity():
    pool = ArtifactAdminPool()
    pool.raise_unique_on_insert = True

    result = await mawf.upsert_artifact_ref(
        pool,
        task_id="task-a",
        role_code="workflow_ledger",
        artifact_path="repo://workflow-ledger.json",
        artifact_key="workflow:run-a:ledger",
    )

    keyed_updates = [
        call
        for call in pool.fetchrow_calls
        if "UPDATE planning.mawf_artifact_refs" in call[0] and "AND artifact_key = $2" in call[0]
    ]
    assert len(keyed_updates) == 2
    assert result["artifact_key"] == "workflow:run-a:ledger"


@pytest.mark.asyncio
async def test_upsert_workflow_run_stores_task_artifact_branch_in_context_json():
    pool = WorkflowRunUpsertPool()

    result = await mawf.upsert_workflow_run(
        pool,
        workflow_run_id="raw-run-a",
        task_id="task-a",
        workflow_name="full-task-workflow",
        workflow_ledger_ref="repo://ledger.json",
        workflow_state_ref="repo://state.json",
        task_artifact_branch=" artifact/task-a ",
    )

    assert pool.context_json["task_artifact_branch"] == "artifact/task-a"
    assert result["task_artifact_branch"] == "artifact/task-a"
    assert result["taskArtifactBranch"] == "artifact/task-a"


@pytest.mark.asyncio
async def test_upsert_workflow_run_omitted_task_artifact_branch_does_not_write_context_key():
    pool = WorkflowRunUpsertPool()

    result = await mawf.upsert_workflow_run(
        pool,
        workflow_run_id="raw-run-a",
        task_id="task-a",
        workflow_name="full-task-workflow",
        task_artifact_branch=" ",
    )

    assert "task_artifact_branch" not in pool.context_json
    assert result["task_artifact_branch"] is None
    assert result["taskArtifactBranch"] is None


@pytest.mark.asyncio
async def test_list_workflow_runs_by_user_validates_owner_and_returns_index_rows():
    owner_user_id = "00000000-0000-0000-0000-000000000123"
    pool = WorkflowRunsByUserPool(run_rows=[_workflow_run_user_row()])

    result = await mawf.list_workflow_runs_by_user(
        pool,
        owner_user_id=owner_user_id,
        workflow_name="full-task-workflow",
        status_code="running",
        terminal=False,
        limit=999,
        offset=5,
    )

    query, args = pool.fetch_calls[0]
    assert "planning.tasks t" in query
    assert "planning.task_workflow_runs" in query
    assert "ops.workflow_runs wr" in query
    assert "workflow_phase" not in query
    assert "workflow_artifacts" not in query
    assert args[0] == uuid.UUID(owner_user_id)
    assert args[1] == "full-task-workflow"
    assert args[2] == 901
    assert args[3] is False
    assert args[6] == 500
    assert args[7] == 5
    assert result[0]["workflow_run_id"] == "run-a"
    assert result[0]["canonical_run_id"] == str(mawf._workflow_run_uuid("run-a"))
    assert result[0]["task_id"] == "task-a"
    assert result[0]["task_title"] == "Task A"
    assert result[0]["owner_user_id"] == owner_user_id
    assert result[0]["attempt"] == 2
    assert result[0]["status_code"] == "running"
    assert result[0]["workflow_ledger_ref"] == "repo://ledger.json"
    assert result[0]["workflow_state_ref"] == "repo://state.json"
    assert result[0]["task_artifact_branch"] == "artifact/task-a"
    assert result[0]["taskArtifactBranch"] == "artifact/task-a"
    assert "current_phase" not in result[0]
    assert "error_text" not in result[0]


@pytest.mark.asyncio
async def test_list_workflow_runs_by_user_active_only_conflict_and_offset_validation():
    pool = WorkflowRunsByUserPool()

    with pytest.raises(ValueError, match="conflicts"):
        await mawf.list_workflow_runs_by_user(
            pool,
            owner_user_id="00000000-0000-0000-0000-000000000123",
            active_only=True,
            terminal=True,
        )
    with pytest.raises(ValueError, match="offset"):
        await mawf.list_workflow_runs_by_user(
            pool,
            owner_user_id="00000000-0000-0000-0000-000000000123",
            offset=-1,
        )


@pytest.mark.asyncio
async def test_list_workflow_runs_by_user_missing_user_and_invalid_status_fail_clearly():
    with pytest.raises(ValueError, match="Invalid owner_user_id"):
        await mawf.list_workflow_runs_by_user(
            WorkflowRunsByUserPool(),
            owner_user_id="not-a-uuid",
        )
    with pytest.raises(ValueError, match="MAWF user not found"):
        await mawf.list_workflow_runs_by_user(
            WorkflowRunsByUserPool(user_exists=False),
            owner_user_id="00000000-0000-0000-0000-000000000123",
        )
    with pytest.raises(ValueError, match="Invalid WORKFLOW_RUN_STATUS value"):
        await mawf.list_workflow_runs_by_user(
            WorkflowRunsByUserPool(),
            owner_user_id="00000000-0000-0000-0000-000000000123",
            status_code="bogus",
        )


@pytest.mark.asyncio
async def test_list_workflow_runs_by_user_active_only_uses_required_statuses_and_ordering():
    pool = WorkflowRunsByUserPool()
    await mawf.list_workflow_runs_by_user(
        pool,
        owner_user_id="00000000-0000-0000-0000-000000000123",
        active_only=True,
    )

    query, args = pool.fetch_calls[0]
    assert set(args[5]) == {
        "RUN_PENDING",
        "RUN_RUNNING",
        "RUN_WAITING_FOR_FEEDBACK",
        "RUN_RESUME_PENDING",
    }
    assert "rv.is_terminal = FALSE THEN 0 ELSE 1 END" in query
    assert "wr.updated_utc DESC" in query
    assert "wr.started_utc DESC" in query
    assert "mawf_attempt" in query


@pytest.mark.asyncio
async def test_list_recoverable_workflow_runs_defaults_to_active_index_rows():
    pool = WorkflowRunsByUserPool(run_rows=[_workflow_run_user_row()])

    result = await mawf.list_recoverable_workflow_runs(pool)

    query, args = pool.fetch_calls[0]
    assert "ops.workflow_runs wr" in query
    assert "planning.task_workflow_runs" in query
    assert "planning.tasks t" in query
    assert "ops.mawf_task_execution_leases" in query
    assert "workflow_phase" not in query
    assert "workflow_artifacts" not in query
    assert "artifact_content" not in query
    assert args[0] == [900, 901, 902, 903]
    assert args[1] is True
    assert args[4] == 100
    assert args[5] == 0
    assert result[0]["workflow_run_id"] == "run-a"
    assert result[0]["task_ledger_ref"] == "repo://task-ledger.json"
    assert result[0]["workflow_ledger_ref"] == "repo://ledger.json"
    assert result[0]["workflow_state_ref"] == "repo://state.json"
    assert result[0]["task_artifact_branch"] == "artifact/task-a"
    assert result[0]["taskArtifactBranch"] == "artifact/task-a"
    assert result[0]["last_heartbeat_at"] == "2026-05-08T11:59:00+00:00"
    assert "current_phase" not in result[0]
    assert "error_text" not in result[0]


@pytest.mark.asyncio
async def test_list_recoverable_workflow_runs_filters_timestamps_statuses_and_ordering():
    pool = WorkflowRunsByUserPool()

    await mawf.list_recoverable_workflow_runs(
        pool,
        status_codes=["running"],
        active_only=False,
        updated_before="2026-05-08T12:00:00Z",
        started_before="2026-05-08T11:00:00+00:00",
        limit=999,
        offset=7,
    )

    query, args = pool.fetch_calls[0]
    assert args[0] == [901]
    assert args[1] is False
    assert args[2].isoformat() == "2026-05-08T12:00:00+00:00"
    assert args[3].isoformat() == "2026-05-08T11:00:00+00:00"
    assert args[4] == 500
    assert args[5] == 7
    assert "wr.updated_utc ASC" in query
    assert "wr.started_utc ASC" in query
    assert "mawf_attempt" in query


@pytest.mark.asyncio
async def test_list_recoverable_workflow_runs_validates_inputs():
    pool = WorkflowRunsByUserPool()

    with pytest.raises(ValueError, match="offset"):
        await mawf.list_recoverable_workflow_runs(pool, offset=-1)
    with pytest.raises(ValueError, match="limit"):
        await mawf.list_recoverable_workflow_runs(pool, limit=0)
    with pytest.raises(ValueError, match="updated_before"):
        await mawf.list_recoverable_workflow_runs(pool, updated_before="not-a-date")
    with pytest.raises(ValueError, match="Invalid WORKFLOW_RUN_STATUS value"):
        await mawf.list_recoverable_workflow_runs(pool, status_codes=["bogus"])


def _lease_row(*, status_code="active", expired=False, released=False, reason=None):
    now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
    return {
        "id": uuid.uuid4(),
        "canonical_task_id": 300,
        "mawf_task_id": "task-a",
        "workflow_run_id": 400,
        "workflow_run_uuid": mawf._workflow_run_uuid("run-a"),
        "workflow_context_json": {"mawf_workflow_run_id": "run-a"},
        "lease_token": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "owner_user_id": None,
        "owner_instance_id": "worker-old",
        "owner_host": None,
        "owner_process_id": None,
        "status_value_id": 701,
        "status_code": status_code,
        "acquired_utc": now - timedelta(minutes=5),
        "last_heartbeat_utc": now - timedelta(minutes=5),
        "expires_utc": now - timedelta(seconds=1) if expired else now + timedelta(seconds=60),
        "released_utc": now if released else None,
        "release_reason_value_id": 801 if reason else None,
        "release_reason": reason,
        "metadata_json": {"attempt": 1},
        "is_expired": expired,
    }


class LeaseTransaction:
    def __init__(self, pool):
        self.pool = pool

    async def __aenter__(self):
        self.pool.transaction_entered = True

    async def __aexit__(self, exc_type, exc, tb):
        self.pool.transaction_exited = True


class LeaseAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return None


class LeaseAdminConn:
    def __init__(self, *, current_open=None, workflow_mismatch=False, fetch_rows=None):
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.fetch_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []
        self.transaction_entered = False
        self.transaction_exited = False
        self.current_open = current_open
        self.workflow_mismatch = workflow_mismatch
        self.fetch_rows = fetch_rows or []
        self.inserted_lease_id = uuid.uuid4()
        self.workflow_run_arg = None

    def acquire(self):
        return LeaseAcquire(self)

    def transaction(self):
        return LeaseTransaction(self)

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "FROM core.reference_values rv" in query and "rt.internal_code = $1" in query:
            values = {
                ("TASK_EXECUTION_LEASE_STATUS", "active"): {
                    "id": 701,
                    "internal_code": "LEASE_ACTIVE",
                    "mawf_code": "active",
                    "display_name": "Active",
                    "description": None,
                    "sort_order": 10,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("TASK_EXECUTION_LEASE_STATUS", "released"): {
                    "id": 702,
                    "internal_code": "LEASE_RELEASED",
                    "mawf_code": "released",
                    "display_name": "Released",
                    "description": None,
                    "sort_order": 20,
                    "is_active": True,
                    "is_terminal": True,
                },
                ("TASK_EXECUTION_LEASE_STATUS", "expired"): {
                    "id": 703,
                    "internal_code": "LEASE_EXPIRED",
                    "mawf_code": "expired",
                    "display_name": "Expired",
                    "description": None,
                    "sort_order": 30,
                    "is_active": True,
                    "is_terminal": True,
                },
                ("TASK_EXECUTION_LEASE_RELEASE_REASON", "completed"): {
                    "id": 801,
                    "internal_code": "LEASE_REASON_COMPLETED",
                    "mawf_code": "completed",
                    "display_name": "Completed",
                    "description": None,
                    "sort_order": 10,
                    "is_active": True,
                    "is_terminal": False,
                },
                ("TASK_EXECUTION_LEASE_RELEASE_REASON", "stale_reclaimed"): {
                    "id": 806,
                    "internal_code": "LEASE_REASON_STALE_RECLAIMED",
                    "mawf_code": "stale_reclaimed",
                    "display_name": "Stale Reclaimed",
                    "description": None,
                    "sort_order": 60,
                    "is_active": True,
                    "is_terminal": False,
                },
            }
            return values.get((args[0], args[1]))
        if "FROM planning.tasks t" in query and "WHERE t.mawf_task_id = $1" in query:
            return {"id": 300, "mawf_task_id": args[0]}
        if "FROM ops.workflow_runs wr" in query and "JOIN planning.task_workflow_runs" in query:
            self.workflow_run_arg = args[0]
            if self.workflow_mismatch:
                return None
            return {"id": 400, "run_id": args[0], "context_json": {"mawf_workflow_run_id": "run-a"}}
        if "FROM ops.mawf_task_execution_leases l" in query and "AND l.released_utc IS NULL" in query:
            return self.current_open
        if "INSERT INTO ops.mawf_task_execution_leases" in query:
            return {"id": self.inserted_lease_id}
        if "WHERE l.id = $1::uuid" in query:
            return _lease_row()
        return None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self.fetch_rows

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


@pytest.mark.asyncio
async def test_acquire_task_execution_lease_uses_transaction_task_lock_and_workflow_bridge():
    pool = LeaseAdminConn()
    result = await mawf.acquire_task_execution_lease(
        pool,
        task_id="task-a",
        workflow_run_id="run-a",
        owner_instance_id="worker-1",
        lease_ttl_seconds=60,
    )

    task_queries = [
        query
        for query, _ in pool.fetchrow_calls
        if "FROM planning.tasks t" in query and "WHERE t.mawf_task_id = $1" in query
    ]
    assert pool.transaction_entered is True
    assert "FOR UPDATE" in task_queries[0]
    assert pool.workflow_run_arg == mawf._workflow_run_uuid("run-a")
    assert result["acquired"] is True
    assert result["canonical_task_id"] == 300


@pytest.mark.asyncio
async def test_acquire_task_execution_lease_rejects_workflow_task_mismatch():
    pool = LeaseAdminConn(workflow_mismatch=True)

    with pytest.raises(ValueError, match="Workflow run not linked to task"):
        await mawf.acquire_task_execution_lease(
            pool,
            task_id="task-a",
            workflow_run_id="run-a",
            owner_instance_id="worker-1",
        )


@pytest.mark.asyncio
async def test_acquire_task_execution_lease_denies_active_non_expired_owner():
    pool = LeaseAdminConn(current_open=_lease_row(expired=False))

    result = await mawf.acquire_task_execution_lease(
        pool,
        task_id="task-a",
        owner_instance_id="worker-2",
    )

    assert result["acquired"] is False
    assert result["current_lease"]["owner_instance_id"] == "worker-old"
    assert not [query for query, _ in pool.fetchrow_calls if "INSERT INTO ops.mawf_task_execution_leases" in query]


@pytest.mark.asyncio
async def test_acquire_task_execution_lease_enforces_ttl_bounds():
    with pytest.raises(ValueError, match="lease_ttl_seconds"):
        await mawf.acquire_task_execution_lease(
            object(),
            task_id="task-a",
            owner_instance_id="worker-1",
            lease_ttl_seconds=4,
        )
    with pytest.raises(ValueError, match="lease_ttl_seconds"):
        await mawf.acquire_task_execution_lease(
            object(),
            task_id="task-a",
            owner_instance_id="worker-1",
            lease_ttl_seconds=3601,
        )


@pytest.mark.asyncio
async def test_stale_reclaim_closes_old_lease_before_new_insert():
    pool = LeaseAdminConn(current_open=_lease_row(expired=True))

    result = await mawf.acquire_task_execution_lease(
        pool,
        task_id="task-a",
        owner_instance_id="worker-2",
    )

    assert result["acquired"] is True
    assert result["stale_reclaimed"] is True
    reclaim_updates = [
        args
        for query, args in pool.execute_calls
        if "UPDATE ops.mawf_task_execution_leases" in query and "release_reason_value_id" in query
    ]
    assert reclaim_updates
    assert reclaim_updates[0][1:] == (703, 806)


@pytest.mark.asyncio
async def test_list_stale_task_execution_leases_filters_open_active_expired_and_caps_limit():
    pool = LeaseAdminConn(fetch_rows=[_lease_row(expired=True)])

    result = await mawf.list_stale_task_execution_leases(
        pool,
        older_than_seconds=30,
        limit=999,
    )

    assert result[0]["task_id"] == "task-a"
    query, args = pool.fetch_calls[0]
    assert "l.released_utc IS NULL" in query
    assert "COALESCE(status.mawf_code, status.internal_code) = 'active'" in query
    assert args == (30, 500)
