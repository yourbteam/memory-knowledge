---
name: system-alignment-assessment-machinery
description: Assess whether observable system behavior aligns with declared intent or a reference by executing actual and reference prototypes on identical frozen inputs, comparing controlled experiments, and producing evidence-bound measures and verdicts. Use standalone from a neutral evidence package or after Info Intake. Do not use for source ingestion or implementation fixes.
---

# System Alignment Assessment Machinery

Use this machinery to answer whether visible or externally observable system behavior is correct.
It can start from a neutral evidence package supplied directly by an operator or from an adapter
over an Info Intake handoff. It does not ingest sources and it does not change the assessed
implementation.

The assessment remains general: an alignment unit is a purpose-relevant subject plus one or more
intent statements grounded in the upstream intake. Dashboard fields, spreadsheets, middleware,
API envelopes, and Reporting V3 are inputs in the current real case, not hardcoded machinery
roles.

## Run the complete assessment path

Use the controller for normal operation. Start from exactly one standalone neutral package:

```text
python3 scripts/run_assessment.py start --work <new-work> \
    --package <evidence-package.json> \
    --experiment-runner <experiment-machinery/run_experiment.py>
```

Or start from a verified Info Intake return plus alignment bindings:

```text
python3 scripts/run_assessment.py start --work <new-work> \
    --handoff <info-intake-source-return.json> --bindings <alignment-bindings.json> \
    --experiment-runner <experiment-machinery/run_experiment.py>
```

The controller runs every admitted actual/reference prototype through Experiment Machinery,
prepares the full question catalog, and exposes exactly one code-bound question. Submit only that
question's response and resume:

```text
python3 scripts/run_assessment.py resume --work <same-work> --response <one-response.json>
```

Repeat only while the returned status is `needs-model-answer`. The terminal return points to the
complete assessment report. Projection-only intake stops at `needs-validation-bindings` before an
experiment. Every controller transition is hash-chained; an existing work directory is never
restarted or overwritten. The component commands below remain available for focused diagnosis.

## Admit real validation evidence

Before tracing or assessing, admit a source-neutral package that binds every subject to at least
one runnable actual/reference case:

```text
python3 scripts/evidence_package.py create \
    --spec <evidence-package-spec.json> --output <new-evidence-package.json>
python3 scripts/evidence_package.py verify <evidence-package.json>
```

Each case supplies one immutable frozen input plus actual and reference adapters that accept the
same controlled result-and-telemetry protocol. Code freshly verifies all source, input, and
adapter hashes and refuses to emit `assessment-ready` when a subject has only static evidence.
Static traces remain useful supporting evidence, but cannot substitute for executed validation.

When the evidence came through Info Intake, adapt its verified source-return handoff through the
same neutral contract:

```text
python3 scripts/intake_handoff_adapter.py create \
    --handoff <info-intake-source-return.json> \
    --bindings <alignment-bindings.json> --output <new-admission.json>
```

The binding names purpose-relevant subjects, selects exact Info Intake evidence item identities,
and supplies their runnable cases. Code freshly verifies the source-return request, immutable
sources, readable projections, and ledgers. Complete bindings produce the identical
`system-alignment-evidence-package` used by standalone callers. Projection-only input produces
`validation-bindings-required` with one precise request per subject; the adapter never invents an
executable actual or reference from intake prose.

## Execute one controlled validation case

Run an admitted subject and case through Experiment Machinery:

```text
python3 scripts/validation_experiment.py run \
    --package <evidence-package.json> \
    --subject <subject-id> --case <case-id> \
    --experiment-runner <experiment-machinery/run_experiment.py> \
    --output <new-validation-run-directory>
```

The actual implementation is the experiment control and the reference is the comparison variant.
Both receive the byte-identical frozen input in isolated work directories. The resulting
`validation-execution.json` binds the experiment specification, hash-chained ledger, summary, and
ordered lane outcomes. A failed lane remains evidence; this stage never converts failure or value
difference into an alignment verdict.

## Prepare runtime assessment questions

After every admitted case has an execution artifact, partition the evidence before asking a model:

```text
python3 scripts/runtime_questions.py create \
    --spec <runtime-question-spec.json> --output <new-runtime-question-catalog.json>
```

Code freshly verifies the admitted package, every execution artifact, experiment summary, frozen
input identity, and hash-chained ledger. A case whose actual and reference lanes both completed
becomes one evidence-bound question exposing their real outcomes. A failed or ineligible lane never
reaches the model; it becomes an immutable `cannot-assess` disposition naming the exact lane that
must be repaired or supplied and rerun.

## Conduct the runtime assessment interview

Prepare one immutable interview and expose only its current question:

```text
python3 scripts/runtime_interview.py prepare --catalog <catalog.json> --work <new-work>
python3 scripts/runtime_interview.py next --work <same-work>
python3 scripts/runtime_interview.py answer --work <same-work> --response <one-response.json>
```

The model chooses only `aligned`, `misaligned`, or `cannot-assess`, one presented measure kind,
and evidence IDs shown with the current real experiment. Code rejects unknown choices, preserves
each accepted answer as a separate immutable source, advances one question at a time, and emits
`runtime-results.json` only after the full catalog is answered. A `cannot-assess` answer uses the
explicit empty `none` measure; it cannot disguise a guessed comparison.

## Produce the practical terminal assessment

Reconcile the complete runtime catalog and its completed interview:

```text
python3 scripts/runtime_terminal.py create \
    --spec <runtime-terminal-spec.json> --output <new-runtime-assessment.json>
```

Code freshly binds the catalog, evidence package, and runtime results; requires exact coverage of
every admitted subject and case; and applies fixed verdict precedence. The terminal artifact gives
each subject its measures, case evidence, and one `aligned`, `misaligned`, or `cannot-assess`
verdict. Every missing lane becomes a precise evidence request. Every confirmed misalignment
becomes an Atom Building candidate carrying the real captured case, desired outcome, practical
value, and stopping condition. It remains `requires-owner-envelope` until the owner supplies the
atomic-step identity, allowed paths, and approval; assessment never authorizes a fix.

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
