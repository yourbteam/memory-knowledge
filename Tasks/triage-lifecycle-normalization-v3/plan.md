# Objective

Introduce a stronger triage lifecycle model so the system distinguishes decision state, execution outcome, validation state, and supersession explicitly and consistently.

# Scope

## In Scope

- additive schema changes for triage lifecycle modeling
- new canonical reference domains
- read-model updates for current-state derivation
- historic backfill strategy
- contract updates where needed for compatibility-safe lifecycle support

## Out Of Scope

- synthesized policy recommendations
- ranking changes in triage search
- automatic enforcement or rollout controls

# Implementation Steps

1. Define lifecycle domains.
- Add a new `core.reference_types` domain for decision lifecycle state, separate from `TRIAGE_OUTCOME_STATUS`.
- Seed canonical values that the current write surface can actually support without inventing new producer phases:
  - `proposed`
  - `feedback_recorded`
  - `validated`
  - `needs_retriage`
  - `human_rejected`
  - `superseded`
- Keep lifecycle state distinct from outcome status so existing analytics can retain outcome semantics while new consumers can ask for canonical decision state.

2. Design additive schema changes.
- Store the current lifecycle projection directly on `ops.triage_cases` to avoid an extra lookup table for a single current-state record.
- Preserve append-only feedback history in `ops.triage_case_feedback`.
- Add:
  - `lifecycle_state_id BIGINT REFERENCES core.reference_values(id)`
  - `lifecycle_updated_utc TIMESTAMPTZ`
  - `superseded_by_case_id UUID NULL REFERENCES ops.triage_cases(triage_case_id)`
- Backfill existing rows so every current case has a lifecycle state immediately after migration.

3. Implement backfill rules.
- Map existing feedback-only history into the lifecycle projection deterministically:
  - no feedback => `proposed`
  - latest normalized outcome `confirmed_correct` => `validated`
  - latest normalized outcome `corrected` => `needs_retriage`
  - latest normalized outcome `overridden_by_human` or `human_override = true` => `human_rejected`
  - any other feedback row => `feedback_recorded`
- Preserve `superseded` as a supported canonical value even if historic backfill cannot infer it automatically from current data.
- Keep PostgreSQL lifecycle backfill separate from `reproject_triage_cases`, which only repairs Qdrant projection state for already persisted triage cases.
- Make backfill deterministic and idempotent.

4. Update read-model helpers.
- Introduce shared helpers in `src/memory_knowledge/triage_memory.py` for:
  - resolving lifecycle reference ids
  - mapping feedback rows to lifecycle internal codes
  - projecting lifecycle fields into API rows
- Replace the repeated latest-feedback projection currently embedded in `_fetch_search_rows`, `_fetch_triage_analysis_rows`, and `get_triage_feedback_summary` with one shared lifecycle projection path.
- Keep outcome-status derivation intact for existing analytics, but stop duplicating lifecycle semantics across search and summary paths.
- Ensure summary, search, and future policy tools all expose the same lifecycle projection for the same case.

5. Decide whether tool contracts need additive updates.
- Keep `save_triage_case` and `record_triage_case_feedback` backward compatible.
- On `save_triage_case`, initialize lifecycle state to `proposed`.
- On `record_triage_case_feedback`, update the case-level lifecycle projection based on the inserted feedback row.
- Add lifecycle fields to read-side responses where they help downstream consumers and do not break existing callers:
  - `search_triage_cases`
  - internal analytics row builders
- Do not require new write parameters in this increment.

6. Add compatibility tests.
- migration backfill for historic case with no feedback
- migration backfill for case with normalized status feedback
- fallback handling for unknown legacy feedback text
- `save_triage_case` initializes lifecycle fields
- `record_triage_case_feedback` updates lifecycle projection consistently
- read paths surface the same lifecycle value for the same case
- explicit `superseded_by_case_id` support if set manually or by later tooling

# Affected Files

- `migrations/versions/<new_lifecycle_revision>.py`
- `src/memory_knowledge/triage_memory.py`
- `src/memory_knowledge/server.py`
- `tests/test_triage_memory.py`
- optionally a new `tests/test_triage_lifecycle.py`

# Validation

- additive migration applies cleanly on top of `011_triage_outcome_status_reference_values`
- current lifecycle projection is identical across search and summary paths for the same case
- historic rows backfill without data loss
- existing integrator calls still succeed
- canonical lifecycle reference values are seeded and queryable through `list_reference_values`

# Dependencies And Sequencing

- should land before or together with policy synthesis
- should inform governance work because lifecycle states define what can be trusted

--- Plan Verification Iteration 1 ---
Findings from verifier: 5
FIX NOW: 3 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 2 (no change)
DISMISS: 0 (no change)
