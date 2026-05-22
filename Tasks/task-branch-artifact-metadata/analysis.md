## Objective

Implement memory-knowledge support for task-scoped artifact branch metadata so workflow-orch can later persist each MAWF task's artifacts to its own Git branch.

This slice is memory-knowledge only. It must not create workflow-orch runtime behavior, artifact worktrees, Git branches, or branch-writing logic.

## Task Classification

- Type: schema and MAWF API contract expansion
- Size: heavy
- Rationale: includes database migrations, public MCP tool payload changes, compatibility-sensitive uniqueness rules, and cross-surface contract discovery used by another system.

## Requested Contract

Add nullable metadata fields:

- `planning.tasks.task_artifact_branch TEXT`
- `planning.mawf_artifact_refs.artifact_branch TEXT`
- `planning.mawf_artifact_refs.artifact_key TEXT`

Preserve nulls for legacy records:

- Existing task rows should have `task_artifact_branch = NULL`.
- Existing artifact refs should have `artifact_branch = NULL`.
- Existing artifact refs should have `artifact_key = NULL`.
- Missing branch/key metadata must remain observable so workflow-orch can apply its own explicit legacy fallback later.

Artifact-ref uniqueness must become:

- Keyed refs: unique `(mawf_task_id, artifact_key)` where `artifact_key IS NOT NULL`.
- Legacy refs: unique `(mawf_task_id, role_id)` where `artifact_key IS NULL`.

The implementation must not backfill fake `artifact_key` values for old rows.

## Current-State Facts

MAWF schema starts in `migrations/versions/016_mawf_contract.py`.

- `planning.tasks` currently has MAWF-facing columns including `mawf_task_id`, `owner_user_id`, `prompt_id`, and `task_ledger_ref`.
- `planning.mawf_artifact_refs` is created with `mawf_task_id`, `role_id`, `artifact_path`, `content_hash`, and `persist_status_id`.
- The original artifact-ref uniqueness rule was `CONSTRAINT uq_mawf_artifact_refs_task_role UNIQUE (mawf_task_id, role_id)`.

Migration `migrations/versions/018_mawf_artifact_ref_keys.py` already introduced `artifact_key`, but its existing behavior conflicts with the new requirements:

- It adds `artifact_key`.
- It backfills `artifact_key` from `COALESCE(role.mawf_code, role.internal_code)`.
- It makes `artifact_key` `NOT NULL`.
- It replaces role uniqueness with a single unique index on `(mawf_task_id, artifact_key)`.

That was coherent for the earlier "make every artifact addressable by key" contract, but it is not coherent for this task's newer "preserve whether the client supplied a key" contract.

Current artifact-ref API behavior also conflicts with the new requirements:

- `src/memory_knowledge/admin/mawf.py` defaults omitted `artifact_key` to `role_code`.
- `upsert_artifact_ref` writes every row with a non-null key.
- `tests/test_mawf_admin.py` currently asserts that omitted `artifact_key` defaults to `role_code`.

The implementation must change these semantics so omitted `artifact_key` remains `NULL`.

## Source Artifacts Inspected

- `migrations/versions/016_mawf_contract.py`
- `migrations/versions/018_mawf_artifact_ref_keys.py`
- `src/memory_knowledge/admin/mawf.py`
- `src/memory_knowledge/server.py`
- `tests/test_mawf_admin.py`
- `tests/test_mawf_contract_migration.py`
- `tests/test_mawf_contract_tools.py`
- `docs/MCP_AGENTS_WORKFLOW_ARTIFACT_REF_KEYS_HANDOFF.md`
- `docs/MCP_AGENTS_WORKFLOW_REMOTE_MAWF_HANDOFF.md`

## Resolved Decisions

- Add migration `022_mawf_task_artifact_branch_metadata.py` after `021_mawf_external_task_id`.
- The migration must add the branch columns, make `artifact_key` nullable, drop the old full `(mawf_task_id, artifact_key)` uniqueness, and install the two partial unique indexes.
- Correct existing `018` role-derived keys by setting `artifact_key = NULL` only when the current key equals the resolved role `mawf_code` or `internal_code`; preserve non-role explicit keys.
- Run and record a remote preflight query before deployment to count role-equivalent keys and non-role keys in `planning.mawf_artifact_refs`.
- Artifact-ref writes use this identity order:
  - if `artifact_ref_id` is supplied, update that row first
  - else if normalized `artifact_key` is non-null, update by `(mawf_task_id, artifact_key)`
  - else update by legacy `(mawf_task_id, role_id)` where `artifact_key IS NULL`
  - if no row updates, insert and let the partial unique indexes protect races
- Normalize omitted, `None`, and blank `task_artifact_branch`, `artifact_branch`, and `artifact_key` to SQL `NULL`.
- Never default branch fields to `main`, and never default omitted `artifact_key` to `role_code`.
- Store workflow-run `task_artifact_branch` only in `ops.workflow_runs.context_json`; omitted or null values preserve any existing context value because current function signatures do not distinguish explicit null from omission.
- Accept snake_case inputs only for MCP tool parameters. Return both snake_case and camelCase fields in payloads and capability discovery.
- Add read-only MCP tool `mawf_get_schema_capabilities` with static metadata for supported fields, lookup modes, uniqueness rules, and null-preservation behavior.
- Update or supersede old artifact-key handoff documentation so it no longer presents omitted `artifact_key` defaulting to `role_code` as the current contract.
- Migration downgrade is best-effort, must not fabricate role-derived artifact keys, and must not restore the pre-`022` non-null artifact-key semantic contract.
- `artifact_ref_id` writes must validate the existing row belongs to the supplied `task_id`.
- Artifact-ref insert unique races must retry once by re-reading/updating the matching keyed or legacy identity before surfacing an error.

## Implementation Surfaces

### Migration Surface

Add `migrations/versions/022_mawf_task_artifact_branch_metadata.py` after `021_mawf_external_task_id`.

Expected migration responsibilities:

- Add `planning.tasks.task_artifact_branch TEXT`.
- Add `planning.mawf_artifact_refs.artifact_branch TEXT`.
- Ensure `planning.mawf_artifact_refs.artifact_key` exists but is nullable.
- If an existing deployment has `artifact_key NOT NULL`, drop the `NOT NULL` constraint.
- Drop the current full unique index on `(mawf_task_id, artifact_key)`.
- Drop or avoid the old role unique constraint for all rows.
- Create a partial unique index for keyed rows:
  - `UNIQUE (mawf_task_id, artifact_key) WHERE artifact_key IS NOT NULL`
- Create a partial unique index for legacy rows:
  - `UNIQUE (mawf_task_id, role_id) WHERE artifact_key IS NULL`
- Do not update existing rows from `NULL` to role-derived keys.
- Set existing role-equivalent keys back to `NULL`:
  - `artifact_key = COALESCE(role.mawf_code, role.internal_code)`
  - or `artifact_key = role.internal_code`
- Preserve non-role explicit keys.
- Do not default branch fields to `main`.

Important deployment note: existing databases that already ran migration `018` may contain role-derived `artifact_key` values. The chosen correction policy treats role-equivalent keys as legacy/defaulted values and preserves non-role keys as intentionally explicit.

Before remote rollout, inspect counts for role-equivalent versus non-role keys so operators know what the migration will clear.

Downgrade is best-effort:

- Drop `ux_mawf_artifact_refs_task_artifact_key_keyed`.
- Drop `ux_mawf_artifact_refs_task_role_legacy`.
- Drop `planning.mawf_artifact_refs.artifact_branch`.
- Drop `planning.tasks.task_artifact_branch`.
- Do not recreate fake role-derived `artifact_key` values.
- Do not recreate the pre-`022` non-null artifact-key semantic contract because null legacy keys cannot satisfy that model without data fabrication.

### Task API Surface

Update `src/memory_knowledge/admin/mawf.py`:

- `upsert_task` accepts `task_artifact_branch`.
- `upsert_task` persists it to `planning.tasks.task_artifact_branch`.
- `_task` returns both:
  - `task_artifact_branch`
  - `taskArtifactBranch`
- `get_task` selects `t.task_artifact_branch`.
- `list_tasks` selects `t.task_artifact_branch`.

Update `src/memory_knowledge/server.py`:

- `mawf_upsert_task` accepts `task_artifact_branch`.
- Do not add camelCase input parameters. Current MAWF MCP tools use snake_case inputs; camelCase is returned only in payloads and capability discovery.

### Workflow Run API Surface

Do not add an `ops.workflow_runs` column.

Store task branch metadata in `context_json` beside existing MAWF refs:

- `mawf_workflow_run_id`
- `mawf_attempt`
- `workflow_ledger_ref`
- `workflow_state_ref`
- `task_artifact_branch`

Update `src/memory_knowledge/admin/mawf.py`:

- `upsert_workflow_run` accepts `task_artifact_branch`.
- The context merge should preserve the existing behavior of merging `EXCLUDED.context_json` into existing `context_json`.
- Omitted or null `task_artifact_branch` does not clear an existing context value in this slice.
- `_workflow_run` returns both:
  - `task_artifact_branch`
  - `taskArtifactBranch`
- All MAWF workflow-run response shapers that already read `ops.workflow_runs.context_json` must return both `task_artifact_branch` and `taskArtifactBranch`, including:
  - `mawf_get_workflow_run`
  - `mawf_list_workflow_runs`
  - `mawf_list_workflow_runs_by_user`
  - `mawf_list_recoverable_workflow_runs`

### Artifact Ref API Surface

Update `src/memory_knowledge/admin/mawf.py`:

- `upsert_artifact_ref` accepts `artifact_branch`.
- `upsert_artifact_ref` accepts nullable `artifact_key`.
- Omitted `artifact_key` must remain `NULL`.
- Blank `artifact_key` normalizes to `NULL`, matching legacy semantics.
- Blank `artifact_branch` normalizes to `NULL`.
- `_artifact_ref` returns both:
  - `artifact_branch`
  - `artifactBranch`
  - `artifact_key`
  - `artifactKey`
- `get_artifact_ref` lookup precedence must be:
  - `artifact_ref_id`
  - `task_id + artifact_key`
  - legacy `task_id + role_code`
- Role lookup should be restricted to legacy rows with `artifact_key IS NULL`.
- `list_artifact_refs` returns branch/key fields.
- `get_task_memory_bundle` receives the updated task and artifact ref shapes automatically if it calls `get_task` and `list_artifact_refs`.

Upsert conflict handling must split by keyed versus legacy identity. PostgreSQL cannot safely reuse the old simple `ON CONFLICT (mawf_task_id, artifact_key)` after moving to partial unique indexes. Use an explicit update-then-insert flow inside a transaction:

1. If `artifact_ref_id` is supplied, fetch the existing row before mutating it.
2. If no row exists for the supplied `artifact_ref_id`, raise `ValueError("Artifact ref not found")`.
3. If the existing row's `mawf_task_id` does not match the supplied `task_id`, raise `ValueError`.
4. Only after validation, update that exact row.
5. Otherwise, if normalized `artifact_key` is non-null, update the row matching `(mawf_task_id, artifact_key)`.
6. Otherwise, update the legacy row matching `(mawf_task_id, role_id)` and `artifact_key IS NULL`.
7. If no row updated, insert.
8. If insert hits a unique-violation race, re-read or update the matching keyed or legacy identity once, then surface an error only if the retry also fails.

### Capability Discovery Surface

Add a read-only advertised capability/schema discovery surface that workflow-orch can call without creating synthetic tasks, refs, branches, DB rows, or write-shaped probes.

Required shape:

- New MCP tool `mawf_get_schema_capabilities`.
- Add admin helper `get_schema_capabilities(pool)` in `src/memory_knowledge/admin/mawf.py` that returns the static capability dict.
- Wrap that helper from `src/memory_knowledge/server.py` via `_run_mawf_tool`.
- Mark it as read-only by using `_run_mawf_tool` without `write=True`.
- Return static contract metadata, not database-probed state.

The payload should prove support for all required fields:

- Task payload input/output:
  - `task_artifact_branch`
  - `taskArtifactBranch`
- Workflow-run payload input/output:
  - `task_artifact_branch`
  - `taskArtifactBranch`
- Artifact-ref payload input/output:
  - `artifact_branch`
  - `artifactBranch`
  - `artifact_key`
  - `artifactKey`
- Lookup support:
  - `artifact_ref_id`
  - `task_id + artifact_key`
  - legacy `task_id + role_code`
- Uniqueness semantics:
  - keyed refs unique by `(mawf_task_id, artifact_key)` when key is non-null
  - legacy refs unique by `(mawf_task_id, role_id)` when key is null
- Compatibility semantics:
  - null branch/key values are preserved
  - missing branch does not imply `main`

This discovery endpoint must not depend on remote database write permissions or runtime branch creation support.

Exact capability payload:

```json
{
  "schema_version": "mawf-task-artifact-branch-metadata-v1",
  "capabilities": {
    "task_artifact_branch": true,
    "workflow_run_task_artifact_branch_context": true,
    "artifact_ref_branch": true,
    "artifact_ref_key_nullable": true,
    "artifact_ref_legacy_role_lookup": true
  },
  "payload_fields": {
    "task": ["task_artifact_branch", "taskArtifactBranch"],
    "workflow_run": ["task_artifact_branch", "taskArtifactBranch"],
    "artifact_ref": ["artifact_branch", "artifactBranch", "artifact_key", "artifactKey"]
  },
  "artifact_ref_lookup_precedence": ["artifact_ref_id", "task_id+artifact_key", "task_id+role_code"],
  "artifact_ref_uniqueness": {
    "keyed": ["mawf_task_id", "artifact_key"],
    "keyed_predicate": "artifact_key IS NOT NULL",
    "legacy": ["mawf_task_id", "role_id"],
    "legacy_predicate": "artifact_key IS NULL"
  },
  "compatibility": {
    "null_branch_preserved": true,
    "null_artifact_key_preserved": true,
    "missing_branch_default": null,
    "camel_case_outputs": true,
    "snake_case_inputs_only": true
  }
}
```

## Compatibility Rules

Legacy branchless records remain valid.

Memory-knowledge must preserve and return nulls:

- `task_artifact_branch = NULL`
- `artifact_branch = NULL`
- `artifact_key = NULL`

Reads must not silently rewrite old rows. New writes may include branch/key metadata once workflow-orch is upgraded.

Branch defaults belong to workflow-orch's future compatibility layer, not memory-knowledge. Memory-knowledge should represent unknown branch metadata as `NULL`, not `main`.

## Test Requirements

Migration tests:

- Migration creates `planning.tasks.task_artifact_branch`.
- Migration creates `planning.mawf_artifact_refs.artifact_branch`.
- Migration creates or preserves nullable `planning.mawf_artifact_refs.artifact_key`.
- Migration does not contain fake key backfill from role values.
- Migration does not set `artifact_key NOT NULL`.
- Keyed artifact refs are unique by `(mawf_task_id, artifact_key)` when key is non-null.
- Legacy refs are unique by `(mawf_task_id, role_id)` when key is null.
- Downgrade intent drops new indexes and columns without recreating role-derived keys.

Admin API tests:

- Task upsert/get/list accepts and returns task branch.
- Workflow-run upsert/get/list stores and returns task branch through `context_json`.
- Artifact-ref upsert/get/list accepts and returns branch/key.
- Omitted artifact key remains null.
- Two artifacts with the same role and different artifact keys can coexist for one task.
- Legacy role-only lookup ignores keyed rows and resolves only null-key rows.
- `artifact_ref_id` updates with a mismatched `task_id` raise an error.
- `artifact_ref_id` updates fetch first, validate task ownership, then mutate.
- Unique-race handling retries once by re-reading/updating the matching keyed or legacy identity.
- `get_task_memory_bundle` includes task branch and artifact ref branch/key.

MCP contract/tool tests:

- `mawf_upsert_task` exposes task branch input.
- `mawf_get_task` and `mawf_list_tasks` return snake_case and camelCase branch names.
- `mawf_upsert_workflow_run` exposes task branch input.
- `mawf_get_workflow_run` and `mawf_list_workflow_runs` return snake_case and camelCase branch names.
- `mawf_upsert_artifact_ref` exposes artifact branch and key input.
- `mawf_get_artifact_ref`, `mawf_list_artifact_refs`, and `mawf_get_task_memory_bundle` return snake_case and camelCase branch/key names.
- Capability discovery exposes the exact required payload without writes.
- Documentation regression checks ensure the old artifact-key handoff no longer presents role-code key defaulting as current guidance.

## Risks

- Existing deployed data may already have role-derived `artifact_key` values from migration `018`. The new semantics cannot distinguish fake backfill values from intentionally supplied role-like keys without data evidence.
- Partial unique indexes require careful SQL upsert design.
- If the API keeps defaulting omitted `artifact_key` to `role_code`, workflow-orch will lose the legacy/null signal.
- Returning only snake_case may leave camelCase clients unable to discover or consume the new metadata.
- Adding an `ops.workflow_runs` column would violate the requested storage model; the branch must live in `context_json`.
- A capability endpoint that probes by writing synthetic rows would violate the no-side-effects requirement.

## Recommended Approach

1. Add a corrective migration that makes `artifact_key` nullable, adds branch columns, and installs partial uniqueness.
2. Update admin MAWF payload shaping for task, workflow-run, and artifact-ref metadata.
3. Change artifact-ref upsert logic so omitted keys remain null and conflict identity follows keyed versus legacy partial uniqueness.
4. Add a static read-only MAWF capability discovery tool.
5. Update MCP tool wrappers and contract tests.
6. Add migration and admin tests that explicitly reject the old role-code key backfill behavior.
7. Before remote rollout, inspect deployed `planning.mawf_artifact_refs` rows to decide whether a data correction is required for rows touched by migration `018`.

## Former Open Questions

- CamelCase aliases are returned in payloads and capability discovery, not accepted as MCP inputs.
- Every workflow-run response shaper that already reads `ops.workflow_runs.context_json` must return task branch metadata, including `mawf_get_workflow_run`, `mawf_list_workflow_runs`, `mawf_list_workflow_runs_by_user`, and `mawf_list_recoverable_workflow_runs`.
- Production data state after migration `018` must be inspected before remote rollout. The migration policy is still deterministic: role-equivalent keys become null, non-role keys are preserved.
