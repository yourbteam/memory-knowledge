# MCP Agents Workflow Remote MAWF Integration Handoff

## Audience

This guide is for the engineer or LLM integrating `mcp-agents-workflow` with the deployed `memory-knowledge` MCP server.

Use this guide when the orchestrator needs to create, update, retrieve, or summarize task memory through the new `mawf_*` MCP tools backed by the remote Supabase/Postgres database.

## Current Remote State

Remote MCP base URL:

```text
https://memory-knowledge.azurewebsites.net/mcp/
```

Health endpoints:

```text
https://memory-knowledge.azurewebsites.net/health
https://memory-knowledge.azurewebsites.net/ready
```

Deployment verified:

- Image: `workfloworchreg.azurecr.io/memory-knowledge:e16f857`
- Migration applied at startup: `015_intake_sessions -> 016_mawf_contract`
- Remote readiness after Neo4j resume: Postgres `ok`, Qdrant `ok`, Neo4j `ok`
- MAWF MCP CRUD smoke tests passed remotely through `/mcp/`

The integration should use the remote MCP endpoint. It should not connect directly to Supabase unless a separate operational/debug task explicitly requires that.

## Authentication

Every MCP request must send the memory-knowledge MCP bearer token:

```http
Authorization: Bearer <MCP_API_KEY>
Content-Type: application/json
Accept: application/json, text/event-stream
```

For Azure-hosted operations, the current key is stored in Key Vault:

```text
vault: hrness
secret: memory-knowledge-mcp-api-key
```

Do not hard-code this secret in `mcp-agents-workflow`. Load it from the deployment secret store or runtime environment.

## MCP Transport

Use the existing streamable HTTP MCP endpoint. Websocket-specific MAWF tools were intentionally not added because Python clients can call the HTTP MCP endpoint directly.

The request shape is standard JSON-RPC:

```json
{
  "jsonrpc": "2.0",
  "id": "request-id",
  "method": "tools/call",
  "params": {
    "name": "mawf_list_catalog_types",
    "arguments": {}
  }
}
```

The response content contains a JSON string in `result.content[0].text`. Parse that string as JSON to get the memory-knowledge tool envelope:

```json
{
  "run_id": "uuid",
  "tool_name": "mawf_list_catalog_types",
  "status": "success",
  "data": {},
  "error": null,
  "duration_ms": null
}
```

Treat `status != "success"` as a failed tool call even if the outer JSON-RPC response is HTTP 200.

## Contract Boundary

The `mawf_*` tools are an MCP/API contract over canonical memory-knowledge storage.

Do not create duplicate physical tables named `users`, `projects`, `repositories`, or `tasks` in `public`.

Canonical storage is:

- `core.reference_types`
- `core.reference_values`
- `core.users`
- `planning.projects`
- `catalog.repositories`
- `ops.mawf_prompts`
- `planning.tasks`
- `planning.mawf_artifact_refs`

The orchestrator should speak in MAWF external identifiers and MAWF codes. The server translates those into canonical internal IDs and reference values.

## Reference Codes

Prefer codes over internal numeric IDs in all client code.

Supported catalog type codes:

- `USER_ROLE`
- `USER_STATUS`
- `PROJECT_STATUS`
- `REPOSITORY_STATUS`
- `TASK_STATUS`
- `ARTIFACT_ROLE`
- `ARTIFACT_PERSIST_STATUS`

Seeded MAWF value codes:

| Type | Codes |
|---|---|
| `USER_ROLE` | `admin`, `employee` |
| `USER_STATUS` | `active`, `inactive` |
| `PROJECT_STATUS` | `active`, `inactive` |
| `REPOSITORY_STATUS` | `active`, `inactive` |
| `TASK_STATUS` | `active`, `completed`, `cancelled`, `failed` |
| `ARTIFACT_ROLE` | `initial_prompt`, `normalized_prompt`, `task_ledger` |
| `ARTIFACT_PERSIST_STATUS` | `local_only`, `persist_pending`, `persisted`, `persist_failed` |

The database enforces reference-type correctness. For example, `completed` is valid as a task status, but invalid as a user role. Invalid type usage returns a tool failure such as `Invalid USER_ROLE value: completed`.

## Tool Groups

### Catalog Tools

Use these to discover and manage MAWF reference data.

| Tool | Purpose |
|---|---|
| `mawf_list_catalog_types` | List MAWF-facing catalog/reference types. |
| `mawf_list_catalog_values` | List values, optionally filtered by `catalog_type_code`. |
| `mawf_upsert_catalog_value` | Create or update a MAWF external code for a catalog type. |
| `mawf_deactivate_catalog_value` | Soft-disable a catalog value by type and code. |

Use catalog writes sparingly. Normal task execution should use existing seeded values.

### User Tools

| Tool | Purpose |
|---|---|
| `mawf_upsert_user` | Create/update a user by email and optional UUID. |
| `mawf_get_user` | Read a user by `user_id` or `email`. |
| `mawf_list_users` | List users, optionally by status. |
| `mawf_deactivate_user` | Set user status to `inactive`. |

Recommended user behavior:

- Resolve or create the actor before creating prompts or tasks.
- Use the real actor email when available.
- Use `role_code: "employee"` unless the caller is known to be an admin.

### Project Tools

| Tool | Purpose |
|---|---|
| `mawf_upsert_project` | Create/update a project over `planning.projects`. |
| `mawf_get_project` | Read by UUID `project_id` or text `project_key`. |
| `mawf_list_projects` | List projects, optionally by status. |
| `mawf_archive_project` | Set project status to inactive. |

`project_id` is the MAWF UUID identity. `project_key` is the stable external text key. Pass both when creating a project if the orchestrator already has a UUID.

### Repository Tools

| Tool | Purpose |
|---|---|
| `mawf_upsert_repository` | Create/update a repository and optional project link. |
| `mawf_get_repository` | Read by UUID `repository_id` or `repository_key`. |
| `mawf_list_repositories` | List repositories, optionally by status. |
| `mawf_deactivate_repository` | Set repository status to inactive. |

When `project_id` is passed to `mawf_upsert_repository`, the server maintains the canonical `planning.project_repositories` link. Use this so later task creation has a valid project/repository relationship.

### Prompt Tools

| Tool | Purpose |
|---|---|
| `mawf_create_prompt` | Create an immutable prompt reference record. |
| `mawf_get_prompt` | Read prompt by UUID. |
| `mawf_get_prompt_by_hash` | Read prompt by normalized hash. |
| `mawf_list_prompts_by_user` | List prompt refs for a user. |
| `mawf_supersede_prompt_ref` | Create a replacement prompt ref linked to an existing one. |

Prompt records store references, not full prompt content. The orchestrator should persist full prompt artifacts wherever its artifact policy requires, then pass stable refs such as `file://`, `s3://`, `repo://`, or another durable URI.

Do not edit prompt content in place. If a normalized prompt changes, create a new prompt record or use `mawf_supersede_prompt_ref`.

### Task Tools

| Tool | Purpose |
|---|---|
| `mawf_upsert_task` | Create/update a task over `planning.tasks`. |
| `mawf_get_task` | Read task by MAWF task ID. |
| `mawf_list_tasks` | List tasks by owner, project, repository, or status. |
| `mawf_cancel_task` | Set task status to `cancelled`. |
| `mawf_complete_task` | Set task status to `completed`. |
| `mawf_fail_task` | Set task status to `failed`. |

Task IDs are external orchestrator IDs. They are text, not UUIDs. Use stable IDs that `mcp-agents-workflow` can reuse across retries.

The task write path expects:

- `task_id`
- `owner_user_id`
- `project_id`
- `repository_id`
- `prompt_id`
- `title`
- `task_ledger_ref`
- optional `status_code`, default `active`

Complete, cancel, and fail are soft lifecycle transitions. There is no hard-delete MAWF task tool.

### Workflow Run Tools

Use these tools when `mcp-agents-workflow` needs to persist a workflow execution under a MAWF task without switching to the older non-prefixed workflow-run API.

| Tool | Purpose |
|---|---|
| `mawf_upsert_workflow_run` | Create/update a workflow run and link it to a MAWF task. |
| `mawf_get_workflow_run` | Read one workflow run by MAWF external workflow run ID. |
| `mawf_list_workflow_runs` | List workflow runs linked to a MAWF task. |

`workflow_run_id` may be a UUID or a text orchestrator ID such as `raw-mawf-run-1778171339`. The server stores a deterministic canonical UUID internally and returns both:

- `workflow_run_id`: the external MAWF/orchestrator ID.
- `canonical_run_id`: the UUID used by canonical `ops.workflow_runs`.

Accepted MAWF workflow status codes:

| MAWF status | Canonical workflow status |
|---|---|
| `queued` | `RUN_PENDING` |
| `pending` | `RUN_PENDING` |
| `submitted` | `RUN_SUBMITTED` |
| `running` | `RUN_RUNNING` |
| `completed` | `RUN_SUCCESS` |
| `success` | `RUN_SUCCESS` |
| `partial` | `RUN_PARTIAL` |
| `failed` | `RUN_ERROR` |
| `error` | `RUN_ERROR` |
| `cancelled` | `RUN_CANCELLED` |
| `canceled` | `RUN_CANCELLED` |

The workflow ledger and state refs are stored in workflow-run context:

- `workflow_ledger_ref`
- `workflow_state_ref`

These refs are returned by `mawf_get_workflow_run`, `mawf_list_workflow_runs`, and inside `mawf_get_task_memory_bundle.workflow_runs`.

### Artifact Reference Tools

| Tool | Purpose |
|---|---|
| `mawf_upsert_artifact_ref` | Create/update one artifact ref for a task and role. |
| `mawf_get_artifact_ref` | Read by artifact UUID, or by `task_id` plus `role_code`. |
| `mawf_list_artifact_refs` | List artifact refs for a task. |
| `mawf_set_artifact_persist_status` | Update persistence status. |

The server enforces one artifact ref per `(task_id, role_code)`. Upserting `task_ledger` for the same task updates that role's artifact ref rather than creating duplicates.

Use these roles for the initial integration:

- `initial_prompt`
- `normalized_prompt`
- `task_ledger`

Use persistence status as follows:

- `local_only`: artifact exists locally or ephemerally.
- `persist_pending`: orchestrator intends to persist it but has not confirmed yet.
- `persisted`: artifact is durably available at `artifact_path`.
- `persist_failed`: persistence was attempted and failed.

### Bundle Read Tool

| Tool | Purpose |
|---|---|
| `mawf_get_task_memory_bundle` | Return the task plus related memory surfaces needed by the orchestrator. |

Use this when resuming, auditing, or reconstructing a task. The remote smoke response returned these top-level keys:

- `task`
- `owner`
- `project`
- `repository`
- `prompt`
- `artifact_refs`
- `workflow_runs`
- `available_memory_surfaces`

The bundle may also include linked workflow artifacts, phases, validator results, findings summary, and triage/adaptation summaries when those canonical surfaces exist for the task.

## Recommended Orchestrator Flow

For a new task:

1. Call `mawf_upsert_user`.
2. Call `mawf_upsert_project`.
3. Call `mawf_upsert_repository` with `project_id`.
4. Persist initial and normalized prompt artifacts in the orchestrator's artifact store.
5. Call `mawf_create_prompt`.
6. Call `mawf_upsert_task`.
7. Call `mawf_upsert_artifact_ref` for `initial_prompt`.
8. Call `mawf_upsert_artifact_ref` for `normalized_prompt`.
9. Call `mawf_upsert_artifact_ref` for `task_ledger`.
10. Call `mawf_upsert_workflow_run` when a workflow execution is queued or starts.
11. During execution, update artifact persistence with `mawf_set_artifact_persist_status`.
12. Update workflow-run status with `mawf_upsert_workflow_run` as the workflow progresses.
13. On terminal outcome, call `mawf_complete_task`, `mawf_fail_task`, or `mawf_cancel_task`.
14. On resume or handoff, call `mawf_get_task_memory_bundle`.

For an existing task:

1. Call `mawf_get_task`.
2. If found, call `mawf_get_task_memory_bundle`.
3. Reconcile missing artifact refs with `mawf_upsert_artifact_ref`.
4. Continue execution using the returned owner/project/repository/prompt context.

For prompt correction:

1. Persist corrected prompt artifacts.
2. Call `mawf_supersede_prompt_ref`.
3. Call `mawf_upsert_task` with the new `prompt_id` if the task should point at the corrected prompt.
4. Add or update artifact refs for corrected prompt artifacts.

## Python Client Example

This example intentionally uses only the Python standard library.

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

    with urllib.request.urlopen(request, timeout=40) as response:
        outer = json.loads(response.read().decode("utf-8"))

    if "error" in outer:
        raise RuntimeError(outer["error"])

    text_payload = outer["result"]["content"][0]["text"]
    payload = json.loads(text_payload)
    if payload.get("status") != "success":
        raise RuntimeError(payload.get("error") or payload)
    return payload["data"]


user = call_mawf(
    "mawf_upsert_user",
    {
        "email": "operator@example.com",
        "display_name": "Operator",
        "role_code": "employee",
        "status_code": "active",
    },
)

project = call_mawf(
    "mawf_upsert_project",
    {
        "project_key": "workflow-orchestrator",
        "display_name": "Workflow Orchestrator",
        "status_code": "active",
    },
)
```

## Minimal Task Creation Example

```json
{
  "jsonrpc": "2.0",
  "id": "create-task",
  "method": "tools/call",
  "params": {
    "name": "mawf_upsert_task",
    "arguments": {
      "task_id": "workflow-task-2026-05-07-001",
      "owner_user_id": "39dbf727-aa07-47aa-8184-71b4bd528ea6",
      "project_id": "79213b60-df8a-4e5f-b80e-7bd4d8c4fdca",
      "repository_id": "f9cf5855-8a52-45a5-8f35-eb603619cab4",
      "prompt_id": "dbff8c7b-558c-48d5-8519-cb3fc9d9c3f3",
      "title": "Implement task workflow integration",
      "task_ledger_ref": "repo://Tasks/workflow-task-2026-05-07-001/ledger.md",
      "status_code": "active"
    }
  }
}
```

## Error Handling Rules

Handle these cases explicitly:

- HTTP `401`: missing or invalid MCP API key.
- HTTP timeout: retry with backoff; do not blindly duplicate task IDs.
- JSON-RPC `error`: transport-level MCP failure.
- Tool envelope `status != "success"`: application or database validation failure.
- Reference errors such as `Invalid USER_ROLE value`: caller passed a valid code in the wrong reference context.
- Unique/hash conflicts: call the matching get tool and reconcile instead of creating a duplicate.

Writes are idempotent where the tool is named `upsert`. Status/lifecycle tools are safe to call repeatedly if the desired state is the same.

## Remote Smoke Evidence

The following remote paths were tested successfully through the deployed `/mcp/` endpoint:

- `mawf_list_catalog_types`
- `mawf_list_catalog_values`
- `mawf_upsert_catalog_value`
- `mawf_deactivate_catalog_value`
- `mawf_upsert_user`
- `mawf_get_user`
- `mawf_list_users`
- `mawf_deactivate_user`
- `mawf_upsert_project`
- `mawf_get_project`
- `mawf_list_projects`
- `mawf_archive_project`
- `mawf_upsert_repository`
- `mawf_get_repository`
- `mawf_list_repositories`
- `mawf_deactivate_repository`
- `mawf_create_prompt`
- `mawf_get_prompt`
- `mawf_get_prompt_by_hash`
- `mawf_list_prompts_by_user`
- `mawf_supersede_prompt_ref`
- `mawf_upsert_task`
- `mawf_get_task`
- `mawf_list_tasks`
- `mawf_cancel_task`
- `mawf_complete_task`
- `mawf_fail_task`
- `mawf_upsert_workflow_run`
- `mawf_get_workflow_run`
- `mawf_list_workflow_runs`
- `mawf_upsert_artifact_ref`
- `mawf_get_artifact_ref`
- `mawf_list_artifact_refs`
- `mawf_set_artifact_persist_status`
- `mawf_get_task_memory_bundle`

Disposable remote smoke records:

```json
{
  "main_task_id": "mawf-smoke-1778168595",
  "edge_task_id": "mawf-edge-1778168636",
  "main_user_id": "39dbf727-aa07-47aa-8184-71b4bd528ea6",
  "main_project_id": "79213b60-df8a-4e5f-b80e-7bd4d8c4fdca",
  "main_repository_id": "f9cf5855-8a52-45a5-8f35-eb603619cab4",
  "main_prompt_id": "dbff8c7b-558c-48d5-8519-cb3fc9d9c3f3",
  "main_artifact_ref_id": "e41416d5-023a-4f8c-a724-d1ccf743663f"
}
```

Negative validation tested remotely:

- User role rejected task status code `completed`.
- Artifact role rejected persistence status code `persisted`.

## Implementation Checklist For `mcp-agents-workflow`

- Configure `MEMORY_KNOWLEDGE_MCP_URL` as `https://memory-knowledge.azurewebsites.net/mcp/`.
- Configure `MEMORY_KNOWLEDGE_MCP_API_KEY` from secret storage.
- Add a reusable MCP `tools/call` client that parses the nested memory-knowledge envelope.
- Add typed wrappers for every `mawf_*` tool the orchestrator will call.
- Create or resolve the actor user before prompt/task writes.
- Ensure project and repository are upserted and linked before task writes.
- Store prompt and ledger content externally, then pass refs into MAWF tools.
- Persist workflow executions with `mawf_upsert_workflow_run` using stable external workflow run IDs.
- Use `mawf_get_task_memory_bundle` for resume/handoff.
- Treat deletes as lifecycle transitions, not hard deletes.
- Add integration tests against a disposable task ID prefix.
- Add negative tests for reference-code misuse.

## Operational Notes

The MAWF schema and tools are additive. Existing memory-knowledge tools remain backward compatible.

If a future deployment has issues, disable the external `mawf_*` caller first. The underlying schema can remain in place because it is additive.

If `/ready` reports degradation, inspect the component fields. MAWF depends primarily on Postgres/Supabase. Qdrant and Neo4j degradation may affect wider memory surfaces in `mawf_get_task_memory_bundle`, but basic MAWF CRUD depends on Postgres.
