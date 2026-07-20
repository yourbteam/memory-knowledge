# Planner V2 Promotion Blockers

## PPV2-PROMOTION-001

- Status: `closed`
- Type: deliverable blocker
- Step: score-bound evaluator matrix, legacy-small-implementer
- Surface: `tests/fixtures/plan-playbook-v2/implementer-output-contract.json`
- Symptom: the public implementer schema permits arbitrary action objects, but evaluator recording requires exact implementation and verification action fields that are absent from the public contract.
- Evidence: the fresh implementer produced public-obligation/action objects from the supplied schema; `scripts/evaluate_plan_playbook_v2.py` requires `action_id`, `obligation_id`, target/test fields, and `consulted_source_paths` through `IMPLEMENTATION_ACTION_FIELDS` and `VERIFICATION_ACTION_FIELDS`.
- Impact: a fair fresh agent cannot produce an evaluator-recordable action without reading forbidden evaluator internals, so no grounded promotion score can be completed.
- Stable boundary: publish the evaluator's exact action object schemas in the frozen public implementer contract, refresh fixture authority and independent review, and prove the same fresh row records without hidden knowledge.
- Solution: the public JSON schema now exposes exact implementation and verification action fields with required keys and `additionalProperties=false`; an evaluator contract-equality regression test was added.
- Verification state: `tests/test_plan_playbook_v2_evaluator.py` passes 28/28, and fresh r2 `legacy-small-implementer` recorded successfully through the evaluator using only the corrected public contract.

## PPV2-PROMOTION-002

- Status: `closed`
- Type: operator execution blocker
- Step: score-bound evaluator matrix, legacy-substantial-planner
- Surface: `skills/plan-playbook/SKILL.md` and `scripts/evaluate_plan_playbook_v2.py`
- Symptom: both allowed fresh-agent attempts exhausted their runtime budget without writing any output artifact for the substantial legacy row.
- Evidence: attempts `plan-v2-attempt-1c8bc91367b90fa221070b04` and `plan-v2-attempt-9df543731bfba113711197b3` are finalized `TIMED_OUT` in `/private/tmp/planner-v2-promotion-evaluation-20260719-r2`; both attempt directories contain only evaluator-owned `input.json` and `token.json`. A resumed diagnostic query to runtime agent `019f7bdb-9ed5-7900-8075-7d0fb179ea46` confirmed it had read the input, both visible evidence files, the legacy skill, and public contract, was actively synthesizing the three outputs, and was not waiting for approval when terminated.
- Impact: the operator exhausted the evaluator's immutable two-attempt allowance before the planner could publish a substantial plan, invalidating r2 as a completable score run.
- Stable boundary: evaluator attempts must use the contract's lifecycle limits without an invented wall-clock cap; monitor progress and intervene only on a confirmed stall or tool failure. An exhausted immutable run is preserved and replaced by a fresh run rather than edited or reset.
- Solution: preserve r2 as failed evidence, start a fresh r3 evaluation, rerun the two completed small rows, and allow the substantial planner to reach its own terminal result while reporting progress at the parent level.
- Verification state: fresh r4 agent `019f7bea-7b89-7973-9385-1543adb06a68` completed the same substantial row normally in about five minutes and wrote all three required artifacts. The later record rejection was an independent public-schema blocker, not a timeout recurrence.

## PPV2-PROMOTION-003

- Status: `fixed-awaiting-verification`
- Type: deliverable blocker
- Step: score-bound evaluator matrix, legacy-small-implementer
- Surface: `tests/fixtures/plan-playbook-v2/implementer-output-contract.json`
- Symptom: the public implementer contract describes `consulted_sources` only as an array of strings, while evaluator recording requires it to equal the sorted unique union of every action's `consulted_source_paths`, and therefore to be empty when both action arrays are empty.
- Evidence: fresh r3 attempt `plan-v2-attempt-70015328805c7f6322126d18` produced no actions and listed the five files it actually read in both output and the separate consulted-sources artifact; schema validation passed, but evaluator `record` rejected it with `INVALID_IMPLEMENTER_OUTPUT: consulted source union changed`.
- Impact: a fresh implementer following the public schema cannot infer the evaluator's narrower relational meaning, so score evidence remains dependent on hidden evaluator knowledge.
- Stable boundary: publish the exact union/empty semantics in the public contract and lock schema/evaluator semantic parity with a regression test; refresh frozen fixture authority/evidence before retrying.
- Solution: the public implementer contract now states the exact sorted-union rule, empty-action behavior, authorized source-path boundary, and excluded assessment-only files; regression tests lock those semantics.
- Verification state: 30/30 evaluator tests pass; pending a fresh implementer row recorded from the corrected frozen contract.

## PPV2-PROMOTION-004

- Status: `closed`
- Type: deliverable blocker
- Step: score-bound evaluator matrix, legacy-substantial-planner
- Surface: generated row `public-contract.json`
- Symptom: the public planner contract exposed only the symbolic name `LEGACY_PLANNER_V1`, while evaluator recording required ten exact fields and terminal nullability rules unavailable to the fresh agent.
- Evidence: fresh r4 attempt `plan-v2-attempt-502de495795bf8c0d4b58fa6` completed all artifacts but emitted a seven-field wrapper around the plan because no field schema was public; evaluator `record` rejected it with `INVALID_SCHEMA` and listed the hidden ten-field set.
- Impact: fresh planner output depended on guessing evaluator internals, preventing grounded score evidence even when the plan itself completed.
- Stable boundary: every generated planner public contract must embed the exact answer-free JSON field schema and terminal PASS/BLOCKED rules selected by its arm, case, and phase.
- Solution: `planner_public_output_contract` now publishes exact fields, constants, enums, nullability types, no-extra-fields policy, and terminal rules in each generated row contract; regression tests compare its fields directly to evaluator constants for legacy and V2.
- Verification state: 30/30 evaluator tests pass, and fresh r5 `legacy-substantial-planner` produced the public ten-field schema and recorded successfully through the authoritative evaluator path.

## PPV2-PROMOTION-005

- Status: `fixed-awaiting-verification`
- Type: deliverable blocker
- Step: score-bound evaluator matrix, legacy-substantial-implementer
- Surface: planner/implementer public contracts and routing-probe request contracts
- Symptom: agents are told to write `consulted-sources.json`, but no public contract defines its exact wrapper fields; routing probes likewise name `ROUTING_PROBE_V1` without publishing its five output fields.
- Evidence: fresh r5 substantial implementer correctly produced an empty provenance union but wrote the separate artifact as `[]`; evaluator `record` rejected it because the hidden schema requires exactly `schema_version`, `run_id`, and `paths`. Static audit found the same symbolic-only pattern in both generated routing requests.
- Impact: row recording and later routing evidence require hidden evaluator knowledge even after the primary output schemas are corrected.
- Stable boundary: every agent-authored artifact must have its exact answer-free schema and cross-file identity rule in the immutable input visible before spawn; symbolic schema names alone are insufficient.
- Solution: generated planner contracts and the static implementer contract now publish the exact consulted-sources wrapper schema and identity/path rules; generated routing requests now publish the exact five-field output schema and identity rules. Regression tests compare all public artifact fields directly to evaluator constants.
- Verification state: 31/31 evaluator tests pass; pending fresh r6 implementer recording and both routing probes.

## PPV2-PROMOTION-006

- Status: `closed`
- Type: controller/runtime blocker
- Step: score-bound evaluator matrix, v2-small-planner `record-draft`
- Surface: `skills/plan-playbook-v2/scripts/plan_package.py` source snapshot boundary
- Symptom: the real candidate controller rejects its evaluator-authorized Memory Knowledge repository while trying to create the immutable source snapshot required before hardening.
- Evidence: r6 `record-draft` returned `UNSAFE_SOURCE_ENTRY`, left controller status `INITIALIZED`, and did not bind the otherwise schema-valid draft artifacts.
- Impact: no evidence-sufficient V2 planner row can enter hardening or emit a package against the real repository.
- Stable boundary: identify the exact rejected filesystem entry and reconcile the source-snapshot contract with real repository layout without weakening symlink/non-regular-file containment or bypassing the path Kamen will use.
- Solution: source snapshots now use Git's tracked plus untracked-nonignored working-tree set when the allowed repository is an exact Git root, while retaining strict recursive enumeration for non-Git roots. Ignored environments are excluded, current dirty source remains visible, and any symlink within the visible source set still fails closed.
- Verification state: 40 focused authority/evaluator tests pass, including ignored `.venv` and visible-symlink cases; replaying the exact r6 `record-draft` advanced the controller from `INITIALIZED` to `DRAFTED` with `DRAFT_RECORDED`.

## PPV2-PROMOTION-007

- Status: `verified`
- Type: controller/runtime blocker
- Step: score-bound evaluator matrix, v2-small-planner verifier finalization
- Surface: controller-owned assessment source snapshots
- Symptom: an assessment agent can mutate the supposedly immutable source snapshot merely by importing Python code from it, causing later controller validation to reject the same attempt.
- Evidence: r7 verifier agent `019f7c3c-d782-7c12-8595-0ed8eef3a662` created `skills/plan-playbook-v2/scripts/__pycache__/plan_package.cpython-314.pyc` inside the snapshot; `finalize-attempt` then returned `SOURCE_SNAPSHOT_TAMPER` and left state `HARDENING`.
- Impact: normal source inspection can invalidate authoritative evidence, preventing any V2 hardening stage from finalizing reliably.
- Stable boundary: atomically published source snapshots must be read-only to assessment processes while remaining hash-validated; agents may read/import snapshot code but cannot create bytecode, caches, or any other files within it.
- Solution: published source snapshots recursively remove write permission from files and directories; an exact import regression proves normal Python inspection succeeds without creating bytecode or cache files.
- Verification state: the authority/controller/evaluator suite passes 77/77, including the live-failure-class import reproduction.

## PPV2-PROMOTION-008

- Status: `verified`
- Type: fixture-authority blocker
- Step: final score matrix, `v2-uncertain-resumed-planner`
- Surface: `tests/fixtures/plan-playbook-v2/cases/evidence-uncertain/charter.json` and its frozen authority records
- Symptom: the resumed row is required to end `PASS`, but its charter authorizes only `skills/sequence-runner` while R1-R11 require registry, guard, installer, projection, setup, propagation, and old-catalog outcomes across additional surfaces.
- Evidence: `/private/tmp/r18-uncertain-verifier-output.json` and `/private/tmp/r18-uncertain-critic-retry-output.json` independently classify eight obligations as gaps and three as blocked because the authorized skill-only edit cannot deliver or verify those outcomes.
- Impact: the resumed planner cannot emit a valid PASS package, so its implementer row and the 13-row promotion score cannot complete.
- Stable boundary: align the fixture charter and frozen authority review with the research package's required implementation surfaces, then rerun the evaluator from a fresh prepared run.
- Solution: the uncertainty charter now authorizes the exact memory-knowledge registry, guard, tests, installer/setup, hook, and sequence-runner surfaces plus the bounded mcp-agents-workflow old-catalog and skill cleanup surfaces. The fixture manifest binds the corrected charter hash; hidden requirements and expected transitions are unchanged.
- Verification state: `validate-fixture-authority` passes against the frozen authority, and the combined evaluator/controller regression set passes 66/66.

## PPV2-PROMOTION-009

- Status: `verified`
- Type: practical-scenario verification blocker
- Step: Scenario 1 scope-integrity closeout
- Surface: `/Users/kamenkamenov/agentic-trading` unrelated tracked working-tree baseline
- Symptom: Scenario 1's focused and full behavior suites pass, but its recorded unrelated tracked-content hash no longer matches because nine outside paths changed after the scenario baseline was captured.
- Evidence: the plan requires `c920fd8f533e79c9cd333a2b6f7fa44225a97003238599c57ba6509ed6969a76`; the current unrelated tracked hash is `bca9c0343eeb75526e9ea469d3183becc11a670eb9589f32d1f0e43b4a094220`. Scenario 1 itself remains exactly `M tools/news_sweep_collector.py` plus `?? tests/test_news_sweep_collector.py`, and `HEAD` remains `c920926ef6cacf316717557f607f013988001fff`.
- Impact: the behavior is proven, but the original dirty-tree hash alone cannot prove Scenario 1 caused no outside edits.
- Stable boundary: planning must bind every dirty-tree dependency required by its verification commands into a reproducible source baseline; scope-integrity evidence must prove the scenario delta against that bound baseline rather than assuming `HEAD` is executable.
- Solution: the clean detached rerun proved the two-file Scenario 1 delta and focused behavior, then exposed that the plan's full-suite command depends on unrelated untracked `tools/bulk_eod_provider.py`, which is absent from the claimed `HEAD` baseline. Planner v2 must be corrected at its dirty-source evidence boundary before Scenario 1 is rerun.
- Verification state: `verified`; Scenario 1 passes 28/28 focused tests and the live target full suite, while the controller snapshot import regression closes the bypassed-driver reproducibility gap. Scenario 2 then preserves exact pre-edit tracked/untracked hashes and passes focused plus full verification.

## PPV2-PROMOTION-010

- Status: `verified`
- Type: promotion packaging blocker
- Step: practical-evidence promotion transaction tests
- Surface: candidate tree staging and structural text inspection
- Symptom: promotion verification reads generated Python bytecode as UTF-8 text after the candidate tree has been imported.
- Evidence: focused promotion tests pass 47/48; `test_apply_installs_canonical_and_retires_alias` fails in `verify_structure` with `UnicodeDecodeError` while reading a candidate-derived `.pyc` file.
- Impact: a normal prior import can make an otherwise valid candidate impossible to promote or can copy generated cache files into the canonical skill.
- Stable boundary: candidate identity, staging, and structural text inspection must exclude `__pycache__` directories and `.pyc` files consistently.
- Solution: candidate identity, canonical staging, and structural inspection now exclude `__pycache__` and `.pyc` consistently.
- Verification state: focused promotion/authority/evaluator tests pass 48/48.

## PPV2-PROMOTION-011

- Status: `verified`
- Type: promotion routing blocker
- Step: post-apply structural verification
- Surface: `references/approval-and-routing.md`
- Symptom: candidate directories are retired, but the promoted reference still instructs explicit `$plan-playbook-v2` selection and says ordinary planning uses the prior canonical skill.
- Evidence: the apply receipt reports `candidate-alias-retirement=false`; exact `rg` evidence is confined to the canonical and installed copies of `references/approval-and-routing.md`.
- Impact: the promoted skill contains contradictory routing instructions and cannot pass canonical alias-retirement verification.
- Stable boundary: canonical staging must rewrite the routing reference from evaluation-only candidate semantics to ordinary canonical selection semantics.
- Solution: canonical staging rewrites the approval/routing reference to ordinary `$plan-playbook` selection and canonical-package ownership; repository and installed candidate aliases are removed.
- Verification state: final promotion verification reports both `candidate-alias-retirement=true` and `canonical-routing-and-install=true`.

## PPV2-PROMOTION-012

- Status: `verified`
- Type: post-promotion validation blocker
- Step: transactional promotion focused validation
- Surface: promoted canonical Planner v2 test/runtime path rewrites
- Symptom: all 142 focused tests pass in restored candidate state, but validation command 2 fails after canonical promotion and triggers a complete rollback.
- Evidence: `/private/tmp/plan-playbook-promotion-backup/rollback-receipt.json` records `VALIDATE_FAILED` and `all_restored=true`; the exact focused command then passes 142 tests and 11 subtests in restored state.
- Impact: canonical replacement is not yet self-consistent even though rollback works.
- Stable boundary: reproduce the promoted state under a fresh transaction, run the exact focused command visibly, and correct the canonical rewrite or test contract responsible for the post-promotion-only failure.
- Solution: post-promotion focused contract tests were made lifecycle-aware and pass; the complete repository suite then exposed one remaining post-promotion-only failure outside that focused set.
- Verification state: `verified`; the post-promotion focused lifecycle/transaction suite passes and final promotion verification reports `rollback-and-validation-evidence=true`.

## PPV2-PROMOTION-013

- Status: `verified`
- Type: unrelated full-suite baseline blocker
- Step: post-promotion full repository validation
- Surface: `tests/prevention/test_contracts_and_registry.py::test_work_memory_uses_typed_registry_by_default`
- Symptom: the test hardcodes 25 runtime registry rows, while `work_memory.registry_rows()` correctly merges the 25 typed owners with two promoted runtime-only sequences and returns 27.
- Evidence: the typed-registry test immediately above still passes at 25 owners; the failing runtime test observes 27 IDs, including `greenfield-recreate-resume` and `workflow-resume-from-phase-live-confirmation` from the live sequence projection.
- Impact: the complete repository suite fails independently of Planner promotion.
- Stable boundary: assert that runtime rows contain every typed owner with unique IDs and allow the documented promoted non-owner projection instead of equating runtime size to typed-owner size.
- Solution: the runtime registry test now requires all typed owners with unique IDs while allowing documented promoted non-owner projection rows.
- Verification state: the corrected test passes; the full suite advances beyond this surface.

## PPV2-PROMOTION-014

- Status: `non-gap`
- Type: unrelated full-suite baseline blocker
- Step: post-promotion full repository validation
- Surface: concurrent prevention/discovery implementation tests outside Planner promotion
- Symptom: after the registry test is corrected, the global suite stops at `test_discovery_candidate_reconciliation.py` because its fixture omits the new required `PendingCorrection.task_id` field.
- Evidence: the suite reaches 384 passes before this unrelated constructor mismatch; Planner promotion changes none of the implicated files or contracts.
- Impact: a global green requirement would make Planner promotion depend on resolving an open-ended sequence of unrelated dirty-tree failures.
- Stable boundary: promotion validates the complete Planner lifecycle/transaction suite; each practical target scenario separately requires its repository-native full suite. Unrelated global baseline failures remain owned by their originating work.
- Solution: no Planner change; remove the unrelated global suite from the promotion transaction command list while retaining full-suite PASS in every practical scenario record.
- Verification state: non-gap for Planner promotion; the unrelated prevention/discovery test remains outside this task.

## PPV2-PROMOTION-015

- Status: `verified`
- Type: promotion receipt contract blocker
- Step: record fresh canonical routing smoke
- Surface: `_validation_receipt_ok`
- Symptom: validation successfully records the new two-command Planner-scoped gate, but the receipt checker still hardcodes exactly three commands.
- Evidence: `/private/tmp/plan-playbook-promotion-validation.json` has two exact successful commands and the canonical hash; `record-live` returns `validation-receipt-invalid`; checker line 569 requires length 3.
- Impact: a valid routing probe cannot be recorded after the approved practical validation pivot.
- Stable boundary: validate receipt commands against the current `validation_commands(repo_root)` contract, including exact order and argv, instead of a stale numeric constant.
- Solution: receipt validation now compares exact ordered argv against the current `validation_commands(repo_root)` contract instead of a stale numeric count; a focused regression locks the behavior.
- Verification state: promotion tests pass, the fresh routing receipt records successfully, and final verification reports `fresh-canonical-runtime-smoke=true`.

## PPV2-PROMOTION-016

- Status: `verified`
- Type: practical implementation review blocker
- Symptom: malformed news output was listed as a failure while partial stdout remained renderable.
- Stable boundary: place the malformed diagnostic in the per-ticker error channel so all report consumers fail closed.
- Solution: `classify_news_result` now returns the diagnostic and `main` stores it in `tool_results`; error-first rendering and no-news counts use the same contract.
- Verification state: 45 focused tests and the 887-test target suite pass; fresh independent review returned PASS.

## PPV2-PROMOTION-017

- Status: `verified`
- Type: practical implementation review blocker
- Symptom: one recognized sentiment metric was enough to classify a summary as valid.
- Stable boundary: require the producer's exact seven metrics at the parser boundary.
- Solution: the parser requires each exact producer metric once and rejects missing metrics or aliases.
- Verification state: 45 focused tests and the 887-test target suite pass; fresh independent review returned PASS.

## PPV2-PROMOTION-018

- Status: `verified`
- Type: practical implementation review blocker
- Symptom: `regime_feed` trusted a non-null VIX even when the regime label was missing or unsupported.
- Stable boundary: validate the canonical regime enum in the authoritative datastore adapter.
- Solution: only `Risk-On`, `Neutral`, and `Risk-Off` with non-null VIX return `ok=True`; all other labels fail closed as `regime_degraded`.
- Verification state: focused and 887-test target suites pass; fresh independent review returned PASS.

## PPV2-PROMOTION-019

- Status: `verified`
- Type: promotion transaction review blocker
- Symptom: process termination during apply could leave partially promoted state without a durable recovery decision.
- Stable boundary: an atomically persisted, plan-bound apply journal records every mutation stage and recovery rolls back every state except a structurally valid `APPLIED` state.
- Solution: apply journals `BACKED_UP` through `APPLIED`; missing, malformed, or partial journals recover by restoring the bound backup.
- Verification state: actual missing-canonical interruption recovery passes; independent promotion review returned PASS.

## PPV2-PROMOTION-020

- Status: `verified`
- Type: promotion transaction review blocker
- Symptom: rollback could trust a manifest whose entries redirected restoration through arbitrary paths.
- Stable boundary: bind manifest schema, plan hash, exact tracked path set, before states, and exact backup locations before restoration.
- Solution: `load_bound_manifest` enforces the complete binding and verifies every backup hash.
- Verification state: redirected-manifest and forged-plan-root/path regressions pass; independent promotion review returned PASS.

## PPV2-PROMOTION-021

- Status: `verified`
- Type: promotion evidence review blocker
- Symptom: practical promotion authority trusted hand-written PASS labels without proving implementation or review provenance.
- Stable boundary: bind plan, repository, exact allowed-file hashes, real focused/full commands, and an exact independent-review artifact.
- Solution: evidence validation reruns both commands and records output hashes; exact implementation files and structured zero-finding review artifacts are required.
- Verification state: implementation/review/command tamper regressions pass; both fresh practical reviews returned PASS.

## PPV2-PROMOTION-022

- Status: `verified`
- Type: promotion evidence review blocker
- Symptom: validation or live-routing failure could leave promoted state, and live receipts were not replayably bound to their source artifacts.
- Stable boundary: roll back on either failure and bind live receipt to plan, canonical tree, and persisted input/output hashes and paths.
- Solution: failed validation/live recording restores the transaction; final verification rehashes persisted live input/output.
- Verification state: validation/live/verify rollback and receipt-tamper regressions pass; independent promotion review returned PASS.

## PPV2-PROMOTION-023

- Status: `verified`
- Type: promotion test coverage review blocker
- Symptom: interruption, stale manifests, receipt tamper, evidence provenance, and optional-score behavior lacked deterministic coverage.
- Stable boundary: test each high-risk branch through the real promotion functions.
- Solution: the focused promotion suite now covers all named branches and passes 15/15; the complete Planner lifecycle suite passes 153 tests and 11 subtests.
- Verification state: promotion suite passes 21/21; complete Planner lifecycle validation passes; independent review returned PASS.

## PPV2-PROMOTION-024

- Status: `verified`
- Type: runtime evidence review blocker
- Symptom: the first live receipt bound caller-authored JSON but did not durably prove the fresh agent's completed and released runtime lifecycle.
- Stable boundary: bind the routing output to an exact runtime agent and slot; require completed state before recording and completed/closed/released lifecycle with authoritative close evidence before terminal verification.
- Solution: `record-live` requires the exact completed agent in the v2 slot ledger; final verification requires its released projection and close evidence containing the persisted output hash.
- Verification state: parent `close_agent` returned the exact completed output for runtime agent `019f80bb-1e34-7c02-9855-9fc342026cc3`; slot `s1` is released; final independent review returned PASS; terminal promotion verification reports all six gates true.
