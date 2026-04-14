# Objective

Prepare V3 work that hardens the triage lifecycle model so cases, outcomes, and post-decision state transitions are explicit, canonical, and easier to reason about operationally.

# Current-State Findings

- Triage case persistence exists in `ops.triage_cases`, but that row is still primarily a captured decision snapshot rather than a first-class lifecycle record.
- Outcome normalization exists in `ops.triage_case_feedback.status_id` through migration `011_triage_outcome_status_reference_values`, but that normalization covers feedback outcomes only, not a richer decision lifecycle state machine.
- Feedback writes are append-only and already capture some operational signals such as `successful_execution`, `human_override`, and correction fields, but there is still no canonical lifecycle layer for concepts such as proposed, executed, validated, superseded, or explicitly rejected.
- Current-state reads still derive effective truth from the latest feedback row. `search_triage_cases`, `_fetch_triage_analysis_rows`, and `get_triage_feedback_summary` each use a lateral join over `ops.triage_case_feedback` ordered by `created_utc DESC, id DESC` and map that latest row into an effective status.
- The system currently mixes decision capture, outcome feedback, and implied state derivation without a single explicit lifecycle contract that all read paths consume from a shared state model.
- The repo already includes descriptive triage analytics through `get_triage_feedback_summary`, `get_triage_confusion_clusters`, and `get_triage_clarification_recommendations`, but those tools still depend on latest-feedback interpretation rather than a canonical lifecycle projection.
- The repo already includes triage reprojection support for persisted cases via `reproject_triage_cases`, but that path repairs vector search projection state only and does not define lifecycle-state backfill semantics.

# Source Artifacts Inspected

- [src/memory_knowledge/triage_memory.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/triage_memory.py)
- [src/memory_knowledge/server.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/server.py)
- [migrations/versions/010_triage_memory.py](/Users/kamenkamenov/memory-knowledge/migrations/versions/010_triage_memory.py)
- [migrations/versions/011_triage_outcome_status_reference_values.py](/Users/kamenkamenov/memory-knowledge/migrations/versions/011_triage_outcome_status_reference_values.py)
- [tests/test_triage_memory.py](/Users/kamenkamenov/memory-knowledge/tests/test_triage_memory.py)

# Scope

## In Scope

- lifecycle-state modeling for triage decisions
- stronger normalization rules for decision state and outcome state
- migration planning for additive lifecycle support
- clearer read/write contracts for “current state” versus “feedback history”
- implications for analytics and policy generation

## Out Of Scope

- automatic policy synthesis
- adaptive ranking logic
- governance rollout mechanics

# Gaps To Close

1. No first-class triage lifecycle state machine exists.
2. Outcome state and decision state are not clearly separated.
3. Reads derive current state from repeated latest-feedback logic rather than a dedicated shared lifecycle projection.
4. There is no canonical notion of superseded or invalidated triage decisions.
5. Historic backfill semantics for richer lifecycle state are not defined.
6. Existing tests cover outcome normalization and analytics behavior, but not first-class lifecycle transitions because no dedicated lifecycle model exists yet.

# Constraints

- Existing tool contracts should be preserved where feasible or upgraded compatibly.
- Lifecycle changes should be additive and migration-safe.
- Historical rows will need backfill rules rather than manual rewrite assumptions.
- State transitions need canonical reference values instead of free-text expansion.
- Existing analytics and search tools already depend on outcome values such as `pending`, `confirmed_correct`, `execution_failed_after_route`, `insufficient_context`, `corrected`, and `overridden_by_human`, so lifecycle work has to preserve or compatibly reinterpret those semantics.

# Risks

- A badly designed lifecycle model can create redundant or contradictory state fields.
- Over-normalization can make integrator writes too heavy.
- If transition rules are underspecified, analytics and policy tools will disagree about “current truth.”
- Backfill rules may misclassify historic cases if not carefully defined.
- If lifecycle semantics are introduced in parallel with existing outcome feedback fields without a shared projection helper, the codebase will keep duplicating state derivation logic in search and analytics queries.

# Recommended Approach

- Introduce explicit decision lifecycle state separate from outcome status.
- Use `core.reference_values` for any new lifecycle domains.
- Preserve append-only feedback as historical evidence, but make read models compute current state through a clearer canonical projection helper or materialized lifecycle representation.
- Define backfill behavior as part of the migration plan, not as an afterthought.
- Add explicit compatibility rules for legacy rows and existing tool callers.

# Proposed Deliverables

- new lifecycle reference domains
- additive columns or tables for triage decision state
- updated triage read-model helpers so search and analytics do not each restate lifecycle CASE logic
- backfill and reconciliation logic for historic rows
- tests covering lifecycle transitions and historic compatibility

# Sequencing Notes

- This task should precede or run alongside policy synthesis because policy confidence depends on reliable state semantics.
- It should land before stronger automation or enforcement is attempted.

--- Analysis Verification Iteration 1 ---
Findings from verifier: 2
FIX NOW: 2 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)
