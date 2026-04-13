# Objective

Define and implement V3 triage policy synthesis so integrators can query recommended routing and clarification behavior derived from measured triage history.

# Scope

## In Scope

- policy artifact schema and storage
- policy synthesis service/module
- MCP read tools for routing and clarification policy outputs
- deterministic repo-scoped and project-scoped policy generation
- evidence thresholds and policy confidence metadata

## Out Of Scope

- automatic enforcement of synthesized policy
- changes in external workflow producers or integrators
- ranking changes inside `search_triage_cases` beyond what is needed to support policy evidence

# Implementation Steps

1. Define the policy artifact model.
- Add a new migration for synthesized policy artifacts and versions.
- Model at least:
  - routing policy recommendations
  - clarification policy recommendations
  - behavior profile metadata
- Include scope fields such as `repository_key`, optional `project_key`, policy kind, version, confidence, case count, and evidence summary.

2. Add a dedicated synthesis module.
- Create a module such as `src/memory_knowledge/triage_policy.py`.
- Implement deterministic aggregation over existing triage case and feedback data.
- Generate recommendations only when minimum evidence thresholds are satisfied.

3. Define synthesized recommendation rules.
- Routing recommendations should consider:
  - dominant successful request kind
  - dominant successful workflow
  - correction frequency
  - clarification frequency
  - minimum sample count
- Clarification recommendations should identify patterns where clarification materially improved outcomes or prevented repeated correction.

4. Add MCP read tools in `server.py`.
- Register tools for synthesized outputs.
- Keep request contracts scope-first:
  - repo required
  - project optional
  - limits and confidence thresholds optional
- Keep responses explicit about advisory status and evidence quality.

5. Add evidence traceability.
- Every recommendation should return:
  - confidence
  - supporting case count
  - recent outcome mix
  - representative prompt snippets or pattern summaries
  - reasons a recommendation was included or excluded

6. Add sparse-signal safeguards.
- Return empty recommendations when evidence thresholds are not met.
- Reject scope combinations that do not exist or do not have enough cases.
- Ensure deterministic ordering across ties.

7. Document the integrator contract.
- Extend the integration docs only after tool contracts stabilize.
- Explain that policy outputs are advisory, versioned, and evidence-backed.

# Affected Files

- `migrations/versions/<new_policy_synthesis_revision>.py`
- `src/memory_knowledge/triage_policy.py`
- `src/memory_knowledge/server.py`
- `tests/test_triage_policy.py`
- optionally `docs/AGENT_INTEGRATION_SPEC.md`

# Validation

- migration applies cleanly after `011_triage_outcome_status_reference_values`
- synthesized tools return empty arrays on sparse-signal scopes
- deterministic ordering is stable under repeated execution
- recommendations include confidence and evidence metadata
- repo-scoped and project-scoped synthesis both work where data exists

# Dependencies And Sequencing

- depends on the current triage persistence and analytics surface already shipped
- should follow the lifecycle-normalization work enough to use canonical current-state semantics
- should be completed before governance-enforcement work
- can proceed in parallel with adaptive-ranking work if schema ownership is coordinated
