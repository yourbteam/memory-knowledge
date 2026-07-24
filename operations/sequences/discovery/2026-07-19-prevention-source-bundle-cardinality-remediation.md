# Sequence Discovery Log: prevention source-bundle cardinality remediation

DiscoveryId: discovery-1ab9b53e-7eb9-5c6b-8aa4-3f582555c270
Status: discovery
CreatedAtUtc: 2026-07-19T02:32:31Z
BootstrapRequestSha256: 802d16a460ff81d444e8093af1664abfdad55765a89dbdf51f23648ab671712d
RegisteredSequenceMatch: none

## Intended Outcome

A valid authenticated dependency bundle with 101 files can start a work-memory run, while the generic 100-item ceiling continues to reject oversized unrelated arrays.

## Why This Looks Repeatable

Large multi-repository convergence bundles can legitimately exceed 100 authenticated files, and run-start must apply a stable field-specific contract instead of failing at the generic JSON-array boundary.

## Required Inputs, Auth, Or Environment

- Original successor selection receipt hash 64e3b1624154a7c1d3c3cd47c934314cd68951c290d4254acbcc6016d4e04883
- Original successor bundle hash a3866ca40254bc10e6add81353a7aea9db24f045486c71633a96a52889661e0c

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| reproduce-source-bundle-limit | scripts/run_pytest.sh tests/test_work_memory.py -q | Focused work-memory tests include a red-before case for a 101-entry run source_bundle. | Use only the repository pytest launcher. |
| fix-source-bundle-contract | apply_patch <source-bundle-field-limit-patch> | Only run_started.source_bundle receives an authoritative higher bound; unrelated arrays keep the generic ceiling. | No manifest pruning and no global array-limit relaxation. |
| verify-focused-work-memory | scripts/run_pytest.sh tests/test_work_memory.py -q | The 101-entry source bundle passes and an unrelated 101-item array remains rejected. | This is the focused regression gate. |
| record-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id fix-source-bundle-contract --changed-artifact scripts/work_memory.py --changed-artifact tests/test_work_memory.py --solution <solution> --reusable-behavior-changed yes | The exact two-file correction is recorded and the failed remediation run closes. | Use the sealed correction launcher; do not bypass stale-bundle guards. |
| same-path-successor-proof | python3 scripts/work_memory.py run-start --task-id prevention-materializer-selection-deadlock-remediation-v1 | The original valid 101-file successor starts unchanged. | This is the required same-path proof for resuming owner-runtime verification. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Catalog the exact failure before editing; any correction requires a fresh remediation successor and the original 101-file run-start must pass unchanged.

## Verified Path

- The remediation is complete only after focused tests pass and the original prevention-materializer successor run-start succeeds on bundle a3866ca4 without removing dependencies.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
