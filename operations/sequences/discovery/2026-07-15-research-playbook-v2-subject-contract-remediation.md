# Sequence Discovery Log: research playbook v2 subject contract remediation

DiscoveryId: discovery-6a9f4f62-798e-5c7c-8bbe-8738a523d1d1
Status: discovery
CreatedAtUtc: 2026-07-15T19:44:01Z
BootstrapRequestSha256: 8ed09f52045b432ea039cbbd5cef0a12892d3018c9c1aeb283faa0f54a8dc054
RegisteredSequenceMatch: none

## Intended Outcome

Bind the mixed-fixture blocker command to its generated discovery subject and prove the previously rejected path succeeds.

## Why This Looks Repeatable

Discovery blocker commands must never confuse a product fixture label with the ledger-owned run subject.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| open-remediation-blocker | python3 scripts/blocker_catalog.py open --run-id <run-id> --subject-id <subject-id> --step-id <step-id> --surface <surface> --error-signature <signature> --symptom <symptom> --evidence <evidence> --impact <impact> --boundary <boundary> | required | Catalog the unconstrained subject placeholder before changing its authoritative discovery instruction. |
| edit-subject-contract | apply_patch operations/sequences/discovery/2026-07-15-research-playbook-v2-mixed-fixture-remediation.md | required | Bind only the open-blocker subject token and clarify where the fixture identity belongs. |
| correct-subject-contract | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact operations/sequences/discovery/2026-07-15-research-playbook-v2-mixed-fixture-remediation.md --solution <solution> --reusable-behavior-changed yes | required | Bind the one-file instruction correction and atomically close the remediation predecessor. |
| successor-classify | python3 scripts/work_memory.py classify --task-id <task-id> --operation-kind other --repeatable yes --meaningful-steps 10 | required | Refresh the correction-bound successor classification. |
| successor-select | python3 scripts/work_memory.py select --task-id <task-id> --discovery-log operations/sequences/discovery/2026-07-15-research-playbook-v2-subject-contract-remediation.md --verification-successor-of <run-id> --verifies-correction-id <correction-id> | required | Select the exact corrected dependency bundle. |
| successor-activate | python3 scripts/sequence_guard.py activate --task-id <task-id> --discovery-log operations/sequences/discovery/2026-07-15-research-playbook-v2-subject-contract-remediation.md | required | Activate only the correction-bound successor receipts. |
| successor-start | python3 scripts/work_memory.py run-start --task-id <task-id> | required | Start the exact same-path verification successor. |
| replay-open-blocker | python3 scripts/blocker_catalog.py open --run-id <run-id> --subject-id <subject-id> --step-id <step-id> --surface <surface> --error-signature <signature> --symptom <symptom> --evidence <evidence> --impact <impact> --boundary <boundary> | required | Execute the previously rejected command with the product run's generated discovery subject. |
| verify-correction | python3 scripts/work_memory.py verify --run-id <run-id> --outcome passed --quality same-path --evidence <evidence> --blocker-id <blocker-id> --correction-id <correction-id> | required | Record the successful blocker-open path as same-path evidence. |
| transition-verified | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status verified --verification-event-id <event-id> | required | Advance only after same-path evidence exists. |
| transition-closed | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status closed --verification-event-id <event-id> --remaining-work none | required | Close the control-plane blocker with no remaining work. |
| close-successor | python3 scripts/work_memory.py run-close --run-id <run-id> --result passed | required | Close the verified remediation lane. |

## Failure Handling

Stop at the first failed guard or command; catalog the exact failure and do not touch any fixture, skill, evaluator, or unrelated sequence artifact.

## Verified Path

- A fresh product run accepts blocker creation with its generated DiscoveryId, and that result closes the correction-bound remediation successor.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
