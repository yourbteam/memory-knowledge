# Sequence Discovery Log: Info intake relationship correction stage

DiscoveryId: discovery-04e6e00a-cb75-5889-9ca2-d0fe5d398e85
Status: discovery
CreatedAtUtc: 2026-08-20T21:48:24Z
BootstrapRequestSha256: d4f4bb23047179f38df7463bf174390763317e1ccd6c4aac511152c9a636a290
RegisteredSequenceMatch: none

## Intended Outcome

Correct independently rejected relationships from a completed first-source projection, independently verify any replacement claims, and stop at canonical projection recording.

## Why This Looks Repeatable

Any intake whose independent relationship check rejects a claim must use the same bounded correction and verification path.

## Required Inputs, Auth, Or Environment

- An existing intake work directory waiting for relationship correction.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| run-relationship-correction-stage | python3 skills/info-intake-machinery/scripts/run_relationship_correction_with_codex.py | Returns projection_recorded with the canonical first projection. | Fail closed unless the intake is exactly waiting for correction, and never start clarification or later assessment. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop on missing, changed, or invalid state or either model failure while preserving all source, interview, ledger, and verification evidence.

## Verified Path

- Run the zero-input launcher on the captured dashboard intake and confirm the correction, fresh independent verdict, and canonical projection are durable without starting later work.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
