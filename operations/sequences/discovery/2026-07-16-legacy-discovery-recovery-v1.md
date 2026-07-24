# Sequence Discovery Log: legacy-discovery-recovery-v1

DiscoveryId: discovery-0f54a98b-4b75-536b-b8d6-6b2d8c8ab98e
Status: discovery
CreatedAtUtc: 2026-07-16T14:56:59Z
BootstrapRequestSha256: b0c161ccb275007be4c3216197a7b300c6d5e1017ac327b9ffe2db832c097939
RegisteredSequenceMatch: none

## Intended Outcome

Recover one authenticated pre-contract discovery whose generated document omitted every canonical correction row.

## Why This Looks Repeatable

Any discovery generated before the correction-row contract can otherwise become permanently unrecoverable after protected bundle drift.

## Required Inputs, Auth, Or Environment

- An active governed recovery run whose selected bundle includes the versioned controller.
- The exact failed task receipt chain and open blocker occurrence.
- A newline-delimited manifest containing the complete selected-bundle drift.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify-automation | scripts/run_pytest.sh tests/test_sequence_discovery_log.py tests/test_work_memory_bootstrap.py | passed | Prove future discovery rows and the exact legacy missing-row migration before use. |
| recover-missing-row | python3 scripts/legacy_discovery_recovery_v1.py correct --authorization-task-id <authorization-task-id> --authorization-run-id <authorization-run-id> --task-id <failed-task-id> --run-id <failed-run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifacts-file <manifest> --solution <solution> --reusable-behavior-changed yes | correction recorded and failed predecessor closed | The controller rejects canonical-row discoveries, terminal runs, mismatched authorization, partial drift, and unrelated blockers. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |

## Failure Handling

Fail closed without ledger mutation on any receipt, controller hash, run, lineage, blocker, or drift mismatch.

## Verified Path

- The focused pytest command passes before the guarded recovery command is executed.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
