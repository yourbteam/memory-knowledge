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

    async def fake_upsert_task(pool, task_id, owner_user_id, project_id, repository_id, prompt_id, title, task_ledger_ref, status_code="active"):
        return {"id": task_id, "owner_user_id": owner_user_id, "project_id": project_id, "repository_id": repository_id, "prompt_id": prompt_id, "title": title, "task_ledger_ref": task_ledger_ref, "status_code": status_code}

    async def fake_get_task(pool, task_id):
        return {"id": task_id, "status_code": "active"}

    async def fake_list_tasks(pool, owner_user_id=None, project_id=None, repository_id=None, status_code=None):
        return [{"id": "task-a", "owner_user_id": owner_user_id, "status_code": status_code or "active"}]

    async def fake_set_task_status(pool, task_id, status_code):
        return {"id": task_id, "status_code": status_code}

    async def fake_upsert_artifact(pool, task_id, role_code, artifact_path, content_hash=None, persist_status_code="local_only", artifact_ref_id=None):
        return {"id": artifact_ref_id or artifact_ref_id, "task_id": task_id, "role_code": role_code, "artifact_path": artifact_path, "persist_status_code": persist_status_code}

    async def fake_get_artifact(pool, artifact_ref_id=None, task_id=None, role_code=None):
        return {"id": artifact_ref_id, "task_id": task_id, "role_code": role_code}

    async def fake_list_artifacts(pool, task_id):
        return [{"id": artifact_ref_id, "task_id": task_id}]

    async def fake_set_artifact_status(pool, artifact_ref_id, persist_status_code):
        return {"id": artifact_ref_id, "persist_status_code": persist_status_code}

    async def fake_bundle(pool, task_id):
        return {"task": {"id": task_id}, "artifact_refs": [{"id": artifact_ref_id}], "workflow_runs": []}

    monkeypatch.setattr(server._mawf, "create_prompt", fake_create_prompt)
    monkeypatch.setattr(server._mawf, "get_prompt", fake_get_prompt)
    monkeypatch.setattr(server._mawf, "get_prompt_by_hash", fake_get_prompt_by_hash)
    monkeypatch.setattr(server._mawf, "list_prompts_by_user", fake_list_prompts)
    monkeypatch.setattr(server._mawf, "supersede_prompt_ref", fake_supersede)
    monkeypatch.setattr(server._mawf, "upsert_task", fake_upsert_task)
    monkeypatch.setattr(server._mawf, "get_task", fake_get_task)
    monkeypatch.setattr(server._mawf, "list_tasks", fake_list_tasks)
    monkeypatch.setattr(server._mawf, "set_task_status", fake_set_task_status)
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
    task = _payload(await server.mawf_upsert_task("task-a", user_id, project_id, repository_id, prompt_id, "Task A", "ledger://task-a"))["data"]
    assert task["task_ledger_ref"] == "ledger://task-a"
    assert _payload(await server.mawf_get_task("task-a"))["data"]["id"] == "task-a"
    assert _payload(await server.mawf_list_tasks(owner_user_id=user_id))["data"]["items"][0]["owner_user_id"] == user_id
    assert _payload(await server.mawf_complete_task("task-a"))["data"]["status_code"] == "completed"
    assert _payload(await server.mawf_cancel_task("task-a"))["data"]["status_code"] == "cancelled"
    assert _payload(await server.mawf_fail_task("task-a"))["data"]["status_code"] == "failed"
    artifact = _payload(await server.mawf_upsert_artifact_ref("task-a", "task_ledger", "Tasks/task-a/plan.md", artifact_ref_id=artifact_ref_id))["data"]
    assert artifact["role_code"] == "task_ledger"
    assert _payload(await server.mawf_get_artifact_ref(artifact_ref_id=artifact_ref_id))["data"]["id"] == artifact_ref_id
    assert _payload(await server.mawf_list_artifact_refs("task-a"))["data"]["items"][0]["id"] == artifact_ref_id
    assert _payload(await server.mawf_set_artifact_persist_status(artifact_ref_id, "persisted"))["data"]["persist_status_code"] == "persisted"
    assert _payload(await server.mawf_get_task_memory_bundle("task-a"))["data"]["task"]["id"] == "task-a"


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
