# Scope

- Add a supported triage-case Qdrant backfill/re-embedding path.
- Keep the implementation aligned with the repo’s supported repair workflow surface rather than adding a one-off triage admin entrypoint.
- Do not broaden the current public triage MCP behavior around uninitialized Qdrant in this task; this task restores already-persisted historic rows through repair/reprojection rather than redesigning the save/search tool dependency contract.
- Cover the path with focused tests.

# Implementation Steps

1. Extract shared triage projection helpers from `src/memory_knowledge/triage_memory.py` so write-time projection and repair-time reprojection use the same:
   - point/payload builder
   - embedding/upsert behavior
   - canonical source-field mapping from persisted PG rows
   - an explicit write-path mechanism for obtaining those persisted fields, such as wider `RETURNING` columns or a follow-up row read after insert
2. Make the shared projection contract explicit for repair use:
   - preserve the current searchable payload fields already used by Qdrant-side filtering
   - keep SQL-only filters such as `execution_mode` and `selected_run_action` out of the Qdrant payload unless the task requires a deliberate contract change
   - choose and document the repair-time behavior for `created_utc`, because the current write path generates it at projection time rather than from canonical PG state
3. Implement a triage-case reprojection function that:
   - reads canonical triage cases from PG by `repository_key`
   - re-embeds rows in batches suitable for larger repair runs
   - upserts deterministic Qdrant points into `triage_cases`
   - tolerates row-level failures without aborting the entire triage reprojection pass
   - records row-level failures in a dedicated triage skipped/error count or equivalent non-fatal report field rather than promoting every bad row into `RepairReport.errors`
4. Integrate triage reprojection into the supported repair path in `src/memory_knowledge/integrity/repair_drift.py`:
   - run it under the existing `qdrant`/`full` repair scopes
   - extend `RepairReport` with a triage-specific repaired count
   - extend `RepairReport` with whatever non-fatal triage skipped/error count is needed for row-level continuation semantics
   - make row-level partial triage failures surface explicitly through the workflow/job contract rather than reporting silent top-level success
   - keep behavior consistent with the current background-job repair workflow contract
   - validate that any new triage report fields remain visible through the existing workflow/job result payload
5. Account for the current public repair-surface coupling in implementation and tests:
   - repository-level repair still requires repo-revision presence today
   - `qdrant` scope still inherits current dependency coupling on initialized Qdrant and Neo4j clients
   - no new public triage-only repair scope should be introduced unless the task intentionally expands the MCP contract
6. Add tests for:
   - shared triage payload/point construction parity
   - successful triage reprojection through the repair path
   - rerun safety / idempotent upsert behavior
   - row-level degradation handling if reprojection continues past a bad row
   - `RepairReport` triage counts and existing repair behavior remaining intact
   - existing learned-memory repair behavior remaining intact under the same `qdrant`/`full` repair scopes
   - restored semantic retrieval for repaired triage cases
   - retrieval of older historic triage cases when `max_age_days` is explicitly widened

# Validation

- Run focused triage-memory and repair/backfill tests.
- Confirm triage reprojection runs through the supported repair path and reports triage-specific repair counts.
- Confirm repaired cases are searchable again for cases within the existing default retrieval window.
- Confirm older historic cases can be recovered when search is invoked with an explicit widened `max_age_days` value, since the default contract still hard-limits retrieval to 180 days.
- Confirm existing repair tests for chunk/summary/learned-memory/Neo4j behavior still pass.

# Affected Files

- `src/memory_knowledge/triage_memory.py`
- `src/memory_knowledge/integrity/repair_drift.py`
- `src/memory_knowledge/workflows/repair_rebuild.py`
- `src/memory_knowledge/server.py`
- `tests/test_repair_drift.py`
- `tests/test_triage_memory.py`
- workflow/job-layer tests if needed to prove partial-vs-success status and persisted result payload behavior

--- Plan Verification Iteration 1 ---
Findings from verifier: 5
FIX NOW: 2 (plan updated)
IMPLEMENT LATER: 1 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 2 (no change)

--- Plan Verification Iteration 2 ---
Findings from verifier: 3
FIX NOW: 1 (plan updated)
IMPLEMENT LATER: 0 (no change)
ACKNOWLEDGE: 1 (no change)
DISMISS: 1 (no change)

--- Plan Verification Iteration 3 ---
Findings from verifier: 2
FIX NOW: 2 (plan updated)
IMPLEMENT LATER: 0 (no change)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

--- Plan Verification Iteration 4 ---
Findings from verifier: 4
FIX NOW: 4 (plan updated)
IMPLEMENT LATER: 0 (no change)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)
