# Roadmap

## Recently Completed

### Analytics Tools Upgrade
**Status:** Implemented and shipped.
**Plan:** `Tasks/analytics-tools/plan.md`
**Delivered:**
- 2 new MCP write tools: `save_workflow_phase_state`, `save_workflow_validator_result`
- 6 analytics tools:
  - `get_agent_performance_summary`
  - `get_phase_quality_summary`
  - `get_validator_failure_summary`
  - `get_loop_pattern_summary`
  - `get_quality_grade_summary`
  - `list_entropy_sweep_targets`
- migration `008_analytics_schema`
- workflow/planning/analytics test coverage
- `get_workflow_run` validator-result readback
- analytics-facing `AGENT_INTEGRATION_SPEC` reconciliation
- analytics rollout runbook and supported bootstrap-path clarification

### Workflow Findings + LLM Integration
**Status:** Implemented.
**Plan:** `Tasks/memory-knowledge-prerequisites/plan.md`
**Delivered:**
- migration `009` workflow findings persistence
- findings administration/query layer
- server integration for findings surfaces
- LLM integration guide and workflow findings operator documentation
- auth/clone/runtime support required for external workflow producer adoption

### Triage Memory v1
**Status:** Implemented.
**Plan:** `Tasks/triage-memory-server-implementation/plan.md`
**Delivered:**
- migration `010_triage_memory`
- core triage tools:
  - `save_triage_case`
  - `search_triage_cases`
  - `record_triage_case_feedback`
  - `get_triage_feedback_summary`
- triage analysis tools:
  - `get_triage_confusion_clusters`
  - `get_triage_clarification_recommendations`
- normalized triage outcome statuses via `core.reference_values`
- historic triage re-embedding/backfill support
- explicit hybrid ranking for `search_triage_cases`

### Triage + Workflow Intelligence V3
**Status:** Implemented and rolled out.
**Plans:**
- `Tasks/triage-lifecycle-normalization-v3/plan.md`
- `Tasks/triage-policy-synthesis-v3/plan.md`
- `Tasks/triage-adaptive-ranking-v3/plan.md`
- `Tasks/triage-governance-composed-tools-v3/plan.md`
**Delivered:**
- stronger triage lifecycle modeling
- routing policy synthesis and clarification policy synthesis
- repository-aware behavioral profiles
- governance metadata and persisted policy artifacts
- higher-level integrator tools:
  - `refresh_triage_policy_artifacts`
  - `get_behavior_policy_status`
  - `triage_request_with_memory`
  - `finalize_triage_outcome`
- adaptive ranking improvements connected to prior outcomes and clarification signals

### Live Remote Rollout Validation
**Status:** Completed.
**Delivered:**
- remote migrations applied successfully
- live app deployed and restarted successfully
- `/health` and `/ready` verified
- live MCP smoke checks completed against the deployed server

### Agent Integration Spec Reconciliation
**Status:** Completed.
**Plan:** `Tasks/agent-integration-spec-reconciliation/plan.md`
**Delivered:**
- replaced stale count- and persona-heavy document structure
- reconciled the spec around the current live MCP surface
- documented planning, workflow telemetry, findings, analytics, triage memory, and triage policy tooling as one current integrator reference

### `docker/init-pg.sql` Bootstrap Deprecation
**Status:** Completed.
**Plan:** `Tasks/init-pg-bootstrap-reconciliation/plan.md`
**Delivered:**
- removed the legacy snapshot from the active local Docker bootstrap path
- documented `alembic upgrade head` as the supported PostgreSQL bootstrap path
- validated fresh local bootstrap against the current migration line
- kept `docker/init-pg.sql` only as a deprecated historical snapshot

## Next Up

### Repo-Owned Roadmap Slice Complete
**Status:** No remaining high-priority repo-owned roadmap item is currently open.
**Meaning:** The next meaningful work now sits either in external adoption or in future enhancement tracks rather than in unresolved current-state reconciliation work.

## External / Depends On Other Repos

### External Workflow Producer Adoption
**Problem:** The canonical workflow telemetry write surfaces exist in this repo, but the external workflow producer must adopt them before phase and validator analytics become richly populated in production usage.
**Goal:** Update the external orchestrator to call `save_workflow_phase_state` and `save_workflow_validator_result` during execution and validator passes.
**Depends on:** Separate implementation work outside this repository.

## Future

### Triage + Workflow Feedback Automation V4
**Status:** Implemented.
**Umbrella Plan:** `Tasks/triage-feedback-automation-v4/plan.md`
**Goal:** Move from passive reporting and reusable memory toward active routing, clarification, and convergence adaptation driven by persisted outcomes.
**Recommended delivery order:**
- `Tasks/outcome-weighted-routing-v4/plan.md`
- `Tasks/clarification-policy-learning-v4/plan.md`
- `Tasks/convergence-intelligence-v4/plan.md`
- `Tasks/failure-mode-playbooks-v4/plan.md`
- `Tasks/actor-team-adaptation-v4/plan.md`
- `Tasks/policy-governance-rollout-v4/plan.md`

### Outcome-Weighted Routing V4
**Plan:** `Tasks/outcome-weighted-routing-v4/plan.md`
**Status:** Implemented.
**Practical effect:** Route selection starts using downstream outcomes such as success rates, loop counts, and validator failures instead of relying mostly on prior case similarity and static policy artifacts.

### Clarification Policy Learning V4
**Plan:** `Tasks/clarification-policy-learning-v4/plan.md`
**Status:** Implemented.
**Practical effect:** Repeated ambiguity patterns become reusable clarification policy so the system asks the right questions before committing to a workflow.

### Convergence Intelligence V4
**Plan:** `Tasks/convergence-intelligence-v4/plan.md`
**Status:** Implemented.
**Practical effect:** Loop summaries become actionable convergence recommendations, helping orchestrators choose better interventions instead of repeating the same retry pattern.

### Failure-Mode Playbooks V4
**Plan:** `Tasks/failure-mode-playbooks-v4/plan.md`
**Status:** Implemented.
**Practical effect:** Recurring validator, finding, and routing failures get mapped to recommended next-step playbooks rather than remaining analytics-only observations.

### Actor/Team Adaptation V4
**Plan:** `Tasks/actor-team-adaptation-v4/plan.md`
**Status:** Implemented.
**Practical effect:** The platform can adapt route confidence, clarification needs, and workflow defaults based on stable actor or automation-source behavior patterns.

### Policy Governance And Rollout V4
**Plan:** `Tasks/policy-governance-rollout-v4/plan.md`
**Status:** Implemented.
**Practical effect:** Adaptive policies now have a consolidated governance summary showing rollout posture, drift, suppression pressure, and promotion-ready advisory candidates.

### Workflow Process Tooling
**Problem:** The internal task-process ergonomics have been improved through the new task intake and size-aware workflow skills, but the repository does not yet include templates or examples for `light`, `standard`, and `heavy` task artifacts.
**Goal:** Add reusable examples/templates if the team finds repeated task-authoring friction in practice.
