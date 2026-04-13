# Objective

Prepare V3 work that adds trust controls and higher-level composed tools so integrators can consume V3 intelligence safely and with less manual orchestration.

# Current-State Findings

- The current server exposes granular write and read tools for triage, planning, workflow telemetry, and analytics.
- Integrators currently need to orchestrate multiple calls manually:
  - search before deciding
  - save after deciding
  - feedback after outcome
  - analytics during correction loops
- There is no server-side concept of policy rollout stages, trust thresholds, or recommendation governance.
- There is no high-level composed helper that returns a memory-aware triage recommendation with evidence and safety metadata in one call.
- There is no drift or rollback model for future adaptive policy artifacts.

# Source Artifacts Inspected

- [src/memory_knowledge/server.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/server.py)
- [src/memory_knowledge/triage_memory.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/triage_memory.py)
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
2. There is no clear trust model for when synthesized recommendations are safe to use.
3. There is no policy rollout stage such as draft, advisory, or trusted.
4. There is no policy rollback or suppression concept.
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

- Add governance metadata to future synthesized policy artifacts.
- Expose high-level tools that compose existing lower-level calls but preserve transparency.
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

- This task should follow policy synthesis enough to have real policy artifacts to govern.
- It can define its governance schema early so policy synthesis work stores the right metadata from the start, but composed tool implementation should come after the first policy artifacts exist.
