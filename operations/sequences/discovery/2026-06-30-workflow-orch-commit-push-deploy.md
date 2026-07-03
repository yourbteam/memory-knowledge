# Sequence Discovery Log: workflow-orch-commit-push-deploy

Status: discovery
CreatedAtUtc: 2026-06-30T10:51:14Z
RegisteredSequenceMatch: none

## Intended Outcome

Commit, push, and deploy workflow-orch changes to Azure

## Why This Looks Repeatable

Workflow-orch code fixes frequently need the same commit, push, Azure deployment, and health verification sequence.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| deploy workflow-orch to Azure | ./infra/azure-push.sh | planned after clean pre-deploy health | Use checked-in deployment script with built-in post-deploy health check. |
| integrate remote before push | /usr/bin/git pull --rebase | planned after non-fast-forward push rejection | Preserve local fix while integrating newer origin/main commits. |
| push workflow-orch fix with system git fallback | /usr/bin/git push | planned after bundled git credential-osxkeychain failure | Use system Git when bundled/runtime Git cannot access macOS credential helper. |
| push workflow-orch fix | git push | planned | Push committed main branch fix to origin before Azure deployment. |
| commit workflow-orch fix | git commit -m "fix: repair remote task resume selection" | planned | Commit staged operator/status hydration fix without AI attribution. |
| stage workflow-orch fix | git add -A | planned | Stage the already-reviewed remote MCP operator, MAWF status hydration, generated package, tests, and research artifacts. |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
