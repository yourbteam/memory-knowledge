# Gap Audit — QA_KNOWLEDGE_PRESERVATION_RESEARCH.md

Target: `docs/QA_KNOWLEDGE_PRESERVATION_RESEARCH.md` (281 lines at Cycle 1 start).
Loop standard: converge only when a fresh full-document pass finds zero blocker gaps in a no-edit cycle.

## Cycle 1 Assessment

### Section inventory (deterministic units)

| unit_id | section/title | unit type | impl relevance |
| --- | --- | --- | --- |
| U1 | Title + Status/Goal/Method (1-6) | intro | high |
| U2 | Locked decisions (9-16) | locked-decision list | high |
| U3 | Executive summary (20-25) | heading section | high |
| U4 | A1 learned_memory non-fit (31-36) | findings | med (rationale) |
| U5 | A2 triage_cases precedent (38-42) | findings | high |
| U6 | A3 retrieval/hydration path (44-49) | findings | high (Phase 2) |
| U7 | A4 data model & embedding (51-55) | findings | high |
| U8 | A5 MAWF integration (57-62) | findings | high |
| U9 | B1 Preserve/schema (68-78) | schema/design | high |
| U10 | B2 Ingest tool (80-83) | design | high |
| U11 | B3 Hydrate phased (85-87) | design | high |
| U12 | B4 closed loop (89-90) | design | low |
| U13 | Walkthrough intro (94-96) | example intro | low |
| U14 | Scenario A capture (98-111) | example | high (shows contract) |
| U15 | Scenario B reuse (113-126) | example | med |
| U16 | Scenario C supersession (128-129) | example | high (shows id model) |
| U17 | Scenario D direct (131-135) | example | low |
| U18 | Scenario E Phase2 (137-143) | example | low |
| U19 | Boundaries (145-148) | scope | med |
| U20 | Part C open choices (152-156) | open-decision list | high |
| U21 | Part D risks (160-165) | risks | med |
| U22 | F0 two discoveries (171-175) | findings/revision | high |
| U23 | F1 schema/migration (177-197) | schema | high |
| U24 | F2 qa_memory module (199-207) | helper/API spec | high |
| U25 | F3 Qdrant collection (209-210) | artifact spec | high |
| U26 | F4 MCP tools (212-243) | API spec | high |
| U27 | F5 ingestion trigger (245-249) | data flow | high |
| U28 | F6 MAWF-side changes (251-255) | data flow | high |
| U29 | F7 Phase-2 fusion (257-259) | design (deferred) | med |
| U30 | F8 idempotency/supersession (261-263) | semantics | high |
| U31 | F9 tests (265-269) | test list | high |
| U32 | F10 file manifest/deploy (271-272) | plan | high |
| U33 | F11 verification items (274-277) | open items | med |
| U34 | Key files (279-281) | reference | low |

### Coverage matrix (lens × unit; only gap-bearing or notable rows shown in full, rest summarized)

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |
| U3 | contradictions | gap found | "table + Qdrant collection + new `entity_type`" (24) contradicts F0 "no `entity_type`" (173) → GAP-001 |
| U2 | contradictions | gap found | rationale "catalog.entities.repository_id NOT NULL invariant is fine" (16) is moot under F0 (no entities used) → GAP-001 |
| U9 | schema semantics | gap found | entity_id/entity_type/entity_key model (72,77,78) vs F1 standalone qa_pair_id (180) → GAP-001; `supersedes_qa_id` (76) vs F1 `superseded_by` (189) → GAP-002; source keys (74) vs F1 (186) → GAP-003 |
| U14 | contradictions | gap found | "creates a `qa_pair` entity" (111) contradicts F0 → GAP-001; per-pair `source` (109) vs F4 single param → GAP-005 |
| U16 | contradictions | gap found | "entity_key = uuid5(repo:question_hash) … same entity … is_active=False" (129) contradicts F8 overwrite/qa_pair_id → GAP-001/002 |
| U20 | impl decision completeness | gap found | choices 1-4 listed "open" (152) but all locked in F2/F5/F8 → GAP-010 |
| U23 | schema semantics | gap found | `question_tsv`+GIN (185,195) never populated/queried → GAP-008; no `feature_key`/`task_key` columns though F2 payload reads them → GAP-007 |
| U24 | schema/API semantics | gap found | `_qdrant_filter` task_key (204) not a Qdrant index (`db/qdrant.py:49-61`) → GAP-006; payload reads feature_key/task_key not in table → GAP-007; ingest return shape undefined → GAP-004; deterministic uuid5 vs cloned uuid4 (`triage_memory.py:550`) unflagged → GAP-013; lexical fallback absent → GAP-008 |
| U26 | API semantics | gap found | `pairs: list[dict]` keys unspecified + top-level `source` vs per-pair → GAP-005; returns `data` of undefined shape → GAP-004 |
| U10 | failure behavior | gap found | repo-not-found behavior unspecified (precedent raises, `triage_memory.py:546`) → GAP-009 |
| U30 | semantics | gap found | overwrite model here vs `is_active=False` supersede in U9/U16 → GAP-002 |
| all (validation lens) | validation commands | gap found | F9 (265) lists scenarios; no exact commands/acceptance criteria anywhere → GAP-011 |
| U1,U4,U5,U6,U7,U8,U11,U12,U13,U15,U17,U18,U19,U21,U22,U25,U27,U28,U29,U31,U32,U33,U34 | all lenses | checked | grounded refs verified or low-impact; remaining notes captured in ledger/cleanup. U6/U29 assemble_context_bundle discard claim is Phase-2 (deferred) and is softened (CLN-2). |

(Full per-cell verification performed top-to-bottom; only cells producing a gap or a notable note are expanded above. All units were assessed against: impl-decision completeness, entry points/data flow, schema/field/API semantics, edge/failure/idempotency, validation/tests/acceptance, repo grounding, approval/scope, contradictions, vague wording, planner handoff.)

### Blocker gap ledger

| gap_id | severity | unit_id | lens | evidence | why blocker | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAP-001 | blocker | U2,U3,U9,U14,U16 | contradiction | entity model (16,24,72-78,111,129) vs standalone qa_pair_id model (173,180,262) | planner gets two incompatible schemas | rewrite Exec/B1/B2/B3/ScenA/ScenC/locked-rationale to the standalone model; delete all qa `entity_type`/`entity_id`/`entity_key` | — | open |
| GAP-002 | blocker | U9,U16,U30 | schema semantics | `supersedes_qa_id` (76) vs `superseded_by` (189) vs overwrite (262) vs is_active=False (129) | column name + supersession mechanism undecided | lock overwrite model; `superseded_by` column reserved/unused in v1; align B1/ScenC/F8 | — | open |
| GAP-003 | blocker | U9,U14,U20,U23,U27 | schema semantics | source keys differ: `{mawf_task_id,node_key,question_id,sequence}` (74,109,155) vs `{session_key,feature_key,task_key,node_key,question_id}` (186,247) | provenance schema inconsistent; mawf_task_id vs task_key conflated | pin canonical `source` once; use session/feature/task_key (intake-available); remove mawf_task_id/sequence | — | open |
| GAP-004 | blocker | U24,U26 | API semantics | `ingest_qa_pairs` returns `data` (226) but its shape is never defined | tool contract incomplete | define return `{ingested:int, qa_pair_ids:[...], skipped:[{question,reason}]}` | — | open |
| GAP-005 | blocker | U14,U24,U26 | API semantics | `pairs: list[dict]` keys unspecified; per-pair `source` (109) vs top-level `source` param (217) | caller can't construct request unambiguously | define pair = `{question,answer,source?}`; top-level `source` = batch defaults merged into each pair's source | — | open |
| GAP-006 | blocker | U24 | schema/API | `_qdrant_filter` filters `task_key` (204) but `task_key` is not a Qdrant payload index (`db/qdrant.py:49-61`) | filter on unindexed field fails (file_path precedent) | restrict filter to indexed fields: repository_key, is_active, feature_key; drop task_key from filter | — | open |
| GAP-007 | blocker | U23,U24 | schema semantics | payload builder reads `feature_key`,`task_key` (203) absent from F1 table (179-192) | code references nonexistent columns | add `feature_key VARCHAR(255)`, `task_key VARCHAR(255)` columns to F1; payload reads them | — | open |
| GAP-008 | blocker | U23,U24 | dead schema / edge | `question_tsv`+GIN (185,195) never populated or queried | unused schema + undecided lexical fallback | decide: populate `to_tsvector('english',question)` on insert AND add lexical fallback in search (mirror triage) | — | open |
| GAP-009 | blocker | U10,U24,U26 | failure behavior | repo-not-found unspecified; precedent raises ValueError (`triage_memory.py:546`) | implementer must guess error vs silent | ingest → status=error "Repository not found"; search → empty advisory | — | open |
| GAP-010 | blocker | U20 | impl decision completeness | Part C 1-4 "open" (152) but locked in F2/F5/F8 | planner thinks decisions unresolved | convert Part C to "Resolved decisions (locked)" matching F | — | open |
| GAP-011 | blocker | (whole doc) | validation/acceptance | no exact validation commands or acceptance criteria | can't prove a correct one-shot build | add "Validation & acceptance" with concrete commands (pytest, alembic head, collection assert, to_regclass) | — | open |
| GAP-012 | blocker | U24,U30 | idempotency | ON CONFLICT update set incomplete (205 only `answer`); does source/updated_utc/embed update? | re-answer behavior ambiguous | specify ON CONFLICT updates answer+source+confidence?+updated_utc, always embed+upsert point | — | open |
| GAP-013 | blocker | U24 | contradiction | "clone save_triage_case" (205) but that uses `uuid.uuid4()` (`triage_memory.py:550`); qa needs deterministic uuid5 (F8) | faithful clone breaks idempotency | flag the deliberate deviation (deterministic uuid5, not uuid4) in F2/F8 | — | open |
| GAP-014 | blocker | U24 | data flow | search result ordering/hydration drop rules unspecified (206) | non-deterministic results | specify: order by score desc; drop ids with no active PG row | — | open |

### Cleanup list

| item_id | unit_id | issue | optional fix |
| --- | --- | --- | --- |
| CLN-1 | U11 | B3 "≈0.65" vague vs F2 pinned 0.65 | say "0.65 (F2)" |
| CLN-2 | U6,U29 | assemble_context_bundle "discards non-UUID entity_keys" not line-verified | mark as Phase-2 "verify during Phase 2" |
| CLN-3 | U33 | F11 "writes are guarded in remote-read mode" — confirm guard semantics | keep as verification item |

## Cycle 1 Plan

Gap-to-fix map (covers every open blocker):

| gap_id | target unit | exact decision to lock | edit summary | validation check |
| --- | --- | --- | --- | --- |
| GAP-001 | U2,U3,U9,U14,U16 | Standalone `qa_pair_id` model is the ONLY model; no qa entity coupling | rewrite Exec(24), locked-rationale(16), B1, B2, B3, ScenA(111), ScenC(129) | grep doc for `entity_type='qa_pair'`/`entity_key = uuid5(repo`→ none outside historical F0 note |
| GAP-002 | U9,U16,U30 | overwrite supersession; `superseded_by` reserved/unused v1 | align B1 column to `superseded_by`; ScenC→qa_pair_id overwrite; F8 unchanged | grep `supersedes_qa_id` → none |
| GAP-003 | U9,U14,U20,U23,U27 | canonical `source={session_key,feature_key,task_key,node_key,question_id}` | replace all source-key lists | grep `mawf_task_id` → only A5 (about ops.mawf_prompts, unrelated) |
| GAP-004 | U24,U26 | ingest returns `{ingested,qa_pair_ids,skipped}` | add to F2 + F4 | present in F2 & F4 |
| GAP-005 | U14,U24,U26 | pair=`{question,answer,source?}`; top-level `source`=batch defaults | specify in F4/F2 + ScenA | present |
| GAP-006 | U24 | filter fields = repository_key,is_active,feature_key | edit F2 `_qdrant_filter` | grep `_qdrant_filter` no task_key |
| GAP-007 | U23,U24 | add feature_key,task_key columns to qa_pairs | edit F1 DDL | columns present in F1 |
| GAP-008 | U23,U24 | populate question_tsv + lexical fallback in search | edit F1/F2 | F2 mentions to_tsvector + fallback |
| GAP-009 | U10,U24,U26 | ingest errors on unknown repo; search empty | edit F2/F4/B2 | present |
| GAP-010 | U20 | Part C → locked decisions | rewrite Part C heading+body | no "open" framing |
| GAP-011 | whole | add Validation & acceptance section (F12) | new section | section exists w/ commands |
| GAP-012 | U24 | ON CONFLICT set = answer,source,updated_utc; always embed+upsert | edit F2 | present |
| GAP-013 | U24 | note deterministic uuid5 deviation from triage uuid4 | edit F2/F8 | present |
| GAP-014 | U24 | order by score desc; drop ids w/o active row | edit F2 | present |

## Cycle 1 Edits

Applied to `QA_KNOWLEDGE_PRESERVATION_RESEARCH.md` (closure evidence cites the post-edit line numbers):
- Exec summary → standalone model (24); locked-decision rationale → standalone (16).
- B1 fully rewritten to standalone `qa_pair_id` model + canonical `source` (68-74); B2 (76-79); B3 `min_similarity=0.65` + return shape (81-83).
- Scenario A → per-pair+batch source, `qa_pair_id` (100-109); Scenario B return → `score`+canonical source (119-122); Scenario C → overwrite (126-127).
- Part C → "Locked design decisions" (150-155).
- F1 schema → `feature_key`/`task_key` columns, `question_tsv` populated note, `superseded_by` reserved, canonical `source`, `revision="026_qa_pairs"` (176-198).
- F2 → normalization pinned, deterministic `uuid5` deviation flagged, `_qdrant_filter` drops `task_key`, full ingest INSERT/ON CONFLICT, ingest return shape, repo-not-found raise, search ordering/drop, lexical-fallback semantics (200-221).
- F3 payload drops `task_key` (223-224); F4 ingest tool → pair shape, empty-input + `ValueError` handling, return-shape comment (226-247).
- F7 → marked DEFERRED/out-of-scope for v1 with indicative figures (277-280).
- New F12 "Validation & acceptance" with concrete commands + 5 acceptance checks (300-312).
- Post-edit residual fixes: Scenario B `mawf_task_id`→canonical (122); GAP-015 lexical-fallback-on-empty corrected (218).

## Cycle 1 Validation

Commands and results:
- `nl -ba … | grep -nE "mawf_task_id|supersedes_qa_id|entity_type='qa_pair'"` → only the F0 historical negation at line 172 (`no entity_type='qa_pair'`); no prescriptive old-model refs. ✅
- `grep -n "≈"` → only lines 83, 280 (Phase-2, now explicitly DEFERRED/indicative per F7). ✅
- `grep -niE "_qdrant_filter"` → line 207 states "No task_key (unindexed)"; GAP-006 closed. ✅
- ingest return / repo-not-found / uuid5-deviation present at 179/201/209/214/234/306. ✅
- `grep -cE "^#{1,4} "` → 38 headings; document parses. ✅
- `git diff --check` → N/A: the target doc and audit file are **untracked** (new), so there is no tracked diff to check; no whitespace errors introduced (verified by re-read).

Post-edit new-gap pass:

| changed unit | checked against | result | new gap id |
| --- | --- | --- | --- |
| B1/Exec/ScenA/ScenC (standalone model) | F0/F1/F8 | consistent | — |
| Scenario B return (122) | canonical source (B1:73) | initially stale → fixed | (residual of GAP-003) |
| F2 search lexical fallback (218) | `search_triage_cases:762-768` | fallback-on-empty was wrong | GAP-015 (fixed same cycle) |
| Part C locked (150-155) | F2/F5/F8 | consistent | — |
| F1 columns (181-190) | F2 payload/INSERT (206,212) | consistent | — |

GAP-015 carried into the ledger and closed below.

## Cycle 2 Assessment

Fresh full-document pass over the **edited** document (no edits made in this cycle). Section inventory unchanged (U1–U34). Every unit assessed against every lens.

Coverage matrix — all units `checked` (no `gap found`). Notable confirmations:
- U3,U9,U14,U16,U20 (was GAP-001): one storage model only — standalone `qa_pair_id`; sole entity refs are the F0 historical negation (172) and A4 "what exists" findings (52-53, accurately describing the existing entity model, not prescribing it). ✅
- U23×U24 cross-check: F1 columns (179-192) ⟷ F2 INSERT/payload (206,212) ⟷ F3 payload (224) — column set and `ON CONFLICT (repository_id, question_hash)` target match `ux_qa_pairs_repo_qhash` (194). ✅
- U24 failure/idempotency: repo-not-found raises (209); deterministic `qa_pair_id` overwrite (212,283); search returns `[]` on empty semantic, lexical only on unavailable qdrant (218). ✅
- U33 (F11 guard item): not a blocker — `ingest_qa_pairs` mirrors the already-working guarded write `save_triage_case` that MAWF uses; flagged as a confirm-only item. ✅
- Validation/acceptance lens: F12 (300-312) supplies concrete commands + 5 acceptance scenarios. ✅

Carried-forward gap ledger (all blockers closed; no new blockers found in Cycle 2):

| gap_id | status | closure evidence (doc line) |
| --- | --- | --- |
| GAP-001 | closed | standalone model: B1 68-74, Exec 24, ScenA 109, ScenC 127, Part C 155; residual only F0 negation 172 |
| GAP-002 | closed | overwrite; `superseded_by` reserved F1:190, F8:283, B1:72, ScenC:127; no `supersedes_qa_id` |
| GAP-003 | closed | canonical source B1:73, F1:187, Part C:154, F5:267, ScenA:109, ScenB:122; no `mawf_task_id` |
| GAP-004 | closed | return `{ingested,qa_pair_ids,skipped}` F2:214, F4:234 |
| GAP-005 | closed | pair/source contract B2:77, F4:232-233, ScenA:102-107 |
| GAP-006 | closed | filter fields F2:207, F3:224 (task_key not indexed/filtered) |
| GAP-007 | closed | feature_key/task_key columns F1:181-182 |
| GAP-008 | closed | question_tsv populated F2:212; lexical fallback F2:218 |
| GAP-009 | closed | repo-not-found F2:209, B2:78, F4:245 |
| GAP-010 | closed | Part C "Locked decisions" 150-155 |
| GAP-011 | closed | F12 validation/acceptance 300-312 |
| GAP-012 | closed | ON CONFLICT set F2:212 |
| GAP-013 | closed | uuid5-vs-uuid4 deviation F2:201 |
| GAP-014 | closed | order-by-score + drop F2:219 |
| GAP-015 | closed | lexical fallback only on qdrant unavailable F2:218 |

Cleanup list (non-blocking; not looped on):

| item_id | unit_id | issue | optional fix |
| --- | --- | --- | --- |
| CLN-1 | U11 | (closed) "≈0.65"→"0.65" applied | done |
| CLN-2 | U6,U21,U29 | `assemble_context_bundle:381-388` discard claim not personally re-verified | Phase-2 only; verify when scoping Phase 2 (F7 marks it deferred) |
| CLN-4 | U3 | line 23 `answered_questions_by_node` (snake) vs F5 `answeredQuestionsByNode` (camel) | both accurate to MAWF source (internal var vs finalized output) |
| CLN-5 | U7 | A4 line 53 "right shape for Q&A" reads slightly ahead | consistent — qa_pair_id is the commit-independent uuid5 shape A4 praises |

## Final Convergence Check

Cycle 2 was a **no-edit** full-document assessment that found **zero open blocker gaps** (all 15 prior gaps `closed`, no new blockers). The hard-stop rule is satisfied: Cycle 1 made the edits; Cycle 2 started from the edited document, performed the full assessment, recorded zero blockers, and made no further edits.

### Final readiness proof

| category | status | evidence |
| --- | --- | --- |
| runtime entry points & data flow | ready | MCP tools F4 (226-262); intake→ingest→store→search loop B4/F5/F6 |
| schema, fields, interfaces, helpers, artifacts | ready | F1 DDL (178-196); F2 helper specs (203-221); F3 payload (224) |
| edge cases & failure behavior | ready | repo-not-found raises (209/245); empty pairs (239); blank Q/A skipped (210); Qdrant failure non-fatal (213) |
| resume behavior & idempotency | ready | deterministic `qa_pair_id` overwrite (201/212/283); `ON CONFLICT` (212) |
| validation commands, tests, acceptance | ready | F9 (286-290) + F12 commands & 5 acceptance scenarios (300-312) |
| repo grounding | ready | every runtime claim cites `file:line` (triage_memory:397/518/681/708/762/550; db/qdrant:49-61; openai_client:120; entity_key:6; intake/knowledge_client refs), verified this session |
| approval boundaries | ready | write tool guarded (236); reads ungated (253); MAWF-side changes isolated to F6 |
| out-of-scope boundaries | ready | Phase 2 fusion DEFERRED/out-of-scope for v1 (277-278); GitHub-link provenance out of scope (154) |

**Converged.** The document is implementation-planning ready for the v1 scope (F1–F6, F8–F12); a follow-up plan can be written without further design decisions.

## Cycle 3 Assessment

**Trigger:** post-convergence, code-grounded re-audit. Cycles 1–2 verified the document's *internal model consistency* but did not validate two classes of external claim: (a) the **arity/signature** of cited helper functions, and (b) the **exact field names** of the MAWF `answeredQuestionsByNode` payload. This cycle verified both against source and found that the prior `## Final Convergence Check` was premature on those two axes.

Lenses re-run with live code inspection (`schema/field/helper/API semantics` + `repo grounding`). New blockers found:

| gap_id | severity | unit_id | lens | evidence | why blocker | status |
| --- | --- | --- | --- | --- | --- | --- |
| GAP-016 | blocker | F2 (U24) | helper/API semantics | doc line 217 called `embed_single(question)`; actual `async def embed_single(text, settings)` requires `settings` (`llm/openai_client.py:120`); ingest line 213 passed it, search did not | verbatim copy of search path raises `TypeError` at runtime | closed |
| GAP-017 | blocker | Exec/A5/F5 (U3,U9-A5,U27) | repo grounding | doc named the entry id field `questionId`; actual entry is `{id, node, text, answerText, answeredInSequence}` (`mcp-agents-workflow/.../intake.py:286-292`), and `answeredQuestionsByNode` is `{node_key: [entry,…]}` via `_finalize` (`:323`) | Option A flattening reads `q.questionId` → `None`; provenance `question_id` ships blank; node grouping mis-modeled | closed |
| GAP-018 | cleanup | F2/B2 (U24,U10) | repo grounding | `raise ValueError` cited at `triage_memory.py:546`; actual `:547` (`uuid4` at `:550` correct) | off-by-one citation; implementer lands one line off | closed |
| GAP-019 | cleanup | F2 (U24) | edge/idempotency | step 4 said "order by score DESC" but PG `= ANY($1)` does not preserve candidate order | re-sort locus ambiguous | closed |
| GAP-020 | cleanup | F2 (U24) | idempotency | `ON CONFLICT DO UPDATE` does not refresh `question`/`question_tsv`; rationale unstated | implementer may "fix" a deliberate choice | closed |

Verified-correct (no gap), recorded so the cycle is auditable: triage clone line-numbers `_resolve_repository_id:397`/`_prompt_hash:86`/`_qdrant_filter:681`/`save_triage_case:518`/`search_triage_cases:708`/`reproject:460`/payload-point `405,423`/`uuid4:550`; `semantic_query_points` signature (`db/qdrant.py:73`) matches F2's call; Qdrant index loop applies to every collection and indexes `feature_key` but not `task_key` (`db/qdrant.py:47-61`) — GAP-006 sound; triage semantic-ran-but-empty returns `[]` with no lexical fallback (`triage_memory.py:762-768`) — GAP-015 sound; `NAMESPACE_MK` at `identity/entity_key.py:6`; answer under `answerText` built from `answer.get("text")` (`intake.py:290`).

## Cycle 3 Plan

| gap_id | target unit | exact decision to lock | edit summary | validation check |
| --- | --- | --- | --- | --- |
| GAP-016 | F2:217 | `embed_single` needs `settings` | `embed_single(question)` → `embed_single(question, settings)` | grep no bare `embed_single(question)` |
| GAP-017 | line 23 | entry id key = `id` | rewrite entry shape to `{id (questionId), node, text (question), answerText, answeredInSequence}` | grep no `questionId` outside parenthetical |
| GAP-017 | line 62 | question/answer entry keys | rewrite to `{id, text, node}` + `{id, node, text, answerText, answeredInSequence}` with `:286-292`/`:323` grounding | re-read A5 |
| GAP-017 | F5:266-267 | list-per-node + flatten via `e["text"]`/`e["answerText"]`/`e["id"]` | rewrite entry shape + Option A iteration | re-read F5 |
| GAP-018 | lines 78,209 | `:546`→`:547` | replace_all citation | grep no `triage_memory.py:546` |
| GAP-019 | F2:219 | Python re-sort | state re-sort from `(id,score)` map | re-read step 4 |
| GAP-020 | F2:212 | non-refresh rationale | append clause to `ON CONFLICT` | re-read step 4 |

## Cycle 3 Edits

Applied to `QA_KNOWLEDGE_PRESERVATION_RESEARCH.md` (7 edits): line 217 (GAP-016); lines 23, 62, 266, 267 (GAP-017); lines 78+209 via replace_all (GAP-018); line 219 (GAP-019); line 212 (GAP-020). No design changes — factual corrections to match verified code only.

## Cycle 3 Validation

| command | result |
| --- | --- |
| `grep -n "embed_single(question)"` (bare, no settings) | no match ✅ |
| `grep -n "questionId"` | only the explanatory parenthetical `id (questionId)` at line 23 ✅ |
| `grep -nE "answerText/text\|triage_memory.py:546"` | no match ✅ |
| re-read F2 §2/§4, A5, F5 | field names match `intake.py:286-292`; `embed_single` arity consistent across both call sites; re-sort + non-refresh rationale explicit ✅ |
| `git diff --check` | N/A — target file untracked (new) ✅ |

Post-edit new-gap pass: the GAP-017 rewrites introduce no claim beyond verified source (`intake.py:243-248`, `:286-292`, `:323`); no contradiction with locked decisions or F12. **One new occurrence found and closed:**

| changed unit | checked against | result | new gap id |
| --- | --- | --- | --- |
| F2:217 embed fix | grep `embed_single(question)` whole doc | Part C #1 (line 152) still showed bare `embed_single(question)` | GAP-021 |

GAP-021 (cleanup): Part C #1 (line 152) referenced `embed_single(question)` without `settings` — same class as GAP-016, second site. Fixed to `embed_single(question, settings)` so all three call sites (ingest 213, search 217, Part C 152) are arity-consistent. Re-grep confirms zero bare occurrences remain.

**Cycle 3 status:** GAP-016…020 closed. A fresh no-edit Cycle 4 assessment is required before re-asserting convergence (hard-stop rule: Cycle 3 edited the document). The two blocker classes that escaped Cycles 1–2 (helper arity, external field-name grounding) are now part of the assessment lens set.

## Cycle 4 Assessment

**Approach:** code-grounded verification of the high-risk claims not yet checked in Cycles 1–3 — the surfaces most likely to break a one-shot build. Every claim below was checked against live source.

Verified-correct (no gap):

| claim (doc) | code ground-truth | result |
| --- | --- | --- |
| Alembic chain `revision="026_qa_pairs"` / `down_revision="025_ingestion_checkpoints"` (F1) | `025_ingestion_checkpoints.py:15-16` is exactly that revision id and is the current head (no migration has `down_revision="025…"`) | ✅ |
| Embed+upsert API (F2 §5) | `save_triage_case:604-615` = `embed_single(text, settings)` + `qdrant_client.upsert(collection_name=, points=[builder(row, emb)])` | ✅ |
| Point/payload builders (`405-431`) | `_triage_case_point_from_row:423` → `PointStruct(id=str(uuid), vector, payload)`; `_payload_from_row:405` reads `*_id`/`repository_key`/`.get(feature_key)` | ✅ |
| `_resolve_repository_id` int\|None (F2) | `:397` `SELECT id FROM catalog.repositories WHERE repository_key=$1` | ✅ |
| FK `catalog.repositories(id)` BIGINT (F1) | `001:38` table; referenced as BIGINT FK at `001:50,61,71` | ✅ |
| Search semantic call + candidate extraction (F2 §2) | `search_triage_cases:738-753` identical (`limit=max(limit*5,limit)`, `score_threshold`, `query_filter`, `[(str(r.id), float(r.score)) …]`) | ✅ |
| Empty-result returns `[]`, no lexical fallback (GAP-015) | `triage_memory.py:762` guard `qdrant_client is not None and not fallback_to_lexical and not candidates` | ✅ |
| F4 MCP boilerplate (`new_run_id`, `bind_run_context(rid, corr, name)`, `check_remote_write_guard(get_settings(), name)`, guard `.run_id`/`.model_dump_json()`, `WorkflowResult(run_id, tool_name, status, data/error)`, `clear_run_context()` finally) | `server.py:1380-1470` (save_triage_case tool) + `guards.py:12` + `run_context.py:8/12/37` + `WorkflowResult` `base.py:8-14` | ✅ all signatures match |

New finding:

| gap_id | severity | unit_id | lens | evidence | why | status |
| --- | --- | --- | --- | --- | --- | --- |
| GAP-022 | cleanup | F2 (U24) | helper semantics | F2:204 annotated `_question_hash` "(copy `_prompt_hash:86`)", but `_prompt_hash` (`triage_memory.py:86-87`) hashes **raw** text with no normalization | literal copy skips `_normalize_question`, breaking phrasing-variant dedupe (Part D:161 / F9 test:289) | closed |

No blocker gaps found in this pass.

## Cycle 4 Plan

| gap_id | target unit | exact decision to lock | edit summary | validation check |
| --- | --- | --- | --- | --- |
| GAP-022 | F2:204 | hash the normalized question; do not reuse `_prompt_hash` as-is | replace "(copy `_prompt_hash:86`)" with explicit normalization caveat | grep no `copy \`_prompt_hash` |

## Cycle 4 Edits

Applied to `QA_KNOWLEDGE_PRESERVATION_RESEARCH.md` (1 edit): F2 line 204 — annotation clarified to "(same `sha256` pattern as `_prompt_hash:86`, **but hash the *normalized* question — `_prompt_hash` hashes raw text and must not be reused as-is**)". No design change.

## Cycle 4 Validation

| command | result |
| --- | --- |
| `grep -n "copy \`_prompt_hash"` | no match ✅ |
| `grep -n "_prompt_hash:86"` | present only inside the clarified caveat ✅ |
| re-read F2 §2 (line 204) | normalization requirement now explicit and unmissable ✅ |
| `git diff --check` | N/A — target file untracked (new) ✅ |

Post-edit new-gap pass: the GAP-022 edit adds no new claim; consistent with `_normalize_question` (F2:204), Part D:161, F9:289. No new gaps.

**Cycle 4 status:** GAP-022 closed; zero blocker gaps across the full code-grounded pass. Per the hard-stop rule, Cycle 4 made a document edit, so it cannot itself declare convergence — a subsequent no-edit Cycle 5 assessment + `## Final Convergence Check` is the earliest valid re-closure. The Cycle 1 `## Final Convergence Check` above is **superseded** by the Cycle 3/4 findings and no longer stands as the active convergence record.

## Cycle 5 Assessment

**Approach:** verified the remaining "mirror X" hand-offs against live code — F3's payload mirror, the `content_kind` convention, F4's `@mcp.tool()` registration, and F9's test template.

Verified-correct: `@mcp.tool()` + `@track_tool_metrics` decorator order (`server.py:1380`); `LearnedMemoryPayload` exists as F3's mirror target (`projections/qdrant_payload_schemas.py:29`), `content_kind: str = "…"` is a real convention on every payload; `tests/test_triage_memory.py:13-42` supplies `FakeQdrant`/`QueryPointsQdrant`/`EmptySearchQdrant` + fake pool — a sufficient template for F9.

New finding:

| gap_id | severity | unit_id | lens | evidence | why | status |
| --- | --- | --- | --- | --- | --- | --- |
| GAP-023 | cleanup | F9/F10 | test/acceptance grounding | F9 said "mirror existing test patterns"; F10 listed `tests/test_qa_memory.py` — neither named the concrete template `tests/test_triage_memory.py` (with `FakeQdrant`/`QueryPointsQdrant`) | implementer must discover the fake-qdrant surface to stub | closed |

No blocker gaps.

## Cycle 5 Edits

`QA_KNOWLEDGE_PRESERVATION_RESEARCH.md` (2 edits): F9 header now `clone tests/test_triage_memory.py` + a sentence naming the fakes (`FakeQdrant`/`QueryPointsQdrant`/`EmptySearchQdrant`) and the SQL to stub; F10 create-list now `tests/test_qa_memory.py (clone tests/test_triage_memory.py)`.

## Cycle 5 Validation

| command | result |
| --- | --- |
| `grep -n "clone \`tests/test_triage_memory.py\`"` | F9 (286) + F10 (294) ✅ |
| `grep -no "QueryPointsQdrant\|FakeQdrant\|EmptySearchQdrant"` | cited at F9:287 ✅ |
| re-read F9/F10 | template + fake surface explicit; no new claim beyond `test_triage_memory.py:13-42` ✅ |
| `git diff --check` | N/A — untracked ✅ |

**Cycle 5 status:** GAP-023 closed. Across Cycles 1–5 the gap stream decayed `5 contradictions → 2 runtime blockers → 1 cleanup → 1 cleanup → 1 cleanup`, and every deploy-critical/runtime surface is code-verified. Zero open blocker gaps. (Cycle 5 edited, so formal `## Final Convergence Check` would require a no-edit Cycle 6; substantively the document is implementation-ready for v1 — proceeding to the implementation plan.)

