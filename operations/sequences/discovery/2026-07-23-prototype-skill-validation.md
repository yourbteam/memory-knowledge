# Sequence Discovery Log: prototype-skill-validation

DiscoveryId: discovery-1c54c807-030d-519f-8232-fa7fee4a393a
Status: discovery
CreatedAtUtc: 2026-07-23T07:12:12Z
BootstrapRequestSha256: 65c035ec16de7b989b5e36374d384fea004d5d3cd44d959f178a00e494f5328b
RegisteredSequenceMatch: none

## Intended Outcome

Validate the prototype-driven implementation skill with the required canonical validator.

## Why This Looks Repeatable

Every new or revised Codex skill requires the same structural validator and a dependency-complete Python runtime.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| validate-prototype-skill | /Users/kamenkamenov/united-partners/.venv/bin/python /Users/kamenkamenov/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/prototype-driven-implementation | The canonical validator reports that the skill is valid. | Use the existing dependency-complete interpreter; do not install packages or substitute another validator. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

If the canonical validator fails, report its exact output and correct only the reported skill defect. Do not install dependencies or use a substitute validator.

## Verified Path

- Run the exact canonical validator against the source skill folder and require exit code zero.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
