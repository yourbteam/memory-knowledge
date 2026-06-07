# Coverage Audit — docs/qa-suggest-fix-plan.md

Breadth check: is the requirement set complete, and is every requirement (decomposed into
obligations) addressed or explicitly scoped-out, each with a testable acceptance criterion?
Sources: `docs/qa-suggest-not-returning-findings.md` (Candidates 1–3, cross-repo note) +
the user's scope "memory-knowledge side full set #1–#5".

## Requirement Inventory

| req_id | requirement | type | source (quoted) |
| --- | --- | --- | --- |
| R1 | Search returns stored Q&A relevant to a question | explicit | findings `:1` "search_qa_knowledge always returns empty"; user "retrieve a suggested answer based on a question" |
| R2 | Lexical fallback when semantic returns zero candidates | explicit | findings Candidate 2 `:39-64`; plan scope `#1` |
| R3 | Lower / configurable `min_similarity` so near-dupes surface | explicit | findings Candidate 3 `:68-73`; plan scope `#2` |
| R4 | Info logging of `repository_key` + counts on ingest & search | explicit | findings cross-repo note `:96-105`; plan scope `#3` |
| R5 | Reconcile embedding config to deployed 768 reality | explicit | plan scope `#4`; diagnosis `:36-41` |
| R6 | Tests for new behavior; rewrite the bug-pinning test | explicit | plan scope `#5` |
| R7 | Lowered threshold must reach the **deployed** search path (server resolves from settings) | implied | entailed by R3 — the MCP tool passed its own `0.65` (`server.py:1646`); a function-default change alone wouldn't affect deployed behavior |
| R8 | No regression: existing passing tests stay green | implied | entailed by editing shared module/tests |
| R9 | Lexical fallback fires only on zero candidates (no double-query) | non-functional | entailed; plan note `:109-110` |
| R10 | Both-empty (semantic+lexical) → advisory empty, not error | negative | entailed; existing `qa_memory.py:213-214` |
| R11 | Logging is side-effect-only (no return/signature change) | non-functional | entailed; plan `:166` |
| R12 | Env edits don't change deployed runtime; dim change warns re-embed | non-functional | plan `:78,82-83` |
| R13 | Threshold not so low it surfaces irrelevant noise (precision bound) | negative | entailed by R1 relevance; plan open-decision `:209-210` |

## Obligation Decomposition

| req_id | obligation | source/why entailed |
| --- | --- | --- |
| R2 | a) detect zero semantic candidates; b) run lexical; c) hydrate+return | the fallback path |
| R3 | a) lower default; b) make configurable (Settings); c) function-level default; d) server passes resolved value | #2 sub-parts |
| R4 | a) ingest start; b) ingest done; c) search every exit (unknown-repo, empty, success); d) fields incl. repository_key | #3 |
| R5 | a) fix all 5 env files; b) PROVIDER+MODEL+DIMENSIONS; c) re-embed comment; d) don't touch deployed | #4 |
| R6 | a) rewrite bug test (R2); b) threshold test (R3c func); c) **server resolution test (R3d/R7)**; d) keep 2 green; e) log assertion (R4) | #5 |
| R7 | a) tool default None; b) resolve None→`settings.qa_search_min_similarity`; c) override honored | server wiring |

## Coverage Matrix

| req_id.obligation | status | addressed where (path:line) / rationale |
| --- | --- | --- |
| R1 | addressed | end-to-end via R2+R3; acceptance = prod re-check `:192-193` |
| R2.a/b/c | addressed | Step 2 `:92-107`; lexical block `qa_memory.py:196-211` |
| R3.a | addressed | Step 3 `:118-119` (0.45) |
| R3.b | addressed | Step 3a `:121-126` (`qa_search_min_similarity`) |
| R3.c | addressed | Step 3b `:128-129` |
| R3.d | addressed | Step 3c `:131-144` |
| R4.a/b | addressed | Step 4 ingest sites |
| R4.c/d | addressed | Step 4 search exits `:168/:214/:241` + fields (closed via skill-1 GAP-001) |
| R5.a–d | addressed | Step 1 `:60-83` (5 files enumerated) |
| R6.a | addressed | Step 5 rewrite bullet |
| R6.b | addressed | Step 5 threshold-from-settings bullet (qa_memory level) |
| **R6.c (server resolution test)** | **ABSENT** | Step 5 tests only `qa_memory.search_qa_knowledge`; the `server.py` None→settings resolution (R3d/R7.b) is untested → CGAP-001 |
| R6.d | addressed | Step 5 "keep green" `:182-183` |
| **R6.e (log assertion)** | **partial** | Step 5 marks log test "Optional" `:184`; R4 has no substantive testable criterion → CGAP-002 |
| R7.a/b/c | addressed (impl) | Step 3c — but verification falls under R6.c (untested) |
| R8 | addressed | Step 5 `:182-183` |
| R9 | addressed | Step 2 short-circuit note `:109-110` |
| R10 | addressed | relies on existing `qa_memory.py:213-214`; acceptance = unchanged behavior |
| R11 | addressed | Step 4 `:166` no signature change |
| R12 | addressed | Step 1 `:78,82-83` |
| R13 | out-of-scope (bounded) | advisory_only surface + tunable config + open-decision `:209-210`; precision not unit-tested by design |

## Conflict Register

| pair | tension | reconciled? |
| --- | --- | --- |
| R2 vs R3 | both widen recall | complementary — lexical only on zero candidates; no conflict |
| R5 (768) vs deployed | could imply runtime change | reconciled: Step 1 explicitly edits files only, not runtime (`:78`) |
| R3 vs R13 | lower threshold ↔ precision | reconciled via advisory framing + tunable config + explicit open decision |

No unreconciled conflicts.

## Acceptance-Criteria Table

| req_id | acceptance criterion | gap? |
| --- | --- | --- |
| R2 | rewritten `test_search_semantic_empty_falls_back_to_lexical` asserts `len(rows)==1` + warning | none |
| R3.c | `test_search_threshold_from_settings` asserts `score_threshold==0.45` at qa_memory level | none |
| R3.d/R7 | **none** — no server-level test of None→settings resolution | CGAP-001 |
| R4 | only "import clean / no signature change" + Optional log test | CGAP-002 (no substantive criterion) |
| R5 | grep gate shows 768/bge-base/local in all 5 files | none |
| R1 (e2e) | prod re-check: near-dup question → ≥1 advisory row | none (manual, deploy-gated) |

## Cycle 1 Assessment — Blocker Gap Ledger

| gap_id | severity | req_id.obligation | lens | evidence | why uncovered | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CGAP-001 | blocker | R6.c / R7.b | decomposition + traceability | Step 3 validation `:150` claims Step 5 asserts the resolved threshold, but Step 5 `:179-181` tests only `qa_memory.search_qa_knowledge` (default 0.45). The `server.py` None→`settings.qa_search_min_similarity` branch (`:141`) — the actual deployed path — has no test. `qa_env` fixture (`test_qa_memory.py:278-283`) makes a server test feasible. | the deployed-path obligation R7.b is implemented but unverified; Step 3's stated acceptance points at a test that doesn't cover it | Add a Step-5 server-level test bullet: call `server.search_qa_knowledge(...)` under `qa_env`, assert `qdrant.query_calls[0]["score_threshold"] == SETTINGS.qa_search_min_similarity`, and that an explicit `min_similarity` arg overrides. Correct Step 3c validation wording. | Step 5 server-test bullet + Step 3c gate updated | closed |
| CGAP-002 | blocker | R6.e / R4 | acceptance-criteria presence | Step 5 `:184` "Optional: assert the new info-log events fire"; R4's only firm criterion is "import clean" (`:166`) | R4's purpose is diagnosis visibility; with the assertion optional, the requirement has no substantive testable acceptance — coverage of *whether logging works* is absent | Elevate to a required test: assert `qa_search_done` fires on the empty path with `repository_key`, `returned=0`, `lexical_used` (structlog capture). Keep ingest-log assertion optional/cleanup. | Step 5 required log-test bullet | closed |

## Cleanup List

| item_id | req | issue | optional fix |
| --- | --- | --- | --- |
| CCLN-001 | R9 | server tool param `float \| None` — confirm MCP callers don't pass positional | note: MCP calls are kwarg-based; low risk |

## Cycle 1 Plan

| gap_id | target | exact edit | validation |
| --- | --- | --- | --- |
| CGAP-001 | Step 5 + Step 3c | add server-resolution test bullet; reword Step 3c validation to name it | Step 5 cites `server.search_qa_knowledge` + `query_calls` |
| CGAP-002 | Step 5 | make empty-path log assertion required | Step 5 lists a required structlog-capture test |

## Cycle 1 Edits

Applied to `docs/qa-suggest-fix-plan.md`:
- Step 5: added a **required** server-level resolution test (`server.search_qa_knowledge` under `qa_env`, assert `query_calls[0]["score_threshold"]` == settings value + override honored); and elevated the empty-path **log assertion to required** (structlog capture of `qa_search_done` with `repository_key`/`returned=0`/`lexical_used`). (closes CGAP-001, CGAP-002)
- Step 3c **Validation gate**: reworded to point at the new server-level test explicitly.

## Cycle 1 Validation

- Re-decomposed R6 → obligations a–e now all `addressed` in the coverage matrix.
- Post-edit new-gap pass: server test depends on `SETTINGS.qa_search_min_similarity` existing — Step 3a adds that field; `qa_env` patches `get_settings`→`SETTINGS` (`test_qa_memory.py:280`), so the field must be present on the test `SETTINGS` object (note added to Step 5). No new conflict; no new un-decomposed obligation.
- Traceability: no orphan mechanisms; every step → a requirement; R7 now has acceptance via R6.c.
- Commands: grounding reads of `tests/test_qa_memory.py:278-320` (qa_env + server tool tests) and `db/qdrant.py:85-91` (threshold passthrough) confirm test feasibility.

## Cycle 2 Assessment

Fresh full pass over the complete requirement set (R1–R13). Carry-forward: CGAP-001 closed, CGAP-002 closed, CCLN-001 cleanup-noted.

- Elicitation: re-derived implied (R7,R8), non-functional (R9,R11,R12), negative (R10,R13) — set complete; no new requirement surfaced.
- Omission: every R has a concrete mechanism; none "mentioned only".
- Decomposition: R6.a–e all addressed; R3.a–d all addressed; R4.a–d addressed.
- Conflict: none unreconciled.
- Acceptance: every R has a criterion or explicit bounded out-of-scope (R13).
- Scope: workflow-orch items explicitly out-of-scope with rationale (`:197-203`); R13 bounded.

No blocker coverage gaps found.

## Final Convergence Check — Final Coverage Proof

| req_id | every obligation covered or scoped-out? | acceptance criterion present? | evidence |
| --- | --- | --- | --- |
| R1 | yes | yes (e2e prod re-check) | `:192-193` |
| R2 | yes (a/b/c) | yes (rewritten test) | Step 2 + Step 5 |
| R3 | yes (a/b/c/d) | yes (qa_memory + server tests) | Step 3 + Step 5 |
| R4 | yes (a–d) | yes (required empty-path log test) | Step 4 + Step 5 |
| R5 | yes (a–d) | yes (grep gate, 5 files) | Step 1 |
| R6 | yes (a–e) | yes (the test list itself) | Step 5 |
| R7 | yes (a/b/c) | yes (server resolution test) | Step 3c + Step 5 |
| R8–R12 | yes | yes | as matrixed |
| R13 | scoped-out (bounded) | advisory + tunable + open decision | `:209-210` |

Intentionally excluded (with rationale): precision/noise hard-bound (R13 — advisory surface, tunable config, open decision); low-confidence-row surfacing (`:146-148`); all workflow-orch changes (`:197-203`).

Converged in 2 cycles. Breadth established: every requirement is **addressed or explicitly scoped-out**, each with a testable acceptance criterion. This does **not** establish that each addressing actually holds end-to-end → run `requirements-satisfaction-gap-loop` next.
