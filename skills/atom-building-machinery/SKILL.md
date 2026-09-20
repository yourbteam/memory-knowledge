---
name: atom-building-machinery
description: Provide PDI with the code-owned protocol for one approved atomic implementation. Use when an atom must be decomposed into independently tested probes, compared through experiments, assembled, promoted, and validated through the real operator path before another atom may begin.
---

# Atom Building Machinery

Bound exactly one approved atom inside Prototype-Driven Implementation. PDI remains the single
implementation lifecycle controller and approved-envelope owner. This machinery owns the atom's
workflow order, immutable evidence identities, allowed enums, and owner decision as a bounded
capability protocol. Experiment Machinery remains its isolated comparison capability; neither
machinery takes lifecycle ownership from PDI.

## Start one atom

The builder accepts one already approved atom. It does not generate competing next atoms,
rank them, assess priority, or require a selection skill to exist. The owner or a separate selector
supplies the chosen work; owner authorization remains required. A future `atom-selection-machinery`
can supply the same handoff, but is not a runtime dependency of this skill.

Use the build-only handoff in [references/build-handoff.md](references/build-handoff.md).
Prepare its receipt with `scripts/build_admission.py`, then pass `--build-packet` and
`--build-receipt` to controller start. This binds the supplied authorization, exact request,
fixed goal and evidence; it makes no comparative judgment and calls no model.
Report the returned BUILD ADMISSION result as approval binding, never as proof of priority.
Existing value packets and receipt field names remain legacy compatibility inputs for preserved
runs; they are not prerequisites of a new build-only handoff.

Read `$experiment-machinery` and `$prototype-driven-implementation` completely before acting.
Freeze and obtain approval for the atom's PDI autonomy envelope before creating its run. The atom
request contains exactly:

- `schema_version`: `1`;
- `atomic_step_id`, `outcome`, `practical_value`, and `stopping_condition`;
- `allowed_paths`: the complete repository-relative edit boundary;
- `captured_cases`: immutable success and failure cases, each with `case_id`, `source_ref`,
  lowercase SHA-256, `kind`, and `expected_outcome`.
- `contract_surface`: exactly `{"kind": "render"}` for a renderer, or a validation declaration
  with `kind: "validation"`, the deliverable module name, and a nonempty ordered `fields` list.
  Every field carries `field`, `shape`, and `shape_source` as
  `repository/path.py::CONSTANT`; shapes are `list`, `object`, `enum`, `integer`,
  `pinned-string`, or `prose`. A field the atom itself adds carries `"introduced": true`: at
  `start` its parent must resolve and the leaf must not exist yet (an existing leaf is refused
  with "declare it without 'introduced'"); `record-promotion` refuses until the canonical module Once the run is started, the canonical module gaining the field is the expected end state: the run keeps loading and promotes; that refusal is a start-time declaration check only.
  carries the leaf. A misspelled field without `introduced` is still refused at `start` with the
  available keys.

An introduced enum field may also declare `introduced_enum`, an ordered, nonempty list of unique
nonempty string values. This is only for `introduced: true` with `shape: "enum"` when its named
constant does not yet exist in an existing deliverable module. Code freezes these values in the
request. Promotion requires both the field and that exact enum constant to exist; changed values
fail closed on resume and promotion. This does not permit missing modules, prose waivers, or
unresolved ordinary fields.

For non-rendering executable behavior, including PHP services, use `{"kind": "behavior", "source_paths": ["app/Service.php"], "case_ids": ["success-case", "failure-case"]}`. Name regular source files within allowed_paths and every captured case exactly once in the same order. New source files may be absent at start but must exist at promotion. Each named source must occur as a changed, hash-verified assembly file. This contract does not parse source as Python and does not replace semantic proof: exact approved-request admission, complete captured-case experiments, exact promotion review, and real-path validation remain required. Use the existing validation contract when the atom validates declared Python payload fields; do not relabel such work to avoid its field or prose rules.

Validation targets are resolved against the named deliverable module's checked-in constants at
`start`. A prose target is an exception and cannot carry a waiver written into the request by the
model or atom author. Start the controller-owned interview instead:

```bash
python3 scripts/atom_controller.py prose-waiver-interview \
  <atom-request.json> <new-or-existing-interview-directory>
```

The command may be launched by either model client. It accepts no answer on standard input or as an
argument. The installed, code-signed helper displays one native macOS window containing the atom
id, full request SHA-256, repository, fields, and the two unchanged hardcoded meanings. The macOS
authentication reason repeats the atom id and request SHA-256. Both identities are inside the
signed payload and are checked at `start`. `waive` adopts the complete displayed authorization for
this exact request while explicitly withholding promotion, operational use, other fields, and other atoms.
`decline` keeps the request blocked until it uses a structured field. `Cancel` records nothing.

After the operator clicks `Waive` or `Decline`, macOS device-owner authentication confirms the
choice with Touch ID or the login password. On its first successful authorization, the helper
creates a random Keychain proof value and restricts it to the byte-identical helpers installed at
both `~/.codex/skills/atom-building-machinery/` and
`~/.claude/skills/atom-building-machinery/`. The value is never printed, passed as an argument, or
written to a receipt. Missing or different client helpers fail closed and require refreshing both
projections through the managed installer.

A helper rebuild can cause macOS Keychain to ask whether the replaced helper may use the existing
proof value. Approve only the installed Codex or Claude helper path. Never grant Keychain access to
`security`, a shell, or another reader: a dialog left unanswered is not proof that policy denied
access. Existing native version-one receipts remain a bounded compatibility input and verify only
for their exact request bytes; every new receipt also signs the atom id explicitly.

The receipt records the OS login/uid, native approval and authentication policy, initiating client
projection and harness markers, helper path/hash, the observed parent application or executable
(or the explicit value `unavailable`), wall-clock time, and a
request-bound HMAC over the helper's signed payload and a random nonce. A model may launch the
window but cannot supply its choice or satisfy macOS authentication. `start` asks either installed
helper only to verify the proof; verification is silent, exposes no secret, and cannot mint a new
receipt. Normal operation requires no terminal input or setup command.

Only a completed interview can admit the exception:

```bash
python3 scripts/atom_controller.py start <atom-request.json> <new-run-directory> --build-packet <packet.json> --build-receipt <receipt.json> \
  --prose-waiver-interview <completed-interview-directory>
```

`start` verifies the entire interview and native presence proof and writes `prose_waiver` with exactly the
observed `operator`, `presence_proof`, complete waiver statement, and code-recorded ISO `date` into
the preserved atom request. A direct
`prose_waiver` in the supplied request is refused. Existing stored runs without this boundary
remain readable, but every new run must declare its contract surface.

New version-two development manifests must preserve each approved `source_ref` exactly and keep its
runtime `case_source_root` separate; Atom Controller compares logical references, not resolved
paths. Version-one comparison remains only for already-recorded assemblies.

While the atom is active, open every encountered blocker with
`scripts/blocker_catalog.py open --atom-run <atom-run>` so code derives its immutable atom request,
run, and attempt identity. Follow `references/blocker-closeout-contract.md`; never add those
identity fields by hand.

The managed installer writes one client-root provenance record binding the canonical source
repository to the exact blocker-catalog and work-memory module hashes. An installed controller uses
only that record for blocker closeout outside the canonical repository. Missing, linked, incomplete,
or changed support refuses and requires refreshing both projections through the managed installer;
support modules are never copied into individual skill projections. The verified support repository
also owns the blocker ledger; the atom's product repository root never replaces that owner.
Direct catalog calls retain their configured `--root` (or module default). Closure requires an
existing regular non-linked ledger at the selected owner and refuses unavailable state rather
than treating it as an empty blocker list. Historical closeout snapshots remain unchanged.

Start the append-only run:

```bash
python3 scripts/atom_controller.py start <atom-request.json> <new-run-directory> --build-packet <packet.json> --build-receipt <receipt.json>
```

When new evidence requires a fresh immutable controller run for the same unfinished atom, declare
the relationship instead of silently taking a new surface baseline:

```bash
python3 scripts/atom_controller.py start <atom-request.json> <new-run-directory> --build-packet <packet.json> --build-receipt <receipt.json> \
  --supersedes <previous-run-directory>
```

The controller requires the same `atomic_step_id`, repository root, and `allowed_paths`, refuses a
completed predecessor, verifies every predecessor request, ledger tip, and change-baseline hash,
and copies the earliest verified baseline into the new run. `status` prints the ordered chain and
its closure state. A normal start without `--supersedes` retains the existing fresh-baseline
behavior.

Run this command from the repository root. The controller records the repository root and an
immutable byte-level baseline of every regular file under `allowed_paths`, including already
modified files. Those pre-start bytes are the boundary between existing work and this atom. The
run directory must be outside and disjoint from every `allowed_paths` boundary; the controller
refuses an overlapping run before it creates any controller output. The
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
The controller imports the admitted summary, final verdict, and verified assembly into the atom
run; the supplied experiment directory is an import source, not continuing authority.
For a validation atom, code also statically scans the changed Python champion modules and records
the payload keys it saw. Every declared target leaf must be read by name. Other observed keys are
reported as contextual evidence and do not themselves cause refusal; the scan is a named heuristic,
not semantic proof.

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
  "contract_surface": {"kind": "render"},
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
whose bytes match the declared SHA-256. Relative paths resolve from the receipt directory. The
receipt, case evidence, change surface, and review are imported into the atom run before the
promotion event is appended; later state reads trust only those run-owned snapshots. Record it:

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

Before appending the validation event, the controller copies the validated receipt and every
evidence file into an event-specific directory under `<atom-run>/evidence/`. The ledger records
only those run-owned snapshots, so later changes to caller-owned live files cannot poison the
history; every snapshot remains rehashed on resume and any snapshot drift fails closed.

Runs created before this snapshot boundary may contain external evidence on a failed validation.
If—and only if—that failure is followed by a later experiment in the same valid hash chain, a
changed evidence hash is reported in `legacy_validation_evidence_drift` and does not block the
newer lifecycle. Missing or linked files, malformed records, changed receipts, current failures,
passed validations, and all run-owned snapshots remain strict.

Any result other than `satisfied` preserves the evidence and routes the atom back to Experiment
Machinery as PDI's required capability. Each nested evidence entry must name its enclosing
captured case. Code rehashes every recorded evidence file during record and resume. Only
all-satisfied immutable evidence plus a clear canonical blocker closeout completes the atom. The
controller snapshots that closeout beside the validation evidence; unresolved linked blockers
leave the atom at validation so they can be dispositioned and the validation recorded again.

## Stop boundary

Inspect the derived state at any time:

```bash
python3 scripts/atom_controller.py status <atom-run>
```

Before accepting a different atom for building, require:

```bash
python3 scripts/atom_controller.py authorize-next <atom-run>
```

The command refuses until the promoted implementation passed every real captured case. It also
rechecks the canonical blocker ledger and refuses when any atom-linked occurrence became blocking
after validation. For a supersession chain it appends one hash-bound closure event to the final
run; repeated authorization is idempotent. Commit,
push, deployment, credentials, destructive work, wider paths, or a changed requirement always
need their own explicit approval; this machinery never grants them.


## Execute a prepared admitted atom

Use `scripts/atom_driver.py <prepared-request.json> <run-directory>` to coordinate
one prepared atom through the existing experiment, exact promotion review, promotion,
actual-source validation and contribution check. The request uses version one, an absolute
repository root, hash-bound atom request/build packet/build receipt/experiment request (the version-one driver
retains the wire field names `value_packet` and `value_receipt` for compatibility),
prepared files and source trees, plus review and validation adapter commands. Each adapter
command contains `{python}`, `{adapter}`, `{input}`, `{output}` exactly once.

Preparation, candidate authorship and source-review judgments remain supplied inputs.
A product contribution check judges completed work through validation. Its own future
verdict and downstream driver completion must not be prerequisites in that product proof.
Verify driver completion afterward from its actual result and genuine contribution receipt.

The driver returns complete only after a supported independent contribution and progress
verdict. Exit 3 reports an exact frozen review payload requiring disclosure approval;
authorization for that payload permits resuming with `--approved-transfer-sha256 <digest>`.
That argument records caller-supplied authorization and does not replace host permission.
Exit 2 preserves the refusal and evidence; inspect the failed boundary before repairing.
Rerunning the same immutable prepared request resumes completed stages without repeating
promotion. Changed inputs or driver bytes refuse; prepare a fresh reviewed attempt.


## Fresh bounded source review

Use `scripts/source_review.py` as the prepared driver's review adapter. Before
launch, place `source-review-context.json` beside the prospective promotion surface
and register its exact path/hash in driver `prepared_files`. Bind both reviewer
modules there as well. The context binds the exact surface hash, outcome, ordered
source-quoted obligations, and exact before/after plus necessary dependency and raw
execution sources. Use obligations applicable to this changed unit. Keep execution
evidence from its matching run and declare the approved operator boundary; a local
change does not establish an unrelated whole-workflow claim.

The reviewer checks all supplied obligations and changed files, cites actual code,
and records additional concrete blocking regressions. Missing evidence produces
withholding, never a manufactured passing judgment. Its receipt uses the existing
driver promotion contract. Keep context preparation and requirement completeness
separate from the transferred source-review judgment.

`source_review.py <surface> <output> --prepare-only` writes the exact prompt without
sending it. Obtain required host disclosure approval before invoking the adapter
without that option. Both outputs are write-once; use a new output for an authorized
new trial. Installed operation uses the existing Codex tool-free model boundary.


## Generate a bounded candidate

Use `scripts/candidate_builder.py <creation-request.json> <new-output> --prepare-only`
to inspect the exact source-and-requirements disclosure before a model call. After the
required host approval, run without that flag into another new output. The existing
Codex model boundary produces unique anchor/replacement edits; code validates the
complete delta before materializing an isolated candidate. A blocked or malformed
answer remains evidence and never becomes a candidate. Do not edit generated code.

The creation request declares version one, outcome, constraints, exact allowed file
paths, absolute baseline, complete ordered file hashes, visible source units and
context. Requirements, dependencies and case selection remain prepared inputs.

For execution-adapter generation, use creation-request version two with the same fields
plus `execution_runtime`, containing absolute existing `php`, `phpunit`, and `bootstrap`
file paths. The normal builder automatically collects installed tool help, the existing
candidate/assembly/experiment launcher functions, and their directly called same-module
helper definitions. Do not paste those definitions into the request context. Preparation
and the post-generation recheck bind the collected source and runtime identities; version
one retains its original behavior. Runtime selection, business requirements and case
selection remain supplied inputs. Helper collection is one level deep, as tested; it does
not claim a complete recursive dependency inventory.

The existing driver also accepts a version-two generated request with exactly
`schema_version`, `template`, `generation`, `probe_id`, `approach_id`, and
`review_context`. The three references bind regular files by absolute path and SHA-256:
- `template`: the ordinary version-one driver request, using the baseline as the
  selected approach's placeholder candidate; no completed implementation is needed.
- `generation`: the builder's preserved `result.json`.
- `review_context`: the existing source-review context shape with prepared requirement,
  dependency and execution sources only; omit before/after sources.

The driver verifies preserved generation lineage and candidate bytes, replaces exactly
one declared approach with the generated source, and derives fresh experiment hashes
and source-review context. Its existing experiment, review, promotion and validation
stages then apply unchanged. The generated source is not a passing verdict. Review
disclosure approval remains required; prepare the exact forecast with the existing
review adapter before allowing its live invocation. Resume reuses the frozen generated
request and refuses changed candidate bytes. This transfers candidate authorship only;
preparing requirements, tests, context and the template is still manual.


### Recheck a completed driver closeout

If a corrected evidence boundary requires a fresh independent contribution check, preserve the
original run and use the installed driver with its original normalized `request.json`, a new
output directory, and `--recheck-closeout-from <original-driver-run>`. This path verifies the
completed controller, unchanged promoted product, prepared inputs and generated lineage, then
creates a separate closeout packet. It never repeats experiment, promotion or product validation.
The original run and its receipts remain unchanged; resume verifies their full recorded snapshot.
The packet includes the actual builder prompt, answer, invocation and exact before/after source.
Obtain explicit review-transfer authorization for the new packet and resume the same command
with `--approved-transfer-sha256 <new-packet-digest>`. A current blocker still withholds closeout;
complete its required correction verification before invoking this recheck.

### Include delivery observations in completion

When the promised proof includes delivery isolation or schema inspection, pass
`--delivery-context <config.json>` to the driver or its closeout recheck. The config names
`repository_root`, a hash-bound `baseline` JSON (branch, commit, checkout_before),
`preserved_checkout`, and hash-bound `schema_evidence` text files. The mechanical collector
saves the applied diff including additions, checks the actual changed paths, compares the other
checkout and its previously recorded untracked files, and includes the schema sources. New
untracked paths are reported separately; their cause is not inferred. The existing completion
model judges these observations. Saved-export inspection must not be described as live MySQL
execution. The config and resulting evidence are preserved beside the completion payload.

## Required goal-sequence continuity

Controller `start` and driver starts now require one registered goal sequence. Initialize it once
through `scripts/atom_sequence.py initialize --goal <fixed-goal-context.json>`. For explicit adoption
of existing work, add `--existing-run <atom-run>`. Reinitialization of the same goal is refused.
The canonical blocker-support repository owns the registry for all installed clients.

The active atom may resume or use its existing same-atom supersession path. A different atom cannot
start until the active run has completed validation and its independent contribution is verified.
The driver records that completion automatically. For an independently reviewed correction, use
`atom_sequence.py record-completion --run <active-run> --completion <completion.json>`.
`authorize-next` now checks both validation and the registered contribution. This is build completion, not permission to choose a successor. Historical validation
status remains readable; it is not itself successor permission.

The matching host guard is `scripts/sequence_hook.py --policy <host-policy.json>`, registered for
PreToolUse/apply_patch. It requires host admission to equal the registered active atom and rejects
edits to sequence authority. Install and trust this guard before claiming host-enforced continuity.
The existing scope gate and shell containment guard remain required. Initial registry adoption and
host policy selection are operator boundaries, not permissions granted to arbitrary atom edits.

## Selection is outside this skill

Successful driver closeout saves `handoff.json` and returns its absolute path in `handoff`
with `handoff_sha256`. The file preserves the admitted atom, complete existing assessment
input (including actual results and progress evidence), independent completion judgment and
hash-bound source references. Python serializes and reloads it without rewriting any judgment.
This establishes the recorded atom contribution, not overall goal completion. Pass the saved
file to the downstream progress assessor; it need not reconstruct the build from scattered files.

For an already completed historical closeout, export to a new file without rebuilding or calling
a model: `python3 scripts/build_handoff.py --closeout <completed-closeout> --output <new-handoff.json>`.
This verifies the preserved evidence, not the current product checkout. It does not update a cycle,
re-authorize a successor, or replace historical records. Incomplete or inconsistent evidence refuses.

Return the verified outcome and remaining evidence to the caller. Do not choose the next atom.
`authorize-next` retains its historical command name; it checks that this build is complete and
that sequence continuity permits another approved build. It does not rank or authorize its content.

The driver uses builder-owned contribution verification for build-only packets. It judges the
promised outcome and progress claim, not whether the atom was the best choice. Existing runs keep
legacy receipt and closeout handling. Do not rewrite historical records during migration.
