# Sequence Discovery Log: Isolated branch reconciliation into main

DiscoveryId: discovery-2d166640-1626-5264-be69-116a07111fa3
Status: discovery
CreatedAtUtc: 2026-08-24T11:53:02Z
BootstrapRequestSha256: 10d7253fc6eb7e6d2e424994b77e00141fec6ac2e3accdfb7a913a1009567a2e
RegisteredSequenceMatch: none

## Intended Outcome

Reconcile an approved feature branch into current origin/main in an isolated worktree, validate the merged result, and publish it without disturbing other sessions.

## Why This Looks Repeatable

Feature branches regularly need reconciliation with an independently advancing main branch while other sessions remain active.

## Required Inputs, Auth, Or Environment

- The repository containing the source and target branches.
- The clean, fully pushed source branch to preserve.
- The remote containing the authoritative target branch.
- The target branch whose latest remote head is the integration base.
- Semantically resolved files that preserve the intended behavior from both branches.
- Focused and full-suite verification that must pass before publication.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| prepare-isolated-merge | python3 scripts/branch_integration_prepare.py | Returns ok true with an isolated integration worktree, exact source and target SHAs, and a complete conflict manifest. | Fails before worktree creation when the source is dirty or unpublished; otherwise leaves conflicts visible and the source worktree untouched. |
| publish-validated-integration | python3 scripts/commit_push_main_launch.py | Returns ok true with focused checks passed and the local commit equal to the remote integration branch. | Code lists the exact changed paths, runs the approved verification, and requires separate authorization for the remote effect. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop before publication on a dirty or unpublished source, remote drift, unsupported merge failure, unresolved conflicts, or any failed verification, retaining the isolated worktree and evidence.

## Verified Path

- The preparation launcher proves exact SHAs, source preservation, and the conflict manifest; the commit controller proves required tests and local-to-remote commit parity.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
