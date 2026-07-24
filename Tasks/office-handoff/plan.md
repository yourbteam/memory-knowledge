# Office Handoff — Implementation Plan

Builds on `research.md` (3 gates converged). Produces a standalone, portable handoff folder + a
consolidated installation document, and completes local-Codex wiring on this machine. Source of
truth = `working-agreement/DIRECTIVES.md` @ `yourbteam/memory-knowledge` HEAD `4f0d3c4`.

## Locked decisions (from research, carried)
D1 macOS · D2 path-parametrized · D3 dest `~/Downloads/working-agreement-handoff/` · D4 snapshot+git ·
D5 8-repo set (editable) · D6 `--append-to` merge for own-AGENTS.md repos · D7 no secrets ·
D8 node-path-portable Codex snippet · D9 pointer demotion optional/skip · D10 configure.sh stamps
repo root across 5 scripts + settings + codex node PATH · D11 single-owner weekly-review (office off).

## Deliverable 1 — standalone folder `~/Downloads/working-agreement-handoff/`

### 1.1 Exact tree
```
working-agreement-handoff/
  INSTALL.md
  MANIFEST.md
  configure.sh                       # chmod +x
  config-templates/
    claude-settings.hooks.json       # block to merge into ~/.claude/settings.json
    codex-config.snippet.toml        # block to merge into ~/.codex/config.toml
  payload/
    working-agreement/               # exact copies (see 1.2)
    scripts/mcp-remote-wrapper.sh
    .github/workflows/weekly-upkeep.yml
    .github/workflows/upkeep-heartbeat.yml
```

### 1.2 payload/working-agreement/ — exact file list (copied verbatim from the repo)
DIRECTIVES.md · inject-directives.sh · inject-corpus.sh · hydrate_corpus.py · inject-repo-memory.sh ·
hydrate_repo_memory.py · auto-capture-stop.sh · auto_capture.py · auto-capture.skill.md ·
generate_projections.py · sync-corpus.sh · sync_corpus.py · weekly-review.sh · weekly_review.py ·
directive_spark.py · upkeep_heartbeat.py · com.kamen.memory-weekly-review.plist ·
SETUP-claude.md · SETUP-codex.md · SETUP-autocapture.md · SETUP-weekly-review.md ·
INSTALL.md (repo's) · PLACEMENT.md · ROADMAP.md.
**Excluded:** `spark-candidates.md` (machine-local output, 39 KB, regenerated), `__pycache__/`.
**Build step:** `cp` each file; copy is a one-time snapshot (MANIFEST records the commit).

### 1.3 config-templates/claude-settings.hooks.json (exact content)
A JSON fragment showing the `hooks` (3 UserPromptSubmit + 1 Stop), `env`
(`MK_AUTOCAPTURE`,`MK_REPO_HYDRATE`), and `mcpServers.memory-knowledge-local` blocks, with the
repo-root path written as the literal token `__REPO_ROOT__` for configure.sh to substitute. Header
comment: "merge into ~/.claude/settings.json; do not replace the file."

### 1.4 config-templates/codex-config.snippet.toml (exact content)
`[mcp_servers.memory-knowledge]` + `[mcp_servers.memory-knowledge.env]` with `command` =
`__REPO_ROOT__/scripts/mcp-remote-wrapper.sh`, args `["-y","mcp-remote","https://memory-knowledge.azurewebsites.net/mcp/"]`,
and `PATH = "__NODE_DIR__:/usr/local/bin:/usr/bin:/bin"`. Plus a commented `[projects."<path>"]
trust_level="trusted"` example. Tokens substituted by configure.sh.

### 1.5 configure.sh — exact behavior (macOS bash; idempotent; D10)
Args: `--repo-root <path>` (default: parent of the handoff folder's detected repo, else prompt);
`--claude` / `--codex` select a single target (default: **both**) (CGAP-002); `--venv` (Tier-B).
**Fresh machine (CGAP-001):** if `~/.claude/settings.json` is absent, configure.sh creates it as `{}`
before the json merge; if `~/.codex/config.toml` is absent, it `touch`es it before appending.
Steps, each echoing what it does and skippable via flags:
1. **Resolve `REPO_ROOT`** — may be the **cloned repo** (Tier A+B) or the handoff **`payload/`** dir
   (Tier A only, no git) (SGAP-001). `NODE_DIR=$(dirname "$(command -v npx)")` (warn if npx absent → Codex MCP skipped).
2. **Stamp paths:** in `$REPO_ROOT/working-agreement/{inject-directives,inject-corpus,inject-repo-memory,auto-capture-stop,weekly-review}.sh`, replace any `/Users/kamenkamenov/memory-knowledge` with `$REPO_ROOT` (sed, with `.bak`). `chmod +x` the 6 shell scripts + configure.
3. **Claude wiring:** merge `claude-settings.hooks.json` (tokens substituted) into `~/.claude/settings.json` using **python3 json merge**. **Deep-merge the hook arrays** — append our hook entries to existing `UserPromptSubmit`/`Stop` lists only if the same `command` path is not already present (idempotent; never deletes a user's existing hooks); set our `mcpServers.memory-knowledge-local` key while preserving other servers; merge `env` keys (SGAP-002). Atomic write (temp+rename).
4. **Codex MCP:** append `codex-config.snippet.toml` (tokens substituted) to `~/.codex/config.toml` **only if** `[mcp_servers.memory-knowledge]` not already present (grep guard).
5. **Codex skill:** `mkdir -p ~/.codex/skills/auto-capture && cp working-agreement/auto-capture.skill.md ~/.codex/skills/auto-capture/SKILL.md`.
6. **Codex projections:** for each repo in `$MK_PROJECTION_REPOS` (default = D5 set, editable): if `AGENTS.md` exists **and its first line is the generated header** (`GENERATED from working-agreement`), it is a stale pure projection → `--write` (overwrite); elif it exists (hand-authored) → `--append-to` (merge into fenced block); else `--write`. **Pure-projection detection prevents duplicating directives** (SGAP-003, found in build). Skip missing repos with a warning.
7. **Tier-B venv (optional, `--venv`):** only if `$REPO_ROOT/pyproject.toml` exists (warn+skip if not — e.g. Tier-A payload root, SGAP-001): `python3.12 -m venv $REPO_ROOT/.venv && $REPO_ROOT/.venv/bin/pip install -e $REPO_ROOT` (prints the manual command if python3.12 absent).
8. **Print** a verification checklist + "restart Claude Code / Codex" reminder. Does **not** enable weekly-review launchd (D11).
Fail-soft: each step logs and continues; never leaves settings.json half-written (json merge is atomic write-to-temp+rename).

## Deliverable 2 — INSTALL.md (the consolidated install document)
Sections (research §4 required-contents):
- **0. In sync — the three shared anchors** (git repo, Azure brain, projection generator).
- **1. Prerequisites** (git access to the private repo; python3 ≥3.12 for Tier-B; node/npx for Codex MCP).
- **2. Quick path (recommended):** clone repo → run `configure.sh --repo-root <repo> --venv` → restart clients. One command set per the two office targets.
- **3. Target 1 — Office Claude Code:** manual steps (mirror configure.sh) + what each hook does + how to benefit + verification block.
- **4. Target 2 — Office Codex:** MCP block, trusted projects, AGENTS.md projection, capture skill + usage + verification.
- **5. Target 3 — Local Codex (this machine):** "already wired except projections" → run the projection step for the 6 repos lacking the directive block (§2c) + verification.
- **6. Verification (all targets):** concrete checks (ask "what does G1 say?"; check repo_scoped_memory after a session; `get_scheduler_heartbeat`; brain `/health`).
- **7. Staying in sync:** `git pull` + re-run projections; corpus auto-syncs on commit.
- **8. Rollback/uninstall:** remove the hook/env/mcp blocks; delete generated AGENTS.md blocks (fenced).
- **9. Tier-A vs Tier-B** table (what works without clone/venv).

## Deliverable 3 — MANIFEST.md
Snapshot provenance: source repo + commit `4f0d3c4`, build date `2026-06-21`, the exact file list,
and the note "snapshot bootstrap; ongoing sync via git pull (D4)."

## Deliverable 4 — Local Codex wiring (this machine, execute now)
Per §2c gap + D6: project directives into the 6 trusted repos lacking the block (memory-knowledge,
taggable-api, taggable-server, taggable-database, united-partners, agentic-trading). **Use the
pure-projection detection from step 6** — 4 of these (taggable-api, taggable-database, united-partners,
agentic-trading) turned out to be **stale pure projections** (their whole AGENTS.md was an old
`--write` projection), so they get `--write` (overwrite); memory-knowledge + taggable-server are
hand-authored → `--append-to`. FCSAPI + mcp-agents-workflow already correct — skip. Verify each repo
has `Prime directive` exactly once. (MCP + capture skill already present.)

## Verification (build acceptance)
- Folder tree matches 1.1; payload count matches 1.2; no `spark-candidates.md`/`__pycache__`; no secrets (`grep -rn` for key/token/PEM → none).
- `bash -n configure.sh` parses; dry-run on a temp REPO_ROOT substitutes tokens correctly.
- `python3 -c json.load` on a merged settings.json copy preserves existing keys.
- Local-Codex: 6 target repos show BEGIN/END markers post-run; FCSAPI/mcp-agents-workflow unchanged.
- INSTALL.md covers all 3 targets with prereqs + steps + usage + verification + sync (research §4).

## Out of scope
Office-machine execution (user runs it there); enabling office weekly-review launchd (D11);
ingesting yourbteam private repos; Tier-C harness isolation; CLAUDE.md pointer demotion on office (D9).
