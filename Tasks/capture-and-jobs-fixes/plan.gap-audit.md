# Gap Audit — `plan.md` (Capture & Jobs Fixes)

Target: `/Users/kamenkamenov/memory-knowledge/Tasks/capture-and-jobs-fixes/plan.md` (560 lines)
Gate: doc-gap-closure-loop (internal readiness only — not interop/runtime-data).
Repo grounding root: `/Users/kamenkamenov/memory-knowledge`.

---

## Cycle 1 Assessment

### Section Inventory

| unit_id | section/title | unit type | implementation relevance |
| --- | --- | --- | --- |
| U-INTRO | Title + Mode/Source/Repo + Shared-infra flag (L1–L11) | intro | high (scoping, deploy target) |
| U-OBJ | Objective (L15–21) | heading | medium |
| U-SCOPE | In-scope / Out-of-scope (L25–36) | heading | high (boundary) |
| U-LD1 | LD1 A1 boundary (L42–46) | locked-decision | high |
| U-LD2 | LD2 case-insensitivity rule (L47–53) | locked-decision | high |
| U-LD3 | LD3 A2 notes-only path (L54–60) | locked-decision | high |
| U-LD4 | LD4 A2 no auto-register (L61–65) | locked-decision | high |
| U-LD5 | LD5 A3 hook script (L66–72) | locked-decision | high |
| U-LD6 | LD6 A4 Codex skill (L73–76) | locked-decision | high |
| U-LD7 | LD7 MK_SPARK_REPOS set (L77–83) | locked-decision | high |
| U-LD8 | LD8 A5 surfacing (L84–87) | locked-decision | high |
| U-LD9 | LD9 B1 cancel design (L88–95) | locked-decision | high |
| U-LD10 | LD10 cancelled excluded from re-enqueue (L96–99) | locked-decision | high |
| U-LD11 | LD11 B2 age threshold (L100–107) | locked-decision | high |
| U-LD12 | LD12 B3 inline insert (L108–111) | locked-decision | high |
| U-LD13 | LD13 no AI attribution (L112) | locked-decision | low |
| U-LD14 | LD14 deploy boundary (L113–116) | locked-decision | high |
| U-A1 | A1 repo-key normalization (L120–164) | item block | high |
| U-A2 | A2 notes-only revision path (L167–220) | item block | high |
| U-A3 | A3 capture→recall loop (L224–262) | item block | high |
| U-A4 | A4 Codex capture path (L266–294) | item block | high |
| U-A5 | A5 MK_SPARK_REPOS + surface (L298–328) | item block | high |
| U-B1 | B1 running→cancelled + cancel tool (L332–397) | item block | high |
| U-B2 | B2 age-gate reclaim (L401–431) | item block | high |
| U-B3 | B3 register_repository NOT-NULL (L435–484) | item block | high |
| U-SEQ | Sequencing & deploy plan (L488–510) | heading | high |
| U-ROLL | Rollback (L514–526) | heading | medium |
| U-TEST | Test plan (L530–552) | heading | high |
| U-OQ | Open questions (L556–560) | heading | low |

29 deterministic units. >200 lines → sibling audit file required (this file).

### Repo-Grounding Verification Log (cited `path:line` claims)

| claim (plan) | cited anchor | verification | result |
| --- | --- | --- | --- |
| `repo_key = Path(cwd).name` | auto_capture.py:48 | `nl` L48 `return Path(cwd).name or None` | OK |
| fail-open swallow | auto_capture.py:127 | L127 `except Exception:` → `return 0  # fail-open` | OK |
| ensure_repo_root_entity exact-match WHERE | repo_note.py:58-63 | L58-61 fetchrow `WHERE repository_key=$1`; raise L62-63 | OK (range fine) |
| no-revision raise | repo_note.py:66-73 | L66-69 rev fetch; L70-73 raise | OK |
| entities insert uses repo_revision_id | repo_note.py:79-90 | L81-90 INSERT catalog.entities with repo_revision_id | OK |
| run_author_note valid_from subquery exact-matches key | repo_note.py:169-174 | L169-173 subquery `WHERE repository_key=$1` | OK (off-by-one L174 is assignment) |
| run_deactivate_note exact-match `WHERE repository_key=$1` | repo_note.py:279-287 | L279-287 query is `WHERE e.entity_key=$1` (join on entities), NOT repository_key | **WRONG → GAP-001** |
| deactivate entity_key derived from repository_key | repo_note.py:275 | L275 `entity_key = learned_record_entity_key(repository_key, ...)` | OK |
| upsert_repo_revision exists, upserts on (repository_id, commit_sha) | entity_registrar.py:27-49 | L27-49 def; ON CONFLICT (repository_id, commit_sha) L39 | OK |
| repo_scoped_memory slice | retrieval.py:851-875 | L851-875 builds `context_bundle["repo_scoped_memory"]` | OK |
| guard allows running→{completed,failed} only | state_transition_guard.py:3-8 | L3-8 dict; running L5 `{"completed","failed"}` | OK |
| pending already has cancelled | (LD9/B1) | L4 `"pending": {"running","cancelled"}` | OK |
| retrying lacks cancelled | (B1 L344) | L7 `"retrying": {"running"}` | OK |
| manifest terminal-set branch | manifest_writer.py:68 | L68 `if state_code in ("completed","failed","dead_letter"):` | OK |
| _background_tasks not job-keyed | server.py:513 | L513 `_background_tasks: set[asyncio.Task] = set()` | OK |
| reclaim marks every running failed | dispatcher.py:62-82 | L62-82 `_reclaim_stale_running`; UPDATE WHERE state_code='running' L79 | OK |
| reclaim UPDATE region | dispatcher.py:73-81 | L73-81 the UPDATE | OK |
| dispatcher poll state_code IN (pending,retrying) | dispatcher.py:119-126 | L122 `WHERE state_code IN ('pending','retrying')` | OK (within range) |
| reclaim reads 'running' | dispatcher.py:79 | L79 `WHERE state_code = 'running'` | OK |
| sweep reads 'failed' | job_retry_manager.py:63,76 | L63 & L76 `WHERE state_code = 'failed'` | OK |
| sweep span | job_retry_manager.py:50-88 | L50-88 `sweep_failed_jobs` | OK |
| execute_job sets failed on error | job_worker.py:59-70 | L59-70 error branch → update_job_state "failed" | OK |
| reclaim setting | config.py:117 | L117 `reclaim_stale_running_jobs_on_start: bool = True` | OK |
| register_repository INSERT | server.py:6156-6169 | L6156-6169 INSERT `(repository_key,name,origin_url)` | OK |
| write guard present | server.py:6150 | L6150 `check_remote_write_guard(...,"register_repository")` | OK |
| mawf upsert mirror | admin/mawf.py:529-556 | L529 `_reference_id`; L531-547 INSERT; L546 RETURNING | OK (insert real span 531-547 incl. provider/owner/repo_name) |
| mawf INSERT cols | admin/mawf.py:533-546 | L533-546 SQL string | OK |
| _reference_id call site | admin/mawf.py:529 | L529 | OK |
| _reference_id def | admin/mawf.py | L171 `def _reference_id` | OK |
| mawf_repository_id+status_id NOT NULL no default | 016_mawf_contract.py:143-145 | L143-144 SET NOT NULL (L145 is unique index) | OK (145 is index, minor over-cite — see GAP-005) |
| REPOSITORY_STATUS/active seeded | 016:62-63 | L62 REPO_ACTIVE/active; L63 REPO_INACTIVE/inactive | partial (active=L62 only; L63 is inactive) → GAP-005 |
| reference trigger | 016:229 | L229 `_create_reference_trigger("catalog","repositories",...)`; name `trg_repositories_reference_types` (L242 pattern, L257) | OK |
| started_utc col | 001_initial_schema.py:286 | L286 `started_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()` (ops.job_manifests) | OK |
| started_utc set at creation not running | (LD11) | no jobs/*.py UPDATEs started_utc; dispatcher poll L118-119 sets state only | OK (fact true; rationale inverted → GAP-002) |
| hydrate_corpus calls corpus_query | hydrate_corpus.py:41 | L41 `call_tool("corpus_query",...)` | OK |
| additionalContext block | hydrate_corpus.py:66-71 | L66-72 lines list (header + context-only note) | OK |
| spark hardcodes 3 | directive_spark.py:28 | L28 `DEFAULT_REPOS=["taggable-api","fcsapi","taggable-server"]` | OK |
| spark reads MK_SPARK_REPOS | directive_spark.py:29 | L29 | OK |
| spark OUT path | directive_spark.OUT | L31 `OUT = ... / "spark-candidates.md"` | OK |
| weekly reads MK_SPARK_REPOS | weekly_review.py:23-24 | L23-24 | OK |
| weekly invokes spark._run | weekly_review.py:59-68 | L66 `await spark._run()` | OK |
| auto-capture.skill.md name | working-agreement/auto-capture.skill.md | L2 `name: auto-capture` | OK |
| Codex no session-end hook quote | SETUP-autocapture.md:28 | L28 exact quote | OK |
| no auto-capture in codex skills | ~/.codex/skills/ | dir exists, no auto-capture/ | OK |
| codex trusted projects | ~/.codex/config.toml:33-46 | L33,36,39,42,45 (5 projects named) | OK |
| check_job_status shape | server.py (mirror) | L883-905 `@mcp.tool()`+`@track_tool_metrics`+bind+get_job_by_id+WorkflowResult.model_dump_json | OK |
| get_job_by_id | manifest_reader.py | L10 def | OK |
| cancel_job absent today | server.py | rg: no cancel_job | OK (new) |
| check_remote_write_guard sig | guards.py | L13-18 `(settings, tool_name, *, is_destructive=False)->WorkflowResult|None` | OK |
| azure-push --tag | infra/azure-push.sh | L16,45,65 supports `--tag` | OK |
| audit source exists | Tasks/brain-alignment-audit/alignment-audit.md | file present | OK |
| validate_transition returns None | state_transition_guard.py:18-22 | returns None implicitly; raises InvalidStateTransition | OK |

### Coverage Matrix (lens × unit; abbreviated to gap-bearing + representative checked rows)

Lenses: DC=decision-completeness, RT=runtime/data-flow, SCH=schema/field/helper/tool semantics, EC=edge/failure/idempotency, VAL=validation/acceptance, RG=repo grounding, AB=approval boundaries, CON=contradictions, VW=vague wording, HO=planner handoff.

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |
| U-INTRO | RG/DC/AB | checked | repo/deploy claims grounded (azure-push.sh exists); SHARED additive framing consistent w/ items |
| U-SCOPE | DC/CON | checked | in/out lists match item set A1-A5,B1-B3; Tier C OUT explicit |
| U-LD1 | DC/RG | checked | repo_note.py boundary confirmed; auto_capture.py:48 left as-is rationale sound |
| U-LD2 | DC/EC | checked | ILIKE-on-lower exact, tie-break exact-case→lowest id deterministic |
| U-LD3 | SCH/RG | checked | sentinel revision via upsert_repo_revision confirmed reusable |
| U-LD4 | DC | checked | no auto-register; consistent with A2/B3 |
| U-LD5 | RT/RG | checked | hook mirrors hydrate_corpus.py; run_retrieval_workflow deployed |
| U-LD6 | RG | checked | skill file + codex dir state confirmed |
| U-LD7 | RG/DC | checked | set = audit 3 + codex 5 + 2; config.toml grounded; casing normalized |
| U-LD8 | DC/RT | checked | post-spark read + stderr summary; OUT exposed |
| U-LD9 | RT/SCH/RG | gap found | DB-flag cancel design sound; checkpoint-boundary claim under-specified → GAP-003 |
| U-LD10 | RG/CON | checked | grounded vs retry/reclaim; no outgoing edge |
| U-LD11 | EC/RG | gap found | started_utc fact OK; "more lenient" rationale inverted → GAP-002 |
| U-LD12 | SCH/RG | checked | inline insert mirrors mawf; reduced cols safe (provider/owner/repo_name nullable) |
| U-LD13 | AB | checked | constraint only |
| U-LD14 | DC/RG | checked | deploy boundary matches per-item file targets |
| U-A1 | RG/CON | gap found | deactivate "WHERE repository_key=$1" miscited → GAP-001 |
| U-A1 | EC/VAL | checked | case-collision warning, acceptance criteria testable |
| U-A2 | SCH/EC/VAL | checked | sentinel idempotent; branch_heads/retrieval_surfaces untouched documented |
| U-A3 | RT/EC/VAL | checked | reads prompt+cwd (corpus reads only prompt — distinction correct); fail-open |
| U-A3 | SCH | gap found | `inject-corpus.sh` cited as mirror but its content not summarized; settings.json merge under-specified → GAP-004 |
| U-A4 | RG/EC | checked | skill install path, front-matter, codex dir all grounded |
| U-A5 | RT/EC/VAL | checked | candidate-line parsing rule (`- ` prefix), none-this-run branch |
| U-B1 | RT/SCH/EC/VAL | gap found | checkpoint set vs "e.g. 3 lines" → GAP-003; rest grounded |
| U-B2 | EC/RG | gap found | GAP-002 rationale; acceptance criteria otherwise testable |
| U-B3 | SCH/RG/EC | gap found | seed-line cite imprecise → GAP-005; reduced cols safe |
| U-SEQ | DC/CON | checked | order B3→A1→A2→B1+B2; deploy phases consistent w/ LD14 |
| U-ROLL | EC | checked | per-file revert; --tag rollback grounded |
| U-TEST | VAL | checked | per-item assertions map to acceptance criteria |
| U-OQ | DC | checked | none blocking; one optional ops decision (P1-5) |

All 29 units assessed against all lenses (full matrix maintained in working notes; gap-bearing and representative rows shown; `not applicable` used for none — every lens applied).

### Cycle 1 Blocker Gap Ledger

| gap_id | severity | unit_id | lens | evidence | why blocker | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAP-001 | blocker | U-A1 | RG/CON | Plan L124 + L143-146 claim `run_deactivate_note` does "exact-match `WHERE repository_key = $1`" and must be changed to resolve canonical key for the lookup. Actual `repo_note.py:279-287` queries `WHERE e.entity_key = $1` (join through catalog.entities); it never filters by `repository_key`. The case bug enters via `entity_key = learned_record_entity_key(repository_key,...)` at L275, not via a repository_key WHERE clause. | The cited mechanism is factually wrong; an implementer following L143-146 ("call `_resolve_repository` first … return existing 'No repo note found' error else use `row['repository_key']`") would try to resolve a repo row that the current deactivate path does not even fetch, and would mis-locate the actual fix (entity_key derivation must use the canonical key). Mis-grounded change instruction → broken implementation. | Correct A1 Problem (L124) and the deactivate sub-bullet (L143-146): state that deactivate matches by `entity_key` (derived from `repository_key` at L275); the fix is to derive `entity_key` from the **canonical** key (resolve via `_resolve_repository` to get canonical `repository_key`, then `learned_record_entity_key(canonical_key, ...)`), keeping the existing entity_key-join lookup. | see Cycle 1 Edits | open |
| GAP-002 | blocker | U-LD11/U-B2 | EC | Plan L105-107 says using creation-time `started_utc` "only ever makes the gate *more* lenient, never less." Gate is `started_utc < NOW() - interval` (reclaim if older). Creation time is **earlier** than the true running-start, so `started_utc` is smaller → predicate flips true **sooner** → job reclaimed **more aggressively** (less lenient). The stated safety direction is inverted. | The locked-decision rationale asserts a safety property that is logically backwards. An implementer/reviewer relying on "only more lenient" could mis-size the threshold or mis-reason about resurrection safety. The conclusion (5 min default is safe) may still hold, but the justification is wrong and must be corrected to be decision-trustworthy. | Rewrite LD11 note: creation-time proxy makes the gate **stricter/earlier** (reclaims slightly sooner than a running-transition timestamp would), which is still safe because (a) for these jobs creation≈running-start and (b) the purpose is to avoid clobbering *recently created* jobs — an earlier `started_utc` only means a young job's clock starts at creation, still well within the 5-min grace. Remove the inverted "more lenient" claim. | see Cycle 1 Edits | open |
| GAP-003 | blocker | U-B1/U-LD9 | RT/SCH | Plan L364-365 lists the cooperative-abort insertion points as "the `_save_ckpt(...)` calls — e.g. lines 580, 916, and the summaries gate ~940". Actual `ingestion.py` has **9** `_save_ckpt` call sites (580, 916, 1088, 1107, 1145, 1170, 1187, 1346 plus the partial at 1088). "e.g." + 3 line numbers under-specifies which boundaries must get the cancel check; an implementer could patch only the 3 named and leave later phases uncancellable. | Without an explicit rule ("after **every** `_save_ckpt` checkpoint when `manifest_job_id is not None`"), coverage of the abort is ambiguous — a long job could pass the un-patched checkpoints and not abort, defeating B1's purpose. | Tighten B1: state the cancel re-check must wrap **every** `_save_ckpt` checkpoint boundary (all 9 sites, enumerated or described as "all `_save_ckpt(...)` call sites"), and recommend factoring the check into the `_save_ckpt`/`_save_ingestion_checkpoint` helper (single chokepoint) so all boundaries are covered by one edit. | see Cycle 1 Edits | open |
| GAP-004 | blocker | U-A3 | SCH/HO | Plan L241-243 says add `inject-repo-memory.sh` "mirror `inject-corpus.sh`" and register a "second `UserPromptSubmit` hook entry in `~/.claude/settings.json` (merge, don't replace)". The plan does not state `inject-corpus.sh`'s actual shape (interpreter/venv invocation) nor the concrete settings.json hook JSON form, so the implementer must reverse-engineer both. The mirror source is named but its load-bearing content is not captured in the doc. | A3 is a from-scratch local artifact whose correctness depends on matching the existing wrapper's Python invocation and the settings.json hook schema. "Mirror X" without the X contract forces the implementer to infer it → not self-sufficient for one-shot. | Add to A3: the exact `inject-corpus.sh` invocation pattern (the repo Python it calls) as the template to copy, and the concrete `UserPromptSubmit` hook entry JSON shape to add (command pointing at `inject-repo-memory.sh`), with the explicit "append to the existing hooks array" instruction. Ground against `inject-corpus.sh` and `SETUP-claude.md`. | see Cycle 1 Edits | open |
| GAP-005 | blocker | U-B3 | RG | Plan L449 says `REPOSITORY_STATUS/active` "is seeded by migration 016 lines 62-63"; actual L62 = `REPO_ACTIVE`/`active`, L63 = `REPO_INACTIVE`/`inactive` — the `active` value is L62 only. Plan L108-111/L143 also cite "016:143-145" for the two NOT-NULL alters, but L145 is the unique index (NOT-NULLs are L143-144). | Both are cited-claim inaccuracies (over-broad line ranges) in a repo-grounding-critical decision (B3 keystone). A reader verifying the seed/constraint would find the cited line says something else, eroding trust and risking a wrong fix if the reader anchors on the wrong line. | Correct the cites: seed at `016:62`; NOT-NULL alters at `016:143-144`. | see Cycle 1 Edits | open |

No cleanup-only items rise above noise this cycle (minor off-by-one ranges that still point at the right statement, e.g. repo_note.py:169-174, are within tolerance and not separately ledgered).

### Cycle 1 Gap-To-Fix Map

| gap_id | target unit | exact decision to lock | edit summary | validation check |
| --- | --- | --- | --- | --- |
| GAP-001 | U-A1 (L124, L143-146) | Deactivate matches by `entity_key` (join), fix = derive entity_key from canonical key | Rewrite Problem clause + deactivate bullet | `rg -n "entity_key" plan.md` shows corrected mechanism; no "WHERE repository_key" attributed to deactivate |
| GAP-002 | U-LD11 (L105-107) | Creation-time proxy = stricter/earlier, still safe; drop "more lenient" | Replace inverted note | `rg -n "lenient" plan.md` returns corrected text |
| GAP-003 | U-B1 (L363-369) | Cancel re-check at **every** `_save_ckpt` site; prefer helper chokepoint | Tighten insertion-point spec | `rg -n "_save_ckpt|every checkpoint" plan.md` |
| GAP-004 | U-A3 (L241-243) | Provide inject wrapper template + concrete settings.json hook entry | Add wrapper invocation + hook JSON | `rg -n "settings.json|inject-repo-memory" plan.md` |
| GAP-005 | U-B3 (L449, L108-111) | Cite `016:62` (active) and `016:143-144` (NOT NULL) | Correct line cites | `rg -n "016" plan.md` shows corrected anchors |

---

## Cycle 1 Plan

Apply the five-row Gap-To-Fix Map above by editing `plan.md` only (no runtime code). Each gap maps to a
specific section edit; validation = re-grep + re-read the edited clause against the verified repo fact.

## Cycle 1 Edits

| gap_id | file/section | edit | post-edit line(s) |
| --- | --- | --- | --- |
| GAP-001 | plan.md A1 Problem + deactivate bullet | Split Problem into authoring (repository_key WHERE) vs deactivation (entity_key derivation + entities-join lookup); rewrote deactivate fix to canonicalize before deriving entity_key | L122-136 (Problem), L159-166 (fix bullet) |
| GAP-002 | plan.md LD11 | Replaced inverted "more lenient" claim with correct "stricter/earlier, still safe" reasoning; added verification that nothing UPDATEs started_utc | L104-112 |
| GAP-003 | plan.md B1 cooperative-abort | Stated all 8 `_save_ckpt` sites (enumerated), locked single-chokepoint edit inside `_save_ingestion_checkpoint` (ingestion.py:165); corrected count 9→8 | L405-411 |
| GAP-004 | plan.md A3 wrapper/hook | Added concrete `inject-repo-memory.sh` body (copy of inject-corpus.sh:1-18) + concrete settings.json hook entry JSON + append-to-array instruction (grounded SETUP-claude.md:21-30) | L261-284 |
| GAP-005 | plan.md B3 Problem + status bullet | Corrected cites: NOT-NULL at 016:143 & :144 (145 is index); active seed at 016:62 (63 is inactive) | L488-489, L499 |

## Cycle 1 Validation

Commands run (cwd `/Users/kamenkamenov/memory-knowledge`):
- `rg -n "lenient" plan.md` → only L109 corrected text ("never *more* lenient" within stricter-direction explanation). PASS.
- `rg -n "WHERE e.entity_key" plan.md` → L135, L161, L165 (deactivate mechanism now correct). PASS.
- `rg -n "await _save_ckpt" src/.../ingestion.py | wc -l` → 8 (matches corrected plan text). PASS.
- `rg -n "inject-repo-memory.sh" plan.md` → L261, L282, L547, L574 (wrapper + hook JSON present). PASS.
- `rg -n "016_mawf_contract.py:143" plan.md` → L488 corrected; L499 seed cite corrected. PASS.
- `git diff --check` → N/A (env reports not a git repo). SKIPPED with reason.
- Stale-word scan `rg -n "TBD|TODO|FIXME|\bmaybe\b|not locked|needs further|or equivalent"` → only matches the
  heading title "resolve all could/maybe" (L40, intentional) — no unresolved decisions. PASS.

Post-edit re-grounding (re-read edited claims vs repo):
- repo_note.py:279-287 confirmed `WHERE e.entity_key = $1` (not repository_key) — GAP-001 edit now matches code.
- jobs/*.py confirmed no UPDATE of started_utc — GAP-002 edit's "stricter/earlier" reasoning is sound.
- ingestion.py 8 `await _save_ckpt` sites confirmed — GAP-003 count correct.
- inject-corpus.sh:1-18 + SETUP-claude.md:21-30 confirmed as templates — GAP-004 body/JSON faithful.
- 016:62 = REPO_ACTIVE/active, :63 = inactive; :143-144 NOT NULL, :145 unique index — GAP-005 cites correct.

### Cycle 1 Post-Edit New-Gap Pass

| changed unit | checked against | result | new gap id |
| --- | --- | --- | --- |
| A1 Problem/fix (GAP-001) | A2 (which threads canonical key via re-query), LD1, LD2 | consistent — A2 relies on A1 resolution; no new contradiction | none |
| LD11 (GAP-002) | B2 acceptance criteria (L417-426), config.py default | consistent — acceptance criteria unchanged & still valid; reasoning now matches predicate | none |
| B1 abort (GAP-003) | LD9, acceptance criteria, rollback (revert 3 files) | consistent — chokepoint is still within ingestion.py (one of the "three files"); JobCancelled sentinel is new but local | none |
| A3 wrapper/hook (GAP-004) | Sequencing (Phase 2 local), Rollback (remove hook) | consistent — still local-only, no deploy; rollback already covers un-register | none |
| B3 cites (GAP-005) | LD12, acceptance criteria | consistent — cite-only change, mechanism unchanged | none |

No new blocker gaps introduced by the edits.

---

## Cycle 2 Assessment

Fresh full-document pass over the **edited** plan.md. Carried-forward prior gaps: GAP-001..GAP-005 all
re-checked CLOSED (see closure evidence below). New blocker found: GAP-006.

### Carry-forward (prior gaps)

| gap_id | status | closure evidence |
| --- | --- | --- |
| GAP-001 | closed | A1 Problem now distinguishes authoring (repository_key WHERE) vs deactivation (entity_key derivation + entities-join, `WHERE e.entity_key=$1`); matches repo_note.py:275,279-287. plan.md L128-141, L158-166. |
| GAP-002 | closed | LD11 now states creation-time proxy is stricter/earlier (never more lenient), still safe; matches predicate direction. plan.md L104-112. |
| GAP-003 | closed | B1 abort now enumerates all 8 `await _save_ckpt` sites + single-chokepoint lock in `_save_ingestion_checkpoint` (ingestion.py:165). Count verified =8. plan.md L405-411. |
| GAP-004 | closed | A3 now includes concrete wrapper body (copy of inject-corpus.sh:1-18) + concrete settings.json hook JSON + append-to-array. plan.md L261-284. |
| GAP-005 | closed | B3 cites corrected: NOT NULL 016:143 & :144 (145=index); active seed 016:62 (63=inactive). plan.md L488-489, L499. |

### Cycle 2 Blocker Gap Ledger (new)

| gap_id | severity | unit_id | lens | evidence | why blocker | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAP-006 | blocker | U-A1 | CON/RT/SCH | A1 "Exact change" only modifies `ensure_repo_root_entity`, the `valid_from` subquery, and `run_deactivate_note`. But `run_author_note` independently derives the note's own `entity_key` at `repo_note.py:177` from the **raw** `repository_key` arg, and passes the **raw** `repository_key` to the Qdrant payload at `repo_note.py:203`. `learned_record_entity_key` is a pure `uuid5(f"{repo_key}:…")` with NO case-folding (`identity/entity_key.py:30-31`), so `FCSAPI`≠`fcsapi`. As written, the plan's A1 acceptance criteria — (a) `FcSaPi`/`fcsapi` upsert to the SAME learned_records row/entity_key (L171-173), and (b) the note is retrievable via `run_retrieval_workflow("fcsapi")` because the Qdrant payload is canonical (L169-170) — CANNOT be met, and authoring's entity_key would differ from the now-canonicalized deactivate entity_key (GAP-001 fix), breaking deactivate too. | The item fails its own stated, testable acceptance criteria and is internally contradictory (deactivate canonicalizes, authoring does not). An implementer following the Exact-change literally produces a build that does not satisfy A1. | Extend A1 Exact-change: `ensure_repo_root_entity` returns the canonical key; `run_author_note` binds `canonical_key` and uses it for the note entity_key (L177), the Qdrant payload (L203), and the valid_from resolution; note `repository_root_entity_key` is likewise case-sensitive but already fed the canonical key. | see Cycle 2 Edits | open |

### Cycle 2 full-lens spot re-check (representative; all 29 units re-swept)

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |
| U-A1 | CON/RT/SCH | gap found | GAP-006 (authoring path not canonicalized) |
| U-A1 | RG | checked | identity/entity_key.py:30-31,34-40 confirm no case-fold |
| U-A2 | SCH/EC | checked | sentinel revision via upsert_repo_revision; idempotent ON CONFLICT; uses A1 resolution (now fully canonical after GAP-006 fix) |
| U-A3 | RT/SCH/HO | checked | wrapper body + hook JSON now self-sufficient; fail-open contract intact |
| U-A4 | RG/EC | checked | grounded; unchanged |
| U-A5 | RT/VAL | checked | candidate parsing + none-branch; unchanged |
| U-B1 | RT/SCH/EC | checked | chokepoint lock removes ambiguity; cancel_job idempotency + guard grounded |
| U-B2 | EC/RG | checked | rationale corrected; predicate + getattr default sound |
| U-B3 | SCH/RG | checked | cites corrected; reduced-col INSERT safe (provider/owner/repo_name nullable, 016:124-126) |
| U-SEQ/U-ROLL/U-TEST/U-OQ | DC/CON/VAL | checked | sequencing order intact; rollback per-file; test plan maps to acceptance; no blocking OQ |
| U-INTRO/U-OBJ/U-SCOPE/U-LD1..LD14 | all | checked | no new contradictions; LD-level decisions consistent with item bodies post-edit |

### Cycle 2 Gap-To-Fix Map

| gap_id | target unit | exact decision to lock | edit summary | validation check |
| --- | --- | --- | --- | --- |
| GAP-006 | U-A1 run_author_note bullet | Thread canonical key through entity_key (L177), Qdrant payload (L203), valid_from | Rewrite the run_author_note sub-bullet to canonicalize the full authoring path; ground entity_key.py:30-31,34-40 | `rg -n "canonical_key|entity_key.py:30" plan.md` |

## Cycle 2 Plan

Edit plan.md A1 Exact-change `run_author_note` bullet only (doc edit; no runtime code). Lock canonical-key
threading through the entire authoring path.

## Cycle 2 Edits

| gap_id | section | edit | post-edit lines |
| --- | --- | --- | --- |
| GAP-006 | A1 Exact change → run_author_note | Replaced the valid_from-only bullet with a full canonical-key threading spec covering valid_from, note entity_key (L177), Qdrant payload (L203), and the root entity_key, grounded in identity/entity_key.py:30-31,34-40 | plan.md L153-172 |

## Cycle 2 Validation

- `rg -n "canonical_key" plan.md` → present in the A1 run_author_note bullet (multiple uses). PASS.
- `rg -n "identity/entity_key.py:30-31|entity_key.py:34-40" plan.md` → cited. PASS.
- Re-ground: `nl -ba src/memory_knowledge/identity/entity_key.py` L30-31 = `learned_record_entity_key` pure uuid5 no case-fold; L34-40 = `repository_root_entity_key` pure uuid5. Matches edit. PASS.
- Re-ground: `repo_note.py:177` raw `repository_key` in entity_key; `repo_note.py:203` raw `repository_key` in Qdrant payload — confirms the edit targets the right lines. PASS.
- Consistency: deactivate fix (GAP-001) uses `learned_record_entity_key(row["repository_key"],…)` = canonical; authoring now uses `canonical_key` = canonical → symmetric. PASS.
- `git diff --check` → N/A (not a git repo). SKIPPED.

### Cycle 2 Post-Edit New-Gap Pass

| changed unit | checked against | result | new gap id |
| --- | --- | --- | --- |
| A1 run_author_note bullet | A1 acceptance criteria (same-row upsert, canonical retrieval) | now satisfiable | none |
| A1 run_author_note bullet | A2 (relies on canonical resolution), deactivate (GAP-001) | symmetric; both use canonical key | none |
| A1 run_author_note bullet | ensure_repo_root_entity return widening (2→3 tuple) | self-consistent; A2 also calls ensure_repo_root_entity — verify A2 not broken by tuple widening (A2 calls it via author_repo_note default path; A2's text references the function's behavior, not its return arity) → no contradiction | none |

No new blocker gaps from the Cycle 2 edit.

---

## Cycle 3 Assessment

Fresh full-document, **no-edit** pass over plan.md (626 lines) — the convergence-qualifying cycle.
All prior gaps carried forward; new-blocker hunt across all 29 units and all lenses.

### Carry-forward

| gap_id | status | note |
| --- | --- | --- |
| GAP-001 | closed | (Cycle 1) deactivate mechanism corrected |
| GAP-002 | closed | (Cycle 1) B2 rationale corrected |
| GAP-003 | closed | (Cycle 1) 8-site chokepoint locked |
| GAP-004 | closed | (Cycle 1) wrapper + hook JSON provided |
| GAP-005 | closed | (Cycle 1) B3 cites corrected |
| GAP-006 | closed | (Cycle 2) authoring path canonical-key threading added; verified single caller of ensure_repo_root_entity (repo_note.py:164) is the one the fix widens; entity_key.py:30-31,34-40 confirm no case-fold |

### Cycle 3 Coverage Matrix (every unit × every lens)

Legend: C=checked, NA=not-applicable (with reason). Lenses: DC, RT, SCH, EC, VAL, RG, AB, CON, VW, HO.

| unit_id | DC | RT | SCH | EC | VAL | RG | AB | CON | VW | HO |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| U-INTRO | C | C | C | NA(scope) | NA(scope) | C(azure-push) | C([SHARED] additive) | C | C | C |
| U-OBJ | C | C | NA | NA | NA | NA | NA | C | C | C |
| U-SCOPE | C | NA | NA | NA | NA | NA | C(Tier C OUT) | C | C | C |
| U-LD1 | C | C | C | NA | NA | C(repo_note boundary) | C | C | C | C |
| U-LD2 | C | NA | C | C(tie-break) | NA | C(ILIKE-lower) | NA | C | C | C |
| U-LD3 | C | C | C | C(idempotent) | NA | C(upsert_repo_revision) | NA | C | C | C |
| U-LD4 | C | NA | NA | C(repo-absent) | NA | C | C(deliberate reg) | C | C | C |
| U-LD5 | C | C | C | C(fail-open) | NA | C(hydrate_corpus) | C(opt-in) | C | C | C |
| U-LD6 | C | NA | C | C | NA | C(skill file) | C(local) | C | C | C |
| U-LD7 | C | NA | NA | C(unreg fail-open) | NA | C(config.toml) | NA | C | C | C |
| U-LD8 | C | C | C | C(none-branch) | NA | C(OUT attr) | NA | C | C | C |
| U-LD9 | C | C | C | C | NA | C(server.py:513) | C(write) | C | C | C |
| U-LD10 | C | C | C | C(terminal) | NA | C(retry/reclaim) | NA | C | C | C |
| U-LD11 | C | C | C | C | NA | C(001:286;no UPDATE) | NA | C | C | C |
| U-LD12 | C | C | C | C | NA | C(mawf mirror) | C(non-destructive) | C | C | C |
| U-LD13 | C | NA | NA | NA | NA | NA | C(constraint) | C | C | NA |
| U-LD14 | C | NA | NA | NA | NA | C(per-file) | C(deploy) | C | C | C |
| U-A1 | C | C | C | C(collision) | C | C(entity_key.py;repo_note) | C | C | C | C |
| U-A2 | C | C | C | C(race) | C | C(repo_revisions schema 001:48-56) | C | C | C | C |
| U-A3 | C | C | C | C(timeout) | C | C(inject-corpus;SETUP) | C(opt-in) | C | C | C |
| U-A4 | C | NA | C | C(unreg) | C | C(skill/codex dir) | C(local advisory) | C | C | C |
| U-A5 | C | C | C | C(write-fail) | C | C(spark/weekly) | NA | C | C | C |
| U-B1 | C | C | C | C(race;mid-phase) | C | C(guard;worker;tool) | C(write-guard) | C | C | C |
| U-B2 | C | C | C | C(skew;young) | C | C(dispatcher;config) | NA | C | C | C |
| U-B3 | C | C | C | C(pre-016;mawf) | C | C(server;mawf;016) | C(write-guard) | C | C | C |
| U-SEQ | C | NA | NA | NA | NA | C(deploy) | C(no push) | C | C | C |
| U-ROLL | C | NA | C | C(revert) | NA | C(--tag) | NA | C | C | C |
| U-TEST | NA | NA | NA | C | C | C(test paths) | NA | C | C | C |
| U-OQ | C | NA | NA | NA | NA | NA | C(optional ops) | C | C | C |

Every unit assessed against every lens; `NA` rows carry concrete reasons inline.

### Cycle 3 Blocker Gap Ledger

No new blocker gaps found. Spot-checks performed this cycle:
- A2 reuse of `upsert_repo_revision`: signature `(pool, repository_id, commit_sha, branch_name, parent_sha=None)` matches the planned call; sentinel `__note_anchor__` (15 chars) and `__notes__` (9 chars) fit `commit_sha VARCHAR(40)` / `branch_name VARCHAR(255)` (001:51-52). No length/NOT-NULL blocker.
- repo_revisions NOT-NULL set = {repository_id, commit_sha, created_utc(defaulted)} (001:48-56) — A2 L221 accurate.
- ensure_repo_root_entity has exactly ONE caller (repo_note.py:164), which the GAP-006 fix widens — tuple widening introduces no orphaned 2-unpack.
- branch_heads/retrieval_surfaces NOT-NULL repo_revision_id confirmed (001:63, 001:72+) and correctly left untouched.
- Final stale-word scan (`TBD|TODO|FIXME|maybe|not locked|needs further|or equivalent|could`, excluding the heading) → zero hits.

## Final Convergence Check

Cycle 3 is a no-edit full-document assessment that found zero open blocker gaps. All six prior gaps
(GAP-001..GAP-006) are closed with grounded evidence. Hard-stop rule satisfied: the edit cycles (1 and 2)
did not declare convergence; convergence is claimed only here in Cycle 3, which made no document edits.

### Final Gap Ledger Status

| gap_id | status |
| --- | --- |
| GAP-001 | closed |
| GAP-002 | closed |
| GAP-003 | closed |
| GAP-004 | closed |
| GAP-005 | closed |
| GAP-006 | closed |

Open blockers: 0.

### Final Readiness Proof

| category | status | evidence |
| --- | --- | --- |
| runtime entry points & data flow | ready | A1 boundary in repo_note.py; A3 hook→run_retrieval_workflow; B1 cancel_job→update_job_state→worker chokepoint; all entry points named + grounded |
| schema/fields/interfaces/helpers/artifacts | ready | repo_revisions/entities/repositories NOT-NULL sets verified (001, 016); helpers upsert_repo_revision, _reference_id, learned_record_entity_key, check_remote_write_guard grounded |
| edge cases & failure behavior | ready | case-collision, concurrent-first-note race, cancel-vs-finish race, mid-phase cancel, clock skew, missing reference value, unregistered repos — all addressed per item |
| resume behavior & idempotency | ready | cancelled is terminal/no-outgoing-edge; ON CONFLICT idempotency for revision + register; age-gated reclaim won't resurrect cancelled; sentinel revision inert |
| validation/tests/acceptance | ready | per-item testable acceptance criteria + Test plan mapping (test_repo_note, test_dispatcher_reclaim, test_config, guard/register/A5 tests); A1 same-row + canonical-retrieval criteria now satisfiable post-GAP-006 |
| repo grounding | ready | ~55 cited path:line claims verified against repo; 6 corrected; remaining within tolerance |
| approval boundaries | ready | write-guard on cancel_job/register_repository; no-push/no-deploy until Kamen asks; local-only vs deploy split locked (LD14) |
| out-of-scope boundaries | ready | Tier C (X-2/3/4/6) + P1-5 explicitly OUT; branch_heads/retrieval_surfaces explicitly not touched |

### Scope of Convergence (honest)

This convergence establishes **internal document readiness only**: the plan is self-sufficient,
decision-complete, internally consistent, and every cited `path:line` claim was verified against the real
`memory-knowledge` repo (6 miscited/contradictory claims corrected). It does **not** establish:
interop with sibling/already-shipped features (e.g. MAWF-owned repo rows, the harness P2 consumer);
runtime/data reality (whether retrieval actually surfaces a note end-to-end in live Qdrant/PG);
or full requirement satisfaction against the live cross-service chain. Next gates before implementation:
`requirements-coverage-gap-loop` then `requirements-satisfaction-gap-loop`.
