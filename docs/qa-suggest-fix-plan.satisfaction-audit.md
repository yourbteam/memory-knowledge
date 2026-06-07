# Satisfaction Audit — docs/qa-suggest-fix-plan.md

Depth check: if a competent implementer builds exactly what the plan says, will the running
system satisfy each addressed requirement against the **real runtime, live data, and sibling
features** (workflow-orch `mcp-agents-workflow`)? Evidence drawn from un-cited code + live DB.

Addressed requirement set imported from `.coverage-audit.md` (R1–R13).

## Requirement Inventory (depth-relevant)

| req_id | requirement | type | source (quoted) |
| --- | --- | --- | --- |
| R1 | qa-suggest returns relevant prior Q&A end-to-end (cross-task) | stated | findings `:1`; user "retrieve a suggested answer based on a question" |
| R2 | lexical fallback returns rows when semantic empty | stated | plan `#1` |
| R3 | lowered threshold surfaces near-dupes | stated | plan `#2` |
| INV-1 | ingest `repository_key` == search `repository_key` (producer/consumer) | invariant | findings cross-repo note `:96-102` |
| INV-2 | qa.suggest consumer reads the memory-knowledge response shape correctly | invariant | implied-essential for R1 end-to-end |
| INV-3 | `question_tsv` populated in live data (lexical depends on it) | implied-essential | `qa_memory.py:197-210` lexical query |

## End-to-End Trace Table

| req_id | trace (trigger → … → surfaced result) | runtime/data evidence | holds? |
| --- | --- | --- | --- |
| INV-3 | ingest writes `question_tsv=to_tsvector('english',q)` → lexical `@@ plainto_tsquery` | live: `question_tsv IS NULL = 0/12`; exact-question lexical `self_in_hits=True` both repos; near-variant `match_count=1` | **yes** |
| R2 | semantic empty → `fallback_to_lexical=True` → `ts_rank` query → hydrate → rows | `qa_memory.py:196-211`; live lexical returns the row | **yes (mk level)** |
| R3 | re-embed (bge-base/768) → cosine score ≥ 0.45 → rows | live near-dupe scores 0.49–0.60; threshold 0.45 admits them | **yes (mk level)** |
| INV-1 | ingest `capture_feedback_qa_to_mk(repository_key=ctx["repository_key"])` vs search `_repository_key_for_run`→`remote_run["repository_key"]`/`context_json["repository_key"]` | `workflow_engine.py:13021` (producer) + `mcp_server.py:15896-15898` (consumer) — same `repository_key` context key; live rows under canonical keys | **yes** |
| R1 (e2e) | `workflow.qa.suggest` → `handle_qa_suggest` → `call_tool_json("search_qa_knowledge")` → read `rows` → surface | **BREAKS at consumer**: response is a `WorkflowResult` envelope (`rows` under `.data`), consumer reads top-level `.rows` → `None` | **NO → SGAP-001** |

## Lens Coverage Matrix

| req_id | lens | status | evidence |
| --- | --- | --- | --- |
| R1 | 1 cross-feature contract | gap found | envelope `{status,data:{rows}}` (`base.py:8-14`) vs consumer top-level `.get("rows")` (`mcp_server.py:15941`) → SGAP-001 |
| R1 | 4 end-to-end trace | gap found | chain breaks at `handle_qa_suggest` unwrap |
| R1 | 8 scope-vs-usage | checked | qa.suggest is the real usage path; mk fix is on the right tool, but consumer unwrap defeats it |
| INV-1 | 1/5 producer/consumer symmetry | checked | both sides read `repository_key` context key (`13021` / `15896-15898`) |
| INV-2 | 1 cross-feature contract | gap found | same as SGAP-001 (the consumer-shape invariant) |
| INV-3 | 2 data-reality | checked | `question_tsv` populated 12/12 (live query) |
| R2 | 2 data-reality | checked | lexical returns rows against real stored text |
| R2 | 6 silent-inert | checked | embed-fail & semantic-empty both route to lexical; only genuine no-match → empty |
| R3 | 2 data-reality | checked | real scores 0.49–0.60 admit at 0.45; cosine score is similarity (self-match=1.0 best) |
| R3 | 3 intent vs mechanism | checked | intent = surface relevant prior Q&A; lowering + lexical serves it |
| R3 | 7 config dependence | checked | `qa_search_min_similarity` default 0.45; no deployed override; applies after redeploy |
| R5 | 7 config/env | checked | deployed uses 768 defaults (collections 768 + today's 768 ingest); env-file edit is cosmetic, no runtime change |
| R4 | 6 silent-inert | checked | logging is side-effect-only; surfaces empties for future diagnosis |
| all | other lenses | not applicable / checked | no ordering/units/encoding values cross beyond rows shape (covered) |

## Cycle 1 Assessment — Blocker Gap Ledger

| gap_id | severity | req_id | lens | evidence (both sides) | why it breaks the requirement | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SGAP-001 | blocker | R1 / INV-2 | 1,4 cross-feature contract / e2e | **Producer:** memory-knowledge `search_qa_knowledge` returns `WorkflowResult(...).model_dump_json()` → `{run_id,tool_name,status,data:{advisory_only,rows,warnings}}` (`server.py:1649-1654`, `workflows/base.py:8-14`). **Transport:** `call_tool`→`content[].text`, `call_tool_json`→`json.loads` full envelope, no unwrap (`knowledge_client.py:314-319,364-395`). **Consumer:** `handle_qa_suggest` reads `(data).get("rows")` / `(data).get("warnings")` at top level (`mcp_server.py:15941,15946`). | `rows` lives at `data["data"]["rows"]`; consumer reads `data["rows"]` → `None` → returns `[]` for every question regardless of the memory-knowledge fix. The mk plan (R2+R3) becomes user-invisible. | **Required workflow-orch co-fix** (record in plan handoff, not a mk code edit): in `handle_qa_suggest`, unwrap the envelope — `env = await client.call_tool_json(...)`; `payload = (env or {}).get("data") or {}`; `rows = payload.get("rows") or []`; `warnings = payload.get("warnings") or []`. Also treat `env.get("status") == "error"` as no-rows + warning. Add a workflow-orch test that feeds a `WorkflowResult`-shaped envelope and asserts `rows` surface. | Plan handoff escalated with exact evidence + fix; R1 satisfiable once mk + this land | closed (documented as required co-fix) |

## Cleanup / Known-Limitation List

| item_id | req | issue | note |
| --- | --- | --- | --- |
| SCLN-001 | R2/R3 | lexical-fallback `score` is `ts_rank` (≠ cosine scale); operator may display mixed scales | cosmetic; advisory only |
| SCLN-002 | R1 | mk-side fix verified vs live data, but the end-to-end pass cannot run prod until both mk + workflow-orch land | acceptance = post-deploy re-check already in Step 5 |

## Cycle 1 Plan

| gap_id | target | exact edit |
| --- | --- | --- |
| SGAP-001 | plan handoff section | escalate to a numbered **Required workflow-orch co-fix** with producer/transport/consumer evidence + the unwrap fix; mark INV-1 key-symmetry as verified-with-evidence |

## Cycle 1 Edits

Applied to `docs/qa-suggest-fix-plan.md`, "Out of scope — workflow-orch" section:
- Added **Required co-fix (R1 end-to-end): `handle_qa_suggest` envelope unwrap** with full `path:line` evidence on both sides and the precise consumer fix + test.
- Re-labelled the `repository_key` bullet as **verified** with evidence (`workflow_engine.py:13021` ↔ `mcp_server.py:15896-15898`).
- Noted the existing "log the ingest result" item remains a separate observability nicety (not the blocker).
- Added a note that R1's end-to-end acceptance (Step 5 prod re-check) requires **both** the mk change and the workflow-orch unwrap.

## Cycle 1 Validation

- Re-traced R1: with the documented consumer unwrap, `payload.data.rows` reaches the operator → R1 satisfiable end-to-end once both land. mk side already verified vs live data.
- Post-edit new-gap pass: the unwrap fix introduces no new asymmetry (it reads the producer's actual shape); `status=="error"` handling added so an mk error degrades to a clean warning, not a crash. No scope drift (still documented as workflow-orch handoff, not an mk code edit).
- INV-1, INV-3, R2, R3 re-confirmed against the evidence above; unchanged.

## Cycle 2 Assessment

Fresh full pass over R1–R13 + INV-1/2/3 against the edited document. Carry-forward: SGAP-001 closed (documented as required co-fix), SCLN-001/002 noted.

- Lens 1 cross-feature: consumer-shape contract now locked in the plan with the unwrap fix.
- Lens 2 data-reality: `question_tsv` populated; scores admit at 0.45 — confirmed.
- Lens 4 e2e: chain now complete once both sides land.
- Lens 5 producer/consumer: key symmetry verified; response-shape symmetry locked.
- Lens 6 silent-inert: lexical fallback + logging cover the degrade paths.
- Lens 7 config/env: threshold default applies; env edit cosmetic.
- No new blocker gaps.

## Final Convergence Check — Final Readiness Proof

| req_id | satisfied end-to-end? | evidence |
| --- | --- | --- |
| R1 | yes — **conditional on the documented workflow-orch unwrap co-fix** (now a required handoff item) | SGAP-001 closure; mk side verified vs live data |
| R2 | yes (mk) | live lexical match; `qa_memory.py:196-211` |
| R3 | yes (mk) | live scores 0.49–0.60 admit at 0.45 |
| R4 | yes | side-effect logging; Step 4 |
| R5 | yes | 768 defaults deployed; env edit cosmetic |
| R7 | yes | server resolves from settings; Step 3c + server test |
| INV-1 | yes | both sides read `repository_key` context key |
| INV-2 | yes (once co-fix lands) | unwrap documented |
| INV-3 | yes | `question_tsv` 12/12 populated |

Converged in 2 cycles. **Key satisfaction gap closed:** an un-cited sibling-feature cross-contract
mismatch (SGAP-001) — the qa.suggest consumer read the memory-knowledge response one nesting level
too shallow, which would have made the entire fix user-invisible. The memory-knowledge plan is
satisfaction-ready; R1 end-to-end is satisfiable once the documented workflow-orch unwrap co-fix
also lands. Stated limitation: full prod acceptance can only be confirmed after both changes deploy.
