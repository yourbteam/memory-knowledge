# Sequence Discovery Log: codex-remote-control-identity-reset

DiscoveryId: discovery-681aa86a-0cde-5ed2-b8cf-615eef3bdb7d
Status: discovery
CreatedAtUtc: 2026-07-15T16:43:07Z
RegisteredSequenceMatch: none

## Intended Outcome

Back up and remove the cloned Codex installation_id on the migrated Mac only

## Why This Looks Repeatable

Mac cloning or Migration Assistant can duplicate Codex installation identity and break Remote Control host separation

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify backup retained | test -f /Users/kamenkamenov/.codex/installation_id.pre-clone-reset-20260715.bak | planned | Confirms rollback artifact exists |
| verify source removed and backup retained | test ! -e /Users/kamenkamenov/.codex/installation_id | planned | Confirms authoritative cloned identity is absent |
| move cloned installation identity aside | mv /Users/kamenkamenov/.codex/installation_id /Users/kamenkamenov/.codex/installation_id.pre-clone-reset-20260715.bak | planned | Reversible backup/removal on migrated Mac only |
| preflight installation identity move | test -f /Users/kamenkamenov/.codex/installation_id | planned | Source must exist before moving; do not touch global state |

## Failure Handling

TBD while discovering.

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
