# Database Fixes — Granular Implementation Plan (F1–F8)

**Status:** Awaiting approval. No code changes until each step is approved.
**Source of findings:** [`docs/DATABASE_UTILIZATION_RESEARCH.md`](DATABASE_UTILIZATION_RESEARCH.md) §8.
**Constraints honored:** runs on remote (do not switch env); no schema/column invented — every reference checked against source.

## Phase ordering & rationale
1. **Phase 1 — Stale-data correctness (F1, F3, F6).** Highest impact; everything else assumes a correct `is_active` model in PG.
2. **Phase 2 — Compaction / GC (F2).** Depends on Phase 1's `is_active` flags to know what is safe to delete.
3. **Phase 3 — Ranking & route-policy integrity (F7, F8).** Independent of 1–2; behavior-changing, needs decisions.
4. **Phase 4 — Ops/security (F4, F5).** Small, isolated, no dependency.

Each phase ends with explicit verification. Phases are independently approvable and revertible.

---

## PHASE 1 — Stale-data correctness (F1, F3, F6)

> **STATUS: COMPLETE + DEPLOYED + VERIFIED in production (2026-06-02).**
> - Steps 1.1–1.7 implemented; `tests/test_ingestion.py` 14/14 pass; ruff clean (no new findings).
> - Committed to `main` (`823110a` → `7a5fde1`) and pushed.
> - Migration `023` applied to prod Supabase (`022` → `023` head); `is_active` columns + partial GIN indexes present; old full GIN indexes dropped.
> - Backfill run across all repos: 18,169 chunks + 12,021 summaries deactivated (fcsapi, millennium-wp); `catalog.chunks` = 66,658 active / 18,169 inactive.
> - Deployed image `memory-knowledge:7a5fde1` via `az acr build` → webapp container set → restart; `/ready` green (pg/qdrant/neo4j all ok).
> - Verified live: full-text for 'fleet' on fcsapi returns 4 active vs 8 unfiltered — 4 stale hits now excluded (F1 fix confirmed). Post-deploy backfill re-run: 0 drift.
> - **Note (pre-existing, unrelated):** prod OpenAI account returns `429 insufficient_quota`, breaking the embedding/semantic-retrieval path (and embedding-dependent ingestion). Not caused by this change; flagged separately.

**Goal:** PG full-text/summary retrieval must serve only current content, matching Qdrant's `is_active` model; deleted files must not linger in PG or Neo4j.

**Design:** `catalog.chunks` and `catalog.summaries` have **no `is_active` column** today and PG retrieval scopes by `repository_id` only. We add `is_active`, deactivate it at the same three sites where Qdrant points are deactivated, filter retrieval on it, and remove deleted-file Neo4j nodes. Backfill PG `is_active` from Qdrant (already authoritative) so existing data is corrected without a full re-ingest.

### Step 1.1 — Migration `023_chunk_summary_is_active`
**New file:** `migrations/versions/023_chunk_summary_is_active.py`
**Why:** add the column the deactivation/filtering logic needs.
**Change (raw SQL, mirrors existing migration idiom in `022_*`):**
- `revision = "023_chunk_summary_is_active"`, `down_revision = "022_mawf_task_artifact_branch_metadata"`.
- `ALTER TABLE catalog.chunks ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE`
- `ALTER TABLE catalog.summaries ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE`
- Partial indexes to keep filtered full-text fast:
  - `CREATE INDEX IF NOT EXISTS idx_chunks_active ON catalog.chunks (id) WHERE is_active`
  - `CREATE INDEX IF NOT EXISTS idx_summaries_active ON catalog.summaries (id) WHERE is_active`
- `downgrade()`: drop the two indexes and two columns.

> Note: defaulting existing rows to `TRUE` is intentionally non-destructive; the one-time backfill (Step 1.6) corrects historical rows.

### Step 1.2 — PG deactivation helpers in `pg_writer.py`
**File:** [`src/memory_knowledge/projections/pg_writer.py`](../src/memory_knowledge/projections/pg_writer.py)
**Why:** provide the PG analogues of `qdrant_projector.deactivate_old_points` / `summary_qdrant.deactivate_old_summary_points` and the per-file Qdrant `set_payload` calls.
**Add three functions:**

1. `deactivate_file_chunks(pool, repository_id, file_path)` — per-file (incremental changed/deleted):
   ```sql
   UPDATE catalog.chunks c SET is_active = FALSE
   FROM catalog.files f, catalog.entities e
   WHERE c.file_id = f.id AND c.entity_id = e.id
     AND e.repository_id = $1 AND f.file_path = $2 AND c.is_active = TRUE
   ```
2. `deactivate_old_chunks(pool, repository_id, branch_name, new_commit_sha)` — full-run (mirrors `deactivate_old_points`):
   ```sql
   UPDATE catalog.chunks c SET is_active = FALSE
   FROM catalog.entities e, catalog.repo_revisions rr
   WHERE c.entity_id = e.id AND e.repo_revision_id = rr.id
     AND rr.repository_id = $1 AND rr.branch_name = $2
     AND rr.commit_sha <> $3 AND c.is_active = TRUE
   ```
3. `deactivate_old_summaries(pool, repository_id, new_commit_sha)` — full-run (mirrors `deactivate_old_summary_points`, repo+commit only, no branch):
   ```sql
   UPDATE catalog.summaries s SET is_active = FALSE
   FROM catalog.entities e, catalog.repo_revisions rr
   WHERE s.entity_id = e.id AND e.repo_revision_id = rr.id
     AND rr.repository_id = $1 AND rr.commit_sha <> $2 AND s.is_active = TRUE
   ```

**Ordering guarantee:** new chunks/summaries are bulk-inserted (default `is_active=TRUE`) *after* these run, so deactivation never touches the rows just written.

### Step 1.3 — Wire deactivation into ingestion
**File:** [`src/memory_knowledge/workflows/ingestion.py`](../src/memory_knowledge/workflows/ingestion.py)
**Why:** keep PG `is_active` in lockstep with the existing Qdrant deactivation, at the identical sites.
- **Deleted file (incremental)** — after the Qdrant `set_payload` at [`:622`](../src/memory_knowledge/workflows/ingestion.py:622): add `await deactivate_file_chunks(pool, repository_id, file_path)`.
- **Changed file (incremental)** — after the Qdrant `set_payload` at [`:646`](../src/memory_knowledge/workflows/ingestion.py:646): add the same call.
- **Full run** — alongside `deactivate_old_points`/`deactivate_old_summary_points` at [`:1110`](../src/memory_knowledge/workflows/ingestion.py:1110): add `await deactivate_old_chunks(pool, repository_id, branch_name, commit_sha)` and `await deactivate_old_summaries(pool, repository_id, commit_sha)`.

### Step 1.4 — Filter retrieval on `is_active`
**File:** [`src/memory_knowledge/workflows/retrieval.py`](../src/memory_knowledge/workflows/retrieval.py)
**Why:** the actual F1/F6 fix — stop serving stale PG content.
- `pg_fulltext_search` **both** query branches ([`:118`](../src/memory_knowledge/workflows/retrieval.py:118), [`:141`](../src/memory_knowledge/workflows/retrieval.py:141)): add `AND c.is_active = TRUE` to each `WHERE`.
- `pg_summary_search` ([`:211`](../src/memory_knowledge/workflows/retrieval.py:211)): add `AND s.is_active = TRUE`.
- (Optional, same theme) learned-rule scope query at [`:807`](../src/memory_knowledge/workflows/retrieval.py:807): not chunk-based; leave for Phase 1.5 evaluation.

### Step 1.5 — Deleted-file cleanup in Neo4j (F3)
**Files:** [`src/memory_knowledge/projections/neo4j_projector.py`](../src/memory_knowledge/projections/neo4j_projector.py) + ingestion deleted-file branch.
**Why:** Neo4j `File`/`Symbol` nodes have no `is_active`, so deleted-file nodes stay graph-traversable.
- Add `delete_file_subgraph(driver, file_entity_key)`:
  ```cypher
  MATCH (f:File {entity_key: $ek}) OPTIONAL MATCH (f)-[:CONTAINS]->(s:Symbol)
  DETACH DELETE s, f
  ```
- In the deleted-file branch ([`ingestion.py:620`](../src/memory_knowledge/workflows/ingestion.py:620)): resolve the file's `entity_key` (it is `file_entity_key(repository_key, commit_sha_of_record, file_path)`; for a deleted file we look it up from PG `catalog.files`→`entities` by repo+path) and call `delete_file_subgraph`, guarded by `if neo4j_driver is not None`.
- Also deactivate the deleted file's PG chunks via Step 1.2 #1 (already added in Step 1.3).

> Symbols/files PG rows for deleted files are left in place (not retrieval-facing); Phase 2 compaction removes them. Documented, not silently skipped.

### Step 1.6 — One-time backfill of historical `is_active`
**New file:** `scripts/backfill_pg_is_active.py` (or an admin tool entry; pattern TBD with you).
**Why:** existing chunk/summary rows default to `TRUE`; stale historical rows must be corrected without a full re-ingest. Qdrant `is_active` is already authoritative (point id == entity_key).
- For each repository: scroll Qdrant `code_chunks` for `is_active=False` point ids → `UPDATE catalog.chunks SET is_active=FALSE WHERE entity_id IN (SELECT id FROM catalog.entities WHERE entity_key = ANY(...))`. Same for `summary_units`→`catalog.summaries`.
- Chunks/summaries with no corresponding Qdrant point: left `TRUE` (conservative; logged with a count).
- Idempotent and re-runnable.

### Step 1.7 — Integrity check awareness (optional, recommended)
**File:** [`src/memory_knowledge/integrity/check_pg_qdrant.py`](../src/memory_knowledge/integrity/check_pg_qdrant.py)
**Why:** the forward check currently expects every PG chunk to have a Qdrant point; after Phase 1 it should compare active-vs-active to avoid false "missing" reports. Add an `is_active` filter to the PG chunk scan.

### Phase 1 verification
- `alembic upgrade head` on a scratch DB; confirm columns + indexes exist.
- Unit: deactivation helpers flip exactly the intended rows (table-driven test with two commits + one deleted file).
- Integration: ingest commit A (file X), then commit B (X changed, Y deleted); assert `pg_fulltext_search` returns only B's content for X and nothing for Y; assert Neo4j has no Y nodes.
- Run backfill on a copy; assert PG active counts match Qdrant active counts per repo.

---

## PHASE 2 — Compaction / garbage collection (F2)

> **STATUS: ✅ FULLY COMPLETE (2026-06-03) — PG compaction + Neo4j orphan GC.**
> - **Neo4j orphan GC done:** refined "current" = files/symbols backed by active chunks ∪ branch-head-revision files/symbols (`ab85706`). Validated (orphans have 0 active chunks, all on old revisions). Deleted 12,024 old-commit File/Symbol nodes; graph 30,293 → 18,269; re-check 0 orphans remain.
> - `integrity/compaction.py` (`compact_repository`, dry-run-first) committed `9e37a4f`. Run offline via local runner (D2 pattern), not the MCP tool.
> - Pruned prod: deleted 18,169 inactive chunks + 12,021 inactive summaries (`catalog.chunks` 84,827→66,658 / 0 inactive; `summaries` 37,692→25,671 / 0 inactive). FK-safe (learned_records empty). `ANALYZE` refreshed; `dead=0` (autovacuum reclaimed for reuse — on-disk size held for reuse, bounding growth; no `VACUUM FULL` to avoid the table lock).
> - Qdrant: 0 inactive points (collections were rebuilt active-only during the embeddings migration).
> - **DEFERRED — Neo4j orphan GC:** the current "active set" derives from `catalog.entities` (which PG never prunes), so graph-orphan detection no-ops. Needs a stricter current-entity definition (e.g. files bearing active chunks) before it removes old-commit File/Symbol nodes.

**Goal:** bound storage growth; nothing is ever hard-deleted today and `repair` only adds.

**Design:** add a **flag-gated, dry-run-first** compaction that removes data already marked inactive/superseded, beyond a retention window. Honors remote write guards (`allow_remote_rebuilds`).

### Step 2.1 — Settings
**File:** [`src/memory_knowledge/config.py`](../src/memory_knowledge/config.py)
- `compaction_enabled: bool = False`
- `compaction_retention_revisions: int = 3` (keep N most recent revisions per branch)
- `compaction_dry_run_default: bool = True`

### Step 2.2 — Compaction module
**New file:** `src/memory_knowledge/integrity/compaction.py`
**Why:** central, testable pruning with a dry-run report; reused by the workflow.
- `compact_repository(pool, qdrant, neo4j, settings, repository_key, *, dry_run)`:
  - **Qdrant:** scroll `code_chunks`/`summary_units` for `is_active=False`; collect point ids; `client.delete(...)` in batches (dry-run: count only).
  - **PG:** delete `catalog.chunks`/`catalog.summaries` where `is_active=FALSE`; then delete now-orphaned `catalog.entities` rows of type `chunk`/`summary` not referenced elsewhere. (FK-safe order: dependents → entities.)
  - **Neo4j:** delete `File`/`Symbol` nodes whose `entity_key` is not in the PG active set for the repo (orphans), batched.
  - Returns a `CompactionReport` (counts per store, dry-run flag).
- **Retention guard:** only operate on revisions older than the `compaction_retention_revisions` newest per branch (resolve via `catalog.repo_revisions` + `catalog.branch_heads`).

### Step 2.3 — Expose via the existing add-only workflow
**File:** [`src/memory_knowledge/workflows/repair_rebuild.py`](../src/memory_knowledge/workflows/repair_rebuild.py)
- Add `repair_scope="compact"` branch calling `compaction.compact_repository(...)`, defaulting to dry-run unless explicitly told otherwise and `allow_remote_rebuilds` is set.
- Log dropped counts (no silent truncation).

### Phase 2 verification
- Seed two superseded revisions; dry-run reports expected counts and deletes nothing.
- Real run deletes only inactive/superseded data; active retrieval results unchanged before/after.
- FK integrity: no dangling references post-delete (`check_entities` passes).

---

## PHASE 3 — Ranking & route-policy integrity (F7, F8)

> **STATUS: ✅ COMPLETE + DEPLOYED + VERIFIED (2026-06-03, image `15d7a25`).**
> - F7: `rerank_results` → scaled RRF (rank-based, magnitude-preserving so `compute_auto_feedback` thresholds stay valid).
> - F8: wired `semantic_assist_enabled` (decision_history now gets a vector pass) + `confidence_threshold` (Qdrant score floor); migration `024` recalibrated thresholds to the bge-base band (sampled empirically) and dropped the 3 dead columns.
> - Verified live: conceptual 40 results; decision_history now returns qdrant+summary (was lexical-only); nonsense cut 40→1 by the threshold. Full test suite green (398 passed); fixed a CI-red embedding-default test.

**Goal:** make fusion scores comparable (F7) and stop the route table implying behavior that doesn't run (F8). **Behavior-changing — needs your decisions (below).**

### Step 3.1 — Comparable fusion (F7)
**File:** [`src/memory_knowledge/workflows/retrieval.py`](../src/memory_knowledge/workflows/retrieval.py) `rerank_results` ([`:293`](../src/memory_knowledge/workflows/retrieval.py:293)).
**Why:** today PG `ts_rank` is normalized to the *set max* (top PG hit always 1.0) and summed with absolute Qdrant cosine — incomparable scales.
**Proposed:** switch to **Reciprocal Rank Fusion (RRF)**: rank each source list independently, score `Σ weight_s / (k + rank_s)` (k≈60), then add the existing graph boost. Keeps it parameter-light and scale-free. Summary lists fold in as additional weighted sources.
**Decision needed (D1):** RRF (recommended) vs. per-source min-max normalization vs. leave as-is.

### Step 3.2 — Route-policy columns (F8)
**Files:** `retrieval.py` `run()` + (if pruning) a migration to drop seed columns.
Today only `first_store`, `second_store`, `allow_fanout`, `allow_graph_expansion` are read. **Decision needed (D2)** per dead column:
- `confidence_threshold` — **wire it**: drop fused results below the policy threshold (recommended; gives the seeded 0.80/0.50 values meaning).
- `third_store` — **wire it**: add a final fan-out tier to the third store when results remain below `FANOUT_THRESHOLD` after the second (recommended), OR drop from schema/seed.
- `semantic_assist_enabled` — **wire it**: for Postgres-led classes, also run a semantic pass when enabled (this directly remediates F6 for `exact_lookup` *if* its policy enables it), OR drop.
- `fusion_strategy` / `rerank_strategy` — currently decorative. Either honor as enums selecting Step 3.1's strategy, or drop. (Recommend: keep `fusion_strategy` to select RRF vs. weighted; drop `rerank_strategy`.)

> If "wire" is chosen for `semantic_assist_enabled` + `confidence_threshold`, **F6 is largely resolved here** rather than needing separate work — `exact_lookup` would gain a semantic assist and a relevance floor.

### Phase 3 verification
- Golden-set ranking tests: a strong semantic match outranks a weak lexical one (regression for F7).
- Per-class tests: `exact_lookup` now performs a semantic assist (if D2 enables it); results below `confidence_threshold` are excluded.
- `route_executions` still records accurately.

---

## PHASE 4 — Ops/security (F4, F5)

> **STATUS: ✅ BOTH COMPLETE + DEPLOYED.**
> - **F5** (Qdrant readiness parity): deployed in `15d7a25`.
> - **F4** (Postgres TLS verification): deployed in `0ce62aa`. `pg_ssl=True` now builds a verifying context (`CERT_REQUIRED` + hostname) against the baked **Supabase Root 2021 CA** (`docker/certs/supabase-root-2021.crt`, app setting `PG_SSL_CA_PATH=/app/certs/...`); `pg_ssl_insecure` is the explicit opt-out escape hatch. `VERIFY_X509_STRICT` kept off for the 2021 CA chain. Validated against the live pooler and confirmed `/ready` postgres=ok post-deploy.

### Step 4.1 — TLS verification (F4)
**Files:** [`src/memory_knowledge/db/postgres.py`](../src/memory_knowledge/db/postgres.py) [`:13`](../src/memory_knowledge/db/postgres.py:13), [`config.py`](../src/memory_knowledge/config.py).
**Why:** `pg_ssl=True` currently sets `check_hostname=False` + `verify_mode=CERT_NONE` — encrypted but unauthenticated (MITM-exposed), and `pg_ssl` is the prod/remote flag.
**Change:**
- Add setting `pg_ssl_insecure: bool = False`.
- In `init_postgres`: when `pg_ssl` is on, build a default verifying context (`CERT_REQUIRED`, hostname checking on, system/Provider CA). Only when `pg_ssl_insecure` is **explicitly** true fall back to the current relaxed context (with a `logger.warning`).
**Decision needed (D3):** confirm the remote/managed PG (Supabase/Azure) presents a CA-valid cert so `CERT_REQUIRED` won't break the live connection. If a custom CA bundle is required, add `pg_ssl_ca_path`.

### Step 4.2 — Qdrant readiness parity (F5)
**File:** [`src/memory_knowledge/db/health.py`](../src/memory_knowledge/db/health.py) [`:42`](../src/memory_knowledge/db/health.py:42).
**Why:** Qdrant is degraded-tolerant at startup but the readiness probe flips status to `not_ready`, unlike Neo4j.
**Change:** on Qdrant failure, set `results["qdrant"] = "degraded: ..."` and append to `results["degraded"]` instead of setting `status="not_ready"` — mirroring the Neo4j branch.
**Decision needed (D4):** confirm Qdrant is intended to be non-critical for readiness (consistent with commit `823110a`). If it *should* be critical, instead make startup fail — but that contradicts the current degraded-startup design.

### Phase 4 verification
- F4: connect to the live remote PG with `pg_ssl=True` and verification on; confirm success. Confirm a bad cert is now rejected.
- F5: simulate Qdrant down; `/health` readiness returns `status != not_ready` with `qdrant` in `degraded`.

---

## Cross-cutting notes
- **Migrations:** one new migration in Phase 1 (`023`), optionally one in Phase 3 if columns are dropped. Run via alembic on remote; coordinate with you before applying.
- **Rollout order:** deploy Phase 1 code + migration → run backfill (1.6) → verify → proceed. Phases 2–4 independently.
- **No env switching;** all work targets the remote configuration already in use.

## Decisions — APPROVED (2026-06-02)
- **D1 (Phase 3.1):** **RRF fusion.** `confidence_threshold` applied pre-fusion at source level (Qdrant `score_threshold` + ts_rank floor), since RRF scores are not 0–1.
- **D2 (Phase 3.2):** **WIRE** `semantic_assist_enabled` (fixes `decision_history` lexical-only bug) and `confidence_threshold`; **DROP** `third_store`, `fusion_strategy`, `rerank_strategy` from `routing.route_policies` (verified unused; removes misleading config). `exact_lookup` stays intentionally lexical (`semantic_assist=FALSE`), documented.
- **D3 (Phase 4.1):** **`CERT_REQUIRED` + Supabase CA bundle** via new `pg_ssl_ca_path`; retain `pg_ssl_insecure` as explicit opt-out. Must validate against live remote before commit.
- **D4 (Phase 4.2):** **Report `degraded`** (mirror Neo4j), consistent with deliberate degraded-startup (commit `823110a`).
- **Sequencing:** gate **step-by-step**; each individual code change presented for approval before it is made.
