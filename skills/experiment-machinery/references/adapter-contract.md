# Phase adapter contract

Use an adapter only to translate the Experiment Machinery process contract into an existing
machinery phase's real entry seam. The adapter must call that phase's production code; it must not
copy or approximate the phase logic.

## Experiment specification

The runner accepts one JSON object:

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
