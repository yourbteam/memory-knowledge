import json
import uuid
from types import SimpleNamespace

import pytest

from memory_knowledge import server


class PlanningPool:
    async def fetchrow(self, query, *args):
        if "SELECT id FROM catalog.repositories WHERE repository_key = $1" in query:
            return {"id": 99}
        if "FROM core.reference_values rv" in query and "WHERE rt.internal_code = $1 AND rv.internal_code = $2" in query:
            type_code, value_code = args
            lookup = {
                ("PROJECT_STATUS", "PROJ_ACTIVE"): {"id": 1, "internal_code": "PROJ_ACTIVE", "display_name": "Active", "is_terminal": False},
                ("FEATURE_STATUS", "FEAT_IDEA"): {"id": 2, "internal_code": "FEAT_IDEA", "display_name": "Idea", "is_terminal": False},
                ("TASK_STATUS", "TASK_TODO"): {"id": 3, "internal_code": "TASK_TODO", "display_name": "To Do", "is_terminal": False},
                ("PRIORITY", "PRIO_MEDIUM"): {"id": 4, "internal_code": "PRIO_MEDIUM", "display_name": "Medium", "is_terminal": False},
            }
            return lookup.get((type_code, value_code))
        return None


@pytest.fixture
def planning_env(monkeypatch):
    pool = PlanningPool()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)
    return pool


@pytest.mark.asyncio
async def test_create_project_tool_uses_reference_lookup(monkeypatch, planning_env):
    async def fake_create_project(pool, project_status_id, name, description=None, repository_keys=None):
        assert project_status_id == 1
        assert name == "Alpha"
        return {"project_id": 10, "project_key": str(uuid.uuid4()), "repository_count": 0}

    monkeypatch.setattr(server._planning, "create_project", fake_create_project)
    result = await server.create_project(name="Alpha")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["project_id"] == 10


@pytest.mark.asyncio
async def test_create_feature_tool_accepts_project_external_ref(monkeypatch, planning_env):
    async def fake_resolve_project_id_by_external(pool, external_system, external_id):
        assert external_system == "clickup"
        assert external_id == "proj-ext-1"
        return 20

    async def fake_create_feature(pool, project_id, feature_status_id, priority_id, title, description=None, repository_keys=None):
        assert project_id == 20
        return {"feature_id": 11, "feature_key": str(uuid.uuid4()), "repository_count": 1}

    monkeypatch.setattr(server._planning, "resolve_project_id_by_external", fake_resolve_project_id_by_external)
    monkeypatch.setattr(server._planning, "create_feature", fake_create_feature)
    result = await server.create_feature(
        title="Feature A",
        repository_keys=["repo-a"],
        project_external_system="clickup",
        project_external_id="proj-ext-1",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"


@pytest.mark.asyncio
async def test_create_feature_tool_resolves_project(monkeypatch, planning_env):
    async def fake_resolve_project_id(pool, project_key):
        assert project_key == "proj-key"
        return 20

    async def fake_create_feature(pool, project_id, feature_status_id, priority_id, title, description=None, repository_keys=None):
        assert project_id == 20
        assert feature_status_id == 2
        assert priority_id == 4
        assert title == "Feature A"
        assert repository_keys == ["repo-a"]
        return {"feature_id": 11, "feature_key": str(uuid.uuid4()), "repository_count": 0}

    monkeypatch.setattr(server._planning, "resolve_project_id", fake_resolve_project_id)
    monkeypatch.setattr(server._planning, "create_feature", fake_create_feature)
    result = await server.create_feature(project_key="proj-key", title="Feature A", repository_keys=["repo-a"])
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["feature_id"] == 11


@pytest.mark.asyncio
async def test_create_task_tool_resolves_feature(monkeypatch, planning_env):
    async def fake_resolve_project_id(pool, project_key):
        assert project_key == "proj-key"
        return 20

    async def fake_resolve_feature_context(pool, feature_key):
        assert feature_key == "feat-key"
        return {"feature_id": 30, "project_id": 20}

    async def fake_create_task(pool, project_id, repository_id, feature_id, task_status_id, priority_id, title, description=None):
        assert project_id == 20
        assert repository_id == 99
        assert feature_id == 30
        assert task_status_id == 3
        assert priority_id == 4
        return {"task_id": 12, "task_key": str(uuid.uuid4()), "repository_count": 0}

    monkeypatch.setattr(server._planning, "resolve_project_id", fake_resolve_project_id)
    monkeypatch.setattr(server._planning, "resolve_feature_context", fake_resolve_feature_context)
    monkeypatch.setattr(server._planning, "create_task", fake_create_task)
    result = await server.create_task(project_key="proj-key", repository_key="repo-a", feature_key="feat-key", title="Task A")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["task_id"] == 12


@pytest.mark.asyncio
async def test_create_task_tool_rejects_feature_from_another_project(monkeypatch, planning_env):
    async def fake_resolve_project_id(pool, project_key):
        return 20

    async def fake_resolve_feature_context(pool, feature_key):
        return {"feature_id": 30, "project_id": 21}

    monkeypatch.setattr(server._planning, "resolve_project_id", fake_resolve_project_id)
    monkeypatch.setattr(server._planning, "resolve_feature_context", fake_resolve_feature_context)
    result = await server.create_task(
        project_key="proj-key",
        repository_key="repo-a",
        feature_key="feat-key",
        title="Task A",
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "does not belong to the given project_key" in payload["error"]


@pytest.mark.asyncio
async def test_create_task_tool_allows_project_only_task(monkeypatch, planning_env):
    async def fake_resolve_project_id(pool, project_key):
        assert project_key == "proj-key"
        return 20

    async def fake_create_task(pool, project_id, repository_id, feature_id, task_status_id, priority_id, title, description=None):
        assert project_id == 20
        assert repository_id == 99
        assert feature_id is None
        return {"task_id": 13, "task_key": str(uuid.uuid4()), "repository_count": 0}

    monkeypatch.setattr(server._planning, "resolve_project_id", fake_resolve_project_id)
    monkeypatch.setattr(server._planning, "create_task", fake_create_task)
    result = await server.create_task(project_key="proj-key", repository_key="repo-a", title="Standalone Task")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["task_id"] == 13


@pytest.mark.asyncio
async def test_create_task_tool_accepts_external_refs(monkeypatch, planning_env):
    async def fake_resolve_project_id_by_external(pool, external_system, external_id):
        assert external_system == "clickup"
        assert external_id == "proj-ext-1"
        return 20

    async def fake_resolve_feature_context_by_external(pool, external_system, external_id):
        assert external_system == "clickup"
        assert external_id == "feat-ext-1"
        return {"feature_id": 30, "project_id": 20}

    async def fake_create_task(pool, project_id, repository_id, feature_id, task_status_id, priority_id, title, description=None):
        assert project_id == 20
        assert repository_id == 99
        assert feature_id == 30
        return {"task_id": 14, "task_key": str(uuid.uuid4()), "repository_id": 99}

    monkeypatch.setattr(server._planning, "resolve_project_id_by_external", fake_resolve_project_id_by_external)
    monkeypatch.setattr(server._planning, "resolve_feature_context_by_external", fake_resolve_feature_context_by_external)
    monkeypatch.setattr(server._planning, "create_task", fake_create_task)
    result = await server.create_task(
        project_external_system="clickup",
        project_external_id="proj-ext-1",
        feature_external_system="clickup",
        feature_external_id="feat-ext-1",
        repository_key="repo-a",
        title="External Task",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["task_id"] == 14


@pytest.mark.asyncio
async def test_link_task_to_workflow_run_tool(monkeypatch, planning_env):
    async def fake_resolve_task_id(pool, task_key):
        assert task_key == "task-key"
        return 40

    async def fake_link(pool, task_id, workflow_run_id, relation_type):
        assert task_id == 40
        assert workflow_run_id == "run-uuid"
        assert relation_type == "implements"
        return {"task_id": 40, "workflow_run_id": 50, "relation_type": "implements"}

    monkeypatch.setattr(server._planning, "resolve_task_id", fake_resolve_task_id)
    monkeypatch.setattr(server._planning, "link_task_to_workflow_run", fake_link)
    result = await server.link_task_to_workflow_run(task_key="task-key", workflow_run_id="run-uuid")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["relation_type"] == "implements"


@pytest.mark.asyncio
async def test_link_task_to_workflow_run_tool_surfaces_repo_mismatch(monkeypatch, planning_env):
    async def fake_resolve_task_id(pool, task_key):
        return 40

    async def fake_link(pool, task_id, workflow_run_id, relation_type):
        raise ValueError("Task repository does not match workflow run repository")

    monkeypatch.setattr(server._planning, "resolve_task_id", fake_resolve_task_id)
    monkeypatch.setattr(server._planning, "link_task_to_workflow_run", fake_link)
    result = await server.link_task_to_workflow_run(task_key="task-key", workflow_run_id="run-uuid")
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "does not match" in payload["error"]


@pytest.mark.asyncio
async def test_link_project_external_ref_tool(monkeypatch, planning_env):
    async def fake_resolve_project_id(pool, project_key):
        assert project_key == "proj-key"
        return 20

    async def fake_create_external_link(pool, table_name, owner_column, owner_id, external_system, external_object_type, external_id, external_parent_id=None, external_url=None):
        assert table_name == "planning.project_external_links"
        assert owner_column == "project_id"
        assert owner_id == 20
        return {"link_id": 1, "external_system": external_system, "external_object_type": external_object_type, "external_id": external_id}

    monkeypatch.setattr(server._planning, "resolve_project_id", fake_resolve_project_id)
    monkeypatch.setattr(server._planning, "create_external_link", fake_create_external_link)
    result = await server.link_project_external_ref(
        project_key="proj-key",
        external_system="clickup",
        external_object_type="space",
        external_id="proj-ext-1",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["external_id"] == "proj-ext-1"


@pytest.mark.asyncio
async def test_add_repository_to_project_tool(monkeypatch, planning_env):
    async def fake_resolve_project_id(pool, project_key):
        assert project_key == "proj-key"
        return 20

    calls = {}

    async def fake_add_repository_to_project(pool, project_id, repository_id):
        calls["project_id"] = project_id
        calls["repository_id"] = repository_id

    monkeypatch.setattr(server._planning, "resolve_project_id", fake_resolve_project_id)
    monkeypatch.setattr(server._planning, "add_repository_to_project", fake_add_repository_to_project)
    result = await server.add_repository_to_project(project_key="proj-key", repository_key="repo-a")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert calls == {"project_id": 20, "repository_id": 99}


@pytest.mark.asyncio
async def test_remove_repository_from_project_tool(monkeypatch, planning_env):
    async def fake_resolve_project_id(pool, project_key):
        return 20

    async def fake_remove_repository_from_project(pool, project_id, repository_id):
        assert project_id == 20
        assert repository_id == 99
        return {"feature_count": 0, "task_count": 0}

    monkeypatch.setattr(server._planning, "resolve_project_id", fake_resolve_project_id)
    monkeypatch.setattr(server._planning, "remove_repository_from_project", fake_remove_repository_from_project)
    result = await server.remove_repository_from_project(project_key="proj-key", repository_key="repo-a")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["repository_key"] == "repo-a"


@pytest.mark.asyncio
async def test_add_repository_to_feature_tool(monkeypatch, planning_env):
    async def fake_resolve_feature_context(pool, feature_key=None, feature_external_system=None, feature_external_id=None):
        return {"feature_id": 30, "project_id": 20}

    calls = {"project_check": False, "feature_add": False}

    async def fake_ensure_project_has_repository(pool, project_id, repository_id):
        assert project_id == 20
        assert repository_id == 99
        calls["project_check"] = True

    async def fake_add_repository_to_feature(pool, feature_id, repository_id):
        assert feature_id == 30
        assert repository_id == 99
        calls["feature_add"] = True

    monkeypatch.setattr(server, "_resolve_feature_identifier", fake_resolve_feature_context)
    monkeypatch.setattr(server._planning, "ensure_project_has_repository", fake_ensure_project_has_repository)
    monkeypatch.setattr(server._planning, "add_repository_to_feature", fake_add_repository_to_feature)
    result = await server.add_repository_to_feature(feature_key="feat-key", repository_key="repo-a")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert calls == {"project_check": True, "feature_add": True}


@pytest.mark.asyncio
async def test_remove_repository_from_feature_tool(monkeypatch, planning_env):
    async def fake_resolve_feature_context(pool, feature_key=None, feature_external_system=None, feature_external_id=None):
        return {"feature_id": 30, "project_id": 20}

    async def fake_remove_repository_from_feature(pool, feature_id, repository_id):
        assert feature_id == 30
        assert repository_id == 99
        return {"task_count": 0}

    monkeypatch.setattr(server, "_resolve_feature_identifier", fake_resolve_feature_context)
    monkeypatch.setattr(server._planning, "remove_repository_from_feature", fake_remove_repository_from_feature)
    result = await server.remove_repository_from_feature(feature_key="feat-key", repository_key="repo-a")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["repository_key"] == "repo-a"


@pytest.mark.asyncio
async def test_list_tasks_tool_accepts_feature_external_filter(monkeypatch, planning_env):
    async def fake_resolve_feature_context_by_external(pool, external_system, external_id):
        assert external_system == "clickup"
        assert external_id == "feat-ext-1"
        return {"feature_id": 30, "project_id": 20}

    async def fake_list_tasks(pool, project_id=None, feature_id=None, repository_key=None, task_status_id=None):
        assert feature_id == 30
        return [{"task_key": "t1", "project_key": "proj-key"}]

    monkeypatch.setattr(server._planning, "resolve_feature_context_by_external", fake_resolve_feature_context_by_external)
    monkeypatch.setattr(server._planning, "list_tasks", fake_list_tasks)
    result = await server.list_tasks(
        feature_external_system="clickup",
        feature_external_id="feat-ext-1",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["tasks"][0]["task_key"] == "t1"


@pytest.mark.asyncio
async def test_get_backlog_tool(monkeypatch, planning_env):
    async def fake_get_backlog(pool, project_id=None, repository_key=None, limit=100):
        assert project_id is None
        assert repository_key == "repo-a"
        return {"features": [{"feature_key": "f1"}], "tasks": [{"task_key": "t1"}]}

    monkeypatch.setattr(server._planning, "get_backlog", fake_get_backlog)
    result = await server.get_backlog(repository_key="repo-a")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["features"][0]["feature_key"] == "f1"


@pytest.mark.asyncio
async def test_list_tasks_tool_accepts_project_filter(monkeypatch, planning_env):
    async def fake_resolve_project_id(pool, project_key):
        assert project_key == "proj-key"
        return 20

    async def fake_list_tasks(pool, project_id=None, feature_id=None, repository_key=None, task_status_id=None):
        assert project_id == 20
        assert feature_id is None
        return [{"task_key": "t1", "project_key": "proj-key"}]

    monkeypatch.setattr(server._planning, "resolve_project_id", fake_resolve_project_id)
    monkeypatch.setattr(server._planning, "list_tasks", fake_list_tasks)
    result = await server.list_tasks(project_key="proj-key")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["tasks"][0]["task_key"] == "t1"
