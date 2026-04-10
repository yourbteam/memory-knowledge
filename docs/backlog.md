# Backlog

## Critical — Fix Before Next Ingestion

### 11. Same-commit retry treated as incremental with empty diff — skips all file processing
**Problem:** When an ingestion fails mid-run but updates `branch_heads`, retrying the same `commit_sha` causes the workflow to compute a git diff between the commit and itself. The diff is empty, so `py_files` is empty, so zero files are processed and zero summaries are generated. The run reports `summaries_created: 0` and completes "successfully" while leaving summaries incomplete.

**Root cause:** `ingestion.py` lines 134-146 — if `old_sha` (from `branch_heads`) is not None, it always does an incremental diff. It does not check whether `old_sha == commit_sha`, which would produce an empty diff by definition.

**Impact:** FCSAPI had 3,393 summaries generated in a failed first run. The retry run created 0 summaries because it saw the same commit and diffed it against itself. 243 new files from the latest commit have no summaries.

**Fix:** If `old_sha == commit_sha`, force a full run:
```python
if old_sha is not None and old_sha != commit_sha:
    diff_files = await asyncio.to_thread(changed_files, repo, old_sha, commit_sha, extensions)
else:
    diff_files = None
```

**Files:** `src/memory_knowledge/workflows/ingestion.py` lines 134-146

**Discovered:** 2026-04-09 — FCSAPI retry run completed with `summaries_created: 0` despite ~2,200 missing summaries.

---

### 12. Existing summaries query not scoped to current revision
**Problem:** The query at `ingestion.py` lines 473-479 that builds `existing_summary_keys` fetches ALL summaries for a repository across all revisions, not filtered by the current `commit_sha` or `repo_revision_id`. This loads unnecessary data into memory and could cause incorrect skip decisions if entity keys collide across revisions.

**Impact:** Latent — doesn't cause incorrect behavior in most cases since per-item checks still work, but wastes memory on large repos with multiple revisions and could mask missing summaries if entity keys are reused.

**Fix:** Add `commit_sha` or `repo_revision_id` filter to the existing summaries query:
```sql
SELECT e.entity_key FROM catalog.summaries s
JOIN catalog.entities e ON s.entity_id = e.id
WHERE e.repository_id = $1 AND e.repo_revision_id = $2
```

**Files:** `src/memory_knowledge/workflows/ingestion.py` lines 473-479

**Discovered:** 2026-04-09 — found during investigation of backlog item #11.

---

## High Priority

### 1. Orphaned background jobs after server restart
**Problem:** When the server restarts (docker restart, deploy, crash), in-flight background ingestion/repair/audit jobs die silently. Their `ops.job_manifests` record stays `state_code='running'` permanently. The job dispatcher only polls for `pending` jobs — it never re-picks orphaned `running` ones.

**Impact:** The next ingestion submission for the same repo works, but the orphaned record pollutes the job history and can cause confusion when checking job status.

**Fix:** On startup, the dispatcher should scan for `running` jobs that have no active process behind them (e.g., `started_utc` older than a configurable timeout like 1 hour) and either:
- Reset them to `pending` for automatic retry
- Mark them as `failed` with `error_text = "orphaned by server restart"`

**Files:** `src/memory_knowledge/jobs/dispatcher.py`

**Discovered:** 2026-04-03 — CSS-FE ingestion orphaned twice by server restarts during remote database testing.

---

### 2. Ingestion performance on remote PostgreSQL
**Problem:** Ingesting large repos (2,580 files for CSS-FE) against remote Supabase PG is extremely slow — ~10 files/minute vs hundreds/minute locally. Each file involves multiple sequential INSERT round-trips over transatlantic latency (~100ms per query).

**Impact:** A 2,580-file repo takes ~4-5 hours just for the parse phase. With summaries, total ingestion could take 12+ hours.

**Fix options:**
- Batch INSERTs using `executemany` or `COPY` instead of individual INSERT per entity/file/chunk/symbol
- Use asyncpg's pipeline mode for write batching
- Buffer chunks in memory and flush in batches of 50-100

**Files:** `src/memory_knowledge/workflows/ingestion.py`

---

### 10. Ingestion workflow lacks checkpoint/resume — re-runs repeat completed phases
**Problem:** When ingestion fails mid-execution (e.g., during summarization), re-running restarts the entire pipeline from step 1. File scanning, chunk registration, edge resolution, and embedding all re-execute even though their data is already persisted. Only the summarization step has skip logic for existing records. The `job_manifests.checkpoint_data` JSONB column exists for exactly this purpose but is only written at completion/error — never during execution as a progress checkpoint.

**Impact:** FCSAPI ingestion failed at ~61% through summarization after 2 hours. The re-run spent ~30 minutes re-scanning all 486 files and 5,600 chunks before reaching the summary phase again.

**Fix:** After each major phase completes, write a checkpoint to `job_manifests.checkpoint_data` with the completed phase name and any state needed to resume. On startup, read the checkpoint and skip to the next incomplete phase. Phases to checkpoint: clone, file scan, chunk registration, edge resolution, summarization (with batch offset), chunk embedding, summary embedding, neo4j projection.

**Files:** `src/memory_knowledge/workflows/ingestion.py`, `src/memory_knowledge/jobs/dispatcher.py`

**Discovered:** 2026-04-09 — FCSAPI ingestion failed twice mid-summarization; each re-run wasted ~30 min on already-completed phases.

---

## Medium Priority

### 13. Settings/guard tests are polluted by ambient env and `.env` defaults
**Problem:** The config and guard test suites are not hermetic against the office shell / `.env` baseline. During local analytics verification after applying `008_analytics_schema`, the broad suite failed in `tests/test_config.py` and `tests/test_guards.py` because ambient values leaked into `Settings()`. Observed symptoms included:
- `qdrant_api_key` resolving to a non-`None` value when tests expected `None`
- `data_mode` / per-DB effective mode resolving unexpectedly
- `check_remote_write_guard()` not tripping when tests set `DATA_MODE=remote`

**Impact:** Full-suite local verification can report unrelated failures even when the analytics upgrade itself is working. This makes rollout readiness harder to assess and weakens confidence in config/guard coverage.

**Likely root cause:** `Settings()` is still reading values from the ambient environment and/or `.env` file in a way that the tests’ helper `_set_base_env()` does not fully neutralize. The tests assume a clean local baseline, but the real office environment is remote-oriented.

**Fix options:**
- make the config/guard tests explicitly clear or override all mode/auth/secret env vars they depend on
- or provide a test-only settings construction path that does not read ambient `.env`
- or make empty-string secret values normalize to `None` consistently if that is intended behavior

**Files:** `src/memory_knowledge/config.py`, `src/memory_knowledge/guards.py`, `tests/test_config.py`, `tests/test_guards.py`

**Discovered:** 2026-04-10 — during local post-migration analytics verification, the focused analytics/workflow tests passed but the broad suite still failed on config/guard expectations unrelated to the analytics upgrade surface.

---

### 3. No per-file progress logging during ingestion
**Problem:** The ingestion workflow logs phase transitions (files_determined, edges_resolved, ingestion_complete) but not per-file progress. During a 2,580-file ingestion, there are no logs for 30+ minutes between `revision_upserted` and `edges_resolved`, making it impossible to distinguish "slow but working" from "hung."

**Fix:** Add periodic progress logging — e.g., every 50 files: `{"event": "ingestion_progress", "files_processed": 150, "total_files": 2580}`

**Files:** `src/memory_knowledge/workflows/ingestion.py`

---

### 4. Qdrant Cloud requires explicit payload indexes
**Problem:** The `ensure_collections` function creates `is_active` as `KEYWORD` type, but the retrieval filter uses it as a `BOOL` match. Local Qdrant auto-handles this, but Qdrant Cloud requires explicit type-matched indexes. Same issue with `branch_name` and `commit_sha` which are needed for `deactivate_old_points` but weren't indexed.

**Status:** Code fix committed in `db/qdrant.py` for `is_active` (bool) and `branch_name`/`commit_sha` (keyword). But indexes keep getting lost after repair workflows — the repair may recreate collections without re-running `ensure_collections`. The `ensure_collections` function runs at startup but NOT after repair. Fix: call `ensure_collections` at the end of any repair workflow, or make indexes idempotent in the repair code itself.

**Files:** `src/memory_knowledge/db/qdrant.py`

---

### 5. No repo data reset/purge MCP tool
**Problem:** Resetting a repo's data across all 3 databases requires manual SQL + Qdrant API + Neo4j Cypher with careful FK ordering. There's no MCP tool to do this safely.

**Fix:** Add a `purge_repository` MCP tool that deletes all data for a repo across PG, Qdrant, and Neo4j in the correct dependency order. Should require `ALLOW_REMOTE_REBUILDS=true` for remote mode.

**Files:** `src/memory_knowledge/server.py`, new function in `src/memory_knowledge/admin/`

---

### 8. Local ingestion → remote export/import pipeline
**Problem:** Ingesting large repos (2,580+ files) directly against remote Supabase PG is extremely slow (~10 files/min). The heavy parse+chunk+embed phase does thousands of sequential INSERT round-trips over transatlantic latency.

**Proposed solution:** Ingest locally (fast), then export and import to remote:
1. Switch to `DATA_MODE=local`, run ingestion against local PG (hundreds of files/min)
2. `export_repo_memory_tool` → JSON dump of all repo data
3. Switch to `DATA_MODE=remote`
4. `import_repo_memory_tool` → bulk load into Supabase
5. `run_repair_rebuild_workflow` → project embeddings to Qdrant Cloud + graph to Neo4j Aura

**Investigation complete:**
- Export covers all 12 PG tables in FK-safe order (entities, files, chunks, symbols, edges, summaries, learned_records, etc.)
- Import handles FK remapping with 5 ID maps, uses UPSERT for idempotency
- Export is JSONL format, does NOT include embeddings or graph data — those are re-projected via `run_repair_rebuild_workflow`
- Import size limit is 50 MB (`max_import_size_mb` in config) — may need increasing for large repos
- Full pipeline: local ingest → export → import to Supabase → repair (re-embeds to Qdrant + projects to Neo4j)

**Remaining work:**
- Test the full pipeline end-to-end with a real repo
- Verify repair workflow re-embeds ALL chunks (not just missing ones)
- Consider increasing `max_import_size_mb` for large repos or adding streaming import

**Files:** `src/memory_knowledge/server.py` (export/import tools), investigate scope

**Discovered:** 2026-04-03 — CSS-FE remote ingestion taking hours due to PG latency.

---

### 9. Import function needs batched writes, incremental commits, and progress logging
**Problem:** `import_repo_memory` writes 87K+ rows one at a time with individual INSERT round-trips. Against remote PG (~100ms/query), a 87K row import takes ~2.5 hours. Also no progress logging and no incremental commits.

**Fix:**
- Use `executemany` or `COPY` for bulk INSERTs instead of individual queries
- Batch commits every 1,000 rows
- Log progress per table
- This is the #1 blocker for the export/import pipeline to be practical with remote databases

**Files:** `src/memory_knowledge/admin/export_import.py`

---

## Low Priority

### 6. Docker Compose override file management for local/remote mode
**Problem:** Switching between local and remote mode requires manually renaming `docker-compose.override.yml` to enable/disable `depends_on`. This is error-prone.

**Fix:** Use a script or Makefile target: `make local` / `make remote` that manages the override file and .env symlink.

---

### 7. Supabase direct connection DNS propagation
**Problem:** New Supabase projects on Nano tier may take hours for the `db.[project-ref].supabase.co` direct connection hostname to propagate. The pooler endpoint (`aws-0-[region].pooler.supabase.com`) is available immediately.

**Status:** Using pooler endpoint (port 6543) with `statement_cache_size=0`. Direct connection can be used once DNS propagates, for better performance (no PgBouncer overhead).

**No code change needed** — just a configuration note.
