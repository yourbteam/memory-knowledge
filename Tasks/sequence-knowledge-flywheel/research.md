# Sequence Knowledge Flywheel — Hardened Research

## Objective

Turn the existing sequence discovery and promotion machinery into a durable knowledge flywheel: every unmatched repeatable operational task is captured as one complete, stable candidate; later observations reuse that candidate; qualification promotes it automatically through the existing atomic lifecycle; registered verification proves the promoted entry; and subsequent matching work finds the registered one-shot entry instead of reconstructing commands.

This work fixes the sequence contract and its orchestration. It does not replace the proven work-memory ledger, blocker/correction lifecycle, promotion transaction, or registry.

## Practical Result

Today, an unmatched task can produce a discovery file containing `TBD` inputs, missing failure handling, no verified path, unchecked readiness, and no durable promotion metadata. It then sits in discovery until an agent manually reconstructs the missing information and CLI flags.

After this change, the sequence runner submits one complete version-2 discovery specification. The system computes a stable fingerprint, reuses an existing matching candidate or creates exactly one new candidate, records the promotion profile in the candidate, checks structural readiness deterministically, drives qualification, atomically promotes after two current-bundle same-path successes, verifies the registered sequence, and returns the exact registered automation entry. The same fingerprint resolves directly to that registered sequence next time.

## Confirmed Current State

### What already works and must be preserved

1. Work memory is an append-only governed ledger for run start, blockers, corrections, bundle transitions, verification, run close/abandonment, and promotion. Its event contract is explicit in `scripts/work_memory.py:44-87`.
2. Discovery readiness already owns the structural, current-bundle, two-run, and zero-open-blocker predicate (`scripts/sequence_discovery_log.py:279-329`). Its current implementation incorrectly treats any passed verification in a run as sufficient instead of the final verification; the locked design below fixes that reducer without replacing the predicate.
3. Promotion is journaled and recoverable, writes the registered document, dependencies, registry row, promoted discovery metadata, and ledger event as one transaction (`scripts/sequence_promote.py:1-105`, `scripts/sequence_promote.py:221-280`).
4. The lifecycle controller already loops qualification, promotion, registered verification, and correction/successor verification until complete (`scripts/discovery_promotion_lifecycle.py:322-389`).
5. Blocker and correction handling is part of the lifecycle rather than an informal side path (`scripts/discovery_promotion_lifecycle.py:430-474`).
6. The bootstrap path is already locked, idempotent for an identical request, validates command placeholders, creates the candidate plus dependency manifest, classifies, selects, and starts a discovery run (`scripts/discovery_bootstrap.py:61-147`, `scripts/discovery_bootstrap.py:230-320`).

### What is broken

1. The default discovery renderer deliberately emits incomplete content: `TBD` inputs, `TBD` failure handling, `Not verified yet`, and five unchecked readiness boxes (`scripts/sequence_discovery_log.py:108-176`).
2. Bootstrap schema v1 requires only the identity, outcome, repeatability statement, and steps. Inputs, failure handling, verified path, dependencies, and all promotion metadata are optional or absent (`scripts/discovery_bootstrap.py:26-37`, `scripts/discovery_bootstrap.py:105-146`).
3. Promotion metadata is not stored in the discovery contract. Operators must supply `use_when`, operation kinds, automation display, pass signal, and qualification limit each time (`scripts/discovery_promotion_lifecycle.py:493-506`).
4. Automatic selection filters registered sequences primarily by operation kind. With multiple candidates it raises an ambiguity error unless an exact ID or a previously linked blocker fingerprint is supplied (`scripts/work_memory.py:963-1034`).
5. The command guard validates that a command is grounded in the selected bundle but records no command observation or outcome (`scripts/sequence_guard.py:670-721`). Therefore the repository cannot infer arbitrary Codex or shell history after the fact.
6. Corpus auto-capture is a different system: it produces low-confidence repository-note candidates at session close, is opt-in and fail-open, and Codex has no session hook (`skills/auto-capture/SKILL.md:11-18`, `skills/auto-capture/SKILL.md:50-53`, `working-agreement/auto_capture.py:1-15`, `working-agreement/auto_capture.py:141-154`). It cannot substitute for operational sequence capture.
7. The reconciliation one-shot is intentionally retain-only. Its policy allows only `remain-discovery`, `quarantine`, and `already-promoted`, and its allowlist names only two registered sequences (`scripts/discovery_candidate_reconciliation.py:233-286`, `operations/sequences/discovery/reconciliation-policy.json:1-10`). It is a safe inventory controller, not a knowledge flywheel.

### Current backlog evidence

The frozen governed reconciliation manifest at `/private/tmp/discovery-candidate-reconciliation-one-shot/run-13bf64b3203b44f58039606b89ff6e05/attempt-1.json` (SHA-256 `13712bfe2c88e5d3dc75271dacd5f74fad5393e1667d188d88b31bdee4a19e06`) contains 49 candidates: 27 remain in discovery, 20 are quarantined, and 2 are already promoted. Sixteen lack a governed discovery ID; two cannot resolve a repository root. Of the structurally inspectable candidates, 26 have incomplete readiness, 22 incomplete inputs, 21 no verified path, 18 incomplete failure handling, and 31 lack two same-path successes. Eleven candidate rows report open blockers.

Live ledger counts are deliberately not acceptance constants. At the 2026-07-16 research pass, `operations/work-memory/events.jsonl` hash `9b75bec5911ba34868af1cbb82d86bde7198cb63cddd571c91a5573789f3d98d` contained 330 discovery starts and 31 unterminated discovery runs. These values can change while work continues. Retirement acceptance is quantified over the ledger hash embedded in the newly generated retirement plan: every unterminated discovery run in that exact snapshot must appear exactly once with a hold disposition.

These figures prove that deleting or moving the pool would break provenance and can break resume. Reset must be logical and reversible, not a bulk filesystem deletion.

## Cause Chain

| layer | confirmed cause | practical effect | stable boundary |
| --- | --- | --- | --- |
| symptom | most candidates never become ready | agents repeatedly inspect and hand-repair discovery files | candidate contract |
| immediate cause | v1 permits incomplete sections and unchecked readiness | the created artifact fails its own promotion predicates | bootstrap/render contract |
| deeper cause | promotion identity and automation metadata are supplied only at drive time | no candidate is self-driving or deterministically reusable | persisted discovery schema |
| reuse cause | selector knows operation kind, exact ID, or blocker fingerprint—not task/candidate identity | more registered sequences increase ambiguity | stable sequence fingerprint |
| reset cause | ledger events reference candidate bundles and live unterminated-run counts change | physical archive can invalidate resume evidence | snapshot-bound logical retirement manifest |

The root cause is confirmed at the contract boundary: the producer is allowed to create an artifact that the downstream readiness and promotion consumers cannot use without manual reconstruction.

## Requirement Set

| id | requirement | acceptance summary |
| --- | --- | --- |
| R1 | governed automatic capture | the registered runner's no-match path must call the v2 capture controller; arbitrary ungoverned terminal history is explicitly not claimed |
| R2 | complete candidate | v2 rejects missing inputs, failure behavior, verification, dependencies, promotion profile, or unsafe steps |
| R3 | stable deduplication | identical normalized specs resolve to one candidate and accumulate distinct run evidence |
| R4 | governed auto-promotion | promotion begins only when the existing readiness predicate passes, including two current-bundle same-path successes |
| R5 | registered verification | completion requires a passed same-path registered run; blockers force correction/successor handling |
| R6 | deterministic reuse | the same fingerprint resolves to the registered sequence and its exact automation entry |
| R7 | one-shot operation | one controller owns capture, status, drive, and retirement planning/apply |
| R8 | reversible reset | legacy pool retirement is hash-manifested, logical, resumable, and does not move referenced bundles |
| R9 | secret safety | persisted identity contains normalized command shapes and hashes, never raw secret values |
| R10 | compatibility | v1 remains readable/runnable but is never auto-promoted by the new controller without explicit v2 upgrade |
| R11 | recovery | every mutation is locked, atomic, idempotent, and safe to retry after interruption |
| R12 | proof | tests cover capture, dedupe, promotion, registered reuse, recursive secret rejection, hash-only execution-result persistence, crash retry, and retirement |

### Frozen scope trace

This table is the scope authority for planning and implementation. A mechanism or
changed surface without a row here is excluded. A later gate may correct how one of
R1-R12 is satisfied, but it may not add a new product outcome.

| requirements | required mechanism | grounded existing boundary | acceptance authority |
| --- | --- | --- | --- |
| R1,R2 | complete v2 capture and deterministic rendering | `discovery_bootstrap.py`, `sequence_discovery_log.py` | AC1, AC3-AC5 |
| R3 | canonical identity, fingerprint, locked exact-match dedupe | bootstrap lock plus discovery/registered manifests | AC2, AC4-AC5 |
| R4 | qualification-only readiness and existing atomic promotion lifecycle | `sequence_discovery_log.py`, `discovery_promotion_lifecycle.py`, `sequence_promote.py` | AC6-AC8, AC14 |
| R5 | registered-stage same-path proof with blocker/correction successor | lifecycle and work-memory ledger | AC7-AC10, AC18 |
| R6 | strict candidate-fingerprint selection and structured automation receipt | `work_memory select`, registered manifest, sequence-runner | AC5, AC9-AC10 |
| R7 | one cataloged controller and registered meta-sequence | flywheel controller, `SEQUENCES.md`, sequence-runner skill | AC5, AC15, AC18 |
| R8 | snapshot-bound logical retirement and reconciliation integration | reconciliation inventory, retirement index, exact-path resume bypass | AC12-AC13 |
| R9 | recursive secret/delimiter/path/argv validation before persistence | existing work-only validator, bootstrap, guard-compatible command contract | AC3-AC4 |
| R10 | v1 read/run compatibility with v2-only automatic drive | existing v1 bootstrap/discovery/promotion/select paths | AC11 |
| R4,R5,R11 | effect-class policy, isolated read-only dry-run, persisted exact approval successor, execution claim/return | the lifecycle executes operational verification commands; work-memory is the durable resume authority | AC7, AC18 |
| R11 | deterministic attempts/events, roots predecessor chain, atomic promotion and retirement retry | work-memory transaction, promotion journal, atomic index write | AC7-AC8, AC13 |
| R12 | focused fixtures followed by the repository test entry point and independent review | `scripts/run_pytest.sh`, existing test suites | AC1-AC18 |

The execution-safety row is retained only because R4/R5 automatically dispatch the
real verification automation and R11 requires an interrupted effectful dispatch to
resume without replay or inferred authority. It does not create a general approval
platform: it is confined to flywheel qualification and registered verification.
Out of scope remain arbitrary command-history capture, generic workflow approvals,
new directive/corpus behavior, cross-repository sequence resolution, and live
retirement apply.

## Locked Design

### 1. Discovery schema v2 is the authoritative producer contract

`discovery_bootstrap.normalize_spec` accepts both versions:

- Version 1 remains byte-compatible for existing callers. It preserves current behavior and is labelled legacy; it is not eligible for automatic flywheel drive.
- Version 2 requires every operational field at creation time and forbids `TBD`, empty lists where operational content is required, unsafe placeholders, and unknown keys.

The only explicit v1-to-v2 upgrade uses existing mechanisms. `capture` never rewrites
or silently upgrades v1, and `status`/`drive` return `v2-upgrade-required`. The
operator first resolves any active run, blocker, or pending correction that keeps the
legacy row held, then submits the complete v2 spec through ordinary `capture` while
the legacy row is still active. Capture performs every registered/active-v2 target and
fingerprint conflict check before creating the v2 candidate; a conflict leaves the
legacy artifact untouched. Only after successful v2 capture does `retire-plan`
classify the now-superseded unpromoted legacy path as `retired`, and separately
approved `retire-apply` records that logical state without moving or editing it. The
v1 path remains provenance and exact-path resume history. Fixtures prove automatic
drive/promotion refusal, held-legacy refusal, preserved historical resume, target
conflict before retirement, and successful v2-capture then logical-retire ordering.

Version 2 fields are:

```json
{
  "schema_version": 2,
  "task_id": "stable task receipt id",
  "operation_kind": "existing work_memory operation kind",
  "date": "YYYY-MM-DD",
  "sequence_name": "human-readable stable name",
  "outcome": "observable outcome",
  "why_repeatable": "evidence that this is expected to recur",
  "steps": [{"step":"stable label","command":"secret-free command shape","result":"expected result","note":"failure/correction note"}],
  "inputs": ["required input/auth/environment contract"],
  "failure_handling": "fail-closed behavior and recovery entry",
  "verified_path": "the exact placeholder-free command from the verify-automation step",
  "dependencies": [{"kind":"file|glob|sequence","repository_key":"key","path_or_sequence_id":"value"}],
  "execution_safety": {
    "effect_class": "read-only|idempotent-local|external-reversible|external-irreversible",
    "approval_scope": "none|bundle|run",
    "idempotency_evidence": "non-empty evidence or null",
    "dry_run": {"effect_class":"read-only","automation_ref":"repo-key:read-only executable","automation_args":[],"pass_signal":"exact line"},
    "dry_run_not_practical_reason": "non-empty reason or null",
    "rollback_sequence_id": "require_id-compatible id or null",
    "no_rollback_reason": "non-empty reason or null",
    "evidence_capture": "what durable result proves each dispatch"
  },
  "promotion": {
    "sequence_id": "registered target id",
    "use_when": "registry match condition",
    "operation_kinds": ["one or more existing kinds"],
    "automation_ref": "repo-key:repo-relative executable script path",
    "automation_args": ["concrete", "secret-free", "argument"],
    "pass_signal": "exact required stdout line",
    "max_qualification_runs": 3
  }
}
```

The top-level `operation_kind` must be one of `promotion.operation_kinds` and is the single classification kind used for discovery qualification and registered verification. `promotion.operation_kinds` is normalized by trimming, deduplicating, and lexicographically sorting it; its ordering has no primary-kind meaning. Version-2 normalization rejects a missing membership relationship. The dedicated `sequence-governance` kind is reserved for the directly registered flywheel meta-sequence and is rejected in both fields of every ordinary v2 candidate. This keeps capture classification, promoted registry matching, qualification, and registered verification on the same operation contract without letting ordinary candidates contaminate the meta-sequence selection set.

Every `automation_args` element must be a JSON string. Elements are preserved byte-for-byte as Unicode text: leading/trailing whitespace and an empty string are meaningful argv data and are not trimmed, collapsed, sorted, or deduplicated. NUL, CR, LF, backtick, dollar sign, and placeholder syntax are rejected in automation arguments because the lifecycle executes them directly and the real command guard rejects those characters. After `shlex.join` constructs the identity and resolved command strings, both are passed through the same control-plane token algorithm as `sequence_guard`: tokenize with POSIX `shlex` and punctuation `;&|<>()`, reject a token composed only of control punctuation, and require `shlex.split(command)` to reproduce the original token array byte-for-byte. All recursive secret rules still apply. The exact preserved array is used by `CandidateIdentity`, fingerprinting, `automation_command`, `resolved_argv`, guard serialization, and subprocess. Non-string array members fail schema validation.

Serialization is fail-closed before the first durable write. Every v2 string rejects CR, LF, and the fenced-block terminator `` ``` ``, including values rendered as headings, paragraphs, and bullet sections. Every value rendered into a Markdown or registry pipe cell also rejects `|`: all four step fields, promotion sequence ID, `use_when`, operation kinds, `automation_ref`, every `automation_args` element, and `pass_signal`. Rendered identity JSON uses canonical JSON inside one fenced block; parse then re-canonicalize must reproduce the exact bytes. Capture tests round-trip every raw Markdown section, the discovery table, and the identity block; promotion tests round-trip the registry row; delimiter fixtures prove no schema-valid value can inject a section, split a cell, or defer failure to promotion.

Path-bearing identifiers are validated before path construction. `promotion.sequence_id` and every dependency with `kind=sequence` must pass `work_memory.require_id`, which permits only `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}` and therefore rejects slash, backslash, traversal, whitespace, and empty values. Automation/dependency `repository_key` is deliberately narrower: `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`, so it cannot contain colon. `automation_ref` must contain exactly one colon, then a non-empty POSIX repository-relative path containing no colon, backslash, absolute prefix, empty segment, `.` segment, or `..` segment; splitting at that only colon round-trips byte-for-byte. `kind=file|glob` values resolve only through the existing confined bundle helpers; absolute paths, `..` escape, and roots outside the mapped repository fail before write. `kind=sequence` is supported only with `repository_key=memory-knowledge`, matching the actual resolver; cross-repository sequence dependencies fail `cross-repository-sequence-dependency-unsupported`, while cross-repository file/glob dependencies remain supported. Tests cover both sequence-ID interpolation sites, one-colon reference round trips, ambiguous key/path rejection, file/glob confinement, and the sequence repository restriction.

Dependencies normalize by validating each row, deduplicating byte-identical normalized `(kind, repository_key, path_or_sequence_id)` tuples, then sorting that tuple order. Before any artifact write, capture expands the complete dependency graph through the supplied roots using the existing resolver. Empty glob expansion, missing file/sequence, sequence cycles, and any two dependency routes producing the same `(repository_key, relative_path)` fail closed (`dependency-empty`, `dependency-cycle`, or `duplicate-bundle-path`) rather than being silently merged. The resolved `automation_ref` must appear exactly once as a file entry in that expanded bundle under its declared repository key; presence only as prose, a sequence ID, or an unexpanded pattern is insufficient. Fingerprinting uses the canonical deduplicated declarations, while bundle hashing uses the validated unique expansion. Fixtures cover exact duplicates, overlapping file/glob/sequence expansion, cycles, empty globs, and missing or multiply covered automation.

`max_qualification_runs` must be a JSON integer (booleans rejected) from 2 through 10 inclusive. It is the cumulative count of distinct discovery `run_started` events for this v2 subject on the current source-bundle hash whose persisted `stage` is exactly `qualification`. Capture ordinal zero counts; a retry of the same deterministic run ID does not; passed, failed, active, and ambiguous claimed qualification attempts each count once. The quota is checked only before creating a new distinct qualification run: any already-started allowed qualification run always resumes to a terminal or correction state even when its ordinal makes the count equal the limit. A correction's bundle transition resets the count for the new bundle. Dry-run, promotion, and registered-verification stages are outside this discovery-qualification quota and do not reset or consume it. When no active resumable qualification run exists and creating the next one would exceed the quota before readiness, `drive` opens `qualification-attempt-limit-exhausted` and fails closed; only an approved correction that creates a new bundle can resume qualification. Tests cover minimum/range/type rejection, final-allowed active-run resume, ordinal-zero accounting, retry idempotency, failed/ambiguous qualification consumption, bundle reset, and dry-run/registered-stage exclusion.

The execution-safety object has exactly the eight declared keys and canonical null semantics. `read-only` requires `approval_scope=none`, `idempotency_evidence=null`, and all dry-run/rollback alternative fields null. `idempotent-local` requires `none` plus non-empty idempotency evidence and all dry-run/rollback fields null. `external-reversible` requires `bundle`, non-empty effect-guard evidence in `idempotency_evidence`, a non-null `dry_run` automation object, `dry_run_not_practical_reason=null`, a valid rollback sequence ID, and `no_rollback_reason=null`. `external-irreversible` requires `run`, non-empty effect-guard evidence, exactly one of a non-null `dry_run` object or a not-practical reason, and exactly one of rollback sequence ID or no-rollback reason. `evidence_capture` is always non-empty. A non-null `dry_run` has exactly `effect_class`, `automation_ref`, `automation_args`, and `pass_signal`; `effect_class` must be literal `read-only` and is the governed v2 submitter's immutable fingerprint-bound attestation, not a fact inferred by the command guard. Sequence-runner presents that attestation with the resolved command before dispatch, and schema/event validation requires it before the special ambiguity/retry path. The remaining fields obey the same one-colon reference, exact-argv, dependency coverage, resolver, guard, and exact-signal rules as the main automation and reference a distinct command. Unknown keys, forbidden non-null fields, empty reasons, or both/neither alternatives fail normalization. This single immutable policy object is used unchanged by validation, CandidateIdentity, fingerprinting, approval checks, and fixtures; mutable dry-run run IDs, event IDs, timestamps, and evidence hashes are ledger proof and never enter it.

Version 2 requires exactly one step whose label is `verify-automation`. Its command cell is the canonical display `automation_ref` followed by shell-quoted `automation_args`; it must contain no placeholders and must equal `verified_path` byte-for-byte after outer whitespace trimming. The referenced file must be present through the repository-root/dependency contract and must be an executable shell/Python entry; composite prose, em dashes, and non-executable registry displays are v1-only and ineligible for automatic promotion.

The v2 lifecycle does not pass this display string to `subprocess` from the memory-knowledge working directory. It splits each automation reference at its single colon, resolves the repository key through the selected repository-roots mapping, and confines the relative path beneath that root. Interpreter precedence is exact: a `.py` suffix yields `['python3', resolved_script, *automation_args]`; otherwise a `.sh` suffix yields `['bash', resolved_script, *automation_args]`; otherwise an executable file yields `[resolved_script, *automation_args]`; every other file fails closed. Suffix rules win even when the file is executable. The referenced repository is `cwd`. No absolute path enters candidate identity. `automation_command` in selection receipts is exactly `shlex.join([automation_ref, *automation_args])`, the stable identity display; it never contains resolved absolute paths. Runtime resolution separately produces `resolved_argv`, exactly the arrays above. Before execution the lifecycle validates `automation_command` against `CandidateIdentity`, then calls `sequence_guard guard` with `source=script`, the manifest-covered resolved script as `source_ref`, and `shlex.join(resolved_argv)`. It passes that same `resolved_argv` list directly to `subprocess` without reparsing or mutation. A fresh qualification succeeds only when the automation exits zero and one stripped stdout line equals `pass_signal` exactly; missing signal or nonzero exit catalogs the existing verification blocker. The signal is non-empty, single-line, and contains no pipe. The controller maps `automation_ref` unchanged into the existing registry automation cell and lifecycle display argument. Any identity/display mismatch, guard mismatch, unresolved/escaping path, unsupported file, nonzero, or missing-signal case fails closed.

Crash recovery never automatically replays the automation. `run_started` means created but not dispatched. Immediately before subprocess dispatch, the lifecycle atomically appends deterministic `execution_claimed`; immediately after return, it appends deterministic `execution_returned` before writing verification. A run with no claim is safe to claim and execute, including capture-created ordinal zero on its first `drive`. A returned event with no verification is completed from the recorded result without replay. Only a claim with no return is ambiguous. No recovery probe is accepted in schema v2 or executed automatically because side-effect freedom cannot be mechanically established. The lifecycle opens `ambiguous-automation-outcome` from the durable claim evidence and leaves the predecessor active and uncredited. Correction is allowed only when `correct --finalize-failed-run` records `reusable_behavior_changed=yes` and at least one actual changed source-bundle artifact covering the automation or one of its declared dependencies; the solution must state the idempotency/effect-guard change that makes a fresh invocation safe. The existing correction transaction moves to a new bundle, transitions the blocker to `fixed-awaiting-verification`, and closes that predecessor failed; only then does the pending-correction path create a deterministic successor for fresh guarded execution. Without such a bundle change, the ambiguous run stays active and blocked.

Execution authority is fail-closed per dispatch. `read-only` requires `approval_scope=none`; `idempotent-local` also uses `none` but requires concrete idempotency/effect-guard evidence. `external-reversible` requires `approval_scope=bundle`, a current governed `dry_run_recorded` proof, and a valid rollback sequence ID. `external-irreversible` requires `approval_scope=run`, plus either that governed dry-run proof or the policy's not-practical reason and either rollback sequence ID or its no-rollback reason. Every class requires durable evidence-capture instructions. Before any external-effect claim, work-memory must contain an explicit `execution_approved` event binding approval ID, candidate fingerprint, subject/lineage, source-bundle hash, command hash, effect class, stage, and the exact authorized run IDs. Run scope authorizes exactly the current nonterminal run. Bundle scope at `stage=qualification` authorizes the sorted set containing the current nonterminal qualification run, if any, plus every not-yet-started deterministic qualification ordinal through `max_qualification_runs - 1`; terminal run IDs are excluded and identical replay recomputes the same remaining set. Bundle scope at `stage=registered-verification` authorizes exactly the current nonterminal registered run; a failed external registered attempt requires the existing correction/bundle transition before another approval request. Promotion creates a new registered bundle and therefore always requires a distinct registered-verification approval.

Missing authority is a persisted successor, not an informal stop. If required dry-run proof is absent, `drive` returns `dry-run-required` with the exact candidate/bundle/safety binding and no approval request. After `dry-run` succeeds, or immediately when no dry run is required, `drive` appends or reuses a deterministic `execution_approval_requested` event and returns `execution-approval-required` with its ID plus a human-review object containing the exact command, effect class, stage, approval scope, authorized run IDs, source-bundle hash, dry-run proof, rollback proof or no-rollback reason, and evidence-capture obligation.

The request event has exactly these required fields, including explicit nulls: `schema_version`, `event_id`, `event_type=execution_approval_requested`, `recorded_at_utc`, `candidate_fingerprint`, `subject_id`, `lineage_id`, `source_bundle_hash`, `command_sha256`, `effect_class`, `approval_scope`, `stage`, sorted unique `authorized_run_ids`, `safety_profile_hash`, `proof_binding_hash`, `dry_run_event_id`, `dry_run_evidence_sha256`, `rollback_sequence_id`, `rollback_bundle_hash`, `rollback_verification_event_id`, `rollback_close_event_id`, `no_rollback_reason`, and `evidence_capture`; unknown or omitted fields fail validation. The nullable proof fields obey the execution-safety class matrix exactly. `proof_binding_hash` is SHA-256 of canonical JSON containing the seven nullable proof fields from `dry_run_event_id` through `no_rollback_reason`. The request event ID is UUIDv5 under `uuid.NAMESPACE_URL` over `memory-knowledge:sequence-flywheel:approval-request:<candidate_fingerprint>:<source_bundle_hash>:<safety_profile_hash>:<command_sha256>:<stage>:<sha256-canonical-authorized-run-ids>:<proof_binding_hash>`. Before generating `recorded_at_utc`, the writer reads that deterministic ID: exact binding replay returns the original timestamp/event; changed run or proof binding produces a different ID; same-ID payload mismatch fails `execution-approval-request-conflict`.

Only the flywheel controller's `approve --file <candidate> --approval-request-id <uuid>` command owns the public approval mutation. Invoking that command is the trusted human-attestation boundary: the sequence-runner is contractually forbidden to invoke it until it has presented that request's complete human-review object and received explicit human approval for that exact request. The controller can validate request currency and identity but cannot mechanically infer conversational consent, so there is no fictitious `not-yet-human-approved` runtime branch. Activation, a prior broad approval, and dry-run success do not authorize invocation. `approve` loads the immutable request, revalidates current candidate/bundle/safety/run/proof bindings, derives `approval_id` as the request UUID string, delegates the ledger append, and returns the original result on retry. The internal work-memory `approve-execution` operation accepts the already-validated request event rather than caller-repeated binding flags. These rules satisfy the dry-run/review, rollback, and evidence obligations without broadening authority.

The controller's `dry-run` command is the only producer of acceptable dry-run proof. It is valid only when the candidate's immutable safety policy contains `dry_run`; it uses the same durable roots authority, resolver, guard, deterministic execution-claim/return machinery, exact pass-signal check, final-effective same-path verification, and passed close rules as qualification, but persists the separate run stage `dry-run` and never dispatches the main external-effect automation. `run_started.stage` is an optional backward-compatible field globally, with allowed values `qualification`, `dry-run`, `registered-verification`, and `registered-execution`; every new v2 run requires it, while historical/v1 events without it retain their existing mode-based behavior. V2 qualification quota, readiness, and lifecycle advancement accept only `stage=qualification`; registered proof accepts only `stage=registered-verification`; ordinary registered reuse records `stage=registered-execution`; dry-run and registered-execution events are excluded from qualification/readiness proof.

Dry-run attempts have an independent, unbounded, explicitly invoked ordinal stream and never consume `max_qualification_runs`. They use the single canonical attempt formula shared by all v2 stages: UUIDv5 under `uuid.NAMESPACE_URL` over `memory-knowledge:sequence-flywheel:attempt:<subject_id>:<source_bundle_hash>:dry-run:<ordinal>`, where ordinal starts at zero. `safety_profile_hash` is SHA-256 of the canonical immutable execution-safety object and `command_sha256` is SHA-256 of the UTF-8 canonical dry-run display `shlex.join([automation_ref, *automation_args])`; both are execution/proof bindings, not a second run identity. One `dry-run` invocation resumes or completes at most one active attempt; it never loops automatically. No claim means dispatch once; return without verification is completed from the durable return; verification without close is closed without replay. Because the immutable dry-run command is required to be read-only, claim-without-return is not replayed under the same run: the controller appends deterministic event ID UUIDv5 of `memory-knowledge:sequence-flywheel:event:<run_id>:run-abandoned` with reason exactly `ambiguous-read-only-dry-run`, then the next explicit invocation may start ordinal N+1 without a correction. The global validator permits claimed/no-return abandonment without correction only when `run_started.stage=dry-run`, the safety policy resolves to read-only dry-run automation, and that exact reason is present; every other claimed/no-return run retains the effectful correction rule. A terminal failed verification/close likewise returns the blocked error and the next explicit invocation may start ordinal N+1. An existing valid `dry_run_recorded` event is returned before creating another attempt. These read-only successor attempts are excluded from qualification blockers, correction requirements, quota, readiness, and promotion proof.

Dry-run context selection is exact. Before promotion it uses `mode=discovery`, `subject_id=discovery_id`, the candidate path-derived lineage, and the candidate's current dependency bundle/hash; ordinal zero copies `repository_roots` from the highest-ordinal current-bundle qualification `run_started` (the capture-created ordinal zero exists before dry-run), and later dry-run ordinals copy the immediately preceding dry-run run. After promotion it uses `mode=registered`, `subject_id=promotion.sequence_id`, the preserved candidate lineage, and the current registered dependency bundle/hash; its first dry-run ordinal copies roots from the same latest passed qualification predecessor selected for first registered verification by `(completed_at_utc, run_id)`, and later dry-run ordinals copy their immediately preceding registered dry-run. In either mode, a caller roots override must exactly equal the selected predecessor map. Missing predecessor, mismatched subject/lineage/bundle, missing root, or drift fails `repository-roots-authority-missing-or-drifted` before `run_started`; fixtures cover first/later discovery dry-run, first/later registered dry-run, promotion bundle switch, and override drift.

On exact success the controller appends `dry_run_recorded`. That event's ID is UUIDv5 under `uuid.NAMESPACE_URL` over `memory-knowledge:sequence-flywheel:dry-run:<candidate_fingerprint>:<source_bundle_hash>:<safety_profile_hash>:<command_sha256>` and it contains exactly the common event fields plus `candidate_fingerprint`, `subject_id`, `lineage_id`, `source_bundle_hash`, `safety_profile_hash`, `command_sha256`, `run_id`, `verification_event_id`, `close_event_id`, `evidence_sha256`, and `recorded_at_utc`. `evidence_sha256` is SHA-256 of canonical JSON `{"run_id":...,"verification_event":<the complete cited final verification event>,"close_event":<the complete cited terminal close event>}`. Before append, validation proves the deterministic ordinal run identity and `dry-run` stage, command equality to the immutable `dry_run` policy, final-effective passed same-path verification, and passed close. Exact deterministic-event replay returns the existing record; a different binding at that ID fails `dry-run-evidence-conflict`.

`approval_id` passes `require_id`; its event ID is UUIDv5 under `uuid.NAMESPACE_URL` over `memory-knowledge:sequence-flywheel:approval:<approval_id>`. `execution_approved` contains exactly the common event fields plus `approval_id`, `approval_request_id`, `candidate_fingerprint`, `subject_id`, `lineage_id`, `source_bundle_hash`, `command_sha256`, `effect_class`, `approval_scope`, `stage`, sorted unique `authorized_run_ids`, `approved_at_utc`, `safety_profile_hash`, nullable `dry_run_event_id`, nullable `dry_run_evidence_sha256`, nullable `rollback_sequence_id`, nullable `rollback_bundle_hash`, nullable `rollback_verification_event_id`, nullable `rollback_close_event_id`, and nullable `no_rollback_reason`. Before generating a timestamp, `approve-execution` computes the deterministic event ID and reads the ledger: an existing event with the same complete request binding returns its original `approved_at_utc` with `already_recorded=true`; a different binding fails `execution-approval-conflict`. Only a missing event receives the current UTC timestamp and is appended. A cited dry-run event must bind the same candidate, subject, lineage, source bundle, safety-profile hash, and immutable dry-run command, and its evidence hash is copied from the approval request. A rollback sequence must resolve through the registry and manifest to a current bundle with cited final-effective passed same-path verification and passed close; those bundle/event IDs are copied into the request and approval event. Before `execution-claim`, lifecycle validation requires the approval event to follow its request and precede the claim, match every bound field and safety-profile hash, include the run ID, and still reference unchanged dry-run/rollback proof events. Missing, stale, later, or mismatched authority creates/returns the current `execution-approval-required` successor without claiming. Global ledger validation enforces request-before-approval-before-claim while legacy runs without execution events remain unaffected.

The stored discovery document gains `CandidateSchemaVersion`, `CandidateFingerprint`, and one machine-readable fenced `CandidateIdentity` canonical JSON block. There is no separate authoritative operation-kind or promotion-profile representation: human-readable headings are rendered from `CandidateIdentity`, and readers either parse the identity block or verify any rendered summary equals it. `drive` reads `candidate_identity.promotion` only. The discovery dependency manifest remains schema v1 but gains optional `candidate_fingerprint` and `candidate_identity` fields; promotion copies both unchanged into the registered manifest. Every reader recomputes SHA-256 over `candidate_identity` and rejects a mismatch, so identity and execution metadata are reconstructable from either persisted discovery or registered artifacts without task receipts.

### 2. Stable fingerprint and deduplication

The candidate fingerprint is SHA-256 over UTF-8 canonical JSON: object keys sorted lexicographically, array order preserved except where stated, no insignificant whitespace, native JSON booleans/numbers, and Unicode preserved without case-folding. The identity object contains every behavior-bearing field:

- operation kind, trimmed outcome, and trimmed repeatability rationale;
- for every step in order: trimmed label, `shlex.split` token array, trimmed expected result, and trimmed correction/note;
- trimmed inputs sorted and deduplicated;
- trimmed failure handling;
- the placeholder-free verification token array;
- dependencies sorted by `(kind, repository_key, path_or_sequence_id)`;
- the complete normalized execution-safety profile;
- promotion target sequence ID, trimmed `use_when`, sorted/deduplicated operation kinds, automation reference, the exact preserved argument array, trimmed pass signal, and qualification limit.

Excluded from the fingerprint: task ID, date, sequence display name, timestamps, repository absolute paths, and every mutable run-observation proof, including dry-run run/event IDs and evidence hashes added after creation. Two specs with the same fingerprint must have byte-equivalent canonical identity objects; otherwise the system fails `candidate-fingerprint-collision` and writes nothing.

Version-2 file identity is `YYYY-MM-DD-<target-sequence-slug>-<fingerprint-first-12>.md`; lineage continues to derive from the repository-relative path. `target-sequence-slug` is exactly `sequence_discovery_log._slug(promotion.sequence_id)`: lowercase the Unicode string, replace each maximal run outside ASCII `[a-z0-9]` with `-`, strip leading/trailing hyphens, and use `unnamed-sequence` only if empty. The fingerprint suffix disambiguates identities whose punctuation, colon, case, or Unicode IDs share a slug; an occupied full path with different content fails closed. Fixtures lock ASCII punctuation, colon, uppercase, Unicode-only, and same-slug/different-fingerprint cases. A registered target sequence ID or active candidate target ID with a different fingerprint fails `target-sequence-id-conflict`; an equal registered fingerprint is a reuse match.

Secret validation applies recursively to every persisted string in the v2 spec, not only commands. The whole spec first passes `work_memory._validate_work_only`, including fixed `SECRET_PATTERNS`. Every string is then rejected when it contains URI user-info, a sensitive query key (`token`, `key`, `sig`, `secret`, or `password`) with a non-placeholder value, or a sensitive name ending in `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`, `ACCESS_KEY`, `PRIVATE_KEY`, `CONNECTION_STRING`, or `SAS` followed by `=` or `:` and a non-placeholder value. Command tokens additionally reject non-placeholder values following `--token`, `--password`, `--secret`, `--api-key`, `--access-key`, `--client-secret`, `--connection-string`, or `--sas-token`. Other fixed literals are allowed. A placeholder is allowed only as an entire `shlex` token in the form already accepted by bootstrap. The `verify-automation` row permits no placeholders because the lifecycle executes it directly. Rejected fixtures cover every sensitive context in inputs, outcomes, notes, failure text, verification, dependencies, and promotion fields; accepted fixtures cover safe fixed literals and fixed-position placeholders.

Capture scans active v2 discovery documents and registered dependency manifests for the fingerprint under a lock and uses strict outcomes without operation-kind fallback:

1. registered match with current final-effective same-path proof → return `registered-ready` with the registered sequence and structured automation entry;
2. registered match without that proof → return `registered-verification-required` with sequence identity and no executable receipt fields; `drive` resumes registered verification;
3. active discovery match → return `discovery-active` with its existing active qualification run or current lifecycle status;
4. no match → create one v2 candidate, start deterministic qualification ordinal zero, and return `discovery-created`;
5. more than one match → fail closed with `candidate-fingerprint-conflict`.

### 3. Deterministic readiness

For v2 only, readiness checkboxes are derived, not manually asserted:

- inputs are present and secret-free;
- commands are present, safe, ordered, and have expected results;
- failure handling is present;
- exact verified path is present and command-grounded;
- promotion profile is complete and valid.

The renderer marks those five boxes checked at creation because validation has already proven the structure. Runtime readiness keeps the existing requirement of two passed same-path current-bundle runs and zero open blockers, but the reducer is corrected to inspect each run's final `verification_recorded` event in ledger order. A run counts only when that final event is `outcome=passed` and `quality=same-path` and its terminal `run_closed` is passed. Earlier passes cannot mask a later failure; a later pass after a failure is the effective result. Manual checkbox mutation remains available for v1 compatibility but cannot make an incomplete v2 contract valid.

Two existing readiness reducer defects are in scope. First, `blocker_recurred` is applied only when its blocker ID was first opened in the candidate lineage. Today `discovery_state` adds every recurrence globally (`scripts/sequence_discovery_log.py:297-304`), so an unrelated lineage can make a valid candidate unready. The implementation aligns this reducer with the lineage-scoped pattern already used in `scripts/work_memory.py:873-880`. Second, the current verification set records any passed same-path event (`scripts/sequence_discovery_log.py:292-295`); it is replaced by the final-effective rule above. Regression fixtures cover cross-lineage recurrence, passed-then-failed, and failed-then-passed runs.

### 4. One canonical flywheel controller

Add `scripts/sequence_knowledge_flywheel.py` with seven commands:

- `capture --spec <json-or-file> --repo-roots-file <json>`: validate v2, deduplicate, create/reuse the candidate, and start or return its deterministic first pending qualification run. The parser requires the roots option and exits 2 when it is absent; capture is the only command allowed to establish the durable roots authority.
- `status --file <candidate>`: return structural validity, current readiness, promotion stage, registered verification state, and the stored promotion profile.
- `dry-run --file <candidate> [--repo-roots-file <json>]`: execute only the immutable read-only dry-run automation, through the same durable resolver/guard/claim/return/verification machinery, and record or return its deterministic governed proof. The optional roots file has the same equality-only behavior as `drive`.
- `approve --file <candidate> --approval-request-id <uuid>`: after explicit human approval, load and revalidate the exact persisted request, append or reuse its deterministic execution approval, and return the approval receipt. It accepts no caller-reconstructed binding fields.
- `drive --file <candidate> [--repo-roots-file <json>]`: read the stored profile and invoke the existing `discovery_promotion_lifecycle` until complete. No promotion metadata is reconstructed from flags. The optional roots file is an equality-only compatibility override: its normalized key/path map must exactly equal the durable predecessor map or the command exits 3 with `repository-roots-authority-missing-or-drifted`; it can never supply missing authority or redirect a root.
- `retire-plan --output <manifest>` and `retire-apply --manifest <manifest> --approved-sha256 <hash>`: create and apply reversible logical retirement.

All commands emit public envelope schema 1. Success is exactly `{"schema_version":1,"ok":true,"command":"<name>","outcome":"<value>","data":{...},"error":null}`, exits 0, and is followed by the final pass-signal line. Failure is `{"schema_version":1,"ok":false,"command":"<name>","outcome":"invalid|blocked|error","data":null-or-actionable-context,"error":{"code":"stable-code","message":"human text","details":{...}}}`, emits no pass signal, and exits 2 for argument/schema validation, 3 for conflict/blocker/approval/stale-state outcomes, or 1 only for unexpected internal failure. Unknown envelope keys are forbidden.

`capture` success outcomes are exactly `registered-ready`, `registered-verification-required`, `discovery-active`, and `discovery-created`. All data contain candidate fingerprint and identity hash. Registered data add sequence ID and match type; `registered-verification-required` also requires the validated candidate path used by `drive`, while only `registered-ready` may add automation reference, exact arguments, canonical command, and pass signal. Discovery data add discovery ID, candidate path, source-bundle hash, run ID or null, and lifecycle status; `discovery-created` requires a run ID and `discovery-active` may return null only when the next lifecycle stage has no active run. Fingerprint conflict is a blocked error, not an outcome. `status` uses outcome `status` and returns those identity fields plus structural validity, readiness, open blocker IDs, current stage, active run ID or null, target sequence ID, and registered-proof state. `dry-run` has only success outcome `dry-run-passed` and returns candidate fingerprint, source-bundle hash, safety-profile hash, dry-run event ID, run ID, verification event ID, close event ID, and evidence SHA-256; absence of a dry-run policy, proof conflict, terminal failure, or stale roots uses the common failure envelope, and ambiguous read-only completion returns the abandoned run ID plus `retryable=true`. `approve` has only success outcome `execution-approved` and returns approval request ID, approval ID, authorized run IDs, approved-at UTC, and already-recorded boolean; stale, mismatched, or absent requests fail closed, while invocation itself is the trusted post-review attestation. `drive` has only success outcome `complete`, returning fingerprint, discovery ID, sequence ID, final stage, and registered verification/close event IDs; correction, qualification-limit, approval, and stale-root conditions are blocked errors with actionable data. `dry-run-required` data contain the candidate/bundle/safety binding; `execution-approval-required` data contain the persisted request ID and complete human-review object. `retire-plan` uses `retirement-plan-created` and returns output path, manifest SHA-256, generation ID, candidate-set/ledger/registry hashes, and disposition counts. `retire-apply` uses `retirement-applied` or `retirement-already-applied` and returns index path, generation ID, manifest hash, and already-applied boolean. Tests assert required/forbidden fields, exact outcomes, error codes, exit codes, and pass-signal behavior for every branch.

`drive` delegates all qualification, promotion, blocker, correction, successor, and registered verification behavior to the existing lifecycle. The capture-created run is qualification ordinal zero: `drive` first resumes it with fresh receipts, executes the v2 resolver, records same-path verification, and closes it. It starts ordinal one only after ordinal zero is terminal and a second proof is still required. Repeated `capture` calls return an existing active current-bundle qualification run; if none is active, they return the next lifecycle status rather than opening an unrelated observation run. Promoted candidates return the registered match. Thus every capture-started run has exactly one terminal path and participates in readiness. `capture` requires the initial repository-roots mapping; later `drive` calls derive roots from durable predecessor runs and never depend on the original caller's temporary roots file.

### 5. Deterministic registered reuse

The registered dependency manifest gains optional `candidate_fingerprint`, `candidate_identity`, repository-relative `source_candidate_path`, and `source_candidate_sha256` copied from v2 discovery during promotion. For v2 all four are required together; for v1 all remain absent-compatible. The hash is SHA-256 of the exact final candidate-file bytes after the promotion-target metadata edit, and promotion computes/stages those final bytes before writing the registered manifest and journal so the same hash survives journal cleanup. On every registered read, the path must resolve under `operations/sequences/discovery/`, its exact current bytes must match `source_candidate_sha256`, and parsing must reproduce the manifest fingerprint/identity and promoted target; missing members, mismatch, or escape fails closed. Fixtures cover restart after journal deletion, missing/altered source, wrong hash/path/fingerprint/identity/target, and v1 absence. Registry parsing remains compatible.

`work_memory select` gains a distinct `--candidate-fingerprint` argument. It is mutually exclusive with `--fingerprint`, `--sequence-id`, and `--discovery-log`; existing `--fingerprint` remains the blocker-fingerprint API unchanged.

Candidate fingerprint selection is strict and never falls through to operation-kind matching:

1. one registered manifest with the exact fingerprint and current same-path proof → select it with reason `candidate-fingerprint-registered`;
2. one registered manifest without current proof → fail `registered-verification-required` and identify the sequence plus its validated source candidate path;
3. one active v2 discovery → select it with reason `candidate-fingerprint-discovery`;
4. no exact match → fail `candidate-discovery-required`, which is the only selection outcome that causes `capture` to create;
5. multiple matches → fail `candidate-fingerprint-conflict`.

The selection receipt adds `candidate_fingerprint`, `candidate_match_type` (`registered` or `discovery`), `candidate_identity_hash`, `automation_ref`, the exact ordered `automation_args`, canonical `automation_command`, and `pass_signal`. Registered values are read from the registered manifest's verified `candidate_identity`, not reconstructed from the registry cell. The sequence runner executes or diagnoses only through these structured receipt fields and the exact script-guard contract; the registry locator remains discovery metadata. Duplicate registered fingerprints fail closed. The controller handles `registered-verification-required` by driving the existing registered verification path, never by broad fallback.

### 6. Logical retirement, not destructive movement

The retirement manifest records:

- schema version, generation ID, creation timestamp, repository root identity, and ledger hash;
- every candidate path, SHA-256, dependency-manifest state/hash, schema generation (`legacy` or `v2`), discovery ID/lineage when present, lifecycle state, open blockers, unterminated runs, promoted target, and disposition;
- disposition is `retired`, `hold-active-run`, `hold-open-blocker`, `hold-pending-correction`, `hold-invalid-v2`, `hold-pending-registered-verification`, `active-v2`, or `registered-provenance`;
- no self-hash field; approval supplies the SHA-256 of the immutable manifest bytes externally through `--approved-sha256`.

Its snapshot schema also records `candidate_set_hash`, registry hash, and ledger hash. `candidate_set_hash` is computed from the sorted list of every discovery candidate markdown path, its content hash, and a typed dependency-manifest component: `{"state":"present","sha256":"..."}` when the paired file exists or `{"state":"missing","sha256":null}` when it does not. The same component is persisted in each row. A missing manifest never removes a legacy candidate from inventory; it is eligible for `retired` only when no higher-precedence hold applies, because logical retirement preserves rather than executes it. Any later appearance, disappearance, or content change of the manifest changes `candidate_set_hash` and makes apply stale. Each `registered-provenance` row records the target sequence ID, registered bundle hash, and the exact current same-path verification and close event IDs that justify the disposition. Apply recomputes the complete candidate set, registry, ledger, target bundles, and proof events and requires exact equality; added, removed, renamed, changed, newly verified, or stale registered inputs make the plan stale. Each unterminated discovery run is assigned exactly once either to its candidate row or, when its source bundle contains no current candidate path, to an `orphan_runs` row that always blocks retirement and preserves its recorded bundle identity.

Disposition precedence is deterministic: `hold-pending-correction` > `hold-open-blocker` > `hold-active-run` > `hold-invalid-v2` > `hold-pending-registered-verification` > `active-v2` > `registered-provenance` > `retired`. The first applicable condition wins and the row records every additional condition as secondary evidence. `hold-invalid-v2` applies to anything claiming version 2 whose identity or schema cannot be validated; it cannot advance automatically. `hold-pending-registered-verification` applies to every promoted candidate whose target lacks the required current final-effective same-path proof. `active-v2` applies to every valid unpromoted v2 candidate. `registered-provenance` applies only to a promoted candidate with that proof. `retired` applies only to legacy, unpromoted, non-held candidates. These predicates are exhaustive, so no v2 or promoted candidate can fall through to retirement. `registered-provenance` and `retired` are terminal inactive membership states and are carried unchanged into every later generation; they can never reactivate. All hold and `active-v2` dispositions remain active. A later generation can advance a legacy held row only when the captured ledger proves all higher-precedence conditions terminal; invalid v2 requires an explicit corrected v2 successor, and pending registered verification advances only after the proof exists.

When several registered same-path proofs exist for a target bundle, the planner first keeps only runs whose **final** `verification_recorded` event in ledger order has outcome `passed` and quality `same-path` and whose terminal event is a passed `run_closed`; it then chooses the close with greatest `(completed_at_utc, run_id)`. The row records that final verification event ID, close event ID, and bundle hash. A later failed verification disqualifies the run. Already-terminal index rows reuse their recorded proof and do not require a newer proof.

`operations/sequences/discovery/retirement-index.json` is the single authority for logical active/retired membership. Only `sequence_knowledge_flywheel retire-apply` writes it. Its schema stores generation ID, applied manifest hash, repository and ledger hashes, and one row per governed path with disposition and evidence. `operations/sequences/discovery/ACTIVE.md` remains a derived human view written by reconciliation; it is not an authority.

The existing approved `reconciliation-policy.json` remains decision provenance, but it cannot reactivate a terminal path. Reconciliation enumeration, rolling execution, active-index rendering, and flywheel dedup all read the retirement index and omit both `retired` and `registered-provenance` rows; hold and `active-v2` rows remain active. Exact `work_memory select --discovery-log <path>`, bundle resolution, blocker/correction lookup, and resume deliberately bypass retirement membership so historical and unterminated runs remain recoverable. New candidates absent from the index are active by default. A missing index means generation zero with every candidate active, preserving backward compatibility.

Retirement planning and apply share one exclusive
`operations/sequences/discovery/.retirement.lock`. `retire-plan` holds it from index
and live-snapshot read through atomic output write. A retry with the same `--output`
first validates the existing manifest and recomputes the snapshot under the lock; if
repository, candidate-set, registry, ledger, and current-index inputs are identical,
it returns the existing bytes, generation, timestamp, and hash. Existing output with
different inputs fails `retirement-plan-conflict`; absent output creates one manifest.
`retire-apply` holds the same lock across manifest verification, index read and
idempotency/conflict checks, live drift validation, and atomic index write.

Apply writes the retirement index atomically. It does not delete, move, or edit candidate bundles. Ordering is exact: parse immutable manifest bytes and verify `--approved-sha256`; read the current retirement index; if it already records the same manifest hash and generation, return `{ok:true, already_applied:true}` before any live snapshot-drift checks. If the same hash points to a different generation or that generation points to another hash, fail `retirement-index-conflict`. Only a not-yet-applied manifest proceeds to repository/ledger/candidate/registry/bundle/proof drift validation and first mutation. Thus a lost-response retry stays idempotent even after later ledger drift. Held entries remain visible until their run, blocker, or correction becomes terminal, after which rerunning the planner produces a new manifest and generation that may advance them to `retired`. Fixtures cover concurrent identical/different plan outputs, plan lost-response replay, plan-versus-apply serialization, concurrent same/different-manifest apply, and concurrent identical/different v2 capture under the existing capture lock.

The controller refuses apply when the repository identity, ledger hash, candidate hashes, or approved manifest hash drift. Apply is idempotent for the same manifest hash. Live `retire-apply` is a destructive-scope operational action and remains separately approval-gated; tests use fixtures, and this implementation run performs only `retire-plan` against the live pool.

### 7. Sequence-runner integration

The sequence-runner skill and a registered `sequence-knowledge-flywheel` sequence become the discovery entry point. An explicit user/registry sequence ID can still be selected directly. Otherwise, for an operational repeatable task the runner first builds the complete v2 spec and repository-roots map, then calls flywheel `capture` as the sole public match/create path. `capture` normalizes the identity, computes the fingerprint, and returns exactly `registered-ready`, `registered-verification-required`, `discovery-active`, or `discovery-created`, with conflict in the blocked error envelope; it never invokes generic operation-kind selection. `registered-ready` uses the structured entry; both discovery outcomes go to `drive`, and `registered-verification-required` goes to `drive --file` using its returned validated source candidate path; blockers use the existing correction path and then rerun `drive`. On `dry-run-required`, the runner invokes `dry-run` and resumes `drive`. On `execution-approval-required`, it presents the complete returned human-review object and pauses; only explicit approval of that exact request permits invocation of `approve --approval-request-id`, which is the trusted attestation boundary, after which it resumes `drive`. Promotion changes the bundle, so registered verification repeats the same dry-run/request/human-approval/approve/resume successor when its safety profile requires it. The runner never hand-creates discovery Markdown, reconstructs promotion or approval flags, or treats an earlier approval as authority for a new request.

This is the practical automatic boundary available to Codex: governed sequence-runner executions are captured. The implementation does not claim visibility into arbitrary unguarded shell history, browser actions, or external tool calls that never pass through the runner.

The meta-sequence registration is exact. `work_memory.OPERATION_KINDS` and
`ALWAYS_OPERATIONAL` gain the dedicated `sequence-governance` kind; no ordinary
candidate uses that kind. The registry row is:

```text
| `sequence-knowledge-flywheel` | Capture, deduplicate, inspect, dry-run, explicitly approve, drive, and retirement-plan governed operational sequence knowledge through one canonical controller. | `operations/sequences/sequence-knowledge-flywheel/` | memory-knowledge:scripts/sequence_knowledge_flywheel.py | `SEQUENCE KNOWLEDGE FLYWHEEL OK` | `sequence-governance` | `sequence-knowledge-flywheel-v2` |
```

The sequence document classifies with `sequence-governance`, selects explicitly
with `--sequence-id sequence-knowledge-flywheel`, activates that document, and
then routes exactly one requested subcommand to `python3
scripts/sequence_knowledge_flywheel.py <capture|status|dry-run|approve|drive|retire-plan|retire-apply>
...`. Each successful subcommand writes its JSON result and then the exact final
stdout line `SEQUENCE KNOWLEDGE FLYWHEEL OK`; failure never writes that line.
`retire-apply` additionally requires the already-defined external manifest-hash
approval. The dependency manifest covers the controller and composed modules.
Because this row has a dedicated operation kind and is selected explicitly, it
cannot enter generic matching for `workflow-drive`, `other`, or a candidate's
own operation kind. Tests prove row parsing, explicit selection, pass-signal
placement, argument routing for all seven subcommands, and absence from ordinary
operation-kind candidate sets.

Receipt task IDs are distinct UUIDv5 values under `uuid.NAMESPACE_URL`. Given
the caller's external task ID, the governance-control task ID is UUIDv5 of
`memory-knowledge:sequence-flywheel:governance:<external_task_id>`. After v2
normalization computes the fingerprint, the capture task ID is UUIDv5 of
`memory-knowledge:sequence-flywheel:capture:<external_task_id>:<fingerprint>`.
Each lifecycle receipt task ID is UUIDv5 of
`memory-knowledge:sequence-flywheel:receipt:<run_id>`. Governance classify,
explicit meta select, and activate use only the governance ID and
`sequence-governance`; candidate classify, strict fingerprint select, and
capture activation use only the capture ID and `CandidateIdentity.operation_kind`;
attempt receipt reconstruction uses only the attempt ID. Candidate-fingerprint
selection verifies the classification receipt operation kind equals the
identity operation kind. Reusing or crossing these receipt chains fails
`flywheel-task-id-scope-mismatch` before activation or mutation.

## Data and Control Flow

```text
task intake
  -> sequence runner identifies operational/repeatable work
  -> build complete v2 spec and repository-roots map
  -> flywheel capture normalizes identity and computes fingerprint
       -> registered-ready: return exact automation
       -> registered-verification-required: drive proof
       -> discovery-active: reuse candidate/run
       -> discovery-created: create candidate/run
  -> lifecycle enters the next qualification or registered-verification stage
       -> dry-run-required: execute/resume read-only dry-run, then drive
       -> execution-approval-required: persist request, present exact review, pause
            -> explicit human approval: approve exact request, then drive
       -> blocker/correction required: use existing correction successor, then drive
  -> lifecycle qualifies current bundle twice using only stage=qualification runs
  -> readiness predicate passes
  -> journaled atomic promotion
  -> registered same-path verification, including a new exact approval successor when required
  -> fingerprint now selects registered automation
```

All durable state remains in repository artifacts and `operations/work-memory/events.jsonl`; temporary locks and receipts remain reconstructable control-plane state.

All deterministic identities use `uuid.NAMESPACE_URL`. The canonical attempt name is `memory-knowledge:sequence-flywheel:attempt:<subject_id>:<source_bundle_hash>:<stage>:<ordinal>` and its UUIDv5 is the run ID; every new v2 `run_started` persists that same stage. Event IDs are UUIDv5 over `memory-knowledge:sequence-flywheel:event:<run_id>:<event_type>` for `run-started`, `execution-claimed`, `execution-returned`, `verification-recorded`, and `run-closed`. The lifecycle calls two new work-memory CLI commands: `execution-claim --run-id --event-id --command-sha256 --source-ref` and `execution-return --run-id --event-id --command-sha256 --exit-code --pass-signal-matched <yes|no> --stdout-sha256 --stderr-sha256`. They infer subject, lineage, stage, and bundle from `run_started`, return `{ok:true,event_id,already_recorded}`, exit 0 for an identical replay, and exit 3 with `execution-event-conflict` or `execution-event-order-invalid` for payload/order violations. Before mutation the lifecycle inspects the ledger: an absent run is started; no claim means safe dispatch; claim without return follows the stage-specific ambiguity rule; return without verification deterministically produces verification; a passed verification skips replay and proceeds to close; a passed terminal run advances only its own stage; a failed terminal run consumes that stage's ordinal and the next allowed attempt uses the next ordinal. Receipt task IDs include the attempt key so a bundle change cannot reuse stale receipts. The existing ledger transaction contract (`scripts/work_memory.py:517-552`) remains the persistence authority and is extended with these exact commands and schemas.

Execution events are presence-based and backward-compatible. `command_sha256` is SHA-256 of the UTF-8 bytes of exactly `shlex.join(resolved_argv)`; claim and return persist and compare that digest, while `automation_command` remains the separate stable identity display. A historical run with neither event remains valid and follows all existing v1 validation. Once either new event exists for a run, there may be exactly one claim and at most one return; claim must follow `run_started` and precede verification or terminal events; return requires an earlier claim, precedes new-path verification, and must match run, subject, lineage, source-bundle hash, and command hash exactly. No claim or return may be appended after a terminal event. A claimed run may close passed only after return and passed verification. Claim-without-return has exactly two terminal paths: a `stage=dry-run` run may append only the deterministic `run_abandoned` event and exact reason defined above; every other stage may close failed only in the same correction transaction that records the ambiguity blocker's replay-safety correction. A return without verification remains resumable. These invariants are enforced by the global ledger validator and transaction preflight without requiring execution events on legacy runs.

Receipts remain expiring control-plane evidence, not durable resume state. Before guarding a resumed active run, the lifecycle reconstructs a canonical repository-roots JSON file under that attempt's receipt directory from `run_started.repository_roots`, then regenerates classification, exact selection (including successor metadata), and activation receipts under the same deterministic attempt task ID using that file. The reconstructed file is control-plane state and is not part of candidate identity. The lifecycle validates every mapped root still resolves to the recorded absolute path and that the new selection's subject, lineage, source bundle, and source-bundle hash equal the durable `run_started` event; it does not require the new timestamped receipt hashes to equal the hashes recorded at start. If any root or durable binding differs, resume fails closed. The fresh receipts authorize the command guard; verification and close then target the existing run ID. This explicitly handles receipt/root-file deletion and expiry without weakening current bundle validation.

Every fresh attempt also has a durable roots predecessor. Qualification ordinal `N>0` copies the exact `repository_roots` map from ordinal `N-1`'s `run_started`; a correction successor copies it from its corrected predecessor; the first registered-verification attempt copies it from the latest passed qualification run selected by `(completed_at_utc, run_id)`; and later registered attempts copy it from their immediately preceding registered run. The controller writes a canonical roots file from that durable map before starting the fresh run, then `run_started` persists the same map for the next link. A caller-supplied roots file on `drive`, if accepted for compatibility, must normalize to byte-equivalent key/path pairs and cannot add, remove, or redirect a root. No qualifying predecessor, a missing mapped root, or any mismatch fails `repository-roots-authority-missing-or-drifted` before `run_started` or command execution. Tests cover ordinal one, correction successor, first registered verification, later registered retry, override equality, and drift rejection.

## Failure, Resume, and Idempotency

| interruption | retry behavior |
| --- | --- |
| capture before write | no artifact exists; retry creates it |
| candidate written before receipt/run | bootstrap's existing conflict/idempotency checks reuse identical content and finish receipts |
| duplicate concurrent capture | lock plus fingerprint re-scan returns the single winner |
| qualification run started, then interrupted | deterministic attempt identity resumes the existing run instead of starting another |
| run started before execution claim | retry writes the deterministic claim and executes once |
| execution claimed, return event absent | never replay or qualify; open `ambiguous-automation-outcome` from claim evidence and require an actual replay-safety bundle correction before successor verification |
| execution return recorded, verification absent | derive verification from the durable return event without replay |
| verification event recorded, run not closed | lifecycle detects the event and writes only the deterministic close event |
| qualification command fails | existing lifecycle catalogs blocker and requires correction/successor evidence |
| dry-run started, no claim | resume and dispatch that read-only attempt once |
| dry-run claimed, return absent | record deterministic abandonment; return retryable; next explicit `dry-run` uses the next dry-run ordinal without qualification credit |
| dry-run returned, verification/close absent | complete only the missing proof events without replay |
| dry-run terminal failure | return blocked and retryable; next explicit `dry-run` uses the next dry-run ordinal; qualification quota/readiness remain unchanged |
| drive lacks required dry-run proof | return `dry-run-required`; runner invokes `dry-run` and resumes the same drive path |
| drive lacks execution authority | persist/reuse exact approval request, return its human-review object, and perform no claim |
| explicit human approval received | runner invokes `approve` for that request only, then resumes `drive`; a new registered bundle produces a new request |
| promotion interrupted | existing promotion journal recovers or rolls back |
| registered verification interrupted | the same deterministic registered attempt resumes and completes it |
| retirement plan becomes stale | apply fails closed on repository, ledger, file, or manifest hash drift |
| retirement apply interrupted | atomic generation files and manifest-hash idempotency make retry safe |

## Granular Implementation Surface

1. `scripts/sequence_discovery_log.py`: render and parse v2 metadata/profile; derive v2 structural readiness.
2. `scripts/discovery_bootstrap.py`: validate complete v2 specs, reject secrets, compute fingerprint, and deduplicate under the existing lock while preserving v1.
3. `scripts/sequence_promote.py`: copy optional fingerprint, identity, and validated source candidate path into the registered dependency manifest without changing v1 promotion semantics.
4. `scripts/work_memory.py`: add strict typed candidate-fingerprint selection, backward-compatible run stages, dry-run/request/approval ledger events, and deterministic event reuse support while preserving blocker-fingerprint behavior.
5. `scripts/discovery_promotion_lifecycle.py`: derive and resume deterministic stage attempts, resolve cross-repository v2 automation, enforce exact pass signals and execution authority, and consume `CandidateIdentity` through the controller.
6. `scripts/discovery_candidate_reconciliation.py`: honor the retirement index when enumerating, applying rolling policy, and rendering `ACTIVE.md`, while preserving exact-path resume.
7. `scripts/sequence_knowledge_flywheel.py`: canonical capture/status/dry-run/approve/drive/retirement controller that composes the existing modules.
8. `skills/sequence-runner/SKILL.md`: replace manual no-match/promotion reconstruction with the controller.
9. `operations/sequences/sequence-knowledge-flywheel/{sequence.md,dependencies.json}` and `operations/sequences/SEQUENCES.md`: catalog the one-shot operational entry.
10. Focused tests in existing suites plus `tests/test_sequence_knowledge_flywheel.py`.
11. Task research, audits, plan, and verification artifacts remain under `Tasks/sequence-knowledge-flywheel/`.

No changes are required in `sequence_guard.py`, the blocker schema, the corpus MCP, or the working-agreement directive source. Guard observations are not the stable identity boundary; complete v2 capture is.

## Acceptance Criteria

1. A complete v2 spec creates one candidate with no `TBD`, all structural readiness boxes checked, a stable persisted `CandidateIdentity`, a dependency manifest, and deterministic active qualification ordinal zero.
2. Repeating the same behavior identity with a different task ID, date, or sequence display name reuses the candidate and never creates a second discovery file; changing a fingerprint-bearing step note creates a distinct identity.
3. Every specified sensitive context, CR/LF heading injection, fenced-block terminator, and Markdown/registry pipe hazard is rejected across all persisted v2 strings before durable writes, safe fixed literals and fixed-position placeholders are accepted outside executable automation arguments, the identity block re-canonicalizes byte-for-byte, and the single placeholder-free `verify-automation` row equals `verified_path`; resolver tests prove exact argument preservation/rejection, `.py`/`.sh`/executable precedence, identity `automation_command`, resolved argv, script guarding, confinement, repository `cwd`, ordered argv equality, exit-zero enforcement, and exact stdout signals.
4. Distinct behavior specs never alias; same-date/name specs receive fingerprinted paths; occupied path, duplicate fingerprint, target-sequence-ID, sequence-dependency-ID, and file/glob confinement violations fail closed before path construction.
5. Sequence-runner builds the complete v2 identity before calling `capture`; `capture` computes the fingerprint and returns only `registered-ready`, `registered-verification-required`, `discovery-active`, or `discovery-created`, with conflict in the schema-1 blocked envelope and no generic operation-kind fallback, while deterministic governance/capture/attempt task IDs keep receipt chains separate and legacy blocker `--fingerprint` remains unchanged.
6. `drive` resumes and terminates capture-created qualification ordinal zero before starting ordinal one; only two passed same-path current-bundle runs with `stage=qualification` plus zero blockers cause promotion using `CandidateIdentity` metadata. Dry-run runs never count toward the quota, readiness, or lifecycle advancement, and registered proof requires `stage=registered-verification`.
7. Crash tests use the locked `uuid.NAMESPACE_URL` names and `execution-claim`/`execution-return` CLI results; before claim, after claim, after process return, before verification, after verification, after close, during promotion, and during registered verification they prove one deterministic run per attempt, safe first dispatch, durable result completion, no automatic ambiguous replay or probe execution for effectful automation, mandatory replay-safety bundle correction, correction-driven failed finalization, and corrected successor re-entry. Safety fixtures prove the immutable class normalization matrix, fingerprint stability across refreshed proof, backward-compatible persisted stages, dry-run contamination/quota exclusion, the single canonical stage attempt ID, deterministic dry-run abandonment ID/validator exception, no-claim/returned/failed/ambiguous read-only retry paths, exact candidate/bundle/safety/command/verification/close binding, dry-run conflict/replay behavior, the exact approval-request required/null field schema, deterministic qualification/registered authorized-run sets, proof-binding-hash identity, rollback-proof refresh creating a new request, stale-request rejection, deterministic approval event schema, timestamp-preserving approval replay, current dry-run and rollback proof lookup, request-before-approval-before-claim ordering/conflict behavior, external bundle/run binding, registered-bundle reapproval, and approval-required failure before claim.
8. Promotion interruption recovery remains green under existing journal tests.
9. Completion is withheld until the registered sequence has a current same-path proof.
10. Selecting by the same fingerprint returns the registered sequence plus verified identity hash, automation reference, exact ordered arguments, canonical command, and pass signal after proof; duplicate fingerprints fail closed and sequence-runner consumes only those structured receipt fields.
11. Existing v1 bootstrap, discovery, promotion, selector, and reconciliation tests remain green; controller tests prove v1 cannot auto-drive or auto-promote, and explicit-upgrade fixtures prove held/conflicting refusal plus provenance-preserving logical-retire then complete-v2 capture.
12. Retirement planning inventories every candidate and includes every unterminated discovery run in its captured ledger snapshot exactly once with a hold disposition, without moving or editing a candidate.
13. Retirement fixture tests prove exhaustive invalid-v2/pending-registered/active-v2/provenance/legacy classification, legacy-only targeting, typed missing/present dependency-manifest hashing, missing-manifest inventory and drift, terminal retired/provenance rows, deterministic proof-pair choice, candidate-set/registry/ledger/registered-bundle/proof-event drift rejection, external manifest-hash approval, disposition precedence, orphan-run holds, held-entry advancement, reconciliation and `ACTIVE.md` rendering, exact-resume bypass, first-apply validation, conflicting-index failure, and already-applied lost-response retry after later ledger drift.
14. A blocker recurrence in another lineage does not affect candidate readiness; recurrence of a blocker opened in the candidate lineage does. Readiness uses only each run's final verification, so passed-then-failed does not count and failed-then-passed does.
15. `sequence-governance` is rejected from ordinary v2 specs; the exact meta-sequence row selects explicitly, routes all seven subcommands, emits its final pass signal only on success, and never appears in ordinary operation-kind candidate sets.
16. `scripts/run_pytest.sh` passes the focused suites, then the complete repository suite.
17. Independent review confirms every changed surface matches this document and no unrelated dirty path changed.
18. An external-effect fixture proves the complete registered successor twice: `drive` returns `dry-run-required`; `dry-run` records isolated read-only proof; `drive` persists and returns an exact approval request; no claim occurs before explicit approval; runner policy invokes `approve` as the trusted human-attestation boundary and consumes only that request; `drive` resumes qualification; promotion persists and validates the source candidate path; the unverified registered match returns that locator; promotion creates a distinct registered-bundle request; and the same human-gated successor completes registered verification without reconstructed binding flags.

## Out of Scope

- inferring sequences from arbitrary terminal history, browser interactions, MCP calls, or conversation transcripts outside the governed sequence-runner path;
- changing directive promotion or corpus-note promotion, both of which retain their human gates;
- deleting or moving legacy discovery artifacts;
- automatically resolving existing blockers, corrections, or unterminated runs;
- running live retirement apply without a separate approval for the exact manifest hash;
- committing, pushing, deploying, or modifying another repository.

## Convergence Delegation Command Contract

The following fixed command shapes govern the assessment-only agent slot used by each hardening and review stage. Only the two runtime IDs vary; executable, subcommand, ledger, flags, labels, and token positions remain exact.

```text
python3 /Users/kamenkamenov/.codex/skills/_shared/agent_slot_ledger.py guard /private/tmp/sequence-knowledge-flywheel-agent-slots.json
python3 /Users/kamenkamenov/.codex/skills/_shared/agent_slot_ledger.py acquire /private/tmp/sequence-knowledge-flywheel-agent-slots.json --label <stage-label>
python3 /Users/kamenkamenov/.codex/skills/_shared/agent_slot_ledger.py bind-agent /private/tmp/sequence-knowledge-flywheel-agent-slots.json --slot-id <slot-id> --agent-id <agent-id>
python3 /Users/kamenkamenov/.codex/skills/_shared/agent_slot_ledger.py mark-completed /private/tmp/sequence-knowledge-flywheel-agent-slots.json --slot-id <slot-id>
python3 /Users/kamenkamenov/.codex/skills/_shared/agent_slot_ledger.py mark-closed /private/tmp/sequence-knowledge-flywheel-agent-slots.json --slot-id <slot-id> --close-evidence <previous-status>
python3 /Users/kamenkamenov/.codex/skills/_shared/agent_slot_ledger.py release /private/tmp/sequence-knowledge-flywheel-agent-slots.json --slot-id <slot-id>
```
