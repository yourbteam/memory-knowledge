---
name: auto-capture
description: |
  At the close of a substantive work session, capture the durable lessons learned into the
  brain as evidence-grade candidates, so knowledge accrues instead of evaporating. Fires when
  a session is wrapping up (task done, "that's all", end of a brainstorm/debug/build).
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
1. At session close, review the session for items meeting the capture criterion (0–3).
2. Run the managed script beside this file with a PTY:
   `/Users/kamenkamenov/memory-knowledge/.venv/bin/python <this-skill-directory>/scripts/auto_capture.py --interview`
3. The script asks for the repository key, then presents numbered menus for:
   - capture nothing / capture durable lessons,
   - content kind,
   - evidence kind,
   - add another evidence reference / finish,
   - add another lesson / finish.
4. When a menu is displayed, answer with exactly one displayed number. Use prose only for the
   requested title, body, repository key, path, UUID, or revision. Never bypass the script by
   hand-authoring `content_kind`, evidence `kind`, or continuation labels in an MCP call.
5. The script maps numbers to canonical values and calls `author_repo_note` with
   `verification_status="unverified"` and `confidence=0.4`.
6. Report what the script captured. If the repository has no ingested revision, report that and
   do not fabricate evidence.

## Output
A short list of captured candidate notes (titles + repo), or "nothing durable to capture."

## Notes
- Candidates are **not** directives. Promotion to a directive is human-gated ("lock it").
- Automatic extraction uses the active installed client subscription boundary; it never calls a
  public model API SDK. Codex and Claude answers pass through the same numbered parser.
- Codex has no session-end hook; this mechanical interview is how Codex (and Claude, as a
  fallback to the automatic hook) performs session-close capture.
