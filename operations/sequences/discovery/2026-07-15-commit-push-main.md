# Sequence Discovery Log: commit-push-main
ReadyAtUtc: 2026-07-15T07:45:47Z

DiscoveryId: discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c
Status: promoted
PromotedSequenceId: commit-push-main
CreatedAtUtc: 2026-07-15T05:31:07Z
RegisteredSequenceMatch: none

## Intended Outcome

Commit and push an explicitly approved file scope while preserving unrelated working-tree changes

## Why This Looks Repeatable

Publishing a completed, verified workspace change is recurring and must preserve unrelated local work

## Required Inputs, Auth, Or Environment

- A local Git worktree root, expected branch, and configured push remote.
- A UTF-8 manifest containing one approved repository-relative file path per line; directories and path escapes are rejected.
- A non-empty commit message approved for the change being published.
- An empty Git index before the sequence starts; unrelated unstaged and untracked work may remain.
- Working Git push authentication and network access. No token values are printed or accepted as arguments.
- Explicit authorization to commit and push the named repository, branch, remote, and manifest scope.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| prepare-manifest | Create a UTF-8 manifest with one approved repository-relative file path per line. | verified | The manifest is the complete staging boundary; never substitute git add -A or a directory path. |
| dry-run | python3 scripts/scoped_git_publish.py --repo <repo> --manifest <manifest> --message <message> --branch <branch> --remote <remote> | verified | Preflight the repository, branch, remote, empty index, manifest paths, and changed-file scope without changing Git state. |
| publish | python3 scripts/scoped_git_publish.py --repo <repo> --manifest <manifest> --message <message> --branch <branch> --remote <remote> --execute | verified | Stage exactly the manifest, reject any staged mismatch or whitespace error, commit, push, and verify the remote branch SHA. |
| resume-push | python3 scripts/scoped_git_publish.py --repo <repo> --branch <branch> --remote <remote> --resume-commit <commit> | verified | After an auth, network, or remote-side push failure, push only the already-created HEAD commit and verify its remote SHA. |
| verify-automation | uv run pytest tests/test_scoped_git_publish.py tests/test_sequence_discovery_log.py tests/test_sequence_promote.py | passed | All 14 focused tests passed through the publish script, discovery helper, and atomic promotion helper entry points. |

## Failure Handling


- A dry-run failure changes no Git state. Correct the reported branch, remote, manifest, or pre-existing staged work, then rerun dry-run.
- Before a commit exists, any execution failure unstages only the manifest paths and preserves all working-tree content.
- After a commit exists, a push or remote-verification failure leaves that commit at HEAD and prints the exact `--resume-commit` value. Repair authentication, network, or remote policy and run the documented resume command; do not create a duplicate commit.
- A non-fast-forward rejection is a stop condition. Inspect and reconcile remote divergence through the repository's approved integration workflow; never force-push from this sequence.
- If remote SHA verification differs from local HEAD, stop and preserve the local commit as evidence. Do not report success or start another publish.
- Catalog every failure before correction or retry. Never print credentials or infer invalid authentication from a sandbox connectivity error.

## Verified Path

- Historical live path: the manually discovered scoped publish committed 45 approved files as `51b0bee540503b46a757d977ece06b61585a2a72` to `mcp-agents-workflow` `origin/main`, while ten excluded paths remained local and unstaged.
- Reusable path: `tests/test_scoped_git_publish.py` exercises dry-run, exact-scope commit and push to a real local bare Git remote, unrelated-worktree preservation, dirty-index rejection, path-escape rejection, and failed-push resume through the production script entry points.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
