# Sequence Discovery Log: Active Discovery Recovery B-Team Final

DiscoveryId: discovery-dee6b8e7-466e-5085-987d-af79dc3910b3
Status: discovery
CreatedAtUtc: 2026-07-19T21:56:19Z
BootstrapRequestSha256: 2cfc50a8bb6382bb35d28c808caf28b718f6b2d0126ef48bb471dfc0ba48af9c
RegisteredSequenceMatch: none

## Intended Outcome

Authorize one exact atomic correction and failed finalization of the stale B-Team discovery run against the final verified product and manifest bundle.

## Why This Looks Repeatable

An active discovery can otherwise become unable to record its already-implemented correction after its selected source bundle changes.

## Required Inputs, Auth, Or Environment

- The current task owner for both the authorization task and target B-Team task.
- The target run-start bundle, exact current bundle, blocker occurrences, and an exact changed-artifact list.
- A fresh directive-read receipt.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| recover-stale-discovery | python3 scripts/active_discovery_recovery_v1.py correct --authorization-task-id <authorization-task-id> --authorization-run-id <authorization-run-id> --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --co-blocker-id <co-blocker-id> --step-id <step-id> --changed-artifacts-file <path> --solution <solution> --reusable-behavior-changed yes | required | Fail closed unless both tasks have the same current owner, the target run is the same nonterminal discovery lineage, trust anchors are unchanged, all blockers are open on that run, and the artifact list exactly equals A-to-B drift. |
| verify-controller | scripts/run_pytest.sh tests/test_active_discovery_recovery_v1.py tests/test_work_memory_bootstrap.py | passed | The focused recovery and bootstrap tests passed before live use. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop on any ownership, lineage, lifecycle, blocker, trust-anchor, canonical-row, or exact-drift mismatch; do not mutate the ledger.

## Verified Path

- The focused integration test records the correction, co-correction, bundle transition, blocker transitions, and failed run close through the real work-memory transaction, then proves an identical retry adds no events.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
