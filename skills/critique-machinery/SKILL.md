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
starts every seat in an isolated working directory with client-specific instruction and capability
controls, and supplies an exact schema through the client's structured output control. Codex
admits only the completed assistant-only trace described below; Claude uses its existing
restricted tool and settings controls. The reply intake accepts exactly one schema-valid JSON object and records exactly
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
the cards it names, the explicit calendar month/phase fields against their bound calendar entries, the loop's deployment month against the
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


## Individual findings (reader contract 2)

New reader replies carry a findings list per lens. Each finding has its own page span,
registered producer span when relevant, reason, and concrete consequence. A clear reply
has no findings. Every finding survives intake, storage, owner inspection, located output,
and the completed document. An ungrounded item remains visible and keeps the owner queue
open; two matching aggregate verdicts do not establish agreement on different finding lists.
Historical replies remain interpreted against their captured schema; they are never rewritten
into the new format.

Use `findings --work RUN` to inspect all grounded and unresolved findings with their reader,
lens, source, and owner provenance. Automatic consolidation only joins identical grounded
evidence, reasons and consequences. Differently worded claims may still describe the same
problem. This inventory is not an independent repair count. The existing defect-cell count
remains separately labeled as a legacy measure.

When the owner explicitly confirms that differently worded entries describe one problem,
record that decision with `group-findings --work RUN --finding ID --finding ID --because
"the owner's exact words"`. The selected IDs must be grounded entries in the same run.
All original observations remain visible alongside the owner grouping. Never supply this
owner decision on the reader's behalf.


## Whole-artifact counterevidence

Public `read-cell`, `read-run`, and `retry-failed` supply the entire bound delivered
page (including its headings and preamble), every numbered unit, and the complete
selected payload. Code rechecks page, state, payload and unit identity before sending
it; it never clips this context. Each reader's evidence preserves artifact-context.json
and its hash in the input envelope and intake.

Before alleging absence, readers inspect that context for the strongest counterevidence.
A relationship legitimately expressed elsewhere must not be demanded again in every
unit. Hidden payload data does not prove that a required visible statement is rendered.
An absence finding explains why the available counterevidence does not fulfill the
actual registered commitment. This is semantic reader judgment, not a code proof of
absence. Direct internal reads without whole-artifact context are labeled unit-only and
must not claim whole-artifact absence. Reader questions derive expectations from the
artifact's purpose and registered evidence, without imposing a calendar or annual format.


Before selecting final findings, readers inventory all explicit source commitments
relevant to the selected unit and inspect each separately against the complete artifact.
Individually specified measures and obligations are not replaced by one broad outcome
check. The inventory is a reader instruction, not a deterministic completeness guarantee;
real unfocused reads must establish whether it improves recall.


## Verify one correction

Use `verify-correction --before BEFORE_RUN --after AFTER_RUN --finding FINDING_ID
--after-unit UNIT_ID --out NEW_RECEIPT_DIRECTORY` after the artifact's own renderer has
produced the revised page and the after run has been opened. The receipt directory must
be new and outside both runs. Critique does not rewrite or render the artifact.

The command verifies immutable page/payload/source bindings and checks the existing
grounded finding against unchanged source commitments. Two blind readers first re-establish the original defect on the before artifact, then
two blind readers assess the after artifact against the same finding. Corrected requires
both before readers to find the defect and both after readers to find its criterion
fulfilled, with an actual artifact change. Both after readers retaining the established
defect means not-corrected. An unestablished original finding, mixed, invalid or ungrounded
responses mean cannot-assess. Raw reader evidence and the scoped receipt remain available.

The result is always specified-finding-only. The receipt exposes unread after cells,
open owner questions, other known after findings, and other before findings explicitly
not reassessed. It never clears the whole card or artifact, changes a run's existing
reader state, invents an owner ruling, or assumes other before findings still exist.


Reader attempts have a 180-second deadline, recorded in each input envelope. Timeout kills
the isolated reader process group, including its launcher and child; successful launchers
also release remaining group members. The attempt remains a visible timeout/no-answer.
This default preserved all 45 successful durations in the captured September 6 round; it
is not a guarantee that future useful replies always finish within three minutes. Retry
remains a separate explicit operator action, never an automatic second three-minute wait.


During `read-run`, each complete blind pair is recorded as soon as both replies finish.
`status` and `findings` can expose that evidence while other readers run; `reader-progress.jsonl`
records finished reader identities, outcomes, and completed-pair counts. Matrix publication
is atomic. No single-seat claim is presented as a completed pair, and unread cells still
block `report` and `document`. This changes evidence availability, not semantic judgments.

### Codex reader isolation

The reader invocation omits ambient skill instructions and project documentation and disables shell, plugin, app, browser, image, collaboration, hook, and workspace dependency capabilities without changing model defaults or authentication. This does not assert an empty tool schema. The preserved Codex JSON event trace must complete one answered turn containing only assistant/reasoning items, and its final assistant text must match the preserved reply. Tool use, unknown events, failed or incomplete traces, and mismatched replies are classified as malformed; they cannot become accepted blind evidence. Claude retains its existing client-specific controls.


The calendar consistency check compares explicit rendered month/phase fields with the bound calendar entries. It does not infer that a card must be named in every month of its active span: that is a separate completeness requirement that the profile does not declare. Unsupported table shapes and historical pages without the span profile remain not applicable. The other declared checks, including the cross-section map-versus-card-span check, are unchanged.

## Review repeated observations together

After reading is complete, use `suggest-groups --work RUN --out NEW_RECEIPT_DIRECTORY` to propose issue groups without merging observations or casting owner votes. Optionally repeat `--finding ID` to freeze a bounded selection; the receipt lists all findings outside that selection as unassessed. Owner-confirmed groups are excluded from new proposals.

Two isolated readers independently partition the selected grounded observations. Code requires complete, exact-once identity coverage and proposes only intersections containing at least two findings that both readers placed together. Different unmet commitments remain distinct even when they share a source line, page span, owner, or possible edit. This is semantic advice, not proof of equivalence or an independent repair count.

The receipt's `review.md` preserves every proposed group's member IDs and original reasons, both reader explanations, and all observations left separate. Raw prompts, schemas, replies and event traces remain beside it. Failed or malformed proposal readers produce no groups. Every reader has the existing 180-second process-group bound and client isolation controls; no retry is automatic. A changed critique matrix refuses proposal admission.

Existing `findings`, `ask-owner`, `group-findings` and owner rulings keep their meanings. Apply a proposed group with `group-findings` only after the owner explicitly confirms equivalence and supplies the recorded reason. The machinery never supplies that approval itself.

## Qualify a full-round experiment

After opening a new run, before any model reading, freeze a JSON list of acceptance criteria with `plan-quality --work RUN --criteria FILE`. Each criterion has exactly id, unit_id, lens and requirement strings and names an applicable model cell. Define the criteria from independently checked real failures and successes before running a candidate. The plan binds the complete artifact, source registry, unit manifest and exact reader implementation. Changing those inputs requires a new run.

Run the ordinary complete `read-run`, then `assess-quality --work RUN --out NEW_DIRECTORY`. Focused reads, missing replies and failed transports cannot qualify as a complete round. An isolated observer assesses both original seats separately for each frozen criterion, citing original observation words. Every criterion must be satisfied; an unknown result cannot qualify. Raw observations, prompts, traces and refusals stay visible. The command does not change findings, owner decisions, the artifact, or promotion state.

This is acceptance against the declared criteria, not proof that every possible defect was found. A later discovered full-round failure must become a frozen regression criterion before another candidate comparison; a focused probe passing never replaces this full-round check. Observers remain fallible: inspect the cited raw evidence and calibrate proposed criteria on known positive and negative records before relying on a new acceptance set.

## Quality assessment after bounded recovery

For a round with a frozen quality plan, `retry-failed` preserves the original execution witness
and every original reader attempt. A successful bounded retry adds a hash-bound recovery receipt
that `assess-quality` verifies before accepting the recovered round. A failed retry remains
unassessed; it never triggers a third attempt. Changed retained evidence or criteria invalidate
the receipt. Preserve an interrupted recovery for diagnosis instead of rerunning the round.

Quality observers select an evidence identifier belonging to the reader being assessed. Code
copies the exact original text into the assessment. Missing or wrong-reader evidence is refused.
These checks establish evidence integrity, not correctness of the model's semantic judgment.

## Declared quality checks remain visible

`status` and `report` show `quality_assessment` separately from reading completion and
owner decisions. `document` includes the same declared-check outcomes. An unassessed plan
remains pending. After `assess-quality`, every declared criterion remains visible even if
its result is not-satisfied or cannot-assess. Reports preserve findings and owner rulings.

The assessment pointer binds the retained receipt to the current plan, matrix and input hashes.
A changed or missing receipt or changed inputs appear as stale; no previous passing verdict
survives that change. Run `assess-quality` into a fresh receipt to assess the current state.
Runs without a plan explicitly say not-planned. These statuses cover only declared checks;
they do not establish complete source coverage or improve semantic reader recall.
