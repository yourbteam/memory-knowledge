# MCP Agents Workflow Artifact Reference Keys Handoff

Status: partially superseded by `Tasks/task-branch-artifact-metadata/analysis.md` and `Tasks/task-branch-artifact-metadata/plan.md`.

The task-branch artifact metadata contract changes omitted-key behavior: omitted or blank `artifact_key` must remain `NULL`, and legacy role-only refs are identified by `(task_id, role_code)` only when `artifact_key IS NULL`.

This guide covers only the latest `mcp-agents-workflow` upgrade: MAWF artifact reference expansion through stable `artifact_key` values.

Remote MCP endpoint:

```text
https://memory-knowledge.azurewebsites.net/mcp/
```

Current deployed image:

```text
workfloworchreg.azurecr.io/memory-knowledge:2dc09a5
sha256:489e8781b8e528432b8fdafe35f867ab040e55821017d8981a98718bd867e2e6
```

Historical migration applied at the time of this handoff:

```text
018_mawf_artifact_ref_keys
```

This is pre-`022` historical deployment evidence. The task-branch metadata implementation plan supersedes the omitted-key behavior and uniqueness semantics from that deployment.

Historical remote readiness at closeout: Postgres `ok`, Qdrant `ok`, Neo4j `ok`.

## Purpose

Memory-knowledge supports multiple durable artifact references under the same MAWF task and role.

The task-branch metadata contract uses two artifact-ref identity rules:

```text
keyed refs: unique(task_id, artifact_key) where artifact_key is not null
legacy refs: unique(task_id, role_code) where artifact_key is null
```

For keyed refs, `role_code` is category metadata, not the unique address. For legacy null-key refs, `role_code` remains the singleton lookup identity.

Do not store artifact contents in memory-knowledge. Do not store phase status, phase telemetry, execution history, or producer/verifier/critic output in memory-knowledge. Store files durably elsewhere, then index only their references in `artifact_path`.

## New Contract

`mawf_upsert_artifact_ref` accepts optional `artifact_key`.

If `artifact_key` is omitted or blank, memory-knowledge stores and returns `artifact_key: null`. This preserves the observable legacy/null signal for singleton calls such as:

- `initial_prompt`
- `normalized_prompt`
- `task_ledger`

For any workflow, phase, generated artifact, or feedback ref, always pass an explicit `artifact_key`.

New artifact role codes are available:

- `workflow_ledger`
- `workflow_state`
- `phase_ledger`
- `telemetry_jsonl`
- `telemetry_summary`
- `generated_artifact`
- `feedback_payload`

Returned artifact refs now include:

```json
{
  "id": "artifact-ref-uuid",
  "task_id": "mawf-task-id",
  "artifact_key": "workflow:run-id:ledger",
  "artifactKey": "workflow:run-id:ledger",
  "artifact_branch": "artifacts/mawf-task-id",
  "artifactBranch": "artifacts/mawf-task-id",
  "role_code": "workflow_ledger",
  "artifact_path": "repo://...",
  "content_hash": null,
  "persist_status_code": "persisted",
  "created_at": "...",
  "updated_at": "..."
}
```

## Required Orchestrator Behavior

Use deterministic keys under the task:

```text
workflow:<workflow_run_id>:ledger
workflow:<workflow_run_id>:state
phase:<workflow_run_id>:<phase_id>:ledger
phase:<workflow_run_id>:<phase_id>:telemetry_jsonl
phase:<workflow_run_id>:<phase_id>:telemetry_summary
artifact:<workflow_run_id>:<artifact_name>
artifact:<workflow_run_id>:<phase_id>:<artifact_name>
feedback:<workflow_run_id>:<feedback_name>
feedback:<workflow_run_id>:<phase_id>:<feedback_name>
```

Rules:

- Reusing the same `task_id + artifact_key` updates the same artifact ref.
- Omitting or blanking `artifact_key` writes a legacy null-key ref.
- Two refs may share the same `role_code` if their `artifact_key` values differ.
- Use `artifact_ref_id` or `task_id + artifact_key` for exact reads.
- Use `task_id + role_code` only for legacy refs where `artifact_key IS NULL`; keyed rows are intentionally ignored by role-only lookup.
- Continue using `mawf_set_artifact_persist_status` by `artifact_ref_id`.

## MCP Calls

Create or update a singleton task ledger ref:

```json
{
  "jsonrpc": "2.0",
  "id": "task-ledger-ref",
  "method": "tools/call",
  "params": {
    "name": "mawf_upsert_artifact_ref",
    "arguments": {
      "task_id": "mawf-task-123",
      "role_code": "task_ledger",
      "artifact_path": "repo://Tasks/mawf-task-123/ledger.md",
      "persist_status_code": "persisted"
    }
  }
}
```

Expected returned singleton payload preserves the null key:

```json
{
  "id": "artifact-ref-uuid",
  "task_id": "mawf-task-123",
  "artifact_key": null,
  "artifactKey": null,
  "artifact_branch": null,
  "artifactBranch": null,
  "role_code": "task_ledger",
  "artifact_path": "repo://Tasks/mawf-task-123/ledger.md",
  "persist_status_code": "persisted"
}
```

Create or update a workflow ledger ref:

```json
{
  "jsonrpc": "2.0",
  "id": "workflow-ledger-ref",
  "method": "tools/call",
  "params": {
    "name": "mawf_upsert_artifact_ref",
    "arguments": {
      "task_id": "mawf-task-123",
      "role_code": "workflow_ledger",
      "artifact_key": "workflow:mawf-run-001:ledger",
      "artifact_path": "repo://Tasks/mawf-task-123/workflows/full-task-workflow/runs/mawf-run-001/workflow-ledger.json",
      "persist_status_code": "persisted"
    }
  }
}
```

Read a specific multi-ref:

```json
{
  "jsonrpc": "2.0",
  "id": "get-workflow-ledger-ref",
  "method": "tools/call",
  "params": {
    "name": "mawf_get_artifact_ref",
    "arguments": {
      "task_id": "mawf-task-123",
      "artifact_key": "workflow:mawf-run-001:ledger"
    }
  }
}
```

List all refs for a task:

```json
{
  "jsonrpc": "2.0",
  "id": "list-artifact-refs",
  "method": "tools/call",
  "params": {
    "name": "mawf_list_artifact_refs",
    "arguments": {
      "task_id": "mawf-task-123"
    }
  }
}
```

Update persistence status:

```json
{
  "jsonrpc": "2.0",
  "id": "set-artifact-persisted",
  "method": "tools/call",
  "params": {
    "name": "mawf_set_artifact_persist_status",
    "arguments": {
      "artifact_ref_id": "artifact-ref-uuid",
      "persist_status_code": "persisted"
    }
  }
}
```

## Historical Remote Smoke Evidence

This evidence was collected before the planned `022_mawf_task_artifact_branch_metadata` migration. It proves the earlier artifact-key expansion, not the final task-branch metadata contract.

The deployed endpoint was tested with disposable task:

```text
mawf-artifact-key-artifact-key-1778234195-e507efce
```

Verified remotely:

- New `ARTIFACT_ROLE` codes are present.
- A disposable user, project, repository, prompt, and task can be created.
- Two `workflow_ledger` refs can exist under the same task with different `artifact_key` values.
- `mawf_list_artifact_refs` returns both keys.
- `mawf_get_artifact_ref` works by `task_id + artifact_key`.
- `mawf_get_artifact_ref` works for legacy null-key refs with `task_id + role_code`.
- Keyed refs are read by `artifact_ref_id` or `task_id + artifact_key`, not role-only lookup.

Health at deployment closeout:

```json
{"status":"ok"}
```

Readiness at deployment closeout:

```json
{"status":"ready","degraded":[],"postgres":"ok","qdrant":"ok","neo4j":"ok"}
```

## Integration Checklist

- Add `artifact_key` to the mcp-agents-workflow artifact-ref wrapper.
- Keep singleton callers working by omitting `artifact_key` only when a legacy null-key ref is intended.
- Generate deterministic `artifact_key` values for workflow, phase, generated artifact, and feedback refs.
- Store artifact contents outside memory-knowledge.
- Pass only durable refs in `artifact_path`.
- Read multi-ref artifacts by `artifact_ref_id` or `task_id + artifact_key`.
- Expect role-only lookup to be valid only for legacy singleton refs with `artifact_key IS NULL`.
