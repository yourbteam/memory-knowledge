# Roadmap

## In Progress

### Analytics Tools Upgrade
**Status:** Core implementation in place; docs/bootstrap reconciliation in progress.
**Plan:** `Tasks/analytics-tools/plan.md`
**Scope:**
- 2 new MCP write tools (`save_workflow_phase_state`, `save_workflow_validator_result`)
- 6 new MCP analytics query tools (agent performance, phase quality, validator failures, loop patterns, quality grades, entropy sweep)
- Migration 008: new table, reference values, schema fixes, indexes
- Test coverage and AGENT_INTEGRATION_SPEC reconciliation
- Bootstrap-path clarification for analytics-ready startup

---

## Planned

### Ingestion Checkpoint/Resume
**Problem:** Ingestion restarts from step 1 on every run. Only the summarization step has skip logic for existing data. A 2-hour ingestion that fails at 90% in the summary phase re-does all file scanning, chunk registration, and edge resolution before reaching summaries again.
**Goal:** True checkpoint-based resume using the existing `job_manifests.checkpoint_data` column. Each completed phase writes a checkpoint; on retry, the workflow reads the checkpoint and jumps to the failed phase.
**Depends on:** Nothing — infrastructure (`checkpoint_data` column) already exists but is unused during execution.
**Discovered:** 2026-04-09 — FCSAPI ingestion failed twice mid-summarization, each re-run wasted ~30 min re-scanning already-processed files.

---

### Remote Ingestion Auth
**Problem:** The remote MCP server cannot clone private GitHub repos — `git clone` fails with `could not read Password`. The `origin_url` is set but no credentials are available on the remote host. Current workaround is running ingestion via the local MCP server which has filesystem access to the cloned repos.
**Goal:** Either (a) deploy key / PAT-based auth for the remote server's git operations, or (b) formalize the local-ingest-then-sync pattern as the supported workflow.
**Discovered:** 2026-04-09 — FCSAPI remote ingestion failed with git auth error; local server used as workaround.

---

## Future

### AGENT_INTEGRATION_SPEC Full Reconciliation
**Problem:** The spec documents 12 MCP tools but the server has 49. The analytics upgrade adds 8 more. The spec needs a full reconciliation pass, not just incremental additions.
**Depends on:** Analytics tools upgrade (adds the last batch of tools before reconciliation makes sense).

---

### init-pg.sql Deprecation or Reconciliation
**Problem:** `docker/init-pg.sql` is frozen at migration-004 level. Missing `core` schema, `planning` schema, post-004 columns, and all reference seed data. It is not a complete analytics-ready bootstrap source.
**Current direction:** Keep `alembic upgrade head` as the supported path and treat raw `init-pg.sql` bootstrap as legacy until a full reconciliation exists.
**Depends on:** Analytics upgrade docs/bootstrap cleanup.
