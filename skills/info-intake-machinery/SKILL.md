---
name: info-intake-machinery
description: Starts and advances a new auditable information intake from only an opening statement. Preserves human answers and files as immutable sources, records readable projections, verifies visual relationships, turns every currently known gap into one code-bound question round, conducts any prepared operator round one question at a time, assesses every completed round against its exact gaps, and prepares immutable follow-up questions for failed clarifications without losing legacy single-gap replay.
---

# Info Intake Machinery

Turn an operator's opening and purpose into the first durable interview stages of an information
intake. Code owns identity, immutable sources and projections, ledger ordering, fixed questions,
model-task boundaries, typed answer validation, canonical assembly, and resume checks. A model
owns semantic judgments and visual reading, but code controls every accepted answer shape.

## Start from only an opening

Run:

```text
python3 scripts/start_intake.py --work <fresh-directory> --opening '<exact operator statement>'
```

Pass the operator's words exactly. The command preserves them as both the original human source
and its first readable projection. It then returns exactly one question:

```text
What information should this intake make AI-readable?
```

Invoke the same command with the same work directory and opening to resume. A resume returns the
same intake identity and question without adding ledger entries. Changed input, altered source or
projection bytes, altered ledger history, or an already-populated unbound directory fails closed.

## Preserve and assess the purpose

After the operator answers, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>'
```

The command preserves the answer as the second source and projection. It returns an exact command
for a code-controlled interview. Run that command and answer only the displayed question. Code
offers only `yes` or `no` for purpose sufficiency. It then conditionally asks for either an exact
source quotation or one focused clarification, rejecting invalid answers without advancing.

Code assembles the fixed assessment schema and asks for the first source only after a valid
sufficient interview. Every rejected and accepted model answer remains in the hash-chained
interview journal, whose final hash and assembled assessment are appended to the intake ledger.

## Freeze the first local file

When the machinery asks for the first source, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' \
    --source '<operator-supplied local file>'
```

Code copies the exact bytes into the intake and records the provided path, resolved origin,
filename, byte count, content hash, detected media type, detection basis, and local-file adapter
version. It records that the readable projection is still pending. This adapter has no rules for
images or any other particular file type. Reusing the same command resumes without another source
occurrence; changed content or origin fails closed. Once frozen, resuming without the original path
remains valid because the intake owns its immutable copy.

## Create the first visual projection attempt

For a frozen image source, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' \
    --project-source
```

The command returns the frozen attachment and an exact command for the code-controlled interview.
Inspect the frozen image, run that command, and answer only its currently displayed question. Code
asks one typed question at a time. It divides the source into a deterministic spatial grid and
requires an explicit `scanned` or `gap` outcome for every region. It generates identities,
constrains each element's anchor to the active region, and binds relationship participants from
source coordinates to exactly one recorded element. A point matching no element or overlapping
elements cannot silently become a relationship: code requires corrected coordinates, capture of a
missing visible endpoint, or an explicit relationship gap. After coordinate binding, code requires
a separate visual verdict of `supported`, `not_supported`, or `unreadable` for the proposed pair.
The proposal is then preserved and a fresh visual-reader run, launched in a new model context,
must independently judge whether the visible relationship terminates at those exact participants.
Only independent `supported` can enter the immutable readable projection. An existing relationship
gap remains in place and is marked ineligible for pair verification because it has no complete
readable pair. Independent `not_supported` or `unreadable` reopens only that readable proposal in a
separate code-controlled correction interview. Code requires either
`propose_replacement_endpoint` or `preserve_gap`; a replacement must identify the origin or target,
select an existing readable element or record a new visible element, and bind a point inside the
selected element. The original proposal and rejection remain unchanged. A second fresh visual
reader judges only the corrected pair. Independent support admits the correction; rejection or an
explicit `preserve_gap` leaves the final relationship as a gap. A producer-side `not_supported` requires corrected
coordinates, capture of a replacement visible endpoint, or an explicit gap; `unreadable` becomes
an explicit gap. Each supported pair resolves only the currently presented relationship obligation,
so another participant's obligation must receive its own visual verdict. It offers only `readable`
or `gap` as status choices after support is established. An answer outside an allowed set is
preserved as rejected and the same question is asked again without advancing.

The model supplies only visual judgments and free text where reasoning is needed: whether another
purpose-relevant unit exists in the active region, its source-neutral kind, its visible content or
concrete gap reason, coordinates inside the two visible relationship participants, and what that
relationship establishes. For each coordinate-bound pair, the model independently judges whether
the visible source supports that connection; code constrains and records the verdict. Code
assembles the canonical projection, including every spatial-region outcome, coordinate evidence,
visual verdict, and the single obligation that verdict resolves, and records the hash-chained
interview journal in the intake ledger. The completed projection is immutable version 1 with
coverage explicitly `unassessed`. No question contains rules for a particular image, annotation
style, color, application, or domain.

To drive every pending visual stage with separate model contexts, run:

```text
python3 scripts/run_projection_with_codex.py
```

Provide the waiting intake directory when prompted. The launcher runs the producer, independent
verifier, correction interview when any readable pair is rejected, and independent correction
verifier when a replacement is proposed. It stops when the intake reaches its terminal result or a
managed stage fails.

## Turn all current gaps into one operator question round

After projection version 1 is recorded with an explicit gap, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' --clarify-gap
```

Code enumerates every explicit gap in canonical projection order and binds each collection,
identity, exact record, record hash, and projection hash before the model runs. One fresh model
process receives those bound gaps one at a time and formulates exactly one focused question for
each. Code keeps the complete round internally; the model cannot omit, duplicate, reorder, or
invent a gap. Every question keeps its own identity and exact gap binding, while the operator sees
only the first unanswered question.

The round request, complete gap list, interview journal, rejected attempts, final question list,
and each operator presentation are appended to the ledger. Answer the displayed question with:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' \
    --gap-answer '<exact answer>'
```

Code first freezes that answer as a new immutable human source and creates its complete verbatim
readable projection. The same ledger entry binds both artifacts to the exact question and gap.
Only then does code record and display the next question. Resume revalidates every question,
answer, source, projection, and ledger link, then returns only the first unanswered question.
Empty answers fail without changing the ledger. After the last answer, the machinery records the
completed round and stops ready for later projection assessment. Existing saved single-gap intakes
remain replayable through their already recorded answer and resolution stages below.

## Assess every preserved question-round answer

After any prepared question round is completely answered, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' \
    --assess-gap-answers
```

The command freezes the complete ordered set of answer-to-gap bindings and returns an exact
code-controlled model command. Run it and answer only the displayed fields. Code presents each
exact gap, question, immutable answer source, readable answer projection, and relevant original
source context in fixed order. It offers only `resolves_gap` or `does_not_resolve_gap`; the model
supplies that judgement and its reason but cannot select, omit, duplicate, reorder, or invent a
binding.

The request, interview journal, rejected attempts, ordered outcomes, and final result are appended
to the intake ledger under the preserved round number. Later rounds do not overwrite earlier
assessment records or artifacts. Resume reconstructs every binding and returns the identical
outcome set. Changed answers, projections, questions, gaps, journals, results, order, identities,
or verdict values fail closed. A second assessment request for the same round is rejected without
changing the ledger. This stage does not change the readable projection, admit an answer, or ask
follow-up questions.

## Admit the next resolving assessed answer

After the complete answer round has been assessed, or for an existing saved single-gap intake with
a preserved relationship-binding answer, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' --resolve-gap
```

For an assessed question round, code selects the next canonical `resolves_gap` outcome that no
earlier admission attempt consumed. On the first invocation this is the first resolving outcome;
after a terminal admission it is the next unused one. Code binds its exact question, immutable
answer source and projection, original assessed gap identity, unchanged gap record and hash,
current parent projection, and accepted assessment into a derived immutable resolution input. If
the gap record changed between projection versions, code refuses the admission. The resolver
cannot reassess the accepted verdict. It receives only the code-listed ambiguous element
identities and the missing relationship facts; an endpoint already recorded in the gap retains its
identity and existing point. The same admission path also accepts a relationship gap with exactly
one recorded endpoint and one missing endpoint. Code locks the recorded identity, offers only
recorded readable identities or one controlled visible-element capture for the missing participant,
and requires points inside both participants when either point is absent. The model supplies the
visible missing participant, coordinates, and relationship meaning; it cannot change the locked
identity.

For a legacy single-gap intake, the returned interview still lets a fresh model judge only whether
the preserved answer resolves that exact bound ambiguity. Code constrains the verdict to
`resolves_gap` or `does_not_resolve_gap`, constrains the selected ambiguous participant to the
recorded candidates, and requires the other endpoint to use a recorded readable element or capture
one visible missing element. Coordinates must fall inside the selected endpoint. When proposed
bounds materially overlap a recorded element, code presents those exact identities and evidence
before allowing the model to choose reuse or a distinct visible element; reuse cannot create a
duplicate identity.

A resolving proposal is not admitted directly. The launcher starts a new model context that checks
the preserved operator answer and both exact visual participants. Only `supported` creates exactly
one new immutable projection version from the current parent. Code replaces only the bound
relationship gap, preserves every earlier version, every other element and relationship, and every
assessment artifact, records parentage and evidence hashes, and appends the request, result,
verification, and version events to the ledger. Before another attempt starts, code archives the
prior terminal attempt and its output projection in append-only state history. `does_not_resolve_gap`,
`not_supported`, or `unreadable` leaves the current parent and its gap unchanged with the reason
recorded. Replay reconstructs every archived attempt and version and rejects changed artifacts.

## Prepare the follow-up question round for failed clarifications

After every already-resolving assessment has been admitted, run the existing clarification request
again:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' --clarify-gap
```

Code selects the complete ordered set of `does_not_resolve_gap` assessments whose exact gap record
still exists in the current projection. It binds each current gap to its prior question, immutable
answer source and projection, and assessment reason, then returns one code-controlled model command.
The model reasons only about the still-missing information and writes one new focused operator
question per bound gap. Code enforces complete coverage, current gap identities, unique round-2
question identities, order, and rejection of an exact repeat of the failed question.

The model request, interview journal, rejected entries, completed round, and operator-ready round
are appended without changing the first question round, its answers, assessments, projection
versions, or resolution history. Resume returns the same prepared round without another ledger
entry. This atomic stage stops with `ready_for_operator_interview`; it does not display a question,
accept an operator answer, or change the readable projection.

## Conduct any prepared operator question round

Once a round is preserved with `ready_for_operator_interview`, start its operator interview with:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' \
    --conduct-question-round
```

Code reads the preserved round number and complete ordered question set; it does not assume round
2. It appends only the first question presentation and returns only that question. Repeating the
command while the round is active returns the same current question without another ledger entry.
Supply each answer separately with the existing `--gap-answer '<exact answer>'` command. Code
rejects an answer before the interview starts, rejects empty or duplicate answers, and cannot skip
or reorder the prepared questions.

Before the next question is shown, each exact answer becomes a new immutable human source and a
complete verbatim readable projection. Its ledger lineage names the prepared-round result, round,
question position, question presentation, active original source, active projection version, and
exact gap binding. After the final answer, code records one round-completion event and stops with
`ready_for_projection_assessment`. It does not assess the answers, create more questions, or alter
the current readable projection.

## Current boundary

Each `--resolve-gap` invocation applies at most the next unused canonical resolving assessment to
one unchanged relationship gap and then stops. Eligible assessed gaps have either a code-listed
identity ambiguity or exactly one known and one missing endpoint. It does not automatically loop
through the remaining assessments. It can prepare one immutable follow-up round from the first
assessment round and conduct any prepared round one question at a time, but it does not yet
admit a later-round resolving answer, decide whether another round is needed, run a question loop
to a grounded terminal condition, accept URLs, or assess whether a projection completely covers its source. Legacy
gap resolution remains limited to an existing preserved single-gap answer bound to a relationship
identity ambiguity. The projection adapter currently accepts images only and fails closed for
other media types. Do not simulate those later units in prose or extend the script while running
these proven stages.

## Status contract

| `status` | Exit | Meaning |
| --- | ---: | --- |
| `needs_operator` | 4 | The intake is waiting for a source, one legacy answer, or one current question-round answer. |
| `waiting_for_model` | 2 | One bounded purpose, projection, question, or answer assessment must be completed. |
| `blocked` | 3 | Input or durable state is missing, changed, or invalid. |
| `ready_for_projection` | 0 | The first local file is frozen and its projection is pending. |
| `ready_for_projection_assessment` | 0 | The current immutable projection version is ready; completeness remains unassessed. |
| `ready_for_operator_interview` | 0 | A complete follow-up question round is preserved but no operator question has been presented. |
