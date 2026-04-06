# Analysis: Batch Import Writes

## Problem

`import_repo_memory()` writes 87K+ rows one at a time via individual INSERT queries. Against remote Supabase PG (~100ms/query), this takes ~2.5 hours. Killed after being impractical.

## Root Cause

The function iterates 12 tables sequentially, with each row being an individual `pool.fetchrow(INSERT ... RETURNING id)` call. For tables needing FK remapping (repositories, revisions, entities, files, symbols, chunks), it must capture the returned `id` to build remapping dicts for dependent tables.

## Key Constraint

Several tables need `RETURNING id` to build FK maps for downstream tables:
- repositories → repo_key_to_id
- repo_revisions → rev_key_to_id  
- entities → ek_to_entity_id
- files → ek_to_file_id
- symbols → ek_to_symbol_id
- chunks → ek_to_chunk_id

This means we can't use simple `executemany` (which discards results) for these tables. We need `RETURNING` values.

## Solution: Batch INSERT with UNNEST

asyncpg supports batch inserts using PostgreSQL's `UNNEST` — pass arrays of values and INSERT from them in one query, with `RETURNING` to get all IDs back in order.

```sql
INSERT INTO catalog.entities (entity_key, entity_type, repository_id, repo_revision_id, external_hash)
SELECT * FROM UNNEST($1::uuid[], $2::text[], $3::bigint[], $4::bigint[], $5::text[])
ON CONFLICT (entity_key) DO UPDATE SET repo_revision_id = EXCLUDED.repo_revision_id
RETURNING id
```

One query inserts 1,000 rows and returns 1,000 IDs. Instead of 1,000 round-trips (100s), it's 1 round-trip (100ms).

For tables that DON'T need RETURNING (summaries, branch_heads, retrieval_surfaces, symbol_calls, file_imports):
- Use `executemany` for maximum speed — no results needed.

## Row Counts (taggable-server export)

| Table | Rows | Needs RETURNING | Approach |
|---|---|---|---|
| catalog.repositories | 1 | Yes | Single INSERT (trivial) |
| catalog.repo_revisions | ~10 | Yes | Single batch |
| catalog.entities | ~25,000 | Yes | UNNEST batches of 1,000 |
| catalog.files | ~2,200 | Yes | UNNEST batch |
| catalog.symbols | ~10,000 | Yes | UNNEST batches of 1,000 |
| catalog.chunks | ~18,000 | Yes | UNNEST batches of 1,000 |
| catalog.summaries | ~4,000 | No | executemany |
| catalog.branch_heads | ~5 | No | executemany |
| catalog.retrieval_surfaces | ~5 | No | executemany |
| catalog.file_imports_file | ~100 | No | executemany |
| catalog.symbol_calls_symbol | ~8,000 | No | executemany |
| memory.learned_records | 0 | Yes | Skip if empty |

**Total: ~67K rows. With UNNEST batching: ~67 queries instead of 67,000. At 100ms/query: ~7 seconds instead of ~1.9 hours.**

## Implementation Approach

1. Parse all JSONL lines into `rows_by_table` (unchanged)
2. Process tables in dependency order (unchanged)
3. For FK-needing tables: batch rows into groups of 1,000, use UNNEST INSERT ... RETURNING, build FK maps
4. For non-FK tables: use `executemany` in batches of 1,000
5. Commit after each table
6. Log progress after each batch
