# Backlog

## Open Repo-Owned Items

### 1. `docker/init-pg.sql` deprecation or full reconciliation
**Priority:** High
**Status:** Open

**Problem:** `docker/init-pg.sql` is still a legacy bootstrap snapshot and does not reflect the current planning, reference-value, workflow, findings, analytics, and triage schema line.

**Why it matters:** The repository currently has two competing bootstrap narratives:
- the supported path: `alembic upgrade head`
- the legacy snapshot path: `docker/init-pg.sql`

That ambiguity is operationally risky and keeps reappearing in task planning, rollout, and local bootstrap assumptions.

**Expected outcome:** Choose and implement one supported direction:
- reconcile `docker/init-pg.sql` to the modern schema line
- or formally deprecate/remove it and make Alembic the only supported bootstrap path

**Relevant context:** `Tasks/analytics-tools/plan.md` documents that the current file is materially incomplete, not just slightly out of date.

### 2. `docs/AGENT_INTEGRATION_SPEC.md` full reconciliation
**Priority:** Medium
**Status:** Open

**Problem:** The integration spec is substantially improved, but it is still not a full one-to-one reference for the current live server surface, especially across newer findings, triage-memory, and triage V3 capabilities.

**Why it matters:** External LLM integrators now have a richer server surface than the original workflow-focused subset. The spec should become a stable reference-quality integration manual rather than a partial bridge document.

**Expected outcome:** Expand and reconcile `docs/AGENT_INTEGRATION_SPEC.md` so it accurately documents the full intended integrator-facing tool surface and current usage expectations.

## External / Non-Repo-Owned Follow-Ups

### 3. External workflow producer adoption
**Priority:** External
**Status:** Pending outside this repo

**Problem:** The canonical workflow telemetry write surfaces now exist in this repo, but the external workflow producer must adopt them before phase and validator analytics become richly populated in real usage.

**Expected outcome:** Update the external orchestrator to call `save_workflow_phase_state` and `save_workflow_validator_result` during execution and validator passes.

## Resolved Archive Summary

The historical backlog items previously tracked here have been resolved and are retained in git history. The major resolved areas are:

- ingestion correctness and resume behavior
- remote private-repo GitHub auth for ingestion
- remote PostgreSQL ingestion performance improvements
- config/guard hermetic test behavior
- purge/reset tooling
- local-to-remote export/import hardening
- triage outcome normalization
- triage historic re-embedding/backfill support
- triage confusion-cluster and clarification-recommendation tools
- stronger hybrid ranking for triage retrieval

For detailed historical wording, consult prior revisions of this file in git history.
