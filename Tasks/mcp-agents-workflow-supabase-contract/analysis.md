# MCP Agents Workflow Supabase Contract Analysis

## Objective

Implement a separate `mawf_*` MCP contract for `mcp-agents-workflow` over the existing Supabase/PostgreSQL relational model. The implementation must avoid duplicate `public.users`, `public.projects`, `public.repositories`, and `public.tasks` tables while providing complete CRUD-style coverage for the requested catalog, user, project, repository, prompt, task, and artifact reference concepts.

## Classification

- Type: migration with API implementation
- Size: heavy
- Grounding: this repository, Supabase/PostgreSQL schema, MCP server tool surface
- Required verification: analysis, plan, and work verification

## Current State Findings

- `core.reference_types` and `core.reference_values` already provide the normalized catalog/reference model.
- `planning.projects` already stores project identity with internal `BIGSERIAL id` and external UUID `project_key`.
- `catalog.repositories` already stores repository identity and is central to ingestion, retrieval, workflow runs, Qdrant projections, and Neo4j projections.
- `planning.tasks` already stores task planning records with project/repository scope.
- `ops.workflow_runs`, `ops.workflow_artifacts`, `ops.workflow_phase_states`, and `ops.workflow_validator_results` already store workflow telemetry and artifacts by workflow run.
- `ops.intake_sessions` and related tables store intake transcripts, draft state, asset refs, and workflow links.
- Missing canonical pieces for the requested MAWF contract are:
  - durable user/actor rows with role and status
  - canonical prompt records keyed by normalized hash
  - task-scoped artifact refs with role and persistence state
  - MAWF-specific external codes over reference values
  - MAWF external IDs/metadata on projects, repositories, and tasks

## Mapping Summary

- Requested catalog tables map to `core.reference_types` and `core.reference_values`, with a new nullable `mawf_code`.
- Requested users map to a new `core.users`.
- Requested projects map to existing `planning.projects`, adding `mawf_project_key`.
- Requested repositories map to existing `catalog.repositories`, adding MAWF id and metadata/status columns.
- Requested prompts map to new immutable `ops.mawf_prompts`.
- Requested tasks map to existing `planning.tasks`, adding owner, prompt, external task id, and ledger ref.
- Requested artifact refs map to new `planning.mawf_artifact_refs`.

## Constraints And Risks

- Reference value FKs must be type-safe. The migration will add trigger enforcement for MAWF-facing reference columns.
- Existing planning and repository MCP tools must remain backward compatible.
- Delete behavior must be soft lifecycle updates only.
- Remote writes must continue to use existing write guards.
- Prompt records should remain immutable. Superseding prompt refs is a controlled correction path.

## Rollout Surfaces

- Local: Alembic migration, Python admin layer, MCP handlers, unit tests.
- Remote: apply migration to Supabase before using `mawf_*` writes.
- Smoke: create user, project, repository, prompt, task, artifact ref, then fetch task memory bundle.
- Containment: migration is additive; existing tools should continue to operate if MAWF tools are unused.

## Recommended Approach

Add one additive migration after `015_intake_sessions`, a focused `memory_knowledge.admin.mawf` service module, and a separate `mawf_*` MCP section in `server.py`. Tests should call the MCP handlers directly and assert both successful CRUD behavior and negative reference-type handling.
