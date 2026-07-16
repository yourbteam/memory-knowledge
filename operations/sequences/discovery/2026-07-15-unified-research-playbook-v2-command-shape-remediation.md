# Sequence Discovery Log: unified research playbook v2 command shape remediation

DiscoveryId: discovery-12a4d13f-4852-5fc4-8106-aebb5efbec71
Status: discovery
CreatedAtUtc: 2026-07-15T19:14:40Z
BootstrapRequestSha256: 5a1196460b2033722ad62b67a661a3ce3274eaeeb3b73f3a5a542fa361e2b37e
RegisteredSequenceMatch: none

## Intended Outcome

Add and verify the exact three-artifact correction shape needed to recover the frozen v2 evaluation after concurrent discovery, guard, and test drift.

## Why This Looks Repeatable

A stale selected bundle must have a documented exact-cardinality correction route before any source or evaluation state mutation can resume.

## Required Inputs, Auth, Or Environment

- The active v14 blocker and occurrence identifiers.
- The existing unified-v2 discovery document and its selected source-bundle evidence.
- The current sequence guard and focused regression tests.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| open-blocker | python3 scripts/blocker_catalog.py open --run-id <run-id> --subject-id <subject-id> --step-id <step-id> --surface <surface> --error-signature <signature> --symptom <symptom> --evidence <evidence> --impact <impact> --boundary <boundary> | required | Catalog the missing exact command shape before editing the reusable discovery contract. |
| edit-command-shape | apply_patch operations/sequences/discovery/2026-07-15-unified-research-playbook-v2-trust-reset.md | required | Add only one exact three-artifact sealed-controller correction row. |
| correct-command-shape | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact operations/sequences/discovery/2026-07-15-unified-research-playbook-v2-trust-reset.md --solution <solution> --reusable-behavior-changed yes | required | Bind the one-file discovery-contract change and atomically close the failed remediation predecessor. |
| successor-classify | python3 scripts/work_memory.py classify --task-id <task-id> --operation-kind other --repeatable yes --meaningful-steps 9 | required | Allocate the fresh same-path verification successor. |
| successor-select | python3 scripts/work_memory.py select --task-id <task-id> --discovery-log operations/sequences/discovery/2026-07-15-unified-research-playbook-v2-command-shape-remediation.md --verification-successor-of <run-id> --verifies-correction-id <correction-id> | required | Bind the exact corrected dependency bundle and correction. |
| successor-activate | python3 scripts/sequence_guard.py activate --task-id <task-id> --discovery-log operations/sequences/discovery/2026-07-15-unified-research-playbook-v2-command-shape-remediation.md | required | Activate only the corrected successor receipts. |
| successor-start | python3 scripts/work_memory.py run-start --task-id <task-id> | required | Start the exact correction verification run. |
| focused-tests | scripts/run_pytest.sh tests/test_sequence_guard.py tests/test_work_memory_bootstrap.py -q | required | Prove exact correction-shape matching, stale-bundle bootstrap, and focused controller compatibility. |
| verify-correction | python3 scripts/work_memory.py verify --run-id <run-id> --outcome passed --quality same-path --evidence <evidence> --blocker-id <blocker-id> --correction-id <correction-id> | required | Record byte-bound same-path evidence. |
| transition-verified | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status verified --verification-event-id <event-id> | required | Advance only after the same-path verification event exists. |
| transition-closed | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status closed --verification-event-id <event-id> --remaining-work none | required | Close with no remaining remediation work. |
| close-successor | python3 scripts/work_memory.py run-close --run-id <run-id> --result passed | required | Close the verified remediation lane. |

## Failure Handling

Stop after the first failed guard or command, catalog that exact failure before editing, and do not mutate any v2 fixture or evaluation state in this lane.

## Verified Path

- The focused tests pass from the correction-bound successor, the blocker reaches closed, and the original v14 three-artifact correction guard then accepts the exact command.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
