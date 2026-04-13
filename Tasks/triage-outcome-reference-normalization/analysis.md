# Task Objective

Normalize triage outcome statuses through `core.reference_types` / `core.reference_values` instead of storing them as uncontrolled freeform strings.

# Current-State Findings

- `ops.triage_case_feedback.outcome_status` is a `VARCHAR(100)` in `010_triage_memory`.
- the public MCP write path does not canonical-validate `outcome_status` at all:
  - `record_triage_case_feedback` only checks that `outcome_status` is non-empty
  - the persistence layer inserts whatever string it receives
- Read paths in `src/memory_knowledge/triage_memory.py` assume semantic values such as:
  - `pending`
  - `confirmed_correct`
  - `corrected`
  - `overridden_by_human`
- additional values such as `execution_failed_after_route` and `insufficient_context` exist in the confidence helper, but they do not currently drive filtering, ranking, or summary metrics
- `pending` is currently both:
  - a possible freeform stored value because writes are unvalidated
  - an implicit derived state for cases with no feedback row, via `COALESCE(..., 'pending')` in search and summary
- the effective current-state outcome model is latest-feedback-row-wins:
  - `ops.triage_case_feedback` is append-only in practice
  - read paths resolve the most recent feedback row by `created_utc DESC, id DESC`
- current read behavior depends materially on `outcome_status`:
  - search filters out `corrected` / `overridden_by_human` when `include_corrected = false`
  - search boosts `confirmed_correct`
  - search down-ranks `corrected` / `overridden_by_human`
  - summary rates and problem-prompt rollups are keyed off the effective status
  - `top_misroutes` is driven by `corrected_request_kind` on the latest feedback row, not directly by `outcome_status`
- current readers effectively use only:
  - `outcome_status`
  - `corrected_request_kind`
  from the latest feedback row
  Other feedback columns are written and stored, but they are not currently consumed by search/summary read paths
- because writes are unvalidated and most read-time branching uses exact literal comparisons, status variants with different casing or formatting can be stored but will not participate correctly in filtering, ranking, or summary rates
  - the only current normalization is in `_outcome_confidence()`, which does `strip().lower()` before mapping confidence values
- the schema and write path also allow contradictory combinations between `outcome_status` and auxiliary feedback fields:
  - there is no cross-field validation tying `outcome_status` to `successful_execution`, `human_override`, `correction_reason`, or the corrected-* fields
  - internally inconsistent feedback rows can therefore be stored even though current read paths mostly key off `outcome_status` and `corrected_request_kind`
- `_outcome_confidence()` is also part of the externally visible read model:
  - `search_triage_cases` returns `outcome_confidence` on every row
  - some non-canonical strings can still collapse to a confidence value in the API response even when they fail exact-match filtering/rate logic elsewhere
- summary rates use the full scoped population as the denominator:
  - `confirmed_correct_rate`, `corrected_rate`, and `human_override_rate` divide by total `case_count`
  - that denominator includes derived `pending` rows and any unrecognized freeform statuses
  - malformed or non-canonical status values therefore dilute the rates rather than being excluded
- Other parts of the repo already normalize several status domains through `core.reference_values`, including workflow run status, planning statuses/priorities, workflow validator status, and workflow finding domains.
- But not every status domain is normalized yet:
  - workflow phase status is still a raw string domain validated in code rather than a reference-value FK
- `list_reference_values(...)` already exposes normalized reference domains to integrators.
- triage outcomes are not currently one of those normalized domains:
  - `010_triage_memory` adds no triage outcome reference type
  - `list_reference_values(...)` can only expose values for reference types that already exist

# Source Artifacts Inspected

- `migrations/versions/005_planning_schema.py`
- `migrations/versions/008_analytics_schema.py`
- `migrations/versions/009_workflow_findings.py`
- `migrations/versions/010_triage_memory.py`
- `src/memory_knowledge/server.py`
- `src/memory_knowledge/triage_memory.py`
- `tests/test_triage_memory.py`

# Constraints

- The MCP contract should remain stable for callers.
- Existing triage feedback rows, if any, need a safe migration path.
- Search and summary behavior should continue to work during and after the normalization change.
- Current tests do not fully cover the normalization gap behaviors described here:
  - no coverage for non-canonical/freeform `outcome_status` values
  - no coverage for derived `pending` from missing feedback
  - no coverage for contradictory auxiliary feedback-field combinations
  - no coverage for exact-match filtering/ranking failures caused by malformed status strings

# Risks And Edge Cases

- Backfilling unknown freeform values into a normalized domain requires an explicit mapping strategy.
- The repo currently exposes triage outcome semantics only implicitly; introducing a reference domain requires choosing canonical internal codes carefully.

# Recommended Approach

- Add a new reference type for triage outcomes.
- Add a foreign-key-backed status column to `ops.triage_case_feedback`.
- Backfill from existing `outcome_status` text values using a deterministic mapping.
- Treat missing feedback rows explicitly, since they currently surface as an effective `pending` state at read time rather than as stored `pending` rows.
- Preserve latest-feedback-row-wins semantics after normalization.
- Keep read/write tool contracts compatible by still accepting/returning stable status codes.

--- Analysis Verification Iteration 1 ---
Findings from verifier: 5
FIX NOW: 2 (analysis updated)
IMPLEMENT LATER: 0 (analysis updated)
ACKNOWLEDGE: 2 (no change)
DISMISS: 1 (no change)

--- Analysis Verification Iteration 2 ---
Findings from verifier: 4
FIX NOW: 3 (analysis updated)
IMPLEMENT LATER: 0 (analysis updated)
ACKNOWLEDGE: 1 (no change)
DISMISS: 0 (no change)

--- Analysis Verification Iteration 3 ---
Findings from verifier: 4
FIX NOW: 2 (analysis updated)
IMPLEMENT LATER: 0 (analysis updated)
ACKNOWLEDGE: 1 (no change)
DISMISS: 1 (no change)

--- Analysis Verification Iteration 4 ---
Findings from verifier: 2
FIX NOW: 2 (analysis updated)
IMPLEMENT LATER: 0 (analysis updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

--- Analysis Verification Iteration 5 ---
Findings from verifier: 3
FIX NOW: 3 (analysis updated)
IMPLEMENT LATER: 0 (analysis updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

--- Analysis Verification Iteration 6 ---
Findings from verifier: 4
FIX NOW: 2 (analysis updated)
IMPLEMENT LATER: 0 (analysis updated)
ACKNOWLEDGE: 1 (no change)
DISMISS: 1 (no change)
