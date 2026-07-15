# Work Blockers

Ledger-SHA256: `c0fa8e419ca9e76128328936c66d1ce68818b17784959674ddc2e97acc17ab78`

This file is generated from `operations/work-memory/events.jsonl`.

## blk-009c8ce9f003444c10d61c2f

- Status: `closed`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `correction-external-repo-root-loss`
- Surface: `work-memory-correction-ledger`
- Symptom: The manifest correction was proven by exact selection but the correction ledger rejected recording it
- Evidence: cmd_correct calls resolve_bundle without the selection repo-roots file and returned missing-repository-root after codex-skills dependencies were declared

## blk-016a972d134f32eaffd58e98

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `guard-registered-deploy-run-start`
- Surface: `sequence-guard`
- Symptom: The registered deploy run-start guard omitted the mandatory source reference.
- Evidence: argparse rejected the guard before validation and printed that --source-ref is required.

## blk-01fb8f61bf3ddba46341a3ec

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-dependency-scope`
- Surface: `operations/sequences/discovery/2026-07-15-unified-research-playbook-v2-trust-reset.dependencies.json`
- Symptom: A concurrent change to tests/test_scoped_git_publish.py invalidated the v2 successor even though scoped publishing is outside the v2 research-playbook evaluation.
- Evidence: The exact current-vs-selected bundle diff contained the two intended v2 replay files plus tests/test_scoped_git_publish.py; no v2 source or evaluator path depends on that test.

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

## blk-06f9a648d262b8afa1e1cf11

- Status: `superseded`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `restore-gh-auth-visible-code`
- Surface: `github-device-auth`
- Symptom: The browser requests an eight-character device code but the user has no terminal view of the CLI-generated code
- Evidence: The active gh flow emitted its code only inside the agent-owned PTY

## blk-0824f088e8dcfdb4a7227835

- Status: `non-gap`
- Subject: `discovery-bc73b987-df58-5ef3-9ae4-e8543289023a`
- Step: `transition-command-shape-blocker`
- Surface: `blocker-catalog-cli`
- Symptom: Catalog transition rejected flags described by the blocker-catalog skill
- Evidence: argparse reported unrecognized --solution-summary and --changed-artifact

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

## blk-0bcbc5962dd62d05f376cd66

- Status: `closed`
- Subject: `discovery-0f04c36f-760d-5cd6-aecb-4381765b7dfa`
- Step: `verify-recovery-automation`
- Surface: `tests/test_scoped_git_publish.py`
- Symptom: The isolated recovery test expected a leading porcelain status space that the shared git helper strips.
- Evidence: Runtime recovery succeeded; pytest reported only expected M excluded.txt versus actual stripped M excluded.txt.

## blk-0cc194931fe4493f937d47c2

- Status: `non-gap`
- Subject: `discovery-bc73b987-df58-5ef3-9ae4-e8543289023a`
- Step: `record-artifact-provenance-correction`
- Surface: `work-memory-correction-ledger`
- Symptom: Correction recording rejected at least one changed artifact path
- Evidence: work_memory.py correct returned changed-artifact-outside-repository

## blk-0d9e2b0044af3e4b745c92fe

- Status: `closed`
- Subject: `discovery-3393078a-d255-508d-a718-2681b85c4a35`
- Step: `record-complete-command-set`
- Surface: `sequence_discovery_log`
- Symptom: Two planned discovery rows could not be recorded; pipe tokens escaped the command argument
- Evidence: invalid-command-row plus zsh command-not-found for greenfield/preflight/parallel tokens

## blk-10adf26e004bba44f735495a

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `initialize-candidate`
- Surface: `sequence-discovery`
- Symptom: The discovery path does not authorize the mandatory init_skill.py scaffold command.
- Evidence: The skill-creator contract requires init_skill.py for a new skill; no matching command exists in the selected discovery document.

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

## blk-17488b4b91687fc9020ef8ce

- Status: `superseded`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `guard-research-edit`
- Surface: `convergence-baseline`
- Symptom: The baseline guard sees the parent-authored research document hash as drift.
- Evidence: Only docs/gf-n3-resume-durability-research.md changed from expected 800b4f... to actual f2605e...; every other allowed path hash matches.

## blk-181ce7d8121a02f705556331

- Status: `open`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `controlled-topic-strategy-state-preservation`
- Surface: `src/up_harness/engine/runner.py`
- Symptom: the source workflow completed policy preparation and join but exposed zero controlled topics after strategy composition
- Evidence: same-path integration test progressed beyond strategy composition then observed len(controlled_topics) equal to zero

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

## blk-1b24a5707c20a0937f146399

- Status: `superseded`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `spawn-and-bind-research-internal`
- Surface: `playbook-convergence-loop-slot-lifecycle`
- Symptom: The exact bind-agent command cannot be guarded before spawn because the agent ID is runtime-generated, while binding must happen immediately after spawn
- Evidence: playbook-convergence-loop requires immediate bind-agent; sequence_guard requires exact command grounded in the selected immutable bundle

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

## blk-21b2da2a8e50279db192754d

- Status: `closed`
- Subject: `commit-push-main`
- Step: `independent-review-proof-surface`
- Surface: `commit-push-main`
- Symptom: The registered verification command executes three test files while the sealed dependency bundle includes only one.
- Evidence: REV-COMMIT-PUSH-001 independently confirmed tests/test_scoped_git_publish.py and tests/test_sequence_promote.py are omitted; scripts/sequence_promote.py is their directly executed helper.

## blk-23c06fb0d9e360287293d158

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `inspect-run-summary`
- Surface: `sequence-guard`
- Symptom: The active discovery run cannot guard its own work-memory summary or blocker-catalog command.
- Evidence: sequence_guard returned source-ref-outside-selected-bundle and command-not-grounded-in-selected-document.

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

## blk-2d4fe08c2f2b0c43df307887

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `superseded-correction-transition-command-contract`
- Surface: `sequence-discovery-contract`
- Symptom: overlapping-document-correction-cannot-be-terminally-superseded-through-discovery-command
- Evidence: older-correction-eee2-hash-is-replaced-by-latest-preserving-document-revision

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

## blk-3e7a70df538ca01016710375

- Status: `non-gap`
- Subject: `discovery-bc73b987-df58-5ef3-9ae4-e8543289023a`
- Step: `terminalize-fixed-awaiting-command-shape`
- Surface: `blocker-catalog-lifecycle`
- Symptom: Direct fixed-awaiting-verification to non-gap transition was rejected
- Evidence: blocker_catalog.py returned invalid-blocker-status-transition

## blk-40488ff90594764f3846303d

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `current-runtime-lens-round-1`
- Surface: `research-playbook-v2-hash-contract`
- Symptom: Independent lenses block because candidate/envelope canonical object hashes differ from the SHA256 of their JSON files and the role contract does not define the hash domain.
- Evidence: INTERNAL_READINESS and REQUIREMENTS_SATISFACTION independently reported candidate file b8da0a44 versus declared ab47703f and envelope file dad48ccc versus declared af7072eb; both stopped rather than assess unverified inputs.

## blk-40b4a227f019ec7882f591e4

- Status: `fixed-awaiting-verification`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `reconcile-third-artifact-revision`
- Surface: `convergence-state-artifact-lineage`
- Symptom: Cycle 4 coverage audit reconciliation fails with artifact has a different live supersession
- Evidence: existing Cycle 1 artifact points to Cycle 3; one-pass loop validates that pointer before repointing Cycle 3 to Cycle 4

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

## blk-4578e027d32ae1aa65cd84da

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `slot-lifecycle-command-guard`
- Surface: `sequence_guard`
- Symptom: The guard rejected the full slot lifecycle command because the discovery log stored only a shortened placeholder form.
- Evidence: sequence_guard returned command-not-grounded-in-selected-document for mark-closed and release; both commands then executed because the orchestration loop failed to stop after the guard rejection.

## blk-45feac2859a7b950a41fcc61

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `record-deployment-verification-lineage`
- Surface: `work-memory-verification`
- Symptom: The successful live deployment evidence was submitted to the corrected discovery lineage as a clean verification.
- Evidence: work_memory.py verify rejected the event with clean-verification-after-correction; the registered deploy sequence has its own selected lineage.

## blk-471c325bdc1a6e949cf96158

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `activate-taggable-api-deploy-sequence`
- Surface: `work-memory-selection`
- Symptom: The registered taggable-api-deploy sequence could not be selected because its taggable-api automation repository root was not supplied.
- Evidence: classify succeeded and the immediately following explicit sequence selection returned missing-repository-root before activation or deployment.

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

## blk-4b7f97392b9d4648553c2dac

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `record-correction`
- Surface: `sequence-guard`
- Symptom: After the selected bundle changes, sequence_guard rejects the work_memory correct command that must record that exact bundle transition.
- Evidence: Both discovery_log and script sourced guards returned stale-source-bundle before command-shape evaluation; verify_receipts fails closed before cmd_guard can authorize work_memory.py correct.

## blk-4edbb8641b9676e9b6278e56

- Status: `closed`
- Subject: `discovery-promotion-lifecycle`
- Step: `independent-review-lifecycle`
- Surface: `discovery-promotion-lifecycle`
- Symptom: Registered failures can bypass correction, interrupted correction is not resumable, and cross-repository correction artifacts are rejected.
- Evidence: REV-LIFECYCLE-001, REV-LIFECYCLE-002, and REV-LIFECYCLE-003 were independently confirmed FIX NOW.

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

## blk-539e7f2311661d7da1eefb74

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `run-focused-v2-tests`
- Surface: `evaluator-tests`
- Symptom: Two focused evaluator tests fail before exercising their intended assertions.
- Evidence: The tests supplied output_hash=None and lifecycle agent_id, while the evaluator requires a lowercase SHA-256 output_hash and runtime_agent_id.

## blk-5631781b9a52545ff026d704

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `accept-core-runner-baseline`
- Surface: `sequence-guard-source-bundle`
- Symptom: sequence_guard rejected the implementation baseline command because the selected memory-knowledge source bundle changed during coding
- Evidence: guard returned stale-source-bundle before dispatching the accept-baseline command

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

## blk-5a8136a16ee7fbce36628938

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `final-memory-suite-uv-cache`
- Surface: `local-test-runner`
- Symptom: The final helper suite could not initialize uv's cache under the sandbox.
- Evidence: uv exited before pytest after failing to open /Users/kamenkamenov/.cache/uv/sdists-v9/.git with os error 1.

## blk-5b6e654711de2b37c90768ca

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `corrected-bundle-successor-selection`
- Surface: `work_memory`
- Symptom: The first corrected-bundle successor selection had no current classification receipt after predecessor closure.
- Evidence: The first select returned missing-classification-receipt; a fresh canonical classify receipt then allowed successor selection.

## blk-5bb7b1e56beedd0a96154972

- Status: `fixed-awaiting-verification`
- Subject: `discovery-a55832eb-534e-5813-b755-dfc6cb73bf75`
- Step: `canonical-ledger-union`
- Surface: `scripts/work_memory.py`
- Symptom: The isolated reconciliation canonical writer rejected remote-order plus local-unseen event union with blocker-correction-required.
- Evidence: isolated-reconcile-remote stopped before commit or push with merged ledger failed canonical validation: blocker-correction-required.

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

## blk-6739e10cf9ef5089784c0f6a

- Status: `open`
- Subject: `discovery-e9f998db-d24a-5932-90e8-c9ca2678c4ef`
- Step: `verify-corrections`
- Surface: `work_memory.verify`
- Symptom: The ledger rejected same-path verification for both corrections after the corrected bundle executed
- Evidence: work_memory.py verify returned verification-correction-mismatch for corrections e67e00e4 and 7dfa35d8

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

## blk-7316f2d6e07bed6cba6ac970

- Status: `closed`
- Subject: `discovery-3393078a-d255-508d-a718-2681b85c4a35`
- Step: `verify-discovery-corrections`
- Surface: `work_memory_verify`
- Symptom: Same-path verification events are rejected although the successor selection lists both correction IDs
- Evidence: work_memory verify returned verification-correction-mismatch for corrections 23cacea6 and d5798140

## blk-7441db416f180077aa835e06

- Status: `fixed-awaiting-verification`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `v2-adjudication-verdict`
- Surface: `skills/research-playbook-v2/scripts/research_package.py`
- Symptom: Rejected provisional lens findings still force IN_PROGRESS or BLOCKED after fresh adjudication.
- Evidence: Round 1: current and scope returned zero actionable fingerprints but remained IN_PROGRESS with LENS_GAPS; mixed rejected RS-EVIDENCE-001 yet became BLOCKED with LENS_BLOCKED.

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

## blk-801829be7d2077acfbe0411c

- Status: `open`
- Subject: `discovery-e9f998db-d24a-5932-90e8-c9ca2678c4ef`
- Step: `locate-runtime`
- Surface: `sequence_guard`
- Symptom: The runtime search command was rejected before execution
- Evidence: sequence_guard returned command-not-grounded-in-selected-document

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

## blk-86fa98060551f4ec68265ccc

- Status: `closed`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `verify-automation`
- Surface: `discovery-verification-command`
- Symptom: the grounded verification command omits the promotion-helper test that is part of the correction
- Evidence: discovery row lists scoped publish and discovery-log tests only; correction 0ec30bae also changes scripts/sequence_promote.py and tests/test_sequence_promote.py

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

## blk-8bcbe4478330315aa3d2f25a

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `register-research-artifact`
- Surface: `sequence_guard`
- Symptom: The convergence state cannot register the research artifact because sequence_guard rejects tool-help evidence outside the selected discovery bundle.
- Evidence: sequence_guard returned {error: source-ref-outside-selected-bundle, ok: false} before register-artifact executed.

## blk-8ce0cf7fb5202a60bb906416

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `research-baseline-guard`
- Surface: `convergence_state.py`
- Symptom: Baseline guard rejected unsupported --path argument before checking state
- Evidence: argparse rejected --path; initial catalog attempt also rejected a guessed subject and the run receipt confirms subject discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a

## blk-8dcf1c94b73742e9410b5303

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `restore-managed`
- Surface: `managed-projection-recovery`
- Symptom: sealed-missing-file-cannot-be-recreated
- Evidence: restore-managed-refused-missing-pyc-before-mutation

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

## blk-9147abcbb1d0b5d7d7a826bb

- Status: `superseded`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `verify-run`
- Surface: `work-memory-lifecycle`
- Symptom: same-path verification cannot be recorded for the generated-artifact blocker
- Evidence: work_memory.py verify returned paired-correction-blocker-required

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

## blk-99e06d8f4cd4edf3e5c55d09

- Status: `closed`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `inspect-convergence-tools`
- Surface: `sequence-guard-discovery-grounding`
- Symptom: The active discovery sequence rejects the first repository/skill inspection command because no command shape is recorded.
- Evidence: sequence_guard.py returned command-not-grounded-in-selected-document for rg --files over the convergence skill directories.

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

## blk-9c4932e5c2c593eac5be7e3d

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `close-failed-remediation-run`
- Surface: `work-memory-run-close`
- Symptom: run-close persists the terminal event but exits with TypeError while computing metrics
- Evidence: scripts/work_memory.py:1101 sums record[terminal] and boolean; non-terminal records yield None

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

## blk-a5d91c78094c2c6abd11ca71

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `validate-managed`
- Surface: `sequence-discovery`
- Symptom: The discovery log records managed validation and install commands without their required source and manifest arguments.
- Evidence: validate_skills.py requires --skills-root; install_skills.py requires --source and --manifest.

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

## blk-ac99e130f7255ca34c0545ba

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `plan-stage-idempotency-retry`
- Surface: `convergence-state`
- Symptom: Corrected final verifier payload was rejected because the prior failed attempt reserved the same stage iteration attempt key
- Evidence: Attempt 1 payload changed only to satisfy the diagnosed owned-gap reconciliation contract

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

## blk-b1f2f0ad31b74d513fee573a

- Status: `superseded`
- Subject: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Step: `validate-staged-diff`
- Surface: `staged-markdown`
- Symptom: git diff --cached --check reports trailing whitespace in new durability research and plan documents
- Evidence: 20 header metadata lines reported across six staged Markdown files

## blk-b23549ebeec52ae32836f61d

- Status: `non-gap`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `foundation-focused-tests`
- Surface: `tests/unit/test_role_executor_usage.py`
- Symptom: The provenance unit test failed before exercising run_role_with_provenance because it assigned run_role on a frozen CommandRoleExecutor instance.
- Evidence: Bundled unittest: tests.unit.test_role_executor_usage.AggregateUsageTests.test_role_execution_keeps_provenance_outside_payload raised dataclasses.FrozenInstanceError at line 54.

## blk-b436d06ac2e1f91e5df5fa40

- Status: `closed`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `legacy-research-fanout`
- Surface: `subagent-fanout`
- Symptom: duplicate-mixed-maturity-writer-created-after-batch-spawn-reported-thread-limit
- Evidence: hidden-agent-019f6263-9294-7110-9e62-72d32c9f10c3-completed-while-replacement-019f6266-44ab-7b60-a604-f33dbf3ed3ab-was-running

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

## blk-bec03ce3f78be19efc3d30a1

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `guard-aggregate-verification`
- Surface: `sequence_guard`
- Symptom: The guard rejects the two-pair aggregate verification command because the discovery row describes repetition with bracket notation rather than an explicit executable shape.
- Evidence: sequence_guard returned command-not-grounded-in-selected-document for run-verify-all-corrections after the grouped selection and baseline passed.

## blk-beec5dbbd5bba52c387659f2

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `bind-research-internal-agent`
- Surface: `sequence_guard`
- Symptom: Concrete runtime agent ID fails guard although the discovery table declares --agent-id <agent-id>
- Evidence: _shape_match compares whole line token length; discovery command is embedded between Markdown table cells

## blk-bfaccd0546fc71be51e67252

- Status: `open`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `coverage-vp2-run-start`
- Surface: `work_memory run-start`
- Symptom: Subagent cannot start the guarded read-only coverage audit run
- Evidence: work_memory.py run-start returned PermissionError after successful activation

## blk-c659e7c0c6c7ef43bc4130b0

- Status: `non-gap`
- Subject: `discovery-dc523951-00f3-567d-984d-2b07a51c9aac`
- Step: `research-doc-gap-attempt-3`
- Surface: `delegated-assessment`
- Symptom: Fresh assessor stopped before document review because it treated read-only evidence inspection as a separate operational sequence.
- Evidence: Stage envelope RDG-EXEC-001; active parent discovery lineage and run already govern this convergence task.

## blk-c7c2be69cc786d528b8e7cf0

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `verifier-generated-output-baseline`
- Surface: `convergence-baseline`
- Symptom: Building the verifier changed bin and obj beneath the allowed verifier directory fingerprint
- Evidence: Only tools/Taggable.ReportExportVerifier directory hash differs after a successful build

## blk-c820736fb9a7767bc974c37f

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `multi-supersession-focused-tests`
- Surface: `controller-regression-tests`
- Symptom: focused-suite-90-passed-2-failed
- Evidence: wrong-private-validator-name-and-old-generic-error-expectation

## blk-c95e0e5f249e5a8d337fe4d4

- Status: `closed`
- Subject: `discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa`
- Step: `research-doc-gap-cycle-25-critic`
- Surface: `multi-agent-verifier`
- Symptom: Fresh Cycle 25 critic stopped before artifact inspection and asked to create orchestration files.
- Evidence: Agent 019f60f1-5406-7552-aa46-109e47d3b0a4 returned no PASS/GAPS result because it treated a new discovery log as mandatory, although discovery-d43595b9-6d8a-5290-8d6a-9b8b476582fa already exists.

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

## blk-d158c5eae27cc2ccab0ee8e2

- Status: `non-gap`
- Subject: `discovery-46914e3d-839f-54cc-9486-70411dd5299a`
- Step: `sequence-select`
- Surface: `work-memory discovery selection`
- Symptom: The selector rejected a discovery log stored outside the canonical repository
- Evidence: ValueError: temporary discovery log is not below /Users/kamenkamenov/memory-knowledge

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

## blk-d830b3f69e35fb5ef45d512e

- Status: `closed`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `full-suite-dependency-manifest`
- Surface: `discovery-dependency-manifest`
- Symptom: successor-selection-rejected-correction-artifact-outside-bundle
- Evidence: test-scoped-git-publish-and-test-sequence-promote-omitted-from-dependencies

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

## blk-e730851043677c62164ab745

- Status: `open`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `activate-sequence`
- Surface: `work-memory sequence activation`
- Symptom: The read-only plan-verification sequence could not activate until directive-read state was refreshed.
- Evidence: Initial sequence_guard.py activate exited nonzero with the exact stale directive-read message; documented directive_guard read then made activation pass.

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

## blk-f5083c31ebd4f7e372ef2c7b

- Status: `superseded`
- Subject: `discovery-683fb3d9-702b-55ff-945f-35c9f667e439`
- Step: `prepare-evaluation-command-contract`
- Surface: `sequence-discovery-contract`
- Symptom: fresh-blind-lock-cannot-be-created-through-recorded-command
- Evidence: discovery-table-has-record-and-score-but-no-prepare

## blk-f688fe246d4cbc81e600ece8

- Status: `fixed-awaiting-verification`
- Subject: `discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab`
- Step: `restore-preinstall`
- Surface: `codex-managed-skill-installation`
- Symptom: selected-discovery-cannot-restore-sealed-baseline
- Evidence: sealed-snapshot-diff-and-recovery-artifacts-confirmed

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

## blk-f9bf87fafc029f0cc74176cd

- Status: `non-gap`
- Subject: `discovery-3aaffc84-ada2-5b1f-803c-19b08cdb803c`
- Step: `ground-research-commands`
- Surface: `sequence-discovery-log`
- Symptom: Embedded pipe and alternation characters executed while recording commands instead of remaining command text
- Evidence: zsh reported command not found for agent_slot_ledger.py, numeric, mssql, Excel, Net, OperatorPayout, and sequence_discovery_log.py reported missing --result

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

## blk-fd3cc7b777171aaaabc2481d

- Status: `closed`
- Subject: `discovery-5ec2431f-c39d-5996-ad95-cbda520fe59a`
- Step: `supersede-stale-baseline-correction`
- Surface: `memory-knowledge/scripts/work_memory.py`
- Symptom: A shared work-memory controller change appeared after successor selection, so correction recording sees unrelated artifact drift.
- Evidence: Selected hash ebbfdc...; current hash a1091c...; git diff adds preservation of prior verification_quality when cmd_correct closes a run.
