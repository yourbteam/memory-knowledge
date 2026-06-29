# Sequence Discovery Log: remote-mcp-user-onboarding

Status: discovery
CreatedAtUtc: 2026-06-23T15:55:03Z
RegisteredSequenceMatch: none

## Intended Outcome

Create a complete remote MCP/MAWF user so first login works without Account not found

## Why This Looks Repeatable

Every new employee needs the same auth-registry, MAWF-user, repo-access, token delivery, and verification sequence

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| Verify deployed auth preflight | redacted /auth/challenge preflight with noChallenge=true after registry reload | passed with HTTP 200 status ok for sdimitrov | Proved deployed login no longer returns Account not found |
| Write deployed auth registry | az keyvault secret show/set hrness workflow-orch-user-registry with token saved to Downloads | passed; sdimitrov active employee with allowedRepos neocurrency-dashboard and owner-only token file | Wrote the registry consumed by deployed /auth/challenge; no token or raw registry JSON printed |
| Compare local and deployed registries | remote user-admin user-list in deployed admin mode | deployed registry listed existing users including amantchev but not sdimitrov | Confirmed local stdio user creation was not authoritative for deployed login |
| Confirm deployed symptom | redacted /auth/challenge preflight for sdimitrov against deployed endpoint | failed with HTTP 403 status not_found Account not found | Proved the user-facing deployed login path still could not see the employee |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
