# Implementation Plan — Ingestion Freshness + Maintenance Ops

**Status:** Awaiting approval. No code changes until each step is approved.
**Derived from:** [`docs/ARCHITECTURE_EVALUATION.md`](ARCHITECTURE_EVALUATION.md) §9 (discovery + resolved owner decisions).

> **Revision (rev 4) — final polish after a fourth self-assessment + code verification:**
> - **`max_per_tick` starvation:** the cap now bounds **enqueues** (not the cheap `ls-remote` checks); enumeration covers **all** in-scope repos **ordered stalest-first** (`ORDER BY bh.updated_utc ASC NULLS FIRST`) so no repo can starve. (A.1, A.3.1, A.3.4)
> - **Scheduler lifecycle:** explicit managed `start()`/`stop()` (cancel + drain the loop task), not the fire-and-forget `_track_task`. (A.4)
> - **Maintenance dedup:** `get_active_job_for_shape` skip before enqueuing audit/compaction. (B.2)
> - **Verified clean:** `create_job` stores `job_params`→`checkpoint_data` (`json.dumps`), the dispatcher loads it into `kwargs`, and `ingestion.run` accepts `checkpoint` — so `dry_run` and resume both flow correctly.
>
> **Revision (rev 3) — gaps closed after a third self-assessment + code verification:**
> - **Orphan-override double-enqueue (regression introduced in rev 2):** removed the age-based orphan override (no job heartbeat exists + `job_orphan_timeout=3600` → a >1h ingest would be re-enqueued while running). Replaced with **skip-if-any-active-shape-job**; crashed commits are superseded by the next commit. (A.3.3)
> - **Auth coverage (verified):** `github-app-config` confirmed to cover **both** orgs the repos span (`thebteambg`, `yourbteam`) + default fallback. Added **per-repo `try/except` isolation** so one repo's failure can't wedge the tick. (A.2, A.3)
> - **Neo4j-degraded under the dispatcher:** documented that the dispatcher passes a dead-but-non-`None` driver during an outage; compaction must classify Neo4j-unavailable as `skipped`, not `error`. (B.1)
> - **Precision:** exact `get_active_job_for_shape`/`create_job` signatures + positional order; gitpython `ls_remote` call (off-thread); `--symref` default-branch parse; corrected the `old_sha`-unreachable rationale; named the Prometheus registry. (A.2, A.3, A.5, A.6)
>
> **Revision (rev 2) — gaps closed after a self-assessment + code verification:**
> - **#1 double-run (critical):** enqueue is now `create_job(job_type="ingestion")` **only**; the `JobDispatcher` is the sole atomic executor (verified it claims `pending` via `FOR UPDATE SKIP LOCKED` and passes `commit_sha`/`branch_name` to `ingestion.run`). The direct `_run_ingestion_background` call is *not* used. (A.3, A.8)
> - **#2 stale-lock:** dedup via `get_active_job_for_shape` (per-commit `pending`/`running`); verified there is **no auto-reclaimer** (`job_retry_manager` only retries `failed`), so the scheduler treats a shape-active job older than `job_orphan_timeout_seconds` as orphaned and re-enqueues with resume checkpoint. (A.3)
> - **#3 token cadence:** verified non-issue — `get_authenticated_git_url` reuses a cached `GitHubAppAuth` singleton. (A.2)
> - **#4 force-push/non-ancestor diff:** explicit full-reingest fallback in `_determine_diff_files`. (A.5)
> - **#5 B-config / #6 compaction→WorkflowResult adapter / #7 enumeration SQL + bootstrap / #8 maintenance load bound / #9 metric / #11 enqueue-contract test:** all now specified (A.1, B.1, A.3, B.2, A.6, A.8).

## Decisions driving this plan (all resolved)
- Posture: the 3-store engine is **infrastructure for MAWF** → *right-size, don't invest* in code-retrieval-specific extras.
- Ingestion was **always hand-run; no scheduler exists** → build freshness automation from scratch.
- Freshness target: **hourly / near-real-time**. Scope: **all registered real repos** (those with an `origin_url`).
- Neo4j is **safely optional** (verified: MAWF/triage/intake/planning have zero Neo4j dependency).

**Two active workstreams (A, B); three shelve/right-size decisions (C).**

---

## Workstream A — Ingestion freshness automation

**Design:** an in-app periodic **`IngestionScheduler`** background task (same pattern as the existing `JobDispatcher`/`CodexTokenManager`). Each tick it cheaply checks each in-scope repo's **remote HEAD** and, only when it changed, enqueues an **incremental** ingestion. This reuses all existing ingestion/job machinery and needs no external infra (the B3 plan runs a single instance → exactly one scheduler, no contention). Hourly poll + change-detection ≈ near-real-time without webhook infrastructure (webhooks noted as a later upgrade for true real-time).

**Why poll-on-change, not just "trigger hourly":** `run_repo_ingestion_workflow` takes an explicit `commit_sha`, and `_determine_diff_files` treats `old_sha == commit_sha` as a **full** re-ingest. So blindly triggering would force expensive full re-ingests of unchanged repos. Resolving remote HEAD first and skipping when unchanged avoids that.

### A.1 — Config (ingestion + maintenance)
**File:** [`config.py`](../src/memory_knowledge/config.py)
- `ingestion_scheduler_enabled: bool = False`
- `ingestion_scheduler_interval_seconds: int = 3600`
- `ingestion_scheduler_repo_allowlist: str = ""` (CSV; empty = all repos with `origin_url`, excluding test-prefixed `mawf-*`/`repo-*`/`idx-*`)
- `ingestion_scheduler_max_per_tick: int = 5` (bounds the number of **enqueues** per tick on the shared B3 — *not* the cheap `ls-remote` checks, which run for every in-scope repo)
- *(used by Workstream B)* `maintenance_scheduler_enabled: bool = False`; `maintenance_interval_seconds: int = 604800` (weekly). `compaction_enabled` already exists.

### A.2 — Lightweight remote-HEAD resolver  *(closes gaps #3, auth-coverage)*
**File:** [`git/clone.py`](../src/memory_knowledge/git/clone.py) (new helpers, async — run blocking git off-thread)
- `resolve_remote_head(origin_url, branch, settings) -> str | None`: `authed = await get_authenticated_git_url(origin_url, settings)`; then `out = await asyncio.to_thread(git.cmd.Git().ls_remote, authed, f"refs/heads/{branch}")`; the sha is the first whitespace-token of the first line (or `None` if empty/branch-missing).
- `resolve_default_branch(origin_url, settings) -> tuple[str, str] | None`: `git.cmd.Git().ls_remote("--symref", authed, "HEAD")` → parse the `ref: refs/heads/<branch>\tHEAD` line for the branch + the `HEAD` sha. Bootstrap only (A.3).
- **Auth (verified, both orgs covered): no per-tick token minting.** `get_authenticated_git_url` resolves per-org from the cached `GitHubAppAuth` registry; the `github-app-config` is confirmed to include **both** `thebteambg` *and* `yourbteam` (the two orgs the real repos span) plus a default fallback, and the installation token is cached until ~5 min before expiry. So `ls-remote` is authenticated for every in-scope repo and reuses the cached token.

### A.3 — Scheduler (provably single-run enqueue)  *(closes gaps #1, #2, #7; rev-3 fixes the orphan double-enqueue)*
**New file:** `jobs/ingestion_scheduler.py` — `IngestionScheduler` (mirrors `CodexTokenManager`). `start(pool, settings)` loops sleeping `interval_seconds`. **Each repo is processed in its own `try/except` → log + continue** (one repo's auth/network/DB failure must not abort the tick or wedge the loop). Each tick:
1. **Enumerate ALL in-scope repos, stalest first** (no enumeration cap — `ls-remote` is cheap; the cap is applied to enqueues in step 4 so no repo can starve):
   ```sql
   SELECT r.repository_key, r.origin_url, bh.branch_name, bh.commit_sha, bh.updated_utc
   FROM catalog.repositories r
   LEFT JOIN catalog.branch_heads bh ON bh.repository_id = r.id
   WHERE r.origin_url IS NOT NULL
     AND r.repository_key NOT LIKE 'mawf%' AND r.repository_key NOT LIKE 'repo-%'
     AND r.repository_key NOT LIKE 'idx-%'
     AND ($allowlist = '{}' OR r.repository_key = ANY($allowlist))
   ORDER BY bh.updated_utc ASC NULLS FIRST   -- never-ingested + stalest repos first
   ```
   (Current data: each real repo has exactly **1** `branch_head`, on its own tracked branch — `main`/`master`/`prod`/`versionUpgradeDevelopment` — so use the stored `branch_name`, never `HEAD`.)
2. **Resolve target commit:**
   - **Bootstrap** (`branch_name IS NULL`, e.g. a freshly `register_repository`'d repo): `(branch, remote) = resolve_default_branch(...)`; this will be a `full` ingest (no `old_sha`).
   - **Normal:** `remote = resolve_remote_head(origin_url, branch_name)`. If `remote is None` or `remote == commit_sha` → **skip** (`log: skipped_unchanged`). Else `commit = remote` (ingestion resolves `old_sha` from `branch_heads` → incremental diff).
3. **Dedup — skip if any active shape-job exists** (rev-3: no orphan-age override). `active = await manifest_reader.get_active_job_for_shape(pool, repository_key=repository_key, commit_sha=commit, branch_name=branch, tool_name="run_repo_ingestion_workflow")` (returns newest `pending`/`running` job for that exact shape). If `active is not None` → **skip** (`log: skip_in_progress`); else proceed.
   - **Why not an orphan-age override (the rev-2 mistake):** there is **no job heartbeat** and `job_orphan_timeout_seconds=3600`, so a legitimately long (>1h) full ingest still `running` would be mis-flagged orphaned and **re-enqueued while running → two jobs for the same commit.** Skip-if-active removes that risk entirely. A crashed job's commit simply stays un-ingested only **until the next commit supersedes it** (a new commit = a new shape → enqueues fresh) — acceptable for a freshness scheduler. The rare "crashed + no new commit ever" case is handled by the manual `run_repo_ingestion_workflow` tool (which already resumes from checkpoint). *(Optional hardening, separate config-gated step: a low-frequency sweep that marks shape-jobs older than a generous `ingestion_stale_seconds`, e.g. 6h, as `failed` so they stop deduping — not in the critical path.)*
4. **Enqueue (single-run):** `resume = await get_latest_resume_checkpoint(pool, repository_key=…, commit_sha=commit, branch_name=branch, tool_name="run_repo_ingestion_workflow")`; then
   `await create_job(pool, new_run_id(), "ingestion", "run_repo_ingestion_workflow", repository_key, commit, branch, job_params={"checkpoint": resume} if resume else None)`
   (positional order = `pool, run_id, job_type, tool_name, repository_key, commit_sha, branch_name`; `correlation_id` left default; `job_params` keyword). **Do NOT call `_run_ingestion_background`.** The `JobDispatcher` is the sole executor — it atomically claims `pending` jobs (`SELECT … FOR UPDATE SKIP LOCKED → 'running'`) and passes `commit_sha`/`branch_name` from the manifest to `ingestion.run` (verified [`dispatcher.py:104`](../src/memory_knowledge/jobs/dispatcher.py:104)). → exactly-once.
   - **Enqueue cap:** keep a per-tick counter; once `max_per_tick` enqueues have happened, stop enqueuing for this tick (continue cheap `ls-remote` checks is unnecessary — break). Because step 1 orders **stalest-first**, the un-enqueued repos are first next tick → no starvation, load on the shared B3 stays bounded.

Structured logs per outcome; per-repo errors are isolated (A.3 intro); the loop never throws.

### A.4 — Wire into lifespan
**File:** [`server.py`](../src/memory_knowledge/server.py) `app_lifespan` — give `IngestionScheduler` an explicit `start()`/`stop()` (mirroring `JobDispatcher`/`CodexTokenManager`: the loop runs in an `asyncio.Task` held on the instance; `stop()` cancels it and awaits drain). Start it **after** the `JobDispatcher` (so a dispatcher exists to run enqueued jobs), guarded by `ingestion_scheduler_enabled`; call `stop()` in the lifespan teardown. (Not the fire-and-forget `_track_task` helper — a long-running loop needs managed cancellation.)

### A.5 — Unreachable-`old_sha` fallback  *(closes gap #4)*
**File:** [`workflows/ingestion.py`](../src/memory_knowledge/workflows/ingestion.py) `_determine_diff_files` — wrap the `changed_files(repo, old_sha, commit_sha)` call in `try/except`; the real failure mode is **`old_sha` no longer reachable** (GC'd after a force-push/rebase → gitpython `repo.commit(old_sha)` raises `BadName`/`ValueError`; note plain non-ancestors still `diff` fine). On any such error, log `incremental_diff_failed` and **return `None` → fall back to a full re-ingest**. (Also hardens manual ingestion.)

### A.6 — Observability  *(closes gap #9)*
- Add a Prometheus gauge `repo_surface_age_seconds{repository_key}` registered on the **existing app metrics registry** (`prometheus-client` is already a dep; reuse the same registry the server exposes on `/metrics`), updated per tick — so the freshness SLA is measurable, not just logged.

### A.7 — Prod enablement + verification
- App settings: `INGESTION_SCHEDULER_ENABLED=true`, `INGESTION_SCHEDULER_INTERVAL_SECONDS=3600`.
- Verify: push to one in-scope repo → within an interval an **incremental** `ingestion_run` appears and completes (exactly one job per change — assert no duplicate manifest); unchanged repos log `skipped_unchanged` (no full re-ingest); `retrieval_surfaces.updated_utc` advances; the gauge drops.
- **Success metric:** every in-scope repo's surface age stays < interval after a push; zero unintended full re-ingests; one job per change.

### A.8 — Tests  *(closes gap #11)*
- `resolve_remote_head` / `resolve_default_branch` parsing (mock `git ls-remote` output incl. `--symref`).
- Scheduler tick with a fake pool + stubbed `get_active_job_for_shape`: enqueues only on sha change; **skips** whenever a shape-job is active (rev-3: no age override); **bootstraps** a null-branch repo; respects allowlist, test-prefix exclusion, and `max_per_tick`; **one repo raising does not abort the tick** (per-repo isolation).
- Enqueue contract: assert the scheduler calls `create_job` **exactly once** and does **not** call `_run_ingestion_background` (guards against the double-run regression).

---

## Workstream B — Operationalize maintenance (keep the infra healthy/bounded)

The `is_active`/compaction/audit machinery we built must run on a schedule, not as one-off scripts.

### B.1 — Expose compaction as a tool  *(closes gap #6; rev-3: Neo4j-degraded handling)*
**Files:** new `workflows/compaction.py` + register + tool in [`server.py`](../src/memory_knowledge/server.py)
- `compact_repository` returns a `CompactionReport`, but the job/execute_job pattern expects `run(...) -> WorkflowResult`. Add the adapter:
  ```python
  # workflows/compaction.py
  async def run(repository_key, run_id, pool=None, qdrant_client=None,
                neo4j_driver=None, settings=None, dry_run=True) -> WorkflowResult:
      report = await compact_repository(pool, qdrant_client, neo4j_driver, settings,
                                        repository_key, dry_run=dry_run)
      status = "error" if report.errors else "success"
      return WorkflowResult(run_id=str(run_id), tool_name="run_compaction_workflow",
                            status=status, data=report.model_dump(),
                            error="; ".join(report.errors) or None)
  ```
- **Neo4j-degraded handling (rev-3):** the `JobDispatcher` injects `get_neo4j_driver()` (the *raising* variant), so during a Neo4j outage the dispatcher passes a **non-`None` but dead** driver object (verified: `init_neo4j` assigns `_driver` *before* `verify_connectivity`, so it stays set). To avoid that turning a healthy PG/Qdrant compaction into a failed job, **`compact_repository`'s Neo4j block must classify a connectivity failure as `skipped` (e.g. `report.skipped.append("neo4j (unavailable)")`), not `errors`** — so `status` stays `success` when only Neo4j is down. (Small change to the existing `except` in `integrity/compaction.py`: distinguish `neo4j.exceptions.ServiceUnavailable`/timeout → skip, vs. real Cypher errors → error.)
- `register_job_type("compaction", _compaction.run)` in lifespan.
- MCP tool `run_compaction_workflow(repository_key, dry_run=True)` mirroring `run_repair_rebuild_workflow`: `check_remote_write_guard(..., is_destructive=True)`; `create_job(pool, run_id, "compaction", "run_compaction_workflow", repository_key, job_params={"dry_run": dry_run})`. The dispatcher does `kwargs.update(params)` from `checkpoint_data`, so `dry_run` flows into `run()` (verified [`dispatcher.py:131`](../src/memory_knowledge/jobs/dispatcher.py:131)). Defaults `dry_run=True`.

### B.2 — Scheduled maintenance  *(closes gap #8)*
**File:** new `jobs/maintenance_scheduler.py`
- Low-frequency loop (`maintenance_interval_seconds`, default weekly), gated `maintenance_scheduler_enabled`.
- Per cycle, for **real repos only** (same `origin_url` + test-prefix exclusion as A.3): **enqueue** an `integrity_audit` job and a `compaction` job (`dry_run = not compaction_enabled`) via `create_job` — *enqueue, don't run inline*. Load is then **bounded by the dispatcher's `max_concurrent=3`** automatically (audit scrolls Qdrant, so this matters); no manual batching needed.
- **Dedup (rev-4):** before enqueuing each, check `get_active_job_for_shape(... tool_name="run_integrity_audit_workflow" | "run_compaction_workflow" ...)` and skip if one is already pending/running — so a slow cycle can't pile duplicate maintenance jobs (also lets `integrity_audit` register a job type if not already). At weekly cadence this is belt-and-suspenders, but cheap.
- Emits audit findings + compaction counts as `warning`-level structured logs (alert hook; real routing out of scope).

### B.3 — Prod enablement + verification
- Settings: `MAINTENANCE_SCHEDULER_ENABLED=true`; keep `COMPACTION_ENABLED=false` initially (dry-run reports only) until the reports look right, then flip on.
- Verify: a maintenance cycle logs audit + compaction-dry-run counts; flipping `COMPACTION_ENABLED=true` prunes on schedule; `/ready` unaffected.

---

## Workstream C — Shelve / right-size (decisions, minimal code)

Per the "MAWF-infrastructure" posture, these are **explicit non-investments**, recorded so they're intentional, not neglect:

- **C.1 Code-knowledge memory layer (`learned_records`) → SHELVE.** 0 rows ever; not the product. Action: document it as parked (a `docs/` note + a comment on the propose/commit tools), do **not** delete (cheap to keep dormant; removal risk > reward). Revisit only if a MAWF use-case needs code-rules.
- **C.2 Neo4j → keep optional, no promotion.** Already degraded-tolerant and MAWF-independent. Action: none now; optionally make `integrity_audit`/`repair_rebuild` graph-optional later so they don't hard-fail without Neo4j. Full removal deferred (would only drop `impact_analysis`, 1.7%).
- **C.3 Human feedback (`submit_route_feedback`) → deprioritize.** Tool exists; router self-tuning is low value for infra. Action: none.

---

## Sequencing, risk, rollback
1. **B.1 first** (expose compaction tool) — small, unlocks B.2.
2. **A (ingestion scheduler)** — the highest-value workstream; ship `enabled=false`, verify on one repo, then enable.
3. **B.2 (maintenance scheduler)** — ship `enabled=false` + dry-run, verify reports, then enable.
4. **C** — documentation/decisions, no deploy of its own.

- **Risk — shared B3 load:** bounded by `max_per_tick` + incremental-only + single instance; monitor plan memory/CPU after enabling (we have the metric path).
- **Risk — runaway / double ingestion:** change-detection (skip unchanged) + `get_active_job_for_shape` dedup + single-executor enqueue (dispatcher only) prevent loops and double-runs; the orphan-age override prevents permanent stuck-on-crash. `enabled` flags are the kill switch (app setting, no redeploy).
- **Rollback:** set `*_SCHEDULER_ENABLED=false` (app setting) to halt instantly; no data migration involved.

## Open inputs (none blocking the build)
- True real-time (webhooks) vs hourly poll: plan ships hourly poll; webhook upgrade is additive later if needed.
- Alert routing for B.2 findings: logged now; wire to a real channel when one is chosen.
