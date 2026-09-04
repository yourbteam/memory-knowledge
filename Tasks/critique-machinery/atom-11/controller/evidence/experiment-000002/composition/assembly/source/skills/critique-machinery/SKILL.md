---
name: critique-machinery
description: Run an evidence-bound 360-degree critique of one delivered client page. Use when a page must be completely inspected unit by unit through fixed buyer, finance, journalist, employee, competitor, benchmark, and upstream lenses without rewriting it or hiding unresolved judgments.
---

# Critique Machinery

Produce located defects, not rewritten copy. Every run is immutable, lives below the active Git
repository, and binds the rendered page to the exact stored payload that produced it. Never move a
run to a temporary root or replace its state.

Use `scripts/critique.py` from this skill directory:

```bash
python3 scripts/critique.py open --page <page.md> \
  --payload <state.json#context.key> --work <repo/Tasks/task/runs/name> \
  --reference <stable-id> --reference-page <reference.md> \
  --upstream-source <producer-id>=<producer-state.json#context.key> \
  --upstream-source <another-id>=<producer-state.json#context.key>
# Declare each absent material class explicitly when it does not exist:
python3 scripts/critique.py open --page <page.md> \
  --payload <state.json#context.key> --work <repo/Tasks/task/runs/name> \
  --no-reference "<recorded reason>" --no-upstream "<recorded reason>"
python3 scripts/critique.py status --work <work>
python3 scripts/critique.py read-run --work <work>
python3 scripts/critique.py retry-failed --work <work>
python3 scripts/critique.py read-cell --work <work> --id <unit::lens>
python3 scripts/critique.py ask-owner --work <work>
python3 scripts/critique.py answer-owner --work <work> --id <decision-id> \
  --choice <offered-verdict> --because "<owner's exact words>"
python3 scripts/critique.py correct-owner --work <work> --id <recorded-decision-id> \
  --choice <offered-verdict> --because "<owner's corrected words>"
python3 scripts/critique.py document --work <work> --out <findings.md>
```

`open` requires exactly one benchmark-source declaration: a reference id plus page, or a non-empty
`--no-reference` reason. In a no-reference run, benchmark cells are recorded as not applicable and
are never sent to readers; `status` and the finished document retain the reason. This is not a
`clear` benchmark judgment.

`open` separately requires exactly one upstream-source declaration: one or more repeated
`--upstream-source <id>=<state.json#context.key>` values, or a non-empty `--no-upstream` reason.
In a no-upstream run, upstream cells are recorded as not applicable, never sent to readers, and
retain the reason in `status` and the finished document. Registered producer text is shown to each
seat. An upstream reject or revise must name one registered source and select exact numbered words;
code copies and verifies the passage. A claim that cannot satisfy that contract becomes a visible
recording refusal, never a defect.

`register-source` and `trace` remain available for legacy runs that did not declare producer
material at open. Before a defect can be recorded under `benchmark-vs-reference`, register the
reference page with `register-reference` and attach exact words from both texts with `benchmark`.
Do not substitute labels, paraphrases, or model memory for those records.

Run each judgment through both fixed blind seats. The installed client projection owns the reader
runtime; the script refuses an unavailable or invalid runtime rather than switching clients. Code
starts every seat in an isolated working directory with that client's settings, tools, persistence,
and ambient instructions disabled, and supplies an exact schema through the client's structured
output control. The reply intake accepts exactly one schema-valid JSON object and records exactly
one of `valid`, `malformed`, `empty`, `timeout`, or `nonzero-exit`; it never repairs fences,
prefaces, truncation, extra keys, or wrong lens order.
This code-owned interview is the only model entry point: `read-cell`, `read-run`, and
`retry-failed` all use the same question, schema, identity, evidence, and intake path. Never invoke
a seat separately or paste a reply into the matrix; replay reads captured bytes and spends no call.
The two seat claims for one cell are committed together. If one cannot be grounded, that cell
records both claims and the exact refusal while every sibling cell in the batch continues; a run
never retains only one seat because another cell failed.
Every failed seat becomes a visible `no-answer` for each cell it covered. `retry-failed` retries
only those failed first attempts, once, into a new `attempt-002` evidence directory. It preserves
the first bytes and refusal, never launches a third attempt, and leaves a second failure visible
for the owner rather than wedging or silently clearing it.
Disagreement, no-answer, and a defect without grounded words remain distinct owner questions.
Present only the first question, record only an offered verdict, and preserve the owner's words
verbatim. The machine never casts that vote.
If the owner refines a recorded ruling, use `correct-owner`; it keeps the prior version in append-only
history rather than silently replacing it.

`status` may expose progress, but `cell`, `report`, and `document` refuse while any cell is unread.
`report` and `document` also refuse while the owner queue is nonempty. A finished document retains
reader quotations, upstream traces, paired benchmark evidence, and every owner-resolved dispute.
