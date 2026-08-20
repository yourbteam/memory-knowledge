---
name: experiment-machinery
description: Run controlled, phase-local experiments against real machinery paths. Use when Codex must freeze one input, compare a control with multiple internal setups in isolated parallel processes, preserve outputs and telemetry in a tamper-evident ledger, rank the results by criteria declared before execution, and recommend—but never automatically promote—the winning setup.
---

# Experiment Machinery

Use the deterministic runner for experiment identity, input hashing, isolation, parallel launch,
telemetry capture, evaluation, and final assembly. Use phase adapters only to exercise the target
machinery's real production seam. Models may produce or judge semantic work; code owns every
experiment boundary.

## Run one experiment

1. Freeze one hypothesis, target machinery and phase, exact input file, constants, control,
   variations, and ordered ranking metrics in one JSON specification. Do not edit the specification
   after execution begins. Generate the target source-tree hash mechanically:

   ```bash
   python3 scripts/run_experiment.py --hash-source <machinery-source-directory>
   ```
2. Read [references/adapter-contract.md](references/adapter-contract.md) when creating or selecting
   a phase adapter. Reject an adapter that reimplements the target phase.
3. Run:

   ```bash
   python3 scripts/run_experiment.py --spec <experiment.json> --output <new-output-directory>
   ```

4. Inspect `summary.json`, `ledger.jsonl`, and every `variants/<id>/` directory. A failed or losing
   variant remains part of the record.
5. Re-run into a different empty output directory when repeatability matters. Compare the champion
   and declared metrics; timestamps and durations are telemetry, not stable ranking inputs.
6. Recommend the champion. Never modify the target machinery or promote a winner during the
   experiment. Promotion needs separate owner approval and one confirmation through the target
   machinery's full operator path.

## Boundaries

- Invocation is opt-in. Existing machinery entrypoints and defaults remain unchanged.
- Every variant receives the same byte-identical frozen input, its own working directory, and a
  read-only snapshot of the declared target source. The adapter never receives the canonical target
  path.
- Variant commands are argument arrays, never shell strings.
- The parent runner alone writes the experiment ledger. Variant processes write only inside their
  assigned directory.
- Declare all ranking metrics before launch. Missing, non-numeric, or non-finite metrics make a
  variant ineligible; do not invent replacement values after seeing results.
- Select a champion only from completed, integrity-valid variants. Break a true metric tie by the
  stable variant id so the same evidence yields the same recommendation.
- Treat a recommendation as evidence for a later implementation decision, not as a machinery
  verdict or permission to change canonical behavior.

For the first proven adapter, run `scripts/intake_purpose_probe.py` through the generic runner. It
drives Info Intake's existing purpose-assessment functions and records their real downstream
boundary; it does not implement purpose assessment itself.
