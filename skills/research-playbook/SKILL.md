---
name: research-playbook
description: This skill should be used when the task is RESEARCH — gathering or verifying information without shipping code (answering a question, surveying options, investigating how something works, producing a findings/analysis document). It defines how Kamen and Codex run research: which skill to reach for, when to harden the output through the three gap-loop gates, and the task-scoped rules that always apply. Do not use it for writing code, planning an implementation, or reviewing a diff.
---

# Playbook: Research

When delegated by `playbook-convergence-loop`, all hardening agents are assessment-only. They may inspect authoritative source/runtime evidence but receive no producer rationale or hidden expected answer. The parent alone edits artifacts and records state. Each gate returns the envelope from `skills/_shared/STAGE_RESULT_CONTRACT.md`: `PASS`, `GAPS`, `BLOCKED`, or `CAP_REACHED`.

*Gather or verify information; no code shipped.*

**Aim:** produce findings — and if those findings will feed a build, harden them through the three gates first so the build isn't surprised later.

## Reach for

- Local repo inspection first when the question is about code, architecture, docs, or project state.
- Web search when the answer depends on current external facts, official docs, laws, prices, releases, or anything likely to have changed.
- `verify-analysis` when a prior analysis needs an independent verifier-critic-fix hardening loop.
- `openai-docs` when the research is about OpenAI, Codex, ChatGPT, or the OpenAI API.

## Hardening gates — default light, flag when build-bound

- **Default:** research stops at findings.
- **If the output looks build-bound** (it will feed an implementation), raise a hand —
  "this looks build-bound; want the gates?" — and **wait** for Kamen's go. Do not launch
  the gates unilaterally.
- **On Kamen's go,** run in order (each loops until a fresh full pass finds zero blocker gaps):
  1. `doc-gap-closure-loop` — internal readiness (document self-sufficient, consistent, cited claims real).
  2. `requirements-coverage-gap-loop` — breadth (the requirement set is complete and every requirement is addressed or explicitly scoped out).
  3. `requirements-satisfaction-gap-loop` — depth (each addressed requirement actually holds against the real runtime, stored data, and sibling features).

  Order matters: no point depth-testing a requirement that breadth proved was never addressed.

## Task-scoped directives

- **R1 · Cite or flag.** Every claim carries a source or is marked as my inference — no
  confident assertions from memory on factual questions.
- **R2 · Scope before searching.** If the question is underspecified, ask 1–3 narrowing
  questions before fanning out — don't research the wrong thing thoroughly.
