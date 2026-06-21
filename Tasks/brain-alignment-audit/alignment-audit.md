# Alignment Audit — memory-knowledge impl ↔ DIRECTIVES.md ↔ second brain

**Mode:** Research (internal, findings only; no code shipped). Created 2026-06-21.
**Deliverable:** Full alignment audit + recommendations across the three components, through two
prisms — **(P1) Kamen's personal work + the brain [PRIORITY]** and **(P2) the mcp-agents-workflow
harness + the brain**. Evidence grounded in `path:line` / live `az`/MCP output; inferences marked.

Produced by four parallel read-only research agents (component coherence; P1 fit; P2 usage;
collision surface), synthesized here.

---

## 0. Executive verdict

The **directive→brain→delivery loop is genuinely sound**; the **capture loop is largely inert for
your personal work**; and the **brain is architecturally fused to the autonomous harness** in a way
that makes your (higher-value, lower-privilege) personal use the *junior tenant* on shared compute,
a shared write-capable vault, a global data namespace, and a global job dispatcher. The incident you
just lived through was not a fluke — it's the predictable output of that fusion.

- **Aligned & working:** DIRECTIVES.md → Tier-1 injection (verbatim) and → Tier-2 corpus (verified
  faithful mirror of G0–G15, sync timestamps match the last directive commit to the second).
- **Misaligned (P1):** the capture half is switched "on" but silently captures little — repo-key
  casing, unregistered repos, no Codex path, and notes that are written but rarely read back.
- **Misaligned (cross-prism):** P1 and P2 share one Basic worker, one vault (harness can *write*
  the brain's secrets), one global corpus/learned-record namespace, and one dispatcher with no
  stop/cancel and an auto-resume — i.e. the harness can degrade, pollute, or destabilise your brain.

**Bottom line for P1:** to make your personal brain *reliable and private*, alignment points toward
**decoupling control-plane + isolating data/secrets from the harness**, plus a handful of cheap
capture fixes. Detail below.

---

## 1. What is aligned and working (don't break these)

| # | Mechanism | Evidence |
| --- | --- | --- |
| A1 | **Tier-1 directives reach every Claude session verbatim** — global `UserPromptSubmit` hook | `inject-directives.sh:14`, `~/.claude/settings.json:8` |
| A2 | **DIRECTIVES.md → corpus mirror is faithful & current** — post-commit hook re-syncs only on directive change; deterministic entry_key; orphan prune | `.git/hooks/post-commit`→`sync-corpus.sh:15`, `sync_corpus.py:128-134`, `entity_key.py:43-48`; **live: G0–G15 all present, `updated_utc` matches commit `1b2c2f6` to the second** |
| A3 | **Tier-2 corpus hydration per prompt** (score≥0.5, top-3, "context only") | `inject-corpus.sh:17`, `hydrate_corpus.py:41` |
| A4 | **Schema/enum coherence** — corpus `kind` CHECK == `VALID_CORPUS_KINDS`; `VALID_MEMORY_TYPES` includes `note` | `027_corpus_schema.py:37-39` == `workflows/corpus.py:28` |
| A5 | **Repo-note write→retrieve loop closes for ingested repos** (PG + `learned_memory` Qdrant, surfaced by `repo_scoped_memory`) | `repo_note.py:179-209`, `retrieval.py:851-875`; live taggable-api: 4 PG == 4 Qdrant |
| A6 | **Codex gets directives via generated per-repo `AGENTS.md`** (full projection or fenced merge) | `generate_projections.py`, `SETUP-codex.md`, trusted projects in `~/.codex/config.toml` |

---

## 2. Misalignments — Prism 1 (your personal work) · PRIORITY

| ID | Severity | Finding | Evidence | Impact |
| --- | --- | --- | --- | --- |
| **P1-1** | **High** | **Capture silently no-ops on case-mismatched repos.** `auto_capture` derives `repo_key = Path(cwd).name` (→ `FCSAPI`), but the registered key is `fcsapi`; `author_repo_note` does an exact-match lookup and raises, swallowed fail-open. | `auto_capture.py:48`, `repo_note.py:59-63`; live: fcsapi has 0 `unverified`/`note` records | Your most-active capitalised repos accrue **nothing**; no error shown. |
| **P1-2** | **High** | **~5 of 8 Codex trusted repos aren't registered/ingested**, so capture dead-ends there (`author_repo_note` refuses without an ingested revision). incl. the brain's own repo. | `repo_note.py:72`; `taggable-database`/`united-partners`/`agentic-trading` absent from `list_repositories` | Capture is impossible across most of where you work — and the only way to enable it today is **full source ingestion** (the heavy/sensitive path that caused the incident). This is the real "notes-only ingestion" gap. |
| **P1-3** | **Med** | **Auto-captured notes are written but rarely read** — the per-prompt hook only calls `corpus_query` (global Tier-2), never `run_retrieval_workflow` (repo-scoped). | `hydrate_corpus.py:41` (no repo-scoped call) | Repo notes/lessons surface only if an agent *deliberately* runs retrieval → the capture→recall loop isn't closed automatically. |
| **P1-4** | **Med** | **No auto-capture in Codex at all** — Stop-hook is Claude-only; the skill isn't installed in `~/.codex/skills`. Codex is ~half your workflow. | `SETUP-autocapture.md:28`; skill absent in codex | Durable lessons from Codex sessions are captured by neither path. |
| **P1-5** | **Med** | **Codex directive freshness depends on the weekly job, which has never run.** `refresh_trusted` only runs in `weekly_review.py` (or manually); plist loaded but no run yet (stamp `2026-06-19`, no log). | `weekly_review.py:80-92`; `launchctl` loaded, no `/tmp/mk-weekly-review.log` | After a `DIRECTIVES.md` edit, Codex sessions read **stale** projected rules until Monday. Claude unaffected (live injection). |
| **P1-6** | **Low** | **Spark/weekly hardcode 3 repos** (`taggable-api,fcsapi,taggable-server`); no `MK_SPARK_REPOS` override set. | `directive_spark.py:28`, `weekly_review.py:23` | Recurring patterns in your other repos never surface as directive candidates; promotion stream is partial. |
| **P1-7** | **Low** | **Stop-hook spends an LLM call every session** but candidates (conf 0.4) have no surfacing/promotion in your daily loop; weekly review doesn't surface spark candidates either. | `auto_capture.py:26`; `weekly_review.py` runs spark+integrity only | Paid calls that (given P1-1/2) often write nothing, and a candidate pile nothing promotes. |

> **Resolved from agent UNVERIFIED:** `author_repo_note`/`deactivate_repo_note` **are** deployed and
> callable (used successfully live this session, incl. `deactivate_repo_note` after the `sha-0f39318`
> deploy). Their absence from the session tool-index was a surfacing artifact, **not** a real gap.

---

## 3. Misalignments — Prism 2 (the harness) and cross-prism collisions

The harness (`workflow-orch-app`) is a heavy brain **writer**: it owns catalog identity
(users/projects/**repositories**/prompts), tasks + leases, workflow runs + all run children,
triage cases, learned-memory proposals, QA pairs — and reads retrieval + the whole `get_*_summary`
telemetry layer (`knowledge_client.py`, `mawf_client.py`, `workflow_persistence.py`, `triage_memory.py`).
It has **no working agreement of its own** — it inherits `DIRECTIVES.md` only as an `AGENTS.md`
projection (doc-level, no runtime enforcement). It is the writer of `catalog.repositories` via
`mawf_upsert_repository` — which is *why* the brain's own `register_repository` is the broken stepchild.

| ID | Severity to P1 | Collision | Evidence | Risk to your work |
| --- | --- | --- | --- | --- |
| **X-1** | **Critical** | **One global job dispatcher, no running-job cancel, threshold-less reclaim-on-start + auto-retry sweep** → started jobs auto-resume across restarts. | `jobs/dispatcher.py:31-131,62-82`, `state_transition_guard.py:3-8`, `job_retry_manager.py:50-88`, `config.py:111,117` | **This is the incident.** You cannot reliably stop your own long job; dispatcher has no consumer/stop awareness. |
| **X-2** | **High** | **Shared vault `hrness`, asymmetric: harness = Secrets Officer (write/delete), brain = read-only** — and harness actively writes secrets at runtime (`KV_WRITEBACK_ENABLED=true`: `git-repo-mapping`, `github-app-config`). | `az role assignment list`; `mcp-agents-workflow/.../credential_refresh.py:710-808,860-890` | A harness bug/injection can **clobber or rotate the brain's secrets** (DB URL, Qdrant/Neo4j, GitHub/Codex auth). Your brain can't even write the vault it depends on. |
| **X-3** | **High** | **Brain data is GLOBAL — no per-consumer namespace.** Tier-2 corpus has no owner column; `learned_records` scoped only by `repository_id`; `run_retrieval_workflow` has no actor/tenant param. | `027_corpus_schema.py:18`, `001_initial_schema.py:207-227`, `retrieval.py:862-871`, `server.py:176` | Harness writes (learned-records, catalog, **corpus**) land in **your** retrieval namespace. Your working-agreement corpus is shared with an autonomous writer; only `repository_key` overlap separates you. |
| **X-4** | **High** | **One B3 (Basic, 1 worker) App Service Plan shared by `memory-knowledge` + `workflow-orch-app` + `up-harness`.** Harness runs autonomous sweeps (15s poll). | `az appservice plan show` (B3, cap 1); harness `WORKFLOW_ORCH_SWEEPS_ENABLED=true` | A heavy harness run can **starve/OOM-restart your brain** — which then triggers X-1's resume chain. Cascading instability. |
| **X-5** | **Med** | **`register_repository` is broken** — inserts without the NOT-NULL `mawf_repository_id`/`status_id` that migration 016 added (no default); only the MAWF path supplies them. | `016_mawf_contract.py:123,143-145` vs `server.py:6158`; **confirmed live this session** (constraint violation) | Your own repo registration fails; you're forced through the harness's `mawf_upsert_repository`. The brain's repo lifecycle is coupled to the MAWF contract. |
| **X-6** | **Low** | Shared ACR `workfloworchreg` + storage `workfloworchstore`. | `az resource list` | Build-time/quota coupling; a problem on one app's image/storage affects the other. |

---

## 4. Recommendations (prioritised — P1 first)

### Tier A — cheap, high-value for your personal work (low risk, mostly local)
1. **Fix capture repo-key normalization** (P1-1): map cwd→registered key case-insensitively (or store a canonical key) so `author_repo_note` resolves. One small change in `auto_capture.py` + `repo_note` lookup. *Unblocks capture for FCSAPI etc.*
2. **Build the notes-only "register a revision" path** (P1-2): let `author_repo_note` anchor to a lightweight repo revision **without full source ingestion** — this is the gap that forced the disastrous full ingest. Makes capture possible everywhere *without* embedding private source. *(This is the single most important P1 build — it both unblocks capture and removes the reason the incident happened.)*
3. **Close the capture→recall loop** (P1-3): add a repo-scoped retrieval call to the per-prompt hook (or a skill) so captured notes actually resurface.
4. **Codex capture path** (P1-4) + **install the skill in `~/.codex/skills`**; **set `MK_SPARK_REPOS`** to your real repo set (P1-6); **surface `spark-candidates.md`** in the weekly review output (P1-7).
5. **Run the weekly job once now** (P1-5) so projections refresh and the cadence is proven before relying on it.

### Tier B — decouple the control plane (kills the incident class)
6. **Make jobs stoppable** (X-1): add a `running→cancelled` transition + a cancel tool, and gate `reclaim_stale_running_jobs_on_start` by an age threshold (and/or per-consumer). This is the durable fix for "can't stop my own ingestion."
7. **Fix `register_repository`** (X-5) — already flagged as a spawned task; make it set `mawf_repository_id`/`status_id` or delegate to the MAWF upsert.

### Tier C — isolate your brain from the harness (the strategic question)
8. **Remove the harness's write access to the brain's secrets** (X-2): give the brain its own vault (or per-secret RBAC the harness can't reach), and stop the harness writeback touching brain secrets.
9. **Namespace brain data by consumer** (X-3) *or* run a **separate brain instance** for personal use: add an actor/owner dimension to corpus + learned_records + retrieval, or physically split. Decide based on whether you want one shared brain with isolation vs two brains.
10. **Give your brain its own compute** (X-4): move `memory-knowledge` off the shared B3 plan (own plan/tier) so harness load can't starve it.

> Tiers B/C are **build-bound** (code + infra). If you want to act on them, the next step is a
> plan + the hardening gates, per the playbooks. Tier A items 1–5 are mostly local config/scripts.

---

## 5. UNVERIFIED ledger (carry into any build)
- Live `corpus_query` recency/min_score behaviour matches source (not exercised live).
- Whether any external agent actually consumes `repo_scoped_memory` from the retrieval bundle.
- `up-harness` (identity `21f06472…`) relationship to the brain — co-tenants the plan + has its own vault secrets; write-path to the brain not traced.
- Whether the harness shares the brain's Postgres **directly** (confirmed sharing is via the MCP write path, not direct DB).
- `run_route_intelligence_workflow`/`submit_route_feedback` are surfaced to subagents but not called by the harness engine (UNVERIFIED whether subagents exercise them at runtime).
- Migration-016 NOT-NULL break confirmed in source + **reproduced live** this session; no later default migration found.
