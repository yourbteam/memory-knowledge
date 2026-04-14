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
