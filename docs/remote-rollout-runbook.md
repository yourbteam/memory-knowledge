# Remote Rollout Runbook

This runbook is for the remote rollout of the locally validated planning, workflow-run status, actor-email, and run-recovery changes.

## Scope

Commits included:

- `efb0e4b` `feat: add planning schema groundwork and workflow run lookups`
- `af69928` `fix: preserve workflow run status and API compatibility`
- `90a4b37` `feat: add planning MCP tools`
- `ae349fd` `fix: make tasks project-scoped and feature-optional`
- `367cdca` `fix: anchor tasks to a single repository`
- `714bcea` `fix: enforce planning repository membership invariants`
- `3ba78f1` `feat: add external reference resolution for planning tools`
- `2781d2c` `feat: add planning scope management tools`
- `85c803f` `feat: enrich actor run recovery with planning context`

Database migrations included:

- `005_planning_schema`
- `006_task_project_scope`
- `007_task_single_repository`

## Important Notes

- `ops.workflow_runs.status` still exists intentionally for compatibility.
- Do not remove legacy `ops.workflow_runs.status` in this rollout.
- Planning data is operational state. It is intentionally not part of the repo memory export/import pipeline.
- If migration succeeds but the app deployment has issues, roll back app code first and leave the additive schema in place.

## 1. Pre-Checks

Run from the repo root:

```bash
git log --oneline -9
git status --short
```

Confirm the expected commits are present and there are no accidental extra changes included in the deploy.

Sanity-check the environment file:

```bash
sed -n '1,120p' .env
```

Confirm the remote values are the intended target before running migrations.

## 2. Apply Remote Database Migrations

Run:

```bash
uv run alembic upgrade head
```

Expected migrations:

- `005_planning_schema`
- `006_task_project_scope`
- `007_task_single_repository`

## 3. Verify Remote Database State

### Check Alembic Version

```bash
uv run python - <<'PY'
import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("SELECT version_num FROM alembic_version")
print(cur.fetchone()[0])
conn.close()
PY
```

Expected:

- `007_task_single_repository`

### Check `ops.workflow_runs` Columns

```bash
uv run python - <<'PY'
import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("""
SELECT column_name
FROM information_schema.columns
WHERE table_schema='ops' AND table_name='workflow_runs'
ORDER BY ordinal_position
""")
print([r[0] for r in cur.fetchall()])
conn.close()
PY
```

Expected to include:

- `status`
- `status_id`
- `actor_email`

### Check Planning Tables

```bash
uv run python - <<'PY'
import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("""
SELECT tablename
FROM pg_tables
WHERE schemaname='planning'
ORDER BY tablename
""")
print([r[0] for r in cur.fetchall()])
conn.close()
PY
```

Expected to include:

- `projects`
- `project_repositories`
- `features`
- `feature_repositories`
- `tasks`
- `task_workflow_runs`
- `roadmaps`
- `roadmap_features`
- `project_external_links`
- `feature_external_links`
- `task_external_links`

### Check Seeded Workflow Run Status Values

```bash
uv run python - <<'PY'
import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("""
SELECT rv.internal_code, rv.is_terminal
FROM core.reference_types rt
JOIN core.reference_values rv ON rv.reference_type_id = rt.id
WHERE rt.internal_code='WORKFLOW_RUN_STATUS'
ORDER BY rv.sort_order
""")
for row in cur.fetchall():
    print(row)
conn.close()
PY
```

Expected values:

- `RUN_PENDING`
- `RUN_SUBMITTED`
- `RUN_RUNNING`
- `RUN_SUCCESS`
- `RUN_PARTIAL`
- `RUN_ERROR`
- `RUN_CANCELLED`

## 4. Deploy Server Code

Use the normal remote deploy path after the database verification succeeds.

If the target deployment is Docker-based:

```bash
docker compose build server
docker compose up -d server
```

If the target uses a different deployment mechanism, use that mechanism instead.

## 5. Verify Service Health

Check health endpoints:

```bash
curl -s http://<server-host>:8000/health
curl -s http://<server-host>:8000/ready
```

Replace `<server-host>` with the actual host.

## 6. MCP Smoke Test Order

Run smoke checks in this order.

### Read-Only Checks

1. `list_reference_values("WORKFLOW_RUN_STATUS")`
2. `list_reference_values("PROJECT_STATUS")`
3. `list_workflow_runs_by_actor("<known-email>", false)`

### Low-Risk Write Checks

1. `create_project`
2. `add_repository_to_project`
3. `list_project_repositories`

Use a disposable project name for these checks.

### Planning Flow Checks

1. `create_feature`
2. `create_task`
3. `list_features`
4. `list_tasks`
5. `get_backlog`

### Reconnect Flow Checks

1. `save_workflow_run` with `actor_email`
2. `list_workflow_runs_by_actor`

Confirm the run shows:

- normalized status fields
- `actor_email`
- linked planning context where available:
  - `task_key`
  - `task_title`
  - `feature_key`
  - `feature_title`
  - `project_key`
  - `project_name`

## 7. What to Watch For

Watch application logs for:

- reference lookup failures
- invalid `status_code` errors
- project/repo/feature invariant violations
- unexpected auth failures on MCP writes

## 8. Rollback Guidance

### If Migration Succeeds but App Deployment Fails

- Roll back app code first.
- Leave the database schema in place.

Reason:

- the schema changes are additive/corrective
- legacy `ops.workflow_runs.status` still exists

### If Migration Fails

- Stop immediately.
- Do not deploy new app code.
- Inspect the failing migration before taking further action.

### Do Not Do in This Rollout

- Do not drop legacy `ops.workflow_runs.status`
- Do not add export/import support for planning tables

## 9. Post-Rollout Observation

After the first successful remote rollout:

- leave the system running with both `status` and `status_id`
- observe production behavior
- only plan a later cleanup release to remove legacy `ops.workflow_runs.status` after confidence is high
