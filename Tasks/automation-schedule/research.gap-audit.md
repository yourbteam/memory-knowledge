# Gap Audit — automation-schedule/research.md

Scope: **internal document readiness** (doc-gap-closure-loop). Verifies the doc is self-sufficient,
decision-complete enough to plan from, internally consistent, and that every *cited* repo claim is real.
Does NOT verify interop, runtime/data reality, or end-to-end requirement satisfaction (next gates).

Target: `/Users/kamenkamenov/memory-knowledge/Tasks/automation-schedule/research.md`
Repo: `/Users/kamenkamenov/memory-knowledge`

---

## Cycle 1 Assessment

### Section Inventory

| unit_id | section/title | unit type | implementation relevance |
| --- | --- | --- | --- |
| U0 | Intro block (Mode/Goal/Next/R1), lines 1-11 | intro text | scope, grounding rule |
| U1 | §1 recurring upkeep task table, lines 13-24 | table | inventory of tasks + triggers + loci (cited paths) |
| U2 | §2 two-loci core finding, lines 27-43 | prose | the split that drives the whole plan (Dockerfile + config + server cites) |
| U3 | §3 scheduling mechanisms table, lines 46-54 | table | mechanism options + fit |
| U4 | §3 launchd-gap paragraph, lines 55-57 | prose | reliability gap + evidence (stamp/log) |
| U5 | §4 recommended schedule item 1 (maintenance), lines 63-67 | recommendation | the server-side flip + cadence |
| U6 | §4 item 2 (Spark+stamp CI), lines 68-71 | recommendation | CI cron + secrets |
| U7 | §4 item 3 (AGENTS.md refresh), lines 72-77 | recommendation | event-driven design point |
| U8 | §4 item 4 (freshness keep disabled), lines 78-81 | recommendation | risk decision |
| U9 | §4 item 5 (retire launchd) + Net, lines 82-86 | recommendation | summary |
| U10 | §5 Risks/guards, lines 90-95 | list | guards + observability |
| U11 | §6 Open decisions, lines 97-101 | list | deferred decisions for plan |
| U12 | §7 UNVERIFIED, lines 103-107 | list | open verification items |

### Coverage Matrix (lenses: DC=decision-completeness, RG=repo grounding, CON=contradictions, VAG=vague wording, VAL=validation/acceptance, HO=planner handoff)

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |
| U0 | DC/RG | checked | R1 promises `path:line` grounding; sets the bar the doc is judged against |
| U1 | RG | gap found | `maintenance_scheduler.py:77-90` ✓ (real path `src/memory_knowledge/jobs/...`); `weekly_review.py:59-68` ≈ Spark block (59-80) ok; **`weekly_review.py:80-92` MISCITED** — AGENTS refresh is lines 92-104; 80-90 is consolidation block (GAP-002). "full source ingest" for IngestionScheduler **factually wrong** — docstring says *incremental* (GAP-003) |
| U1 | DC | checked | task/trigger/locus columns complete per task |
| U2 | RG | gap found | `config.py:100/101/92` ✓; `server.py:6596-6609` **MISCITED** — that range is `startup_mode_summary` log; real wiring is 6655-6669 (GAP-001). `Dockerfile:25-29` range ok but description "copies only src/, migrations/, docker/, alembic.ini" overstates: line 25 is `/install` copy, `docker/` is NOT wholesale-copied (only `docker/entrypoint.sh` + `docker/certs/`) (GAP-004) |
| U2 | CON | checked | conclusion (no working-agreement/DIRECTIVES/git in image) is correct & load-bearing |
| U3 | RG | checked | ci.yml exists ✓ (claim is "repo already has ci.yml", not "ci.yml has cron"); launchd plist `com.kamen.memory-weekly-review.plist` exists ✓ |
| U3 | DC | checked | mechanism/fit mapping complete |
| U4 | RG | checked | stamp `2026-06-19` ✓ (DIRECTIVES.md:4); no `/tmp/mk-weekly-review.log` ✓ |
| U5 | DC | gap found | Recommends enabling maintenance scheduler for "integrity audit + compaction" but omits that `compaction_enabled=False` (config.py:88) → compaction runs **dry-run** (maintenance_scheduler.py:71); flipping only `maintenance_scheduler_enabled` yields audits + *no real* compaction (GAP-005) |
| U5 | RG | checked | `job_dispatcher_max_concurrent=1` ✓ (config.py:114, uncited); `_enqueue_if_absent` ✓ (:83); `daily_at` only for ingestion `config.py:94` ✓; maintenance `_loop` interval-only ✓ (:58-68) |
| U5 | VAG | checked | "[inf]" off-peak correctly flagged as inference |
| U6 | DC | checked | secrets approach locked (GitHub Actions secrets); auth token deferred to U11.4 (acceptable open decision) |
| U7 | DC | checked | explicitly an open design point, cross-refs §6; acceptable to leave open with recommendation |
| U8 | RG | gap found | "would still full-ingest any origin_url repo on a schedule" — same overstatement as GAP-003; real behavior is incremental for changed in-scope repos, bootstrap-full only for never-ingested; A2/SGAP-002 notes-only guard at ingestion_scheduler.py:36 ✓. `ingestion_scheduler_repo_allowlist` config.py:96 ✓ (GAP-003 covers) |
| U9 | DC | checked | summary consistent with U5/U6 |
| U10 | RG | checked | `_enqueue_if_absent` dedupe ✓; `max_per_tick` (ingestion only) config.py:97 ✓; `maintenance_scheduler_tick_complete` log ✓ (:81); A2 sentinel guard ✓ |
| U10 | VAL | checked | observability guard present; [inf] alerting flagged |
| U11 | DC | checked | open decisions are genuine policy choices (keep for plan) |
| U12 | RG | gap found | Item 2 ("whether MaintenanceScheduler interval is purely loop-based — read `_loop`") is now **answerable from repo**: `_loop` (maintenance_scheduler.py:58-68) is interval-only, no wall-clock anchor. Listing it as still-unverified is stale (GAP-006). Items 1/3/4 are genuinely external (MCP auth, network egress, multi-repo CI perms) — keep |

### Blocker Gap Ledger

| gap_id | severity | unit_id | lens | evidence | why blocker | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAP-001 | blocker | U2 | RG | Doc line 34 cites `server.py:6596-6609` for scheduler startup wiring; `nl -ba server.py` 6596-6609 is the `startup_mode_summary` log block; real wiring is `server.py:6655-6669` (`if settings.maintenance_scheduler_enabled: ... MaintenanceScheduler().start(...)`) | A planner verifying "flip the flag and they run" lands on the wrong code; the cited anchor is false | Correct cite to `server.py:6655-6669` | line 34 now cites 6655-6669 | open |
| GAP-002 | blocker | U1 | RG | Doc line 20 cites `weekly_review.py:80-92` for AGENTS.md refresh; `nl -ba weekly_review.py` shows 82-90 = "Consolidation/integrity", AGENTS refresh = lines 92-104 | Wrong anchor for a task locus the plan must wire; planner would read the consolidation block instead | Correct cite to `weekly_review.py:92-104` | line 20 cite corrected | open |
| GAP-003 | blocker | U1/U8 | RG | Doc lines 18, 80 call IngestionScheduler "full source ingest" / "would still full-ingest any origin_url repo". Docstring `ingestion_scheduler.py:3-4`: "only when [HEAD] changed, enqueues an **incremental** ingestion job"; `_process_repo` skips unchanged (`scheduler_skipped_unchanged`), bootstrap-full only when never ingested (`:188`); `docs/FRESHNESS_AND_MAINTENANCE_PLAN.md:39,92-93` confirm "no full re-ingest" of unchanged | Factually wrong runtime claim that drives the keep-disabled risk decision; misstates the actual risk (unintended *scope* of auto-ingest + bootstrap-full for new repos), which the plan inherits | Reword to: incremental for changed in-scope repos; bootstrap full-ingest only for never-ingested repos; risk = any non-allowlisted `origin_url` repo gets auto-ingested. Keep keep-disabled recommendation | lines 18, 80 reworded | open |
| GAP-004 | blocker | U2 | RG | Doc lines 37-38: image "copies only `src/`, `migrations/`, `docker/`, `alembic.ini` (`Dockerfile:25-29`)". `nl -ba Dockerfile`: L25 `COPY --from=builder /install /usr/local`, L26 `COPY src/ src/`, L27 `COPY docker/entrypoint.sh alembic.ini ./`, L28 `COPY migrations/ migrations/`, L29 `COPY docker/certs/ /app/certs/` — `docker/` is NOT wholesale-copied; L25 is the install copy | Mischaracterizes what the cited line range contains; a planner checking "no working-agreement in image" against the cite sees a different copy set | Correct the file list to `src/`, `alembic.ini`, `docker/entrypoint.sh`, `migrations/`, `docker/certs/` and keep cite `Dockerfile:25-29`; conclusion (no working-agreement/DIRECTIVES/git) unchanged | lines 37-38 corrected | open |
| GAP-005 | blocker | U5 | DC | §4.1 recommends enabling MaintenanceScheduler for "integrity audit + compaction" but omits `compaction_enabled=False` (config.py:88) → `dry_run = not compaction_enabled` (maintenance_scheduler.py:71) means compaction is enqueued **dry-run**. Flipping only `maintenance_scheduler_enabled` gives audits + dry-run compaction, not real consolidation | The upkeep goal includes consolidation; a planner following §4.1 would ship a scheduler that never actually compacts and silently believe upkeep is done — a missed decision | Add to §4.1: to get *real* compaction also set `compaction_enabled=1` (config.py:88); otherwise compaction runs dry-run-only (maintenance_scheduler.py:71). Surface as an explicit decision | §4.1 names both flags | open |
| GAP-006 | cleanup→blocker | U12 | RG | §7 item 2 asks to confirm MaintenanceScheduler interval is loop-based; already confirmed: `maintenance_scheduler.py:58-68` `_loop` is interval-only (`asyncio.wait_for(stop.wait(), timeout=interval)`), no wall-clock anchor | Listing a repo-answerable fact as "unverified" forces the next gate to redo work the doc could close; R1 promises grounding | Move item 2 from UNVERIFIED to a resolved/grounded statement (cite `:58-68`); keep genuinely-external items | §7 item 2 resolved with cite | open |

### Cleanup List

| item_id | unit_id | issue | optional fix |
| --- | --- | --- | --- |
| C1 | U1/U2 | Path-prefix convention is implicit: scheduler/config/server cites omit `src/memory_knowledge/` while Dockerfile/ci.yml are repo-root-relative | Add a one-line note in U0/R1 stating runtime cites are relative to `src/memory_knowledge/` (resolves ambiguity for the planner) — promoting to fix since it affects every RG cite's resolvability |
| C2 | U5 | `job_dispatcher_max_concurrent=1` referenced without a line cite | add `config.py:114` |

## Cycle 1 Plan

### Gap-To-Fix Map

| gap_id | target unit | exact decision to lock | edit summary | validation check |
| --- | --- | --- | --- | --- |
| GAP-001 | U2 line 34 | wiring cite = `server.py:6655-6669` | replace `server.py:6596-6609` | `nl -ba server.py \| sed -n '6655,6669p'` shows the `if settings.*_scheduler_enabled` blocks |
| GAP-002 | U1 line 20 | AGENTS refresh cite = `weekly_review.py:92-104` | replace `weekly_review.py:80-92` | `nl -ba weekly_review.py \| sed -n '92,104p'` is the AGENTS refresh block |
| GAP-003 | U1 line 18, U8 line 80 | scheduler enqueues **incremental** (changed in-scope repos), bootstrap-full only for never-ingested; risk = unintended auto-ingest *scope* | reword "full source ingest"/"full-ingest any origin_url repo" | `ingestion_scheduler.py:3-4` + `:188` + `docs/FRESHNESS_AND_MAINTENANCE_PLAN.md:39` |
| GAP-004 | U2 lines 37-38 | correct copied set: `src/`, `alembic.ini`, `docker/entrypoint.sh`, `migrations/`, `docker/certs/` | reword the file list; keep `Dockerfile:25-29` cite and the no-working-agreement conclusion | `nl -ba Dockerfile \| sed -n '25,29p'` |
| GAP-005 | U5 lines 63-67 | real compaction requires ALSO `compaction_enabled=1`; else dry-run only | add the second flag + cite `config.py:88` / `maintenance_scheduler.py:71` | `nl -ba maintenance_scheduler.py \| sed -n '71p'` |
| GAP-006 | U12 lines 103-107 | item 2 is resolved: `_loop` interval-only, no wall-clock | move item 2 to a grounded statement with cite `maintenance_scheduler.py:58-68` | `nl -ba maintenance_scheduler.py \| sed -n '58,68p'` |
| C1 | U0 line 9 | runtime cites are relative to `src/memory_knowledge/` | add a path-convention note to R1 | doc reads consistently |
| C2 | U5 line 64 | add `config.py:114` to the max_concurrent reference | inline cite | grep |

## Cycle 1 Edits

All edits applied to `research.md` (verified by re-Read of changed regions):

- **GAP-001** — R1/U2: line 34 now `server.py:6655-6669` (was 6596-6609).
- **GAP-002** — U1: AGENTS.md refresh row now `weekly_review.py:92-104` (was 80-92).
- **GAP-003** — U1 Freshness row reworded to "incremental ingest only when remote HEAD changed, skipping unchanged" + bootstrap-full cite `:188`; risk relabeled "auto-ingest scope". §4.4 reworded: residual risk = scope (every `origin_url` repo with an empty allowlist) + one-time bootstrap full ingest; A2/SGAP-002 cite `:36` added.
- **GAP-004** — U2: copied set corrected to `src/`, `alembic.ini`, `docker/entrypoint.sh`, `migrations/`, `docker/certs/`; cite `Dockerfile:25-29` kept; no-working-agreement conclusion preserved.
- **GAP-005** — U5/§4.1: added the two-flag requirement (`compaction_enabled=1`, `config.py:88`) and the dry-run consequence (`maintenance_scheduler.py:71`); added an explicit rollout decision; `max_concurrent` now cites `config.py:114`; `_enqueue_if_absent` cites `:83`.
- **GAP-006** — U12/§7: item 2 moved to a "Resolved from the repo" statement citing `maintenance_scheduler.py:58-68` (interval-only `_loop`); genuinely-external items retained.
- **C1** — R1: added path-convention note (runtime cites relative to `src/memory_knowledge/`).

## Cycle 1 Validation

Commands run and results:

- `rg -ni 'TBD|TODO|maybe|not locked|needs further|or equivalent' research.md` → **none**.
- `rg -ni 'such as|candidate|could|should' research.md` → 4 hits, all benign: `spark-candidates.md` (real filename ×2), "candidate notes" (auto-capture output description), "could be enqueued twice" (factual risk, not a hidden decision). No vague wording hides a decision.
- Re-confirmed every corrected cite against the repo:
  - `server.py:6657/6665` = the `if settings.*_scheduler_enabled` wiring blocks ✓
  - `weekly_review.py:92` (AGENTS refresh comment) / `:101` (`gp.refresh_trusted`) ✓
  - `ingestion_scheduler.py:4` = "incremental ingestion job"; `:188` = "Bootstrap … (full ingest)" ✓
  - `Dockerfile:25-29` = `/install`, `src/`, `docker/entrypoint.sh alembic.ini`, `migrations/`, `docker/certs/` ✓
  - `maintenance_scheduler.py:71` = `dry_run = not self._settings.compaction_enabled`; `:83` = `_enqueue_if_absent` ✓
  - `config.py:88` compaction_enabled=False, `:94` daily_at (ingestion), `:96` allowlist, `:114` max_concurrent=1 ✓
- `git diff --check -- research.md` → exit 0 (no whitespace errors).

Post-edit new-gap pass:

| changed unit | checked against | result | new gap id |
| --- | --- | --- | --- |
| U2 line 34 (server cite) | server.py:6655-6669 | accurate; no scope drift | none |
| U1 freshness row + §4.4 | ingestion_scheduler.py:3-4,36,188; FRESHNESS doc:39 | now matches runtime; keep-disabled recommendation unchanged | none |
| U1 AGENTS cite | weekly_review.py:92-104 | accurate | none |
| U2 Dockerfile list | Dockerfile:25-29 | accurate; conclusion intact | none |
| U5 §4.1 two-flag | config.py:88,114; maintenance_scheduler.py:71,83 | accurate; new decision added to §6-adjacent text but framed as explicit choice, not a hidden gap | none |
| U12 §7 resolved item | maintenance_scheduler.py:58-68 | accurate; UNVERIFIED list now only genuinely-external items | none |
| R1 path note | n/a (doc-internal) | resolves prefix ambiguity for all RG cites | none |

No new blocker gaps introduced by the edits.

## Cycle 2 Assessment

Fresh full-document pass over the edited `research.md` (re-Read lines 1-116). Carrying forward GAP-001…006 as **closed** (closure evidence in Cycle 1 Validation), C1 closed, C2 closed.

### Coverage Matrix (Cycle 2)

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |
| U0 | DC/RG | checked | R1 now states the path convention (lines 9-12); resolves every runtime cite's prefix |
| U1 | RG | checked | all 4 row cites now accurate: maintenance `:77-90`, ingestion `:3-4`/`:188`, Spark `:59-68`, AGENTS `:92-104`; post-commit hook `.git/hooks/post-commit` (symlink → sync-corpus.sh, fires on DIRECTIVES change) ✓ |
| U1 | DC/CON | checked | loci/trigger columns internally consistent with §2 split |
| U2 | RG | checked | config :100/:101/:92 ✓; server :6655-6669 ✓; Dockerfile list+:25-29 ✓ |
| U2 | CON | checked | "no working-agreement in image → repo-git can't run server-side" sound |
| U3 | RG/DC | checked | ci.yml exists (claim is existence, not cron); launchd plist exists; mechanism/fit complete |
| U4 | RG | checked | stamp 2026-06-19 ✓, no /tmp log ✓ |
| U5 | DC | checked | now decision-complete: both flags named, dry-run consequence stated, rollout decision surfaced, cadence grounded `:58-68` |
| U5 | RG | checked | config :88/:114/:94; maintenance :71/:83/:58-68 all confirmed |
| U6 | DC | checked | secrets locked to GH Actions secrets; auth token deferred to §6.4 (legitimate open decision) |
| U7 | DC | checked | event-driven recommendation + explicit open design point (§6.2) |
| U8 | DC/RG | checked | keep-disabled with grounded, corrected risk framing (scope, not "full ingest"); allowlist cite `:96` |
| U9 | CON | checked | Net summary consistent with U5/U6 (one flip + one cron); note U5 now also implies a 2nd flag for real compaction — Net's "one app-setting flip" is about *enabling the scheduler*, not a contradiction (see check below) |
| U10 | RG/VAL | checked | dedupe `_enqueue_if_absent`, `max_per_tick` (ingestion :97), `maintenance_scheduler_tick_complete` log :81, A2 guard — all real; [inf] alerting flagged |
| U11 | DC | checked | open decisions are genuine policy choices; §6.3 cadence + §6.4 MCP auth align with §7 |
| U12 | RG | checked | UNVERIFIED list now only genuinely-external items; resolved item moved out with cite |

### Cycle 2 — contradiction re-check on the Net line (U9)

Potential concern: §4.1 now says real compaction needs **two** flags, but §9 "Net" says "**one** app-setting flip (server maintenance)". Re-read: the Net sentence describes replacing launchd with two *schedules* (server maintenance + CI cron); "one app-setting flip" refers to turning the maintenance scheduler on. With GAP-005 now explicit in §4.1 that real compaction needs a second flag, the Net's "one flip" is a mild simplification but **not a contradiction** — it is scoped to "enable the schedule", and §4.1 is the authoritative detail. Marked **cleanup C3**, not a blocker (the authoritative §4.1 already forces the correct decision; a planner cannot be misled into shipping dry-run because §4.1 names both flags).

### Cycle 2 Blocker Gap Ledger

No new blocker gaps. All prior gaps closed.

| gap_id | status | closure evidence |
| --- | --- | --- |
| GAP-001 | closed | research.md:34 = `server.py:6655-6669`; verified `:6657/:6665` |
| GAP-002 | closed | research.md U1 = `weekly_review.py:92-104`; verified `:92/:101` |
| GAP-003 | closed | U1 row + §4.4 reworded to incremental/scope; verified `ingestion_scheduler.py:4,36,188` |
| GAP-004 | closed | U2 list matches `Dockerfile:25-29` |
| GAP-005 | closed | §4.1 names `compaction_enabled` (`config.py:88`) + dry-run (`maintenance_scheduler.py:71`) + rollout decision |
| GAP-006 | closed | §7 resolved item cites `maintenance_scheduler.py:58-68` |

### Cycle 2 Cleanup List

| item_id | unit_id | issue | optional fix |
| --- | --- | --- | --- |
| C3 | U9 | "Net: one app-setting flip" is a mild simplification now that real compaction needs a 2nd flag | optional: "one-to-two app-setting flips"; non-blocking — §4.1 is authoritative and already forces the decision |

## Final Convergence Check

Cycle 2 is a **no-edit assessment cycle** (no document edits made in Cycle 2). The full-document pass found **zero blocker gaps**; the only finding is cleanup C3.

### Final Readiness Proof

| category | status | evidence |
| --- | --- | --- |
| runtime entry points & data flow | ready | server.py:6655-6669 wiring; maintenance `_tick`/`_loop` :70-92/:58-68; ingestion `_tick`/`_process_repo` :149-200 |
| schema/fields/interfaces/helpers/artifacts | ready | config flags :88-114 enumerated with defaults; `_enqueue_if_absent` :83; tools `run_integrity_audit_workflow`/`run_compaction_workflow`/`run_repo_ingestion_workflow` named from code |
| edge cases & failure behavior | ready | dry-run compaction path; bootstrap full-ingest; A2/SGAP-002 notes-only exclusion :36; skip-unchanged |
| resume behavior & idempotency | ready | `_enqueue_if_absent` dedupe; skip-if-active; post-commit fail-open hook |
| validation/test/acceptance | ready (doc-internal) | §5 observability + log events; FRESHNESS plan success metrics referenced. Note: end-to-end acceptance against live data is a satisfaction-gate concern, out of scope here |
| repo grounding | ready | every cited path:line re-verified against the repo this cycle |
| approval boundaries | ready | no runtime code changed; recommendations + open decisions (§6) left explicitly to the plan |
| out-of-scope boundaries | ready | auto-capture marked out of scope (U1); §7 lists genuinely-external unverified items |

**Convergence: reached** (internal document readiness only). 2 cycles. The final full-document pass (Cycle 2) made no edits and found no blocker gaps; one cleanup (C3) noted, non-blocking.

**Scope caveat:** this convergence establishes internal readiness only — self-sufficient, decision-complete, internally consistent, and all *cited* repo claims verified real. It does NOT establish interop with sibling features, runtime/data reality, or end-to-end requirement satisfaction. Next gates: `requirements-coverage-gap-loop` then `requirements-satisfaction-gap-loop` before implementation.
