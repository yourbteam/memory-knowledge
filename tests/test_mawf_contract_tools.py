import json
import uuid
from types import SimpleNamespace

import pytest

from memory_knowledge import server


@pytest.fixture
def mawf_env(monkeypatch):
    pool = SimpleNamespace(name="pool")
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)
    return pool


def _payload(result: str) -> dict:
    return json.loads(result)


@pytest.mark.asyncio
async def test_mawf_catalog_type_and_value_crud_through_mcp(monkeypatch, mawf_env):
    async def fake_list_types(pool):
        assert pool is mawf_env
        return [{"id": 1, "code": "USER_ROLE", "description": "roles"}]

    async def fake_list_values(pool, catalog_type_code=None, include_inactive=False):
        assert catalog_type_code == "USER_ROLE"
        assert include_inactive is True
        return [{"id": 1, "code": "admin", "is_active": True}]

    async def fake_upsert_value(pool, catalog_type_code, code, description=None, sort_order=0, is_active=True):
        assert catalog_type_code == "USER_ROLE"
        assert code == "manager"
        return {"id": 99, "code": code, "description": description, "is_active": is_active}

    async def fake_deactivate_value(pool, catalog_type_code, code):
        assert catalog_type_code == "USER_ROLE"
        assert code == "manager"
        return {"id": 99, "code": code, "is_active": False}

    monkeypatch.setattr(server._mawf, "list_catalog_types", fake_list_types)
    monkeypatch.setattr(server._mawf, "list_catalog_values", fake_list_values)
    monkeypatch.setattr(server._mawf, "upsert_catalog_value", fake_upsert_value)
    monkeypatch.setattr(server._mawf, "deactivate_catalog_value", fake_deactivate_value)

    assert _payload(await server.mawf_list_catalog_types())["data"]["items"][0]["code"] == "USER_ROLE"
    assert _payload(await server.mawf_list_catalog_values("USER_ROLE", include_inactive=True))["data"]["items"][0]["code"] == "admin"
    assert _payload(await server.mawf_upsert_catalog_value("USER_ROLE", "manager", "Manager"))["data"]["id"] == 99
    assert _payload(await server.mawf_deactivate_catalog_value("USER_ROLE", "manager"))["data"]["is_active"] is False


@pytest.mark.asyncio
async def test_mawf_user_crud_through_mcp(monkeypatch, mawf_env):
    user_id = str(uuid.uuid4())

    async def fake_upsert(pool, email, user_id=None, display_name=None, role_code="employee", status_code="active"):
        return {"id": user_id or "generated", "email": email, "display_name": display_name, "role_code": role_code, "status_code": status_code}

    async def fake_get(pool, user_id=None, email=None):
        return {"id": user_id, "email": email or "user@example.com", "status_code": "active"}

    async def fake_list(pool, status_code=None):
        return [{"id": user_id, "status_code": status_code or "active"}]

    async def fake_deactivate(pool, user_id):
        return {"id": user_id, "status_code": "inactive"}

    monkeypatch.setattr(server._mawf, "upsert_user", fake_upsert)
    monkeypatch.setattr(server._mawf, "get_user", fake_get)
    monkeypatch.setattr(server._mawf, "list_users", fake_list)
    monkeypatch.setattr(server._mawf, "deactivate_user", fake_deactivate)

    assert _payload(await server.mawf_upsert_user("user@example.com", user_id=user_id, display_name="User"))["data"]["email"] == "user@example.com"
    assert _payload(await server.mawf_get_user(user_id=user_id))["data"]["id"] == user_id
    assert _payload(await server.mawf_list_users(status_code="active"))["data"]["items"][0]["status_code"] == "active"
    assert _payload(await server.mawf_deactivate_user(user_id))["data"]["status_code"] == "inactive"


@pytest.mark.asyncio
async def test_mawf_project_and_repository_crud_through_mcp(monkeypatch, mawf_env):
    project_id = str(uuid.uuid4())
    repository_id = str(uuid.uuid4())

    async def fake_upsert_project(pool, project_key, display_name, project_id=None, status_code="active"):
        return {"id": project_id, "project_key": project_key, "display_name": display_name, "status_code": status_code}

    async def fake_get_project(pool, project_id=None, project_key=None):
        return {"id": project_id, "project_key": project_key, "status_code": "active"}

    async def fake_list_projects(pool, status_code=None):
        return [{"id": project_id, "status_code": status_code or "active"}]

    async def fake_archive_project(pool, project_id):
        return {"id": project_id, "status_code": "inactive"}

    async def fake_upsert_repo(pool, repository_key, repository_id=None, project_id=None, provider=None, owner=None, repo_name=None, remote_url=None, status_code="active"):
        return {"id": repository_id, "project_id": project_id, "repository_key": repository_key, "provider": provider, "owner": owner, "repo_name": repo_name, "remote_url": remote_url, "status_code": status_code}

    async def fake_get_repo(pool, repository_id=None, repository_key=None):
        return {"id": repository_id, "repository_key": repository_key or "repo-a", "status_code": "active"}

    async def fake_list_repos(pool, status_code=None):
        return [{"id": repository_id, "status_code": status_code or "active"}]

    async def fake_deactivate_repo(pool, repository_id):
        return {"id": repository_id, "status_code": "inactive"}

    monkeypatch.setattr(server._mawf, "upsert_project", fake_upsert_project)
    monkeypatch.setattr(server._mawf, "get_project", fake_get_project)
    monkeypatch.setattr(server._mawf, "list_projects", fake_list_projects)
    monkeypatch.setattr(server._mawf, "archive_project", fake_archive_project)
    monkeypatch.setattr(server._mawf, "upsert_repository", fake_upsert_repo)
    monkeypatch.setattr(server._mawf, "get_repository", fake_get_repo)
    monkeypatch.setattr(server._mawf, "list_repositories", fake_list_repos)
    monkeypatch.setattr(server._mawf, "deactivate_repository", fake_deactivate_repo)

    assert _payload(await server.mawf_upsert_project("proj-a", "Project A", project_id=project_id))["data"]["id"] == project_id
    assert _payload(await server.mawf_get_project(project_id=project_id))["data"]["status_code"] == "active"
    assert _payload(await server.mawf_list_projects())["data"]["items"][0]["id"] == project_id
    assert _payload(await server.mawf_archive_project(project_id))["data"]["status_code"] == "inactive"
    repo = _payload(await server.mawf_upsert_repository("repo-a", repository_id=repository_id, project_id=project_id, provider="github", owner="org", repo_name="repo", remote_url="https://example/repo"))["data"]
    assert repo["project_id"] == project_id
    assert _payload(await server.mawf_get_repository(repository_id=repository_id))["data"]["id"] == repository_id
    assert _payload(await server.mawf_list_repositories())["data"]["items"][0]["id"] == repository_id
    assert _payload(await server.mawf_deactivate_repository(repository_id))["data"]["status_code"] == "inactive"


@pytest.mark.asyncio
async def test_mawf_prompt_task_artifact_and_bundle_through_mcp(monkeypatch, mawf_env):
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    repository_id = str(uuid.uuid4())
    prompt_id = str(uuid.uuid4())
    superseded_id = str(uuid.uuid4())
    artifact_ref_id = str(uuid.uuid4())

    async def fake_create_prompt(pool, normalized_hash, original_prompt_ref, normalized_prompt_ref, created_by_user_id, prompt_id=None, supersedes_prompt_id=None, correction_note=None):
        return {"id": prompt_id or superseded_id, "normalized_hash": normalized_hash, "created_by_user_id": created_by_user_id, "supersedes_prompt_id": supersedes_prompt_id, "correction_note": correction_note}

    async def fake_get_prompt(pool, prompt_id):
        return {"id": prompt_id, "normalized_hash": "hash-a"}

    async def fake_get_prompt_by_hash(pool, normalized_hash):
        return {"id": prompt_id, "normalized_hash": normalized_hash}

    async def fake_list_prompts(pool, user_id):
        return [{"id": prompt_id, "created_by_user_id": user_id}]

    async def fake_supersede(pool, prompt_id, normalized_hash, original_prompt_ref, normalized_prompt_ref, correction_note=None):
        return {"id": superseded_id, "supersedes_prompt_id": prompt_id, "normalized_hash": normalized_hash}

    async def fake_upsert_task(pool, task_id, owner_user_id, project_id, repository_id, prompt_id, title, task_ledger_ref, status_code="active", external_task_id=None):
        return {"id": task_id, "external_task_id": external_task_id, "owner_user_id": owner_user_id, "project_id": project_id, "repository_id": repository_id, "prompt_id": prompt_id, "title": title, "task_ledger_ref": task_ledger_ref, "status_code": status_code}

    async def fake_get_task(pool, task_id=None, external_task_id=None):
        return {"id": task_id or "task-a", "external_task_id": external_task_id, "status_code": "active"}

    async def fake_list_tasks(pool, owner_user_id=None, project_id=None, repository_id=None, status_code=None):
        return [{"id": "task-a", "external_task_id": "ABC-123", "owner_user_id": owner_user_id, "status_code": status_code or "active"}]

    async def fake_set_task_status(pool, task_id, status_code):
        return {"id": task_id, "status_code": status_code}

    async def fake_upsert_workflow_run(
        pool,
        workflow_run_id,
        task_id,
        workflow_name,
        attempt=1,
        status_code="queued",
        workflow_ledger_ref=None,
        workflow_state_ref=None,
        current_phase=None,
        iteration_count=None,
        error_text=None,
        relation_type="implements",
    ):
        return {
            "workflow_run_id": workflow_run_id,
            "task_id": task_id,
            "workflow_name": workflow_name,
            "attempt": attempt,
            "status_code": status_code,
            "workflow_ledger_ref": workflow_ledger_ref,
            "workflow_state_ref": workflow_state_ref,
            "relation_type": relation_type,
        }

    async def fake_get_workflow_run(pool, workflow_run_id):
        return {"workflow_run_id": workflow_run_id, "task_id": "task-a"}

    async def fake_list_workflow_runs(pool, task_id):
        return [{"workflow_run_id": "run-a", "task_id": task_id}]

    async def fake_list_workflow_runs_by_user(
        pool,
        owner_user_id,
        workflow_name=None,
        status_code=None,
        terminal=None,
        active_only=False,
        limit=50,
        offset=0,
    ):
        return [
            {
                "workflow_run_id": "run-a",
                "task_id": "task-a",
                "owner_user_id": owner_user_id,
                "workflow_name": workflow_name,
                "status_code": status_code or "running",
                "is_terminal": terminal if terminal is not None else False,
                "active_only": active_only,
                "limit": limit,
                "offset": offset,
            }
        ]

    async def fake_list_recoverable_workflow_runs(
        pool,
        status_codes=None,
        active_only=True,
        updated_before=None,
        started_before=None,
        limit=100,
        offset=0,
    ):
        return [
            {
                "workflow_run_id": "run-a",
                "task_id": "task-a",
                "status_codes": status_codes,
                "active_only": active_only,
                "updated_before": updated_before,
                "started_before": started_before,
                "limit": limit,
                "offset": offset,
                "task_ledger_ref": "repo://task-ledger.json",
                "workflow_ledger_ref": "repo://workflow-ledger.json",
                "workflow_state_ref": "repo://workflow-state.json",
            }
        ]

    async def fake_set_workflow_run_status(
        pool,
        workflow_run_id,
        status_code,
        current_phase=None,
        iteration_count=None,
        error_text=None,
    ):
        return {
            "workflow_run_id": workflow_run_id,
            "status_code": status_code,
            "current_phase": current_phase,
            "iteration_count": iteration_count,
            "error_text": error_text,
        }

    async def fake_acquire_lease(
        pool,
        task_id,
        owner_instance_id,
        workflow_run_id=None,
        owner_user_id=None,
        owner_host=None,
        owner_process_id=None,
        lease_ttl_seconds=60,
        metadata_json=None,
    ):
        return {
            "ok": True,
            "acquired": True,
            "task_id": task_id,
            "workflow_run_id": workflow_run_id,
            "canonical_task_id": 300,
            "lease_token": "00000000-0000-0000-0000-000000000001",
            "expires_utc": "2026-05-08T12:01:00+00:00",
            "stale_reclaimed": False,
            "lease": {
                "task_id": task_id,
                "owner_instance_id": owner_instance_id,
                "status_code": "active",
                "metadata_json": metadata_json,
            },
        }

    async def fake_heartbeat_lease(pool, task_id, lease_token, lease_ttl_seconds=60):
        return {
            "ok": True,
            "task_id": task_id,
            "lease": {
                "lease_token": lease_token,
                "status_code": "active",
                "expires_utc": "2026-05-08T12:02:00+00:00",
            },
        }

    async def fake_release_lease(pool, task_id, lease_token, release_reason):
        return {
            "ok": True,
            "task_id": task_id,
            "lease": {
                "lease_token": lease_token,
                "status_code": "released",
                "release_reason": release_reason,
            },
        }

    async def fake_get_lease(pool, task_id):
        return {
            "ok": True,
            "task_id": task_id,
            "has_active_lease": True,
            "lease": {"task_id": task_id, "status_code": "active"},
        }

    async def fake_list_stale_leases(pool, older_than_seconds=60, limit=100):
        return [
            {
                "task_id": "task-a",
                "status_code": "active",
                "expires_utc": "2026-05-08T12:00:00+00:00",
            }
        ]

    async def fake_upsert_artifact(pool, task_id, role_code, artifact_path, content_hash=None, persist_status_code="local_only", artifact_ref_id=None, artifact_key=None):
        return {"id": artifact_ref_id or artifact_ref_id, "task_id": task_id, "artifact_key": artifact_key or role_code, "role_code": role_code, "artifact_path": artifact_path, "persist_status_code": persist_status_code}

    async def fake_get_artifact(pool, artifact_ref_id=None, task_id=None, role_code=None, artifact_key=None):
        return {"id": artifact_ref_id, "task_id": task_id, "artifact_key": artifact_key, "role_code": role_code}

    async def fake_list_artifacts(pool, task_id):
        return [{"id": artifact_ref_id, "task_id": task_id, "artifact_key": "task_ledger"}]

    async def fake_set_artifact_status(pool, artifact_ref_id, persist_status_code):
        return {"id": artifact_ref_id, "persist_status_code": persist_status_code}

    async def fake_bundle(pool, task_id):
        return {"task": {"id": task_id, "external_task_id": "ABC-123"}, "artifact_refs": [{"id": artifact_ref_id}], "workflow_runs": []}

    monkeypatch.setattr(server._mawf, "create_prompt", fake_create_prompt)
    monkeypatch.setattr(server._mawf, "get_prompt", fake_get_prompt)
    monkeypatch.setattr(server._mawf, "get_prompt_by_hash", fake_get_prompt_by_hash)
    monkeypatch.setattr(server._mawf, "list_prompts_by_user", fake_list_prompts)
    monkeypatch.setattr(server._mawf, "supersede_prompt_ref", fake_supersede)
    monkeypatch.setattr(server._mawf, "upsert_task", fake_upsert_task)
    monkeypatch.setattr(server._mawf, "get_task", fake_get_task)
    monkeypatch.setattr(server._mawf, "list_tasks", fake_list_tasks)
    monkeypatch.setattr(server._mawf, "set_task_status", fake_set_task_status)
    monkeypatch.setattr(server._mawf, "upsert_workflow_run", fake_upsert_workflow_run)
    monkeypatch.setattr(server._mawf, "get_workflow_run", fake_get_workflow_run)
    monkeypatch.setattr(server._mawf, "list_workflow_runs", fake_list_workflow_runs)
    monkeypatch.setattr(server._mawf, "list_workflow_runs_by_user", fake_list_workflow_runs_by_user)
    monkeypatch.setattr(server._mawf, "list_recoverable_workflow_runs", fake_list_recoverable_workflow_runs)
    monkeypatch.setattr(server._mawf, "set_workflow_run_status", fake_set_workflow_run_status)
    monkeypatch.setattr(server._mawf, "acquire_task_execution_lease", fake_acquire_lease)
    monkeypatch.setattr(server._mawf, "heartbeat_task_execution_lease", fake_heartbeat_lease)
    monkeypatch.setattr(server._mawf, "release_task_execution_lease", fake_release_lease)
    monkeypatch.setattr(server._mawf, "get_task_execution_lease", fake_get_lease)
    monkeypatch.setattr(server._mawf, "list_stale_task_execution_leases", fake_list_stale_leases)
    monkeypatch.setattr(server._mawf, "upsert_artifact_ref", fake_upsert_artifact)
    monkeypatch.setattr(server._mawf, "get_artifact_ref", fake_get_artifact)
    monkeypatch.setattr(server._mawf, "list_artifact_refs", fake_list_artifacts)
    monkeypatch.setattr(server._mawf, "set_artifact_persist_status", fake_set_artifact_status)
    monkeypatch.setattr(server._mawf, "get_task_memory_bundle", fake_bundle)

    assert _payload(await server.mawf_create_prompt("hash-a", "orig://a", "norm://a", user_id, prompt_id=prompt_id))["data"]["id"] == prompt_id
    assert _payload(await server.mawf_get_prompt(prompt_id))["data"]["normalized_hash"] == "hash-a"
    assert _payload(await server.mawf_get_prompt_by_hash("hash-a"))["data"]["id"] == prompt_id
    assert _payload(await server.mawf_list_prompts_by_user(user_id))["data"]["items"][0]["created_by_user_id"] == user_id
    assert _payload(await server.mawf_supersede_prompt_ref(prompt_id, "hash-b", "orig://b", "norm://b"))["data"]["supersedes_prompt_id"] == prompt_id
    task = _payload(await server.mawf_upsert_task("task-a", user_id, project_id, repository_id, prompt_id, "Task A", "ledger://task-a", external_task_id="ABC-123"))["data"]
    assert task["task_ledger_ref"] == "ledger://task-a"
    assert task["external_task_id"] == "ABC-123"
    assert _payload(await server.mawf_get_task("task-a"))["data"]["id"] == "task-a"
    assert _payload(await server.mawf_get_task(external_task_id="ABC-123"))["data"]["external_task_id"] == "ABC-123"
    assert _payload(await server.mawf_list_tasks(owner_user_id=user_id))["data"]["items"][0]["owner_user_id"] == user_id
    assert _payload(await server.mawf_list_tasks(owner_user_id=user_id))["data"]["items"][0]["external_task_id"] == "ABC-123"
    assert _payload(await server.mawf_complete_task("task-a"))["data"]["status_code"] == "completed"
    assert _payload(await server.mawf_cancel_task("task-a"))["data"]["status_code"] == "cancelled"
    assert _payload(await server.mawf_fail_task("task-a"))["data"]["status_code"] == "failed"
    run = _payload(
        await server.mawf_upsert_workflow_run(
            "raw-run-a",
            "task-a",
            "full-task-workflow",
            workflow_ledger_ref="repo://ledger.json",
            workflow_state_ref="repo://state.json",
        )
    )["data"]
    assert run["workflow_run_id"] == "raw-run-a"
    assert run["status_code"] == "queued"
    assert run["workflow_ledger_ref"] == "repo://ledger.json"
    assert _payload(await server.mawf_get_workflow_run("raw-run-a"))["data"]["task_id"] == "task-a"
    assert _payload(await server.mawf_list_workflow_runs("task-a"))["data"]["items"][0]["workflow_run_id"] == "run-a"
    runs_by_user = _payload(
        await server.mawf_list_workflow_runs_by_user(
            user_id,
            workflow_name="full-task-workflow",
            status_code="running",
            terminal=False,
            active_only=True,
            limit=999,
            offset=10,
        )
    )["data"]["items"][0]
    assert runs_by_user["owner_user_id"] == user_id
    assert runs_by_user["workflow_name"] == "full-task-workflow"
    assert runs_by_user["status_code"] == "running"
    assert runs_by_user["is_terminal"] is False
    assert runs_by_user["active_only"] is True
    assert runs_by_user["limit"] == 999
    assert runs_by_user["offset"] == 10
    recoverable_runs = _payload(
        await server.mawf_list_recoverable_workflow_runs(
            status_codes=["running"],
            active_only=True,
            updated_before="2026-05-08T12:00:00Z",
            started_before="2026-05-08T11:00:00Z",
            limit=999,
            offset=20,
        )
    )["data"]["items"][0]
    assert recoverable_runs["status_codes"] == ["running"]
    assert recoverable_runs["active_only"] is True
    assert recoverable_runs["updated_before"] == "2026-05-08T12:00:00Z"
    assert recoverable_runs["started_before"] == "2026-05-08T11:00:00Z"
    assert recoverable_runs["limit"] == 999
    assert recoverable_runs["offset"] == 20
    assert recoverable_runs["task_ledger_ref"] == "repo://task-ledger.json"
    updated_run = _payload(
        await server.mawf_set_workflow_run_status(
            "raw-run-a",
            "running",
            current_phase="implement",
            iteration_count=2,
        )
    )["data"]
    assert updated_run["status_code"] == "running"
    assert updated_run["current_phase"] == "implement"
    assert updated_run["iteration_count"] == 2
    lease = _payload(
        await server.mawf_acquire_task_execution_lease(
            "task-a",
            "worker-1",
            workflow_run_id="raw-run-a",
            lease_ttl_seconds=60,
            metadata_json={"slot": "primary"},
        )
    )["data"]
    assert lease["acquired"] is True
    assert lease["canonical_task_id"] == 300
    assert lease["lease"]["metadata_json"]["slot"] == "primary"
    heartbeat = _payload(
        await server.mawf_heartbeat_task_execution_lease(
            "task-a", "00000000-0000-0000-0000-000000000001"
        )
    )["data"]
    assert heartbeat["lease"]["status_code"] == "active"
    release = _payload(
        await server.mawf_release_task_execution_lease(
            "task-a", "00000000-0000-0000-0000-000000000001", "completed"
        )
    )["data"]
    assert release["lease"]["release_reason"] == "completed"
    assert _payload(await server.mawf_get_task_execution_lease("task-a"))["data"]["has_active_lease"] is True
    assert _payload(await server.mawf_list_stale_task_execution_leases())["data"]["items"][0]["task_id"] == "task-a"
    artifact = _payload(await server.mawf_upsert_artifact_ref("task-a", "task_ledger", "Tasks/task-a/plan.md", artifact_ref_id=artifact_ref_id))["data"]
    assert artifact["role_code"] == "task_ledger"
    assert artifact["artifact_key"] == "task_ledger"
    keyed_artifact = _payload(await server.mawf_upsert_artifact_ref("task-a", "workflow_ledger", "Tasks/task-a/workflow-ledger.json", artifact_key="workflow:run-a:ledger"))["data"]
    assert keyed_artifact["artifact_key"] == "workflow:run-a:ledger"
    assert _payload(await server.mawf_get_artifact_ref(artifact_ref_id=artifact_ref_id))["data"]["id"] == artifact_ref_id
    assert _payload(await server.mawf_get_artifact_ref(task_id="task-a", artifact_key="workflow:run-a:ledger"))["data"]["artifact_key"] == "workflow:run-a:ledger"
    assert _payload(await server.mawf_list_artifact_refs("task-a"))["data"]["items"][0]["id"] == artifact_ref_id
    assert _payload(await server.mawf_set_artifact_persist_status(artifact_ref_id, "persisted"))["data"]["persist_status_code"] == "persisted"
    bundle = _payload(await server.mawf_get_task_memory_bundle("task-a"))["data"]
    assert bundle["task"]["id"] == "task-a"
    assert bundle["task"]["external_task_id"] == "ABC-123"


@pytest.mark.asyncio
async def test_mawf_reference_type_errors_surface_through_mcp(monkeypatch, mawf_env):
    async def fake_bad_user(pool, **kwargs):
        raise ValueError("Invalid USER_ROLE value: TASK_DONE")

    async def fake_bad_task(pool, **kwargs):
        raise ValueError("Invalid TASK_STATUS value: admin")

    async def fake_bad_artifact(pool, **kwargs):
        raise ValueError("Invalid ARTIFACT_ROLE value: persisted")

    monkeypatch.setattr(server._mawf, "upsert_user", fake_bad_user)
    monkeypatch.setattr(server._mawf, "upsert_task", fake_bad_task)
    monkeypatch.setattr(server._mawf, "upsert_artifact_ref", fake_bad_artifact)

    user_payload = _payload(await server.mawf_upsert_user("user@example.com", role_code="TASK_DONE"))
    task_payload = _payload(await server.mawf_upsert_task("task-a", str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()), "Task", "ledger", status_code="admin"))
    artifact_payload = _payload(await server.mawf_upsert_artifact_ref("task-a", "persisted", "path"))

    assert user_payload["status"] == "error"
    assert "USER_ROLE" in user_payload["error"]
    assert task_payload["status"] == "error"
    assert "TASK_STATUS" in task_payload["error"]
    assert artifact_payload["status"] == "error"
    assert "ARTIFACT_ROLE" in artifact_payload["error"]


@pytest.mark.asyncio
async def test_mawf_lease_write_tools_use_remote_write_guard(monkeypatch, mawf_env):
    blocked_tools = []

    def fake_guard(settings, tool_name):
        blocked_tools.append(tool_name)
        return server.WorkflowResult(
            run_id="guarded",
            tool_name=tool_name,
            status="error",
            error=f"blocked {tool_name}",
        )

    monkeypatch.setattr(server, "check_remote_write_guard", fake_guard)

    acquire = _payload(await server.mawf_acquire_task_execution_lease("task-a", "worker-1"))
    heartbeat = _payload(
        await server.mawf_heartbeat_task_execution_lease(
            "task-a", "00000000-0000-0000-0000-000000000001"
        )
    )
    release = _payload(
        await server.mawf_release_task_execution_lease(
            "task-a", "00000000-0000-0000-0000-000000000001", "completed"
        )
    )

    assert acquire["status"] == "error"
    assert heartbeat["status"] == "error"
    assert release["status"] == "error"
    assert blocked_tools == [
        "mawf_acquire_task_execution_lease",
        "mawf_heartbeat_task_execution_lease",
        "mawf_release_task_execution_lease",
    ]


@pytest.mark.asyncio
async def test_mawf_list_workflow_runs_by_user_is_read_only(monkeypatch, mawf_env):
    async def fake_list_by_user(pool, owner_user_id, **kwargs):
        return [{"workflow_run_id": "run-a", "owner_user_id": owner_user_id, **kwargs}]

    def fail_guard(settings, tool_name):
        raise AssertionError(f"write guard should not run for {tool_name}")

    monkeypatch.setattr(server._mawf, "list_workflow_runs_by_user", fake_list_by_user)
    monkeypatch.setattr(server, "check_remote_write_guard", fail_guard)

    payload = _payload(
        await server.mawf_list_workflow_runs_by_user(
            "00000000-0000-0000-0000-000000000123",
            active_only=True,
        )
    )

    assert payload["status"] == "success"
    assert payload["data"]["items"][0]["active_only"] is True


@pytest.mark.asyncio
async def test_mawf_list_recoverable_workflow_runs_is_read_only(monkeypatch, mawf_env):
    async def fake_list_recoverable(pool, **kwargs):
        return [{"workflow_run_id": "run-a", **kwargs}]

    def fail_guard(settings, tool_name):
        raise AssertionError(f"write guard should not run for {tool_name}")

    monkeypatch.setattr(server._mawf, "list_recoverable_workflow_runs", fake_list_recoverable)
    monkeypatch.setattr(server, "check_remote_write_guard", fail_guard)

    payload = _payload(
        await server.mawf_list_recoverable_workflow_runs(
            status_codes=["running"],
            active_only=True,
        )
    )

    assert payload["status"] == "success"
    assert payload["data"]["items"][0]["status_codes"] == ["running"]
    assert payload["data"]["items"][0]["active_only"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "No active lease for task: task-a",
        "Lease expired",
        "Lease is released",
        "Lease token mismatch",
    ],
)
async def test_mawf_heartbeat_lease_errors_surface_through_mcp(monkeypatch, mawf_env, message):
    async def fake_heartbeat(pool, task_id, lease_token, lease_ttl_seconds=60):
        raise ValueError(message)

    monkeypatch.setattr(server._mawf, "heartbeat_task_execution_lease", fake_heartbeat)

    payload = _payload(
        await server.mawf_heartbeat_task_execution_lease(
            "task-a", "00000000-0000-0000-0000-000000000001"
        )
    )
    assert payload["status"] == "error"
    assert payload["error"] == message
