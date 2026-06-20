# Research: Remaining tails after the 8-gap closure

**Mode:** Research (findings only — no code shipped). Created 2026-06-20. Owner: memory-knowledge.
**Question:** Of the work that remains after all 8 gaps shipped, what is the *real* current state of
each tail, what does closing it actually require, and what blocks/risks it? Every row is grounded in
a file or live-system probe; inferences are marked **[inf]**.

> **R1/cite:** evidence is `path:line`, a shell probe, or a live MCP call captured this session.
> **Scope:** the tails listed in `README.md:34-39`. This does **not** re-open the 8 gaps (all shipped).

---

## Evidence snapshot (this session)

| Probe | Result |
| --- | --- |
| `launchctl list \| grep weekly` | only Apple's `LWWeeklyMessageTracer` — **#7 plist NOT loaded** |
| `~/Library/LaunchAgents/` | **no** `com.kamen.memory-weekly-review.plist` — not installed |
| `~/.claude/skills/` | **no** `auto-capture` — #2 skill not installed |
| `~/.claude/settings.json` hooks | `Stop` hook **not** wired to `auto-capture-stop.sh` (only existing hooks present) |
| `MK_AUTOCAPTURE` (env + shell rc) | **UNSET** everywhere — #2 auto-capture inert |
| `git log 7fff0ad..HEAD` | `7fff0ad` (cosmetic #2) is an **ancestor** of HEAD; deployed `sha-232d57f` predates it → **not deployed** |
| `curl …/health` | `{"status":"ok"}` (live); `/version` → `Unauthorized` (can't read deployed sha remotely) |
| `list_repositories` (live MCP) | returns **9** active repos; the 3 blocked-note targets are **absent** |
| local clones of 3 targets | `~/mcp-agents-workflow` ✅ · `~/memory-knowledge` ✅ (this repo) · `taggable-backoffice` ❌ not on disk |

Live active repos (9): css-scheduler, css-fe, fcs-admin, fcsapi, millennium-wp,
neocurrency-dashboard *(ingestion `running`)*, taggable-api, taggable-server,
tpp-petkey *(`last_ingestion_status: null` despite non-zero counts — **anomaly, see T6**)*.

---

## Tail-by-tail findings

### T1 · Enable automation: #7 weekly review (launchd)
- **State:** built + committed (`weekly_review.py`, `weekly-review.sh`, plist); **not installed/loaded**.
- **Requires:** `cp` plist → `~/Library/LaunchAgents/`, `launchctl load` (`SETUP-weekly-review.md:8-11`).
  Runs Mondays 09:00, logs `/tmp/mk-weekly-review.log`.
- **Dependency:** the wrapper bumps `DIRECTIVES.md` "Last reviewed" and **commits** it — so the
  account running launchd needs git push rights for the corpus sync to mirror the stamp. **[inf]** the
  wrapper assumes a clean working tree; an uncommitted `DIRECTIVES.md` could collide. *Verify wrapper
  behavior before enabling.*
- **Risk:** low. Fail-soft per step (`weekly_review.py:67-78`). Worst case: a noisy log file.
- **Cost:** ~2 min setup; weekly background run hits the live MCP for integrity/compaction on 3 repos.

### T2 · Enable automation: #2 auto-capture (Stop hook + skill)
- **State:** built (`auto_capture.py`, `auto-capture-stop.sh`, `auto-capture.skill.md`); **fully inert** —
  env unset, hook unwired, skill not installed.
- **Requires (Option 1, Claude only):** `export MK_AUTOCAPTURE=1` + merge the `Stop` hook into
  `~/.claude/settings.json` (`SETUP-autocapture.md:14-24`) + restart. **(Option 2, Claude+Codex):**
  install the skill into the client's skills dir.
- **Dependency:** writes only to **already-ingested** repos (`repo_note.py:64-67` raises on no revision);
  needs a chat model the codex token can call (`auto_capture.py:26`, `SETUP-autocapture.md:30-32`).
- **Risk:** low — fail-open (captures nothing on any error, never blocks session end,
  `auto_capture.py:127-128`). Real cost: a per-session LLM call when enabled.
- **Verification step (from setup):** end one session, then check the repo's `repo_scoped_memory`
  for an `unverified` note.

### T3 · Deploy the #2 cosmetic fix (`7fff0ad`)
- **State:** committed; **not deployed** (deployed `sha-232d57f` is older — git range confirms).
- **Scope check:** the *only* server-side change since deploy is `7fff0ad` (return line echoes the
  passed `verification_status`). #3/#7 are **local scripts**, not server code → no deploy needed for them.
- **Impact:** purely cosmetic — stored value was already correct (summary + `repo_note.py:222`); the
  live tool just echoes the constant in its response. **No functional gap.**
- **Requires:** one `infra/azure-push.sh` run (`az acr build` → entrypoint `alembic upgrade head`).
  No new migration since 028 → upgrade is a no-op. **Fold into the next real deploy; not worth a deploy alone.**

### T4 · #4 per-project `AGENTS.md` generation
- **State:** mechanism exists (`generate_projections.py` projects DIRECTIVES.md → AGENTS.md / thin
  CLAUDE.md). Home-level projection done; **per-repo `AGENTS.md` not generated** in the 9 active repos.
- **Requires:** run the generator into each target repo checkout. **Cross-repo** — touches other working
  trees, so per CLAUDE.md worktree rules each needs its own branch/commit.
- **Open question (needs Kamen):** *which* repos get an `AGENTS.md`, and do they get the full directive
  projection or a thin pointer to the brain? Not derivable from this repo. **[inf]** likely the active
  repos Codex actually runs in (taggable-*, fcsapi) — confirm before generating.
- **Risk:** medium — writes into N external repos; reversible (generated files), but noisy across PRs.

### T5 · 36 blocked Bucket-B notes (ingest the 3 target repos)
- **State:** 9 file-memory notes migrated (taggable-api 4, taggable-server 5); **36 blocked** because
  their target repos aren't ingested. Live probe shows those 3 repos aren't even **registered**.
- **Per-target requirement:**
  - `mcp-agents-workflow` — local clone at `~/mcp-agents-workflow` → `register_repository` +
    `run_repo_ingestion_workflow`, then migrate its notes. Feasible.
  - `memory-knowledge` — **this very repo** (`~/memory-knowledge`) → self-ingest, then migrate. Feasible
    but **[inf]** large/self-referential; confirm desired.
  - `taggable-backoffice` — **no local clone found** → must clone first (needs origin URL + access)
    before any ingestion. **Hard blocker until the repo is available locally.**
- **Dependency chain per repo:** register → ingest (heavy: full repo embed) → `ensure_repo_root_entity`
  succeeds → `author_repo_note` per blocked note. The migration itself is cheap; **ingestion is the cost**.
- **Risk:** medium — ingestion is the heaviest live operation here (embeds, Qdrant upserts) and bulk
  writes to shared infra; each repo is a separate authorized action.

### T6 · Cleanups
- **a. test-marker notes (2)** in taggable-server brain (S5/#2 verification artifacts) — should be
  deactivated. **[inf]** locate via `repo_scoped_memory` / `corpus_query` then `corpus_deactivate`.
- **b. 3 redundant taggable-server file-memory files** — superseded by the migrated notes; delete in the
  taggable-server checkout (cross-repo). *Paths not yet confirmed — needs that checkout.*
- **c. `test_guards.py` env-leak** — 4 pre-existing failures (diagnosed: `.env` `ALLOW_REMOTE_WRITES=true`
  leaks into the test; not my code). Fix = isolate the env in the test. Independent of the 8 gaps.
- **d. [new finding] deployed `list_repositories` lacks `include_inactive`** — the live tool schema
  exposes only `correlation_id`; it filters inactive by default (returns 9) but the param added in #6 to
  *see* inactive repos isn't in the deployed build. So there's currently **no MCP way to list the 46
  deactivated repos**. Resolves itself on the next deploy (T3's deploy carries it). **[inf]** confirm the
  param is in HEAD's `server.py` before relying on it.
- **e. [new finding] `tpp-petkey` ingestion anomaly** — non-zero file/symbol/chunk counts but
  `last_ingestion_status: null`. Either a legacy/partial ingest. Worth a `check_job_status` /
  re-ingest decision; not blocking anything above.

---

## Dependency / sequencing summary

- **No-cost, high-leverage, do-first:** T1 + T2 (turn on what's already built). Pure operator setup.
- **Cheap tidy, defer:** T3 — fold the cosmetic deploy into the next real deploy (also clears T6d).
- **Needs a Kamen decision before acting:** T4 (which repos / full-vs-thin), T5-memory-knowledge (self-ingest?).
- **Hard-blocked:** T5-taggable-backoffice (no local clone — needs the repo first).
- **Independent maintenance:** T6c (test env-leak), T6e (tpp-petkey anomaly).

## Open questions for Kamen (P2 — not buried)
1. T4: which repos get `AGENTS.md`, and full projection or thin pointer?
2. T5: self-ingest `memory-knowledge`? And do you have a clone/URL for `taggable-backoffice`?
3. T6e: investigate the `tpp-petkey` null-status ingestion, or leave it?

## Unverified / inference ledger
- Wrapper git-push assumptions (T1), Codex-runnable chat model (T2), per-repo AGENTS.md target set (T4),
  memory-knowledge self-ingest size (T5), exact paths for T6a/T6b, and whether HEAD `server.py` carries
  `include_inactive` (T6d) — all marked **[inf]** above and require a direct check before building.
