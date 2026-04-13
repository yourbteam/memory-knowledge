# Task Objective

Add a supported backfill/re-embedding path for historic triage cases so semantic retrieval can be repaired or rebuilt after Qdrant loss, embedding changes, or degraded writes.

# Current-State Findings

- `save_triage_case` does a best-effort Qdrant upsert at write time.
- If that upsert fails, the case is still persisted and only a warning is logged.
- That best-effort behavior exists at the helper layer, but the supported public MCP triage tools still hard-require an initialized Qdrant client because `server.save_triage_case(...)` and `server.search_triage_cases(...)` both call `get_qdrant_client()` before entering `triage_memory`.
- There is currently no dedicated re-embedding or backfill path for `ops.triage_cases`.
- `src/memory_knowledge/db/qdrant.py` now ensures the `triage_cases` collection exists and attempts to create the payload indexes used by filtered triage search, but payload-index creation failures are silently ignored.
- The repo already has two nearby repair idioms:
  - `src/memory_knowledge/integrity/embedding_backfill.py` compares canonical PG rows against existing Qdrant IDs for `code_chunks`, `summary_units`, and `learned_memory`, but if the Qdrant existence check fails it can fall back to re-embedding every eligible row in that collection
  - `src/memory_knowledge/integrity/repair_drift.py` reprojects canonical PG data into Qdrant/Neo4j for repository repair workflows and already runs `ensure_collections(...)` before Qdrant repair
- Those existing repair paths do not currently touch triage data:
  - `embedding_backfill.py` has no `triage_cases` branch
  - `repair_drift.py` has no triage-case query, no triage-case payload builder, and no triage-case count in `RepairReport`
- Triage data is repository-scoped, not repo-revision-scoped:
  - `ops.triage_cases` stores `repository_id` and request metadata, but not `repo_revision_id` or commit identifiers
  - that means triage reprojection should key off repository scope and current payload contract rather than the latest repo revision
- Current triage Qdrant payload shape is written inline inside `save_triage_case` and includes:
  - `triage_case_id`
  - `repository_key`
  - `project_key`
  - `feature_key`
  - `request_kind`
  - `selected_workflow_name`
  - `policy_version`
  - `created_utc`
- That payload is not fully canonical today:
  - `created_utc` is generated with `dt.datetime.now(...)` at projection time rather than sourced from the persisted PostgreSQL row
  - repeating the current projection path for the same historic case would therefore mutate the Qdrant payload timestamp unless the implementation intentionally changes that behavior
- The inline payload builder means there is no shared helper today to guarantee write-time and backfill-time payload parity.
- That Qdrant payload is only part of the live search contract:
  - Qdrant-side filtering uses `repository_key`, `project_key`, `feature_key`, `request_kind`, `selected_workflow_name`, and `policy_version`
  - SQL post-filtering still applies additional constraints such as `execution_mode` and `selected_run_action`
  - through the supported public write surface, `selected_run_action` is only persisted when `request_kind == "run_operation"`, even though search still exposes filtering on that column
- Triage embeddings currently use `embed_single(...)` at write time, while the existing generic backfill path uses batched `embed(...)`; any backfill design should choose explicitly whether triage stays single-item or adds a batched helper for larger repairs.
- `search_triage_cases` does not lexically backfill when semantic search returns zero hits from Qdrant; it only falls back when semantic retrieval is unavailable. Missing historic points therefore create silent semantic blind spots rather than automatic lexical recovery.
- Even after semantic points are restored, default retrieval still excludes older rows:
  - both the MCP wrapper and helper default `max_age_days` to `180`
  - the SQL fetch path enforces that age window, so re-embedding alone does not make older historic triage cases show up in default searches
- `save_triage_case` does not call `ensure_collections(...)` before attempting the `triage_cases` upsert:
  - it writes the canonical PG row first
  - then it directly upserts to Qdrant if a client exists
  - any Qdrant failure is logged and suppressed
- The supported repair workflow surface is stricter than the analysis first implied:
  - `run_repair_rebuild_workflow` is the public MCP entrypoint, guarded as a destructive remote write, and submits background job execution that returns a `job_id`
  - it only exposes repository-level `repair()` with `repair_scope` in `{full, qdrant, neo4j}`
  - there is no public triage-only repair scope today
  - qdrant-only repair is still blocked unless the repository has at least one `catalog.repo_revisions` row, because `repair()` resolves the latest revision before any Qdrant work runs
  - qdrant-only repair also still inherits full dependency coupling on the current public path, because the workflow requires initialized `qdrant_client`, `neo4j_driver`, and other dependencies before any scope-specific branch runs

# Source Artifacts Inspected

- `src/memory_knowledge/triage_memory.py`
- `src/memory_knowledge/server.py`
- `src/memory_knowledge/db/qdrant.py`
- `src/memory_knowledge/integrity/embedding_backfill.py`
- `src/memory_knowledge/integrity/repair_drift.py`
- `src/memory_knowledge/workflows/repair_rebuild.py`
- `tests/test_triage_memory.py`
- `tests/test_repair_drift.py`

# Constraints

- PostgreSQL remains authoritative for triage case structure.
- The backfill path should be safe to rerun.
- The implementation should fit existing repair/rebuild idioms rather than inventing a one-off admin path without tests.
- The triage backfill path must preserve the current `triage_cases` payload contract used by filtered search.
- The repair entry point should remain compatible with the repo’s supported repair workflow surface.
- If the supported repair surface remains the entry point, the implementation must account for the current repo-revision prerequisite even though triage cases themselves are not revision-scoped.

# Risks And Edge Cases

- Historic rows may lack any Qdrant point after partial write failures.
- Embedding dimensions and payload schema must match the current `triage_cases` collection contract.
- Large backfills should not fail the whole operation on one bad row.
- Reprojecting triage points through a repo-revision-oriented workflow can introduce the wrong coupling because triage rows are not versioned by repo revision.
- If triage repair is folded into `RepairReport`, callers and tests may need explicit handling for a new triage repair count field.
- If triage repair stays behind the existing `full`/`qdrant` scopes, operators will not be able to invoke it independently unless the public scope surface changes.

# Recommended Approach

- Extract a shared triage-point builder so write-time projection and backfill/repair use the same payload contract.
- Add a triage-case backfill/reprojection function that scans canonical PG triage rows by repository, recomputes embeddings, and upserts deterministic Qdrant points.
- Integrate that function into the supported Qdrant repair path rather than creating an unrelated one-off surface.
- Extend tests to cover collection repair, payload parity, and idempotent reruns.

--- Analysis Verification Iteration 1 ---
Findings from verifier: 5
FIX NOW: 3 (analysis updated)
IMPLEMENT LATER: 0 (no change)
ACKNOWLEDGE: 2 (no change)
DISMISS: 0 (no change)

--- Analysis Verification Iteration 2 ---
Findings from verifier: 4
FIX NOW: 4 (analysis updated)
IMPLEMENT LATER: 0 (no change)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

--- Analysis Verification Iteration 3 ---
Findings from verifier: 5
FIX NOW: 3 (analysis updated)
IMPLEMENT LATER: 0 (no change)
ACKNOWLEDGE: 2 (no change)
DISMISS: 0 (no change)

--- Analysis Verification Iteration 4 ---
Findings from verifier: 3
FIX NOW: 2 (analysis updated)
IMPLEMENT LATER: 0 (no change)
ACKNOWLEDGE: 1 (no change)
DISMISS: 0 (no change)
