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
# For a declared deliverable profile, derive its payload and complete producer set:
python3 scripts/critique.py open --page <page.md> \
  --from-run <state.json> --deliverable tactical_roadmap \
  --work <repo/Tasks/task/runs/name> --no-reference "<recorded reason>"
python3 scripts/critique.py status --work <work>
python3 scripts/critique.py read-run --work <work>
python3 scripts/critique.py retry-failed --work <work>
python3 scripts/critique.py read-cell --work <work> --id <unit::lens>
python3 scripts/critique.py ask-owner --work <work>
python3 scripts/critique.py answer-owner --work <work> --id <decision-id> \
  --choice <offered-verdict> --because "<owner's exact words>"
python3 scripts/critique.py rule-bulk --work <work> --assessment <assessment.md> \
  --by "<owner's words>"
python3 scripts/critique.py correct-owner --work <work> --id <recorded-decision-id> \
  --choice <offered-verdict> --because "<owner's corrected words>"
python3 scripts/critique.py document --work <work> --out <findings.md>
python3 scripts/critique.py located --work <work> --only disputed
python3 scripts/critique.py trend --work <run-v1> --work <run-v2> --work <run-v3>
```

`open` requires exactly one benchmark-source declaration: a reference id plus page, or a non-empty
`--no-reference` reason. In a no-reference run, benchmark cells are recorded as not applicable and
are never sent to readers; `status` and the finished document retain the reason. This is not a
`clear` benchmark judgment.

`open` separately requires exactly one upstream-source declaration: one or more repeated
`--upstream-source <id>=<state.json#context.key>` values, or a non-empty `--no-upstream` reason.
In a no-upstream run, upstream cells are recorded as not applicable, never sent to readers, and
retain the reason in `status` and the finished document. Registered producer text is shown to each
seat. An upstream reject or revise must name one registered source and select exact numbered words.
Code accepts an exact passage of at least 25 collapsed characters or an entire line of the
registered source; the seat instruction and refusal state that same rule. A claim that cannot
satisfy it becomes an owner question with both raw seat claims and the exact refusal. It never
disappears, and `document` remains blocked until the owner rules.

`open --from-run --deliverable` is a bounded derivation mode, not a new declaration class. It
prints the payload key and complete producer registry it derived, and refuses before opening if the
deliverable profile or any consumed producer is absent. Use the explicit flags for deliverables
without a declared profile.

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
`rule-bulk` accepts only a complete summary table plus numbered grounding blocks for the current
queue. It checks every row, choice, lens, and grounding before writing any ruling; any mismatch
files nothing. The `--by` words are preserved before the drafted-by-reader marker.

Use `located` to inspect stored line spans without a reader call. `disputed` includes disagreements
and agreement defects, `defects` includes agreed or owner-resolved defects, and `all` includes every
applicable cell with both stored seats. It reads the run's own reader-response and source records;
missing or invalid evidence refuses instead of reconstructing words.

`trend` is the one measure that survives across versions. Given completed runs of one deliverable,
it counts each run's located defects by the exact rule the report uses — agreement-defect cells plus
owner-resolved cells ruled revise or reject — orders the runs by the version their bound page names,
and prints each count with its delta from the previous comparable run and the direction of the
whole series. A run whose reading or owner queue is unfinished is listed with its reason and never
compared. Runs of another deliverable, a page that names no version, or two runs of one version
refuse, naming the runs. It spends no reader call and reads only the runs' own records; a project's
goal store reads this command rather than composing a per-round number.

`status` may expose progress, but `cell`, `report`, and `document` refuse while any cell is unread.
`report` and `document` also refuse while the owner queue is nonempty. A finished document retains
reader quotations, upstream traces, paired benchmark evidence, and every owner-resolved dispute.

## The code-owned consistency lens

The eighth lens, `payload-consistency`, has no reader. For a deliverable opened with
`--from-run --deliverable`, run

```bash
python3 scripts/critique.py consistency --work <work>
```

after `open` and before `read-run`. Code reads the bound payload against the page and fills both
seats of that lens on every unit a declared check reads: a located `revise` where the page
contradicts the payload (a map cell against a card's span, a stage's months against the spans of
the cards it names, the calendar rows against a span, the loop's deployment month against the
equipping card, the widening month against the Launch span), `clear` where it does not, and
`not-applicable` with its reason where no check reads the unit or the page carries no field the
check reads. A run opened with explicit `--payload` flags records the lens as not applicable
because no profile declares checks. Both seats are code and always agree, so the lens never raises
an owner question; `read-run` never sends it to a reader, and `read-cell` refuses it. The evidence
is the same shape as a reader's — a response with the lens, verdict and unit lines under
`reader-evidence/code-<unit>/` — plus every compared fact, and the findings document prints each
contradicted fact under its cell. A page that contradicts itself across units was invisible to the
unit-by-unit seats: on 2026-09-05 both seats cleared a B Team map whose Senior craft story series
read "Sustain" while the card ran Months 6 to 12; this lens locates five such rows on that page.
