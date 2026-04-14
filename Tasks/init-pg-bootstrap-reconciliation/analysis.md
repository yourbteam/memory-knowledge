# init-pg Bootstrap Reconciliation Analysis

## Objective

Resolve the remaining bootstrap ambiguity around `docker/init-pg.sql` by deciding whether the repository should:

- fully reconcile the legacy SQL snapshot to the modern schema line
- or formally deprecate it and rely on Alembic as the single supported bootstrap path

## Task Type and Size

- task type: `migration` / `workflow-process`
- task size: `heavy`

This is `heavy` because it affects local bootstrap behavior, developer expectations, Docker startup, migration ownership, and future rollout assumptions.

## Source Artifacts Inspected

- `docker/init-pg.sql`
- `docker-compose.yml`
- `docker-compose.override.yml.local`
- `docker/entrypoint.sh`
- `README.md`
- `migrations/env.py`
- `migrations/versions/001_initial_schema.py`
- `migrations/versions/004_workflow_tracking.py`
- `migrations/versions/005_planning_schema.py`
- `migrations/versions/008_analytics_schema.py`
- `docs/remote-rollout-runbook.md`
- `Tasks/analytics-tools/plan.md`
- `docs/roadmap.md`
- `docs/backlog.md`

## Current-State Findings

### Docker local startup currently uses a split bootstrap path

`docker-compose.yml` mounts:

- `./docker/init-pg.sql:/docker-entrypoint-initdb.d/init.sql`

for the local `postgres` service.

At the same time, the `server` container entrypoint runs:

```sh
alembic upgrade head
```

on startup.

So the local Docker path already has two bootstrap layers:

1. PostgreSQL init-script snapshot
2. Alembic upgrade to head

### `init-pg.sql` is explicitly legacy

The header of `docker/init-pg.sql` already says:

- it is a legacy bootstrap snapshot
- it is not a complete analytics-ready schema bootstrap
- the supported fresh-install path is `alembic upgrade head`

So the file itself already declares that it is not authoritative.

### Alembic already owns the real schema line

The migration chain now runs through:

- `001_initial_schema.py`
- `...`
- `014_triage_policy_governance.py`

Important findings:

- migration `001` recreates the original schema and seed content from the early snapshot
- migration `005` introduces `core` and `planning`
- migration `008` introduces analytics schema elements and validator reference values
- migrations `009` through `014` continue the findings and triage schema line

That means the modern schema is already Alembic-owned in practice.

### Full reconciliation would create duplicate ownership debt

To keep `docker/init-pg.sql` fully current, it would need to track:

- all later schemas and tables
- all normalized reference types and values
- all post-004 workflow changes
- all triage and governance changes
- future migrations as they continue

This would create a second schema authority that must stay synchronized with the migration chain.

### The repository already documents Alembic as the supported path

`docs/remote-rollout-runbook.md` already says:

- supported bootstrap path is `alembic upgrade head`
- `docker/init-pg.sql` should be treated as legacy seed snapshot only

`Tasks/analytics-tools/plan.md` also documents that raw init-script bootstrap is unsupported for the analytics-ready path and that the snapshot is materially incomplete.

## Decision

The correct implementation direction is:

### Formally deprecate `docker/init-pg.sql` from the live bootstrap path

Do not attempt full schema reconciliation of the snapshot.

Instead:

- remove it from the active Docker local bootstrap path
- keep Alembic as the single supported schema initialization path
- update local startup documentation so this is explicit
- keep the legacy file only as historical reference or deprecation artifact unless a later cleanup removes it completely

## Why This Direction Is Better

### 1. One source of truth

Alembic already owns the actual schema line. Making it the only supported bootstrap path removes ambiguity.

### 2. Lower maintenance cost

A full reconciliation would require keeping a large raw SQL snapshot synchronized with every future migration. That is unnecessary and brittle.

### 3. Safer operational model

An empty local Postgres database plus `alembic upgrade head` is easier to reason about than a legacy snapshot followed by many idempotent migrations.

### 4. Matches current docs and rollout behavior

The documentation and remote rollout path already treat Alembic as authoritative.

## Expected Implementation Shape

Likely changes:

- remove `docker/init-pg.sql` mount from `docker-compose.yml`
- update `README.md` to describe the supported local startup path clearly
- update `docker/init-pg.sql` header to mark it deprecated and no longer part of the supported bootstrap flow
- possibly update other bootstrap-facing docs if needed

## Risks and Edge Cases

### Risk: local developers may assume Postgres starts fully pre-seeded

Mitigation:

- document clearly that Postgres only provides an empty database
- server startup applies the schema through Alembic

### Risk: route-policy seed data depended on init script

Mitigation:

- migration `001` already seeds route policies
- server startup runs Alembic before serving

### Risk: some custom local workflows may have relied on raw Postgres init without server startup

Mitigation:

- mark that workflow unsupported
- direct users to `alembic upgrade head` for schema initialization

## Verification Constraints

This task qualifies as `heavy`, so `verify-analysis`, `verify-plan`, and `verify-work` would normally be required by the upgraded workflow.

However, the verifier skills require delegated subagent review. In the current turn, I do not have explicit delegation permission from the user, so I am proceeding with the documented workflow artifacts and noting that the delegated hardening stages could not be run in their intended form.
