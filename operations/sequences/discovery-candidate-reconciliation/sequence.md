# discovery-candidate-reconciliation

<!-- BEGIN SEMANTIC INTAKE ENTRYPOINT -->
## Operator entry point

After selecting and activating this registered sequence, launch the shared controller with no
arguments:

```bash
python3 scripts/sequence_intake_launch.py
```

Answer only the semantic questions shown. Every question includes its response format, an example,
and constraints. The controller derives JSON, files, environment, flags, and argv; displays the
exact prepared operation; and requires a separate yes/no authorization before guarded dispatch.

Any argument-bearing commands below are machine-compatibility and verification evidence for the
deterministic adapter. Operators and agents must not construct or invoke those forms directly.
<!-- END SEMANTIC INTAKE ENTRYPOINT -->

## Use When

Audit all logged discovery sequences, decide which should promote, absorb, remain, supersede, or quarantine, and clean the active queue without deleting provenance.

## Outcome

Run the governed reconciliation lifecycle from one command: verify the current registered bundle (including any correction-bound successor), execute a separate guarded rolling run, record same-path evidence, close the run, and remove terminal candidates from the active queue without deleting provenance.

## Required Inputs

- The memory-knowledge repository root and a clean, readable Git HEAD for the audit snapshot.
- A complete generated disposition manifest reviewed and explicitly approved by Kamen before execute.
- For rolling cleanup, the checked-in approved `operations/sequences/discovery/reconciliation-policy.json`; it preserves every approved disposition, names the exact terminal allowlist, and admits a newly logged candidate automatically only while its audited disposition is `remain-discovery`.
- A caller-supplied task id and reusable output root. The one-shot drive obtains current passed-and-closed registered same-path verification itself, binds any pending correction to its successor, and then selects a separate registered run for live rolling execution.
- For each promote row: sequence_id, use_when, operation_kind, automation_display, pass_signal, and max_qualification_runs required by the canonical lifecycle.
- For absorb or supersede rows: a concrete registered target and evidence that the reusable behavior is already preserved there.

## Commands

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| drive-one-shot | python3 scripts/discovery_candidate_reconciliation.py drive --task-id <task-id> --output-root <output-root> | Classifies, selects, activates, and starts the required registered runs; verifies the current bundle; guards and executes rolling reconciliation; records same-path evidence; closes the live run; and returns one terminal JSON result. | This is the canonical operator entry point. Re-running with the same task id is safe because each governed run receives a new run id and each rolling execution receives a unique invocation directory. |
| protected-controller-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --solution <solution> --reusable-behavior-changed yes --changed-artifact <path> | The sealed pre-change controller validates and records the exact corrected artifact set, then a successor run verifies it. | Use this immutable bootstrap path when the correction changes scripts/work_memory.py; never execute the changed controller to authorize itself. |
| failed-successor-correction | python3 scripts/work_memory.py correct --run-id <failed-successor-run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes --supersedes-correction-id <unverified-correction-id> --finalize-failed-run | The new correction becomes the only active correction for the accumulated bundle, and the superseded correction's blocker becomes terminal atomically. | Repeat `--supersedes-correction-id` once for every unverified active correction inherited by the failed successor. Do not try to bind corrections from different bundle hashes to one successor or transition their blockers manually. |
| bind-dependencies-from-file | python3 scripts/sequence_discovery_log.py set-dependencies --file operations/sequences/discovery/2026-07-15-discovery-candidate-reconciliation.md --dependencies-json /private/tmp/discovery-candidate-reconciliation-dependencies.json | The discovery manifest is updated from the JSON document at the supplied path. | --dependencies-json accepts a filesystem path, not inline JSON. |
| bootstrap-controller | Create scripts/discovery_candidate_reconciliation.py and tests/test_discovery_candidate_reconciliation.py before dependency binding and source-bundle selection. | The controller and test entry points exist before a guarded implementation run is selected. | Selection fails closed when a recorded executable is absent; scaffold the registered entry point first, then bind it into the discovery manifest. |
| verify-automation | scripts/run_pytest.sh tests/test_discovery_candidate_reconciliation.py tests/test_discovery_promotion_lifecycle.py -q | planned | Exercise complete inventory, manifest validation, fail-closed drift, lifecycle delegation, checkpointing, one-shot correction/verification/live closure, and non-destructive active-index cleanup. |
| execute-approved | python3 scripts/discovery_candidate_reconciliation.py execute --manifest <manifest> --active-index <active-index> | planned | Drive only approved promote rows through discovery_promotion_lifecycle.py; terminal non-promotion rows change only the generated active queue and never delete discovery provenance. |
| execute-rolling | python3 scripts/discovery_candidate_reconciliation.py --root <repository-root> execute-rolling --baseline operations/sequences/discovery/reconciliation-policy.json --output-dir <output-root> --active-index operations/sequences/discovery/ACTIVE.md --max-attempts 6 | planned | Run only from a separate registered run after the current bundle's correction successor has verified and closed. Reapply the approved retain-only policy to the complete current log, allocate a unique invocation directory under the reusable output root, retry bounded candidate-set arrival races, but stop on any existing decision change, any new non-retain candidate, target proof drift, or terminal-allowlist change. |
| validate-dispositions | python3 scripts/discovery_candidate_reconciliation.py validate --manifest <manifest> | planned | Require exact candidate-set and HEAD match plus complete evidence-backed dispositions before execution. |
| audit-candidates | python3 scripts/discovery_candidate_reconciliation.py audit --output <manifest> | planned | Freeze repository HEAD and enumerate every discovery log with lifecycle, registry, blocker, readiness, and verification facts; no repository mutations. |

## Failure Handling

The one-shot drive stops before live execution when current-bundle verification fails; the existing lifecycle records that verification blocker. A guard, rolling execution, evidence-recording, or closure failure is cataloged against the live registered run before the command exits. Re-run the same one-shot command only after correcting the recorded reusable boundary; it detects and binds the pending correction successor before starting another separate live run. Fail before mutation when HEAD or the candidate set differs from the frozen manifest, any disposition is pending or lacks required evidence, a target sequence is missing, or an unexpected path appears. Execute candidates in manifest order with a durable checkpoint. Each rolling invocation owns a unique child directory under the supplied output root, so repeated use cannot collide with a prior attempt checkpoint. Rolling execution may absorb a concurrent new candidate only when a fresh audit still classifies it as `remain-discovery`; it reruns from a new frozen manifest and requires a stable post-audit before success. A changed existing decision, new promotion/quarantine candidate, registered-target bundle drift, or terminal-allowlist change is a semantic change and stops for review. Never bind different bundle hashes as parallel active corrections, and never force their blocker statuses manually. Never delete discovery logs; cleanup means excluding evidence-backed terminal rows from the generated active index.

## Verification

- Correction-bound successor a2dc4314-459f-4449-bdcb-450e6fdd2178 ran scripts/run_pytest.sh across reconciliation, promotion lifecycle, and work-memory correction tests: 74 passed in 0.23s; correction 9ad950ff-e4bd-5c7f-85d5-183efa6b5cf6 verified and blocker blk-822f5912321b9e00df07c17c closed.
- The rolling policy path is verified by the same registered command after its correction-bound successor; it covers approved-policy validation, exact decision retention, new-candidate admission, semantic-change stops, bounded retry, and stable post-audit.

Pass signal: The controller returns ok true, every frozen candidate has an approved disposition, canonical promote rows reach registered verification, and the active index excludes only terminal rows while original logs remain.

Promoted from `2026-07-15-discovery-candidate-reconciliation`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
