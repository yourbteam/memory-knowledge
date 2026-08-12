---
name: info-intake-machinery
description: Starts and advances a new auditable information intake from only an opening statement. Preserves the opening and purpose answer, assesses purpose sufficiency without domain-specific rules, freezes the first operator-supplied local file, and records its first immutable AI-readable visual projection attempt.
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
constrains each element's anchor to the active region, offers only recorded element identities as
relationship endpoints, and offers only `readable` or `gap` as status choices. An answer outside
an allowed set is preserved as rejected and the same question is asked again without advancing.

The model supplies only visual judgments and free text where reasoning is needed: whether another
purpose-relevant unit exists in the active region, its source-neutral kind, its visible content or
concrete gap reason, and what a visible relationship establishes. Code assembles the canonical
projection, including every spatial-region outcome, and records the hash-chained interview journal
in the intake ledger. The completed projection is immutable version 1 with coverage explicitly
`unassessed`. No question contains rules for a particular image, annotation style, color,
application, or domain.

## Current boundary

This machinery does not yet accept URLs, assess whether a projection completely covers its source,
or decide what supporting evidence is needed. Its projection adapter currently accepts images
only and fails closed for other media types. Do not simulate those later units in prose or extend
the script while running these proven stages.

## Status contract

| `status` | Exit | Meaning |
| --- | ---: | --- |
| `needs_operator` | 4 | The intake exists and is waiting for its current operator answer or source. |
| `waiting_for_model` | 2 | One bounded purpose assessment or source projection must be completed. |
| `blocked` | 3 | Input or durable state is missing, changed, or invalid. |
| `ready_for_projection` | 0 | The first local file is frozen and its projection is pending. |
| `ready_for_projection_assessment` | 0 | Projection version 1 is immutable and its coverage remains unassessed. |
