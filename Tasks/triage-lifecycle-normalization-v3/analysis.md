# Objective

Prepare V3 work that hardens the triage lifecycle model so cases, outcomes, and post-decision state transitions are explicit, canonical, and easier to reason about operationally.

# Current-State Findings

- Triage case persistence exists, but the base triage case row is still primarily a captured decision snapshot plus append-only feedback history.
- Outcome normalization exists through `status_id`, but there is no richer lifecycle state machine for the triage decision itself.
- Feedback writes are append-only and useful, but the server does not distinguish concepts such as proposed, executed, validated, superseded, or rejected by human.
- Existing analytics infer effective status from the latest feedback row rather than from a first-class lifecycle model.
- The system currently mixes:
  - decision capture
  - outcome feedback
  - implied state derivation
  without an explicit lifecycle contract.

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
3. Reads derive current state from ad hoc latest-feedback logic.
4. There is no canonical notion of superseded or invalidated triage decisions.
5. Historic backfill semantics for richer lifecycle state are not defined.

# Constraints

- Existing tool contracts should be preserved where feasible or upgraded compatibly.
- Lifecycle changes should be additive and migration-safe.
- Historical rows will need backfill rules rather than manual rewrite assumptions.
- State transitions need canonical reference values instead of free-text expansion.

# Risks

- A badly designed lifecycle model can create redundant or contradictory state fields.
- Over-normalization can make integrator writes too heavy.
- If transition rules are underspecified, analytics and policy tools will disagree about “current truth.”
- Backfill rules may misclassify historic cases if not carefully defined.

# Recommended Approach

- Introduce explicit decision lifecycle state separate from outcome status.
- Use `core.reference_values` for any new lifecycle domains.
- Preserve append-only feedback, but make read models compute current state through clearer canonical rules.
- Define backfill behavior as part of the migration plan, not as an afterthought.
- Add explicit compatibility rules for legacy rows and existing tool callers.

# Proposed Deliverables

- new lifecycle reference domains
- additive columns or tables for triage decision state
- updated triage read-model helpers
- backfill and reconciliation logic for historic rows
- tests covering lifecycle transitions and historic compatibility

# Sequencing Notes

- This task should precede or run alongside policy synthesis because policy confidence depends on reliable state semantics.
- It should land before stronger automation or enforcement is attempted.
