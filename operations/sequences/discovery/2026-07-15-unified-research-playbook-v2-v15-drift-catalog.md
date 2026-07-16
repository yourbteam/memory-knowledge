# Sequence Discovery Log: unified research playbook v2 v15 drift catalog

DiscoveryId: discovery-96a53aeb-7f80-5141-9a16-792b6862b555
Status: discovery
CreatedAtUtc: 2026-07-15T19:24:26Z
BootstrapRequestSha256: 94634cc3ed63fb9103cf72ab8ae0d03d2c6e1802853472c5311b1ef331629ea7
RegisteredSequenceMatch: none

## Intended Outcome

Authorize the canonical blocker entry for the two-file external source reversion that invalidated v15 before any clean evaluation state was written.

## Why This Looks Repeatable

A stale active receipt cannot authorize its own blocker-open command, so a current byte-bound catalog lane is required.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| open-v15-blocker | python3 scripts/blocker_catalog.py open --run-id <run-id> --subject-id <subject-id> --step-id <step-id> --surface <surface> --error-signature <signature> --symptom <symptom> --evidence <evidence> --impact <impact> --boundary <boundary> | required | Record the exact external reversion on the affected v15 run. |
| close-catalog-lane | python3 scripts/work_memory.py run-close --run-id <run-id> --result passed | required | Close this no-edit catalog lane after the blocker entry succeeds. |

## Failure Handling

Stop on the first failed guard or command and do not mutate source or evaluation state.

## Verified Path

- The v15 blocker exists in the canonical ledger and this catalog-only run closes passed.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
