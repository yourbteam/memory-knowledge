---
name: info-intake-machinery
description: Starts and advances a new auditable information intake from only an opening statement. Preserves human answers, files, and public URLs as immutable sources, collects any number of independent sources through a one-question-at-a-time code interview, records readable projections, verifies visual relationships, reconstructs one source-to-projection outcome for every intake source, qualifies every collected projection against its exact adapter evidence, admits that qualification as either Layer-One completion or an immutable ordered clarification queue, turns every currently known gap into one code-bound question round, conducts any prepared operator round one question at a time, assesses projected additional-source evidence and completed answer rounds against their exact gaps, and prepares immutable follow-up questions without losing legacy replay.
---

# Info Intake Machinery

Turn an operator's opening and purpose into the first durable interview stages of an information
intake. Code owns identity, immutable sources and projections, ledger ordering, fixed questions,
model-task boundaries, typed answer validation, canonical assembly, and resume checks. A model
owns semantic judgments and visual reading, but code controls every accepted answer shape.

## Start from only an opening

For the complete operator entry path, run the zero-input launcher:

```text
python3 scripts/run_intake.py
```

Code asks one question at a time. It first selects `new` or `resume`, obtains the intake work
directory, and, for a new intake, preserves the operator's exact opening words. A statement such
as `There is a new intake` is sufficient to begin. It then collects the purpose, sends the
preserved purpose through its code-controlled model interview, accepts the first source only as a
code-selected `local_file` or `url`, freezes it, and hands every subsequent model and operator
boundary to the existing projection driver. Resume reconstructs the preserved opening and purpose
and continues from purpose assessment, first-source acquisition, first projection, or any later
supported boundary without asking the operator to repeat saved answers. The launcher contains no source-, image-, annotation-,
or domain-specific rule.

For a bounded visual resume, code can limit the invocation by completed spatial regions or by
completed relationship outcomes. It accepts only a positive whole-number limit and counts only
outcomes preserved in the immutable projection journal.

The stage commands below remain the deterministic replay and diagnostic interface used by that
launcher.

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

## Freeze the first file or public URL

When the machinery asks for the first source, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' \
    --source '<operator-supplied local file>'
```

Use `--source-url '<public HTTP(S) URL>'` instead of `--source` for a web source.

Code copies the exact bytes into the intake and records the provided path, resolved origin,
filename, byte count, content hash, detected media type, detection basis, and local-file adapter
version. It records that the readable projection is still pending. This adapter has no rules for
images or any other particular file type. Reusing the same command resumes without another source
occurrence; changed content or origin fails closed. Once frozen, resuming without the original path
remains valid because the intake owns its immutable copy.

For a URL, code permits no credentials, resolves and connects only to public addresses, rechecks
every redirect, follows at most five, accepts only a successful response, and reads at most 20 MiB.
It preserves the supplied and final URLs, complete redirect trail, response status and headers,
address evidence, retrieval time, and exact response bytes. Resume never fetches it again.

## Create the first readable projection

For the frozen first file or URL, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' \
    --project-source
```

Code selects the adapter from the frozen source. If every byte is valid UTF-8, it writes those
exact bytes as projection version 1, records complete one-to-one coverage, and stops at
`first_source_projection_complete` without a model call. Decoding must round-trip to the frozen
bytes, so the adapter performs no Unicode normalization or other rewriting. Invalid UTF-8 fails
closed: the pending acquisition reservation remains visible and no projection ledger entry is
written. For an OOXML spreadsheet, code identifies the workbook from its media type or package
content declaration, follows the workbook relationship graph rather than assuming numbered sheet
paths, and writes deterministic JSON containing sheet order, names, visibility, cells, stored
values, formulas, styles, merges, and a hash/size inventory of every package part. Every package
part receives exactly one `represented` or explicit `gap` coverage outcome. A malformed workbook
records one immutable failed conversion outcome with its exact reason. Neither path calls a model.
For an image, code instead starts the visual projection path below.

The command returns an immutable crop of the first active region and an exact command for the
code-controlled interview. Inspect that crop, run the command, and answer only its currently
displayed question. Code asks one typed question at a time. It divides the source into a
deterministic spatial grid and keeps each non-overlapping normalized region as its ownership core.
It expands that core toward later traversal regions by a fixed, clipped context margin, maps both bounds to exact source pixels,
renders a clean context PNG plus a companion ownership guide, and journals the source hash, core
and context normalized bounds, core and crop pixel bounds, both paths and hashes, and both adapters
before the model can judge that region. The clean crop preserves readable evidence. Its companion
guide outlines the exact active core in bright green and dims context-only pixels; neither artifact
may be missing or changed on replay. After the model names a candidate kind, code offers only
`owned_by_active_core` or `context_only`. An owned candidate continues to coordinates, where code
still requires its left/top anchor inside the active core. A context-only candidate creates no
element or relationship obligation in the active region. The model supplies that candidate's
top-left ownership anchor; code validates the point is inside the visible context but outside the active core,
calculates the one later core that owns it, and appends an immutable deferral tied to the exact
source region, owner region, point, clean crop, guide, and candidate kind. The owner region receives
a pending candidate obligation before its ordinary scan. Code offers only `record_owned_element`
or `record_explicit_gap`, and that region cannot finish while any such obligation remains pending.
An owned resolution must contain the deferred point and creates exactly one ordinary element;
an explicit gap creates one point-anchored gap element so existing qualification and clarification
machinery must count it, without inventing readable content. When an owned proposed element spatially intersects a recorded element, code lists the
exact colliding identities and offers only
`distinct_unit` or `same_unit`. The model decides semantic unit identity. `distinct_unit` continues
ordinary capture. `same_unit` requires selection of one code-listed identity, complete bounds that
contain both records, and complete readable content or an explicit gap. Code appends an immutable
supersession event containing the original element, triggering candidate, and replacement; it never
overwrites history or creates a second relationship obligation for the same unit. Code accepts
exactly one `scanned` or `gap` outcome for the active region, journals that outcome against the same
crop, and stops the model run. Only then can the launcher attach the next region's distinct crop in
a fresh model context. Crop bytes cannot be missing or changed on resume. After every region has an
outcome, the full frozen source is attached for cross-region relationship work. Code generates identities,
constrains each element's anchor to the active region, and binds relationship participants from
the pending obligation and source coordinates. The model first chooses whether the exact
code-required element is the relationship origin or target. Code locks that element identity and
accepts only a point inside its unchanged complete bounds; the model cannot substitute a different
participant. Only the other participant is discovered from source coordinates. A point matching no element or overlapping
elements cannot silently become a relationship: code requires corrected coordinates, capture of a
missing visible endpoint, selection of one exact overlapping recorded identity, or an explicit
relationship gap. For an overlap, code presents only the exact matching element IDs together with
their complete recorded evidence as a constrained enum. The model selects one identity; code
validates that it is one of the point-containing candidates and binds it without changing any
element bounds. Historical bound-refinement events remain replayable, but before a journal resumes,
code appends migration events that restore still-active prior bounds, preserve supported
relationships whose selected participant identity remains grounded, and reopen only false gaps or
relationships whose participant identity no longer holds. No prior source, answer, relationship,
or journal entry is overwritten. Legacy gaps that omitted their required participant are likewise
invalidated and reopened by append-only migration before command generation. The launcher selects
its obligation only after these deterministic preparations, so the displayed and executed command
cannot retain a stale pre-migration obligation. After coordinate binding, code requires
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
an explicit gap. A supported readable pair resolves the currently presented relationship obligation.
Code then appends a reconciliation event for every still-pending obligation held by either exact
participant, binding those closures to the same relationship without another model verdict; unrelated
obligations remain pending. It offers only `readable` or `gap` as status choices after support is established. An answer outside an allowed set is
preserved as rejected and the same question is asked again without advancing.

Each generated relationship command is bound to the exact next pending obligation. One model
context may preserve exactly one readable relationship or explicit relationship gap and then
returns. The launcher can stop after a code-selected positive relationship count; replayed or stale
commands fail before another outcome is written.

The model supplies only visual judgments and free text where reasoning is needed: whether another
purpose-relevant unit exists in the active region, its source-neutral kind, its visible content or
concrete gap reason, coordinates inside the two visible relationship participants, and what that
relationship establishes. For each coordinate-bound pair, the model independently judges whether
the visible source supports that connection; code constrains and records the verdict. Code
assembles the canonical projection, including every spatial-region outcome, coordinate evidence,
visual verdict, and every participant obligation reconciled to that verdict, and records the hash-chained
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
question and its code-controlled answer type. Text becomes an immutable source and verbatim
projection. A requested local file first becomes a new immutable source with a reserved projection.
The boundary then selects that exact pending source and validates its question and gap lineage.
Valid UTF-8 is copied verbatim without a model; images run the same code-controlled visual
producer, independent verifier, and correction stages under a source-specific artifact namespace.
After the reserved projection is filled, code binds the exact original gap, original and current
projection hashes, additional projection, and every readable evidence identity. A fresh model may
choose only `resolves_gap` or `does_not_resolve_gap`; a resolving verdict must select one or more
code-listed evidence items one at a time before giving its reason. The immutable assessment never
changes either existing projection. When that verdict binds exactly one readable element to one
unchanged element gap, code creates one immutable child projection that fills only that element
and records the complete source, evidence, assessment, gap, and parent lineage. No second model
judgment can rewrite the accepted verdict. The launcher otherwise stops only at a grounded boundary.
A changed question, mismatched command, attachment, boundary, or exit status fails closed.

## Collect independent sources before semantic assessment

After any source reaches a projected or explicitly failed conversion outcome, the zero-input
launcher starts a code-controlled source-collection interview. It asks exactly one question at a
time. The operator first chooses only `add_source` or `finish_sources`. `add_source` then asks only
`local_file` or `url`, requests that one source, freezes it under the next ledger-derived identity,
and sends it through the existing adapter selected from its immutable bytes. After that source has
a terminal projection outcome, code asks the add-or-finish question again. No model chooses these
enum values and no prompt instruction is trusted to enforce them.

The three maintained product probes are `source_collection_decision.py`,
`source_collection_reservation.py`, and `source_collection_closure.py`. Decision constrains the
operator action, reservation derives a collision-free source/projection pair from exact ledger
identities, and closure reconciles exactly one terminal outcome for every declared source. They
remain separate repair boundaries; the launcher only composes their accepted results with the
existing acquisition and projection adapters.

`finish_sources` appends an immutable collection-completion event only after exact reconciliation.
Missing, duplicate, unknown, or pending outcomes refuse closure and name the affected source.
Replay rehashes all source and projection artifacts and returns the same completed source set
without another question or ledger entry. This stage does not compare sources, decide what another
source is needed to explain, assess whether one source resolves another, or contain rules for
annotations, spreadsheets, generators, dashboards, or any other domain. Those are later semantic
assessment responsibilities.

## Qualify the complete collected source set

On the next clarification-boundary resume after `source_collection_complete`, code qualifies the
whole collected set at `source_set_qualification_complete`. Three maintained product probes remain
independently repairable:

- `source_qualification_binding.py` binds every closure outcome to the exact source identity,
  projection ledger sequence, projection identity, version, path, and SHA-256;
- `source_projection_qualification.py` applies the evidence contract of the adapter that created
  each projection: exact byte preservation for verbatim UTF-8, complete part accounting for OOXML
  spreadsheets, page and explicit-gap accounting for PDFs, and the existing sixteen-region visual
  qualification contract for images;
- `source_qualification_reconciliation.py` requires exactly one qualification for every collected
  source and restores collection order, refusing missing, duplicate, unknown, or invalid outcomes.

Each source receives exactly one of `readable_projection_complete`,
`readable_projection_incomplete`, or `conversion_incomplete`. The intake-wide result is
`readable_source_set_complete` only when every source projection is complete; otherwise it is
`readable_source_set_incomplete` and retains every exact adapter gap, including the specific
spreadsheet package part, PDF page item, or visual projection unit that did not become readable.
Code appends one hash-chained `source_set_qualification_completed` event containing the unchanged
source-projection closure and the ordered qualification. Replay recomputes the result from the
immutable artifacts and adds nothing.

This qualification performs no semantic comparison between sources, does not decide whether one
source explains another, and does not formulate operator questions. It establishes the complete,
auditable input to the deterministic admission below.

## Admit qualification to completion or clarification

The same launcher then derives one route from every exact source outcome. Three additional product
probes remain separate repair boundaries:

- `qualification_terminal_disposition.py` recomputes the intake-wide status from every source and
  refuses contradictory aggregate or gap evidence;
- `clarification_obligation_binding.py` converts every incomplete unit, in source and gap order,
  into an obligation bound to its source, projection, adapter method, reason, qualification event,
  and gap SHA-256;
- `qualification_admission_publication.py` permits only `first_layer_complete` with no obligations
  or `clarification_required` with at least one exact obligation.

Code appends one hash-chained `qualification_admission_completed` event. Replay requalifies the
immutable artifacts, reconstructs the same route and obligations, verifies the preserved event,
and appends nothing. `first_layer_complete` means every collected source has a complete readable
projection. `clarification_required` exposes one ordered queue for the later question-formulation
step. This admission itself performs no model call, semantic source comparison, or question
formulation, and contains no source-type or domain exception.

## Turn all current gaps into one operator question round

After projection version 1 is recorded with an explicit gap, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' --clarify-gap
```

Code enumerates every explicit gap in canonical projection order and binds each collection,
identity, exact record, record hash, and projection hash before the model runs. One fresh model
process receives those bound gaps one at a time. For each, code offers only `operator_text`,
`local_file`, or `url`; the model chooses which evidence the operator must supply, then formulates exactly
one focused question. Code keeps the complete round internally; the model cannot omit, duplicate,
reorder, or invent a gap or response type. Every question keeps its own identity, required response
type, and exact gap binding, while the operator sees only the first unanswered question.

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

For `local_file`, supply one existing file through the one-question operator command, or directly
with `--gap-file '<path>'`. Text, a missing path, or a directory is rejected without advancing.
Code freezes the exact bytes under the next source identity and records origin, hash, media type,
exact question and gap lineage, and a reserved projection identity with `pending` coverage. It then
stops at `additional_source_frozen`; acquisition itself does not project or combine the file or
present the next question. Re-enter the clarification boundary to dispatch the applicable adapter.
Valid UTF-8 fills that exact reserved identity verbatim without a model. An OOXML spreadsheet fills
the same reserved identity with the deterministic workbook projection and complete part-accounting
outcomes, then stops before semantic source-to-gap assessment. An image fills it using
complete spatial traversal. Both proceed to the exact source-to-gap assessment above. A non-image
whose complete bytes are not valid UTF-8 fails closed without changing the source, reservation,
or ledger.

For `url`, supply one public address through the one-question operator command or directly with
`--gap-url '<URL>'`. Code applies the same retrieval controls and freezes one new URL source with
the exact question, gap lineage, and pending projection identity before conversion.

For a flat, unencrypted PDF, code inspects attachments, forms, JavaScript, encryption, and page
count, then renders at most 100 visible pages to bounded PNGs. It hashes every rendering and sends
one page at a time, in fixed page order, through the same code-controlled spatial interview and
independent relationship verification used for images. Only after every page has an accepted
outcome does code create one ordered PDF manifest and fill the reserved projection identity. The
manifest freezes every explicit gap with its page, exact item identity and record, page projection, and rendered-page hashes. Code sends all affected pages to one model question-formulation pass in
page order, then the existing interview presents the resulting questions to the operator one at a
time. A PDF with explicit gaps cannot stop as projection-complete. Malformed or unsupported PDFs
preserve one immutable failed projection outcome with the exact reason. Missing, changed,
incomplete, reordered, or unbound page artifacts and gap identities fail closed.

## Close the source-to-projection inventory

Run the deterministic closure gate with:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --source-projection-closure
```

Code reconstructs every `source_projected` and `source_acquired` entry and every later
`projection_version_created` entry from the immutable hash-chained ledger. It validates each
source and projection artifact against its path and SHA-256, preserves the acquisition-time
reservation, orders projection versions, and returns exactly one outcome per source. `projected`
names the latest immutable projection; `pending` retains a supported source still awaiting
conversion; `failed` retains the exact recorded or deterministic conversion failure reason.
All outcomes projected gives `all_projected`; any pending or failed outcome
gives `conversion_incomplete`.

The gate is a replayable read-only view. It does not append a ledger event, alter a reservation,
judge projection coverage, decide whether one source resolves another source's gap, or combine
projections. The first-layer terminal gate recomputes this view and permits completion only when
its verdict is `all_projected`. `conversion_incomplete` returns every exact pending or failed
source outcome as `source_conversion_required` without writing a completion event. A changed or
missing artifact, duplicate source or projection identity, broken projection version order,
unknown source binding, or failure to fill an explicit reservation returns `terminal_invalid` at
that completion seam.

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
obligations, and projection-record counts. For current projections it also reconstructs every
context deferral against its source evidence, deterministic owner, anchor, candidate kind, and
unique resolved element. Missing, pending, duplicated, mismatched, or contradictory context chains
make the terminal invalid. Qualification reports both total and closed context-obligation counts.
With no explicit gaps the value is
`readable_projection_complete`. With gaps it is `readable_projection_incomplete` and carries every
exact gap record in canonical region, element, then relationship order. Missing, duplicated,
reordered, contradictory, or changed coverage evidence returns `terminal_invalid` without writing
the terminal event. The qualification takes no model answer and does not mutate the projection.

A deterministic disposition gate then decides what that qualification permits. Only
`readable_projection_complete` with zero exact gaps and an intake-wide `all_projected` closure
becomes `first_layer_complete` and may append the clarification-terminal event.
`conversion_incomplete` becomes `source_conversion_required` with its exact pending and failed
outcomes and writes no completion event. `readable_projection_incomplete` becomes
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
- `first_source_projection_complete` returns a frozen valid UTF-8 first source and its exact
  complete verbatim projection, then stops before later projection assessment.
- `additional_source_gap_assessment_complete` returns one immutable verdict with its exact original
  gap and selected additional-projection evidence when it is non-resolving or not yet supported by
  a typed reconciliation contract.
- `clarification_required` returns the admitted child projection plus every exact remaining gap
  when admission did not finish the readable representation; it cannot emit first-layer completion.
- `source_conversion_required` returns the exact pending or failed source outcomes and stops
  without a first-layer completion event.
- `clarification_complete` returns the preserved grounded terminal result plus its exact complete
  projection qualification, `all_projected` closure, and `first_layer_complete` disposition, then
  stops.

`clarification_required` is an internal continuation, not an external boundary. When an admitted
file or URL fulfilled the active question of an incomplete prepared round, code records that exact
question as fulfilled, verifies every remaining gap still matches the already-prepared unanswered
questions, and returns only the next question as `needs_operator_answer`. It does not call the model
again or repeat the source request. After a completed assessed round, the controller instead uses
the exact ordered remaining gaps to request the next complete follow-up question round and returns
that request as `needs_model_interview`. It never invents, presents, or answers a question.

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
Supply each response separately. Use `--gap-answer '<exact answer>'` only for `operator_text`, or
the one-question operator command/`--gap-file '<path>'` for `local_file`. Code rejects a response
before the interview starts, rejects empty, missing, wrong-type, or duplicate responses, and cannot
skip or reorder the prepared questions.

Before the next question is shown, each exact answer becomes a new immutable human source and a
complete verbatim readable projection. Its ledger lineage names the prepared-round result, round,
question position, question presentation, active original source, active projection version, and
exact gap binding. After the final answer, code records one round-completion event and stops with
`ready_for_projection_assessment`. It does not assess the answers, create more questions, or alter
the current readable projection.

## Current boundary

The intake-wide qualification path now continues beyond the first operator answer. Code binds every
prepared question to one exact obligation, preserves each text, file, or URL answer as a new
immutable source plus readable projection, and presents each answer to the model through the
code-controlled assessment interview. Only the declared `resolves_obligation` or
`does_not_resolve_obligation` verdict can be recorded. Exact resolving assessments are admitted and
closed by code; unresolved current gaps become the next ordered question round. Each successor
round has its own directory and one indexed readable-state record containing the complete prior
round, and the event that activates it ledger-binds that complete history. The operator launcher can
therefore conduct question → answer → projection → assessment rounds until a terminal boundary,
while still stopping at each actual operator or model turn. The terminal recomputes the current
source set and accepts cumulative resolutions only when source, projection id and digest, method,
qualification, unit, reason, and gap digest all match the current gap. It emits
`first_layer_complete` only when no unmatched current gap remains; otherwise it opens the next
round without rewriting any earlier source, projection, answer, assessment, or ledger event.

Each `--resolve-gap` invocation applies at most the next unused canonical resolving assessment from
any completed round to one unchanged relationship gap and then stops. Eligible assessed gaps have either a code-listed
identity ambiguity or exactly one known and one missing endpoint. It does not automatically loop
through the remaining assessments. It can prepare exactly one immutable successor round from the
latest completed assessed round and conduct any prepared round one question at a time. It returns
one deterministic continuation decision and can execute exactly one corresponding transition, but
its boundary controller still stops for every model interview and operator answer; it does not run
external work or a fully automatic question loop
to a grounded terminal condition. Its terminal qualification verifies the recorded
coverage contract and explicit gaps, and its disposition gate prevents an incomplete projection
from ending the first layer. Its boundary controller resumes the same prepared round after a
resolving additional source, or turns a completed assessed round's `clarification_required` result
into the next complete follow-up question-round request. It does not perform the later semantic
projection assessment against the source. It can freeze one additional local file or public URL selected by
a code-typed gap question, copy any completely valid UTF-8 source verbatim, route any pending image source
through the source-neutral visual projection contract, fill its reserved immutable projection,
assess code-listed readable evidence against the exact originating gap, and deterministically admit
one selected readable element into one exact unchanged element gap. The parent projection and the
additional-source projection remain immutable; the admitted value exists only in a new child
version whose ledger event binds every input hash. Code then requalifies that child and checks every
source projection. A gap-free child with complete source conversion receives the append-only
`first_layer_complete` terminal event; any remaining gap is returned exactly as
`clarification_required`, with no false completion event. When that admission came from a prepared
question, code appends its immutable source, assessment, and child-projection fulfillment to the
same answer round, validates the remaining gap-to-question identities, and presents exactly the next
existing question. The operator can finish the remaining questions one at a time. Assessing a
mixed round now preserves one complete ordered assessment without asking the model to rejudge an
already-admitted source: code carries that position's accepted assessment and exact child-projection
proof, sends only operator-text positions through the code-controlled verdict interview, and merges
the outcomes back into their immutable round positions. Missing, duplicated, or reordered plan
positions fail before the interview or any ledger append. A non-resolving operator-text outcome can
therefore advance directly to the next focused question round. For a resolving operator-text
outcome bound to one exact unchanged element gap, code now copies the complete immutable answer
verbatim into a new child projection. It preserves the parent, binds the question, assessment,
answer-source, answer-projection, original gap, and child hashes in the ledger, prevents the same
assessment position from being consumed twice, and re-enters the existing continuation decision.
A gap-free child can therefore reach the grounded `first_layer_complete` terminal without another
model call. Visual projection can also resume from completed spatial traversal with the full
immutable source, bind the exact next pending relationship obligation, preserve one relationship
outcome, and stop before the next obligation. Region-gap admission, semantic rewriting of an answer, and multi-evidence element
admissions remain later units. Legacy
gap resolution remains limited to an existing preserved single-gap answer bound to a relationship
identity ambiguity. The projection layer currently accepts images, flat visible-page PDFs,
OOXML spreadsheets, and complete valid UTF-8 files; other non-image bytes fail closed. Spreadsheet
projection is code-only and preserves every package part as represented or an explicit gap. Its source-projection closure gate can prove whether every immutable source has
a readable-projection outcome, but that gate remains separate from semantic gap assessment and
the remaining projection-combination contracts. Do not simulate those later units in prose or extend the script while
running these proven stages.

## Status contract

| `status` | Exit | Meaning |
| --- | ---: | --- |
| `needs_operator` | 4 | The intake is waiting for a source, one legacy answer, or one current question-round answer. |
| `waiting_for_model` | 2 | One bounded purpose, projection, question, or answer assessment must be completed. |
| `blocked` | 3 | Input or durable state is missing, changed, or invalid. |
| `ready_for_projection` | 0 | A requested file or URL is frozen and its projection is pending. |
| `ready_for_projection_assessment` | 0 | The current immutable projection version is ready. Before clarification terminal, completeness remains unassessed; the terminal result includes the code-derived projection qualification. |
| `ready_for_operator_interview` | 0 | A complete follow-up question round is preserved but no operator question has been presented. |
| `source_projection_closure` | 0 | The read-only gate returned one validated projected, pending, or failed conversion outcome per immutable source. |
| `source_collection_complete` | 0 | The operator finished the independent source set and code preserved one terminal projection outcome per source. |
| `source_set_qualification_complete` | 0 | Code bound and adapter-qualified every collected source projection in collection order and stopped before semantic comparison or clarification. |
| `qualification_admission_complete` | 0 | Code admitted the exact intake-wide qualification as either `first_layer_complete` or one immutable ordered `clarification_required` obligation queue. |
| `ready_for_qualification_assessment` | 0 | Every answer in the active indexed qualification round is preserved as an immutable source and readable projection, ready for the code-controlled model verdict interview. |
| `qualification_answer_assessment_complete` | 0 | One exact enum verdict and reason is preserved for every active-round answer and reconciled in question order. |
| `first_layer_complete` | 0 | Every current source gap is either absent or matched by one cumulatively admitted resolution with exact source, projection, method, qualification, unit, reason, and gap identity. |
