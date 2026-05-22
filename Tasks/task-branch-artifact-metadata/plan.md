## Summary

Implement memory-knowledge support for task-scoped artifact branch metadata in a follow-up code slice. The implementation must preserve legacy nulls, expose branch/key metadata through MAWF APIs, add read-only schema capability discovery, and avoid any workflow-orch runtime behavior or Git branch creation.

## Scope Boundaries

- In scope: memory-knowledge schema, MAWF admin helpers, MCP tool wrappers, tests, and handoff documentation.
- Out of scope: workflow-orch runtime changes, artifact worktrees, Git branch creation, artifact content persistence, and adding an `ops.workflow_runs` column.
- Branch defaults remain external to memory-knowledge. Missing branch metadata is represented as `NULL`, not `main`.

## Implementation Steps

1. Add migration `migrations/versions/022_mawf_task_artifact_branch_metadata.py`.
   - Revision follows `021_mawf_external_task_id`.
   - Add `planning.tasks.task_artifact_branch TEXT`.
   - Add `planning.mawf_artifact_refs.artifact_branch TEXT`.
   - Add `planning.mawf_artifact_refs.artifact_key TEXT` if missing and drop any `NOT NULL` constraint.
   - Convert role-equivalent existing keys to `NULL` when `artifact_key` equals resolved role `mawf_code` or `internal_code`; preserve all non-role keys.
   - Drop `ux_mawf_artifact_refs_task_artifact_key` and `uq_mawf_artifact_refs_task_role` if present.
   - Create `ux_mawf_artifact_refs_task_artifact_key_keyed` on `(mawf_task_id, artifact_key)` where `artifact_key IS NOT NULL`.
   - Create `ux_mawf_artifact_refs_task_role_legacy` on `(mawf_task_id, role_id)` where `artifact_key IS NULL`.
   - Implement best-effort downgrade by dropping both new partial indexes, dropping `artifact_branch` and `task_artifact_branch`, and not recreating role-derived keys. Do not restore the pre-`022` non-null artifact-key semantic contract because doing so would require fabricating data.

2. Update MAWF admin behavior in `src/memory_knowledge/admin/mawf.py`.
   - Normalize omitted, `None`, and blank `task_artifact_branch`, `artifact_branch`, and `artifact_key` to `None`.
   - Extend task upsert/get/list to persist and return `task_artifact_branch` and `taskArtifactBranch`.
   - Extend workflow-run upsert/get/list to store `task_artifact_branch` in `context_json` and return `task_artifact_branch` and `taskArtifactBranch`; omitted or null input preserves an existing context value.
   - Include `task_artifact_branch` and `taskArtifactBranch` on every MAWF workflow-run response shaper that already reads `ops.workflow_runs.context_json`, including `mawf_get_workflow_run`, `mawf_list_workflow_runs`, `mawf_list_workflow_runs_by_user`, and `mawf_list_recoverable_workflow_runs`.
   - Extend artifact-ref upsert/get/list to persist and return `artifact_branch`, `artifactBranch`, `artifact_key`, and `artifactKey`.
   - Replace artifact-ref default-key behavior: omitted `artifact_key` remains null and never falls back to `role_code`.
   - Implement artifact-ref write identity as update-then-insert in a transaction:
     - when `artifact_ref_id` is supplied, fetch the existing row first
     - raise `ValueError("Artifact ref not found")` if the supplied `artifact_ref_id` does not exist
     - validate the existing row belongs to the supplied `task_id` before mutating it
     - update by `artifact_ref_id` only after validation
     - otherwise update by keyed `(mawf_task_id, artifact_key)` when key is non-null
     - otherwise update by legacy `(mawf_task_id, role_id)` with `artifact_key IS NULL`
     - insert if no row updated
     - on insert unique-violation races, re-read or update the matching keyed or legacy identity once before surfacing an error
   - Restrict legacy role lookup to rows where `artifact_key IS NULL`; keyed rows are read by `artifact_ref_id` or `task_id + artifact_key`.

3. Update MCP surfaces in `src/memory_knowledge/server.py`.
   - Add snake_case input parameters only: `task_artifact_branch` for task/workflow-run upserts and `artifact_branch` for artifact-ref upserts.
   - Do not add camelCase input parameters.
   - Return both snake_case and camelCase through admin payload shapers.
   - Add admin helper `get_schema_capabilities(pool)` in `src/memory_knowledge/admin/mawf.py` returning the static capability dict.
   - Add read-only MCP wrapper `mawf_get_schema_capabilities` in `src/memory_knowledge/server.py` using `_run_mawf_tool` without `write=True`.
   - Capability payload must statically return this exact shape:

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

4. Update documentation.
   - Update `docs/MCP_AGENTS_WORKFLOW_ARTIFACT_REF_KEYS_HANDOFF.md` so omitted `artifact_key` no longer defaults to `role_code`.
   - Add a note that the task-branch metadata contract supersedes the old singleton-default key behavior.
   - Include remote rollout preflight SQL to count role-equivalent and non-role artifact keys before applying migration `022`.
   - Remove stale current-contract statements that describe a single `unique(task_id, artifact_key)` rule or ambiguity-based role lookup for keyed rows.

## Test Plan

- Migration tests in `tests/test_mawf_contract_migration.py`:
  - assert migration `022` exists and follows `021`
  - assert task/artifact branch columns are created
  - assert `artifact_key` is nullable and no role-code backfill or `SET NOT NULL` remains
  - assert both partial unique index predicates exist
  - assert role-equivalent key correction preserves non-role keys
  - assert downgrade intent drops new indexes/columns, does not recreate role-derived keys, and does not restore non-null key semantics

- Admin tests in `tests/test_mawf_admin.py`:
  - task upsert/get/list accepts and returns both task branch names
  - workflow-run upsert/get/list stores and returns task branch through `context_json`
  - workflow-run user/recoverable index shapers return both task branch naming styles when `context_json` contains the branch
  - artifact-ref upsert/get/list accepts and returns branch/key fields in both naming styles
  - omitted and blank artifact keys return `None`
  - same-role refs with different non-null keys coexist
  - legacy role-only lookup ignores keyed rows and resolves only null-key rows
  - `artifact_ref_id` update order is fetch, not-found error if missing, task-ownership validation, then update
  - `artifact_ref_id` with mismatched `task_id` raises an error before mutation
  - unique-race behavior retries once by re-reading/updating the matching keyed or legacy identity
  - task memory bundle includes task branch and artifact ref branch/key fields

- MCP contract tests in `tests/test_mawf_contract_tools.py`:
  - wrappers pass snake_case branch/key inputs through to admin helpers
  - payloads expose snake_case and camelCase fields
  - `mawf_get_schema_capabilities` is read-only and is not blocked by the write guard
  - `mawf_get_schema_capabilities` is tested by monkeypatching the new admin helper
  - capability payload matches the exact required keys and values
  - update old expectations so omitted `artifact_key` is `None`, not `role_code`
  - documentation regression checks ensure the old handoff no longer presents role-code key defaulting as current guidance

## Rollout Notes

- Before remote migration, inspect deployed artifact refs:

```sql
SELECT
  COUNT(*) FILTER (
    WHERE ar.artifact_key = COALESCE(role.mawf_code, role.internal_code)
       OR ar.artifact_key = role.internal_code
  ) AS role_equivalent_keys,
  COUNT(*) FILTER (
    WHERE ar.artifact_key IS NOT NULL
      AND ar.artifact_key IS DISTINCT FROM COALESCE(role.mawf_code, role.internal_code)
      AND ar.artifact_key IS DISTINCT FROM role.internal_code
  ) AS explicit_non_role_keys,
  COUNT(*) FILTER (WHERE ar.artifact_key IS NULL) AS already_null_keys
FROM planning.mawf_artifact_refs ar
JOIN core.reference_values role ON role.id = ar.role_id;
```

- Apply migration `022`.
- Smoke test `mawf_get_schema_capabilities` without creating rows.
- Smoke test a legacy artifact ref with omitted `artifact_key` and confirm returned key is null.
- Smoke test a keyed artifact ref and confirm lookup by `task_id + artifact_key`.

## Assumptions

- Snake_case remains the only MCP input style.
- CamelCase exists only in returned payloads and capability discovery.
- Role-equivalent existing keys are legacy/defaulted values and should be nulled.
- Non-role existing keys are intentionally explicit and should be preserved.
- Clearing an existing workflow-run `task_artifact_branch` is not part of this slice because current function signatures do not distinguish explicit null from omission.
