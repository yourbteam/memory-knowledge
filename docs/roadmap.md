# Roadmap

## In Progress

### Analytics Tools Upgrade
**Status:** Implemented and shipped.
**Plan:** `Tasks/analytics-tools/plan.md`
**Delivered:**
- 2 new MCP write tools (`save_workflow_phase_state`, `save_workflow_validator_result`)
- 6 new MCP analytics query tools (agent performance, phase quality, validator failures, loop patterns, quality grades, entropy sweep)
- Migration 008: new table, reference values, schema fixes, indexes
- Test coverage for workflow/planning/analytics contracts
- `get_workflow_run` validator-result readback
- AGENT_INTEGRATION_SPEC reconciliation for the analytics/tooling surface
- Bootstrap-path clarification for analytics-ready startup

### Workflow Findings + LLM Integration
**Status:** Implemented and in active rollout hardening.
**Plan:** `Tasks/memory-knowledge-prerequisites/plan.md`
**Scope:**
- Migration 009 workflow findings persistence
- findings administration/query layer
- LLM integration guide and workflow findings operator docs
- server integration for findings and related ingestion/runtime support
- expanded ingestion/runtime tests and auth/clone support work that landed with this slice

### Triage Memory
**Status:** Implemented.
**Plan:** `Tasks/triage-memory-server-implementation/plan.md`
**Delivered v1:**
- migration `010_triage_memory`
- 4 MCP tools:
  - `save_triage_case`
  - `search_triage_cases`
  - `record_triage_case_feedback`
  - `get_triage_feedback_summary`
- 2 triage analysis tools:
  - `get_triage_confusion_clusters`
  - `get_triage_clarification_recommendations`
- canonical PostgreSQL persistence for triage cases and feedback
- normalized triage outcome statuses through `core.reference_values`
- best-effort Qdrant-backed semantic retrieval for similar-case search
- lexical fallback only when semantic retrieval is unavailable
- triage-case re-embedding/backfill support for historic recovery
- feedback-summary aggregation and focused server-side test coverage
- deterministic confusion-cluster and clarification-recommendation aggregation over triage history
- explicit hybrid ranking for `search_triage_cases`

---

## Planned

### Triage + Workflow Intelligence V3
**Problem:** The server now persists triage cases, workflow telemetry, planning context, and analytics, but it still mostly reports history rather than adapting behavior from that history. Integrators must manually interpret triage outcomes, confusion patterns, and workflow failure signals.
**Goal:** Upgrade the platform from passive memory plus analytics into a controlled closed-loop decision system that can synthesize routing guidance, generate clarification policies, improve ranking, and connect workflow outcomes back into future triage behavior.
**Target v3 scope:**
- decision policy synthesis from triage history
  - produce reusable routing guidance from prior successful and failed cases
  - surface repo-scoped and project-scoped routing heuristics instead of only raw case matches
- stronger triage lifecycle modeling
  - expand outcome normalization and make triage state transitions more explicit
  - support clearer separation between proposed, executed, validated, corrected, and superseded decisions
- first-class historic repair and reindex operations
  - make triage backfill, re-embedding, and recovery workflows operationally explicit
  - support safer selective refresh of historic triage data after schema or ranking changes
- stronger hybrid ranking
  - combine semantic similarity with repository affinity, project affinity, historical success rate, recency, clarification cost, and workflow priors
  - improve result ordering for `search_triage_cases` beyond the current lightweight score adjustments
- policy-oriented confusion intelligence
  - turn confusion clusters and clarification recommendations into concrete suggested intake prompts, question templates, and guardrails
- repository-aware behavioral profiles
  - allow routing behavior to differ by repository or project when history shows different successful patterns
- evaluator-assisted feedback loops
  - add automatic evaluators that can score triage decisions against retrieved evidence or later workflow results
  - reduce dependence on purely manual or downstream feedback
- higher-level integrator tools
  - add composed tools such as a memory-aware triage helper and outcome finalization helper so integrators do less manual orchestration
- planning and workflow convergence
  - let repeated validator failures, phase quality patterns, and finding patterns feed back into routing and clarification advice
- governance and trust controls
  - add confidence thresholds, drift tracking, and reversible policy rollout for learned decision guidance
**Expected outcome:** Future integrator LLMs should be able to ask the server not only what happened before, but what behavior is currently recommended based on prior evidence and measured outcomes.
**Depends on:** Stable adoption of the current triage, workflow telemetry, planning, and analytics tools by integrator clients so V3 has enough real operational signal to learn from.

### Live Remote Rollout Validation
**Problem:** The analytics upgrade and newer findings/runtime changes are implemented, but final confidence still depends on executing the remote rollout runbook against the real office environment and verifying health, migrations, and MCP smoke checks end-to-end.
**Goal:** Run the remote deployment and validation sequence using the supported `alembic upgrade head` path and capture a rollout report with migration, health, and smoke-test results.
**Depends on:** Office network access and real remote credentials.

---

### External Workflow Producer Adoption
**Problem:** The canonical workflow telemetry write surfaces now exist in this repo, but the external workflow producer still needs to adopt them before phase and validator analytics become populated in real usage.
**Goal:** Update the external orchestrator to call `save_workflow_phase_state` and `save_workflow_validator_result` during execution and validator passes.
**Depends on:** An up-to-date external producer repo and separate implementation work outside this repository.

---

## Future

### AGENT_INTEGRATION_SPEC Full Reconciliation
**Problem:** The spec has already been updated past the original 12-tool narrative, but it is still a workflow-integration document rather than a full one-to-one reference for every server tool and newer findings/runtime surface.
**Depends on:** Stabilizing the post-migration-009 server surface before doing a complete reference-style reconciliation.

---

### init-pg.sql Deprecation or Reconciliation
**Problem:** `docker/init-pg.sql` remains a legacy bootstrap snapshot and still does not reflect the modern planning/reference/workflow/findings schema line.
**Current direction:** Keep `alembic upgrade head` as the supported path and treat raw `init-pg.sql` bootstrap as legacy until a future full reconciliation or removal decision.
**Depends on:** Separate bootstrap ownership work, not the completed analytics docs cleanup.
