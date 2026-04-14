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

## Execution Result

Implemented:

- rewrote `docs/roadmap.md` to separate completed work from active next items
- rewrote `docs/backlog.md` so it is once again an active backlog instead of a resolved-issue dump
- created task artifacts under `Tasks/roadmap-backlog-hardening/`

Validation performed:

- read back the updated roadmap
- read back the updated backlog
- confirmed both now treat triage V3 and live remote rollout as completed
- confirmed both now point to the same next repo-owned priorities:
  - `docker/init-pg.sql` deprecation or reconciliation
  - `docs/AGENT_INTEGRATION_SPEC.md` full reconciliation

Closeout state:

- implemented: yes
- locally verified: yes, by direct document readback
- remotely verified: not applicable
- deployed: not applicable
- pushed: no
- follow-ups remaining:
  - none for this hardening task itself
