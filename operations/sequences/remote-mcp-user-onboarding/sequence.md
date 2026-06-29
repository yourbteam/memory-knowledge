# Remote MCP User Onboarding Sequence

## Purpose

Create or repair an employee so the deployed Remote MCP harness and MAWF can both recognize the same person on first use.

This sequence exists because the deployed login path reads the Azure Key Vault user registry. A local stdio `workflow.user.add` can show a user locally while the deployed `/auth/challenge` endpoint still returns `Account not found`. For deployed employees, the deployed registry is authoritative.

## Use When

- Adding a new employee who will use the deployed Remote MCP harness.
- Repairing `Account not found` from `/auth/challenge`.
- Aligning an employee's repo access to an existing employee.
- Rotating and saving a first-use token for a deployed employee.

Do not use this sequence for local container-only tests unless the local sequence explicitly says to seed the same registry.

## Stable Boundaries

- Deployed auth boundary: `AZURE_KEYVAULT_NAME=hrness`, secret `workflow-orch-user-registry`, consumed by deployed `/auth/challenge` and `/auth/verify`.
- Local stdio boundary: useful for local development only; it is not proof that the deployed login can see the user.
- MAWF identity boundary: memory-knowledge MAWF user storage, managed through `mawf_get_user` and `mawf_upsert_user`.
- Repo access boundary: auth registry `allowedRepos` must use the canonical memory repository key, such as `neocurrency-dashboard`, not a GitHub full name unless that full name is explicitly what the deployed repo mapping expects.

## Inputs

- Employee email.
- First name, last name, and display name.
- Employee user id for deployed auth.
- Role, usually `employee`.
- Canonical memory repository key or the existing employee whose access should be mirrored.
- Token output path on the administrator machine.
- Deployed server URL, normally `wss://workflow-orch-app-evbxebcccsd7fpgp.westeurope-01.azurewebsites.net/ws`.

## Preflight

1. Invoke `sequence-runner`, read this sequence, then activate it:

   ```bash
   uv run python scripts/sequence_guard.py activate --sequence-id "remote-mcp-user-onboarding" --sequence-doc "operations/sequences/remote-mcp-user-onboarding/sequence.md"
   ```

2. Confirm the deployed registry source without printing secrets:

   ```bash
   az webapp config appsettings list --resource-group workflow-orch-rg --name workflow-orch-app --query "[?name=='AZURE_KEYVAULT_NAME' || name=='WORKFLOW_ORCH_USER_REGISTRY_SECRET' || name=='WORKFLOW_ORCH_USER_REGISTRY_ENABLED'].{name:name,value:value}" -o json
   ```

3. Confirm the canonical repo key with memory-knowledge:

   - Call `mcp__memory_knowledge.list_repositories(include_inactive=true)`.
   - Use the `repository_key` value as the access key.
   - If mirroring another employee, inspect the deployed auth registry entry for that employee and copy only the intended repo key.

4. Confirm the MAWF user:

   - Call `mcp__memory_knowledge.mawf_get_user(email=<employee-email>)`.
   - If missing or wrong, call `mcp__memory_knowledge.mawf_upsert_user(email=<employee-email>, display_name=<name>, role_code="employee", status_code="active")`.

## Deployed Auth Registry Write

Preferred path: use the remote user-admin package against the deployed server.

1. List deployed users in admin mode and confirm whether the employee exists:

   ```bash
   python3 dist/remote-mcp-user-admin/remote_mcp_user_admin_tui.py --server-url wss://workflow-orch-app-evbxebcccsd7fpgp.westeurope-01.azurewebsites.net/ws --agent-action user-list --tool-timeout-seconds 60
   ```

2. If the package asks for a challenge code for the administrator, put the emailed code in a local file and rerun the returned `nextCommandTemplate`. Never paste the code into chat.

3. For a new user, run the package's `new-user-*`, `repo-access-*`, `create-user-review`, and `create-user-apply` flow. Use `--token-output-file <private-token-path>` on `create-user-apply`.

4. For an existing user, use the package's detail/update/repo-access actions to set:

   - `email` to the employee email.
   - `firstName` and `lastName` to the employee name.
   - `role` to `employee`.
   - `status` to `active`.
   - `allowedRepos` to exactly the approved canonical repo keys.

Fallback path when the package write is blocked but Azure admin access is available:

1. Read `hrness/workflow-orch-user-registry` with `az keyvault secret show`.
2. Add or replace exactly one JSON user object for the employee.
3. Generate a new `tokenKey`, set `tokenExpiresAt`, set `status` to `active`, and set `allowedRepos` to the canonical repo key list.
4. Write the complete registry JSON back with `az keyvault secret set`.
5. Save only the generated token key to the requested local file with mode `0600`.
6. Do not print token keys, JWTs, challenge codes, or the raw registry JSON.

## Verification

1. Wait at least 60 seconds for deployed registry reload.

2. Run a redacted deployed auth preflight with `noChallenge=true`:

   - Request: `/auth/challenge?email=<employee-email>&tokenKey=<saved-token>&noChallenge=true`
   - Pass: HTTP 200 with `status: ok`, or a non-`not_found` challenge status when the token needs refresh.
   - Fail: `status: not_found`, which means the deployed endpoint still does not read the registry row.

3. Verify the MAWF user again with `mawf_get_user`.

4. Verify repo access:

   - The deployed auth registry row must contain exactly the intended `allowedRepos`.
   - The canonical memory repository key must exist in `list_repositories`.
   - When task tools are available, `workflow_task_choices_mine(actorEmail=<employee-email>, repositoryKey=<repo-key>)` must not fail with missing actor or repo-access errors.

5. Verify the token file:

   ```bash
   ls -l <private-token-path>
   ```

   Pass when the file exists and is owner-only, such as `-rw-------`.

## Failure Handling

| symptom | meaning | action |
| --- | --- | --- |
| `/auth/challenge` returns `Account not found` | The deployed auth registry does not contain the email, or the wrong deployment/secret was updated. | Inspect deployed app settings, update `hrness/workflow-orch-user-registry`, wait 60 seconds, retry deployed preflight. |
| Local `workflow.user.list` shows the user but deployed auth returns `not_found` | The local stdio registry is not the deployed registry. | Treat local evidence as non-authoritative and write the deployed registry. |
| `MAWF_USER_NOT_FOUND` or actor-required errors | The MAWF identity boundary is missing the employee. | Run `mawf_upsert_user` and verify with `mawf_get_user`. |
| Repo choices are empty or access is denied | `allowedRepos` uses the wrong key or has extra/missing repos. | Use memory-knowledge `repository_key` and align to exactly the intended list. |
| `challenge_required` or expired token | The user exists, but the token needs challenge refresh or rotation. | Rotate/generate a fresh token and save it privately; do not print it. |
| `rate_limited` | A challenge email was recently sent. | Wait for the cooldown or use the latest emailed code. |
| `email_failed` | The user exists but challenge email delivery failed. | Check SendGrid/email allowlist and retry after fixing delivery. |

## Evidence To Report

- Deployed auth user id, email, role, status, allowed repos, and token expiry.
- MAWF user id, email, role code, and status code.
- Token file path and file mode only.
- Redacted `/auth/challenge` status.
- Repo key evidence from memory-knowledge.

Never report raw token keys, JWTs, challenge codes, Azure credentials, or raw secret JSON.
