# Scope

- Introduce normalized triage outcome statuses.
- Update triage write/read logic to use the normalized status model.
- Preserve MCP compatibility.
- Preserve the existing legacy string-facing MCP contract through an explicit legacy-to-normalized mapping layer.
  Current permissive acceptance of arbitrary non-empty status strings is part of that legacy contract, so this task must preserve permissive acceptance and normalize only recognized legacy values while handling unknowns safely.

# Implementation Steps

1. Add a migration that:
   - seeds a triage outcome reference type and values
   - uses namespaced `core.reference_values.internal_code` values that are safe under the global uniqueness constraint
   - adds `status_id` to `ops.triage_case_feedback`
   - keeps the raw `outcome_status` text column so unknown but accepted legacy strings can still be stored and round-tripped through MCP reads
   - backfills existing rows from legacy string values to normalized reference values
   - defines fallback behavior for missing / unmapped legacy cases by leaving `status_id` nullable for unknown-but-accepted strings while preserving the raw text value
   - updates constraints/indexes as needed
2. Add or update a legacy mapping layer so MCP-facing status strings still resolve correctly:
   - write path accepts the existing legacy string names and resolves recognized values to normalized reference values
   - write path continues accepting arbitrary non-empty legacy strings, stores them in raw `outcome_status`, and leaves `status_id` unset when no canonical mapping exists
   - read paths continue to expose stable legacy-facing `outcome_status` values unless the contract is intentionally changed
3. Update triage feedback writes to resolve status codes through `core.reference_values`.
4. Update triage reads and summary logic to use the normalized status model while preserving existing behavior:
   - derived `pending` for no-feedback cases
   - search filtering / exclusion behavior
   - search ranking adjustments
   - `outcome_confidence` behavior
   - summary-rate semantics
   - latest-feedback-row-wins semantics
5. Ensure the new triage outcome reference domain is discoverable through the existing MCP `list_reference_values` surface.
6. Expand the test harness to support `core.reference_types` / `core.reference_values` lookups so normalized-path tests exercise real status resolution behavior.
7. Add/adjust tests for:
   - the chosen compatibility policy for legacy / invalid / unknown status inputs
   - backward-compatible legacy input mapping
   - summary/search using normalized outcomes
   - reference-value discoverability through `list_reference_values`
   - direct `outcome_confidence` assertions
   - fake-pool reference lookups and normalized read/write paths

# Validation

- Run focused triage-memory tests plus the existing `list_reference_values` coverage in `tests/test_workflow_runs.py`.
- Confirm the chosen compatibility policy for invalid / unknown legacy status inputs.
- Confirm legacy status inputs are still accepted or mapped according to the compatibility contract.
- Confirm search and summary behavior still matches expected semantics.
- Confirm triage outcome reference values are discoverable through `list_reference_values`.
- Confirm `outcome_confidence` behavior is preserved explicitly.

# Affected Files

- `migrations/versions/*`
- `src/memory_knowledge/triage_memory.py`
- `src/memory_knowledge/server.py`
- `tests/test_triage_memory.py`
- `tests/test_workflow_runs.py`

--- Plan Verification Iteration 1 ---
Findings from verifier: 4
FIX NOW: 3 (plan updated)
IMPLEMENT LATER: 0 (plan updated)
ACKNOWLEDGE: 1 (no change)
DISMISS: 0 (no change)

--- Plan Verification Iteration 2 ---
Findings from verifier: 4
FIX NOW: 4 (plan updated)
IMPLEMENT LATER: 0 (plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

--- Plan Verification Iteration 3 ---
Findings from verifier: 3
FIX NOW: 2 (plan updated)
IMPLEMENT LATER: 0 (no change)
ACKNOWLEDGE: 1 (no change)
DISMISS: 0 (no change)
