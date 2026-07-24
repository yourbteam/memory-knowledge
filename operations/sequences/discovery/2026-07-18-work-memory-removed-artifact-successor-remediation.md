# Sequence Discovery Log: work-memory-removed-artifact-successor-remediation

DiscoveryId: discovery-d1e88fbc-3f88-5911-b54e-219fa2ff8ebb
Status: discovery
CreatedAtUtc: 2026-07-17T23:23:04Z
BootstrapRequestSha256: b028394ae7293f41f037aa75c94c1c019f426eb3542e3d6844516e816fff6b4f
RegisteredSequenceMatch: none

## Intended Outcome

Correct the work-memory correction-to-successor contract so an artifact intentionally removed from the successor bundle can be verified without requiring mutable post-correction bytes to retain an obsolete hash.

## Why This Looks Repeatable

Any governed correction that removes a generated or obsolete dependency can otherwise become impossible to verify through the required correction-bound successor lifecycle.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| inspect-correction-and-successor-contract | rg -n -C 6 <pattern> scripts/work_memory.py scripts/work_memory_bootstrap.py | The correction producer, bundle transition, successor selector, and run-start consumer are traced end to end. | Read-only diagnosis. |
| inspect-focused-tests | rg -n -C 8 <pattern> tests/test_work_memory.py tests/test_work_memory_bootstrap.py | Existing intended behavior and missing removed-artifact cases are identified. | Read-only diagnosis. |
| inspect-immutable-event-evidence | rg -n <pattern> operations/work-memory/events.jsonl | The exact immutable correction, transition, and selection-failure evidence is recovered by ID. | The append-only ledger is inspected live but excluded from sealed dependencies. |
| run-root-cause-assessor | multi_agent_v1.spawn_agent work-memory-removed-artifact-root-cause | An independent assessment-only agent confirms symptom, cause chain, stable boundary, and negative constraints. | Parent retains all edit authority. |
| write-remediation-findings | apply_patch <research-findings-patch> | A task-local artifact records only evidence-backed findings and the stable contract boundary. | No implementation edits. |
| run-findings-verifier | multi_agent_v1.spawn_agent work-memory-removed-artifact-findings-verifier | A fresh independent assessor confirms the findings against controller code, tests, and immutable events. | Assessment-only. |
| write-remediation-plan | apply_patch <remediation-plan-patch> | A granular plan names every controller, schema, and focused-test change with its reason. | Implementation remains G11 approval-gated. |
| run-remediation-plan-verifier | multi_agent_v1.spawn_agent work-memory-removed-artifact-plan-verifier | A fresh assessor confirms the plan closes the cause without weakening tamper detection. | Assessment-only. |
| implement-approved-remediation | apply_patch <approved-remediation-patch> | Only the granular user-approved controller and test changes are applied. | No commit or deployment. |
| run-focused-tests | scripts/run_pytest.sh <focused-test-paths> | Focused tests prove preserved-file tamper rejection and removed-artifact successor acceptance. | Use the repository test wrapper. |
| run-correction-bound-successor | python3 scripts/work_memory.py select --task-id <task-id> --discovery-log <discovery-log> --verification-successor-of <run-id> --verifies-correction-id <correction-id> | The original blocked correction selects and starts a fresh bound successor through the same path. | Only this same-path confirmation permits verifier remediation to resume. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| record-protected-correction-three-artifacts | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact operations/sequences/discovery/2026-07-18-work-memory-removed-artifact-successor-remediation.md --changed-artifact scripts/work_memory.py --changed-artifact tests/test_work_memory.py --solution <solution> --reusable-behavior-changed yes | required for the approved controller, focused-test, and discovery-contract correction | The exact three-path drift is finalized atomically by the sealed controller. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Catalog every failure before correction. Any controller or selected-bundle edit records a correction, closes the predecessor failed, and requires a fresh correction-bound successor.

## Verified Path

- Focused red-before and green-after tests plus successful selection and start of the original correction-bound successor without relaxing preserved-artifact tamper rejection.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
