# Sequence Discovery Log: plan-playbook-deadline-continuation-immutability-remediation

DiscoveryId: discovery-3bef6153-87a3-5e9c-b57c-f4133fe5f158
Status: discovery
CreatedAtUtc: 2026-07-21T21:33:27Z
BootstrapRequestSha256: d09605f2cbae4b62a665dc35f245b8521dd4ebce825ae79dff0db13572745bc9
RegisteredSequenceMatch: none

## Intended Outcome

Plan Playbook can issue a fresh immutable deadline-continuation request after valid controller state changes, then generate the current Decision 5 request without weakening exact approval binding.

## Why This Looks Repeatable

Any substantial Plan Playbook package can cross its deadline after verifier or ledger state changes, so revision-only immutable request identity can dead-end future packages.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify-deadline-request-state-addressing | scripts/run_pytest.sh tests/test_plan_playbook_v2.py -k deadline_continuation | Focused tests prove red-before/green-after behavior for a stale request followed by a fresh state-addressed request and exact continuation. | The repository launcher imports the edited controller and provides the bounded runtime check. |
| install-canonical-plan-playbook | python3 working-agreement/install_skills.py --source skills --manifest skills/managed-skills.txt --target codex --only plan-playbook | Only the validated canonical Plan Playbook projection is installed into the Codex skills root. | Installation follows the existing managed-skills boundary. |
| generate-current-decision5-continuation-request | python3 /Users/kamenkamenov/.codex/skills/plan-playbook/scripts/plan_package.py prepare-deadline-continuation-approval /Users/kamenkamenov/united-partners/Tasks/up-decision5-operational-alignment-package-completion/.plan-playbook/state.json --out <request-path> | The controller publishes the current state-addressed immutable request and returns DEADLINE_CONTINUATION_APPROVAL_REQUIRED. | The concrete request path is derived from the controller state hash after the corrected contract is installed. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Any repeated fingerprint stops the sequence and updates blocker blk-c18f8e0d20976eaa33241da1 before another retry.

## Verified Path

- The installed controller must generate a new current-state Decision 5 request while preserving the stale immutable request.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
