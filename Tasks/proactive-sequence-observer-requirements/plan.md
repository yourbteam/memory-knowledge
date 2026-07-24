# Proactive Sequence Observer — Granular Implementation Plan

## Goal and fixed boundary

Implement a deterministic, passive observer that turns durable evidence from completed governed operational work into exactly one advisory disposition: `NO_CANDIDATE`, `LINK_REGISTERED`, `LINK_DISCOVERY`, or `PROPOSE_DISCOVERY`. The observer may persist safe observations and decisions, link an existing candidate, or submit one complete candidate through the canonical discovery bootstrap. It must never execute a candidate, grant authority, qualify or promote a discovery, register a sequence, alter lifecycle gates, scan conversations or terminal history, write to observed repositories, or contact external services.

The frozen requirements are `OBS-001` through `OBS-030` in `Tasks/proactive-sequence-observer-requirements/research-package/requirements.json`. This plan implements all of them. It does not redesign unrelated workflow, telemetry, deployment, backlog cleanup, model, or policy behavior.

## Practical old-versus-new result

- Today: `sequence_guard.py` authorizes a command but only prints a transient receipt. `work_memory.py` records that a run started and later closed, but not the exact authorized command that was actually dispatched and returned. A later process cannot reconstruct a complete operation without terminal or conversation memory, so an automatic observer would guess.
- After this plan: the canonical checked invoker persists a claim and return for the exact guard-authorized argv and provenance. At run close, a passive deterministic observer consumes only those durable events, applies bounded eligibility/value/identity rules, searches registered identities first and active discoveries second, and either records why no candidate is safe or submits one complete bootstrap specification. Promotion remains entirely under the current readiness, blocker, correction, qualification, atomic-promotion, and registered-verification gates.
- Cost: one required checked-in invoker replaces the current two-step “guard, then separately execute” mechanic for observable runs; the ledger gains additive versioned events; terminal close performs one bounded local observer pass. Existing v1 events and non-observer runs remain valid, and disabling the observer returns close behavior to its present state.

## Locked implementation decisions

1. `sequence_guard` remains the sole command-authority producer. The observer is not an authority source.
2. A new canonical invoker owns dispatch of already-authorized work and writes `execution_claimed` immediately before subprocess dispatch and `execution_returned` immediately after return. The observer itself never imports or calls `subprocess`.
3. Candidate identity is a shared versioned canonical object used by the invoker evidence reducer, observer, discovery manifest, promotion copy, reconciliation, and registered matching. There is no operation-kind fallback or parallel identity.
4. Only explicit volatility fields are removed: task/run/event/receipt IDs, timestamps, absolute root locations, and configured harmless argument positions. Executable, ordered argv, semantic flags, step order, repository-qualified dependencies, effect class, expected outcome, and verification contract remain identity-bearing.
5. The final-effective verification rule is shared and ordered: for a run/bundle, only the last applicable `verification_recorded` event counts; it must be `passed`, `same-path`, and exact-bundle. Earlier passes, proxy evidence, later failures, cross-lineage evidence, and unrelated bundles never become proof. Historical v1 consumers keep existing behavior unless reading a v2 candidate.
6. Registered matching precedes active-discovery matching. Active candidates come from a fresh deterministic reconciliation inventory, not `operations/sequences/discovery/ACTIVE.md` as authority.
7. Observer decisions are append-only and immutable. Governed later lifecycle dispositions can be joined by candidate fingerprint but can affect future decisions only through a new explicit rule/config version.
8. Unsupported time-saved or avoided-reconstruction estimates are `UNKNOWN` and receive no value credit.
9. Observer configuration version 1 is fixed for this implementation: evidence age 90 days; at most 512 ledger events after run/identity prefiltering; one candidate write; 2,000 ms elapsed time; and only the canonical ledger, registry, discovery documents/manifests, selected source-bundle files, and governed repository-root map. Events are ordered by `(recorded_at_utc, event_id)` descending. A cap returns API status `CAP_REACHED`, persists disposition `NO_CANDIDATE`, `safe_failure_code="CAP_REACHED"`, and the last consumed tuple as `cap_cursor`; resume continues strictly before that tuple and cannot widen the roots or surfaces.
10. Value rule version 1 uses a threshold of 20 and five bounded components: recurrence = 0/10/20 for zero/one/two-or-more prior compatible task IDs; saved effort = `UNKNOWN`/0 unless valid run timestamps exist, then 5/10/20 for at least 2/10/30 minutes; correction reduction = 0/10/20 for none/one exact verified correction/repeated exact blocker plus verified successor; operational risk = 0 for read-only/single-test/single-build, 5 for other, 15 for image/container/workflow-drive/package, and 20 for auth/deploy/database/remote-operator/cleanup; reconstruction avoided = 0/10/20 for one-to-two/three-to-five/six-or-more exact steps, with an explicit special-environment or semantic-flag annotation raising this component to at least 10. A component without its stated evidence is `UNKNOWN` and contributes zero. Eligibility, structural completeness, score at least 20, and at least one positive evidence-backed component are all required.
11. Suppression rule version 1 binds `(candidate_fingerprint or safe incomplete-evidence fingerprint, rule_version, evidence_set_hash)`. Low-value or incomplete `NO_CANDIDATE` decisions are suppressed for 30 days; governed dismissal or quarantine is suppressed for 90 days. A changed semantic identity, changed evidence-set hash, explicit config/rule version, or expiry permits reconsideration; a timestamp alone does not.
12. CandidateIdentity carries the shared flywheel effect-class attestation `read-only`, `idempotent-local`, `external-reversible`, or `external-irreversible`; it is supplied explicitly in `operation_context_recorded`, validated independently, and never inferred from command text. The existing `run_started.operation_kind` remains the sole input to the observer value-risk table. A missing effect-class attestation yields `NO_CANDIDATE`; changing it changes identity.

## Change 1 — Add shared candidate identity and final-verification contracts

**Files**

- Add `scripts/sequence_candidate_contract.py`.
- Update `scripts/work_memory.py` only to call the shared validator/reducer where ledger semantics are required.
- Add `tests/test_sequence_candidate_contract.py`; extend `tests/test_work_memory.py` for compatibility.

**Implementation**

- Define closed schema `CandidateIdentity` version 1 with: ordered steps; exact token arrays; original guard provenance (`sequence_doc`, `discovery_log`, `script`, or `tool_help`); stable repository-qualified source references and dependencies; existing operation kind; explicit shared effect class; expected outcome; verification contract; declared volatility policy; and candidate fingerprint.
- Canonicalize with the existing `canonical_bytes` rules and compute the fingerprint as SHA-256 of the complete normalized identity. Reject unknown fields, malformed argv/control tokens, identity/fingerprint disagreement, absolute-path authority, unsupported provenance, and semantic collisions.
- Preserve original authority when an observer record derives a step: derivation IDs are provenance links, not a fifth authority class.
- Permit volatility only through finite typed annotations persisted with the operation context: `task_id`, `run_id`, `event_id`, `receipt_path`, or `timestamp`, each bound to an exact step argument index. The checked invoker verifies that the annotated token equals the corresponding governed value before replacing it with the typed placeholder. No free-form regex, wildcard, inferred harmless argument, or caller-selected arbitrary value may be normalized.
- Add a shared `final_effective_verification(...)` reducer for exact lineage/run/bundle and versioned stage semantics. Use it for v2 observer/flywheel records while preserving legacy interpretation for existing v1 data.
- Add recursive safe-payload validation that reuses the existing forbidden-key and secret/personal-content patterns and extends them only for the closed observer schemas. Reject raw output, auth, credential, personal-profile, transcript/history, encoded-secret, and unknown nested fields before persistence or diagnostics.

**Why first**

Every later writer and reader must hash, compare, and verify the same behavior. Building observer-local normalization would create identity drift and duplicate candidates.

**Requirements**

`OBS-011`, `OBS-014`, `OBS-015`, `OBS-017`, `OBS-026`, `OBS-027`, `OBS-028`.

## Change 2 — Persist the real authorized execution boundary

**Files**

- Update `scripts/work_memory.py`.
- Update `scripts/sequence_guard.py` to expose a library-level authorization result without changing current CLI output.
- Add `scripts/sequence_checked_exec.py`.
- Update `skills/sequence-runner/SKILL.md` so observable command execution uses the checked invoker rather than a separated guard call and manual dispatch.
- Add `tests/test_sequence_checked_exec.py`; extend `tests/test_sequence_guard.py` and `tests/test_work_memory.py`.

**Implementation**

- Add strict additive ledger events:
  - `operation_context_recorded`: exact required fields after the common event fields are `context_id`, `run_id`, `subject_id`, `lineage_id`, `source_bundle_hash`, `repository_roots_hash`, `intended_outcome`, `repeatability_reason`, `repeatability_evidence_ids`, `required_inputs`, `dependencies`, `failure_handling`, `verification_contract`, `effect_class`, `environment_annotations`, `semantic_flag_annotations`, and `volatility_annotations`; optional field set is empty. `required_inputs` contains names/descriptions, never values. `dependencies` entries have exactly `repository_key,path`. `failure_handling` entries have exactly `fingerprint,symptom,response`. `verification_contract` has exactly `quality` (`same-path`), `expected_outcome` (`passed`), and nonempty safe `success_evidence`. Effect class is the four-value shared enum. Semantic flag entries have exactly `step_ordinal,arg_index`; volatility entries have exactly `step_ordinal,arg_index,kind`, where kind is the five-value volatility enum. Lists are finite, ordered where behavior/order matters, and recursively safe.
  - `execution_claimed`: exact required fields are `execution_id`, `context_id`, `run_id`, `subject_id`, `lineage_id`, `source_bundle_hash`, `step_ordinal`, `step_id`, `argv`, `command_sha256`, `command_source`, `source_ref`, `repository_roots_hash`, `operation_kind`, `effect_class`, and `claimed_at_utc`; optional field set is empty. `source_ref` has exactly `repository_key,path`; source and operation/effect enums must match the bound context/run.
  - `execution_returned`: exact required fields are `execution_id`, `context_id`, `run_id`, `subject_id`, `lineage_id`, `source_bundle_hash`, `exit_code`, `result`, and `returned_at_utc`; optional field set is empty. `result` is exactly `passed` for exit zero and `failed` otherwise. It stores no stdout/stderr, environment, secret-bearing payload, or conversation text.
- Deterministic IDs are UUIDv5 under `uuid.NAMESPACE_URL`: `context_id` over `memory-knowledge:observer:context:<run_id>:<source_bundle_hash>`; `execution_id` over `memory-knowledge:observer:execution:<context_id>:<step_ordinal>:<command_sha256>`; claim event ID over `memory-knowledge:observer:claim:<execution_id>`; and return event ID over `memory-knowledge:observer:return:<execution_id>`. Timestamps never enter identity.
- Add idempotent work-memory CLI/API operations:
  - `record-operation-context --run-id <id> --context-file <json>`;
  - `execution-claim --run-id <id> --context-id <id> --step-ordinal <n> --step-id <id> --argv-json <json-array> --command-source <enum> --source-ref-repository <key> --source-ref-path <path> --repository-roots-hash <sha256>`;
  - `execution-return --execution-id <id> --exit-code <int>`;
  - `observer-decision-append --decision-file <json>`, `observer-bootstrap-result-append --result-file <json>`, and `observer-link-append --link-file <json>` for the observer-owned records defined below.
  Exact replays return `{"ok":true,"already_recorded":true,"event_id":...,<domain_id>:...}`; first writes return the same with `already_recorded:false`. Schema/enum/argument errors return safe `invalid-<record>-<field>` with exit 2; missing or invalid run-state/order returns a stable typed code with exit 3; deterministic-ID content conflict returns `<record>-id-conflict` with exit 3; bundle/root/source drift or path escape returns a stable typed code with exit 4; I/O/lock failure uses exit 5. No error payload echoes argv, context text, or raw field values.
- The checked invoker accepts an already classified/selected task, step metadata, guard source, source reference, and exact argv. It obtains guard authorization, writes the claim transaction, dispatches that exact argv without shell reparsing, writes the return in a `finally` path, and exits with the child result. It does not interpret the command as a candidate or grant any new execution authority.
- The invoker supports exactly the same direct command shape already accepted by `sequence_guard` and executes an argv array with `shell=False`; pipes, redirections, substitutions, compound shell syntax, and other guard-rejected control tokens remain unsupported and unobservable rather than being wrapped in a shell. The runner records `operation_context_recorded` once while the task facts are known, then uses the invoker for each observable step. Existing separated guard/manual execution remains compatible but cannot qualify for `PROPOSE_DISCOVERY` because its evidence is incomplete.
- A claim without a return is an ambiguous execution result. Neither invoker recovery nor observer replays or probes it. A returned event without later observation is safe for observer retry.
- Preserve current `sequence_guard.py guard` behavior for callers not yet using observation; observer disablement and legacy sequences continue to operate exactly as today, but they do not become proposal-eligible without complete claim/return evidence.

**Why**

This closes the confirmed producer gap. Run-start/close records alone cannot prove what was actually run, in what order, or under which command authority.

**Requirements**

`OBS-002`, `OBS-005`, `OBS-013`, `OBS-015`, `OBS-020`, `OBS-021`, `OBS-023`, `OBS-026`, `OBS-027`.

## Change 3 — Add the bounded deterministic observer evaluator and audit record

**Files**

- Add `scripts/sequence_observer.py`.
- Update `scripts/work_memory.py` with closed observer events and an idempotent append API.
- Add `tests/test_sequence_observer.py`.

**Implementation**

- Define `ObserverConfig` version 1 with finite defaults and CLI overrides: maximum evidence age, maximum observation count, maximum candidate writes (hard maximum one), maximum elapsed milliseconds, allowed repository keys/surfaces, deterministic pagination cursor, value threshold, and suppression review/expiry policy.
- Observer version 1 triggers only from a durable `run_closed` event. Active, abandoned, ambiguous, mutating, and checkpoint state is not evaluated in this version. The trigger identity is deterministic from terminal event ID, observer version, config hash, and ledger snapshot hash.
- Reconstruct the ordered operation only from a complete contiguous set of claimed-and-returned executions plus exact final-effective verification and bound blocker/correction evidence. Missing order, missing return, failed execution, unsupported provenance, incomplete dependency/root binding, or missing verified outcome produces `NO_CANDIDATE` with typed reasons.
- Take outcome, repeatability, input names, dependency decision, failure handling, verification contract, special-environment facts, and volatility annotations only from the single exact-bundle `operation_context_recorded` event. Claim/return records never invent or paraphrase them. Missing or conflicting context produces `NO_CANDIDATE`.
- Encode eligibility version 1 for every standing trigger: at least three meaningful steps; evidenced recurrence; external-system interaction; image/container/auth/deploy/workflow drive; special environment/flags; or a repeated corrected failure. Trivial read-only and isolated one-step work is ineligible unless another explicit trigger applies.
- Encode the locked value rule version 1 and threshold above. Each component records value, evidence IDs, and `KNOWN|UNKNOWN`; unsupported estimates are `UNKNOWN` with zero credit.
- Persist `observer_decision_recorded` with exact required fields after common event fields: `decision_id`, `observer_version`, `rule_version`, `config_hash`, `trigger_event_id`, `trigger_type`, `ledger_snapshot_hash`, `evidence_event_ids`, `evidence_set_hash`, `candidate_identity`, `candidate_fingerprint`, `eligibility`, `value_components`, `threshold`, `considered_registered_ids`, `considered_discovery_ids`, `disposition`, `target_kind`, `target_id`, `suppression`, `cap_cursor`, and `safe_failure_code`; optional set is empty and unavailable values are explicit `null`. `trigger_type` is exactly `run_closed`; disposition remains one of the four frozen outcomes. `CAP_REACHED` is never a disposition: it is the API status and safe failure code paired with `NO_CANDIDATE` and a non-null cursor. Target kind is `registered`, `discovery`, or null. Eligibility and each value component use closed versioned objects; suppression and cap cursor use the locked rules above. Decision ID is UUIDv5 over `memory-knowledge:observer:decision:<trigger_event_id>:<observer_version>:<rule_version>:<config_hash>:<ledger_snapshot_hash>:<cursor-or-root>`.
- Persist `observer_bootstrap_result_recorded` after every canonical bootstrap return. Exact required fields are `bootstrap_attempt_id`, `attempt_ordinal`, `decision_id`, `bootstrap_request_sha256`, `outcome`, `safe_error_code`, `retryable`, `discovery_id`, `lineage_id`, `run_id`, `source_bundle_hash`, `document_path`, and `manifest_path`; optional set is empty and unavailable success/failure fields are explicit `null`. Outcome is `succeeded` or `failed`; safe errors never include raw bootstrap input. Attempt ID is UUIDv5 over `memory-knowledge:observer:bootstrap:<decision_id>:<bootstrap_request_sha256>:<attempt_ordinal>`. Exact replay is idempotent; a retry after a persisted retryable failure uses the next ordinal, while a crash before result persistence reuses the same ordinal and lets bootstrap recover the identical request.
- Persist `observer_candidate_linked` only for a successful link/proposal binding. Exact required fields are `link_id`, `decision_id`, `candidate_fingerprint`, `target_kind`, `target_id`, and `link_kind`; optional set is empty. `link_kind` is `existing` or `proposed`; link ID is UUIDv5 over `memory-knowledge:observer:link:<decision_id>:<target_kind>:<target_id>`. Exact replay is idempotent; a changed binding at either deterministic ID is a conflict. Never mutate the originating run, terminal result, or prior decisions.
- The module contains no subprocess, network, credential, model, promotion, qualification, registration, directive-edit, project-repository-write, terminal-history, or conversation-history path. Scope constants and tests enforce this mechanically.

**Why**

This is the passive decision engine. It produces a complete explanation rather than an opaque score and creates no lifecycle authority.

**Requirements**

`OBS-001`, `OBS-003`, `OBS-004`, `OBS-005`, `OBS-007`, `OBS-008`, `OBS-014`, `OBS-016`, `OBS-017`, `OBS-018`, `OBS-020`, `OBS-021`, `OBS-022`, `OBS-023`, `OBS-024`, `OBS-025`, `OBS-028`, `OBS-030`.

## Change 4 — Implement registered-first and fresh active-discovery matching

**Files**

- Update `scripts/work_memory.py` registered selector helpers without changing legacy `cmd_select` behavior.
- Update `scripts/discovery_candidate_reconciliation.py` with a read-only fresh candidate-identity inventory API.
- Update `scripts/sequence_observer.py` to consume those authoritative readers.
- Extend `tests/test_work_memory.py`, `tests/test_discovery_candidate_reconciliation.py`, and `tests/test_sequence_observer.py`.

**Implementation**

- Registered match: load registry/manifests through existing repository-root and bundle validation, validate stored CandidateIdentity/fingerprint, require exact semantic identity compatibility and current final-effective registered same-path proof, and return `LINK_REGISTERED`. Do not write a discovery. Legacy registered entries without reconstructable authoritative identity remain nonmatches rather than receiving guessed semantics.
- For legacy v1 registered entries, a single bounded adapter may reconstruct CandidateIdentity only when the canonical sequence document and manifest explicitly provide the full ordered command/action rows, inputs, repository-qualified dependencies, failure handling, exact verification/pass signal, and registry operation kind. Any missing field is a nonmatch; `use when` prose or operation-kind similarity is never semantic authority. Persisted v2 identity always takes precedence.
- Before treating an unreconstructable legacy row as irrelevant, run an ambiguity screen using only exact authoritative fields: shared registry operation kind plus exact automation/source reference or exact first executable source reference. If that screen matches but full legacy identity cannot be reconstructed, return `NO_CANDIDATE` with `legacy-registered-identity-ambiguous`; do not continue to discovery creation. Tests cover both a fully reconstructable legacy `LINK_REGISTERED` and an ambiguous legacy hold that creates no duplicate.
- Active discovery match: generate a fresh deterministic inventory from current discovery documents/manifests and ledger state, validate identity/fingerprint and active disposition, then return `LINK_DISCOVERY` and append only observer evidence allowed by the canonical discovery/ledger contracts. Do not use the rendered `ACTIVE.md` index as source of truth.
- Detect multiple incompatible matches, hash/root drift, invalid v2 identity, and fingerprint collision as typed fail-closed decisions. Concurrent identical triggers use deterministic IDs and compare-and-swap ledger/bootstrap writers so at most one link or lineage is created.
- Apply the locked suppression rule version 1 above. A materially different identity or evidence set bypasses the old suppression; unchanged evidence remains suppressed until expiry or explicit rule/config review.

**Why**

The observer must reuse accumulated knowledge before creating more discovery-log noise, and matching must use current canonical state rather than a stale human index.

**Requirements**

`OBS-009`, `OBS-010`, `OBS-011`, `OBS-013`, `OBS-018`, `OBS-021`, `OBS-022`, `OBS-024`, `OBS-025`, `OBS-026`, `OBS-027`.

## Change 5 — Submit only complete proposals through canonical bootstrap

**Files**

- Update `scripts/discovery_bootstrap.py` to accept optional versioned CandidateIdentity/fingerprint and observer provenance while preserving every v1 input and output.
- Update `scripts/sequence_discovery_log.py` to read v2 identity and use the shared final-effective reducer for v2 readiness only.
- Update `scripts/sequence_promote.py` to copy identity/provenance unchanged into the registered manifest.
- Update `scripts/discovery_promotion_lifecycle.py` only where it must preserve/read the shared identity and final-effective registered proof; do not change gate predicates or promotion authority.
- Update `scripts/sequence_observer.py` to call bootstrap as a library/API transaction, never render discovery files directly.
- Extend `tests/test_discovery_bootstrap.py`, `tests/test_sequence_discovery_log.py`, `tests/test_sequence_promote.py`, `tests/test_discovery_promotion_lifecycle.py`, and `tests/test_sequence_observer.py`.

**Implementation**

- Map the complete observed operation into the existing bootstrap contract: intended outcome, repeatability reason/evidence, finite ordered steps, explicit inputs, repository-qualified dependencies, failure fingerprints/handling, verified path, exact success evidence, and CandidateIdentity/fingerprint.
- Any absent field produces `NO_CANDIDATE` naming the missing evidence. No `TBD`, inferred command, partial step list, or direct discovery renderer is allowed.
- Bootstrap uses one deterministic observer request identity and existing atomic/recovery journal behavior. Exact retry recovers/returns the same discovery; conflicting identity or repository drift fails closed; concurrent identical proposals create one lineage.
- Observer provenance remains informational. It cannot mark readiness, count qualification, close blockers, promote, register, or satisfy registered verification.
- v1 bootstrap specifications, legacy discovery documents/events, explicit promotion commands, reconciliation, and resume remain behaviorally unchanged when the optional v2 fields are absent.

**Why**

This is the only candidate-write path. It prevents a second format and guarantees the existing lifecycle can consume the proposal without manual repair.

**Requirements**

`OBS-005`, `OBS-006`, `OBS-011`, `OBS-012`, `OBS-013`, `OBS-014`, `OBS-015`, `OBS-017`, `OBS-019`, `OBS-021`, `OBS-023`, `OBS-026`, `OBS-027`.

## Change 6 — Wire post-terminal invocation and governed feedback without changing close outcomes

**Files**

- Update `scripts/work_memory.py` run-close path with an opt-in/opt-out observer hook after the canonical terminal event is durably committed.
- Update `scripts/discovery_candidate_reconciliation.py` and `scripts/discovery_promotion_lifecycle.py` only to expose stable disposition/provenance joins by candidate fingerprint.
- Update `scripts/sequence_observer.py` feedback reader.
- Extend `tests/test_work_memory.py`, `tests/test_discovery_candidate_reconciliation.py`, `tests/test_discovery_promotion_lifecycle.py`, and `tests/test_sequence_observer.py`.

**Implementation**

- Commit `run_closed` first; invoke the observer afterward against the committed terminal event and a bounded ledger snapshot. An observer error cannot roll back or falsify the close result.
- Release the work-memory transaction lock after committing `run_closed`; then evaluate. For `PROPOSE_DISCOVERY`, use `date = completed_at_utc[0:10]`, `sequence_name = observed-<candidate_fingerprint[0:16]>`, and `task_id = observer-<candidate_fingerprint[0:12]>-<trigger_event_id-without-hyphens[0:12]>`. The canonical bootstrap request includes the decision ID and full CandidateIdentity; `bootstrap_request_sha256` is the canonical request identity. Persist the decision first, call bootstrap, persist the immutable bootstrap result, require successful returned `discovery_id`, `lineage_id`, `run_id`, document/manifest paths, bundle hash, classification/selection hashes, and active state to match that request, then append the deterministic link. A bootstrap failure is durably recorded on the result event as `observer-bootstrap-<safe-error-code>` and never rewrites the decision or close. A retry after a crash before bootstrap replays the same request and ordinal; after bootstrap but before result persistence it recovers the request and records the missing result; after result but before link it verifies the success result and appends the missing link; after link it returns existing records. Never hold the ledger lock while acquiring bootstrap/repository locks. The run-close CLI returns `ok:true` for the committed close plus a separate observer result/diagnostic, even when observer processing fails.
- Add explicit disablement so close performs no observer evaluation or observer writes and retains current behavior.
- Expose promotion, registered reuse, quarantine/dismissal, supersession, and correction outcomes as immutable joins to the original candidate fingerprint/decision ID. Do not reinterpret old decisions or silently tune rules.
- A future decision may consult only explicit governed dispositions allowed by its declared rule/config version. Changing feedback behavior requires a new version and leaves historical decisions byte-stable.

**Why**

This creates the requested proactive behavior at the one safe boundary while preserving lifecycle ownership and failure isolation.

**Requirements**

`OBS-003`, `OBS-018`, `OBS-019`, `OBS-021`, `OBS-023`, `OBS-024`, `OBS-025`, `OBS-026`.

## Change 7 — Prove requirement coverage and one real lifecycle path

**Files**

- Complete focused tests in the files listed above.
- Add `tests/test_sequence_observer_end_to_end.py`.
- Update only task-local requirement/verification mapping artifacts under `Tasks/proactive-sequence-observer-requirements/`; do not alter directives or unrelated documentation.

**Verification matrix**

1. Ledger and invoker contract: red-before/green-after for missing durable execution evidence; claim/return ordering; exact argv/provenance; ambiguous claim; idempotent replay; conflict; root/bundle drift; no raw output or secrets.
2. Eligibility/value: every G17/G18 trigger; trivial negative cases; one-step external operation; recurrence; corrected repeated failure; unknown estimates get no credit; deterministic threshold breakdown.
3. Reconstruction and safety: complete/incomplete order; missing step/return/dependency/outcome; recursive secrets/personal/transcript rejection; effectful non-dispatch; observer module has no execution/network/credential/model path.
4. Identity and dedupe: stable volatility cases; semantic changes split identity; collisions fail; registered-first; active-discovery reuse from fresh inventory; suppression/reconsideration; concurrent duplicate triggers create one decision/candidate.
5. Verification and lifecycle compatibility: final pass/fail order cases; proxy/cross-bundle/cross-lineage rejection; legacy v1 unchanged; observer disabled; failure isolation; caps/cursor/restart; cross-repository ownership and no project writes.
6. End to end: use the canonical checked invoker to create eligible exact evidence, close the run, obtain `PROPOSE_DISCOVERY` through bootstrap, drive the unchanged existing readiness/qualification/promotion/registered-verification path, then observe the same identity again and obtain `LINK_REGISTERED` with no second discovery. This is the only lifecycle-spanning test; all other tests stay at the cheapest contract boundary.
7. Scope enforcement: assert the observer imports/calls no dispatch, promotion, registration, directive mutation, cleanup, external-service, chat/history, or unlisted-root APIs; inspect the in-scope diff and run the focused observer suite, full repository suite, and `git diff --check`.
8. Contract completeness: fixtures exercise every required/optional field and conflict rule for `operation_context_recorded`, `execution_claimed`, `execution_returned`, `observer_decision_recorded`, `observer_bootstrap_result_recorded`, and `observer_candidate_linked`, including exact CLI replay behavior, run-closed-only triggering, `CAP_REACHED` status/disposition mapping, and safe diagnostic fields.

**Requirement coverage**

- Advisory outcomes and safe trigger: `OBS-001`, `OBS-003`, `OBS-020`, `OBS-023`, `OBS-030`.
- Durable complete evidence and provenance: `OBS-002`, `OBS-005`, `OBS-006`, `OBS-014`, `OBS-015`, `OBS-016`, `OBS-017`, `OBS-027`.
- Eligibility, value, explainability, and bounds: `OBS-004`, `OBS-007`, `OBS-008`, `OBS-018`, `OBS-022`, `OBS-024`, `OBS-025`, `OBS-028`.
- Identity, reuse, atomicity, and lifecycle interoperability: `OBS-009`, `OBS-010`, `OBS-011`, `OBS-012`, `OBS-013`, `OBS-019`, `OBS-021`, `OBS-026`.
- Complete validation: `OBS-029` plus every requirement above.

## Implementation-surface and verification coverage queue

| ID | Surface | Risk | Why in scope | Evidence | Initial status |
| --- | --- | --- | --- | --- | --- |
| COV-01 | Shared CandidateIdentity and fingerprint | high | All dedupe/persistence consumers need one semantic identity | flywheel research; bootstrap/manifests | unverified |
| COV-02 | Final-effective verification reducer | high | A stale earlier pass must never become candidate proof | work-memory/discovery/lifecycle reducers | unverified |
| COV-03 | Ledger event schemas and transactions | high | Durable cross-session evidence and decisions depend on atomic strict events | `scripts/work_memory.py` | unverified |
| COV-04 | Guard-to-dispatch invoker boundary | high | Exact executed behavior cannot otherwise be proven | `scripts/sequence_guard.py`; runner skill | unverified |
| COV-05 | Observer pure evaluator | high | Owns eligibility, value, bounds, safety, and dispositions | frozen requirements | unverified |
| COV-06 | Registered matching | high | Must avoid duplicate discoveries and require current proof | registry/selector/manifests | unverified |
| COV-07 | Active discovery matching | high | Must use fresh current inventory and single lineage | reconciliation/bootstrap/log | unverified |
| COV-08 | Canonical bootstrap and promotion copy | high | Proposal must enter existing lifecycle without parallel format | bootstrap/promote/lifecycle | unverified |
| COV-09 | Terminal hook and failure isolation | high | Proactivity must not alter originating outcome | work-memory close | unverified |
| COV-10 | Secrets, roots, and effect safety | high | Durable observer data must be safe and project repos read-only | validators/root bindings | unverified |
| COV-11 | Concurrency, crash, idempotency, caps | high | Repeated triggers must not duplicate or widen work | ledger/bootstrap transactions | unverified |
| COV-12 | Governed feedback and suppression | medium | Avoid noise without hidden learning or permanent false suppression | reconciliation/lifecycle events | unverified |
| COV-13 | v1 compatibility and disablement | high | Existing sequences/resume must remain unchanged | all current fixtures | unverified |
| COV-14 | Requirement matrix and E2E proof | high | Must prove all 30 requirements and registered reuse | test suite | unverified |
| COV-15 | Scope enforcement | high | Prevent observer from becoming dispatcher or policy engine | import/call/diff checks | unverified |

## Bounded implementation order and stop conditions

Implement Changes 1 through 7 in order. After each change, run only its focused tests. If evidence requires a new requirement, another repository, a lifecycle-gate change, credentials, deployment, directive change, or unrelated cleanup, stop for fresh approval rather than widening this plan. After Change 7, run the complete focused observer matrix, the full repository test suite, and review every in-scope committed/staged/unstaged/untracked diff surface. No commit or push is authorized by this plan.
