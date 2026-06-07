# Gap Audit — docs/qa-suggest-fix-plan.md

Target: `docs/qa-suggest-fix-plan.md` (212 lines, 15 deterministic units).
Loop: doc-gap-closure-loop. Scope: internal document readiness only.

## Section Inventory

| unit_id | section/title | unit type | implementation relevance |
| --- | --- | --- | --- |
| U1 | Title (`:1`) | heading | low |
| U2 | Source of truth (`:3-4`) | intro | med — provenance |
| U3 | Scope #1–#5 (`:6-11`) | list | high — work items |
| U4 | Execution rule (`:13-15`) | intro | med — process/approval |
| U5 | Confirmed diagnosis table (`:19-28`) | table | high — grounding of root cause |
| U6 | Root cause para (`:30-34`) | text | high |
| U7 | Embedding consistency para (`:36-41`) | text | high — Step 1 basis |
| U8 | Dependency graph (`:45-54`) | diagram | med — ordering |
| U9 | Step 1 #4 env reconcile (`:58-81`) | step | high |
| U10 | Step 2 #1 lexical fallback (`:85-112`) | step | high |
| U11 | Step 3 #2 threshold/config (`:116-150`) | step | high |
| U12 | Step 4 #3 logging (`:154-166`) | step | high |
| U13 | Step 5 #5 tests (`:170-193`) | step | high |
| U14 | Out-of-scope handoff (`:197-203`) | text | med — scope boundary |
| U15 | Open decisions (`:207-212`) | list | med — unresolved choices |

## Cycle 1 Assessment

Coverage matrix (lenses: DC=decision completeness, RG=repo grounding, EC=edge/failure, VAL=validation/tests, CON=contradictions, VAG=vague wording, SCOPE=approval/out-of-scope, HAND=handoff):

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |
| U3 | DC | checked | five items map 1:1 to Steps 1–5 (`:6-11` ↔ `:58,85,116,154,170`) |
| U5 | RG | checked | table figures confirmed live: 12 rows, 768 collections, self-match 1.0 (diagnostic run 2026-06-07) |
| U6 | RG | checked | `qa_memory.py:162` default 0.65; `:193-194` early empty-return; `:171` `qdrant_client is None` |
| U7 | RG | gap found | "Deployed reality is bge-base/768/local" stated as fact but deployed env not directly observed → GAP-003 |
| U8 | CON | checked | order consistent with steps; Step 5 depends on 2–4 (`:54`) |
| U9 | RG | gap found | claims `.env`,`.env.remote` set vars — true (`.env:33-34`,`.env.remote:33-34`) but 3 more files also carry them (`.env.example:39-40`,`.env.local.example:39-40`,`.env.remote.example:30-31`); validation grep covers only 2 → GAP-002 |
| U9 | DC | checked | action block + comment text concrete; `reembed_collections.py` exists |
| U10 | RG | checked | early-return text matches `qa_memory.py:192-194`; `if fallback_to_lexical:` at `:196` |
| U10 | DC | checked | exact before/after diff; short-circuit note (`:109-110`) |
| U11 | RG | checked | `config.py:8` Settings; `qa_memory.py:162`; `server.py:1623-1648`; `correlation_id: str|None` precedent `:1628` |
| U11 | DC | checked | 3a/3b/3c concrete; resolves via `settings.qa_search_min_similarity` |
| U12 | DC | gap found | "before return" ambiguous: `search_qa_knowledge` has 4 return sites (`:168,194,214,241`); empty-result cases (the step's purpose) would be missed if logging only at success; `semantic_hits` computation undefined since `candidates` is overwritten by lexical (`:211`) → GAP-001 |
| U13 | RG | gap found(cleanup) | "token overlaps the stored question" — `QAPool` lexical mock returns all rows regardless of token (`test_qa_memory.py:74-75`); assertion still holds → CLN-001 |
| U13 | VAL | checked | `EmptyQdrant` returns `[]` (`:34-37`); threshold capturable via `FakeQdrant.query_calls` + `db/qdrant.py:85-91` |
| U10–U13 | EC | checked | lexical-also-empty handled by existing `:213-214`; logging cannot throw |
| U14 | SCOPE/HAND | checked | callers confirmed via rg in mcp-agents-workflow; key canonical |
| U15 | DC | checked | open decisions are genuine user choices (threshold/guard/low-conf), not hidden gaps; recommendation given |
| U1,U2,U4 | DC/SCOPE | checked | provenance + approval-gating explicit (`:13-15`) |
| all | resume/idempotency | not applicable | doc plans config + small synchronous code edits + tests; no long-running/resumable job introduced |

### Blocker Gap Ledger (Cycle 1)

| gap_id | severity | unit_id | lens | evidence | why blocker | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAP-001 | blocker | U12 | DC | `search_qa_knowledge` returns at `qa_memory.py:168,194,214,241`; `candidates` overwritten at `:211` | "before return" + `semantic_hits=<n>` underspecified; implementer could log only success, defeating "make empty results visible", and miscompute semantic count | Lock log sites: capture `semantic_hits=len(candidates)` after semantic block; log `qa_search_done` before unknown-repo (`:168`), threshold-empty (`:214`), and success (`:241`) returns | Step 4 rewritten with per-exit sites + capture point | closed |
| GAP-002 | blocker | U9 | RG/VAL | EMBEDDING vars in 5 files (`.env:33-34`,`.env.example:39-40`,`.env.local.example:39-40`,`.env.remote:33-34`,`.env.remote.example:30-31`); validation grep only `.env .env.remote` (`:80`) | validation would pass while 3 example files stay inconsistent — incomplete edit coverage | Enumerate all 5 files in Action; expand validation grep to all 5 + `git diff --name-only` | Step 1 Action+gate list all 5 files | closed |
| GAP-003 | blocker | U7/U9 | RG | `:36-41`,`:61-62` assert "deployed ignores those values" as fact; deployed env vars not inspected | ungrounded runtime claim (loop rule: ground or qualify) | Qualify as inference from collections=768 + 768-dim vectors created 2026-06-07; state deployed env not directly observed; step edits repo files only | Step 1 "Deployed reality (inferred…)" para added | closed |

### Cleanup List (Cycle 1)

| item_id | unit_id | issue | optional fix |
| --- | --- | --- | --- |
| CLN-001 | U13 | "token overlaps" mismatches the unconditional lexical mock | reword to cite `test_qa_memory.py:74-75`; add `FakeQdrant.query_calls` capture mechanism for the threshold test |

## Cycle 1 Plan

Gap-to-fix map:

| gap_id | target unit | exact decision to lock | edit summary | validation check |
| --- | --- | --- | --- | --- |
| GAP-001 | U12 (Step 4) | log at all 3 real exits; `semantic_hits` captured pre-fallback | replace logging bullets with per-exit, grounded sites | re-read Step 4 cites `:168,214,241` and capture point |
| GAP-002 | U9 (Step 1) | edit all 5 env files; validate all 5 | enumerate files + expand grep | grep gate lists 5 files |
| GAP-003 | U9/U7 (Step 1) | label deployed claim as inference w/ evidence | add "Deployed reality (inferred…)" para; soften U7 | text says "inferred, not directly observed" |
| CLN-001 | U13 (Step 5) | match test desc to mock; add capture path | reword bullets, cite `:74-75`, `db/qdrant.py:85-91` | Step 5 cites mock lines |

## Cycle 1 Edits

Applied to `docs/qa-suggest-fix-plan.md`:
- Step 1 (U9): rewrote **Why** to enumerate all 5 files with `path:line`; added **Deployed reality (inferred, not directly observed)** paragraph; **Action** now lists all 5 files; **Validation gate** greps all 5 files + `git diff --check`/`--name-only`. (closes GAP-002, GAP-003)
- Step 4 (U12): replaced logging bullets with locked per-exit `qa_search_done` sites (`:168`, `:214`, `:241`), a `semantic_hits=len(candidates)` capture before the Step-2 fallback, and concrete `ingest_qa_pairs` sites (`:71` entry, `:148` return). (closes GAP-001)
- Step 5 (U13): reworded the rewrite bullet to cite `EmptyQdrant` (`:34-37`) and the unconditional `QAPool` lexical mock (`:74-75`); added the threshold-capture mechanism via `FakeQdrant.query_calls` + `db/qdrant.py:85-91`. (closes CLN-001)

## Cycle 1 Validation

Commands:
- `grep -nE "EMBEDDING_(MODEL|DIMENSIONS|PROVIDER)" .env .env.example .env.local.example .env.remote .env.remote.example` → 5 files × MODEL+DIMENSIONS present, PROVIDER absent (confirms the Step-1 target set).
- `grep -nE "qa_memory.py:(168|214|241)|semantic_hits" docs/qa-suggest-fix-plan.md` → Step 4 now references all three exits + capture var.
- `rg -n "test_qa_memory.py:34-37|test_qa_memory.py:74-75|db/qdrant.py:85-91" docs/qa-suggest-fix-plan.md` → Step 5 grounded.
- Unresolved-term scan `rg -nE "TBD|TODO|maybe|could|should|candidate|or equivalent|such as|not locked" docs/qa-suggest-fix-plan.md` → only the intentional Open-decisions wording and "candidate" inside `search_qa_knowledge`-history prose; no new unresolved implementation choices.
- `git diff --check docs/qa-suggest-fix-plan.md` → clean (untracked file; whitespace OK).

Post-edit new-gap pass:

| changed unit | checked against | result | new gap id |
| --- | --- | --- | --- |
| Step 1 | locked decisions / scope / RG | files enumerated, claim qualified; "Do NOT change deployed runtime" preserved | none |
| Step 4 | exits in `qa_memory.py` post-Step-2 | `:194` becomes fallback (not return) after Step 2; logged exits are `:168/:214/:241` — consistent | none |
| Step 5 | mock behavior | description now matches `:74-75`; capture path valid | none |

Delta regression: no conflict with U3 scope, U8 ordering, U14 out-of-scope, or U15 open decisions; threshold value still the single open decision (unchanged).

## Cycle 2 Assessment

Fresh full-document pass over the edited document. Carry-forward: GAP-001 closed, GAP-002 closed, GAP-003 closed, CLN-001 closed.

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |
| U7 | RG | checked | now "inferred, not directly observed" with 2026-06-07 evidence — grounded/qualified |
| U9 | RG/VAL | checked | 5 files enumerated; validation grep covers all 5; action + gate aligned |
| U12 | DC | checked | three exit sites named; `semantic_hits` capture point fixed; ingest sites `:71/:148` |
| U13 | VAL | checked | mock lines cited; threshold capture grounded in `db/qdrant.py:85-91` |
| U3,U4,U5,U6,U8,U10,U11,U14,U15 | all lenses | checked | unchanged; re-verified consistent with edits; no new contradiction |
| all | resume/idempotency | not applicable | unchanged rationale |

No blocker gaps found in the fresh pass.

## Final Convergence Check

Final readiness proof:

| category | status | evidence |
| --- | --- | --- |
| runtime entry points & data flow | ready | `server.py:1623` tool → `qa_memory.search_qa_knowledge:155` / `ingest_qa_pairs:71` |
| schema/fields/interfaces/helpers | ready | `config.qa_search_min_similarity` (new), `semantic_query_points` (`db/qdrant.py:72-93`), `get_settings/get_pg_pool/get_qdrant_client` imports (`server.py:19,43,44`) |
| edge cases & failure behavior | ready | semantic-empty → lexical (Step 2); lexical-empty → advisory empty (`qa_memory.py:213-214`); embed failure already caught (`:185-188`) |
| resume/idempotency | n/a | no resumable job; ingest upsert idempotent via `ON CONFLICT` (existing) |
| validation/tests/acceptance | ready | Step 5 grounded tests + prod re-check (`thebteambg/neocurrency-dashboard` near-dup → ≥1 row) |
| repo grounding | ready | every step cites `path:line`; deployed claim explicitly qualified |
| approval boundaries | ready | per-step approval (`:13-15`); optional items flagged separate approval |
| out-of-scope boundaries | ready | workflow-orch handoff (`:197-203`); low-confidence rows deferred (`:146-148`) |

Converged in 2 cycles (1 edit cycle + 1 clean fresh pass). All blockers closed; 1 cleanup closed.
