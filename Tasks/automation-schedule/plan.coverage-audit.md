# Coverage Audit — Plan: Automation schedule for second-brain upkeep

Audited document: `Tasks/automation-schedule/plan.md`
Gate: requirements-coverage-gap-loop (breadth). Upstream: passed internal-readiness (`plan.gap-audit.md`).
Source requirement set carried from: `research.md` + `research.coverage-audit.md` (27 requirements / 60 obligations, converged) + `research.satisfaction-audit.md` + `research.gap-audit.md`.
Grounding repo: `/Users/kamenkamenov/memory-knowledge` (verified live: `jobs/maintenance_scheduler.py`, `config.py`, `server.py`, `middleware/auth.py`, `guards.py`, `working-agreement/{weekly_review,sync_corpus,generate_projections}.py`, `working-agreement/{sync-corpus.sh,weekly-review.sh}`, `.git/hooks/post-commit`, the plist, live `launchctl list`, live `DIRECTIVES.md` stamp).

This artifact holds the full coverage analysis. The chat reply summarizes.

**Convergence:** ACHIEVED (breadth) at Cycle 3 (no-edit). 3 blocker coverage gaps found and closed in Cycle 1; zero new in Cycle 2; fresh full pass in Cycle 3 found zero.

---

## Method note — what "the requirement set" is for the PLAN gate

The plan is downstream of an already-converged research coverage pass (27 req / 60 obl). This gate verifies two things:

1. **No regression** — every research requirement/obligation/finding (and each research CGAP-xxx / SGAP-xxx closure) is **carried into the plan** as a concrete plan mechanism or an explicit scoped-out statement, not silently dropped.
2. **Plan-introduced obligations** — the plan commits to *executable* mechanisms the research stated only abstractly (a YAML workflow, a `curl` probe, a `sync_corpus.py` invocation order, a restart-anchored tick, a regex heartbeat). Each such mechanism creates new obligations (its inputs must be defined, its ordering must hold, its claimed coverage must actually cover). These are decomposed and traced here even though they did not exist at the research layer.

The 5 workstreams (WS1–WS5) and 11 locked decisions (D1–D11) are the plan's structural units; every research requirement maps onto one or more of them.

---

## Requirement Inventory (carried from research; same 27 req_ids)

| req_id | requirement | type | carried-into-plan anchor |
| --- | --- | --- | --- |
| R-INTEG | Integrity audit + compaction run recurringly | explicit | WS1, D1, D3 |
| R-FRESH | Freshness re-ingest addressed | explicit | §2 out-of-scope, D2 |
| R-SPARK | Directive Spark runs recurringly | explicit | WS2, D8/D9 |
| R-AGENTS | AGENTS.md refresh addressed | explicit | WS3, D4 |
| R-STAMP | DIRECTIVES stamp + commit runs recurringly | explicit | WS2, D9 |
| R-CORPUS | Corpus sync remains covered | explicit | WS2 step 7, WS3 (local hook), D7 |
| R-CAPTURE | Auto-capture scope addressed | explicit | §2 out-of-scope |
| R-NOMANUAL | No manual triggers | explicit | §1, §2 (freshness exception) |
| R-MACHINEINDEP | Machine-independent | explicit | WS1 (Azure) + WS2/WS5 (GitHub) |
| R-MULTIMACHINE | Correct across home/office | explicit | WS4, D9 |
| R-NOINCIDENT | Don't re-arm freshness incident | explicit | D2, §2 |
| R-SHAREDINFRA | Don't overwhelm shared worker | explicit | WS1 (problem + edge cases) |
| R-OBSERV | Scheduled failure observable | implied | WS1 logs, WS2 emails, WS5 dead-man |
| R-SECRETS | CI secrets safe | non-functional | WS2 secrets, D6 |
| R-IDEMPOTENT | No double-run | implied/negative | D9, WS4, WS2 idempotent stamp/upsert |
| R-RETIRE | launchd retirement clean | implied/boundary | WS4 re-homing checklist |
| R-COST | CI minute cost bounded | non-functional | WS2 verification (CGAP-009) |
| R-CADENCE | Timezone/cadence correct | non-functional | D8, §5 |
| R-BACKCOMPAT | Post-commit hook + plist coexistence | non-functional | WS3, WS4, §7 rollback |
| R-NEG-BRAINDOWN | Brain down while scheduled | negative/boundary | WS1 edge cases, D10, WS2 probe |
| R-NEG-CIREACH | CI runner can't reach brain | negative/boundary | WS2 step 4 probe, §8.2 |
| R-NEG-RUNNING | Job already running at tick | negative/boundary | WS1 (_ACTIVE_BY_TOOL) |
| R-NEG-MIDFLIGHT | DIRECTIVES edit mid-refresh / mid-run | negative/boundary | WS2 step 6 rebase/retry |
| R-NEG-NOORIGIN | No-origin repo | negative/boundary | WS1 edge cases |
| R-NEG-CONCURRENT | Concurrent maintenance + dispatcher | negative/boundary | WS1 (serialization + dedup) |
| R-AUTH | MCP auth for CI | implied (was blocking) | D6 — RESOLVED (no token) |

Carried requirement-set size: **27** (unchanged). Plus **plan-introduced obligations** decomposed below (P-prefixed).

---

## Obligation Decomposition — carried obligations (research) + plan-introduced (P-*)

### Carried obligations (must not regress; each must map to a plan mechanism or explicit scope-out)

| req_id | obligation | research closure (must be carried) | plan anchor |
| --- | --- | --- | --- |
| R-INTEG.O1 | integrity audit scheduled server-side | §4.1 | WS1 (`plan.md:64-68`); AC `plan.md:74` |
| R-INTEG.O2 | compaction scheduled | §4.1 | WS1; D1 `plan.md:35` |
| R-INTEG.O3 | dry-run vs real decision | CGAP closure | D1 dry-run-first `plan.md:35`; follow-up §6.7 `plan.md:193` |
| R-INTEG.O4 | off-peak tick | CGAP-001 (restart anchor) | D3 `plan.md:37`; §5 `plan.md:181`; AC `plan.md:75` |
| R-FRESH.O1–O4 | disabled / incident-bounded / bootstrap / re-enable path | §4.4 | D2 `plan.md:36`; §2 out-of-scope `plan.md:25` |
| R-SPARK.O1 | scheduled machine-independently | §4.2 | WS2 `plan.md:89` |
| R-SPARK.O2 | writes spark-candidates.md | §4.2 | WS2 step 5 `plan.md:97` |
| R-SPARK.O3 | surfaced to user (CGAP-004) | §4.5 job summary | WS2 step 8 `plan.md:100`; AC `plan.md:108` |
| R-AGENTS.O1 | locus decided (local) | §4.3 | D4 `plan.md:38`; WS3 `plan.md:120-122` |
| R-AGENTS.O2 | cross-repo feasibility (CI ruled out) | §7 scoped-out | §2 out-of-scope `plan.md:27` |
| R-AGENTS.O3 | staleness bound | §4.3 | WS3 bounded-staleness `plan.md:124` |
| R-STAMP.O1/O2 | stamp bumped + committed | §4.2 | WS2 steps 5–6 `plan.md:97-98` |
| R-CORPUS.O1 | stays event-driven post-commit (local) | §1/§4.2 | WS3 inherits hook; D-context |
| R-CORPUS.O2 | CI commit fires sync (CGAP-002/SGAP-003) | §4.2 explicit step | WS2 step 7 `plan.md:99` |
| R-CAPTURE.O1 | scoped out | §1 | §2 out-of-scope `plan.md:26` |
| R-NOMANUAL.O1/O2 | every task has non-manual trigger; freshness exception explicit | §4/§4.4 | §1, §2; WS4 re-homing `plan.md:141-145` |
| R-MACHINEINDEP.O1 | always-on infra | §3 | WS1+WS2/WS5 |
| R-MULTIMACHINE.O1/O2 | correct per machine; no per-machine dup (CGAP-003) | §4.5 single-commit | D9 `plan.md:43`; WS4 `plan.md:147-150` |
| R-NOINCIDENT.O1–O3 | freshness not silently re-enabled / guard / bootstrap | §4.4/§5 | D2; §2 |
| R-SHAREDINFRA.O1 | serialization | §5 | WS1 `plan.md:60` |
| R-SHAREDINFRA.O2 | enqueue bound — corrected (CGAP-005) | §4.1 (no cap; dedup+serialize) | WS1 `plan.md:60`; AC `plan.md:73` |
| R-SHAREDINFRA.O3 | off-peak (SGAP-001 harness co-tenancy) | §4.1 | D3 `plan.md:37`; WS1 problem `plan.md:60`; AC `plan.md:76` |
| R-OBSERV.O1 | server failures observable | §5 | WS1 `plan.md:78`; AC `plan.md:72-73` |
| R-OBSERV.O2 | CI failures observable | §5 | WS2 emails (D10) |
| R-OBSERV.O3 | silent no-op / dead cadence detected (CGAP-007) — **for either GH cron OR server scheduler** | §5 dead-man + criterion | WS5 `plan.md:165-171`; D11 |
| R-SECRETS.O1/O2 | secrets in GH only, not repo | §4.2 | WS2 `plan.md:101` |
| R-IDEMPOTENT.O1–O3 | server dedup; launchd-vs-server; GH-vs-launchd git double-run (CGAP-006) | §5 sole-committer | D9 `plan.md:43`; WS4 `plan.md:155` |
| R-RETIRE.O1/O2 | nothing breaks; no launchd-only task left (CGAP-012) | §4.5 re-homing checklist | WS4 table `plan.md:141-145`; AC `plan.md:153` |
| R-COST.O1 | CI minutes bounded (CGAP-009) | §5 | WS2 verification `plan.md:112` |
| R-CADENCE.O1–O3 | maintenance cadence; Spark cron time; UTC/DST (CGAP-010) | §5 | D3, D8 `plan.md:42`; §5 `plan.md:182` |
| R-BACKCOMPAT.O1/O2 | hook works; plist decommission | §4.5 | WS3; WS4; §7 |
| R-NEG-BRAINDOWN.O1 | server tick-error logged | §5 | WS1 edge `plan.md:78` |
| R-NEG-BRAINDOWN.O2 | CI fail-loud on brain down (CGAP-008) | §5 | D10; WS2 step 4 probe `plan.md:96` |
| R-NEG-CIREACH.O1/O2 | detect unreachable + fail visibly | §5 probe | WS2 step 4 `plan.md:96`; §8.2 `plan.md:207` |
| R-NEG-RUNNING.O1 | skip active (repo,tool) | §4.1 | WS1 `plan.md:78` |
| R-NEG-MIDFLIGHT.O1 | concurrent edit → consistent (CGAP-011) | §4.2 rebase/retry | WS2 step 6 `plan.md:98` |
| R-NEG-NOORIGIN.O1/O2 | no-origin excluded from ingestion; still maintained (CGAP-014) | §5 | WS1 edge `plan.md:78`; D2 |
| R-NEG-CONCURRENT.O1/O2 | enqueues don't exceed worker; serialize | §4.1/§5 | WS1 `plan.md:60` |
| R-AUTH.O1/O2 | token requirement resolved | §6.4/§7 RESOLVED | D6 `plan.md:40` (upgrade: research left scoped-open; plan resolves) |

### Plan-introduced obligations (new executable commitments)

| P-id | obligation (entailed by the plan's own mechanism) | why entailed | plan anchor |
| --- | --- | --- | --- |
| P-PROBE-URL | the reachability probe's target URL must be a defined, derivable value | WS2 step 4 commits to `curl --fail … "$CORPUS_HEALTH_URL"`; the var must exist for the step to run | `plan.md:96` |
| P-SYNC-ORDER | the CI corpus-sync (`HEAD~1` orphan diff) must be correct in **every** run path, including a run where step 6 made **no commit** | step 7's correctness rationale ("HEAD~1 orphan diff is correct") is conditional on a commit having just been made; step 6 commits only-if-diff | `plan.md:98-99` |
| P-DEADCADENCE-SERVER | the dead-man's-switch must detect a silently-stopped **server MaintenanceScheduler**, not only a stopped CI cron | WS1 edge (`plan.md:78`) delegates "silently-skipped week" coverage to WS5; R-OBSERV.O3 requires "either … or the server scheduler" | `plan.md:78,165-171`; research §5 `research.md:227` |
| P-RESTART-ANCHOR | the restart-anchored off-peak claim must hold for the **immediate first tick** as well as recurring ticks | D3 commits to "first tick fires ~immediately at start()" as the anchor mechanism | `plan.md:37,68,181` |
| P-CRON-UTC | the chosen UTC cron must map to the intended off-peak Sofia window incl. DST | D8 | `plan.md:42` |
| P-HEARTBEAT-PARSE | heartbeat date-diff must use a baseline consistent with how the stamp is written (UTC) | WS5 parses stamp; WS2 writes `date -u +%F` | `plan.md:97,168` |
| P-SEQ | rollout order must leave no window where both launchd and CI commit, and dry-run precedes real | §6 | `plan.md:186-195` |

---

## Cycle 1 Assessment

Lenses applied: elicitation completeness, omission, decomposition/partial, conflict, acceptance-criteria, scope-boundary, traceability, prioritization. Evidence cited as `plan.md:line` (coverage) and `repo path:line` (grounding, all live-verified).

### Coverage Matrix (Cycle 1 — carried obligations)

All 60 carried obligations were re-traced. Result: **57 addressed, 0 absent among carried, 3 affected by plan-introduced regressions** (R-CORPUS.O2 via P-SYNC-ORDER; R-OBSERV.O3 via P-DEADCADENCE-SERVER; R-NEG-CIREACH.O1/R-NEG-BRAINDOWN.O2 via P-PROBE-URL). Carried obligations not affected by a plan gap are addressed at the anchors in the Obligation Decomposition table above and are not re-listed.

### Coverage Matrix (Cycle 1 — plan-introduced obligations)

| P-id | status | evidence |
| --- | --- | --- |
| P-PROBE-URL | **partial (gap)** | WS2 step 4 (`plan.md:96`) references `$CORPUS_HEALTH_URL` but the only secret/var defined is `CLAUDE_CORPUS_MCP_URL` = `…/mcp/` (`plan.md:101`). `/health` ≠ `/mcp/`; no transform/definition for `CORPUS_HEALTH_URL` is given. The probe step is non-executable as written → the fail-loud guarantee (D10) for the brain-down/unreachable case rests on an undefined variable. → CGAP-P01 |
| P-SYNC-ORDER | **partial (gap)** | Step 7 rationale "AFTER the commit (so `HEAD~1` orphan diff is correct)" (`plan.md:99`) holds only when step 6 actually committed. Step 6 commits "only if staged diff non-empty" (`plan.md:98`). A same-day `workflow_dispatch` re-run (an AC test path, `plan.md:104`) finds the stamp already = today → no diff → no commit → step 7 then computes orphans from `_previous_directives()` = `HEAD~1` of a *prior unrelated* commit (`sync_corpus.py:46-58,129-134`, live-verified). Upsert-of-current stays correct (idempotent) but the orphan/deactivate set is computed against a stale baseline — the stated correctness rationale fails for the no-commit path. → CGAP-P02 |
| P-DEADCADENCE-SERVER | **absent (gap)** | WS1 edge case delegates "a silently-skipped week is covered by Workstream 5" (`plan.md:78`). But WS5 only parses the DIRECTIVES **stamp** (`plan.md:168`), which is bumped exclusively by the **CI cron WS2** (`weekly_review.py:108`, `weekly-review.sh:13-16` retired) — never by the server scheduler. If WS1's server `MaintenanceScheduler` silently dies while the CI cron keeps stamping, the stamp stays fresh → heartbeat green → dead server scheduler undetected. Research CGAP-007 AC requires alert "if **either** the GH cron **or the server scheduler** stops ticking" (`research.md:227`). The plan covers only the cron half → **regression of a research-converged obligation**. → CGAP-P03 |
| P-RESTART-ANCHOR | addressed | D3/WS1 (`plan.md:37,68`) — verified against `maintenance_scheduler.py:58-68`: `_tick()` (line 62) precedes `wait_for(timeout=interval)` (line 66); first tick at `start()`, recurring ticks at restart wall-clock hour. AC `plan.md:75`. |
| P-CRON-UTC | addressed | D8 `plan.md:42` — UTC `0 3 * * 1` → 05:00/06:00 Sofia; ±1h DST explicitly accepted. AC `plan.md:110`. |
| P-HEARTBEAT-PARSE | addressed | WS2 writes `date -u +%F` (`plan.md:97`); WS5 date-diff (`plan.md:168`); both UTC dates, no TZ skew. |
| P-SEQ | addressed | §6 (`plan.md:186-195`): WS4 (retire launchd) first, dry-run before real compaction (§6.6→6.7). AC implicit in §9 single-committer test `plan.md:225`. |

### Acceptance-Criteria presence (Cycle 1)

Unlike the research doc, the plan carries explicit per-workstream "Acceptance criteria (testable)" blocks (WS1 `plan.md:71-76`, WS2 `plan.md:103-108`, WS3 `plan.md:126`, WS4 `plan.md:153`, WS5 `plan.md:171`) plus a consolidated §9 test plan (`plan.md:213-226`). Every carried requirement has a testable criterion. The 3 plan-introduced gaps below each also lack a sound criterion (the criterion that exists rests on the broken mechanism).

### Conflict Register (Cycle 1)

| pair | tension | reconciled? |
| --- | --- | --- |
| WS2 step 6 (commit only-if-diff) vs WS2 step 7 (sync assumes a fresh commit) | ordering/precondition conflict on the no-commit path | NOT reconciled — CGAP-P02 |
| WS1 (delegates dead-cadence to WS5) vs WS5 (only watches the stamp the CI cron writes) | WS1 relies on coverage WS5 doesn't provide for the server half | NOT reconciled — CGAP-P03 |
| All three research conflicts (launchd double-run; local-hook-vs-CI; enqueue bound) | — | reconciled — carried via D9/WS4, WS2 step 7, WS1 corrected claim (verified present) |

### Blocker Gap Ledger (Cycle 1)

| gap_id | severity | req_id.obligation | lens | evidence | why uncovered | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CGAP-P01 | blocker | R-NEG-CIREACH.O1 / R-NEG-BRAINDOWN.O2 / P-PROBE-URL | omission (undefined input) | `plan.md:96` uses `$CORPUS_HEALTH_URL`; only `CLAUDE_CORPUS_MCP_URL=…/mcp/` defined (`plan.md:101`); `/health` is a distinct public path (`middleware/auth.py:8`) | the fail-loud probe (D10) is the sole guard for brain-unreachable, and its target URL is undefined/non-derivable as written → mechanism non-executable | Define `CORPUS_HEALTH_URL` explicitly (own secret or derive from the MCP URL by stripping the `/mcp/` suffix and appending `/health`); state the derivation in WS2 step 4 + secrets list | edited `plan.md:96,101a` | closed |
| CGAP-P02 | blocker | R-CORPUS.O2 / P-SYNC-ORDER | conflict / partial | step 7 correctness ("HEAD~1 orphan diff is correct", `plan.md:99`) conditional on step 6 having committed; step 6 commits only-if-diff (`plan.md:98`); no-commit re-run path leaves orphan baseline stale (`sync_corpus.py:46-58,129-134`) | the corpus-sync coverage of R-CORPUS.O2 is only sound on the commit path; the no-commit (same-day re-dispatch) path has no defined correct behavior | Reconcile: gate step 7 on "a commit was made this run" (skip sync otherwise) OR state that the no-commit re-sync is idempotent-safe with rationale (upsert-of-current always correct; orphan-set worst case re-deactivates already-absent slugs = no-op); add an AC for the same-day re-dispatch path | edited `plan.md:99,110` | closed |
| CGAP-P03 | blocker | R-OBSERV.O3 / P-DEADCADENCE-SERVER | regression / omission | WS1 delegates silent-week coverage to WS5 (`plan.md:78`); WS5 watches only the stamp (`plan.md:168`) which the server scheduler never writes; research AC requires "either … or the server scheduler" (`research.md:227`) | a silently-dead server `MaintenanceScheduler` (CI cron still healthy) is undetected → research-converged dead-cadence obligation regressed to cron-only | Add a server-half dead-cadence detector to WS5 (or scope it explicitly): e.g. heartbeat also asserts a recent `maintenance_scheduler_tick_complete` (within `interval × 1.5`) via a log/health probe, OR explicitly scope server-half dead-detection out with a stated rationale + compensating manual check + correct the WS1:78 cross-reference | edited `plan.md:78,169-170,171` | closed |

Cleanup list: none new (research CGAP-014 carried as addressed).

Cycle 1 result: **3 blocker gaps**, all plan-introduced (no carried-requirement was dropped; the regressions are in the plan's new executable mechanisms). Proceeding to Cycle 1 Plan + Edits.

---

## Cycle 1 Plan

- CGAP-P01 → WS2 step 4 + secrets bullet: define `CORPUS_HEALTH_URL` (derive `/health` from the MCP URL base, or add as a second secret); make the probe executable; keep the AC.
- CGAP-P02 → WS2 step 7 + edge-cases: gate the sync on a commit-made flag and/or document idempotent-safe no-commit re-sync; add a same-day re-dispatch AC.
- CGAP-P03 → WS1 edge + WS5: add server-half dead-cadence detection (recent `*_tick_complete`) or explicitly scope it out with rationale; fix the WS1:78 cross-reference so it no longer over-claims WS5 coverage.

Document edits only; no runtime code changed.

## Cycle 1 Edits

| gap_id | edit applied | location |
| --- | --- | --- |
| CGAP-P01 | defined `CORPUS_HEALTH_URL` derivation (strip `/mcp/`, append `/health`) in WS2 step 4; added to secrets/env note | `plan.md` WS2 step 4 + secrets |
| CGAP-P02 | gated corpus-sync on a "commit was made" flag; documented idempotent-safe skip; added same-day re-dispatch AC + edge note | `plan.md` WS2 step 7, AC, edge cases |
| CGAP-P03 | added server-half dead-cadence assertion to WS5 (recent `maintenance_scheduler_tick_complete`); corrected WS1:78 cross-reference; added AC | `plan.md` WS1 edge, WS5 mechanism + AC |

## Cycle 1 Validation

Re-read each edited section; confirmed each now has a concrete, executable mechanism (or explicit scoped-out statement) AND a testable acceptance criterion. Grounding re-verified live:
- `/health` ∈ `_PUBLIC_PATHS` (`middleware/auth.py:8`) and `/mcp` ∈ `_PUBLIC_PREFIXES` (`auth.py:16`) — both public; deriving `/health` from the same host is sound (CGAP-P01).
- `sync_corpus.py` upsert-of-current reads the live working tree unconditionally (`sync_corpus.py:123`); orphan set from `HEAD~1` (`:129-134`) — confirms upsert is always correct and only the orphan-set is baseline-sensitive (CGAP-P02 idempotent-safe rationale holds).
- `maintenance_scheduler_tick_complete` is the only periodic server liveness signal (`maintenance_scheduler.py:81`); no other server-side dead-detection exists — confirms CGAP-P03 needed a server-half assertion.

### Post-Edit New-Gap Pass (after Cycle 1 edits)

- CGAP-P01 fix derives `/health` from the MCP base — introduces no new secret-handling gap (R-SECRETS holds: still one secret, or a second public URL with no credential).
- CGAP-P02 fix (skip sync when no commit) — does it leave R-CORPUS.O2 uncovered on the no-commit path? No: when no commit was made, no directive changed this run, so the corpus already mirrors current state from the prior run/local hook; skipping is correct. No new gap.
- CGAP-P03 fix (heartbeat asserts recent `*_tick_complete`) — introduces a dependency on the heartbeat being able to read server logs/health. Noted as a satisfaction-depth concern (can the GH runner observe the server's last-tick time?), not a coverage gap: the obligation is now *addressed* with a mechanism + AC; whether the mechanism *works* against the real log/health surface is for the satisfaction pass. Flagged forward.
No new blocker coverage gaps.

---

## Cycle 2 Assessment (fresh full pass over the edited document)

Re-ran all 8 lenses over the full carried 27-req / 60-obl set + the 7 plan-introduced obligations against the edited `plan.md`.

| obligation | status | evidence |
| --- | --- | --- |
| P-PROBE-URL | addressed | WS2 step 4 now defines `CORPUS_HEALTH_URL` derivation; probe executable; AC `plan.md` WS2 |
| P-SYNC-ORDER | addressed | WS2 step 7 gated on commit-made + idempotent-safe rationale; same-day re-dispatch AC added |
| P-DEADCADENCE-SERVER | addressed | WS5 asserts recent `*_tick_complete`; WS1:78 cross-ref corrected; AC added |
| all carried obligations | addressed / scoped-out | unchanged from research convergence; no regression introduced by edits |

Conflict Register (Cycle 2): the two new conflicts (step6/step7; WS1/WS5) reconciled; three research conflicts remain reconciled. No new conflicts.

Blocker Gap Ledger (Cycle 2): zero new. CGAP-P01…P03 closed.

Per the hard-stop rule, this cycle is an assessment over the edited document and made **no edits**. Convergence declared in the next no-edit cycle.

---

## Cycle 3 — Final Convergence Check (no edits)

Fresh full pass; zero blockers discoverable. Carried requirement set (27 req / 60 obl) is fully carried into the plan with no silent drop; the 3 plan-introduced regressions are closed; every workstream obligation and every locked decision (D1–D11) maps to a concrete plan mechanism with a testable acceptance criterion; the new conflicts are reconciled. No edits this cycle.

### Final Coverage Proof (compact)

| req_id | every obligation covered or scoped-out? | acceptance criterion present? | evidence |
| --- | --- | --- | --- |
| R-INTEG | yes | yes | WS1 + D1/D3 + §9 |
| R-FRESH | yes (scoped disabled) | yes | D2, §2 |
| R-SPARK | yes | yes | WS2 + D8/D9 + §9 |
| R-AGENTS | yes (scoped local) | yes | WS3 + D4 + §2 |
| R-STAMP | yes | yes | WS2 + D9 |
| R-CORPUS | yes (commit + no-commit paths) | yes | WS2 step 7 (post-fix), WS3 |
| R-CAPTURE | yes (scoped-out) | yes | §2 |
| R-NOMANUAL | yes (freshness exception explicit) | yes | §1/§2, WS4 |
| R-MACHINEINDEP | yes | yes | WS1+WS2/WS5 |
| R-MULTIMACHINE | yes | yes | WS4 + D9 |
| R-NOINCIDENT | yes | yes | D2, §2 |
| R-SHAREDINFRA | yes | yes | WS1 (corrected bound) |
| R-OBSERV | yes (cron + server halves, post-fix) | yes | WS1, WS2, WS5 |
| R-SECRETS | yes | yes | WS2, D6 |
| R-IDEMPOTENT | yes | yes | D9, WS4 |
| R-RETIRE | yes | yes | WS4 checklist |
| R-COST | yes | yes | WS2 verification |
| R-CADENCE | yes | yes | D3, D8, §5 |
| R-BACKCOMPAT | yes | yes | WS3, WS4, §7 |
| R-NEG-BRAINDOWN | yes (server + CI, post-fix probe) | yes | WS1, D10, WS2 step 4 |
| R-NEG-CIREACH | yes (probe defined, post-fix) | yes | WS2 step 4 |
| R-NEG-RUNNING | yes | yes | WS1 |
| R-NEG-MIDFLIGHT | yes | yes | WS2 step 6 |
| R-NEG-NOORIGIN | yes | yes | WS1 + D2 |
| R-NEG-CONCURRENT | yes | yes | WS1 |
| R-AUTH | yes (RESOLVED — no token) | yes | D6 (upgrade over research scoped-open) |

**Convergence: ACHIEVED (breadth).** All 27 carried requirements / 60 obligations carried into the plan with no silent drop; the plan's 7 introduced executable obligations decomposed and traced; 3 plan-introduced blocker regressions (undefined probe URL, no-commit sync-ordering, server-half dead-cadence) closed; all carry testable acceptance criteria; all conflicts reconciled.

**Requirements intentionally excluded (explicit, with rationale, carried from research):** R-FRESH auto-ingest stays DISABLED (incident-driven, §2/D2); R-CAPTURE scheduling out-of-scope (event hook, §2); cross-repo AGENTS refresh in CI infeasible (§2); real-compaction deferred one cycle (§2/D1); wall-clock off-peak anchoring not directly schedulable — best-effort via restart-time (§2/D3).

**No user decision required for breadth convergence.** R-AUTH (previously the one open user decision) is resolved by D6. The four §8 live confirmations are operator runtime checks, not design choices, and each has a defined fail-loud behavior if the check fails.

This establishes **breadth** (every requirement addressed / scoped-out), not depth. Next gate: **requirements-satisfaction-gap-loop** — verify each addressed requirement holds end-to-end against the real runtime (notably: can the heartbeat actually observe the server's last `*_tick_complete`; does the derived `/health` URL respond; does `ALLOW_REMOTE_WRITES=true` live).
