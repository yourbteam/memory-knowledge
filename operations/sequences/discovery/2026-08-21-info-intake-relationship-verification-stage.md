# Sequence Discovery Log: Info intake relationship verification stage

DiscoveryId: discovery-4e938ff3-599e-5b59-90e6-e2b83faa9eeb
Status: discovery
CreatedAtUtc: 2026-08-20T21:26:03Z
BootstrapRequestSha256: 105422e04f30e3fc28744a0e279515802ac55b9bf17a918bad5328cf0470fadd
RegisteredSequenceMatch: none

## Intended Outcome

Independently verify all pending relationships in one completed first-source projection and stop at canonical projection recording or the exact correction-required boundary.

## Why This Looks Repeatable

Every image-source intake with recorded visual relationships must run the same independent verification before its projection can be canonical.

## Required Inputs, Auth, Or Environment

- An existing intake work directory whose completed projection is waiting for independent relationship verification.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| run-relationship-verification-stage | python3 skills/info-intake-machinery/scripts/run_relationship_verification_with_codex.py | Returns projection_recorded or relationship_correction_required after one verifier model pass. | Fail closed unless the saved intake is exactly waiting for verification and stop before any correction or clarification work. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop immediately on missing, changed, invalid, or non-verification state and preserve all existing source, projection, ledger, and verification evidence.

## Verified Path

- Run the zero-input launcher on the captured real dashboard intake, confirm all relationship verdicts are durable, and confirm it stops at projection recording or correction without starting later work.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
