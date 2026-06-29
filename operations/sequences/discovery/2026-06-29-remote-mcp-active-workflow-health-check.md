# Sequence Discovery Log: remote-mcp-active-workflow-health-check

Status: discovery
CreatedAtUtc: 2026-06-29T10:56:22Z
RegisteredSequenceMatch: none

## Intended Outcome

Check whether the deployed Workflow Orchestrator MCP has active/busy workflows

## Why This Looks Repeatable

Before deploys, debugging, and operator runs we often need a quick non-mutating deployed active-workflow count check.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| Interpret deployed health JSON | Read runningWorkflowCount, busyWorkflowCount, pendingWorkflowCount, and waitingApprovalCount from the captured /health JSON | runningWorkflowCount=0, busyWorkflowCount=0, pendingWorkflowCount=0, waitingApprovalCount=0 | No active workflow is running at the deployed MCP according to /health. orphanedRunningCount was null because orphanedCheckStatus was skipped. |
| Fetch deployed health JSON | curl -sS https://workflow-orch-app-evbxebcccsd7fpgp.westeurope-01.azurewebsites.net/health | planned before execution | Read-only deployed health endpoint check for runningWorkflowCount and busyWorkflowCount. |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
