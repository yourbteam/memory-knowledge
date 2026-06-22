# MAWF Task Execution Lease Integration Handoff

This guide covers only the latest `mcp-agents-workflow` upgrade: task-scoped execution leases in the deployed `memory-knowledge` MCP server.

## Deployment Target

Remote MCP endpoint:

```text
https://memory-knowledge.azurewebsites.net/mcp/
```

Current deployed image:

```text
workfloworchreg.azurecr.io/memory-knowledge:211f677
```

The remote deployment has been smoke-tested with the lease tools listed below.

## Purpose

Task execution leases coordinate worker ownership for a MAWF task. They answer:

```text
Which worker currently owns execution for this task?
```

They do not store workflow telemetry, phase ledgers, workflow ledgers, artifact contents, DB-backed polling state, or execution history. Task folders and Git-persisted ledgers remain the source of truth for what happened during execution.

## Required Orchestrator Flow

For every executable MAWF task:

1. Create or resolve the MAWF task and workflow run as usual.
2. Call `mawf_acquire_task_execution_lease` before doing task work.
3. If `acquired` is `false`, do not execute from this worker.
4. If `acquired` is `true`, persist the returned `lease_token`.
5. Call `mawf_heartbeat_task_execution_lease` periodically while executing.
6. On terminal outcome or shutdown, call `mawf_release_task_execution_lease`.
7. Then update workflow/task terminal status with existing MAWF tools.

Suggested heartbeat interval:

```text
lease_ttl_seconds / 2
```

Default TTL is `60` seconds. The server accepts TTL values from `5` through `3600` seconds.

## New Catalog Types

The lease upgrade adds these MAWF-facing catalog types:

| Catalog type | Codes |
|---|---|
| `TASK_EXECUTION_LEASE_STATUS` | `active`, `released`, `expired`, `failed` |
| `TASK_EXECUTION_LEASE_RELEASE_REASON` | `completed`, `failed`, `cancelled`, `operator_cancelled`, `server_shutdown`, `stale_reclaimed` |

Discover them with:

```json
{
  "jsonrpc": "2.0",
  "id": "catalog-types",
  "method": "tools/call",
  "params": {
    "name": "mawf_list_catalog_types",
    "arguments": {}
  }
}
```

## New MCP Tools

| Tool | Purpose |
|---|---|
| `mawf_acquire_task_execution_lease` | Atomically acquire task execution ownership. |
| `mawf_heartbeat_task_execution_lease` | Extend a matching active lease. |
| `mawf_release_task_execution_lease` | Release a matching active lease. |
| `mawf_get_task_execution_lease` | Return active lease if present, otherwise latest lease. |
| `mawf_list_stale_task_execution_leases` | List open active leases whose expiry is stale. |

All write tools use the existing remote write guard.

## Acquire Lease

Call this before any worker begins task execution.

```json
{
  "jsonrpc": "2.0",
  "id": "acquire-task-lease",
  "method": "tools/call",
  "params": {
    "name": "mawf_acquire_task_execution_lease",
    "arguments": {
      "task_id": "mawf-task-id",
      "workflow_run_id": "mawf-workflow-run-id",
      "owner_user_id": "uuid-or-null",
      "owner_instance_id": "worker-instance-id",
      "owner_host": "host-or-null",
      "owner_process_id": "pid-or-null",
      "lease_ttl_seconds": 60,
      "metadata_json": {
        "worker_role": "executor"
      }
    }
  }
}
```

Important validation:

- `task_id` is the MAWF external task ID.
- `workflow_run_id` is optional, but if supplied it must already be linked to the same task through `mawf_upsert_workflow_run`.
- `owner_user_id` is optional, but if supplied it must exist in MAWF users.
- `owner_instance_id` is required.

Successful acquisition:

```json
{
  "ok": true,
  "acquired": true,
  "task_id": "mawf-task-id",
  "workflow_run_id": "mawf-workflow-run-id",
  "canonical_task_id": 24,
  "lease_token": "uuid",
  "expires_utc": "2026-05-08T08:55:00.000000+00:00",
  "stale_reclaimed": false,
  "lease": {
    "task_id": "mawf-task-id",
    "workflow_run_id": "mawf-workflow-run-id",
    "lease_token": "uuid",
    "owner_instance_id": "worker-instance-id",
    "status_code": "active",
    "acquired_utc": "...",
    "last_heartbeat_utc": "...",
    "expires_utc": "...",
    "released_utc": null
  }
}
```

Denied acquisition:

```json
{
  "ok": true,
  "acquired": false,
  "task_id": "mawf-task-id",
  "current_lease": {
    "workflow_run_id": "mawf-workflow-run-id",
    "owner_user_id": "uuid-or-null",
    "owner_instance_id": "current-worker",
    "status_code": "active",
    "last_heartbeat_utc": "...",
    "expires_utc": "..."
  }
}
```

Denied acquisition is not an error. It means another active, non-expired worker owns the task.

## Heartbeat Lease

Call periodically while the worker is still executing.

```json
{
  "jsonrpc": "2.0",
  "id": "heartbeat-task-lease",
  "method": "tools/call",
  "params": {
    "name": "mawf_heartbeat_task_execution_lease",
    "arguments": {
      "task_id": "mawf-task-id",
      "lease_token": "uuid-from-acquire",
      "lease_ttl_seconds": 60
    }
  }
}
```

Heartbeat succeeds only when:

- The task has an open active lease.
- The token matches.
- The lease has not expired.
- The lease has not been released.

Expected success data:

```json
{
  "ok": true,
  "task_id": "mawf-task-id",
  "lease": {
    "lease_token": "uuid-from-acquire",
    "status_code": "active",
    "last_heartbeat_utc": "...",
    "expires_utc": "..."
  }
}
```

Expected failure cases:

- `No active lease for task: <task_id>`
- `Lease token mismatch`
- `Lease expired`
- `Lease is released`

Treat these as ownership loss. The worker should stop executing or transition into recovery logic.

## Release Lease

Call when the worker exits ownership, including terminal workflow outcome and controlled shutdown.

```json
{
  "jsonrpc": "2.0",
  "id": "release-task-lease",
  "method": "tools/call",
  "params": {
    "name": "mawf_release_task_execution_lease",
    "arguments": {
      "task_id": "mawf-task-id",
      "lease_token": "uuid-from-acquire",
      "release_reason": "completed"
    }
  }
}
```

Valid `release_reason` values:

- `completed`
- `failed`
- `cancelled`
- `operator_cancelled`
- `server_shutdown`
- `stale_reclaimed`

Release is idempotent only when the same token has already been released with the same reason.

Expected success data:

```json
{
  "ok": true,
  "task_id": "mawf-task-id",
  "lease": {
    "lease_token": "uuid-from-acquire",
    "status_code": "released",
    "release_reason": "completed",
    "released_utc": "..."
  }
}
```

## Get Lease

Use this for diagnostics, resume, or handoff.

```json
{
  "jsonrpc": "2.0",
  "id": "get-task-lease",
  "method": "tools/call",
  "params": {
    "name": "mawf_get_task_execution_lease",
    "arguments": {
      "task_id": "mawf-task-id"
    }
  }
}
```

Response shape:

```json
{
  "ok": true,
  "task_id": "mawf-task-id",
  "canonical_task_id": 24,
  "has_active_lease": true,
  "lease": {
    "status_code": "active",
    "lease_token": "uuid",
    "owner_instance_id": "worker-instance-id",
    "expires_utc": "..."
  }
}
```

When `has_active_lease` is `false`, `lease` is the latest historical lease summary if one exists.

## List Stale Leases

Use this for recovery scans.

```json
{
  "jsonrpc": "2.0",
  "id": "list-stale-task-leases",
  "method": "tools/call",
  "params": {
    "name": "mawf_list_stale_task_execution_leases",
    "arguments": {
      "older_than_seconds": 60,
      "limit": 100
    }
  }
}
```

Behavior:

- Returns open active leases where `expires_utc` is older than the specified grace period.
- Default `older_than_seconds` is `60`.
- Default `limit` is `100`.
- Server caps `limit` at `500`.

To reclaim a stale lease, call `mawf_acquire_task_execution_lease` for that task. If the lease is expired, the server atomically:

1. Marks the old lease `expired`.
2. Sets release reason `stale_reclaimed`.
3. Sets `released_utc`.
4. Creates a new active lease.

## Recommended Worker State Machine

```text
queued/runnable task
  -> upsert workflow run as queued/running
  -> acquire lease
     -> acquired false: stop, requeue, or observe current owner
     -> acquired true: execute
          -> heartbeat loop
          -> terminal result
          -> release lease
          -> set workflow/task terminal status
```

If heartbeat fails:

```text
heartbeat error
  -> stop writing execution outputs
  -> do not release unless this worker still has a valid matching lease
  -> call get/list stale for diagnostics
  -> let recovery acquire after expiry
```

## Python Client Pattern

```python
import json
import os
import urllib.request

MCP_URL = "https://memory-knowledge.azurewebsites.net/mcp/"
MCP_API_KEY = os.environ["MEMORY_KNOWLEDGE_MCP_API_KEY"]


def call_mawf(tool_name: str, arguments: dict) -> dict:
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": tool_name,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        MCP_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {MCP_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        outer = json.loads(response.read().decode("utf-8"))

    payload = json.loads(outer["result"]["content"][0]["text"])
    if payload.get("status") != "success":
        raise RuntimeError(payload.get("error") or payload)
    return payload["data"]


lease = call_mawf(
    "mawf_acquire_task_execution_lease",
    {
        "task_id": "mawf-task-id",
        "workflow_run_id": "mawf-workflow-run-id",
        "owner_instance_id": "worker-1",
        "lease_ttl_seconds": 60,
    },
)

if not lease["acquired"]:
    raise SystemExit("Task is owned by another worker")

lease_token = lease["lease_token"]

try:
    call_mawf(
        "mawf_heartbeat_task_execution_lease",
        {
            "task_id": "mawf-task-id",
            "lease_token": lease_token,
            "lease_ttl_seconds": 60,
        },
    )
    # Execute task work here.
finally:
    call_mawf(
        "mawf_release_task_execution_lease",
        {
            "task_id": "mawf-task-id",
            "lease_token": lease_token,
            "release_reason": "completed",
        },
    )
```

## Live Smoke Evidence

The deployed endpoint was tested with a disposable task:

```json
{
  "task_id": "mawf-lease-smoke-005f8f3459",
  "workflow_run_id": "mawf-lease-run-005f8f3459",
  "acquired": true,
  "denied_acquired": false,
  "heartbeat_status": "active",
  "active_has_lease": true,
  "release_status": "released",
  "release_reason": "completed",
  "after_has_active": false,
  "lease_status_codes": ["active", "released", "expired", "failed"],
  "has_lease_catalogs": true
}
```

Remote readiness at deployment closeout:

```json
{
  "status": "ready",
  "degraded": [],
  "postgres": "ok",
  "qdrant": "ok",
  "neo4j": "ok"
}
```
