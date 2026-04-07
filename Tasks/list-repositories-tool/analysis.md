# Analysis: List Repositories MCP Tool

## Task Objective

Expose a new MCP tool `list_repositories` that returns all registered repositories from the connected PostgreSQL database. Since the server connects to either local or remote PG based on `DATA_MODE`, the tool automatically returns the correct list for the current deployment.

## Current State

### Repository storage
- `catalog.repositories` table already stores all registered repos with columns: `id`, `repository_key`, `name`, `origin_url`, `created_utc`, `updated_utc`
- `catalog.branch_heads` tracks the latest ingested branch per repo
- `catalog.repo_revisions` tracks every ingested commit
- `catalog.entities` tracks all entities (files, symbols, chunks) per repo
- `ops.ingestion_runs` tracks ingestion history

### No new table needed
The data is already in `catalog.repositories`. Both local and remote PG instances have this table populated by prior `register_repository` + `run_repo_ingestion_workflow` calls.

### Existing pattern
All MCP tools in `server.py` follow the same pattern: `@mcp.tool()` + `@track_tool_metrics()` decorator, use `get_pg_pool()`, return `WorkflowResult.model_dump_json()`.

## Recommended Approach

Add a single `list_repositories` MCP tool that:
1. Queries `catalog.repositories` joined with aggregate counts from `catalog.entities` and latest branch from `catalog.branch_heads` / `catalog.repo_revisions`
2. Returns a list of repos with: `repository_key`, `name`, `origin_url`, latest branch, latest commit SHA, entity counts (files, chunks, symbols), last ingestion status
3. No `repository_key` parameter needed — returns ALL repos
4. Read-only — no write guard needed

## Source Artifacts

- `docker/init-pg.sql` — schema definitions
- `src/memory_knowledge/server.py` — existing tool registration pattern
- `src/memory_knowledge/config.py` — data_mode config
