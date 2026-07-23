# commit-push-main

<!-- BEGIN SEMANTIC INTAKE ENTRYPOINT -->
## Operator entry point

After selecting and activating this registered sequence, launch the shared controller with no
arguments:

```bash
python3 scripts/sequence_intake_launch.py
```

Answer only the semantic questions shown. Every question includes its response format, an example,
and constraints. The controller derives JSON, files, environment, flags, and argv; displays the
exact prepared operation; and requires a separate yes/no authorization before guarded dispatch.

Any argument-bearing commands below are machine-compatibility and verification evidence for the
deterministic adapter. Operators and agents must not construct or invoke those forms directly.
<!-- END SEMANTIC INTAKE ENTRYPOINT -->

## Use When

Commit and push an explicitly approved file scope while preserving unrelated working-tree changes.

## Outcome

Commit and push an explicitly approved file scope while preserving unrelated working-tree changes

## Required Inputs

- A local Git worktree root, expected branch, and configured push remote.
- A UTF-8 manifest containing one approved repository-relative file path per line; directories and path escapes are rejected.
- A non-empty commit message approved for the change being published.
- An empty Git index before the sequence starts; unrelated unstaged and untracked work may remain.
- Working Git push authentication and network access. No token values are printed or accepted as arguments.
- GitHub CLI authentication is not a prerequisite and `gh auth status` must not gate this sequence.
  The CLI may run in a sandbox that cannot access the operator's keyring, while the guarded Git
  push uses a different credential path. Only the actual `git push` result from the deterministic
  publish or resume operation is authoritative for Git remote authentication.
- Explicit authorization to commit and push the named repository, branch, remote, and manifest scope.

## Commands

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| prepare-manifest | Create a UTF-8 manifest with one approved repository-relative file path per line. | verified | The manifest is the complete staging boundary; never substitute git add -A or a directory path. |
| dry-run | python3 scripts/scoped_git_publish.py --repo <repo> --manifest <manifest> --message <message> --branch <branch> --remote <remote> | verified | Preflight the repository, branch, remote, empty index, manifest paths, and changed-file scope without changing Git state. |
| publish | python3 scripts/scoped_git_publish.py --repo <repo> --manifest <manifest> --message <message> --branch <branch> --remote <remote> --execute | verified | Stage exactly the manifest, reject any staged mismatch or whitespace error, commit, push, and verify the remote branch SHA. |
| resume-push | python3 scripts/scoped_git_publish.py --repo <repo> --branch <branch> --remote <remote> --resume-commit <commit> | verified | After an auth, network, or remote-side push failure, push only the already-created HEAD commit and verify its remote SHA. |
| integrate-remote-and-resume | python3 scripts/scoped_git_publish.py --repo <repo> --manifest <manifest> --branch <branch> --remote <remote> --resume-commit <commit> --integrate-remote | verified | After a non-fast-forward rejection, fetch the named remote branch, require the complete local commit stack to equal the manifest scope, transactionally rebase it, revalidate the post-rebase scope, push without force, and verify the remote SHA. |
| isolated-integrate-and-resume | python3 scripts/scoped_git_publish.py --repo <repo> --manifest <manifest> --overlay-manifest <overlay-manifest> --message <message> --branch <branch> --remote <remote> --resume-commit <commit> --isolated-integrate-remote | verified | When unrelated tracked work makes the source worktree unsafe to rebase, clone the preserved commit into a temporary workspace, copy only the approved overlay, commit it, run the same exact-scope integration, push, and leave the source worktree byte-for-byte untouched. |
| isolated-reconcile-and-resume | python3 scripts/scoped_git_publish.py --repo <repo> --manifest <manifest> --overlay-manifest <overlay-manifest> --ledger-path operations/work-memory/events.jsonl --generated-view-path operations/blockers/BLOCKERS.md --message <message> --branch <branch> --remote <remote> --resume-commit <commit> --isolated-reconcile-remote | verified | When isolated rebase reports semantic conflicts, start from remote HEAD, deterministically three-way merge clean same-path edits, fail on actual content conflicts without an explicit rule, take verified overlay files from the untouched source worktree, merge the append-only ledger through the canonical work-memory writer by immutable event ID, regenerate the blocker view, create one scoped commit, push without force, and verify both remote SHA and unchanged source state. |
| verify-automation | uv run pytest tests/test_work_memory.py tests/test_blocker_catalog.py tests/test_scoped_git_publish.py tests/test_sequence_discovery_log.py tests/test_sequence_promote.py | passed | All 71 focused tests passed, including canonical sole-writer enforcement, append-only ledger union, bounded persisted-ledger compatibility, strict new-event validation, durable repository-root snapshots, clean three-way same-path merging, real semantic-conflict overlays, lifecycle promotion, and dirty-source preservation. |

## Failure Handling

- A dry-run failure changes no Git state. Correct the reported branch, remote, manifest, or pre-existing staged work, then rerun dry-run.
- Before a commit exists, any execution failure unstages only the manifest paths and preserves all working-tree content.
- After a commit exists, a push or remote-verification failure leaves that commit at HEAD and prints the exact `--resume-commit` value. Repair authentication, network, or remote policy and run the documented resume command; do not create a duplicate commit.
- A non-fast-forward rejection uses `integrate-remote-and-resume`; never hand-run pull/rebase and never force-push.
- The integration mode requires a clean tracked worktree and empty index, preserves unrelated untracked files, and rejects any pre- or post-rebase scope mismatch.
- When unrelated tracked changes exist, use the isolated mode with a full publish manifest and an overlay manifest that is a strict subset. It never stashes, resets, or rebases the source worktree.
- A rebase conflict is aborted automatically and the original HEAD is verified restored. Catalog that conflict and open a guarded discovery successor for its concrete semantic resolution; do not resolve it from memory.
- A catalogued semantic conflict uses `isolated-reconcile-and-resume` only with a full publish manifest and explicit overlay manifest. Same-path edits first receive a deterministic three-way file merge; a clean result is accepted, while a real content conflict fails closed unless covered by an overlay or the named ledger/derived-view rule.
- Ledger event IDs are immutable. An identical event is deduplicated, a source-only event is appended in source order, and the operation stops if the same event ID has different canonical content.
- The Git helper never writes the ledger directly. It calls the canonical work-memory merge command, which validates the complete lifecycle and regenerates the derived blocker view atomically.
- Each input ledger must validate independently before union. Historical events accepted by the persisted-ledger compatibility rule remain historical after import; the same shape submitted as a newly authored event is still rejected by the strict lifecycle contract.
- If remote SHA verification differs from local HEAD, stop and preserve the local commit as evidence. Do not report success or start another publish.
- Catalog every failure before correction or retry. Never print credentials or infer invalid
  authentication from `gh auth status`, a sandbox connectivity error, or any other probe that does
  not exercise the guarded Git remote operation.

## Verification

- Historical live path: the manually discovered scoped publish committed 45 approved files as `51b0bee540503b46a757d977ece06b61585a2a72` to `mcp-agents-workflow` `origin/main`, while ten excluded paths remained local and unstaged.
- Reusable path: `tests/test_scoped_git_publish.py` exercises dry-run, exact-scope commit and push to a real local bare Git remote, unrelated-worktree preservation, dirty-index rejection, path-escape rejection, and failed-push resume through the production script entry points.

Pass signal: The script returns ok:true with local commit equal to remote_commit, and unrelated unstaged work remains untouched.

Promoted from `2026-07-15-commit-push-main`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
