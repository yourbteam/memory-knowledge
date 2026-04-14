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
- Extend the live `ops.triage_policy_artifacts` baseline with fields for:
  - rollout stage
  - confidence threshold
  - minimum evidence threshold
  - drift state
  - last reviewed timestamp
  - suppression or disablement marker

2. Add governance storage and read helpers.
- Extend the existing persisted policy-artifact model in `ops.triage_policy_artifacts` or add a tightly related governance table keyed to persisted artifacts.
- Support explicit versioning and reversible stage changes.

3. Define composed tool contracts.
- `triage_request_with_memory`
  - takes the current prompt and scope
  - composes the current lower-level surfaces:
    - `search_triage_cases`
    - `get_routing_policy_recommendations`
    - `get_clarification_policy`
    - `list_triage_behavior_profiles`
  - returns recommended request kind, workflow guidance, clarification advice, and evidence quality metadata
- `finalize_triage_outcome`
  - wraps `record_triage_case_feedback`
  - optionally refreshes persisted policy artifacts for the affected scope
  - returns updated policy/analytics/governance implications after the write
- `get_behavior_policy_status`
  - returns policy stage, confidence, drift state, and suppression information for a scope

4. Keep evidence visible.
- Composed tools must return:
  - advisory status
  - recommendation confidence
  - minimum evidence thresholds used
  - reasons no recommendation was made
  - `ranking_features` or equivalent transparent score components when search evidence contributes to the result
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
- governance metadata is stored and returned on persisted policy artifacts, not only computed in memory
- persisted-artifact refresh plus governance state transitions are test-covered end to end

# Dependencies And Sequencing

- extends the live `013_triage_policy_artifacts` policy baseline
- should land after the current synthesized-policy implementation already in repo
- should be in place before any integrator treats policy outputs as default decision guidance

--- Plan Verification Iteration 1 ---
Findings from verifier: 6
FIX NOW: 6 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)
