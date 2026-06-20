# Coverage Audit — close-8-gaps-plan.md

Plan-playbook Gate A: **requirements-coverage-gap-loop** (breadth). Requirement set = the 8 gaps (decomposed) + implied-essential implementation requirements. Convergence = every obligation addressed or explicitly scoped-out, each with a testable acceptance criterion, no unreconciled conflicts. §0.1 (endpoint A/B) is a recorded **open user decision** — non-convergence allowed on that single item only.

---

## Cycle 1 Assessment

### Requirement Inventory (selected — full set traced in matrix)

| req_id | requirement | type |
| --- | --- | --- |
| G1 | DIRECTIVES.md authoritative; all surfaces projected | explicit |
| G2 | session-close auto-capture → evidence tier | explicit |
| G3 | proactive directive Spark from telemetry | explicit |
| G4 | portable directive read path (Codex+) | explicit |
| G5 | recency + relevance floor in retrieval | explicit |
| G6 | prune test-repo clutter | explicit |
| G7 | scheduled review/consolidation cadence | explicit |
| G8 | cite retrieved memory to entry_key/link_slug | explicit |
| X-DEPLOY | server-side changes must ship to the canonical endpoint | implied-essential |
| X-TEST | new/changed code carries tests (repo uses pytest) | non-functional |
| X-PROMOTE | path from evidence-tier capture → global directive/corpus | implied-essential |
| X-SCOPE-FILES | which CLAUDE.md/AGENTS.md instances are in scope | implied-essential |

### Coverage Matrix (obligation-level; blockers extracted below)

| obligation | status | evidence |
| --- | --- | --- |
| G1 distill global ~/.claude/CLAUDE.md / ~/CLAUDE.md / ~/AGENTS.md | addressed | `close-8-gaps-plan.md:35-39` |
| G1 Codex projection | addressed | `:41-45` |
| G1 demote legacy files | addressed | `:47-49` |
| G1 fold file-memory | addressed | `:51-52` |
| G1 endpoint unification | addressed, **no acceptance** | `:54` → CGAP-002 |
| G1 which CLAUDE.md/AGENTS.md instances (global vs per-project) | **absent** | not enumerated → CGAP-001 |
| G2 capture hook + Codex + promotion gate | addressed | `:64-68` |
| G2 selection criteria (what's worth capturing) | partial | → cleanup C1 |
| G3 pull telemetry → cluster → drafts | addressed | `:76-79` |
| G3 telemetry scope (repo_key — repo-scoped tools) | **absent** | → CGAP-005 |
| G4 SETUP-codex.md | addressed | `:86-88` |
| G5 recency + threshold in corpus_query | addressed | `:97-100` |
| G5 deploy the server change to canonical endpoint | **absent** | → CGAP-003 (X-DEPLOY) |
| G6 identify + purge via non-destructive tool | addressed | `:108-111` |
| G7 wrap+schedule consolidation; schedule Spark; stamp | addressed, **scheduler not locked** | `:119-123` → CGAP-006 |
| G8 inject entry_key/link_slug + preamble | addressed | `:132-135` |
| X-TEST (all new code) | **absent** | no testing obligation → CGAP-004 |
| X-PROMOTE (evidence→global) | **absent** | §2/§3/§1 link not drawn → CGAP-007 |
| §0.1 endpoint A/B | open decision | `:11-21` — recorded, awaiting Kamen |

### Conflict Register

| pair | tension | reconciled? |
| --- | --- | --- |
| G5 recency vs G8 (same file `hydrate_corpus.py`) | both edit injection | yes — sequenced together (`:142`) |
| G1.3 demote vs G1.2 projection | demote before projection = rules drop | yes — ordering+verify gate (`:56`) |
| G2 evidence (repo-scoped) vs G1 global authority | where do captured lessons become directives? | **no** — promotion path missing → CGAP-007 |

### Blocker Gap Ledger

| gap_id | severity | req | lens | evidence | why uncovered | planned fix | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CGAP-001 | blocker | X-SCOPE-FILES | decomposition | `:35-49` lists only 3 home/global files; Kamen has per-project `CLAUDE.md`/`AGENTS.md` in active repos (FCSAPI, taggable-server, taggable-api…) per `~/.codex/config.toml` trusted projects | "demote CLAUDE.md/AGENTS.md" is ambiguous in scope; per-project instances could be missed or wrongly clobbered | Enumerate in-scope instances (global + Kamen-owned project repos); explicitly exclude third-party repos (e.g. OB1-main) | open |
| CGAP-002 | blocker | G1 | acceptance | `:54` step 1.5 has no acceptance criterion | can't verify endpoint unification done | Add acceptance: all 3 consumers resolve one URL; identical top-k for a fixed query | open |
| CGAP-003 | blocker | X-DEPLOY/G5 | omission | `:97-100` edits `corpus_query` (server-side `src/`) but no deploy step; server runs at local:8000 and Azure | a server code change without redeploy doesn't take effect | Add a Deployment obligation: src/ changes ship to the canonical endpoint; acceptance asserts the deployed endpoint serves new behavior | open |
| CGAP-004 | blocker | X-TEST | non-functional | repo has `tests/` + pytest; plan names no tests for new code | unverified code = regressions | Add cross-cutting Testing requirement: each code change ships a test; per-gap acceptance references it | open |
| CGAP-005 | blocker | G3 | partial | telemetry tools (`get_finding_pattern_summary` etc.) require `repository_key`; `:76-79` doesn't say which repo(s) | Spark can't run without a defined scope | Lock Spark's scope: iterate the active repo set (or a defined aggregate) | open |
| CGAP-006 | blocker | G7 | partial/decision | `:119` "the schedule/cron mechanism" — not locked | implementer can't pick the scheduler | Lock to a concrete scheduler (cron/launchd wrapper, consistent with existing shell-script automation) | open |
| CGAP-007 | blocker | X-PROMOTE | traceability/conflict | §2 writes repo-scoped evidence; §1 makes DIRECTIVES.md/global corpus authoritative; no path between them | captured lessons never become durable directives → §2 inert | Draw the promotion path: evidence proposals surface in §3 Spark/review → "lock it" into DIRECTIVES.md or a global corpus `reference` entry | open |

### Cleanup List

| id | issue | fix |
| --- | --- | --- |
| C1 | G2 "durable lesson" selection criteria unspecified (noise risk) | add a one-line capture criterion |

---

## Cycle 1 Plan (gap-to-fix)

| gap | edit |
| --- | --- |
| CGAP-001 | §1 add "In-scope instances" line (global + Kamen project repos; exclude third-party like OB1-main) |
| CGAP-002 | §1.5 add acceptance criterion |
| CGAP-003 | new "Cross-cutting: Deployment" item + reference from §5/§8 |
| CGAP-004 | new "Cross-cutting: Testing" item; per-gap acceptance references a test |
| CGAP-005 | §3 lock telemetry scope |
| CGAP-006 | §7 lock scheduler mechanism |
| CGAP-007 | §2/§3 add promotion-path bridge |
| C1 | §2 add capture criterion |

Plan accepted; applying.

---

## Cycle 1 Edits

| gap | edit | location |
| --- | --- | --- |
| CGAP-001 | §1 "In-scope file instances (locked)" — global + Kamen project repos; excludes third-party (OB1-main) | plan §1 |
| CGAP-002 | §1.5 acceptance criterion added | plan §1.5 |
| CGAP-003 | §0.3 "Deployment (X-DEPLOY)" cross-cutting req | plan §0.3 |
| CGAP-004 | §0.3 "Testing (X-TEST)" cross-cutting req + per-gap acceptance references | plan §0.3, §2/§3/§7 |
| CGAP-005 | §3 "Telemetry scope (locked)" — active repo set, cross-repo ranking | plan §3 |
| CGAP-006 | §7 scheduler locked to launchd weekly (cron fallback) | plan §7 |
| CGAP-007 | §2 "Promotion path to the authoritative store" + §3 ingests evidence queue | plan §2/§3 |
| C1 | §2 capture criterion | plan §2 |

## Cycle 1 Validation

- Each fix present (grep): CGAP-001 in-scope ✓, CGAP-002 endpoint acceptance ✓, CGAP-003 X-DEPLOY ✓, CGAP-004 X-TEST ✓ (4 refs), CGAP-005 telemetry scope ✓, CGAP-006 launchd ✓, CGAP-007 promotion path ✓, C1 ✓.
- Unresolved-term scan → none.
- Post-edit new-gap pass: the new promotion path (§2→§3→§1) reconciles the prior conflict (evidence vs global authority) — no new conflict. Testing/deploy reqs add obligations but each gap's acceptance now references them. No new uncovered obligation introduced.

## Cycle 2 Assessment (fresh full pass, no edits)

| req | every obligation covered or scoped? | acceptance? |
| --- | --- | --- |
| G1 | yes — distill/Codex/demote/file-memory/endpoint + in-scope instances locked | yes (incl. §1.5) |
| G2 | yes — capture + criterion + promotion path + trust gate | yes |
| G3 | yes — telemetry scope locked + evidence-queue input | yes |
| G4 | yes — SETUP-codex.md (rests on §1.2/§0.1) | yes |
| G5 | yes — recency+threshold + deploy obligation | yes (incl. X-DEPLOY) |
| G6 | yes — identify+purge via verified non-destructive tool | yes |
| G7 | yes — launchd weekly + stamp + schedules Spark | yes |
| G8 | yes — entry_key/link_slug injection + preamble | yes |
| X-DEPLOY / X-TEST / X-PROMOTE / X-SCOPE-FILES | yes — §0.3 + §1 + §2/§3 | yes |

Conflict register re-checked: G5↔G8 (sequenced), G1.2↔G1.3 (ordering+verify), G2↔G1 (promotion path) — all reconciled.

Blocker coverage gaps in Cycle 2: **0**. Open user decision: **§0.1 endpoint A/B** (recorded; the loop's non-convergence rule explicitly permits a single user-decision item).

## Final Convergence Check

**Breadth convergence: reached, conditional on one recorded user decision.** Every gap and every implied-essential obligation (distillation, Codex projection, endpoint unification, deployment, testing, trust gates, promotion path, scheduling, file-scope) is addressed by a concrete plan step or explicitly scoped out, each with a testable acceptance criterion; the one cross-requirement conflict (captured evidence vs global authority) is reconciled via the promotion path. The **only** open item is **§0.1 (canonical endpoint A=Azure vs B=local)** — a deliberate Kamen decision, recorded with rationale, not silently dropped.

**Scope:** breadth only — all requirements are *addressed*. Whether each *holds end-to-end against the real runtime/data* is the satisfaction/depth gate (next).
