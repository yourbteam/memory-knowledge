# Development-probe manifest contract

Use this contract when one approved atomic implementation must be built from independently proven
functional parts. A mini-probe is one part of the product behavior, not one stage of the development
process.

## Whole-process boundary

1. Freeze one atomic outcome, its practical value, stopping condition, and immutable captured
   success and failure cases.
2. Decompose that outcome into independently buildable mini-probes. Each mini-probe must start from
   captured atomic cases; it cannot consume another mini-probe's unfinished output.
3. Give every mini-probe at least two materially different implementation approaches, a falsifiable
   hypothesis for each, its expected tradeoff, practical success and failure criteria, and ordered
   metrics that determine which passing approach ranks first.
4. Run every mini-probe experiment concurrently, subject only to the available execution capacity.
   Approaches within a probe receive the same frozen inputs and declared ranking criteria.
5. Preserve each experiment's winner as a promotion candidate. A winner is not canonical product
   code merely because it ranked first.
6. Wait for all mini-probe winners, then compose the exact declared winner artifacts. Missing,
   duplicate, unknown, or substituted artifacts fail closed.
7. Validate the assembled atomic implementation through the declared operator path against both
   captured success and failure outcomes. A set of passing mini-probes is not proof that the atomic
   outcome works.
8. If validation fails, return the evidence to the affected mini-probe or composition boundary and
   run another bounded experiment there. Do not rebuild unrelated winners.

The whole controller is Development-Probe Machinery. Experiment Machinery is its per-mini-probe
comparison engine.

## Manifest shape

The root contains exactly:

- `schema_version`: currently `1`;
- `atomic_step`: atomic identity, outcome, practical value, stopping condition, and captured cases;
- `mini_probes`: independently buildable functional probes;
- `composition`: the complete winner-consumption and final-validation contract.

Every captured case records an id, immutable source reference, SHA-256 digest, success or failure
kind, and expected practical outcome.

Every mini-probe records:

- its goal and practical contribution to the atomic outcome;
- whether code, a model, or both own its decision and why;
- captured-case inputs only;
- at least two distinct approaches with hypothesis, implementation mechanism, and tradeoff;
- observable success and failure criteria;
- one or more ordered, uniquely named winner-selection metrics and whether each is maximized or
  minimized;
- one `across_cases` entry for every ordered metric, using `sum`, `mean`, or `worst`;
- one uniquely named winner artifact and its meaning.

Composition records every mini-probe id and exact winner artifact once, states how the winners form
the atomic behavior, and names the operator path plus captured success and failure cases that prove
the assembled result.

## Validate

Run before launching any mini-probe experiment:

```bash
python3 scripts/development_probe_manifest.py validate <manifest.json>
```

The validator returns a small JSON confirmation for a complete parallel manifest. It refuses
malformed fields, duplicate identities, fewer than two approaches, duplicate mechanisms, missing
or duplicate winner-selection metrics, missing or reordered cross-case methods, unknown captured
inputs, inter-probe inputs, missing winner artifacts, and incomplete final validation with an
actionable explanation. Cross-case `sum` adds observations, `mean` takes their arithmetic mean,
and `worst` takes the minimum for a maximized metric or maximum for a minimized metric.

This first contract atom validates the plan for the whole process. Parallel experiment launch,
winner-bundle persistence, composition execution, and final operator-path execution are subsequent
controller atoms and must not be claimed from manifest validation alone.

## Runnable candidate bundle

Before an approach can run, build it into a new bundle with:

```bash
python3 scripts/development_probe_candidate.py build <request.json> <new-bundle-directory>
```

The request identifies one declared probe and approach, the development manifest, baseline and
candidate source directories, a relative candidate entrypoint, the `experiment-result-v1` output
protocol, and a structured argument array. Commands never use shell strings. Placeholders are
exact whole arguments; `{candidate-entrypoint}` is mandatory.

The bundle is write-once and contains exactly the canonical development manifest, a deterministic
read-only source snapshot, and `bundle.json`. The latter binds the atomic step, probe, approach,
manifest digest, baseline digest, exact per-file candidate hashes and sizes, candidate tree digest,
entrypoint, command, declared captured cases, and ordered evaluation metrics.

Run `verify` before use. It rejects changed, missing, extra, writable, linked, or relocated source
evidence; undeclared identities or cases; mismatched metrics; and unsafe command shapes. Run
`execute` only as an Experiment Machinery variant. It binds the frozen input bytes to the selected
declared case, executes the copied candidate, and proves the bundle remained unchanged afterward.
The candidate is still only a promotion candidate; the experiment records a recommendation and
never writes canonical product code.

## Run one complete mini-probe experiment

Use one launcher request containing exactly:

- `schema_version`;
- `development_manifest`;
- one declared `probe_id` and one captured `case_id` used by that probe;
- `approach_build_requests`, with one approach id and candidate-build request path for every
  approach declared by the selected probe.

Run:

```bash
python3 scripts/development_probe_experiment.py run <request.json> <new-output-directory>
```

The launcher reconciles the complete approach set in manifest order, prepares bundles concurrently
with a fixed worker bound, and preserves every build's output and error evidence. It generates
collision-free runner variant ids (`control`, then numbered variations) while recording their exact
approach mapping. One real Experiment Machinery run compares every bundle against byte-identical
captured input and the probe's ordered metrics.

A recommendation is written only when every declared variant completed and remained integrity
valid. The rank-one champion must map to exactly one bundle whose probe, case membership, and fresh
digest still match. Failure at any boundary writes `launch-summary.json`, retains existing build or
experiment evidence, and writes no recommendation. `promotion_applied` is always false.

## Run one mini-probe across all declared cases

Remove `case_id` from the single-case request and run:

```bash
python3 scripts/development_probe_cross_case.py run <request.json> <new-output-directory>
```

The launcher derives the complete ordered case set from the manifest and runs the proven
single-case launcher once per case with bounded concurrency and isolated output. It waits for every
case, preserves successful evidence when another case fails, and writes results in manifest order.
Only a complete set advances to the metric method declared before execution.

The cross-case winner is ranked by the manifest's ordered metrics and stable approach-id tie-break.
It is recommended only when the rank-one approach has one exact mapping in every case, every
mapped bundle freshly verifies, and all verified bundle digests are identical. Missing, duplicate,
failed, incomplete, or digest-inconsistent evidence writes `cross-case-summary.json` and no
recommendation. Promotion remains false.

## Run every mini-probe

Create one request containing the validated development manifest and exactly one cross-case
request path for every declared mini-probe, then run:

```bash
python3 scripts/development_probe_all_probes.py run <request.json> <new-output-directory>
```

Code refuses missing, duplicate, unknown, or substituted probe requests before launching anything.
It copies normalized requests into the run evidence, launches every cross-case probe with bounded
concurrency and isolated output, waits for all outcomes, and writes results in manifest order. A
failed probe does not erase completed probe evidence, but any failure prevents candidate-set output.

After every probe succeeds, code rechecks the recorded recommendation, its rank-one and unpromoted
status, atomic and probe identities, ordered cases, and recorded recommendation hash. It then
locates and freshly verifies the selected bundle for every case. Only one identical digest across
all cases becomes the probe's declared winner artifact. `promotion-candidates.json` contains
exactly one such candidate per probe in manifest order and still applies no promotion.

The controller now proves and collects every mini-probe winner. Final operator-path validation
remains a later controller boundary.

## Assemble the verified winners

Create one request with exactly `schema_version`, `development_manifest`, `baseline`, and
`promotion_candidates`, then run:

```bash
python3 scripts/development_probe_compose.py run <request.json> <new-output-directory>
```

The composer first reconciles exactly one candidate with every `composition.consumes` entry in
manifest order. It freshly verifies each immutable bundle and requires its recorded identity,
cases, manifest, and digest to match. It then rehashes the supplied baseline and requires every
winner to have been built from those exact bytes.

For each winner, code derives sorted add, change, and delete operations by comparing the complete
candidate snapshot with the baseline. Operations are indexed globally by relative path. Identical
same-path operations are coalesced while preserving every contributing probe; differing actions or
content refuse the entire assembly before any source tree is created. All winners must also expose
one byte-identical safe execution contract and entrypoint.

Only after those checks pass does code apply the merged operations to an isolated baseline copy.
The output `assembly/` contains a canonical manifest, read-only source, immutable captured-input
copies, and `assembly.json`, which binds every winner digest, merged operation and contributor,
baseline and assembled-tree digest, execution contract, and atomic-step identity. It never edits
the baseline, winner bundles, or canonical product source and always records
`promotion_applied: false`.

Verify or execute the isolated assembly with:

```bash
python3 scripts/development_probe_compose.py verify <assembly-directory>
python3 scripts/development_probe_compose.py execute <assembly-directory> <case-id> <new-output-directory>
```

Execution uses the packaged bytes for the selected declared case, runs the assembled entrypoint,
requires the `experiment-result-v1` result, and re-verifies that the assembly stayed unchanged.
This establishes that independently proven winner pieces form one runnable candidate. It does not
yet establish the manifest's complete final operator-path success and failure criteria; that is the
next controller boundary and the only basis for declaring the atomic step validated.

## Validate the complete atomic step

Create a request with exactly `schema_version`, `assembly`, and `assessment`. Assessment contains
one stable adapter file and a structured argument array using exactly one each of
`{assessment-adapter}`, `{assessment-request}`, and `{assessment-response}`. Run:

```bash
python3 scripts/development_probe_final_validation.py run <request.json> <new-output-directory>
```

Code freshly verifies the immutable assembly, derives the complete final case set from its copied
manifest, and executes every case exactly once with bounded concurrency and isolated output. It
waits for all cases, preserves successful and failed execution evidence, and serializes results in
manifest order. One case cannot cancel or erase another.

Each case is then presented separately to the assessment adapter with the atomic outcome, operator
path, expected case outcome, applicable success or failure criterion, execution result, named
execution evidence, and exactly three available answers: `satisfied`, `not-satisfied`, or
`cannot-assess`. Code accepts only one exact response object for that case, with a nonempty reason
and at least one evidence pointer naming evidence actually presented for that case. Free-form,
batched, misidentified, unknown, or ungrounded answers fail closed with all case runs preserved.
A `satisfied` answer must cite the completed execution result, or the recorded execution error when
the expected behavior is a refusal; execution status alone cannot establish satisfaction. An
incomplete execution never offers `satisfied` as an available answer.

Only the exact complete assessment set advances. Code binds one assessment per declared case to
the verified atomic-step and assembly identities, restores manifest order, and returns:

- `passed` only when every case is `satisfied`;
- `failed` when any case is `not-satisfied`;
- `inconclusive` when no case failed but at least one is `cannot-assess`.

The assembly and assessment adapter are rehashed after use. The run writes the complete evidence
and always records `promotion_applied: false`. A `passed` result proves the assembled atomic step
against its declared operator-path cases; it does not authorize copying it into canonical product
code. Failed or inconclusive evidence returns to the affected mini-probe or composition boundary
for another bounded experiment.

## Run the complete process once

Create one request with exactly `schema_version`, `development_manifest`, `baseline`,
`probe_requests`, and `assessment`, then run:

```bash
python3 scripts/development_probe_run.py run <request.json> <new-output-directory>
```

`development_manifest` and `assessment.adapter` contain exactly `path` and the file's SHA-256.
`baseline` contains its path and the source-tree SHA-256 produced by `run_experiment.py
--hash-source`. Every `probe_requests` entry contains `probe_id`, `request`, and the request file's
SHA-256. Assessment also supplies the safe structured command used by final validation.

Before launching a child stage, code validates every hash, the exact declared probe set, manifest
order, baseline, adapter, and assessment-command shape. It preserves that normalized handoff as the
top-level run request. The fixed stage order is all probes, composition, then final validation.
Each stage receives an isolated directory and a receipt containing its exit status, stdout and
stderr, evidence path and digest, and result path and digest. A failed stage prevents every later
stage from launching while retaining prior receipts and artifacts.

After final validation, code ignores stdout as verdict authority. It freshly hashes and validates
the final artifact, binds its atomic-step identity and assembly digest to a freshly verified
assembly, requires `passed`, `failed`, or `inconclusive`, and requires `promotion_applied: false`.
Only then does the top-level launcher return and preserve that verdict.

The complete launcher does not merge away probe identities. Probe outputs, approach experiments,
winners, and case evidence remain under the probe stage. Repair a probe-local issue through that
probe's cross-case launcher before rerunning the complete process. Resolve winner conflicts at
composition and cross-probe behavioral failures at final validation rather than assigning them to
an unrelated probe.

## Repair a failed probe without rebuilding unrelated winners

Use `development_probe_repair.py run` with one hash-bound complete-run request, a positive repair
budget, one repair contract per eligible probe, and code-controlled routing, planner, and builder
adapter commands. Each probe repair contract supplies two or three ordered approach identities and
the exact relative files those approaches may change.

The controller first runs the complete process unchanged. A passed result returns immediately. For
a failed semantic result, code maps the failed case to its declared probe inputs. A unique probe is
mechanical; an ambiguous mapping becomes one enum question whose answer must be one of the exact
presented probe, combined-probe, final-validation, or operator-decision choices.

For every routed probe, code freshly verifies the current winner, gives its failure evidence and
allowed paths to the planner, accepts exactly the declared two or three approaches, and runs each
builder concurrently in an isolated copy. Actual file snapshots enforce each approach's declared
scope. A derived repair manifest retains the original captured cases, proof, and metrics while
declaring the repair approaches, so the existing cross-case launcher remains the comparison engine.

The selected repair is repackaged against the original manifest, approach identity, baseline, and
execution contract. The controller substitutes only that probe bundle, preserves the other bundle
digests, recomposes the complete candidate set, and runs the existing final validator. Failed
evidence can feed the next round until `passed`, `operator-decision`,
`repair-budget-exhausted`, or `mechanical-failure`. Every request, model answer, candidate,
experiment result, replacement bundle, composition, and verdict remains in its numbered round;
`promotion_applied` remains false.

This repair mode currently fixes semantic failures routed to declared probes. Composition and
final-validation routes remain distinct and are returned for their own boundary repair rather than
being forced into a probe.
