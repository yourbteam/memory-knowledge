# Sequence Discovery Log: Corrective Planner real research handoff

DiscoveryId: discovery-f5aae412-18b7-5696-b2dd-e39771918ed3
Status: discovery
CreatedAtUtc: 2026-07-20T21:02:42Z
BootstrapRequestSha256: 883bc0903046efd05684895dd737fb2e164dd28274a54ae062daa3ed8aeeb57a
RegisteredSequenceMatch: none

## Intended Outcome

Initialize and reopen a canonical Planner state from the real hardened Planner-assessment research package using the corrective candidate code.

## Why This Looks Repeatable

Canonical Planner releases need a real Research-to-Plan handoff acceptance run.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| initialize-real-research-handoff | /Users/kamenkamenov/memory-knowledge/.venv/bin/python /private/tmp/mk-corrective-66a93560/skills/plan-playbook/scripts/plan_package.py init /private/tmp/planner-corrective-live-validation/.plan-playbook/state.json --task-directory /private/tmp/planner-corrective-live-validation --charter /private/tmp/planner-corrective-live-validation/charter.json --entry-mode RESEARCH_PACKAGE --task-size heavy --approval-context ORDINARY --research-package /Users/kamenkamenov/memory-knowledge/Tasks/plan-playbook-assessment-v2/research-package | Controller returns ok=true and INITIALIZED with a canonical state. | Uses the real historical research package and candidate controller; no evaluator fixture. |
| reopen-real-research-handoff | /Users/kamenkamenov/memory-knowledge/.venv/bin/python /private/tmp/mk-corrective-66a93560/skills/plan-playbook/scripts/plan_package.py show /private/tmp/planner-corrective-live-validation/.plan-playbook/state.json | Controller validates the state and reports the real research package binding. | Reopens the exact persisted state through the same candidate controller. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop on the first non-zero controller result and preserve its JSON error envelope.

## Verified Path

- Both commands execute the corrective candidate controller against the real Planner-assessment research package.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
