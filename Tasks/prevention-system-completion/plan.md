# Implementation plan: mechanical-error prevention system

> **Active implementation authority (2026-07-19):** Only
> `increment-01-generic-unseen-sequence/plan.md` is authorized for the current
> increment. The material below is retained as historical context and does not
> authorize duration admission, ten-owner production wiring, host interception,
> or any other adjacent implementation.

## Result to build

Build one repository-owned prevention boundary that turns a recurring mechanical intent into a typed, registered, pre-dispatch decision; durably runs or resumes the selected sequence owner; makes verified corrections mandatory; advances one evidence-linked learning lineage; reserves a complete long-running unit before work; and emits reproducible enforcement metrics.

The implementation is complete only when the acceptance report proves all six fixed measures. If the Codex host grants an action class that project hooks cannot intercept and the launcher cannot structurally withhold, the correct terminal state is `HOST_CAPABILITY_UNSATISFIED`; it is forbidden to report the run as fully governed. Owner coverage is the frozen state/admission contract: all ten approved executable owners must pass, while all six custodian-required and nine unavailable owners must remain non-dispatchable.

## Fixed scope

- Practical-boundary correction approved 2026-07-19: the prevention system governs the finite registered operational-workflow surface, not every ordinary Codex coding action. The ten `AVAILABLE` owners must enter through `PreventionController`/`OwnerRuntime`; their typed admission, budgets, effects, recovery, terminal proof, correction lineage, and lifecycle ownership remain mandatory. Ordinary Codex Bash, edit, browser, MCP, and subagent activity is outside this completion boundary unless it explicitly requests a registered operational owner.
- The unfinished universal Codex hook/socket design is not an acceptance dependency for this target. It may not be used to claim that a raw tool call was a registered `ActionIntent`, and the fixed process-global FD 198 design is rejected as incompatible with concurrent Codex tasks. Any future universal host-interception product requires separate research, planning, and approval.
- “No raw dispatch” in this corrected boundary means no raw or caller-reconstructed dispatch inside a governed registered-owner lifecycle. It does not claim OS-level prevention of every same-user invocation of an underlying script or every unrelated Codex tool action.

- Implementation repositories: `/Users/kamenkamenov/memory-knowledge` for the registry/controller/ledger and `/Users/kamenkamenov/mcp-agents-workflow` for the existing task-branch snapshot producer and Codex launcher enforcement. The original task and subsequent scope-expansion approval authorize both; a memory-knowledge-local substitute is not equivalent.
- External automation repositories are read-only evidence sources only; user-global Codex configuration, phase-ledger contracts, and secrets remain excluded.
- No commit, push, deployment, or remote mutation.
- Preserve all pre-existing working-tree changes; take a scoped baseline before editing and review the accumulated in-scope surface at the end.
- Explicit concurrency-safety expansion (2026-07-18): multiple Codex tasks may run concurrently, but only one host-authenticated Codex task may own and mutate a given work-memory task/run lifecycle. This adds no authority outside the existing work-memory control plane.
- Original research authority: `Tasks/prevention-system-completion/research-v3/package/`.
- Three-defect closure authority: `Tasks/prevention-system-completion/research-v7/package/`, terminal verdict `PASS`, candidate SHA-256 `b01a93931fc4b67edc97dced6ecbb8d3e86ac08f3df0e9feae41eaf67633f1a6`.

## Approved three-defect closure delta

This delta closes only the three defects found after the original implementation. It does not reopen the nine original changes or authorize adjacent refactoring.

### Delta 1 — Make host interception launcher-owned and worktree-safe

**Practical result:** A governed Codex run in either an ordinary checkout or a Git worktree cannot start merely because a project hook file exists. The workflow launcher creates an isolated per-session configuration home, installs the prevention `PreToolUse` hook through the official trust/hash contract, proves the hook fires with a nonce-bound harmless challenge, and emits a signed capability receipt. If the hook, trust proof, challenge, supported action coverage, or authorized authentication provider is absent, launch stops before model work or mutation.

**Implementation surfaces:**

- Add `mcp-agents-workflow/src/workflow_orch/prevention_hook.py` for the closed launcher-owned session contract: isolated-home construction, normalized hook/config hashing, trusted-hash validation, challenge result validation, receipt construction, and an injected `AuthenticatedSessionProvider` protocol. This module must never read, copy, infer, or log credentials.
- Extend `CliConfig` with a typed optional governed-session request/provider binding; do not pass prevention state through arbitrary `extra_args` or environment keys.
- Modify `CodexCliWrapper` so both persistent MCP-server and `codex exec` launch paths prepare a fresh governed session before subprocess creation, pass the launcher-owned config home only to that subprocess, run the challenge before the real invocation, attach non-secret capability metadata to `CliResponse`, and clean up the temporary home/session on stop or invocation completion.
- Modify `AgentExecutor` to require the injected provider for Codex calls marked `prevention_governed`, forward the exact allowed MCP set and action-class coverage, and return a stable `HOST_CAPABILITY_UNSATISFIED` failure before invocation when admission fails.
- Keep `ToolTranslator` as the structural-withholding producer: it may declare only the MCP servers and action classes actually granted; it must not claim interception itself.

**Acceptance tests:**

- Ordinary repository and `.git`-file worktree fixtures both use the launcher-owned hook and pass the same nonce challenge.
- Project hook omission or non-discovery does not remove launcher-owned interception.
- Missing provider, provider rejection, stale or mismatched trusted hash, failed challenge, replayed/expired receipt, and an uncovered granted action class all fail before the real Codex subprocess call.
- The provider is invoked through the typed interface, receives only the fresh home/session request, and no credential bytes appear in argv, environment snapshots, receipts, logs, or task artifacts.
- Resume creates a new home, nonce, challenge, and receipt; no prior receipt is reused.

### Delta 2 — Persist authoritative recurring-action eligibility and derive registered use from it

**Practical result:** The 95% registered-use measure cannot be rewritten by later registry changes or outcomes. Each validated intent gets exactly one immutable eligibility record before selection, and the metric replays only those records plus matching dispatch selections.

**Implementation surfaces:**

- Add closed enums to `prevention_contract.py`: `RecurrencePolicy = {ONE_SHOT, RECURRENT, NOT_APPLICABLE}`, `AvailabilityPolicy = {AVAILABLE, UNAVAILABLE, CUSTODIAN_EVIDENCE_REQUIRED}`, and `IneligibleReasonCode = {RECURRENCE_ONE_SHOT, RECURRENCE_NOT_APPLICABLE, AVAILABILITY_UNAVAILABLE, AVAILABILITY_CUSTODIAN_EVIDENCE_REQUIRED, OWNER_CONTRACT_UNRESOLVED, UNREGISTERED_ACTION_CLASS}`.
- Extend the prevention journal/work-memory schema with one `action_eligibility_recorded` event containing exactly `intent_id`, `registry_sha256`, `owner_sequence_id`, `owner_contract_sha256`, `recurrence_policy`, `availability_policy`, `eligibility`, and `ineligible_reason_code`, in addition to the common event envelope. Enforce the finite truth table and reject missing, duplicate, conflicting, or extra fields.
- Modify `PreventionController.register_intent` to resolve the frozen owner contract, append `action_intent_recorded`, then append exactly one eligibility event before `dispatch`; idempotent replay must validate both immutable records.
- Bind `dispatch_selected` to `selected_owner_sequence_id` and `selected_owner_contract_sha256` so it can match the eligibility record without consulting current registry state.
- Implement the registered-use query in `prevention_metrics.py`: denominator is distinct in-window eligibility records with `RECURRENT`, `AVAILABLE`, and `eligibility=true`; numerator is the subset with one matching durable selected-dispatch owner id and contract hash. Missing/duplicate/conflicting eligibility or dispatch identity fails the report closed.

**Acceptance tests:**

- Recurrent+available enters the denominator; one-shot, not-applicable, unavailable, custodian-required, unresolved-contract, and unregistered-class cases are excluded with their one exact reason code.
- Later registry, availability, source, dispatch-outcome, or promotion changes do not change replayed numerator or denominator.
- A selected dispatch with a different owner id or owner-contract hash does not enter the numerator and produces an integrity failure.
- Exact 95% boundary passes; one event below fails; missing/duplicate/conflicting events never get inferred.

### Delta 3 — Materialize the 25 owner states and the ten source-grounded executable contracts

**Practical result:** Registry initialization no longer treats an identifier or prose descriptor as executable. Ten owners have content-addressed typed contracts copied exactly from the terminal research package; six remain blocked on named custodian evidence and nine remain unavailable. The latter fifteen cannot dispatch.

**Implementation surfaces:**

- Add `Tasks/prevention-system-completion/owner-contracts.json` as the checked-in frozen materialization input. It must enumerate all 25 sequence ids, contain the ten `AVAILABLE` contract maps exactly as recorded in the terminal candidate, and contain only explicit state/reason/evidence identifiers for the six `CUSTODIAN_EVIDENCE_REQUIRED` and nine `UNAVAILABLE` rows.
- Each available row must contain and validate: `sequence_id`, `owner_sequence_id`, `owner_contract_sha256`, `implementation_source_sha256`, `parameter_schema`, `canonical_call`, `action_class`, `full_unit_budget`, `effect_identity`, `reconciliation_rule`, `terminal_schema`, `recurrence_policy`, and `availability_policy`.
- Modify `prevention_registry.py` to load this file as the executable-contract authority, verify all 25 ids against the migration manifest, recompute each owner contract hash, verify the source hash against the exact accessible implementation file, and expose immutable contract/state values to controller and selector.
- Reject source drift, a missing materialized field, any prose-derived fallback, an unknown row, state-count drift, or an executable field on a non-available row at registry initialization.
- Modify selector/controller admission so `UNAVAILABLE` and `CUSTODIAN_EVIDENCE_REQUIRED` owners produce the matching eligibility exclusion and cannot reach execution preparation.

**Frozen state counts:**

- `AVAILABLE` (10): `local-workflow-orch-image`, `greenfield-full-drive`, `mawf-playbook-blocker-reentry`, `claude-auth-token-refresh`, `discovery-promotion-lifecycle`, `commit-push-main`, `discovery-bootstrap`, `discovery-candidate-reconciliation`, `convergence-checkpoint-run`, `convergence-state-review-cycle`.
- `CUSTODIAN_EVIDENCE_REQUIRED` (6): `remote-mcp-user-onboarding`, `mawf-playbook-full-test`, `mawf-playbook-speed-test`, `github-app-repos-refresh`, `callcenter-harness-provision-verify`, `scoped-context-edit`.
- `UNAVAILABLE` (9): `taggable-source-reload`, `taggable-api-deploy`, `taggable-admin-spa-deploy`, `taggable-media-worker-deploy`, `airgapped-local-bulgarian-stt`, `airgapped-redaction-stack`, `airgapped-llm-judge`, `secure-landing-seed`, `callcenter-harness-engine-invariants`.

**Acceptance tests:**

- All 25 ids appear exactly once and state counts are 10/6/9.
- Each available row matches the terminal research contract byte-for-byte after canonical JSON serialization, its owner hash recomputes, and its implementation source hash matches.
- Source drift, descriptor-only evidence, missing/extra contract fields, and state/count changes reject registry initialization.
- Every unavailable or custodian-dependent owner is rejected before dispatch; every available owner yields only its materialized typed call/reconcile/terminal contract.

### Delta execution and review order

1. Materialize and validate Delta 3 first because Deltas 1 and 2 consume authoritative owner/action coverage.
2. Add Delta 2 contracts, journal events, controller emission, and metrics replay against that registry.
3. Wire Delta 1 into the launcher with a fake injected authentication provider for tests; production remains intentionally fail-closed until an authorized provider is supplied.
4. Run focused tests after each delta, then the full memory-knowledge suite through `scripts/run_pytest.sh` and the full workflow-orch suite through `uv run pytest`.
5. Independently review the complete in-scope working-tree surface against this delta and the original acceptance requirements. Fix only validated in-scope defects and repeat the same-path tests.

### Delta terminal conditions

- `PASS`: all three delta acceptance suites pass, original focused prevention tests remain green, and independent accumulated-surface review has no actionable in-scope finding.
- `HOST_CAPABILITY_UNSATISFIED`: launcher enforcement or an authorized authentication provider is absent; this is an honest fail-closed runtime result, not an implementation pass substitute.
- `EXTERNAL_OWNER_EVIDENCE_MISSING`: any of the fifteen non-available owners is requested; it remains non-dispatchable and cannot be counted as covered.

## Approved five-defect owner-runtime closure delta

This extension is governed by `Tasks/prevention-system-completion/research-v11/package/`, terminal verdict `PASS`, candidate SHA-256 `86584ee1d33aecc3d0d3e6882d6db268e1cf98ae881f4f9bc8c8dbae24193e54`, and envelope SHA-256 `4f6b643356c5f686854c5471b4818353daf7d7b8ea815801a35d641fac1547fc`. It closes only `MG-O1` through `MG-O5`. It does not alter the frozen 10 `AVAILABLE` / 6 `CUSTODIAN_EVIDENCE_REQUIRED` / 9 `UNAVAILABLE` classification, phase-ledger contracts, or any earlier acceptance threshold. For this revision, any older plan sentence requiring 25/25 executable black-box PASS is superseded: success requires all ten approved executable contracts to pass and all fifteen non-available owners to remain correctly non-dispatchable.

### Owner-runtime delta 1 — Materialize the executable owner contract authority

**Practical result:** Availability no longer implies executability. Each of the ten `AVAILABLE` rows becomes executable only when its approved proposal is present, hash-valid, complete, source-current, and fully resolvable; the other fifteen rows and any incomplete available row fail before budget or argv construction.

**Implementation surfaces:**

- Add `scripts/prevention_contract_materializer.py` and generated `Tasks/prevention-system-completion/owner-executable-contracts.json` as the canonical typed materialization of the ten individually approved files in `owner-contract-proposals/`. Each row binds the approved proposal hash, authority-decision ids, current implementation-source hash, complete normalized budget/parameter/root/provider/reconciliation/terminal contracts, availability, and parent rule. The materializer accepts the proposal's `unit_budget` or greenfield `budget_contract` input only through the closed normalized union below; no runtime field is copied as opaque prose.
- The materializer contains an explicit exhaustive owner/command/mode mapping table, not a natural-language interpreter. It normalizes every proposal parameter type and cross-field rule to `ParameterSpec`/predicate AST; every budget profile/formula to `OwnerBudgetContract`; and every effect/terminal clause to the typed policy contracts below. It emits a clause-coverage map from each proposal JSON pointer to one typed contract node and rejects uncovered or multiply mapped decision clauses. A changed approved proposal, source correction, or implementation source hash requires deterministic regeneration and full contract tests before that owner can regain executable admission; availability remains unchanged during regeneration.
- Extend `scripts/prevention_registry.py` to load and authenticate that artifact alongside the existing 25-row availability authority. Recompute the canonical executable-contract hash, verify proposal approval and current implementation-source hashes, validate exactly ten executable contracts, and expose an immutable `ExecutableOwnerContract`; do not parse prose or infer absent fields.
- Extend `scripts/prevention_contract.py` with closed typed representations for materialized parameter rules, trusted-root bindings, provider handles, reconciliation results, terminal evidence, and executable owner contracts. Direct dataclass construction must enforce the same invariants as JSON decoding.
- Add `tests/prevention/test_owner_contract_materialization.py` covering exact proposal-to-contract equality, source drift, missing/extra fields, unknown providers/roots, non-available executable fields, and availability/admission separation.

### Owner-runtime delta 2 — Make complete budgets owner-authoritative

**Practical result:** A caller can no longer understate the work to obtain admission. The selected executable contract supplies the full `UnitBudget`, and the controller reserves it before any lifecycle preparation.

**Implementation surfaces:**

- Add a closed `OwnerBudgetContract` union and canonical JSON discriminator: `FIXED_UNIT` contains the exact complete component vector; `PROFILED_PROGRESSIVE` contains a finite command/mode profile table whose entries name exact productive task vectors and role/overhead vectors; `ATOMIC_FRONTIER` is used only by greenfield and contains the approved feature/round/defect/fix-chain bounds plus typed durable-task/frontier records; `CHILD_COMPOSITION` contains a complete parent vector plus the content-addressed child contract and its complete derived vector. Proposal formulas normalize to the one closed integer expression AST: nonnegative `CONST`, approved named `VAR`, `ADD`, `MULTIPLY`, and bounded `SUM(index, LIST_VAR, expression)`. Every list variable has one typed producer, maximum cardinality, per-item schema, and frozen content hash before evaluation; free-text formulas and unresolved variables reject admission.
- Make `UnitBudget` reject incomplete role coverage, inconsistent component sums, negative or non-integer components, owner/profile mismatch, and unknown dimensions. Add canonical serialization and deterministic derivation from the selected `OwnerBudgetContract`: fixed returns its vector; profiled selects the exact validated command/mode and next durable task; atomic frontier sums the fully typed next frontier component-wise; child composition sums the complete parent and resolved child vectors. There is no generic or caller-provided fallback.
- Remove `unit_budgets` from `PreventionController.__init__` and every call site. In `execute`, resolve the executable owner contract first, derive its budget internally, compare-and-reserve the complete vector, and reject missing/incomplete/insufficient contracts before `OwnerRuntime.prepare`.
- Implement the greenfield progressive budget producer as durable next-task/frontier materialization: every atomic task is at most 3,600,000 ms including retry; reserve the full component-wise frontier before launch; cap the plan at 20 features, 5 validation rounds, 4 distinct fatal defects per round, and 20 fix chains. Never interpret 3,600,000 ms as a whole-workflow cap.
- Update `tests/prevention/test_full_unit_admission.py` and `tests/prevention/test_typed_dispatch.py`; add an exact-admission case for every materialized owner/command/mode budget profile and a separate one-unit-below rejection for every supported vector dimension. Add greenfield missing-role, untyped-task, unresolved-frontier, cap, and checkpoint cases plus child-composition missing/mismatched child cases. Assert zero journal/effect mutation on rejection.

### Owner-runtime delta 3 — Reconcile STARTED effects through the selected owner

**Practical result:** Restart no longer turns every interrupted effect into permanent manual uncertainty. The runtime re-observes the exact approved owner effect and safely skips an already-applied mutation, executes a proved-not-applied mutation once, or fails closed when evidence is indeterminate.

**Implementation surfaces:**

- Replace the placeholder `reconcile_*` symbols in `scripts/prevention_adapters.py` with a closed reconciler registry keyed by executable-contract hash plus reconciler hash and the ten approved reconciliation contracts. Each reconciler consumes only typed resolved parameters, effect identity, the immutable preparation-evidence artifact, captured result/receipt state, and approved read-only observables.
- Add `scripts/prevention_source_probes.py` as the sole production observer module. It defines `ProductionSourceProbeBackend`, the closed immutable `PROVIDER_FACTORIES[(owner_sequence_id, profile_id)]` map for every materialized profile, typed true-external-edge interfaces, and `build_production_transport(executable_contract, preparation_artifact, source_edges)`. Observation requests contain the owner/profile id, effect id, preparation-artifact hash, hash-bound non-secret observation targets, prepared pre-state identities, and prepared receipt/version identities. The backend returns raw source facts and exact ownership evidence; it never manufactures `SATISFIED`, `ABSENT`, identity matches, or semantic verdicts from the request. The selected reconciler and terminal verifier alone classify those facts.
- Remove `owner_observation_transport` from `PreventionController.__init__` and remove arbitrary backend/transport/factory injection from the production controller path. The controller may pass only a typed `SourceEdgeRegistry` whose members are true external edges. `OwnerRuntime` owns the closed imported `build_production_transport` builder: after `prepare` has written and re-read the hash-valid preparation artifact, runtime invokes that non-caller-selectable builder with the selected executable contract, verified artifact, and typed edge registry. No production constructor accepts a backend, transport, or factory. Unit tests may instantiate `OwnerRuntime` through an explicit test-only constructor with a test transport, but those traces are marked `TEST_TRANSPORT` and can never satisfy `production_source_probe_backend`. The acceptance corpus keeps the production backend/builder and swaps only the typed Docker, remote MCP/HTTP, Git remote, Key Vault/credential, or operator edge. A controller-construction test proves missing factory rows, test-transport injection, provider-id mismatch, and caller-selected backends/transports/factories fail closed before source execution.
- Each normalized reconciliation policy contains exact `ObservableSpec` entries with `observable_id=<owner>/<command-or-mode>/<name>`, provider symbol, request schema, result schema, ownership fields, freshness rule, and `read_only=true`. Its ordered classification is fixed: any identity/schema/ownership/freshness conflict is `INDETERMINATE`; otherwise a fully satisfied approved postcondition is `ALREADY_APPLIED`; otherwise the exact prepared pre-state plus proved absence of every mutation receipt/postcondition is `NOT_APPLIED`; every other state is `INDETERMINATE`. Owner-specific typed predicates may narrow these branches but cannot change that priority or add another outcome.
- Before mutation, make `OwnerRuntime.prepare` write a content-addressed preparation-evidence artifact containing the exact proposal-required identity, normalized pre-state and hashes, deterministic child/stage ids, root snapshot, and non-secret provider/resource versions for that owner/command/mode. Extend `effect_prepared` with `owner_contract_sha256`, `reconciler_sha256`, and `preparation_artifact_sha256`; append it only after the artifact hash is verified. Missing required preparation fields reject before `STARTED`.
- Derive the final source invocation only after the effect id and preparation artifact are durable. Every mutating source profile receives the same effect/preparation identity through its typed CLI/API contract and persists a source-visible non-secret receipt or label before/with the mutation. A source that cannot accept and later re-observe that identity remains `contract_verification=UNVERIFIED` with `dispatch_admission=CLOSED`; an outer runtime journal record alone is not ownership proof.
- Extend the exact `effect_reconciled` schema with `attempt_generation`, `prior_reconciliation_event_id?`, `owner_contract_sha256`, `reconciler_sha256`, `preparation_artifact_sha256`, `reconciliation_artifact_sha256`, `observable_ownership_sha256`, and `evidence_sha256`. Reconciliation is immutable and unique by `(effect_id, attempt_generation)`, not by effect id alone. Generation 0 is the required initial observation of the prepared pre-state. For any generation `g`, `ALREADY_APPLIED` proceeds to semantic verification, `INDETERMINATE` remains nonterminal, and `NOT_APPLIED` atomically authorizes exactly execution attempt `g+1` while referencing the generation-`g` reconciliation.
- Execution attempt `g+1` requires that exact unconsumed authorization and atomically appends one same-numbered `effect_execution_started` before the external call. A crash before or after the call reconciles generation `g+1` and links back to generation `g`. The new observation may legitimately evolve from prior `NOT_APPLIED` to `ALREADY_APPLIED`; prior events are retained and never rewritten. Another `NOT_APPLIED` authorizes only `g+2` after proving attempt `g+1` left the exact prepared pre-state unchanged. Generations are contiguous and monotonic with no skip, reuse, second start, or execution without its unique preceding authorization.
- A returned process result appends `effect_committed` for its exact `attempt_generation` and `execution_started_event_id`. The journal accepts at most one committed result per effect/generation, only from the same-generation start, and rejects an unstarted, superseded, delayed-prior-generation, or conflicting commit. `EXECUTED_RESULT` terminal verification must bind the accepted committed-event id; a later generation can succeed only when every earlier generation is durably reconciled and has no accepted competing commit.
- Preserve idempotent identical replay within a generation and reject a changed contract/reconciler hash, changed effect identity, changed preparation evidence, conflicting same-generation classification, duplicate authorization/start, artifact/hash disagreement, or observable ownership mismatch.
- Extend `tests/prevention/test_owner_runtime.py` with red-before/green-after crash-after-effect fixtures for every approved owner observable, using the real reconciler code path and source-grounded captured states. Prove no duplicate mutation and no terminal emission for indeterminate evidence.

### Owner-runtime delta 4 — Require semantic terminal proof and exactly-once terminalization

**Practical result:** Exit zero is only transport evidence. An owner reaches `TERMINAL` only when its materialized terminal schema validates and its declared semantic state is re-observed; the same execution identity can have exactly one terminal event and matching immutable artifact.

**Implementation surfaces:**

- Add `owner_terminal` to the exact prevention event schema in `scripts/work_memory.py` and `scripts/prevention_journal.py`, bound to `effect_id`, owner id, executable-contract hash, result hash, terminal-evidence hash, artifact hash, and semantic verdict. Validate common ownership and forbid missing/extra fields.
- Implement a closed terminal-verifier registry in `scripts/prevention_adapters.py` from the ten materialized `terminal_contract` objects. Parse exact stdout/result envelopes, reject malformed or semantically failed evidence even when return code is zero, and perform the approved read-only re-observation before returning verified evidence.
- Evaluate the exact owner/profile terminal predicates materialized from the approved proposal. Generic rules such as “all probes are satisfied,” return code zero, or a source-regression test pass cannot stand in for an owner/profile semantic verdict.
- Each normalized terminal policy has exactly two closed branches. `EXECUTED_RESULT` requires one accepted `effect_committed` and binds its committed-event id, attempt generation, and execution-started event; it then validates transport, exact output encoding/fields, typed identity predicates, observable schemas/freshness, semantic-success, and detached/nonterminal rules. `RECOVERED_RESULT` is allowed only from an authenticated `ALREADY_APPLIED` reconciliation when no committed process result exists; it requires that reconciliation event/artifact, the same contract/effect/preparation identities, and fresh terminal semantic postcondition evidence, and emits a canonical envelope containing `result_kind=RECOVERED_RESULT`, effect id, reconciliation event/hash, terminal-evidence hash, and no return-code claim. Both branches produce a canonical `result_hash`. Missing fields, extra fields where closed, unknown enum/status, stale observation, or any predicate failure is nonterminal. The materializer maps every owner/command/mode terminal clause to one or both branches and the clause-coverage map rejects an unmapped clause.
- Modify `scripts/prevention_owner_runtime.py` to persist stdout/stderr or their declared evidence envelopes safely and call the selected verifier after `EXECUTED` or `ALREADY_APPLIED`. Terminalization uses one locked compare-and-append keyed by `effect_id`: construct deterministic canonical terminal bytes, write/verify the content-addressed artifact first, then under the ledger hash/version lock reject any conflicting terminal event and append exactly one `owner_terminal` referencing that artifact. The event is the commit authority and the artifact is its deterministic immutable projection. A crash before append leaves only a hash-valid orphan projection that resume may reuse; a crash after append but before checkpoint repair derives `TERMINAL` from the event. Identical concurrent/replayed calls return the same event/artifact pair; different bytes, hashes, contracts, results, or second events fail closed.
- Correct `mcp-agents-workflow/scripts/mawf_playbook_test_sequence.py:cmd_reenter` at the producer boundary so blocked/unknown/error envelopes return nonzero and successful output includes `targetRunId`; do not compensate with permissive runtime aliases.
- Extend `tests/prevention/test_owner_runtime.py` and add `tests/prevention/test_owner_terminal_contract.py` plus `tests/prevention/test_prevention_event_contract.py` cases for all ten positive/negative semantic paths, detached nonterminal work, malformed evidence, zero-plus-failure, identical replay, conflicting replay, delayed/conflicting prior-generation result rejection, successful later-generation commit provenance, and crash-after-side-effect-before-any-process-result recovery through `RECOVERED_RESULT` for every applicable owner/command/mode. Run relevant MCP tests because the re-entry producer changes.

### Owner-runtime delta 5 — Enforce parent-only re-entry and trusted typed parameters

**Practical result:** The blocker re-entry child cannot be invoked directly or with copied parent data, and no path/resource/secret/approval value reaches argv without a materialized schema and trusted provider binding.

**Implementation surfaces:**

- Add exact `child_delegation_recorded` and `child_delegation_consumed` event schemas to `scripts/work_memory.py`/`scripts/prevention_journal.py`. Bind delegation id, parent effect and owner, child owner and intent, blocker verification, mode, and task/run/branch/worktree ownership.
- In `PreventionController.execute`, reject `mawf-playbook-blocker-reentry` before budget when no matching unconsumed delegation exists, the parent is not one of `mawf-playbook-full-test` or `mawf-playbook-speed-test`, its exact same-journal effect state is not `STARTED`, ownership differs, verification is absent, or the delegation is stale/foreign/consumed. Atomically bind delegation consumption to child effect preparation; identical replay is allowed only for the same child effect id. The other 24 owners remain standalone.
- Preserve both allowed parents as `CUSTODIAN_EVIDENCE_REQUIRED`: this delta does not make either executable and therefore the child remains non-admissible in a live registry until a separately authorized future contract makes one parent executable and `STARTED`. Contract tests may construct schema-valid same-journal parent/delegation fixtures for both allowed ids to prove the admission algorithm; they are not reported as live end-to-end execution evidence.
- Replace `FLAG_ORDER`, `POSITIONAL_COMMAND`, and `PATH_PARAMETERS` as validation authorities in `scripts/prevention_adapters.py` with the selected materialized `parameter_contract`. Keep only closed renderer functions that consume already validated/resolved values.
- Add a typed resolver registry: static roots come only from the contract; local repository keys resolve through `work_memory._repo_roots`; remote repository keys use `git_runtime.build_git_manager_from_settings`; secrets, approvals, and resources use declared injected providers. The provider interface returns a typed non-secret `BindingReceipt` with exactly `receipt_id`, `binding_kind`, `provider_id`, `key_or_resource_id`, `version_id`, `scope_sha256`, `value_fingerprint_sha256`, `consumable`, and `expires_at_utc` (optional only for non-expiring providers); secret values remain ephemeral and never enter the receipt.
- Add exact `owner_binding_recorded` and `authorization_receipt_consumed` event schemas bound to task/run/branch/worktree, intent/effect id, owner id, executable-contract hash, parameter name, binding-receipt hash, provider/key/resource/version identity, and scope hash. Record every resolved binding before argv. For consumable approval/publication/disposition receipts, one journal-lock transaction validates unconsumed identity/scope/version and binds consumption to `effect_prepared`; identical replay is allowed only for the same effect id. Missing, expired, conflicting, reused, wrong-scope, or provider-version-drift receipts fail before mutation.
- Replace the current argv-derived effect identity. After schema validation and provider resolution, derive `effect_id` from the executable-contract hash, intent/task/run/owner identity, canonical validated non-secret parameter identities, secret-handle identities, and sorted binding-receipt hashes; never include rendered argv or resolved secret bytes. Record bindings against that effect id, then render argv only from the same immutable resolved parameter object. Recompute and compare the identity on replay; tests assert provider input → receipt → effect identity → argv all consume the identical canonical parameter/binding set.
- Resolve every path against its declared root before argv construction. Reject absolute input, `..`, nonexistent read targets, invalid write parents, symlink escape, root/key mismatch, and mode-inapplicable values after canonical resolution.
- Extend `tests/prevention/test_typed_dispatch.py` for direct/forged/stale/inactive/foreign/consumed delegation, every non-`STARTED` parent state, and contract-only valid fixtures for both allowed parent ids; separately assert that the frozen live registry cannot create either parent and keeps the child non-admissible. Extend `tests/prevention/test_owner_adapters.py` across every applicable owner mode for missing/extra/wrong-type/wrong-tag, invalid enum/range/union, mode-inapplicable input, unknown provider/root, absolute/traversal/symlink/write-parent escape, derived-field override, raw argv/command payload, typed-child bypass, secret non-disclosure, and missing/conflicting/expired/reused/wrong-scope/atomically-consumed provider or approval receipts.

### Source-bound owner integration and admission

**Practical result:** A generated report can no longer make an owner executable merely because its ordinary source tests passed. Admission is lifted owner by owner only after the real controller, runtime, source implementation, production observer, reconciler, and terminal verifier have passed the exact source-path corpus.

**Common admission contract:**

- `scripts/prevention_contract_materializer.py` derives `required_profile_ids` independently from the exact finite profile selectors and the union of reconciliation and terminal observable profiles. Those sets must be identical where both apply; any unmapped or extra profile rejects materialization. `required_profile_set_sha256` binds the sorted complete set. For each profile, the materialized effect class mechanically marks each of six proof kinds `REQUIRED` or `NOT_APPLICABLE`: controller/runtime positive, controller/runtime semantic-negative, crash reconciliation, terminal semantics, effect-identity source binding, and production source-probe backend. `NOT_APPLICABLE` is allowed only for a contract-proved observation/operator-instruction branch with no mutation, and it records the exact contract clause hash; it is never a caller-authored waiver.
- `scripts/prevention_owner_acceptance.py` emits no trusted scalar `PASS` strings. It runs the source-path corpus and writes immutable canonical trace artifacts under `Tasks/prevention-system-completion/owner-acceptance-artifacts/<sha256>.json`; the owner report contains only the complete required profile set plus content-addressed proof references. Each proof trace has exactly: `schema_version`, owner/profile/proof/case ids, applicability, source/test/provider/contract/policy hashes, production-backend id and implementation hash, source-edge kind, runner-command hash, canonical journal-event hash, preparation/reconciliation/source-capture/terminal artifact hashes when applicable, and expected and observed typed outcomes. The trace contains no self-hash field. The proof reference and filename are the SHA-256 of the complete canonical trace bytes and must be equal. The trace includes the exact event/capture envelopes needed to replay the claim; credential bytes and other secret material are forbidden.
- The materializer enumerates every required profile/proof itself, loads every referenced trace, verifies its canonical hash and current source/test/provider/contract hashes, replays the journal/event chain through the production validators, revalidates the raw source capture and expected typed outcome, and derives success from that evidence. It never trusts a report-supplied result/status string. A missing, extra, stale, duplicate, self-inconsistent, non-production-backend, test-transport, or semantically failing proof leaves that owner contract `UNVERIFIED` and dispatch closed.
- Contract verification and live dispatch admission are separate fields. `contract_verification` is `VERIFIED` only when every required proof for every required profile validates. A standalone verified owner has `dispatch_admission=STANDALONE`; MAWF re-entry has `dispatch_admission=PARENT_GATED`; every unverified owner has `dispatch_admission=CLOSED`. These fields never relabel the frozen 10/6/9 availability map.
- The source-path corpus invokes `PreventionController.execute` and `OwnerRuntime` against the real owner source and `ProductionSourceProbeBackend`. It may fake only a true external edge (Docker daemon, remote MCP/HTTP, Git remote, Key Vault/credential provider, or operator service) with captured schema-valid payloads; it may not replace the owner source, runtime, observer, reconciler, terminal verifier, journal, or preparation artifacts. Each required mutating profile has positive, semantic-negative, crash-after-source-effect, recovered-terminal, and conflicting-identity cases; non-mutating profiles have the exact mechanically applicable subset. Proof traces bind the exact source, provider, contract, test, and runtime artifact hashes.
- Live credential/remote/custodian drives remain separate evidence. Their absence cannot be converted into a pass, and no secret is read during contract acceptance. A source implementation whose true external edge is unavailable may pass the deterministic source-path contract with the approved fake edge, but production execution still requires its normal provider/auth admission.

| Executable owner | Authorized source writes | Read-only authenticated dependencies | Authorized focused tests | Required source facts and stable fix |
| --- | --- | --- | --- | --- |
| `discovery-promotion-lifecycle` | `scripts/discovery_promotion_lifecycle.py`; `scripts/prevention_source_receipt.py` | its approved proposal and sequence bundle | `tests/test_discovery_promotion_lifecycle.py`; `/Users/kamenkamenov/memory-knowledge/tests/prevention/test_owner_source_acceptance.py` | Bind effect/preparation identity before readiness, qualification, promotion, and correction; replace Markdown/`shlex` child execution with typed child dispatch and receipts; fix qualification count at three; expose read-only bundle/registry/ledger/promotion/child/blocker/correction facts. |
| `commit-push-main` | `scripts/scoped_git_publish.py`; `scripts/prevention_source_receipt.py` | its approved proposal and sequence bundle | `tests/test_scoped_git_publish.py`; `/Users/kamenkamenov/memory-knowledge/tests/prevention/test_owner_source_acceptance.py` | Persist prepared repository/HEAD/index/remote/manifest identities and effect-marked commit/stage receipts; observe exact local/remote heads, effect trailer, authorized tree delta, index/rebase state, and source snapshot without mutation. |
| `discovery-bootstrap` | `scripts/discovery_bootstrap.py` | its approved proposal and sequence bundle | `tests/test_discovery_bootstrap.py`; `/Users/kamenkamenov/memory-knowledge/tests/prevention/test_owner_source_acceptance.py` | Bind the outer effect to deterministic discovery/spec/candidate identities before creation; observe discovery state, selected bundle, receipt, and exact absence/presence of the deterministic candidate. |
| `discovery-candidate-reconciliation` | `scripts/discovery_candidate_reconciliation.py`; `scripts/prevention_source_receipt.py` | its approved proposal and sequence bundle | `tests/test_discovery_candidate_reconciliation.py`; `/Users/kamenkamenov/memory-knowledge/tests/prevention/test_owner_source_acceptance.py` | Bind effect/attempt identities to manifests, checkpoints, child runs, active index, and ledger receipts; observe the current exact bundle and deterministic attempt rather than generating fresh retry identities. |
| `convergence-checkpoint-run` | `scripts/convergence_checkpoint_run.py`; `scripts/prevention_source_receipt.py` | the approved shared convergence-state helper and sequence bundle | `tests/test_convergence_checkpoint_run.py`; `/Users/kamenkamenov/memory-knowledge/tests/prevention/test_owner_source_acceptance.py` | Bind effect to the prepared baseline and typed child intent; observe structured accept/guard receipts and the exact child terminal artifact; never infer success from the fixed pass string. |
| `convergence-state-review-cycle` | `scripts/convergence_state_review_cycle.py`; `scripts/prevention_source_receipt.py` | the approved shared convergence-state helper and sequence bundle | `tests/test_convergence_state_review_cycle.py`; `/Users/kamenkamenov/memory-knowledge/tests/prevention/test_owner_source_acceptance.py` | Bind request/operation ids and preparation identity before helper calls; observe exact per-operation receipts, predecessor state hashes, approvals, and final status from the shared convergence-state authority. |
| `local-workflow-orch-image` | `/Users/kamenkamenov/mcp-agents-workflow/scripts/local_workflow_orch_image_harness.py`; `/Users/kamenkamenov/mcp-agents-workflow/scripts/prevention_source_receipt.py` | `/Users/kamenkamenov/mcp-agents-workflow/src/workflow_orch/credential_refresh.py`; `/Users/kamenkamenov/memory-knowledge/operations/sequences/local-workflow-orch-image/sequence.md` | `/Users/kamenkamenov/mcp-agents-workflow/tests/test_local_workflow_orch_image_harness.py`; `/Users/kamenkamenov/memory-knowledge/tests/prevention/test_owner_source_acceptance.py` | Separate read-only prepare/inspect from mutation; apply effect/prepared labels or receipts to every mutating profile; use staged atomic copy; verify owner/id before stop; emit structured logs/health/Codex/Git semantics and post-write observations. |
| `greenfield-full-drive` | `/Users/kamenkamenov/mcp-agents-workflow/scripts/greenfield_full_drive.sh`; `/Users/kamenkamenov/mcp-agents-workflow/scripts/greenfield_evaluation_drive.py`; `/Users/kamenkamenov/mcp-agents-workflow/scripts/greenfield_drive_dag.py`; `/Users/kamenkamenov/mcp-agents-workflow/src/workflow_orch/greenfield_program_state.py` | existing `workflow.greenfield.driveStatus` in `/Users/kamenkamenov/mcp-agents-workflow/src/workflow_orch/mcp_server.py` is read-only and is not an authorized write | `/Users/kamenkamenov/mcp-agents-workflow/tests/test_greenfield_resume_durability.py`; `/Users/kamenkamenov/mcp-agents-workflow/tests/test_greenfield_post_harvest_checkpoint.py`; `/Users/kamenkamenov/mcp-agents-workflow/tests/test_greenfield_n3_dag_drive.py`; `/Users/kamenkamenov/mcp-agents-workflow/tests/test_greenfield_n3_program_drive.py`; `/Users/kamenkamenov/memory-knowledge/tests/prevention/test_owner_source_acceptance.py` | Replace the opaque shell effect with deterministic typed child stages; derive and persist program identity from the prepared effect before detached launch; observe durable N1/N2/program status; verify terminal identities, ≤20-feature execution/merge/coverage invariants, validated verdict, and authenticated remote-head equality. The four writable source paths exactly equal the approved proposal source set. |
| `mawf-playbook-blocker-reentry` | `/Users/kamenkamenov/mcp-agents-workflow/scripts/mawf_playbook_test_sequence.py` | both allowed parent ids remain frozen `CUSTODIAN_EVIDENCE_REQUIRED` | `/Users/kamenkamenov/mcp-agents-workflow/tests/test_mawf_playbook_test_sequence.py`; `/Users/kamenkamenov/memory-knowledge/tests/prevention/test_owner_source_acceptance.py` | Carry effect/preparation/delegation identity through `cmd_reenter`; query status after mutation; prove task/workflow/run ownership and exactly one deterministic new lineage for restart/start-over. All six applicable contract proofs use a schema-valid same-journal `STARTED` parent/delegation fixture, the real controller/runtime/source/production backend, and only a fake operator edge. A verified contract is `PARENT_GATED`; the frozen live registry still cannot create either parent, so no standalone/live positive dispatch is claimed. |
| `claude-auth-token-refresh` | `/Users/kamenkamenov/mcp-agents-workflow/scripts/claude_auth_refresh.sh`; `/Users/kamenkamenov/mcp-agents-workflow/scripts/macos_keychain_secret.py`; `/Users/kamenkamenov/mcp-agents-workflow/scripts/prevention_source_receipt.py` | `/Users/kamenkamenov/mcp-agents-workflow/scripts/rotate-credentials.sh` is hash-bound read-only evidence; `/Users/kamenkamenov/memory-knowledge/operations/sequences/claude-auth-token-refresh/sequence.md` is the read-only sequence authority | `/Users/kamenkamenov/mcp-agents-workflow/tests/test_claude_auth_refresh_contract.py`; `/Users/kamenkamenov/memory-knowledge/tests/prevention/test_owner_source_acceptance.py` | Bind prepared resource ids, fingerprints, versions, request id, effect id, and child graph to every mutation; replace human status with typed read-only observations; verify Key Vault tags/version, reseed receipt, and exact local/host/remote `AUTH_OK`; dry-run reads no credential and reports `DRY_RUN`. |

Add `tests/prevention/test_owner_source_acceptance.py` and extend only the exact existing tests named in the table. The ten-owner matrix is complete only when every required profile has current-hash evidence for every mechanically applicable proof kind and every `NOT_APPLICABLE` entry is derived from its materialized non-mutating clause.

### Concurrency-safety remediation — enforce one Codex writer per tracked lifecycle

**Practical result:** Several Codex tasks can operate at the same time without corrupting each other's lifecycle state. The first host-authenticated Codex task to select a work-memory task becomes its durable writer. Every later selection, activation, run mutation, blocker transition, correction, verification, and close checks that writer identity at the common ledger boundary before changing bytes. A different Codex task is rejected without mutation unless the current owner records an explicit handoff; after handoff, the old owner's receipts are stale and only the named new owner can continue.

**Implementation surfaces:**

- Extend `scripts/work_memory.py` with durable writer-claim and writer-handoff events, host-only `CODEX_THREAD_ID` resolution, task/run ownership derivation, and atomic authorization inside the existing ledger file lock. Caller arguments may name a handoff target but may never override the current host identity.
- Bind new selections and `run_started` events to the current ownership generation. Keep historical ledger replay readable; require an explicit claim when a pre-feature active lifecycle has no owner binding.
- Extend `scripts/sequence_guard.py` so activation, receipt verification, status, and guarded execution reject missing, stale, foreign, or handed-off ownership before executing a command. Classification, selection, active-state rotation, handoff, and target repair share one task receipt lock; handoff writes use old/new hash compare-and-swap so the former owner cannot overwrite target progress after losing authority.
- Keep direct bootstrap, immutable-launcher, blocker-catalog, merge, and repair callers on the same current enforced transaction boundary; a sealed pre-ownership snapshot must be bridged to current ownership validation before it can execute. No bypass or parallel lease store is allowed.
- Treat the canonical ledger and generated blocker view as one inseparable path pair. A custom ledger must name a separate explicit custom view; no custom or foreign ledger may rewrite the canonical `BLOCKERS.md` projection.

**Acceptance tests:**

- Same-owner selection, activation, run mutation, correction, blocker transition, verification, and close pass.
- A second Codex task using the same task/run is rejected before receipt, active-state, ledger, or generated blocker-view mutation.
- A second task also cannot create a different task/run and mutate the original blocker's correction, successor-verification, transition, or close lineage; successor runs retain the predecessor task identity across an owner handoff.
- Different Codex tasks using different task ids proceed concurrently.
- An owner-recorded handoff admits only the named target, invalidates the old owner's receipts, and rejects handoff attempts by non-owners.
- Missing or invalid host identity fails closed; no CLI parameter can impersonate the owner.
- A two-writer race for an unowned task produces exactly one durable owner.
- Historical ledgers still replay, while a pre-feature active run cannot be mutated until explicitly claimed.
- Direct and immutable-launcher bootstrap paths both reject a foreign writer before invoking sealed lifecycle code; custom-ledger transact, merge, and repair calls cannot target the canonical blocker view.

### Five-defect execution and verification order

1. Materialize and authenticate the ten executable contracts; hold all owners non-executable until this passes.
2. Replace caller budgets with owner-derived admission and prove rejection occurs before effects.
3. Materialize parameter/root/provider resolution and parent delegation admission so runtime inputs are authoritative.
4. Implement the production observer request/response boundary and the ten source integrations above; keep every owner fail-closed until its source-path corpus passes.
5. Implement owner reconciler dispatch and crash recovery against those raw source facts.
6. Implement owner/profile semantic verification, the terminal event/artifact pair, and the re-entry producer correction.
7. Generate the content-addressed per-profile acceptance traces and ten-owner report; derive `contract_verification` from complete evidence validation, then set `dispatch_admission` to `STANDALONE`, `PARENT_GATED`, or `CLOSED` by the materialized parent contract.
8. After each defect slice, run its focused red-before/green-after tests. Then run the full prevention suite, `scripts/run_pytest.sh` through the registered sequence, relevant MCP tests if its source changed, compilation/lint, and independent `verify-work` over the accumulated in-scope surface.
9. Correct and same-path verify the owner-contract blocker records, then transition each through `fixed-awaiting-verification` → `verified` → `closed` with `remaining_work=none` only after all five acceptance slices and full regressions pass.

### Five-defect terminal rule

This delta is `PASS` only when all ten executable owner contracts have `contract_verification=VERIFIED`, the nine standalone owners have `dispatch_admission=STANDALONE`, MAWF re-entry has `dispatch_admission=PARENT_GATED`, no caller budget or hard-coded validation authority remains, every STARTED owner has a source-grounded three-way reconciler, exit zero cannot bypass semantic verification, terminal event/artifact replay is exactly once, blocker re-entry is parent-only, trusted-root/provider validation covers every bound parameter, the focused/full suites pass on one code revision, and independent accumulated-surface review has no actionable finding. The live registry's inability to create either frozen MAWF parent is required parent-gating evidence, not a missing contract proof or a standalone-admission pass. Any missing contract, provider, observable, source match, or applicable profile proof is a fail-closed non-pass and must be reported as remaining work.

## Change 1 — Freeze the typed prevention contracts and canonical owner registry

**Why:** Runtime currently parses a Markdown table and accepts prose/composite ownership. Every later guarantee needs one closed source of truth.

**Files:**

- Add `scripts/prevention_contract.py`.
- Add `scripts/prevention_registry.py`.
- Consume the frozen planning input `Tasks/prevention-system-completion/owner-migration-manifest.json`; validate its 25 unique evidence pointers against the pinned `owner-descriptors.json` hash before generating runtime contracts.
- Add `operations/prevention/sequence-owners.json`.
- Modify `scripts/work_memory.py:registry_rows` to consume the validated registry API rather than parse `SEQUENCES.md`.
- Modify `operations/sequences/SEQUENCES.md` only through a renderer in `prevention_registry.py`; preserve its explanatory prose and render its table from canonical data.
- Add `tests/prevention/test_contracts_and_registry.py`.

**Exact contract:**

- Closed enums and immutable values use the exact members and schemas in **Normative contract A** below; persisted encodings are schema-versioned canonical JSON with sorted keys, no `null` for required fields, and unknown keys rejected.
- Exact owner keys: `schema_version`, `sequence_id`, `use_when`, `sequence_folder`, `owner_kind`, `handler`, `parameter_schema`, `argv_tokens`, `action_classes`, `long_unit_budget`, `effect_reconciler`, `terminal_signal`, `standalone`, `parent_sequence_ids`, `automation_display`, `pass_signal_display`, `operation_kinds`, and `lineage_id`.
- `automation_display` is rendered from `handler` plus fixed `argv_tokens`; `pass_signal_display` is rendered from `terminal_signal`. The human text is stored only to preserve the current projection byte-for-byte during migration and is rejected if it differs from the typed render.
- Reject unknown keys, duplicate sequence ids, shell metacharacters in fixed argv tokens, free command strings, untyped parameter values, unresolved handler symbols, multi-owner rows, standalone dispatch of a non-standalone row, or registry/Markdown projection drift before any effect.
- Seed exactly the frozen 25 sequence ids. Composite rows use one adapter handler; `mawf-playbook-blocker-reentry` resolves to its declared parent and has `standalone=false`.

**Verification:**

- Assert 25/25 exact ids, one handler per row, one terminal signal, and no Markdown-only owner.
- Mutation corpus rejects extra fields, malformed enum/boolean/integer values, command strings, arbitrary argv, duplicate owners, and projection drift.
- Existing registry consumers receive the same `use_when`, `folder`, `automation`, `pass_signal`, `operation_kinds`, and `lineage_id` values. Render → parse → render is byte-stable for all 25 rows.

**Evidence/containment:** Emit `owner-registry-validation.json` with registry hash and 25 row results. Revert by restoring `registry_rows` to the pre-change implementation and deleting only the new registry surfaces; do not rewrite existing ledger data.

**Requirements:** `CUR-ENTRYPOINT`, `FUT-ENTRYPOINT`, `CUR-TYPED`, `FUT-TYPED`.

## Change 2 — Extend the existing ledger with prevention, journal, and metric events

**Why:** Correction, resume, learning, and metrics are currently separate records or post-hoc joins. A second ledger would create another source of truth.

**Files:**

- Modify `scripts/work_memory.py:EVENT_FIELDS`, event validation, state derivation, `_metrics`, and `summarize`.
- Add `scripts/prevention_journal.py` as a typed API over the existing single-authority ledger commit.
- Add `tests/prevention/test_prevention_event_contract.py` and `tests/prevention/test_journal_ownership.py`.

**New event types and required payloads:** Use the common ownership fields and exact per-event fields in **Normative contract B**. No field is deferred to implementation.

**Rules:**

- Existing event schemas are unchanged; no legacy event is silently normalized.
- Every prevention event carries controller-derived task-branch/worktree/run ownership. A mismatched owner is a hard rejection.
- `PREPARED` without `COMMITTED` is reconciled by adapter-specific effect identity; it is never blindly rerun.
- The ledger append is the single commit point. Generated views are derived and may lag; every read/start checks the ledger hash, repairs a stale view under the ledger lock, and regenerates it idempotently. Readers that make enforcement decisions use the ledger only.
- Prevention events, journals, and generated artifacts are added to the workflow snapshot owned by `mcp-agents-workflow/src/workflow_orch/artifact_repository.py:TaskBranchSnapshotWriter`. The existing resolver remains the sole authority for the remote `task/<task_id>` branch, commit, push, and acknowledgement. Prevention code must not create a competing local task branch.
- Each run stores prevention state at `Tasks/<task_id>/workflows/<workflow_name>/runs/<run_id>/prevention/`: `events.jsonl`, `checkpoint.json`, immutable `artifacts/<sha256>`, and generated views. `workflow_snapshot()` already stages every file recursively under that exact run directory, so earlier run ids remain separate tracked paths on the same task branch. A transition becomes resumable only after its event and referenced artifacts are included in the returned Git acknowledgement (`commit_sha`, `committed`, `pushed`) for that task-branch snapshot. Resume accepts `task_id` and `run_id`, loads the acknowledged snapshot through the same artifact repository, verifies repository/task/run ownership, and continues from the first uncommitted transition. Local ledger state may be a write-through cache but never the durable authority.

**Verification:** Replay the current ledger, append every new valid event, reject every missing/extra-field variant, crash before/after each journal event, and prove branch A/B plus run A/B isolation.

**Evidence/containment:** Emit crash-matrix and ownership results. New event readers must ignore no unknown events; rollback is code-only before new event emission, otherwise a forward-compatible reader must remain.

**Requirements:** `CUR-RESUME`, `FUT-RESUME`, `CUR-LEARNING`, `FUT-LEARNING`, `CUR-METRICS`, `FUT-METRICS`.

## Change 3 — Implement the sole typed prevention controller and selector

**Why:** Guards are voluntary and callers reconstruct lifecycle commands. Selection must happen before any execution claim.

**Files:**

- Add `scripts/prevention_controller.py`.
- Add `scripts/prevention_selector.py`.
- Add `tests/prevention/test_typed_dispatch.py` and `tests/prevention/test_selector_order.py`.

**Public operations:**

1. `inspect-host` consumes and validates a host-issued capability manifest and challenge receipt; the controller cannot mint either.
2. `register-intent` validates operation-independent identity plus named parameters against the requested canonical owner's descriptor; no JSON file/string, command text, raw patch, or remainder argv is accepted.
3. `dispatch` resolves the effective owner, revalidates every parameter against that owner's schema, emits exactly one terminal `DispatchDecision`, then performs host admission, eligibility accounting, budget admission, journal transition, adapter invocation, verification, and terminal emission.
4. `resume` accepts only `task_id` and `run_id`; repository, branch, and worktree identity are derived and verified before loading the next valid transition.
5. `report` calls the canonical metric query from Change 8.

**Selector precedence:**

1. If the requested implementation is prohibited and a compatible verified successor exists, record `prevented_failure_recorded` and return one terminal `SELECT_SUCCESSOR` decision; the internal predecessor rejection is not also counted as a rejected dispatch.
2. If the requested implementation is prohibited and no compatible verified successor exists, return one terminal `REJECT` decision.
3. Select a verified promoted sequence compatible with the intent.
4. Select the canonical registered owner for the requested sequence.
5. Reject `NO_REGISTERED_IMPLEMENTATION`; never fall back to remembered shell or prose.

The controller records `execution_claimed` only after selection and effect preparation. Direct use of legacy `sequence_guard --command`, `sequence_checked_exec <argv>`, `work_memory transact --request-json`, and caller-built context/argv JSON is rejected for a `FULLY_GOVERNED` run. A host-issued `host_action_observed` record is required for every granted mechanical action; an observed action with no joined terminal dispatch decision is counted as `raw_dispatch`.

**Verification:** Inject unknown operation, extra flag, JSON/text input, malformed typed value, raw argv, direct legacy dispatch, and missing selector result; assert zero subprocess calls and zero mutation. Verify selector order and exact reason codes.

**Evidence/containment:** Emit a negative-path decision ledger. Keep legacy CLIs callable only for non-governed migration tests until Change 9; do not silently translate them.

**Requirements:** `CUR-TYPED`, `FUT-TYPED`, `ACC-ZERO-RAW`, `CUR-CORRECTION`, `FUT-CORRECTION`, `ACC-ZERO-REPEAT`, `ACC-MANDATORY-CORRECTION`.

## Change 4 — Add one closed owner adapter for every registered sequence

**Why:** One controller is meaningless if it delegates to unvalidated command reconstruction.

**Files:**

- Add `scripts/prevention_adapters.py` and `scripts/prevention_owner_runtime.py`.
- Populate all 25 rows in `operations/prevention/sequence-owners.json` only from the schema-valid `Tasks/prevention-system-completion/owner-migration-manifest.json`; `owner-descriptors.json` is evidence input and may never be consumed by runtime or translated ad hoc.
- Add `tests/prevention/test_owner_coverage.py` and `tests/prevention/test_owner_black_box.py`.

**Adapter contract:** `initialize(intent)`, `required_budget(intent)`, `prepare_effect(intent, journal)`, `reconcile(effect_id)`, `execute(effect_id)`, `verify(effect_id)`, and `emit_terminal(effect_id)`. Exact method inputs, states, results, and error behavior are fixed by **Normative contract C**. Adapters call `subprocess.run(argv, shell=False)` only with tokens assembled from the owner schema and trusted repository-root bindings.

**Coverage rules:**

- Local Python/shell owners receive concrete adapters immediately.
- Composite owners expose either one proven one-shot executable with an equivalent durable child journal, or a typed acyclic child-effect graph. Each child has its own dependencies, effect identity, PREPARED/COMMITTED/reconciled state, verification, and terminal derivation; resume reconciles every prepared child before selecting the next runnable child.
- The non-standalone blocker re-entry row delegates only through its parent adapter.
- An owner counts as executable only when its approved materialized contract and real initialization-to-terminal evidence pass. Contract fixtures prove rejection or schema behavior but cannot turn any of the six custodian-required or nine unavailable rows into an executable pass.
- Before adapter code begins, convert descriptor evidence into machine-readable invocation/result envelopes, exact effect identities/reconcilers, and non-secret black-box evidence authority. Five formerly unresolved owners are grounded from checked-in implementations in the authorized repositories: `remote-mcp-user-onboarding`, `mawf-playbook-full-test`, `mawf-playbook-speed-test`, `github-app-repos-refresh`, and `scoped-context-edit`. `callcenter-harness-provision-verify` is grounded read-only from its checked-in provision/verify runbook and scripts; its adapter owns the typed composite child graph without editing that repository. No command or schema is guessed.
- No adapter may accept a raw command, arbitrary argv, opaque JSON payload, key-order-dependent object, or prose pass signal.

**Verification:** Contract-test every adapter; kill/reinvoke at each lifecycle boundary; assert exactly one terminal event. Run available owners through their real black-box path. Emit 25-row results with `PASS`, `EVIDENCE_MISSING`, or `FAIL`; the aggregate passes only at 25 `PASS`.

**Evidence/containment:** `owner-coverage-report.json` names the real invocation evidence and hash for each row. External unavailability is explicit and cannot be converted to a pass.

**Requirements:** `CUR-ENTRYPOINT`, `FUT-ENTRYPOINT`, `CUR-RESUME`, `FUT-RESUME`.

## Change 5 — Enforce supported Codex actions before execution and fail closed on uncovered grants

**Why:** The controller cannot depend on the model remembering to call it.

**Files:**

- Add `.codex/hooks.json` with project-local `PreToolUse` matchers for `Bash`, `apply_patch`, and MCP names.
- Add `.codex/hooks/prevention_pre_tool_use.py`.
- Add `scripts/prevention_host.py`.
- Modify `mcp-agents-workflow/src/workflow_orch/agents/tool_translator.py`, `agents/executor.py`, and `cli/codex_cli.py` so the launcher freezes the actual tool/sandbox/hook configuration, issues the nonce-bound capability receipt, and passes the vetted project hook using the installed Codex CLI's stable hooks capability.
- Add `tests/prevention/test_action_surface_interception.py` and hook stdin/stdout fixtures.
- Add launcher contract tests in `mcp-agents-workflow/tests/test_agents.py` and `tests/test_cli.py`.

**Behavior:**

- Parse the official hook envelope into a strict `ActionIntent`; unknown/extra/malformed fields deny the tool call.
- Call `prevention_selector` before supported Bash/edit/MCP execution. Return allow/rewrite only for a registered selected implementation; return deny with a stable reason otherwise.
- Never log hook payloads that may contain secrets.
- `HostCapabilities` covers shell, file edit, MCP, unified shell, WebSearch/browser, subagent, and non-MCP remote.
- For a governed Codex launch, the wrapper uses a generated, revision-hashed config layer with `--strict-config`, `--enable hooks`, and `--dangerously-bypass-hook-trust`; it ignores unvetted user configuration, does not pass `--search`, allowlists only declared MCP servers, and disables `browser_use`, `browser_use_external`, `computer_use`, `apps`, `multi_agent`, and `image_generation`. The installed CLI's feature inventory and accepted flags are captured in the capability receipt. An unavailable/renamed flag is admission failure, not a silent omission.
- Current `PreToolUse` coverage is limited to shell/Bash, unified execution, `apply_patch`, and MCP. Those four classes must pass the nonce challenge. Every other action class must have structural-withholding evidence from the exact generated launch config or the run is `HOST_CAPABILITY_UNSATISFIED`.
- Receipt authentication is `HMAC-SHA256` over canonical JSON excluding `mac`, keyed by a fresh 32-byte launcher-owned per-session key from the OS CSPRNG. The key is delivered only through inherited read-once file descriptors to the hook and controller—never argv, environment, disk, logs, or the task branch. The trust root is the launcher process that owns the exact `CliConfig`, child process ids, and file descriptors. The controller is the sole verifier; it checks MAC, nonce, session id, process lineage, config/hook hashes, issue/expiry times, and one-time receipt id before appending `host_capability_recorded` or `host_action_observed`. Resume never reuses an old receipt: the new launcher issues a new session/key/challenge, while the ledger retains only the already-verified event and receipt hash for audit.
- Mark a class `INTERCEPTED` only after a same-session, nonce-bound live hook challenge returns the expected `session_id`, hook/config hashes, trusted/enabled state, and unexpired challenge receipt. The `mcp-agents-workflow` launcher—not the controller—issues the manifest and nonce from the exact `CliConfig` it invokes, then records the receipt beside execution metadata. Mark `WITHHELD` only when the invoked config structurally omits or disables the class. Any other granted class is `UNSUPPORTED` and prevents `FULLY_GOVERNED` startup.
- Project-local hooks require a trusted `.codex/` layer; absence of trust is a visible capability failure.
- Hook rewrite is limited to the same supported tool class and never pretends `apply_patch` or MCP can be converted into another tool. Unsupported output shapes are treated as hook failure and therefore fail host admission before governed work.

**Verification:** Direct Bash, `apply_patch`, and MCP fixtures are denied or rewritten before mutation. Unified shell, browser/search, subagent, and remote fixtures either carry a structural-withholding receipt or make host admission fail. No advisory fallback is accepted.

**Evidence/containment:** Emit `host-capability-report.json`. Removing `.codex/hooks.json` disables only the new project hook; it must also make governance admission fail, preventing a false protected state.

**Requirements:** `CUR-INTERCEPTION`, `FUT-INTERCEPTION`, `ACC-ZERO-RAW`.

## Change 6 — Make verified corrections mandatory and join the causal learning path

**Why:** Current correction, discovery, promotion, and later reuse evidence are not one pre-action lineage.

**Files:**

- Modify `scripts/work_memory.py:cmd_correct`, `cmd_verify`, and `cmd_run_close` only at their typed event boundary.
- Modify `scripts/sequence_observer.py` to expose typed compatibility/lineage construction without post-execution-only coupling.
- Modify `scripts/discovery_bootstrap.py`, `scripts/discovery_promotion_lifecycle.py`, and `scripts/discovery_candidate_reconciliation.py` to accept/controller-return typed calls while preserving all approval predicates.
- Modify `scripts/sequence_promote.py` to publish the verified successor binding atomically with registered verification.
- Extend `tests/test_sequence_observer_end_to_end.py`; add `tests/prevention/test_mandatory_successor.py` and `tests/prevention/test_learning_lineage.py`.

**Behavior:**

- A failure records stable fingerprint and compatibility key.
- A correction records predecessor/successor implementation identities. Each identity is a canonical hash over `sequence_id`, owner-registry schema/version/hash, operation signature, source-bundle hash, and changed-artifact hashes; in-place corrections with the same sequence id still have different identities.
- Only same-path verification permits `predecessor_prohibited`, which stores both implementation identities, compatibility key, failure fingerprint, and verification event id. Selector matching is by implementation identity, never sequence id alone.
- Before `predecessor_prohibited` commits, the controller maps the predecessor intent to the successor using the total mapping rules, validates every mapped value against the successor `ParameterSpec`, recomputes and matches the successor compatibility key, and proves effect class plus verification-contract hash equality. Any missing required value, type/enum/secret-handle mismatch, unversioned default/addition, key mismatch, or verification-contract mismatch leaves the predecessor allowed and emits a typed incompatibility rejection.
- Promotion still requires existing qualification, approval, atomic promotion, and registered verification.
- The next compatible intent is intercepted before execution and selects only the successor/promoted owner.
- One lineage query returns intent → attempt → failure → diagnosis → correction → same-path verification → discovery → promotion → registered verification → pre-action reuse with no manual join.

**Verification:** Update the current end-to-end test so the second intent has no seed execution before `LINK_REGISTERED`; assert predecessor `execution_claimed` is absent, successor claim is present, and `prevented_failure_count` increments on a forced repeat. Add four mapping cases before prohibition: exact-name/type pass; explicitly versioned added parameter with declared default pass; missing-required/type-or-enum mismatch fail; compatibility-key/effect-or-verification-contract mismatch fail. Every fail case asserts no `predecessor_prohibited` event.

**Evidence/containment:** Preserve old post-run observer events for history but do not treat them as pre-action reuse. No approval or correction gate is weakened.

**Requirements:** `CUR-CORRECTION`, `FUT-CORRECTION`, `CUR-LEARNING`, `FUT-LEARNING`, `ACC-ZERO-REPEAT`, `ACC-MANDATORY-CORRECTION`.

## Change 7 — Add full-atomic-unit admission before long work

**Why:** The current research formula reserves too little and other long owners have no common admission gate.

**Files:**

- Add `scripts/prevention_budget.py`.
- Modify `skills/research-playbook/scripts/research_run.py:admit_round`, `_admit_operation`, and retry admission to use `UnitBudget`.
- Wire every long owner adapter's `required_budget` through the controller before preparation or launch.
- Add `tests/prevention/test_full_unit_admission.py` and extend `tests/test_research_run.py`.

**Budget components and reservation:** Use the exact `UnitBudget` and `BudgetReservation` schemas in **Normative contract D**. Duration milliseconds are mandatory for every long unit; token and monetary micros are either both supported by the named capacity authority or explicitly `UNSUPPORTED` and excluded from both required and remaining vectors. Components are summed per dimension before one atomic compare-and-reserve ledger transaction. The reservation is bound to task/run/owner, has a lease expiry, supports idempotent renewal/release, and is reconciled after a crash. A missing mandatory estimate rejects admission.

**Verification:** For research, assert core + three lenses + adjudicator + materialization + terminal + bounded retry. For every long owner, run exact-boundary and one-unit-below for each supported dimension. Add concurrent double-admission, lease-expiry/reconciliation, crash/recovery, and idempotent release tests. Every rejection must emit `budget_rejected` and create no role launch, subprocess, effect preparation, or external mutation.

**Evidence/containment:** Emit the per-owner component audit. A long owner without a complete contract is unavailable, not assigned zero cost.

**Requirements:** `CUR-BUDGET`, `FUT-BUDGET`, `ACC-BUDGET-ADMISSION`.

## Change 8 — Implement canonical enforcement queries and threshold reporting

**Why:** Success is otherwise a prose assertion and bypasses remain invisible.

**Files:**

- Add `scripts/prevention_metrics.py`.
- Modify `scripts/work_memory.py:_metrics` and `summarize` to expose the new query result without duplicating formulas.
- Add `tests/prevention/test_metric_contracts.py` and `tests/prevention/test_acceptance_report.py`.

**Metric contract:**

- Registered use = `registered_dispatch` / `eligible_recurring_action` over a fixed window; pass at `>= 0.95`. Eligibility is derived by the controller from registry recurrence metadata and the selected operation signature, never supplied by the caller. Registered dispatch is a terminal `SELECT_SUCCESSOR`, `SELECT_PROMOTED`, or `SELECT_REGISTERED` decision.
- Raw dispatch = count of granted mechanical actions lacking a selected typed operation; pass only at zero.
- Mechanical-failure time = sum of timing intervals classified as retry, reconstruction, malformed recovery, failed guard/selector, or correction.
- Repeated fingerprint = prohibited predecessor execution claims after verification; pass only at zero.
- Promoted reuse = pre-action promoted selections / eligible compatible intents.
- Prevented failures = explicit pre-dispatch rejections of prohibited predecessors.
- Mechanical overhead = `mechanical_seconds / governed_active_seconds`; hard pass at `<= 0.10`, desired status at `<= 0.05`. Governed active time is the union of run-active intervals. Mechanical time is the union of included mechanical intervals clipped to that active union; overlap is counted once and the explicit exclusion classes take precedence.

Only separately event-classified user-approval wait, external service/rate-limit wait, and productive model/domain execution are excluded from the overhead numerator. Local retries, reconstruction, malformed recovery, guard, selector, and correction time remain mechanical.

**Verification:** Freeze `Tasks/prevention-system-completion/acceptance-corpus.json` before the first measured action. Its hash, immutable revision, window rule, minimum denominator, required action/owner strata, warm-up treatment, incomplete/failure treatment, and exclusion policy follow **Normative contract E**. Each report embeds that hash plus numerator, denominator, and event ids. Unit fixtures prove formulas but return `CONTRACT_TEST_ONLY`. Only the frozen representative real governed corpus can produce acceptance PASS; a mutated manifest or insufficient stratum returns `INSUFFICIENT_EVIDENCE`.

**Evidence/containment:** Emit `acceptance-report.json` and a human Markdown projection from the same result. Queries are read-only and can be rolled back without changing the ledger.

**Requirements:** `CUR-METRICS`, `FUT-METRICS`, `ACC-REGISTERED-95`, `ACC-OVERHEAD`, `ACC-ZERO-RAW`, `ACC-ZERO-REPEAT`.

## Change 9 — Migrate governed call sites and prohibit the legacy path

**Why:** New APIs do not prevent errors while normal runbooks still invoke old raw boundaries.

**Files:**

- Update `skills/sequence-runner/SKILL.md` and registered sequence documents to call `prevention_controller.py dispatch/resume/report` as their single public path.
- Keep legacy scripts as internal adapters where needed, but require an opaque controller-created `GovernanceCapability` bound to run, intent, decision, registry hash, and process/session identity. Constructors and mutating journal/adapter methods are private to the controller package; direct public invocation cannot mint this capability.
- Regenerate `SEQUENCES.md` from the canonical registry.
- Add `tests/prevention/test_no_legacy_governed_entrypoints.py`.

**Migration rule:** Do not add aliases or permissive adapters. Each old public command is either replaced by a typed owner call, retained as a private adapter implementation, or rejected with `LEGACY_GOVERNED_ENTRYPOINT_PROHIBITED`. Build a complete call-graph inventory covering CLI/subprocess edges and direct Python imports/calls. Static AST/import checks permit mutation only from the controller-owned allowlist and also scan registry documents, skills, and tests for `--request-json`, `--context-file`, `--argv-json`, `--command`, remainder argv, or model-authored JSON/text patches.

**Verification:** Static scan plus live negative tests prove zero governed legacy entry points. Non-governed diagnostic compatibility is explicitly labeled and excluded from fully governed acceptance.

**Evidence/containment:** Emit a migration inventory with every old boundary and disposition. Do not delete a legacy implementation until its typed adapter and same-path test pass.

**Requirements:** `CUR-TYPED`, `FUT-TYPED`, `ACC-ZERO-RAW`, `CUR-ENTRYPOINT`, `FUT-ENTRYPOINT`.

## Change 10 — Run the accumulated-surface review and real acceptance drive

**Why:** Unit tests alone cannot prove host enforcement, external owner coverage, durable resume, or representative metrics.

**Files/evidence:**

- Add `Tasks/prevention-system-completion/implementation-evidence/` only for controller-produced reports.
- Do not hand-edit acceptance JSON.

**Validation order:**

1. `python3 -m compileall` for all new/modified Python surfaces.
2. `python3 scripts/run_pytest.sh` for targeted prevention tests.
3. `python3 scripts/run_pytest.sh` for the full memory-knowledge suite.
4. Run owner coverage and black-box acceptance; require all ten approved executable contracts to PASS and exact fail-closed state/admission results for the six custodian-required and nine unavailable owners.
5. Run the full crash matrix across transitions, effects, branches, worktrees, and multiple run ids.
6. Run hook/action-surface bypass tests from a trusted project-local Codex layer.
7. Run a fixed representative governed corpus through the sole controller entry point.
8. Generate the acceptance report and require: raw dispatch `0`; repeated prohibited fingerprint executions `0`; under-budget launches `0`; first compatible post-verification dispatch uses the successor; registered use `>=0.95`; mechanical overhead `<=0.10`, with `<=0.05` also reported.
9. Run `verify-work` against the recorded pre-change baseline, including committed, staged, unstaged, and untracked in-scope files; fix validated findings and rerun invalidated tests.

**Terminal rule:** The implementation may be called complete only if all steps pass on the same code revision and all agent/tool resources are closed. `HOST_CAPABILITY_UNSATISFIED`, `EXTERNAL_OWNER_EVIDENCE_MISSING`, `INSUFFICIENT_EVIDENCE`, or any metric miss is a concrete non-pass, not a waived limitation.

## Normative contract A — enums and immutable values

All identifiers are non-empty ASCII strings matching the existing `work_memory.require_id` contract; timestamps are UTC RFC 3339 seconds; hashes are lowercase 64-character SHA-256; paths are normalized repository-relative strings unless explicitly named absolute.

| Contract | Exact members or required fields |
| --- | --- |
| `ActionClass` | `BASH`, `APPLY_PATCH`, `MCP`, `UNIFIED_SHELL`, `WEB_SEARCH_BROWSER`, `SUBAGENT`, `NON_MCP_REMOTE` |
| `OwnerKind` | `PYTHON_SCRIPT`, `SHELL_SCRIPT`, `COMPOSITE`, `SUBSEQUENCE`, `EXTERNAL` |
| `OperationName` | `INSPECT_HOST`, `REGISTER_INTENT`, `DISPATCH`, `RESUME`, `REPORT` |
| `GovernanceLevel` | `FULLY_GOVERNED`, `HOST_CAPABILITY_UNSATISFIED`, `UNGOVERNED_DIAGNOSTIC` |
| `DecisionKind` | `SELECT_SUCCESSOR`, `SELECT_PROMOTED`, `SELECT_REGISTERED`, `REJECT` |
| `TransitionState` | `INITIALIZED`, `HOST_ADMITTED`, `INTENT_RECORDED`, `SELECTED`, `BUDGET_RESERVED`, `EFFECT_PREPARED`, `EFFECT_COMMITTED`, `VERIFIED`, `TERMINAL_EMITTED` |
| `TimingClass` | `MECHANICAL_RETRY`, `MECHANICAL_RECONSTRUCTION`, `MECHANICAL_MALFORMED_RECOVERY`, `MECHANICAL_GUARD`, `MECHANICAL_SELECTOR`, `MECHANICAL_CORRECTION`, `EXCLUDED_USER_APPROVAL_WAIT`, `EXCLUDED_EXTERNAL_WAIT`, `PRODUCTIVE_MODEL_DOMAIN` |
| `ParameterValue` | closed canonical union. Scalars: `STRING`, `INTEGER`, finite `NUMBER`, `BOOLEAN`, `UUID`, `SHA1`, `SHA256`, `FULL_GIT_OBJECT_ID`, `GIT_BRANCH_NAME`, `PATH`, `ENUM`, `ENUM_FROM_REGISTRY`, `RESOURCE_KEY`, `SECRET_HANDLE`, `APPROVAL_RECEIPT_ID`. Collections: homogeneous ordered `LIST`, canonical sorted-unique `SET`, `NONEMPTY_SET`, `SET_ENUM`; structural values: closed `TAGGED_UNION(tag,payload)` and `EXACT_OBJECT` with the exact declared fields. Secrets use only provider/key/version handles and never persist resolved values. |
| `TypedParameter` | `name:id`, `value:ParameterValue`; names are unique and values validate against the effective owner's `ParameterSpec` before selection and again before dispatch |
| `ActionIntent` | `schema_version:int=1`, `intent_id:id`, `task_id:id`, `run_id:id`, `requested_sequence_id:id`, `requested_implementation_id:sha256`, `compatibility_key:sha256`, `action_class:ActionClass`, `parameters:tuple[TypedParameter,...]`; no optional fields; recurrence eligibility is controller-derived |
| `HostCapabilities` | `schema_version:int=1`, `session_id:id`, `challenge_nonce:id`, `config_sha256`, `hook_sha256`, `trusted:bool`, `enabled:bool`, `intercepted_classes:set[ActionClass]`, `withheld_classes:set[ActionClass]`, `granted_classes:set[ActionClass]`, `issued_at_utc`, `expires_at_utc`, `host_signature:string`; sets are disjoint where appropriate and every granted class is intercepted or withheld for `FULLY_GOVERNED` |
| `ParameterSpec` | `name`, one exact `ParameterValue` constructor, constructor arguments (enum/registry/root/provider/object/union/element schema), and a closed predicate AST. Predicate nodes are `ALL`, `ANY`, `NOT`, `PRESENT`, `ABSENT`, `EQ`, `NE`, `IN`, `IMPLIES`, `REQUIRED_IF`, `REQUIRED_UNLESS`, `RANGE`, `LENGTH`, `MATCHES`, `ROOT_CONTAINED`, and `RESOLVES`; operands are only `FIELD`, typed `LITERAL`, or another predicate. Proposal strings such as `required_for`, `required_unless`, `fixed`, `derived_from`, mutually exclusive fields, and mode-specific exact objects must be normalized to this AST in the executable contract; runtime prose evaluation is forbidden. |
| `OwnerBudgetContract` | closed union `FIXED_UNIT`, `PROFILED_PROGRESSIVE`, `ATOMIC_FRONTIER`, `CHILD_COMPOSITION`; all variants derive complete vectors without caller budget fields |
| `BindingReceipt` | exact non-secret provider result: `receipt_id`, `binding_kind`, `provider_id`, `key_or_resource_id`, `version_id`, `scope_sha256`, `value_fingerprint_sha256`, `consumable`, `expires_at_utc?`; secret contents are forbidden |
| `ReconciliationContract` | owner/command/mode id, preparation-evidence schema, closed read-only observable specs, ordered typed predicates for conflict, applied, and not-applied, default `INDETERMINATE`, and exact result-evidence schema; all fields are content-addressed |
| `TerminalContract` | owner/command/mode id and exactly two typed branches: `EXECUTED_RESULT` requires an accepted same-generation `effect_committed`/`effect_execution_started` provenance chain plus recorded transport/output and semantic re-observation; `RECOVERED_RESULT` requires authenticated `ALREADY_APPLIED` reconciliation plus fresh semantic postcondition evidence and forbids a return-code claim; both emit an exact content-addressed verifier-output schema and canonical `result_hash` |
| `OwnerSpec` | exactly the owner keys listed in Change 1, with `parent_sequence_ids:tuple[id,...]` replacing the scalar parent; `schema_version=1`; handler resolves; parameter names unique; `${name}` argv placeholders reference exactly declared parameters; parents are sorted/unique and non-empty iff `standalone=false`; dispatch requires the active parent to be present |
| `OperationSignature` | canonical ordered record of `operation_kind`, `effect_class`, `verification_contract_sha256`, `parameter_schema_sha256`, `action_class`, `owner_implementation_id`, `source_bundle_sha256`, and `repository_roots_sha256` |
| `CompatibilityKey` | SHA-256 of the versioned operation-signature compatibility subset plus normalized non-secret compatibility parameters; mapping is exact-name/type, an explicitly versioned compatible addition with a declared default, or incompatible |
| `TaskRepositoryIdentity` | `repository_common_dir_sha256`, `worktree_root:absolute-path`, `worktree_id:sha256`, `branch_ref:string`, `branch_base_commit:sha1`, `task_id:id`; all values are controller-derived from Git and the recorded task metadata |
| `GovernanceCapability` | opaque in-memory value with `capability_id`, `task_id`, `run_id`, `intent_id`, `decision_id`, `registry_sha256`, `session_id`, `process_id:int`, `issued_at_utc`, `expires_at_utc`, and controller-only MAC; it is never accepted from CLI, JSON, environment, or another process |
| `EffectIdentity` | `effect_id:sha256`, `idempotency_key:sha256`, `effect_kind:id`, `owner_sequence_id:id`, `implementation_id:sha256`, `task_id:id`, `run_id:id`, `branch_ref:string`, `worktree_id:sha256`; `effect_id` hashes the executable-contract hash, intent/task/run/owner identity, canonical validated non-secret parameter and secret-handle identities, and sorted binding-receipt hashes—never argv or resolved secret bytes |
| `DispatchDecision` | `decision_id:id`, `intent_id:id`, `kind:DecisionKind`, `reason_code:id`, `effective_sequence_id:id?`, `effective_implementation_id:sha256?`, `selector_milliseconds:int>=0`; effective fields are required for select kinds and forbidden for `REJECT` |

Canonical JSON is a persistence/projection encoding only. Public governed operations accept typed CLI flags or in-process values; they never accept caller-authored JSON.

## Normative contract B — prevention event fields

Every new event has the existing common `event_id`, `event_type`, and `recorded_at_utc` fields plus `task_id`, `run_id`, `branch_ref`, and `worktree_id`. Fields below are additional and exact; `?` means optional only under the stated invariant.

| Event | Additional required fields and invariant |
| --- | --- |
| `action_intent_recorded` | `intent_id`, `requested_sequence_id`, `requested_implementation_id`, `compatibility_key`, `action_class`, `parameters`; parameters persist canonical non-secret values and secret handles only |
| `host_action_observed` | `host_action_id`, `session_id`, `action_class`, `observed_at_utc`, `capability_manifest_sha256`; every granted mechanical action must have exactly one record before project dispatch |
| `host_capability_recorded` | `session_id`, `challenge_nonce`, `governance_level`, `config_sha256`, `hook_sha256`, `intercepted_classes`, `withheld_classes`, `granted_classes`, `expires_at_utc`, `evidence_ref` |
| `dispatch_selected` | `intent_id`, `decision_id`, `decision_kind`, `effective_sequence_id`, `effective_implementation_id`, `reason_code`, `selector_milliseconds`; kind is a select kind |
| `dispatch_rejected` | `intent_id`, `decision_id`, `decision_kind=REJECT`, `reason_code`, `selector_milliseconds`; effective owner fields forbidden |
| `predecessor_prohibited` | `compatibility_key`, `failure_fingerprint`, `predecessor_sequence_id`, `predecessor_implementation_id`, `successor_sequence_id`, `successor_implementation_id`, `verification_event_id` |
| `budget_admitted` | `reservation_id`, `owner_sequence_id`, `unit_budget`, `reserved_vector`, `remaining_vector_before`, `lease_expires_at_utc` |
| `budget_rejected` | `owner_sequence_id`, `unit_budget`, `required_vector`, `remaining_vector`, `failed_dimensions`, `reason_code` |
| `transition_prepared` / `transition_committed` | `journal_id`, `transition`, `state_hash`; committed also requires `prepared_event_id` |
| `effect_prepared` | `journal_id`, all `EffectIdentity` fields, `transition_prepared_event_id`, `owner_contract_sha256`, `reconciler_sha256`, `preparation_artifact_sha256`; the artifact contains every selected owner/command/mode pre-mutation identity, pre-state/hash, child/stage id, root snapshot, and non-secret provider version required by its typed contract |
| `effect_committed` | `journal_id`, `effect_id`, `prepared_event_id`, `attempt_generation:int>0`, `execution_started_event_id`, `result_hash`, `exit_status`; exactly one per effect/generation, the start must be the same generation, and unstarted/superseded/delayed/conflicting commits are rejected |
| `effect_reconciled` | `journal_id`, `effect_id`, `prepared_event_id`, `attempt_generation:int>=0`, `prior_reconciliation_event_id?`, `owner_contract_sha256`, `reconciler_sha256`, `preparation_artifact_sha256`, `reconciliation:ALREADY_APPLIED|NOT_APPLIED|INDETERMINATE`, `reconciliation_artifact_sha256`, `observable_ownership_sha256`, `evidence_sha256`; unique by effect/generation, linked across generations, and `INDETERMINATE` fails closed |
| `effect_execution_authorized` | `journal_id`, `effect_id`, `attempt_generation:int>0`, `not_applied_reconciliation_event_id`, `prior_generation:int>=0`, `owner_contract_sha256`, `authorization_sha256`; generation must equal `prior_generation+1`, the referenced reconciliation is `NOT_APPLIED` at `prior_generation`, and exactly one authorization exists per effect/generation |
| `effect_execution_started` | `journal_id`, `effect_id`, `attempt_generation:int>0`, `execution_authorized_event_id`, `owner_contract_sha256`; atomically consumes the same-numbered authorization and is unique by effect/generation before the external call; generation 1 follows reconciliation 0 and all later generations are contiguous |
| `owner_binding_recorded` | `intent_id`, `effect_id`, `owner_sequence_id`, `owner_contract_sha256`, `parameter_name`, all non-secret `BindingReceipt` identity/version/scope fields, `binding_receipt_sha256`; effect id is derived from the canonical validated parameter/handle identities plus sorted receipt hashes, and the event is required before argv/effect preparation |
| `authorization_receipt_consumed` | `receipt_id`, `provider_id`, `version_id`, `scope_sha256`, `intent_id`, `effect_id`, `owner_sequence_id`, `owner_contract_sha256`, `effect_prepared_event_id`; journal-lock unique by receipt id and replayable only for the same effect |
| `child_delegation_recorded` | `delegation_id`, `parent_effect_id`, `parent_owner_sequence_id`, `child_owner_sequence_id`, `child_intent_id`, `blocker_id`, `verification_event_id`, `mode`; common ownership binds the same task/run/branch/worktree and the parent must be same-journal `STARTED` |
| `child_delegation_consumed` | `delegation_id`, `parent_effect_id`, `child_effect_id`, `child_intent_id`, `effect_prepared_event_id`; journal-lock unique by delegation id and replayable only for the identical child effect |
| `owner_terminal` | `effect_id`, `owner_sequence_id`, `owner_contract_sha256`, `result_kind:EXECUTED_RESULT|RECOVERED_RESULT`, `result_hash`, `terminal_evidence_sha256`, `terminal_artifact_sha256`, `semantic_verdict`, `effect_committed_event_id?`, `attempt_generation?`, `execution_started_event_id?`, `reconciliation_event_id?`, `reconciliation_artifact_sha256?`; the committed/start fields are required only for `EXECUTED_RESULT`, the reconciliation fields only for `RECOVERED_RESULT`, all opposite-branch fields are forbidden, and recovered evidence has no return-code claim; one locked compare-and-append per effect id |
| `registered_reuse_recorded` | `intent_id`, `decision_id`, `compatibility_key`, `sequence_id`, `implementation_id`, `promotion_event_id`, `registered_verification_event_id`, `pre_dispatch:bool=true` |
| `prevented_failure_recorded` | `intent_id`, `decision_id`, `compatibility_key`, `failure_fingerprint`, `predecessor_implementation_id`, `successor_implementation_id?`, `prohibition_event_id` |
| `timing_interval_recorded` | `interval_id`, `intent_id?`, `decision_id?`, `timing_class`, `started_at_utc`, `ended_at_utc`, `duration_milliseconds`; computed duration must equal the timestamps and intervals for one run may not overlap within the same timing class |

## Normative contract C — owner adapter lifecycle

Each method accepts `GovernanceCapability` plus the typed value named below. Results use `AdapterState = INITIALIZED|PREPARED|ALREADY_APPLIED|EXECUTED|VERIFIED|TERMINAL` and `AdapterError = INVALID_INPUT|DEPENDENCY_MISSING|AUTH_REQUIRED|EVIDENCE_MISSING|EFFECT_INDETERMINATE|EXECUTION_FAILED|VERIFICATION_FAILED`; errors are data plus a nonzero exit, never a fallback.

| Method | Input | Result and transition |
| --- | --- | --- |
| `initialize` | `ActionIntent`, `OwnerSpec` | resolved repository roots and `INITIALIZED`; no mutation |
| `required_budget` | initialized owner, selected command/mode, typed durable task/frontier/child state | complete owner-derived `UnitBudget`; no caller budget and no mutation |
| `prepare_effect` | initialized owner, journal | `EffectIdentity`, typed binding/approval receipts, immutable preparation-evidence artifact, and durable `PREPARED`; all required pre-state exists before mutation |
| `reconcile` | effect identity, executable-contract/reconciler hashes, preparation artifact, typed observable results | authenticated `ALREADY_APPLIED`, `NOT_APPLIED`, or fail-closed `EFFECT_INDETERMINATE` plus immutable evidence/artifact hashes |
| `execute` | prepared `EffectIdentity` | one shell-free argv effect and `EXECUTED`; never called after `ALREADY_APPLIED` |
| `verify` | executed/already-applied effect | typed terminal evidence and `VERIFIED` |
| `emit_terminal` | verified effect | deterministic hashed artifact followed by one locked `owner_terminal` compare-and-append; the event commits `TERMINAL` and replay repairs checkpoint/projection without duplication |

`Tasks/prevention-system-completion/owner-descriptors.json` is non-normative evidence inventory only. `owner-migration-manifest.json` is the frozen planning authority; its 25 rows validate exactly as migration `OwnerSpec`/adapter specs and include handler symbol, typed parameter mapping, fixed argv tokens, effect identity, reconciler algorithm, terminal result parser/schema, repository binding, parent relation, evidence paths, and evidence hashes. Every formerly `CUSTODIAN_EVIDENCE_REQUIRED` row names its now-located checked-in authority; no prose is translated by inference during coding.

## Normative contract D — budget reservation

`BudgetRoleId` is closed: `CORE`, `INTERNAL_READINESS`, `REQUIREMENTS_COVERAGE`, `REQUIREMENTS_SATISFACTION`, `ADJUDICATOR`, `MATERIALIZATION`, `TERMINAL`, `RETRY`. `UnitBudget` fields are `schema_version=1`, `owner_sequence_id`, `productive_milliseconds`, `mandatory_role_milliseconds` keyed only by `BudgetRoleId`, `adjudication_milliseconds`, `materialization_milliseconds`, `terminal_milliseconds`, `retry_milliseconds`, `token_units:int?`, and `monetary_micros:int?`. All supported values are nonnegative integers; required duration is the exact sum. `BudgetReservation` fields are `reservation_id`, `task_id`, `run_id`, `owner_sequence_id`, `required_vector`, `remaining_vector_before`, `remaining_vector_after`, `lease_started_at_utc`, `lease_expires_at_utc`, `status:ACTIVE|RELEASED|EXPIRED|RECONCILED`, and `version:int`.

`OwnerBudgetContract` is the sole producer of `UnitBudget`: `FIXED_UNIT` returns its exact vector; `PROFILED_PROGRESSIVE` selects a finite materialized owner/command/mode profile; `ATOMIC_FRONTIER` sums every typed task in the durable next frontier; `CHILD_COMPOSITION` sums the complete parent and content-addressed child vectors. Budget expression nodes are nonnegative `CONST`, approved named `VAR`, `ADD`, `MULTIPLY`, and bounded `SUM(index, LIST_VAR, expression)`. A list variable has an exact typed producer, maximum cardinality, per-item schema, and frozen content hash before evaluation. A profile that supplies only `productive_task_count=N` deterministically expands tasks as `<owner>/<profile>/productive/<zero-padded-index>` for `0..N-1`, each with the approved atomic-task cap; its declared duration must equal those tasks plus the exact role/overhead vector or materialization fails. Every atomic task includes retry within its 3,600,000 ms cap; a long workflow is the progressive sum of its tasks, never one 60-minute unit.

`DurationCapacityProvider` derives remaining duration from the controller's persisted start/deadline and monotonic elapsed-time projection and defines initialization, refresh, restart recovery, and lease reconciliation. Token and monetary providers exist only when a named authoritative host/provider API supplies capacity and recovery semantics; otherwise the host capability record persists `UNSUPPORTED` and those dimensions are absent from both vectors. Compare-and-reserve, renewal, release, and expiry reconciliation are atomic against ledger `version`; exact duplicate requests return the same reservation, while a second owner cannot consume reserved capacity. One-unit-below means subtract one unit from each supported dimension in separate owner/command/mode tests.

## Normative contract E — representative acceptance corpus

The corpus manifest is frozen and hashed before its first action. It contains `schema_version=1`, `revision`, `frozen_at_utc`, `window_start_event_id`, `window_end_rule=FIRST_TERMINAL_AFTER_ALL_STRATA`, `minimum_eligible_recurring_actions=40`, `minimum_completed_runs=6`, required `ActionClass` strata for every granted class, required owner strata containing every locally available owner plus every external owner authorized for that drive, `warmup_runs=1` excluded only from thresholds but retained in raw evidence, `include_failed_and_incomplete=true`, and the three permitted exclusion classes from the research package.

The existing six-run sufficiency floor is retained and strengthened by the 40-action and strata requirements. The report rejects a manifest edited after `window_start_event_id`, a missing required stratum, a denominator below 40, fewer than six completed runs, or any interval lacking a timing class. Selection of the end event is mechanical and cannot be moved after results are observed.

## Requirement traceability

| Requirement | Implemented by | Proven by |
| --- | --- | --- |
| `CUR-ENTRYPOINT`, `FUT-ENTRYPOINT` | Changes 1, 4, 9 plus the five-defect delta | exact 25-row 10/6/9 state report, ten executable-contract passes, fifteen pre-dispatch rejections, and one-entry static/live checks |
| `CUR-TYPED`, `FUT-TYPED` | Changes 1, 3, 9 | typed negative corpus and raw-dispatch zero query |
| `CUR-INTERCEPTION`, `FUT-INTERCEPTION` | Changes 3, 5 | supported hook tests plus unsupported-class withholding/admission evidence |
| `CUR-CORRECTION`, `FUT-CORRECTION` | Changes 2, 3, 6 | prohibited predecessor and mandatory successor tests |
| `CUR-LEARNING`, `FUT-LEARNING` | Changes 2, 6 | one-lineage end-to-end test with pre-action reuse |
| `CUR-BUDGET`, `FUT-BUDGET` | Changes 2, 7 | component audit and one-unit-below zero-launch tests |
| `CUR-RESUME`, `FUT-RESUME` | Changes 2, 3, 4 | full transition/effect/branch/multiple-run crash matrix |
| `CUR-METRICS`, `FUT-METRICS` | Changes 2, 8 | canonical metric contract and reproducible report |
| `ACC-ZERO-RAW` | Changes 3, 5, 8, 9 | raw dispatch count zero and injected raw paths mutate nothing |
| `ACC-ZERO-REPEAT` | Changes 3, 6, 8 | prohibited predecessor has no execution claim |
| `ACC-BUDGET-ADMISSION` | Change 7 | every one-unit-below case launches zero work |
| `ACC-MANDATORY-CORRECTION` | Changes 3, 6 | fresh compatible intent dispatches only successor |
| `ACC-REGISTERED-95` | Change 8 | fixed-window real-corpus report at or above 0.95 |
| `ACC-OVERHEAD` | Change 8 | real-corpus ratio at or below 0.10 and 0.05 status reported |

## Approval and stop boundaries

The user's explicit bounded convergence approvals authorize implementation of the five-defect owner-runtime delta after its fresh coverage and satisfaction gates both PASS; no additional change-by-change approval is required inside this recorded scope. The earlier changes remain bounded by their existing approvals. The two authorized repositories are `memory-knowledge` and `mcp-agents-workflow`; MCP writes are limited to the exact **Authorized source writes** and **Authorized focused tests** paths in the source-bound integration table. Read-only authenticated dependencies in that table may be inspected but not edited. Stop before any new requirement, another repository, a path not named by this delta, user-global hook installation, phase-ledger contract change, commit, push, deployment, secret access, external message, or destructive action.
