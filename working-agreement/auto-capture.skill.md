---
name: auto-capture
description: |
  At the close of a substantive work session, capture the durable lessons learned into the
  brain as evidence-grade candidates, so knowledge accrues instead of evaporating. Fires when
  a session is wrapping up (task done, "that's all", end of a brainstorm/debug/build).
author: Kamen / memory-knowledge
version: 1.0.0
---

# Auto-Capture (session-close)

## Problem
Lessons learned mid-session — a confirmed gotcha, a corrected approach, a decision with lasting
rationale — evaporate when the session ends unless someone deliberately saves them. This is the
skill-driven half of Gap #2 (the automatic Stop-hook is the other half). It captures **candidates**
(evidence-grade, `verification_status='unverified'`), never authoritative directives — promotion is
a separate, human-gated step (#3 Spark → "lock it").

## When to use
- A work, debug, or build session is wrapping up and produced reusable knowledge.
- The user signals done ("that's all", "thanks", "ship it") or the task is complete.

## When NOT to use
- One-off chit-chat, transient state, or anything already in `DIRECTIVES.md`/the brain.
- Mid-task (capture at *close*, not on every turn).

## Capture criterion (what qualifies)
Capture only **durable, reusable** lessons:
- a confirmed gotcha or root cause (not a guess),
- a corrected approach ("X didn't work, do Y"),
- a decision with lasting rationale,
- a stable project fact.
Skip: task chatter, transient status, secrets, large code blocks, anything already stored.

## Process
1. At session close, review the session for items meeting the capture criterion (typically 0–5).
2. For each, call the `author_repo_note` MCP tool with:
   - `repository_key` = the repo this session was about,
   - `title` = a one-line summary,
   - `body_text` = the lesson + its **why**,
   - `verification_status="unverified"` (candidate), `confidence` ~0.4.
3. If the repo isn't ingested into the brain (`author_repo_note` returns "no ingested revision"),
   skip it and say so — don't fabricate.
4. Report what was captured (titles), so the user can see and later promote/correct.

## Output
A short list of captured candidate notes (titles + repo), or "nothing durable to capture."

## Notes
- Candidates are **not** directives. Promotion to a directive is human-gated ("lock it").
- Codex has no session-end hook; this skill is how Codex (and Claude, as a fallback to the
  automatic hook) performs session-close capture.
