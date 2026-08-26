---
name: experiment-machinery
description: Run controlled, phase-local experiments against real machinery paths. Use when Codex must freeze one input, compare a control with multiple internal setups in isolated parallel processes, preserve outputs and telemetry in a tamper-evident ledger, rank the results by criteria declared before execution, and recommend—but never automatically promote—the winning setup.
---

# Experiment Machinery

Use the deterministic runner for experiment identity, input hashing, isolation, parallel launch,
telemetry capture, evaluation, and final assembly. Use phase adapters only to exercise the target
machinery's real production seam. Models may produce or judge semantic work; code owns every
experiment boundary.

## Development-probe foundation

When an atomic implementation is being decomposed into parallel functional probes, read
[references/development-probe-contract.md](references/development-probe-contract.md). Validate its
manifest before launching experiments:

```bash
python3 scripts/development_probe_manifest.py validate <manifest.json>
```

Package every declared approach before it enters Experiment Machinery:

```bash
python3 scripts/development_probe_candidate.py build <request.json> <new-bundle-directory>
python3 scripts/development_probe_candidate.py verify <bundle-directory>
```

Use the bundle executor as the experiment variant command. Its configuration contains exactly the
declared captured `case_id`; code verifies the bundle and frozen input before launching the copied
candidate, then verifies the bundle again after execution. The canonical product source is never
the candidate execution path.

Run one complete mini-probe comparison for one declared captured case with:

```bash
python3 scripts/development_probe_experiment.py run <request.json> <new-output-directory>
```

The request supplies the validated development manifest, selected probe and case, and exactly one
candidate-build request per declared approach. Code builds every candidate concurrently, launches
the real Experiment Machinery runner, requires every approach to complete and remain integrity
valid, and binds the rank-one champion to its freshly verified bundle digest. It preserves every
build and experiment result and never promotes the recommendation.

Run that mini-probe across every case declared by its manifest with:

```bash
python3 scripts/development_probe_cross_case.py run <request.json> <new-output-directory>
```

This request omits `case_id`. Code runs the single-case launcher for the complete manifest-ordered
case set with bounded concurrency, preserves all case evidence, and applies the metric's declared
`sum`, `mean`, or direction-aware `worst` method. It recommends one approach only when every case
completed and that approach freshly verifies to one unchanged bundle digest across all cases.

Run every declared mini-probe with:

```bash
python3 scripts/development_probe_all_probes.py run <request.json> <new-output-directory>
```

Supply exactly one cross-case request path per manifest probe. Code refuses an incomplete or
substituted set before launch, runs all probes with bounded concurrency, waits for every result,
and preserves successes when another probe fails. It emits one manifest-ordered candidate per
probe only after rechecking each recommendation and freshly verifying the selected bundle across
every case. Recommendations remain unpromoted.

Assemble the verified winner set into one isolated runnable candidate with:

```bash
python3 scripts/development_probe_compose.py run <request.json> <new-output-directory>
python3 scripts/development_probe_compose.py verify <output-directory>/assembly
python3 scripts/development_probe_compose.py execute <output-directory>/assembly <case-id> <new-execution-output>
```

The request supplies the same validated manifest, its unchanged baseline source, and the
`promotion-candidates.json` produced by the all-probe launcher. Code freshly verifies every winner,
recovers its exact add/change/delete operations against the recorded baseline, rejects incompatible
same-path changes, and requires one identical execution contract. It applies only a conflict-free
set to an isolated baseline copy, packages the captured inputs, and emits a read-only assembly.
This proves the winners can run together; it still performs no product promotion.

Validate the complete assembly across every declared final case with:

```bash
python3 scripts/development_probe_final_validation.py run <request.json> <new-output-directory>
```

The request supplies the immutable assembly and one assessment adapter plus its structured command.
Code executes every declared success and failure case with bounded concurrency, waits for all
outcomes, and then presents each case separately for semantic assessment. The adapter may answer
only `satisfied`, `not-satisfied`, or `cannot-assess`; code binds its answer to the presented case
and requires grounded execution-evidence references. The terminal result is `passed` only when
every case is satisfied, `failed` when any case is not satisfied, and otherwise `inconclusive`.
Every result remains evidence only; promotion is still separate and explicit.

Run the complete Development-Probe process with one command after its manifest, per-probe requests,
baseline, and assessment adapter are ready:

```bash
python3 scripts/development_probe_run.py run <request.json> <new-output-directory>
```

Bind the manifest, every per-probe request, baseline source tree, and assessment adapter to their
declared SHA-256 values in the request. Code validates and normalizes the complete input set before
launching anything, then runs all probes, composition, and final validation in fixed order. Each
stage has its own output and durable receipt. A failure stops before the next stage, preserves all
earlier evidence, and identifies its exact boundary. The final verdict is read from, rehashed, and
bound to the verified assembly rather than trusted from process output. The launcher never promotes.

When that complete run returns a semantic failed verdict that maps to a probe, run the opt-in
self-contained repair controller:

```bash
python3 scripts/development_probe_repair.py run <repair-request.json> <new-output-directory>
```

The repair request hash-binds the complete-run request plus code-controlled routing, planning, and
builder adapters. It declares a bounded repair budget and, per repairable probe, two or three
approach identities and the exact source paths those approaches may change. Code presents a shared
failure as one enum question, presents the failed evidence to the planner, builds every returned
approach concurrently in isolated copies of the current winner, and runs the affected probe's real
cross-case experiment. It repackages only the selected probe, preserves every unaffected winner,
recomposes the exact set, and repeats final validation. Every round remains under `repairs/`; no
winner is promoted. A composition, final-validation, or undeclared-probe route returns an explicit
operator decision instead of being mislabeled as a probe repair.

Treat mini-probes as independently buildable pieces of the atomic product behavior, not as stages
of the development process. Every mini-probe has multiple implementation approaches and its own
experiment with ordered winner-selection metrics. Their experiments run concurrently, each winner
remains a promotion candidate, all winners are composed, and only the final operator-path result
can validate the atomic step.

The manifest validator, candidate bundler, single-case launcher, cross-case launcher, all-probe
launcher, composer, and final validator enforce these contract boundaries. None promotes winners
or edits canonical product code. Only a `passed` final result proves the complete atomic outcome;
failed or inconclusive results return the evidence to the affected probe or composition boundary.

## Run one experiment

1. Freeze one hypothesis, target machinery and phase, exact input file, constants, control,
   variations, each adapter path and SHA-256, and ordered ranking metrics in one version 2 JSON
   specification. Do not edit the specification after execution begins. Generate the target
   source-tree hash mechanically:

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
- Every variant command is `[this runner's Python runtime, adapter, optional arguments]`; the
  declared regular, non-symbolic-link adapter must be exactly operand 1 and is SHA-256-bound by
  the specification. The runner executes a read-only snapshot of those verified bytes, records
  that actual launch identity, refuses changed bytes before launch, and makes mid-run source or
  snapshot drift ineligible.
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
