# Satisfaction Audit — Plan: Automation schedule for second-brain upkeep

Audited document: `Tasks/automation-schedule/plan.md`
Gate: requirements-satisfaction-gap-loop (DEPTH). Upstream: passed internal-readiness (`plan.gap-audit.md`) + coverage (`plan.coverage-audit.md`, converged breadth at Cycle 3).
Question this gate answers: of the requirements the plan addresses, will each actually **hold end-to-end** against the real runtime, stored data, the co-tenant `workflow-orch-app` harness, and CI runner reality?

Grounding repos (read into un-cited code):
- `/Users/kamenkamenov/memory-knowledge` — `jobs/maintenance_scheduler.py`, `jobs/dispatcher.py`, `jobs/job_worker.py`, `jobs/manifest_writer.py`, `jobs/manifest_reader.py`, `config.py`, `server.py` (lifespan, tools, routes), `middleware/auth.py`, `db/health.py`, `observability/metrics.py`, `workflows/integrity_audit.py`, `working-agreement/{sync_corpus.py,sync-corpus.sh,weekly_review.py,generate_projections.py}`, `.git/hooks/post-commit`.
- `/Users/kamenkamenov/mcp-agents-workflow` — `src/workflow_orch/knowledge_client.py`, repo-wide DB/job grep (harness interop).

This artifact holds the full analysis. The chat reply summarizes.

**Convergence:** ACHIEVED at Cycle 3 (no-edit). 1 blocker satisfaction gap (SGAP-001, WS5 server-half observability unsatisfiable as written) found and closed in Cycle 1; Cycle 2 fresh full pass found zero new; Cycle 3 final no-edit pass confirms zero blockers.

---

## Requirement Inventory (addressed requirement set + depth-only implied invariants)

Carries the 27 req_ids / 60 obligations from the coverage pass. This gate adds **implied-essential satisfaction invariants** (I-*) that only become visible at depth, and **interop invariants** (X-*) with the harness/CI. Only rows that required reading into un-cited code/data are expanded; the rest are confirmed in the Lens Matrix.

| req_id | requirement | type | source (quoted) |
| --- | --- | --- | --- |
| R-INTEG | Integrity audit + compaction run recurringly server-side | stated | plan.md:18 "Server-side maintenance — enable `MaintenanceScheduler`" |
| R-INTEG.O4 | off-peak via restart anchor | stated | plan.md:37 "the first tick fires ~immediately at `start()` … every subsequent weekly tick lands at the restart wall-clock hour" |
| R-CORPUS.O2 | CI commit fires corpus sync (mirror current + prune orphans), fail-loud | stated | plan.md:99 "run `sync_corpus.py` … only when `COMMIT_MADE=1` … exit propagated" |
| R-OBSERV.O3 | dead cadence detected for **either** GH cron **or** the server scheduler | stated | plan.md:45 "(b) server half … fails when the latest `maintenance_scheduler_tick_complete` / terminal `integrity_audit` is older than `interval × 1.5`" |
| R-AGENTS | AGENTS.md refresh on DIRECTIVES change (local post-commit) | stated | plan.md:122 "add … `generate_projections.py --refresh-trusted`" |
| R-SHAREDINFRA / R-NEG-CONCURRENT | don't overwhelm / destructively contend the shared single worker | stated | plan.md:60 "`ops.job_manifests` is shared with the harness" |
| R-NEG-BRAINDOWN.O2 / R-NEG-CIREACH | CI fail-loud on brain unreachable | stated | plan.md:96 "`curl --fail … "$CORPUS_HEALTH_URL"` — non-200 fails the job" |
| R-AUTH | CI reaches `/mcp` with only the URL, no token | stated | plan.md:40 "D6 … `/mcp` bypasses `ApiKeyAuthMiddleware`" |
| **I-TICK-ANCHOR** | the maintenance `_loop` must tick immediately at `start()` AND `start()` must be called at container startup | implied-essential | depth: the restart-anchor claim (R-INTEG.O4) holds only if both halves are true |
| **I-JOBTYPE-REG** | enabling the scheduler must actually produce integrity_audit + compaction jobs the dispatcher runs | implied-essential | depth: scheduler `create_job`s; dispatcher must have the types registered + claim them |
| **I-DEDUP** | `_enqueue_if_absent` must truly dedupe per (repo,tool) | implied-essential | depth: AC `plan.md:73` "no dup (repo,tool)" |
| **I-INTERVAL-READ** | `MAINTENANCE_INTERVAL_SECONDS` must actually be read at runtime | implied-essential | depth: cadence + `interval × 1.5` heartbeat window depend on it |
| **I-TICK-OBSERVABLE** | the WS5 server-half check must be able to OBSERVE the server's last maintenance tick / last terminal integrity_audit age, from a GitHub runner, with only `CLAUDE_CORPUS_MCP_URL` (no token) | implied-essential | depth: WS5 server-half (plan.md:45,171) is satisfiable only if such a read surface exists |
| **I-HEALTH-PUBLIC** | the `/health` endpoint the CI probe derives must actually exist and be public | implied-essential | depth: CGAP-P01 probe (plan.md:96) depends on it |
| **X-HARNESS-JOBTYPES** | the harness must not mis-handle / destructively contend `integrity_audit`/`compaction` job types it now sees in the shared `ops.job_manifests` | invariant (interop) | depth: plan.md:60 shared table; harness co-tenant |
| **X-HARNESS-ASSUME-OFF** | the harness must not assume these schedulers are off | invariant (interop) | depth |
| **X-SYNC-EXIT** | `sync_corpus.py` must return non-zero on guarded/failed writes so the CI step fails loud | invariant (CI) | plan.md:44 D10; plan.md:99 |
| **X-HOOK-SYMLINK** | editing `working-agreement/sync-corpus.sh` (WS3) must actually be exercised by the installed post-commit hook | invariant (scope-vs-usage) | plan.md:122 edits sync-corpus.sh; the live hook is what fires |

---

## End-to-End Trace Table (real call chain; un-cited code read)

| req_id | trace (trigger → … → surfaced result) | runtime/data evidence (path:line / value) | holds? |
| --- | --- | --- | --- |
| I-TICK-ANCHOR (a) | `start()` → `create_task(_loop())` → `_loop` runs `_tick()` **before** `wait_for(timeout=interval)` | `maintenance_scheduler.py:45` create_task; `:60-68` loop: `_tick()` at :62 precedes `wait_for(self._stop_event.wait(), timeout=interval)` at :66 — first tick immediate, recurring every interval | **yes** |
| I-TICK-ANCHOR (b) | container startup → `app_lifespan` → `if settings.maintenance_scheduler_enabled: MaintenanceScheduler().start(pool, settings)` | `server.py:6509` `app_lifespan`; `:6665-6669` conditional start; `:6774` `lifespan=app_lifespan` on the Starlette app → start() IS called at startup when flag on | **yes** |
| I-JOBTYPE-REG | flag on → tick → `create_job(...,'integrity_audit'/'compaction',...)` into `ops.job_manifests` → dispatcher poll → claim → `execute_job(job_fn=integrity_audit.run / compaction.run)` | scheduler `maintenance_scheduler.py:77-78,90`; types registered `server.py:6644-6647`; dispatcher started `:6653`; dispatcher claims pending/retrying `dispatcher.py:120-127` and calls `workflow_fn` `:190-196` | **yes** |
| I-DEDUP | tick → `_enqueue_if_absent` → `SELECT job_id FROM ops.job_manifests WHERE repository_key=$1 AND tool_name=$2 AND state_code IN ('pending','running')`; skip if present | `maintenance_scheduler.py:27-31` `_ACTIVE_BY_TOOL_SQL`; `:86-89` skip-if-existing → dedupe per (repo,tool) holds | **yes** |
| I-INTERVAL-READ | `start()` logs `interval=settings.maintenance_interval_seconds`; `_loop` reads `self._settings.maintenance_interval_seconds` | `maintenance_scheduler.py:46,59`; field `config.py:101` default 604800; app-setting `MAINTENANCE_INTERVAL_SECONDS` (BaseSettings, no prefix, `config.py:8-9`) | **yes** |
| R-INTEG.O4 | enabling `az webapp restart` in off-peak window → first tick at restart wall-clock → recurring weekly at same hour | mechanism = I-TICK-ANCHOR (a)+(b) both confirmed; restart timing is operator step §8.4 (`plan.md:214`) | **yes** (operator-timed) |
| X-HARNESS-JOBTYPES | harness pushes → it calls MCP tool `run_repo_ingestion_workflow` over HTTP; polls by its own `job_id` via `check_job_status` | harness is a pure MCP **client**: `knowledge_client.py:526-543` (`call_tool_json`), `:545-556` poll by job_id; repo-wide grep shows **no** `asyncpg`/`job_manifests`/own dispatcher in harness src | **yes** (no destructive contention) |
| X-HARNESS-ASSUME-OFF | harness has no code path that reads job_type distribution or assumes scheduler state | no `integrity_audit`/`compaction`/`maintenance` refs in harness src (grep) | **yes** |
| X-SYNC-EXIT | guarded/failed write → `_report` returns False → `failures += 1` → `run()` returns failures → `main()` returns it → `SystemExit(main())` non-zero | `sync_corpus.py:103-114` `_report` ok=status=="success"; `:90,99` accumulate; `:100,138` return; `:142` `raise SystemExit(main())` | **yes** |
| R-CORPUS.O2 | CI commit (COMMIT_MADE=1) → `sync_corpus.py --url` → upsert current (`run_corpus_upsert_workflow`) + deactivate orphans vs `HEAD~1` (`corpus_deactivate`) | `sync_corpus.py:123` parse current; `:128-134` orphans vs `git show HEAD~1`; `:81-99` write calls; both are write-guarded MCP tools | **yes** (commit path); no-commit path skipped per CGAP-P02 |
| X-HOOK-SYMLINK | DIRECTIVES commit → `.git/hooks/post-commit` (symlink → `working-agreement/sync-corpus.sh`) runs → gated grep → sync + (new) refresh | `.git/hooks/post-commit` is a **symlink** → `working-agreement/sync-corpus.sh` (ls -la); gate `sync-corpus.sh:15`; sync `:23`; `exit 0` `:24` → WS3 edit IS exercised | **yes** (per machine the symlink must exist — WS3 verification covers it) |
| R-AGENTS | DIRECTIVES commit → hook → `generate_projections.py --refresh-trusted` → rewrites generated AGENTS.md across trusted projects | flag `generate_projections.py:154-156`; `--codex-config` default `~/.codex/config.toml` `:158-159`; `refresh_trusted` `:127`; returns 0 `:168` | **yes** |
| I-HEALTH-PUBLIC | CI `curl …/health` → `health_endpoint` → `{"status":"ok"}` 200; auth bypassed | route `server.py:6748`; `health_endpoint` `:6721-6722`; `health_check` returns `{"status":"ok"}` `db/health.py:23-24`; `/health` ∈ `_PUBLIC_PATHS` `middleware/auth.py:8,24` | **yes** |
| R-AUTH | CI `/mcp` call with no token → `ApiKeyAuthMiddleware.dispatch` returns `call_next` before key check | `middleware/auth.py:16` `/mcp` ∈ `_PUBLIC_PREFIXES`; `:24` early return | **yes** |
| **I-TICK-OBSERVABLE** | WS5 heartbeat (GitHub runner, URL only) → query brain for "age of last terminal `integrity_audit` job" → red if older than `interval×1.5` | **NO read surface exists** — see SGAP-001 below | **NO** |
| R-OBSERV.O3 (server half) | depends on I-TICK-OBSERVABLE | unsatisfiable as written → **SGAP-001** | **NO** (pre-fix) |

---

## SGAP-001 — WS5 server-half dead-cadence check is unsatisfiable as written (the original failure mode: passes green while observing nothing)

**Severity:** blocker. **req_id:** R-OBSERV.O3 (server half) / I-TICK-OBSERVABLE / P-DEADCADENCE-SERVER.
**Lenses:** (1) cross-feature contract invariant; (4) end-to-end runtime trace; (6) silent-inert/silent-wrong; (8) scope-vs-usage.

**What the plan asserts (both sides quoted).**
- Producer side (what the scheduler actually writes): the maintenance scheduler enqueues jobs into **`ops.job_manifests`** with `tool_name='run_integrity_audit_workflow'` / `'run_compaction_workflow'` (`maintenance_scheduler.py:77-78,90` → `manifest_writer.create_job` → `INSERT INTO ops.job_manifests`, `manifest_writer.py:30-32`). The dispatcher executes them via `execute_job` (`dispatcher.py:190-196`), which only ever calls `update_job_state` → **`ops.job_manifests`** (`job_worker.py:39,43,63,83,94`). The job's effect on `ops.workflow_runs` is **none** — `integrity_audit.run` returns a `WorkflowResult` and writes **no** `workflow_runs` row (`workflows/integrity_audit.py:24-93`); `grep` confirms **zero** `workflow_runs`/`save_workflow_run` references anywhere under `src/memory_knowledge/jobs/`.
- Consumer side (what the plan's WS5 mechanism reads): `plan.md:171` — "query the brain for the latest terminal `integrity_audit` job age via the public `/mcp` endpoint (e.g. `list_workflow_runs`/job-status …)". But `list_workflow_runs` reads **`ops.workflow_runs`** (`server.py:3357-3394`: `FROM ops.workflow_runs wr JOIN catalog.repositories … ORDER BY wr.started_utc`), keyed by `repository_key`, returning `workflow_name`/`started_utc`. Maintenance jobs never create such a row.

**Why it breaks the requirement (end-to-end).** The read path (`ops.workflow_runs`) is a **different table** than the write path (`ops.job_manifests`). A GitHub runner calling `list_workflow_runs(repository_key=…)` will get rows for **interactive/harness** workflow runs (or none), and **never** a maintenance-driven `integrity_audit`. The age computed will therefore reflect something other than the maintenance tick — most often "no recent integrity_audit run" even when the scheduler is perfectly healthy (false red), or a stale interactive run (false green). The check cannot distinguish "scheduler dead" from "scheduler alive" → it is the exact original failure mode (a check that is green/red for reasons unrelated to the thing it claims to watch).

**Exhaustive search for ANY feasible read surface (URL only, no token, single stateless request).** None exists:
- `list_workflow_runs` → wrong table (`ops.workflow_runs`), never written by maintenance (`server.py:3357-3394`).
- `check_job_status(job_id)` → requires a known `job_id`; the runner cannot know maintenance job ids (`server.py:884-905`; `manifest_reader.get_job_by_id` is by id only, `manifest_reader.py:10-13`).
- No MCP tool reads `ops.job_manifests` by job_type/age: `grep -n job_manifests server.py` → **zero matches**. `manifest_reader` has `get_failed_jobs`/`get_active_job_for_shape`/`get_latest_resume_checkpoint` but **none** is exposed as an MCP tool, and all require `repository_key`+`tool_name` or a state filter, not a cross-repo "latest terminal by type" (`manifest_reader.py:44-132`).
- `get_memory_stats` → memory-architecture counts, no job/tick timestamp (`server.py:962-979`).
- `list_repositories` → last **ingestion** state only, not maintenance/integrity-audit (`server.py:1011-1012`).
- `/health` → static `{"status":"ok"}` (`db/health.py:23-24`). `/ready` → DB/store readiness (`db/health.py:27-62`). Neither carries scheduler-tick info.
- `/metrics` (Prometheus, public, `server.py:6732-6735`) → `job_transitions_total` is unlabeled by job_type and is a **monotonic counter** with no timestamp (`metrics.py:21`), and is **not** incremented in `manifest_writer.py`/`dispatcher.py` (grep: zero). `tool_calls_total{tool_name}` (`metrics.py:51`) only wraps the `@track_tool_metrics`-decorated **MCP tool entrypoints** (e.g. `run_integrity_audit_workflow` `server.py:737`); the dispatcher path calls `integrity_audit.run` **directly** (`dispatcher.py:193`), which is **undecorated** → maintenance ticks do **not** increment `tool_calls_total` either. No metric ages a maintenance tick, and a stateless runner cannot diff a monotonic counter without prior-snapshot state.
- The only periodic server liveness signal for maintenance is the **structlog line** `maintenance_scheduler_tick_complete` (`maintenance_scheduler.py:81`) — persisted to **logs only**, queryable from a GitHub runner only via Azure log APIs (needs Azure creds, not just the URL → out of the plan's "URL only, no token" contract).

**Planned fix (document edit only; lock a feasible contract + record the required runtime step).** The server-half check is genuinely unsatisfiable with the current read surface, so the plan must EITHER (chosen: A) lock a feasible mechanism that requires a small, named runtime addition recorded as an implementation step, OR (B) scope the server-half out with a compensating manual check. The plan already commits to the server-half as a hard requirement (D11, R-OBSERV.O3 / research CGAP-007 "either … or the server scheduler"), so scoping it out would re-open a converged obligation. Therefore lock **A**: add a minimal read-only **last-maintenance-tick surface** the scheduler writes and the heartbeat can read with URL only — concretely, the maintenance scheduler records `last_tick_utc` (e.g. an `ops.scheduler_heartbeats` row keyed by scheduler name, written at the end of `_tick`), exposed by a new read-only MCP tool (e.g. `get_scheduler_heartbeat`) reachable on `/mcp` with no token, returning the most recent `maintenance_scheduler` tick timestamp; WS5 server-half then ages that value against `interval×1.5`. Record this as a REQUIRED implementation step in the plan (it is a runtime/code change, not an app-setting), correct the WS5 mechanism text and AC to name this surface, and mark the previously-named `list_workflow_runs`/`check_job_status` mechanism as rejected with the table-mismatch reason. Until that surface ships, the server-half is explicitly NOT covered by `list_workflow_runs` and the plan must say so.

**Closure evidence:** edited `plan.md` D11, WS1 edge-case cross-ref, WS5 server-half mechanism + AC, §6 sequencing (the new tool must ship before WS5), §8 live confirmations, §9 test plan, §10 — see Cycle 1 Edits.
**Status:** closed (Cycle 1).

---

## Lens Coverage Matrix (every requirement × every lens)

Legend: ✓ checked-holds · G gap (→ ledger) · N/A (with reason).

| req_id | L1 contract | L2 data-reality | L3 intent | L4 e2e trace | L5 producer/consumer | L6 silent-inert | L7 config/env | L8 scope-vs-usage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-INTEG / I-JOBTYPE-REG | ✓ types registered server.py:6644-6647 | ✓ jobs land in job_manifests | ✓ | ✓ scheduler→dispatcher→run | ✓ create_job/claim symmetric | ✓ tick_error caught & logged | ✓ flag read server.py:6665 | ✓ dispatcher is sole claimer |
| R-INTEG.O4 / I-TICK-ANCHOR | ✓ | N/A (timing not data) | ✓ off-peak intent via restart | ✓ both halves confirmed | N/A | ✓ | ✓ operator restart §8.4 | ✓ |
| I-DEDUP | ✓ (repo,tool) key | ✓ state_code IN(pending,running) | ✓ | ✓ | ✓ | ✓ skip logged | N/A | ✓ |
| I-INTERVAL-READ | ✓ | ✓ default 604800 | ✓ | ✓ read :46,59 | N/A | N/A | ✓ MAINTENANCE_INTERVAL_SECONDS | ✓ |
| R-SHAREDINFRA / R-NEG-CONCURRENT / X-HARNESS-* | ✓ shared table, serialized | ✓ | ✓ latency-only contention | ✓ harness is MCP client only | ✓ | ✓ | ✓ max_concurrent=1 | ✓ harness no SQL/dispatcher |
| R-CORPUS.O2 / X-SYNC-EXIT | ✓ identity = write path entry_key | ✓ orphans vs HEAD~1 | ✓ | ✓ upsert+deactivate | ✓ identity triple == entry_key (sync_corpus.py:12-13,42-43) | ✓ non-zero on guarded/failed | ✓ ALLOW_REMOTE_WRITES (§8.1) | ✓ COMMIT_MADE gate |
| R-AGENTS / X-HOOK-SYMLINK | ✓ flag exists | N/A | ✓ | ✓ hook symlink → sync-corpus.sh | ✓ | ✓ fail-open `|| true` | ✓ ~/.codex/config.toml | ✓ symlink confirmed |
| R-NEG-BRAINDOWN.O2 / R-NEG-CIREACH / I-HEALTH-PUBLIC | ✓ /health public | ✓ returns ok | ✓ fail-loud | ✓ curl --fail | ✓ derived from MCP URL base | ✓ non-200 → red | ✓ runner egress §8.2 (unverifiable) | ✓ |
| R-AUTH | ✓ /mcp public | N/A | ✓ no token | ✓ early return | N/A | ✓ | ✓ secret URL only | ✓ |
| R-OBSERV.O3 (server half) / I-TICK-OBSERVABLE | **G SGAP-001** | **G** (no queryable tick datum) | **G** (mechanism ≠ intent) | **G** (read≠write table) | **G** (asymmetric) | **G** (false green/red) | ✓ | **G** (reads a path that never carries the signal) |
| R-OBSERV.O3 (cron half) | ✓ stamp regex | ✓ stamp = date -u +%F | ✓ | ✓ stamp >9d → red | ✓ writer/reader both UTC date | ✓ | ✓ | ✓ |
| R-SPARK / R-STAMP / R-COST / R-CADENCE / R-SECRETS / R-IDEMPOTENT / R-RETIRE / R-NEG-RUNNING / R-NEG-MIDFLIGHT / R-NEG-NOORIGIN / R-FRESH / R-CAPTURE / R-NOMANUAL / R-MACHINEINDEP / R-MULTIMACHINE / R-NOINCIDENT / R-BACKCOMPAT | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

(For the omnibus final row: each was traced via the coverage pass anchors and re-confirmed against live code where a runtime dependency existed; none introduced a depth gap beyond SGAP-001. E.g. R-NEG-RUNNING holds via `_ACTIVE_BY_TOOL_SQL` `maintenance_scheduler.py:27-31`; R-NEG-NOORIGIN holds because `_REAL_REPOS_SQL` does not require `origin_url` `maintenance_scheduler.py:18-25`; R-CORPUS local-half via the symlinked hook.)

---

## Cleanup / Known-Limitation List (non-blocking)

- **CL-1 (env contract, recorded as §8 live check, not a blocker):** `ALLOW_REMOTE_WRITES=true` must be live for the CI sync (`guards.py`); if false the step fails red (loud) — acceptable, already §8.1.
- **CL-2 (unverifiable from repo):** GitHub runner egress to `https://memory-knowledge.azurewebsites.net` (§8.2) and live Azure app-setting values (§8.3) — genuinely unverifiable here; each has a defined fail-loud behavior. Marked explicitly.
- **CL-3 (X-HOOK-SYMLINK per machine):** the `.git/hooks/post-commit → working-agreement/sync-corpus.sh` symlink must exist on each machine for WS3 to fire; WS3 verification (`plan.md:131`) exercises it per machine. Not a blocker (the corpus local mirror already relies on the same symlink today and works).

---

## Cycle 1 Plan

- SGAP-001 → edit `plan.md`: (1) D11 server-half — replace the `list_workflow_runs`/`check_job_status` mechanism with a feasible `get_scheduler_heartbeat` (last `maintenance_scheduler` tick) read tool, and record that this read surface is a REQUIRED runtime implementation step (scheduler writes `last_tick_utc`; new read-only MCP tool). (2) WS5 server-half mechanism + AC — name the new tool; state the rejected mechanism + reason (read/write table mismatch). (3) WS1 edge-case cross-reference — keep delegating dead-cadence to WS5 but to the corrected mechanism. (4) §6 sequencing — the new read tool + scheduler last-tick write must ship/deploy before WS5 validation. (5) §8 — add a live confirmation that the heartbeat tool responds. (6) §9 — update the server-half test row. (7) §10 — note the one runtime addition.
- Document edits only; the runtime change is recorded as a required implementation step, not coded.

## Cycle 1 Edits

| gap_id | edit applied | location |
| --- | --- | --- |
| SGAP-001 | D11(b): replaced unsatisfiable `maintenance_scheduler_tick_complete`/`integrity_audit` via `list_workflow_runs` with a `get_scheduler_heartbeat` last-tick read tool; flagged required runtime step | plan.md §3 D11 |
| SGAP-001 | WS1 edge-case: corrected cross-ref to the WS5 server-half mechanism (no longer implies `list_workflow_runs` covers it) | plan.md WS1 "Edge cases" |
| SGAP-001 | WS5 server-half mechanism: rewrote to (i) require a `last_tick_utc` write in `_tick` + a read-only `get_scheduler_heartbeat` MCP tool; (ii) age that value against `interval×1.5`; (iii) explicitly reject `list_workflow_runs`/`check_job_status` with the read/write-table-mismatch reason | plan.md WS5 |
| SGAP-001 | WS5 server-half AC: test the heartbeat tool directly | plan.md WS5 AC |
| SGAP-001 | §6 sequencing: added a step — ship the scheduler last-tick write + `get_scheduler_heartbeat` tool (deploy) before WS5 validation | plan.md §6 |
| SGAP-001 | §8: added live confirmation #5 — `get_scheduler_heartbeat` returns a recent tick on the deployed app | plan.md §8 |
| SGAP-001 | §9: updated the dead-man's-switch (server half) test row to the new tool | plan.md §9 |
| SGAP-001 | §10 + Critical files: recorded the single required runtime addition | plan.md §10, Critical files |

## Cycle 1 Validation

Re-read each edited section. Re-ran the I-TICK-OBSERVABLE trace against the corrected mechanism: a scheduler-written `last_tick_utc` (in `_tick`, alongside `maintenance_scheduler_tick_complete` at `maintenance_scheduler.py:81`) read by a new `get_scheduler_heartbeat` MCP tool over the public `/mcp` (no token, same bypass as every other tool `middleware/auth.py:16,24`) IS observable from a GitHub runner with URL only — the read path now reads exactly what the producer writes (producer/consumer symmetric). Confirmed the rejected mechanism's reason still holds (no existing tool reads `ops.job_manifests` by type/age; `grep job_manifests server.py` = zero). All other traces unchanged and still carry live evidence.

### Post-Edit New-Gap Pass (after Cycle 1 edits)
- Does the new `get_scheduler_heartbeat` introduce an auth gap? No — `/mcp` is open (`middleware/auth.py:16,24`); same contract as the corpus tools the plan already relies on. R-SECRETS holds (still URL only).
- Does adding a `last_tick_utc` write contend with the harness? No — it is a tiny upsert keyed by scheduler name, serialized like everything else; harness never reads it (harness is an MCP client, no SQL). X-HARNESS-* unaffected.
- Does the §6 sequencing edit create a window where WS5 validates before the tool exists? No — the new step explicitly orders the tool-ship before WS5 validation.
- Scope drift: the change is recorded as a required runtime step (a small write + a read tool), not silently widening WS1's "app-settings-only" claim — WS1 itself remains app-settings-only; the heartbeat surface is a WS5 prerequisite. No new gap.

No new blocker gaps.

---

## Cycle 2 Assessment (fresh full pass over the edited document)

Re-ran all 8 lenses over the full addressed requirement set + I-* + X-* invariants against the edited `plan.md`.

| requirement/invariant | status | evidence |
| --- | --- | --- |
| I-TICK-ANCHOR (a)+(b) | holds | `maintenance_scheduler.py:60-68` (tick before wait); `server.py:6665-6669,6774` (start at lifespan startup) |
| I-JOBTYPE-REG | holds | `server.py:6644-6647,6653`; `dispatcher.py:120-127,190-196` |
| I-DEDUP | holds | `maintenance_scheduler.py:27-31,86-89` |
| I-INTERVAL-READ | holds | `maintenance_scheduler.py:46,59`; `config.py:101` |
| X-HARNESS-JOBTYPES / X-HARNESS-ASSUME-OFF | holds | harness MCP-client only (`knowledge_client.py:526-556`); no harness SQL/dispatcher/job_type refs (grep) |
| X-SYNC-EXIT | holds | `sync_corpus.py:90,99-100,138,142` |
| R-CORPUS.O2 | holds | commit path `sync_corpus.py:123,128-134,81-99`; no-commit skipped (CGAP-P02) |
| X-HOOK-SYMLINK | holds | post-commit symlink → sync-corpus.sh; gate `:15`; insert before `exit 0` `:24` |
| R-AGENTS | holds | `generate_projections.py:154-159,127,168` |
| I-HEALTH-PUBLIC / R-NEG-CIREACH | holds | `server.py:6721-6722,6748`; `db/health.py:23-24`; `middleware/auth.py:8,24` |
| R-AUTH | holds | `middleware/auth.py:16,24` |
| **R-OBSERV.O3 (server half) / I-TICK-OBSERVABLE** | **holds (post-fix)** | corrected mechanism reads a scheduler-written `last_tick_utc` via a `get_scheduler_heartbeat` tool on public `/mcp`; producer/consumer now symmetric; recorded as required runtime step |
| R-OBSERV.O3 (cron half) | holds | stamp regex vs `date -u +%F`, >9d → red |
| all other carried requirements | hold / scoped-out | unchanged from coverage convergence; no depth regression introduced by edits |

Per the hard-stop rule, Cycle 2 is an assessment over the edited document; it made **no edits**. Convergence declared in the next no-edit cycle.

---

## Cycle 3 — Final Convergence Check (no edits)

Fresh full pass; zero blockers discoverable from the document, repo, or data. Every addressed requirement is traced end-to-end to confirming live evidence; every producer/consumer and read/write boundary checked on **both** sides (notably the read=write table identity for corpus sync, and the now-corrected read=write surface for the server-half heartbeat). The one original blocker (SGAP-001, the server-half check reading a different table than the scheduler writes — the classic "green while observing nothing" failure) is closed by locking a feasible same-surface mechanism and recording its required runtime addition. No edits this cycle.

### Final Readiness Proof (compact)

| req_id | satisfied end-to-end? | evidence |
| --- | --- | --- |
| R-INTEG (+O4 off-peak restart anchor) | yes | tick-before-wait `maintenance_scheduler.py:60-68` + start-at-startup `server.py:6665-6669,6774`; off-peak via operator restart §8.4 |
| I-JOBTYPE-REG / I-DEDUP / I-INTERVAL-READ | yes | `server.py:6644-6647`; `maintenance_scheduler.py:27-31,46,59,86-89` |
| R-CORPUS.O2 (+ X-SYNC-EXIT) | yes | `sync_corpus.py:123,128-134,81-99,138,142`; identity == write-path entry_key `:12-13` |
| R-AGENTS (+ X-HOOK-SYMLINK) | yes | symlinked hook → `sync-corpus.sh`; `generate_projections.py:154-168` |
| R-OBSERV.O3 cron half | yes | stamp >9d → red |
| R-OBSERV.O3 server half | yes (post-fix; requires the recorded runtime step) | corrected `get_scheduler_heartbeat` last-tick mechanism; rejected `list_workflow_runs` (table mismatch, `server.py:3357-3394` vs `job_manifests`) |
| R-SHAREDINFRA / R-NEG-CONCURRENT / X-HARNESS-* | yes | single serialized dispatcher `config.py:114`; harness MCP-client only |
| R-NEG-BRAINDOWN.O2 / R-NEG-CIREACH / I-HEALTH-PUBLIC | yes | `/health` public+real; `curl --fail` |
| R-AUTH | yes | `/mcp` public `middleware/auth.py:16,24` |
| all other carried requirements | yes / scoped-out | coverage anchors re-confirmed; no depth regression |

**Convergence: ACHIEVED (depth).** 1 blocker satisfaction gap (SGAP-001) found and closed; fresh full pass found zero. Harness interop verified non-destructive (latency-only; harness is a pure MCP client with no DB/dispatcher access). CI corpus-sync verified fail-loud and table-symmetric. The restart anchor verified on both halves.

**Genuinely-unverifiable items (marked explicitly, per the loop's non-convergence rule):**
- Live Azure app-setting values (`ALLOW_REMOTE_WRITES`, `MAINTENANCE_SCHEDULER_ENABLED`, `COMPACTION_ENABLED`) — §8.1/§8.3; each has a defined fail-loud behavior.
- GitHub runner egress to the Azure host — §8.2.
- Whether the new `get_scheduler_heartbeat` tool/`last_tick_utc` write is implemented and deployed — it is recorded as a REQUIRED implementation step (this gate produces a plan, not code); WS5 server-half is satisfiable **only after** that step ships (sequenced in §6, confirmed in §8.5).

**Requirement remaining a user decision:** none for satisfaction. The server-half fix introduces one small required runtime addition (scheduler last-tick write + a read-only `get_scheduler_heartbeat` MCP tool). The user should be aware this is the single new code item the plan now mandates; if the user instead prefers to scope the server-half dead-cadence detection OUT (accepting that a silently-dead maintenance scheduler with a healthy CI cron would go undetected), that is the alternative — but it re-opens research CGAP-007 / R-OBSERV.O3 and must be an explicit accepted limitation. The plan locks the in-scope fix (A).
