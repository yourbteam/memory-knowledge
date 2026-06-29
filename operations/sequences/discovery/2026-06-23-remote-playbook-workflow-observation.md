# Sequence Discovery Log: remote-playbook-workflow-observation

Status: discovery
CreatedAtUtc: 2026-06-23T17:39:50Z
RegisteredSequenceMatch: none

## Intended Outcome

Run one real playbook workflow at a time through the remote-mcp-operator package and record code-change-worthy issues.

## Why This Looks Repeatable

We need to validate deployed playbook workflows the same way Kamen will use them, while preserving telemetry/status/artifact observations and issue notes for follow-up fixes.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| inspect remote operator playbook help | python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --help | Help output confirms dedicated playbook actions: playbook-start, playbook-continuation-select, and playbook-repair. | Use package-owned playbook actions for real playbook workflow observation; do not use older task-start continuation inference for this validation. |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
