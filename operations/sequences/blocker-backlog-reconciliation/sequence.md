# blocker-backlog-reconciliation

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

Audit the canonical blocker backlog and apply only an explicitly approved evidence-bound reconciliation manifest.

## Outcome

Audit every active blocker, execute only approved evidence-valid terminal transitions, and generate an owned actionable resolution queue without deleting history.

## Required Inputs

- An active governed task identity with this sequence selected and activated.
- The reconciliation operation: audit, validate, or execute.
- The registered repository containing the canonical blocker ledger and controller.
- For audit, a temporary manifest output path; for validation or execution, the exact reviewed manifest path; for execution, the active governed run identity.

## Commands

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify-automation | scripts/run_pytest.sh tests/test_blocker_backlog_reconciliation.py tests/test_sequence_intake_adapters.py::test_blocker_backlog_execute_derives_controller_owned_index_and_run tests/test_sequence_intake_launch.py::test_memory_knowledge_entrypoints_route_bare_launch_to_intake tests/test_work_memory.py::test_backlog_reconciliation_can_close_stranded_verified_correction tests/test_work_memory.py::test_only_registered_backlog_reconciliation_can_reuse_historical_verification tests/test_work_memory.py::test_only_exact_same_path_successor_can_close_blocker tests/test_work_memory.py::test_only_canonical_scripts_write_event_ledger -q | passed | Prove audit, exact approval validation, atomic execution, historical evidence reuse, semantic intake derivation, bare entrypoint routing, and canonical ledger ownership without requiring the registry row that this lifecycle is promoting. |
| audit-blockers | python3 scripts/sequence_intake_launch.py | Controller returns ok true with a complete pending manifest and disposition counts. | Freeze the active blocker projection so unrelated ledger appends do not invalidate review, while any blocker-state change fails closed. |
| validate-manifest | python3 scripts/sequence_intake_launch.py | Controller returns ok true only for a complete explicitly approved manifest matching current blocker state. | Reject pending decisions, missing owners or next actions, stale blocker facts, and closure without exact same-path verification. |
| execute-approved | python3 scripts/sequence_intake_launch.py | Controller applies one atomic evidence-valid transition batch and writes the actionable active queue. | Only the registered reconciliation subject may reuse exact historical verification; unsupported closure and concurrent blocker drift fail before mutation. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop before mutation on stale blocker projection, incomplete approval, unsupported lifecycle transition, wrong reconciliation authority, or ledger concurrency; preserve exact error evidence.

## Verification

- Focused controller and work-memory tests pass, then the zero-input audit reports the real active count and an approved execution proves the resulting active queue.

Pass signal: Controller returns ok true after registered same-path verification completes.

Promoted from `2026-07-23-blocker-backlog-reconciliation`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
