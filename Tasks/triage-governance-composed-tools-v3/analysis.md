# Objective

Prepare V3 work that adds trust controls and higher-level composed tools so integrators can consume V3 intelligence safely and with less manual orchestration.

# Current-State Findings

- The current server exposes granular write and read tools for triage, planning, workflow telemetry, and analytics.
- The server now also exposes policy-synthesis and policy-refresh surfaces:
  - `get_routing_policy_recommendations`
  - `get_clarification_policy`
  - `list_triage_behavior_profiles`
  - `refresh_triage_policy_artifacts`
- Integrators currently need to orchestrate multiple calls manually:
  - search before deciding
  - save after deciding
  - feedback after outcome
  - analytics during correction loops
- Policy artifacts now exist through `ops.triage_policy_artifacts` and explicit refresh logic, but there is still no server-side concept of policy rollout stages, trust thresholds, drift state, review state, or recommendation governance.
- There is no high-level composed helper that returns a memory-aware triage recommendation with evidence and safety metadata in one call.
- `search_triage_cases` now exposes `ranking_features`, so governance/composed tools already have a transparent score-component baseline they can reuse instead of inventing separate opaque trust heuristics.
- There is still no drift or rollback model for adaptive policy artifacts.

# Source Artifacts Inspected

- [src/memory_knowledge/server.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/server.py)
- [src/memory_knowledge/triage_memory.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/triage_memory.py)
- [src/memory_knowledge/triage_policy.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/triage_policy.py)
- [migrations/versions/013_triage_policy_artifacts.py](/Users/kamenkamenov/memory-knowledge/migrations/versions/013_triage_policy_artifacts.py)
- [tests/test_triage_policy.py](/Users/kamenkamenov/memory-knowledge/tests/test_triage_policy.py)
- [docs/AGENT_INTEGRATION_SPEC.md](/Users/kamenkamenov/memory-knowledge/docs/AGENT_INTEGRATION_SPEC.md)
- [docs/roadmap.md](/Users/kamenkamenov/memory-knowledge/docs/roadmap.md)

# Scope

## In Scope

- governance model for synthesized recommendations
- high-level composed MCP tools for integrators
- trust thresholds, rollout stages, and reversal semantics
- drift and low-signal handling

## Out Of Scope

- low-level triage storage changes
- ranking internals
- external orchestrator implementation work

# Gaps To Close

1. Integrators still need to manually stitch together multiple tools for one decision loop.
2. There is no clear trust model for when existing synthesized recommendations are safe to use.
3. There is no policy rollout stage such as draft, advisory, or trusted on top of the current artifact model.
4. There is no policy rollback or suppression concept on persisted policy artifacts.
5. There is no drift-monitoring mechanism for adaptive guidance.

# Constraints

- Composed tools must not hide critical evidence or uncertainty.
- Governance controls must be explicit in data, not implicit in code comments.
- Recommendation trust cannot depend on hidden heuristics.
- Composed tools must remain compatible with the existing MCP response envelope.

# Risks

- A high-level helper can over-abstract important uncertainty if not carefully designed.
- Governance that is too weak will create over-trust; governance that is too heavy will make the feature unusable.
- If rollout stages are not modeled explicitly, operators will have no safe way to adopt adaptive behavior gradually.

# Recommended Approach

- Add governance metadata to the existing synthesized policy artifact model rather than creating a second parallel artifact surface.
- Expose high-level tools that compose existing lower-level calls but preserve transparency.
- Reuse current ranking diagnostics and persisted policy artifacts as evidence inputs for composed-tool responses.
- Keep the first governance model simple:
  - draft
  - advisory
  - trusted
  - disabled
- Make rollback a first-class operation on policy artifacts rather than an undocumented manual process.

# Proposed Deliverables

- governance schema for policy stage, confidence threshold, drift state, and suppression
- composed MCP tools such as:
  - `triage_request_with_memory`
  - `finalize_triage_outcome`
  - `get_behavior_policy_status`
- documentation for integrator expectations and safety interpretation
- tests for low-signal downgrade and stage-aware responses

# Sequencing Notes

- This task now extends a live policy-artifact baseline rather than waiting for the first policy implementation to exist.
- Composed tool implementation can build directly on the current policy, ranking, and feedback surfaces.

--- Analysis Verification Iteration 1 ---
Findings from verifier: 5
FIX NOW: 5 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)
