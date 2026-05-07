import uuid

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
                ("TASK_STATUS", "active"): {"id": 10, "internal_code": "TASK_TODO", "mawf_code": "active", "display_name": "Active", "description": None, "sort_order": 10, "is_active": True, "is_terminal": False},
                ("PRIORITY", "PRIO_MEDIUM"): {"id": 11, "internal_code": "PRIO_MEDIUM", "mawf_code": None, "display_name": "Medium", "description": None, "sort_order": 10, "is_active": True, "is_terminal": False},
                ("ARTIFACT_ROLE", "task_ledger"): {"id": 12, "internal_code": "ARTIFACT_TASK_LEDGER", "mawf_code": "task_ledger", "display_name": "Task Ledger", "description": None, "sort_order": 10, "is_active": True, "is_terminal": False},
            }
            return values.get((type_code, value_code))
        if "SELECT id FROM core.reference_types WHERE internal_code = $1" in query:
            return {"id": 77}
        if "SELECT id FROM catalog.repositories WHERE mawf_repository_id = $1::uuid" in query:
            return {"id": 200}
        if "FROM planning.projects p" in query and "p.project_key = $1::uuid" in query:
            return {"id": 100, "project_key": args[0], "mawf_project_key": "proj-a", "name": "Project A", "project_status_id": 1, "created_utc": None, "updated_utc": None, "status_code": "active"}
        if "UPDATE planning.tasks" in query and "WHERE mawf_task_id = $1" in query:
            return None
        if "INSERT INTO planning.tasks" in query:
            return {"id": 300}
        if "FROM planning.tasks t" in query and "WHERE t.mawf_task_id = $1" in query:
            return {
                "mawf_task_id": args[0],
                "owner_user_id": uuid.uuid4(),
                "project_key": uuid.uuid4(),
                "mawf_repository_id": uuid.uuid4(),
                "prompt_id": uuid.uuid4(),
                "title": "Task A",
                "task_status_id": 10,
                "task_ledger_ref": "ledger://task-a",
                "created_utc": None,
                "updated_utc": None,
                "status_code": "active",
            }
        return None

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


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
    link_calls = [
        call for call in pool.execute_calls
        if "INSERT INTO planning.project_repositories" in call[0]
    ]
    assert link_calls
    assert link_calls[0][1] == (100, 200)
