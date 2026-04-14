# init-pg Bootstrap Reconciliation Plan

## Scope

Implement the deprecation path for `docker/init-pg.sql` so Alembic becomes the single supported schema bootstrap path for local Docker startup and future repo documentation.

## Implementation Steps

1. Update `docker-compose.yml`.
   - remove the mount that injects `docker/init-pg.sql` into PostgreSQL init
   - leave PostgreSQL responsible only for creating the empty database container state

2. Update `README.md`.
   - clarify that local Docker startup relies on server-side `alembic upgrade head`
   - clarify that `docker/init-pg.sql` is not part of the supported current bootstrap flow

3. Update `docker/init-pg.sql`.
   - keep the file for historical reference
   - mark it explicitly deprecated
   - make clear it is no longer used by the supported Docker bootstrap path

4. Update any additional bootstrap-facing references if needed.
   - only if required to keep docs consistent with the new path

5. Validate the deprecation path.
   - confirm the compose file no longer mounts the init script
   - confirm docs consistently point to Alembic as the supported path
   - validate that `alembic upgrade head` is sufficient for a local empty database bootstrap

## Affected Files

- `docker-compose.yml`
- `README.md`
- `docker/init-pg.sql`
- `migrations/env.py`
- `Tasks/init-pg-bootstrap-reconciliation/analysis.md`
- `Tasks/init-pg-bootstrap-reconciliation/plan.md`

## Validation Approach

- inspect the updated compose file
- inspect the updated docs
- verify migration ownership assumptions against the existing Alembic chain
- if feasible, run a local empty-database migration bootstrap test

## Completion Criteria

The task is complete when:

- the active Docker bootstrap no longer depends on `docker/init-pg.sql`
- the supported schema bootstrap path is clearly documented as `alembic upgrade head`
- the legacy SQL snapshot is explicitly deprecated
- the repo’s bootstrap story is no longer ambiguous

## Execution Result

Implemented:

- removed the active `docker/init-pg.sql` mount from `docker-compose.yml`
- updated `README.md` so the supported bootstrap path is explicitly `alembic upgrade head`
- updated `docker/init-pg.sql` header to mark it deprecated and no longer part of the supported Docker bootstrap flow
- fixed `migrations/env.py` so the Alembic version table supports the repository’s longer descriptive revision IDs and the online migration path commits cleanly for empty-database bootstrap

Validation performed:

- read back the updated compose and documentation surfaces
- verified local PostgreSQL connectivity
- created fresh scratch local databases
- ran `uv run alembic upgrade head` against an empty scratch database
- verified the resulting database reached `014_triage_policy_governance`
- verified presence of modern schema tables including:
  - `core.reference_values`
  - `planning.tasks`
  - `ops.workflow_validator_results`
  - `ops.workflow_findings`
  - `ops.triage_cases`
  - `ops.triage_policy_artifacts`

Notable execution correction:

- the first empty-database validation surfaced a real blocker in the supported path:
  - Alembic’s default `alembic_version.version_num` width was too small for this repo’s long revision identifiers
- this was fixed inside `migrations/env.py` as part of the task

Closeout state:

- implemented: yes
- locally verified: yes
- remotely verified: not applicable
- deployed: not applicable
- pushed: no
- follow-ups remaining:
  - optionally remove `docker/init-pg.sql` entirely in a later cleanup task if the team no longer wants to retain the deprecated historical snapshot
