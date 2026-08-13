# Sequence Discovery Log: Real image projection interview validation

DiscoveryId: discovery-748c90b8-778b-5b80-968e-4f274ed8f46e
Status: discovery
CreatedAtUtc: 2026-08-12T14:41:38Z
BootstrapRequestSha256: ba47f7fa5a74152193270c07e570c62e84ffdbc3edf630baf827f76938c4fe7f
RegisteredSequenceMatch: none

## Intended Outcome

Drive the frozen source image through the code-enforced projection interview and produce its immutable projection v1 terminal result.

## Why This Looks Repeatable

Each new image intake will require the same frozen-source attachment and code-enforced projection interview drive.

## Required Inputs, Auth, Or Environment

- The absolute directory of an intake waiting for its first projection interview.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| run-projection-interview | python3 skills/info-intake-machinery/scripts/run_projection_with_codex.py | Codex returns the intake's ready_for_projection_assessment terminal JSON. | Fail closed unless the intake is pending projection and its frozen image still matches its recorded hash. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop before model launch when intake state or source integrity fails, and preserve any launched interview's terminal evidence.

## Verified Path

- The zero-input script launches the real frozen image and the same intake reaches ready_for_projection_assessment with unchanged source and valid ledgers.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
