---
name: info-intake-machinery
description: Starts and advances a new auditable information intake from only an opening statement. Preserves human answers and files as immutable sources, records readable projections, verifies visual relationships, turns one gap into a code-bound operator clarification, and can admit one independently verified clarification as an immutable next projection version.
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

## Turn one unresolved gap into operator input

After projection version 1 is recorded with an explicit gap, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' --clarify-gap
```

Code selects the first gap in canonical projection order and binds its collection, identity, exact
record, record hash, and projection hash. The returned model command asks a fresh model to
formulate exactly one focused operator question from that bound gap, the frozen source, and the
intake purpose. The model cannot select a different gap or alter the ledger. The generated question
and every rejected question attempt remain in the hash-chained interview journal.

After the machinery returns `needs_operator`, preserve the operator's exact answer with:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' \
    --gap-answer '<exact operator answer>'
```

Code rejects an empty answer without advancing. A non-empty answer becomes immutable
`source-000004`; its first projection is the exact same UTF-8 bytes with complete one-unit
coverage. The ledger links the original projection gap to the generated question, answer source,
and verbatim projection. Replay checks every hash and byte.

## Resolve one answered relationship gap

For a preserved answer to a relationship-binding ambiguity, run:

```text
python3 scripts/start_intake.py --work <same-directory> \
    --opening '<exact opening>' --purpose '<exact purpose answer>' --resolve-gap
```

The returned interview lets a fresh model judge only whether the preserved answer resolves that
exact bound ambiguity. Code constrains the verdict to `resolves_gap` or
`does_not_resolve_gap`, constrains the selected ambiguous participant to the recorded candidates,
and requires the other endpoint to use a recorded readable element or capture one visible missing
element. Coordinates must fall inside the selected endpoint. When proposed bounds materially
overlap a recorded element, code presents those exact identities and evidence before allowing the
model to choose reuse or a distinct visible element; reuse cannot create a duplicate identity.

A resolving proposal is not admitted directly. The launcher starts a new model context that checks
the preserved operator answer and both exact visual participants. Only `supported` creates
projection version 2. Code replaces only the bound relationship gap, preserves version 1 and every
assessment artifact, records parentage and evidence hashes, and appends the request, result,
verification, and version events to the ledger. `does_not_resolve_gap`, `not_supported`, or
`unreadable` leaves version 1 and its gap unchanged with the reason recorded. Replay reconstructs
the expected version and rejects changed artifacts.

## Current boundary

This machinery does not yet accept URLs or assess whether a projection completely covers its
source. Gap resolution currently applies only to a preserved answer bound to a relationship
identity ambiguity. Its projection adapter currently accepts images only and fails closed for
other media types. Do not simulate those later units in prose or extend the script while running
these proven stages.

## Status contract

| `status` | Exit | Meaning |
| --- | ---: | --- |
| `needs_operator` | 4 | The intake exists and is waiting for its current operator answer or source. |
| `waiting_for_model` | 2 | One bounded purpose assessment or source projection must be completed. |
| `blocked` | 3 | Input or durable state is missing, changed, or invalid. |
| `ready_for_projection` | 0 | The first local file is frozen and its projection is pending. |
| `ready_for_projection_assessment` | 0 | The current immutable projection version is ready; completeness remains unassessed. |
