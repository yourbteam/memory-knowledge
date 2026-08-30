---
name: atom-building-machinery
description: Provide PDI with the code-owned protocol for one approved atomic implementation. Use when an atom must be decomposed into independently tested probes, compared through experiments, assembled, promoted, and validated through the real operator path before another atom may begin.
---

# Atom Building Machinery

Bound exactly one approved atom inside Prototype-Driven Implementation. PDI remains the single
implementation lifecycle controller and approved-envelope owner. This machinery owns the atom's
workflow order, immutable evidence identities, allowed enums, and terminal decision as a bounded
capability protocol. Experiment Machinery remains its isolated comparison capability; neither
machinery takes lifecycle ownership from PDI.

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

Run this command from the repository root. The controller records the repository root and an
immutable byte-level baseline of every regular file under `allowed_paths`, including already
modified files. Those pre-start bytes are the boundary between existing work and this atom. The
controller keeps `next_skill` fixed to `prototype-driven-implementation` for every incomplete
state and reports the only bounded `required_capability` that may run next. Do not infer or begin
another capability.

## Build and prove the isolated atom

When `required_capability` is `experiment-machinery`, PDI invokes its complete Development-Probe
process. The experiment must decompose the atom into independent functional probes, compare at least two
approaches per probe, compose every winner, and validate the complete isolated assembly across the
atom's exact captured cases. Record the complete run directory:

```bash
python3 scripts/atom_controller.py record-experiment <atom-run> <development-probe-run>
```

Code checks the complete fixed stage set, exact atom and case identities, final artifact hash,
verdict enums, and `promotion_applied: false`. A failed or inconclusive experiment is preserved and
leaves `experiment-machinery` as PDI's required capability. Only `passed` advances.

## Promote through PDI

When `required_capability` is `promotion`, PDI uses the freshly proven assembly under the already
approved envelope. PDI alone applies the candidate to canonical product code. Derive
the accumulated in-scope change surface after the final prototype:

```bash
python3 scripts/atom_controller.py change-surface <atom-run> <new-change-surface.json>
```

Review exactly that surface, then write a final review artifact with `schema_version: 1`,
`status: "completed"`, `verdict: "passed"`, the change-surface file SHA-256 in
`change_surface_sha256`, and an empty `blocking_findings` list. Write a promotion receipt with
exactly:

```json
{
  "schema_version": 1,
  "status": "promoted",
  "atomic_step_id": "...",
  "controller": "prototype-driven-implementation",
  "experiment_event_sha256": "...",
  "experiment_assembly_sha256": "...",
  "changed_paths": ["..."],
  "change_surface": {"path": "...", "sha256": "..."},
  "review": {"path": "...", "sha256": "..."},
  "evidence": [
    {"case_id": "...", "path": "...", "sha256": "..."}
  ]
}
```

`changed_paths` must equal the controller-derived surface in exact order; remaining inside
`allowed_paths` is not enough. Code recomputes the live surface at promotion, requires the review
to pass against that exact surface hash with no blocking findings, and rehashes both artifacts on
every resume. Every evidence entry names one declared captured case and an existing regular file
whose bytes match the declared SHA-256. Relative paths resolve from the receipt directory. Record
it:

```bash
python3 scripts/atom_controller.py record-promotion <atom-run> <promotion-receipt.json>
```

## Validate the promoted real path

When `required_capability` is `real-path-validation`, PDI exercises the exact operator path the
user will use against every captured success and failure case. The model may assess semantic
evidence, but code accepts only `satisfied`, `not-satisfied`,
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
      "evidence": [
        {"case_id": "...", "path": "...", "sha256": "..."}
      ]
    }
  ]
}
```

Record it:

```bash
python3 scripts/atom_controller.py record-validation <atom-run> <validation-receipt.json>
```

Any result other than `satisfied` preserves the evidence and routes the atom back to Experiment
Machinery as PDI's required capability. Each nested evidence entry must name its enclosing
captured case. Code rehashes every recorded evidence file during record and resume. Only
all-satisfied immutable evidence completes the atom.

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
