# Objective

Add V3 governance controls and composed tools so integrators can consume adaptive routing intelligence with less orchestration and with explicit safety boundaries.

# Scope

## In Scope

- policy governance metadata and rollout stages
- composed memory-aware triage tools
- rollback and suppression semantics
- drift and low-signal behavior

## Out Of Scope

- low-level triage persistence redesign
- detailed ranking implementation
- external-client adoption work

# Implementation Steps

1. Define governance metadata.
- Add fields for:
  - rollout stage
  - confidence threshold
  - minimum evidence threshold
  - drift state
  - last reviewed timestamp
  - suppression or disablement marker

2. Add governance storage and read helpers.
- Extend the future policy artifact model or add a related governance table.
- Support explicit versioning and reversible stage changes.

3. Define composed tool contracts.
- `triage_request_with_memory`
  - takes the current prompt and scope
  - returns recommended request kind, workflow guidance, clarification advice, and evidence quality metadata
- `finalize_triage_outcome`
  - composed write helper that records outcome feedback and returns updated policy/analytics implications
- `get_behavior_policy_status`
  - returns policy stage, confidence, drift state, and suppression information for a scope

4. Keep evidence visible.
- Composed tools must return:
  - advisory status
  - recommendation confidence
  - minimum evidence thresholds used
  - reasons no recommendation was made
  - links or identifiers to supporting policy or cases where applicable

5. Add drift and downgrade rules.
- If evidence quality drops or drift is detected, composed tools should downgrade from trusted to advisory or to no recommendation.
- Define deterministic fallback behavior for low-signal scopes.

6. Add operator controls.
- Support policy disablement or suppression without deleting history.
- Make policy stage transitions auditable.

7. Add tests and docs.
- stage-aware recommendation visibility
- low-signal no-op behavior
- drift-triggered downgrade behavior
- rollback/suppression behavior

# Affected Files

- `migrations/versions/<new_governance_revision>.py`
- `src/memory_knowledge/server.py`
- `src/memory_knowledge/triage_policy.py` or a new governance module
- `tests/test_triage_policy.py`
- `docs/AGENT_INTEGRATION_SPEC.md`

# Validation

- composed tools preserve MCP envelope and provide transparent evidence metadata
- advisory versus trusted behavior is explicit and test-covered
- suppression and rollback work without deleting historical policy artifacts
- low-signal scopes return safe no-recommendation responses

# Dependencies And Sequencing

- depends on policy synthesis artifact design
- should land after or together with the first synthesized-policy implementation
- should be in place before any integrator treats policy outputs as default decision guidance
