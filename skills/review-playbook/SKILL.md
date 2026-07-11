---
name: review-playbook
description: This skill should be used when the task is REVIEW — auditing existing code, a diff, a PR, or a document for problems (correctness, security, quality) and for whether it covers the plan it was based on. It defines how Kamen and Codex run reviews: what a review rests on, which skills to reach for, and the task-scoped rules that always apply. Do not use it for open-ended research, planning, or writing the code itself.
---

# Playbook: Review

*Audit existing code / a diff / a doc for problems.*

**Aim:** surface the *real* problems (correctness, security) **and** confirm the implementation
actually covers the plan it's based on.

**Upstream — a review rests on knowing what the code is *supposed* to do:** when a plan exists,
that plan is the baseline; if there is no clear intent/spec, get it before reviewing — otherwise
intended behavior gets flagged as a bug, and missing work goes unnoticed.

## Reach for

- Codex's review stance: findings first, ordered by severity, grounded in file/line evidence.
- Security-focused inspection when the change touches auth, secrets, permissions, input handling, persistence, network calls, or dependency boundaries.
- `verify-analysis` when a document or architecture review needs iterative verifier-critic hardening.
- `verify-work` only when Kamen has asked to both review and fix to convergence.

## Task-scoped directives

- **RV1 · Real over many.** Every finding cites *where* and *why it's a genuine problem*;
  separate must-fix from nits; don't inflate the list. A false positive costs more than a missed nit.
- **RV2 · Cover the plan.** When the work is based on a plan, check the implementation addresses
  *every part* of it; flag anything in the plan that is missing or built differently — not only
  bugs in the code that is there.

(Fixing what a review finds stays gated on Kamen's go — that is **G3** (examine ≠ change), not a
new rule.)
