# What goes where — Directives vs Playbook vs MCP corpus

When something is worth keeping, decide which of the three homes it belongs in. It's a
**trichotomy**, not a binary:

| Home | What belongs there | Shape | Delivery |
| --- | --- | --- | --- |
| **`DIRECTIVES.md`** (Tier-1) | A **universal rule** I must obey on *every applicable turn*, across all projects | short, pass/fail | auto-injected every prompt |
| **Playbook skill** (task-scoped) | A rule that's real but only applies to *one task type* (research/plan/write-code/review) | short, pass/fail | loaded when that mode fires |
| **MCP corpus** (Tier-2) | **Reference / rationale / examples** — background that helps *when the topic comes up* | can be long, not pass/fail | retrieved on demand by relevance |

## Litmus test

- **Directive** — "a rule I must *obey* every applicable turn; short; pass/fail; universal enough
  that always-injecting it is worth the cost." (G0–G4 are this.)
- **Playbook rule** — same pass/fail character, but **only relevant inside one mode** — so it rides
  with that playbook, not the always-on file. (e.g. *"every DB migration must have a `downgrade()`"* →
  write-code playbook.)
- **Corpus entry** — "*background* that helps *when relevant*; can be long; not a rule to obey;
  would be **noise** if injected on every prompt." (rationale, incident history, worked examples,
  references.)

## Worked example

Working on the FCS auth/token-refresh code:

- *"Never log secrets/tokens — redact before any log or output."* → **`DIRECTIVES.md`**: universal,
  short, pass/fail, must fire on every applicable turn.
- *"FCS token-refresh uses idempotency keys because a 2025 incident showed naive retry double-charged
  the billing call; a 500 is indeterminate — reconcile, don't blindly retry."* → **MCP corpus**:
  rich, project-specific rationale; only relevant near that code; noise if always-on.
- *"Here's the shape of a correct token-refresh handler in this repo (snippet + why)."* → **MCP corpus**:
  a worked example / reference, not a rule.
- *"Every DB migration must have a `downgrade()`."* → **write-code playbook**: a real rule, but
  task-scoped, not universal.

## Rule of thumb

If injecting it on **every** prompt would be worth it → directive. If it's a rule but only in one
mode → that playbook. If it's knowledge you'd want **pulled up when the subject arises** → corpus
(add via the `corpus-add` skill).
