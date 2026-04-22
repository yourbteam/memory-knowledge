# Roadmap and Backlog Hardening Analysis

## Objective

Harden `docs/roadmap.md` and `docs/backlog.md` so they reflect current reality and can be used as active planning surfaces rather than stale historical snapshots.

## Source Artifacts Inspected

- `docs/roadmap.md`
- `docs/backlog.md`
- `Tasks/analytics-tools/plan.md`
- `Tasks/memory-knowledge-prerequisites/plan.md`
- `Tasks/triage-memory-server-implementation/plan.md`
- `Tasks/triage-policy-synthesis-v3/plan.md`
- `Tasks/triage-governance-composed-tools-v3/plan.md`
- `Tasks/task-workflow-skill-architecture/analysis.md`
- `Tasks/task-workflow-skill-upgrade/plan.md`
- implementation and test references under `src/` and `tests/` for triage memory and triage policy

## Current-State Findings

### Roadmap is stale

`docs/roadmap.md` still lists several items as planned or in-progress that have already been implemented and, in some cases, deployed:

- triage memory is implemented
- triage and workflow intelligence V3 is implemented
- live remote rollout validation has been executed
- workflow findings + LLM integration is implemented in the repo-owned surface

That makes the roadmap unreliable as a sequencing document.

### Backlog is no longer an active backlog

Every status entry in `docs/backlog.md` is marked resolved or stale-resolved. There are no active unresolved items in the current file.

That means the current backlog functions as a historical incident log, not as an actionable backlog.

### Current docs mix planning and archive concerns

Both files currently blur:

- active work
- future ideas
- external dependencies
- resolved historical context

That weakens their usefulness for fast decision-making.

## Recommended Hardening

### Roadmap

Restructure into:

- `Recently Completed`
- `Next Up`
- `External / Depends On Other Repos`
- `Future`

This keeps completed major slices visible without pretending they are still pending.

### Backlog

Restructure into:

- `Open Repo-Owned Items`
- `External / Non-Repo-Owned Follow-Ups`
- `Resolved Archive Summary`

Given the current state, the open backlog should be very short and contain only truly unresolved repo-owned work.

## Repo-Owned Open Items That Still Make Sense

The strongest current repo-owned next items are:

1. `docker/init-pg.sql` deprecation or reconciliation
2. `docs/AGENT_INTEGRATION_SPEC.md` full reconciliation

Both are already referenced in roadmap/task artifacts and remain unresolved in a meaningful way.

## Non-Repo-Owned or External Items

- external workflow producer adoption remains valid, but should be clearly marked as external rather than as in-repo backlog work

## Editing Strategy

- update `docs/roadmap.md` to reflect completed work and a shorter active future queue
- rewrite `docs/backlog.md` to show only active open items plus a concise resolved archive summary
- avoid keeping resolved items mixed into the active backlog body

## Risks

- compressing backlog history too aggressively could discard useful context
- leaving too much old detail in place would preserve the current confusion

## Decision

The right balance is:

- keep a concise resolved archive summary in `docs/backlog.md`
- move active planning focus to a short list of real unresolved items
- make roadmap and backlog agree on what is complete and what is next

## 2026-04-21 Follow-Up Analysis

### Objective

Reconcile `docs/roadmap.md` and `docs/backlog.md` after the latest repository-refresh and ingestion-control work.

### Task Type and Size

- task type: documentation / planning hygiene
- task size: light

This is light because it updates planning documents only. It does not change runtime behavior, schema, or remote data.

### Current-State Findings

The current roadmap and backlog contradict each other:

- `docs/roadmap.md` says no high-priority repo-owned roadmap item is open.
- `docs/backlog.md` still lists `docker/init-pg.sql` deprecation as open.
- `docs/backlog.md` still lists `docs/AGENT_INTEGRATION_SPEC.md` full reconciliation as open.

The task artifacts show `docker/init-pg.sql` deprecation is already implemented and locally verified in `Tasks/init-pg-bootstrap-reconciliation/plan.md`.

`docs/AGENT_INTEGRATION_SPEC.md` is already marked as the current integration reference and the roadmap lists agent integration spec reconciliation as completed. There is no clear evidence in the current docs that another full reconciliation is actively required; if a future one-to-one generated tool catalog is wanted, that should be a new optional docs-audit task rather than an open current-state blocker.

The latest operational work also completed:

- remote repository refreshes for the active ingested repos
- forced full `millennium-wp` refresh with a completed authoritative full run
- ingestion control-plane hardening for blank failure diagnostics and duplicate active ingestion requests

Remaining real current items are:

- external workflow producer adoption, outside this repo
- Neo4j readiness degradation, because `/ready` still reports Neo4j DNS failure even though `/health` is OK and ingestion degrades around Neo4j
- unresolved `fcsapi-remote-test` catalog placeholder, blocked until a real source URL is provided

### Recommended Approach

Update the docs so:

- completed repo-owned items are removed from the open backlog
- the latest ingestion-control hardening appears in completed roadmap/backlog history
- operationally real current follow-ups are represented accurately
- external or blocked items are not misclassified as normal repo-owned implementation work
