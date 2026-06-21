# Research — Automation schedule for the second-brain upkeep (no manual triggers)

**Mode:** Research (findings only; no code shipped). Created 2026-06-21. Owner: memory-knowledge.
**Goal:** run the brain's recurring upkeep on a **reliable, machine-independent schedule** — no manual
triggers, no dependence on a single laptop being awake — given Kamen works across home/office machines,
the shared single-worker Azure infra, and the freshness-scheduler auto-ingest risk (the prior incident).
**Next:** this is build-bound → harden via the 3 gates (doc-gap → coverage → satisfaction) before a plan.

> R1: every claim is grounded in `path:line` / config. Inferences marked **[inf]**. No invented names.
> Path convention: runtime cites (`config.py`, `server.py`, `jobs/...`, `workflows/...`) are relative to
> `src/memory_knowledge/`; repo-root files (`Dockerfile`, `.github/workflows/ci.yml`, `working-agreement/...`,
> `.git/hooks/...`) are cited from the repo root.

---

## 1. The recurring upkeep tasks (what must run, and how it's triggered today)

| Task | What it does | Trigger today | Execution locus |
| --- | --- | --- | --- |
| **Integrity audit + compaction** | per-repo data integrity + consolidation | manual, or the local weekly review (never run) | **server-capable** — `MaintenanceScheduler` enqueues `integrity_audit`+`compaction` via the dispatcher (`jobs/maintenance_scheduler.py:77-90`) |
| **Freshness re-ingest** | re-ingest changed repos | manual | **server** — `IngestionScheduler` enqueues an **incremental** ingest only when remote HEAD changed, skipping unchanged repos (`jobs/ingestion_scheduler.py:3-4`); bootstrap = full ingest only for never-ingested repos (`jobs/ingestion_scheduler.py:188`). **RISK: auto-ingest scope** — enabling it auto-ingests any `origin_url` repo not on the allowlist (the incident class) |
| **Directive Spark** | mine brain telemetry → `spark-candidates.md` | local weekly review only (`weekly_review.py:59-68`); never run | **repo-git** — writes a file in the repo working tree |
| **AGENTS.md refresh** | regenerate Codex projections across trusted repos | local weekly review only (`weekly_review.py:92-104`) | **repo-git + cross-repo** — needs each repo's local checkout |
| **`DIRECTIVES.md` "Last reviewed" stamp + commit** | bump + commit so the post-commit sync mirrors to corpus | local weekly review only | **repo-git** — needs a checkout + `git commit` |
| **Corpus sync (DIRECTIVES→corpus)** | mirror directive edits into Tier-2 corpus | **already automated**: git post-commit hook on `DIRECTIVES.md` (`.git/hooks/post-commit`) | repo-git, **event-driven** (fine) |
| **Auto-capture (#2)** | session-close lessons → candidate notes | **event hook** (`Stop` hook), not a schedule | client-side; out of scope for "scheduling" |

---

## 2. Core finding: the work splits into two loci, and only one can run server-side

**Server, always-on (Azure container).** Anything operating on the brain's DB/stores can be enqueued by
the in-process schedulers and run by the dispatcher — machine-independent, runs whether any laptop is on.
Two schedulers already exist but are **disabled by default**:
- `maintenance_scheduler_enabled = False` (`config.py:100`), `maintenance_interval_seconds = 604800` (weekly, `config.py:101`).
- `ingestion_scheduler_enabled = False` (`config.py:92`).
They are wired at startup (`server.py:6655-6669`) — flip the flag (app setting) and they run.

**Repo-git, CANNOT run server-side.** The Azure image copies only `src/`, `alembic.ini`,
`docker/entrypoint.sh`, `migrations/`, and `docker/certs/` (`Dockerfile:25-29`) — **no `working-agreement/`,
no `DIRECTIVES.md`, no git checkout** (the working tree is never copied). So
Spark, AGENTS.md refresh, and the stamp+commit **physically cannot run in the container**. They need a
git-capable runner.

**Implication:** "schedule the weekly review on the server" is impossible as-is for the repo-git half. The
schedule must be split: server-side for data maintenance, a git-capable runner for the repo-git tasks.

---

## 3. Scheduling mechanisms available (and multi-machine reliability)

| Mechanism | Always-on / machine-independent? | Git-capable? | Fit |
| --- | --- | --- | --- |
| **In-server `MaintenanceScheduler`** (exists, disabled) | ✅ Azure always-on | ❌ (operates on stored data, not the repo) | **Data maintenance** (integrity+compaction) |
| **In-server `IngestionScheduler`** (exists, disabled) | ✅ | ❌ | **Freshness** — but auto-ingest risk; needs a decision/guard |
| **GitHub Actions scheduled (`cron`)** — repo already has `.github/workflows/ci.yml` | ✅ GitHub infra, machine-independent | ✅ checkout + commit + push | **Repo-git half** (Spark + stamp); needs secrets for brain calls |
| **launchd plist** (current `#7`, loaded) | ❌ single laptop; doesn't run if asleep/off | ✅ | **Reject as primary** for a multi-machine user; optional local fallback only |

The current `#7` automation is **launchd only** — which is exactly the multi-machine reliability gap: it
runs on one laptop, only when that laptop is awake. (It has also never actually run — no
`/tmp/mk-weekly-review.log`, stamp still `2026-06-19`.)

---

## 4. Recommended schedule (per task → locus → cadence → guard)

1. **Integrity audit + compaction → enable the in-server `MaintenanceScheduler`** (`maintenance_scheduler_enabled=1`
   app setting). Server-side, weekly. **Two flags, not one:** with `compaction_enabled=False` (`config.py:88`)
   the scheduler computes `dry_run = not compaction_enabled` (`jobs/maintenance_scheduler.py:71`), so compaction
   is enqueued **dry-run only** — integrity audits run but no consolidation is written. To get real compaction,
   also set `compaction_enabled=1`. **Decision:** confirm whether the first rollout enables real compaction or
   stays dry-run for one cycle. The dispatcher serializes (`job_dispatcher_max_concurrent=1`, `config.py:114`) so it
   won't stampede the shared B3 worker; `_enqueue_if_absent` (`jobs/maintenance_scheduler.py:83-89`) avoids duplicate
   jobs. **Enqueue volume (CGAP-005):** the maintenance scheduler has **no `max_per_tick` cap** — it enqueues
   `integrity_audit` + `compaction` for **every** real repo each tick (`maintenance_scheduler.py:72-78`), unlike the
   ingestion scheduler which is bounded (`ingestion_scheduler_max_per_tick`, `config.py:97`). With ~8 real repos that
   is up to 16 jobs queued at once; they don't run concurrently (serialized) but they queue up and contend for the
   single B3 worker over the hours after a tick. Contention is bounded by **serialization + per-repo dedup**, not by
   an enqueue cap; this is acceptable at the current repo count but should be revisited if the real-repo set grows
   large. **Acceptance criterion:** a weekly tick enqueues at most `2 × (real-repo count)` jobs, never duplicates an
   already pending/running tool for a repo (`_ACTIVE_BY_TOOL_SQL`), and the worker drains the backlog before the next
   tick. **Off-peak timing (CGAP-001 / R-INTEG.O4):** maintenance cadence is a pure interval loop with **no
   wall-clock anchor** — `_loop` waits `timeout=interval` (`maintenance_scheduler.py:58-68`); a `daily_at` control
   exists **only** for ingestion (`config.py:94`). So "off-peak" is **not directly schedulable** for maintenance.
   **Mechanism:** control the tick phase by the **deploy/restart time** (the first tick fires `interval` seconds after
   startup, so restart the container at an off-peak hour to anchor the weekly tick there), or accept any-hour ticking
   since serialization already prevents a worker stampede. **Decision (for the plan):** either treat off-peak as
   best-effort-via-restart-time, or scope it out as unnecessary given serialization. **Acceptance criterion:** the
   `maintenance_scheduler_tick_complete` log timestamp falls in the intended off-peak window (if pursued), else the
   doc records off-peak as explicitly out-of-scope with the serialization rationale.
   **Shared dispatcher with the workflow-orch harness (SGAP-001 / INV-DISPATCH-COTENANT — interop).** The brain's
   job dispatcher (`ops.job_manifests`, single serialized worker `job_dispatcher_max_concurrent=1`) is **shared with
   the `workflow-orch-app` harness**, a co-tenant MCP client of the *same* deployed brain. The harness enqueues
   `run_repo_ingestion_workflow` jobs into the **same** `ops.job_manifests` table — the brain's MCP handler does
   `create_job` (`server.py:663-708`) — on every `workflow.push` (harness `src/workflow_orch/mcp_server.py:8527`;
   the harness push poll is fire-and-forget, ~0.6s, so harness operations do not *hang*, but the enqueued ingestion
   waits behind the worker). Two consequences the single-tenant framing missed: **(a)** maintenance enqueues
   `2 × real-repo count` jobs that drain over the hours after a tick and **contend with harness ingestion on the one
   worker** — serialization + per-repo dedup bound *queue correctness*, **not latency**, so a maintenance backlog can
   delay the harness's post-push memory freshness; **(b)** the maintenance enumeration prefixes
   (`NOT LIKE 'mawf%'/'repo-%'/'idx-%'`, `maintenance_scheduler.py:19-25`) do **not** exclude harness-registered real
   repos (e.g. `mcp-agents-workflow`, `org/repo`-style keys), so the real-repo count is **≥** the brain-only ~8 and
   those repos receive integrity+compaction too. **Disposition:** acceptable at current scale, but the off-peak
   anchor (restart-time) should be chosen to keep the weekly backlog **out of the harness's active working hours**,
   not merely "any hour." **Acceptance criterion:** a weekly tick's backlog drains before it materially delays harness
   ingestion latency (observe `maintenance_scheduler_tick_complete` backlog vs harness `run_repo_ingestion_workflow`
   queue age), or off-peak anchoring keeps the backlog outside harness working hours.
   **Live app-settings are operator/deploy-time facts (SGAP-005, unverifiable from repo).** Enabling this scheduler
   requires `maintenance_scheduler_enabled=1` (and `compaction_enabled=1` for real compaction) on the **deployed Azure
   app settings** (`server.py:6665-6669`; defaults `False`, `config.py:88,100`). These are required implementation
   steps; their live values cannot be confirmed from the repo.
2. **Spark + `DIRECTIVES` stamp → GitHub Actions scheduled workflow (weekly cron)** in the memory-knowledge
   repo. Machine-independent, commits `spark-candidates.md` + the stamp bump. Needs `CLAUDE_CORPUS_MCP_URL` as a
   **GitHub Actions secret** (no secrets in the repo — Guard Rail). **No MCP auth token is required** — see the
   R-AUTH resolution below (SGAP-002): the brain's `/mcp` endpoint is unauthenticated by design, so the CI job calls
   it with the URL alone, exactly as the existing local hook does.
   - **MCP auth for CI — RESOLVED from the repo (SGAP-002).** The earlier "needs any MCP auth token" caveat is
     **withdrawn**. The brain's `ApiKeyAuthMiddleware` lists `/mcp` (and `/.well-known/`) in `_PUBLIC_PREFIXES` and
     returns `call_next` *before* the `mcp_api_key` check (`src/memory_knowledge/middleware/auth.py:16,24,29`,
     comment "MCP auth is open"), so MCP calls are accepted without an `Authorization` header. Every existing client
     already relies on this (`sync_corpus.py:77`, `directive_spark.py:109`, `weekly_review.py:84` call
     `streamable_http_client(URL)` with no header) and the live local corpus hook works today. **The CI Spark/stamp
     job therefore needs only `CLAUDE_CORPUS_MCP_URL`.** Residual risk: if a future deployment fronts `/mcp` with an
     auth gateway, re-introduce a token secret then — but that is not the current state.
   - **Corpus sync from a CI commit (CGAP-002).** The directive→corpus mirror runs from the **local** git
     `post-commit` hook (`.git/hooks/post-commit` → `working-agreement/sync-corpus.sh`); a commit pushed by
     GitHub Actions runs on GitHub's servers and **does not fire that local hook**, so a naive "let the stamp
     commit trigger the existing sync" would silently never update the corpus. **Mechanism:** the CI workflow must
     call the corpus mirror itself as an explicit step — run `working-agreement/sync_corpus.py` (the same helper the
     hook invokes) after committing the stamp, using the `CLAUDE_CORPUS_MCP_URL` secret. **Acceptance criterion:**
     after a CI run that bumps the stamp, `corpus_query` for the changed directive returns the new text (or the CI
     step logs the upsert/deactivate counts); the corpus is not left mirroring the pre-CI directive state.
     **Write-guard precondition + fail-loud (SGAP-003 / INV-CORPUS-WRITEGUARD).** `run_corpus_upsert_workflow` and
     `corpus_deactivate` are gated by `check_remote_write_guard` (`server.py:409,444` → `guards.py:26-38`): on the
     remote-DB Azure brain they return `status:"error"` unless `allow_remote_writes=true` (`config.py:137`, default
     `False`). So the CI sync silently mirrors nothing if that app setting is off. Two requirements: **(1)** the
     deployed brain must have `allow_remote_writes=true` — this is the **same** setting the existing local post-commit
     sync already depends on, so it is **implied already true** today (the live hook successfully mirrors), but its
     actual live value is unverifiable from the repo and must be confirmed in the plan; **(2)** the CI step must
     **propagate `sync_corpus.py`'s non-zero exit** — `sync_corpus.py` checks `status == "success"` and returns a
     failure count (`sync_corpus.py:104-110`), so a guarded/failed upsert is *not* silently green provided the
     workflow does not swallow the exit (ties to CGAP-008).
   - **Commit ownership / no double-writer (CGAP-006).** The GitHub Actions cron is the **single writer** of
     `spark-candidates.md` and the `Last reviewed` stamp. launchd must **not** also commit these (see §4.5 — its
     consolidation+commit step is disabled when retired). If a local launchd fallback is ever re-enabled, it runs in
     **dry-run/no-commit** mode only; the CI cron remains the sole committer. **Acceptance criterion:** `git log`
     shows stamp/spark commits authored only by the CI bot identity, never duplicated by a local run in the same week.
   - **Concurrent DIRECTIVES edit during a CI run (CGAP-011).** A human DIRECTIVES commit can land between the CI
     job's checkout and its push. **Mechanism:** the CI job rebases (`git pull --rebase`) before pushing and, on
     push rejection, re-runs the bump on the new HEAD and retries (bounded retries); the stamp bump is idempotent
     (`bump_review_stamp`, `weekly_review.py:29-31`, `count=1`) so a re-apply is safe. **Acceptance criterion:** a
     CI run whose push initially races a human commit still lands the stamp without a merge conflict marker and
     without clobbering the human edit (verify: both commits present in history after the run).
3. **AGENTS.md refresh → make it event-driven on DIRECTIVES change, not a weekly schedule.** Rationale: it's
   only needed when `DIRECTIVES.md` actually changes (Claude already gets live injection; Codex is the only
   consumer of the projection). **Mechanism (grounded):** `generate_projections.refresh_trusted(...)`
   (`working-agreement/generate_projections.py:127-143`) iterates the **local** Codex trusted-project list read from
   `~/.codex/config.toml` (`generate_projections.py:115-126`) and rewrites each project's generated `AGENTS.md`
   **in its local working tree**. It does not commit or push those files, and `weekly-review.sh` commits only
   `DIRECTIVES.md` + `spark-candidates.md` — so the refresh is inherently a **local, per-machine** action, not a
   server- or CI-runnable one. A CI runner has no checkout of the other trusted repos and no Codex config, so it
   **cannot** refresh them. **Recommended locus:** keep AGENTS refresh as a **local hook fired on DIRECTIVES change
   on whichever machine made the edit** (the same machine that runs the commit that triggers corpus sync), refreshing
   only that machine's checked-out trusted projects. **Scoped-out (with rationale):** AGENTS.md in trusted repos
   **not** checked out on the editing machine is left stale until that machine next opens them or the user edits them;
   this is low-harm because the live DIRECTIVES injection (Claude) is unaffected and Codex re-reads AGENTS.md per
   session — staleness only affects a Codex session opened on a machine whose AGENTS.md predates the latest DIRECTIVES
   edit, bounded to the gap until that machine's next DIRECTIVES change. **Acceptance criterion:** after a DIRECTIVES
   edit on machine M, every generated `AGENTS.md` under M's `~/.codex/config.toml` trusted projects shows the new
   directive content (verify with `generate_projections.py --refresh-trusted` returning `refreshed:` lines and no
   `skip(not-generated)` on intended files). *(Locus choice remains an open decision — see §6.)*
4. **Freshness re-ingest → keep DISABLED for now** (recommended). It is the auto-ingest path that caused the
   incident; the A2/SGAP-002 guard excludes notes-only repos (`jobs/ingestion_scheduler.py:36`), and changed
   repos get an *incremental* (not full) ingest. The residual risk is **scope**: with an empty allowlist it
   would auto-ingest *every* `origin_url` repo whose HEAD moves — including ones you never intended to track —
   plus a one-time full bootstrap ingest for any never-ingested repo (`jobs/ingestion_scheduler.py:188`). Keep
   manual/explicit; revisit later with a strict `ingestion_scheduler_repo_allowlist` (`config.py:96`) of only
   repos you *want* auto-refreshed. **Scope note (R-NOMANUAL.O2):** freshness is the **one upkeep task
   deliberately left non-automated** — this is an explicit, incident-driven exception to the "no manual triggers"
   goal, not a silent gap. **Acceptance criterion:** `ingestion_scheduler_enabled` stays `False` until a strict
   allowlist is chosen; re-enablement is itself a separate decision (§6.1), so the manual state is the intended
   end-state for this rollout.
5. **Retire launchd as the primary**; optionally keep the plist as a local fallback, but it is not the
   machine-independent answer.
   - **Re-homing checklist before retirement (CGAP-012 / R-RETIRE.O2).** launchd today uniquely runs five things
     (`weekly_review.py`): (a) Spark → now GH cron §4.2; (b) integrity+compaction → now server scheduler §4.1;
     (c) DIRECTIVES stamp+commit → now GH cron §4.2; (d) AGENTS refresh → now local-on-edit hook §4.3; (e)
     surfacing spark candidates to the user → see CGAP-004 below. No task may remain **launchd-only** after
     retirement. **Acceptance criterion:** with the plist unloaded (`launchctl unload`), each of (a)–(e) still has a
     live non-launchd trigger; a dry-run of each confirms it fires.
   - **Required runtime step — the plist is currently LOADED but has never fired (SGAP-004).** Live state at audit
     time: `launchctl list | grep memory` returns `com.kamen.memory-weekly-review` (the agent is **loaded** on this
     machine, scheduled Mon 09:00 local per the plist `StartCalendarInterval`), yet it has **never run** — no
     `/tmp/mk-weekly-review.log` and the `DIRECTIVES.md` stamp is still `2026-06-19`. The single-committer /
     no-duplication / no-dead-cadence guarantees of this whole section hold **only once the plist is actually
     unloaded**, which has not happened. **Required implementation step (runtime, not a code change):** run
     `launchctl unload ~/Library/LaunchAgents/com.kamen.memory-weekly-review.plist` on **every** machine where it is
     loaded, then verify `launchctl list | grep memory` returns empty. Until then, retirement is on paper only.
   - **Surfacing Spark candidates once launchd is gone (CGAP-004 / R-SPARK.O3).** Today candidate lines are printed
     to stderr → the launchd log (`weekly_review.py:67-78`), which Kamen could read on the laptop. On GitHub Actions
     that stderr goes only into the Actions run log (not surfaced). **Mechanism:** the CI Spark workflow writes the
     candidate summary to the **GitHub Actions job summary** (`$GITHUB_STEP_SUMMARY`) and, when there are
     candidates, opens/updates a tracking GitHub issue (or sends the existing notification channel) so Kamen is
     actively told. **Acceptance criterion:** a CI run that produces N≥1 candidates results in a visible notification
     (job-summary line + issue/notification), not just a buried log line; a zero-candidate run produces no noise.
   - **Multi-machine duplication if launchd is kept (CGAP-003 / R-MULTIMACHINE.O2).** Kamen runs two laptops
     (home/office). A launchd "fallback" loaded on **both** would fire the weekly job on each, and together with the
     GH cron that is up to three weekly runs → duplicate `spark-candidates.md`/stamp commits, duplicate AGENTS
     writes, and redundant maintenance enqueues (server-deduped, but git side is not). **Decision/scope:** the
     **recommended** end-state is **launchd fully retired** (plist unloaded on every machine); the GH cron is the
     sole git-side trigger. If a local fallback is retained at all, it is allowed on **at most one** machine and runs
     **no-commit/dry-run** (per CGAP-006), so it never duplicates the CI committer. **Acceptance criterion:** across
     all machines in a given week there is exactly one stamp/spark commit (the CI bot's) and no machine other than
     the editing one writes AGENTS.md for the same DIRECTIVES revision.

**Net:** one app-setting flip (server maintenance) + one GitHub Actions cron (repo-git half) replaces the
single-laptop launchd job with two always-on, machine-independent schedules.

---

## 5. Risks / guards
- **Freshness auto-ingest** re-arming the incident → keep disabled or strict-allowlist; A2 sentinel guards already protect notes-only repos (`ingestion_scheduler.py:36-43`).
- **Shared B3 worker contention** → dispatcher `max_concurrent=1` serializes execution (`config.py:114`). Note (CGAP-005): `max_per_tick` bounds the **ingestion** scheduler only (`config.py:97`); **maintenance has no enqueue cap** and queues `2 × real-repo count` jobs per tick — contention is bounded by serialization + per-repo dedup, not by a cap (see §4.1).
- **Harness co-tenancy of the dispatcher (SGAP-001 / INV-DISPATCH-COTENANT)** → the single worker is **shared with the `workflow-orch-app` harness**, which enqueues `run_repo_ingestion_workflow` into the same `ops.job_manifests` (`server.py:663-708`) on every `workflow.push`. Serialization keeps queue results correct but **not latency**: a weekly maintenance backlog (2 × real-repo count, including harness-registered real repos not excluded by the `mawf%/repo-%/idx-%` filter, `maintenance_scheduler.py:19-25`) can delay the harness's post-push ingestion freshness. Mitigate by anchoring the maintenance tick (via restart-time, §4.1) **outside harness working hours**. Acceptable at current scale; revisit if either repo set grows.
- **CI secrets** → MCP URL/token in GitHub Actions secrets only; never in the repo.
- **Observability — failed runs** → GitHub Actions emails on failed runs; the brain logs `maintenance_scheduler_tick_complete` (`maintenance_scheduler.py:81`) and `*_tick_error` on exceptions (`maintenance_scheduler.py:63-64`).
- **Observability — silent no-op / dead cadence (CGAP-007 / R-OBSERV.O3).** The actual launchd failure mode was a schedule that **never fired at all** (no `/tmp/mk-weekly-review.log`, stamp stuck at `2026-06-19`, §3) — a run that never happens emits no failure email. **Mechanism:** a **dead-man's-switch / freshness check** independent of the scheduler — e.g. a lightweight monitor (separate GH Actions cron, or a `/health`-adjacent check) that alerts if the `Last reviewed` stamp age exceeds the cadence + grace, or if `maintenance_scheduler_tick_complete` has not been logged within `maintenance_interval_seconds × 1.5`. **Acceptance criterion:** if either the GH cron or the server scheduler stops ticking for one full cadence, an alert is raised within one grace window; tested by pausing the scheduler and observing the alert.
- **CI best-effort swallows brain-unreachable (CGAP-008 / R-NEG-BRAINDOWN.O2, R-NEG-CIREACH.O2).** `weekly_review.py` swallows MCP/consolidation errors and continues (`weekly_review.py:79-80, 89-90`) and `main()` returns 0 — so a CI Spark/stamp run with the brain **down or unreachable** would exit **green** with no Spark/consolidation performed and **no failure email**. **Mechanism:** the **scheduled CI run** must treat brain-unreachability as a hard failure — either run with a flag that propagates the MCP error to a non-zero exit, or add an explicit reachability probe (`corpus_query`/`/health`) as a gating CI step that fails the job on error. (The fail-open swallow stays correct for the *local interactive* path; only the *scheduled* path must fail loud.) **Acceptance criterion:** a scheduled CI run executed while the brain is unreachable ends with a non-zero status and surfaces an Actions failure notification, rather than a green no-op.
- **Double-run (CGAP-006).** If both launchd (if ever kept) and the new schedules run, server maintenance is deduped by `_enqueue_if_absent` (`maintenance_scheduler.py:83-89`), but the **git-side** commits (stamp/spark) are not — see §4.2/§4.5: the GH cron is the **sole committer**; any retained launchd fallback runs no-commit/dry-run and on at most one machine.
- **Timezone / DST (CGAP-010 / R-CADENCE.O3).** GitHub Actions `cron` is **UTC-only**; launchd (`StartCalendarInterval`) and the ingestion scheduler (`ingestion_scheduler_timezone="Europe/Sofia"`, `config.py:95`) are local. A "weekly 9am Sofia" intent must be written in the GH cron as the corresponding **UTC** time and will **drift by an hour across DST**. **Decision:** pick a UTC cron time and accept ±1h DST drift (upkeep cadence is not time-critical), or document the two cron lines needed to hold a fixed local hour. **Acceptance criterion:** the chosen cron's effective local fire time stays within the intended off-peak window year-round (or the ±1h DST drift is explicitly accepted).
- **CI cost/quota (CGAP-009 / R-COST.O1).** The added schedule is **one weekly GH Actions run** (Spark + stamp + corpus-sync step), well within the free-tier minutes for this private repo; the dead-man's-switch monitor adds one more lightweight cron. **Acceptance criterion:** scheduled-workflow minutes stay within the account's monthly Actions allotment (one short weekly job + one monitor).
- **No-origin repos (CGAP-014).** Ingestion enumeration requires `origin_url IS NOT NULL` (`ingestion_scheduler.py:31`), so origin-less repos are never auto-ingested; maintenance does **not** require `origin_url` (`maintenance_scheduler.py:18`) so those repos still receive integrity+compaction. (Coverage holds; stated for traceability.)

## 5b. Acceptance criteria (coverage proof per kept task) — CGAP-013

Each recurring task is "covered" when its criterion is observably true. (Detailed criteria for the
cross-cutting risks live inline in §4–§5; this table is the per-task summary.)

| Task | Locus (final) | Trigger | Acceptance criterion (testable) |
| --- | --- | --- | --- |
| Integrity audit | server `MaintenanceScheduler` | weekly interval tick | `maintenance_scheduler_tick_complete` logged weekly; an `integrity_audit` job per real repo reaches a terminal state |
| Compaction | server `MaintenanceScheduler` | weekly interval tick | compaction job per real repo runs; `compaction_dry_run` flag matches the rollout decision (§4.1) |
| Freshness re-ingest | **disabled** (scoped-out) | none (manual until allowlist) | `ingestion_scheduler_enabled=False` (`config.py:92`) remains; no auto-ingest of non-allowlisted repos — verified by absence of `ingestion_scheduled` logs for unintended repos |
| Directive Spark | GitHub Actions cron | weekly cron | weekly run regenerates `spark-candidates.md`; candidates surfaced via job summary + notification (§4.5/CGAP-004) |
| AGENTS.md refresh | local on-DIRECTIVES-change hook | git event on editing machine | after a DIRECTIVES edit, `refresh_trusted` returns `refreshed:` for that machine's trusted projects (§4.3) |
| DIRECTIVES stamp + commit | GitHub Actions cron | weekly cron | weekly stamp bump committed by CI bot; `Last reviewed` advances (single committer, §4.2) |
| Corpus sync | CI explicit step (CI path) + local post-commit hook (local path) | per stamp/directive commit | after a CI stamp commit, `corpus_query` returns the new directive text (§4.2/CGAP-002) |
| Auto-capture | client-side `Stop` hook | event (out of scope) | unchanged; explicitly not a scheduled task (research.md §1) |
| Dead-man's-switch monitor | independent monitor | secondary cron / health check | alerts if stamp age or `*_tick_complete` exceeds cadence + grace (§5/CGAP-007) |

## 6. Open decisions (for the plan — P2)
1. **Freshness scheduler:** keep disabled (recommended) or enable with an allowlist?
2. **AGENTS.md refresh locus:** event-on-DIRECTIVES-change local hook (recommended) vs keep-local-launchd. (Weekly **CI** is ruled out — not feasible cross-repo, see §7.) Decision is which local trigger, not whether CI.
3. **Cadences:** maintenance weekly (default 604800s) — keep? Spark cron day/time?
4. **MCP auth for CI:** ~~what token does the deployed brain require?~~ **RESOLVED (SGAP-002):** none. The brain's
   `/mcp` endpoint is unauthenticated (`middleware/auth.py:16,24`); the CI job needs only `CLAUDE_CORPUS_MCP_URL`. No
   longer an open decision. (Re-open only if a future deployment fronts `/mcp` with an auth gateway.)

## 7. UNVERIFIED / to confirm in the gates
- ~~Whether the deployed brain requires an auth token for MCP calls~~ — **RESOLVED in the satisfaction gate
  (SGAP-002): no token required.** The `/mcp` endpoint is unauthenticated (`middleware/auth.py:16,24`); the CI
  Spark/stamp job calls it with `CLAUDE_CORPUS_MCP_URL` alone. No longer blocks R-SPARK on CI.
- Whether a GitHub Actions runner can reach the brain MCP endpoint (network/egress) — assumed public HTTPS, **not
  testable from the repo**. If unreachable, the scheduled run must fail loud, not green (§5/CGAP-008).
- **Live Azure app settings (unverifiable from repo — required implementation steps).** `maintenance_scheduler_enabled`,
  `compaction_enabled`, and `allow_remote_writes` actual values on the deployed brain (config defaults are all
  `False`; `config.py:88,100,137`). The existing local corpus hook working today **implies `allow_remote_writes=true`
  already**, but the live values cannot be confirmed from the repo and must be checked/flipped in the plan
  (SGAP-003/SGAP-005). The CI cron + `CLAUDE_CORPUS_MCP_URL` secret do not yet exist (`.github/workflows/ci.yml`
  has only push/PR triggers) — creating them is a required implementation step.

**Resolved (was open): cross-repo AGENTS refresh in CI is *not feasible* and is not attempted.** A CI runner
has no checkout of the other trusted repos and no `~/.codex/config.toml`, and `refresh_trusted` rewrites
**local working-tree** `AGENTS.md` files without committing them (`generate_projections.py:127-143`). AGENTS
refresh is therefore re-homed to a **local on-DIRECTIVES-change hook** (§4.3), with non-checked-out repos'
projections explicitly scoped as low-harm-stale.

**Resolved from the repo (no longer open):** `MaintenanceScheduler` cadence is purely loop/interval-based with
no wall-clock anchor — `_loop` runs `await asyncio.wait_for(self._stop_event.wait(), timeout=interval)` in a
`while` loop (`jobs/maintenance_scheduler.py:58-68`). There is no `daily_at` equivalent for maintenance (that
control exists only for ingestion, `config.py:94`).
