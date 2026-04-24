# Backlog

## Open Repo-Owned Items

### 1. Qdrant Startup Fingerprint Logging
**Priority:** Medium
**Status:** Open

**Problem:** Startup fingerprinting currently logs PostgreSQL and Neo4j details, but Qdrant does not have an equivalent harmless version/cluster fingerprint. This leaves one of the three configured stores without startup evidence that the process is connected to the intended environment.

**Expected outcome:** Add Qdrant version or cluster/info logging during startup, masking any sensitive values. The startup mode summary should make it easy to confirm local versus remote Qdrant connections without relying only on URL inspection.

**Likely files:** `src/memory_knowledge/server.py`, `src/memory_knowledge/db/qdrant.py`, startup/logging tests if practical.

### 2. Eventual Consistency And Repair Documentation
**Priority:** Medium
**Status:** Open

**Problem:** PostgreSQL is the canonical source while Qdrant and Neo4j are projections. Projection failures can leave the stores temporarily inconsistent until integrity audit, repair, or backfill tools run. The architecture supports this, but the operator-facing docs do not clearly describe the consistency model or expected recovery flow.

**Expected outcome:** Document the consistency contract, common drift scenarios, and when to use `run_integrity_audit_workflow`, `run_repair_rebuild_workflow`, `rebuild_revision_workflow`, and `run_embedding_backfill`.

**Likely files:** `README.md`, `docs/AGENT_INTEGRATION_SPEC.md`, `docs/remote-rollout-runbook.md`.

### 3. Remote Write Guard Coverage Tests
**Priority:** Medium
**Status:** Open

**Problem:** Remote write/rebuild guards are applied broadly, but the tool surface is large and growing. New write tools can be added without guard coverage unless tests enforce the safety contract.

**Expected outcome:** Add tests or static assertions that known write-path MCP tools call `check_remote_write_guard`, and destructive tools pass `is_destructive=True`.

**Likely files:** `tests/test_guards.py`, `tests/test_workflow_runs.py`, or a focused new server-tool guard coverage test.

### 4. Cross-Store Projection Drift Test Coverage
**Priority:** Medium
**Status:** Open

**Problem:** Integrity and repair workflows exist for PostgreSQL-to-Qdrant and PostgreSQL-to-Neo4j drift, but broader tests should cover representative projection-missing and repair scenarios across code chunks, summaries, learned memory, and triage cases.

**Expected outcome:** Add focused tests that simulate missing Qdrant points or Neo4j nodes/edges and verify audit/repair tools report and repair the expected drift without corrupting canonical PostgreSQL data.

**Likely files:** `tests/test_repair_drift.py`, `tests/test_ingestion.py`, `tests/test_triage_memory.py`, integrity workflow tests.

### 5. Repository Projection Freshness/Status Tool
**Priority:** Low
**Status:** Open

**Problem:** Freshness and integrity information exists in several places, but operators do not have one compact MCP read tool that summarizes per-repository projection status across PostgreSQL, Qdrant, and Neo4j.

**Expected outcome:** Add a read-only tool that returns repository revision, active retrieval surface, Qdrant projection counts/status, Neo4j projection status, last ingestion, last repair/audit signal if available, and freshness warnings.

**Likely files:** `src/memory_knowledge/server.py`, `src/memory_knowledge/admin/memory_stats.py` or a new admin module, integration spec docs, focused tests.

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
