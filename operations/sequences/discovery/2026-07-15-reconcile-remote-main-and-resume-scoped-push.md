# Sequence Discovery Log: reconcile remote main and resume scoped push

DiscoveryId: discovery-0f04c36f-760d-5cd6-aecb-4381765b7dfa
Status: discovery
CreatedAtUtc: 2026-07-15T09:19:13Z
RegisteredSequenceMatch: none

## Intended Outcome

Integrate an advanced origin/main without force-push, preserve the scoped local commit, resume its push, and verify remote SHA.

## Why This Looks Repeatable

Any scoped publish can race with another writer and receive a non-fast-forward rejection after the local commit exists.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| integrate-and-resume | python3 scripts/scoped_git_publish.py --repo <repo> --manifest <manifest> --branch <branch> --remote <remote> --resume-commit <commit> --integrate-remote | planned | Use only after all approved tracked recovery changes are committed and HEAD names the commit stack to integrate. |
| isolated-integrate-and-resume | python3 scripts/scoped_git_publish.py --repo <repo> --manifest <manifest> --overlay-manifest <overlay-manifest> --message <message> --branch <branch> --remote <remote> --resume-commit <commit> --isolated-integrate-remote | planned | Use when unrelated tracked source changes overlap remote work; publish from a temporary clone and preserve the source worktree unchanged. |
| verify-recovery-automation | uv run pytest tests/test_scoped_git_publish.py | planned | Prove clean remote advance, exact scope preservation, conflict abort/HEAD restoration, and dirty-worktree rejection. |
| inspect-remote-changes | git -C <repo> diff --name-status <merge-base>..<remote>/<branch> | planned | Determine whether remote changes overlap the approved publish manifest. |
| inspect-merge-base | git -C <repo> merge-base HEAD <remote>/<branch> | planned | Identify the common ancestor before choosing a reconciliation mechanism. |
| inspect-remote-head | git -C <repo> rev-parse <remote>/<branch> | planned | Capture the fetched remote branch SHA. |
| inspect-local-head | git -C <repo> rev-parse HEAD | planned | Confirm the preserved local commit. |
| fetch-remote | git -C <repo> fetch <remote> <branch> | planned | Refresh only the named remote branch; never force-push. |
| catalog-push-blocker | python3 scripts/blocker_catalog.py open --run-id <run-id> --subject-id <subject-id> --step-id <step-id> --surface <surface> --error-signature <error-signature> --symptom <symptom> --evidence <evidence> --impact <impact> --boundary <boundary> | planned | Record the non-fast-forward failure before inspection or correction. |

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
