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
  --reference <stable-id> --reference-page <reference.md>
# Or, only when no real reference exists:
python3 scripts/critique.py open --page <page.md> \
  --payload <state.json#context.key> --work <repo/Tasks/task/runs/name> \
  --no-reference "<recorded reason>"
python3 scripts/critique.py status --work <work>
python3 scripts/critique.py read-run --work <work>
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

Before a defect can be recorded under `upstream-trace`, register its producer with
`register-source` and attach exact producer words with `trace`. Before a defect can be recorded
under `benchmark-vs-reference`, register the reference page with `register-reference` and attach
exact words from both texts with `benchmark`. Do not substitute labels, paraphrases, or model
memory for those records.

Run each judgment through both fixed blind seats. The installed client projection owns the reader
runtime; the script refuses an unavailable or invalid runtime rather than switching clients.
Disagreement, no-answer, and a defect without grounded words remain distinct owner questions.
Present only the first question, record only an offered verdict, and preserve the owner's words
verbatim. The machine never casts that vote.
If the owner refines a recorded ruling, use `correct-owner`; it keeps the prior version in append-only
history rather than silently replacing it.

`status` may expose progress, but `cell`, `report`, and `document` refuse while any cell is unread.
`report` and `document` also refuse while the owner queue is nonempty. A finished document retains
reader quotations, upstream traces, paired benchmark evidence, and every owner-resolved dispute.
