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
- Add canonical reference domains for decision lifecycle state.
- Keep decision lifecycle distinct from outcome status.
- Candidate states:
  - proposed
  - executed
  - validated
  - corrected
  - superseded
  - rejected_by_human

2. Design additive schema changes.
- Choose whether lifecycle state belongs directly on `ops.triage_cases` or in a dedicated state table.
- Preserve append-only feedback history in `ops.triage_case_feedback`.
- Add fields needed for explicit current-state derivation and timestamps.

3. Implement backfill rules.
- Map existing feedback-only history into the new lifecycle model.
- Document how historic rows without explicit validation or execution phases are interpreted.
- Make backfill deterministic and idempotent.

4. Update read-model helpers.
- Refactor triage current-state logic into a shared helper instead of duplicating CASE expressions in multiple queries.
- Ensure summary, search, and future policy tools all interpret current state consistently.

5. Decide whether tool contracts need additive updates.
- If write tools remain unchanged, lifecycle state may be inferred.
- If richer control is required, add optional fields without breaking current callers.

6. Add compatibility tests.
- historic case with no feedback
- case with normalized status feedback
- case with unknown legacy feedback text
- superseded case
- corrected case with follow-up validation

# Affected Files

- `migrations/versions/<new_lifecycle_revision>.py`
- `src/memory_knowledge/triage_memory.py`
- `src/memory_knowledge/server.py`
- `tests/test_triage_memory.py`
- optionally a new `tests/test_triage_lifecycle.py`

# Validation

- additive migration applies cleanly on top of current remote head
- current-state derivation is identical across search and summary paths for the same case
- historic rows backfill without data loss
- existing integrator calls still succeed
- canonical lifecycle reference values are seeded and queryable

# Dependencies And Sequencing

- should land before or together with policy synthesis
- should inform governance work because lifecycle states define what can be trusted
