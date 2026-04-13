# Scope

- Add two new read-only triage analysis MCP tools:
  - `get_triage_confusion_clusters`
  - `get_triage_clarification_recommendations`
- Keep v1 deterministic and explainable by deriving results from current PostgreSQL triage-case and triage-feedback data.
- Do not introduce opaque embedding-based clustering, offline jobs, or new persistence for this task.

# Contracts

- `get_triage_confusion_clusters` should expose repeated confusing/misrouted patterns as ranked cluster rows derived from existing structured fields and latest-feedback outcomes.
- `get_triage_clarification_recommendations` should expose ranked clarification hotspots and recommendation rows derived from current triage cases and feedback history.
- Both tools should return `WorkflowResult(..., status="success", data=...)` envelopes with stable empty arrays on zero-match scopes.
- Both tools should remain read-only and therefore unguarded, matching the current triage read surface.
- `get_triage_confusion_clusters` should return a stable `data` object with filter metadata, aggregate counts, and `clusters: []` on empty scopes.
- `get_triage_clarification_recommendations` should return a stable `data` object with filter metadata, aggregate counts, and `recommendations: []` on empty scopes.

# Implementation Steps

1. Define narrow v1 row schemas and ranking rules.
   - Use repository/project/request-kind scope as first-class filters.
   - Include a time-window filter consistent with current triage reads.
   - Keep ordering deterministic with explicit sort keys and documented tie-breakers.
   - Treat `selected_run_action` as a conditional dimension for `run_operation` cases rather than a universal grouping key.

2. Implement PostgreSQL-backed aggregation helpers in `src/memory_knowledge/triage_memory.py`.
   - Add one helper for confusion-cluster aggregation using latest effective outcome data from triage feedback.
   - Add one helper for clarification-recommendation aggregation using persisted triage-case fields such as workflow, request kind, clarification flags, and optional prompt-pattern heuristics.
   - Compute outcome semantics from the current read path rules, including the latest-feedback join and normalized status resolution already used by triage reads.
   - Keep grouping logic explainable and row-based rather than semantic-cluster-based.

3. Define stable v1 grouping and recommendation heuristics.
   - For confusion clusters, group by explainable structured dimensions such as request kind, selected workflow, corrected request kind, and conditional selected run action where present.
   - For clarification recommendations, rank by clarification rate and supporting counts, then derive short recommendation labels from the grouped dimensions rather than free-form generation.
   - Prefer PostgreSQL-backed fields over Qdrant payload assumptions; use the richer row model already available to current read helpers.

4. Add MCP wrappers in `src/memory_knowledge/server.py`.
   - Validate required inputs consistently with existing triage tools.
   - Return stable success envelopes for empty and non-empty scopes.
   - Keep tool names, parameter naming, and correlation/run-context handling aligned with the existing triage MCP surface.

5. Add focused tests under `tests/test_triage_memory.py`.
   - Cover non-empty confusion-cluster results.
   - Cover non-empty clarification-recommendation results.
   - Cover empty-scope behavior for both tools.
   - Cover deterministic ordering and tie-break behavior.
   - Cover scope filters, including time-window handling and conditional `selected_run_action` behavior where relevant.
   - Cover wrapper-level validation/error responses for required or invalid inputs introduced by the new MCP tools.

6. Update task/backlog documentation after implementation.
   - Mark backlog item `#17` resolved with the actual delivered tool names and behavior.
   - Update `docs/roadmap.md` to move the delivered confusion-cluster and clarification-recommendation tooling out of the remaining triage follow-up list.

# Affected Files

- `src/memory_knowledge/triage_memory.py`
- `src/memory_knowledge/server.py`
- `tests/test_triage_memory.py`
- `docs/backlog.md`
- `docs/roadmap.md`

# Validation

- Run focused triage test coverage with `uv run pytest -q tests/test_triage_memory.py`.
- Confirm both new tools return stable JSON envelopes with `status="success"` on zero-match scopes.
- Confirm deterministic ordering from repeated test execution and explicit tie-break assertions.
- Confirm the implementation stays within the scoped v1 design:
  - no new tables or migrations
  - no new Qdrant clustering dependency
  - no write-surface changes to existing triage tools

--- Plan Verification Iteration 1 ---
Findings from verifier: 6
FIX NOW: 3 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 2 (no change)
DISMISS: 1 (no change)

--- Plan Verification Iteration 2 ---
Findings from verifier: 1
FIX NOW: 1 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)
