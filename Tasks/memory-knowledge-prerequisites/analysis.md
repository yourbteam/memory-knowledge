# Memory-Knowledge Prerequisites Analysis

## Objective

Implement the memory-knowledge changes required by `/Users/kamenkamenov/mcp-agents-workflow/Tasks/verifier-critic-upgrades-requirements/memory-knowledge-prerequisites.md` so workflow-orch can:

- persist verifier/reviewer findings
- persist critic decisions about those findings
- query same-run suppressions for later verifier rounds
- query aggregated finding patterns for later analytics and learning

This task is repo-scoped to `memory-knowledge`. It does not include prompt changes or workflow-orch-side producer adoption beyond documenting the integration contract.

## Source Artifacts Inspected

- `/Users/kamenkamenov/mcp-agents-workflow/Tasks/verifier-critic-upgrades-requirements/memory-knowledge-prerequisites.md`
- [server.py](../../src/memory_knowledge/server.py)
- [analytics.py](../../src/memory_knowledge/admin/analytics.py)
- [008_analytics_schema.py](../../migrations/versions/008_analytics_schema.py)
- [AGENT_INTEGRATION_SPEC.md](../../docs/AGENT_INTEGRATION_SPEC.md)
- [LLM_INTEGRATION_GUIDE.md](../../docs/LLM_INTEGRATION_GUIDE.md)

## Current-State Findings

### Existing workflow telemetry is strong at the run/phase/validator layer

The repo already has canonical storage and MCP write/read tools for:

- workflow runs
- workflow artifacts
- workflow phase states
- workflow validator results
- run recovery by actor email
- analytics over run/phase/validator/artifact facts

This is visible in:

- [server.py](../../src/memory_knowledge/server.py): workflow write/read tools and 6 analytics tools
- [analytics.py](../../src/memory_knowledge/admin/analytics.py): run/phase/validator/artifact read models and summaries
- [008_analytics_schema.py](../../migrations/versions/008_analytics_schema.py): validator-result storage and supporting reference values

Important nuance:

- workflow run status is normalized through `core.reference_values`
- workflow validator-result status is normalized through `core.reference_values`
- workflow phase status is still validated as a raw string set in Python
- validator codes are still validated as a hard-coded Python allowlist

### There is currently no first-class persistence for findings or critic decisions

The repo has no finding-level storage model today:

- no workflow-finding table
- no critic-decision table
- no reference sets for finding kinds / decision buckets / suppression scopes
- no MCP tools for saving findings or decisions
- no suppression lookup query
- no finding-pattern analytics

Repository search over `src/`, `migrations/`, and `tests/` showed no existing implementation for those concepts.

### Current analytics are insufficient for the new use case

Current analytics summarize:

- actor/run performance
- phase quality
- validator failure patterns
- loop patterns
- quality grades
- entropy sweep targets

These summaries are actor-oriented and run-oriented. They do not provide first-class internal verifier/reviewer/critic agent identity. The closest current identity field is `actor_email` on workflow runs, and the repo already treats that as trigger-actor identity rather than subagent identity.

These operate on stored workflow telemetry and do not expose:

- hallucination vs. gap vs. false-positive finding kinds
- critic dismissal/acknowledgement buckets for findings
- suppression lookup by run/phase/artifact lineage
- repeated finding fingerprints and their decision history

So Tasks 3 and 4 from the external requirements cannot be satisfied with the current model.

## Requirements Interpreted for This Repo

### Minimum persistence needed

The external requirements document calls for two first-class record types:

1. workflow findings
2. workflow finding decisions

For this repo, the clean fit is:

- new tables in `ops`
- normalized reference values in `core.reference_types` / `core.reference_values`
- MCP write tools in [server.py](../../src/memory_knowledge/server.py)
- query helpers in a new admin module, likely adjacent to existing analytics helpers

But the required record shape is materially richer than “two tables plus a run link.” The external requirements explicitly call for additional fields such as:

- finding-side:
  - `agent_name`
  - `attempt_number`
  - `artifact_name`
  - `artifact_iteration`
  - `artifact_hash`
  - `finding_fingerprint`
  - `finding_title`
  - `finding_message`
  - `location`
  - `evidence_text`
  - `finding_kind`
  - `severity`
  - `source_kind`
  - `status`
- decision-side:
  - `critic_phase_id`
  - `critic_agent_name`
  - `decision_bucket`
  - `actionable`
  - `reason_text`
  - `evidence_text`
  - `suppression_scope`
  - `suppress_on_rerun`
  - `created_utc`

So the schema and tool surface here are a meaningfully larger addition than the existing validator-result model.

### Minimum MCP surface needed

Required v1 tool surface from the external requirements:

- `save_workflow_finding`
- `save_workflow_finding_decision`
- `list_workflow_finding_suppressions`
- `get_finding_pattern_summary`

Recommended v1 addition:

- `get_agent_failure_mode_summary`

### Required behavior constraints

Based on the external requirements, the implementation must support:

- deterministic dedupe/upsert of findings within the same run/phase/attempt/fingerprint
- decision history retention rather than “latest only”
- same-run suppression as the default v1 suppression boundary
- artifact-lineage-aware suppression filtering when artifact fields are provided
- aggregated analytics without forcing consumers to parse raw markdown artifacts

## Design Constraints

### Must fit the current workflow-tracking architecture

This repo already standardized on:

- `ops.workflow_runs` as the canonical run table
- `ops.workflow_phase_states` for phase telemetry
- `ops.workflow_validator_results` for validator telemetry
- `core.reference_values` for normalized workflow run status and validator-result status

The finding/decision model should follow that existing pattern rather than inventing a parallel persistence style.

But this layer is not fully normalized today:

- phase status remains string-valued
- validator codes remain code-defined
- actor identity exists, but agent identity does not

So the new finding/decision model should align with the current workflow-tracking architecture without assuming the existing telemetry model is already fully reference-backed.

### Must preserve repo scoping and current tool behavior

The new tools should:

- resolve `repository_key` against `catalog.repositories`
- link to `ops.workflow_runs` by `run_id`
- behave like existing MCP write tools:
  - standard `WorkflowResult`
  - remote write guard for writes
  - read-only analytics tools with no write guard

### Agent identity is a real new requirement

The external prerequisite document requires:

- `agent_name` on findings
- `critic_agent_name` on decisions
- finding analytics grouped by `agent_name`

Current memory-knowledge telemetry does not have a first-class agent identity field. Existing summaries that use the word “agent” are actually grouped by `actor_email`. This task should treat agent identity as a new data dimension that must be stored explicitly.

## Risks and Edge Cases

### Finding fingerprint semantics are external

This repo can store and query `finding_fingerprint`, but it does not own the fingerprint-generation algorithm. So:

- fingerprints must be treated as caller-supplied canonical identifiers
- empty or malformed fingerprints should be rejected
- cross-run or cross-artifact suppression logic should not assume more semantic stability than the caller provides

### Decision history vs. suppression lookup are different concerns

The requirements want both:

- full decision history retention
- suppression lookup for later verifier rounds

That means the decision table should be append-only, while suppression queries should select the relevant subset instead of overwriting decisions in place.

### Artifact-lineage matching needs a pragmatic v1 rule

The requirements mention:

- `artifact_name`
- `artifact_iteration`
- `artifact_hash`

V1 should not try to infer lineage from raw content. The likely practical rule is:

- same-run suppression is the grounded v1 baseline
- `phase_id` is clearly part of the query/input surface, but the exact matching rule should be finalized in the plan rather than asserted here as already settled
- if artifact filters are provided, only match decisions whose stored artifact lineage fields materially match those inputs

### Analytics must remain deterministic on zero-match cases

Existing analytics already return success with empty collections on zero-match filters. The new finding analytics should follow the same behavior.

### Existing analytics already expose coverage limits

The current analytics layer already publishes partial-history qualifiers such as:

- `historical_complete: false`
- `basis: post_adoption_only`
- eligible/excluded run counts

That does not change the core gap analysis, but it matters for the new design: finding-pattern analytics and decision-history summaries should be explicit about their own coverage semantics rather than implying complete historical reconstruction.

## Scope Boundaries

Included:

- schema changes in this repo
- MCP write/read/query tools in this repo
- tests in this repo
- integration documentation updates in this repo

Excluded:

- workflow-orch prompt changes
- verifier/critic producer changes in workflow-orch
- retroactive extraction of historical findings from old raw artifacts
- automatic persona tuning or validator generation

## Recommended Approach

The clean repo-local approach is:

1. Add new reference types and values for:
   - finding kinds
   - finding decision buckets
   - suppression scopes
2. Add two new `ops` tables:
   - `workflow_findings`
   - `workflow_finding_decisions`
3. Add write tools:
   - `save_workflow_finding`
   - `save_workflow_finding_decision`
4. Add query/read tools:
   - `list_workflow_finding_suppressions`
   - `get_finding_pattern_summary`
   - `get_agent_failure_mode_summary`
5. Keep decisions append-only and derive suppressions through query logic.
6. Follow existing MCP/analytics patterns so the new surface feels like an extension of the current workflow telemetry model rather than a separate subsystem.

---

--- Analysis Verification Iteration 1 ---
Findings from verifier: 6
FIX NOW: 5 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 1 (context added, no core conclusion change)
DISMISS: 0 (no change)

--- Analysis Verification Iteration 2 ---
Findings from verifier: 3
FIX NOW: 0
IMPLEMENT LATER: 0
ACKNOWLEDGE: 1 (phase-level decision persistence acknowledged as distinct from finding-level decisions)
DISMISS: 2 (no analysis change required)
