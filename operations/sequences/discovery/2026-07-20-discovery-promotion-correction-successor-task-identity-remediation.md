# Sequence Discovery Log: Discovery Promotion Correction Successor Task Identity Remediation

DiscoveryId: discovery-533b6358-99dd-5950-b4ee-05094f10316a
Status: discovery
CreatedAtUtc: 2026-07-20T15:14:59Z
BootstrapRequestSha256: eaecbb20cb458373d4d4e4357b3c88cbb640dcf0dd9942fc4bb0dde0b0a771bd
RegisteredSequenceMatch: none

## Intended Outcome

Allow the promotion lifecycle to verify a corrected discovery by preserving the correction predecessor's task identity for its bound successor.

## Why This Looks Repeatable

Every bootstrapped discovery uses a caller-supplied task id, so any corrected candidate can encounter this same promotion failure.

## Required Inputs, Auth, Or Environment

- The recorded cross-task-successor-selection failure.
- The predecessor run's existing task ownership event.
- The discovery promotion lifecycle and its focused tests.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| catalog-cross-task-successor-defect | python3 scripts/blocker_catalog.py open --run-id <run-id> --subject-id <discovery-id> --step-id promotion-successor-selection --surface <surface> --error-signature <signature> --symptom <symptom> --evidence <evidence> --impact <impact> --boundary <boundary> | The controller defect is durably cataloged before implementation. | Use the exact lifecycle failure evidence. |
| verify-automation | scripts/run_pytest.sh tests/test_discovery_promotion_lifecycle.py | The lifecycle suite passes, including correction-bound and ordinary qualification task identity branches. | No external model or product workflow is invoked. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop on the first failing focused test. Do not weaken work-memory cross-task ownership; correct only the lifecycle's successor task-id production.

## Verified Path

- Reproduce through the focused lifecycle regression, prove the correction-bound successor reuses the predecessor task id, and prove ordinary qualifications retain the generated promotion task id.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
