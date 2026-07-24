# Sequence Discovery Log: plan-playbook-source-snapshot-recursion-remediation
ReadyAtUtc: 2026-07-21T20:51:21Z

DiscoveryId: discovery-43cb4423-8a2b-5fa6-8a1a-f2b0711ff5e1
Status: discovery
CreatedAtUtc: 2026-07-21T20:39:20Z
BootstrapRequestSha256: 88d8d2f7842f35a69d45bbd04fdccbc7abc54f480ec388536505ab8288522ff3
RegisteredSequenceMatch: none

## Intended Outcome

Plan Playbook source snapshots exclude nested controller source-snapshot archives while preserving real repository sources, and the grounded Decision 5 revision-4 draft binds successfully.

## Why This Looks Repeatable

Every fresh Plan Playbook controller snapshots an entire allowed repository; repositories containing prior controller snapshots can otherwise recurse on every continuation.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| reproduce-recursive-source-snapshot-failure | python3 skills/plan-playbook/scripts/plan_package.py record-draft /Users/kamenkamenov/united-partners/Tasks/up-decision5-operational-alignment-package-completion/.plan-playbook/state.json --plan /Users/kamenkamenov/united-partners/Tasks/up-decision5-operational-alignment-continuation-final-verification/.plan-playbook/proposed-revisions/4/plan.md --surface-map /Users/kamenkamenov/united-partners/Tasks/up-decision5-operational-alignment-continuation-final-verification/.plan-playbook/proposed-revisions/4/surface-map.json --decisions /Users/kamenkamenov/united-partners/Tasks/up-decision5-operational-alignment-continuation-final-verification/.plan-playbook/proposed-revisions/4/decisions.json --verification-ledger /Users/kamenkamenov/united-partners/Tasks/up-decision5-operational-alignment-continuation-final-verification/.plan-playbook/proposed-revisions/4/verification-ledger.json | Before correction, record-draft fails in create_source_snapshot with Errno 63 after recursively nesting prior .plan-playbook/source-snapshots. | Captured traceback is bound to blocker blk-0ed9f07c51859cfe4d69b5fd. |
| apply-and-verify-approved-snapshot-exclusion | scripts/run_pytest.sh tests/test_plan_playbook_v2.py -k source_snapshot | Focused source-snapshot regression passes and proves ordinary source files remain captured while nested controller archives are excluded. | The edit itself uses the approval-gated apply_patch boundary; this repository launcher imports the edited controller and provides its syntax/runtime check. |
| install-canonical-plan-playbook | python3 working-agreement/install_skills.py --source skills --manifest skills/managed-skills.txt --target codex --only plan-playbook | Only the validated canonical plan-playbook projection is installed into the Codex skills root. | The repository source and installed controller must be byte-identical after installation. |
| verify-real-decision5-draft-binding | python3 /Users/kamenkamenov/.codex/skills/plan-playbook/scripts/plan_package.py record-draft /Users/kamenkamenov/united-partners/Tasks/up-decision5-operational-alignment-package-completion/.plan-playbook/state.json --plan /Users/kamenkamenov/united-partners/Tasks/up-decision5-operational-alignment-continuation-final-verification/.plan-playbook/proposed-revisions/4/plan.md --surface-map /Users/kamenkamenov/united-partners/Tasks/up-decision5-operational-alignment-continuation-final-verification/.plan-playbook/proposed-revisions/4/surface-map.json --decisions /Users/kamenkamenov/united-partners/Tasks/up-decision5-operational-alignment-continuation-final-verification/.plan-playbook/proposed-revisions/4/decisions.json --verification-ledger /Users/kamenkamenov/united-partners/Tasks/up-decision5-operational-alignment-continuation-final-verification/.plan-playbook/proposed-revisions/4/verification-ledger.json | The exact grounded revision-4 draft records successfully and the continuation controller reaches DRAFTED. | This is the same path that previously failed, not a proxy fixture. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Any repeated fingerprint stops the sequence and updates blocker blk-0ed9f07c51859cfe4d69b5fd before another retry.

## Verified Path

- The exact United Partners Decision 5 record-draft command must return DRAFT_RECORDED.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
