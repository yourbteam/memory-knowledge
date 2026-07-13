# Work Blockers

Ledger-SHA256: `528f72c21476ffc8f48ee4f603586b66b84c20b536790091d0673260c49e471f`

This file is generated from `operations/work-memory/events.jsonl`.

## blk-063234e3cc282c9cf8934590

- Status: `fixed-awaiting-verification`
- Subject: `discovery-de6c9083-3ed4-5c8a-8976-ef44a67a82a2`
- Step: `document-runtime-placeholder-slot-binding`
- Surface: `convergence-sequence-integration`
- Symptom: Convergence slot lifecycle cannot be followed under sequence guarding because the skills omit predeclared runtime-ID command shapes
- Evidence: sequence_guard _shape_match supports <placeholder>; convergence and sequence skills did not describe using it before spawn

## blk-0d9e2b0044af3e4b745c92fe

- Status: `closed`
- Subject: `discovery-3393078a-d255-508d-a718-2681b85c4a35`
- Step: `record-complete-command-set`
- Surface: `sequence_discovery_log`
- Symptom: Two planned discovery rows could not be recorded; pipe tokens escaped the command argument
- Evidence: invalid-command-row plus zsh command-not-found for greenfield/preflight/parallel tokens

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

## blk-20cba16bfef4306bd02dbda2

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `bind-research-internal-slot`
- Surface: `agent_slot_ledger`
- Symptom: bind-agent --label research-internal-1 matches released s1 and reserved s2
- Evidence: agent_slot_ledger returned selector matched 2 slots after acquire returned s2

## blk-2b9fd4c172625b52eabe38b5

- Status: `closed`
- Subject: `discovery-87df1262-3559-590e-9102-27b64fd3c6ad`
- Step: `install-both-clients`
- Surface: `managed-skill-installer`
- Symptom: The dual-client installer refused before changing either managed root.
- Evidence: working-agreement/install-skills.sh returned: --target both requires --reconciliation.

## blk-30fc6d2e072f46cf732eefc2

- Status: `fixed-awaiting-verification`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `run-start`
- Surface: `work-memory-control-plane`
- Symptom: verifier-could-not-create-required-run-ledger
- Evidence: run-start returned PermissionError twice; parent same command succeeded with authorized write

## blk-37575ef28f83a55bd0433d9a

- Status: `open`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `research-gap-2-stable-boundary`
- Surface: `cross-repository-task-persistence`
- Symptom: Reused task-universe rows cannot be reconciled because memory-knowledge exposes create_task but no general planning-task update tool
- Evidence: memory-knowledge server.py:4651-4721 and admin/planning.py:417-447 only insert new task UUID rows; workflow-orch feature_task_universe.py:149-247 reuses without updating

## blk-486dd03ab73cee3ebc1a1501

- Status: `non-gap`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `transition-command-grounding-blocker`
- Surface: `blocker_catalog`
- Symptom: Blocker transition was sent with a zero UUID instead of the verification event returned by the prior command
- Evidence: verify returned e54e9a70-985a-4ed1-8734-dd5820205670; transition rejected 00000000 UUID

## blk-4f6b72278a35b093ce1df7fd

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `record-memory-knowledge-repository-approval`
- Surface: `sequence-guard-markdown-tokenization`
- Symptom: The corrected approval command is still ungrounded because shlex rejects the entire Markdown row
- Evidence: Record row note contains unmatched apostrophe in helper's; shlex.split raises No closing quotation

## blk-585b09207361d374d81e6ee3

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `register-research-artifact`
- Surface: `sequence_guard`
- Symptom: Guard rejects a convergence_state register-artifact command sourced from the shared helper
- Evidence: sequence_guard returned source-ref-outside-selected-bundle

## blk-5e5921daa66d3f06148dbcf5

- Status: `fixed-awaiting-verification`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `record-memory-knowledge-repository-approval`
- Surface: `convergence-approval-sequence`
- Symptom: The recorded scope approval command is guard-valid but convergence_state rejects kind scope-expansion
- Evidence: convergence_state.py:18 permits scope-change, not scope-expansion; command exited invalid approval kind

## blk-6249d7b3d6b2e9b1f2d0f140

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `advance-expected-docs-root-baseline`
- Surface: `sequence-baseline-command`
- Symptom: The guarded docs baseline advance crashes because --changed-path docs resolves to memory-knowledge/docs instead of the target repository docs directory
- Evidence: ValueError: /Users/kamenkamenov/memory-knowledge/docs is not in subpath /Users/kamenkamenov/mcp-agents-workflow

## blk-6b01bc3647830f730117a63a

- Status: `closed`
- Subject: `discovery-3393078a-d255-508d-a718-2681b85c4a35`
- Step: `inventory-commit-range`
- Surface: `sequence_guard`
- Symptom: Guard rejects the first Git inventory command after the discovery log is extended
- Evidence: sequence_guard returned stale-source-bundle immediately after append-step row 04dfe512

## blk-7316f2d6e07bed6cba6ac970

- Status: `closed`
- Subject: `discovery-3393078a-d255-508d-a718-2681b85c4a35`
- Step: `verify-discovery-corrections`
- Surface: `work_memory_verify`
- Symptom: Same-path verification events are rejected although the successor selection lists both correction IDs
- Evidence: work_memory verify returned verification-correction-mismatch for corrections 23cacea6 and d5798140

## blk-8ab6978877066e6789afbeb9

- Status: `closed`
- Subject: `discovery-87df1262-3559-590e-9102-27b64fd3c6ad`
- Step: `inspect-release-entrypoints`
- Surface: `sequence-guard`
- Symptom: The release inspection command was refused before execution.
- Evidence: sequence_guard returned command-not-grounded-in-selected-document for the exact rg command.

## blk-9c4932e5c2c593eac5be7e3d

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `close-failed-remediation-run`
- Surface: `work-memory-run-close`
- Symptom: run-close persists the terminal event but exits with TypeError while computing metrics
- Evidence: scripts/work_memory.py:1101 sums record[terminal] and boolean; non-terminal records yield None

## blk-aa358c52c5dceacb935be8a4

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `accept-research-doc-baseline`
- Surface: `convergence_state`
- Symptom: accept-baseline rejects the authorized research file as path outside declared change set
- Evidence: Baseline allowed path is docs aggregate; command declared only docs/latest-100-commits-implementation-gap-research.md

## blk-b7cb84d572fd87609528a538

- Status: `closed`
- Subject: `discovery-3393078a-d255-508d-a718-2681b85c4a35`
- Step: `ground-full-evidence-command-set`
- Surface: `sequence_guard`
- Symptom: Guard rejects additional read-only Git evidence commands absent from the selected discovery log
- Evidence: Five guards returned command-not-grounded-in-selected-document

## blk-bbb7b9dc36e2892544b9a95c

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `initialize-convergence-state`
- Surface: `convergence_state`
- Symptom: Convergence state initialization rejects the Markdown requirements file
- Evidence: requirement_map calls json.loads and raised JSONDecodeError at line 98

## blk-beec5dbbd5bba52c387659f2

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `bind-research-internal-agent`
- Surface: `sequence_guard`
- Symptom: Concrete runtime agent ID fails guard although the discovery table declares --agent-id <agent-id>
- Evidence: _shape_match compares whole line token length; discovery command is embedded between Markdown table cells

## blk-cac8b080c04cae568e377e05

- Status: `fixed-awaiting-verification`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `guard-before-research-internal`
- Surface: `convergence_state`
- Symptom: Baseline guard blocks reviewer spawn because docs working hash changed after creating the research artifact
- Evidence: Only docs working_hash changed; src/workflow_orch and tests hashes match baseline

## blk-d004263ef5a949460423d2f7

- Status: `closed`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `coverage68-artifact-read`
- Surface: `sequence-command-grounding`
- Symptom: guarded-read-commands-rejected-before-execution
- Evidence: four exact sed read commands were rejected by sequence_guard; no artifact reads executed

## blk-e730851043677c62164ab745

- Status: `open`
- Subject: `discovery-944efff2-29a6-55b3-88db-f484bef24764`
- Step: `activate-sequence`
- Surface: `work-memory sequence activation`
- Symptom: The read-only plan-verification sequence could not activate until directive-read state was refreshed.
- Evidence: Initial sequence_guard.py activate exited nonzero with the exact stale directive-read message; documented directive_guard read then made activation pass.
