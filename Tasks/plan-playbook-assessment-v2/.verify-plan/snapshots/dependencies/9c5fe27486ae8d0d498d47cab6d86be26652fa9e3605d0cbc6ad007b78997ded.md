# Verify-Plan Coverage Remediation Plan

## Goal

Prevent `verify-plan` from declaring a coverage surface complete unless a finite,
revision-grounded set of verification obligations has been independently approved
as complete and every required obligation has a current critic-approved result.

This plan closes only the convergence-control defect confirmed in
`verify-plan-coverage-remediation-analysis.md`. It does not claim to explain why an
agent missed a particular semantic defect, redesign the other planning lenses, or
make model judgment deterministic.

## In-Scope Files

- `skills/verify-plan/SKILL.md`
- `skills/_shared/verification_ledger.py`
- `tests/test_verification_ledger.py` (new)
- `tests/test_skill_contracts.py`
- `Tasks/plan-playbook-assessment-v2/plan.md`
- `Tasks/plan-playbook-assessment-v2/plan-verification-ledger.json`
- task-local durable critic snapshots at
  `<ledger-parent>/.verify-plan/critic-outputs/<attempt-id>.json`

`skills/verify-plan/scripts/verification_ledger.py` remains byte-unchanged because it
already delegates to the shared helper. Its real wrapper path is exercised by the
focused tests.

## Change 1: Add A Plan-Only Obligation Contract To The Shared Ledger

Extend `skills/_shared/verification_ledger.py` without changing the existing
`analysis` or `work` ledger behavior. `init --kind plan` requires both
`--plan-sha256` and `--evidence-revision-sha256`; non-plan initialization rejects
those arguments. It emits an otherwise empty valid work-in-progress
`plan_verification` object with exactly `contract_version=1`, the two supplied active
hashes, `inventory_sha256=null`, and empty `inventories`, `assignments`,
`obligation_assessments`, `critic_outputs`, and `coverage_exclusion_approvals` arrays.
This shape is valid only while `iteration=0` and `coverage_queue` is empty. Ordinary
`check` passes, `next-assignment` reports `inventory-not-ready`, and `--can-stop`
reports `inventory-not-approved`. The first populated coverage queue and inventory
must be written together, after which `inventory_sha256` is non-null and names exactly
one inventory record.
A `kind=plan` ledger must contain one `plan_verification` object with:

- `contract_version`;
- active `plan_sha256`, `evidence_revision_sha256`, and `inventory_sha256`;
- immutable `inventories`, `assignments`, and `obligation_assessments` arrays;
- a `critic_outputs` registry;
- `coverage_exclusion_approvals` for the only non-obligation terminal states.

Canonical JSON hashing in this contract means UTF-8, recursively sorted object keys,
preserved array order unless the schema requires sorting, separators `,` and `:`,
ASCII escaping, and no trailing newline. Every `*_sha256` below is lowercase SHA-256
over the named canonical projection.

Each immutable inventory contains exactly `inventory_sha256`, `plan_sha256`,
`evidence_revision_sha256`, `plan_sections`, `evidence_items`, `dependencies`,
`obligations`, nullable `completeness_approval`, and nullable
`completeness_approval_ref`.

The three controller-owned reference registries use these exact records:

- plan section: `{id,path,start_line,end_line,content_sha256}` with a normalized
  repository-relative path, positive inclusive lines, and digest of the exact frozen
  UTF-8 line bytes;
- evidence item: `{id,source_ref,content_sha256}` where `source_ref` is exactly
  `{repository_key,path,selector}`; `selector` is `WHOLE_FILE` or an RFC 6901 JSON
  pointer. `WHOLE_FILE` hashes the selected frozen file's raw bytes; a JSON pointer
  hashes the selected value's canonical JSON bytes under this contract;
- dependency: the same exact `{id,source_ref,content_sha256}` shape and projection,
  resolving against the frozen dependency/source snapshot rather than the evidence
  index.

Registry IDs are unique and arrays are sorted by ID. `content_sha256` never hashes its
own registry record. The live parent must build each record from the frozen
plan/evidence/source envelope, strict-resolve the referenced file, reject symlinks and
traversal, apply the selector, and re-open the selected bytes before ledger validation;
the Plan V2 controller performs the same operation itself. The shared helper validates
exact record shape, ordering, ID resolution, and hashes the complete registry records
into each obligation binding.

Each obligation contains exactly:

- stable `id` and owning `coverage_id`;
- one explicit `claim` to verify;
- sorted unique `plan_section_refs`, `evidence_refs`, and `dependency_refs`, each an
  array of registry IDs;
- `binding_sha256`, derived from canonical JSON containing `id`, `coverage_id`,
  `claim`, and the complete resolved registry records selected by those three arrays.

The helper recomputes `inventory_sha256` from canonical JSON containing the contract
version, plan hash, evidence revision hash, all three registries, and the ordered
obligation array. Duplicate obligation IDs, unknown coverage IDs, invalid references,
caller-supplied hash mismatches, and any in-scope coverage item with no obligation fail
validation.

`completeness_approval` and `completeness_approval_ref` are both null or both
non-null. The approval contains exactly `inventory_sha256`, `plan_sha256`,
`evidence_revision_sha256`, `decision`, `rationale`, and `evidence`; it contains no
snapshot or snapshot hash. Only `decision=APPROVED` on the current identities permits
completion. The reference contains exactly `critic_attempt_id`,
`critic_snapshot_path`, `critic_snapshot_sha256`, and `approval_sha256`, where the
last digest hashes the canonical approval object. Changing the inventory or either
active revision requires a new inventory and fresh approval.

Every assignment contains exactly `iteration`, `inventory_sha256`, sorted unique
`assigned_obligation_ids`, and `assignment_sha256`; the digest covers the first three
fields. Iterations are positive, unique, and contiguous. The helper exposes
`next-assignment <ledger> --limit <positive-int>` and emits the next incomplete IDs in
deterministic order: coverage risk high, medium, low; then coverage-queue order; then
inventory obligation order. A current `BLOCKED` obligation makes this command return a
blocked error instead of silently scheduling around it.

Assessment evidence is a sorted unique array of exact
`{registry_kind,id,claim}` records. `registry_kind` is
`PLAN_SECTION|EVIDENCE|DEPENDENCY`, `id` resolves in that active inventory registry,
and `claim` states what the cited frozen content establishes.

Every obligation assessment contains exactly `iteration`, `obligation_id`,
`binding_sha256`, one status (`SUPPORTED`, `GAP`, or `BLOCKED`), `evidence`,
`finding_snapshots`, nullable `blocked_boundary`, `assessment_fingerprint`, `approval`,
and `approval_ref`. One assessment is required for every assigned ID and no other ID
in that iteration. The fingerprint hashes the canonical assessment projection that
omits all three of `assessment_fingerprint`, `approval`, and `approval_ref`; it cannot
hash itself.

Each finding snapshot contains exactly `id`, `fingerprint`, `classification`,
`obligation_ids`, and `iteration_first_seen`. `fingerprint` hashes the immutable
finding core and excludes mutable resolution status. The approval contains exactly
`iteration`, `obligation_id`, `binding_sha256`, `assessment_fingerprint`, `decision`,
`rationale`, and `evidence`; it contains no critic-output identity. `approval_ref` uses
the same exact four-field reference schema as the inventory approval. Only
`decision=APPROVED` is authoritative, and the referenced critic snapshot must contain
one byte-equivalent canonical approval object.

`blocked_boundary` is null except for BLOCKED and then contains exactly `type`,
`binding_kind`, `binding_id`, `observed_content_sha256`, and `required_change`.
`type` is `EVIDENCE|RUNTIME|APPROVAL`; `binding_kind` is `EVIDENCE|DEPENDENCY`; the ID
must resolve in that active registry and its content hash must equal the observed
hash. Runtime and approval availability are represented by frozen dependency records.
The obligation is eligible for reassignment only after the named record's digest
changes, which changes the obligation binding; a prose-only claim that the block
cleared is insufficient.

Each `critic_outputs` record contains exactly `attempt_id`, `snapshot_path`, and
`output_sha256`. `snapshot_path` is a normalized ledger-directory-relative path with no
absolute, parent, symlink, or special-file resolution and must equal
`.verify-plan/critic-outputs/<attempt-id>.json`. The parent writes this file once with
atomic replace, fsyncs file and directory, reopens it, and rejects any pre-existing
different bytes. The file is canonical JSON with
exactly `schema_version`, `attempt_id`, nullable `inventory_approval`,
`assessment_approvals`, and `coverage_exclusion_approvals`. The two arrays are sorted
by their canonical approval hash and contain no duplicates; the inventory approval is
non-null exactly when that output assesses inventory completeness. `output_sha256`
hashes those exact reopened file bytes. No approval object inside the snapshot contains
`snapshot_path`, `output_sha256`, or `critic_snapshot_sha256`, so no digest cycle
exists.

On every `check`, `next-assignment`, and `--can-stop`, the helper reopens each snapshot,
requires canonical bytes and matching attempt/output identities, validates every
embedded approval's exact schema, and derives the approval hashes itself. Every
approval copied into inventory, assessment, or exclusion state must have an adjacent
approval reference whose path/hash match one registry entry and must be byte-identical
to exactly one object in that independent critic snapshot; missing, foreign, duplicate,
or multiply claimed approval objects fail. The registry is therefore an index of
immutable controller-owned output bytes, not caller-authored proof.

Assessment history is immutable. The current assessment is the greatest iteration for
that obligation whose binding hash equals the active inventory obligation. This
permits unchanged evidence to survive a later revision after fresh inventory approval,
while a changed section, evidence, dependency, or claim changes the binding hash and
invalidates only affected assessments.

The helper enforces this completion truth table:

| Obligation state | Complete | Stop effect |
| --- | --- | --- |
| Current critic-approved `SUPPORTED` | yes | permits stop |
| `GAP` | no | requires exact linked unresolved actionable findings and blocks stop |
| `BLOCKED` | no | blocks stop regardless of finding state |
| Missing, stale, unapproved, or foreign | no | blocks stop |

For `SUPPORTED`, `finding_snapshots` is empty and evidence is non-empty. For `GAP`,
`finding_snapshots` is the immutable assessment-time set of actionable finding cores
then linked to the obligation; every snapshot must match the ledger finding's immutable
core, carry that obligation ID, and have
`iteration_first_seen <= assessment.iteration`. Evidence is non-empty. For `BLOCKED`,
`finding_snapshots` is empty and `blocked_boundary` is non-null.

Current truth is derived separately from immutable history. A greatest-iteration GAP
is current only while at least one of its approved snapshot findings remains unresolved; after
all resolve it becomes stale and must be reassessed. A greatest-iteration SUPPORTED is
current only while no unresolved actionable finding names the obligation. Any later
such finding makes the assessment stale. Historical GAP records are never rewritten
to drop resolved finding snapshots. An unapproved historical GAP never affects
checked/fixed derivation.

Coverage completion is exact. `checked` means every owned obligation is currently
approved `SUPPORTED` and no obligation has prior GAP history. `fixed` means the same
current truth and at least one owned obligation has a prior critic-approved GAP
snapshot for which all
linked actionable findings are now resolved. A resolved historical GAP without a
later current SUPPORTED assessment remains stale/incomplete; it cannot derive fixed.
`pending`, `unverified`, and legacy `deferred`
are incomplete. `out_of_scope` and `deferred_by_critic` are legal only with one exact
`coverage_exclusion_approvals` record containing `coverage_id`, `prior_status`,
`approved_status`, active `plan_sha256`, `evidence_revision_sha256`,
`inventory_sha256`, `rationale`, `evidence`, and `approval_ref`. The approval object is
byte-identical to the corresponding critic-snapshot object, which contains those same
fields except `approval_ref`. A revision or inventory change therefore makes the
exclusion stale. Those items own no active required obligations. The helper rejects
every caller-authored coverage status that disagrees with this derived truth.

Every current `GAP` or `BLOCKED` obligation blocks convergence regardless of coverage risk.
Every in-scope low-risk obligation must also be supported unless its whole coverage
item has the explicit `deferred_by_critic` approval above. There is no low-risk silence
bypass.

Ordinary `check` separates structural validity from convergence readiness. It accepts
a structurally valid work-in-progress ledger containing a newly stale assessment only
when the owning coverage item has already been reset to `unverified`; it reports the
stale obligation as incomplete but exits successfully. `--can-stop` fails, and
`next-assignment` includes that stale obligation in risk order. A newly recorded
actionable finding against SUPPORTED must therefore atomically append the finding and
reset the owning item to `unverified`; the subsequent assigned pass records GAP or a
new evidence-grounded SUPPORTED assessment. Leaving the item `checked|fixed` while its
assessment is stale fails ordinary `check`.

Legacy coarse plan ledgers may still be loaded by `_load` for diagnostic tooling, but
the public `check` and `check --can-stop` commands both exit 1 and print
`plan-obligation-contract-required`. `next-assignment` exits 1 with the same code.
There is no automatic migration because obligations cannot be inferred reliably from
broad status labels.

Reason: the deterministic stop gate must consume evidence of completed obligations,
not trust a caller-authored broad coverage status.

## Change 2: Make Verify-Plan Produce And Approve Obligation Results

Update `skills/verify-plan/SKILL.md` so the parent creates the finite inventory from
the frozen plan, implementation-surface map, risks, contracts, flows, preservation
requirements, and authoritative evidence before an item can become complete.
Replace its current initialization command with
`python3 scripts/verification_ledger.py init --kind plan --plan-sha256 <sha256>
--evidence-revision-sha256 <sha256> --output <ledger.json>` and require both hashes to
come from the frozen active plan/evidence envelope.

The first verifier may inspect an inventory that is not yet approved, but no result
can establish completion until its paired independent critic assesses inventory
completeness. This uses the existing verifier/critic pair and does not add another
agent or expand the attempt cap.

Every verifier pass receives exact assigned obligation IDs. It returns exactly one
`SUPPORTED`, `GAP`, or `BLOCKED` assessment for each assigned obligation. Missing,
duplicate, foreign, or unassigned results fail the pass. `GAP` names exact finding
IDs; `BLOCKED` states the unavailable evidence or runtime boundary; `SUPPORTED`
includes direct evidence for the stated claim.

The critic independently:

- approves or rejects the complete inventory hash;
- emits one fingerprint-bound decision for every verifier obligation assessment;
- continues to adjudicate every verifier finding;
- cannot convert silence, partial assignment, `GAP`, or `BLOCKED` into completion.

Later assignments come from pending, stale, or `GAP` obligations. A current `BLOCKED`
obligation terminalizes the pass until the named evidence/runtime boundary changes and
creates a new binding eligible for assignment. A later finding must carry sorted
unique `obligation_ids`; a finding against a completed obligation records coverage
failure, invalidates that assessment, and prevents convergence. The parent records
each controller-derived assignment before spawn and the helper requires the verifier
and critic results to correspond exactly to it. Iteration summaries report obligations
assigned, supported, gapped, blocked, invalidated, and remaining.

Reason: the producer and critic contracts must create the evidence the deterministic
ledger now requires.

## Change 3: Reconcile Plan Playbook V2 With The Live Contract

Update `Tasks/plan-playbook-assessment-v2/plan.md` so its controller and role schemas
match the repaired live helper:

- role inputs carry both owning coverage IDs and exact assigned obligation IDs;
- verifier outputs carry exact obligation assessments;
- critic outputs carry inventory-completeness and per-assessment approvals;
- `record-verification-ledger` validates exact inventory, assignment, assessment,
  approval, finding, and derived-status correspondence;
- `can-stop` uses only the shared obligation-aware helper;
- revision handling derives invalidation from section, evidence, and dependency
  bindings and requires a new inventory approval while preserving unchanged assessment
  evidence;
- package, replay, evaluator, and promotion checks reject coarse-only completion.

Update the active Plan V2 ledger by rebuilding an explicit C01-C14 obligation
inventory on the current plan/evidence revision and resetting every prior coarse
`checked` result. No previous checked status is carried as obligation evidence.

Reason: implementing a repaired live verifier while leaving the V2 controller design
on the defective coarse contract would recreate the same failure after promotion.

## Change 4: Add Deterministic Tests

Create `tests/test_verification_ledger.py` and exercise the shared helper directly and
through `skills/verify-plan/scripts/verification_ledger.py`. Cover:

1. `analysis` and `work` legacy behavior remains unchanged.
2. `init --kind plan` requires both revision hashes, emits an empty non-stoppable V2
   contract with null active inventory, and non-plan init rejects plan-only arguments.
3. A valid plan inventory with all current approved `SUPPORTED` obligations derives
   checked coverage and permits stop when no actionable finding remains.
4. A partial slice records its exact assignment and `next-assignment` returns the next
   risk-ordered remaining obligation.
5. A partial or omitted inventory cannot derive checked or stop.
6. A changed inventory hash invalidates its completeness approval.
7. A changed section/evidence/dependency binding invalidates only affected obligation
   assessments; unchanged binding evidence remains valid after fresh inventory
   approval.
8. Whole-file and JSON-pointer registry fixtures produce non-circular content and
   binding hashes; traversal, symlink, selector, and digest mismatches fail.
9. Critic snapshot bytes are reopened; caller-authored registry claims, changed bytes,
   noncanonical JSON, digest-cycle fields, and approvals absent from the snapshot fail.
10. `BLOCKED` never derives completion and always blocks stop, including low-risk work.
    Changing its exact evidence/dependency boundary digest changes the binding and
    makes the obligation assignable again; unchanged prose does not.
11. Historical GAP finding snapshots remain immutable after resolution; fixed requires
    a later current SUPPORTED assessment, and unapproved GAP history cannot derive fixed.
12. Missing, duplicate, foreign, omitted, or unassigned assessments and approvals fail.
13. Caller-authored `checked` or `fixed` that disagrees with derived history fails.
14. Explicit critic-linked exclusion is the only out-of-scope or low-risk deferral path.
    A plan, evidence, or inventory revision makes that exclusion stale.
15. A later finding against a completed obligation plus an atomic reset passes ordinary
    `check`, fails `--can-stop`, and is returned by `next-assignment`; omitting the reset
    fails ordinary `check`.
16. A coarse-only legacy plan ledger cannot pass `check --can-stop`.
    Ordinary `check` and `next-assignment` also return the exact migration-required
    error, while `_load` can still support diagnosis.
17. The real `skills/verify-plan/scripts/verification_ledger.py` wrapper produces the
    same init, check, next-assignment, and stop results as the shared helper.
18. Skill-contract tests assert the exact two-hash plan initialization command and the
    task-local critic snapshot path contract.

Extend `tests/test_skill_contracts.py` to assert the live skill requires the inventory,
explicit assignments, the three-state truth table, critic completeness approval,
binding-derived invalidation, and obligation-aware stop behavior.

Reason: tests must prove both the new root boundary and preservation of sibling
verify-* behavior.

## Change 5: Same-Path Verification And Exit Criteria

Run focused tests only through `scripts/run_pytest.sh`. Then run a fresh verify-plan
pass against the revised Plan Playbook V2 plan and rebuilt C01-C14 obligation ledger.

This remediation passes only when:

1. all focused helper, wrapper, and skill-contract tests pass;
2. the ledger rejects one intentionally omitted obligation and one `BLOCKED`
   obligation before the live pass;
3. the fresh verifier and critic return complete obligation results on the same frozen
   plan/evidence revision;
4. every C01-C14 status is derived from approved obligation truth;
5. `--can-stop` passes without caller-authored coarse completion;
6. a fresh unrestricted confirmation finds no actionable defect in an item already
   derived complete;
7. only then may the ordinary Plan V2 internal-readiness, requirements-coverage, and
   requirements-satisfaction stages resume.

## Approval Boundary

Writing this plan changes no verifier or Plan V2 runtime behavior. Implementation of
Changes 1-4, including edits to the active Plan V2 plan and ledger, requires one
granular approval for the exact in-scope paths above. Commits, promotion, and push
remain separately approval-gated.
