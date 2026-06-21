# Gap Audit — `plan.md` (Automation schedule for second-brain upkeep)

Target: `/Users/kamenkamenov/memory-knowledge/Tasks/automation-schedule/plan.md` (237 lines)
Skill: doc-gap-closure-loop (internal-readiness gate)
Repo grounded against: `/Users/kamenkamenov/memory-knowledge`
Convergence standard: a fresh full-document pass that finds zero blocker gaps, in a cycle that made no edits.

Scope note: this loop verifies INTERNAL readiness only (self-sufficient, decision-complete, internally consistent, every CITED claim real). It does NOT verify interop / runtime-data reality / end-to-end requirement satisfaction — those are the coverage and satisfaction gates.

---

## Cycle 1 Assessment

### Section inventory

| unit_id | section/title | unit type | implementation relevance |
| --- | --- | --- | --- |
| U0 | Header (Mode/Source/Repo, lines 1-5) | intro | env/repo facts |
| U-PC | Path convention note (line 7) | unheaded claim block | anchor base + app-setting-name rule |
| U1 | §1 Objective (11-13) | heading | goal framing |
| U2 | §2 Scope in/out (15-29) | heading + list | scope boundaries + grounding |
| U3 | §3 Locked Decisions D1-D11 (31-45) | locked-decision table | the core decisions |
| U4 | §4 In/Out app-settings summary (47-54) | table | exact settings + restart semantics |
| W1 | Workstream 1 server maintenance (58-80) | heading block | app-setting-only enable |
| W2 | Workstream 2 GH Actions weekly cron (84-112) | heading block | new workflow YAML |
| W3 | Workstream 3 AGENTS refresh local (116-130) | heading block | sync-corpus.sh edit |
| W4 | Workstream 4 Retire launchd (134-157) | heading block + table | runtime ops |
| W5 | Workstream 5 dead-man's-switch (161-175) | heading block | heartbeat workflow |
| U5 | §5 Off-peak (179-182) | heading | off-peak mechanism |
| U6 | §6 Sequencing & rollout (184-195) | heading + ordered list | ordering |
| U7 | §7 Rollback (197-202) | heading | rollback |
| U8 | §8 Required live confirmations (204-209) | heading + list | operator checks |
| U9 | §9 Test plan (211-226) | table | acceptance/tests |
| U10 | §10 Open questions + Critical files (228-237) | heading + list | residual decisions/files |

### Repo-grounding ledger (every cited `path:line` checked)

CONFIRMED CORRECT:
- `config.py:8-9` no env_prefix → uppercased field-name app settings — `nl config.py` lines 8-9: `class Settings(BaseSettings)` / `model_config = SettingsConfigDict(env_file=...)`, no `env_prefix`. ✓
- `config.py:88` `compaction_enabled: bool = False` ✓; `:92` `ingestion_scheduler_enabled = False` ✓; `:94` `ingestion_scheduler_daily_at` ✓; `:97` `ingestion_scheduler_max_per_tick = 5` ✓; `:100` `maintenance_scheduler_enabled = False` ✓; `:101` `maintenance_interval_seconds = 604800` ✓; `:114` `job_dispatcher_max_concurrent = 1` ✓; `:137` `allow_remote_writes = False` ✓; `:95` `ingestion_scheduler_timezone = "Europe/Sofia"` ✓ (cited in D8 for Sofia tz).
- `server.py:6646-6647` register_job_type integrity_audit/compaction ✓; `:6663-6669` maintenance scheduler wired under flag ✓; `:6665` `if settings.maintenance_scheduler_enabled:` (read once at startup) ✓.
- `maintenance_scheduler.py:19-25` `_REAL_REPOS_SQL` excl mawf%/repo-%/idx-% ✓; `:27-31` `_ACTIVE_BY_TOOL_SQL` ✓; `:46` `maintenance_scheduler_started interval=` ✓; `:71` `dry_run = not compaction_enabled` ✓; `:78` compaction enqueue with dry_run ✓; `:81` `maintenance_scheduler_tick_complete repos=/enqueued=/compaction_dry_run=` ✓; `:63-64` tick_error caught, loop continues ✓; `:79-80` per-repo warning continues ✓; `:83-89` `_enqueue_if_absent` dedup ✓; `:86-89` skip-active ✓.
- `middleware/auth.py:8` `_PUBLIC_PATHS` incl `/health` ✓; `:16` `_PUBLIC_PREFIXES` incl `/mcp` ✓; `:24` bypass startswith → call_next before key check ✓.
- `guards.py:26-38` is_any_remote + allow_remote_writes error ✓; `:29` `if not settings.allow_remote_writes:` ✓.
- `sync-corpus.sh:14-15` gate on git diff-tree HEAD + grep DIRECTIVES ✓; `:15` grep line ✓; `:23` `"$PY" "$HELPER" 2>/dev/null` ✓ (line 24 is `exit 0`).
- `sync_corpus.py:46-58` HEAD~1 read ✓; `:50-58` git show HEAD~1 ✓; `:100` return failures ✓; `:104-111` _report parse + ok=status=="success" ✓; `:112` print status= ✓; `:128-134` orphan diff ✓; `:138` asyncio.run(run(...)) ✓; `--url` flag line 119 ✓; DEFAULT_URL line 35 ✓.
- `weekly_review.py:26` `_STAMP_RE` ✓; `:29-31` bump_review_stamp idempotent ✓; `:60-66` spark ✓; `:67-78` candidate surfacing ✓; `:71-76` first-5 lines ✓; `:79-90` swallow try/except ✓; `:83-90` consolidation ✓; `:92-104` agents refresh ✓; `:101-104` refresh_trusted call ✓; `:106-109` stamp ✓; `:110` return 0 ✓; `:117` asyncio.run(_run) ✓.
- `directive_spark.py:109` streamable_http_client(URL) no auth ✓; `MK_SPARK_REPOS` read at module import line 29 ✓ (picked up at runtime since weekly_review dynamically imports the module after process env is set).
- `generate_projections.py:108-112` refresh_agents_file→None for non-generated ✓; `:115-126` codex_trusted_projects (def 115-124) ~✓ (range slightly over by 2 lines); `:117-118` config missing → [] ✓; `:127-143` refresh_trusted rewrites in place (def 127-142) ✓; `:134-141` refreshed:/skip(not-generated) prints ✓; `:137-139` skip(not-generated) ✓; `:155` --refresh-trusted flag ✓; `:155-159` flag+codex-config default (154-160) ✓.
- `com.kamen.memory-weekly-review.plist:10-11` Weekday 1 Hour 9 ✓.
- `weekly-review.sh:8` 8-repo MK_SPARK_REPOS ✓; `:11-16` weekly_review call + commit ✓; `:13-16` commit stamp+candidates ✓.
- `ci.yml:28` `pip install ".[dev]"` ✓; checkout@v4 / setup-python@v5 / py3.12 ✓; only ci.yml in `.github/workflows/` ✓.
- `DIRECTIVES.md:4` `<!-- Last reviewed: 2026-06-19 -->` ✓.
- `docs/FRESHNESS_AND_MAINTENANCE_PLAN.md:154-155` kill switch / `*_SCHEDULER_ENABLED=false` ✓.
- `.git/hooks/post-commit → sync-corpus.sh` symlink confirmed ✓.
- `SETUP-weekly-review.md` exists (WS4 step 4 target) ✓.

FACTUALLY WRONG:
- **First-tick timing.** D3 (line 37), WS1 step 2 (line 68), and §5 (line 181 implicitly via D3) all assert the first maintenance tick "fires `interval` seconds after `start()`" / "first tick fires `interval` (604800s) after `start()`", citing `maintenance_scheduler.py:45,66`. The actual `_loop` (lines 58-68) calls `await self._tick()` (line 62) IMMEDIATELY on the first iteration, THEN `await asyncio.wait_for(stop.wait(), timeout=interval)` (line 66). So the FIRST tick fires ~immediately at `start()` (container start); each SUBSEQUENT tick fires `interval` later. The off-peak conclusion (restart in off-peak window pins the weekly cadence) is still achievable — but via "first tick fires AT restart time; the recurring weekly tick lands at restart-hour" — NOT "first tick fires interval after start." This is a wrong-mechanism claim against cited code. → GAP-001.

PRECISION / INTERNAL-CONSISTENCY ISSUES:
- App-settings table line 52 says `COMPACTION_ENABLED` "Read per tick (`maintenance_scheduler.py:71`)". Line 71 reads `self._settings.compaction_enabled`, but `self._settings` is captured once at `start()` (line 43) from the process-startup `Settings`; it is NOT re-read live. The table already says "restart for determinism," but "Read per tick" overstates liveness. → GAP-002 (consistency/grounding).
- WS1 acceptance (line 75) "The tick timestamp falls in the off-peak window (proves the restart anchor)" depends entirely on the corrected mechanism; with the immediate-first-tick reality, this holds only because the enabling restart is performed in the off-peak window (step 2). Once GAP-001 is corrected the criterion is coherent; flagged as dependent. → folded into GAP-001.

### Coverage matrix (lens × unit)

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |
| U0 | repo grounding | checked | repo/app/URL facts; URL matches sync_corpus DEFAULT_URL:35, weekly_review:22 |
| U-PC | repo grounding / decision completeness | checked | env_prefix absent config.py:9 → uppercase rule sound |
| U1 | decision completeness | checked | objective restates the 5 workstreams; no decision hidden |
| U2 | scope / repo grounding | checked | out-of-scope cites config.py:92, auto-capture-stop.sh, generate_projections.py:127-143, maintenance_scheduler.py:58-68 — all real |
| U3 | locked-decision grounding/consistency | gap found | D3 first-tick mechanism wrong (GAP-001); D1/D2/D4-D11 grounded |
| U4 | schema/field/restart semantics | gap found | line 52 "Read per tick" overstates liveness (GAP-002); names + defaults correct |
| W1 | runtime entry/edge/verification | gap found | step 2 first-tick mechanism wrong (GAP-001); rest grounded |
| W2 | YAML authorability/decision completeness | checked | triggers/permissions/concurrency/steps/secrets all concrete; cites real lines |
| W3 | edit-site/edge | checked | sync-corpus.sh:23 insert point; fail-open pattern; gate line 15; generate_projections flag real |
| W4 | ops completeness/re-homing | checked | re-homing table all five tasks mapped to real triggers; commands concrete |
| W5 | heartbeat completeness | checked | cron, stamp parse regex shape (weekly_review.py:26), threshold 9d=7+2 explicit |
| U5 | off-peak mechanism | gap found | inherits GAP-001 (D3 mechanism) |
| U6 | sequencing | checked | order prevents double-commit; dry-run precedes real; mechanism-per-step listed |
| U7 | rollback | checked | per-workstream rollback; idempotency noted; kill switch grounded |
| U8 | approval/live-confirm boundaries | checked | 4 operator checks; all genuinely unverifiable-from-repo |
| U9 | acceptance/tests | checked | 12 tests map to WS acceptance; pass conditions concrete |
| U10 | residual decisions / files | checked | "None open"; critical files list matches WS edit targets |

### Blocker Gap Ledger

| gap_id | severity | unit_id | lens | evidence | why blocker | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAP-001 | blocker | U3/W1/U5 | repo grounding (factually wrong) | `maintenance_scheduler.py:58-68`: `_loop` runs `await self._tick()` (line 62) on the FIRST iteration before the `wait_for(..., timeout=interval)` (line 66). Plan D3 (line 37), WS1 step 2 (line 68), §5 (line 181) claim "first tick fires `interval` seconds after `start()`." That is the opposite of the code: the first tick fires immediately at `start()`; subsequent ticks fire every `interval`. | An implementer following the stated mechanism would expect NO tick for a week after restart and would mis-diagnose the immediate startup tick as a bug; the off-peak acceptance criterion (line 75) is justified by a false premise. | Rewrite D3, WS1 step 2, WS1 acceptance, and §5 to state the correct mechanism: first tick fires ~immediately at `start()` (container restart); each subsequent weekly tick lands at the restart wall-clock hour, so performing the enabling restart in the off-peak window pins both the immediate first tick and all weekly ticks to that hour. | (filled in Cycle 1 Validation) | open |
| GAP-002 | blocker | U4 | schema/field semantics + grounding | App-settings table line 52: `COMPACTION_ENABLED` "Read per tick (`maintenance_scheduler.py:71`)". Line 71 reads `self._settings.compaction_enabled`, but `self._settings` is frozen at `start()` (line 43) from the process-startup `Settings` singleton; it is not re-read from app settings each tick. | Misleads the implementer/operator into thinking flipping `COMPACTION_ENABLED` takes effect on the next tick without restart; the determinism note partially contradicts the "Read per tick" phrasing. Decision-completeness: the operator must know a restart is required. | Reword the cell to: value is captured at startup into the scheduler's `Settings` (`maintenance_scheduler.py:43`); each tick computes `dry_run` from it (`:71`); a flip requires a restart to take effect. Restart-needed = Yes (for the flip to apply). | (filled in Cycle 1 Validation) | open |

### Cleanup list

| item_id | unit_id | issue | optional fix |
| --- | --- | --- | --- |
| C1 | W3 (line 122) | "mirroring `sync-corpus.sh:5-8`" cites the fail-open COMMENT block; the executable fail-open guards are lines 20-21,23. | Optionally cite `sync-corpus.sh:20-23` for the executable pattern. (Non-blocking: intent is clear and the `2>/dev/null || true` form is self-contained.) |
| C2 | W3 (line 120) | "after the corpus-sync invocation (`sync-corpus.sh:23`)" — line 24 is `exit 0`, so the insert must be BEFORE `exit 0`. | Optionally note "before the final `exit 0` (line 24)". |
| C3 | W3 (line 122) | `generate_projections.py:115-126` for codex_trusted_projects is 115-124 (range over by 2). | Tighten to `115-124`. |

---

## Cycle 1 Plan

Gap-to-fix map:

| gap_id | target unit | exact decision to lock | edit summary | validation check |
| --- | --- | --- | --- | --- |
| GAP-001 | D3 (line 37), WS1 step 2 (line 68), WS1 acceptance (line 75), §5 (line 181) | First maintenance tick fires immediately at `start()` (container restart), not `interval` later; recurring weekly ticks land at restart wall-clock hour; enabling restart in off-peak window therefore pins both first and recurring ticks off-peak. | Replace the "first tick fires interval seconds after start()" phrasing in all four sites with the correct immediate-first-tick + recurring-at-restart-hour mechanism, citing `maintenance_scheduler.py:58-68` (loop ticks then waits) and `:45,62,66`. | re-read sites; grep for "interval seconds after"/"interval (604800s) after start" → none remain. |
| GAP-002 | §4 table line 52 | `COMPACTION_ENABLED` is captured at startup; a flip requires a restart to take effect; dry_run computed per tick from the startup-captured value. | Reword the COMPACTION_ENABLED row's "Restart needed?" cell. | re-read line 52; ensure no "Read per tick" liveness claim. |

Cleanup C1-C3 will be applied opportunistically while editing W3 lines 120-122 (cheap, same region).

---

## Cycle 1 Edits

(Applied to plan.md — see Cycle 1 Validation for exact resulting text and closure evidence.)

- GAP-001: edited D3 (line 37), WS1 step 2 (line 68), WS1 acceptance bullet (line 75), §5 first bullet (line 181).
- GAP-002: edited §4 table row for `COMPACTION_ENABLED` (line 52).
- C1/C2/C3: edited W3 lines 120-122.

## Cycle 1 Validation

Validation commands + results:
- `rg -n "interval seconds after|interval \(604800s\) after start|Read per tick" plan.md` → NONE FOUND (stale wrong-mechanism phrasing removed).
- `rg -n "115-126" plan.md` → only line 118; corrected to 115-124 (C3 closed).
- `rg -n "TBD|TODO|maybe|could|not locked|needs further|or equivalent" plan.md` → only "could double-commit" at 136/155 (legitimate risk prose, not an unresolved decision).
- `git diff --check plan.md` → clean (file is untracked content-wise but no whitespace markers).

Closure evidence:
- GAP-001 CLOSED. D3 (now): "first tick fires ~immediately at `start()` … every subsequent weekly tick lands at the restart wall-clock hour", cite `maintenance_scheduler.py:45,58-68` with explicit "line 62 precedes line 66". WS1 step 2, WS1 acceptance bullet, and §5 first bullet all rewritten to the immediate-first-tick + recurring-at-restart-hour mechanism. Matches code: `_loop` line 62 `await self._tick()` runs before line 66 `wait_for(..., timeout=interval)`.
- GAP-002 CLOSED. §4 row for `COMPACTION_ENABLED` now: "captured into the scheduler's `Settings` at startup (`maintenance_scheduler.py:43`); each tick derives `dry_run` from that captured value (`:71`), so a flip only takes effect after a restart"; Restart-needed = **Yes**. Matches code: `self._settings` set at line 43, `dry_run = not self._settings.compaction_enabled` at line 71.
- C1 CLOSED (W3 now cites `sync-corpus.sh:20-23` executable fail-open pattern). C2 CLOSED ("before the final `exit 0` (line 24)"). C3 CLOSED (115-124 in both W3 sites).

Post-edit new-gap pass:

| changed unit | checked against | result | new gap id |
| --- | --- | --- | --- |
| D3 (line 37) | maintenance_scheduler.py:45,58-68,62,66 | mechanism now matches code; consistent with WS1 step 2 + §5 | none |
| WS1 step 2 (line 68) | maintenance_scheduler.py:58-68 | consistent; restart command unchanged | none |
| WS1 acceptance (line 75) | D3 + step 2 | criterion now justified by off-peak restart, not false premise | none |
| §5 first bullet (line 181) | D3 | identical mechanism wording; no contradiction | none |
| §4 COMPACTION_ENABLED row (line 52) | maintenance_scheduler.py:43,71; D1; §6 step 7 (restart to flip) | "restart to flip" agrees with §6 step 7 ("COMPACTION_ENABLED=true + restart") and D1 | none |
| W3 lines 120-122 | sync-corpus.sh:15,20-24; generate_projections.py:115-124,155-159 | insert site + gate + cites all correct | none |
| W3 problem line 118 | generate_projections.py:115-124 | cite tightened, consistent with W3 exact-change | none |

Delta regression vs locked decisions / approval boundaries / out-of-scope: edits touched only mechanism descriptions and one restart-semantics cell; no locked decision value changed (D1 dry-run-first, D2 freshness disabled, D3 weekly off-peak all intact); out-of-scope §2 (incl. "Wall-clock off-peak … achieved best-effort via restart-time") remains consistent with the corrected mechanism; no new runtime-code commitment introduced; no approval-gated text altered.

---

## Cycle 2 Assessment (fresh full-document pass, no edits)

Re-inventoried all 17 units (U0,U-PC,U1,U2,U3,U4,W1-W5,U5-U10). Re-ran every lens top to bottom over the edited document.

Carry-forward of prior gaps:
- GAP-001 — closed (see Cycle 1 Validation). Verified against `maintenance_scheduler.py:58-68` again: line 62 `_tick()` then line 66 `wait_for(timeout=interval)`; document now states this. status: closed.
- GAP-002 — closed. Verified `maintenance_scheduler.py:43` (`self._settings = settings`) + `:71`; document row corrected. status: closed.

Fresh full-pass coverage matrix:

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |
| U0 | repo grounding | checked | URL/repo/RG facts; URL matches DEFAULT_URL sync_corpus.py:35 + weekly_review.py:22 |
| U-PC | decision completeness / grounding | checked | config.py:9 no env_prefix → uppercase app-setting rule sound |
| U1 | decision completeness | checked | objective enumerates 5 workstreams; nothing unresolved |
| U2 | scope / grounding | checked | every out-of-scope cite real (config.py:92; generate_projections.py:127-143; maintenance_scheduler.py:58-68; auto-capture-stop.sh) |
| U3 | locked-decision grounding/consistency | checked | D1 (config.py:88, ms.py:71,78) ✓; D2 (config.py:92) ✓; D3 corrected ✓; D4 (gen_proj:127-143,155; post-commit→sync-corpus.sh) ✓; D5 (plist) ✓; D6 (auth.py:16,24) ✓; D7 (guards.py:26-38, config.py:137) ✓; D8 (cron UTC; config.py:95) ✓; D9 ✓; D10 (weekly_review.py:79-90; sync_corpus.py:104-111) ✓; D11 ✓ |
| U4 | schema/restart semantics | checked | MAINTENANCE_SCHEDULER_ENABLED restart-Yes (server.py:6665) ✓; COMPACTION_ENABLED corrected ✓; INGESTION n/a ✓; ALLOW_REMOTE_WRITES per-call no restart (guards.py:29) ✓ |
| W1 | runtime/edge/verification | checked | problem cites all real (config.py:100; server.py:6663-6669,6646-6647; ms.py:71,78,58-68,19-25,83-89; config.py:114,97); mechanism corrected; acceptance coherent; rollback grounded (docs:154-155) |
| W2 | YAML authorability | checked | triggers/concurrency/permissions/8 steps/secrets concrete; cites sync_corpus.py:50-58,46-58,128-134; auth.py:8,24; ci.yml:28; weekly_review.py:71-76,29-31; weekly-review.sh:8 — all real |
| W3 | edit-site/edge | checked | insert before exit 0 line 24; gate line 15; cites 20-23,115-124,155-159,108-112,137-139,117-118 — all real |
| W4 | ops/re-homing | checked | five re-homed tasks each map to a live trigger (weekly_review.py:60-66/83-90/106-109/92-104/67-78); unload/neutralize/doc commands concrete; SETUP-weekly-review.md exists |
| W5 | heartbeat | checked | cron 0 12 * * 1; stamp parse (DIRECTIVES.md:4, weekly_review.py:26 regex shape); 9d=7+2 threshold explicit; red-on-stale |
| U5 | off-peak | checked | corrected mechanism; repo-git cron 0 3 * * 1 + DST accepted |
| U6 | sequencing | checked | WS4→WS3→WS1→WS2→WS5→observe→follow-up; no double-commit window; dry-run precedes real; step 7 restart consistent with §4 GAP-002 fix |
| U7 | rollback | checked | per-workstream; kill switch docs:154-155; idempotent stamp/corpus |
| U8 | approval/live-confirm | checked | 4 operator checks genuinely unverifiable-from-repo (ALLOW_REMOTE_WRITES live value, runner egress, live flag values, restart timing) |
| U9 | acceptance/tests | checked | 12 tests trace to WS acceptance; pass conditions concrete and observable from logs/git/job-summary |
| U10 | residual/files | checked | "None open"; 5 critical files match WS edit/retire targets |

Fresh-pass blocker ledger: **no new blocker gaps.** GAP-001 and GAP-002 confirmed closed; no contradiction, ungrounded claim, vague decision, or scope drift found on the full pass.

## Final Convergence Check

Final readiness proof:

| category | status | evidence |
| --- | --- | --- |
| runtime entry points & data flow | ready | server.py:6663-6669 scheduler wiring; ms.py:58-92 loop/tick; post-commit→sync-corpus.sh; weekly_review.py dynamic spark/gen-proj import |
| schema/fields/interfaces/helpers/artifacts | ready | app-setting names = uppercased fields (config.py:9 no env_prefix); --url/--refresh-trusted/--codex-config flags real; corpus tools run_corpus_upsert_workflow/corpus_deactivate (sync_corpus.py:82,93) |
| edge cases & failure behavior | ready | tick_error continues (ms.py:63-64); per-repo warn (79-80); skip-active (86-89); fail-loud CI (D10, probe step 4 + propagated exit); fail-open local hook (sync-corpus.sh:20-23) |
| resume behavior & idempotency | ready | idempotent stamp (weekly_review.py:29-31); idempotent corpus upsert + orphan prune (sync_corpus.py:128-134); dedup _enqueue_if_absent; push rebase-retry ≤3 |
| validation/tests/acceptance | ready | §9 12-row test matrix with concrete pass conditions; per-WS acceptance criteria observable |
| repo grounding | ready | every cited path:line re-verified against the repo; the one factually-wrong claim (first-tick timing) corrected (GAP-001); one overstated liveness claim corrected (GAP-002) |
| approval boundaries | ready | §8 four live confirmations isolated as operator checks; no design choice deferred |
| out-of-scope boundaries | ready | §2 explicit out-of-scope each with grounded rationale; first-cycle real-compaction deferred (D1/§6 step 7) |

Convergence: Cycle 2 is a no-edit fresh full-document assessment that found zero blocker gaps; both prior blockers closed with code-grounded evidence. **Converged (internal readiness only).**

Scope caveat: convergence here establishes internal document readiness — self-sufficient, decision-complete, internally consistent, every cited claim verified against the repo. It does NOT establish interop with sibling/shipped features, runtime/stored-data reality, or end-to-end requirement satisfaction. (Note: the upstream research.md already carries coverage + satisfaction audits; this plan-level loop only re-affirms internal readiness of the plan document.)
