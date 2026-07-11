# Working Agreement — Build Roadmap
<!-- Continuity doc: lets a new session resume the slice-by-slice build. Last updated: 2026-06-13 -->

## Goal (north star)
A small, Kamen-authored set of rules Claude reliably follows, so Kamen stops having to
re-explain himself.

## How we work on this (governed by G1)
One small, checkable slice at a time. Each slice tied to the goal in a sentence. No big
blueprints. Cut over add. Kamen authors; Claude proposes — nothing is binding until Kamen
confirms. **Confirm word: "lock it"** — that phrase, and nothing else, promotes a rule
from "proposed" to live.

## Decisions locked
- **Scope:** global (all projects), via a hook that injects the rules file every session.
- **Two tiers, both live:** Tier-1 = always-injected rules file (this repo); Tier-2 = MCP
  knowledge DB for the larger corpus (examples/rationale), retrieved on demand.
- **Three knowledge kinds:** Directives (rules) · Playbooks (how we run a task type → skills)
  · Corpus (reference → MCP).
- **Placement:** overarching directives live in `DIRECTIVES.md`; task-scoped ones live inside
  their playbook skill.
- **Refinement rule:** when a rule isn't perfect, sharpen the existing rule in place — never
  add a new rule for the same problem. A rule is "done" when its `repeated:` counter stays 0.
- **Measurement (lightweight):** a `repeated:` counter on each directive.
- **Task types (the playbook buckets):** Research · Plan · Write code · Review.

## Done (live plumbing)
- `DIRECTIVES.md` with directives **G0** (open every turn with a checkable compliance pass),
  **G1** (keep Kamen in grasp), **G2** (concrete consequence before a decision),
  **G3** (stay inside the scope of the ask), **G4** (no unapproved workarounds).
- `inject-directives.sh` (executable) + global `UserPromptSubmit` hook in
  `~/.claude/settings.json` → `DIRECTIVES.md` is auto-injected every session, every project.
- `SETUP-claude.md` (office-machine runbook). Codex setup deferred to a future `SETUP-codex.md`.

## Backlog — candidate next slices (pick ONE at a time)
- [x] Decide the promotion/confirm word → **"lock it"**.
- [x] Enumerate Kamen's recurring task types → **Research · Plan · Write code · Review**.
      (bugfix/feature collapse into write-code; infra cut for now.)
- [x] Author the first playbook skill → **Research** (`~/.claude/skills/research-playbook/SKILL.md`).
      Shape settled: when-it-triggers + skills to reach for + task-scoped directives. Research uses
      Option C — default to findings, flag when build-bound, then run the 3 gap-loop gates on Kamen's go.
- [x] **Plan** playbook (`~/.claude/skills/plan-playbook/SKILL.md`). Default to hardening (plans are
      build-bound): `verify-plan` for small plans; flag-and-wait → coverage + satisfaction gates for
      build-critical ones. Directives P1 (one-shot test) and P2 (lock decisions, don't list options).
      Upstream link locked (Option 1): a plan rests on *sufficient understanding*, not a mandatory
      research step — research only when understanding is missing; loop back when planning hits an unknown.
- [x] **Write code** playbook (`~/.claude/skills/write-code-playbook/SKILL.md`). Rests on sufficient
      plan/understanding; reach for `verify` / `code-review` / `simplify` / `review-fix-loop`.
      Directive WC1 (verify before "done"). Deliberately no "smallest change" rule — that's G3 for code.
- [x] **Review** playbook (`~/.claude/skills/review-playbook/SKILL.md`). Rests on knowing intent
      (the plan, when one exists); reach for `code-review` / `security-review` / `review` /
      `review-fix-loop`. Directives RV1 (real over many) and RV2 (cover the plan).
      All four task-type playbooks now authored: Research · Plan · Write code · Review.
- [x] Task-mode router table added to `DIRECTIVES.md` (after the prime directive): the four modes
      → their playbooks, with the Research → Plan → Write code → Review chain noted.
- [~] MCP corpus path. **Research done:** no direct row-write tool; writes go via learned-memory
      (propose→commit) or repo-ingestion, both ill-fitting — so we're **building a new path + tables**.
      **Plan done & gated** (coverage + satisfaction converged): `docs/TIER2_CORPUS_IMPLEMENTATION_PLAN.md`
      (+ `.coverage-audit.md`, `.satisfaction-audit.md`). New `memory.corpus_entries` table (global,
      not repo-scoped), PG + Qdrant (no Neo4j), direct write tool `run_corpus_upsert_workflow` +
      read tool `corpus_query`. Build order: (1) migration (2) writer+qdrant (3) workflow+MCP (4) tests.
      **Slice 1 DONE** — `migrations/versions/027_corpus_schema.py` (`memory.corpus_entries`); upgrade/
      downgrade round-trip verified against the remote DB (table + CHECK + 4 indexes confirmed; DB at 027).
      **Slice 2 DONE (PG side)** — `corpus_writer.py`, `corpus_qdrant.py`, `CorpusEntryPayload`,
      `corpus_entry_key`, `corpus_entries` + kind/link_slug payload indexes in `db/qdrant.py`. PG writer
      verified live (insert/idempotent-upsert/deactivate/supersede/CHECK-reject, all clean) using a
      captured Supabase CA bundle for verified TLS (no .env change). Qdrant projection + collection
      registration written & import-verified; **live Qdrant check folded into slice 3** (workflow
      exercises embed→upsert→query end-to-end).
      **Slice 3 DONE (code + partial live verify)** — `workflows/corpus.py` (`run_upsert`/`run_query`)
      + MCP tools `run_corpus_upsert_workflow` (remote-write guard) and `corpus_query`, wired in `server.py`.
      Verified live: imports clean; `ensure_collections` created the `corpus_entries` collection + payload
      indexes against live Qdrant (confirms slice-2 SGAP-001/002); PG upsert path fired. NOT verifiable
      locally: embed→Qdrant + semantic query — `fastembed`/`onnxruntime` has no wheel for x86_64-mac/py3.14;
      runs only in docker/linux. **Folded into slice 4 (tests in CI/docker).**
      **Slice 4 DONE** — `tests/test_corpus.py` (12 tests, all pass locally via mocked pool/qdrant/embed,
      mirroring `test_qa_memory.py`): entry_key determinism, upsert PG+Qdrant, invalid-kind/empty-input
      errors, idempotent re-upsert, supersede (old deactivated in PG+Qdrant + supersedes_key link),
      query is_active/kind/link_slug filter + PG hydrate, and the MCP tools incl. guard-blocks-write.
      Mocks cover the embed/query/supersede logic the local platform can't run live (fastembed wheel);
      true-live infra check remains for CI/docker. No regressions (sibling tests pass).
      **ALL FOUR BUILD SLICES COMPLETE — Tier-2 corpus path built & tested.**
      **Review pass done** (review-playbook): RV2 confirms all R1–R16 + acceptance covered; RV1 found
      no blocker — 3 findings (F1 title-in-identity, F2 supersede/embed ordering, F3 shared index loop)
      all resolved as by-design → documented in code (no behavior change). 12 corpus tests still green.
      Chain complete: Research → Plan (gated) → Write code → Review. Merged + deployed live (Azure).
      **MCP verified end-to-end** through the deployed server (`corpus_query`/`run_corpus_upsert_workflow`):
      real ingest → semantic hydrate (score 0.62) → link_slug filter excludes — all `status:success`.
      MCP entry: user-global `~/.claude.json` + vendored `scripts/mcp-remote-wrapper.sh`.
- [~] **Corpus triggers** (make ingest/hydrate actually fire — storage alone is inert).
      **Backfill DONE** — `scripts/backfill_corpus.py` ingested G0–G4 as `directive_rationale` entries via
      the deployed MCP; hydration spot-check passed (G2/G4/G3 retrieved correctly, semantic + filtered).
      **Skill DONE** — `~/.claude/skills/corpus-add/` (curate one entry on demand via the MCP tool;
      stops if MCP not connected, no workaround per G4). The skill is now versioned in this repo's
      managed skill manifest and installed to clients through the transactional installer.
      **Hydration trigger DONE (Option A)** — `working-agreement/hydrate_corpus.py` + `inject-corpus.sh`,
      registered as a 2nd `UserPromptSubmit` hook in `~/.claude/settings.json`. Per prompt it queries the
      deployed `corpus_query`, injects top hits ≥0.5 score (≤3), labeled context-only; fail-open + 6s timeout.
      Verified: relevant prompt → G2 injected (0.73); unrelated → nothing; bad URL → fail-open exit 0.
      (Takes effect on next session start — hooks load at startup.)
- [x] **Corpus triggers COMPLETE** — ingest (backfill + `corpus-add` skill) and hydrate (per-prompt hook)
      both live. The Tier-2 corpus is now self-serving: content goes in deliberately, relevant entries
      come back automatically each prompt.
      Note: pre-existing `.env` leakage (`ALLOW_REMOTE_WRITES=true`) fails 4 `test_guards.py` tests when
      run from the repo dir — unrelated to this work (same class as the prior `test_config.py` isolation fix).
- [~] **Corpus auto-sync (full mirror)** — keep Tier-2 mirrored to DIRECTIVES.md on every commit, not
      just on remembered manual ingests. **Server DONE** — new `corpus_deactivate` MCP tool
      (`server.py` + `workflows/corpus.py:run_deactivate`, soft-delete PG + Qdrant, remote-write guarded),
      reusing the existing `deactivate_corpus_entry`/`deactivate_corpus_point`. 17 corpus tests green
      (12 + 5 new). **Hook DONE** — `working-agreement/sync_corpus.py` + `sync-corpus.sh`, installed as the
      repo's git `post-commit` hook (symlink). On a commit touching DIRECTIVES.md it diffs HEAD vs HEAD~1:
      upserts current rules + deactivates orphans (rename = old title gone; deletion = rule removed).
      Verified offline: dry-run (6 rules, 0 orphans) + synthetic rename+deletion both detected as orphans.
      **PENDING DEPLOY** — `corpus_deactivate` is live only after the service is redeployed; until then
      upserts work and orphan-deactivation errors fail-open. (Pre-deploy, the upsert path also ingests G5.)
- [ ] Capture additional overarching directives as they come up.
- [ ] (later) Project overlays via the project-scoped memory store.

## Files
- `working-agreement/DIRECTIVES.md` — Tier-1 rules (auto-injected)
- `working-agreement/inject-directives.sh` — Tier-1 directives hook
- `working-agreement/hydrate_corpus.py` + `inject-corpus.sh` — Tier-2 per-prompt corpus hydration hook
- `working-agreement/sync_corpus.py` + `sync-corpus.sh` — Tier-2 corpus auto-sync (git post-commit; mirror DIRECTIVES.md)
- `working-agreement/INSTALL.md` — full Tier-1 + Tier-2 install runbook (new machine)
- `working-agreement/PLACEMENT.md` — what goes where (directive vs playbook vs corpus) litmus test
- `working-agreement/SETUP-claude.md` — original Tier-1 setup runbook
- `working-agreement/ROADMAP.md` — this file
- `scripts/backfill_corpus.py` · `scripts/mcp-remote-wrapper.sh` — corpus seed + MCP bridge wrapper
