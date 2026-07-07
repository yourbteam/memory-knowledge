# Repeatable Operational Sequences

This registry is the canonical, **cross-project** home (in the `memory-knowledge` repo) for repeatable operational sequences — the first place to check before running one. A sequence's automation may live in another repo; the `automation` column names it as `<repo-key>:<path>` (e.g. `mcp-agents-workflow:scripts/…`, `taggable-api:tools/…`).

Use it when a task involves a multi-step command sequence that has been run before or is likely to be run again. The matching sequence folder owns the executable steps, scripts, required inputs, failure handling, and verification evidence. If no registered sequence matches, create a discovery log before or during execution so the real steps can be promoted into a registered sequence after they are validated.

## Registry Rules

- Invoke the `sequence-runner` skill before starting a repeatable sequence.
- Read this registry, select one matching row, then read that row's `sequence.md`.
- Read the canonical working-agreement directives before sequence activation:
  ```bash
  uv run python scripts/directive_guard.py read --mode "<mode>"
  ```
- Activate the selected sequence before running operational commands:
  ```bash
  uv run python scripts/sequence_guard.py activate --sequence-id "<sequence-id>" --sequence-doc "operations/sequences/<sequence-id>/sequence.md"
  ```
- Before running a sequence command, guard it with `scripts/sequence_guard.py guard` and one of the allowed command sources: `sequence_doc`, `discovery_log`, `script`, or `tool_help`.
- Prefer the scripts named by the sequence document over reconstructed shell commands.
- Do not print secrets, tokens, auth payloads, or private challenge values in sequence output.
- If a sequence step fails, record the failed step and exact error before changing the sequence.
- If the same manual correction is needed twice, update the sequence document or script before claiming the sequence is reusable.
- If no registered sequence matches, create a discovery log under `operations/sequences/discovery/` with `scripts/sequence_discovery_log.py` and append validated steps as they are discovered.
- Do not run a repeatable sequence command from memory. If the command is not in a sequence doc, not already in a discovery log, not a script invocation, and not verified from tool help, the guard must fail.

## Available Sequences

| sequence id | use when | sequence folder | automation | pass signal |
| --- | --- | --- | --- | --- |
| `local-workflow-orch-image` | Build and locally validate a `workflow-orch` Docker image before deploying server/runtime changes, testing Codex auth inside the image, or reproducing deployed container behavior locally. | `operations/sequences/local-workflow-orch-image/` | `mcp-agents-workflow:scripts/local_workflow_orch_image_harness.py` | Docker image exists, container health passes, optional Codex auth seed/probe passes when requested. |
| `remote-mcp-user-onboarding` | Add or repair an employee for deployed Remote MCP/MAWF access, including challenge login, repo access, MAWF identity, and token delivery. | `operations/sequences/remote-mcp-user-onboarding/` | `mcp-agents-workflow:dist/remote-mcp-user-admin/remote_mcp_user_admin_tui.py` plus `mcp__memory_knowledge.mawf_upsert_user` | Deployed `/auth/challenge` returns `ok` or a challenge status for the user, MAWF user is active, allowed repos contain only the canonical memory repository key, and the token file exists with owner-only permissions. |
| `taggable-source-reload` | Idempotently re-load a source's per-table CSV export into `taggable-dev` via the `db-import` WebJob (weekly/ad-hoc reload of app/app2/app3) — no wipe. | `operations/sequences/taggable-source-reload/` | `taggable-api:tools/Taggable.MigrationRunner/scripts/reload-source.sh` | WebJob run status Success; `OauthAccessTokens` count stable (no PK collision / no doubling); big tables grow modestly not doubled; other `system_record_id`s untouched; DB scaled back to S1. |
| `mawf-playbook-full-test` | Regression-test the MAWF 4-playbook chain (Research → Plan → Write-code → Review) end-to-end on the local image **through all optional gates**, stopping on the first blocker (fix via `/playbook-convergence-loop`, re-enter per `mawf-playbook-blocker-reentry`). | `operations/sequences/mawf-playbook-full-test/` | `mcp-agents-workflow:scripts/mawf_playbook_test_sequence.py` (`--gate-policy` full) | Chain reaches Review with **both** optional gates driven to zero `COVERAGE_GAP`. |
| `mawf-playbook-speed-test` | Fast smoke of the MAWF 4-playbook chain spine — same chain **skipping** the optional gates; stop on first blocker (fix + re-enter per `mawf-playbook-blocker-reentry`). | `operations/sequences/mawf-playbook-speed-test/` | `mcp-agents-workflow:scripts/mawf_playbook_test_sequence.py` (`--gate-policy` speed) | Chain reaches Review on the skip branch with no blocker. |
| `mawf-playbook-blocker-reentry` | **Sub-sequence (not run standalone)** — the shared blocker → `/playbook-convergence-loop` → narrowest-blast-radius re-entry contract invoked by the full/speed tests. | `operations/sequences/mawf-playbook-blocker-reentry/` | — (sub-sequence; invoked by full/speed) | N/A — contract followed by the invoking sequence. |
| `github-app-repos-refresh` | Re-sync the available repository alias mapping from the configured GitHub App installation(s) after a repo is added to / removed from an App installation (admin `workflow.repos.refresh`), so `workflow.project.set <alias>` and per-user repo access see the current set. | `operations/sequences/github-app-repos-refresh/` | `mcp-agents-workflow:scripts/github_app_repos_refresh.py` | `workflow.repos.refresh` returns `ok:true`; the `added`/`removed` match the intended GitHub-side change; a follow-up `workflow.repos.list` shows the new alias; any `removed`-with-active-clone warnings reviewed. |
| `claude-auth-token-refresh` | Mint/refresh the Claude Code OAuth token and seed it into the local docker container AND Azure Key Vault `hrness` (`cli-auth-claude`/`-config`) — when the container's Claude CLI is "Not logged in"/401, or image/PDF (vision) phases fail with `INPUT_FILE_DOWNLOAD_FAILED` while link/codex phases still work, or after a rebuild/rotation. Subscriptions only, no API keys. | `operations/sequences/claude-auth-token-refresh/` | `mcp-agents-workflow:scripts/claude_auth_refresh.sh` (+ `scripts/rotate-credentials.sh` for the audited Azure path) | `claude --print` authenticates inside the container (`AUTH_OK`); a screenshot task's `download-detected-file-links` succeeds (`description_status: extracted`, no `INPUT_FILE_DOWNLOAD_FAILED`); Azure `/health` ok. |
| `taggable-api-deploy` | Deploy the taggable-api ASP.NET app to the Azure Web App `taggable-api-dev` after merging to main (or any checkout you want live on dev). | `operations/sequences/taggable-api-deploy/` | `taggable-api:scripts/deploy-api.sh` | `zipdeploy HTTP 200`, the `db-import` WebJob is still present (not clobbered), and `taggable-api-dev.../swagger/v1/swagger.json` returns HTTP 200. |
| `taggable-admin-spa-deploy` | Build the taggable-admin-spa (Vite/React) front-end and deploy its static `dist/` build to the Azure Web App `taggable-admin` (RG `taggable`, Linux NODE 22-lts) after merging admin-UI changes. `VITE_API_BASE_URL` is baked at build (default dev `https://taggable-api-dev.azurewebsites.net/api`). Deploys via `az webapp deploy` (AAD auth) because SCM basic auth is disabled on the app. | `operations/sequences/taggable-admin-spa-deploy/` | `taggable-admin-spa:scripts/deploy-admin-spa.sh` | `az webapp deploy` exits 0 (`deploy accepted`), the dev API base is baked into the bundle (no `localhost` leak), and `taggable-admin.azurewebsites.net/` returns HTTP 200 serving a Vite `index-*.js` asset. |
| `taggable-media-worker-deploy` | Deploy the `Taggable.MediaWorker` **continuous** WebJob to `taggable-api-dev` (RG `Umbraco`) — the background FFmpeg worker that turns pending `product_video` rows into 720p + watermark + poster renditions. Separate from the API deploy; does not touch the `db-import` WebJob. **PENDING FIRST RUN** (blocked on ffmpeg binaries K1, storage App Settings K5, Always On K3, and applying the `product_video` migration K10). | `operations/sequences/taggable-media-worker-deploy/` | `taggable-api:scripts/deploy-media-worker.sh` | WebJob deploy HTTP 200/201 and `GET $SCM/api/continuouswebjobs/media-worker` reports `status: Running`; final line `DONE: deployed continuous WebJob media-worker ...`. |
| `airgapped-local-bulgarian-stt` | Set up (home/dev/prod) a self-hosted, air-gapped Bulgarian speech-to-text env (ffmpeg + faster-whisper, vendored weights) and transcribe a callcenter recording **offline with no network egress** (compliance NFR-7). Provision is online; process/verify run air-gapped; diarization comes from stereo channel-split, not a vendor. | `operations/sequences/airgapped-local-bulgarian-stt/` | `callcenter-harness:scripts/setup_airgapped_stt.sh` (+ `scripts/transcribe_airgapped.py`) | `verify <audio>` prints `VERIFY PASS`: transcript + per-word timestamps produced with network black-holed (dead proxy + `HF_HUB_OFFLINE=1`); model loaded from a local vendored dir. |

## Missing Sequence Discovery

Use this path when the task is about to run a repeatable sequence but the `Available Sequences` table has no matching row.

Start a discovery log:

```bash
uv run python scripts/sequence_discovery_log.py start --sequence-name "<short name>" --outcome "<intended outcome>" --why-repeatable "<why this will likely recur>"
```

Append each validated step:

```bash
uv run python scripts/sequence_discovery_log.py append-step --file <log-path> --step "<step>" --command "<command or action>" --result "<result>" --note "<correction or note>"
```

Promotion rule: do not create a registered sequence folder until the discovery log contains stable commands or documented human steps, required inputs, failure handling, and verification evidence.
