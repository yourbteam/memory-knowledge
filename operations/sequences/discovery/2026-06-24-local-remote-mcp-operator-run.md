# Sequence Discovery Log: local-remote-mcp-operator-run

Status: discovery
CreatedAtUtc: 2026-06-24T17:47:16Z
RegisteredSequenceMatch: none

## Intended Outcome

Run the packaged remote MCP operator against a local workflow-orch Docker/WebSocket endpoint with the correct network permissions and evidence capture.

## Why This Looks Repeatable

This is the path Kamen uses to validate MAWF workflows locally through the sendable package before deploying.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| Run packaged operator WebSocket calls with network permission | python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --server-url ws://127.0.0.1:<local-port>/ws --agent-action <action> | Sandboxed execution can fail before reaching the local server with REMOTE_CONNECT_FAILED and PermissionError: [Errno 1] Operation not permitted; rerunning the same package command with network escalation reaches the real workflow status. | In Codex, local WebSocket package calls to Docker-hosted workflow-orch require sandbox escalation. Do not diagnose a sandbox PermissionError as a workflow/runtime failure. |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
