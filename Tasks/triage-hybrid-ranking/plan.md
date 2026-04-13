# Scope

- Strengthen final ordering inside `search_triage_cases` while preserving the current MCP response contract and retrieval pipeline shape.
- Keep semantic candidate admission, lexical fallback behavior, and zero-semantic-hit early-empty behavior intact.
- Limit the change surface to ranking computation, deterministic ordering, focused tests, and tracking docs.

# Ranking Contract

- Continue returning the existing `search_triage_cases` payload:
  - `advisory_only`
  - `retrieval_summary`
  - `rows`
  - `warnings`
- Keep Qdrant as candidate retrieval only.
- Keep lexical fallback only when semantic retrieval is unavailable or errors.
- Keep zero semantic hits with functioning Qdrant as an immediate empty result rather than a lexical retry.

# Implementation Steps

1. Define an explicit weighted hybrid score formula in `src/memory_knowledge/triage_memory.py`.
   - Start from the existing semantic score or lexical fallback baseline.
   - Add documented weighted components for:
     - a preserved but explicit same-project preference derived from the current live project boost
     - calibrated outcome-quality weighting using normalized effective outcome status / outcome confidence
     - clarification adjustment
     - bounded recency weighting
   - Treat repository/feature/policy dimensions primarily as retrieval-scope filters under the current API, not as general soft-ranking signals among already admitted rows.
   - Keep weights explicit, small enough to avoid overwhelming the baseline, and easy to reason about in tests.

2. Separate score computation from final tie-break ordering.
   - Introduce a helper for hybrid score calculation.
   - Introduce a complete deterministic sort key that resolves ties after the weighted score.
   - Preserve stable ordering in both semantic and lexical-fallback paths.

3. Keep the ranking scope aligned with the current retrieval architecture.
   - Apply the new score only to rows already admitted to PostgreSQL hydration.
   - Do not change `_qdrant_filter(...)`, candidate count strategy, or the zero-semantic-hit early return in this task.
   - Do not broaden the task into fixing `selected_run_action` candidate-admission gaps unless directly required by the verified plan.

4. Update row output only if needed for explainability without changing the external envelope shape.
   - Preserve existing row fields unless a lightweight additional score-detail field is clearly justified and consistent with current tests.
   - Keep `similarity_score` as the externally returned ranking score field, but define explicitly whether it now represents hybrid relevance rather than near-raw semantic similarity.
   - Preserve or intentionally redefine `retrieval_summary.consensus_strength` in lockstep with the chosen `similarity_score` semantics so the summary contract stays coherent.
   - If score-detail output is added, keep it deterministic and derived only from the explicit weighted components.

5. Expand focused search-ranking coverage in `tests/test_triage_memory.py`.
   - Add representative semantic-ranking tests proving:
     - corrected / overridden outcomes are penalized consistently
     - clarification-heavy rows are adjusted according to the chosen weighting
     - recency weighting affects otherwise similar rows without overwhelming clearly better matches
     - ranking scenarios stay grounded in rows that can actually co-exist under the current filter semantics
   - Add lexical-fallback ordering tests proving deterministic results when semantic retrieval is unavailable.
   - Add tie-break tests that pin deterministic ordering for equal or near-equal weighted scores.
   - Add a dedicated test for `retrieval_summary.consensus_strength` so the summary stays coherent with the chosen `similarity_score` semantics.
   - Preserve and rerun the existing tests for advisory shape, zero semantic hits, and widened `max_age_days` retrieval.

6. Update tracking docs after implementation.
   - Mark backlog item `#19` resolved with the delivered ranking behavior.
   - Update `docs/roadmap.md` to remove hybrid ranking from the remaining Triage Memory follow-up list once the implementation is complete.

# Affected Files

- `src/memory_knowledge/triage_memory.py`
- `tests/test_triage_memory.py`
- `docs/backlog.md`
- `docs/roadmap.md`
- `Tasks/triage-hybrid-ranking/analysis.md`
- `Tasks/triage-hybrid-ranking/plan.md`

# Validation

- Run focused triage test coverage with `uv run pytest -q tests/test_triage_memory.py`.
- Confirm existing `search_triage_cases` contract tests still pass unchanged.
- Confirm newly added ranking tests prove the intended ordering tradeoffs.
- Confirm the chosen `similarity_score` meaning and `retrieval_summary.consensus_strength` behavior are covered by tests and remain internally consistent.
- Confirm no changes were introduced to:
  - zero-semantic-hit empty-result behavior
  - lexical-fallback activation rules
  - Qdrant filter shape
  - MCP wrapper signature for `search_triage_cases`

--- Plan Verification Iteration 1 ---
Findings from verifier: 7
FIX NOW: 3 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 2 (no change)
DISMISS: 2 (no change)

--- Plan Verification Iteration 2 ---
Findings from verifier: 2
FIX NOW: 2 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

--- Plan Verification Iteration 3 ---
Findings from verifier: 2
FIX NOW: 2 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)
