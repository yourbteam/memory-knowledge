# Current Pending Work Closure Plan

## Scope

Close the two current pending items tracked in roadmap/backlog:

- Neo4j readiness degradation
- `fcsapi-remote-test` catalog placeholder

## Implementation

1. Change readiness behavior in `src/memory_knowledge/db/health.py`.
   - PostgreSQL failure sets top-level status to `not_ready`.
   - Qdrant failure sets top-level status to `not_ready`.
   - Neo4j failure sets `neo4j` to a degraded diagnostic and appends `neo4j` to `degraded`, but does not set top-level status to `not_ready`.

2. Update tests in `tests/test_health.py`.
   - Adjust existing Neo4j blank-message test to expect degraded-ready status.
   - Add/keep coverage proving required dependency failures still make the service not ready.

3. Remove `fcsapi-remote-test` from remote PostgreSQL.
   - Re-check reference counts.
   - Delete only confirmed disposable smoke/context rows for repository id `1`:
     `ops.workflow_phase_states`, `ops.workflow_validator_results`,
     `planning.task_workflow_runs`, `ops.triage_case_feedback`,
     `ops.triage_cases`, `ops.workflow_runs`, `planning.tasks`,
     `planning.feature_repositories`, `planning.features`,
     `planning.project_repositories`, and `planning.projects`.
   - Delete `catalog.repositories` row for `repository_key = 'fcsapi-remote-test'`
     only after confirming it has no real repository content.
   - Verify the row is absent.

4. Update `docs/roadmap.md` and `docs/backlog.md`.
   - Move Neo4j readiness degradation to resolved/completed as degraded-readiness semantics.
   - Move `fcsapi-remote-test` placeholder to resolved as removed.
   - Leave external workflow producer adoption as external.

## Local Rollout

Run focused tests:

```sh
uv run pytest tests/test_health.py -q
```

Run compile check for touched modules:

```sh
uv run python -m compileall src/memory_knowledge/db src/memory_knowledge/server.py
```

## Remote Rollout

1. Build and push updated image to ACR.
2. Restart Azure web app `memory-knowledge`.
3. Verify:
   - `/health` returns OK
   - `/ready` returns HTTP 200 with PostgreSQL/Qdrant OK and Neo4j degraded if DNS remains unavailable
   - remote catalog no longer lists `fcsapi-remote-test`

## Rollback / Containment

- If readiness behavior is wrong, revert `src/memory_knowledge/db/health.py` and redeploy.
- If catalog deletion fails due hidden references, stop and inspect the foreign-key error; do not force delete.
- If new references are not clearly disposable smoke/context telemetry, leave the repository row in place and document the blocker.
- If the placeholder is needed later, recreate it with a real `origin_url` and branch metadata.

## Validation Approach

- local focused tests
- local compile check
- remote health/readiness smoke checks
- remote catalog query after placeholder deletion

## Closeout Checklist

- implemented: yes
- locally verified: yes
  - `uv run pytest tests/test_health.py -q`
  - `uv run python -m compileall src/memory_knowledge/db src/memory_knowledge/server.py`
- remotely verified: yes
  - remote catalog no longer contains `fcsapi-remote-test`
  - remote catalog contains `css-fe`, `fcs-admin`, `fcsapi`, `millennium-wp`, and `taggable-server`
  - `/health` returns `{"status":"ok"}`
  - `/ready` returns HTTP 200 with `status: ready`, PostgreSQL/Qdrant OK, and `degraded: ["neo4j"]`
- deployed: yes
  - image digest `sha256:8f948d0468b62bc278d6ccd3c9d2edf3a91c2daf2279da2b7b1993d49e32c7e5`
- pushed: no
- follow-ups remaining: external workflow producer adoption outside this repo
