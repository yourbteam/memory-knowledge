# Current Pending Work Closure Analysis

## Objective

Close the current pending work listed in `docs/roadmap.md` and `docs/backlog.md`:

- Neo4j readiness degradation
- `fcsapi-remote-test` catalog placeholder

## Task Type and Size

- task type: operational cleanup / readiness semantics / remote catalog cleanup
- task size: heavy

This is heavy because it affects deployed readiness behavior and remote production catalog state.

## Source Artifacts Inspected

- `docs/roadmap.md`
- `docs/backlog.md`
- `src/memory_knowledge/db/health.py`
- `src/memory_knowledge/db/neo4j.py`
- `src/memory_knowledge/config.py`
- `src/memory_knowledge/server.py`
- `tests/test_health.py`
- remote PostgreSQL catalog rows for `fcsapi-remote-test`

## Current-State Findings

### Neo4j readiness

`src/memory_knowledge/db/health.py` currently marks `/ready` as `not_ready` when Neo4j connectivity fails.

Recent ingestion work intentionally made Neo4j optional for startup and ingestion:

- startup logs `neo4j_startup_degraded`
- ingestion skips Neo4j projection when no driver is available
- PostgreSQL and Qdrant remain the required stores for the useful retrieval/ingestion path

The deployed service currently has:

- `/health`: OK
- `/ready`: not ready because Neo4j DNS cannot resolve `1f9c5ae5.databases.neo4j.io:7687`

Given current runtime behavior, readiness should distinguish required dependencies from optional graph projection. PostgreSQL and Qdrant should continue to gate readiness. Neo4j should report degraded status without returning HTTP 503 for the whole service.

### `fcsapi-remote-test`

Remote catalog inspection showed:

- repository id: `1`
- repository key: `fcsapi-remote-test`
- origin URL: `NULL`
- repo revisions: `0`
- branch heads: `0`
- entities: `0`
- ingestion runs: `0`

Initial direct deletion was blocked by `ops.workflow_runs_repository_id_fkey`.
Follow-up inspection found only disposable remote-smoke state for repository id `1`:

- `remote-analytics-smoke-b7b8101f`, actor `analytics-smoke+b7b8101f@yourbteam.com`
- `ctx-check-workflow-3`, actor `ctx-check@yourbteam.com`
- three `planning.projects` rows named `remote-analytics-smoke-*`
- three matching `planning.features` rows
- three matching `planning.tasks` rows with disposable descriptions
- one `ops.triage_cases` row with `decision_source = 'remote_smoke_test'`

The dependent rows are limited to one `ops.workflow_phase_states` row, one
`ops.workflow_validator_results` row, one `planning.task_workflow_runs` row,
and one `ops.triage_case_feedback` row. There are no workflow artifacts,
findings, finding decisions, roadmaps, external links, ingestion runs,
revisions, branch heads, or entities. This remains safe to remove as disposable
smoke/context telemetry before deleting the placeholder repository row, but the
cleanup scope is broader than the initial direct catalog-row delete.

## Constraints and Unknowns

- The Neo4j DNS issue itself may require external Aura/network credential work. This task can close the readiness gap by making readiness semantics match the intentionally degraded runtime behavior.
- Some graph-specific tools still require Neo4j and may fail or degrade independently. This task does not make graph features available without Neo4j.
- Remote catalog cleanup must avoid deleting any real repository data. The placeholder has zero references in the checked tables.

## Risks and Edge Cases

- If operators expect `/ready` to mean every optional dependency is healthy, changing Neo4j to degraded-ready could hide graph-projection unavailability. Mitigation: include explicit `degraded` details in readiness output.
- If hidden tables reference `catalog.repositories.id`, a direct delete can fail on foreign keys. Mitigation: inspect the FK path, delete only confirmed disposable child telemetry in a transaction, and verify no row remains.
- If `fcsapi-remote-test` is later needed, it should be recreated with a real origin URL and branch.

## Recommended Approach

1. Update readiness semantics:
   - keep PostgreSQL and Qdrant as readiness gates
   - report Neo4j as `ok` when healthy
   - report Neo4j as `degraded: ...` and include `degraded: ["neo4j"]` when unavailable
   - keep top-level status `ready` if only Neo4j is degraded

2. Add/update tests:
   - blank Neo4j errors are still informative
   - Neo4j failure does not make readiness `not_ready`
   - PostgreSQL/Qdrant failures still make readiness `not_ready`

3. Remove disposable `fcsapi-remote-test` planning, workflow, and triage smoke data, then remove the placeholder from remote catalog if no real repository content exists.

4. Update roadmap/backlog after successful verification.

## Rollout Surfaces

- Local code and tests
- Deployed Azure web app image/restart
- Remote PostgreSQL catalog row deletion
- Documentation updates in `docs/roadmap.md` and `docs/backlog.md`

## Remote State Dependencies

- Remote PostgreSQL access via `.env.remote`
- Azure app deploy/restart permissions
- Current remote catalog shape for `fcsapi-remote-test`

## Operator Assumptions

- Neo4j graph projection is optional/degraded for current service readiness.
- A catalog placeholder with no origin URL and no dependent rows can be removed.

## Closeout State

- Neo4j readiness degradation is closed by an explicit degraded-readiness policy:
  PostgreSQL and Qdrant remain readiness gates; Neo4j reports degraded diagnostics
  without failing `/ready`.
- The remote `fcsapi-remote-test` placeholder is removed. Cleanup also removed only
  confirmed disposable remote-smoke planning, workflow, and triage rows.
- The remote deployed catalog now contains five repositories:
  `css-fe`, `fcs-admin`, `fcsapi`, `millennium-wp`, and `taggable-server`.
- Remaining pending work is external workflow producer adoption outside this repo.
