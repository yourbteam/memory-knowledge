# Plan: Workflow Tracking Persistence

## Scope

3 new tables + Alembic migration + 5 new MCP tools + update init-pg.sql.

## Implementation Steps

### Step 1: Alembic migration `004_workflow_tracking.py`

Creates `ops.workflow_runs`, `ops.workflow_artifacts`, `ops.workflow_phase_states` with all indexes and constraints per the requirements.

### Step 2: Update `docker/init-pg.sql`

Add the same DDL to init-pg.sql so fresh local databases get the tables.

### Step 3: Add 5 MCP tools to `server.py`

All follow the existing pattern: `@mcp.tool()` + `@track_tool_metrics()` + `WorkflowResult` return.

1. **`save_workflow_run`** — upsert workflow run record. Write-guarded.
2. **`save_workflow_artifact`** — upsert artifact by (run_id, artifact_name). Write-guarded.
3. **`get_workflow_run`** — return run + phases + artifact metadata. Read-only.
4. **`get_workflow_artifact`** — return full artifact content. Read-only.
5. **`list_workflow_runs`** — list runs for a repository with optional status filter. Read-only.

### Step 4: Run migration on remote DB

`alembic upgrade head` against Supabase.

### Step 5: Deploy

Commit, `az acr build`, `az webapp restart`.

## Affected Files

- `migrations/versions/004_workflow_tracking.py` — new
- `docker/init-pg.sql` — add DDL
- `src/memory_knowledge/server.py` — add 5 tools

## Validation

- Local: `docker compose build && docker compose up -d` → call tools via curl
- Remote: deploy and test via MCP
