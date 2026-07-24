# Sequence Discovery Log: Codex Remote Control Identity Regeneration

DiscoveryId: discovery-6c9c32b3-939c-54f1-8cff-5bd9758f8821
Status: discovery
CreatedAtUtc: 2026-07-15T17:34:26Z
BootstrapRequestSha256: 358632ed6752ed0fabc562eb066b2ea78ba40323171247be0e3c37edf4bd6fea
RegisteredSequenceMatch: none

## Intended Outcome

Remove the cloned Codex installation identity from active use while retaining one rollback copy so this Mac can generate a distinct identity.

## Why This Looks Repeatable

Cloned Macs can inherit the same Codex installation identity and collide during remote-control registration.

## Required Inputs, Auth, Or Environment

- Codex is installed for user kamenkamenov.
- The cloned installation identity exists at /Users/kamenkamenov/.codex/installation_id.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify-cloned-remote-control-enrollment-reset | python3 scripts/reset_codex_remote_control_enrollment.py inspect --codex-home /Users/kamenkamenov/.codex | Both remote_control_enrollments tables report zero rows before re-enrollment and global state has no stale environment key while the installation identity still matches. | After ChatGPT reopens, enable Remote Control and verify the websocket no longer returns HTTP 409. |
| schedule-cloned-remote-control-enrollment-reset | python3 scripts/reset_codex_remote_control_enrollment.py schedule --codex-home /Users/kamenkamenov/.codex --wait-for-app-exit 180 --quit-app-after 30 --reopen --receipt <receipt-path> | One double-forked worker quits ChatGPT after 30 seconds, backs up and clears only cloned enrollment state, verifies the active installation identity is preserved, writes a receipt, and reopens ChatGPT exactly once. | Use a new receipt path for each explicitly approved reset. The schedule marker and pre-execution receipt prevent duplicate scheduling or execution. Never use launchctl submit for this worker because submitted jobs are keepalive. |
| inspect-cloned-remote-control-enrollment | python3 scripts/reset_codex_remote_control_enrollment.py inspect --codex-home /Users/kamenkamenov/.codex | Reports enrollment row counts and confirms global state preserves the active installation identity without printing identifiers. | Run before scheduling reset. |
| preflight-installation-identity | test -f /Users/kamenkamenov/.codex/installation_id | passed | Require the cloned identity before moving it. |
| rotate-installation-identity | mv /Users/kamenkamenov/.codex/installation_id /Users/kamenkamenov/.codex/installation_id.pre-clone-reset-20260715 | required | Preserve one rollback copy and remove the cloned identifier from active use. |
| verify-installation-identity-backup | test -f /Users/kamenkamenov/.codex/installation_id.pre-clone-reset-20260715 | passed | Confirm the rollback copy exists before Codex is relaunched. |

## Failure Handling

Stop on the first failure. Do not overwrite an existing backup. Restore the backup only if Codex cannot generate a new installation identity after relaunch.

## Verified Path

- After relaunch, Codex recreates installation_id with a distinct identifier and remote control registration succeeds.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
