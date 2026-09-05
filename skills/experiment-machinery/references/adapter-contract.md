# Phase adapter contract

Use an adapter only to translate the Experiment Machinery process contract into an existing
machinery phase's real entry seam. The adapter must call that phase's production code; it must not
copy or approximate the phase logic.

## Experiment specification

For new experiments use specification version 5 with the observation contract below. Version 4 remains runnable for replaying historical numeric evaluators; it does not provide independent observation scoring. This legacy example documents the version-4 shape:

```json
{
  "schema_version": 4,
  "experiment_id": "one-stable-id",
  "hypothesis": "One falsifiable sentence.",
  "target": {
    "machinery": "name",
    "phase": "phase-name",
    "source": {"path": "/absolute/machinery", "sha256": "stable source-tree hash"},
    "entrypoint": "scripts/phase_entry.py"
  },
  "frozen_input": {"path": "input.json", "sha256": "64 lowercase hex characters"},
  "execution_limits": {
    "variant_timeout_ms": 1800000,
    "evaluator_timeout_ms": 600000
  },
  "variants": [
    {
      "id": "control",
      "command": ["/absolute/python", "/absolute/adapter.py"],
      "adapter": {"path": "/absolute/adapter.py", "sha256": "64 lowercase hex characters"},
      "configuration": {}
    },
    {
      "id": "variation-a",
      "command": ["/absolute/python", "/absolute/adapter.py"],
      "adapter": {"path": "/absolute/adapter.py", "sha256": "64 lowercase hex characters"},
      "configuration": {}
    }
  ],
  "evaluation": {
    "metrics": [
      {"name": "quality-score", "direction": "maximize"},
      {"name": "refusal-count", "direction": "minimize"}
    ],
    "evaluator": {
      "adapter": {"path": "/absolute/evaluator.py", "sha256": "64 lowercase hex characters"},
      "command": ["{python}", "{evaluation-adapter}", "{evaluation-request}", "{evaluation-response}"]
    }
  }
}
```

Variant ids and metric names use lowercase letters, digits, and hyphens. One variant id is exactly
`control`. Metric order is ranking priority. Do not include elapsed time, cost, or another unstable
measurement unless the experiment's hypothesis is specifically about that measurement and its
collection is controlled.

## Adapter environment

Generate `target.source.sha256` before writing the specification:

```bash
python3 scripts/run_experiment.py --hash-source /absolute/machinery
```

The runner starts every adapter concurrently with these values:

- `EXPERIMENT_ID`
- `EXPERIMENT_VARIANT_ID`
- `EXPERIMENT_WORK_DIR`
- `EXPERIMENT_INPUT_PATH` — a read-only byte-identical copy of the frozen input
- `EXPERIMENT_VARIANT_PATH` — the exact variant configuration
- `EXPERIMENT_TARGET_PATH` — a per-variant read-only copy of the declared target source
- `EXPERIMENT_TARGET_ENTRYPOINT` — the entrypoint relative to that copy
- `EXPERIMENT_RESULT_PATH` — the adapter's write-once result
- `EXPERIMENT_TELEMETRY_PATH` — the adapter's append-only JSONL telemetry

Write no file outside `EXPERIMENT_WORK_DIR`. Load target code only from
`EXPERIMENT_TARGET_PATH/EXPERIMENT_TARGET_ENTRYPOINT`; the canonical target path is not supplied to
the adapter. Never write the shared experiment ledger; only the parent runner owns it.

## Adapter result

Write `EXPERIMENT_RESULT_PATH` exactly once with:

```json
{
  "schema_version": 1,
  "variant_id": "control",
  "status": "completed",
  "outcome": {},
  "metrics": {"quality-score": 1, "refusal-count": 0},
  "error": null
}
```

A completed result exits zero. A failed result exits non-zero, uses `status: "failed"`, preserves
the practical error text, and remains in the experiment record. Candidate metrics are preserved as
`reported_metrics` for audit and ignored for ranking.

After all eligible variants finish, the runner gives code-owned execution facts, the result hash,
and hash-bound stdout, stderr, and telemetry references to the frozen evaluator in one
code-controlled request. It deliberately withholds the candidate outcome object and reported
metrics. The evaluator derives its scores from independently inspected evidence and returns exactly
one ordered score object per eligible variant and one finite value per declared metric. Code rejects
changed inputs, configurations, adapters, evaluator bytes, incomplete scores, unknown identities,
and reordered answers. The evaluator cannot edit candidates or the parent ledger.
Once the ledger records `experiment_started`, every path is terminal. Evaluation timeout, nonzero
exit, malformed or invalid response, input or evaluator drift, and internal validation errors write
one structured failure summary with no champion and append exactly one `experiment_failed` event.
Successful and no-eligible runs append exactly one `evaluation_completed` event. A caller never
needs stderr inspection to distinguish a failed run from a running one.

## Telemetry minimum

Append and flush phase start, meaningful work or decisions, rejections/errors, and phase finish.
Include the variant identity, sequence, timestamp, and safe evidence references or hashes. Preserve
the exact setup in the variant configuration instead of duplicating sensitive payloads in events.

For a Development-Probe candidate, the wrapper owns the variant feed. It gives the child operator
a separate append-only feed starting at the integer in `EXPERIMENT_TELEMETRY_SEQUENCE_START`.
Operator events are exactly `work_completed`, `decision_recorded`, `operator_rejected`, or
`operator_error`; each carries the active variant id, timestamp, message, evidence SHA-256, and
observations object. Rejections and errors also carry an actionable correction. The wrapper
validates and forwards those records between its own start and terminal events. A successful
candidate without work or decision evidence, or any malformed or non-monotonic feed, is ineligible.

The runner produces `summary.json`, a hash-chained `ledger.jsonl`, captured stdout/stderr, and every
variant directory. It always records `promotion_applied: false`.


## Version 5 independent observations

New experiments use `schema_version: 5` and add `evaluation.assessment`:

```json
{
  "reference": {"path": "reference.json", "sha256": "64 lowercase hex characters"},
  "output_fields": ["judgments"],
  "criteria": [
    {"id": "grounding", "metric": "quality-score", "reference_pointer": "/grounding"}
  ]
}
```

Freeze a JSON reference with independently established expectations before execution. Every
criterion references an existing JSON Pointer in that document and names one declared metric.
Every metric must have at least one criterion and use `maximize`: code scores the fraction of its
criteria satisfied. `output_fields` selects the actual top-level outcome artifacts the judge must
inspect; select raw judgments or outputs, never candidate scores, claimed correctness, or summary
counts. These selections are an explicit experiment-design responsibility, not a blacklist of names.
The reference bytes are hash-checked in preflight and copied before candidates execute. Scoring
uses that frozen copy, never a subsequently edited source reference.

The evaluator receives request version 2 containing `experiment_id`, `metrics`, `reference`,
`criteria`, and ordered `candidates`. Each candidate contains only `variant_id`, execution facts,
and `output` with the declared raw fields. It receives no candidate paths, result hash, metrics,
other outcome fields, or telemetry references. This is a controlled input contract, not an operating
system sandbox for an arbitrary evaluator executable.

Return exactly:

```json
{
  "schema_version": 2,
  "judgments": [{
    "variant_id": "control",
    "observations": [{
      "criterion_id": "grounding",
      "verdict": "satisfied",
      "output_pointer": "/judgments/0",
      "reference_pointer": "/grounding",
      "reason": "Explain how the presented output satisfies this reference criterion."
    }]
  }]
}
```

Candidate and criterion coverage must be complete and preserve request order. Both pointers must
resolve in the presented documents, and the reference pointer must match the criterion. The empty
output pointer addresses the whole output and can ground a finding about absence. Verdicts are
`satisfied`, `not-satisfied`, or `cannot-assess`; the latter fails evaluation explicitly with no
recommendation. Numeric score responses are rejected. The runner derives official fractions from
validated observations and preserves the evaluator response for audit.

This validates evidence provenance, completeness, and arithmetic. It cannot prove that a semantic
judge is honest or correct. Calibrate each judge on independent positive and negative examples,
including claim-only mutations and plausible but irrelevant evidence. A long quote alone cannot
establish that advice is useful. Supply an explicit semantic criterion and assess the actual output;
if needed evidence is absent, record failure or inability to assess. Legacy version-4 scores retain
their old interpretation and must not be presented as version-5 independent observations.


## Quality qualification and inconclusive comparisons

Add `evaluation.selection` to a generic specification, or `selection` to a Development-Probe
single-case/cross-case request:

```json
{"minimums": {"grounded-verdicts": 1}}
```

Each minimum must be finite and name a declared maximize metric. An explicit selection must
contain at least one minimum. Version 5 defaults to a minimum of 1 for every satisfaction metric;
explicit minima replace that default and may gate only essential metrics. Version-5 fractions
require minima between 0 and 1. Version 4 without selection retains historical ranking behavior.

Execution `eligible` remains separate from quality `qualified`. Every variant keeps its original
scores and unmet minimum details. Only qualified candidates enter winner ranking. A tie across
all ordered metrics returns null champion with `selection_outcome: no-demonstrated-advantage`;
if none qualify, it returns `no-qualified-candidate`. Completed comparisons return success from
the CLI even when they deliberately make no recommendation. Execution/evaluation failures remain
failures. No recommendation file is written for an inconclusive single-case comparison.

Cross-case selection checks the minimums separately on every original case before ranking
aggregate metrics. Summing or averaging cannot hide a failed case. A single-case tie is retained
as evidence and does not stop the other cases: aggregate evidence can still distinguish a winner.
An aggregate tie or absence of a universally qualified approach returns an explicit
`no-recommendation` summary. All-probe orchestration preserves those outcomes and produces no
promotion-candidates artifact when any probe has no recommendation.


## Calibrate the judge before candidate execution

Every new quality experiment should include version-5 `assessment` and hash-bound `calibration`.
In generic specifications use `evaluation.calibration`; in Development-Probe single-case and
cross-case requests use top-level `calibration` beside `assessment`. All-probe and full-run
requests reference those per-probe requests and preserve their assessment/calibration fields.
Both reference and calibration paths resolve relative to the declaring request, even when the
orchestration copies requests into other directories.

```json
{"calibration": {"path": "calibration.json", "sha256": "64 lowercase hex characters"}}
```

The calibration file contains independently labeled raw-output examples:

```json
{
  "schema_version": 1,
  "cases": [
    {"id": "positive", "outcome": {"judgments": []}, "expected_metrics": {"quality-score": 1}},
    {"id": "negative", "outcome": {"judgments": []}, "expected_metrics": {"quality-score": 0}}
  ]
}
```

The empty judgments above show the shape only: supply actual independently checked positive and
negative outputs appropriate to the frozen reference and criteria. Cases need unique IDs, every
selected raw-output field, and exact finite satisfaction metrics. Every metric must have both an
expected 1 and expected 0 case. This rejects an all-positive self-test that cannot detect an
always-pass judge.

Code validates and freezes calibration bytes before execution. It invokes the same observation
evaluator against all calibration cases using the same raw-output projection, reference,
criteria, response validation, and code-owned score calculation used for real candidates.
Expected scores are withheld from the evaluator. Candidate execution starts only after observed
scores equal the frozen expectations. A malformed response, mismatch, timeout, or tamper writes
a terminal failure at `evaluator-preflight` with zero candidate executions. The calibration
request, response, errors, and ledger events are retained under the experiment's `calibration/`.
Invalid specifications, including a bad declared hash, remain output-free preflight refusals.

Calibration adds one evaluator invocation per experiment/captured case. It can avoid all candidate
work for an incompatible judge; this does not establish a production speedup. Semantic confidence
is limited to the independently chosen cases. An evaluator that passes these examples can still
make mistakes on unseen outputs. Add real failure examples when they reveal new judging gaps.
Historical version-4 and uncalibrated version-5 requests remain runnable for replay, but absence of
calibration must not be described as a checked judge. Version 4 cannot declare observation calibration.
