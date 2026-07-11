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

## Hardening — plans are build-bound, so default to hardening; scale to size

- **Small plan:** run `verify-plan` (quick verify-critic-fix loop in conversation).
- **Substantial / build-critical plan:** raise a hand — "want the full gates?" — and
  **wait** for Kamen's go. Do not launch the gates unilaterally. On his go, run in order
  (each loops until a fresh full pass finds zero blocker gaps):
  1. `requirements-coverage-gap-loop` — breadth (the requirement set is complete and every requirement is addressed or explicitly scoped out).
  2. `requirements-satisfaction-gap-loop` — depth (each addressed requirement actually holds against the real runtime, stored data, and sibling features).

  (`doc-gap-closure-loop` — internal readiness — is available too if the plan document
  itself needs consistency/grounding hardening before the breadth/depth gates.)

## Task-scoped directives

- **P1 · One-shot test.** Before calling a plan done, ask: could a competent implementer
  build this without coming back to Kamen for a decision? If not, it isn't done.
- **P2 · Lock decisions, don't list options.** A plan resolves choices; it doesn't hand
  Kamen a menu. Genuine open questions go to him explicitly — never buried as "could" or "maybe".
