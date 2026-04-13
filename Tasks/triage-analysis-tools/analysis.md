# Task Objective

Add higher-level triage analysis tools for confusion clusters and clarification recommendations.

# Current-State Findings

- Current triage-memory v1 provides:
  - save case
  - search cases
  - record feedback
  - feedback summary
- There is no dedicated higher-level tool to surface repeated confusion patterns across similar prompts as explicit clusters or ranked recommendations.
- There is no tool to surface prompts or patterns that frequently require clarification.
- Existing summary logic already exposes some ingredients:
  - derived corrected request kinds from latest feedback rows
  - clarification flags
  - prompt text
- The current persisted triage dataset already contains stable grouping fields that can support deterministic v1 analysis without a new subsystem:
  - `request_kind`
  - `execution_mode`
  - `knowledge_mode`
  - `selected_workflow_name`
  - `selected_run_action` for `run_operation` cases
  - `requires_clarification`
  - `confidence`
  - `project_key`
  - `feature_key`
  - `policy_version`
  - `workflow_catalog_version`
  - `decision_source`
  - `suggested_workflows`
  - `clarifying_questions`
  - `fallback_route`
  - `reasoning_summary`
  - `matched_case_ids`
  - latest effective `outcome_status` derived from the latest feedback row
  - latest `corrected_request_kind` derived from the latest feedback row
- Current read behavior is split across two surfaces:
  - `search_triage_cases` is a Qdrant-first candidate-oriented read surface that:
    - queries semantic candidates first when Qdrant is available
    - falls back to lexical SQL only when semantic retrieval is unavailable or errors
    - returns immediate empty `rows` when semantic retrieval succeeds but yields zero candidates
    - returns individual cases plus a retrieval summary
  - `get_triage_feedback_summary` is aggregate-oriented and already computes:
    - clarification rate
    - top misroutes
    - top problem prompts
- The current summary surface is repository/project/request-kind scoped only; it does not expose:
  - cluster/group identifiers
  - workflow-level clarification hotspots
  - reusable recommendation text or ranked recommendation objects
- Existing misroute aggregation is simple and explainable:
  - it counts `(request_kind, corrected_request_kind)` pairs from the latest feedback row
  - it does not use embeddings, semantic clustering, or fuzzy prompt grouping
- Existing clarification aggregation is also simple:
  - it counts `requires_clarification`
  - it does not group by prompt pattern, workflow, or request archetype
- Current search already produces deterministic ordering via explicit score adjustments and a stable sort key; new analysis tools should keep that deterministic bias rather than introducing opaque clustering/ML behavior.
- There is no current prompt-normalization helper for clustering:
  - no tokenization pipeline
  - no canonical pattern extraction
  - no vector-cluster storage for triage prompts
- no offline batch job that computes reusable triage clusters
- The inspected scope does contain a triage reprojection helper for Qdrant repair scenarios, and tests show it can restore historical searchability after reprojection, but there is still no dedicated MCP/admin triage reprojection or backfill tool in the inspected surface; v1 analysis should therefore operate directly from current PG fields and explainable heuristics rather than assuming an established higher-level triage analytics subsystem.

# Source Artifacts Inspected

- `src/memory_knowledge/triage_memory.py`
- `src/memory_knowledge/server.py`
- `tests/test_triage_memory.py`
- `docs/backlog.md`

# Constraints

- New tools should be deterministic and explainable.
- Empty-result behavior should mirror the observed current triage read contracts rather than a single generalized convention:
  - `search_triage_cases` returns stable empty `rows` plus retrieval summary specifically when Qdrant semantic retrieval succeeds but yields zero candidates
  - `get_triage_feedback_summary` returns zeroed aggregates and empty arrays on empty PG scope
- The tools should build on current triage-case and feedback data rather than requiring a new large subsystem unless analysis proves it necessary.
- V1 should avoid inventing an ML clustering pipeline where the codebase currently has only row-level case storage and simple aggregate summaries.
- New MCP tool outputs should follow the existing `WorkflowResult(..., status=\"success\", data=...)` shape and return stable empty arrays on zero-match cases.
- New higher-level analysis tools should remain read-oriented surfaces; existing triage reads are unguarded while triage writes are remote-write guarded.
- Any analysis grouped by workflow should be derived from base triage rows, not from `get_triage_feedback_summary` alone, because the current summary output is not workflow-bucketed.

# Risks And Edge Cases

- “Confusion cluster” is underspecified and could balloon into an ML project.
- Prompt grouping needs a practical, explainable v1 approach.
- Clarification recommendations should avoid vague prose-only outputs with no ranking basis.
- Over-indexing on raw prompt text can leak into unstable free-form grouping unless the v1 grouping key is intentionally narrow and explainable.
- If clustering tries to depend on Qdrant semantic neighbors, the tool behavior could become sensitive to missing embeddings and retrieval thresholds instead of staying deterministic.

# Recommended Approach

- Define a scoped v1:
  - confusion clusters based on repeated misroutes / corrected outcomes grouped by explainable route-pattern keys derived from existing structured fields
  - clarification recommendations based on high clarification-rate request/workflow/prompt-pattern combinations derived from persisted rows
- Implement explicit ranking and empty-result semantics.
- Keep the v1 grouping contract narrow enough to be implemented directly from current PG data and unit-tested deterministically.

--- Analysis Verification Iteration 1 ---
Findings from verifier: 7
FIX NOW: 6 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 1 (no change)
DISMISS: 0 (no change)

--- Analysis Verification Iteration 2 ---
Findings from verifier: 6
FIX NOW: 1 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 4 (no change)
DISMISS: 1 (no change)

--- Analysis Verification Iteration 3 ---
Findings from verifier: 3
FIX NOW: 2 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 1 (no change)
DISMISS: 0 (no change)

--- Analysis Verification Iteration 4 ---
Findings from verifier: 7
FIX NOW: 2 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 2 (no change)
DISMISS: 3 (no change)

--- Analysis Verification Iteration 5 ---
Findings from verifier: 5
FIX NOW: 0 (analysis unchanged)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis unchanged)
ACKNOWLEDGE: 5 (no change)
DISMISS: 0 (no change)
