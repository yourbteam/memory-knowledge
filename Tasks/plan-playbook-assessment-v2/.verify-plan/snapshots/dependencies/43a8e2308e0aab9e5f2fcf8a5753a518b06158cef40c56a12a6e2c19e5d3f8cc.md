# Implementation Plan — Close the 8 Memory/Directives Gaps

**Mode:** Plan (per `plan-playbook`). **Source of gaps:** `our-approach-vs-open-brain-gaps.md` (3-gate hardened; §1 reframed per Kamen 2026-06-20). **System under change:** `/Users/kamenkamenov/memory-knowledge` (git repo, branch `main`) + the deployed `memory-knowledge` MCP. **Grounding:** every step cites a real script/tool; no invented names.

> **One explicit open decision (P2)** — surfaced, not buried — is in **§0**. Everything else is locked.

---

## 0. Foundation decisions (do first — unblocks §1, §4, §5, §8)

### 0.1 Canonical brain endpoint — **DECIDED: Azure (Kamen, 2026-06-20)**
**Practical problem (resolved).** Three consumers read the brain through **two** different endpoints, so they can return different results for the same query:
- Claude Code MCP tools → `http://localhost:8000/mcp/` (`~/.claude/settings.json` → `memory-knowledge-local`).
- Claude Code corpus hook → Azure (`hydrate_corpus.py` default `CLAUDE_CORPUS_MCP_URL`).
- Codex MCP → Azure (`~/.codex/config.toml` → `mcp_servers.memory-knowledge`).

**Decision:** **Azure (`https://memory-knowledge.azurewebsites.net/mcp/`) is canonical** for all three consumers, set via a single env var with one default; **localhost `:8000` is an opt-in dev override** (set the env var locally when doing server dev). Rationale: matches the cross-tool/cross-machine portability thesis and is already the default for 2 of 3 consumers; offline degradation is already fail-open. **Implication for §5 (X-DEPLOY):** the `corpus_query` recency change must be deployed to the Azure server to take effect for all consumers.

### 0.2 Knowledge-grade taxonomy (locked)
When distilling the legacy files (§1), classify each item once:
- **Directive-grade** (a behavioral rule) → a new `G`-rule in `DIRECTIVES.md`, promoted via the existing "lock it" flow.
- **Reference-grade** (lookups, mappings) → a corpus entry of `kind: "reference"` via `run_corpus_upsert_workflow`. **Note (depth-verified):** `kind` is **not** free-form — `memory.corpus_entries` has a CHECK constraint limiting it to `{directive_rationale, playbook_detail, example, reference}` (`migrations/versions/027_corpus_schema.py`). "reference" is the valid choice here; any new kind requires a migration to extend the CHECK.

### 0.3 Cross-cutting requirements (apply to every gap below)
- **Deployment (X-DEPLOY).** Any change to server-side code (`src/`, e.g. `corpus_query` in §5) only takes effect once the `memory-knowledge` MCP server is **redeployed to the canonical endpoint** (and to local dev if used). Server-side gaps are not "done" until the deployed endpoint serves the new behavior. Hook/script/generator changes (`working-agreement/*`, §1/§2/§8) are local and need no deploy.
- **Testing (X-TEST).** Every code change ships with a test in `tests/` (the repo uses pytest; see existing `tests/test_codex_*.py`): the recency/threshold ranking (§5), `generate_projections.py` (§1.2), the capture hook (§2), `directive_spark.py` (§3), and the citation injection (§8). Each gap's acceptance is met only with its test green.
- **Rollback.** Generated files (§1.2/§1.3) and hook edits are revertible via git; the §5 server change ships behind the new threshold/recency params with the existing hook default unchanged until validated.
- **Non-breaking (X-COMPAT) — Kamen, 2026-06-20.** Every change must be backward-compatible: new params are optional with safe defaults; existing tool signatures, MCP contracts, DB columns, and call sites keep working; schema changes are additive (no drop/rename of live columns); any change that alters a *default* behavior (e.g. §6 hiding inactive repos) must be explicitly flagged, recoverable via a param/flag, and reversible. Prefer additive over destructive everywhere.

---

## 1. Gap #1 — `DIRECTIVES.md` as the one authoritative source; all tools become projections

**Objective.** `DIRECTIVES.md` stays the single human-authored truth; the corpus mirrors it (already true via `sync_corpus.py`); Claude Code, Codex, `CLAUDE.md`, `AGENTS.md`, and file-memory all become **generated projections or thin pointers**, never independent sources.

**In-scope file instances (locked).** The projection/demotion applies to **Kamen-owned** instruction files only: global `~/.claude/CLAUDE.md`, `~/CLAUDE.md`, `~/AGENTS.md`, **and** per-project `CLAUDE.md`/`AGENTS.md` in Kamen's active repos (enumerate from the `trusted` projects in `~/.codex/config.toml` — e.g. `FCSAPI`, `taggable-api`, `memory-knowledge`, `united-partners`, `agentic-trading`). **Explicitly out of scope:** third-party/cloned repos that ship their own `CLAUDE.md`/`AGENTS.md` (e.g. `Downloads/OB1-main`) — never rewrite those. The generator writes a pointer to each in-scope instance; it must never touch an out-of-scope file.

**Step 1.1 — Distill legacy files into the authoritative source (migration, one-time).**
Move durable content out of the soon-to-be-demoted files:
- Global `~/.claude/CLAUDE.md` → two directive-grade rules: "never invent API/DB schema/column/attribute names" and "make code changes via a granular, change-by-change plan and wait for approval." Add as new `G`-rules in `DIRECTIVES.md` (heading format `## G<N> · Title` so `parse_directives` picks them up).
- `~/CLAUDE.md` → directive-grade: "never add `Co-Authored-By: Claude`/AI attribution to commits" (new `G`-rule); reference-grade: the repo mappings (FCS backend→FCSAPI, Taggable→taggable-server, Taggable uploader→taggable-dropbox-manager) → one `reference` corpus entry.
- `~/AGENTS.md` → repo index duplicates the mappings above → no new content; it will become a generated pointer.
- **Acceptance:** `python scripts/backfill_corpus.py --dry-run` lists the new `G`-rules; nothing durable remains only in the legacy files.

**Step 1.2 — Add the Codex directive projection (the real new plumbing).**
Codex gets no directives today and has no per-prompt hook. Make `DIRECTIVES.md` reach Codex by **generating Codex's `AGENTS.md` from `DIRECTIVES.md`**:
- New generator `working-agreement/generate_projections.py`: reads `DIRECTIVES.md`, writes (a) a **per-project `AGENTS.md`** in each in-scope repo (the reliable Codex load path — Codex loads `AGENTS.md` from the repo tree) carrying the directives + "authored in `DIRECTIVES.md`; do not edit here", and (b) thin-pointer `CLAUDE.md` files. **Depth note:** do **not** rely on a global `~/.codex/AGENTS.md` (it doesn't exist today and global-load is unverified); per-project files are the load-guaranteed path. Add `~/.codex/AGENTS.md` only after confirming Codex loads it.
- Wire generation into the existing post-commit path (alongside `sync-corpus.sh`) so every `DIRECTIVES.md` edit regenerates projections.
- **Acceptance:** after editing `DIRECTIVES.md` and committing, Codex's `AGENTS.md` reflects the change; a fresh Codex session answers "what does G1 say?" correctly.

**Step 1.3 — Demote `CLAUDE.md`/`AGENTS.md` to generated pointers.**
Replace their bodies with a generated stub: "Directives live in `working-agreement/DIRECTIVES.md` (authored there) and the memory-knowledge brain. Do not author rules here." Mark generated (header comment + add to `.gitignore`-style "generated" note). The Claude Code hook (`inject-directives.sh`) continues to inject the real `DIRECTIVES.md`, so demoting `CLAUDE.md` loses nothing.
- **Acceptance:** the legacy files contain only the generated pointer; behavior is unchanged because the hook + generated `AGENTS.md` carry the rules.

**Step 1.4 — Fold in file-memory.**
`~/.claude/.../memory/` (types user/feedback/project/reference) becomes a projection: migrate its durable entries into the corpus. **Depth note (kind constraint):** the corpus `kind` enum is `{directive_rationale, playbook_detail, example, reference}` — file-memory's `user`/`feedback`/`project` types do **not** map 1:1. Map each: behavioral `feedback` → a directive (via `DIRECTIVES.md` "lock it"), durable `user`/`project`/`reference` facts → `kind: "reference"`. If a distinct kind is genuinely needed, ship a migration extending the CHECK first. Keep `MEMORY.md` as a generated index or retire it. **Acceptance:** no durable fact lives only in file-memory; every migrated entry uses a CHECK-valid kind.

**Step 1.5 — Endpoint unification** (from §0.1 decision): point `inject-corpus.sh`/`hydrate_corpus.py`, the Claude MCP config, and Codex MCP at the canonical endpoint via the single env var.
- **Acceptance:** all three consumers resolve the same canonical URL from one source of truth; the identical `corpus_query` for a fixed prompt returns the same top-k entries whether issued from the Claude hook, the Claude MCP, or Codex.

**Dependencies:** §0.1 decision. **Risk:** demoting `CLAUDE.md` before the generated `AGENTS.md`/hook is verified would briefly drop Codex rules — so 1.2 must verify-green before 1.3.

---

## 2. Gap #2 — Habitual session-close auto-capture into an evidence tier

**Objective.** Session-level lessons get captured automatically as **evidence-grade candidates** (not directives), for later promotion.

**Steps.**
- Use the existing `run_learned_memory_proposal_workflow` (evidence-backed, repo-scoped, `confidence`) as the candidate store — do **not** auto-write the global corpus.
- Add a session-close capture: a `Stop` hook (Claude Code — this event exists) that summarizes the session's durable lessons and calls the proposal workflow with `evidence_entity_key` set to the session. **Depth note:** Codex has **no session-end hook** — only `notify=[...,"turn-ended"]` (a per-turn external notification). So Codex capture is **best-effort**: either drive capture from the `notify` turn-ended program (detecting end-of-work heuristically) or treat Codex auto-capture as a documented follow-up. Claude Code `Stop` is the guaranteed path; **do not assume a Codex session hook that doesn't exist.**
- **Capture criterion (locked, to control noise):** capture only durable, reusable lessons — a confirmed gotcha, a corrected approach, or a decision with lasting rationale. Do **not** capture one-off task chatter, transient state, or anything already in `DIRECTIVES.md`.
- Promotion stays manual via `run_learned_memory_commit_workflow` (approve/reject) — preserves the trust gate.
- **Promotion path to the authoritative store (closes the §2→§1 link).** An approved evidence proposal does not itself become a directive. It is surfaced to the §3 Spark/review queue; from there Kamen either (a) "lock it" into a new `G`-rule in `DIRECTIVES.md` (directive-grade), or (b) upsert a global corpus `reference` entry (reference-grade). This is the only route by which repo-scoped captured evidence becomes part of the global authoritative memory (§1).
- **Acceptance:** ending a session creates ≥1 proposal candidate meeting the capture criterion; `run_learned_memory_commit_workflow` can approve it; an approved candidate appears in the §3 review queue; nothing lands in the global corpus/`DIRECTIVES.md` without Kamen's explicit promotion; capture/Codex hook has a test (X-TEST).
**Dependency:** none hard; feeds §3 (promotion).

---

## 3. Gap #3 — Proactive "directive Spark"

**Objective.** Surface *candidate* directives from our own telemetry before a lapse repeats.
**Steps.**
- New scheduled job `working-agreement/directive_spark.py` that pulls `get_finding_pattern_summary`, `get_clarification_policy`, `get_triage_confusion_clusters`, `get_agent_failure_mode_summary`, clusters recurring patterns above a frequency floor, and emits proposed `G`-rule drafts to a review file (never auto-commits to `DIRECTIVES.md`).
- **Telemetry scope (locked).** These tools are repo-scoped (`repository_key` required). Spark iterates the **active repo set** (the same Kamen-owned repos enumerated in §1's in-scope list) and aggregates patterns across them; cross-cutting patterns (seen in ≥2 repos) rank highest. It also ingests the §2 approved-evidence queue as candidate input.
- You review → "lock it" promotes a draft into `DIRECTIVES.md` (existing flow); this is the same promotion path §2 feeds.
- **Acceptance:** running it across the active repo set produces ≥1 grounded candidate with its supporting pattern + source repo(s); §2 approved-evidence items appear as candidates; zero auto-writes to `DIRECTIVES.md`; `directive_spark.py` has a test (X-TEST).
**Dependency:** §7 schedules it.

---

## 4. Gap #4 — Portable, client-agnostic directive read path

**Objective.** The working agreement applies in Codex (and any MCP client), not only Claude Code.
**Resolution.** Largely delivered by **§1.2 (Codex `AGENTS.md` projection)** + **§0.1 (one endpoint)**. Remaining: document the projection/connection pattern in a new `working-agreement/SETUP-codex.md` (the file `SETUP-claude.md` already promised), mirroring `SETUP-claude.md`.
- **Acceptance:** `SETUP-codex.md` exists; following it on a clean machine gives Codex the directives; both tools read the same canonical brain.
**Dependency:** §1.2, §0.1.

---

## 5. Gap #5 — Recency + relevance floor in corpus retrieval

**Objective.** Stop stale/weak entries being injected as authoritative background.
**Grounded nuance:** a relevance floor *already exists* at the Claude hook (`hydrate_corpus.py` `MIN_SCORE`, default 0.5). The real gaps: (a) **no recency weighting** anywhere; (b) the floor lives only in the Claude hook, not in `corpus_query` or for other consumers.
**Steps.**
- Add recency-aware ranking server-side in `corpus_query` plus an optional `min_score`/threshold param so every consumer (not just the hook) benefits.
- **Recency source (depth-locked).** `memory.corpus_entries` already has `created_utc`/`updated_utc` (`migration 027`), but the Qdrant `CorpusEntryPayload` carries **no timestamp**, so it's not available at vector-rank time. **Default approach:** after the Qdrant similarity search, **re-rank in PG** by joining `corpus_entries` on `entry_key` to blend similarity with `updated_utc` age — this needs **no Qdrant re-index**. (Alternative, only if re-rank proves too slow: add `updated_utc` to `CorpusEntryPayload` and re-index.)
- Keep the hook's `MIN_SCORE` as a client override.
- **Acceptance:** for two entries of equal similarity, the newer (`updated_utc`) ranks higher; a below-threshold entry is excluded at the `corpus_query` layer; the Claude hook still passes; recency ranking has a test (X-TEST); change deployed to the canonical endpoint (X-DEPLOY).
**Dependency:** §0.1 (so all consumers see the same ranking).

---

## 6. Gap #6 — Prune test-repo clutter

**Objective.** `list_repositories` shows the 9 real repos, not 47 empty `mawf-*`/`example.invalid` test artifacts.

**Depth correction (2026-06-20).** The plan originally assumed deactivation alone cleans the listing. **It does not:** `list_repositories` (`src/memory_knowledge/server.py:846`) does `SELECT … FROM catalog.repositories r … ORDER BY r.name` with **no status filter**, so it returns repos regardless of `status_id`; `deactivate_repository` (`admin/mawf.py:621`) only sets `status_id → inactive`. So #6 needs a small **code change** to the listing tool + deploy, not just an operational deactivation.

**Steps (corrected, non-breaking).**
- **Code (additive + one default change).** Add optional param `include_inactive: bool = False` to `list_repositories`; add `LEFT JOIN core.reference_values rstat ON rstat.id = r.status_id` and `WHERE ($1::bool OR rstat.internal_code IS DISTINCT FROM 'inactive')`. Safe: a repo's `status_id` always resolves to a `REPOSITORY_STATUS` value (reference trigger `016:229`) and is `NOT NULL` (`016:144`). **Non-breaking analysis:** param is additive (existing calls unchanged); the *one* behavior change is the default now hides `inactive` repos — fully recoverable via `include_inactive=True`, only ever applied to repos we explicitly deactivate.
- **Data (reversible).** Set the ~47 empty test repos to `inactive`: MAWF repos via `mawf_deactivate_repository` (resolve `mawf_repository_id` first); confirm each non-MAWF `repo-*`/`idx-*` resolves, else handle via the same status path. **Never** `purge_repository` (hard delete across PG/Qdrant/Neo4j) — soft only, reversible by reactivating.
- **Deploy (X-DEPLOY).** Ship the `list_repositories` change to the Azure canonical endpoint (Kamen/ops step).
- **Test (X-TEST).** Unit test: inactive excluded by default; included when `include_inactive=True`; active always present.
- **Acceptance:** after deploy, `list_repositories` (default) returns only active/real repos; `include_inactive=True` still returns all; nothing purged; pre-deactivation inventory printed and approved.
**Dependency:** Azure deploy. Low-risk and reversible.

---

## 7. Gap #7 — Scheduled review/consolidation cadence

**Objective.** Drift (stale rationale, dupes, dead links) gets cleaned on a schedule, not by memory.
**Steps.**
- Wrap existing tools (`consolidate-memory` skill, `run_compaction_workflow`, `run_integrity_audit_workflow`) into one wrapper script under `working-agreement/` (consistent with the existing shell-script automation pattern, e.g. `sync-corpus.sh`).
- **Scheduler (locked).** Schedule the wrapper with a local **launchd** job (macOS) running weekly — chosen over a cloud routine because the wrapper invokes local scripts + the local `.venv`, matching how `inject-*`/`sync-*` already run on this machine. (Cron is the Linux fallback if Kamen moves the job off macOS.)
- Also schedule §3's `directive_spark.py` in the same weekly job.
- Auto-update the `DIRECTIVES.md` "Last reviewed:" stamp when the review runs (commit the stamp change so `sync_corpus.py`'s post-commit mirror stays consistent).
- **Acceptance:** the launchd job runs on the weekly schedule and produces a consolidation report; the stamp updates automatically; the wrapper has a test or a documented manual dry-run (X-TEST).
**Dependency:** §3 (for the Spark step).

---

## 8. Gap #8 — Cite retrieved memory back to its source

**Objective.** When a corpus entry informs an answer, its source is identifiable (audit trail) — honoring G0's "checkable artifact."
**Grounded detail:** `hydrate_corpus.py` currently labels injected entries with `title`/`link_slug` + score but **not** `entry_key`. `corpus_query` already returns `entry_key`.
**Steps.**
- Update `hydrate_corpus.py` to include `entry_key` (and `link_slug`) in each injected block, and add a one-line instruction in the injected preamble: "cite the entry_key/link_slug when an entry materially informs an action."
- Optionally add a lightweight convention to `DIRECTIVES.md` (a G-rule) making citation expected for corpus-driven decisions.
- **Acceptance:** injected corpus blocks show `entry_key`/`link_slug`; a corpus-driven answer can name its source.
**Dependency:** none hard; pairs naturally with §5 (same file).

---

## Sequencing (recommended)

1. **§6** (quick win, zero deps) → **§0.1 decision** → **§5 + §8** (same file, one retrieval PR) → **§1** (the big one: 1.1→1.2→verify→1.3→1.4→1.5) → **§4** (`SETUP-codex.md`, falls out of §1) → **§2** → **§3** → **§7** (schedules §3 + consolidation).

## Locked decisions (P2)
- Authoritative source = `DIRECTIVES.md` (file), brain mirrors it; all else projected. *(Kamen, 2026-06-20)*
- Auto-capture writes **evidence-tier proposals**, never the global corpus directly; promotion stays human-gated.
- Spark **proposes**, never auto-edits `DIRECTIVES.md`.
- Distillation: directive-grade → new `G`-rules; reference-grade → corpus `reference` entries.
- §6 uses an existing repo-deactivation tool, verified non-destructive first — no invented bulk delete.

## Open decisions
- **None.** §0.1 (canonical endpoint) is **decided: Azure** (2026-06-20). The plan is fully resolved and ready to implement.

## Out of scope (named, not silently dropped)
- Model/embedding-gateway abstraction and global-corpus export tool (the two "smaller adjacent gaps") — deferred unless you want them folded in.
- Multi-user/RLS sharing (single-operator today).

## Risks
- §1.3 before §1.2 verifies → temporary loss of Codex rules (mitigation: order + verify-green gate).
- §5 recency change alters what gets injected globally → ship behind the threshold/recency params with the hook default unchanged until validated.
- §6 wrong tool → data loss (mitigation: confirm non-destructive tool + dry-run/inspect first).
