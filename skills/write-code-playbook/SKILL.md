---
name: write-code-playbook
description: This skill should be used when the task is WRITING CODE — implementing a change in the codebase (adding a feature, fixing a bug, refactoring, wiring something up). It defines how Kamen and Codex run implementation: what it rests on upstream, which skills to reach for, and the task-scoped rule that always applies. Do not use it for open-ended research, planning an implementation, or reviewing someone else's diff.
---

# Playbook: Write code

*Implement a change in the codebase.*

**Aim:** a correct, verified change that does what the plan/goal says — and nothing extra.

**Upstream — rests on sufficient plan/understanding (not a mandatory plan step):** a substantial
change → plan first (see `plan-playbook`); a small/clear change → implement directly. If writing
reveals the plan was wrong, pause and re-plan rather than coding around it.

## Reach for

- Repo-native tests, builds, linters, smoke tests, and direct behavior checks.
- `prototype-driven-implementation` when the outcome is concrete but important implementation
  behavior remains uncertain, or when Kamen explicitly asks for a bounded sequence of grounded
  prototypes. Its autonomy envelope does not override the working agreement's approval rules.
- In the `memory-knowledge` repository, run pytest only through
  `scripts/run_pytest.sh <test paths and pytest arguments>`. The launcher routes Python,
  uv, and pytest cache writes away from read-only repository/home paths. Do not invoke
  `uv run pytest`, `python -m pytest`, or `pytest` directly there.
- Browser verification for local frontend changes when the target page or port is known.
- A manual code-review pass over the diff before reporting done.
- `verify-work` when Kamen asks for an independent review/fix convergence loop. Commits require separate commit-scoped approval.

When called by `playbook-convergence-loop`, the approved hardened plan authorizes edits inside its recorded paths. Run `guard-baseline` immediately before each source edit or verification command. The parent orchestrator is the only fixer/state writer; nested verification agents remain assessment-only and return the shared stage-result envelope. Default commit policy is `none`.

## Task-scoped directive

- **WC1 · Verify before "done".** Never report a change complete without running it / observing
  the behavior. If it genuinely can't be verified, say so and why — don't imply it works.

(No "smallest change / no opportunistic refactors" rule here: that is **G3** applied to code —
don't widen the ask — and the global directive already covers it. Per the refinement rule, no
new rule for a problem an existing rule already handles.)
