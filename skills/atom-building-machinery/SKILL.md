---
name: atom-building-machinery
description: Build one approved atomic implementation through the proven Development-Probe and Prototype-Driven Implementation sequence. Use when an atom must be decomposed into independently tested probes, compared through experiments, assembled, promoted, and validated through the real operator path before another atom may begin.
---

# Atom Building Machinery

Build exactly one approved atom. Code owns the workflow order, immutable evidence identities,
allowed enums, and terminal decision. Models reason inside the existing Experiment Machinery and
Prototype-Driven Implementation boundaries; they do not decide whether a stage may be skipped.

## Start one atom

Read `$experiment-machinery` and `$prototype-driven-implementation` completely before acting.
Freeze and obtain approval for the atom's PDI autonomy envelope before creating its run. The atom
request contains exactly:

- `schema_version`: `1`;
- `atomic_step_id`, `outcome`, `practical_value`, and `stopping_condition`;
- `allowed_paths`: the complete repository-relative edit boundary;
- `captured_cases`: immutable success and failure cases, each with `case_id`, `source_ref`,
  lowercase SHA-256, `kind`, and `expected_outcome`.

Start the append-only run:

```bash
python3 scripts/atom_controller.py start <atom-request.json> <new-run-directory>
```

The controller reports the only stage that may run next. Do not infer or begin another stage.

## Build and prove the isolated atom

When `next_skill` is `experiment-machinery`, use its complete Development-Probe process. The
experiment must decompose the atom into independent functional probes, compare at least two
approaches per probe, compose every winner, and validate the complete isolated assembly across the
atom's exact captured cases. Record the complete run directory:

```bash
python3 scripts/atom_controller.py record-experiment <atom-run> <development-probe-run>
```

Code checks the complete fixed stage set, exact atom and case identities, final artifact hash,
verdict enums, and `promotion_applied: false`. A failed or inconclusive experiment is preserved and
routes back to Experiment Machinery. Only `passed` advances.

## Promote through PDI

When `next_skill` is `prototype-driven-implementation`, give PDI the freshly proven assembly and
the already approved envelope. PDI alone applies the candidate to canonical product code, reviews
the retained delta, and writes a promotion receipt with exactly:

```json
{
  "schema_version": 1,
  "status": "promoted",
  "atomic_step_id": "...",
  "controller": "prototype-driven-implementation",
  "experiment_event_sha256": "...",
  "experiment_assembly_sha256": "...",
  "changed_paths": ["..."],
  "evidence_pointers": ["..."]
}
```

Every changed path must remain inside `allowed_paths`. Record it:

```bash
python3 scripts/atom_controller.py record-promotion <atom-run> <promotion-receipt.json>
```

## Validate the promoted real path

Exercise the exact operator path the user will use against every captured success and failure
case. The model may assess semantic evidence, but code accepts only `satisfied`, `not-satisfied`,
or `cannot-assess`, one ordered result per declared case. Write a validation receipt with exactly:

```json
{
  "schema_version": 1,
  "status": "completed",
  "atomic_step_id": "...",
  "promotion_event_sha256": "...",
  "cases": [
    {
      "case_id": "...",
      "verdict": "satisfied",
      "reason": "...",
      "evidence_pointers": ["..."]
    }
  ]
}
```

Record it:

```bash
python3 scripts/atom_controller.py record-validation <atom-run> <validation-receipt.json>
```

Any result other than `satisfied` preserves the evidence and routes the atom back to Experiment
Machinery. Only all-satisfied evidence completes the atom.

## Stop boundary

Inspect the derived state at any time:

```bash
python3 scripts/atom_controller.py status <atom-run>
```

Before selecting or defining another atom, require:

```bash
python3 scripts/atom_controller.py authorize-next <atom-run>
```

The command refuses until the promoted implementation passed every real captured case. Commit,
push, deployment, credentials, destructive work, wider paths, or a changed requirement always
need their own explicit approval; this machinery never grants them.
