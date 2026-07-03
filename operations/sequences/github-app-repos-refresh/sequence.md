# Sequence: Refresh the available repos for the GitHub App(s)

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
   - writes the new mapping to disk (`repo_mapping_path`), to Key Vault (`keyvault_name`), and to the
     in-memory mapping,
   - returns `{ ok, added:[...], removed:[...], warnings:[...], kv_status, ... }`.
     `warnings` flags any `removed` alias that still has an active local clone.

3. **Capture AFTER state + verify**: `workflow.repos.list` again → confirm the mapping now contains
   the expected repos, and that `list`'s delta matches the refresh response's `added`/`removed`.

## Verification (acceptance)

- `refresh` returned `ok: true`.
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
| write/KV failure in response | mapping fetched but couldn't persist to disk/Key Vault | check `repo_mapping_path` writability + `keyvault_name` access (managed identity) |
| repo added on GitHub but not in `added` | the App installation doesn't actually have access to it | grant the App access to that repo in GitHub App settings, then re-run |

## Invocation options

- **Via the connected `workflow-orch-remote` MCP** (interactive/agent): call
  `workflow.repos.list`, then `workflow.repos.refresh`, then `workflow.repos.list`.
- **Via the wrapper script** (non-interactive): `scripts/github_app_repos_refresh.py`
  (see that script's `--help`) — runs list→refresh→list, prints the diff, and exits non-zero on any
  non-`ok` result or a `NOT_CONFIGURED`/`FORBIDDEN` precondition failure.

## Notes

- Idempotent: running it again with no GitHub-side change returns `ok:true` with empty
  `added`/`removed`.
- Does NOT touch task/workflow state; safe to run while workflows are idle. (It only rewrites the
  alias mapping + KV + cache.)
- Canonical registry: promote/keep this in the memory-knowledge sequence registry (per G18) in
  addition to this repo copy.
