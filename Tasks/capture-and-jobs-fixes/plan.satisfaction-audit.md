# Satisfaction Audit — Capture & Jobs Fixes plan

**Target document:** `Tasks/capture-and-jobs-fixes/plan.md`
**Loop:** `requirements-satisfaction-gap-loop` (DEPTH — does each addressed requirement actually HOLD end-to-end against real runtime / stored-data shape / sibling+harness features, given un-cited code).
**Grounding repos:** `/Users/kamenkamenov/memory-knowledge` (brain) and `/Users/kamenkamenov/mcp-agents-workflow` (co-tenant `workflow-orch-app` / `up-harness`).
**Presupposes:** `plan.gap-audit.md` (internal readiness) + `plan.coverage-audit.md` (breadth) converged. Requirement set reused from the coverage pass.
**Started:** 2026-06-21.

> Depth question: if a competent implementer builds exactly this plan, will each addressed requirement actually be satisfied against the code the plan does NOT cite, the live/stored data, and the harness it shares one PG/corpus/B3-plan with?

---

## Requirement Inventory (addressed set + implied-essential + interop invariants)

| req_id | requirement | type | source (quoted) |
| --- | --- | --- | --- |
| A1 | Capture repo-key normalization: case-insensitive resolution at the brain boundary (`FCSAPI`→`fcsapi`) on author + deactivate | stated | plan §A1; audit P1-1 |
| A2 | Notes-only revision/anchor path: anchor a note without full source ingestion (keystone) | stated | plan §A2; audit P1-2 |
| A3 | Close capture→recall: repo-scoped notes resurface automatically per prompt | stated | plan §A3; audit P1-3 |
| A4 | Codex capture path: install `auto-capture` skill in `~/.codex/skills` | stated | plan §A4; audit P1-4 |
| A5 | `MK_SPARK_REPOS` real set + surface `spark-candidates.md` in weekly output | stated | plan §A5; audit P1-6/P1-7 |
| B1 | Jobs stoppable: `running→cancelled` + `cancel_job` tool; cooperative ingestion abort; cancelled excluded from re-enqueue/reclaim | stated | plan §B1; audit X-1 |
| B2 | Age-gate reclaim-on-start so a fresh restart doesn't clobber a just-started job | stated | plan §B2; audit X-1/B2 |
| B3 | Fix `register_repository` NOT-NULL columns (`mawf_repository_id`, `status_id`) | stated | plan §B3; audit X-5 |
| INV-1 | **Write key == read key**: note authored under canonical key is retrievable by the same canonical key (Qdrant payload + entity_key) | implied-essential | A1.c/A1.d; loop brief lens 1/2 |
| INV-2 | **Synthetic `__note_anchor__` revision must not corrupt any latest-revision/branch-head/freshness/MAWF-repo consumer** | invariant | loop brief canonical risk |
| INV-3 | **`cancelled` state must be inert to every brain re-enqueue/reclaim path AND to the harness's job-state readers** | invariant | loop brief lens 1/5/6 |
| INV-4 | **B3 INSERT must satisfy the *full* live NOT-NULL set on `catalog.repositories` and produce rows the MAWF/harness repo-readers accept** | invariant | loop brief lens 5 |
| INV-5 | **A2 must not, by enabling capture on un-ingested repos, cause the heavy ingestion path it exists to avoid to fire (autonomously)** | invariant (intent) | loop brief lens 3/8; audit X-1 |

---

## Live/stored-data facts (verified vs unverifiable)

| fact | status | evidence |
| --- | --- | --- |
| `ops.job_manifests.started_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()` exists | VERIFIED | `migrations/.../001_initial_schema.py` job_manifests block |
| `catalog.repositories` NOT-NULL additions are ONLY `mawf_repository_id` + `status_id`; `provider/owner/repo_name` are nullable | VERIFIED | `016_mawf_contract.py:124-127,143-144` |
| `REPOSITORY_STATUS`/`active` reference value seeded (mawf_code='active') | VERIFIED | `016_mawf_contract.py:62` |
| `resolve_reference_value` matches `mawf_code=$2 OR internal_code=$2` | VERIFIED | `admin/mawf.py:159` |
| `learned_records` upsert conflict target = `(entity_id)`, entity from note's own `entity_key` | VERIFIED | `projections/learned_memory_writer.py:36,54`; `001` uq_learned_records_entity |
| `ingestion_scheduler_enabled` default **False** | VERIFIED (default); **live Azure value UNVERIFIABLE** | `config.py:92` |
| `reclaim_stale_running_jobs_on_start` default **True** | VERIFIED | `config.py:117` |
| Whether notes-only personal repos will be registered WITH an `origin_url` | **UNVERIFIABLE from repo** (depends on how B3 `register_repository` is called operationally) | — |
| Live count of `__note_anchor__` rows / current fcsapi note rows | **UNVERIFIABLE** (cannot read live PG/Qdrant) | plan asserts "fcsapi has 0 note records" |

---

## End-to-End Trace Table

| req_id | trace (trigger → … → surfaced result) | runtime/data evidence (path:line / value) | holds? |
| --- | --- | --- | --- |
| A1 | Stop-hook `repo_key_from_cwd`=`Path(cwd).name`=`FCSAPI` → `author_repo_note` → `ensure_repo_root_entity` resolve `lower(repository_key)=lower($1)` → canonical `fcsapi` threaded to entity_key + Qdrant payload → `run_retrieval_workflow("fcsapi")` filters Qdrant by `repository_key='fcsapi'` | `working-agreement/auto_capture.py` `repo_key_from_cwd`; `repo_note.py:58-63` (current exact-match), plan rewrites; `learned_memory_writer.py:54` conflict on entity_id; `retrieval.py:854-872` filters by `repository_key` | YES (with edits) |
| A1.deact | `deactivate_repo_note` → canonicalize first → `learned_record_entity_key(canonical,…)` → join `catalog.entities` by entity_key | `repo_note.py:274-287`; no `repository_key` WHERE (verified) | YES |
| A2 | `author_repo_note` → `ensure_repo_root_entity(auto_create_revision=True)` → no revision → `upsert_repo_revision(commit_sha='__note_anchor__')` → entities insert with synthetic `repo_revision_id` → learned_record → Qdrant | `entity_registrar.py:27-49` (ON CONFLICT repo_id,commit_sha); `repo_note.py:66-90` | YES (write); **interop fault — see SGAP-001/002** |
| A3 | UserPromptSubmit → `inject-repo-memory.sh` → `hydrate_repo_memory.py` (opt-in `MK_REPO_HYDRATE=1`) → `run_retrieval_workflow(raw cwd basename, prompt)` → reads `repo_scoped_memory` slice → additionalContext | mirror `hydrate_corpus.py`/`inject-corpus.sh`; `retrieval.py:851-875` builds `repo_scoped_memory` | YES |
| A4 | Codex session close → agent invokes `auto-capture` SKILL → `author_repo_note` (now works via A1+A2) | skill copy; depends on A1/A2 live | YES (advisory) |
| A5 | `weekly-review.sh` exports `MK_SPARK_REPOS` → `weekly_review._run` execs `directive_spark` module (reads env at import) → writes `spark-candidates.md` → weekly reads `spark.OUT`, prints count/path | `directive_spark.py:29,31,114-115`; `weekly_review.py:62-66` (loads module as `spark`) | YES (see cleanup CL-1) |
| B1 | `cancel_job` → write-guard → `get_job_by_id` → terminal? idempotent : `update_job_state("cancelled")` (guard `running→cancelled`) → worker `_save_ingestion_checkpoint` re-reads state → raises `JobCancelled` → `run()` returns error → `execute_job` skips `failed` transition (state already cancelled) | `state_transition_guard.py:5` (adds cancelled); `manifest_writer.py:66-68` (terminal branch); `ingestion.py:165` checkpoint chokepoint; `job_worker.py:59-100` (must add cancelled-guard) | YES (with edits; see CL-2) |
| B1.inert | `cancelled` excluded: dispatcher poll `IN ('pending','retrying')`; retry sweep `state_code='failed'`; reclaim `state_code='running'`; `get_active_job_for_shape` `IN ('pending','running')` | `dispatcher.py:121-122,79`; `job_retry_manager.py:63,76`; `manifest_reader.py:125` | YES |
| B2 | container restart → `_reclaim_stale_running` UPDATE adds `started_utc < NOW()-($1*INTERVAL '1s')` bind `reclaim_running_min_age_seconds` | `dispatcher.py:73-81`; `started_utc` exists (001) | YES |
| B3 | `register_repository` → `_reference_id("REPOSITORY_STATUS","active")` → INSERT `(mawf_repository_id, repository_key, name, origin_url, status_id)` → trigger validates status_id | `server.py:6156-6169` (current 3-col); `admin/mawf.py:529-546`; `016:143-144,229` | YES |

---

## Lens Coverage Matrix

| req_id | lens | status | evidence |
| --- | --- | --- | --- |
| A1 | 1 cross-feature contract | checked | Qdrant write payload `repository_key` vs `retrieval.py:854` filter — symmetric once canonical (INV-1) |
| A1 | 2 data-reality | checked | `learned_record_entity_key` is uuid5 with no case-fold (`entity_key.py:30`); canonicalization required & specified |
| A1 | 3 intent | checked | intent "capture works for capitalized dirs" served by boundary fix (all callers) |
| A1 | 4 e2e trace | checked | trace row A1 |
| A1 | 5 producer/consumer | checked | author writes canonical; deactivate + retrieval resolve canonical |
| A1 | 6 silent-inert | checked | Stop-hook fail-open preserved; previously-silent-zero now succeeds |
| A1 | 7 config | n/a | no env dependence |
| A1 | 8 scope-vs-usage | checked | boundary in `repo_note.py` covers Stop-hook/Codex/manual/deactivate |
| A2 | 1 contract | **GAP** | synthetic `commit_sha='__note_anchor__'` consumed by freshness_audit/repair_drift as a real sha → SGAP-001 |
| A2 | 2 data-reality | checked | revision row satisfies NOT-NULLs (`entity_registrar.py:37`); zero files/chunks |
| A2 | 3 intent | **GAP** | intent = capture WITHOUT heavy ingestion; freshness scheduler may auto-ingest notes-only repos → SGAP-002 (INV-5) |
| A2 | 4 e2e trace | checked | trace row A2 |
| A2 | 5 producer/consumer | checked | `list_repositories`/scheduler `latest_commit` go via `branch_heads` (NOT written) → synthetic invisible there (false-positive cleared) |
| A2 | 6 silent-inert | checked | ON CONFLICT idempotent; absent repo still errors |
| A2 | 7 config | checked | autocreate default True; no missing env |
| A2 | 8 scope-vs-usage | checked | `author_repo_note` already calls `ensure_repo_root_entity` default True |
| A3 | 1-8 | checked | mirrors deployed `hydrate_corpus.py` contract; opt-in + fail-open; `repo_scoped_memory` slice exists (`retrieval.py:875`) |
| A4 | 3,8 | checked | advisory skill; depends on A1/A2 (sequenced Phase 2 after Phase 1 deploy) |
| A5 | 2,7 | checked | `MK_SPARK_REPOS` read at spark import from process env; `weekly-review.sh` export feeds it; `OUT` constant exists |
| A5 | 1,5 | cleanup | plan says read `directive_spark.OUT`; must use the already-loaded `spark` module object → CL-1 |
| B1 | 1 contract | checked (+interop) | harness treats `cancelled` as terminal/non-active/non-recoverable already (INV-3) — one minor poll-timeout, non-fatal |
| B1 | 2 data-reality | checked | `manifest_writer` terminal branch must include `cancelled` (plan line 419) |
| B1 | 4 e2e trace | checked | trace rows B1/B1.inert |
| B1 | 5 producer/consumer | checked | abort chokepoint = `_save_ingestion_checkpoint` (covers all 8 ckpts); `execute_job` cancelled-guard required |
| B1 | 6 silent-inert | checked | offline path `job_id is None` → no re-check, but offline path is not the cancel target (dispatcher/tool path always has job_id) |
| B1 | 7 config | n/a | — |
| B1 | 8 scope-vs-usage | checked | chokepoint on ingestion hot path (8 `_save_ckpt` sites); non-ingestion = cancelled-on-record |
| B2 | 1,2,4,6 | checked | `started_utc` exists & not updated post-create (plan LD-11); DB `NOW()` both sides |
| B2 | 3 intent | checked | conservative (creation-time proxy trips earlier, never more lenient) |
| B2 | 7 config | checked | `getattr(...,300)` default; setting additive |
| B3 | 1,5 contract/symmetry | checked | INV-4: only `mawf_repository_id`+`status_id` NOT-NULL; provider/owner/repo_name nullable; MAWF readers use `repository_key/origin_url/name` (harness) + `mawf_repository_id/status_id` (MAWF view) — both populated |
| B3 | 2 data-reality | checked | `active` resolves via mawf_code (`mawf.py:159`); trigger satisfied |
| B3 | 3,8 | checked | unblocks registration; ON CONFLICT preserves MAWF columns |
| INV-2 | 1 | **GAP** | SGAP-001 (direct latest-revision readers) |
| INV-5 | 3 | **GAP** | SGAP-002 (freshness scheduler bootstrap) |
| INV-3 | 1 | checked | harness `mawf_recovery_scanner.py:18-23` excludes non-recoverable; `_is_terminal_status` includes cancelled; CL-3 (harness job-poll terminal set) |

---

## Blocker Gap Ledger

| gap_id | severity | req_id | lens | evidence (both sides) | why it breaks the requirement | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SGAP-001 | blocker | A2 / INV-2 | 1 cross-feature contract | **Producer:** plan writes `repo_revisions.commit_sha='__note_anchor__'` via `entity_registrar.upsert_repo_revision` (`entity_registrar.py:37`). **Consumers reading latest revision DIRECTLY from `repo_revisions` (not via branch_heads):** `integrity/freshness_audit.py:27-37` `SELECT rr.commit_sha … ORDER BY rr.created_utc DESC LIMIT 1` → sets `latest_pg_commit='__note_anchor__'`, compares to Qdrant points → falsely reports stale; `integrity/repair_drift.py` (rebuild) `ORDER BY rr.created_utc DESC LIMIT 1` → tags rebuilt Qdrant/Neo4j with `__note_anchor__` and may `checkout_commit('__note_anchor__')` (`git/clone.py:80`) → git error. | A notes-only repo that is later integrity-audited or rebuilt mis-reports freshness and can drive a bad git checkout — the synthetic revision is **not** the inert no-op the plan's Rollback/Edge-cases claim ("a synthetic revision with no files is inert"). The invariant "synthetic revision must not corrupt any latest-revision consumer" fails for the direct-`repo_revisions` readers. | **Lock the contract in the plan:** (1) document that the synthetic revision IS read as "latest" by `freshness_audit.py` and `repair_drift.py`, and add a **required implementation step**: those two queries must exclude the sentinel — `AND rr.commit_sha <> '__note_anchor__'` in the `ORDER BY … LIMIT 1` selects (and any future "latest real revision" reader). (2) Correct the plan's "inert" claims (§A2 Edge cases, Rollback A1/A2) to "inert for *source-retrieval* and for *branch_heads-keyed* readers (list_repositories, scheduler enqueue), but visible to direct latest-`repo_revisions` readers, which must filter the sentinel." | (pending edit) | OPEN |
| SGAP-002 | blocker | A2 / INV-5 | 3 intent / 8 scope-vs-usage | **Mechanism:** A2 lets a registered-but-uningested repo hold notes (good). **Collision:** `jobs/ingestion_scheduler.py:26-37` enumerates `catalog.repositories WHERE origin_url IS NOT NULL` (minus mawf/repo-/idx- prefixes), LEFT JOIN `branch_heads`. For a notes-only repo `branch_name IS NULL` → `_process_repo` bootstrap path (`ingestion_scheduler.py:179-185`) `resolve_default_branch` → `create_job('ingestion')` = **full source ingestion**. Gated by `ingestion_scheduler_enabled` (`config.py:92`, default False; **live Azure value not readable here**) and `ingestion_scheduler_repo_allowlist` (`config.py:96`, empty=all). | A2 exists precisely to enable capture WITHOUT the heavy/sensitive ingestion that caused the incident (audit X-1). If the freshness scheduler is enabled in the deployed env and a notes-only repo has `origin_url` set (B3 lets the caller set it), the brain will **autonomously full-ingest** that repo — defeating A2's intent and re-arming the very incident class B1/B2 contain. The plan never reconciles A2 against the scheduler. | **Lock in plan:** add an explicit interop subsection to §A2 + a **required step**: a notes-only repo must be excluded from the freshness scheduler's auto-ingest. Two acceptable mechanisms, pick one in the plan: (a) register notes-only repos with `origin_url = NULL` (scheduler filters `origin_url IS NOT NULL`, so a null-origin repo is never enumerated) — and state this as the B3-registration contract for personal/notes-only repos; OR (b) add `AND r.repository_key NOT IN (notes-only set)`/a sentinel-branch guard to `_ENUMERATE_SQL`. Also add a **verification step**: confirm `ingestion_scheduler_enabled` value in the live Azure env and the allowlist, and record the decision. Mark the live env value as the one user-decidable item if (a)/(b) cannot be guaranteed. | (pending edit) | OPEN |

---

## Cleanup / Known-Limitation List (non-blocking)

- **CL-1** (A5): Plan says "read `directive_spark.OUT`"; `weekly_review.py:62-66` loads the spark module into a local var `spark` via importlib. The surfacing code should read `spark.OUT` (the loaded module object), not a fresh `import directive_spark`. `OUT` is a module-level `Path` constant (`directive_spark.py:31`) so the value is identical; purely a wording precision. Acceptance still holds.
- **CL-2** (B1): The plan's `job_worker.py` cancelled-guard is essential (prevents `cancelled→failed` invalid transition raising inside `execute_job`). It is specified (plan lines 447-452) but should reference the exact result-handling sites `job_worker.py:59-70` (error) and `:83-88` (completed) and `:91-100` (except) — all three call `update_job_state` and all three would raise `InvalidStateTransition` on a cancelled row; the guard must precede all three (or wrap `update_job_state` to no-op when current=='cancelled'). Non-blocking because the plan already locks the intent; tightening the site list improves implementability.
- **CL-3** (B1/INV-3 harness): `mcp-agents-workflow/src/workflow_orch/mcp_server.py:8553` job-poll terminal set is `{"success","completed","error","failed"}` — does NOT include `cancelled`; a harness-initiated ingestion that gets cancelled will poll 3× then settle (≈0.6s) on a non-terminal/unknown read rather than recognizing `cancelled`. Harness-side, out of THIS repo's scope; recorded so the harness owner can add `cancelled` to that set. The brain change itself is safe (recovery scanner + active filters already exclude cancelled).
- **Known limitation** (B2, already documented in plan LD-11): `started_utc` is creation-time, a conservative proxy — acceptable.
- **Unverifiable** (explicit): live `__note_anchor__` row count, live fcsapi note count, and the live `ingestion_scheduler_enabled`/allowlist values cannot be read from the repo; SGAP-002 closure requires confirming the live scheduler config.

---

## Cycle 1 Plan (gap → exact edits)

- **SGAP-001** → Edit §A2 "Edge cases / failure behavior" and the Rollback bullets: replace the unqualified "inert" claim with the qualified statement; add a new bullet under §A2 "Exact change" listing the **required implementation step** to add `AND rr.commit_sha <> '__note_anchor__'` to the latest-revision selects in `integrity/freshness_audit.py:27-37` and `integrity/repair_drift.py` (the `ORDER BY rr.created_utc DESC LIMIT 1` reads), with acceptance "freshness audit on a notes-only repo returns `latest_pg_commit = NULL` (no real revision), not `__note_anchor__`."
- **SGAP-002** → Add a new subsection "§A2 interop — freshness scheduler" + a required step locking that notes-only repos are kept out of `ingestion_scheduler._ENUMERATE_SQL` (chosen mechanism), plus a verification step to confirm the live `ingestion_scheduler_enabled`/allowlist and record the decision. Cross-reference B3: the registration contract for personal/notes-only repos.
- **CL-1/CL-2/CL-3** → small precision edits (A5 wording, B1 job_worker site list, harness note) — applied with the blocker edits.

(Edits applied below in "Cycle 1 Edits"; a fresh Cycle 2 assessment follows per the no-same-cycle-convergence rule.)

---

## Cycle 1 Edits (applied to plan.md)

| edit | plan.md location | closes |
| --- | --- | --- |
| Added "Consequence (verified)" note that `list_repositories`/scheduler read latest commit via `branch_heads` (empty) so the sentinel is invisible there | §A2 `branch_heads`/`retrieval_surfaces` bullet | SGAP-001 (scoping the real exposure) |
| Added "Sentinel-revision filter on direct latest-`repo_revisions` readers (REQUIRED)" with `AND rr.commit_sha <> '__note_anchor__'` step for `freshness_audit.py:27-37` + `repair_drift.py:53-61`, citing `git/clone.py:80-82` | §A2 Exact change | SGAP-001 |
| Added "§A2 interop — freshness scheduler must NOT auto-ingest notes-only repos (REQUIRED)" — mechanism 1 (`origin_url=NULL`), mechanism 2 (enumeration filter), verification step for live `ingestion_scheduler_enabled` | §A2 (before acceptance) | SGAP-002 |
| Qualified the "inert" claim (Edge cases) and Rollback A1/A2 bullet | §A2 Edge cases; Rollback | SGAP-001 |
| Phase 3: register notes-only repos with `origin_url=NULL`; confirm live scheduler config | Sequencing Phase 3 | SGAP-002 |
| Test plan: SGAP-001 integrity sentinel-filter tests; SGAP-002 scheduler-exclusion test | Test plan | SGAP-001/002 |
| A5: read `spark.OUT` from the already-loaded module (not a fresh import) | §A5 surface bullet | CL-1 |
| B1: `job_worker.py` cancelled-guard must cover all three `update_job_state` sites (`:63-69`, `:83-88`, `:94-100`) or be a no-op in `update_job_state` | §B1 worker abort | CL-2 |
| B1: harness interop paragraph (recovery scanner excludes cancelled; poll-set CL-3 note) | §B1 (new Harness interop block) | CL-3 / INV-3 |

## Cycle 1 Validation

- Re-read `integrity/freshness_audit.py:26-41` and `integrity/repair_drift.py:48-70`: both confirmed
  `ORDER BY rr.created_utc DESC LIMIT 1` directly on `catalog.repo_revisions`, both have an `if row is None`
  branch that the `<> '__note_anchor__'` filter routes a notes-only repo into. SGAP-001 fix is correct and
  does not break the real-revision case (real shas are `<> '__note_anchor__'`).
- Re-read `server.py:945-988` (`list_repositories`) and `ingestion_scheduler.py:26-37`: both derive
  latest commit through `branch_heads` LATERAL/JOIN; with `branch_heads` unwritten the sentinel cannot reach
  `latest_commit`/the scheduler `commit_sha` — confirms the SGAP-001 exposure is limited to the two direct
  readers, and the MAWF/harness "latest commit" view is uncorrupted.
- Re-read `ingestion_scheduler.py:165-222`: bootstrap-on-null-branch → `create_job("ingestion")` confirmed;
  SGAP-002 mechanism 1 (`origin_url IS NULL` → filtered at line 31) and mechanism 2 (EXISTS non-sentinel
  revision) both correctly prevent enqueue.
- Post-edit new-gap scan: the SGAP-001 filter changes only the `LIMIT 1` selects; it introduces no new
  asymmetry (the note authoring path in `repo_note.py:66-74,169-174` intentionally selects the synthetic
  revision and is NOT filtered — correct, that is the producer/consumer the sentinel is FOR). The SGAP-002
  `origin_url=NULL` mechanism does not affect capture (capture never reads `origin_url`). No new gap.

---

## Cycle 2 Assessment (fresh full pass, no edits)

Re-ran every lens over the full addressed set against the edited plan.

| req_id | satisfied end-to-end? | key evidence |
| --- | --- | --- |
| A1 | YES | canonical key threaded to entity_key (`entity_key.py:30`, no case-fold) + Qdrant payload; retrieval filters same key (`retrieval.py:854`); upsert collapses casings on `(entity_id)` (`learned_memory_writer.py:54`) |
| A2 | YES (with required SGAP-001 filter + SGAP-002 mechanism) | synthetic revision satisfies NOT-NULLs (`entity_registrar.py:37`); direct latest-revision readers now filter sentinel; freshness scheduler excluded |
| A3 | YES | mirrors deployed `hydrate_corpus.py`; opt-in/fail-open; `repo_scoped_memory` slice present (`retrieval.py:875`) |
| A4 | YES | advisory skill; sequenced after A1/A2 deploy |
| A5 | YES | `MK_SPARK_REPOS` read from process env at spark import (`directive_spark.py:29`); `spark.OUT` exists (`:31`); export in `weekly-review.sh` |
| B1 | YES | `running→cancelled` guard; idempotent tool; `_save_ingestion_checkpoint` chokepoint covers all 8 ckpts; `execute_job` cancelled-guard (3 sites); inert to poll/sweep/reclaim/`get_active_job_for_shape`; harness treats cancelled correctly |
| B2 | YES | `started_utc` exists & not post-create-updated; DB-NOW predicate; `getattr` default 300 |
| B3 | YES | only `mawf_repository_id`+`status_id` NOT-NULL (`016:143-144`); `active` resolves via mawf_code (`mawf.py:159`); trigger satisfied; ON CONFLICT preserves MAWF columns |
| INV-1 | YES | write key == read key (canonical on both sides) |
| INV-2 | YES (after fix) | sentinel filtered from direct readers; invisible to branch_heads-keyed readers |
| INV-3 | YES | brain excludes cancelled everywhere; harness excludes it from recovery/active (one cosmetic poll delay, out of scope) |
| INV-4 | YES | full live NOT-NULL set satisfied; MAWF/harness readers compatible |
| INV-5 | YES (after fix) | notes-only repos kept out of autonomous ingestion via origin_url=NULL / enumeration filter; live scheduler config flagged for confirmation |

**No new blocker gaps found in Cycle 2.** Both SGAP entries closed by plan edits (locked contract + required
implementation steps). Remaining open items are non-blocking cleanups (CL-1/2/3, all addressed in plan text)
and ONE operational confirmation folded into a required step: verify the live `ingestion_scheduler_enabled`
value — this does not block the build (mechanism 1 `origin_url=NULL` makes the requirement hold regardless of
the scheduler state), so it is recorded as a required Phase-3 verification, not an open user-decision blocker.

## Final Convergence Check

- Fresh full pass (Cycle 2) over the addressed set: **0 open blockers.**
- Hard-stop rule satisfied: edits were made in Cycle 1; Cycle 2 is a separate no-edit pass and is the one
  declaring convergence.
- Every ledger/trace row carries `path:line` or schema/data evidence; producer AND consumer read for each
  boundary (Qdrant payload vs retrieval filter; sentinel producer vs all latest-revision consumers;
  cancelled producer vs dispatcher/sweep/reclaim/harness consumers; B3 INSERT vs live NOT-NULL set + MAWF
  readers).
- Unverifiable items explicitly marked: live `__note_anchor__`/note counts and live
  `ingestion_scheduler_enabled` value (the latter neutralized by mechanism 1, also a recorded Phase-3 check).

## Final Readiness Proof

| req_id | satisfied end-to-end? | evidence |
| --- | --- | --- |
| A1 | YES | trace row A1; `entity_key.py:30`, `retrieval.py:854`, `learned_memory_writer.py:54` |
| A2 | YES | trace row A2 + SGAP-001/002 required steps; `entity_registrar.py:37`, `freshness_audit.py:29-37`, `repair_drift.py:53-61`, `ingestion_scheduler.py:31,179-185` |
| A3 | YES | `retrieval.py:851-875`; `hydrate_corpus.py` parity |
| A4 | YES | skill copy; A1/A2 dependency sequenced |
| A5 | YES | `directive_spark.py:29,31`; `weekly_review.py:62-66` |
| B1 | YES | `state_transition_guard.py:5`, `manifest_writer.py:66-68`, `ingestion.py:165`, `job_worker.py:63-100`, `dispatcher.py:79,121-122`, `job_retry_manager.py:63,76`, `manifest_reader.py:125`; harness `mawf_recovery_scanner.py:18-23` |
| B2 | YES | `dispatcher.py:73-81`, `config.py:117`, `001` started_utc |
| B3 | YES | `server.py:6156-6169`, `admin/mawf.py:159,529-546`, `016:62,124-127,143-144,229` |

**CONVERGED — Cycle 2, 0 blockers.**
