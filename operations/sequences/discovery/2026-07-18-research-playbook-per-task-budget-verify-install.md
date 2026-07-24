# Sequence Discovery Log: research-playbook-per-task-budget-verify-install

DiscoveryId: discovery-12c52079-69f3-520b-a0d8-a77b9d5099ba
Status: discovery
CreatedAtUtc: 2026-07-18T00:44:20Z
BootstrapRequestSha256: 201d8011ebe4f934c3a4b4b5629f146c0d10919d15809797e56d9612aaa4f569
RegisteredSequenceMatch: none

## Intended Outcome

Verify the corrected per-task research deadline contract, transactionally install only research-playbook, and prove the formerly blocked controller path.

## Why This Looks Repeatable

Managed skill changes repeatedly require focused tests, manifest validation, scoped installation, and installed same-path verification.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| focused-tests | scripts/run_pytest.sh tests/test_research_playbook_v2.py tests/test_research_run.py | All controller and driver tests pass, including long-workflow and shared-retry-deadline cases. | Use the repository-mandated test runner. |
| validate-managed-skills | python3 working-agreement/validate_skills.py --skills-root skills --manifest skills/managed-skills.txt | Managed skill source and manifest validate. | Must pass before installation. |
| install-research-playbook | python3 working-agreement/install_skills.py --source skills --manifest skills/managed-skills.txt --target codex --only research-playbook | Only research-playbook is transactionally installed into the Codex skills root. | Requires filesystem approval for the managed Codex skills directory. |
| installed-same-path | python3 /Users/kamenkamenov/.codex/skills/research-playbook/scripts/research_package.py show Tasks/prevention-system-completion/research-v10/work/state.json | The installed controller reads the legacy capped state without treating workflow age as a live mutation deadline. | Follow with a fresh successor controller for immutable same-path PASS proof. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Catalog any failed step before correction; do not install if focused tests or validation fail; never patch the installed copy directly.

## Verified Path

- Focused tests, managed-skill validation, scoped install, installed controller read, fresh successor same-path completion.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
