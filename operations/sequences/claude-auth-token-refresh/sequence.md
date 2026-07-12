# Claude Auth Token Refresh Sequence

## Purpose

Mint / refresh the **Claude Code OAuth token** and seed it into BOTH the **local
docker container** and **Azure Key Vault `hrness`** (from which the deployed Azure
container reseeds), so the Claude-CLI-backed phases authenticate. This sequence
exists because the token is not reconstructable from memory and expires/rotates,
and because its failure is silent-partial: link/codex phases keep working while
image/PDF (vision) phases fail.

Subscriptions only — never an API key (Claude subscription OAuth `claudeAiOauth`,
or a long-lived `claude setup-token` token).

## Use This Sequence When

- The container's Claude CLI is "Not logged in" or returns `401 Invalid
  authentication credentials`.
- Image/PDF handling fails: `download-detected-file-links` →
  `INPUT_FILE_DOWNLOAD_FAILED` → run fails terminal, while link (codex) tasks
  still work (the tell-tale asymmetry).
- After a local image rebuild that did not carry Claude auth, or after the
  Keychain token expired (accessToken expired and/or refreshToken missing).
- Rotating credentials into Key Vault `hrness` for the Azure deployment.

## Do Not Use This Sequence When

- Only link/codex phases are needed (codex is authed separately via
  `cli-auth-codex`; use `seed-codex-auth` in the local-workflow-orch-image sequence).
- You would run `claude setup-token` / read the Keychain from an agent auto-mode
  context — the credential classifier blocks credential materialization there.
  Run the mint step in a plain operator terminal.

## Why It Breaks (grounded)

- Image/PDF phases run on the **Claude CLI** (vision). `src/workflow_orch/cli/claude_cli.py`
  invokes `claude`; when unauthenticated the phase-ledger producer fails
  (`CLI_EXECUTION_FAILED`, "Not logged in · Please run /login").
- In-container auto-refresh renews the token **in place using the refreshToken**:
  `credential_refresh.py:_refresh_claude_token` (:283) POSTs `grant_type=refresh_token`
  to `_CLAUDE_OAUTH_URL`. A seeded credential with an **empty refreshToken cannot
  renew** → 401 after expiry.
- The macOS Keychain item can be stale (expired accessToken + empty refreshToken).
  `scripts/rotate-credentials.sh:extract_claude_from_keychain` validates expiry and
  **dies** on a stale item, and nothing mints a fresh one. That Azure-only script
  also never seeds the LOCAL container. This sequence fills both gaps.
- KV secret names are fixed: `cli-auth-claude`, `cli-auth-claude-config`
  (`credential_refresh.py:_KV_SECRET_NAMES` :538; `rotate-credentials.sh:kv_secret_name`).

## Script

Primary script (this repo): `mcp-agents-workflow:scripts/claude_auth_refresh.sh`

Activate + guard before operational commands:

```bash
python3 scripts/work_memory.py classify --task-id "<task-id>" --operation-kind auth --repeatable yes --meaningful-steps 3
python3 scripts/work_memory.py select --task-id "<task-id>" --sequence-id claude-auth-token-refresh
python3 scripts/sequence_guard.py activate --task-id "<task-id>" \
  --sequence-doc operations/sequences/claude-auth-token-refresh/sequence.md
```

Commands:

- `status`        — show token state (host keychain / local container / KV). No secrets printed.
- `mint`          — instructions to mint a fresh long-lived token via `claude setup-token`.
- `seed-local`    — seed the local container's `/home/cli-auth/.claude/.credentials.json`.
- `push-kv`       — upload to KV `hrness` (`cli-auth-claude` + `cli-auth-claude-config`).
- `reseed-azure`  — trigger deployed reseed + `/health` (full audited rotation: `rotate-credentials.sh --backends claude`).
- `verify`        — `claude --print` auth probe inside the local container.
- `all`           — seed-local + push-kv + reseed-azure.

## Inputs

- `--token-file PATH` — a file containing EITHER a bare `claude setup-token` token
  (`sk-ant-oat…`) OR a full `claudeAiOauth` JSON. Omit to read the Keychain (fails
  closed if expired / no refreshToken).
- `--config-file PATH` — source for stripped `.claude.json` (default `~/.claude.json`).
- `--container NAME` — default `workflow-orch-local-sequence-check`.
- `--keyvault NAME` — default `hrness`.
- `--dry-run` — print commands only.

## Steps — PROVEN WORKING PATH (2026-07-04)

The operator (browser + subscription; a phone cannot mint — the auto-mode credential
classifier blocks `setup-token`, keychain scanning, and settings edits from the agent)
runs exactly two commands; the agent does everything after `--token-file`:

```bash
claude setup-token > /private/tmp/claude-oat.txt     # step A — mint (browser approve)
scripts/claude_auth_refresh.sh all --token-file /private/tmp/claude-oat.txt   # step B — seed local+KV+azure+verify
rm -f /private/tmp/claude-oat.txt                     # step C — delete the token file
```

**CRITICAL (the gotcha that bit us):** `claude setup-token` redirected to a file writes
the token surrounded by **ANSI escapes + interactive prompt text** (the file was ~24 KB,
not a clean ~100-byte token). The script's extractor now strips ANSI and **regex-pulls
`sk-ant-oat…` from anywhere in the file** (`scripts/claude_auth_refresh.sh`, commit
18983da9d). Do NOT assume the file is a clean token; do NOT hand-edit it. If a future
`setup-token` format changes, fix the regex in `resolve_credential`, not by trimming the file.

Detailed / recovery breakdown:
1. **Diagnose**: `scripts/claude_auth_refresh.sh status` (host keychain / container 401 / KV stale).
2. **Mint** (operator terminal, browser, subscription): `claude setup-token > /private/tmp/claude-oat.txt`.
   Long-lived (~1y), no refreshToken — fine (no in-container refresh needed). Alternative
   refreshable path: complete `claude` `/login` so the Keychain gets a fresh item WITH a
   refreshToken, then run the script WITHOUT `--token-file`.
3. **Seed local**: `scripts/claude_auth_refresh.sh seed-local --token-file /private/tmp/claude-oat.txt`
   → docker cp `.credentials.json` (mode 600) + merge `oauthAccount` → **prints "Local container Claude CLI authenticates"**.
4. **Push KV**: `scripts/claude_auth_refresh.sh push-kv --token-file …` → `cli-auth-claude` + `cli-auth-claude-config` in `hrness`.
5. **Reseed Azure**: `scripts/rotate-credentials.sh --backends claude` (audited) OR `scripts/claude_auth_refresh.sh reseed-azure` → `/health`.
6. **Clean up**: `rm -f /private/tmp/claude-oat.txt` (it is a live credential).
7. **All-in-one**: `scripts/claude_auth_refresh.sh all --token-file /private/tmp/claude-oat.txt` (= 3+4+5).

## Verification

- Local: `docker exec <container> claude --print 'Reply with exactly: AUTH_OK'` → `AUTH_OK`
  (the script's `verify` / `seed-local` does this).
- End-to-end (PROVEN 2026-07-04, task mawf-task-63f27f5d): re-drive a task whose prompt
  has a real screenshot (Dropbox `.png`) via operator `playbook-start`; the
  `download-detected-file-links` phase must succeed → `input_artifacts.files[].download_status
  = materialized` + `description_status = extracted` with a real visual `description_text`
  (e.g. "Admin history screen … order/conversion history table …"), and the digest
  `input-artifacts/file-contents/IMG-001.md` gets injected into the scope-research
  producer prompt (Accepted Task File Description Artifacts block). No `INPUT_FILE_DOWNLOAD_FAILED`.
- Azure: `curl -fsS $REMOTE_URL/health`.

## Failure Fingerprints

- `Not logged in · Please run /login` (container) → no `.credentials.json`; run seed-local.
- `401 Invalid authentication credentials` (container `claude --print`) → seeded token
  expired / bad; the seeded credential has an empty refreshToken (can't auto-renew) →
  MINT fresh (step 2, prefer `claude setup-token`).
- **`all --token-file` ran but the container cred did NOT change (still 401, `.credentials.json`
  mtime unchanged)** → the `--token-file` was `setup-token` output with ANSI/prompt noise
  and the extractor couldn't find the token (pre-18983da9d bug: it only checked the last
  whitespace field). FIXED — the extractor now regex-pulls `sk-ant-oat…` after stripping
  ANSI. If it recurs, the token pattern changed: update the regex in `resolve_credential`.
  Re-run `seed-local`; on success it prints "Local container Claude CLI authenticates".
- `Claude Keychain credentials are invalid or expired` (rotate-credentials.sh) → same;
  mint fresh, then `--token-file`.
- Keychain has 2 items and `-w` returns the stale one → pass a freshly-minted token via
  `--token-file` instead of reading the Keychain. Do NOT dump/scan the Keychain in
  agent auto-mode (classifier blocks credential scanning).
- `--dangerously-skip-permissions cannot be used with root` → the executor drops that
  flag when root (`claude_cli.py:129`); a plain `claude --print` works.
