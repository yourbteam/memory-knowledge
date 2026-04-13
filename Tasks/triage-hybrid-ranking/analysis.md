# Task Objective

Strengthen `search_triage_cases` with a more explicit and testable hybrid ranking model while preserving the current MCP response contract.

# Current-State Findings

- `search_triage_cases` remains the only triage retrieval tool that ranks individual similar cases rather than returning aggregates.
- The search flow is still split into two phases:
  - semantic candidate retrieval from Qdrant when available
  - PostgreSQL row hydration and final ordering in `_fetch_search_rows(...)`
- The shipped ranking baseline is the Qdrant candidate score when semantic retrieval succeeds, or a fixed lexical fallback baseline of `0.65` when semantic retrieval is unavailable.
- The shipped hybrid score now applies explicit weighted components for:
  - same-project preference
  - normalized outcome-confidence weighting
  - clarification penalty
  - bounded recency weighting
- The shipped deterministic tie-break chain now orders by:
  - hybrid `similarity_score`
  - `outcome_confidence`
  - non-clarification preference
  - presence of `created_utc`
  - `created_utc`
  - `repository_key`
  - `triage_case_id`
- Repository/feature/policy dimensions remain retrieval-scope filters under the current API rather than soft weighted signals among admitted rows.
- `prefer_same_repository` is still accepted by the MCP wrapper for compatibility, but disabling it now emits an explicit warning instead of silently implying a ranking effect.
- Several alignment dimensions are already enforced upstream as retrieval filters rather than being absent from the overall retrieval path:
  - Qdrant candidate retrieval filters by `repository_key`, `project_key`, `feature_key`, `request_kind`, `selected_workflow_name`, and `policy_version`
  - PostgreSQL hydration also hard-filters by those fields plus `execution_mode` and `selected_run_action`
  - the gap is therefore in weighted final ordering, not in basic retrieval scoping
- The current final ranking is computed only after PostgreSQL hydration, which means richer row-level signals are already available at ranking time:
  - `execution_mode`
  - `knowledge_mode`
  - `selected_workflow_name`
  - `selected_run_action`
  - `requires_clarification`
  - `confidence`
  - `project_key`
  - `feature_key`
  - `policy_version`
  - latest effective `outcome_status`
  - derived `outcome_confidence`
- Outcome semantics used by ranking are already normalized through the current read path:
  - reads prefer `status_id` / `core.reference_values` mapping when present
  - reads fall back to normalized raw `outcome_status` text only when needed
- Existing focused tests now validate:
  - advisory result shape
  - zero-semantic-hit no-lexical-fallback behavior
  - semantic-path hybrid ranking behavior
  - lexical-path outcome, clarification, recency, and deterministic ordering behavior
  - `retrieval_summary.consensus_strength` coherence with ranked row scores
  - widened `max_age_days` retrieval after reprojection
- Explicit policy-version weighting was not added:
  - under the current API, `policy_version` remains a retrieval-scope filter rather than a soft ranking component
- The current response contract should be preserved:
  - `search_triage_cases` returns `WorkflowResult(..., status="success", data=...)`
  - `data` still contains `advisory_only`, `retrieval_summary`, `rows`, and `warnings`
  - zero semantic hits with available Qdrant still return immediate empty rows without lexical fallback
- Hybrid ranking scope is limited to admitted candidates:
  - when Qdrant is available and returns zero candidates, the function exits before PostgreSQL hydration and final ranking
  - stronger weighting can therefore improve ordering among admitted candidates, but not the zero-semantic-hit path

# Source Artifacts Inspected

- `src/memory_knowledge/triage_memory.py`
- `src/memory_knowledge/server.py`
- `tests/test_triage_memory.py`
- `docs/backlog.md`
- `docs/roadmap.md`

# Constraints

- The ranking upgrade must preserve the external `search_triage_cases` tool contract.
- Ranking behavior must remain explainable and deterministic.
- The task should strengthen final ordering, not redesign the retrieval pipeline.
- Qdrant remains candidate retrieval only; this task should not add a clustering or offline indexing subsystem.
- Zero semantic hits with functioning Qdrant should keep the current early-empty behavior rather than silently switching to lexical fallback.

# Risks And Edge Cases

- More ranking signals can make the model harder to reason about unless weights are explicit and stable.
- Overweighting recency can bury older but higher-quality cases, especially after historic reprojection recovery.
- Policy-version preference can become too strong if it overwhelms clear semantic or outcome-quality differences.
- Clarification-heavy cases are ambiguous signals:
  - they may indicate poor routing quality
  - or they may indicate healthy escalation behavior for inherently underspecified prompts
- Lexical fallback rows all start from the same baseline score, so the hybrid model must still produce stable and sensible ordering in the no-semantic path.

# Recommended Approach

- Completed:
  - replaced the old shallow nudges with an explicit weighted hybrid score over hydrated PostgreSQL rows
  - preserved deterministic ordering with a complete tie-break chain after the weighted score
  - added focused tests for semantic and lexical ranking paths plus summary coherence

--- Analysis Verification Iteration 1 ---
Findings from verifier: 4
FIX NOW: 2 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 1 (no change)
DISMISS: 1 (no change)

--- Analysis Verification Iteration 2 ---
Findings from verifier: 3
FIX NOW: 0 (analysis unchanged)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis unchanged)
ACKNOWLEDGE: 1 (no change)
DISMISS: 2 (no change)

--- Analysis Verification Iteration 3 ---
Findings from verifier: 2
FIX NOW: 1 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 1 (no change)
