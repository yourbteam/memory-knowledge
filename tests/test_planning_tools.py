import json
import uuid
from types import SimpleNamespace

import pytest

from memory_knowledge import server


class PlanningPool:
    async def fetchrow(self, query, *args):
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
async def test_create_feature_tool_resolves_project(monkeypatch, planning_env):
    async def fake_resolve_project_id(pool, project_key):
        assert project_key == "proj-key"
        return 20

    async def fake_create_feature(pool, project_id, feature_status_id, priority_id, title, description=None, repository_keys=None):
        assert project_id == 20
        assert feature_status_id == 2
        assert priority_id == 4
        assert title == "Feature A"
        return {"feature_id": 11, "feature_key": str(uuid.uuid4()), "repository_count": 0}

    monkeypatch.setattr(server._planning, "resolve_project_id", fake_resolve_project_id)
    monkeypatch.setattr(server._planning, "create_feature", fake_create_feature)
    result = await server.create_feature(project_key="proj-key", title="Feature A")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["feature_id"] == 11


@pytest.mark.asyncio
async def test_create_task_tool_resolves_feature(monkeypatch, planning_env):
    async def fake_resolve_feature_id(pool, feature_key):
        assert feature_key == "feat-key"
        return 30

    async def fake_create_task(pool, feature_id, task_status_id, priority_id, title, description=None, repository_keys=None):
        assert feature_id == 30
        assert task_status_id == 3
        assert priority_id == 4
        return {"task_id": 12, "task_key": str(uuid.uuid4()), "repository_count": 0}

    monkeypatch.setattr(server._planning, "resolve_feature_id", fake_resolve_feature_id)
    monkeypatch.setattr(server._planning, "create_task", fake_create_task)
    result = await server.create_task(feature_key="feat-key", title="Task A")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["task_id"] == 12


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
