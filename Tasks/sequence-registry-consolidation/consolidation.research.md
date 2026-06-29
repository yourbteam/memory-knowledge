# Research — consolidate the sequence registry into `memory-knowledge`, propagated to Claude + Codex on every machine

**Objective:** make `memory-knowledge` the single canonical home for the whole second-brain setup
(directives — already there — **plus skills and the operational-sequence registry**), and ensure a change
committed there is picked up by **both Claude and Codex on this machine and the home machine**, safely
(no secrets, no silent breakage).

## Current architecture (grounded)
Two distinct distribution patterns exist today:

1. **Directives — live-sourced (no copy):**
   - Claude: a global `UserPromptSubmit` hook runs `working-agreement/inject-directives.sh`, which reads
     `memory-knowledge/working-agreement/DIRECTIVES.md` **each prompt** (`SETUP-claude.md`). A `git pull`
     reflects immediately.
   - Codex: `generate_projections.py` projects `DIRECTIVES.md` → a per-repo `AGENTS.md`; re-run on change
     (`SETUP-codex.md`). Plus the `memory-knowledge` MCP.
2. **Skills — COPIED into each tool dir:** `~/.claude/skills/<name>/SKILL.md` (21) and
   `~/.codex/skills/<name>/SKILL.md` (28), populated by `cp` (the bundle's `INSTALL-OFFICE.md` step 1,
   and `auto-capture.skill.md` → `~/.codex/skills/auto-capture/`). **No symlinks.**
3. **Sequences — in `mcp-agents-workflow` only:** `operations/sequences/SEQUENCES.md` (catalog) →
   `<id>/sequence.md`; guard tooling `scripts/sequence_guard.py` + `sequence_discovery_log.py` run via
   `uv run python scripts/...` from the mcp-agents-workflow root (which owns the uv project). The
   `sequence-runner` skill **hardcodes** "locate the `mcp-agents-workflow` repo root."

**Evidence of the problem the copy model causes:** the `sequence-runner` `SKILL.md` is identical in
`~/.claude` and `~/.codex` (`cf5983…`) but **differs from the `mcp-agents-workflow` repo source**
(`af8ca6…`) — the installed copies have already **drifted** from the nominal source.

**Canonical-source statement (bundle):** `INSTALL-OFFICE.md` says source-of-truth is *both*
`memory-knowledge` and `mcp-agents-workflow`. Directives have already migrated into memory-knowledge;
**sequences are the lone outlier**, which is the split this work removes.

## Locked design decisions
- **D1 — `memory-knowledge` is the single source** for: directives (already), the playbook/sequence-runner
  **skills** (`memory-knowledge/skills/`), and the **sequence registry + guard tooling**
  (`memory-knowledge/operations/sequences/` + `scripts/sequence_guard.py`, `sequence_discovery_log.py`).
- **D2 — Distribution model = COPY via one idempotent installer, not symlinks.** Rejected symlinks because
  skill discovery through symlinks is **unverified across both Claude and Codex** and would fail silently if
  unsupported (now or after a tool update); the tool skill dirs are also OS-touched (`.DS_Store`). Copy is
  unambiguous and *fixes* drift (install is the only writer).
- **D3 — `install.sh` in `memory-knowledge`** (idempotent, prints a sync summary, no secrets) fans
  `skills/*` into **both** `~/.claude/skills/` and `~/.codex/skills/`, and regenerates the Codex `AGENTS.md`
  projection. It reuses the existing `SETUP-claude.md`/`SETUP-codex.md` mechanics rather than inventing new
  plumbing.
- **D4 — `post-merge` git hook** (installed by `install.sh`) auto-runs `install.sh` after `git pull`, giving
  "pull = reflected in both tools" **without** symlink risk. Precedent: `SETUP-codex.md` already suggests
  wiring regeneration "into the same post-commit path as `sync-corpus.sh`."
- **D5 — Cross-repo automation references.** The registry stays a single catalog in memory-knowledge, but a
  sequence's `automation` may live in another repo. The `SEQUENCES.md` automation column and the guard
  `--source script --source-ref` use an explicit **`<repo-key>:<path>`** form (e.g.
  `mcp-agents-workflow:scripts/local_workflow_orch_image_harness.py`,
  `taggable-api:tools/Taggable.MigrationRunner/scripts/reload-source.sh`). This lets the existing two
  mcp-agents-workflow sequences keep their automation in place while the catalog/skill/guard live in
  memory-knowledge — no script relocation required.
- **D6 — `sequence-runner` rewire:** change "locate the `mcp-agents-workflow` repo root" → resolve the
  catalog at `memory-knowledge/operations/sequences/SEQUENCES.md`, via an env override
  (`MK_SEQUENCES_ROOT`, defaulting to `$HOME/memory-knowledge`) mirroring `CLAUDE_DIRECTIVES_PATH`.
- **D7 — Propagation:** commit→push to memory-knowledge (safe over git, no secrets) → on each machine
  `git -C ~/memory-knowledge pull` triggers the `post-merge` hook → both tool skill dirs + Codex projection
  refresh. Home machine picks it up on its next pull. Claude directives are already live via the hook.
- **D8 — Migrate the two existing sequences + their guard tests** into memory-knowledge (catalog + sequence
  dirs) with automation referenced via D5; **deprecate** `mcp-agents-workflow/operations/sequences/` to a
  pointer that redirects to memory-knowledge (avoid a stale second catalog). Revert the misplaced taggable
  files I added to mcp-agents-workflow; the taggable sequence lands in memory-knowledge instead.

## Requirements (for coverage)
| req | requirement | type |
| --- | --- | --- |
| R1 | single canonical home for directives+skills+sequences = memory-knowledge | explicit |
| R2 | a committed change reaches **Claude** on this machine | explicit |
| R3 | …reaches **Codex** on this machine | explicit |
| R4 | …reaches **Claude** on the home machine | explicit |
| R5 | …reaches **Codex** on the home machine | explicit |
| R6 | safe (no secrets in the propagation channel) | explicit |
| R7 | no silent breakage if a tool doesn't support the mechanism | implied-essential |
| R8 | existing 2 sequences keep working (no orphaned automation) | implied-essential |
| R9 | guard tooling runs under memory-knowledge's environment | implied-essential |
| R10 | no two competing catalogs (no drift between repos) | implied-essential |
| R11 | idempotent, re-runnable install | non-functional |

## Gate 1 — doc-gap-closure (internal readiness)
- **GAP-1 (closed):** initial draft didn't say *how skills are discovered* by each tool — the installer is
  meaningless if a copied dir isn't auto-loaded. Resolution: D3 places skills exactly where the 21/28
  existing auto-discovered skills already live (`~/.claude/skills/<name>/`, `~/.codex/skills/<name>/`), i.e.
  presence-based discovery already in force. **Required pre-impl verification:** confirm a freshly-copied
  skill dir is discovered by each tool (it is, empirically — that's how today's skills load).
- **GAP-2 (closed):** guard scripts run via `uv` from mcp-agents-workflow; moving them needs them runnable
  under memory-knowledge's uv project. Resolution (D1/D9): **required verification** = the guard scripts'
  imports are stdlib-only or satisfied by memory-knowledge's `pyproject.toml`; if not, add the dep. Recorded
  as a plan step, not assumed.
- **GAP-3 (closed):** cross-repo automation (existing sequences' scripts live in mcp-agents-workflow) —
  resolved by D5 (`<repo-key>:<path>`), so the registry can reference automation in any repo.
- No internal contradiction remains; D1–D8 are consistent; every claim cites a real file/behavior. **Converged.**

## Gate 2 — requirements-coverage (breadth)
| req | covered? | where |
| --- | --- | --- |
| R1 | yes | D1 |
| R2 | yes | D3/D4 (copy to `~/.claude/skills` + Claude directives already live) |
| R3 | yes | D3/D4 (copy to `~/.codex/skills` + AGENTS.md regen) |
| R4 / R5 | yes | D7 (home machine: `git pull` → post-merge hook runs install) |
| R6 | yes | D7 (git, no secrets — matches bundle's "no tokens/JWTs/secrets") |
| R7 | yes | D2 (copy avoids symlink-discovery dependency) |
| R8 | yes | D5 + D8 (automation referenced cross-repo; existing sequences migrated, not orphaned) |
| R9 | yes (verify) | GAP-2 verification step |
| R10 | yes | D8 (deprecate mcp-agents-workflow catalog to a pointer) |
| R11 | yes | D3 (idempotent installer) |
- **CGAP-1 (closed):** first pass omitted the home-machine Codex `AGENTS.md` regen (R5) — the post-merge hook
  (D4) must also run `generate_projections.py`, not only copy skills. Folded into D3/D4.
- No requirement unaddressed. **Converged.**

## Gate 3 — requirements-satisfaction (depth, traced)
- **R2/R3 (this machine):** `install.sh` `cp`s `skills/*` over the existing `~/.claude/skills` + `~/.codex/skills`
  (same dirs today's skills load from) → both tools see the new version next session. Holds. *Claude directives
  already live via the hook (no action).* 
- **R4/R5 (home machine):** depends on the home machine running `git pull` (triggers hook). **Honest limit:**
  propagation is **pull-triggered, not push-automatic** — "eventually reflected" = on next pull there. This is
  inherent to git-based distribution and is acceptable per the objective ("will *eventually* be reflected").
- **SGAP-1 (closed):** the `post-merge` hook only fires on `pull`/`merge`, not on a fresh `clone`. Resolution:
  `INSTALL-OFFICE.md`/`SETUP-*` already cover first-time install (run `install.sh` once after clone); the hook
  covers ongoing updates. Documented.
- **SGAP-2 (closed):** drift — after migration, if anyone still `cp`s from the old mcp-agents-workflow source,
  drift returns. D8's deprecation-pointer + D1 single-source close this; the installer copies only from
  memory-knowledge.
- **SGAP-3 (verify, not blocker):** does Codex actually auto-load `~/.codex/skills/<name>/SKILL.md` by presence?
  Empirically yes (28 live there now); recorded as a confirm-on-impl, with a non-silent failure mode (the skill
  simply wouldn't appear, caught by the install verify step).
- Producer/consumer symmetry: the single writer is `install.sh`; both consumers (Claude, Codex) read their own
  dir; no asymmetric path. **Converged.**

## Open verification items (carried into the plan, not blockers)
1. Confirm each tool auto-discovers a copied skill dir (empirically true today).
2. Confirm the guard scripts run under memory-knowledge's uv env (deps).
3. Decide the deprecation shape for the old mcp-agents-workflow catalog (pointer file vs delete).

## Out of scope
- Live push-propagation to the home machine (no daemon); git-pull-triggered is the accepted model.
- Symlink distribution (rejected, D2).
- Rewriting the directives distribution (already live and working).
