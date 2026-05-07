# MCP Agents Workflow Supabase Contract Plan

## Scope

Implement the MAWF contract as additive schema and MCP tooling. Reuse canonical `core`, `catalog`, `planning`, and `ops` tables where they already exist. Add only missing fields and new canonical tables for users, prompts, and task artifact refs.

## Implementation Steps

1. Add Alembic migration `016_mawf_contract.py`.
   - Add `core.reference_values.mawf_code` and unique `(reference_type_id, mawf_code)` index.
   - Seed MAWF catalog types and values.
   - Add `core.users`.
   - Extend `planning.projects`, `catalog.repositories`, and `planning.tasks`.
   - Add `ops.mawf_prompts`.
   - Add `planning.mawf_artifact_refs`.
   - Add a reusable trigger function and table triggers to enforce reference type correctness.

2. Add `src/memory_knowledge/admin/mawf.py`.
   - Implement CRUD-style service functions for catalog values, users, projects, repositories, prompts, tasks, artifact refs, and task memory bundle.
   - Resolve MAWF external codes to `core.reference_values`.
   - Translate canonical DB rows into requested MAWF response shapes.
   - Use soft status transitions for deactivate/archive/cancel/complete/fail.

3. Add a separate `MCP Agents Workflow Contract` section in `src/memory_knowledge/server.py`.
   - Add all requested `mawf_*` tools.
   - Route writes through `check_remote_write_guard`.
   - Return `WorkflowResult` JSON consistently.

4. Add tests.
   - `tests/test_mawf_contract_tools.py`: calls `server.mawf_*` handlers directly and covers CRUD through MCP code.
   - `tests/test_mawf_contract_migration.py`: verifies the migration includes required tables, columns, indexes, seeds, and triggers.
   - Run focused tests plus existing planning/workflow tests.

## Validation

- `uv run pytest tests/test_mawf_contract_tools.py tests/test_mawf_contract_migration.py tests/test_planning_tools.py tests/test_workflow_runs.py`
- If migration syntax risk appears, also run `python -m py_compile` or equivalent compile checks for changed Python files.

## Rollout

- Local: apply migration with `alembic upgrade head`, then run the MAWF smoke sequence through MCP.
- Remote: apply migration to Supabase before enabling `mcp-agents-workflow` to call `mawf_*` writes.
- Smoke sequence: upsert user, project, repository, create prompt, upsert task, upsert artifact refs, update task status, fetch task memory bundle.

## Rollback And Containment

- Changes are additive. Existing tools remain compatible.
- If MAWF issues appear, disable external `mawf_*` caller usage while leaving existing memory-knowledge behavior unaffected.
- Downgrade drops added MAWF tables/columns/triggers only.

## Closeout Checklist

- Implemented: migration `016_mawf_contract`, `memory_knowledge.admin.mawf`, `mawf_*` MCP handlers, and MAWF contract tests.
- Hardened: catalog deactivation now preserves catalog type identity, and MAWF task upsert now ensures the project/repository membership link exists before task persistence.
- Locally verified: focused MAWF/planning/workflow tests passed; changed Python files compile.
- Full suite note: unrelated config/guard tests fail in the current worktree because remote environment values are loaded.
- Remotely verified: not run.
- Deployed: not run.
- Follow-ups: apply Alembic migration and run MAWF smoke sequence against the intended Supabase environment.
