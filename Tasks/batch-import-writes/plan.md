# Plan: Batch Import Writes

## Scope

Rewrite `import_repo_memory()` in `src/memory_knowledge/admin/export_import.py` to use batched writes. One file change. Target: 87K rows imported in minutes, not hours.

## Approach

Replace individual `pool.fetchrow(INSERT)` loops with:
- **UNNEST batch INSERTs** for tables needing `RETURNING id` (entities, files, symbols, chunks)
- **`executemany`** for tables not needing RETURNING (summaries, branch_heads, etc.)
- **Batch size: 1,000 rows** per query
- **Progress logging** after each batch
- **Per-table commits** so partial progress survives failures

## Changes

### Single file: `src/memory_knowledge/admin/export_import.py`

Add a batch helper function:

```python
async def _batch_upsert_returning(
    pool, sql, columns, rows, batch_size=1000
):
    """Batch INSERT ... RETURNING using UNNEST arrays."""
    results = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        arrays = [list(col_values) for col_values in zip(*batch)]
        batch_results = await pool.fetch(sql, *arrays)
        results.extend(batch_results)
        logger.info("import_batch_progress", rows=len(results), total=len(rows))
    return results
```

Rewrite each table's import section to collect rows first, then batch-insert.

### Example: Entities (largest table, ~25K rows)

**Before (25,000 individual queries):**
```python
for row in rows_by_table.get("catalog.entities", []):
    r = await pool.fetchrow("INSERT INTO catalog.entities (...) VALUES ($1,$2,$3,$4,$5) ON CONFLICT ... RETURNING id", ...)
    ek_to_entity_id[row["entity_key"]] = r["id"]
```

**After (25 batched queries):**
```python
entity_rows = []
entity_keys = []
for row in rows_by_table.get("catalog.entities", []):
    rk = row.get("_repository_key", "")
    repo_id = repo_key_to_id.get(rk)
    if not repo_id:
        continue
    commit_sha = row.get("_revision_commit_sha")
    rev_id = rev_key_to_id.get((rk, commit_sha)) if commit_sha else None
    entity_rows.append((uuid.UUID(row["entity_key"]), row["entity_type"], repo_id, rev_id, row.get("external_hash")))
    entity_keys.append(row["entity_key"])

# Batch insert
for i in range(0, len(entity_rows), 1000):
    batch = entity_rows[i:i+1000]
    batch_keys = entity_keys[i:i+1000]
    keys, types, rids, rvids, hashes = zip(*batch)
    results = await pool.fetch(
        """INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id, external_hash)
           SELECT * FROM UNNEST($1::uuid[], $2::text[], $3::bigint[], $4::bigint[], $5::text[])
           ON CONFLICT (entity_key) DO UPDATE SET repo_revision_id = EXCLUDED.repo_revision_id, external_hash = EXCLUDED.external_hash
           RETURNING id, entity_key""",
        list(keys), list(types), list(rids), list(rvids), list(hashes),
    )
    for r in results:
        ek_to_entity_id[str(r["entity_key"])] = r["id"]
    logger.info("import_progress", table="catalog.entities", done=min(i+1000, len(entity_rows)), total=len(entity_rows))
```

### For non-RETURNING tables (summaries, symbol_calls, etc.):

```python
summary_rows = rows_by_table.get("catalog.summaries", [])
if summary_rows:
    args = [(ek_to_entity_id.get(r["_entity_key"]), r["summary_level"], r["summary_text"]) for r in summary_rows if ek_to_entity_id.get(r["_entity_key"])]
    for i in range(0, len(args), 1000):
        batch = args[i:i+1000]
        await pool.executemany(
            "INSERT INTO catalog.summaries (entity_id, summary_level, summary_text) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            batch,
        )
        logger.info("import_progress", table="catalog.summaries", done=min(i+1000, len(args)), total=len(args))
```

## Verification

1. Run full test suite
2. Export taggable-server locally
3. Import to remote Supabase
4. Verify row counts match
5. Run repair to project Qdrant + Neo4j
6. Test retrieval
