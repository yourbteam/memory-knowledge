# Work Blockers

Ledger-SHA256: `604d1b9ead8410b12f66c3ec615e048b8c926279142dae40f91345ad8f6f5b40`

This file is generated from `operations/work-memory/events.jsonl`.

## blk-009c8ce9f003444c10d61c2f

- Status: `closed`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `correction-external-repo-root-loss`
- Surface: `work-memory-correction-ledger`
- Symptom: The manifest correction was proven by exact selection but the correction ledger rejected recording it
- Evidence: cmd_correct calls resolve_bundle without the selection repo-roots file and returned missing-repository-root after codex-skills dependencies were declared

## blk-00bb2ceebc4dd6192ab64da2

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/touchpoints.py`
- Symptom: The real source run produced a valid strategy and owner-question manifest, but compose-platform-lock-session-guide blocked because the command-backed guide payload violated the exact grounding contract.
- Evidence: up-run-66394f2cc69e records platform_lock_session_guide_status={status:invalid,issues:[platform_lock_guide_grounding_invalid]}; the phase ledger reason is the same and publication was never reached.

## blk-010279601780b9c2fe9cb4c1

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `verify-correction-bootstrap-guard`
- Surface: `sequence-guard-tests`
- Symptom: Two existing direct-correction guard tests rejected valid relative memory-repository artifact paths.
- Evidence: tests/test_sequence_guard.py: 53 passed, 2 failed with invalid-correction-bootstrap-artifact in the direct work_memory.py correction path.

## blk-016a972d134f32eaffd58e98

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `guard-registered-deploy-run-start`
- Surface: `sequence-guard`
- Symptom: The registered deploy run-start guard omitted the mandatory source reference.
- Evidence: argparse rejected the guard before validation and printed that --source-ref is required.

## blk-018e75ffc4689db389ef6b33

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-test-diagnostic-baseline`
- Surface: `/Users/kamenkamenov/.local/state/kamen-convergence/up-harness-cd-s-002-upgrades-20260714/state.json`
- Symptom: The approved tests baseline update could not atomically write its convergence state file under the sandbox.
- Evidence: tempfile.mkstemp raised PermissionError for the convergence state directory.

## blk-01fb8f61bf3ddba46341a3ec

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-dependency-scope`
- Surface: `operations/sequences/discovery/2026-07-15-unified-research-playbook-v2-trust-reset.dependencies.json`
- Symptom: A concurrent change to tests/test_scoped_git_publish.py invalidated the v2 successor even though scoped publishing is outside the v2 research-playbook evaluation.
- Evidence: The exact current-vs-selected bundle diff contained the two intended v2 replay files plus tests/test_scoped_git_publish.py; no v2 source or evaluator path depends on that test.

## blk-02843a2f775ca97659278bd2

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `sealed-bootstrap-launcher-correction`
- Surface: `scripts/work_memory_bootstrap_launcher.py`
- Symptom: The immutable sealed bootstrap launcher rejected the trust-reset correction before writing because the task active state no longer matches its current classification/selection receipts.
- Evidence: work_memory_bootstrap_launcher.py correct returned exit 4 and active-state-receipt-mismatch; no correction event was appended.

## blk-036a1d3f8e9384ec8df94616

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/platform_decisions.py`
- Symptom: The live canary completed its source re-draft and first owner-decision/evidence continuation, but the canonical platform decision gate remained non-locked.
- Evidence: The command-backed canary exited with platform did not lock; the continuation state contains the exact gate issues and claim usability evidence.

## blk-056a285935402e93ed9804f7

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `/Users/kamenkamenov/united-partners/scripts/run_cd_s_002_upgrade_canary.py`
- Symptom: The first continuation stayed provisional and blocked final composition because the synthetic owner record selected a core-line claim whose generated proof row required a clearance the fixture did not supply.
- Evidence: up-run-bd764c0695f4 platform_decisions_gate issues are required_clearance_missing and public_claim_not_usable for claim-demo-governance-grade; compose-final-strategy-brief then blocked.

## blk-0599ff16677a344d8bb87f7e

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `score-evaluation`
- Surface: `final-v17-comparative-score`
- Symptom: complete-18-record-score-failed-critical-recall-13-of-17-and-planner-pass-every-case-false
- Evidence: current-timeout-after-acceptance-test-missing-and-conflict-archive-retention-versus-pii-deletion-absent-from-v2-material-gaps

## blk-05a905f3cd51821710c0480d

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `guard-registered-deploy-run-start-bundle`
- Surface: `sequence-guard`
- Symptom: The optional nested deploy run-start tried to ground work_memory.py against a registered bundle that intentionally contains only deploy artifacts.
- Evidence: sequence_guard rejected scripts/work_memory.py as outside the selected taggable-api-deploy source bundle; the guarded deploy script itself had already passed.

## blk-063234e3cc282c9cf8934590

- Status: `fixed-awaiting-verification`
- Subject: `discovery-de6c9083-3ed4-5c8a-8976-ef44a67a82a2`
- Step: `document-runtime-placeholder-slot-binding`
- Surface: `convergence-sequence-integration`
- Symptom: Convergence slot lifecycle cannot be followed under sequence guarding because the skills omit predeclared runtime-ID command shapes
- Evidence: sequence_guard _shape_match supports <placeholder>; convergence and sequence skills did not describe using it before spawn

## blk-0650626e15d66f50f203ca11

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `schema-remediation-replay`
- Surface: `research-package-raw-finding-ingress`
- Symptom: captured-malformed-lens-envelopes-enter-trusted-state
- Evidence: final-v4-captured-raw_findings-and-finding_type-shapes-plus-permissive-normalize_raw_findings

## blk-06f9a648d262b8afa1e1cf11

- Status: `superseded`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `restore-gh-auth-visible-code`
- Surface: `github-device-auth`
- Symptom: The browser requests an eight-character device code but the user has no terminal view of the CLI-generated code
- Evidence: The active gh flow emitted its code only inside the agent-owned PTY

## blk-079e153aaafc9926aa6c10c2

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `strategy-contract-fix-baseline`
- Surface: `convergence-baseline-guard`
- Symptom: The convergence guard blocks the confirmed strategy contract edit because its expected hashes predate already-made approved fixes.
- Evidence: guard-baseline reported drift only in scripts, src/up_harness, and tests; docs and workflows matched their expected hashes and Git HEAD/index did not drift.

## blk-080f363bbda43a35924db97d

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/final_strategy.py`
- Symptom: The command-backed canary passed structured draft generation but blocked at compose-final-strategy-brief with an empty phase error.
- Evidence: Live run up-run-e78d789027f9 is blocked at compose-final-strategy-brief; the canonical final_strategy_validation record in its state is the required diagnostic source.

## blk-0824f088e8dcfdb4a7227835

- Status: `non-gap`
- Subject: `discovery-bc73b987-df58-5ef3-9ae4-e8543289023a`
- Step: `transition-command-shape-blocker`
- Surface: `blocker-catalog-cli`
- Symptom: Catalog transition rejected flags described by the blocker-catalog skill
- Evidence: argparse reported unrecognized --solution-summary and --changed-artifact

## blk-089558d0d5b04a4cd63a1dba

- Status: `non-gap`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `create-legacy-workdirs`
- Surface: `scripts/sequence_guard.py`
- Symptom: sequence-guard-rejected-workdir-command
- Evidence: argparse-required-step-and-source-ref

## blk-0a65afd883030d71c00f618d

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `baseline-approval-shell-quoting`
- Surface: `sequence-discovery-log`
- Symptom: Recording the grant-approval command stripped nested JSON quotes and triggered glob expansion
- Evidence: The sequence append failed before changing approval or convergence state

## blk-0a99913e389b4c894128bd65

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `restore-managed`
- Surface: `managed-projection-recovery`
- Symptom: generated-cache-parent-can-be-absent
- Evidence: restore-managed-refused-missing-pycache-parent-before-mutation

## blk-0aadecd689db7f4a04d09dab

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `verify-run`
- Surface: `discovery-command-contract`
- Symptom: guarded-verification-command-cannot-name-all-selected-corrections-atomically
- Evidence: work-memory-transaction-requires-exact-correction-set-at-lines-367-through-370

## blk-0af1c50b1031aeb6891a0bba

- Status: `superseded`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `restore-gh-auth`
- Surface: `sequence-guard`
- Symptom: The guard rejected the documented gh browser-login command
- Evidence: sequence_guard.py returned command-not-grounded-in-selected-document

## blk-0bc83d86cbd25e92c88b43d5

- Status: `open`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `final-v4-requirement-conflict-satisfaction`
- Surface: `requirements-satisfaction-terminal-envelope`
- Symptom: conflict-satisfaction-finding-used-originating-stage-REQUIREMENTS_SATISFACTION
- Evidence: locked-prompt-and-finding-contract-require-originating-stage-RESEARCH

## blk-0bcbc5962dd62d05f376cd66

- Status: `closed`
- Subject: `discovery-0f04c36f-760d-5cd6-aecb-4381765b7dfa`
- Step: `verify-recovery-automation`
- Surface: `tests/test_scoped_git_publish.py`
- Symptom: The isolated recovery test expected a leading porcelain status space that the shared git helper strips.
- Evidence: Runtime recovery succeeded; pytest reported only expected M excluded.txt versus actual stripped M excluded.txt.

## blk-0c551f9a30f8cf4d583644cb

- Status: `non-gap`
- Subject: `discovery-e239c5e0-5bff-58b1-a62f-99f64e686baf`
- Step: `catalog-invalid-spec`
- Surface: `discovery-bootstrap-spec`
- Symptom: Bootstrap rejected failure_handling before creating a run.
- Evidence: First bootstrap exited 2 with invalid-bootstrap-failure-handling; the field was a JSON list but the contract requires one non-empty string.

## blk-0cc194931fe4493f937d47c2

- Status: `non-gap`
- Subject: `discovery-bc73b987-df58-5ef3-9ae4-e8543289023a`
- Step: `record-artifact-provenance-correction`
- Surface: `work-memory-correction-ledger`
- Symptom: Correction recording rejected at least one changed artifact path
- Evidence: work_memory.py correct returned changed-artifact-outside-repository

## blk-0ce64ff33985d5f1913a87c5

- Status: `fixed-awaiting-verification`
- Subject: `discovery-6c9c32b3-939c-54f1-8cff-5bd9758f8821`
- Step: `verify-reset-worker-at-most-once-under-launchd`
- Surface: `launchctl-job-contract`
- Symptom: submitted-one-shot-job-remains-spawn-scheduled-after-successful-exit
- Evidence: launchctl-print-showed-properties-keepalive-runs-4-state-spawn-scheduled-last-exit-code-0

## blk-0d4dec0b648f70201ce730ae

- Status: `superseded`
- Subject: `discovery-782832ed-7fa4-5efe-9765-463303ecd2a2`
- Step: `expand-discovery-dependencies`
- Surface: `scripts/sequence_discovery_log.py`
- Symptom: The canonical set-dependencies helper rejected the supplied dependency array before changing the manifest.
- Evidence: sequence_discovery_log.py returned exactly invalid-dependencies-json for a JSON array of dependency entries.

## blk-0d9e2b0044af3e4b745c92fe

- Status: `closed`
- Subject: `discovery-3393078a-d255-508d-a718-2681b85c4a35`
- Step: `record-complete-command-set`
- Surface: `sequence_discovery_log`
- Symptom: Two planned discovery rows could not be recorded; pipe tokens escaped the command argument
- Evidence: invalid-command-row plus zsh command-not-found for greenfield/preflight/parallel tokens

## blk-0dc4feadc070f3efb02dbcda

- Status: `superseded`
- Subject: `discovery-6c9c32b3-939c-54f1-8cff-5bd9758f8821`
- Step: `schedule-cloned-remote-control-enrollment-reset`
- Surface: `launchd-reset-worker`
- Symptom: chatgpt-repeatedly-quits-and-reopens
- Evidence: user-reported-loop-and-launchd-service-removal-stopped-worker

## blk-104cd4ddbbbfd8469317242d

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `compose-platform-lock-session-guide`
- Symptom: The real gpt-5.5 guide now preserves all owner questions but its option grounding payload does not exactly match the manifest pairs required by the validator.
- Evidence: Harness run up-run-da0f753dddb0 stored platform_lock_guide_grounding_invalid after the question-mismatch correction passed.

## blk-10adf26e004bba44f735495a

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `initialize-candidate`
- Surface: `sequence-discovery`
- Symptom: The discovery path does not authorize the mandatory init_skill.py scaffold command.
- Evidence: The skill-creator contract requires init_skill.py for a new skill; no matching command exists in the selected discovery document.

## blk-110e4e87393edd3855a45cbc

- Status: `open`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `final-v4-current-runtime-satisfaction`
- Surface: `requirements-satisfaction-terminal-envelope`
- Symptom: current-satisfaction-returned-raw_findings-envelope-instead-of-findings
- Evidence: locked-prompt-requires-exact-verdict-findings-object-and-complete-finding-record

## blk-12c1ccdc00f12a3ba0627521

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/platform_decisions.py`
- Symptom: The live canary produced a valid structured brief whose core-line question offered no option equal to a proof-manifest claim, so no discipline-safe owner core-line decision could be constructed.
- Evidence: The command-backed canary exited with core-line options do not bind exactly one proof claim after completing source generation.

## blk-139ea98a01bb530b1824487e

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `final-strategy-unit-verification`
- Surface: `tests/unit/test_final_strategy.py`
- Symptom: The locked final-strategy unit vector returned invalid instead of valid because its draft question section failed the canonical parser.
- Evidence: test_locked_roadmap_uses_supplied_values_and_verified_proof failed with final validation issue beginning owner_questions_invalid.

## blk-147e5a540edd6d8e3114a736

- Status: `fixed-awaiting-verification`
- Subject: `discovery-f4cf2e8f-5fd3-5fc0-9b2a-54e3c9ad8ccd`
- Step: `activate-sequence-guard`
- Surface: `sequence-guard`
- Symptom: sequence_guard activation rejects the current task because the recorded directive read SHA is stale
- Evidence: activation output: directive read state is stale because directives SHA changed

## blk-1606b8b40b267413a9efedb5

- Status: `non-gap`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `final-v3-future-internal-lens-timeout`
- Surface: `/private/tmp/research-playbook-v2-eval-20260715-final-v3/v2-work/future-system/internal-readiness-output.json`
- Symptom: The future-system INTERNAL_READINESS agent remained running for over five minutes and wrote no output file.
- Evidence: Agent 019f6535-112e-7080-985d-90cbd93437f0 returned repeated wait timeouts across more than five minutes; expected internal-readiness-output.json is absent.

## blk-1648042967067975b9dc380d

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `blocker-catalog-command-guard`
- Surface: `scripts/sequence_guard.py`
- Symptom: The sequence guard rejected the blocker-catalog validation because the invocation omitted --step and --source-ref.
- Evidence: Argparse reported: the following arguments are required: --step, --source-ref.

## blk-170d08987d47896e428af8ed

- Status: `non-gap`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `correction-recording`
- Surface: `work-memory-correction-lifecycle`
- Symptom: The canonical correction recorder rejected the approved typed-answer artifact set before it could bind the fix to the original evaluator blocker.
- Evidence: work_memory.py correct exited 3 with correction-artifact-drift-mismatch for blocker blk-c94e16da740af387f954abdd; no tests or rerun followed.

## blk-17237a0f4e911444c1c9e845

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-source-tests-baseline`
- Surface: `scripts/sequence_guard.py`
- Symptom: The sequence guard rejected atomic source/tests baseline advancement because the selected source bundle no longer matches current shared operational files.
- Evidence: sequence_guard returned {error: stale-source-bundle, ok: false} before dispatching convergence_state.py.

## blk-17488b4b91687fc9020ef8ce

- Status: `superseded`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `guard-research-edit`
- Surface: `convergence-baseline`
- Symptom: The baseline guard sees the parent-authored research document hash as drift.
- Evidence: Only docs/gf-n3-resume-durability-research.md changed from expected 800b4f... to actual f2605e...; every other allowed path hash matches.

## blk-1748ae1078707861f452c473

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `final-v4-lens-schema-boundary`
- Surface: `research-package-raw-finding-ingress`
- Symptom: repeated-lens-agents-emitted-wrong-finding-field-shapes
- Evidence: research_package-normalize_raw_findings-only-calls-canonical_json-and-conflict-retry-used-finding_type-instead-of-type

## blk-181ce7d8121a02f705556331

- Status: `open`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `controlled-topic-strategy-state-preservation`
- Surface: `src/up_harness/engine/runner.py`
- Symptom: the source workflow completed policy preparation and join but exposed zero controlled topics after strategy composition
- Evidence: same-path integration test progressed beyond strategy composition then observed len(controlled_topics) equal to zero

## blk-18da244547076d574b8e92c1

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `record-owner-question-contract-correction`
- Surface: `work-memory-control`
- Symptom: The sequence guard rejected a direct work_memory.py correction command in correction-bootstrap mode.
- Evidence: sequence_guard.py returned invalid-correction-bootstrap-command before the correction command ran.

## blk-192048d5b4826bf16f7a61f1

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `transition-corrected-blocker`
- Surface: `correction-bootstrap-dependency-bundle`
- Symptom: The prescribed post-correction transition cannot be guarded because blocker_catalog.py is absent from the predecessor selected bundle.
- Evidence: sequence_guard.py returned invalid-correction-bootstrap-source after the exact transition command was added and correction recording succeeded.

## blk-1964e23016a13f5237b9944c

- Status: `superseded`
- Subject: `discovery-candidate-reconciliation`
- Step: `review-rerun`
- Surface: `scripts/discovery_candidate_reconciliation.py`
- Symptom: A second execute-rolling invocation using the same output directory overwrites attempt-1.json but then encounters the prior checkpoint with a different manifest hash.
- Evidence: cmd_execute_rolling writes output_dir/attempt-1.json on every invocation; audit generated_at_utc changes the manifest hash; _load_checkpoint rejects the retained attempt-1 checkpoint as checkpoint-manifest-mismatch.

## blk-1975f40a029b3a7885de0493

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `test-focused`
- Surface: `discovery-sequence-pytest-command`
- Symptom: The correction-bound verification sequence prescribes direct uv pytest, but the repository contract requires every memory-knowledge pytest run to use scripts/run_pytest.sh.
- Evidence: Discovery test-focused row calls uv run --extra dev pytest; skills/write-code-playbook/SKILL.md requires scripts/run_pytest.sh and forbids direct uv/pytest invocation.

## blk-19f5420d72778a0233bd0442

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `carried-correction-selection`
- Surface: `work-memory-controller`
- Symptom: A still-active correction cannot be selected after an intermediate failed verification run, and later replay compares raw correction hashes with semantic source-bundle hashes.
- Evidence: The preserved 2026-07-12 ledger contains the first valid carried correction followed by an intermediate run; the trusted controller enforces direct predecessor lineage and its draft artifact check compared incompatible hash representations.

## blk-1a0a6bfde85dd9a69c7be856

- Status: `fixed-awaiting-verification`
- Subject: `discovery-a08426bf-f240-5341-850d-29c397ea347c`
- Step: `init convergence state`
- Surface: `convergence-state`
- Symptom: state initialization rejected the recorded --state flag
- Evidence: convergence_state.py init --help shows positional state argument

## blk-1a151c7dd05870d0e8f57c60

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `convergence-state-inspection`
- Surface: `/Users/kamenkamenov/.codex/skills/_shared/convergence_state.py`
- Symptom: State inspection command rejected the nonexistent show subcommand.
- Evidence: argparse lists status, not show, as the supported read command.

## blk-1af5226c2775a0c65e1264e6

- Status: `open`
- Subject: `discovery-6c9c32b3-939c-54f1-8cff-5bd9758f8821`
- Step: `verify-reset-worker-unit-test`
- Surface: `python-unittest`
- Symptom: reset-worker-test-did-not-start
- Evidence: python3-m-unittest-rejected-filesystem-path-as-module-name

## blk-1b24a5707c20a0937f146399

- Status: `superseded`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `spawn-and-bind-research-internal`
- Surface: `playbook-convergence-loop-slot-lifecycle`
- Symptom: The exact bind-agent command cannot be guarded before spawn because the agent ID is runtime-generated, while binding must happen immediately after spawn
- Evidence: playbook-convergence-loop requires immediate bind-agent; sequence_guard requires exact command grounded in the selected immutable bundle

## blk-1c2627343d77a52f371f5121

- Status: `superseded`
- Subject: `discovery-promotion-lifecycle`
- Step: `protected-correct`
- Surface: `scripts/work_memory_bootstrap_launcher.py`
- Symptom: The sealed bootstrap refused the generated protected correction command before recording the controller fix.
- Evidence: discovery_promotion_lifecycle.py emitted a content-bound correction id and exact two-file artifact list; work_memory_bootstrap_launcher.py returned bootstrap-command-not-grounded.

## blk-1da9d4977b4f37968d8b751b

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `overlapping-correction-lifecycle`
- Surface: `work-memory-controller`
- Symptom: later-preserving-revision-cannot-supersede-all-prior-corrections-to-same-artifact
- Evidence: selection-rejects-old-artifact-hash-and-recovery-rejects-nonlegacy-fixed-blocker

## blk-1df6f3935b7b0c0d5b9c4046

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `focused-mcp-freshness-test`
- Surface: `tests/integration/test_mcp_stdio.py`
- Symptom: the new decision-rerun test inherited two trailing assertions from the preceding history test and fails with NameError
- Evidence: bundled unittest points to test_mcp_stdio.py line 361; filtered is local to the preceding test

## blk-1e60d1e3a7cb0715cb2b9f53

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/strategy_brief.py`
- Symptom: The final command-backed canary failed in compose-llm-strategy-brief with owner_question_manifest_invalid:4 after earlier runs failed different owner-manifest fields.
- Evidence: /tmp/up-cd-s-002-upgrade-canary/canary-failure.json and run up-run-3adc5b8cd0bf record deterministic rejection of structured owner-question manifest row 4.

## blk-1eb4cec7ca00caded9403f3e

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `quick-validate-candidate`
- Surface: `skill-creator-runtime`
- Symptom: The canonical quick_validate.py cannot start.
- Evidence: System Python raised ModuleNotFoundError: No module named yaml.

## blk-1f1e5f4e40827f9918b43438

- Status: `non-gap`
- Subject: `discovery-e4cdc863-c807-565a-baba-14d826c9df90`
- Step: `transition-stale-bundle-blocker-verified`
- Surface: `blocker_catalog status transition`
- Symptom: The required explicit transition to verified was rejected after a successful same-path verification event
- Evidence: blocker_catalog.py transition returned {error: invalid-blocker-status-transition, ok: false} for blk-5f0381d736e14801b802be9c using verification event 98df96d3-92b6-4dbb-b5bd-477a1ba9d553

## blk-1f2780e54e553406ea2d158f

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `register-full-verification-commands`
- Surface: `operations/sequences/discovery/2026-07-14-up-harness-cd-s-002-live-verification.dependencies.json`
- Symptom: The sequence correction rejected the newly registered verify_harness command because its executable script is absent from the dependency manifest.
- Evidence: work_memory.py correct returned executable-outside-manifest::scripts/verify_harness.py.

## blk-1f4cb7b82439f59a6c162ca1

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `sealed-correction-finalization`
- Surface: `scripts/work_memory_bootstrap.py`
- Symptom: The sealed bootstrap cannot record a later correction on a run that already contains a passed same-path verification.
- Evidence: bootstrap cmd_correct forces finalize_failed_run=True; work_memory cmd_correct emits run_closed verification_quality=none; lifecycle rejected this because run 153e56bd already contains verification 3cc1d03c with quality same-path.

## blk-20cba16bfef4306bd02dbda2

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `bind-research-internal-slot`
- Surface: `agent_slot_ledger`
- Symptom: bind-agent --label research-internal-1 matches released s1 and reserved s2
- Evidence: agent_slot_ledger returned selector matched 2 slots after acquire returned s2

## blk-2104690038466a1318cd108c

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-structured-prompt-and-fixture-fix`
- Surface: `sequence command registry`
- Symptom: The guard rejected the required atomic source-plus-tests expected-state command.
- Evidence: sequence_guard returned command-not-grounded-in-selected-document before accept-baseline executed.

## blk-2165c0c033c5b4cae015ee1e

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `record-combined-command-registry-correction`
- Surface: `scripts/work_memory.py`
- Symptom: A combined correction record could not represent simultaneous discovery-log and dependency-manifest drift.
- Evidence: work_memory.py correct returned correction-artifact-drift-mismatch after both changed artifacts were supplied.

## blk-21b2da2a8e50279db192754d

- Status: `closed`
- Subject: `commit-push-main`
- Step: `independent-review-proof-surface`
- Surface: `commit-push-main`
- Symptom: The registered verification command executes three test files while the sealed dependency bundle includes only one.
- Evidence: REV-COMMIT-PUSH-001 independently confirmed tests/test_scoped_git_publish.py and tests/test_sequence_promote.py are omitted; scripts/sequence_promote.py is their directly executed helper.

## blk-226c908efabad4d1392d67d9

- Status: `closed`
- Subject: `discovery-12a4d13f-4852-5fc4-8106-aebb5efbec71`
- Step: `edit-command-shape`
- Surface: `v14-correction-bootstrap-contract`
- Symptom: The v14 stale-bundle bootstrap rejects the exact three-artifact correction because its selected discovery document declares only one, two, four, five, and eleven-artifact shapes.
- Evidence: The guarded wrapper command for the current discovery document, sequence guard, and sequence guard test returned command-not-grounded-in-selected-document before any correction ran.

## blk-234f25d500b05ba32c9dcd9a

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `compose-platform-lock-session-guide`
- Symptom: The real gpt-5.5 run passed structured strategy composition and stopped with the new platform-lock session-guide phase blocked.
- Evidence: Harness run up-run-ab4991abdff9 returned overall blocked with compose-platform-lock-session-guide status blocked and no phase error.

## blk-23c06fb0d9e360287293d158

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `inspect-run-summary`
- Surface: `sequence-guard`
- Symptom: The active discovery run cannot guard its own work-memory summary or blocker-catalog command.
- Evidence: sequence_guard returned source-ref-outside-selected-bundle and command-not-grounded-in-selected-document.

## blk-2494393a7c1adcc3a8d485c7

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `final-research-verification`
- Surface: `work_memory_verification`
- Symptom: aggregate verification omitted the successor correction binding
- Evidence: work_memory verify returned clean-verification-after-correction

## blk-24eb24daf377058df643288d

- Status: `non-gap`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `record-evaluation`
- Surface: `sequence-guard`
- Symptom: The guard rejected the repository-root evaluator command before recording a completed legacy output.
- Evidence: The discovery row uses python3 evaluate_research_playbook_v2.py from scripts/; the concrete run uses python3 scripts/evaluate_research_playbook_v2.py from repository root.

## blk-25226aa23e317a9df6357c04

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `restore-managed`
- Surface: `codex-managed-skill-installation`
- Symptom: restored-live-projection-changed-after-success
- Evidence: recovery-e5cb-backup-34b6-live-c4a0-prove-third-version

## blk-25dc77ab0a773cba67eb8174

- Status: `non-gap`
- Subject: `discovery-f4cf2e8f-5fd3-5fc0-9b2a-54e3c9ad8ccd`
- Step: `refine-semantic-comparator`
- Surface: `temporary-analysis-script`
- Symptom: semantic comparison refinement patch could not find the expected row-diff condition
- Evidence: apply_patch verification failed for the expected row comparison lines

## blk-25f7d99d99453b0dfd68c73d

- Status: `closed`
- Subject: `discovery-e4cdc863-c807-565a-baba-14d826c9df90`
- Step: `read-complete-numbered-inputs`
- Surface: `discovery command encoding`
- Symptom: The registered full-read command would print literal backslash-n separators instead of one numbered source line per output line
- Evidence: The selected discovery document stores printf format %s:%d:%s\\n, which AWK interprets as a literal escaped backslash followed by n

## blk-263f4b2d4f9eb32be4ba5b7a

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `plan-critic-slot-state`
- Surface: `agent-slot-ledger`
- Symptom: Critic slot s9 remained reserved because the reused agent id was already bound to an earlier closed slot
- Evidence: bind-agent returned agent id already bound and mark-completed then rejected s9 as not running

## blk-2706ea770b9cc42b01af4385

- Status: `non-gap`
- Subject: `discovery-f4cf2e8f-5fd3-5fc0-9b2a-54e3c9ad8ccd`
- Step: `read-spreadsheet-skill-references`
- Surface: `spreadsheet-skill`
- Symptom: API_QUICK_START.md and style_guidelines.md named by the spreadsheet skill are absent from its directory
- Evidence: wc returned No such file or directory for both named paths under the skill folder

## blk-29e418ee4467ee87b73fdafc

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `integrated-upgrade-workflow-test`
- Surface: `src/up_harness/engine/runner.py command preflight`
- Symptom: A redraft run with the approved constructor-injected fixture executor blocks before any phase.
- Evidence: _preflight_command_executor_block checks only UP_HARNESS_AGENT_COMMAND; _role_executor_for_run correctly supports role_executor_factory.

## blk-2a1f5c824e2aadde77b0ccfc

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `v2-emit-package`
- Surface: `research_package`
- Symptom: controller-allows-hidden-answer-aliases-unbound-terminal-retargeting-missing-scope-id-and-dangling-evidence-ids
- Evidence: independent-audit-confirmed-four-contract-gaps-against-evaluator-lines-1031-through-1042

## blk-2a4516f299e85c7311a2d096

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `accept-authorized-parent-edits`
- Surface: `convergence_state`
- Symptom: Post-edit verification cannot start because the baseline still contains the pre-edit hashes for the authorized research and audit artifacts.
- Evidence: guard-baseline returned BLOCKED and showed only allowed-path drift for hypothesis-validation-protocol-research.md and its gap-audit.md.

## blk-2ade3deacde01a5751eb052a

- Status: `closed`
- Subject: `discovery-6a9f4f62-798e-5c7c-8bbe-8738a523d1d1`
- Step: `open-blocker`
- Surface: `sequence-contract`
- Symptom: wrong-subject-binding-accepted-by-guard
- Evidence: product-run-returned-subject-run-mismatch

## blk-2b96f570c4b12dd76a7b32eb

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `run-id-bootstrap`
- Surface: `work-memory-run-start`
- Symptom: Run start rejected a descriptive slug passed as run id
- Evidence: work_memory.py run-start returned invalid-run-id; source validation requires UUID

## blk-2b9fd4c172625b52eabe38b5

- Status: `closed`
- Subject: `discovery-87df1262-3559-590e-9102-27b64fd3c6ad`
- Step: `install-both-clients`
- Surface: `managed-skill-installer`
- Symptom: The dual-client installer refused before changing either managed root.
- Evidence: working-agreement/install-skills.sh returned: --target both requires --reconciliation.

## blk-2c3cc9cbd1504d955fdd2adb

- Status: `non-gap`
- Subject: `discovery-6c9c32b3-939c-54f1-8cff-5bd9758f8821`
- Step: `start-successor-diagnostic-run`
- Surface: `work-memory`
- Symptom: fresh-diagnostic-run-could-not-start
- Evidence: work_memory.py-run-start-returned-PermissionError

## blk-2cdef6071b36075203d13c85

- Status: `non-gap`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `select-verification-sequence`
- Surface: `work-memory-routing`
- Symptom: The requested registered verification sequence could not be selected.
- Evidence: work_memory.py select returned sequence-not-valid-for-operation; registry contains no v2-regression-tests row.

## blk-2d4fe08c2f2b0c43df307887

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `superseded-correction-transition-command-contract`
- Surface: `sequence-discovery-contract`
- Symptom: overlapping-document-correction-cannot-be-terminally-superseded-through-discovery-command
- Evidence: older-correction-eee2-hash-is-replaced-by-latest-preserving-document-revision

## blk-2e65432f8ed08537a4557b65

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `v2-emit-package`
- Surface: `sequence-command-contract`
- Symptom: The reusable discovery command cannot emit a controller-valid package because it omits the required planner-readiness input.
- Evidence: research_package.py emit-package --help requires --planner-readiness; the selected discovery row has no such argument.

## blk-2ec0005e9c80d950709e1f75

- Status: `open`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `plan-verifier-4-run-start`
- Surface: `memory-knowledge work_memory run-start`
- Symptom: The delegated plan verifier cannot create its own guarded run receipt after successful activation.
- Evidence: work_memory.py run-start returned PermissionError for task durable-resume-plan-verify-iteration-4

## blk-2f953da000b0520e5bcfacbb

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `release-coverage-slot`
- Surface: `sequence_guard`
- Symptom: The guard rejected release of closed coverage slot s83 because the selected source bundle is stale
- Evidence: sequence_guard.py guard returned stale-source-bundle after mark-closed succeeded; slot s83 is closed and not released

## blk-30424585bd80d1b3a201f07d

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-init-state`
- Surface: `selected-source-bundle`
- Symptom: The active v7 guard rejected the first case initialization before state creation.
- Evidence: sequence_guard.py guard returned stale-source-bundle for the selected v7 bundle 996165f2284060c5ea9259a896dbb3653278365e068299cacd1511b97d8e8a8a31 before running research_package.py init.

## blk-30b441c2d5efd2b0efcd4adb

- Status: `closed`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `verify-fresh-gh-auth`
- Surface: `github-auth`
- Symptom: A clean OAuth login succeeds but the new credential is immediately rejected by gh auth status
- Evidence: gh auth logout succeeded; fresh browser OAuth succeeded; immediate same-path gh auth status still exited 1

## blk-30e56040d0248a28c0bce2dd

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `work-memory-reproduction-discovery-shape`
- Surface: `focused-work-memory-reproduction`
- Symptom: The focused reproduction stopped before exercising the missing repository-root path
- Evidence: resolve_bundle rejected the test discovery fixture because mandatory discovery sections were absent

## blk-30f1bf296a75b6afdf6473de

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `final-live-canary`
- Surface: `/Users/kamenkamenov/united-partners/scripts/run_cd_s_002_upgrade_canary.py`
- Symptom: The live canary expected a locked platform but its synthetic owner decision made claim-resilience-high-level public while the supplied evidence made only qaf-913f42e3bf30bd90 public-usable.
- Evidence: up-run-cb8c681814bf completed 35 phases; platform_decisions_gate returned provisional with public_claim_not_usable, claim-resilience-high-level public_usable=false, and qaf-913f42e3bf30bd90 public_usable=true.

## blk-30fc6d2e072f46cf732eefc2

- Status: `fixed-awaiting-verification`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `run-start`
- Surface: `work-memory-control-plane`
- Symptom: verifier-could-not-create-required-run-ledger
- Evidence: run-start returned PermissionError twice; parent same command succeeded with authorized write

## blk-31d120c2fdfa5884e67b10ab

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `record-evaluation`
- Surface: `planner-handoff-evaluator`
- Symptom: planner-input-is-recorded-v2-evaluation-json-not-six-file-research-package
- Evidence: matrix_binds_planner_to_one_v2_output_hash_while_planner_handoff_contract_requires_manifest_research_requirements_evidence_findings_and_handoff_files

## blk-31e6cfd7cf5bfadd422464b9

- Status: `superseded`
- Subject: `discovery-promotion-lifecycle`
- Step: `independent-review`
- Surface: `discovery-promotion-lifecycle`
- Symptom: Independent review proved registered failures can bypass correction, interrupted correction is not resumable, cross-repository corrections are rejected, and commit-push proof omits two executed tests.
- Evidence: Reviewer and critic independently classified REV-LIFECYCLE-001, REV-LIFECYCLE-002, REV-LIFECYCLE-003, and REV-COMMIT-PUSH-001 as FIX NOW.

## blk-348b191e37b8d5c1a1f4964c

- Status: `closed`
- Subject: `discovery-candidate-reconciliation`
- Step: `validate-dispositions`
- Surface: `scripts/discovery_candidate_reconciliation.py`
- Symptom: Manifest validation accepts the same HEAD and candidate path list even when an uncommitted candidate log changes or the sequence registry changes after audit.
- Evidence: The schema stores candidate_set_hash and registry_hash, but validate_manifest checks only HEAD, path list, and path-list hash; it never recomputes per-candidate bytes or registry_hash.

## blk-34d433bae9511f2ea2686a1a

- Status: `non-gap`
- Subject: `discovery-e4cdc863-c807-565a-baba-14d826c9df90`
- Step: `repair-stale-bundle-status-order`
- Surface: `blocker_catalog terminal-run enforcement`
- Symptom: The omitted fixed-awaiting-verification transition cannot be added to the original run after it was closed
- Evidence: blocker_catalog.py transition returned {error: event-after-terminal, ok: false} when moving blk-5f0381d736e14801b802be9c from open using original run 26577984-bdcf-447a-9091-c61cef322024

## blk-3565d2fc254f73e4e6e981e1

- Status: `open`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `controlled-topic-source-workflow-test`
- Surface: `tests/integration/test_command_workflow.py`
- Symptom: a redraft source carrying one FLAG policy ended failed before the continuation could run
- Evidence: test_controlled_policy_is_preserved_into_locked_qna_continuation expected completed but observed failed

## blk-36882cb3337256a01fe88a55

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-idempotent-adjudication-replay`
- Surface: `skills/research-playbook-v2/scripts/research_package.py`
- Symptom: Existing adjudication replay returns ADJUDICATION_ALREADY_RECORDED without recomputing a persisted verdict created by the prior controller.
- Evidence: Current, mixed, and scope states retain pre-fix IN_PROGRESS/BLOCKED verdicts even though their immutable adjudications are valid under the corrected disposition-driven evaluation.

## blk-369d6d3ac0069a2dd91f0b90

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-canary-script-baseline`
- Surface: `/Users/kamenkamenov/.local/state/kamen-convergence/up-harness-cd-s-002-upgrades-20260714/state.json`
- Symptom: convergence accept-baseline rejected a scripts-only advance because another authorized path also differs from expected state
- Evidence: accept-baseline returned: an authorized path outside the declared change set drifted

## blk-370041ea4cabe0295e3669a3

- Status: `non-gap`
- Subject: `discovery-e239c5e0-5bff-58b1-a62f-99f64e686baf`
- Step: `catalog-prerun-deadlock`
- Surface: `blocker-catalog-bootstrap`
- Symptom: The blocker catalog helper rejected a blocker that occurred before bootstrap had created its required run_started event.
- Evidence: blocker_catalog.py open exited 3 with run-not-found after the first bootstrap validation failure; successful bootstrap supplied the run identity used here. Two later script-source guard attempts also proved blocker_catalog.py is not automatically selected as a trust anchor.

## blk-3709a6c0c65f62629fea1282

- Status: `non-gap`
- Subject: `discovery-e78611ed-2903-5b35-9fa2-142b91bcebc3`
- Step: `validate-agentic-trading`
- Surface: `agentic-trading-test-suite`
- Symptom: The full agentic-trading suite produced EXIT for CLSK:verdict while TestGraphBuilder.test_c6_verdict_value requires MONITOR.
- Evidence: uv run pytest: 1 failed, 807 passed; tests/test_graph.py:375 asserted v[0] == MONITOR but actual was EXIT.

## blk-370bea2272786caf34525347

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `inspect-blocker-ledger-files`
- Surface: `shell-expansion`
- Symptom: A read-only ledger inspection command stopped before rg because zsh expanded a nonexistent operations/events/*.jsonl glob.
- Evidence: zsh:1: no matches found: operations/events/*.jsonl

## blk-37575ef28f83a55bd0433d9a

- Status: `open`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `research-gap-2-stable-boundary`
- Surface: `cross-repository-task-persistence`
- Symptom: Reused task-universe rows cannot be reconciled because memory-knowledge exposes create_task but no general planning-task update tool
- Evidence: memory-knowledge server.py:4651-4721 and admin/planning.py:417-447 only insert new task UUID rows; workflow-orch feature_task_universe.py:149-247 reuses without updating

## blk-38144e343c015add1cbec812

- Status: `superseded`
- Subject: `discovery-promotion-lifecycle`
- Step: `registered-activation`
- Surface: `discovery-promotion-lifecycle`
- Symptom: Registered verification selected the sequence but attempted activation by retired sequence ID.
- Evidence: The controller received activation-sequence-id-retired:run-work_memory-select-then-pass-selected-document after successful promotion.

## blk-3b66c303f1d339987b9de43e

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `successor-dependency-removal`
- Surface: `scripts/work_memory.py`
- Symptom: A correction that intentionally removes an unrelated dependency cannot be selected as a successor because validation requires the removed artifact to remain in the new bundle.
- Evidence: Correction 63d6cdf4 recorded exact transition 793d9fee to 7823d634 and named the manifest plus removed tests/test_scoped_git_publish.py; successor validation rejected the removed test as outside bundle.

## blk-3cae6fd88843a16fb572ee5b

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-executor-baseline`
- Surface: `convergence-state`
- Symptom: Sequential source baseline advancement is rejected while the approved script edit remains unaccepted.
- Evidence: accept-baseline with changed-path src/up_harness returned authorized path outside the declared change set drifted.

## blk-3ce1c7326b935eeed5407bb5

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `final-evaluation-agent-spawn`
- Surface: `multi-agent-runtime`
- Symptom: fresh-final-executions-did-not-return-runtime-agent-ids
- Evidence: eight-request-Promise-all-returned-agent-thread-limit-reached

## blk-3d3a6824bbea9c6033c28fe9

- Status: `closed`
- Subject: `discovery-promotion-lifecycle`
- Step: `protected-terminal-replacement`
- Surface: `lifecycle-controller-bootstrap-routing`
- Symptom: The complete correction drift includes protected trust anchors, but the predecessor activation snapshot predates the verified terminal-replacement contract.
- Evidence: Exact drift is discovery doc, discovery manifest, helper, helper test, work_memory.py, and work_memory_bootstrap.py; the old task activation sealed pre-contract controller hashes while current registered lifecycle run 957da562-b757-4390-b209-cda40d68cf05 passed 159 tests.

## blk-3dd4136f89ebaa69ef53c38e

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `validate-captured-guide-payload`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/touchpoints.py`
- Symptom: Three guide correction attempts received only platform_lock_guide_grounding_invalid even though the payload has dozens of independently validated quote and structural fields.
- Evidence: The live up-run-87ba98207ae2 exhausted all three attempts with the same generic reason; an offline exact-substring audit of the later captured payload found no invalid evidence quote, confirming that failures can move between fields while retaining an indistinguishable diagnostic.

## blk-3e14bd2b2f6f6910231fba26

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `compose-llm-strategy-brief`
- Symptom: The real gpt-5.5 CD-S-002 canary stopped in compose-llm-strategy-brief because the structured proof manifest did not satisfy the runtime contract.
- Evidence: Harness run up-run-7d46e4627fc6 returned phase compose-llm-strategy-brief status failed and error proof_manifest_invalid.

## blk-3e7a70df538ca01016710375

- Status: `non-gap`
- Subject: `discovery-bc73b987-df58-5ef3-9ae4-e8543289023a`
- Step: `terminalize-fixed-awaiting-command-shape`
- Surface: `blocker-catalog-lifecycle`
- Symptom: Direct fixed-awaiting-verification to non-gap transition was rejected
- Evidence: blocker_catalog.py returned invalid-blocker-status-transition

## blk-3f797e3f5fa8eece40757d76

- Status: `non-gap`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `focused-suite-node-selection`
- Surface: `tests/test_work_memory.py`
- Symptom: A focused pytest command selected the correction-bootstrap test from the wrong module and collected zero tests.
- Evidence: pytest reported not found under tests/test_work_memory.py and exited 4 before collection.

## blk-3f94234308fcfebb048becc4

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `repair-live-owner-question-contract`
- Surface: `compose-llm-strategy-brief`
- Symptom: The clean before-state structured strategy prompt does not state the strict owner-question list grammar that the downstream validator enforces.
- Evidence: Live run up-run-87d9d0de034b failed owner_questions_invalid_line:106; source inspection proves the producer prompt omits the canonical list syntax.

## blk-3fb8a9cf220a4d11f9f79238

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `verify-final-strategy`
- Surface: `scripts/sequence_guard.py`
- Symptom: The guard rejected one unittest command containing three target tokens.
- Evidence: The discovery row records unittest <targets> as one placeholder token; the same single-target shape previously passed.

## blk-40488ff90594764f3846303d

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `current-runtime-lens-round-1`
- Surface: `research-playbook-v2-hash-contract`
- Symptom: Independent lenses block because candidate/envelope canonical object hashes differ from the SHA256 of their JSON files and the role contract does not define the hash domain.
- Evidence: INTERNAL_READINESS and REQUIREMENTS_SATISFACTION independently reported candidate file b8da0a44 versus declared ab47703f and envelope file dad48ccc versus declared af7072eb; both stopped rather than assess unverified inputs.

## blk-40ab28e6c972d0e250143be4

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `restore-correction-bundle`
- Surface: `work-memory-selection`
- Symptom: The active correction receipt omits one changed UP test and includes unrelated selected-controller/discovery drift.
- Evidence: Independent remediation assessment found tests/unit/test_strategy_brief_prompt.py absent from the dependency manifest and unrelated drift in scripts/work_memory.py plus the discovery document.

## blk-40b4a227f019ec7882f591e4

- Status: `fixed-awaiting-verification`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `reconcile-third-artifact-revision`
- Surface: `convergence-state-artifact-lineage`
- Symptom: Cycle 4 coverage audit reconciliation fails with artifact has a different live supersession
- Evidence: existing Cycle 1 artifact points to Cycle 3; one-pass loop validates that pointer before repointing Cycle 3 to Cycle 4

## blk-40eda9272e80b63fc13005cc

- Status: `closed`
- Subject: `discovery-223a62bb-62d5-5004-a1b6-cedb69d65585`
- Step: `adjudication`
- Surface: `blind-fixture`
- Symptom: planner-must-invent-future-boundary
- Evidence: /private/tmp/research-playbook-v2-eval-20260715-final-v7/v15-unrecorded-adjudication/mixed-maturity/adjudication-output.json

## blk-415d303e1ee7a936686d098c

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `record-final-strategy-correction`
- Surface: `work-memory-correction-bundle`
- Symptom: The work-memory ledger rejected the final-strategy producer correction because final_strategy.py is not in the selected UP dependency bundle, although its focused test is.
- Evidence: work_memory.py correct returned correction-artifact-drift-mismatch for final_strategy.py plus test_final_strategy.py; the selected dependency manifest contains only the test path.

## blk-4269e3b7cb8ed9c13ee456d7

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `research-inventory-rerun`
- Surface: `sequence_guard`
- Symptom: sequence_guard rejected the repository inspection command before execution
- Evidence: guard usage error: required --step, --source-ref, and --task-id were omitted

## blk-4286396929b5fae000d04032

- Status: `closed`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `completed-state-historical-artifact-drift`
- Surface: `convergence-state-check`
- Symptom: The completed convergence state fails integrity because four early stage records reference mutable research and plan artifact identities.
- Evidence: check reported drift for plan-critic:1:1 artifact plan-critic:884b2e24c4f7, plan-verifier:1:1 artifact plan-verifier:884b2e24c4f7, and research-readiness attempts 1 and 2 artifact research-readiness:92622d01ecd3.

## blk-431250ed4ee0dce9f9e221bc

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `implementation-baseline-guard`
- Surface: `united-partners/src-and-tests`
- Symptom: guard-baseline reports unexpected src/up_harness and tests working hashes before the next edit
- Evidence: expected src 743f0fab/tests 7be1ec91; actual src 3e94580d/tests 74a7cba6; docs/scripts/workflows unchanged

## blk-43a7d8044d3be3dcdb6f7642

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-executor-baseline`
- Surface: `convergence-state`
- Symptom: The convergence state rejected expected-state advancement for approved executor edits.
- Evidence: accept-baseline rejected src as lacking a matching path approval, then scripts as drift outside the declared change set.

## blk-44599b6976b59b1f17db1443

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `blind-planner-evaluation`
- Surface: `research-playbook-v2-planner-handoff-readiness`
- Symptom: packages-reported-terminal-pass-but-current-missing-evidence-and-conflict-planners-could-not-close-without-invention
- Evidence: blind-planners-identified-missing-code-test-anchors-evidence-acquisition-route-and-named-approval-owner

## blk-449400a4c2d00ece71d97b45

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `ground-cross-repository-correction-command`
- Surface: `discovery-command-registry`
- Symptom: The repaired guard rejected the exact two-file correction because the selected discovery document has no matching direct-correction shape.
- Evidence: sequence_guard.py returned command-not-grounded-in-selected-document before correction recording.

## blk-4520c56ce6e059950345a694

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-core-attempt-input-extraction`
- Surface: `temporary-evaluation-state-query`
- Symptom: core-attempt-input-query-failed-before-recording
- Evidence: jq-reported-Cannot-index-object-with-number-for-all-six-state-files

## blk-452a57aab253846fde06993a

- Status: `non-gap`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `v2-record-candidate`
- Surface: `bounded-v2-workdir`
- Symptom: The controller could not record the first candidate because the new run directory lacked evidence-availability.json.
- Evidence: record-candidate returned INVALID_OPERATION with Errno 2 for the exact new-run evidence-availability path; no candidate was recorded.

## blk-4578e027d32ae1aa65cd84da

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `slot-lifecycle-command-guard`
- Surface: `sequence_guard`
- Symptom: The guard rejected the full slot lifecycle command because the discovery log stored only a shortened placeholder form.
- Evidence: sequence_guard returned command-not-grounded-in-selected-document for mark-closed and release; both commands then executed because the orchestration loop failed to stop after the guard rejection.

## blk-45c7753ddfaa89af3f1eda61

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-adjudication`
- Surface: `research-playbook-v2-maturity-adjudication`
- Symptom: future-system-runtime-proof-absence-survived-as-material-planning-gap
- Evidence: mixed-maturity-finding-only-restates-frozen-future-acceptance-obligation-and-current-absence

## blk-45feac2859a7b950a41fcc61

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `record-deployment-verification-lineage`
- Surface: `work-memory-verification`
- Symptom: The successful live deployment evidence was submitted to the corrected discovery lineage as a clean verification.
- Evidence: work_memory.py verify rejected the event with clean-verification-after-correction; the registered deploy sequence has its own selected lineage.

## blk-462b26b8c690df49a4fbf881

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `resume-main-research`
- Surface: `work_memory_cli`
- Symptom: work_memory rejected the help request because start is not a valid subcommand
- Evidence: CLI advertised run-start as the supported subcommand

## blk-471c325bdc1a6e949cf96158

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `activate-taggable-api-deploy-sequence`
- Surface: `work-memory-selection`
- Symptom: The registered taggable-api-deploy sequence could not be selected because its taggable-api automation repository root was not supplied.
- Evidence: classify succeeded and the immediately following explicit sequence selection returned missing-repository-root before activation or deployment.

## blk-47b3276f929caa22b98b8e45

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `v2-record-lens`
- Surface: `sequence-guard`
- Symptom: The guard rejected the current controller record-lens command after the first lens attempt was recorded.
- Evidence: The discovery document specifies --raw-findings; current research_package.py CLI and contract require --terminal-envelope.

## blk-486dd03ab73cee3ebc1a1501

- Status: `non-gap`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `transition-command-grounding-blocker`
- Surface: `blocker_catalog`
- Symptom: Blocker transition was sent with a zero UUID instead of the verification event returned by the prior command
- Evidence: verify returned e54e9a70-985a-4ed1-8734-dd5820205670; transition rejected 00000000 UUID

## blk-48ae855ba4112ba36df7f6b8

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-record-candidate`
- Surface: `sequence-guard-discovery-receipt`
- Symptom: The first v2 record-candidate guard rejected the active discovery receipt before controller state mutation.
- Evidence: sequence_guard.py guard returned exit 4 with {error: stale-source-bundle, ok: false} at 2026-07-15T08:28:08Z.

## blk-49b3bdf47edaa26b8212c280

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `adopt-approved-research-artifact`
- Surface: `convergence-baseline-guard`
- Symptom: Baseline guard blocked after the approved research document was created
- Evidence: Only docs working hash changed; git status shows the new up-cd-s-002-remaining-harness-upgrades research folder

## blk-49cebe5ff91bf431e475d00c

- Status: `superseded`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `refresh-selection-after-discovery-append`
- Surface: `sequence_guard`
- Symptom: sequence_guard activate also rejected the updated discovery log as stale
- Evidence: second same fingerprint: activate returned stale-source-bundle

## blk-4b7f97392b9d4648553c2dac

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `record-correction`
- Surface: `sequence-guard`
- Symptom: After the selected bundle changes, sequence_guard rejects the work_memory correct command that must record that exact bundle transition.
- Evidence: Both discovery_log and script sourced guards returned stale-source-bundle before command-shape evaluation; verify_receipts fails closed before cmd_guard can authorize work_memory.py correct.

## blk-4c8b8fb67b86ea3078916913

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `compose-llm-strategy-brief`
- Symptom: The real gpt-5.5 successor passed the proof-manifest boundary but rejected owner_questions manifest entry 1 against the deterministic grounding contract.
- Evidence: Harness run up-run-55743050815d failed at compose-llm-strategy-brief with owner_question_manifest_invalid:1.

## blk-4d38212b0771a4dc9b96e8b1

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `final-v3-candidate-requirement-status-contract`
- Surface: `skills/research-playbook-v2/references/planner-handoff.md`
- Symptom: All six fresh core agents produced richer requirement_statuses objects without the required research_value field, so terminal PASS states cannot emit packages.
- Evidence: emit-package returned every requirement status must contain requirement_id, research_value, and evidence_ids. Every final-v3 candidate status uses status/conclusion fields instead; SKILL.md and planner-handoff.md do not define the exact candidate requirement_statuses schema, and record_candidate accepts it until emission.

## blk-4db4846763b87bb0d4afe19f

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `record-platform-lock-guide-correction`
- Surface: `work-memory-correction-bundle`
- Symptom: The work-memory ledger rejected the guide producer correction because its selected cross-repository bundle does not contain the changed touchpoints implementation and test paths.
- Evidence: work_memory.py correct returned correction-artifact-drift-mismatch for src/up_harness/touchpoints.py and tests/unit/test_touchpoints.py.

## blk-4edbb8641b9676e9b6278e56

- Status: `closed`
- Subject: `discovery-promotion-lifecycle`
- Step: `independent-review-lifecycle`
- Surface: `discovery-promotion-lifecycle`
- Symptom: Registered failures can bypass correction, interrupted correction is not resumable, and cross-repository correction artifacts are rejected.
- Evidence: REV-LIFECYCLE-001, REV-LIFECYCLE-002, and REV-LIFECYCLE-003 were independently confirmed FIX NOW.

## blk-4eec50da6e9e5e04aeda7d96

- Status: `superseded`
- Subject: `discovery-782832ed-7fa4-5efe-9765-463303ecd2a2`
- Step: `select-bulk-reconciliation`
- Surface: `operations/sequences/SEQUENCES.md`
- Symptom: Canonical selection returned discovery-required for the repeatable bulk discovery-log audit and promotion operation.
- Evidence: work_memory.py select for task audit-discovery-promotion-candidates-20260715 returned exactly discovery-required before the discovery bootstrap.

## blk-4f6b72278a35b093ce1df7fd

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `record-memory-knowledge-repository-approval`
- Surface: `sequence-guard-markdown-tokenization`
- Symptom: The corrected approval command is still ungrounded because shlex rejects the entire Markdown row
- Evidence: Record row note contains unmatched apostrophe in helper's; shlex.split raises No closing quotation

## blk-50674a734681b26819e7b8e4

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `prepare-evaluation`
- Surface: `blind-evaluator`
- Symptom: staged-inputs-omit-required-predicate-scope-and-planner-check-vocabulary
- Evidence: evaluator_matches_output_predicate_id_scope_id_and_planner_check_names_against_hidden_gold_but_raw_snapshots_expose_only_request_and_evidence_ids

## blk-51b1de3620f40a21ed38e2dd

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `inventory-keap-tests-config`
- Surface: `repository_inventory`
- Symptom: targeted Keap scan returned path errors for absent tests and .github directories
- Evidence: rg reported tests: No such file or directory and .github: No such file or directory; it still found only the two known source references

## blk-538209598c5346c2fa63b43b

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `expand-correction-dependency-bundle`
- Surface: `dependency-manifest`
- Symptom: The approved dependency-manifest patch could not find the just-inspected context.
- Evidence: apply_patch verification failed before mutation because scripts/work_memory_bootstrap.py was no longer present in the expected formatted location.

## blk-53898f13b6d53b4f8edf20d1

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `record-strategy-section-correction`
- Surface: `sequence-guard-receipt-chain`
- Symptom: The sequence guard rejects correction recording because the selected discovery document changed after this run started.
- Evidence: The selected discovery document hash is 7ef3e0d6; current hash is b31906fd; all selected controller and manifest hashes still match.

## blk-539e7f2311661d7da1eefb74

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `run-focused-v2-tests`
- Surface: `evaluator-tests`
- Symptom: Two focused evaluator tests fail before exercising their intended assertions.
- Evidence: The tests supplied output_hash=None and lifecycle agent_id, while the evaluator requires a lowercase SHA-256 output_hash and runtime_agent_id.

## blk-55ae370049697ba81174488f

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `activate-keap-research-sequence`
- Surface: `sequence-guard`
- Symptom: The selected Keap integration research discovery sequence could not activate because the cached directive-read receipt exceeded its maximum age.
- Evidence: sequence_guard.py activate returned directive read state is stale because it exceeded max age before any repository inspection command ran.

## blk-5631781b9a52545ff026d704

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-core-runner-baseline`
- Surface: `sequence-guard-source-bundle`
- Symptom: sequence_guard rejected the implementation baseline command because the selected memory-knowledge source bundle changed during coding
- Evidence: guard returned stale-source-bundle before dispatching the accept-baseline command

## blk-5656ea8e0e215d6cb947f743

- Status: `non-gap`
- Subject: `discovery-6c9c32b3-939c-54f1-8cff-5bd9758f8821`
- Step: `record-receipt-polling-correction`
- Surface: `work-memory-correction-recorder`
- Symptom: approved-test-correction-cannot-be-recorded-against-sealed-run
- Evidence: work_memory-correct-returned-correction-artifact-drift-mismatch

## blk-56aedb8236dd9e68fdbf806f

- Status: `open`
- Subject: `discovery-f4cf2e8f-5fd3-5fc0-9b2a-54e3c9ad8ccd`
- Step: `record-run-verification`
- Surface: `work-memory-ledger`
- Symptom: final clean same-path verification is rejected while the runtime directive-receipt blocker remains fixed-awaiting-verification
- Evidence: work_memory.py verify returned clean-verification-after-correction

## blk-57c95d2845a726af79299da6

- Status: `non-gap`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `full-suite-unrelated-scoped-publish-test`
- Surface: `tests/test_scoped_git_publish.py`
- Symptom: Full pytest suite reports one failure because the test expects a leading porcelain-status space after its helper strips leading whitespace.
- Evidence: uv run pytest -q: 1 failed, 869 passed, 1 skipped; tests/test_scoped_git_publish.py git() returns stdout.strip() at line 12 while line 212 expects a string beginning with a space.

## blk-57fb6beb5742ee7e24b4c353

- Status: `superseded`
- Subject: `discovery-782832ed-7fa4-5efe-9765-463303ecd2a2`
- Step: `implement-controller`
- Surface: `scripts/discovery_candidate_reconciliation.py`
- Symptom: The approved bulk discovery reconciliation sequence existed only as a scaffold and could not audit, validate, checkpoint, or execute candidate dispositions.
- Evidence: The current run source bundle captured the scaffold baseline before the controller and tests were implemented.

## blk-585b09207361d374d81e6ee3

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `register-research-artifact`
- Surface: `sequence_guard`
- Symptom: Guard rejects a convergence_state register-artifact command sourced from the shared helper
- Evidence: sequence_guard returned source-ref-outside-selected-bundle

## blk-58883afa521aba789ca08040

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `full-suite-contract-drift`
- Surface: `full-repository-tests`
- Symptom: full-suite-825-passed-2-failed
- Evidence: status-helper-strips-leading-space-and-promotion-test-double-rejects-repo-roots-file-keyword

## blk-58df6c0d333377be1f8293ff

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `successful-run-close-command-contract`
- Surface: `sequence-discovery-contract`
- Symptom: discovery-contract-has-no-work-memory-run-close-passed-command
- Evidence: sequence-table-only-declares-bootstrap-close-failed

## blk-58ecb70a47f60408e2e470ee

- Status: `superseded`
- Subject: `discovery-a55832eb-534e-5813-b755-dfc6cb73bf75`
- Step: `live-isolated-reconcile`
- Surface: `scripts/scoped_git_publish.py`
- Symptom: Live reconciliation stopped on scripts/sequence_guard.py and tests/test_sequence_guard.py even though the prior Git rebase did not report content conflicts for them.
- Evidence: isolated-reconcile-remote returned remote conflict has no approved reconciliation rule for exactly scripts/sequence_guard.py and tests/test_sequence_guard.py before commit or push.

## blk-59180b19228e8b7c7cafa1fb

- Status: `closed`
- Subject: `discovery-e239c5e0-5bff-58b1-a62f-99f64e686baf`
- Step: `promotion-tests`
- Surface: `promotion-controller-evaluation-rewrite`
- Symptom: Two promotion controller tests failed before mutation because the historical approval sentence did not match one physical line.
- Evidence: Focused pytest reported 2 failed and 2 passed at stage_canonical; evaluation.md wraps Legacy replacement remains across two source lines.

## blk-5933375df65e9126834306c6

- Status: `closed`
- Subject: `discovery-promotion-lifecycle`
- Step: `verify-automation`
- Surface: `operations/sequences/discovery-promotion-lifecycle/sequence.md:verify-automation`
- Symptom: The registered lifecycle sequence prescribes uv run pytest directly instead of the repository-mandated scripts/run_pytest.sh entry point.
- Evidence: Registered verify-automation row contains uv run pytest across seven test modules; repository verification discipline uses scripts/run_pytest.sh and the lifecycle dependency manifest does not currently include that runner.

## blk-5a2c8846b801b89eb6f5c84c

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `final-live-canary`
- Surface: `/Users/kamenkamenov/united-partners/scripts/client_packet.py`
- Symptom: All three workflow runs completed and both continuations published valid locked strategies, but packet verification failed because Positioning Options and Measurement Framework headings were absent.
- Evidence: The canary exited with PACKET FAILED: strategy is missing structured sections: [## Positioning Options, ## Measurement Framework] after up-run-537f885b9977 reached publication=published and final_strategy_validation=valid.

## blk-5a8136a16ee7fbce36628938

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `final-memory-suite-uv-cache`
- Surface: `local-test-runner`
- Symptom: The final helper suite could not initialize uv's cache under the sandbox.
- Evidence: uv exited before pytest after failing to open /Users/kamenkamenov/.cache/uv/sdists-v9/.git with os error 1.

## blk-5a9068b12f7b1d9dd93a1c09

- Status: `non-gap`
- Subject: `discovery-e78611ed-2903-5b35-9fa2-142b91bcebc3`
- Step: `sequence-selection`
- Surface: `work-memory-sequence-selector`
- Symptom: The selector matched three unrelated application deployment sequences for a Git commit-and-push task.
- Evidence: work_memory.py select returned ambiguous-sequence:taggable-admin-spa-deploy,taggable-api-deploy,taggable-media-worker-deploy

## blk-5a978b19f46e13679a211247

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `close-verification-run`
- Surface: `scripts/work_memory.py`
- Symptom: The verified work-memory run remained open because run-close was called with an event ID already used by the verification event.
- Evidence: work_memory.py run-close returned event-id-conflict for 39fed7e5-7091-45c8-aca4-14fe5bb4ff1f.

## blk-5b6e654711de2b37c90768ca

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `corrected-bundle-successor-selection`
- Surface: `work_memory`
- Symptom: The first corrected-bundle successor selection had no current classification receipt after predecessor closure.
- Evidence: The first select returned missing-classification-receipt; a fresh canonical classify receipt then allowed successor selection.

## blk-5b791a9a76559b620325e00e

- Status: `non-gap`
- Subject: `discovery-66c9c758-8b03-5e3b-9622-faa1044070c9`
- Step: `sequence-selection`
- Surface: `operations/work-memory/events.jsonl`
- Symptom: Sequence selection and blocker recording both rejected the canonical ledger.
- Evidence: Working tree contained conflict marker at events.jsonl line 360; Git stages 2 and 3 were independently valid; canonical merge-ledger produced a 1670-event union.

## blk-5bb7b1e56beedd0a96154972

- Status: `closed`
- Subject: `discovery-a55832eb-534e-5813-b755-dfc6cb73bf75`
- Step: `canonical-ledger-union`
- Surface: `scripts/work_memory.py`
- Symptom: The isolated reconciliation canonical writer rejected remote-order plus local-unseen event union with blocker-correction-required.
- Evidence: isolated-reconcile-remote stopped before commit or push with merged ledger failed canonical validation: blocker-correction-required.

## blk-5bdd8951968543c4ca2f0dec

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-canary-dependency-manifest`
- Surface: `operations/sequences/discovery/2026-07-14-up-harness-cd-s-002-live-verification.dependencies.json`
- Symptom: work-memory selection rejects the recorded live canary because its canonical adapter executable is absent from the dependency manifest
- Evidence: select returned executable-outside-manifest::scripts/codex_role_command.py before creating a selection receipt

## blk-5c06394170ef484b6fe41c2a

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `transition-blocker`
- Surface: `sequence-discovery`
- Symptom: The discovery bundle cannot guard verified/closed blocker transitions and would become stale when the approved validator edit is applied.
- Evidence: The transition command omits required verification-event-id tokens; validate_skills.py is hashed as a dependency even though this task must edit it.

## blk-5c2b6767c81706c90d2656ae

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `initialize-convergence-state`
- Surface: `convergence-state`
- Symptom: convergence state initialization rejected the requirements file, and artifact registration then failed because state was absent
- Evidence: init returned every requirement needs id, text, and source; register-artifact raised FileNotFoundError for state.json

## blk-5c4f1036ff22b246fa80563a

- Status: `superseded`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `managed-validation`
- Surface: `managed-skill-validator`
- Symptom: managed validation rejects generated __pycache__ artifacts in research-playbook-v2
- Evidence: validate_skills.py reported scripts/__pycache__ and its pyc file

## blk-5c9cb35edc2f753234252c93

- Status: `non-gap`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `prepare-blind-evaluation`
- Surface: `prepared-evaluation-state`
- Symptom: The locked blind evaluation directory and its retained execution records are absent.
- Evidence: find returned No such file or directory for /private/tmp/research-playbook-v2-eval-20260714-2048.

## blk-5d890d2359461b711a0a680a

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `test-policy-validator`
- Surface: `python-test-runtime`
- Symptom: The documented focused pytest command cannot start.
- Evidence: Homebrew Python 3.14 reported No module named pytest.

## blk-5d8b04fef972363c4d5fa2d9

- Status: `closed`
- Subject: `discovery-candidate-reconciliation`
- Step: `correction-successor-recovery`
- Surface: `operations/sequences/discovery-candidate-reconciliation/sequence.md`
- Symptom: A correction successor that failed and produced a second correction left both corrections active, so direct dual successor binding failed on the earlier sealed document hash and blocker supersession was rejected.
- Evidence: Selection returned successor-correction-bundle-mismatch for both correction IDs; blocker transition returned blocker-correction-not-superseded; work_memory.cmd_correct atomically supports supersedes_correction_ids and prior-blocker supersession when the final correction is recorded.

## blk-5da33ca4f4baa4dc7ab4910e

- Status: `superseded`
- Subject: `discovery-04cf3898-8384-5912-9dbb-77f555ee1b22`
- Step: `read-authoritative-material`
- Surface: `sequence-guard`
- Symptom: The guard rejected the exact authorized read command because it was not yet present in the discovery document
- Evidence: sequence_guard.py returned command-not-grounded-in-selected-document for the explicit rg command despite source=tool_help

## blk-5e5921daa66d3f06148dbcf5

- Status: `fixed-awaiting-verification`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `record-memory-knowledge-repository-approval`
- Surface: `convergence-approval-sequence`
- Symptom: The recorded scope approval command is guard-valid but convergence_state rejects kind scope-expansion
- Evidence: convergence_state.py:18 permits scope-change, not scope-expansion; command exited invalid approval kind

## blk-5eb6a3333e984f5cf9b324e3

- Status: `non-gap`
- Subject: `discovery-cf976104-9e51-5bbd-83e0-83a396426eef`
- Step: `discovery-check`
- Surface: `sequence discovery closeout`
- Symptom: sequence_discovery_log.py check could not access its canonical metadata path in the default sandbox
- Evidence: check returned PermissionError; the path is outside the workspace writable roots

## blk-5f0381d736e14801b802be9c

- Status: `closed`
- Subject: `discovery-e4cdc863-c807-565a-baba-14d826c9df90`
- Step: `measure-complete-review-inputs`
- Surface: `sequence_guard discovery activation`
- Symptom: The first registered read-only inspection command is rejected because appending it changed the discovery bundle after selection and activation
- Evidence: sequence_guard.py guard returned {error: stale-source-bundle, ok: false} immediately after append-step row_hash d427a201e512d713212132b357f97b7e6261224748a0e2957f8b8e40fdc6ac2b

## blk-5fc647c4571c183d1ded4862

- Status: `non-gap`
- Subject: `discovery-cf976104-9e51-5bbd-83e0-83a396426eef`
- Step: `record-verification`
- Surface: `work_memory verification`
- Symptom: The ledger rejected same-path verification after workflow blocker activity in this run
- Evidence: work_memory.py verify returned clean-verification-after-correction and did not record an event

## blk-6013cd4dbfed4543e3921246

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `accept-protected-authorized-research-edits`
- Surface: `convergence_state`
- Symptom: The bounded baseline acceptance rejected the pre-existing protected research path even after scoped autonomy approval.
- Evidence: convergence_state.py returned: cannot accept protected dirty path; state protected_dirty_paths contains plans/hypothesis-validation-protocol-research.md

## blk-6249d7b3d6b2e9b1f2d0f140

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `advance-expected-docs-root-baseline`
- Surface: `sequence-baseline-command`
- Symptom: The guarded docs baseline advance crashes because --changed-path docs resolves to memory-knowledge/docs instead of the target repository docs directory
- Evidence: ValueError: /Users/kamenkamenov/memory-knowledge/docs is not in subpath /Users/kamenkamenov/mcp-agents-workflow

## blk-62982aa3a803a33ff37e83ca

- Status: `closed`
- Subject: `discovery-candidate-reconciliation`
- Step: `validate-dispositions`
- Surface: `scripts/discovery_candidate_reconciliation.py:manifest-snapshot`
- Symptom: The approved manifest names two already-promoted targets proven on bundle b389a844, but the execution selection resolved bundle c03b8165 and both registered verification predicates are now false.
- Evidence: Selection ccedc156 source bundle c03b81656287a9d4c6e23c5b6c00d056fa2426ee2f2815fd4c53cd06866938b6 includes changed sequence_guard.py and test hashes; direct checks returned false for discovery-candidate-reconciliation and discovery-promotion-lifecycle.

## blk-62a8d37e7c13b521c858c3c3

- Status: `closed`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `hardening-gate-1-api-exposure`
- Surface: `research_document`
- Symptom: draft says the Infusionsoft field is not exposed by an API contract without explicitly excluding direct User entity responses
- Evidence: the field is public on User.cs:45, so reflection-based JSON exposure must be ruled out separately from named DTO searches

## blk-62a9a0ec25a8c852f5129dcd

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `record-stage-correction`
- Surface: `work-memory-correction-artifact`
- Symptom: The stage-envelope correction cannot be registered from its temporary result file
- Evidence: work_memory.py correct returned changed-artifact-outside-repository

## blk-62da0fed57e3bc3a07572f82

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `red-before-reproduction`
- Surface: `isolated-pytest-import`
- Symptom: The preserved controller test cannot be collected because Python cannot import the isolated scripts package.
- Evidence: pytest exited 4 with ModuleNotFoundError: No module named scripts before collecting test_carried_correction_can_verify_after_an_intermediate_run.

## blk-63d3944ce367affd3079849a

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `activate-corrected-bundle`
- Surface: `sequence_guard`
- Symptom: The corrected discovery bundle cannot activate
- Evidence: sequence_guard.py activate returned bootstrap-sources-not-selected; the selected dependency manifest has an empty dependencies array

## blk-63f7e71bc42e5123b050d992

- Status: `non-gap`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `sequence-select`
- Surface: `work-memory-sequence-registry`
- Symptom: The canonical selector could not choose one workflow-drive sequence automatically.
- Evidence: Five unrelated workflow-drive candidates matched; the registry proved none covered this convergence run, so the documented discovery path was selected.

## blk-64a63471b24499af323d6c00

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `self-update-bootstrap`
- Surface: `sequence-guard`
- Symptom: controller-cannot-record-its-own-grounded-correction
- Evidence: sealed-predecessor-hash-0e55a0af-matches-but-current-path-must-remain-byte-identical

## blk-64abd808af57fd130e06b55e

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `repair-cross-repository-correction-guard-v2`
- Surface: `scripts/sequence_guard.py`
- Symptom: correction-guard-cannot-authorize-exact-multi-repository-artifact-bundles
- Evidence: selected-guard-rejects-external-artifacts-and-partial-bundle-validation

## blk-658f6163af8ba811b9a99fe0

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-implementation-baseline`
- Surface: `/Users/kamenkamenov/.local/state/kamen-convergence/up-harness-cd-s-002-upgrades-20260714/state.json`
- Symptom: The convergence baseline update could not create its atomic temporary file under the task state directory.
- Evidence: convergence_state.py accept-baseline raised PermissionError operation not permitted for .convergence-*.tmp before saving state.

## blk-65d8b02621a7cc33355289f8

- Status: `open`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/touchpoints.py`
- Symptom: All three bounded platform-lock guide attempts failed the same grounding contract and the source run blocked at compose-platform-lock-session-guide.
- Evidence: up-run-87ba98207ae2 records platform_lock_guide_grounding_invalid after the three-attempt correction implementation passed focused tests.

## blk-663f98228359c7ee35ffb4e2

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `verify-complete-correction-set`
- Surface: `work_memory`
- Symptom: The successor run cannot verify corrections one at a time because the ledger requires every declared correction and paired blocker in one verification event.
- Evidence: work_memory.py lines 345-358 require event correction_ids to equal the complete available correction set; the scalar verification returned verification-correction-mismatch.

## blk-66b9c25c2a688b5807d044ce

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `corrected-bundle-activation`
- Surface: `sequence_guard`
- Symptom: The corrected discovery bundle could not activate because the workflow directive-read guard state file is absent.
- Evidence: sequence_guard.py activate returned directive read state not found: /private/tmp/workflow-orch-directive-guard.json.

## blk-66c4e816b6427950be975d16

- Status: `closed`
- Subject: `discovery-54330313-0f49-590b-a9be-7751ab2b8664`
- Step: `tool-help-bootstrap-grounding`
- Surface: `sequence-guard`
- Symptom: The documented tool_help guard source cannot authorize the first discovery-log command
- Evidence: cmd_guard always requires _shape_match against the selected document and does not consume evidence_text

## blk-66d7fbf92b0e72abb2f52393

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `compose-final-strategy-brief`
- Symptom: The real gpt-5.5 run passed structured strategy, decisions, evidence, controlled-topic policy, and the new platform-lock guide, then blocked in final strategy composition.
- Evidence: Harness run up-run-770096c57fad returned compose-final-strategy-brief status blocked with no phase exception.

## blk-6739e10cf9ef5089784c0f6a

- Status: `open`
- Subject: `discovery-e9f998db-d24a-5932-90e8-c9ca2678c4ef`
- Step: `verify-corrections`
- Surface: `work_memory.verify`
- Symptom: The ledger rejected same-path verification for both corrections after the corrected bundle executed
- Evidence: work_memory.py verify returned verification-correction-mismatch for corrections e67e00e4 and 7dfa35d8

## blk-67d78d84e549faa4a8cfff33

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-init-state`
- Surface: `research-package-v2-cli`
- Symptom: init-rejected-literal-AVAILABLE-as-missing-file
- Evidence: controller-returned-cannot-read-JSON-from-AVAILABLE

## blk-67ea3ddac63fa16ac6d02859

- Status: `closed`
- Subject: `discovery-b6658d35-7870-5d15-9f4b-d316138cec83`
- Step: `successor-state-reduction`
- Surface: `discovery-promotion-lifecycle`
- Symptom: The controller treated a fixed-awaiting-verification blocker as open and refused successor selection.
- Evidence: Drive returned correction-required after correction 934c1531 was recorded; the real blocker_transitioned event has no subject or lineage fields.

## blk-68ab4df0590776737934759b

- Status: `non-gap`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-hash-json-guard-source`
- Surface: `sequence-guard`
- Symptom: hash-json-guard-rejected-out-of-bundle-tool-help
- Evidence: twelve-read-only-hash-commands-rejected

## blk-68b05e47b0d2832a2b8818bf

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `correction-lifecycle-order`
- Surface: `correction-run-sequencing`
- Symptom: final-v4-correction-bootstrap-rejected-terminal-run
- Evidence: sequence-guard-stale-bootstrap-context-rejects-run_closed-before-correct

## blk-6961bf647157f2f07e2470b0

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/strategy_brief.py`
- Symptom: The command-backed CD-S-002 canary failed in compose-llm-strategy-brief because the candidate owner-question manifest did not match the rendered owner-question block.
- Evidence: /tmp/up-cd-s-002-upgrade-canary/run-20260715T212807Z-66484/state/up-run-acc2fec2fdcb.json records compose-llm-strategy-brief failed with owner_questions_manifest_mismatch.

## blk-69b5f1f3a25b8eb69a74357c

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-record-adjudication`
- Surface: `missing-runtime-evidence-adjudicator-output`
- Symptom: evidence-limit-adjudication-rejected-before-state-mutation
- Evidence: controller-returned-invalid-operation-missing-raw-finding

## blk-6a6f3afe2a9fe77fbc9ee7b1

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `compare-managed`
- Surface: `codex-managed-skill-installation`
- Symptom: side-by-side install changed _shared and blocker-catalog in addition to adding research-playbook-v2
- Evidence: compare-managed reported added research-playbook-v2 and changed _shared, blocker-catalog

## blk-6b01bc3647830f730117a63a

- Status: `closed`
- Subject: `discovery-3393078a-d255-508d-a718-2681b85c4a35`
- Step: `inventory-commit-range`
- Surface: `sequence_guard`
- Symptom: Guard rejects the first Git inventory command after the discovery log is extended
- Evidence: sequence_guard returned stale-source-bundle immediately after append-step row 04dfe512

## blk-6c3fab30f761100bce09be02

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `research-doc-gap-agent`
- Surface: `multi_agent_v1`
- Symptom: Research document-gap verifier did not return after repeated waits and an interrupt requesting immediate completion
- Evidence: Agent 019f609a-d13f-71d2-b6b3-ea07c23805a4 remained non-terminal across normal waits, queued conclusion request, interrupt, and 60-second successor wait

## blk-6cbec0d82f7285f2702757c3

- Status: `open`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `record-final-v2-evaluation`
- Surface: `/private/tmp/research-playbook-v2-eval-20260715-final-v2/evaluation-lock.json`
- Symptom: The evaluator refuses to record v2 research packages because the v2 skill tree changed after the evaluation lock was frozen.
- Evidence: evaluate_research_playbook_v2.py record returned locked-skill-tree-drift:v2 immediately after correction 49d184c8-8ef5-4164-b7b7-1fe7954a008f changed research_package.py and its test.

## blk-6ce5332bdc4ba0296f1c109a

- Status: `closed`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `inspect-origin-commit`
- Surface: `sequence_guard`
- Symptom: sequence_guard rejected newly appended research steps because the active bundle predates the updated discovery log
- Evidence: guard returned stale-source-bundle immediately after append-step changed the discovery document

## blk-6dcd7e0b50b4ec0e63f558f4

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `repair-owner-question-output-contract-v2`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/strategy_brief.py`
- Symptom: live-gpt-5.5-strategy-output-breaks-owner-question-parser
- Evidence: run-up-run-87d9d0de034b-failed-at-compose-llm-strategy-brief-line-106

## blk-6e4eda023d95363875059cbf

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/engine/runner.py`
- Symptom: The live canary locked the platform and published the final strategy, but the published compatibility brief still contained a reserved QAF claim marker.
- Evidence: The signed-document canary exited with publication leaked claim markers after the continuation lock assertions passed.

## blk-6e51c6e83cd6ea138ff85d3a

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `work-memory-inspection`
- Surface: `scripts/work_memory.py`
- Symptom: Work-memory inspection command rejected the nonexistent status subcommand.
- Evidence: argparse lists summary, not status, as the supported summary command.

## blk-6ee002fe32ae5818f516abc5

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `command-workflow-policy-candidate`
- Surface: `tests/integration/test_command_workflow.py`
- Symptom: The changed-policy integration case raised KeyError because controlled_topic_policy_candidate was absent from the continuation context.
- Evidence: test_changed_policy_cannot_replace_platform_source_policy failed at line 371 with KeyError controlled_topic_policy_candidate.

## blk-70e9a4477dcd42d3ba7f87c4

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `convergence-stage-result-schema`
- Surface: `convergence-state`
- Symptom: record-stage rejected the condensed independent gate result
- Evidence: new_gaps entries lacked full section lens evidence why_blocker planned_fix and status fields

## blk-712c39cea3dc0bcf33b65ff3

- Status: `closed`
- Subject: `discovery-promotion-lifecycle`
- Step: `independent-review-iteration-3`
- Surface: `discovery-promotion-lifecycle`
- Symptom: A legitimate bootstrap edit is dispatched to the changed bootstrap, which rejects itself against the old activated hash before recording correction.
- Evidence: Iteration-3 reviewer and critic confirmed REV-LIFECYCLE-002 remains FIX NOW and requires an immutable launcher executing authenticated old bootstrap bytes.

## blk-717474e2e230ab661680b7df

- Status: `non-gap`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `record-doc-gap-cycle-3`
- Surface: `convergence_state`
- Symptom: The state writer rejected the valid Cycle 3 GAPS envelope after a fresh critic introduced GAP-008.
- Evidence: convergence_state.py record-stage returned: stage artifact identity changed

## blk-718ba04a4f65a8e017cc66ab

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `plan-stage-artifact-identity`
- Surface: `convergence-state`
- Symptom: record-stage rejected verifier iteration 2 after the plan at the same path was revised
- Evidence: The plan-stage evidence id is derived from the artifact path while its content hash changed between iterations

## blk-727b5bf9aa6ec61cbf675dda

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `spawn-reproduction-remediation`
- Surface: `multi-agent-control-plane`
- Symptom: The reproduction remediation lane was rejected before initialization.
- Evidence: multi_agent_v1 spawn returned: Full-history forked agents inherit the parent agent type; omit agent_type or spawn without a full-history fork.

## blk-72dd39296d121e65c2a87419

- Status: `open`
- Subject: `discovery-promotion-lifecycle`
- Step: `drive`
- Surface: `discovery-promotion-lifecycle`
- Symptom: The one-shot drive completed three additional same-bundle same-path passes but remained in qualification because every promotion-readiness declaration was unchecked.
- Evidence: Lifecycle status reports successful_runs=4, source_bundle_hash=11eb9e7557b161714b0786fa85046ecd7e918ee0bcf224ef98ab13e1c858faaa, and unmet_predicates=[readiness].

## blk-7316f2d6e07bed6cba6ac970

- Status: `closed`
- Subject: `discovery-3393078a-d255-508d-a718-2681b85c4a35`
- Step: `verify-discovery-corrections`
- Surface: `work_memory_verify`
- Symptom: Same-path verification events are rejected although the successor selection lists both correction IDs
- Evidence: work_memory verify returned verification-correction-mismatch for corrections 23cacea6 and d5798140

## blk-73394a07e10b92ed3124f9e5

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `bind-product-canary-successor`
- Surface: `scripts/work_memory.py`
- Symptom: A still-open product correction cannot receive same-path verification after later independent corrections advance the sequence bundle, despite its changed artifact remaining byte-identical.
- Evidence: The controller rejected correction d3d98166-97db-4c61-a421-50db1fec3d97 because transition hash 54403fe4... differs from current bundle 06ca93d4...; scripts/run_cd_s_002_upgrade_canary.py still hashes to the correction value 48dd4bd2....

## blk-7441db416f180077aa835e06

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-adjudication-verdict`
- Surface: `skills/research-playbook-v2/scripts/research_package.py`
- Symptom: Rejected provisional lens findings still force IN_PROGRESS or BLOCKED after fresh adjudication.
- Evidence: Round 1: current and scope returned zero actionable fingerprints but remained IN_PROGRESS with LENS_GAPS; mixed rejected RS-EVIDENCE-001 yet became BLOCKED with LENS_BLOCKED.

## blk-74feda3dc50e38b180f8875f

- Status: `superseded`
- Subject: `discovery-782832ed-7fa4-5efe-9765-463303ecd2a2`
- Step: `bootstrap-discovery-bundle`
- Surface: `work_memory.py-select`
- Symptom: Selection rejected first scripts/run_pytest.sh and then the not-yet-created discovery_candidate_reconciliation.py before a run could start.
- Evidence: work_memory.py select returned executable-outside-manifest for each recorded executable; a minimal controller scaffold and explicit launcher/controller/test dependencies were required before selection succeeded.

## blk-756d91ccabe45fa88fa5caf4

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `verify-refreshed-source-before-integrated-test`
- Surface: `united-partners/tests`
- Symptom: The convergence guard sees only the newly added integrated command-workflow test as drift.
- Evidence: Expected tests hash 11ae807d...; actual ff6ca68b...; all other approved roots match.

## blk-762c3a75fd8dce93824127ac

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `successor-sequence-activation`
- Surface: `scripts/sequence_guard.py`
- Symptom: A valid successor selection was written, but sequence_guard activation refused to consume it.
- Evidence: select returned receipt cadb8c3fbd2568ffbd33c65c9502598ce2c37a2cf9d843c0113a11f7ebf54f89 and source bundle 23a473bccd2fdc11693362e07b20b84b80f788082442188807128f5f412d7e93; activate immediately returned bootstrap-sources-not-selected.

## blk-76da3c70097aadf894593307

- Status: `non-gap`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `record-shared-helper-correction`
- Surface: `work-memory-correction`
- Symptom: Canonical correction recording rejects the approved shared convergence helper because it is outside the active repository bundle.
- Evidence: work_memory.py correct returned changed-artifact-outside-repository for /Users/kamenkamenov/.codex/skills/_shared/convergence_state.py.

## blk-7769e472ae1f0944f2844cdb

- Status: `closed`
- Subject: `discovery-candidate-reconciliation`
- Step: `audit-terminal-verification`
- Surface: `scripts/discovery_candidate_reconciliation.py:_candidate_row`
- Symptom: Guarded audit suggested four already-promoted rows although the executor predicate rejects two as unverified; legacy exact absorption targets also fail registered verification with missing-repository-root.
- Evidence: Red manifest /private/tmp/discovery-candidate-reconciliation-red.json reports already-promoted=4; registered checks: commit-push-main=false, discovery-bootstrap=false, remote-mcp-user-onboarding=missing-repository-root, taggable-admin-spa-deploy=missing-repository-root.

## blk-77740d820bbf7e79e99d7e00

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `select-successor`
- Surface: `overlapping-active-corrections`
- Symptom: A verification successor cannot carry all four active corrections after a later correction changed their shared discovery document.
- Evidence: Corrections 46ad161e-c641-440d-98b9-8acfaa0d52f0, bae51208-7e25-416d-bf67-9fc10120b789, and cd0eed01-6357-49c2-8820-303423f985e3 seal the discovery document at a122be426653d85fcd1d19fd0739a2bb6d0880610bc7d56f6f39ecb89682b980; correction 8960346d-3b5b-48b4-b460-7146688a6b5c moved the same document to 7746e9702155cc33b70cbe3b0cc07c78f62e205b26da607b61657b0094356d8f without superseding those overlapping corrections.

## blk-780d4ae6289bb109347ca087

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `full-deterministic-verification-command-guard`
- Surface: `operations/sequences/discovery/2026-07-14-up-harness-cd-s-002-live-verification.md`
- Symptom: The sequence guard rejected the unit-discovery, integration-discovery, and verify_harness commands because only a single-target unittest shape was registered.
- Evidence: All three guards returned command-not-grounded-in-selected-document; none of the verification commands executed.

## blk-78118958dbd62e3e4ead8731

- Status: `open`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `final-live-canary`
- Surface: `tool-session-supervision`
- Symptom: The final canary process disappeared after two workflows completed and the third reached compose-platform-lock-session-guide.
- Evidence: up-run-cfcc73588d76 and up-run-5ea9263892ab completed 35 phases; up-run-e00aa81e16f2 remained running at 27 phases; ps found no canary or role process and no current-run summary exists.

## blk-7864e7ef841aead64e2b6cf9

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `focused-test_evidence_verification`
- Surface: `tests/unit/test_evidence_verification.py`
- Symptom: All evidence contract vectors block before claim validation.
- Evidence: The test constant still supplies execution/model/reasoning_effort; the runtime now requires the closed verified|fixture provenance record.

## blk-78796f39be2e174a55e23cca

- Status: `fixed-awaiting-verification`
- Subject: `discovery-8fb5c613-edd8-567b-97e5-bf4940b6c397`
- Step: `record-inspection-command`
- Surface: `sequence discovery command table`
- Symptom: the command-recording helper rejected the repository inspection command
- Evidence: append-step returned invalid-command-row for a regex containing pipe separators

## blk-78de0dcdfb8ebb167f0afa78

- Status: `closed`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `review-helper-path-validation`
- Surface: `sequence-discovery-log`
- Symptom: The newly recorded implementation-review command points to a nonexistent convergence state helper.
- Evidence: Python reported cannot open /Users/kamenkamenov/.codex/skills/playbook-convergence-loop/scripts/convergence_state.py because the file does not exist.

## blk-795fa3c9bffc549850d4d345

- Status: `non-gap`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `record-research-stage`
- Surface: `convergence-state-recorder`
- Symptom: The stage recorder rejected document gap IDs supplied as owned execution blocker IDs.
- Evidence: record-stage returned stage owns unknown blockers; RDG IDs are recorded gaps, not blocker-catalog IDs.

## blk-79b4376fc30f780813dc4493

- Status: `non-gap`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `record-research-doc-gap-stage`
- Surface: `convergence_state`
- Symptom: The independent GAPS verdict cannot be recorded because the critic's new_gaps objects use fields accepted by the narrative contract but not the convergence state schema.
- Evidence: convergence_state.py record-stage returned: new gap is missing required fields.

## blk-7c377a0bb7100ace418962f1

- Status: `non-gap`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `spawn-research-doc-gap-critic`
- Surface: `multi_agent_v1`
- Symptom: The independent critic was not created because the spawn call used prompt instead of the required message or items field.
- Evidence: multi_agent_v1__spawn_agent returned: Provide one of: message or items; no agent id was issued.

## blk-7d8e4dc776ed4131a77ffa49

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `durable-run-start`
- Surface: `work-memory-command-selection`
- Symptom: the bootstrap launcher rejected run-start because it only supports correct and run-close
- Evidence: argparse listed launcher choices correct and run-close; documented work_memory.py run-start immediately succeeded and created run 51ad9a4a

## blk-7dedfb3ab573b95699b0fd84

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `plan-gap-state-reconciliation`
- Surface: `convergence-state`
- Symptom: Final verifier PASS could not close PV-002 because convergence state still records it open after the parent plan fix
- Evidence: The result transition expects fixed-in-plan to closed, but no parent set-gap transition was recorded after correcting the plan

## blk-7e13d9b8496766903598a0ba

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `focused-workflow-topology-test`
- Surface: `src/up_harness/engine/workflow.py`
- Symptom: the exact 35-phase workflow cannot load because the closed phase-type registry rejects its first new type
- Evidence: ValueError from WorkflowDefinition.validate at workflow.py line 97 for prepare-controlled-topic-policy-inputs

## blk-7e78835cf33aa2f6b32ab92a

- Status: `closed`
- Subject: `discovery-promotion-lifecycle`
- Step: `target-registered-selection`
- Surface: `discovery-promotion-lifecycle`
- Symptom: The controller classified commit-push-main registered verification as workflow-drive instead of the target's other operation kind.
- Evidence: After commit-push-main promotion, select rejected registered-verify-commit-push-main with sequence-not-valid-for-operation.

## blk-7ecdc512174bc56522df743c

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `ground-regex-searches`
- Surface: `sequence-discovery-log`
- Symptom: Discovery helper rejects stored rg commands whose quoted regex contains pipe alternation
- Evidence: append-step returned invalid-command-row for both memory search and report-label trace after shell quoting was corrected

## blk-7f61aafc54c93e5d1373abcb

- Status: `non-gap`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `correction-lifecycle-order`
- Surface: `work-memory-orchestration`
- Symptom: The correction-bound successor could not be selected because the predecessor blocker remained open after its run was closed.
- Evidence: successor selection returned successor-correction-not-awaiting-verification; transition on the closed predecessor returned event-after-terminal.

## blk-7fa6482208e9bbacae565824

- Status: `superseded`
- Subject: `discovery-candidate-reconciliation`
- Step: `execute-rolling`
- Surface: `operations/sequences/discovery-candidate-reconciliation/sequence.md`
- Symptom: execute-rolling changed the reconciliation discovery candidate from already-promoted to quarantine while the corrected registered bundle's successor was still open.
- Evidence: The guarded live command returned rolling-existing-disposition-changed for discovery-candidate-reconciliation: already-promoted->quarantine; the current bundle had passing tests but no recorded passed same-path verification and passed close yet.

## blk-7fc1c7428ce176309641ffa1

- Status: `non-gap`
- Subject: `discovery-782832ed-7fa4-5efe-9765-463303ecd2a2`
- Step: `inspect-lifecycle-help`
- Surface: `sequence_guard.py`
- Symptom: The active discovery guard rejected the lifecycle help inspection before it ran.
- Evidence: sequence_guard.py guard returned exactly stale-source-bundle after activation.

## blk-801829be7d2077acfbe0411c

- Status: `open`
- Subject: `discovery-e9f998db-d24a-5932-90e8-c9ca2678c4ef`
- Step: `locate-runtime`
- Surface: `sequence_guard`
- Symptom: The runtime search command was rejected before execution
- Evidence: sequence_guard returned command-not-grounded-in-selected-document

## blk-802727e9596a22606e2fdd70

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `roots-correction-supersession`
- Surface: `scripts/blocker_catalog.py`
- Symptom: The catalog rejected direct supersession of the roots blocker because its attached correction remains active in the correction ledger.
- Evidence: blocker_catalog.py returned blocker-correction-not-superseded for blk-923e1cf6d66a4b9f87287f12.

## blk-8073bfceb3ce55625e3a4bc2

- Status: `open`
- Subject: `commit-push-main`
- Step: `publish`
- Surface: `memory-knowledge-origin-main`
- Symptom: The scoped commit exists locally but origin/main rejected the push because the remote branch has commits absent locally.
- Evidence: git push origin main rejected 4056fc63018702047190a41eb0d27c6ccbe759aa with fetch-first/non-fast-forward.

## blk-813ce08bf5ad83ddf4b35cc0

- Status: `open`
- Subject: `discovery-e9f998db-d24a-5932-90e8-c9ca2678c4ef`
- Step: `read-summary`
- Surface: `work_memory.summary`
- Symptom: The first summary command used task-id but the CLI requires subject-id
- Evidence: argparse reported --subject-id is required

## blk-8154d3307003a1112828bd5c

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `record-research-doc-gap-cycle-25`
- Surface: `convergence-state-stage-ledger`
- Symptom: Cycle 25 stage-result cannot be recorded because convergence state knows gaps only through GAP-021 while the audit has reached GAP-067.
- Evidence: record-stage returned stage assigns unknown gaps; state stages contain research-doc-gap attempt 1 and doc-gap-closure attempts 1-12 only, while the audit documents Cycles 13-25.

## blk-822f5912321b9e00df07c17c

- Status: `closed`
- Subject: `discovery-782832ed-7fa4-5efe-9765-463303ecd2a2`
- Step: `audit-candidates`
- Surface: `scripts/discovery_candidate_reconciliation.py`
- Symptom: The audit manifest included operations/sequences/discovery/README.md as candidate 46 and classified it as discovery-id-missing.
- Evidence: Audit /private/tmp/discovery-candidate-reconciliation-20260715.json returned 46 rows; row 46 is README.md, which is directory documentation rather than a discovery run log.

## blk-83f0a654438fd4f644768834

- Status: `non-gap`
- Subject: `discovery-bc73b987-df58-5ef3-9ae4-e8543289023a`
- Step: `record-captured-state-inspection`
- Surface: `sequence-discovery-log`
- Symptom: Discovery logger rejected the planned jq command row
- Evidence: append-step returned {error: invalid-command-row, ok: false}

## blk-840b9f283f20a71425877d08

- Status: `non-gap`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `independent-package-audit`
- Surface: `multi_agent`
- Symptom: read-only-auditor-remained-running-after-repeated-waits-and-explicit-stop-request
- Evidence: agent-019f62bc-7fe3-70c3-b6fe-5fccc9a8ff76-returned-no-status-across-five-waits

## blk-84a850c5303de34d5ce6e884

- Status: `non-gap`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `plan-critic-6-agent`
- Surface: `multi-agent-runtime`
- Symptom: independent plan critic remained running after repeated 20-second waits and a direct conclusion request
- Evidence: agent /root/research_coverage_sgap20 produced no mailbox result across more than 80 seconds

## blk-84c6df6252dd91043099abc0

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `repository-roots-successor-selection`
- Surface: `scripts/work_memory.py`
- Symptom: The roots correction successor could not bind after a later product correction advanced the discovery source bundle.
- Evidence: Correction 7ae65fce-7ca0-41ce-8351-c07cd30f3799 expects bundle b884, while the current selected bundle is 42033fd42c1e5231356a883331ec15ab83337e32465d12f211b12e520595ced3.

## blk-85f4b845329a1390c55d08cb

- Status: `non-gap`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-init-state`
- Surface: `skills/research-playbook-v2/scripts/research_package.py`
- Symptom: all-five-v2-state-initializations-rejected-before-write
- Evidence: argparse-requires-current-runtime-future-system-or-mixed-enum

## blk-86fa98060551f4ec68265ccc

- Status: `closed`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `verify-automation`
- Surface: `discovery-verification-command`
- Symptom: the grounded verification command omits the promotion-helper test that is part of the correction
- Evidence: discovery row lists scoped publish and discovery-log tests only; correction 0ec30bae also changes scripts/sequence_promote.py and tests/test_sequence_promote.py

## blk-8748ce255b175eb2f2aa9eef

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-record-attempt-help`
- Surface: `operational-command-grounding`
- Symptom: record-attempt-help-path-failed-and-first-catalog-open-used-wrong-subject
- Evidence: run-receipt-binds-subject-discovery-683fb3d9-702b-55ff-945f-35c9f667e439-and-rg-locates-controller-at-skills/research-playbook-v2/scripts/research_package.py

## blk-87d14c39def5a888a2c1e392

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `evaluator-command-discovery`
- Surface: `scripts/evaluate_research_playbook_v2.py`
- Symptom: help-probe-used-lock-instead-of-prepare
- Evidence: argparse-rejected-lock-before-any-evaluation-state-write

## blk-881ff356a4b4cd18adf7d149

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `record-evaluation`
- Surface: `evaluate-research-playbook-v2-record-order`
- Symptom: research-record-rejected-because-unrecorded-planner-files-existed
- Evidence: evaluator-returned-orphaned-output-current-runtime-v2-planner-json

## blk-8993d8c4248483be1f967a45

- Status: `non-gap`
- Subject: `discovery-promotion-lifecycle`
- Step: `stable-bundle-selection`
- Surface: `git-index-ledger-conflict`
- Symptom: A concurrent stash application reintroduced conflict markers after a clean 143-test verification, making selection stale before run-start.
- Evidence: git status showed UU in ledger, blocker view, sequence document, and bootstrap; canonical ledger union appended 104 events and regenerated the blocker view.

## blk-8a0d8a7aae77d49d366def9d

- Status: `non-gap`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `record-research-gaps`
- Surface: `convergence-state-recorder`
- Symptom: The convergence-state recorder rejected comma-separated requirement IDs.
- Evidence: parse_json_list called json.loads and raised JSONDecodeError; --requirement-ids requires a JSON array.

## blk-8a4b8c26e54d0d7906bb0e86

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `restore-managed`
- Surface: `managed-projection-recovery`
- Symptom: recovery-target-changed-between-live-checks
- Evidence: command-observed-present-then-immediate-check-observed-missing-with-no-backup

## blk-8ab6978877066e6789afbeb9

- Status: `closed`
- Subject: `discovery-87df1262-3559-590e-9102-27b64fd3c6ad`
- Step: `inspect-release-entrypoints`
- Surface: `sequence-guard`
- Symptom: The release inspection command was refused before execution.
- Evidence: sequence_guard returned command-not-grounded-in-selected-document for the exact rg command.

## blk-8b43d5a52314e62f83e84a5a

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `blocker-helper-contract`
- Surface: `blocker-catalog`
- Symptom: Repository-local blocker helper rejected the skill-documented transition command
- Evidence: mcp-agents-workflow helper exposes add/update while memory-knowledge helper exposes open/transition

## blk-8b6be409b3d95d0cfe47a51a

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `successor-selection`
- Surface: `work-memory-correction-carry-forward`
- Symptom: A fresh successor cannot bind older still-valid corrections after an unrelated bundle change when those corrections include the semantic discovery document.
- Evidence: All eleven raw correction artifacts still match their recorded SHA-256 values, but _validate_successor_corrections compares the discovery document's raw correction hash to its semantic source-bundle hash and rejects selection.

## blk-8bcbe4478330315aa3d2f25a

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `register-research-artifact`
- Surface: `sequence_guard`
- Symptom: The convergence state cannot register the research artifact because sequence_guard rejects tool-help evidence outside the selected discovery bundle.
- Evidence: sequence_guard returned {error: source-ref-outside-selected-bundle, ok: false} before register-artifact executed.

## blk-8c1dcf77bcbfff4a57a49000

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `record-cross-repository-correction`
- Surface: `sequence-guard-contract`
- Symptom: The clean before-state guard cannot authorize the typed bootstrap wrapper or repository-qualified UP artifacts while preserving relative memory-repository paths.
- Evidence: Independent assessment plus red/green guard tests identified the stale prefix, task binding, repository identity, and exact-drift contract.

## blk-8c4036400e25c270eb7a1bb8

- Status: `fixed-awaiting-verification`
- Subject: `discovery-6c9c32b3-939c-54f1-8cff-5bd9758f8821`
- Step: `verify-reset-worker-tests`
- Surface: `reset-worker-sqlite`
- Symptom: regression-tests-emit-repeated-unclosed-database-warnings
- Evidence: python-unittest-emitted-multiple-ResourceWarning-unclosed-database-messages

## blk-8ce0cf7fb5202a60bb906416

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `research-baseline-guard`
- Surface: `convergence_state.py`
- Symptom: Baseline guard rejected unsupported --path argument before checking state
- Evidence: argparse rejected --path; initial catalog attempt also rejected a guessed subject and the run receipt confirms subject discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a

## blk-8d00495043a7badd2b1a94c4

- Status: `open`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `command-workflow-locked-qna`
- Surface: `tests/integration/test_command_workflow.py`
- Symptom: The locked controlled-policy continuation blocked at compose-final-strategy-brief instead of completing.
- Evidence: test_controlled_policy_is_preserved_into_locked_qna_continuation expected completed but received blocked for compose-final-strategy-brief.

## blk-8daf0f33edaa3c2e03743951

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `record-lineage-controller-correction`
- Surface: `scripts/sequence_guard.py`
- Symptom: The sequence guard rejected the controller correction command before it could be recorded.
- Evidence: sequence_guard.py guard --correction-bootstrap returned invalid-correction-bootstrap-source with scripts/work_memory.py as both invoked controller and source-ref.

## blk-8dcf1c94b73742e9410b5303

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `restore-managed`
- Surface: `managed-projection-recovery`
- Symptom: sealed-missing-file-cannot-be-recreated
- Evidence: restore-managed-refused-missing-pyc-before-mutation

## blk-8e3d23e3fab2ac13377e86ef

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `sequence-guard-status-before-stage5-baseline`
- Surface: `sequence_guard`
- Symptom: The active sequence receipt no longer matches the current selected controller bundle.
- Evidence: sequence_guard status returned {error: stale-source-bundle, ok: false} on 2026-07-15.

## blk-8e6823c77df76e296b919e1d

- Status: `closed`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `refresh-after-review-log`
- Surface: `sequence-selection`
- Symptom: The active-sequence refresh rejected newly logged convergence slot commands.
- Evidence: work_memory.py select returned executable-outside-manifest::scripts/convergence_slots.py immediately after the five review/critic steps were appended.

## blk-904959edb04746bea7cbe1e3

- Status: `open`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `plan-verifier-4-read-plan`
- Surface: `sequence guard discovery bundle`
- Symptom: The verifier cannot read the current plan or its verification ledger through the active sequence guard.
- Evidence: sequence_guard rejected exact sed reads for docs/gf-n3-resume-durability-plan.md and /private/tmp/gf-n3-resume-durability-plan-verification.json; the recorded research read was accepted.

## blk-909a39c3c98f1f638ca79574

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `guard-final-live-canary`
- Surface: `sequence-guard-working-directory`
- Symptom: The live-canary guard failed before dispatch because it was invoked from the UP repository instead of the discovery repository.
- Evidence: sequence_guard.py returned missing-repository-root; run-start succeeded from memory-knowledge with the identical selected bundle and roots manifest.

## blk-9147abcbb1d0b5d7d7a826bb

- Status: `superseded`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `verify-run`
- Surface: `work-memory-lifecycle`
- Symptom: same-path verification cannot be recorded for the generated-artifact blocker
- Evidence: work_memory.py verify returned paired-correction-blocker-required

## blk-91b24d910bcd5a622a9665c7

- Status: `closed`
- Subject: `discovery-candidate-reconciliation`
- Step: `one-shot-drive`
- Surface: `scripts/discovery_candidate_reconciliation.py`
- Symptom: The registered reconciliation sequence still requires separate manual classification, selection, verification, live execution, evidence recording, and run closure commands.
- Evidence: The reconciliation parser exposes only audit, validate, execute, and execute-rolling; the sequence document lists the governed lifecycle as separate operator steps.

## blk-923e1cf6d66a4b9f87287f12

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `product-correction-recording`
- Surface: `scripts/work_memory.py`
- Symptom: The work-memory ledger refused to bind the UP source correction because the selection has no UP repository root.
- Evidence: work_memory.py correct returned changed-artifact-outside-repository for /Users/kamenkamenov/united-partners/src/up_harness/strategy_brief.py.

## blk-929eb38f1d020f4de6b4d125

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `transition-non-gap`
- Surface: `discovery-control-plane`
- Symptom: guard-rejected-proven-non-gap-transition-command
- Evidence: sequence-guard-returned-command-not-grounded-and-discovery-table-lacks-transition-non-gap-row

## blk-92e68eaa772055447b599ca2

- Status: `closed`
- Subject: `discovery-ad8664ac-4bf6-53de-9aea-074b5093bde6`
- Step: `smoke-package`
- Surface: `repository-bundle`
- Symptom: packaged git bundle cannot be cloned on an isolated home
- Evidence: clone failed: Could not read parent 17996ac and remote did not send all necessary objects

## blk-930990aeeaa49df37536fbfe

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `guard-before-integrated-upgrade-test`
- Surface: `memory-knowledge selected source bundle`
- Symptom: The sequence guard is stale before the integrated test because shared controller and discovery files changed after selection.
- Evidence: Selected discovery/controller hashes 47f08e.../a1091c...; current hashes 62b6c8.../a42f16....

## blk-937364a65584e386463f135a

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `record-parser-boundary-correction`
- Surface: `scripts/work_memory.py`
- Symptom: The work-memory ledger rejected the proven parser correction because platform_decisions.py was absent from the selected dependency snapshot.
- Evidence: work_memory.py correct returned correction-artifact-drift-mismatch for /Users/kamenkamenov/united-partners/src/up_harness/platform_decisions.py.

## blk-93dcecee88f315fc1e2fa743

- Status: `non-gap`
- Subject: `discovery-cf976104-9e51-5bbd-83e0-83a396426eef`
- Step: `closeout-tool-help-guard`
- Surface: `sequence_guard tool_help grounding`
- Symptom: The guard rejected each documented work-memory/discovery closeout command before execution
- Evidence: All five sequence_guard invocations returned command-not-grounded-in-selected-document

## blk-944631f0da71d2268a16b783

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `implementation-baseline-guard`
- Surface: `convergence-state`
- Symptom: guard-baseline detected new src/tests hashes while bounded implementation workers were uploading their assigned modules.
- Evidence: Expected src hash 452969... and tests be008d...; actual src 89786a... and tests be5fb8... immediately after three approved disjoint workers started.

## blk-945eeec0793fed58bb785255

- Status: `closed`
- Subject: `discovery-b6511eb5-57d4-5481-ad26-c2a4e7e997f2`
- Step: `read-research-execution-block`
- Surface: `sequence_guard`
- Symptom: Guard rejected a newly recorded bounded read after whole-file output truncation
- Evidence: sequence_guard returned stale-source-bundle after the discovery log gained the missing lines 289-305 read

## blk-94d61940ec2d3a6a408ef0a7

- Status: `non-gap`
- Subject: `discovery-f4cf2e8f-5fd3-5fc0-9b2a-54e3c9ad8ccd`
- Step: `record-directive-receipt-correction`
- Surface: `work-memory-ledger`
- Symptom: correction record rejects the actual changed directive receipt because it is intentionally stored under private tmp
- Evidence: work_memory.py correct returned changed-artifact-outside-repository for /private/tmp/workflow-orch-directive-guard.json

## blk-95ef5694c26493a0afbc8f13

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `blocker-subject-contract`
- Surface: `blocker-catalog`
- Symptom: Blocker open rejected the task id as the run subject
- Evidence: Active selection binds the run to discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c

## blk-961b309e641228540cd016a7

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `reconstruct-clean-correction-baseline`
- Surface: `safety-approval`
- Symptom: The safety layer rejected temporary removal of the approved guard and owner-question hunks before any file changed.
- Evidence: apply_patch returned unacceptable risk: destructive rollback not clearly authorized; it required explicit authorization naming the temporary reversal and immediate reapplication.

## blk-9633479be37098d61b4320ca

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `refresh-stale-source-receipt-20260715-4`
- Surface: `sequence_guard`
- Symptom: current operational receipt changed before the diagnosed owner-question injector fix could be applied
- Evidence: sequence_guard rejected guard-before-owner-question-injector-fix with stale-source-bundle

## blk-96ab15c39011b378da70a4bf

- Status: `open`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `coverage-vp2-read-research`
- Surface: `sequence_guard command grounding`
- Symptom: Guard rejects the read-only command needed to inspect the research artifact
- Evidence: sequence_guard rejected nl -ba docs/gf-n3-resume-durability-research.md

## blk-97163ba12dade318f9a9f82b

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `compare-managed`
- Surface: `managed-snapshot-comparator`
- Symptom: exact-restored-snapshot-reported-failing
- Evidence: compare-returned-unallowed-pre-missing-for-identical-before-and-after

## blk-983ba89016dc82aee3b2b871

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `independent-package-audit`
- Surface: `work_memory_source_bundle`
- Symptom: test-contract-can-change-without-invalidating-active-run-bundle
- Evidence: selected-source-bundle-contains-controller-but-omits-tests-test-research-playbook-v2-py

## blk-9840dc7237480079e55472ed

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-stage5-packet-baseline`
- Surface: `sequence_guard`
- Symptom: The packet stage changed src/up_harness, scripts, and tests together, but the discovery log lacks the exact atomic three-root accept-baseline command.
- Evidence: sequence_guard rejected the three-root command with command-not-grounded-in-selected-document.

## blk-99e06d8f4cd4edf3e5c55d09

- Status: `closed`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `inspect-convergence-tools`
- Surface: `sequence-guard-discovery-grounding`
- Symptom: The active discovery sequence rejects the first repository/skill inspection command because no command shape is recorded.
- Evidence: sequence_guard.py returned command-not-grounded-in-selected-document for rg --files over the convergence skill directories.

## blk-9ad363bfbc7631ae4c7777de

- Status: `closed`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `close-stale-directive-receipt-blocker`
- Surface: `sequence-guard-source-bundle`
- Symptom: The active Keap research discovery bundle cannot guard the canonical blocker terminal transition because blocker_catalog.py is absent from its dependency manifest.
- Evidence: sequence_guard.py guard returned source-ref-outside-selected-bundle for /Users/kamenkamenov/memory-knowledge/scripts/blocker_catalog.py; the discovery manifest dependencies array is empty.

## blk-9afd55aa254755b5d8267659

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `final-formatter-scan-quoting`
- Surface: `sequence-discovery-log`
- Symptom: Nested single-quoted rg patterns broke the discovery-log append command
- Evidence: Only acceptance, solution-build, and verifier steps were recorded; no verification command executed

## blk-9bcbf875cc1643208cacbdf2

- Status: `closed`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `check-gh-auth`
- Surface: `github-auth`
- Symptom: gh auth status reports the active yourbteam token is invalid
- Evidence: gh auth status exited 1 and identified an invalid token without exposing it

## blk-9bd1010a362febf24870f984

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `live-cd-s-002-upgrade-canary`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/touchpoints.py`
- Symptom: The command-backed acceptance canary completed its discovery run with a platform-lock session guide even though that artifact is permitted only for corporate re-drafts.
- Evidence: /tmp/up-cd-s-002-upgrade-canary/canary-failure.json records error discovery run emitted a session guide.

## blk-9c4932e5c2c593eac5be7e3d

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `close-failed-remediation-run`
- Surface: `work-memory-run-close`
- Symptom: run-close persists the terminal event but exits with TypeError while computing metrics
- Evidence: scripts/work_memory.py:1101 sums record[terminal] and boolean; non-terminal records yield None

## blk-9cbf32aa7597b0b9cdd18cac

- Status: `non-gap`
- Subject: `discovery-6c9c32b3-939c-54f1-8cff-5bd9758f8821`
- Step: `compare-current-and-cloned-enrollment`
- Surface: `sequence-guard-orchestration`
- Symptom: read-only-comparison-executed-after-guard-rejected-stale-bundle
- Evidence: guard-returned-stale-source-bundle-but-combined-tool-script-continued-to-sqlite-query

## blk-9d066ad64f69a4b253a939fb

- Status: `superseded`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `successor-selection`
- Surface: `work-memory-successor-binding`
- Symptom: corrected-bundle successor selection rejected the discovery-helper correction
- Evidence: the earlier selection returned successor-correction-artifact-outside-bundle because four corrected control-plane files were absent from the discovery dependencies

## blk-9d2190e3144df21103036aeb

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `final-review-requirement-order`
- Surface: `convergence-state`
- Symptom: The final review PASS was attempted before R1 through R7 were marked satisfied.
- Evidence: convergence_state.py record-stage rejected final-review-iteration-1 immediately after the legal implementation-to-review transition.

## blk-9d6b80920183daffcad5118d

- Status: `closed`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `activate-corrected-bundle`
- Surface: `sequence-guard`
- Symptom: The corrected discovery bundle cannot activate
- Evidence: sequence_guard.py activate returned bootstrap-sources-not-selected

## blk-9e3a0f0d74e5e2ae86da1567

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `canary-static-command-grounding`
- Surface: `operations/sequences/discovery/2026-07-14-up-harness-cd-s-002-live-verification.md`
- Symptom: sequence_guard rejected the bundled-Python canary --help command because the exact command is absent from the selected discovery document
- Evidence: sequence_guard returned exit 4 with command-not-grounded-in-selected-document for the exact bundled interpreter and script path

## blk-9e9ee1daf2ff86ae6f1a77d3

- Status: `open`
- Subject: `commit-push-main`
- Step: `isolated-integrate-and-resume`
- Surface: `memory-knowledge-origin-main`
- Symptom: The isolated integration aborted while rebasing the lifecycle commit onto origin/main.
- Evidence: Rebase stopped applying 4056fc6, aborted, and restored temporary HEAD 30fb98c; source worktree and remote were unchanged.

## blk-9ee27ad87083764d950e0e7c

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `convergence-approval-state`
- Surface: `convergence_state.py`
- Symptom: Pre-approved plan scope could not be recorded
- Evidence: grant-approval rejected comma-separated values because parse_json_list calls json.loads

## blk-9f87807653a04e72cbf2bcc8

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `blocker-recovery-command-contract`
- Surface: `sequence-discovery-contract`
- Symptom: fixed-awaiting-overlapping-correction-cannot-return-open-before-supersession
- Evidence: work-memory-valid-transitions-require-fixed-awaiting-to-open-then-open-to-superseded

## blk-9fee6cb16be1f2c7b6a1e9ed

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `refresh-stale-source-receipt-20260715-2`
- Surface: `sequence_guard`
- Symptom: current operational receipt no longer matches the selected shared controller bundle
- Evidence: sequence_guard status returned stale-source-bundle before any UP source edit

## blk-9ff3ae55ed163258380d6ceb

- Status: `non-gap`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `wait-research-doc-gap-critic`
- Surface: `multi_agent_v1`
- Symptom: The critic wait call did not attach because the runtime expects a non-empty agent id collection rather than the singular agent_id field.
- Evidence: multi_agent_v1__wait_agent returned: agent ids must be non-empty; the bound agent remains active.

## blk-a0fecad285c0e403c22fba64

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-init-state`
- Surface: `selected-source-bundle-v10`
- Symptom: The active v10 guard rejected the first case initialization after the controller and its tests changed again.
- Evidence: After v10 selection, scripts/work_memory.py and tests/test_work_memory.py acquired new hashes before any v2 state was created.

## blk-a123a8b1fcf2622e153c8b6d

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `reusable-live-model-canary`
- Surface: `scripts/run_cd_s_002_upgrade_canary.py`
- Symptom: The pre-approved Stage 6.2 live canary entrypoint does not exist in scripts/.
- Evidence: rg --files scripts lists client_packet.py, codex_role_command.py, mcp_smoke.py, run_evaluation.py, and verify_harness.py, but no run_cd_s_002_upgrade_canary.py.

## blk-a1c07342b4019033f278ee33

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `record-cycle7-stage`
- Surface: `convergence-state-gap-transition`
- Symptom: The corrected Cycle 7 envelope was rejected when it attempted to reopen terminal GAP-006 and GAP-008.
- Evidence: record-stage returned: unsupported gap transition for closed-to-open recurrence transitions.

## blk-a24f9bf964dc4adbd39b63c6

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `refresh-stale-source-receipt-20260715-3`
- Surface: `sequence_guard`
- Symptom: current operational receipt no longer matches the selected shared controller bundle
- Evidence: sequence_guard rejected the atomic src plus tests baseline update with stale-source-bundle

## blk-a4e2b2dcbe6f68e0c72eb879

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `verify-plan-ledger-schema`
- Surface: `verify-plan-ledger`
- Symptom: Verification ledger check rejected all six coverage items
- Evidence: Each item has subsystem why risk evidence miss_risk status but lacks required summary

## blk-a507a01ef80c9f9bf706e43e

- Status: `closed`
- Subject: `discovery-66c9c758-8b03-5e3b-9622-faa1044070c9`
- Step: `verify-automation`
- Surface: `tests/test_screenshot_source_locator.py`
- Symptom: The exact discovery verification command could not start the test suite.
- Evidence: /opt/homebrew/opt/python@3.14/bin/python3.14: No module named pytest

## blk-a5d91c78094c2c6abd11ca71

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `validate-managed`
- Surface: `sequence-discovery`
- Symptom: The discovery log records managed validation and install commands without their required source and manifest arguments.
- Evidence: validate_skills.py requires --skills-root; install_skills.py requires --source and --manifest.

## blk-a61d3ce9e34f92de1b3f894f

- Status: `open`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `successor-select`
- Surface: `work-memory-correction-chain`
- Symptom: The final successor could not bind both corrections because the test-launcher correction changed the dependency manifest already sealed by the typed-answer correction.
- Evidence: Selection with corrections a573dd49-7498-4317-885d-213f8ce06f20 and 726c3f3f-003b-40b7-a114-a4c9d4f9e3a1 exited 3 with successor-correction-bundle-mismatch; work_memory.py lines 925-960 require each active correction artifact hash to match the effective successor bundle.

## blk-a6e730de2cac3cac1e397d45

- Status: `closed`
- Subject: `discovery-04cf3898-8384-5912-9dbb-77f555ee1b22`
- Step: `record-read-command`
- Surface: `work-memory-correction`
- Symptom: Correction recording rejected the discovery bundle because an explicitly read Python contract path is not declared in the dependency manifest
- Evidence: work_memory.py correct returned executable-outside-manifest::scripts/research_package.py after the read command named the locked script

## blk-a97a1b0a939925fbdbcd19a0

- Status: `non-gap`
- Subject: `discovery-promotion-lifecycle`
- Step: `full-repository-suite`
- Surface: `skills/managed-skills.txt`
- Symptom: The complete repository suite has one validator failure because research-playbook-v2 remains in managed-skills.txt.
- Evidence: Full suite: 1 failed, 972 passed, 1 skipped, 13 subtests passed; failing assertion is test_validate_skills.py:68.

## blk-a9904c536f46f6645b9eb6f9

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `legacy-research-batch`
- Surface: `subagent-runtime`
- Symptom: six-agent-legacy-spawn-returned-no-ids-after-thread-limit
- Evidence: runtime-reported-agent-thread-limit-reached-and-sequence-doc-warns-partial-allocation

## blk-aa358c52c5dceacb935be8a4

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `accept-research-doc-baseline`
- Surface: `convergence_state`
- Symptom: accept-baseline rejects the authorized research file as path outside declared change set
- Evidence: Baseline allowed path is docs aggregate; command declared only docs/latest-100-commits-implementation-gap-research.md

## blk-aa7d40ffffa28b9a074a4896

- Status: `non-gap`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `discovery-check`
- Surface: `workspace-sandbox`
- Symptom: the exact discovery check cannot rewrite status metadata inside memory-knowledge under the default workspace sandbox
- Evidence: sequence_discovery_log.py check returned PermissionError after all 14 focused tests passed

## blk-ab2c26b9ffb045a799a5bcb9

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `record-cycle5-stage`
- Surface: `convergence-state-stage-envelope`
- Symptom: Cycle 5 stage envelope is rejected before its gap transition can be recorded
- Evidence: record-stage returned: record transition is missing required fields or evidence

## blk-ac4508f797ea8ec31f6b15df

- Status: `closed`
- Subject: `discovery-6c9c32b3-939c-54f1-8cff-5bd9758f8821`
- Step: `verify-reset-worker-tests`
- Surface: `reset-worker-regression-test`
- Symptom: focused-scheduler-test-observes-valid-started-receipt-and-fails-before-worker-finishes
- Evidence: pytest-assertion-started-not-in-complete-failed-after-waiting-only-for-receipt-existence

## blk-ac8e0fb8bf444adb3083e0b5

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `sealed-controller-correct`
- Surface: `discovery-bootstrap-task-namespace`
- Symptom: The recorded sealed-controller correction command hardcodes the original task ID and cannot load a successor run active state.
- Evidence: scripts/work_memory_bootstrap.py:_load_context reads classification, selection, and active receipts from /private/tmp/work-memory/<task-id> and compares state.task_id to that argument. v11 receipts and active state use unified-research-playbook-v2-final-v11-20260715; the failed command passed unified-research-playbook-v2-trust-reset-20260715.

## blk-ac99e130f7255ca34c0545ba

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `plan-stage-idempotency-retry`
- Surface: `convergence-state`
- Symptom: Corrected final verifier payload was rejected because the prior failed attempt reserved the same stage iteration attempt key
- Evidence: Attempt 1 payload changed only to satisfy the diagnosed owned-gap reconciliation contract

## blk-ad923f3eea2c6e9dbe1a38d5

- Status: `non-gap`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `start-durable-run`
- Surface: `work-memory-ledger-write`
- Symptom: run-start could not append its durable event inside the workspace sandbox.
- Evidence: Two sandboxed invocations returned PermissionError; the same command succeeded unchanged with approved elevated repository-write access.

## blk-ae9411e160019d27b47474d8

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `final-verification-remediation-read-state`
- Surface: `operator-tooling`
- Symptom: Attempted blocker_catalog show command is unsupported.
- Evidence: argparse returned invalid choice show and listed only open and transition.

## blk-af961444acabec745c386dab

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `final-strategy-runner-edit`
- Surface: `src/up_harness/engine/runner.py`
- Symptom: The combined runner patch was rejected before mutation because the touchpoint-status context did not match the current file.
- Evidence: apply_patch reported Failed to find expected lines; git worktree runner file remained unchanged by this patch.

## blk-afcfd0f40c6a94aee24a4339

- Status: `open`
- Subject: `discovery-681aa86a-0cde-5ed2-b8cf-615eef3bdb7d`
- Step: `run-start`
- Surface: `memory-knowledge-run-ledger`
- Symptom: The sandbox denied writing the governed run record
- Evidence: work_memory.py run-start returned PermissionError; the same command succeeded with scoped escalation

## blk-b0115258deb6307476c6ba9b

- Status: `superseded`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `verify-gh-auth`
- Surface: `github-auth`
- Symptom: Browser OAuth completed successfully but immediate gh auth status still rejects the active yourbteam credential
- Evidence: gh auth login exited 0 as yourbteam; gh auth status immediately exited 1 with token invalid

## blk-b0176e5e26eb3cd29ac2584b

- Status: `non-gap`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `sequence-selection`
- Surface: `work-memory-sequence-registry`
- Symptom: Automatic sequence selection returned five unrelated workflow sequences and no usable match
- Evidence: work_memory select returned callcenter-harness-provision-verify, greenfield-full-drive, mawf-playbook-blocker-reentry, mawf-playbook-full-test, and mawf-playbook-speed-test

## blk-b079618ade4b284b057b4d59

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `select-successor`
- Surface: `correction-lifecycle-transition`
- Symptom: The cumulative correction exists but its owning blocker remained open, so successor selection rejects it.
- Evidence: Correction f9d4b2bc-ba36-43ec-9219-463173d889e3 was recorded in v12 without --finalize-failed-run; work_memory.py only adds the open-to-fixed-awaiting-verification transition inside the finalizing branch. v12 was then closed before an explicit blocker transition.

## blk-b1f2f0ad31b74d513fee573a

- Status: `superseded`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `validate-staged-diff`
- Surface: `staged-markdown`
- Symptom: git diff --cached --check reports trailing whitespace in new durability research and plan documents
- Evidence: 20 header metadata lines reported across six staged Markdown files

## blk-b20bcf38ad8cb8de94e38208

- Status: `superseded`
- Subject: `discovery-223a62bb-62d5-5004-a1b6-cedb69d65585`
- Step: `open-blocker`
- Surface: `sequence-control`
- Symptom: blocker-entry-rejected
- Evidence: command-returned-subject-run-mismatch

## blk-b23549ebeec52ae32836f61d

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `foundation-focused-tests`
- Surface: `tests/unit/test_role_executor_usage.py`
- Symptom: The provenance unit test failed before exercising run_role_with_provenance because it assigned run_role on a frozen CommandRoleExecutor instance.
- Evidence: Bundled unittest: tests.unit.test_role_executor_usage.AggregateUsageTests.test_role_execution_keeps_provenance_outside_payload raised dataclasses.FrozenInstanceError at line 54.

## blk-b235c96f00f12bb4bf80c173

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `score-evaluation`
- Surface: `evaluation-planner-output-schema`
- Symptom: planner-outputs-pass-envelope-validation-but-scorer-rejects-first-planner-before-quality-scoring
- Evidence: scorer-calls-_evaluate_claims-for-every-record-and-requires-claims-and-material_gaps-before-role-branch

## blk-b2db18a08a6b0dde2751ebe8

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `verify-owner-question-contract-fix`
- Surface: `convergence-control`
- Symptom: The convergence baseline guard detected the approved source and test edits, but the focused test command still ran in the same orchestration cell.
- Evidence: guard-baseline returned BLOCKED with drift in src/up_harness and tests; the subsequent unittest command then ran and reported one fixture-mode failure.

## blk-b3501b51c123e69c94ad936a

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `reusable-live-model-canary-static-contract`
- Surface: `/Users/kamenkamenov/united-partners/scripts/run_cd_s_002_upgrade_canary.py`
- Symptom: the initial canary demanded controlled Q&A during discovery and could generate evidence below the owner-selected global proof threshold
- Evidence: build_strategy_profile emits guide/Q&A only for redraft; gate_platform_decisions applies the stronger of claim tier and owner threshold, while the initial _write_evidence used only claim.required_tier

## blk-b414456f2223b1be55e52624

- Status: `superseded`
- Subject: `discovery-promotion-lifecycle`
- Step: `sealed-protected-correct`
- Surface: `activated work_memory bootstrap snapshot`
- Symptom: The old sealed bootstrap passed command grounding but failed internally before recording the combined correction.
- Evidence: work_memory_bootstrap_launcher.py returned TypeError with exit code 5 for the exact grounded five-artifact correction command.

## blk-b436d06ac2e1f91e5df5fa40

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `legacy-research-fanout`
- Surface: `subagent-fanout`
- Symptom: duplicate-mixed-maturity-writer-created-after-batch-spawn-reported-thread-limit
- Evidence: hidden-agent-019f6263-9294-7110-9e62-72d32c9f10c3-completed-while-replacement-019f6266-44ab-7b60-a604-f33dbf3ed3ab-was-running

## blk-b4b8a6d8d7e16121e2f0d5b3

- Status: `fixed-awaiting-verification`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `final-live-canary`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/final_strategy.py`
- Symptom: The corrected source strategy and guide passed, but final strategy composition blocked because the controlled-Q&A output could not be reconstructed against the strategy draft.
- Evidence: Run up-run-c85238fe23f3 reports controlled_qna.status=invalid and final_strategy_validation issues exactly final_strategy_reconstruction_mismatch and controlled_qna_section_invalid; all prior phases are valid.

## blk-b4f5ebc96928c0f7b3e6a4a6

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `reproduce-final-strategy`
- Surface: `/Users/kamenkamenov/united-partners/src/up_harness/final_strategy.py`
- Symptom: The model followed the corrected empty-markdown compatibility contract, but the final-strategy envelope validator rejected the empty string.
- Evidence: Captured-input GPT-5.5 reproduction returned final_strategy_envelope_invalid; prompt requires markdown empty while validator still applies bool(payload[markdown]).

## blk-b5175d1c747569d56dc72408

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-implementation-src-baseline-write`
- Surface: `sandbox-filesystem-permission`
- Symptom: the guarded accept-baseline command could not create its atomic temp file under ~/.local/state in the default sandbox
- Evidence: PermissionError at tempfile.mkstemp under the convergence task state directory; identical escalated command returned expected baseline advanced

## blk-b6c4767a597d2556c8f0f00c

- Status: `superseded`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `discovery-activation`
- Surface: `sequence-guard`
- Symptom: the updated discovery bundle cannot activate
- Evidence: sequence_guard.py activate returned bootstrap-sources-not-selected after control dependencies were removed from the manifest

## blk-b7844825bd3857c3ce4176e3

- Status: `non-gap`
- Subject: `discovery-66c9c758-8b03-5e3b-9622-faa1044070c9`
- Step: `record-route-trace`
- Surface: `sequence_discovery_log.py append-step`
- Symptom: The route-trace evidence row was rejected because its command contained a literal Markdown table separator.
- Evidence: append-step returned invalid-command-row while all surrounding metadata commands succeeded.

## blk-b78810aeb63ca80f94f8cfe0

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `guard-taggable-api-deploy-command`
- Surface: `sequence-guard`
- Symptom: The guard rejected the runbook's documented PATH export plus deploy script as one executable command.
- Evidence: sequence_guard returned command-not-grounded-in-selected-document before scripts/deploy-api.sh ran.

## blk-b7cb84d572fd87609528a538

- Status: `closed`
- Subject: `discovery-3393078a-d255-508d-a718-2681b85c4a35`
- Step: `ground-full-evidence-command-set`
- Surface: `sequence_guard`
- Symptom: Guard rejects additional read-only Git evidence commands absent from the selected discovery log
- Evidence: Five guards returned command-not-grounded-in-selected-document

## blk-b804fe0116f66d43bc3f29ad

- Status: `open`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `controlled-topic-lock-threshold-fixture`
- Surface: `tests/integration/test_command_workflow.py`
- Symptom: the controlled-topic continuation remained provisional instead of locking
- Evidence: the test selected technical_artifact while claim-core requires and the fixture reports only internal_demo; the gate fail-closed path therefore rejects public use

## blk-b88f9146dd8fe5e2658b74f7

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `baseline-accept-research-protected-two-paths`
- Surface: `sequence-guard-receipt`
- Symptom: Sequence guard rejected the baseline-accept command before it could run.
- Evidence: sequence_guard.py guard and status both returned active-state-receipt-mismatch; no repository mutation occurred.

## blk-b97b15e62ab3407f777a271e

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `v2-init-state`
- Surface: `sequence_guard`
- Symptom: valid-package-controller-command-rejected-before-execution
- Evidence: shape-match-shlex-splits-entire-table-row-and-skips-unmatched-apostrophe

## blk-ba5f99c940a42174feb50a8a

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `verify-sequence-blocker`
- Surface: `sequence_guard`
- Symptom: The same-path blocker verification cannot run because the recorded run-verify step omits required blocker-id and correction-id arguments.
- Evidence: sequence_guard returned command-not-grounded-in-selected-document for work_memory.py verify with blocker and correction ids.

## blk-baa353d0d0094f7876f4806e

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `run-live-cd-s-002-upgrade-canary`
- Surface: `external-model-data-boundary`
- Symptom: The registered real gpt-5.5 canary was rejected before process start because it may send private United Partners workflow or client content to an external model service.
- Evidence: The execution reviewer rejected CreateProcess and explicitly confirmed that no safer-equivalent workaround may be used without informed user approval.

## blk-bab8ab59a58c3c3820a46f75

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `controller-regression-tests`
- Surface: `work-memory-bootstrap`
- Symptom: sealed-bootstrap-correction-raises-AttributeError-repo_roots_file
- Evidence: two-bootstrap-tests-failed-at-work_memory.py-line-1142

## blk-bafa8e18fbe41915ddc91924

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-implementation-src-baseline`
- Surface: `sequence-guard-discovery-grounding`
- Symptom: sequence_guard rejected the exact implementation accept-baseline command because only the docs variant is recorded
- Evidence: guard returned command-not-grounded-in-selected-document for changed-path src/up_harness and implementation approval

## blk-bb2b92399880db2d6bb72d9e

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `sgap-020-contradiction-scan`
- Surface: `shell`
- Symptom: A read-only contradiction scan executed backticked pattern fragments as shell commands.
- Evidence: zsh reported command not found: source_packet and command not found: document_ingestion while rg still ran with altered patterns.

## blk-bb67915ce02d51c967baa681

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `integrated-upgrade-workflow-retest`
- Surface: `CD-S-002 redraft source run`
- Symptom: The injected-executor redraft now starts phases but ends failed before the source platform completes.
- Evidence: Integrated test expected completed and observed failed after the preflight fix; phase error is not yet exposed by the assertion.

## blk-bb88cf3d20d1f0c1cf9bc31e

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `discovery-registry-isolation`
- Surface: `sequence-guard-receipt-chain`
- Symptom: discovery-guard-and-correction-bootstrap-both-return-stale-registry-receipt
- Evidence: selection-registry-hash-ab7a6f-no-longer-matches-SEQUENCES-after-unrelated-discovery-promotion-registration

## blk-bbb7b9dc36e2892544b9a95c

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `initialize-convergence-state`
- Surface: `convergence_state`
- Symptom: Convergence state initialization rejects the Markdown requirements file
- Evidence: requirement_map calls json.loads and raised JSONDecodeError at line 98

## blk-bbbb4bf424719d18aee18218

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `research-doc-gap-cycle-6-critic`
- Surface: `assessment-agent-sequence-boundary`
- Symptom: The read-only Cycle 6 critic produced no assessment because it tried to create a separate discovery log
- Evidence: Agent 019f5fd9-1a6f-7b21-9b22-abfe19a701fa returned: Assessment paused: the required sequence gate needs a discovery-log file

## blk-bc06b62295625775871d4361

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `verify-atomic-baseline-correction`
- Surface: `work-memory-ledger`
- Symptom: The ledger rejected valid same-path evidence because the successor selection did not bind the correction ID.
- Evidence: work_memory.py verify returned verification-correction-mismatch; selection showed verifies_correction_ids empty.

## blk-bc960ed5f920fb61a1be0165

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `managed-validation`
- Surface: `managed-skill-validator`
- Symptom: full pytest suite writes __pycache__ into managed skills/_shared and managed validation fails
- Evidence: validator reported skills/_shared/__pycache__/convergence_state.cpython-314.pyc after 740 tests passed

## blk-bcbf8be4d4d5ffe19b1f3773

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `v2-init-state`
- Surface: `v2-requirements-package-contract`
- Symptom: honest-parent-cannot-freeze-unknown-claim-values-or-add-them-after-core-without-scope-drift
- Evidence: create_state-hashes-entire-requirements-before-core-while-evaluator-load_v2_package-requires-research_value-and-evidence_ids-in-emitted-requirements

## blk-bd53f0c42db72f7f79b3e139

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `final-verification-remediation-guard-help`
- Surface: `operator-tooling`
- Symptom: Verification remediation help commands could not be guard-authorized with scripts/work_memory.py as source-ref.
- Evidence: sequence_guard returned source-ref-outside-selected-bundle for five command receipts; selected manifest covers only scripts/blocker_catalog.py.

## blk-bdb73fecb9f30ad4c3457a89

- Status: `non-gap`
- Subject: `discovery-promotion-lifecycle`
- Step: `verify-automation`
- Surface: `scripts/run_pytest.sh`
- Symptom: The documented repository test runner exits immediately with zsh permission denied.
- Evidence: Exact command scripts/run_pytest.sh tests/test_discovery_promotion_lifecycle.py tests/test_work_memory_bootstrap.py tests/test_sequence_guard.py returned exit code 126.

## blk-bdc091e901a4c2e6916360cb

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `guard-live-canary-baseline`
- Surface: `convergence-baseline`
- Symptom: The convergence guard blocked the live canary because verify_harness changed working hashes under scripts, src/up_harness, and tests after all deterministic checks passed.
- Evidence: guard-baseline reported scripts d169f51c..., src/up_harness 7ffd53db..., tests 2a81fe54... instead of the recorded hashes; docs and workflows remained unchanged.

## blk-bec03ce3f78be19efc3d30a1

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `guard-aggregate-verification`
- Surface: `sequence_guard`
- Symptom: The guard rejects the two-pair aggregate verification command because the discovery row describes repetition with bracket notation rather than an explicit executable shape.
- Evidence: sequence_guard returned command-not-grounded-in-selected-document for run-verify-all-corrections after the grouped selection and baseline passed.

## blk-bed4e799176d097207c61ecb

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `research-inventory-rerun`
- Surface: `sequence_guard`
- Symptom: sequence_guard rejected the absolute-path form of a logged repository inspection command
- Evidence: guard returned command-not-grounded-in-selected-document

## blk-beec5dbbd5bba52c387659f2

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `bind-research-internal-agent`
- Surface: `sequence_guard`
- Symptom: Concrete runtime agent ID fails guard although the discovery table declares --agent-id <agent-id>
- Evidence: _shape_match compares whole line token length; discovery command is embedded between Markdown table cells

## blk-bf148505c9528d2ef1e4a87e

- Status: `non-gap`
- Subject: `discovery-promotion-lifecycle`
- Step: `controller-regression-suite`
- Surface: `tests/test_discovery_promotion_lifecycle.py`
- Symptom: Two controller tests failed before command assertions because their declared changed artifacts did not exist.
- Evidence: 30 tests passed; test_correct_accepts_one_stable_artifact_manifest_argument and test_registered_correction_forwards_repository_roots raised changed-artifact-not-found from the new content-bound identity helper.

## blk-bfaccd0546fc71be51e67252

- Status: `open`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `coverage-vp2-run-start`
- Surface: `work_memory run-start`
- Symptom: Subagent cannot start the guarded read-only coverage audit run
- Evidence: work_memory.py run-start returned PermissionError after successful activation

## blk-c04206b1671a956e970f5d2d

- Status: `open`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `final-live-canary`
- Surface: `/Users/kamenkamenov/united-partners/scripts/run_cd_s_002_upgrade_canary.py`
- Symptom: The final synthetic-fixture canary was rejected before process creation because its generated UP workflow draft would be sent to external GPT-5.5.
- Evidence: The safety layer returned unacceptable risk and required fresh explicit user approval after disclosure; no canary process or model call started.

## blk-c2ac363470fe4bb0c1f97c4e

- Status: `non-gap`
- Subject: `discovery-e239c5e0-5bff-58b1-a62f-99f64e686baf`
- Step: `catalog-sandbox-boundary`
- Surface: `discovery-bootstrap-filesystem`
- Symptom: Bootstrap could not write its discovery bundle under the default workspace sandbox.
- Evidence: Corrected bootstrap exited 5 with PermissionError; the same command crossed the boundary and progressed under bounded write escalation.

## blk-c659e7c0c6c7ef43bc4130b0

- Status: `non-gap`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `research-doc-gap-attempt-3`
- Surface: `delegated-assessment`
- Symptom: Fresh assessor stopped before document review because it treated read-only evidence inspection as a separate operational sequence.
- Evidence: Stage envelope RDG-EXEC-001; active parent discovery lineage and run already govern this convergence task.

## blk-c6d54f9736b7c08a0c36d6be

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `parser-correction-verification-successor`
- Surface: `scripts/work_memory.py`
- Symptom: A correction-bound successor selection was rejected because correction 469fe5da was no longer in awaiting-verification state; stale activation and run start then failed closed.
- Evidence: Selection returned successor-correction-not-awaiting-verification; activation returned stale-source-bundle; run-start returned stale-selection-bundle. A subsequent normal selection feac5e55 activated and started run 1c11fa88.

## blk-c7c2be69cc786d528b8e7cf0

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `verifier-generated-output-baseline`
- Surface: `convergence-baseline`
- Symptom: Building the verifier changed bin and obj beneath the allowed verifier directory fingerprint
- Evidence: Only tools/Taggable.ReportExportVerifier directory hash differs after a successful build

## blk-c803fdecb7a9c864cf0210da

- Status: `closed`
- Subject: `discovery-04cf3898-8384-5912-9dbb-77f555ee1b22`
- Step: `inventory-authoritative-inputs`
- Surface: `sequence-guard`
- Symptom: The guard rejected the recorded read-only inventory command after the discovery log changed
- Evidence: sequence_guard.py returned stale-source-bundle immediately after append-step changed the selected discovery document

## blk-c820736fb9a7767bc974c37f

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `multi-supersession-focused-tests`
- Surface: `controller-regression-tests`
- Symptom: focused-suite-90-passed-2-failed
- Evidence: wrong-private-validator-name-and-old-generic-error-expectation

## blk-c94e16da740af387f954abdd

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `score-evaluation`
- Surface: `research-package-structured-claims`
- Symptom: The bounded evaluator rejected semantically correct yes/no conclusions because the package serialized them as explanatory strings instead of boolean values.
- Evidence: score verdict FAIL: complete critical recall was 6/8; the current-runtime v2 research and planner each preserved the material gap but missed both typed predicate values, while evidence, scope, maturity, budget, lifecycle, and planner rubric checks passed.

## blk-c95e0e5f249e5a8d337fe4d4

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `research-doc-gap-cycle-25-critic`
- Surface: `multi-agent-verifier`
- Symptom: Fresh Cycle 25 critic stopped before artifact inspection and asked to create orchestration files.
- Evidence: Agent 019f60f1-5406-7552-aa46-109e47d3b0a4 returned no PASS/GAPS result because it treated a new discovery log as mandatory, although discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa already exists.

## blk-c9dbe9aacced22115f59cb04

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `hardening-gate-1-closeout`
- Surface: `blocker_catalog`
- Symptom: catalog rejected direct transition of the corrected proof gap to closed
- Evidence: same-path verification event fe4b7c94-b91c-4f7c-80c0-30f5355bc2be exists; transition returned invalid-blocker-status-transition

## blk-ca14471bcd458665a94fcd79

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `blocker-remediation-proof`
- Surface: `sequence_discovery_log_cli`
- Symptom: sequence_discovery_log rejected verify because the supported validation subcommand is check
- Evidence: CLI returned valid choices start, append-step, set-inputs, set-failure-handling, set-verified-path, set-readiness, set-dependencies, check, backlog, closeout; no state changed

## blk-cabce4fb88dfed2ef99ff43a

- Status: `closed`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `discovery-readiness-check`
- Surface: `sequence-discovery-semantic-hash`
- Symptom: The readiness check rewrites discovery metadata and then rejects its own rewrite as a semantic bundle change.
- Evidence: After two same-bundle passed runs, sequence_discovery_log.py check returned helper-rewrite-changed-semantic-bundle; a subsequent run-start returned stale-selection-bundle and reselection changed the document SHA from 02e88303 to 2f811f21.

## blk-cac8b080c04cae568e377e05

- Status: `fixed-awaiting-verification`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `guard-before-research-internal`
- Surface: `convergence_state`
- Symptom: Baseline guard blocks reviewer spawn because docs working hash changed after creating the research artifact
- Evidence: Only docs working_hash changed; src/workflow_orch and tests hashes match baseline

## blk-cc19a00d79446695934e63ab

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `spawn-legacy-batch`
- Surface: `multi-agent-runtime`
- Symptom: six-agent-batch-partially-allocated-without-returned-ids
- Evidence: tool-returned-agent-thread-limit-reached

## blk-cc419900291a40c4cdb6c30f

- Status: `closed`
- Subject: `discovery-promotion-lifecycle`
- Step: `full-registered-verification`
- Surface: `tests/test_sequence_guard.py`
- Symptom: Three sequence-guard tests monkeypatch _repo_roots with a lambda that does not accept the new snapshot keyword.
- Evidence: Full registered suite failures raise TypeError: lambda() got an unexpected keyword argument snapshot.

## blk-cd779554e707f3293f2fa8f6

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `blocker-lifecycle-repair`
- Surface: `blocker-catalog-state-machine`
- Symptom: a prematurely fixed blocker cannot accept a correction or be superseded
- Evidence: correction returned correction-for-nonopen-blocker and superseded transition returned invalid-blocker-status-transition

## blk-cd84f039e5bf341d4c33259c

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-record-attempt-close-evidence`
- Surface: `research-package-controller-invocation`
- Symptom: record-attempt-rejected-status-word-as-file-path
- Evidence: controller-returned-cannot-read-json-from-completed

## blk-cda440c4512e21a084533710

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `record-correction`
- Surface: `work-memory-artifact-hashing`
- Symptom: package-cleanliness correction cannot be recorded using directory artifacts
- Evidence: work_memory.py correct accepts only existing files and rejected the skill directories

## blk-cdef1e7f5a85c9df3862a4fd

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `verifier-dotnet-runtime`
- Surface: `local-toolchain`
- Symptom: The real verifier project could not compile because dotnet is not on PATH
- Evidence: The guarded dotnet build command exited before compilation

## blk-ce2d5ffa0a4827ffa948b731

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `v2-package-state-init`
- Surface: `v2-parent-orchestration`
- Symptom: main-parent-cannot-guard-package-init-candidate-attempt-lens-adjudication-and-emission-commands
- Evidence: research_package.py-exposes-seven-stateful-subcommands-and-discovery-log-declares-none

## blk-ce862dc4e9fc566fe051b52a

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `terminal-plan-baseline-guard`
- Surface: `sequence-guard`
- Symptom: Sequence guard rejected the recorded convergence baseline command after the discovery source bundle changed.
- Evidence: sequence_guard returned {error: stale-source-bundle, ok: false}; convergence_state guard-baseline separately returned PASS and plan artifact validation passed.

## blk-ceac8a7820bd261da01932d7

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `independent-package-audit`
- Surface: `test_research_playbook_v2`
- Symptom: combined-retarget-test-stops-at-lens-mismatch-and-cannot-detect-later-binding-regressions
- Evidence: independent-auditor-cited-test-line-822-and-controller-lines-1001-and-1053

## blk-cedbcb5b263c5edd787331f0

- Status: `non-gap`
- Subject: `discovery-promotion-lifecycle`
- Step: `targeted-controller-regression`
- Surface: `uv cache initialization`
- Symptom: The sandboxed test process could not initialize uv's home-directory cache.
- Evidence: Failed to initialize cache at /Users/kamenkamenov/.cache/uv: Operation not permitted.

## blk-cf7c1d98acc835c31bc60947

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `record-cycle7-stage`
- Surface: `convergence-state-stage-envelope`
- Symptom: The Cycle 7 GAPS envelope was rejected before task state could record the verdict.
- Evidence: record-stage returned: stage result does not reconcile owned gaps; GAP-004 was assigned but absent from both open_gap_ids and closed_gap_ids.

## blk-d004263ef5a949460423d2f7

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `coverage68-artifact-read`
- Surface: `sequence-command-grounding`
- Symptom: guarded-read-commands-rejected-before-execution
- Evidence: four exact sed read commands were rejected by sequence_guard; no artifact reads executed

## blk-d12156f7ae4fec13960a0323

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `close-corrected-predecessor`
- Surface: `sequence-discovery-command-contract`
- Symptom: The correction predecessor cannot be closed because the exact run-close failed command is absent from the selected discovery table.
- Evidence: sequence_guard.py post-correction-bootstrap returned command-not-grounded-in-selected-document; correction 07aae488 is already recorded and no successor has started.

## blk-d1340c73e0b1366c8892439f

- Status: `closed`
- Subject: `discovery-promotion-lifecycle`
- Step: `correct-superseding`
- Surface: `scripts/work_memory.py::cmd_correct`
- Symptom: Even without redundant finalization, the canonical correction transaction rejects a replacement correction because its predecessor run is terminal.
- Evidence: Live screenshot correction command included --supersedes-correction-id and omitted --finalize-failed-run, but work_memory.py returned run-is-terminal.

## blk-d158c5eae27cc2ccab0ee8e2

- Status: `non-gap`
- Subject: `discovery-46914e3d-839f-54cc-9486-70411dd5299a`
- Step: `sequence-select`
- Surface: `work-memory discovery selection`
- Symptom: The selector rejected a discovery log stored outside the canonical repository
- Evidence: ValueError: temporary discovery log is not below /Users/kamenkamenov/memory-knowledge

## blk-d1b062d2207b8108d126a859

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `schema-remediation-record-candidate`
- Surface: `research-package-cli-grounding`
- Symptom: record-candidate-could-not-read-AVAILABLE-as-file
- Evidence: controller-returned-cannot-read-JSON-from-AVAILABLE

## blk-d204b870a2c4b98d1f9b144c

- Status: `superseded`
- Subject: `discovery-b6658d35-7870-5d15-9f4b-d316138cec83`
- Step: `controller-bootstrap`
- Surface: `discovery-promotion-lifecycle`
- Symptom: The controller status query rejected a valid discovery before it could create the first qualification run.
- Evidence: The guard-authorized drive command returned discovery-not-bound-to-run before promotion state changed.

## blk-d21c0ebd786c4a0296922eef

- Status: `closed`
- Subject: `discovery-promotion-lifecycle`
- Step: `independent-review-iteration-2`
- Surface: `discovery-promotion-lifecycle`
- Symptom: A failed successor can be retried before its new blocker is corrected, and correction evidence can omit files that changed in the selected bundle.
- Evidence: Iteration-2 reviewer and critic confirmed REV-LIFECYCLE-001 and REV-LIFECYCLE-002 remain FIX NOW; prior correction omitted changed work_memory_bootstrap.py.

## blk-d24a1a03828787308684c55f

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `guard-baseline-approval-command`
- Surface: `sequence_guard`
- Symptom: The guard rejects the generic autonomy-approval row when the actual command contains JSON scope lists and evidence text.
- Evidence: sequence_guard returned command-not-grounded-in-selected-document before grant-approval executed.

## blk-d2a5dd8faec5309d0df3edd2

- Status: `superseded`
- Subject: `discovery-promotion-lifecycle`
- Step: `correct-superseding`
- Surface: `scripts/discovery_promotion_lifecycle.py`
- Symptom: A valid superseding correction request fails before recording because the controller passes the old correction id as the new correction id.
- Evidence: Controller emitted work_memory.py correct with both --correction-id e7174b34-c65c-50f6-9d83-27ce1aa7c056 and --supersedes-correction-id e7174b34-c65c-50f6-9d83-27ce1aa7c056; work_memory returned correction-id-conflict.

## blk-d35e3271969ce26b019e946f

- Status: `superseded`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `run-live-cd-s-002-upgrade-canary`
- Surface: `compose-llm-strategy-brief`
- Symptom: The real gpt-5.5 CD-S-002 canary failed while composing the strategy brief because owner-question line 106 violated the canonical format.
- Evidence: Canary exit 1 for run up-run-87d9d0de034b: compose-llm-strategy-brief failed with owner_questions_invalid_line:106.

## blk-d40f117232b9bc5dbc69a283

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-combined-tests`
- Surface: `work-memory-successor-validation`
- Symptom: The carried-correction raw-byte check leaks missing-dependency when the corrected artifact is absent.
- Evidence: tests/test_work_memory.py::test_successor_rejects_bundle_drift_after_recorded_correction failed; 218 sibling tests passed.

## blk-d5089d868945bf418fa33010

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-package-emission-adjudicated-pass`
- Surface: `skills/research-playbook-v2/scripts/research_package.py`
- Symptom: A research state can be canonically PASS after adjudication rejects false raw findings, but emit_package still rejects it because one provisional lens verdict was GAPS or BLOCKED.
- Evidence: research_package.py lines 1518-1521 require every raw lens verdict to equal PASS, while record_adjudication and validate_state now derive PASS from canonical adjudicated dispositions; current-runtime and scope-inflation-trap are concrete PASS states containing rejected provisional findings.

## blk-d57e2a603a4601edec37d389

- Status: `non-gap`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `final-v3-mixed-internal-lens-input-contract`
- Surface: `/private/tmp/research-playbook-v2-eval-20260715-final-v3/v2-work/mixed-maturity/internal-readiness-output.json`
- Symptom: The mixed-maturity INTERNAL_READINESS lens returned BLOCKED with zero findings because it treated raw file hashes as the supplied identity hashes and could not resolve relative skill references.
- Evidence: Agent final reported input hashes mismatched and references absent. Controller hash-json proves candidate canonical 8a32ea... versus file 1d2d01..., and envelope canonical 0dd758... versus file 3396a0...; the supplied hashes are correct under sha256-canonical-json-utf8-no-trailing-newline-v1.

## blk-d587d0712325d53c39d072c3

- Status: `fixed-awaiting-verification`
- Subject: `discovery-681aa86a-0cde-5ed2-b8cf-615eef3bdb7d`
- Step: `sequence-selection`
- Surface: `local-codex-remote-control-identity`
- Symptom: Sequence selection offered two unrelated auth workflows for a cloned Codex installation ID reset
- Evidence: work_memory select returned ambiguous-sequence with claude-auth-token-refresh and remote-mcp-user-onboarding

## blk-d6114f9536fb3a57af3c0cb4

- Status: `closed`
- Subject: `discovery-e239c5e0-5bff-58b1-a62f-99f64e686baf`
- Step: `final-review`
- Surface: `promotion-controller-fail-closed-boundary`
- Symptom: Final review found that pre-apply failures can leave staging or partial backup state, and a recomputed plan can redirect tracked path values.
- Evidence: apply_plan stages before its cleanup try; create_backup failure leaves backup_root when manifest assignment never completes; validate_preconditions compares only tracked key sets rather than each planned path to tracked_paths(repo_root, installed_root).

## blk-d6588c5770330e723c81c152

- Status: `fixed-awaiting-verification`
- Subject: `discovery-8fb5c613-edd8-567b-97e5-bf4940b6c397`
- Step: `activate-sequence-guard`
- Surface: `work-memory sequence setup`
- Symptom: sequence guard activation could not see the selection bootstrap state
- Evidence: activate returned bootstrap-sources-not-selected after selection; run-start was launched concurrently

## blk-d744bd7251029dd92f30e887

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `lens-verdict-contract`
- Surface: `research-playbook-v2-lens-contract`
- Symptom: honest-lenses-cannot-terminate-planner-ready-packages-with-known-planning-gaps
- Evidence: missing-runtime-and-requirement-conflict-cases-returned-GAPS-for-HANDOFF_TO_PLANNER-findings

## blk-d82b3f505167055e2e838202

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-canary-script-baseline`
- Surface: `/Users/kamenkamenov/united-partners/scripts/run_cd_s_002_upgrade_canary.py`
- Symptom: sequence guard rejected the approved scripts baseline transition because the selected bundle contains the placeholder canary while the worktree contains the implemented driver
- Evidence: sequence_guard returned exit 4 with {error: stale-source-bundle, ok: false}

## blk-d830b3f69e35fb5ef45d512e

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `full-suite-dependency-manifest`
- Surface: `discovery-dependency-manifest`
- Symptom: successor-selection-rejected-correction-artifact-outside-bundle
- Evidence: test-scoped-git-publish-and-test-sequence-promote-omitted-from-dependencies

## blk-d86cae24cc9d226e25254c49

- Status: `non-gap`
- Subject: `discovery-candidate-reconciliation`
- Step: `audit-candidates`
- Surface: `operations/sequences/discovery/2026-07-15-discovery-candidate-reconciliation.dependencies.json`
- Symptom: The promoted reconciliation discovery log is quarantined because its historical manifest declares scripts/run_pytest.sh directly and also receives it transitively from discovery-promotion-lifecycle.
- Evidence: Schema-3 audit row reports duplicate-bundle-file; the discovery sidecar contains both discovery-promotion-lifecycle and direct scripts/run_pytest.sh, while the registered target resolves and is current.

## blk-d86d592cdcf8ddaea9a63b8e

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `resume-main-research`
- Surface: `work_memory_cli`
- Symptom: blocker catalog rejected an attempted write to a closed verification run
- Evidence: catalog returned event-after-terminal for run a26a9b4f-052c-4623-9d8e-78c83b6378d9

## blk-d950859cd05e764e4f7a7ace

- Status: `open`
- Subject: `discovery-6c9c32b3-939c-54f1-8cff-5bd9758f8821`
- Step: `inspect-remote-control-processes`
- Surface: `sequence-guard-command-shape`
- Symptom: duplicate-process-inspection-command-rejected-before-execution
- Evidence: sequence_guard-returned-invalid-guarded-command-for-ps-pipe-rg

## blk-d9c6f4df2bd8c81ca0333228

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `consolidate-active-corrections`
- Surface: `work_memory`
- Symptom: The final bundle cannot supersede older active corrections because their blockers are fixed-awaiting-verification rather than open.
- Evidence: work_memory.py correct returned correction-for-nonopen-blocker before recording any correction.

## blk-da3a13f7ac987acbdc9b0ff3

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `implementation-baseline-progression`
- Surface: `convergence-baseline`
- Symptom: The mandatory pre-edit guard rejected the first approved implementation changes inside allowed paths
- Evidence: Drift output lists only Taggable.Api.sln, the two approved report files, new helper, AssemblyInfo, and verifier directory

## blk-db7492776918c481f8ae5f15

- Status: `non-gap`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `v2-current-runtime-research`
- Surface: `delegated-v2-orchestrator`
- Symptom: delegated-v2-executor-returned-blocked-without-package
- Evidence: agent-019f6270-8e53-73e0-b35a-7d62ee686bfb-reported-no-spawn-wait-close-tools-and-skill-lines-10-14-require-parent-level-tools

## blk-dc41c036a1fe1ec55b299052

- Status: `closed`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `review-manifest-missing-correction-linkage`
- Surface: `work-memory-blocker-lifecycle`
- Symptom: The repaired manifest blocker cannot advance to verified through the successor protocol
- Evidence: blk-8e transitioned open to fixed-awaiting-verification before work_memory correct succeeded; lifecycle forbids correction_recorded unless blocker status is open

## blk-dca5fd26c3e53a6ce193f940

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `close-correction-run`
- Surface: `operations/work-memory/events.jsonl`
- Symptom: The correction run could not be closed because the active workspace sandbox denied writes to the memory-knowledge ledger.
- Evidence: work_memory.py run-close returned PermissionError before emitting a run_closed event.

## blk-dec6a4256092a99c8ed3fa04

- Status: `open`
- Subject: `discovery-b85c4483-4f52-5290-9e2e-7f54ca3c49aa`
- Step: `discovery-log-start`
- Surface: `sequence-runner`
- Symptom: The mandatory source-review discovery sequence initially could not be created
- Evidence: sequence_discovery_log.py start returned PermissionError under workspace sandbox

## blk-df9ecc20de8e883a358c1edf

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `sequence-selection-bootstrap`
- Surface: `work-memory-selection`
- Symptom: Automatic selection offered only unrelated workflow sequences for the spreadsheet repair
- Evidence: work_memory.py select returned five unrelated workflow-drive sequence ids before any product command ran

## blk-e09ed3e7b6e42e86da08b5cd

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `correction-successor-selection`
- Surface: `scripts/work_memory.py`
- Symptom: A correction-bound successor could not start because the blocker catalog still showed the corrected blockers as open.
- Evidence: BLOCKERS.md showed blk-1a151c7dd05870d0e8f57c60 and blk-6e51c6e83cd6ea138ff85d3a status open after work_memory.py correct; the discovery sequence already requires an explicit fixed-awaiting-verification transition.

## blk-e23a8093a7a470d019ea146c

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-init-state`
- Surface: `selected-source-bundle-v15`
- Symptom: The first clean-state replay guard rejected v15 as stale after another process restored sequence_guard.py and tests/test_sequence_guard.py to earlier bytes.
- Evidence: v15 selected sequence_guard.py=1d1bd5db84f434fd0e0cefa154f1f29c7636d38c3f0491ecb4beae414f20a600 and tests/test_sequence_guard.py=66e853403832f31ee7acdcc27d6b808b59c59788b7f6f2d31541e8351c8efbd6; current stable hashes are 42518faba590693dbfdb06e360e32c50d084d06e4729c715fe48c84be8365cef and bd4476016db727cd3d17a741df70af19d7cec2e1d7bc71f23d9dbcadaa1a748c. The fail-closed replay wrote zero state files.

## blk-e2959c49b9463620770cc809

- Status: `superseded`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `discovery-check`
- Surface: `sequence-discovery-log`
- Symptom: discovery check cannot resolve a manifest dependency stored in mcp-agents-workflow
- Evidence: sequence_discovery_log.py _bundle calls work_memory.resolve_bundle without a repo-roots file; check returned missing-repository-root

## blk-e3e8339cdc5096a5c6d991cc

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `verify-correction-lineage`
- Surface: `work_memory`
- Symptom: The corrected successor run cannot verify the registration correction because its selection receipt contains no verifies_correction_ids.
- Evidence: work_memory.py verify returned verification-correction-mismatch; the current selection output showed verifies_correction_ids: [] and predecessor_run_id: null.

## blk-e4f09a3292c8356d5c90b664

- Status: `fixed-awaiting-verification`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `accept-authorized-dirty-research`
- Surface: `convergence-baseline`
- Symptom: The convergence helper cannot acknowledge an authorized edit to the pre-existing untracked research artifact.
- Evidence: cmd_accept rejects any protected dirty path unless --accept-generated-overlap, then hard-limits that exception to AGENTS.md; source lines 319-330.

## blk-e5d7ebfe4777d398830ddf6f

- Status: `open`
- Subject: `discovery-e9f998db-d24a-5932-90e8-c9ca2678c4ef`
- Step: `record-locate-runtime`
- Surface: `sequence_discovery_log`
- Symptom: The discovery logger rejected an rg alternation command as an invalid command row
- Evidence: append-step returned invalid-command-row for an rg pattern containing pipe alternation

## blk-e633458a1b6db8fc98b5e2da

- Status: `superseded`
- Subject: `discovery-a55832eb-534e-5813-b755-dfc6cb73bf75`
- Step: `inspect-isolated-conflicts`
- Surface: `memory-knowledge-origin-main`
- Symptom: The isolated rebase identified four exact conflicts: ledger, generated blocker view, work-memory controller, and blocker-catalog tests.
- Evidence: conflict_paths were operations/blockers/BLOCKERS.md, operations/work-memory/events.jsonl, scripts/work_memory.py, tests/test_blocker_catalog.py; temporary rebase aborted and restored HEAD.

## blk-e70ef0c4bd678413b7dfe416

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `schema-remediation-replay-grounding`
- Surface: `sequence-guard-command-source`
- Symptom: temporary-reproduction-script-rejected-before-execution
- Evidence: sequence-guard-returned-source-ref-outside-selected-bundle

## blk-e730851043677c62164ab745

- Status: `open`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `activate-sequence`
- Surface: `work-memory sequence activation`
- Symptom: The read-only plan-verification sequence could not activate until directive-read state was refreshed.
- Evidence: Initial sequence_guard.py activate exited nonzero with the exact stale directive-read message; documented directive_guard read then made activation pass.

## blk-e7e5fae5456b377e6fe909f2

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `score-evaluation`
- Surface: `evaluation-legacy-output-schema`
- Symptom: locked-score-rejected-first-legacy-output-before-quality-scoring
- Evidence: scorer-returned-unsupported-output-schema-current-runtime-legacy-research

## blk-e9b0b0f06d71257e62fc7636

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `blocker-lifecycle-recovery`
- Surface: `blocker_catalog.py`
- Symptom: The corrected approval blocker remains open after same-path verification because the failed run was closed before its fixed-awaiting transition
- Evidence: blocker_catalog transition on run 3bfc... returned event-after-terminal; BLOCKERS.md still reports blk-9ee... open

## blk-ea3b738004a3710d38bea800

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `verify-plan-helper-dependency`
- Surface: `sequence-selection`
- Symptom: Sequence selection rejected the required verify-plan ledger helper
- Evidence: Discovery log references /Users/kamenkamenov/.codex/skills/verify-plan/scripts/verification_ledger.py while dependencies manifest is empty

## blk-eb0e284eb68069e05306fdcb

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `advance-convergence-baseline`
- Surface: `convergence-control`
- Symptom: The approved baseline advancement could not atomically write the convergence state file.
- Evidence: PermissionError opening /Users/kamenkamenov/.local/state/kamen-convergence/up-harness-cd-s-002-upgrades-20260714/.convergence-*.tmp.

## blk-edc8fa1326f247b90486b412

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-controlled-topic-src-tests-baseline`
- Surface: `convergence_state`
- Symptom: atomic expected-state update could not create its temporary file under ~/.local/state
- Evidence: convergence_state.py raised PermissionError at tempfile.mkstemp after sequence_guard passed

## blk-ee739a200d37bacf4b26b1fa

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `work-memory-pytest-dev-extra`
- Surface: `memory-knowledge-test-runner`
- Symptom: The focused helper reproduction could not start because the default uv environment omits pytest
- Evidence: pyproject declares pytest only in project.optional-dependencies.dev and uv run pytest exited 2 with Failed to spawn pytest

## blk-f1a0eb4cedf8520c60a7cec7

- Status: `non-gap`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `final-v3-adjudication-record-contract`
- Surface: `/private/tmp/research-playbook-v2-eval-20260715-final-v3/v2-work/current-runtime/adjudications.json`
- Symptom: Three adjudicators emitted summary records with finding_id/fingerprint/rationale instead of controller-valid records embedding each exact raw_finding plus finding_type, materiality, and disposition.
- Evidence: current record-adjudication returned every adjudication must include raw_finding; current, missing-runtime, and requirement-conflict output keys omit raw_finding, finding_type, and materiality. Scope-inflation output is valid empty list.

## blk-f1daa02c7ecff0e8c81f39e8

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `product-repository-roots-bundle`
- Surface: `operations/sequences/discovery/2026-07-14-up-harness-cd-s-002-live-verification.dependencies.json`
- Symptom: The roots-manifest correction could not be recorded because the new file was outside the discovery dependency bundle.
- Evidence: work_memory.py correct returned correction-artifact-drift-mismatch after both the log and repositories JSON were named as changed artifacts.

## blk-f239f184dbe0cf9c9a8f4f36

- Status: `non-gap`
- Subject: `discovery-8f6f0b9b-0174-5840-b07e-f61d9ed1acf4`
- Step: `blocker-remediation-proof-check`
- Surface: `sequence_discovery_log_cli`
- Symptom: supported discovery-log check could not refresh canonical state under the default sandbox
- Evidence: python3 scripts/sequence_discovery_log.py check returned PermissionError and no state change

## blk-f2a7a53d16490f32d20f4946

- Status: `closed`
- Subject: `discovery-promotion-lifecycle`
- Step: `verify-automation`
- Surface: `discovery-promotion-lifecycle`
- Symptom: The documented same-path verification command failed.
- Evidence: The guarded verification command exited 1; output remains in the operator terminal.

## blk-f2f9e61bef174c8ed44d9588

- Status: `non-gap`
- Subject: `discovery-f4cf2e8f-5fd3-5fc0-9b2a-54e3c9ad8ccd`
- Step: `verify-directive-receipt-fix`
- Surface: `work-memory-ledger`
- Symptom: same-path verification for the repaired directive blocker was rejected because no correction id was paired
- Evidence: work_memory.py verify returned paired-correction-blocker-required

## blk-f33ebd6cfa377a6c074f6a25

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-emit-package`
- Surface: `current-runtime-evidence-index-input`
- Symptom: first-final-package-emission-rejected-before-output
- Evidence: controller-returned-invalid-operation-evidence-index-item-zero-invalid-fields

## blk-f33fe9c4a8bdb4568e7c0be8

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `baseline-capture-cssm-warning`
- Surface: `bundled-dotnet-runtime`
- Symptom: The successful baseline capture emitted a macOS CSSM module-load warning
- Evidence: The verifier still reported both immutable baselines captured and exited successfully

## blk-f39166919cfa090c3e395199

- Status: `superseded`
- Subject: `discovery-a55832eb-534e-5813-b755-dfc6cb73bf75`
- Step: `inspect-isolated-conflicts`
- Surface: `scripts/scoped_git_publish.py`
- Symptom: The isolated rebase abort reports the failed commit but omits the exact unresolved file paths.
- Evidence: Live failure named commit 4056fc6 and restored temporary HEAD but did not return conflict_paths.

## blk-f4c40d29a989efeb555a7c19

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-record-attempt`
- Surface: `selected-source-bundle-v14`
- Symptom: The v14 source receipt became stale before coverage attempt recording, and the batch orchestration executed six state writes despite six failed guards.
- Evidence: v14 selected scripts/sequence_guard.py=42518faba590693dbfdb06e360e32c50d084d06e4729c715fe48c84be8365cef and tests/test_sequence_guard.py=bd4476016db727cd3d17a741df70af19d7cec2e1d7bc71f23d9dbcadaa1a748c; current hashes are d004942ecab3f87354856057039896c792090ef064b61aced721bbc5dae36fa0 and 66e853403832f31ee7acdcc27d6b808b59c59788b7f6f2d31541e8351c8efbd6. All six guard calls returned stale-source-bundle, but the JS batch did not gate execution on their exit codes.

## blk-f5083c31ebd4f7e372ef2c7b

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `prepare-evaluation-command-contract`
- Surface: `sequence-discovery-contract`
- Symptom: fresh-blind-lock-cannot-be-created-through-recorded-command
- Evidence: discovery-table-has-record-and-score-but-no-prepare

## blk-f5b0232da20b663738c6e583

- Status: `closed`
- Subject: `discovery-promotion-lifecycle`
- Step: `correct-superseding`
- Surface: `scripts/discovery_promotion_lifecycle.py`
- Symptom: A replacement correction is generated correctly but the wrapper always passes --finalize-failed-run, even when the stale correction already finalized that run.
- Evidence: Screenshot discovery correction attempt returned run-is-terminal before recording correction 9f1895dc-db28-57fa-a940-15259fa4961e.

## blk-f65fdb80e74569a77dd38c68

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `abandon-stranded-predecessor`
- Surface: `scripts/sequence_guard.py`
- Symptom: run-abandon-rejected-before-execution
- Evidence: first-guard-missing-exact-help-shape-and-followup-shell-tokenization-errors

## blk-f688fe246d4cbc81e600ece8

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `restore-preinstall`
- Surface: `codex-managed-skill-installation`
- Symptom: selected-discovery-cannot-restore-sealed-baseline
- Evidence: sealed-snapshot-diff-and-recovery-artifacts-confirmed

## blk-f6b81fcc2c8624973af9c381

- Status: `non-gap`
- Subject: `discovery-e239c5e0-5bff-58b1-a62f-99f64e686baf`
- Step: `catalog-undeclared-executable`
- Surface: `discovery-bootstrap-manifest`
- Symptom: Bootstrap rejected an executable named by the discovery document but absent from its dependency manifest.
- Evidence: Escalated bootstrap exited 3 with executable-outside-manifest::scripts/run_pytest.sh; declaring the existing script made the same path pass.

## blk-f70c149b27319d28eb799c3b

- Status: `fixed-awaiting-verification`
- Subject: `discovery-6c9c32b3-939c-54f1-8cff-5bd9758f8821`
- Step: `activate-remote-control-after-regeneration`
- Surface: `codex-remote-control`
- Symptom: remote-control-activation-still-fails-after-codex-restart
- Evidence: active-installation-id-exists-and-differs-byte-for-byte-from-pre-clone-backup

## blk-f7316d2a4c12acf443b3f54c

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `activate-live-verification`
- Surface: `control-plane`
- Symptom: Activation rejected the retired explicit discovery sequence-id argument.
- Evidence: sequence_guard.py returned activation-sequence-id-retired:run-work_memory-select-then-pass-selected-document.

## blk-f74c1079c548e9e2f714a4ba

- Status: `closed`
- Subject: `discovery-candidate-reconciliation`
- Step: `execute-rolling`
- Surface: `scripts/discovery_candidate_reconciliation.py:command-surface`
- Symptom: The successful rolling cleanup required ad hoc orchestration around audit, semantic comparison, manifest construction, retry, execution, and post-audit stability.
- Evidence: Run 3b43fa64 executed 49 rows successfully, but the controller exposes only audit, validate, and execute; the approved rolling retain-only gate and retry semantics are absent from the registered command table.

## blk-f774b622fcd9e5d112a02346

- Status: `open`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `transition-verified`
- Surface: `work_memory`
- Symptom: atomic-verification-event-cannot-transition-two-valid-carried-blockers
- Evidence: validator-line-432-requires-immediate-predecessor-despite-selected-correction-set-and-current-bundle

## blk-f813407233632962f7bda14b

- Status: `non-gap`
- Subject: `discovery-cf976104-9e51-5bbd-83e0-83a396426eef`
- Step: `select-discovery-log`
- Surface: `work_memory discovery selection`
- Symptom: Selection rejected a discovery log rooted in /private/tmp with pathlib.relative_to(ROOT) ValueError
- Evidence: scripts/work_memory.py resolve_bundle lines 579-585 require discovery documents and manifests below canonical ROOT; canonical-root selection then succeeded

## blk-f92429b3b2b961c059641f99

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `non-reusable-correction-successor-selection`
- Surface: `scripts/work_memory.py`
- Symptom: A second successor selection was attempted for a correction recorded with reusable_behavior_changed=no and was rejected; dependent activation/start failed closed.
- Evidence: Correction b1c73f41 had no eligible_corrections entry; successor selection returned successor-correction-not-awaiting-verification. Normal selection 6ea364f7 started run 859be192.

## blk-f9342af8345d9a7267cea922

- Status: `fixed-awaiting-verification`
- Subject: `discovery-e78611ed-2903-5b35-9fa2-142b91bcebc3`
- Step: `inspect-repository-ancestry`
- Surface: `sequence-guard`
- Symptom: Every newly appended Git ancestry inspection command is rejected by sequence_guard.py with stale-source-bundle.
- Evidence: Four independent guard calls returned error=stale-source-bundle and exit code 4 after the discovery log gained the new command rows.

## blk-f9bf87fafc029f0cc74176cd

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `ground-research-commands`
- Surface: `sequence-discovery-log`
- Symptom: Embedded pipe and alternation characters executed while recording commands instead of remaining command text
- Evidence: zsh reported command not found for agent_slot_ledger.py, numeric, mssql, Excel, Net, OperatorPayout, and sequence_discovery_log.py reported missing --result

## blk-fa58d7cb2c1bb3bbcb0ddb04

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `verify-pre-snapshot-parser-fix`
- Surface: `scripts/work_memory.py`
- Symptom: The ledger refused a verification-only event because the blocker has no correction paired to this roots-aware run.
- Evidence: work_memory.py verify returned paired-correction-blocker-required for blk-8d00495043a7badd2b1a94c4.

## blk-fa87299b96d3612464af01ca

- Status: `fixed-awaiting-verification`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `convergence-state-check-plan-gate`
- Surface: `convergence-state-artifact-lineage`
- Symptom: convergence_state.py check reports eight research stage artifact hash drift errors
- Evidence: research artifacts were revised by later approved hardening passes while earlier stage records retained path-derived artifact ids and intermediate hashes

## blk-fba0c1c0a50ead2c944c3015

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `red-before-reproduction-launcher`
- Surface: `uv-offline-launcher`
- Symptom: The corrected isolated reproduction command panics in uv before pytest starts in the parent execution environment.
- Evidence: uv exited 101 in system-configuration dynamic_store.rs with Attempted to create a NULL object and Tokio executor failed; no test was collected.

## blk-fbf6dd86c948d16fcb580969

- Status: `non-gap`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `mixed-maturity-round2-time-cap`
- Surface: `/private/tmp/research-playbook-v2-eval-20260715-final-v2/v2-work/mixed-maturity/state.json`
- Symptom: The mixed-maturity revision-2 candidate cannot be recorded because the case state reached its one-hour TIME_BUDGET while controller and package-contract blockers were remediated.
- Evidence: record-candidate returned verdict CAP_REACHED, reason TIME_BUDGET, candidate_hash null; state started 2026-07-15T08:23:24Z with deadline 2026-07-15T09:23:24Z.

## blk-fc2aae96b1dcd9b87fa043ec

- Status: `open`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `full-unit-suite-publication-compatibility`
- Surface: `tests/unit/test_workflows.py`
- Symptom: A legacy unit test raised KeyError because a blocked required-live run no longer writes the published llm_strategy_brief key before publication.
- Evidence: test_required_live_strategy_brief_blocks_without_command_executor failed at test_workflows.py:156; 185 other unit tests passed and all 22 integration tests passed.

## blk-fc97747daa4d144b7d7759b7

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `activate-verification-successor`
- Surface: `sequence-guard-activation`
- Symptom: Verification successor could not activate because the command supplied the retired discovery lineage id as sequence-id.
- Evidence: sequence_guard.py returned activation-sequence-id-retired:run-work_memory-select-then-pass-selected-document

## blk-fc99c032ad54102e89b3e73b

- Status: `verified`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `revalidate-live-canary-command`
- Surface: `selected-source-bundle`
- Symptom: The informed-approved live canary remained unable to start because sequence_guard found the active selected source bundle stale.
- Evidence: sequence_guard returned stale-source-bundle before dispatch; convergence guard still passed for the UP repository.

## blk-fd3cc7b777171aaaabc2481d

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `supersede-stale-baseline-correction`
- Surface: `memory-knowledge/scripts/work_memory.py`
- Symptom: A shared work-memory controller change appeared after successor selection, so correction recording sees unrelated artifact drift.
- Evidence: Selected hash ebbfdc...; current hash a1091c...; git diff adds preservation of prior verification_quality when cmd_correct closes a run.

## blk-fdd74263e18a0e14686911bc

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-record-attempt`
- Surface: `selected-source-bundle-v11`
- Symptom: The v11 source receipt no longer matches the controller bytes before completed lens results can be recorded.
- Evidence: Selected scripts/work_memory.py=f3da696e4a92648f40b5dc2d5325cf437cecc9c6432b10c81da97de8fac18b64 and tests/test_work_memory.py=dc73786b1d734b167a920eb09c3f01849eee1c8fe99a6f00a37b052de78ac677; current scripts/work_memory.py=d287d1101e05a66e7c51c27fde3b2524f5c4943a147242422714089d06f65f49 and tests/test_work_memory.py=c1594e411c4144280bf6f2aafe023faee435f9125eb70891a332a2e6903fcfad. The current revision adds subject-document resolution through the matching dependencies manifest and lineage plus regression coverage.

## blk-fe72934a138ce48d2c6e84b0

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `focused-suite-concurrent-work-memory-drift`
- Surface: `scripts/work_memory.py`
- Symptom: The broader controller/bootstrap suite has six failures before v2 code runs because legacy one-argument _repo_roots monkeypatches reject the new snapshot keyword.
- Evidence: Current scripts/work_memory.py and tests/test_work_memory.py hashes exactly match correction aed4a49c-4369-40bb-97de-ba95efd886a2; six failures report unexpected keyword argument snapshot in tests/test_work_memory.py, tests/test_sequence_guard.py, and tests/test_work_memory_bootstrap.py.

## blk-ffc10318728bf2a91bccb2b2

- Status: `non-gap`
- Subject: `discovery-promotion-lifecycle`
- Step: `full-registered-verification`
- Surface: `tests/test_work_memory.py::test_registry_and_manifest_coverage`
- Symptom: Registered sequence taggable-api-authed-endpoint-verify has no dependencies.json.
- Evidence: Full registered suite: 139 passed, 4 failed; registry coverage reports the missing manifest path.
