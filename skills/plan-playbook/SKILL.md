---
name: plan-playbook
description: This skill should be used when the task is PLANNING — turning a goal into a checkable implementation plan before any code is written (deciding how to build something, sequencing the work, resolving design choices, producing a plan/spec document). It defines how Kamen and Codex run planning: which skills to reach for, how to harden the plan in proportion to its size, and the task-scoped rules that always apply. Do not use it for open-ended research, writing code, or reviewing a diff.
---

# Playbook: Plan

When delegated by `playbook-convergence-loop`, verifier and critic agents are assessment-only and can inspect authoritative source/runtime evidence while remaining isolated from producer rationale. The parent alone edits the plan and state. Require the baseline guard before each edit or delegated pass, return the shared stage-result envelope, and make no commits by default.

*Turn a goal into a checkable implementation plan before building.*

**Aim:** a plan solid enough to build from one-shot — a competent implementer should not have to come back with a decision.

**Upstream — a plan rests on sufficient understanding (not a mandatory research step):** if the
area is already understood (known cold, or just researched), plan directly. If not, do
Research first (see `research-playbook`), then plan. If planning exposes an unknown mid-way,
pause and research that point, then resume. The downstream hardening (`verify-plan` /
coverage + satisfaction gates) is the safety net for a misjudged "I understand enough".

## Reach for

- Codex planning in the current thread when the user asks for a plan or the change needs a decision-complete implementation sequence.
- `verify-plan` — to harden the plan in-conversation (verify-critic-fix loop).

## Hardening — plans are build-bound; scale review to concrete risk

- **Small, clear plan:** perform a direct source-grounding and P1/P2 check in the current thread.
  Do not invoke `verify-plan` by default. Use it only when a concrete correctness, coverage, or
  decision-completeness risk is identified, or when Kamen explicitly requests independent
  hardening.
- **Standard plan:** when a concrete risk warrants independent hardening, allow at most one
  revision round.
- **Substantial / build-critical plan:** raise a hand — "want the full gates?" — and
  **wait** for Kamen's go. Do not launch the gates unilaterally. On his go, run in order
  within at most two total revision rounds:
  1. `requirements-coverage-gap-loop` — breadth (the requirement set is complete and every requirement is addressed or explicitly scoped out).
  2. `requirements-satisfaction-gap-loop` — depth (each addressed requirement actually holds against the real runtime, stored data, and sibling features).

  (`doc-gap-closure-loop` — internal readiness — is available too if the plan document
  itself needs consistency/grounding hardening before the breadth/depth gates.)

A revision round is one full assessment of one frozen candidate across the selected gates,
followed by at most one parent revision. Any fresh full assessment consumes another round.
The budget follows the objective across renamed or successor packages and cannot reset. At the cap,
stop and return the best valid deliverable with remaining findings assigned downstream. If an
actual blocker remains, report the deliverable as blocked; another round requires Kamen's explicit
approval.

## Task-scoped directives

- **P1 · Decision-complete, not omniscient.** A plan must resolve every product, architecture,
  ownership, and implementation decision that available evidence can resolve. A runtime fact that
  can only be learned by executing the real path must become a bounded implementation experiment
  with its command or path, required evidence, success condition, and expected outcome branches.
  Do not manufacture certainty to make the plan appear complete.
- **P2 · Lock decisions and decision procedures.** Resolve actual choices; do not list arbitrary
  options. When an unknowable runtime fact controls the next step, lock the experiment and the rule
  for selecting the resulting branch. Genuinely unexpected evidence pauses implementation and
  returns only that point to planning.
