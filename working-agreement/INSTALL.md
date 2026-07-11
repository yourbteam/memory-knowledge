# Working Agreement — Install (Tier-1 directives + Tier-2 corpus)

How to set up the full working-agreement system on a new machine. Two layers:

- **Tier-1 — directives:** `DIRECTIVES.md` auto-injected into every Claude Code prompt by a hook.
- **Tier-2 — corpus:** durable knowledge in the deployed `memory-knowledge` service (PG + Qdrant),
  written via an MCP tool and auto-retrieved per prompt by a second hook.

> **Paths below assume the repo lives at `/Users/kamenkamenov/memory-knowledge`.** On a different
> machine, either clone to that path or override via the env vars noted at each step.

## 0. Prerequisites

- This repo cloned locally.
- **Python venv with the `mcp` client** (used by the hydration hook and the backfill script):
  ```bash
  cd <repo>
  uv venv && uv pip install --python .venv/bin/python mcp
  ```
  The hook/backfill only need the `mcp` package — do **not** require a full `pip install -e .`
  (the service's `fastembed`/`onnxruntime` deps have no wheel on some platforms, e.g. x86-mac/py3.14,
  and embedding runs server-side anyway).
- **Node/`npx`** on PATH (for `mcp-remote`, which bridges the deployed MCP into Claude).

## 1. Tier-1 — directives hook

Register `inject-directives.sh` as a global `UserPromptSubmit` hook in `~/.claude/settings.json`:
```json
{ "hooks": { "UserPromptSubmit": [
  { "hooks": [ { "type": "command", "command": "<repo>/working-agreement/inject-directives.sh" } ] }
] } }
```
Override the directives path with `CLAUDE_DIRECTIVES_PATH` if the repo isn't at the default location.

## 2. MCP entry — connect Claude to the deployed corpus

Add to `~/.claude.json` under `mcpServers` (user-global):
```json
"memory-knowledge": {
  "type": "stdio",
  "command": "<repo>/scripts/mcp-remote-wrapper.sh",
  "args": ["-y", "mcp-remote", "https://memory-knowledge.azurewebsites.net/mcp/"],
  "env": { "PATH": "<node-bin-dir>:/usr/local/bin:/usr/bin:/bin" }
}
```
`<node-bin-dir>` = the directory containing `npx` (e.g. `~/.nvm/versions/node/<ver>/bin`). The wrapper
(`scripts/mcp-remote-wrapper.sh`, vendored in this repo) handles clean shutdown. The endpoint is open
(no auth). Connect/approve the server via `/mcp` (or restart Claude); MCP servers load at session start.

## 3. Tier-2 — corpus hydration hook

Add `inject-corpus.sh` as a **second** `UserPromptSubmit` hook (append to the array from step 1):
```json
{ "hooks": [ { "type": "command", "command": "<repo>/working-agreement/inject-corpus.sh" } ] }
```
It runs `hydrate_corpus.py` via `.venv/bin/python`, queries the deployed `corpus_query`, and injects the
top hits (≥0.5 score, ≤3) labeled context-only. **Fail-open** with a 6s timeout — if the venv/MCP is
unavailable it injects nothing and never blocks the prompt. Overrides:
`CLAUDE_CORPUS_PYTHON`, `CLAUDE_CORPUS_HELPER`, `CLAUDE_CORPUS_MCP_URL`, `CLAUDE_CORPUS_TIMEOUT`,
`CLAUDE_CORPUS_MIN_SCORE`, `CLAUDE_CORPUS_LIMIT`.

Smoke-test the hook directly (no Claude restart needed):
```bash
echo '{"prompt":"why must I show concrete consequences before deciding"}' | ./working-agreement/inject-corpus.sh
# expect a JSON additionalContext payload containing G2
```

## 4. Seed the corpus (backfill the directives)

With the MCP reachable, ingest the directives as corpus entries:
```bash
.venv/bin/python scripts/backfill_corpus.py           # --dry-run to preview
```
Idempotent (deterministic `entry_key`); re-running updates in place.

## 4b. Auto-sync hook (keep the corpus mirrored to DIRECTIVES.md)

Step 4 is a one-shot seed. To keep Tier-2 mirrored automatically, install a git **post-commit**
hook so any commit that touches `DIRECTIVES.md` re-syncs the corpus — upserting current rules and
**deactivating orphans** (rules that were renamed or deleted):
```bash
ln -sf ../../working-agreement/sync-corpus.sh <repo>/.git/hooks/post-commit
```
`sync-corpus.sh` is **fail-open**: it does nothing unless the commit changed `DIRECTIVES.md`, and
never blocks the commit. It runs `sync_corpus.py`, which diffs the new commit against `HEAD~1`
(upsert current via `run_corpus_upsert_workflow`; deactivate orphans via `corpus_deactivate`).
Override the interpreter with `CLAUDE_CORPUS_PYTHON`. Preview without writing:
```bash
.venv/bin/python working-agreement/sync_corpus.py --dry-run
```
> **Deploy dependency:** orphan pruning calls the `corpus_deactivate` MCP tool, which must be live
> on the deployed service (see *Service deploy* below). Until the service is redeployed, upserts
> work but deactivation of orphans will error (logged, fail-open) — pruning activates post-deploy.

## 5. Canonical personal skills

Personal skills are versioned in this repository under `skills/` and declared by
`skills/managed-skills.txt`. Use the validator and transactional installer described below; do not
hand-copy installed client directories.

## 6. Verify end-to-end

1. New Claude session → confirm the `memory-knowledge` MCP server is connected (`/mcp`).
2. Ingest a throwaway entry via `run_corpus_upsert_workflow`, then `corpus_query` it back; delete after.
3. Start a fresh session and confirm a relevant prompt auto-injects a "Tier-2 corpus — retrieved for
   this prompt" block (the hydration hook firing).

## Codex managed skills and no-commit directive sync

Canonical Codex skills live under `skills/` and are declared in `skills/managed-skills.txt`:

```bash
working-agreement/validate-skills.sh
working-agreement/install-skills.sh
```

The installer defaults to Codex, uses a global lock and recovery journal, replaces only managed
directories, verifies tree hashes, and preserves unrelated skills. Claude installation requires
explicit reconciliation plus `--target both --accept-cross-client`.

When locked directive edits must reach Tier-2 before a commit, run:

```bash
working-agreement/sync-corpus.sh --force-current
```

Force mode compares committed `HEAD:working-agreement/DIRECTIVES.md` with the working-tree file,
upserts current identities, deactivates removed identities, and verifies both states through the
active-only `corpus_query` MCP read path before succeeding.

## Service deploy (separate concern)

The `memory-knowledge` service itself (the MCP backend) is deployed via `infra/azure-push.sh`
(ACR build → webapp container swap → restart → health check). The corpus DB table ships in migration
`027_corpus_schema`. See that script and `docs/TIER2_CORPUS_IMPLEMENTATION_PLAN.md`.
