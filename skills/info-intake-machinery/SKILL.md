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
verifier when a replacement is proposed. After each successful model interview it re-enters the
deterministic clarification boundary. It launches only the exact next model command returned by
that boundary. When the boundary returns one current operator question, code presents only that
question, preserves the exact non-empty answer as an immutable source and readable projection,
then re-enters the boundary. It stops only at grounded first-layer completion or a managed failure.
A changed question, mismatched command, attachment, boundary, or exit status fails closed.

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

## Read and execute one deterministic clarification continuation

Every completed answer assessment and every terminal assessed-answer admission returns one
code-computed `continuation` record. It contains exactly one decision:

- `apply_resolving_answer` identifies the canonical unused assessment round, position, and
  unchanged current gap.
- `prepare_next_round` identifies the latest assessed round, its successor round number, and the
  complete ordered set of unchanged gaps whose answers did not resolve them.
- `clarification_complete` means no preserved assessed answer is currently applicable. Its
  remaining current-gap count is evidence, not by itself a claim that projection coverage is
  complete. At this terminal only, code separately qualifies the current projection from its
  canonical coverage evidence.

The classifier takes no model input and changes neither state nor ledger. It reconstructs every
assessment binding from immutable answer sources, projections, question artifacts, and round
history; replay returns the same decision. Incomplete, duplicated, reordered, changed, or unbound
records fail closed.

To execute exactly that decision, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' \
    --continue-clarification
```

Code recomputes the decision against current immutable evidence immediately before dispatch. It
then performs exactly one existing transition: start the bound admission request, start preparation
of the bound successor round, or append the grounded clarification-terminal event. It stops before
any model or operator answer. Repeating the command while work is active cannot create another
request, artifact, or ledger event; replaying the terminal decision returns its preserved result.
A stale round, position, gap set, or projection fails closed.

The terminal event and result contain exactly one `projection_qualification`. Code first verifies
the immutable projection identity, all sixteen ordered scan-region outcomes, unique element and
relationship identities, consistent region-to-element membership, closed relationship
obligations, and projection-record counts. With no explicit gaps the value is
`readable_projection_complete`. With gaps it is `readable_projection_incomplete` and carries every
exact gap record in canonical region, element, then relationship order. Missing, duplicated,
reordered, contradictory, or changed coverage evidence returns `terminal_invalid` without writing
the terminal event. The qualification takes no model answer and does not mutate the projection.

A deterministic disposition gate then decides what that qualification permits. Only
`readable_projection_complete` with zero exact gaps becomes `first_layer_complete` and may append
the clarification-terminal event. `readable_projection_incomplete` becomes
`clarification_required` with the same exact ordered gaps and writes no completion event.
Contradictory decision counts, qualification counts, or gap lists become `terminal_invalid`.
This gate does not formulate questions, run interviews, or alter the projection.

Any model work started by this dispatcher remains accepted only through its code-controlled,
one-question-at-a-time interview with enforced choices and persisted rejected and accepted attempts.
The executor does not run an interview or loop.

## Resume to the next clarification boundary

Use one entry point instead of choosing the next machinery command yourself:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --clarification-boundary
```

The controller validates and consumes any already-persisted interview result, then performs only
code-owned transitions until it reaches exactly one typed boundary:

- `needs_model_interview` returns exactly one existing code-controlled interview command and stops.
- `needs_operator_answer` returns exactly one current prepared question and stops.
- `clarification_complete` returns the preserved grounded terminal result plus its exact complete
  projection qualification and `first_layer_complete` disposition, then stops.

`clarification_required` is an internal continuation, not an external boundary. The controller
uses its exact ordered remaining gaps to request the next complete follow-up question round, then
returns that round as `needs_model_interview`. It never invents, presents, or answers a question.

The controller never executes a model interview and never supplies or accepts an operator answer.
After that external response has entered through its existing code-controlled interview or
immutable human-source path, run the same boundary command again. Repeating it before a response
returns the identical boundary without another request, artifact, question presentation, or ledger
event. Invalid or stale state fails closed. This is a resumable external-boundary controller: all
internal code-owned transitions are automatic, while model interviews and operator answers remain
external work.

## Admit the next resolving assessed answer

After the complete answer round has been assessed, or for an existing saved single-gap intake with
a preserved relationship-binding answer, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' --resolve-gap
```

For any assessed question round, code selects the next canonical `resolves_gap` outcome that no
earlier admission attempt consumed. The immutable selection identity is the round plus its answer
position, so position 1 in a later round cannot collide with position 1 in round 1. On the first
invocation this is the first resolving outcome; after a terminal admission it is the next unused
one. Code binds its exact question, immutable
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
recorded. A first independently rejected assessed-answer proposal starts one bounded correction
attempt instead of asking the operator the same question again. Code freezes the rejected proposal,
verifier verdict, and exact verifier reason into the next attempt; the retry model must reselect both
relationship endpoints from complete code-listed readable-element choices and provide coordinates
inside those selected bounds. The same independent verifier then decides whether the correction is
admissible. A second rejection stops as `gap resolution retry exhausted`, preserving the human
answer and both model attempts for later machinery policy; it does not silently loop or create a
human question. If a rejected assessed-answer attempt was archived before this retry path existed,
code recovers the oldest such attempt whenever its exact unchanged gap still exists and no later
attempt already names it as `retry_of`. The current projection becomes the retry parent while the
original answer, failed proposal, verifier verdict, and verifier reason remain the immutable retry
evidence. Replay reconstructs every archived attempt and version and rejects changed artifacts.

## Prepare the follow-up question round for failed clarifications

After every already-resolving assessment has been admitted, run the existing clarification request
again:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' --clarify-gap
```

Code starts from the latest completed assessed round. It selects that round's complete ordered set
of `does_not_resolve_gap` assessments whose exact gap record still exists unchanged in the current
projection. It binds each current gap to its prior question, immutable answer source and projection,
and assessment reason, then returns one code-controlled model command. The model reasons only about
the still-missing information and writes one new focused operator question per bound gap. Code owns
the successor round number, complete coverage, current gap identities, unique question identities,
order, and rejection of an exact repeat of the failed question.

Before preparing round N+1, code archives round N's prepared question record and operator interview
as an ordered replay-validated snapshot. The model request, interview journal, rejected entries,
completed round, and operator-ready round are appended without changing any earlier question round,
answer source, assessment, projection version, or resolution history. Resume reconstructs archived
rounds from their immutable artifacts and ledger identities; changed gaps, omissions, duplicates,
reordered bindings, repeated questions, or altered archived artifacts fail closed. This atomic stage
stops with `ready_for_operator_interview`; it does not display a question, accept an operator answer,
assess the new round, decide whether another round is needed, or change the readable projection.

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

Each `--resolve-gap` invocation applies at most the next unused canonical resolving assessment from
any completed round to one unchanged relationship gap and then stops. Eligible assessed gaps have either a code-listed
identity ambiguity or exactly one known and one missing endpoint. It does not automatically loop
through the remaining assessments. It can prepare exactly one immutable successor round from the
latest completed assessed round and conduct any prepared round one question at a time. It returns
one deterministic continuation decision and can execute exactly one corresponding transition, but
its boundary controller still stops for every model interview and operator answer; it does not run
external work or a fully automatic question loop
to a grounded terminal condition or accept URLs. Its terminal qualification verifies the recorded
coverage contract and explicit gaps, and its disposition gate prevents an incomplete projection
from ending the first layer. Its boundary controller turns `clarification_required` into the next
complete follow-up question-round request, but does not perform the later semantic projection
assessment against the source. Legacy
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
| `ready_for_projection_assessment` | 0 | The current immutable projection version is ready. Before clarification terminal, completeness remains unassessed; the terminal result includes the code-derived projection qualification. |
| `ready_for_operator_interview` | 0 | A complete follow-up question round is preserved but no operator question has been presented. |
