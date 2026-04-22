# Roadmap and Backlog Hardening Plan

## Scope

Update `docs/roadmap.md` and `docs/backlog.md` so they accurately represent completed work, active next items, and archived history.

## Implementation Steps

1. Rewrite `docs/roadmap.md`.
   - move completed delivered slices out of implied active execution
   - add a `Recently Completed` section
   - ensure the remaining planned items are genuinely still open
   - separate repo-owned future work from external dependencies

2. Rewrite `docs/backlog.md`.
   - replace the current resolved-item-heavy layout with an active backlog first
   - keep only real unresolved repo-owned items in the active section
   - add an external follow-up section for non-repo-owned work
   - preserve historical context via a concise resolved archive summary rather than dozens of full resolved entries

3. Validate consistency.
   - confirm roadmap and backlog both treat V3 and remote rollout as completed
   - confirm the same next repo-owned items appear in both documents where appropriate
   - confirm external producer adoption is clearly marked as external

## Affected Files

- `docs/roadmap.md`
- `docs/backlog.md`
- `Tasks/roadmap-backlog-hardening/analysis.md`
- `Tasks/roadmap-backlog-hardening/plan.md`

## Validation Approach

- read both updated docs end-to-end
- confirm there are no stale “planned” items that are already implemented
- confirm backlog is actionable rather than archival

## Completion Criteria

The task is complete when:

- roadmap reflects actual implemented status
- backlog lists real open work first
- resolved history is retained in a compact form
- the two documents no longer contradict current repo state

## 2026-04-21 Follow-Up Plan

### Scope

Update `docs/roadmap.md` and `docs/backlog.md` to reflect the latest completed work and the actual remaining pending items.

### Implementation Steps

1. Update `docs/backlog.md`.
   - remove `docker/init-pg.sql` deprecation from open items
   - remove `docs/AGENT_INTEGRATION_SPEC.md` full reconciliation from open items unless a concrete unresolved gap is identified
   - add current open items only:
     - Neo4j readiness degradation
     - `fcsapi-remote-test` missing source URL, marked blocked
   - keep external workflow producer adoption as external
   - add recent ingestion-control and repo-refresh work to resolved archive summary

2. Update `docs/roadmap.md`.
   - add recent repository-refresh and ingestion-control hardening to `Recently Completed`
   - make `Next Up` match the backlog’s current open/blocked items
   - keep external workflow producer adoption separate
   - note Neo4j readiness as an operational follow-up rather than completed rollout validation

3. Validate consistency.
   - read both docs after edit
   - scan for stale `Status: Open` entries that contradict completed roadmap entries

### Affected Files

- `docs/roadmap.md`
- `docs/backlog.md`
- `Tasks/roadmap-backlog-hardening/analysis.md`
- `Tasks/roadmap-backlog-hardening/plan.md`

### Validation Approach

- direct document readback
- text scan for stale open statuses

### Closeout Checklist

- implemented: yes
- locally verified: yes, by document readback and targeted text scan
- remotely verified: not applicable
- deployed: not applicable
- pushed: no
- follow-ups remaining:
  - resolve Neo4j readiness degradation or define degraded-readiness semantics
  - provide or remove the `fcsapi-remote-test` catalog placeholder source
  - external workflow producer adoption remains outside this repo

## Execution Result

Implemented:

- rewrote `docs/roadmap.md` to separate completed work from active next items
- rewrote `docs/backlog.md` so it is once again an active backlog instead of a resolved-issue dump
- created task artifacts under `Tasks/roadmap-backlog-hardening/`

Validation performed:

- read back the updated roadmap
- read back the updated backlog
- confirmed both now treat triage V3 and live remote rollout as completed
- confirmed both originally pointed to the same then-open repo-owned priorities:
  - `docker/init-pg.sql` deprecation or reconciliation
  - `docs/AGENT_INTEGRATION_SPEC.md` full reconciliation
- superseded on 2026-04-21 by the follow-up closeout above, which archives those two items as completed

Closeout state:

- implemented: yes
- locally verified: yes, by direct document readback
- remotely verified: not applicable
- deployed: not applicable
- pushed: no
- follow-ups remaining:
  - superseded by the 2026-04-21 follow-up closeout above
