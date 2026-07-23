# Sequence: Refresh the available repos for the GitHub App(s)

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

**sequence-id:** `github-app-repos-refresh`
**Purpose:** Re-sync the repository alias mapping (the "available repos") from what the configured
GitHub App installation(s) can actually access — after a repo is added to / removed from an App
installation on GitHub, or after a new App/installation is configured. Updates the on-disk mapping,
Key Vault, and the running server's in-memory cache so `workflow.project.set <alias>` and per-user
repo access see the current set.

**When to run:** you added or removed a repository from the GitHub App installation on GitHub (or
installed the App on a new org/repo), and the workflow-orch server still shows the old repo list.

**Owner/role:** ADMIN. `workflow.repos.refresh` is admin-gated (`mcp_server.py:9296 _is_admin()`).

---

## Preconditions (verify before running)

Grounded in `credential_refresh.py:895 validate_repos_refresh_preconditions` +
`handle_repos_refresh` (`mcp_server.py:9294`):

1. **Admin session.** The caller must be an admin (else `FORBIDDEN: Admin access required`). Connect
   with an admin token / admin user.
2. **Git remote management enabled.** The server's git manager must be a `GitRemoteManager`
   (else `NOT_AVAILABLE: Repository refresh requires Git remote management.`).
3. **GitHub App auth configured.** `git_manager.auth_registry` must exist and be configured — i.e.
   `github_app_id`, an installation, and the App private key/PEM (+ `app-config.json` for multi-org)
   are set (else `NOT_CONFIGURED: GitHub App auth is not configured. Cannot refresh repo mapping.`).
   Quick presence check (does NOT print secrets), from the running container:
   ```bash
   docker exec <container> sh -lc 'cd /app && PYTHONPATH=/app/src /app/.venv/bin/python -c "
   from workflow_orch.settings import get_settings; s=get_settings()
   print(\"github_app_id_set=\", bool(s.git.github_app_id))
   print(\"github_app_installation_id_set=\", bool(s.git.github_app_installation_id))
   print(\"github_app_pem_path_set=\", bool(s.git.github_app_pem_path))
   print(\"github_app_config_path_set=\", bool(s.git.github_app_config_path))
   print(\"repo_mapping_path_set=\", bool(s.git.repo_mapping_path))
   "'
   ```

---

## Steps (exact tool calls)

These are MCP tools on the workflow-orch server (call them through the connected
`workflow-orch-remote` MCP, or via the wrapper script below). All are non-destructive except that
`refresh` rewrites the alias mapping file + Key Vault secret + in-memory cache.

1. **Capture BEFORE state** (read-only, non-admin):
   `workflow.repos.list` → record the current alias → `org/repo` mapping.

2. **Refresh** (admin):
   `workflow.repos.refresh` (no args). It:
   - queries every configured GitHub App installation for accessible repos
     (`auth_registry.list_all_repos()`),
   - diffs against the current mapping at `git_settings.repo_mapping_path`,
   - writes the new mapping to BOTH the on-disk file (`repo_mapping_path`) AND the canonical Key
     Vault (`credential_settings.keyvault_name`, via `writeback_repo_mapping_to_keyvault`), plus the
     in-memory mapping,
   - returns `{ ok, added:[...], removed:[...], warnings:[...], kvWriteback, ... }` where
     `kvWriteback` is **`"ok"`** only when the Key Vault was actually written, **`"skipped"`** when
     the target server has NO `keyvault_name` configured (e.g. the isolated local sequence-check
     container), or **`"error: <msg>"`** on a KV write failure. `warnings` flags any `removed`
     alias that still has an active local clone.

   > A refresh that returns `kvWriteback: "skipped"` (or `error:`) updated ONLY the local mapping,
   > NOT the canonical Key Vault — the change is EPHEMERAL (lost on container rebuild) and is NOT a
   > durable, cross-instance repo-availability update. Run against the KV-backed server (the deployed
   > `workflow-orch`), not the isolated local sequence-check container.

3. **Capture AFTER state + verify**: `workflow.repos.list` again → confirm the mapping now contains
   the expected repos, and that `list`'s delta matches the refresh response's `added`/`removed`.

## Verification (acceptance)

- `refresh` returned `ok: true` **AND `kvWriteback: "ok"`** — i.e. the mapping was persisted to BOTH
  the Key Vault (canonical/durable) AND the local mapping file. A `kvWriteback` of `"skipped"`/`error`
  means the refresh did NOT update the Key Vault and MUST NOT be accepted as durable (the wrapper
  script exits non-zero in that case unless `--allow-local-only` is passed for an explicitly
  ephemeral, local-only refresh).
- The `added`/`removed` in the refresh response match the intended change (the repo you added on
  GitHub appears in `added`; a removed one appears in `removed`).
- Step-3 `workflow.repos.list` shows the new repo alias (and it now works with
  `workflow.project.set <alias>`).
- Any `warnings` about a removed alias with an active clone were reviewed (that clone won't resolve
  after removal).

## Failure handling

| Symptom | Meaning | Action |
| --- | --- | --- |
| `FORBIDDEN: Admin access required` | not an admin session | reconnect with an admin token/user |
| `NOT_AVAILABLE: … requires Git remote management` | server not running GitRemoteManager | check deployment/config; git remote management must be enabled |
| `NOT_CONFIGURED: GitHub App auth is not configured` | App id/installation/PEM missing | run the presence check above; seed the GitHub App credentials (id, installation, PEM, `app-config.json`) |
| `GITHUB_API_ERROR: <msg>` | GitHub API call failed (auth expired, rate limit, network) | verify the App installation is still valid on GitHub; retry; check App token minting |
| `kvWriteback: "skipped"` (script exits 2) | target server has NO `keyvault_name` — the refresh updated only the local mapping (ephemeral, not durable). This is the isolated local sequence-check container. | Run against the KV-backed **deployed** `workflow-orch` server so the canonical Key Vault is updated. Only pass `--allow-local-only` when you deliberately want an ephemeral local-only refresh. |
| `kvWriteback: "error: <msg>"` | mapping written to disk but the Key Vault write FAILED (auth/managed-identity/network) | check the target's Key Vault access (managed identity / `keyvault_name`); the mapping is NOT durably persisted until this succeeds — re-run after fixing KV access. |
| repo added on GitHub but not in `added` | the App installation doesn't actually have access to it | grant the App access to that repo in GitHub App settings, then re-run |

## Target (which server to run against)

The refresh updates the stores of **the server it runs on**. To make repos DURABLY available across
harness instances you must update the canonical Key Vault, so run against a **KV-backed** server:

- **Deployed `workflow-orch` (durable — required for a real change).** `keyvault_name` is set →
  `workflow.repos.refresh` writes BOTH the Key Vault (canonical) and that server's local mapping →
  `kvWriteback: "ok"`. This is the acceptable path; every instance that reads the KV then sees the
  new repos.
- **Local sequence-check container (ephemeral only).** `keyvault_name` is EMPTY → the refresh writes
  only the container's local `repo-mapping.json` + in-memory cache and returns `kvWriteback:
  "skipped"`. Useful to make the LOCAL harness see a repo for a one-off local drive, but it is NOT
  durable and does NOT update the Key Vault. Requires the explicit `--allow-local-only` flag.

## Invocation options

- **Via the connected `workflow-orch-remote` MCP** (interactive/agent): call
  `workflow.repos.list`, then `workflow.repos.refresh`, then `workflow.repos.list`; require
  `kvWriteback == "ok"`.
- **Via the wrapper script** (non-interactive): `scripts/github_app_repos_refresh.py`
  (see `--help`) — runs list→refresh→list, prints the diff + `kvWriteback`, verifies the KV was
  written, and **exits non-zero** on any non-`ok` result, a `NOT_CONFIGURED`/`FORBIDDEN` precondition
  failure, OR a KV-skipped/errored writeback (unless `--allow-local-only` is passed for the ephemeral
  local-container case). Point it at the deployed server with `--server-url wss://<host>/ws` (+ admin
  auth in the env) for the durable path.

## Notes

- Idempotent: running it again with no GitHub-side change returns `ok:true` with empty
  `added`/`removed`.
- Does NOT touch task/workflow state; safe to run while workflows are idle. (It only rewrites the
  alias mapping + KV + cache.)
- **Durability rule:** a refresh is only "done" when it updated BOTH the Key Vault and the local
  mapping (`kvWriteback: "ok"`). A `skipped`/`error` writeback means the change is not durable — see
  Failure handling. This is why the wrapper script fails a KV-skipped run by default.
- Canonical registry: kept in the memory-knowledge sequence registry (per G18); automation lives at
  `mcp-agents-workflow:scripts/github_app_repos_refresh.py`.
