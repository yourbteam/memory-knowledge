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

## Next Up

### `docker/init-pg.sql` Deprecation or Full Reconciliation
**Problem:** `docker/init-pg.sql` remains a legacy bootstrap snapshot and does not reflect the current planning, reference-value, workflow, findings, analytics, and triage schema line.
**Goal:** Decide and implement one supported direction:
- either fully reconcile `docker/init-pg.sql` with the modern schema line
- or formally deprecate/remove it in favor of `alembic upgrade head`
**Why next:** This is the most important remaining repo-owned bootstrap/operations ambiguity.

### `docs/AGENT_INTEGRATION_SPEC.md` Full Reconciliation
**Problem:** `docs/AGENT_INTEGRATION_SPEC.md` is materially improved, but it is still not a full one-to-one reference for the current live server surface, including newer findings and triage V3 capabilities.
**Goal:** Bring the integration spec up to a complete, stable reference-quality document for external LLM integrators.
**Depends on:** Finalizing the bootstrap/support stance around the current server surface so the document does not need another structural rewrite immediately after.

## External / Depends On Other Repos

### External Workflow Producer Adoption
**Problem:** The canonical workflow telemetry write surfaces exist in this repo, but the external workflow producer must adopt them before phase and validator analytics become richly populated in production usage.
**Goal:** Update the external orchestrator to call `save_workflow_phase_state` and `save_workflow_validator_result` during execution and validator passes.
**Depends on:** Separate implementation work outside this repository.

## Future

### Deeper Workflow/Triage Feedback Automation
**Problem:** The platform now supports triage policy synthesis and workflow analytics, but evaluator-assisted automatic feedback loops are still limited compared with the long-term closed-loop direction.
**Goal:** Add stronger evaluator-driven scoring and convergence feedback so future routing and clarification guidance can be refined with less manual intervention.

### Workflow Process Tooling
**Problem:** The internal task-process ergonomics have been improved through the new task intake and size-aware workflow skills, but the repository does not yet include templates or examples for `light`, `standard`, and `heavy` task artifacts.
**Goal:** Add reusable examples/templates if the team finds repeated task-authoring friction in practice.
