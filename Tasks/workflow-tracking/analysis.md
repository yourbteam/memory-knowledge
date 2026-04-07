# Analysis: Workflow Tracking Persistence

## Task Objective

Add durable persistence for workflow runs, phase states, and artifacts to the ops schema in PostgreSQL. Expose via 5 new MCP tools so the workflow-orch can save/recover workflow state across container restarts.

## Current State

- Workflow artifacts live only on ephemeral filesystem (`/tmp/workflow-workspaces/`)
- Container restart destroys all workflow state and artifacts
- `ops` schema already models run/job/status/checkpoint pattern via `ingestion_runs` + `job_manifests`
- `entity_type` is unconstrained VARCHAR(50) — non-code entity types are established
- Migration chain: 001 → 002 → 003, next is 004

## Design Decisions (from requirements)

- **ops schema** (not new schema or catalog.entities) — natural home, established patterns
- **3 new tables**: `workflow_runs`, `workflow_artifacts`, `workflow_phase_states`
- **5 new MCP tools**: `save_workflow_run`, `save_workflow_artifact`, `get_workflow_run`, `get_workflow_artifact`, `list_workflow_runs`
- Artifacts upserted on `(workflow_run_id, artifact_name)` — updated in place per iteration
- `content_tsv` auto-generated via `GENERATED ALWAYS AS`
- Write-path tools use `check_remote_write_guard`
- Read-path tools have no write guard

## Source Artifacts

- `docker/init-pg.sql` — existing schema
- `migrations/versions/003_add_auto_feedback_flag.py` — migration pattern
- `src/memory_knowledge/server.py` — tool registration pattern
- `src/memory_knowledge/guards.py` — write guard pattern
