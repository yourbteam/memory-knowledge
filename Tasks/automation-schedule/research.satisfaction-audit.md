# Satisfaction Audit (DEPTH gate) — Automation schedule for second-brain upkeep

Audited document: `Tasks/automation-schedule/research.md`
Gate: **requirements-satisfaction-gap-loop** (depth). Upstream passed: internal-readiness (doc-gap-closure) + breadth (requirements-coverage, `research.coverage-audit.md`, 27 reqs / 60 obligations, converged).
Grounding repos:
- Brain: `/Users/kamenkamenov/memory-knowledge` (`src/memory_knowledge/...`, `working-agreement/...`, `.git/hooks/...`, `.github/workflows/ci.yml`).
- Harness (co-tenant): `/Users/kamenkamenov/mcp-agents-workflow` (`src/workflow_orch/...`).

This loop asks: for each requirement the doc **addresses**, will it actually **hold end-to-end** against the real runtime, the stored data, and the sibling harness it must interoperate with — reading into un-cited code? Evidence is cited `path:line` and is drawn from the surrounding system, not the document.

Requirement set reused from the coverage pass (same `req_id`s). The deterministic units are the addressed requirements plus the implied-essential satisfaction invariants and harness interop invariants that only surface at depth.

---

## Requirement Inventory (reused + depth-only additions)

| req_id | requirement | type | source (quoted) |
| --- | --- | --- | --- |
| R-INTEG | Integrity audit + compaction run recurringly | stated | research.md:20 |
| R-FRESH | Freshness re-ingest addressed | stated | research.md:21 |
| R-SPARK | Directive Spark runs recurringly | stated | research.md:22 |
| R-AGENTS | AGENTS.md refresh addressed | stated | research.md:23 |
| R-STAMP | DIRECTIVES stamp + commit runs recurringly | stated | research.md:24 |
| R-CORPUS | Corpus sync stays covered | stated | research.md:25 |
| R-CAPTURE | Auto-capture scheduling status addressed | stated | research.md:26 |
| R-NOMANUAL | No manual triggers | stated | research.md:4 |
| R-MACHINEINDEP | Machine-independent | stated | research.md:4-6 |
| R-MULTIMACHINE | Correct across home/office machines | stated | research.md:5 |
| R-NOINCIDENT | Not re-arm the ingestion incident | stated | research.md:6 |
| R-SHAREDINFRA | Not overwhelm shared single-worker infra | stated | research.md:5 |
| R-OBSERV | Failed/dead schedules observable | implied | coverage R-OBSERV |
| R-SECRETS | CI secrets safe | non-functional | Guard Rail |
| R-IDEMPOTENT | No double-run across schedulers | implied | research.md:179 |
| R-RETIRE | Behaviour when launchd retired | boundary | research.md §4.5 |
| R-COST | CI minute cost bounded | non-functional | research.md:181 |
| R-CADENCE | Timezone/cadence correctness | non-functional | research.md:180 |
| R-BACKCOMPAT | Coexist with post-commit hook + plist | non-functional | research.md §1,§3 |
| R-NEG-BRAINDOWN | Scheduler enabled but brain down | negative | research.md:178 |
| R-NEG-CIREACH | CI cannot reach brain MCP | negative | research.md:209 |
| R-NEG-RUNNING | Job already running at tick | negative | research.md §4.1 |
| R-NEG-MIDFLIGHT | DIRECTIVES edited during refresh/CI run | negative | research.md:107-112 |
| R-NEG-NOORIGIN | Repo with no origin_url | negative | research.md:182 |
| R-NEG-CONCURRENT | Concurrent maintenance + dispatcher | negative | research.md:174 |
| R-AUTH | MCP auth token for CI-originated calls | implied (gates R-SPARK on CI) | research.md:205,208 |
| **INV-DISPATCH-COTENANT** | The brain's job dispatcher (`ops.job_manifests`, single worker) is **shared with the workflow-orch harness**; enabling maintenance must not starve harness jobs nor be mis-estimated by ignoring harness-registered repos | invariant (depth-only) | harness `run_repo_ingestion_workflow` → `create_job` (server.py:663-708); harness submits on `workflow.push` (mcp-agents-workflow `mcp_server.py:8527`) |
| **INV-MCP-OPEN** | The deployed brain's `/mcp` endpoint is **unauthenticated** (the read/write key for "does CI need a token"); the write tools are instead gated by `allow_remote_writes` | invariant (depth-only) | auth.py:16,24 (`/mcp` bypasses auth) vs guards.py:29 (`allow_remote_writes`) |
| **INV-CORPUS-WRITEGUARD** | The CI corpus-sync step's success depends on the deployed brain having `allow_remote_writes=true`; otherwise `run_corpus_upsert_workflow` returns `status:"error"` | invariant (depth-only) | server.py:409,444 guard; guards.py:29; config.py:137 |

---

## End-to-End Trace Table

| req_id | trace (trigger → … → surfaced result) | runtime/data evidence (path:line / value) | holds? |
| --- | --- | --- | --- |
| R-INTEG | weekly tick → `_enqueue_if_absent("integrity_audit"/"compaction")` → `create_job` into `ops.job_manifests` → dispatcher claims `LIMIT max_concurrent FOR UPDATE SKIP LOCKED` → `JOB_TYPE_REGISTRY[job_type]` runs the workflow → integrity/compaction effect on stored data; `maintenance_scheduler_tick_complete` logged | scheduler enqueue maintenance_scheduler.py:77-78,81; job types **registered** server.py:6646-6647 (`integrity_audit`, `compaction`); dispatcher lookup dispatcher.py:138-143; claim query dispatcher.py:120-135; compaction honors `dry_run` from job_params compaction.py:32,41; startup gate server.py:6665-6669 | **holds** (mechanism real end-to-end) |
| R-INTEG (dry-run gate) | `dry_run = not compaction_enabled` → compaction enqueued dry-run unless `compaction_enabled=1` | maintenance_scheduler.py:71; compaction.py:32 default `dry_run=True`; config.py:88 `compaction_enabled=False` | holds; doc states the two-flag requirement correctly (research.md:67-72) |
| R-FRESH | kept disabled; enumeration `WHERE origin_url IS NOT NULL` + sentinel-only exclusion; bootstrap full-ingest for never-ingested | ingestion_scheduler.py:31,38-43,188; config.py:92 `ingestion_scheduler_enabled=False` | holds (disabled is the chosen end-state) |
| R-SPARK | CI cron → `directive_spark._run()` → `streamable_http_client(URL)` → `call_tool(get_finding_pattern_summary,…)` (read-only telemetry) → write `spark-candidates.md` | directive_spark.py:34-37,66,109; `/mcp` open (auth.py:24) so read tools reachable w/o token | holds **iff** CI is implemented (greenfield: no cron exists, ci.yml:1-6) |
| R-AGENTS | local on-DIRECTIVES-change → `refresh_trusted(DIRECTIVES, ~/.codex/config.toml)` rewrites generated `AGENTS.md` in each trusted project's **local** working tree (no commit/push) | generate_projections.py:118-143; weekly_review.py:107-115 already calls it; cross-repo CI ruled out (no checkout/config on runner) | holds (local-only) — matches research.md §4.3/§7 |
| R-STAMP | CI cron → `bump_review_stamp` (idempotent `count=1`) → CI commit | weekly_review.py:29-31,116-118; wrapper commit pattern weekly-review.sh | holds iff CI implemented |
| R-CORPUS (local path) | local commit touching DIRECTIVES → `.git/hooks/post-commit` → `sync_corpus.py` → `run_corpus_upsert_workflow`+`corpus_deactivate` | post-commit hook present + gates on `working-agreement/DIRECTIVES.md`; sync_corpus.py:82,93 | holds (local) |
| R-CORPUS (CI path) | **CI** stamp commit runs on GitHub servers → local post-commit hook **does not fire** → corpus stale unless CI calls `sync_corpus.py` explicitly | post-commit is a client-side hook (only fires on the committing machine); CI = GitHub servers | **holds only with the doc's CGAP-002 fix** (explicit CI step). Confirmed correct. New nuance: write-guard precondition → SGAP-003 |
| R-CAPTURE | unchanged `Stop` hook (out of scope) | research.md:26 | holds (scoped-out) |
| R-NOMANUAL | each kept task has a non-manual trigger; freshness is the explicit exception | research.md §4, §4.4 | holds |
| R-MACHINEINDEP | server maintenance on Azure always-on; Spark/stamp on GitHub infra; AGENTS local-on-edit | research.md §3 | holds; AGENTS refresh is per-machine local (acceptable, scoped) |
| R-MULTIMACHINE | launchd retired everywhere; CI sole git committer | research.md §4.5 single-committer | holds **given launchd is actually unloaded** → SGAP-004 (it is currently *loaded*) |
| R-NOINCIDENT | freshness disabled; sentinel guard; allowlist path | ingestion_scheduler.py:38-43; config.py:96 | holds |
| R-SHAREDINFRA | dispatcher serializes (max_concurrent=1); maintenance has **no** enqueue cap; bound = serialization + per-repo dedup | config.py:114; maintenance_scheduler.py (no max_per_tick); _enqueue_if_absent maintenance_scheduler.py:83-89; ingestion cap config.py:97 | partially — doc corrected the false cap claim (research.md:74-81). **But** repo-count estimate ignores harness repos → SGAP-001 |
| R-OBSERV | tick logs; failed CI emails; dead-man's-switch monitor for never-fires | maintenance_scheduler.py:81,63-64; research.md §5/CGAP-007 | holds as a required impl step |
| R-SECRETS | MCP URL in GH secrets; **no MCP token actually needed** (`/mcp` open) | auth.py:24 | holds; secret-set is smaller than doc assumes (R-AUTH) |
| R-IDEMPOTENT | server dedup `_enqueue_if_absent`; git side: CI sole committer | maintenance_scheduler.py:83-89; research.md:179 | holds given launchd unloaded (SGAP-004) |
| R-RETIRE | re-homing checklist; each launchd-only task re-homed | research.md §4.5 | holds **once executed** — launchd still loaded today (SGAP-004) |
| R-COST | one weekly GH run + one monitor | research.md:181 | holds (assertion, within free tier) |
| R-CADENCE | GH cron UTC-only; ±1h DST drift accepted or two cron lines | research.md:180; ingestion tz config.py:95 | holds (decision recorded) |
| R-BACKCOMPAT | post-commit hook unchanged; plist coexistence defined | post-commit hook present; research.md §4.5 | holds |
| R-NEG-BRAINDOWN | server: tick exception logged, week skipped silently → covered by dead-man's-switch; CI: must fail loud | maintenance_scheduler.py:63-64; weekly_review.py:79-90 swallow + `main()` returns 0 | holds **only with** CGAP-008 fail-loud impl + dead-man's-switch |
| R-NEG-CIREACH | reachability probe / non-zero exit required | research.md:178,209 | holds as required CI impl step |
| R-NEG-RUNNING | `_enqueue_if_absent` skips pending/running per (repo,tool) | maintenance_scheduler.py:27-31,86-89; ingestion get_active_job_for_shape ingestion_scheduler.py:204-214 | holds |
| R-NEG-MIDFLIGHT | CI rebase/retry; idempotent stamp | research.md:107-112; weekly_review.py:29-31 | holds (required CI impl step) |
| R-NEG-NOORIGIN | ingestion excludes `origin_url IS NULL`; maintenance does not require origin_url | ingestion_scheduler.py:31; maintenance_scheduler.py:18-25 | holds |
| R-NEG-CONCURRENT | dispatcher serializes; but harness also enqueues to same worker | config.py:114; harness create_job server.py:663-708 (via harness push) | partially → SGAP-001 (harness contention unaddressed) |
| R-AUTH | "does the deployed brain require a token for CI MCP calls?" → **No**: `/mcp` bypasses auth | auth.py:8,16,24 | **doc overstates this as UNVERIFIED/blocking** → SGAP-002 |

---

## Lens Coverage Matrix

Lenses: 1 cross-feature-contract, 2 data-reality, 3 intent-vs-mechanism, 4 e2e-trace, 5 producer/consumer-symmetry (+harness interop), 6 silent-inert/wrong, 7 config/env-dependence, 8 scope-vs-usage.

| req_id | lens | status | evidence |
| --- | --- | --- | --- |
| R-INTEG | 1 | checked | job_type produced (maintenance_scheduler.py:77-78) == consumed key (`JOB_TYPE_REGISTRY` server.py:6646-6647, dispatcher.py:139) |
| R-INTEG | 2 | checked | `_REAL_REPOS_SQL` returns real repos; compaction `dry_run` flows via job_params compaction.py:41 |
| R-INTEG | 3 | checked | intent "recurring upkeep w/o manual trigger" served by interval loop maintenance_scheduler.py:58-68 |
| R-INTEG | 4 | checked | full chain confirmed (trace table) |
| R-INTEG | 5 | checked | producer create_job / consumer dispatcher claim symmetric on job_type, repository_key |
| R-INTEG | 6 | checked | tick exception caught + logged maintenance_scheduler.py:63-64,79-80 (no silent success) |
| R-INTEG | 7 | gap found | requires `maintenance_scheduler_enabled` AND `compaction_enabled` app-settings on the live Azure app — **unverifiable from repo** (SGAP-005, marked) |
| R-INTEG | 8 | checked | server is the always-on locus that actually runs the dispatcher server.py:6653 |
| R-SHAREDINFRA / R-NEG-CONCURRENT | 5 | **gap found** | maintenance enqueues to `ops.job_manifests`; harness also `create_job`s into same table (server.py:663-708) on `workflow.push` → shared single worker; doc never names the harness co-tenant → **SGAP-001** |
| R-SHAREDINFRA | 2 | **gap found** | repo-count drives enqueue volume; harness registers real-prefix repos (`mcp-agents-workflow`, org/repo) NOT excluded by `NOT LIKE 'mawf%'/'repo-%'/'idx-%'` (maintenance_scheduler.py:19-25) → "~8 repos" estimate is a floor, not the real set → **SGAP-001** |
| R-AUTH | 1/7 | **gap found** | doc: "whether the deployed brain requires an auth token … not confirmed … Blocks R-SPARK on CI" (research.md:208). Reality: `/mcp` bypasses auth (auth.py:24) → no token needed → **SGAP-002** |
| R-CORPUS (CI) | 7/6 | **gap found** | CI `run_corpus_upsert_workflow` is write-guarded by `allow_remote_writes` (server.py:409, guards.py:29, config.py:137 default False); if unset on live app, CI sync returns `status:"error"` → corpus silently stale (sync_corpus.py exits non-zero, so visible IF CI propagates exit) → **SGAP-003** (precondition) + marked unverifiable (live app setting) |
| R-CORPUS (CI) | 1 | checked | sync_corpus.py checks `status == "success"` and returns failure count (sync_corpus.py:104-110) → not silently green on tool error; CI must propagate the exit (ties CGAP-008) |
| R-MULTIMACHINE / R-RETIRE / R-IDEMPOTENT | 8 | **gap found** | launchd plist is **currently loaded** (`launchctl list` → `com.kamen.memory-weekly-review`); doc's single-committer / no-dup guarantees presuppose it is unloaded → required runtime step, not yet true → **SGAP-004** |
| R-SPARK | 6 | checked | weekly_review.py swallows spark/consolidation errors & returns 0 (weekly_review.py:79-90,116) → confirms doc CGAP-008 fail-loud requirement is necessary for the CI path |
| R-AGENTS | 8 | checked | refresh_trusted writes only local trees, no commit (generate_projections.py:127-143); CI cannot exercise it (no checkout) → doc's local-only locus is the only viable surface |
| R-AGENTS | 2 | checked | reads `[projects."<path>"]` from `~/.codex/config.toml` (generate_projections.py:118-126) — per-machine data; staleness bound is the per-machine reality the doc scopes |
| R-FRESH / R-NOINCIDENT | 2 | checked | sentinel-only exclusion SQL verified (ingestion_scheduler.py:38-43); A2 guard real |
| R-FRESH / R-NEG-NOORIGIN | 1 | checked | `origin_url IS NOT NULL` filter ingestion_scheduler.py:31; maintenance omits it maintenance_scheduler.py:18 |
| R-NEG-RUNNING | 5 | checked | dedup keys (repository_key, tool_name, state pending/running) symmetric maintenance_scheduler.py:27-31 |
| R-CADENCE | 7 | checked | GH cron UTC vs Europe/Sofia config.py:95 — doc reconciles |
| R-OBSERV | 6 | checked | dead-cadence is the real failure mode (launchd loaded but never fired: no /tmp/mk-weekly-review.log, stamp 2026-06-19) → confirms dead-man's-switch need |
| R-COST/R-SECRETS/R-CAPTURE/R-BACKCOMPAT/R-NOMANUAL/R-MACHINEINDEP/R-STAMP/R-NEG-MIDFLIGHT/R-NEG-CIREACH/R-NEG-BRAINDOWN | 1-8 | checked / n.a. | see trace table; no new depth gaps beyond those listed |

`not applicable`: R-CAPTURE lenses 2/5 (no scheduled data path — event hook, out of scope); R-FRESH lens 5 producer/consumer (disabled — no producer).

---

## Blocker Gap Ledger

| gap_id | severity | req_id | lens | evidence (both sides) | why it breaks the requirement | planned fix (doc edit) | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SGAP-001 | blocker | R-SHAREDINFRA, R-NEG-CONCURRENT, INV-DISPATCH-COTENANT | 5 producer/consumer + harness interop | Maintenance enqueues to `ops.job_manifests` (maintenance_scheduler.py:77-90); **harness** `run_repo_ingestion_workflow` MCP tool does `create_job` into the **same** table (server.py:663-708) and is invoked on every `workflow.push` (mcp-agents-workflow mcp_server.py:8527). Harness repos use real-prefix keys (`mcp-agents-workflow`, org/repo) NOT excluded by maintenance's `NOT LIKE 'mawf%'/'repo-%'/'idx-%'` (maintenance_scheduler.py:19-25). Both share the single serialized worker (config.py:114). | The doc treats the brain as a single-tenant of the dispatcher ("won't stampede the shared B3 worker", research.md:72) and bounds contention to "~8 real repos". It never names the **harness co-tenant**: a maintenance backlog (up to 2×N jobs, draining for hours behind the single worker) delays the harness's post-push ingestion (fire-and-forget, but freshness lags) and the harness's real repos are themselves enumerated for maintenance. The shared-infra invariant is asserted on an incomplete model. | Add a harness-interop note to §4.1/§5: (a) the dispatcher is shared with the workflow-orch harness which also enqueues `run_repo_ingestion_workflow` jobs; (b) maintenance enumerates harness-registered real repos too, so real-repo count ≥ the brain-only ~8; (c) record the contention disposition: serialization + per-repo dedup bound *queue correctness* but not *latency* — harness ingestion can lag behind a maintenance backlog; (d) acceptance: a weekly tick's backlog drains before the harness's typical push cadence is materially delayed, OR off-peak anchoring (restart-time) is used to keep the backlog out of harness working hours. | research.md §4.1 + §5 harness-interop paragraph added | open |
| SGAP-002 | blocker | R-AUTH, R-SECRETS | 1/7 config-dependence | Doc: "Whether the deployed brain requires an auth token for MCP calls (CI secret) — not confirmed from the repo. **Blocks R-SPARK on CI**" (research.md:208); §6.4 open decision. Reality: `ApiKeyAuthMiddleware` lists `/mcp` in `_PUBLIC_PREFIXES` and returns `call_next` before the `mcp_api_key` check (auth.py:16,24,29) — **the MCP endpoint is unauthenticated by design** (comment: "MCP auth is open"). All client scripts already call `streamable_http_client(URL)` with no Authorization header (sync_corpus.py:77, directive_spark.py:109, weekly_review.py:84) and the existing local post-commit sync works. | The requirement is reported as an unresolved blocker/UNVERIFIED, but it is resolvable from the repo: CI needs **no MCP auth token**. Leaving it "blocking R-SPARK on CI" overstates the blocker and would make a plan wait on a non-existent secret. (Residual: a future deployment could front `/mcp` with a gateway — note as the only real risk.) | Edit §6.4 + §7: mark R-AUTH **resolved from the repo** — `/mcp` bypasses `ApiKeyAuthMiddleware` (auth.py:16,24), so no Bearer token is required for CI-originated MCP calls; only `CLAUDE_CORPUS_MCP_URL` is needed. Downgrade from "blocks R-SPARK on CI" to "no token required; re-confirm only if a future gateway fronts /mcp." | research.md §6.4, §7, §4.2 updated | open |
| SGAP-003 | blocker | R-CORPUS.O2, INV-CORPUS-WRITEGUARD | 6 silent-inert + 7 config-dependence | CI corpus-sync calls `run_corpus_upsert_workflow`/`corpus_deactivate` (sync_corpus.py:82,93). Both handlers run `check_remote_write_guard` (server.py:409,444) which returns `status:"error"` when the brain is remote and `allow_remote_writes` is False (guards.py:26-38; config.py:137 default False). On the deployed (remote-DB) brain this is a hard precondition. | The doc's CI corpus-sync fix (CGAP-002) assumes the upsert succeeds; if the live app does not set `allow_remote_writes=true`, every CI sync returns error and the corpus never updates from CI. (Mitigated: `sync_corpus.py` checks `status=="success"` and returns a non-zero failure count, sync_corpus.py:104-110, so it is **not** silently green — *provided* the CI step propagates the exit, which ties to CGAP-008.) | Add to §4.2 corpus-sync bullet: precondition that the deployed brain has `allow_remote_writes=true` (the same setting the existing local post-commit sync already relies on — server.py:409 guards corpus_upsert), and that the CI step must propagate `sync_corpus.py`'s non-zero exit (CGAP-008). Mark the *live value* of `allow_remote_writes` as unverifiable-from-repo (live Azure app setting) but **already implied true** since the existing local hook successfully mirrors today. | research.md §4.2 corpus-sync bullet | open |
| SGAP-004 | blocker | R-MULTIMACHINE, R-RETIRE, R-IDEMPOTENT | 8 scope-vs-usage | Doc's single-committer / no-duplication / no-dead-cadence guarantees presuppose launchd is retired (research.md §4.5: "plist unloaded on every machine"). Live state: `launchctl list` shows `com.kamen.memory-weekly-review` **loaded** on this machine (and the plist fires Mon 09:00 local, plist `StartCalendarInterval`), yet it has **never run** (no `/tmp/mk-weekly-review.log`; DIRECTIVES stamp stuck at `2026-06-19`). | The retirement is a **runtime action that has not happened**. Until `launchctl unload` is executed on every machine, R-RETIRE/R-MULTIMACHINE/R-IDEMPOTENT hold only on paper. The doc records the rule but not that it is an outstanding required runtime step with a verification. | Add to §4.5 a **required implementation step** (not code edit): "Execute `launchctl unload ~/Library/LaunchAgents/com.kamen.memory-weekly-review.plist` on every machine where it is loaded; verify with `launchctl list | grep memory` returning empty." Record current state (loaded but never fired) as the starting condition. | research.md §4.5 required-step note | open |
| SGAP-005 | known-limitation (not blocker) | R-INTEG, R-SPARK | 7 config-dependence | Server schedulers activate only if `maintenance_scheduler_enabled` (+ `compaction_enabled` for real compaction) are set on the **live Azure app settings** (server.py:6665-6669; config.py:88,100). The CI cron + secrets do not yet exist (ci.yml has no `schedule`/`workflow_dispatch`). These are deployment-time facts not inspectable from the repo. | Not a doc defect — it is the intended operator action. Recorded so the plan treats "flip the app setting" and "add the CI workflow + `CLAUDE_CORPUS_MCP_URL` secret" as explicit required implementation steps whose live state is unverifiable here. | Confirm §4.1/§4.2 already frame these as app-setting flips / new CI workflow (they do). Mark live values explicitly **unverifiable from repo**. | research.md §4.1/§4.2 (already framed) + audit note | open→tracked |

Cleanup / known-limitation list:
- SGAP-005 (operator/deploy-time settings; unverifiable from repo — flagged, not a blocker).
- The corpus-sync second-writer (CI + local hook) converges idempotently (upsert + deactivate orphans), already validated in the coverage pass; no new asymmetry at depth (both call the same `run_corpus_upsert_workflow`).

---

## Cycle 1 Plan (gap → exact doc edit; document only)

- SGAP-001 → §4.1 + §5: add harness-co-tenant interop paragraph (shared `ops.job_manifests`, harness `run_repo_ingestion_workflow` contention, harness repos enumerated, latency-not-correctness bound, off-peak/backlog acceptance).
- SGAP-002 → §6.4 + §7 + §4.2: resolve R-AUTH from the repo (`/mcp` open, no token needed; only URL secret).
- SGAP-003 → §4.2 corpus-sync bullet: add `allow_remote_writes=true` precondition + CI-must-propagate-exit; mark live value unverifiable-but-implied-true.
- SGAP-004 → §4.5: add required runtime step `launchctl unload` on every machine + verification; record current loaded-but-never-fired state.
- SGAP-005 → §4.1/§4.2 + §7: mark live app-settings / CI-existence as required impl steps, unverifiable from repo.

## Cycle 1 Edits

(Applied to `research.md` — see below; this section records location + substance.)

| gap_id | edit applied | location |
| --- | --- | --- |
| SGAP-001 | harness co-tenant interop paragraph (dispatcher sharing, repo enumeration, latency bound, acceptance) | research.md §4.1, §5 |
| SGAP-002 | R-AUTH resolved: `/mcp` unauthenticated → no CI token | research.md §6.4, §7, §4.2 |
| SGAP-003 | corpus-sync `allow_remote_writes` precondition + propagate exit | research.md §4.2 |
| SGAP-004 | launchd `launchctl unload` required runtime step + current-state note | research.md §4.5 |
| SGAP-005 | explicit unverifiable-from-repo markers for live app settings / CI existence | research.md §4.1, §7 |

## Cycle 1 Validation

Re-verified each edit against the surrounding system:
- SGAP-001: harness `create_job` into `ops.job_manifests` re-confirmed (server.py:663-708) and harness invocation on push (mcp-agents-workflow mcp_server.py:8527); maintenance enumeration prefixes re-read (maintenance_scheduler.py:19-25) — harness keys genuinely not excluded.
- SGAP-002: re-read auth.py:8,16,24,29 — `/mcp` returns `call_next` before the `mcp_api_key` check; clients send no header (sync_corpus.py:77). Resolution accurate.
- SGAP-003: re-read guards.py:26-38 + server.py:409,444 + config.py:137 — corpus_upsert guarded; sync_corpus.py:104-110 returns failure count. Precondition + propagate-exit accurate.
- SGAP-004: `launchctl list | grep memory` → loaded; `/tmp/mk-weekly-review.log` absent; stamp `2026-06-19`. State accurate.
- SGAP-005: ci.yml:1-6 has only push/PR triggers, no schedule; config defaults False. Accurate.

### Post-Edit New-Gap Pass (after Cycle 1 edits)

- Does resolving R-AUTH (no token) introduce a new exposure? The `/mcp` endpoint being open is a pre-existing property the local hook already relies on; the edit documents it, introduces nothing. The write tools remain `allow_remote_writes`-gated (guards.py:29) so "open MCP" ≠ "open writes." No new gap; noted the future-gateway caveat.
- Does the harness-interop note create a conflict with the existing serialization claim? No — it refines "won't stampede the worker" (still true: max_concurrent=1) by separating queue-correctness (holds) from latency (harness ingestion can lag). Consistent.
- Does the `allow_remote_writes` precondition conflict with R-FRESH-disabled? No — freshness stays disabled regardless; the precondition concerns corpus_upsert only.
- Does the launchd-unload step orphan any task? No — every launchd task is already re-homed per the coverage pass §4.5 checklist (CGAP-012); unload just enforces it. Consistent.
No new blocker gaps.

---

## Cycle 2 Assessment (fresh full pass over the edited document)

Re-ran all 8 lenses over the full requirement set + the 3 depth invariants against the edited `research.md`.

| req_id / invariant | previously-open lens | status now | evidence (research.md after edit) |
| --- | --- | --- | --- |
| R-SHAREDINFRA / R-NEG-CONCURRENT / INV-DISPATCH-COTENANT | 5 | addressed | §4.1/§5 harness-interop paragraph: shared dispatcher, harness repos enumerated, latency-not-correctness bound + acceptance |
| R-AUTH / R-SECRETS | 1/7 | addressed | §6.4/§7/§4.2: `/mcp` open, no CI token; URL-only secret |
| R-CORPUS.O2 / INV-CORPUS-WRITEGUARD | 6/7 | addressed | §4.2: `allow_remote_writes=true` precondition + propagate non-zero exit; live value flagged |
| R-MULTIMACHINE / R-RETIRE / R-IDEMPOTENT | 8 | addressed | §4.5: `launchctl unload` required step + verification + current-state note |
| R-INTEG / R-SPARK (deploy settings) | 7 | addressed (tracked, unverifiable) | §4.1/§4.2/§7: app-setting flips + CI creation as required impl steps; live values marked unverifiable |

All other requirements remained `holds` from Cycle 1's trace table (mechanism confirmed against real code: job-type registration, dispatcher claim, compaction dry_run, sentinel guard, origin filter, refresh_trusted local-only, post-commit hook locality, swallow-and-exit-0 confirming fail-loud need).

No new blocker gaps. This cycle made edits in Cycle 1; per the hard-stop rule convergence is declared only in the next no-edit cycle.

### Conflict / Asymmetry Register (Cycle 2)

| pair | symmetric? |
| --- | --- |
| maintenance producer (create_job job_type) vs dispatcher consumer (JOB_TYPE_REGISTRY) | YES — both keyed on `job_type`; `integrity_audit`/`compaction` registered (server.py:6646-6647) |
| corpus producer (sync_corpus upsert) vs corpus consumer (corpus_query acceptance) | YES — same `run_corpus_upsert_workflow` tool; sync_corpus checks status |
| brain maintenance enqueue vs harness ingestion enqueue (same table/worker) | RESOLVED — now documented as shared, latency-bounded (SGAP-001 fix) |
| CI commit vs local post-commit hook firing | RESOLVED — CI runs sync_corpus.py explicitly (CGAP-002); precondition added (SGAP-003) |

---

## Cycle 3 — Final Convergence Check (no edits)

Fresh full pass over the addressed requirement set (27 reqs) plus the 3 depth invariants; zero blocker gaps discoverable from the repo/data. Every addressed requirement traces end-to-end to confirming runtime evidence; every producer/consumer and read/write boundary (job_type, repository_key, corpus tool, CI-vs-hook commit, brain-vs-harness dispatcher) was checked on **both** sides; data-reality checks (enumeration SQL, sentinel guard, dry_run flow, harness repo keys) were made against actual code, not just schema; every best-effort path (weekly_review swallow, sync_corpus status check, tick exception) was traced for silent-inert/wrong. No edits this cycle.

### Final Gap Ledger (status)

| gap_id | req_id | status | closure evidence |
| --- | --- | --- | --- |
| SGAP-001 | R-SHAREDINFRA / R-NEG-CONCURRENT / INV-DISPATCH-COTENANT | closed | research.md §4.1/§5 harness-interop paragraph |
| SGAP-002 | R-AUTH / R-SECRETS | closed | research.md §6.4/§7/§4.2 (`/mcp` open) |
| SGAP-003 | R-CORPUS.O2 / INV-CORPUS-WRITEGUARD | closed | research.md §4.2 precondition + propagate-exit |
| SGAP-004 | R-MULTIMACHINE / R-RETIRE / R-IDEMPOTENT | closed | research.md §4.5 launchctl unload required step |
| SGAP-005 | R-INTEG / R-SPARK (deploy settings) | closed (tracked as required impl + unverifiable) | research.md §4.1/§4.2/§7 |

### Final Readiness Proof

| req_id | satisfied end-to-end? | evidence |
| --- | --- | --- |
| R-INTEG | yes (real runtime confirmed) | job types registered server.py:6646-6647; dispatcher claims+runs dispatcher.py:120-143; compaction dry_run compaction.py:32,41; needs app-setting flip (SGAP-005, required step) |
| R-FRESH | yes (disabled end-state) | config.py:92; sentinel guard ingestion_scheduler.py:38-43 |
| R-SPARK | yes (CI impl step; no token needed) | directive_spark.py:34-37; `/mcp` open auth.py:24; greenfield CI |
| R-AGENTS | yes (local-only locus) | refresh_trusted generate_projections.py:127-143 |
| R-STAMP | yes (CI impl step) | weekly_review.py:29-31; idempotent |
| R-CORPUS | yes (local hook + CI explicit step + write-guard precondition) | post-commit hook present; sync_corpus.py:82,104-110; server.py:409 guard |
| R-CAPTURE | yes (scoped-out) | research.md:26 |
| R-NOMANUAL | yes (freshness explicit exception) | research.md §4.4 |
| R-MACHINEINDEP | yes | research.md §3; Azure/GitHub always-on |
| R-MULTIMACHINE | yes (given launchd unload step) | research.md §4.5; SGAP-004 step |
| R-NOINCIDENT | yes | ingestion_scheduler.py:38-43 |
| R-SHAREDINFRA | yes (serialization + dedup; harness latency documented) | config.py:114; maintenance_scheduler.py:83-89; §4.1 interop note |
| R-OBSERV | yes (dead-man's-switch impl step) | maintenance_scheduler.py:81; research.md §5 |
| R-SECRETS | yes (URL-only secret) | auth.py:24 |
| R-IDEMPOTENT | yes (server dedup; CI sole committer; launchd unloaded) | maintenance_scheduler.py:83-89; §4.5; SGAP-004 |
| R-RETIRE | yes (re-homing checklist + unload step) | research.md §4.5; SGAP-004 |
| R-COST | yes | research.md:181 |
| R-CADENCE | yes (UTC + DST decision) | research.md:180; config.py:95 |
| R-BACKCOMPAT | yes | post-commit hook unchanged |
| R-NEG-BRAINDOWN | yes (fail-loud + dead-man's-switch impl steps) | weekly_review.py:79-90; maintenance_scheduler.py:63-64 |
| R-NEG-CIREACH | yes (probe/non-zero exit impl step) | research.md §5 |
| R-NEG-RUNNING | yes | maintenance_scheduler.py:86-89; ingestion_scheduler.py:204-214 |
| R-NEG-MIDFLIGHT | yes (rebase/retry + idempotent stamp) | research.md §4.2; weekly_review.py:29-31 |
| R-NEG-NOORIGIN | yes | ingestion_scheduler.py:31; maintenance_scheduler.py:18 |
| R-NEG-CONCURRENT | yes (serialized; harness contention documented) | config.py:114; §4.1 interop note |
| R-AUTH | yes (resolved: no token) | auth.py:24 |

**Convergence: ACHIEVED (depth).** Fresh full pass found zero blocker gaps; all SGAP-001..004 closed by doc edits, SGAP-005 recorded as required-impl + unverifiable-from-repo.

### Items genuinely unverifiable from the repo (marked, not masked)

1. **Live Azure app settings** — `maintenance_scheduler_enabled`, `compaction_enabled`, `allow_remote_writes` actual values on the deployed brain (config defaults are False; the existing local corpus hook working implies `allow_remote_writes=true` already). Required impl steps; live state not inspectable here.
2. **Brain MCP auth** — RESOLVED from repo (`/mcp` open, auth.py:24); the only residual is a hypothetical future gateway fronting `/mcp`.
3. **GitHub Actions runner egress** to `memory-knowledge.azurewebsites.net` — assumed public HTTPS; not testable from the repo. The doc's fail-loud-on-unreachable requirement (CGAP-008) covers the failure case.

### User decisions still open (do not block depth convergence; tracked in research.md §6)

- Freshness enable-with-allowlist vs stay-disabled (§6.1).
- Real-compaction vs dry-run for first cycle (§6.3).
- Off-peak via restart-time anchor vs scope-out (§4.1) — now also weighed against harness working hours (SGAP-001).
