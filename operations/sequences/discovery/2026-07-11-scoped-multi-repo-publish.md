# Sequence Discovery Log: scoped-multi-repo-publish

Status: discovery
CreatedAtUtc: 2026-07-11T14:03:25Z
RegisteredSequenceMatch: none

## Intended Outcome

Commit and push only approved task-owned paths across existing repository branches

## Why This Looks Repeatable

Working-agreement and skill projections are distributed across multiple repositories and require repeatable scope-safe publication

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| Push only branches whose unpublished history equals the approved commit | git push origin BRANCH | Five projection commits pushed successfully; branches with older unpublished commits were withheld. | Require explicit authorization before pushing pre-existing unrelated commits. |
| Create projection commits from explicit paths | git add -- AGENTS.md; git diff --cached --name-status; git diff --cached --check; git commit -m "Refresh working agreement directives" | Six focused commits created, each containing only AGENTS.md. | Never use repository-wide staging in dirty worktrees. |
| Refresh remote refs and safely fast-forward behind branches | git fetch origin; git pull --rebase --autostash origin BRANCH | Remote refs refreshed; three branches fast-forwarded; autostashes reapplied and cleared. | Hash-check unrelated modified files before and after autostash. |
| Preflight every repository | git status --short --branch; git remote get-url origin; git rev-list --left-right --count UPSTREAM...HEAD; git diff --cached --name-status | Identified clean indexes, three behind branches, one branch with older unpublished history, and one repository with a prior unpublished commit. | Treat ahead history outside the approved task surface as a push blocker. |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
