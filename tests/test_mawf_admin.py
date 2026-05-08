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


class ArtifactAdminPool:
    def __init__(self, *, role_rows=None):
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.fetch_calls: list[tuple[str, tuple]] = []
        self.role_rows = role_rows or []
        self.artifact_id = uuid.uuid4()

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "FROM core.reference_values rv" in query and "rt.internal_code = $1" in query:
            values = {
                ("ARTIFACT_ROLE", "task_ledger"): {"id": 12, "internal_code": "ARTIFACT_TASK_LEDGER", "mawf_code": "task_ledger", "display_name": "Task Ledger", "description": None, "sort_order": 10, "is_active": True, "is_terminal": False},
                ("ARTIFACT_ROLE", "workflow_ledger"): {"id": 13, "internal_code": "ARTIFACT_WORKFLOW_LEDGER", "mawf_code": "workflow_ledger", "display_name": "Workflow Ledger", "description": None, "sort_order": 20, "is_active": True, "is_terminal": False},
                ("ARTIFACT_PERSIST_STATUS", "local_only"): {"id": 60, "internal_code": "ARTIFACT_LOCAL_ONLY", "mawf_code": "local_only", "display_name": "Local Only", "description": None, "sort_order": 10, "is_active": True, "is_terminal": False},
            }
            return values.get((args[0], args[1]))
        if "INSERT INTO planning.mawf_artifact_refs" in query:
            return {"id": self.artifact_id}
        if "WHERE ar.id = $1::uuid" in query:
            return {
                "id": args[0],
                "mawf_task_id": "task-a",
                "artifact_key": "workflow:run-a:ledger",
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


@pytest.mark.asyncio
async def test_upsert_artifact_ref_uses_artifact_key_for_conflict_identity():
    pool = ArtifactAdminPool()
    result = await mawf.upsert_artifact_ref(
        pool,
        task_id="task-a",
        role_code="workflow_ledger",
        artifact_path="repo://workflow-ledger.json",
        artifact_key="workflow:run-a:ledger",
    )

    insert_query, insert_args = [
        call for call in pool.fetchrow_calls if "INSERT INTO planning.mawf_artifact_refs" in call[0]
    ][0]
    assert "artifact_key" in insert_query
    assert "ON CONFLICT (mawf_task_id, artifact_key)" in insert_query
    assert insert_args[2] == "workflow:run-a:ledger"
    assert result["artifact_key"] == "workflow:run-a:ledger"


@pytest.mark.asyncio
async def test_upsert_artifact_ref_defaults_artifact_key_to_role_code():
    pool = ArtifactAdminPool()
    await mawf.upsert_artifact_ref(
        pool,
        task_id="task-a",
        role_code="task_ledger",
        artifact_path="repo://task-ledger.json",
    )

    _, insert_args = [
        call for call in pool.fetchrow_calls if "INSERT INTO planning.mawf_artifact_refs" in call[0]
    ][0]
    assert insert_args[2] == "task_ledger"


@pytest.mark.asyncio
async def test_get_artifact_ref_rejects_ambiguous_role_lookup():
    row = {
        "id": uuid.uuid4(),
        "mawf_task_id": "task-a",
        "artifact_key": "workflow:run-a:ledger",
        "role_id": 13,
        "role_code": "workflow_ledger",
        "artifact_path": "repo://workflow-ledger.json",
        "content_hash": None,
        "persist_status_id": 60,
        "persist_status_code": "local_only",
        "created_utc": None,
        "updated_utc": None,
    }
    pool = ArtifactAdminPool(role_rows=[row, {**row, "id": uuid.uuid4(), "artifact_key": "workflow:run-b:ledger"}])

    with pytest.raises(ValueError, match="provide artifact_ref_id or artifact_key"):
        await mawf.get_artifact_ref(pool, task_id="task-a", role_code="workflow_ledger")


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
                ("TASK_EXECUTION_LEASE_STATUS", "active"): {"id": 701, "internal_code": "LEASE_ACTIVE", "mawf_code": "active", "display_name": "Active", "description": None, "sort_order": 10, "is_active": True, "is_terminal": False},
                ("TASK_EXECUTION_LEASE_STATUS", "released"): {"id": 702, "internal_code": "LEASE_RELEASED", "mawf_code": "released", "display_name": "Released", "description": None, "sort_order": 20, "is_active": True, "is_terminal": True},
                ("TASK_EXECUTION_LEASE_STATUS", "expired"): {"id": 703, "internal_code": "LEASE_EXPIRED", "mawf_code": "expired", "display_name": "Expired", "description": None, "sort_order": 30, "is_active": True, "is_terminal": True},
                ("TASK_EXECUTION_LEASE_RELEASE_REASON", "completed"): {"id": 801, "internal_code": "LEASE_REASON_COMPLETED", "mawf_code": "completed", "display_name": "Completed", "description": None, "sort_order": 10, "is_active": True, "is_terminal": False},
                ("TASK_EXECUTION_LEASE_RELEASE_REASON", "stale_reclaimed"): {"id": 806, "internal_code": "LEASE_REASON_STALE_RECLAIMED", "mawf_code": "stale_reclaimed", "display_name": "Stale Reclaimed", "description": None, "sort_order": 60, "is_active": True, "is_terminal": False},
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
        query for query, _ in pool.fetchrow_calls
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
    assert not [
        query for query, _ in pool.fetchrow_calls
        if "INSERT INTO ops.mawf_task_execution_leases" in query
    ]


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
        args for query, args in pool.execute_calls
        if "UPDATE ops.mawf_task_execution_leases" in query
        and "release_reason_value_id" in query
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
