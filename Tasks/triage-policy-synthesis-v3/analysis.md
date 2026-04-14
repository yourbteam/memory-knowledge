# Objective

Prepare V3 work that upgrades triage memory from case retrieval plus analytics into policy synthesis that can recommend routing behavior from prior evidence and measured outcomes.

# Current-State Findings

- The server already persists triage cases and feedback in PostgreSQL via `ops.triage_cases` and `ops.triage_case_feedback`.
- Triage outcomes are normalized through `core.reference_values` with migration `011_triage_outcome_status_reference_values`.
- Canonical decision lifecycle semantics are now also present through migration `012_triage_decision_lifecycle_state`, which adds `ops.triage_cases.lifecycle_state_id`, `lifecycle_updated_utc`, and `superseded_by_case_id`, seeds `TRIAGE_DECISION_LIFECYCLE_STATE`, and backfills historic cases.
- Similar-case retrieval is available through `search_triage_cases` in [src/memory_knowledge/triage_memory.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/triage_memory.py).
- Operational triage analytics already exist:
  - `get_triage_feedback_summary`
  - `get_triage_confusion_clusters`
  - `get_triage_clarification_recommendations`
- The current triage read/write surface already uses lifecycle projection semantics:
  - `save_triage_case` initializes lifecycle state
  - `record_triage_case_feedback` updates lifecycle state from feedback
  - `search_triage_cases` projects `lifecycle_state`
- Planning and workflow telemetry now exist in the same server surface, so synthesized routing guidance can eventually be grounded to repo, project, task, phase, validator, and finding context.
- There is no current server-side concept of a synthesized routing policy artifact, recommended clarification policy, or repo-specific decision profile.
- Current triage analytics are descriptive only. They return counts, clusters, and recommendations, but they do not produce durable policy objects that an integrator can consume directly.
- Existing triage tests now cover not only persistence, normalization, retrieval, and descriptive analytics, but also lifecycle-backed read/write behavior for save, feedback, and read-side projection.

# Source Artifacts Inspected

- [docs/roadmap.md](/Users/kamenkamenov/memory-knowledge/docs/roadmap.md)
- [src/memory_knowledge/triage_memory.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/triage_memory.py)
- [src/memory_knowledge/server.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/server.py)
- [migrations/versions/010_triage_memory.py](/Users/kamenkamenov/memory-knowledge/migrations/versions/010_triage_memory.py)
- [migrations/versions/011_triage_outcome_status_reference_values.py](/Users/kamenkamenov/memory-knowledge/migrations/versions/011_triage_outcome_status_reference_values.py)
- [migrations/versions/012_triage_decision_lifecycle_state.py](/Users/kamenkamenov/memory-knowledge/migrations/versions/012_triage_decision_lifecycle_state.py)
- [tests/test_triage_memory.py](/Users/kamenkamenov/memory-knowledge/tests/test_triage_memory.py)

# Scope

## In Scope

- Defining how synthesized triage and clarification policies should be represented and stored
- Defining the MCP tools needed to read policy outputs
- Connecting triage analytics inputs to policy generation
- Repo-scoped and project-scoped policy support
- Acceptance criteria for “policy synthesis works and is trustworthy enough to consume”

## Out Of Scope

- Replacing the underlying triage case persistence model
- Integrator changes in external repos
- Fully automatic policy application without trust controls
- General ML training systems outside the existing memory-knowledge architecture

# Gaps To Close

1. There is no canonical policy artifact model.
2. There is no distinction between descriptive analytics and recommended behavior.
3. There is no durable store for synthesized routing or clarification policies.
4. There is no composed tool that lets an integrator ask for current routing guidance rather than raw history.
5. There is no quality threshold model for when a policy is safe to expose.

# Constraints

- V3 must stay consistent with the existing MCP server pattern: `server.py` remains thin and task logic lives in dedicated modules.
- Policy synthesis must be explainable. The system cannot silently invent recommendations that cannot be traced back to observed cases and outcomes.
- Policy outputs must be reversible and versioned, because they will eventually influence routing behavior.
- Repo-level differences matter. Policies cannot assume all repositories behave the same.
- Any synthesized recommendation must be advisory until governance controls are in place.

# Risks

- If policy synthesis is built too early on sparse or noisy data, it will overfit and degrade routing quality.
- If policy storage is not versioned, future adjustments will be hard to reason about or roll back.
- If recommendations are not explicitly tied to evidence thresholds, integrators may over-trust weak guidance.
- If repo/project scoping is not built in from the start, policy outputs will be too coarse to be useful.

# Recommended Approach

- Introduce explicit policy artifacts rather than overloading current analytics responses.
- Start with read-side synthesis tools before any automatic enforcement.
- Make policy generation deterministic and traceable from observed triage cases, feedback, and workflow outcomes.
- Use confidence thresholds, minimum sample counts, and evidence summaries in all synthesized outputs.
- Support repo-scoped policy first, then allow project-scoped overrides where enough signal exists.

# Proposed Deliverables

- Policy storage schema for synthesized routing and clarification guidance
- Synthesis module under `src/memory_knowledge/`
- MCP read tools such as:
  - `get_routing_policy_recommendations`
  - `get_clarification_policy`
  - `list_triage_behavior_profiles`
- Test coverage for sparse-signal rejection, deterministic ordering, and evidence traceability

# Sequencing Notes

- This task now depends on the lifecycle-normalization stream that has already established canonical decision-state semantics in the repo.
- It depends on the existing triage analytics surface and should consume the current lifecycle projection rather than re-deriving policy evidence from latest-feedback logic.
- Governance work should refine the trust and rollout rules after the first synthesis model is defined.

--- Analysis Verification Iteration 1 ---
Findings from verifier: 4
FIX NOW: 4 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)
