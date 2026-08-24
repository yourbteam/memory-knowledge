---
name: system-alignment-assessment-machinery
description: Trace a declared system value from its visible subject through the current implementation to a reference implementation, then produce evidence-bound measures and verdicts. Use after Info Intake has made the relevant sources readable. Do not use for source ingestion or implementation fixes.
---

# System Alignment Assessment Machinery

Use this machinery to answer whether a visible or externally observable system value is assembled
correctly. It owns the assessment after Info Intake has returned immutable, readable source
packages. It does not ingest sources and it does not change the assessed implementation.

The assessment remains general: an alignment unit is a purpose-relevant subject plus one or more
intent statements grounded in the upstream intake. Dashboard fields, spreadsheets, middleware,
API envelopes, and Reporting V3 are inputs in the current real case, not hardcoded machinery
roles.

## Admit alignment units

Create a write-once unit package from an exact JSON specification:

```text
python3 scripts/alignment_units.py create \
    --spec <alignment-unit-spec.json> --output <new-alignment-units.json>
```

The specification contains exactly `schema_version`, `source_artifact`, and a nonempty ordered
`units` list. `source_artifact` contains its absolute `path` and current `sha256`. Every unit
contains exactly `unit_id`, `sequence`, `label`, `subject`, and `intent_statements`. Subjects have
exactly `identity`, `kind`, and `evidence_sha256`; intent statements have exactly `statement_id`,
`text`, and `evidence_sha256`.

Code enforces consecutive order, unique unit and subject identities, exact fields, fresh source
bytes, and the presence of every subject and statement identity, text, and evidence hash in the
bound source artifact. It emits no measure or verdict. Reverify before downstream use:

```text
python3 scripts/alignment_units.py verify <alignment-units.json>
```

Later stages must preserve these unit identities and source bindings. Missing implementation
evidence is returned to Info Intake through its `source_handoff.py` contract; semantic sufficiency
and final alignment verdicts remain here.

## Freeze the required trace paths

Before tracing code, bind the assessment route to the admitted units:

```text
python3 scripts/path_inventory.py create \
    --spec <path-inventory-spec.json> --output <new-path-inventory.json>
```

The specification declares exactly one `actual` path, one `reference` path, their ordered stages,
and the actual/reference stages that will be compared. Stage kinds are code-controlled as
`observable`, `transformation`, `transport`, `service`, or `reference`; purposes remain grounded
free text. The machinery does not hardcode dashboards, APIs, spreadsheets, or Reporting V3.

Code freshly verifies the exact alignment-unit package, unique path and stage identities,
consecutive ordering, stage-kind enums, and comparison endpoints. Reverify with
`path_inventory.py verify` before collecting trace evidence. This artifact says what must be
traced; it does not claim that any path is complete or correct.

## Capture an implementation trace

Ground every stage of one inventory lane in current code without editing the source repositories:

```text
python3 scripts/trace_capture.py create \
    --spec <trace-spec.json> --output <new-trace.json>
```

The trace must cover every stage of the selected `actual` or `reference` lane exactly once and in
inventory order. Each stage records its exact successor and one or more evidence references with
repository, absolute file path, whole-file hash, line span, excerpt hash, and reason. Code freshly
recomputes every file and excerpt hash and refuses missing, reordered, or stale stages. Reverify
with `trace_capture.py verify` before comparison. Trace evidence records what code exists; it does
not decide whether the code is correct.

## Prepare all unit-mapping questions

Before asking a model anything, derive the complete known question catalog in one pass:

```text
python3 scripts/unit_mapping_questions.py create \
    --spec <mapping-question-spec.json> --output <new-question-catalog.json>
```

The specification binds the admitted units plus the complete `actual` and `reference` traces.
Code emits exactly one ordered question per unit, with the answer enum `mapped`, `needs-source`, or
`not-applicable` and only freshly derived trace-evidence choices. Changed units, changed traces,
duplicate units, or an empty evidence lane fail closed. The catalog declares
`one-question-at-a-time`; it is the complete input to the interview and contains no answers.

## Conduct the mapping interview

Prepare a write-once interview from the catalog, then expose only its current question:

```text
python3 scripts/unit_mapping_interview.py prepare --catalog <catalog.json> --work <new-work>
python3 scripts/unit_mapping_interview.py next --work <same-work>
python3 scripts/unit_mapping_interview.py answer --work <same-work> --response <one-response.json>
```

Code accepts exactly one response for the currently presented question. The answer must use the
enum `mapped`, `needs-source`, or `not-applicable`; selected evidence IDs must come from that
question. `mapped` requires both evidence lanes and both expressions. `needs-source` names missing
stages for a later Info Intake request. `not-applicable` carries only its reason. Every answer is
preserved as a separate immutable source and bound into a hash-chained ledger before the next
question is exposed. Completion produces `mappings.json`; earlier answers are never overwritten.

## Prepare and conduct the comparison interview

Turn the complete unit mappings into a full comparison catalog before asking for verdicts:

```text
python3 scripts/comparison_questions.py create \
    --spec <comparison-question-spec.json> --output <new-comparison-catalog.json>
```

Code partitions every admitted unit exactly once. A `mapped` unit becomes one ordered comparison
question; `needs-source` and `not-applicable` answers remain explicit dispositions. No unit may
disappear. The model then answers through the code-controlled one-question interface:

```text
python3 scripts/comparison_interview.py prepare --catalog <catalog.json> --work <new-work>
python3 scripts/comparison_interview.py next --work <same-work>
python3 scripts/comparison_interview.py answer --work <same-work> --response <one-response.json>
```

Each response selects the verdict enum `aligned`, `misaligned`, or `cannot-assess`, one allowed
measure kind, and only evidence IDs shown for that unit. The reason and expected/actual expressions
remain model judgments; code owns identity, enums, evidence admission, order, append-only answers,
and the terminal condition. Completion produces `comparison-results.json`.

## Produce the terminal alignment package

Bind all proven assessment artifacts into the practical downstream handoff:

```text
python3 scripts/terminal_alignment.py create \
    --spec <terminal-spec.json> --output <new-terminal-alignment.json>
python3 scripts/terminal_alignment.py verify <terminal-alignment.json>
```

The specification names exactly the alignment units, path inventory, actual trace, reference trace,
unit mappings, and comparison results by absolute path, whole-file hash, and internal artifact
hash. The two promoted probe units remain separate: `terminal_input_binding.py` freshly verifies
the immutable inputs, while `terminal_package_builder.py` reconciles exact coverage and produces
the ordered list, summary counts, and overall verdict. The launcher writes once and verification
rebuilds the package from the current input bytes; it never trusts the stored summary.
