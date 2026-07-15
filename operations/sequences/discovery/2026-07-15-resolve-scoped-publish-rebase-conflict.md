# Sequence Discovery Log: resolve scoped publish rebase conflict

DiscoveryId: discovery-a55832eb-534e-5813-b755-dfc6cb73bf75
Status: discovery
CreatedAtUtc: 2026-07-15T09:39:26Z
RegisteredSequenceMatch: none

## Intended Outcome

Identify every conflicting file for a preserved scoped publish, apply deterministic file-specific merge rules in isolation, rerun verification, push without force, and leave the source worktree untouched.

## Why This Looks Repeatable

Concurrent writers can modify the same governed ledger, registry, controller, and test files between scoped commit creation and push.

## Required Inputs, Auth, Or Environment

- The preserved local HEAD commit, its original full-scope manifest, and an overlay manifest containing only reviewed semantic resolutions.
- The expected branch and push remote, plus working fetch/push authentication.
- For governed work-memory conflicts, the repository-relative ledger and generated blocker-view paths.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| inspect-remote-conflict-diff | git -C <repo> diff <base>..<remote> -- operations/work-memory/events.jsonl scripts/work_memory.py tests/test_blocker_catalog.py | verified | Remote added durable repository-root snapshots and canonical `reopen_evidence`; the ledger contained remote-only immutable events. |
| inspect-local-conflict-diff | git -C <repo> diff <base>..<local> -- operations/work-memory/events.jsonl scripts/work_memory.py tests/test_blocker_catalog.py | verified | Local added exact correction drift, successor binding, trust anchors, and local-only immutable events; BLOCKERS.md was confirmed derived. |
| inspect-isolated-conflicts | python3 scripts/scoped_git_publish.py --repo <repo> --manifest <manifest> --overlay-manifest <overlay-manifest> --message <message> --branch <branch> --remote <remote> --resume-commit <commit> --isolated-integrate-remote | failed-contained | The helper reported exactly four conflicts and aborted the isolated rebase without changing the source: blocker view, ledger, work-memory controller, and blocker tests. |
| reconcile-isolated-conflicts | python3 scripts/scoped_git_publish.py --repo <repo> --manifest <manifest> --overlay-manifest <overlay-manifest> --ledger-path operations/work-memory/events.jsonl --generated-view-path operations/blockers/BLOCKERS.md --message <message> --branch <branch> --remote <remote> --resume-commit <commit> --isolated-reconcile-remote | verified | Remote HEAD is the base; clean same-path changes receive a deterministic three-way merge; approved overlays carry reviewed semantic unions for real conflicts; work-memory alone merges ledger events and regenerates the derived view; unsupported content conflicts fail closed. |
| verify-conflict-evidence | uv run pytest tests/test_work_memory.py tests/test_blocker_catalog.py tests/test_scoped_git_publish.py tests/test_sequence_discovery_log.py tests/test_sequence_promote.py | passed | 71 tests proved exact conflict output, clean same-path merging, real-conflict overlays, canonical sole-writer enforcement, bounded historical-ledger union, strict new-event validation, lifecycle validation, and unchanged dirty source state. |
| catalog-conflict-evidence-gap | python3 scripts/blocker_catalog.py open --run-id <run-id> --subject-id <subject-id> --step-id <step-id> --surface <surface> --error-signature <error-signature> --symptom <symptom> --evidence <evidence> --impact <impact> --boundary <boundary> | verified | The exact-path conflict gap was catalogued before the helper and sequence were corrected. |

## Failure Handling

- Attempt a deterministic three-way merge for a same-path remote/local edit; abort and preserve the source only when that merge has a real content conflict absent from the overlay or named ledger/view rule.
- Reject differing canonical content for the same ledger event ID; never choose one silently.
- Validate both persisted ledgers independently before union. Preserve legacy compatibility only for event IDs already present in those validated inputs; never grant legacy status to a newly authored event.
- Reject any staged path outside the full manifest, any path lacking a commit/overlay source, a remote advance during isolation, a canonical ledger validation failure, or a source-state change.
- Push without force and require the published branch SHA to equal the isolated reconciled commit.

## Verified Path

- `uv run pytest tests/test_work_memory.py tests/test_blocker_catalog.py tests/test_scoped_git_publish.py tests/test_sequence_discovery_log.py tests/test_sequence_promote.py -q` passed 71 tests.
- The real local bare-remote test creates a same-file remote/local conflict, publishes the reviewed overlay from a temporary remote-based clone, and proves the dirty source HEAD, status, and content remain unchanged.
- The reusable recovery path is absorbed into registered sequence `commit-push-main` as `isolated-reconcile-and-resume`.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Absorbed into the existing registered `commit-push-main` sequence rather than creating a competing top-level sequence.
