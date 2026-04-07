# Plan: List Repositories MCP Tool

## Scope

Add one new MCP tool `list_repositories` to `server.py`. Single query, no new tables, no new files.

## Implementation

### Step 1: Add tool to server.py

Add after the `get_memory_stats` tool (~line 470). The tool:
- Takes no required parameters (optional `correlation_id`)
- Queries `catalog.repositories` with LEFT JOINs to get:
  - Latest branch head (branch_name, commit_sha) from `catalog.branch_heads` + `catalog.repo_revisions`
  - Entity counts (files, symbols, chunks) from `catalog.entities`
  - Last ingestion run status from `ops.ingestion_runs`
- Returns `WorkflowResult` with a list of repo objects

### SQL Query

```sql
SELECT
    r.repository_key,
    r.name,
    r.origin_url,
    r.created_utc,
    r.updated_utc,
    bh.branch_name   AS latest_branch,
    rv.commit_sha     AS latest_commit,
    rv.committed_utc  AS latest_commit_utc,
    COALESCE(ec.file_count, 0)    AS file_count,
    COALESCE(ec.symbol_count, 0)  AS symbol_count,
    COALESCE(ec.chunk_count, 0)   AS chunk_count,
    ir.status         AS last_ingestion_status,
    ir.completed_utc  AS last_ingestion_utc
FROM catalog.repositories r
LEFT JOIN LATERAL (
    SELECT bh2.branch_name, bh2.repo_revision_id
    FROM catalog.branch_heads bh2
    WHERE bh2.repository_id = r.id
    ORDER BY bh2.updated_utc DESC LIMIT 1
) bh ON TRUE
LEFT JOIN catalog.repo_revisions rv ON rv.id = bh.repo_revision_id
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE e2.entity_type = 'file')   AS file_count,
        COUNT(*) FILTER (WHERE e2.entity_type = 'symbol') AS symbol_count,
        COUNT(*) FILTER (WHERE e2.entity_type = 'chunk')  AS chunk_count
    FROM catalog.entities e2
    WHERE e2.repository_id = r.id
) ec ON TRUE
LEFT JOIN LATERAL (
    SELECT ir2.status, ir2.completed_utc
    FROM ops.ingestion_runs ir2
    WHERE ir2.repository_id = r.id
    ORDER BY ir2.id DESC LIMIT 1
) ir ON TRUE
ORDER BY r.name
```

### Step 2: Deploy

Commit, `az acr build`, `az webapp restart`.

## Affected Files

- `src/memory_knowledge/server.py` — add ~40 lines for the new tool

## Validation

- `curl` to local `/mcp/` calling `list_repositories` tool
- `claude mcp list` to verify tool appears
- Call via remote server to see remote repos
