# Plan — consolidate the sequence registry into `memory-knowledge` + distribute to Claude & Codex on every machine

Grounded in [consolidation.research.md](consolidation.research.md) (3 gates converged). Goal: `memory-knowledge`
becomes the single source for the sequence registry + `sequence-runner` skill + guard tooling, distributed to
both `~/.claude/skills` and `~/.codex/skills` by an idempotent installer auto-run on `git pull`. **Copy model,
no symlinks.** Existing two sequences keep their automation in `mcp-agents-workflow` via cross-repo references.

## Acceptance
- A change committed+pushed to `memory-knowledge` reaches Claude **and** Codex on this machine (after the
  hook runs) and on the home machine (on its next `git pull`).
- `sequence-runner` resolves the catalog from `memory-knowledge`, not `mcp-agents-workflow`.
- The two existing sequences still pass their guard/tests; their automation scripts are untouched.
- No second/stale catalog; no symlinks; no secrets in the channel; installer is idempotent and non-deleting.

## Change-by-change

### Change 1 — `memory-knowledge/operations/sequences/` (new registry)
- Create `SEQUENCES.md` (the canonical catalog) by **moving** the rows from
  `mcp-agents-workflow/operations/sequences/SEQUENCES.md`, rewriting each `automation` cell to the
  **`<repo-key>:<path>`** form (D5): `local-workflow-orch-image` →
  `mcp-agents-workflow:scripts/local_workflow_orch_image_harness.py`; `remote-mcp-user-onboarding` →
  `mcp-agents-workflow:dist/remote-mcp-user-admin/...`.
- Move the two sequence folders (`local-workflow-orch-image/`, `remote-mcp-user-onboarding/`) and `discovery/`
  here verbatim (their `sequence.md` step bodies are unchanged; only the catalog's automation column gains the
  repo-key prefix). Update each `sequence.md`'s `sequence_guard.py activate --sequence-doc` path to the
  memory-knowledge location.
- Add the **`taggable-source-reload/sequence.md`** here (the content I drafted), automation
  `taggable-api:tools/Taggable.MigrationRunner/scripts/reload-source.sh`; add its `SEQUENCES.md` row.
*Why:* single catalog in the canonical repo (research D1/D8); cross-repo automation keeps scripts in place (D5).

### Change 2 — `memory-knowledge/scripts/sequence_guard.py` + `sequence_discovery_log.py` (+ tests)
- Copy both from `mcp-agents-workflow/scripts/` (verified **stdlib-only, path-agnostic** — paths come from
  args), plus `tests/test_sequence_guard.py`, `test_sequence_discovery_log.py`.
- **Verify** they run under memory-knowledge's uv: `uv run python scripts/sequence_guard.py --help` and
  `uv run pytest tests/test_sequence_guard.py tests/test_sequence_discovery_log.py` → pass.
*Why:* guard tooling co-located with the catalog so `sequence-runner` runs it from memory-knowledge (research
D1, GAP-2 verified).

### Change 3 — `memory-knowledge/skills/sequence-runner/SKILL.md` (canonical, rewired)
- Seed from the **in-use** copy (`~/.claude/skills/sequence-runner/SKILL.md`, md5 `cf5983…` — the live one),
  NOT the stale `mcp-agents-workflow` copy (`af8ca6…`).
- Rewire step 1: "Locate the `mcp-agents-workflow` repo root" → resolve the catalog at
  `${MK_SEQUENCES_ROOT:-$HOME/memory-knowledge}/operations/sequences/SEQUENCES.md` (mirrors
  `CLAUDE_DIRECTIVES_PATH`). Update the guard invocation paths to memory-knowledge.
*Why:* one authoritative skill source; fixes the existing drift (research evidence); D6.

### Change 4 — `memory-knowledge/working-agreement/install-skills.sh` (new, idempotent installer)
- For each `memory-knowledge/skills/<name>/`: `cp -R` into **both** `~/.claude/skills/<name>/` and
  `~/.codex/skills/<name>/` (overwrite-in-place; **never** `rsync --delete` — must not remove the other
  ~20/27 skills not yet migrated).
- Print a one-line-per-skill sync summary; resolve `$HOME` (honor an office login differing from
  `/Users/kamenkamenov`, per INSTALL-OFFICE.md's #1-breakage note); **no secrets printed**.
- Final verification: re-read one synced `SKILL.md` and assert md5 matches the source.
*Why:* the single writer to the tool dirs → kills drift (research D2/D3/R10/R11). Scoped to `skills/` so it
generalizes to future skill migrations without change.

### Change 5 — `post-merge` hook via tracked `memory-knowledge/.githooks/`
- Add tracked `.githooks/post-merge` that runs `working-agreement/install-skills.sh`.
- `install-skills.sh` (run once per machine, also from SETUP) sets `git -C ~/memory-knowledge config
  core.hooksPath .githooks` so the tracked hook is active (since `.git/hooks` isn't tracked).
*Why:* `git pull` then auto-syncs both tools — symlink convenience without symlink risk (D4). One-time hooks
path config per machine.

### Change 6 — `mcp-agents-workflow` cleanup
- **Revert** the taggable files I added earlier (the `taggable-source-reload` dir + the `SEQUENCES.md` row) —
  they move to memory-knowledge (Change 1).
- Replace `mcp-agents-workflow/operations/sequences/SEQUENCES.md` body with a **deprecation pointer**:
  "Catalog moved to `memory-knowledge/operations/sequences/SEQUENCES.md`; use `sequence-runner`." Keep the two
  automation scripts (`scripts/...`, `dist/...`) in place (referenced cross-repo). Leave the moved sequence
  folders as pointers or remove (operator choice — default: leave a one-line pointer to avoid broken links).
- Update `mcp-agents-workflow/skills/sequence-runner/SKILL.md` to the rewired version (or replace with a
  pointer to the memory-knowledge canonical skill).
*Why:* no competing catalog (R10); scripts stay where they run.

### Change 7 — docs
- Update `memory-knowledge/working-agreement/SETUP-claude.md` + `SETUP-codex.md` (and the
  `office-computer-second-brain-setup` `INSTALL-OFFICE.md`/`README.md`/`MANIFEST.md`) to: install skills via
  `install-skills.sh`, set `core.hooksPath`, and note sequences are now canonical in memory-knowledge.
- Update directive **G18** text reference from `operations/sequences/SEQUENCES.md` (implicitly
  mcp-agents-workflow) to the memory-knowledge path.
*Why:* the install/discipline docs must match the new home (R1).

## Validation
1. `uv run pytest` for the two guard tests in memory-knowledge → pass (Change 2).
2. `install-skills.sh` run locally → both `~/.claude/skills/sequence-runner` and
   `~/.codex/skills/sequence-runner` updated to the memory-knowledge source (md5 match); other skills untouched
   (count unchanged).
3. `sequence-runner` dry read resolves the memory-knowledge catalog; `sequence_guard.py activate` +
   `guard --source sequence_doc` succeeds against a memory-knowledge `sequence.md`.
4. Simulate propagation: a no-op commit + `git pull` fires the `post-merge` hook → install runs (observe the
   summary).
5. Existing two sequences: `sequence_guard.py` accepts their `sequence.md` source refs at the new paths.

## verify-plan / coverage / satisfaction (folded, converged)
- **verify-plan:** every referenced file/behavior exists and was checked — guard scripts stdlib/path-agnostic
  (verified); skills are presence-discovered in `~/.claude/skills` + `~/.codex/skills` (21/28 live today);
  `CLAUDE_DIRECTIVES_PATH` env-override precedent exists; `core.hooksPath` is the standard way to ship a hook.
  No invented paths/flags.
- **coverage:** R1–R11 from research each map to a change — R1→C1/C3/C7, R2/R3→C4, R4/R5→C5, R6→C5 (git),
  R7→C4 (copy), R8→C1/C6 (cross-repo refs, scripts untouched), R9→C2 (verified), R10→C6 (deprecation pointer),
  R11→C4 (idempotent, non-deleting). **CGAP closed:** C4 must be **non-deleting** (cp, not rsync --delete) or
  it would wipe unmigrated skills — locked in C4.
- **satisfaction:** traced — install writes both tool dirs from one source (no asymmetry); hook covers updates,
  SETUP covers fresh clone (SGAP-1); deprecation pointer + single writer prevent drift recurrence (SGAP-2);
  home machine reflects on next pull (accepted limitation, not a blocker). **SGAP closed:** the hook needs
  `core.hooksPath` set first — made an explicit one-time install step (C5), else the tracked hook never fires.
- **No blocker gaps.** One-shot executable.

## Out of scope (named, not built)
- Migrating the other ~20/27 skills into `memory-knowledge/skills/` — the installer (C4) already handles them
  when they move; do as a follow-on.
- Live push-propagation to the home machine (git-pull-triggered is the model).
- The deferred natural-key/RowId business-key loader fix (separate track).
