# Plan — Automation schedule for second-brain upkeep (no manual triggers)

> **STATUS — BUILT 2026-06-21 (heartbeat tool included).** Live & verified:
> - **WS1** maintenance scheduler **ENABLED** (`MAINTENANCE_SCHEDULER_ENABLED=true`, `COMPACTION_ENABLED=false` dry-run) — verified ticking (`get_scheduler_heartbeat` non-null, age ~2s). Cadence anchored to the enabling restart **~11:07 UTC** (NOT off-peak — re-anchor via a deliberate off-peak restart when convenient).
> - **WS5 tool** `get_scheduler_heartbeat` deployed (`sha-99a86e0`) + dead-man's-switch script shipped.
> - **WS3** on-DIRECTIVES AGENTS-refresh hook shipped (live via the post-commit symlink).
> - **WS4** launchd retired on THIS machine.
> - Code committed `99a86e0`; GitHub secret `CLAUDE_CORPUS_MCP_URL` set; `ALLOW_REMOTE_WRITES=true` confirmed.
> **Pending (operator — credential/machine limits):** (1) **push the 2 workflow files** (`weekly-upkeep.yml`, `upkeep-heartbeat.yml`) — git/`gh` token lacks `workflow` scope (`gh auth refresh -s workflow`, then push); (2) retire launchd on the **other** machine; (3) §7 follow-up: flip `COMPACTION_ENABLED=true` after one clean dry-run cycle; (4) optional: re-anchor WS1 cadence off-peak.

**Mode:** Implementation plan (decision-complete; no code shipped). Created 2026-06-21. Owner: memory-knowledge.
**Source:** `research.md` + `research.gap-audit.md` + `research.coverage-audit.md` + `research.satisfaction-audit.md` (same folder). Honors every GAP/CGAP/SGAP finding.
**Repo:** `/Users/kamenkamenov/memory-knowledge` (GitHub `yourbteam/memory-knowledge`, default branch `main`). Python MCP server deployed on Azure App Service (RG `workflow-orch-rg`, app `memory-knowledge`, URL `https://memory-knowledge.azurewebsites.net/mcp/`). The brain's job dispatcher is shared with the `workflow-orch-app` harness (co-tenant).

> Path convention: runtime cites (`config.py`, `server.py`, `jobs/...`, `middleware/...`, `guards.py`) are relative to `src/memory_knowledge/`; repo-root files (`Dockerfile`, `.github/workflows/...`, `working-agreement/...`, `.git/hooks/...`) are cited from the repo root. App-setting names are the **uppercased pydantic field name** — `Settings` is a `BaseSettings` with no `env_prefix` (`config.py:8-9`), so field `maintenance_scheduler_enabled` is set via app setting `MAINTENANCE_SCHEDULER_ENABLED`.

---

## 1. Objective

Run the brain's recurring upkeep on a reliable, machine-independent schedule with **no manual triggers**, correct for a user across two machines (home/office), without re-arming the freshness/ingestion incident and without overwhelming the shared single-worker Azure dispatcher. Replace the single-laptop launchd job (currently loaded but has never fired) with two always-on schedules: a server-side maintenance scheduler (Azure) and a GitHub Actions weekly cron (repo-git half), plus a local on-DIRECTIVES-change AGENTS refresh and an independent dead-man's-switch.

## 2. Scope

**In scope (exactly the 5 workstreams):**
1. Server-side maintenance — enable `MaintenanceScheduler` via Azure app settings.
2. GitHub Actions weekly cron for Directive Spark + DIRECTIVES "Last reviewed" stamp + explicit corpus sync.
3. AGENTS.md refresh wired to the local DIRECTIVES-change event (post-commit path).
4. Retire launchd on every machine.
5. Dead-man's-switch / observability for never-fired schedules.

**Out of scope (explicit, with rationale):**
- **Freshness re-ingest** — stays DISABLED (`INGESTION_SCHEDULER_ENABLED` unchanged). Locked default; incident-driven exception to "no manual triggers" (`config.py:92`).
- **Auto-capture (#2)** — client-side `Stop` hook, not a schedule (`working-agreement/auto-capture-stop.sh`, `auto_capture.py`); unchanged.
- **Cross-repo AGENTS refresh in CI** — physically infeasible (no checkout / no `~/.codex/config.toml` on a GitHub runner; `refresh_trusted` writes uncommitted local trees, `generate_projections.py:127-143`).
- **Real-compaction in the first cycle** — deferred to a documented follow-up after one clean dry-run cycle (see §6 and §7).
- **Wall-clock off-peak anchoring of maintenance** — not directly schedulable (interval loop, no anchor, `maintenance_scheduler.py:58-68`); achieved best-effort via restart-time (§5, Workstream 1).

## 3. Locked Decisions

| # | Decision | Grounding |
| --- | --- | --- |
| D1 | **Compaction dry-run for the first cycle.** Set `MAINTENANCE_SCHEDULER_ENABLED=true` but leave `COMPACTION_ENABLED=false`. The scheduler computes `dry_run = not compaction_enabled` (`maintenance_scheduler.py:71`) → compaction enqueued dry-run only; integrity audits run for real. Flip `COMPACTION_ENABLED=true` after one clean observed cycle (§7 follow-up). | `config.py:88`, `maintenance_scheduler.py:71,78` |
| D2 | **Freshness scheduler stays DISABLED.** No change to `INGESTION_SCHEDULER_ENABLED` (default `false`). | `config.py:92` |
| D3 | **Maintenance scheduler ENABLED, weekly.** `MAINTENANCE_SCHEDULER_ENABLED=true`; cadence keeps the default `MAINTENANCE_INTERVAL_SECONDS=604800` (weekly). Off-peak achieved by anchoring the cadence via the deploy/restart time. The `_loop` runs `_tick()` immediately on its first iteration, **then** waits `interval` (`maintenance_scheduler.py:58-68`: `_tick()` at line 62 precedes the `wait_for(..., timeout=interval)` at line 66) — so the **first tick fires ~immediately at `start()`** (container restart) and **every subsequent weekly tick lands at the restart wall-clock hour**. Performing the enabling restart in the off-peak window therefore pins both the immediate first tick and all recurring weekly ticks off-peak. | `config.py:100-101`, `maintenance_scheduler.py:45,58-68` |
| D4 | **AGENTS.md refresh = event-on-DIRECTIVES-change, local (post-commit), NOT CI.** Add a `generate_projections.py --refresh-trusted` call to the existing local post-commit path. | `generate_projections.py:127-143,155`, `.git/hooks/post-commit → sync-corpus.sh` |
| D5 | **Retire launchd as primary.** `launchctl unload` the plist on every machine + neutralize it (move out of `~/Library/LaunchAgents/`) so it cannot double-commit. GitHub Actions is the machine-independent runner for the repo-git half. | live `launchctl list` shows it loaded; `com.kamen.memory-weekly-review.plist` |
| D6 | **CI needs only the `CLAUDE_CORPUS_MCP_URL` secret; no MCP auth token.** `/mcp` bypasses `ApiKeyAuthMiddleware` (`_PUBLIC_PREFIXES`, returns `call_next` before the key check). | `middleware/auth.py:16,24` |
| D7 | **`ALLOW_REMOTE_WRITES=true` is a precondition** for the CI corpus-sync step (write tools are guarded). Implied already true (the live local post-commit sync mirrors successfully today) but must be confirmed live (§8). | `guards.py:26-38`, `server.py` corpus handlers, `config.py:137` |
| D8 | **CI cron time = `0 3 * * 1` (Mondays 03:00 UTC).** 05:00/06:00 Europe/Sofia (EEST/EET), off-peak + outside harness working hours; ±1h DST drift explicitly accepted (upkeep cadence is not time-critical). | GitHub cron is UTC-only; `config.py:95` `Europe/Sofia` |
| D9 | **CI bot is the sole committer** of `spark-candidates.md` + the stamp. launchd is fully retired; no local fallback writes commits. | research §4.2/§4.5 |
| D10 | **The scheduled CI path must FAIL LOUD** on brain-unreachable or any sync error (non-zero exit), unlike the fail-open local interactive path. | `weekly_review.py:79-90` swallows + returns 0; `sync_corpus.py:104-111` returns failure count |
| D11 | **Dead-man's-switch = a second GitHub Actions cron** with **two** assertions: (a) repo-git half — fails when the DIRECTIVES "Last reviewed" stamp age exceeds cadence + grace; (b) server half (CGAP-P03 / SGAP-001) — fails when the server scheduler's **last maintenance tick** is older than `interval × 1.5`, read via a dedicated **last-tick surface** (see WS5 + the required runtime step below), since the stamp (CI-written) cannot detect a dead **server** scheduler. Either failing → red → GitHub failure email. **Required runtime addition (SGAP-001):** the `list_workflow_runs`/`check_job_status` route originally named for the server half is **rejected** — maintenance jobs live only in `ops.job_manifests` (`maintenance_scheduler.py:77-90` → `manifest_writer.py:30-32`; `job_worker.py` only `update_job_state`s the manifest), and the `integrity_audit`/`compaction` workflows write **no** `ops.workflow_runs` row (`workflows/integrity_audit.py:24-93`), whereas `list_workflow_runs` reads **`ops.workflow_runs`** (`server.py:3357-3394`); the two are different tables, so the server half would be green/red for reasons unrelated to the scheduler. Instead, the maintenance scheduler must record `last_tick_utc` (a tiny upsert keyed by scheduler name, e.g. `ops.scheduler_heartbeats`) at the end of `_tick` (alongside `maintenance_scheduler_tick_complete`, `maintenance_scheduler.py:81`), surfaced by a new **read-only MCP tool `get_scheduler_heartbeat`** reachable on the public `/mcp` with no token (`middleware/auth.py:16,24`). This is the single code item the plan mandates; it is sequenced before WS5 validation (§6) and confirmed live (§8.5). | research §5/CGAP-007 ("either the GH cron **or the server scheduler**"); SGAP-001 |

## 4. In/Out app-settings summary (live changes)

| App setting | Current default | Target | Restart needed? |
| --- | --- | --- | --- |
| `MAINTENANCE_SCHEDULER_ENABLED` | `false` (`config.py:100`) | `true` | **Yes** — read once at startup (`server.py:6665`) |
| `COMPACTION_ENABLED` | `false` (`config.py:88`) | `false` now → `true` after one clean cycle | **Yes** — captured into the scheduler's `Settings` at startup (`maintenance_scheduler.py:43`); each tick derives `dry_run` from that captured value (`:71`), so a flip only takes effect after a restart |
| `INGESTION_SCHEDULER_ENABLED` | `false` (`config.py:92`) | unchanged (`false`) | n/a |
| `ALLOW_REMOTE_WRITES` | `false` (`config.py:137`) | confirm `true` (implied already) | Read per call in guard; no restart |

---

## Workstream 1 — Server-side maintenance (enable MaintenanceScheduler)

**Problem (evidence).** Integrity audit + compaction is server-capable but disabled: `maintenance_scheduler_enabled = False` (`config.py:100`); wired at startup only when the flag is on (`server.py:6663-6669`). Job types are registered (`server.py:6646-6647`: `integrity_audit`, `compaction`) and the dispatcher runs them. Real compaction additionally requires `compaction_enabled` because `_tick` sets `dry_run = not compaction_enabled` (`maintenance_scheduler.py:71,78`). The `_loop` is pure interval, no wall-clock anchor (`maintenance_scheduler.py:58-68`). Maintenance enumerates real repos via `_REAL_REPOS_SQL` excluding only `mawf%`/`repo-%`/`idx-%` prefixes (`maintenance_scheduler.py:19-25`) — so harness-registered real repos (e.g. `mcp-agents-workflow`) are included. There is **no `max_per_tick`** cap on maintenance (unlike ingestion's `config.py:97`); each tick enqueues up to `2 × real-repo count` jobs, deduped per (repo,tool) by `_enqueue_if_absent` (`maintenance_scheduler.py:83-89`), drained by the single serialized worker (`job_dispatcher_max_concurrent=1`, `config.py:114`). `ops.job_manifests` is shared with the harness, which `create_job`s `run_repo_ingestion_workflow` on every push — serialization keeps queue correctness but not latency.

**Exact change (no code; Azure app settings + restart).**
1. Set app settings on the deployed app:
   - `MAINTENANCE_SCHEDULER_ENABLED=true`
   - `COMPACTION_ENABLED=false` (D1; dry-run first cycle)
   - Leave `INGESTION_SCHEDULER_ENABLED` unset/`false` (D2).
   `az webapp config appsettings set -g workflow-orch-rg -n memory-knowledge --settings MAINTENANCE_SCHEDULER_ENABLED=true COMPACTION_ENABLED=false`.
2. **Off-peak anchor (D3):** restart the container at an off-peak hour outside harness working hours (~03:00–05:00 Europe/Sofia). The `_loop` ticks immediately on its first iteration then sleeps `interval` (`maintenance_scheduler.py:58-68`; `_tick()` at line 62 runs before `wait_for(..., timeout=interval)` at line 66), so the **first tick fires ~immediately at this restart** and each subsequent weekly tick (every 604800s) lands at the restart wall-clock hour — pinning the cadence to the off-peak window. `az webapp restart -g workflow-orch-rg -n memory-knowledge`.
3. No repo file changes; no `config.py` default changes (additive/non-breaking).

**Acceptance criteria (testable).**
- After restart, logs `maintenance_scheduler_started interval=604800` (`maintenance_scheduler.py:46`).
- One tick logs `maintenance_scheduler_tick_complete repos=<N> enqueued=<E> compaction_dry_run=true` (`maintenance_scheduler.py:81`); `E ≤ 2 × N`; no dup (repo,tool).
- One `integrity_audit` job per real repo reaches terminal; one dry-run `compaction` job per real repo runs with `compaction_dry_run=true`.
- The immediate first tick (logged right after `maintenance_scheduler_started`) and each subsequent weekly tick timestamp fall in the off-peak window — proving the restart anchor (because the enabling restart in step 2 was performed off-peak).
- Backlog drains without materially delaying harness `run_repo_ingestion_workflow` latency.

**Edge cases / failure behavior.** Tick exception → caught + logged `maintenance_scheduler_tick_error`, loop continues (`maintenance_scheduler.py:63-64`); a silently-skipped week (or a fully-dead scheduler that stops ticking, `maintenance_scheduler.py:81`) is detected by Workstream 5's **server-half** dead-cadence check, which ages the scheduler-written `last_tick_utc` via the new `get_scheduler_heartbeat` read tool (SGAP-001) — **not** via `list_workflow_runs` (maintenance jobs never write `ops.workflow_runs`; see WS5/D11). The stamp alone does not cover this — the stamp is written by the CI cron, not the server scheduler. Per-repo enqueue error → logged, others continue (`maintenance_scheduler.py:79-80`). Active (repo,tool) → skipped (`_ACTIVE_BY_TOOL_SQL`, `maintenance_scheduler.py:27-31,86-89`). No-origin repos still maintained (intended). Harness contention bounded by serialization + dedup + off-peak anchor.

**Verification.** Tail logs for `maintenance_scheduler_started` post-restart, then `maintenance_scheduler_tick_complete` after the first interval. Rollback: `MAINTENANCE_SCHEDULER_ENABLED=false` + restart (kill switch, `docs/FRESHNESS_AND_MAINTENANCE_PLAN.md:154-155`).

---

## Workstream 2 — GitHub Actions weekly cron (Spark + DIRECTIVES stamp + corpus sync)

**Problem (evidence).** Spark, the stamp bump, and the corpus mirror run today only from the never-fired launchd job (`weekly-review.sh:11-16`). The corpus mirror is a **local** git post-commit hook (`.git/hooks/post-commit → working-agreement/sync-corpus.sh`, gating on `git diff-tree HEAD` of the local commit, `sync-corpus.sh:14-15`) — it does **not** run on GitHub's servers (SGAP-003/CGAP-002). The CI job must call `working-agreement/sync_corpus.py` itself. `weekly_review.py`/`directive_spark.py` call `streamable_http_client(URL)` with no auth header (`weekly_review.py:84`, `directive_spark.py:109`) — `/mcp` is open (`middleware/auth.py:24`), so only `CLAUDE_CORPUS_MCP_URL` is needed (D6). Corpus writes are guarded by `allow_remote_writes` (`guards.py:29`) — D7. `weekly_review.py` swallows errors and `main()` returns 0 (`weekly_review.py:79-90,110,117`) → scheduled path must fail loud (D10). `sync_corpus.py` returns a non-zero failure count on tool error (`sync_corpus.py:100,104-111,138`) — safe to propagate. No existing cron/`workflow_dispatch` in `.github/` (only `ci.yml`).

**Exact change — new workflow `.github/workflows/weekly-upkeep.yml`** (additive; does not touch `ci.yml`):
- **Triggers:** `schedule: - cron: "0 3 * * 1"` (D8) **and** `workflow_dispatch:`.
- **Concurrency:** `group: weekly-upkeep, cancel-in-progress: false`.
- **Permissions:** `contents: write`.
- **Job `upkeep`** (`ubuntu-latest`):
  1. `actions/checkout@v4` `fetch-depth: 0` (sync_corpus reads `HEAD~1`, `sync_corpus.py:50-58`).
  2. `actions/setup-python@v5` `python-version: "3.12"`.
  3. `pip install ".[dev]"` (matches `ci.yml:28`; provides `mcp` client).
  4. **Reachability probe (fail-loud, D10):** derive the health URL from the MCP secret — `CORPUS_HEALTH_URL="${CLAUDE_CORPUS_MCP_URL%/mcp/}/health"` (strip the trailing `/mcp/`, append `/health`; both are public on the same host — `/health` ∈ `_PUBLIC_PATHS`, `/mcp` ∈ `_PUBLIC_PREFIXES`, `middleware/auth.py:8,16`). Then `curl --fail --silent --show-error "$CORPUS_HEALTH_URL"` — non-200 fails the job before any write. (No new secret needed; the derivation is the sole definition of `CORPUS_HEALTH_URL`.)
  5. **Spark + stamp:** `python working-agreement/weekly_review.py --date "$(date -u +%F)"` with env `CLAUDE_CORPUS_MCP_URL=${{ secrets.CLAUDE_CORPUS_MCP_URL }}` and `MK_SPARK_REPOS` = the 8-repo set (matching `weekly-review.sh:8`). The loud-failure guarantee comes from step 4 + step 7's propagated exit (this plan does not modify `weekly_review.py`).
  6. **Commit (sole committer, D9):** `git config user.name "memory-knowledge-bot"` / `user.email "memory-knowledge-bot@users.noreply.github.com"`; `git add working-agreement/DIRECTIVES.md working-agreement/spark-candidates.md`; commit only if staged diff non-empty (set `COMMIT_MADE=1` when a commit is created, else `0`); message `chore(weekly-review): refresh spark candidates + bump Last reviewed (<UTC date>)` (no AI attribution). **Concurrent-edit safety (CGAP-011):** `git pull --rebase origin main` before push; on rejection re-apply the (idempotent, `weekly_review.py:29-31`) stamp on new HEAD and retry (≤3).
  7. **Explicit corpus sync (CGAP-002/SGAP-003):** run `python working-agreement/sync_corpus.py --url "$CLAUDE_CORPUS_MCP_URL"` **only when `COMMIT_MADE=1`**, AFTER the commit (so the `HEAD`/`HEAD~1` orphan diff is taken across exactly this run's directive change, `sync_corpus.py:46-58,123,129-134`); exit propagated (no `|| true`) → guarded/failed upsert fails the job (D7/D10). **No-commit path (CGAP-P02):** when `COMMIT_MADE=0` (e.g. a same-day `workflow_dispatch` re-run where the stamp already equals today's UTC date), **skip** this step — no directive changed this run, so the corpus already mirrors current state from the prior run/local hook. Skipping is correct because running `sync_corpus.py` here would compute orphans against a *prior, unrelated* `HEAD~1` (`sync_corpus.py:129-134`); the upsert-of-current (`sync_corpus.py:123`) would stay correct but the orphan baseline would be wrong. (If a future change must re-sync without a new commit, that re-sync is idempotent for the upsert but is **not** a substitute for the gated path and must not be added here.)
  8. **Surface candidates (CGAP-004):** append count + first 5 `- ` lines from `spark-candidates.md` to `$GITHUB_STEP_SUMMARY` (matches `weekly_review.py:71-76`); job-summary only (no auto-issue) this rollout.
- **Secrets:** `CLAUDE_CORPUS_MCP_URL` = `https://memory-knowledge.azurewebsites.net/mcp/`. No token (D6). No secrets in repo.

**Acceptance criteria (testable).**
- `workflow_dispatch` on a healthy brain: green; exactly one bot stamp/candidates commit; "Last reviewed" advances.
- `corpus_query` for a changed directive returns new text (or sync logs `status=success`, `sync_corpus.py:112`).
- Brain unreachable → **red** (probe), failure email; no green no-op (D10).
- Racing human DIRECTIVES commit → stamp lands, both commits present, no conflict marker.
- Job summary shows candidate count (CGAP-004).
- **Same-day re-dispatch (CGAP-P02):** a second `workflow_dispatch` on the same UTC date makes no commit (`COMMIT_MADE=0`) → the corpus-sync step is **skipped**, the job is still green, and `corpus_query` for every directive still returns current text (no stale orphan-deactivation).

**Edge cases / failure behavior.** `ALLOW_REMOTE_WRITES=false` → sync `status:"error"` → non-zero exit → red (fix = D7). No directive change *on a new UTC date* → stamp bumps date → commit made (`COMMIT_MADE=1`) → corpus upsert idempotent + no orphans. No directive change *on the same UTC date* (re-dispatch) → `COMMIT_MADE=0` → corpus-sync skipped (CGAP-P02), still green. Push race exhausts retries → red, no clobber. DST → ±1h accepted (D8).

**Verification.** `workflow_dispatch` after merge; confirm green + commit + corpus. Cost (CGAP-009): one weekly ~1–2min job + heartbeat — within free Actions minutes.

---

## Workstream 3 — AGENTS.md refresh on DIRECTIVES change (local)

**Problem (evidence).** AGENTS refresh rewrites each trusted project's **local** `AGENTS.md` in place (`generate_projections.refresh_trusted`, `generate_projections.py:127-143`), reading the trusted list from local `~/.codex/config.toml` (`generate_projections.py:115-124`). It does not commit/push and cannot run on a CI runner (no checkout, no Codex config) — infeasible (research §7). Today it runs only inside the never-fired `weekly_review.py:101-104`. The corpus mirror already fires locally on every DIRECTIVES-touching commit (`sync-corpus.sh:14-15`); AGENTS refresh should ride the same local event.

**Exact change — extend the local post-commit path** (additive; one repo file). In `working-agreement/sync-corpus.sh`, after the corpus-sync invocation (`sync-corpus.sh:23`) and **before the final `exit 0` (line 24)**, add a fail-open guarded call (matching the executable fail-open pattern at `sync-corpus.sh:20-23`):
- `"$PY" "$REPO_ROOT/working-agreement/generate_projections.py" --refresh-trusted 2>/dev/null || true`
- Gated by the same `grep -q "^working-agreement/DIRECTIVES.md$"` condition at `sync-corpus.sh:15` (the script already exits 0 before reaching line 23 for non-DIRECTIVES commits, so the new call inherits that gate). The `--refresh-trusted` flag + default `--codex-config ~/.codex/config.toml` exist (`generate_projections.py:155-159`). It reads the trusted list from `~/.codex/config.toml` (`codex_trusted_projects`, `generate_projections.py:115-124`) and only rewrites generator-produced files (skips hand-authored via `refresh_agents_file → None`, `generate_projections.py:108-112,137-139`).

**Bounded-staleness rationale.** Trusted repos not checked out on the editing machine keep a stale generated `AGENTS.md` until that machine next edits DIRECTIVES. Low-harm: Claude gets live injection (unaffected); Codex re-reads `AGENTS.md` per session — staleness bounded to the gap until the machine's next DIRECTIVES change.

**Acceptance criteria.** After a DIRECTIVES commit on machine M, generated `AGENTS.md` under M's trusted projects show new content; `--refresh-trusted` prints `refreshed:` for generated, `skip(not-generated)` for hand-authored (`generate_projections.py:134-141`). A non-DIRECTIVES commit triggers no refresh (gated).

**Edge cases.** Missing venv/Codex config → fail-open exit 0 (`codex_trusted_projects → []`, `generate_projections.py:117-118`); never blocks the commit. Hand-authored `AGENTS.md` never clobbered.

**Verification.** Trivial DIRECTIVES edit+commit on each machine; confirm `refreshed:` lines + updated content.

---

## Workstream 4 — Retire launchd

**Problem (evidence).** `com.kamen.memory-weekly-review` is **loaded** (live `launchctl list`, no PID) but has **never fired** — no `/tmp/mk-weekly-review.log`, stamp stuck `2026-06-19` (`DIRECTIVES.md:4`). The plist runs `weekly-review.sh` Mondays 09:00 local (`com.kamen.memory-weekly-review.plist:10-11`), which commits stamp+candidates (`weekly-review.sh:13-16`). Left loaded with the new CI cron, it could double-commit (CGAP-006). Its five tasks are all re-homed (CGAP-012).

**Re-homing checklist (verify each has a live non-launchd trigger):**
| launchd-only task | Re-homed to |
| --- | --- |
| (a) Directive Spark (`weekly_review.py:60-66`) | GitHub Actions cron (WS2) |
| (b) Integrity audit + compaction (`weekly_review.py:83-90`) | Server `MaintenanceScheduler` (WS1) |
| (c) DIRECTIVES stamp + commit (`weekly_review.py:106-109`, `weekly-review.sh:13-16`) | GitHub Actions cron (WS2) |
| (d) AGENTS refresh (`weekly_review.py:92-104`) | Local post-commit on DIRECTIVES change (WS3) |
| (e) Surfacing Spark candidates (`weekly_review.py:67-78`) | GitHub Actions job summary (WS2 step 8) |

**Exact change (operator runtime, every machine — home + office):**
1. `launchctl unload ~/Library/LaunchAgents/com.kamen.memory-weekly-review.plist`
2. Verify: `launchctl list | grep memory` empty.
3. Neutralize: `mv ~/Library/LaunchAgents/com.kamen.memory-weekly-review.plist ~/Library/LaunchAgents/com.kamen.memory-weekly-review.plist.retired` (repo copy stays as docs, out of load path). No local fallback committer (D9).
4. Update `working-agreement/SETUP-weekly-review.md` to mark launchd retired + point to the two schedules (doc-only).

**Acceptance criteria.** On every machine: `launchctl list | grep memory` empty; no plist in the load path. Across any week: exactly one stamp/candidates commit (CI bot's). Dry-run of each re-homed task (a)–(e) confirms its new trigger.

**Edge cases.** Until unload, a machine's launchd could in principle double-commit — mitigated: it has never fired and unload is the first rollout step per machine (§6). No data risk (server dedup); only a duplicate git commit, eliminated by unload.

**Verification.** Run the three checklist commands on home + office; record output.

---

## Workstream 5 — Dead-man's-switch / observability

**Problem (evidence).** The real failure was a schedule that **never fired** — no signal (no log, stamp frozen `2026-06-19`). GitHub emails only on *failed* runs; a run that never happens emits nothing. The server logs `maintenance_scheduler_tick_complete` (`maintenance_scheduler.py:81`) only when it ticks. Need an independent dead-cadence detector.

**Exact change — new workflow `.github/workflows/upkeep-heartbeat.yml`** (additive; independent of `weekly-upkeep.yml`):
- **Trigger:** `schedule: - cron: "0 12 * * 1"` (Mondays 12:00 UTC, 9h after the upkeep run so a fresh stamp is visible) **and** `workflow_dispatch:`.
- **Permissions:** `contents: read`.
- **Job — two independent assertions, both must pass (any failure → red → email):**
  1. **Repo-git half (stamp freshness).** Checkout (`fetch-depth: 1`), parse the `<!-- Last reviewed: YYYY-MM-DD -->` line (`DIRECTIVES.md:4`, regex shape per `weekly_review.py:26`) and **exit non-zero** when `today - stamp_date > 9 days` (7d cadence + 2d grace). Catches a stopped CI cron (WS2).
  2. **Server half (maintenance liveness, CGAP-P03 / SGAP-001).** Assert the server `MaintenanceScheduler` is still ticking — the stamp does **not** cover this because the stamp is written by the CI cron, never by the server scheduler, so a dead server scheduler with a healthy cron leaves the stamp fresh. **Mechanism (locked, feasible):** read the scheduler's **last-tick timestamp** via a dedicated read-only MCP tool `get_scheduler_heartbeat` on the public `/mcp` endpoint (no token, same bypass as every tool, `middleware/auth.py:16,24`) using `CLAUDE_CORPUS_MCP_URL`, and **exit non-zero** when `last_tick_utc` for scheduler `maintenance_scheduler` is older than `maintenance_interval_seconds × 1.5` (~10.5 days), or absent. **Required runtime addition (single code item this plan mandates — sequenced in §6, confirmed live in §8.5):** (i) the maintenance scheduler writes `last_tick_utc` at the end of `_tick` (a tiny upsert keyed by scheduler name, e.g. `ops.scheduler_heartbeats`, alongside `maintenance_scheduler_tick_complete`, `maintenance_scheduler.py:81`); (ii) a new read-only MCP tool `get_scheduler_heartbeat` returns that timestamp. **Rejected mechanism + reason (SGAP-001):** the earlier `list_workflow_runs`/`check_job_status` for `run_integrity_audit_workflow` is **not** usable — maintenance jobs are written only to `ops.job_manifests` (`maintenance_scheduler.py:77-90` → `manifest_writer.py:30-32`) and executed via `execute_job`, which only `update_job_state`s the manifest (`job_worker.py:39,43,63,83,94`); `integrity_audit.run` writes **no** `ops.workflow_runs` row (`workflows/integrity_audit.py:24-93`). But `list_workflow_runs` reads **`ops.workflow_runs`** keyed by `repository_key` (`server.py:3357-3394`), and `check_job_status` needs a `job_id` the runner cannot know (`server.py:884-905`). No existing MCP tool reads `ops.job_manifests` by job_type/age (`grep job_manifests server.py` = 0), and `/health` (`db/health.py:23-24`), `/ready`, `/metrics` (`job_transitions_total` is an unlabeled monotonic counter, not incremented in the dispatcher path; the dispatcher calls the **undecorated** `integrity_audit.run`, so `tool_calls_total` does not move either) carry no ageable maintenance-tick datum. Hence the dedicated last-tick surface is required; until it ships, the server half is **not** covered (do not substitute `list_workflow_runs`).
- Together these are the dead-man's-switch for **both** halves: stamp-staleness catches the repo-git cron, last-tick-age catches the server scheduler. This satisfies research CGAP-007's "either the GH cron **or the server scheduler** stops ticking" criterion (`research.md:227`).

**Acceptance criteria.**
- **Repo-git half:** if the upkeep cron stops (stamp >9 days old), the next heartbeat run is **red** + emails within one grace window. Tested via `workflow_dispatch` against an artificially old stamp (red) and a fresh stamp (green).
- **Server half (CGAP-P03 / SGAP-001):** if the server `MaintenanceScheduler` stops ticking while the CI cron keeps stamping (stamp stays fresh), the last-tick-age assertion still goes **red** within one grace window. Tested by calling `get_scheduler_heartbeat` directly: with the maintenance scheduler disabled (`MAINTENANCE_SCHEDULER_ENABLED=false`, so `last_tick_utc` for `maintenance_scheduler` goes stale/absent) → red, and with it ticking (recent `last_tick_utc`) → green. The test must confirm `get_scheduler_heartbeat` returns the maintenance scheduler's `last_tick_utc` over the public `/mcp` with URL only (no token) — i.e. the required runtime addition is deployed (§8.5) before this AC can pass.

**Edge cases.** Heartbeat's own non-firing is bounded: two independent schedulers (server + upkeep cron) would both have to silently die *and* GitHub cron fail — acceptable last-resort; GitHub surfaces disabled-schedule warnings. DST irrelevant (date comparison).

**Verification.** `workflow_dispatch` the heartbeat with stale and fresh stamps; confirm red/green.

---

## 5. How off-peak is achieved (locked)

- **Maintenance (server):** not directly schedulable (`_loop` is interval-only with no wall-clock anchor, `maintenance_scheduler.py:58-68`; `daily_at` exists only for ingestion, `config.py:94`). **Mechanism (D3):** perform the enabling `az webapp restart` in the off-peak window. The `_loop` ticks immediately then sleeps `interval` (line 62 before line 66), so the first tick fires at the restart and every subsequent weekly tick lands at the restart wall-clock hour — pinning the cadence to that off-peak hour. If an unrelated restart re-phases it, serialization (`max_concurrent=1`) keeps any-hour ticking correctness-safe; re-anchor via another off-peak restart.
- **Repo-git cron:** off-peak via UTC cron `0 3 * * 1` (D8), ±1h DST accepted.

## 6. Sequencing & rollout

Order so no window lets both launchd and the CI cron commit, and dry-run precedes real compaction:
1. **WS4 first (retire launchd) on every machine** — removes the only other git committer before the CI cron is armed.
2. **WS3 (local AGENTS refresh hook)** — edit `working-agreement/sync-corpus.sh` (commit via a feature branch per repo policy).
3. **WS1 (server maintenance)** — set `MAINTENANCE_SCHEDULER_ENABLED=true`, `COMPACTION_ENABLED=false`; restart in off-peak window (anchors the tick).
4. **WS2 (weekly cron)** — add `CLAUDE_CORPUS_MCP_URL` secret; merge `weekly-upkeep.yml`; `workflow_dispatch` once to validate.
4b. **Server last-tick surface (SGAP-001 prerequisite for WS5 server half)** — implement + deploy the maintenance-scheduler `last_tick_utc` write and the read-only `get_scheduler_heartbeat` MCP tool; restart the app; confirm `get_scheduler_heartbeat` returns a recent `maintenance_scheduler` tick (§8.5). This is a code change (unlike WS1's app-settings-only), so it ships via a feature branch + redeploy before WS5 validation.
5. **WS5 (heartbeat)** — merge `upkeep-heartbeat.yml`; `workflow_dispatch` to validate (server half depends on step 4b being live).
6. **Observe one clean maintenance cycle** (one tick `compaction_dry_run=true`, integrity audits terminal, no `*_tick_error`).
7. **Follow-up — real compaction (D1):** after step 6 clean, `COMPACTION_ENABLED=true` + restart in off-peak; verify next tick `compaction_dry_run=false` + consolidation written.

Mechanism per step: Azure app-setting + restart → 3, 7. CI (workflow + secret) → 4, 5. Local repo edit → 2. Per-machine runtime → 1.

## 7. Rollback

- **Maintenance:** `MAINTENANCE_SCHEDULER_ENABLED=false` + restart (kill switch, `docs/FRESHNESS_AND_MAINTENANCE_PLAN.md:154-155`). Revert real→dry: `COMPACTION_ENABLED=false` + restart.
- **Cron/heartbeat:** disable in Actions tab or revert the `.yml` commit. No state to unwind (idempotent stamp + idempotent corpus upserts).
- **AGENTS hook:** revert the one-line `sync-corpus.sh` addition (fail-open; never blocked anything).
- **launchd:** re-load only as a deliberate fallback (not recommended; re-introduces double-commit).

## 8. Required live confirmations (operator must check; unverifiable from repo)

1. **`ALLOW_REMOTE_WRITES=true`** on the deployed app (D7) — `az webapp config appsettings list -g workflow-orch-rg -n memory-knowledge`. If false, the CI sync step correctly fails red.
2. **GitHub Actions runner egress** to `https://memory-knowledge.azurewebsites.net` — assumed public HTTPS; if blocked, the probe fails red (not green-no-op).
3. **Current live values** of `MAINTENANCE_SCHEDULER_ENABLED` / `COMPACTION_ENABLED` (defaults false) before/after the set.
4. **Restart timing** — perform the enabling (step 3) and real-compaction (step 7) restarts in the off-peak window (D3).
5. **`get_scheduler_heartbeat` reachable + fresh (SGAP-001)** — after the §6 step 4b runtime addition is deployed, calling `get_scheduler_heartbeat` over the public `/mcp` (URL only, no token) returns a recent `last_tick_utc` for scheduler `maintenance_scheduler`. The WS5 server-half assertion is satisfiable only once this returns a real tick; until then the server half is uncovered (do not fall back to `list_workflow_runs`).

## 9. Test plan (consolidated)

| Test | How | Pass condition |
| --- | --- | --- |
| Maintenance enabled | restart with flag; tail logs | `maintenance_scheduler_started` then `…tick_complete … compaction_dry_run=true` |
| Dry-run honored | tick log + a compaction job's params | `compaction_dry_run=true`; no consolidation written |
| Enqueue bound | count jobs after a tick | `enqueued ≤ 2 × repos`; no dup (repo,tool) |
| CI happy path | `workflow_dispatch` (healthy) | green; one bot commit; stamp advances; `corpus_query` new text |
| CI fail-loud (brain down) | `workflow_dispatch` bad/blocked URL | red + failure email; no commit-as-success |
| CI fail-loud (writes blocked) | run with `ALLOW_REMOTE_WRITES=false` (test) | sync step red |
| Concurrent edit | human DIRECTIVES commit during run | stamp lands, both commits, no conflict |
| Same-day re-dispatch (CGAP-P02) | `workflow_dispatch` twice same UTC date | 2nd run: no commit, corpus-sync skipped, green; `corpus_query` still current |
| Reachability probe URL (CGAP-P01) | inspect derived `CORPUS_HEALTH_URL` | resolves to `…/health`; 200 on healthy brain, job red on non-200 |
| Candidate surfacing | run with ≥1 candidate | job summary shows count + lines |
| AGENTS local refresh | DIRECTIVES commit on each machine | `refreshed:` lines; updated AGENTS.md |
| launchd retired | `launchctl list \| grep memory` per machine | empty; plist out of load path |
| Single committer | `git log` over a week | exactly one bot stamp/candidates commit |
| Dead-man's-switch (repo-git half) | `workflow_dispatch` heartbeat stale vs fresh stamp | red on stale, green on fresh |
| Dead-man's-switch (server half, CGAP-P03 / SGAP-001) | `workflow_dispatch` heartbeat with maintenance disabled (stamp still fresh); heartbeat reads `get_scheduler_heartbeat` (NOT `list_workflow_runs`) | red on stale/absent `last_tick_utc`, green when ticking; requires the §6 step 4b runtime surface deployed |
| Server last-tick surface live (SGAP-001) | call `get_scheduler_heartbeat` over `/mcp` (URL only) | returns recent `last_tick_utc` for `maintenance_scheduler`; reachable with no token |

## 10. Open questions

None blocking. All decisions locked in §3 (incl. the approved defaults: dry-run-first compaction D1, freshness disabled D2, maintenance weekly off-peak D3, AGENTS event-on-change local D4, launchd retired D5). The three previously-open user decisions resolve to D2/D1/D3. Items requiring action outside the repo are the five live confirmations in §8 (operator checks, not design choices).

**One required runtime addition (SGAP-001, satisfaction pass).** Unlike the rest of the plan (app-settings + CI YAML + a one-line hook edit, no brain code), the WS5 **server-half** dead-cadence check requires a small brain code change: the maintenance scheduler must record `last_tick_utc` and a read-only MCP tool `get_scheduler_heartbeat` must surface it (D11, WS5, §6 step 4b, §8.5). This is mandated because the originally-named `list_workflow_runs`/`check_job_status` mechanism reads `ops.workflow_runs` while maintenance jobs only ever touch `ops.job_manifests` — the server half would otherwise pass green while observing nothing (the exact original failure mode). **User option:** if the user prefers not to add this code, the only alternative is to **scope the server-half dead-cadence detection OUT** with an explicit accepted limitation (a silently-dead maintenance scheduler with a healthy CI cron would go undetected) — but that re-opens research CGAP-007 / R-OBSERV.O3, so the plan locks the in-scope fix.

### Critical files
- `.github/workflows/weekly-upkeep.yml` (new — WS2)
- `.github/workflows/upkeep-heartbeat.yml` (new — WS5)
- `working-agreement/sync-corpus.sh` (edit — WS3)
- `working-agreement/com.kamen.memory-weekly-review.plist` (retire — WS4, runtime unload)
- `src/memory_knowledge/jobs/maintenance_scheduler.py` (behavior reference for app-setting-only WS1; **+ SGAP-001 runtime addition:** record `last_tick_utc` in `_tick`)
- `src/memory_knowledge/server.py` (**SGAP-001 runtime addition:** new read-only MCP tool `get_scheduler_heartbeat`)
- `.github/workflows/upkeep-heartbeat.yml` (WS5 server half calls `get_scheduler_heartbeat`, NOT `list_workflow_runs`)
