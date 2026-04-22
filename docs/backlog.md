# Backlog

## Open Repo-Owned Items

None currently tracked.

## Blocked / Needs Input

None currently tracked.

## External / Non-Repo-Owned Follow-Ups

### 3. External workflow producer adoption
**Priority:** External
**Status:** Pending outside this repo

**Problem:** The canonical workflow telemetry write surfaces now exist in this repo, but the external workflow producer must adopt them before phase and validator analytics become richly populated in real usage.

**Expected outcome:** Update the external orchestrator to call `save_workflow_phase_state` and `save_workflow_validator_result` during execution and validator passes.

## Resolved Archive Summary

The historical backlog items previously tracked here have been resolved and are retained in git history. The major resolved areas are:

- `docker/init-pg.sql` deprecation from the active bootstrap path
- `docs/AGENT_INTEGRATION_SPEC.md` reconciliation into a current integration reference
- remote repository refresh/status reconciliation for `css-fe`, `fcs-admin`, `fcsapi`, `taggable-server`, and `millennium-wp`
- ingestion control-plane hardening for blank failure diagnostics and duplicate active ingestion requests
- Neo4j readiness semantics now report graph projection as degraded while PostgreSQL/Qdrant remain readiness gates
- remote `fcsapi-remote-test` placeholder and its disposable smoke-test planning/workflow/triage rows were removed
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
