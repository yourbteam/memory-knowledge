# Office Handoff — Research Findings

**Goal (verbatim intent):** a standalone handoff folder containing all needed files plus a
separate installation-instructions document, for installing and taking advantage of the
working-agreement / second-brain upgrades on the **office machine** for **Claude Code** and
**Codex** (separately), and for completing the wiring of **local Codex on this machine** — all
three wired and **in sync**.

Mode: Research (build-bound — feeds the Plan → Build → Review chain). Every runtime claim below is
grounded in a real file on this machine.

---

## 1. What "the upgrades" actually are (the payload)

All upgrade artifacts live under `~/memory-knowledge/working-agreement/` (verified `ls`,
2026-06-21) plus two repo-level CI workflows and one MCP wrapper. The functional set:

| Artifact | Path | Role |
| --- | --- | --- |
| `DIRECTIVES.md` | working-agreement/DIRECTIVES.md | **Single source of truth** (human-authored). Everything else projects from it. |
| `inject-directives.sh` | working-agreement/ | Claude `UserPromptSubmit` hook → injects DIRECTIVES.md each prompt. Uses **system `python3`** only. |
| `inject-corpus.sh` + `hydrate_corpus.py` | working-agreement/ | Claude `UserPromptSubmit` hook → injects Tier-2 corpus matches. Needs repo **`.venv`** (`mcp` client). |
| `inject-repo-memory.sh` + `hydrate_repo_memory.py` | working-agreement/ | Claude `UserPromptSubmit` hook (A3) → injects repo-scoped notes. Needs **`.venv`**; opt-in `MK_REPO_HYDRATE=1`. |
| `auto-capture-stop.sh` + `auto_capture.py` | working-agreement/ | Claude `Stop` hook (#2) → LLM-extracts session lessons → `unverified` notes. Needs **`.venv`**; opt-in `MK_AUTOCAPTURE=1`. |
| `auto-capture.skill.md` | working-agreement/ | Capture skill for **Codex** (no Stop hook there). Installed at `~/.codex/skills/auto-capture/SKILL.md`. |
| `generate_projections.py` | working-agreement/ | Projects DIRECTIVES.md → Codex `AGENTS.md` and → `CLAUDE.md` pointers. System `python3`. |
| `sync-corpus.sh` + `sync_corpus.py` | working-agreement/ | git post-commit hook → mirrors DIRECTIVES changes into corpus + refreshes trusted AGENTS.md. Needs `.venv`. |
| `weekly-review.sh` + `weekly_review.py` + `directive_spark.py` | working-agreement/ | Weekly cadence (#7). Needs `.venv`. |
| `com.kamen.memory-weekly-review.plist` | working-agreement/ | launchd schedule (macOS) for weekly-review. |
| `upkeep_heartbeat.py` | working-agreement/ | Dead-man's-switch (WS5). Needs `.venv` (`mcp` client). |
| `scripts/mcp-remote-wrapper.sh` | scripts/ | Codex MCP transport wrapper (node/`npx mcp-remote`). |
| `weekly-upkeep.yml`, `upkeep-heartbeat.yml` | .github/workflows/ | **Repo-level CI** (GitHub Actions). Run server-side, not per machine — informational for the handoff. |
| `SETUP-claude.md`, `SETUP-codex.md`, `SETUP-autocapture.md`, `SETUP-weekly-review.md` | working-agreement/ | Existing per-mechanism setup docs (granular; the handoff consolidates them). |

**Dependency tiers (decisive for the office install):**
- **Tier A — needs only `python3` + the files:** directives injection (Claude), AGENTS.md / CLAUDE.md
  projection (Codex), auto-capture skill. `inject-directives.sh:14` shells `python3 -c json...`; no venv.
- **Tier B — needs the cloned repo + a `.venv` with the package:** corpus injection, repo-memory
  hydration, auto Stop-capture, sync-corpus, weekly-review, heartbeat. Each is **fail-open**: a missing
  `.venv` makes the hook a silent no-op (`inject-corpus.sh:13` `[ -x "$VENV_PY" ] || exit 0`), so Tier B
  degrades cleanly to Tier A.
  - **Tier-B bootstrap (verified):** `pyproject.toml:9` `requires-python = ">=3.12"`; deps include
    `mcp>=1.26.0`, `asyncpg`, `qdrant-client`, `neo4j`, `openai` (`pyproject.toml:10-20`). Office
    venv = `python3.12 -m venv .venv && .venv/bin/pip install -e .` from the repo root (confirmed
    `.venv/bin/python -c "import memory_knowledge, mcp"` → OK on this machine). **Prereq: Python ≥ 3.12.**

---

## 2. How it is wired on THIS machine (the reference wiring)

### 2a. Claude Code — `~/.claude/settings.json` (verified)
- `hooks.UserPromptSubmit` = three hooks, absolute paths: `inject-directives.sh`, `inject-corpus.sh`,
  `inject-repo-memory.sh`.
- `hooks.Stop` = one hook: `auto-capture-stop.sh`.
- `env` = `{ "MK_AUTOCAPTURE": "1", "MK_REPO_HYDRATE": "1" }`.
- `mcpServers.memory-knowledge-local` = `{ "type": "url", "url": "https://memory-knowledge.azurewebsites.net/mcp/" }`
  — native URL transport, **no node needed**.

### 2b. Codex — `~/.codex/config.toml` (verified)
- `[mcp_servers.memory-knowledge]` = `scripts/mcp-remote-wrapper.sh -y mcp-remote https://memory-knowledge.azurewebsites.net/mcp/`
  with `PATH` env pointing at nvm node — **needs node/`npx`**.
- `[projects."<path>"] trust_level = "trusted"` for 8 repos:
  mcp-agents-workflow, FCSAPI, memory-knowledge, taggable-database, taggable-api,
  Downloads/claude-working-agreement-setup, united-partners, agentic-trading.
- Directives reach Codex only via generated `AGENTS.md` (no per-prompt hook exists in Codex —
  `SETUP-codex.md:6-10`).

### 2c. Codex directive-projection coverage on THIS machine (verified `grep -c` of the merge marker)
| Repo | `AGENTS.md`? | Directive block? |
| --- | --- | --- |
| FCSAPI | yes | **yes** (2 markers = BEGIN+END) |
| mcp-agents-workflow | yes | **yes** (2 markers) |
| memory-knowledge | yes | **no** (own AGENTS.md, 0 markers) |
| taggable-api | yes | **no** |
| taggable-server | yes | **no** |
| taggable-database | yes | **no** |
| united-partners | yes | **no** |
| agentic-trading | yes | **no** |

→ **Local-Codex gap:** 6 of 8 trusted repos have an `AGENTS.md` but **no directive projection**, so
Codex in those repos runs without the working agreement. Closing this is the local-machine work item.
Auto-capture skill (`~/.codex/skills/auto-capture/SKILL.md`) and MCP are already present (verified).

---

## 3. What "in sync" means (the synchronization model)

Three machines/clients stay in sync through **three shared anchors**, not by copying state around:

1. **One source of truth — git.** `DIRECTIVES.md` (and all scripts) live in the private repo
   `github.com/yourbteam/memory-knowledge` @ `main` (HEAD `4f0d3c4`, verified `git remote -v` +
   `git log`). Every machine clones/pulls the same repo; `git pull` is the sync channel for the
   directives + tooling.
2. **One brain — Azure.** Both clients on both machines point at the same MCP endpoint
   `https://memory-knowledge.azurewebsites.net/mcp/`. Memory (corpus, notes, learned records) is
   server-side, so it is **inherently shared** — nothing to sync per machine.
3. **One projection generator.** Codex `AGENTS.md` and `CLAUDE.md` pointers are regenerated from
   DIRECTIVES.md by `generate_projections.py`; the post-commit `sync-corpus.sh` refreshes the
   trusted projections on commit (`sync-corpus.sh:28` `--refresh-trusted`). So once a machine has
   the hooks wired, a `git pull` of a DIRECTIVES change + a regenerate keeps Codex current.

**Consequence:** "wired and in sync" = each target (a) reads DIRECTIVES.md from the same git repo,
(b) points MCP at the same Azure endpoint, (c) regenerates projections from that one file. No
machine holds authoritative state of its own.

**Private-repo access:** the repo is private (`yourbteam`). The office machine must authenticate to
GitHub to clone/pull (the user owns it). The standalone folder carries Tier-A copies so directives +
projections + skill work even **before** a clone; Tier B switches on after clone + `.venv`.

---

## 4. The deliverable (standalone handoff folder)

A self-contained, portable folder the user can move to the office by any channel (no git required to
read it), containing:

```
working-agreement-handoff/
  INSTALL.md                       # the single consolidated installation doc (3 targets)
  MANIFEST.md                      # snapshot provenance: source commit 4f0d3c4, date, file list
  configure.sh                     # one-shot, path-portable wiring helper (macOS)
  config-templates/
    claude-settings.hooks.json     # the ~/.claude/settings.json block to merge
    codex-config.snippet.toml      # the ~/.codex/config.toml block to merge
  payload/
    working-agreement/             # copies of every script + DIRECTIVES.md + SETUP docs + skill + plist
    scripts/mcp-remote-wrapper.sh  # Codex MCP transport wrapper
    .github/workflows/             # weekly-upkeep.yml, upkeep-heartbeat.yml (informational copy)
```

`INSTALL.md` covers, **separately**, three install flows that all converge on the same three shared
anchors (§3): **(1) Office Claude Code**, **(2) Office Codex**, **(3) Local Codex (this machine)**.

**Required INSTALL.md contents (per target):** (a) prerequisites; (b) ordered install/wiring steps;
(c) a short **"what each upgrade does / how to take advantage of it"** note so the user benefits, not
just installs (R7); (d) a **verification block** with concrete pass/fail checks (R12); (e) the
**sync** note (how `git pull` + regenerate keeps the target current). Plus a top-level "in sync"
section stating the three shared anchors and a rollback/uninstall note.

---

## 5. Locked decisions (sensible defaults; P2)

| # | Decision | Default locked | Rationale |
| --- | --- | --- | --- |
| D1 | OS assumption | Office machine is **macOS** (same as this machine). | Both `~/.claude` + `~/.codex` clients are macOS; launchd plist is macOS. INSTALL notes the Linux cron substitute for weekly-review (already in `SETUP-weekly-review.md:13`). |
| D2 | Path portability | INSTALL + `configure.sh` are **path-parametrized** via `$REPO_ROOT` and the scripts' env overrides (`CLAUDE_DIRECTIVES_PATH`, `CLAUDE_CORPUS_PYTHON`, `CLAUDE_CORPUS_HELPER`, `CLAUDE_REPO_HYDRATE_PYTHON/HELPER`). | Works whether the office username is `kamenkamenov` or not; no hardcoded `/Users/kamenkamenov` assumption required to function. |
| D3 | Standalone location | `~/Downloads/working-agreement-handoff/`. | Portable, outside git, copyable by USB/cloud/AirDrop. |
| D4 | Snapshot vs live | Handoff is a **bootstrap snapshot** pinned to commit `4f0d3c4` in MANIFEST; ongoing sync is `git pull`. | Avoids silent drift; the doc tells the user the copies are a snapshot and git is the live channel. |
| D5 | Repos governed by Codex projection | The canonical **8-repo set** (`MK_SPARK_REPOS`, `SETUP-weekly-review.md:24`); user edits the list per machine. | Matches the existing Spark/consolidation scope; office may have a different checkout set, so the list is editable. |
| D6 | Local-Codex work | Close the §2c gap by **merging** (`--append-to`) the directive block into the 6 repos that have their own `AGENTS.md` and lack it; never overwrite a hand-authored `AGENTS.md`. | `--append-to` is idempotent and preserves the repo's own content (`SETUP-codex.md:38-46`). |
| D7 | Secrets | No credentials, tokens, or PEMs in the handoff folder. MCP URL is public-by-design (open `/mcp`). | Guard rail; the brain endpoint needs no token (`/mcp` is open-auth). |
| D8 | Codex node path | `codex-config.snippet.toml` **parametrizes the node dir** (office runs `configure.sh`, which sets the MCP `env.PATH` to `$(dirname "$(command -v npx)")`); never ship this machine's hardcoded nvm path. **Prereq: node/`npx` on the office machine.** | This machine's `config.toml` hardcodes `/Users/kamenkamenov/.nvm/versions/node/v24.9.0/bin` (verified) — invalid elsewhere. |
| D9 | CLAUDE.md pointers | Pointer demotion (`generate_projections.py --kind claude-pointer`) is **optional/cosmetic** on the office machine — **skip by default**. | Claude Code receives directives via the `inject-directives.sh` hook regardless of CLAUDE.md content (§2a); demotion only prevents duplication, not required for function or sync. |
| D10 | Path stamping | `configure.sh` **rewrites the repo-root prefix** in the 5 path-bearing scripts (`inject-directives.sh`, `inject-corpus.sh`, `inject-repo-memory.sh`, `auto-capture-stop.sh`, `weekly-review.sh` — verified grep) to the actual office repo root, then writes `~/.claude/settings.json` hook paths + MCP block + env and the Codex MCP node PATH (D8) using that root. | Hooks/configs are absolute; an un-rewritten path silently no-ops (Tier-B fail-open) — install would "succeed" yet inject nothing. |
| D11 | Weekly-review owner | Weekly-review **launchd is single-owner**; the office machine does **not** enable it by default — CI `weekly-upkeep.yml` + the existing owner machine cover the cadence. Opt-in only, exactly one machine. | Two machines bumping the DIRECTIVES "Last reviewed" stamp + committing causes duplicate/racing scheduled commits, undermining sync. |

---

## 6. Open questions for the user — none blocking

All choices above are locked with defaults. The single environment fact not verifiable from this
machine — the office machine's username / repo path — is **neutralized by D2** (path-parametrized),
so the build proceeds without it. If the office machine is **not** macOS, only the weekly-review
scheduler changes (cron vs launchd), already documented.

---

## 7. Evidence index (files inspected on this machine, 2026-06-21)

- `~/.claude/settings.json` — hooks + env + mcpServers (§2a).
- `~/.codex/config.toml` — MCP server + trusted projects (§2b).
- `working-agreement/` `ls` — payload inventory (§1).
- `working-agreement/inject-directives.sh:7,14`; `inject-corpus.sh:10,13`; `inject-repo-memory.sh:4-8` — dependency tiers (§1).
- `working-agreement/generate_projections.py:147-178` — `--kind {agents,claude-pointer}`, `--write`, `--append-to`, `--refresh-trusted` (§3, §5).
- `working-agreement/SETUP-claude.md`, `SETUP-codex.md`, `SETUP-autocapture.md`, `SETUP-weekly-review.md` — wiring semantics (§2, §3, §5).
- `git remote -v` / `git log` — private repo + HEAD `4f0d3c4` (§3).
- `grep -c` merge-marker across 8 repos — projection coverage (§2c).
- `~/.codex/skills/auto-capture/SKILL.md`, `scripts/mcp-remote-wrapper.sh` — Codex capture + transport (§1, §2c).
