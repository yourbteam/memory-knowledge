# Coverage Audit — Automation schedule for second-brain upkeep

Audited document: `Tasks/automation-schedule/research.md`
Gate: requirements-coverage-gap-loop (breadth). Upstream: passed internal-readiness (doc-gap-closure).
Grounding repo: `/Users/kamenkamenov/memory-knowledge` (jobs/*, config.py, server.py, Dockerfile, .github/workflows/ci.yml, working-agreement/weekly_review.py + wrappers).

This artifact holds the full coverage analysis. The chat reply summarizes.

---

## Requirement Inventory

| req_id | requirement | type | source (quoted) |
| --- | --- | --- | --- |
| R-INTEG | Integrity audit + compaction must run recurringly | explicit | research.md:20 "Integrity audit + compaction … per-repo data integrity + consolidation"; goal "recurring upkeep" research.md:4 |
| R-FRESH | Freshness re-ingest of changed repos must be addressed | explicit | research.md:21 "Freshness re-ingest … re-ingest changed repos" |
| R-SPARK | Directive Spark must run recurringly | explicit | research.md:22 "Directive Spark … mine brain telemetry → spark-candidates.md" |
| R-AGENTS | AGENTS.md refresh must be addressed | explicit | research.md:23 "AGENTS.md refresh … regenerate Codex projections across trusted repos" |
| R-STAMP | DIRECTIVES 'Last reviewed' stamp + commit must run recurringly | explicit | research.md:24 "DIRECTIVES.md 'Last reviewed' stamp + commit" |
| R-CORPUS | Corpus sync (DIRECTIVES→corpus) must remain covered | explicit | research.md:25 "Corpus sync … mirror directive edits into Tier-2 corpus" |
| R-CAPTURE | Auto-capture scheduling status must be addressed | explicit | research.md:26 "Auto-capture (#2) … session-close lessons → candidate notes" |
| R-NOMANUAL | No manual triggers; runs without a human kicking it | explicit | research.md:4 "no manual triggers" |
| R-MACHINEINDEP | Machine-independent; not dependent on one laptop awake | explicit | research.md:4-6 "machine-independent schedule … no dependence on a single laptop being awake" |
| R-MULTIMACHINE | Correct for a user across home/office machines | explicit | research.md:5 "Kamen works across home/office machines" |
| R-NOINCIDENT | Schedule must not re-arm the freshness/ingestion incident | explicit | research.md:6 "the freshness-scheduler auto-ingest risk (the prior incident)" |
| R-SHAREDINFRA | Must not overwhelm the shared single-worker Azure infra | explicit | research.md:5 "shared single-worker Azure infra" |
| R-OBSERV | A scheduled job that fails must be observable / alertable | implied | entailed by "reliable" research.md:4; doc §5 line 105 raises it |
| R-SECRETS | Secrets for any CI handled safely (no secrets in repo) | non-functional | Guard Rail (CLAUDE.md); doc §4.2 line 79, §5 line 104 |
| R-IDEMPOTENT | No double-run / safe across overlapping schedulers | implied/negative | doc §5 line 106 "Double-run"; new launchd+server overlap |
| R-RETIRE | Behavior when the laptop / launchd is retired | implied/boundary | entailed by machine-independence goal; "retire launchd" §4.5 |
| R-COST | Cost/quota of CI minutes | non-functional | entailed by introducing GitHub Actions cron |
| R-CADENCE | Timezone / cadence correctness | non-functional | doc §6.3 "Cadences", §7 cadence question |
| R-BACKCOMPAT | Backward-compat with existing post-commit hook + launchd plist | non-functional | doc §3 line 57 launchd, §1 line 25 post-commit |
| R-NEG-BRAINDOWN | Scheduler enabled but brain down | negative/boundary | user-specified boundary case |
| R-NEG-CIREACH | CI runner cannot reach the brain MCP endpoint | negative/boundary | doc §7 line 116 "whether a GitHub Actions runner can reach the brain MCP endpoint" |
| R-NEG-RUNNING | A job already running at tick | negative/boundary | dedup via _enqueue_if_absent; user boundary |
| R-NEG-MIDFLIGHT | DIRECTIVES changes while a refresh is mid-flight | negative/boundary | user-specified boundary case |
| R-NEG-NOORIGIN | A repo with no origin_url | negative/boundary | user-specified; ingestion_scheduler enumerate filters origin_url |
| R-NEG-CONCURRENT | Concurrent maintenance + dispatcher | negative/boundary | user-specified; dispatcher max_concurrent=1 |
| R-AUTH | MCP auth token the deployed brain requires for CI-originated calls | implied (blocks R-SPARK on CI) | doc §6.4, §7 line 115 |

Requirement-set size: **27** requirements.

---

## Obligation Decomposition

| req_id | obligation | source/why entailed |
| --- | --- | --- |
| R-INTEG | O1 integrity audit scheduled server-side; O2 compaction scheduled; O3 dry-run vs real-compaction decision; O4 off-peak tick | research.md §4.1 |
| R-FRESH | O1 disposition (enable/disable) decided; O2 incident-risk-bounded; O3 bootstrap full-ingest risk addressed; O4 path to safe re-enable | research.md §4.4 |
| R-SPARK | O1 scheduled machine-independently; O2 writes spark-candidates.md; O3 surfaced to user | research.md §4.2 |
| R-AGENTS | O1 locus decided; O2 cross-repo refresh feasibility; O3 staleness tolerance for non-checked-out repos | research.md §4.3, §6.2 |
| R-STAMP | O1 stamp bumped on schedule; O2 committed so post-commit sync fires | research.md §4.2 |
| R-CORPUS | O1 stays event-driven post-commit; O2 fired by the new stamp-commit path | research.md §1 line 25, §4.2 |
| R-CAPTURE | O1 explicit scope decision (event-hook, not schedule) | research.md:26 |
| R-NOMANUAL | O1 every kept task has a non-manual trigger; O2 no task left "manual" silently | research.md §1 trigger column |
| R-MACHINEINDEP | O1 each kept task runs on always-on infra (Azure or GitHub) | research.md §3 |
| R-MULTIMACHINE | O1 schedule correct regardless of which machine is used; O2 no per-machine duplication | research.md §3 launchd row |
| R-NOINCIDENT | O1 freshness path not silently re-enabled; O2 guard/allowlist; O3 bootstrap bound | research.md §4.4, §5 |
| R-SHAREDINFRA | O1 serialization; O2 enqueue bound; O3 off-peak timing | research.md §5 line 103 |
| R-OBSERV | O1 server-side failures observable; O2 CI failures observable; O3 silent no-op detected (cadence didn't fire) | research.md §5 line 105 |
| R-SECRETS | O1 MCP URL/token in GH secrets only; O2 not in repo | research.md §4.2, §5 line 104 |
| R-IDEMPOTENT | O1 server dedup; O2 launchd-vs-server overlap; O3 GH-cron-vs-launchd overlap (Spark/stamp) | research.md §5 line 106 |
| R-RETIRE | O1 nothing breaks when launchd removed; O2 no task ONLY on launchd left orphaned | entailed by §4.5 |
| R-COST | O1 CI minute usage bounded/acceptable | introducing GH cron |
| R-CADENCE | O1 maintenance cadence; O2 Spark cron day/time; O3 timezone correctness | research.md §6.3, §7 |
| R-BACKCOMPAT | O1 post-commit hook still works; O2 launchd plist coexistence/decommission defined | research.md §1, §3 |
| R-NEG-BRAINDOWN | O1 server scheduler behavior if DB/brain down; O2 CI behavior if brain unreachable | boundary |
| R-NEG-CIREACH | O1 detect unreachable; O2 fail visibly not silently | research.md §7 |
| R-NEG-RUNNING | O1 tick when job already running → skip | research.md §4.1 dedup |
| R-NEG-MIDFLIGHT | O1 DIRECTIVES edited during refresh → consistent result | boundary |
| R-NEG-NOORIGIN | O1 no-origin repo excluded from ingestion; O2 still gets maintenance | jobs SQL |
| R-NEG-CONCURRENT | O1 maintenance enqueues don't exceed worker; O2 dispatcher serializes | research.md §5 line 103 |
| R-AUTH | O1 token requirement confirmed/scoped; O2 CI cannot proceed unconfirmed | research.md §6.4, §7 |

---

## Cycle 1 Assessment

Lenses applied: elicitation completeness, omission, decomposition/partial, conflict, acceptance-criteria, scope-boundary, traceability, prioritization. Evidence cited as `research.md:line` for coverage and `repo path:line` for grounding.

### Coverage Matrix

| req_id.obligation | status | addressed where / rationale |
| --- | --- | --- |
| R-INTEG.O1 | addressed | research.md:67-75 (enable MaintenanceScheduler); grounded maintenance_scheduler.py:77 |
| R-INTEG.O2 | addressed | research.md:67-72; maintenance_scheduler.py:78 |
| R-INTEG.O3 | addressed (decision open, flagged) | research.md:71-72 "Decision: confirm whether first rollout enables real compaction"; §6.3 |
| R-INTEG.O4 | partial | research.md:74-75 "[inf] schedule off-peak … interval-based, no wall-clock" — names the limitation but no concrete mechanism for achieving off-peak with an interval loop |
| R-FRESH.O1 | addressed | research.md:86 "keep DISABLED for now" |
| R-FRESH.O2 | addressed | research.md:87-88; ingestion_scheduler.py:36-43 sentinel guard |
| R-FRESH.O3 | addressed | research.md:89-90 bootstrap full-ingest named; ingestion_scheduler.py:188 |
| R-FRESH.O4 | addressed | research.md:90-92 strict allowlist path; config.py:96 |
| R-SPARK.O1 | addressed | research.md:76-79 GH Actions cron |
| R-SPARK.O2 | addressed | research.md:77 commits spark-candidates.md |
| R-SPARK.O3 | **absent** | weekly_review.py:67-78 surfaces candidates to stderr (launchd log). On GH Actions, stderr → Actions log only; doc never says how Kamen is told candidates exist once launchd is retired. Silent drop of an existing capability. |
| R-AGENTS.O1 | addressed (decision open) | research.md:80-85, §6.2 |
| R-AGENTS.O2 | **partial/absent** | research.md:82-84 calls cross-repo refresh "awkward (needs each trusted repo checked out + pushed)". Grounding: refresh_trusted (generate_projections.py:127-143) writes AGENTS.md into LOCAL trusted-project working trees read from ~/.codex/config.toml; weekly-review.sh commits ONLY DIRECTIVES.md+spark-candidates.md — the other repos' AGENTS edits are left uncommitted in local trees. Doc's "recommended" event-driven refresh "scoped to repos checked out on the runner" has no mechanism and no acceptance criterion. |
| R-AGENTS.O3 | partial | research.md:84 "treat other repos' staleness as low-harm until next edit" — asserted, not given a testable bound |
| R-STAMP.O1 | addressed | research.md:76-77 |
| R-STAMP.O2 | addressed | research.md:77 "+ the stamp bump (which triggers the existing corpus sync)" |
| R-CORPUS.O1 | addressed | research.md:25 post-commit hook event-driven; sync-corpus.sh |
| R-CORPUS.O2 | partial | research.md:77 assumes GH-Actions commit of DIRECTIVES.md fires corpus sync, but the post-commit hook is a LOCAL git hook (.git/hooks/post-commit → sync-corpus.sh); it does NOT run on GitHub's servers when a commit lands via Actions push. Mechanism gap: how does the corpus sync fire for a CI-originated stamp commit? |
| R-CAPTURE.O1 | addressed (scoped out) | research.md:26 "client-side; out of scope for 'scheduling'" |
| R-NOMANUAL.O1 | addressed | research.md §4 each task gets a trigger |
| R-NOMANUAL.O2 | partial | R-FRESH stays "manual/explicit" (research.md:90) — acceptable as a scoped decision but is the one task left non-automated; called out but no acceptance criterion that this is the intended end-state |
| R-MACHINEINDEP.O1 | addressed | research.md §3 table; §4 |
| R-MULTIMACHINE.O1 | addressed | research.md:57-61 reject launchd as primary |
| R-MULTIMACHINE.O2 | **absent** | If launchd is kept as "local fallback" (research.md:93-94) on BOTH home and office machines, each fires weekly → duplicate Spark commits / duplicate AGENTS writes / double maintenance enqueues. Doc dedupes server maintenance (_enqueue_if_absent) but not the git-side duplication across two laptops both running launchd + the GH cron. No mechanism. |
| R-NOINCIDENT.O1 | addressed | research.md:86, §5 line 102 |
| R-NOINCIDENT.O2 | addressed | research.md:91; config.py:96 allowlist |
| R-NOINCIDENT.O3 | addressed | research.md:89-90 |
| R-SHAREDINFRA.O1 | addressed | research.md:73 dispatcher max_concurrent=1; config.py:114 |
| R-SHAREDINFRA.O2 | partial | research.md:103 "max_per_tick bounds enqueues" — true for ingestion (config.py:97) but maintenance scheduler has NO max_per_tick; it enqueues 2 jobs × every real repo per tick (maintenance_scheduler.py:72-78). Doc attributes a bound to maintenance that does not exist. |
| R-SHAREDINFRA.O3 | partial | same as R-INTEG.O4 — off-peak not mechanizable on interval loop |
| R-OBSERV.O1 | addressed | research.md:105 brain logs maintenance_scheduler_tick_complete; maintenance_scheduler.py:81 |
| R-OBSERV.O2 | addressed | research.md:105 GitHub Actions emails on failed runs |
| R-OBSERV.O3 | **absent** | research.md:105 "[inf] add explicit failure alerting (no silent no-op cadence)" names the need but gives NO mechanism for detecting a scheduler that silently STOPPED ticking (the exact launchd failure mode: it never ran, stamp stuck at 2026-06-19, research.md:61). A failed run emails; a run that never fires emits nothing. No heartbeat/dead-man's-switch mechanism or acceptance criterion. |
| R-SECRETS.O1 | addressed | research.md:78-79 GH secrets |
| R-SECRETS.O2 | addressed | research.md:79 "no secrets in the repo — Guard Rail" |
| R-IDEMPOTENT.O1 | addressed | research.md:73,106; maintenance_scheduler.py:83-89 |
| R-IDEMPOTENT.O2 | addressed | research.md:106 disable launchd consolidation step |
| R-IDEMPOTENT.O3 | **absent** | GH-cron Spark/stamp vs a still-loaded launchd both commit DIRECTIVES/spark-candidates → conflicting/duplicate commits & races. research.md:106 only covers maintenance double-enqueue (server-deduped), not the git-commit-level double-run between GH cron and launchd. |
| R-RETIRE.O1 | partial | research.md:93-94 "retire launchd as the primary" but doesn't enumerate that EVERY task launchd uniquely did is now covered elsewhere; AGENTS cross-repo refresh (R-AGENTS.O2) and candidate-surfacing (R-SPARK.O3) were launchd-only and are not re-homed |
| R-RETIRE.O2 | **absent** | no checklist that no task remains launchd-only after retirement; ties to R-AGENTS.O2, R-SPARK.O3 gaps |
| R-COST.O1 | **absent** | doc introduces a weekly GH Actions cron (research.md:76) but never mentions CI-minute cost/quota acceptability (a named requirement in the task). No statement (even "negligible — one weekly run"). |
| R-CADENCE.O1 | addressed (open) | research.md §6.3 maintenance weekly 604800s |
| R-CADENCE.O2 | addressed (open) | research.md §6.3 Spark cron day/time — flagged as decision |
| R-CADENCE.O3 | **absent** | GH Actions cron is UTC-only; launchd/ingestion use Europe/Sofia (config.py:95, plist Hour 9 local). Doc never reconciles that a "weekly 9am" intent expressed in cron must be written in UTC and will drift with DST. Timezone-correctness obligation unaddressed for the GH cron. |
| R-BACKCOMPAT.O1 | addressed | research.md:25 hook unchanged |
| R-BACKCOMPAT.O2 | partial | research.md:93-94 keep plist as optional fallback — coexistence rule under-specified (see R-IDEMPOTENT.O3, R-MULTIMACHINE.O2) |
| R-NEG-BRAINDOWN.O1 | partial | maintenance_scheduler.py:63-64 catches tick exceptions & logs; doc doesn't state the resulting behavior (skips a week silently → ties to R-OBSERV.O3) |
| R-NEG-BRAINDOWN.O2 | **absent** | CI Spark call when brain unreachable: weekly_review.py:89-90 swallows the exception ("continuing"), so the GH job could exit 0 with no Spark done and no failure email. Doc assumes "Actions emails on failure" but the best-effort code makes failure invisible. Unaddressed. |
| R-NEG-CIREACH.O1 | partial | research.md:116 lists "whether a runner can reach the brain" as UNVERIFIED — elicited but not addressed (no mechanism, deferred to gates) |
| R-NEG-CIREACH.O2 | **absent** | same swallow-and-exit-0 problem as R-NEG-BRAINDOWN.O2 |
| R-NEG-RUNNING.O1 | addressed | research.md:73; maintenance_scheduler.py:86-89; ingestion_scheduler.py:204-214 |
| R-NEG-MIDFLIGHT.O1 | **absent** | DIRECTIVES edited (local commit → corpus sync) while a CI Spark/stamp run is mid-flight, or two stamp commits interleave → last-writer-wins / merge conflict on push. Not addressed. |
| R-NEG-NOORIGIN.O1 | addressed | ingestion_scheduler.py:31 WHERE origin_url IS NOT NULL |
| R-NEG-NOORIGIN.O2 | addressed | maintenance_scheduler.py:18 "origin_url is not required" — no-origin repos still get maintenance; doc §1 line 20 implies it but could be explicit |
| R-NEG-CONCURRENT.O1 | partial | dispatcher serializes execution (max_concurrent=1) but maintenance enqueues unboundedly (R-SHAREDINFRA.O2); queue depth, not worker, is the contention |
| R-NEG-CONCURRENT.O2 | addressed | research.md:103; config.py:114 |
| R-AUTH.O1 | partial | research.md:112,115 elicited as open decision/unverified — not resolved, deferred to gates (acceptable as scoped-open IF flagged as blocking R-SPARK on CI) |
| R-AUTH.O2 | addressed | research.md:112 "Needs confirming before the GitHub Action can call Spark" — dependency stated |

### Acceptance-Criteria presence (Cycle 1)

The doc carries decisions and risks but, being a research/findings doc, has almost **no testable acceptance criteria** per requirement. This is itself a coverage gap (lens 5) for every requirement: there is no "this requirement is covered when X is observably true." Tracked as a cross-cutting blocker (CGAP-013) plus per-requirement criteria added during fixes.

### Conflict Register (Cycle 1)

| pair | tension | reconciled? |
| --- | --- | --- |
| R-MACHINEINDEP vs R-BACKCOMPAT (keep launchd) | keeping launchd reintroduces single-machine dependence and double-run | NOT reconciled — CGAP-003, CGAP-006 |
| R-CORPUS (post-commit hook) vs R-SPARK/R-STAMP (CI commits) | local hook won't fire on CI push | NOT reconciled — CGAP-002 |
| R-SHAREDINFRA (bounded) vs R-INTEG (maintenance enqueues per repo, unbounded) | claimed bound doesn't exist for maintenance | NOT reconciled — CGAP-005 |

### Blocker Gap Ledger (Cycle 1)

| gap_id | severity | req_id.obligation | lens | evidence | why uncovered | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CGAP-001 | blocker | R-AGENTS.O2/O3 | omission/partial | research.md:82-84 vs generate_projections.py:127-143 (writes local trees, wrapper commits only DIRECTIVES+spark) | "recommended" event-driven cross-repo refresh has no mechanism; uncommitted AGENTS edits in other repos; staleness bound untestable | Add concrete locus mechanism + explicit scoped staleness bound + acceptance criterion | | open |
| CGAP-002 | blocker | R-CORPUS.O2 | conflict | research.md:77 assumes stamp commit fires corpus sync; .git/hooks/post-commit is local-only | CI push won't run the local post-commit hook → corpus never updated from CI stamp | Specify how corpus sync fires for CI-originated stamp (e.g. CI runs sync_corpus.py directly, or stamp commit done locally) + criterion | | open |
| CGAP-003 | blocker | R-MULTIMACHINE.O2 | omission/conflict | research.md:93-94 keep launchd fallback on multiple laptops | two laptops + GH cron all fire weekly → duplicate git commits/AGENTS writes/maintenance enqueues | Add multi-machine dedup rule or scope launchd-fallback to single-machine-only with rationale + criterion | | open |
| CGAP-004 | blocker | R-SPARK.O3 | silent-drop | research.md (none) vs weekly_review.py:67-78 surfaces candidates | candidate-surfacing existed via launchd stderr; on CI it's buried in Actions logs, no notification path | Add a surfacing mechanism for CI (job summary / issue / notification) or explicit scope-out + criterion | | open |
| CGAP-005 | blocker | R-SHAREDINFRA.O2 | partial/conflict | research.md:103 "max_per_tick bounds enqueues" vs maintenance_scheduler.py:72-78 (no cap) | doc attributes an enqueue bound to maintenance that doesn't exist; contention is queue depth | Correct the claim; state real bound (per-repo + _enqueue_if_absent dedup) or add mitigation + criterion | | open |
| CGAP-006 | blocker | R-IDEMPOTENT.O3 | conflict | research.md:106 covers only server dedup | GH-cron vs launchd both commit DIRECTIVES/spark → racing/duplicate commits | Reconcile: if launchd kept, define which owns the commit; else retire fully + criterion | | open |
| CGAP-007 | blocker | R-OBSERV.O3 | omission | research.md:105 "[inf] add explicit failure alerting (no silent no-op cadence)" | no mechanism to detect a scheduler that STOPPED firing (the actual launchd failure: never ran) | Add a dead-man's-switch / staleness-of-stamp check mechanism + criterion | | open |
| CGAP-008 | blocker | R-NEG-BRAINDOWN.O2 / R-NEG-CIREACH.O2 | omission/conflict | weekly_review.py:89-90 swallows MCP errors → exit 0; research.md:105 assumes failure emails | best-effort code makes CI brain-unreachable invisible; Actions won't email on a green run | Specify CI must fail (non-zero) on brain-unreachable for the scheduled run, or accept-with-rationale + criterion | | open |
| CGAP-009 | blocker | R-COST.O1 | omission | research.md (none) | CI-minute cost/quota named in requirements never addressed | Add a cost statement (e.g. one weekly run, negligible) + criterion | | open |
| CGAP-010 | blocker | R-CADENCE.O3 | omission | research.md (none) vs cron-is-UTC, config.py:95 Europe/Sofia | timezone correctness for the GH cron unaddressed; DST drift | State cron must be UTC-anchored, note DST behavior + criterion | | open |
| CGAP-011 | blocker | R-NEG-MIDFLIGHT.O1 | omission | research.md (none) | concurrent DIRECTIVES edit vs CI stamp commit → push race/conflict | Add handling (rebase/retry, or local-only stamp) + criterion | | open |
| CGAP-012 | blocker | R-RETIRE.O2 | omission | research.md:93-94 | no verification that no task remains launchd-only after retirement | Add a re-homing checklist tying R-AGENTS.O2 + R-SPARK.O3 + criterion | | open |
| CGAP-013 | blocker | ALL (acceptance criteria) | acceptance-criteria | research.md (none structured) | research doc has no per-requirement testable acceptance criteria | Add an acceptance-criteria table for the recommended schedule + each kept task | | open |
| CGAP-014 | cleanup | R-NEG-NOORIGIN.O2 | traceability | maintenance_scheduler.py:18 | maintenance covers no-origin repos but doc only implies it | Make explicit (minor) | | open |

Cleanup list: CGAP-014.

Cycle 1 result: **14 gaps (13 blocker, 1 cleanup)**. Proceeding to Cycle 1 Plan + Edits.

---

## Cycle 1 Plan

Decision-complete map of each open gap → exact doc edit (document only; no runtime code changed):

- CGAP-001 → §4.3: replace hand-wave with grounded mechanism (local refresh_trusted, not CI/server), explicit scoped staleness bound, acceptance criterion.
- CGAP-002 → §4.2 bullet: corpus sync must be an explicit CI step (run sync_corpus.py); criterion.
- CGAP-003 → §4.5 bullet: multi-machine duplication rule (launchd retired everywhere; fallback ≤1 machine, no-commit); criterion.
- CGAP-004 → §4.5 bullet: candidate surfacing on CI via job summary + notification; criterion.
- CGAP-005 → §4.1 + §5: correct the false maintenance max_per_tick claim; state real bound; criterion.
- CGAP-006 → §4.2 + §5: single-committer rule; criterion.
- CGAP-007 → §5: dead-man's-switch for dead cadence; criterion.
- CGAP-008 → §5: scheduled CI must fail loud on brain-unreachable; criterion.
- CGAP-009 → §5: CI-minute cost statement; criterion.
- CGAP-010 → §5: cron-UTC/DST reconciliation; criterion.
- CGAP-011 → §4.2 bullet: concurrent-edit rebase/retry; criterion.
- CGAP-012 → §4.5 bullet: re-homing checklist; criterion.
- CGAP-013 → new §5b: per-task acceptance-criteria table.
- CGAP-014 → §5: make no-origin maintenance coverage explicit.

## Cycle 1 Edits

| gap_id | edit applied | location |
| --- | --- | --- |
| CGAP-001 | grounded mechanism + scoped staleness + criterion | research.md §4.3 |
| CGAP-002 | explicit CI corpus-sync step + criterion | research.md §4.2 |
| CGAP-003 | multi-machine single-commit rule + criterion | research.md §4.5 |
| CGAP-004 | CI candidate surfacing (job summary/issue) + criterion | research.md §4.5 |
| CGAP-005 | corrected enqueue-bound claim + real bound + criterion | research.md §4.1, §5 |
| CGAP-006 | sole-committer reconciliation + criterion | research.md §4.2, §5 |
| CGAP-007 | dead-man's-switch monitor + criterion | research.md §5, §5b |
| CGAP-008 | scheduled-path fail-loud rule + criterion | research.md §5 |
| CGAP-009 | CI cost statement + criterion | research.md §5 |
| CGAP-010 | UTC/DST reconciliation + criterion | research.md §5 |
| CGAP-011 | rebase/retry on concurrent edit + criterion | research.md §4.2 |
| CGAP-012 | re-homing checklist + criterion | research.md §4.5 |
| CGAP-013 | per-task acceptance-criteria table | research.md §5b |
| CGAP-014 | explicit no-origin maintenance note | research.md §5 |
| (extra) | R-NOMANUAL.O2 explicit scope note + criterion | research.md §4.4 |
| (extra) | §7 cross-repo AGENTS resolved; R-AUTH flagged as blocking R-SPARK-on-CI | research.md §6.2, §7 |

## Cycle 1 Validation

Re-read each edited section; confirmed each newly-covered obligation now has a **concrete mechanism or an explicit scoped-out statement** AND a testable acceptance criterion. Grounding re-verified against the repo:

- post-commit hook is local-only (`.git/hooks/post-commit` → `sync-corpus.sh`; the script gates on `git diff-tree HEAD` of the just-made local commit) → CGAP-002 mechanism is correct: CI must call `sync_corpus.py` itself.
- `weekly_review.py:79-80, 89-90` swallow exceptions and `main()` returns 0 → CGAP-008 fail-loud requirement is correct.
- maintenance scheduler has no `max_per_tick` (`maintenance_scheduler.py:70-81`) while ingestion does (`config.py:97`) → CGAP-005 correction is accurate.
- `refresh_trusted` writes local trees, wrapper commits only DIRECTIVES+spark (`weekly-review.sh`) → CGAP-001/§7 resolution is accurate.
- No existing GH cron / `workflow_dispatch` in `.github/` (only `ci.yml` push/PR); launchd not currently loaded; no `/tmp/mk-weekly-review.log` → confirms "never ran" framing and that the schedule is greenfield.

### Post-Edit New-Gap Pass (after Cycle 1 edits)

Checked whether new mechanisms introduced new obligations/conflicts:
- New **dead-man's-switch monitor** (CGAP-007) is itself a scheduled job → does *it* need observability? It is the observer of last resort; its own failure mode (GH Actions cron not firing) is covered by GitHub's own failed-run email on the monitor + the fact that two independent schedulers (server + GH) would both have to silently die. Acceptable; noted, not a blocker.
- New **explicit CI corpus-sync step** (CGAP-002) introduces a second corpus writer (CI + local hook). Could they conflict? Corpus upsert is keyed/idempotent (mirror = upsert current + deactivate orphans, per `sync-corpus.sh` header); concurrent local+CI sync converge to the same directive state. No new conflict.
- New **rebase/retry** (CGAP-011) relies on `bump_review_stamp` idempotency — verified `count=1` regex substitution (`weekly_review.py:29-31`) is safe to re-apply. No new gap.
- New **single-committer** rule (CGAP-006) fully subsumes the old double-run line; no orphaned obligation.
No new blocker gaps found.

---

## Cycle 2 Assessment (fresh full pass over the edited document)

Re-ran all 8 lenses over the complete 27-requirement / 60-obligation set against the edited `research.md`.

### Coverage Matrix (Cycle 2 — only previously-open obligations shown; all others remain addressed as in Cycle 1)

| req_id.obligation | status | addressed where (research.md) |
| --- | --- | --- |
| R-INTEG.O4 (off-peak) | addressed | §4.1 (restart-time anchor or scoped-out w/ serialization rationale) + criterion |
| R-AGENTS.O2 (cross-repo refresh) | addressed (scoped) | §4.3 + §7 — local-only mechanism; CI ruled out with rationale + criterion |
| R-AGENTS.O3 (staleness) | addressed (scoped) | §4.3 — bounded low-harm staleness + criterion |
| R-CORPUS.O2 (CI commit fires sync) | addressed | §4.2 explicit CI sync step + criterion |
| R-SPARK.O3 (surface candidates) | addressed | §4.5 job summary + notification + criterion |
| R-MULTIMACHINE.O2 (no per-machine dup) | addressed | §4.5 single-commit rule + criterion |
| R-SHAREDINFRA.O2 (enqueue bound) | addressed | §4.1, §5 corrected claim + real bound + criterion |
| R-SHAREDINFRA.O3 (off-peak) | addressed | §4.1 (= R-INTEG.O4) |
| R-OBSERV.O3 (dead cadence) | addressed | §5 dead-man's-switch + criterion |
| R-IDEMPOTENT.O3 (git double-run) | addressed | §4.2, §5 sole-committer + criterion |
| R-RETIRE.O1/O2 (re-homing) | addressed | §4.5 checklist + criterion |
| R-COST.O1 | addressed | §5 cost statement + criterion |
| R-CADENCE.O3 (timezone) | addressed | §5 UTC/DST reconciliation + criterion |
| R-BACKCOMPAT.O2 | addressed | §4.5 / §5 coexistence rules |
| R-NEG-BRAINDOWN.O1 | addressed | §5 (tick-error logged) + dead-man's-switch for the silent case |
| R-NEG-BRAINDOWN.O2 | addressed | §5 scheduled-path fail-loud + criterion |
| R-NEG-CIREACH.O1/O2 | addressed | §5 fail-loud + reachability probe + criterion |
| R-NEG-MIDFLIGHT.O1 | addressed | §4.2 rebase/retry + idempotent stamp + criterion |
| R-NEG-CONCURRENT.O1 | addressed | §4.1 enqueue bound + serialization; §5 |
| R-NEG-NOORIGIN.O2 | addressed | §5 explicit note |
| R-NOMANUAL.O2 | addressed (scoped) | §4.4 explicit incident-driven exception + criterion |
| R-AUTH.O1 | addressed (scoped-open) | §7 flagged as blocking R-SPARK-on-CI; explicit dependency, not silent |
| ALL (acceptance criteria) | addressed | §5b per-task table + inline criteria |

### Conflict Register (Cycle 2)

| pair | reconciled? |
| --- | --- |
| R-MACHINEINDEP vs R-BACKCOMPAT (launchd) | YES — §4.5 launchd retired everywhere; fallback ≤1 machine no-commit |
| R-CORPUS vs R-SPARK/R-STAMP (CI commit) | YES — §4.2 CI runs sync_corpus.py explicitly |
| R-SHAREDINFRA vs R-INTEG (enqueue volume) | YES — §4.1/§5 claim corrected; bound = serialization + dedup |

All three Cycle-1 conflicts reconciled. No new conflicts.

### Blocker Gap Ledger (Cycle 2)

Zero new blocker gaps. All CGAP-001…CGAP-014 marked **closed** (see ledger update below).

Per the hard-stop rule, this cycle is an **assessment over the edited document**; it made **no edits**. Convergence is declared in the next, no-edit cycle's Final Convergence Check.

---

## Cycle 3 — Final Convergence Check (no edits)

Fresh full pass; zero blockers discoverable. The requirement set (27 requirements, 60 obligations) is complete across explicit / implied / non-functional / negative sources; every obligation traces to an addressing mechanism in `research.md` or an explicit scoped-out statement with rationale; every kept task carries a testable acceptance criterion (§5b + inline); the three requirement conflicts are reconciled. No edits were made in this cycle.

### Updated Gap Ledger (final)

| gap_id | req_id.obligation | status | closure evidence (research.md) |
| --- | --- | --- | --- |
| CGAP-001 | R-AGENTS.O2/O3 | closed | §4.3 local mechanism + scoped staleness + criterion |
| CGAP-002 | R-CORPUS.O2 | closed | §4.2 CI sync step + criterion |
| CGAP-003 | R-MULTIMACHINE.O2 | closed | §4.5 single-commit + criterion |
| CGAP-004 | R-SPARK.O3 | closed | §4.5 surfacing + criterion |
| CGAP-005 | R-SHAREDINFRA.O2 | closed | §4.1/§5 corrected bound + criterion |
| CGAP-006 | R-IDEMPOTENT.O3 | closed | §4.2/§5 sole-committer + criterion |
| CGAP-007 | R-OBSERV.O3 | closed | §5 dead-man's-switch + criterion |
| CGAP-008 | R-NEG-BRAINDOWN.O2/R-NEG-CIREACH.O2 | closed | §5 fail-loud + criterion |
| CGAP-009 | R-COST.O1 | closed | §5 cost statement + criterion |
| CGAP-010 | R-CADENCE.O3 | closed | §5 UTC/DST + criterion |
| CGAP-011 | R-NEG-MIDFLIGHT.O1 | closed | §4.2 rebase/retry + criterion |
| CGAP-012 | R-RETIRE.O2 | closed | §4.5 re-homing checklist + criterion |
| CGAP-013 | ALL (criteria) | closed | §5b table + inline |
| CGAP-014 | R-NEG-NOORIGIN.O2 | closed (cleanup) | §5 explicit note |

### Final Coverage Proof

| req_id | every obligation covered or scoped-out? | acceptance criterion present? | evidence |
| --- | --- | --- | --- |
| R-INTEG | yes | yes | §4.1, §5b |
| R-FRESH | yes (scoped disabled) | yes | §4.4, §5b |
| R-SPARK | yes | yes | §4.2, §4.5, §5b |
| R-AGENTS | yes (scoped local) | yes | §4.3, §7, §5b |
| R-STAMP | yes | yes | §4.2, §5b |
| R-CORPUS | yes | yes | §4.2, §5b |
| R-CAPTURE | yes (scoped-out) | yes | §1, §5b |
| R-NOMANUAL | yes (freshness scoped exception) | yes | §4, §4.4 |
| R-MACHINEINDEP | yes | yes | §3, §4 |
| R-MULTIMACHINE | yes | yes | §4.5 |
| R-NOINCIDENT | yes | yes | §4.4, §5 |
| R-SHAREDINFRA | yes | yes | §4.1, §5 |
| R-OBSERV | yes | yes | §5 |
| R-SECRETS | yes | yes | §4.2, §5 |
| R-IDEMPOTENT | yes | yes | §4.2, §5 |
| R-RETIRE | yes | yes | §4.5 |
| R-COST | yes | yes | §5 |
| R-CADENCE | yes | yes | §5, §6.3 |
| R-BACKCOMPAT | yes | yes | §4.5, §5 |
| R-NEG-BRAINDOWN | yes | yes | §5 |
| R-NEG-CIREACH | yes | yes | §5 |
| R-NEG-RUNNING | yes | yes | §4.1 |
| R-NEG-MIDFLIGHT | yes | yes | §4.2 |
| R-NEG-NOORIGIN | yes | yes | §5 |
| R-NEG-CONCURRENT | yes | yes | §4.1, §5 |
| R-AUTH | yes (scoped-open, flagged blocking) | yes | §7 |

**Convergence: ACHIEVED (breadth).** All 27 requirements / 60 obligations addressed or explicitly scoped-out with rationale; all carry testable acceptance criteria; all conflicts reconciled. This establishes breadth (every requirement addressed), not depth.

**Requirement intentionally excluded:** R-FRESH auto-ingest stays **disabled** (incident-driven, §4.4) and R-CAPTURE scheduling is **out of scope** (event-hook, §1) — both explicit with rationale.

**User decision still pending (does not block coverage):** R-AUTH — whether/what MCP auth token the deployed brain requires for CI calls (§7). Coverage treats it as an explicit, flagged dependency that gates only R-SPARK-on-CI; it must be resolved in the satisfaction/depth pass or the plan before the CI workflow can call the brain.

Next gate: **requirements-satisfaction-gap-loop** (depth) — verify each addressed requirement holds end-to-end against the real runtime, stored data, and sibling features.
