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

---

## Planned

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
