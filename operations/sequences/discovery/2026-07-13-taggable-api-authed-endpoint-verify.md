# Sequence Discovery Log: taggable-api-authed-endpoint-verify

DiscoveryId: discovery-3db5d8f0-2802-5ecb-8a9d-2599c66d5201
Status: discovery
CreatedAtUtc: 2026-07-15T12:33:16Z
RegisteredSequenceMatch: none

## Intended Outcome

Verify a deployed taggable-api admin endpoint on dev by logging in (email/password from env, never printed) and calling the endpoint, comparing actual vs expected.

## Why This Looks Repeatable

Every feature touching an admin API endpoint needs live auth'd verification on dev; the login->token->call chain, secret-safe creds handling, and response-count checks recur for every such change.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| CORRECTION: xlsx timeout for the full report | curl --max-time 300 (was 180) | no-filter FULL .xlsx returns 200 in ~219s; 180s cap caused a false HTTP-500. Narrow range=200/13s. | The non-optimized V3 handler is slow for the full 149-tour report (pre-existing; optimized variant exists for this). Not caused by the scope-filter change. |
| VERIFIED live on dev (result) | bash scripts/verify-v3-report-scope.sh | login 200; optimized matrix 149/1/5/0/1 (all match); production .xlsx filtered=200/8972B | Proves feature end-to-end on real HTTP+EF path, both handlers. |
| Run verification matrix | taggable-api: bash scripts/verify-v3-report-scope.sh | PENDING live confirmation (env-export fix applied); prints tour counts only | Expected super-admin: 149 / 1 / 5 / 0 / 1; plus xlsx endpoint 200+bytes (both-handler coverage). |
| Login contract (AuthContracts.cs / AuthController.cs) | POST /api/auth/admin/login body {email,password} -> token at .data.access_token | 200 -> AuthTokenEnvelope{data:{access_token,...}}; 401 on bad creds | LoginRequest(Email,Password,Sid?); Ok(new AuthTokenEnvelope(tokens)). |
| CORRECTION: auto-export sourced env before subprocesses | set -a; source ~/.taggable-verify.env; set +a | Fixes KeyError TAGGABLE_ADMIN_EMAIL / login HTTP 400 (plain 'source' does not export → python os.environ misses it) | Failure fingerprint: python KeyError from os.environ + login HTTP 400. |
| Secret-safe credentials | ~/.taggable-verify.env holds TAGGABLE_ADMIN_EMAIL / TAGGABLE_ADMIN_PW (outside any git repo); never printed | Runner sources them; token/creds never echoed | No pasting tokens in chat; no scraping creds from FS (safety-blocked). Env-file is the sanctioned channel. |
| Deploy feature under test to dev | taggable-api: bash scripts/deploy-api.sh  (registered sequence taggable-api-deploy) | zipdeploy 200; WebJob intact; swagger 200; deployed swagger schema shows the new field (proves feature is in the build) | Verify via swagger SCHEMA, not just app restart. |

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
