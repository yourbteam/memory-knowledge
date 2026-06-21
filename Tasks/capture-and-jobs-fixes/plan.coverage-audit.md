# Coverage Audit — Capture & Jobs Fixes plan

**Target document:** `Tasks/capture-and-jobs-fixes/plan.md`
**Loop:** `requirements-coverage-gap-loop` (breadth — presence/completeness; NOT depth).
**Grounding repo:** `/Users/kamenkamenov/memory-knowledge` (claims verified against real source — see Cycle 1 Validation).
**Sibling sources for elicitation:** `Tasks/brain-alignment-audit/alignment-audit.md` (§2 Tier A = P1-1..P1-7; §3/§4 Tier B = X-1, X-5).
**Started:** 2026-06-21.

> Convergence here means **every requirement is addressed somewhere or explicitly scoped-out with a testable criterion** (breadth). It does NOT prove each addressing actually holds end-to-end — that is the `requirements-satisfaction-gap-loop` (depth) pass that follows.

---

## Requirement Inventory

Built from three sources: (1) explicit plan/audit items; (2) implied/derived requirements entailed by the goal; (3) non-functional/cross-cutting and negative/boundary requirements (including those the user named explicitly in the loop brief).

| req_id | requirement | type | source (quoted) |
| --- | --- | --- | --- |
| **A1** | Capture repo-key normalization: case-insensitive resolution at the brain boundary so capture works on capitalized dirs (`FCSAPI`→`fcsapi`) | explicit | audit P1-1 "Capture silently no-ops on case-mismatched repos"; plan §A1 |
| **A2** | Notes-only "register a revision" path: anchor a note without full source ingestion (keystone) | explicit | audit P1-2 "the only way to enable it today is full source ingestion"; plan §A2 |
| **A3** | Close the capture→recall loop: repo-scoped notes resurface automatically per prompt | explicit | audit P1-3 "written but rarely read"; plan §A3 |
| **A4** | Codex capture path: install `auto-capture` skill into `~/.codex/skills` | explicit | audit P1-4 "No auto-capture in Codex at all"; plan §A4 |
| **A5** | `MK_SPARK_REPOS` real set + surface `spark-candidates.md` in weekly output | explicit | audit P1-6, P1-7; plan §A5 |
| **B1** | Make jobs stoppable: `running→cancelled` transition + cancel tool; cancelled excluded from re-enqueue/reclaim | explicit | audit X-1 "no running-job cancel … this is the incident"; plan §B1 |
| **B2** | Age-gate `reclaim_stale_running_jobs_on_start` so a fresh restart doesn't clobber a just-started job | explicit | audit X-1/B2 "threshold-less reclaim-on-start"; plan §B2 |
| **B3** | Fix `register_repository` NOT-NULL columns (`mawf_repository_id`, `status_id`) | explicit | audit X-5 "register_repository is broken … confirmed live"; plan §B3 |
| **N1** | Write→read symmetry: anything written must be readable by the same key | implied | "if it writes data, something reads it" (loop brief) |
| **N2** | Idempotency: repeated calls (author, cancel, register, revision-create) converge, no duplicate rows | implied | loop brief "idempotency" |
| **N3** | Non-breaking / additive on shared infra: no existing call site changes meaning | non-functional | plan shared-infra header lines 7-11 "[SHARED] … additive / non-breaking" |
| **N4** | Shared-infra safety: a change must not destabilize the co-tenant harness (P2) or be destabilized by it | non-functional | plan lines 7-11; audit §3 collisions |
| **N5** | Security / secrets: no credentials in files; secrets via env | non-functional | repo CLAUDE.md Guard Rails; loop brief "security/secrets" |
| **N6** | Backward-compat: callers of changed function signatures still work | non-functional | loop brief "backward-compat"; N3 |
| **N7** | Remote-write guard: every write tool honors `check_remote_write_guard` | non-functional | loop brief "the remote-write guard"; plan §B1/§B3 |
| **N8** | User-facing error handling: capture/recall failures never break the host session (fail-open) | implied | loop brief "if user-facing, errors handled"; plan fail-open contracts |
| **N9** | Tests: each code change has a verification/test | non-functional | loop brief "tests"; plan Test plan |
| **N10** | Deploy: each change has a deploy boundary stated | non-functional | loop brief "deploy"; plan Locked Decision 14 + Sequencing |
| **N11** | Observability: state changes / anomalies are logged | non-functional | loop brief implied; plan log lines |
| **G1** | Empty/missing repo (repo row absent in `catalog.repositories`) | negative | loop brief "empty/missing repo" |
| **G2** | Repo already has a real (ingested) revision when a note is authored | negative | loop brief "repo already has a real revision" |
| **G3** | Concurrent runs (first-note race; concurrent cancels; restart racing a fresh job) | negative | loop brief "concurrent runs" |
| **G4** | Case-collision of two repos differing only by case | negative | loop brief "case-collision of two repos differing only by case" |
| **G5** | Cancel of an already-finished (terminal) job | negative | loop brief "cancel of an already-finished job" |
| **G6** | Reclaim of a legitimately-running job | negative | loop brief "reclaim of a legitimately-running job" |
| **S1** | Tier-C exclusions (X-2 secrets RBAC, X-3 namespacing, X-4 own compute, X-6 ACR/storage split) explicitly out-of-scope with rationale | scope | plan In/Out-of-scope lines 32-36 |
| **S2** | P1-5 (run weekly job once) explicitly out-of-scope (operational, not code) | scope | plan lines 33-34, Open Questions lines 624-626 |

---

## Obligation Decomposition

Each requirement broken into the obligations coverage is assessed against.

| req_id | obligation | source/why entailed |
| --- | --- | --- |
| A1.a | Canonicalize on the **authoring** path (repo-row lookup) | audit P1-1 authoring break |
| A1.b | Canonicalize on the **deactivation** path (entity_key derivation) | plan §A1 "fix must canonicalize on both paths" |
| A1.c | Stored Qdrant payload `repository_key` is canonical (read-back) | plan line 167-170 read-back-critical |
| A1.d | Note's own `entity_key` derived from canonical key (same-row upsert) | plan line 162-166 |
| A1.e | `valid_from_revision_id` resolved via canonical key | plan line 158-159 |
| A1.f | Fix at brain boundary so all callers (Stop-hook, Codex skill, manual, deactivate) fixed at once | Locked Decision 1 |
| A2.a | Create synthetic note-anchor revision on demand (no MCP tool, no ingestion) | Locked Decision 3 |
| A2.b | Zero files/chunks/source-embeddings created | plan acceptance line 237-239 |
| A2.c | Opt-in per call (`auto_create_revision`), default True for authoring; deactivate never creates | Locked Decision 3 |
| A2.d | Do NOT auto-register an absent repo row | Locked Decision 4 |
| A2.e | `branch_heads`/`retrieval_surfaces` not touched | plan lines 232-234 |
| A3.a | Per-prompt hook calls `run_retrieval_workflow` (repo-scoped) | audit P1-3 |
| A3.b | Opt-in (`MK_REPO_HYDRATE=1`); fail-open (error/timeout → nothing, exit 0) | Locked Decision 5 |
| A3.c | Registered as a second `UserPromptSubmit` hook (append, not replace) | plan lines 293-301 |
| A3.d | Reads repo-scoped slice (`repo_scoped_memory`); empty → prints nothing | plan lines 302-304 |
| A4.a | Skill file installed at `~/.codex/skills/auto-capture/SKILL.md` | plan §A4 |
| A4.b | Docs updated (SETUP-codex.md, SETUP-autocapture.md) | plan §A4 |
| A5.a | `MK_SPARK_REPOS` set to the locked 8-repo union | Locked Decision 7 |
| A5.b | Surface candidate count + path in weekly stderr | Locked Decision 8 |
| A5.c | No-candidates / missing-file → "none this run" (no crash) | plan acceptance line 377 |
| B1.a | `running→cancelled` (+ pending/retrying→cancelled) transition added; cancelled terminal | Locked Decision 9-10 |
| B1.b | New `cancel_job` MCP tool (idempotent on terminal; honors write guard) | plan lines 411-420 |
| B1.c | Cooperative abort in the **worker** at every checkpoint boundary | plan lines 421-439 |
| B1.d | `cancelled` excluded from dispatcher poll, retry sweep, reclaim | Locked Decision 10; plan acceptance 446-447 |
| B1.e | `update_job_state` stamps `completed_utc` on cancel | plan lines 406-410 |
| B1.f | `execute_job` skips failed/completed transition when state already cancelled | plan lines 434-439 |
| B2.a | New setting `reclaim_running_min_age_seconds=300` (additive, defaulted) | plan lines 474 |
| B2.b | Age predicate added to reclaim UPDATE (`started_utc < NOW() - interval`) | plan lines 476-480 |
| B2.c | `started_utc`-as-creation-time proxy limitation documented & shown conservative | Locked Decision 11 |
| B3.a | INSERT supplies `mawf_repository_id` + `status_id` | plan §B3 |
| B3.b | `status_id` resolved via `_reference_id("REPOSITORY_STATUS","active")` | plan lines 511-515 |
| B3.c | ON CONFLICT update preserves MAWF-owned columns | plan lines 527-529 |
| B3.d | `created` flag (xmax) preserved | plan acceptance line 538 |
| N1–N11 | (one obligation each, as inventoried) | — |
| G1–G6 | (one obligation each, as inventoried) | — |
| S1,S2 | explicit out-of-scope statement + rationale | — |

---

## Cycle 1 Assessment

Lenses applied across all requirements/obligations. Evidence cited as `plan.md:line` / quoted audit source / `repo path:line` from the grounding pass.

### Coverage Matrix

| req_id.obligation | status | addressed where / out-of-scope rationale |
| --- | --- | --- |
| A1.a | addressed | plan.md:148-149 `_resolve_repository` replaces exact-match (repo `repo_note.py:58-63` confirmed) |
| A1.b | addressed | plan.md:174-182 canonicalize before deriving entity_key in `run_deactivate_note` |
| A1.c | addressed | plan.md:167-170 `repository_key=canonical_key` in Qdrant payload |
| A1.d | addressed | plan.md:162-166 `learned_record_entity_key(canonical_key,…)` (repo `entity_key.py:30-31` confirmed no case-fold) |
| A1.e | addressed | plan.md:158-159 resolve via canonical id |
| A1.f | addressed | plan.md:42-46 Locked Decision 1 (boundary in `repo_note.py`) |
| A2.a | addressed | plan.md:214-223 reuse `upsert_repo_revision` (repo `entity_registrar.py:27-49` confirmed) |
| A2.b | addressed | plan.md:237-239 acceptance: zero files/chunks/embeddings |
| A2.c | addressed | plan.md:214,229-230 default True; deactivate read-only |
| A2.d | addressed | plan.md:62-65 Locked Decision 4 |
| A2.e | addressed | plan.md:232-234 explicitly not touched + rationale |
| A3.a | addressed | plan.md:270 calls `run_retrieval_workflow` |
| A3.b | addressed | plan.md:274-276 opt-in + fail-open |
| A3.c | addressed | plan.md:293-301 append to array (repo `~/.claude/settings.json` array confirmed) |
| A3.d | addressed | plan.md:302-304 reads `repo_scoped_memory` (repo `retrieval.py:851-875` confirmed) |
| A4.a | addressed | plan.md:332-333 install SKILL.md (repo: no `auto-capture/` in codex skills confirmed) |
| A4.b | addressed | plan.md:336-339 doc updates |
| A5.a | addressed | plan.md:77-83 Locked Decision 7 + plan.md:363-367 export in `weekly-review.sh` |
| A5.b | addressed | plan.md:368-372 candidate-surfacing print |
| A5.c | addressed | plan.md:377 "none this run" |
| B1.a | addressed | plan.md:398-405 guard transitions (repo `state_transition_guard.py:3-8` confirmed) |
| B1.b | addressed | plan.md:411-420 cancel_job tool |
| B1.c | **PARTIAL** | plan.md:421-439 abort added **only inside ingestion's** `_save_ingestion_checkpoint`; repo confirms 4 dispatchable job types (`ingestion`,`repair`,`integrity_audit`,`compaction` — `server.py:6584-6587`). Other 3 have no cooperative abort. See CGAP-001. |
| B1.d | addressed | plan.md:446-447 (repo `dispatcher.py:122`, `job_retry_manager.py:63,76`, `dispatcher.py:79` confirmed) |
| B1.e | addressed | plan.md:406-410 |
| B1.f | addressed | plan.md:434-439 execute_job skip (repo `job_worker.py:59-89` confirmed) |
| B2.a | addressed | plan.md:474 (repo `config.py:117` confirmed; no existing setting) |
| B2.b | addressed | plan.md:476-480 (repo `dispatcher.py:73-81` confirmed) |
| B2.c | addressed | plan.md:106-113 Locked Decision 11 (repo `001_initial_schema.py:286` + never-UPDATEd confirmed) |
| B3.a | addressed | plan.md:516-526 |
| B3.b | addressed | plan.md:511-515 (repo `admin/mawf.py:529`, migration 016:62 confirmed) |
| B3.c | addressed | plan.md:527-529 |
| B3.d | addressed | plan.md:538 |
| N1 | addressed | A1.c/A1.d collapse write+read to one canonical key; acceptance plan.md:185-188 |
| N2 | addressed | A1.d same-row upsert; A2 ON CONFLICT; B1.b idempotent; B3.c ON CONFLICT |
| N3 | addressed | plan.md:7-11 [SHARED] header; per-item additive notes |
| N4 | addressed | plan.md:7-11; B2 conservative; B3.c preserves MAWF columns |
| N5 | **GAP** | No explicit secrets statement; A3 hook & B-tools use env (`CLAUDE_CORPUS_MCP_URL`) but plan never asserts "no secrets in the new files." See CGAP-002. |
| N6 | addressed | A1 widens `ensure_repo_root_entity` return tuple; repo confirms **single caller** (`repo_note.py:164`) — safe. But plan does not state this. See CGAP-003 (cleanup→blocker on traceability). |
| N7 | addressed | plan.md:413 (cancel_job), plan.md:543 (register_repository); both honor guard |
| N8 | addressed | A3.b fail-open; A1 edge plan.md:194 Stop-hook fail-open preserved |
| N9 | addressed | plan.md:597-619 Test plan per item |
| N10 | addressed | plan.md:119-122 Locked Decision 14 + Sequencing |
| N11 | addressed | A1 `repo_key_case_collision` warning; B2 threshold log; B1 `@track_tool_metrics` |
| G1 | addressed | plan.md:62-65,190 "Repository not found" |
| G2 | addressed | plan.md:242-244 anchors to latest real revision |
| G3 | **PARTIAL** | first-note race (plan.md:247) ✓; restart-vs-fresh-job (B2) ✓; but **concurrent `cancel_job` calls** not given a criterion. See CGAP-004. |
| G4 | **PARTIAL** | authoring case-collision deterministic pick (plan.md:192-194) ✓; but deactivation path looks up by `entity_key` with **no `repository_key` filter** (repo `repo_note.py:279-287` confirmed) — interaction with case-collision not addressed. See CGAP-005. |
| G5 | addressed | plan.md:448 idempotent `already_terminal` |
| G6 | addressed | plan.md:483-484 young running row not reclaimed |
| S1 | addressed | plan.md:32-36 Tier-C OUT with rationale |
| S2 | addressed | plan.md:33-34 + 624-626 P1-5 OUT (operational) |

### Conflict Register (Cycle 1)

| pair | tension | reconciliation |
| --- | --- | --- |
| A2.c (auto-create default True) vs A2.d (don't auto-register absent repo) | both touch "what gets created on author" | Reconciled in plan: revision auto-created only when repo row exists; absent repo still errors (Locked Decision 3 + 4). No conflict. |
| B1.a (cancelled terminal) vs B1.d (reclaim/retry exclusion) | cancelled must never be resurrected | Reconciled: cancelled has no outgoing edges; sweeps read only failed/running (Locked Decision 10). No conflict. |
| B2.b (age-gate reclaim) vs G6 (don't clobber running job) | reclaim must spare fresh jobs | Reconciled: predicate spares <5min jobs (plan.md:483-484). No conflict. |
| N3 additive vs B3.c (ON CONFLICT update) | update path could overwrite MAWF columns | Reconciled: update preserves `mawf_repository_id`/`status_id` (plan.md:527-529). No conflict. |
| **NEW** B1.b generic `cancel_job` vs B1.c ingestion-only abort | tool accepts any job_id but only ingestion aborts | **Unreconciled** — see CGAP-001. |

### Blocker Gap Ledger (Cycle 1)

| gap_id | severity | req_id.obligation | lens | evidence | why uncovered | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CGAP-001 | blocker | B1.c / B1 | decomposition + scope-explicitness + conflict | plan.md:421-439 instruments only ingestion's checkpoint; repo `server.py:6584-6587` registers 4 job types (ingestion, repair, integrity_audit, compaction); `cancel_job(job_id)` is generic | "Make jobs stoppable" (X-1) is decomposed only for ingestion; cancel on a repair/integrity_audit/compaction job sets state=cancelled but the workflow runs to completion (no abort check), so the job is not actually stopped. Plan never states this scope boundary. | Add an explicit scope statement to §B1: cooperative abort is ingestion-only (the incident's heavy path); other job types are cancelled-on-record (state flips, `execute_job` skips terminal transition) but run to completion — with rationale (they are short/bounded) + a testable criterion, OR commit to instrumenting them. | — | OPEN |
| CGAP-002 | blocker | N5 | elicitation (non-functional) | plan §A3 new files use `CLAUDE_CORPUS_MCP_URL` etc.; no statement that the new hook/skill/script files contain no secrets | Security non-functional requirement (repo CLAUDE.md "No credentials … in any file") never enumerated for the new artifacts; a coverage gap of omission for a cross-cutting requirement. | Add a one-line non-functional note (Sequencing or a new "Security/secrets" line): new files (`hydrate_repo_memory.py`, `inject-repo-memory.sh`, SKILL.md, env exports) carry no secrets; MCP URL/timeouts via overridable env only; acceptance: grep the new files for secret literals → none. | — | OPEN |
| CGAP-003 | blocker | N6 | traceability (backward-compat) | plan.md:154-157 widens `ensure_repo_root_entity` return tuple 2→3; repo grep confirms exactly one caller (`repo_note.py:164`) | Plan asserts "additive/non-breaking" globally but never demonstrates the signature change has no other caller — a backward-compat obligation left untraced; an interop reviewer could not confirm coverage from the doc alone. | Add to §A1 a note: `ensure_repo_root_entity` has a single caller (`run_author_note`); widening the tuple breaks no other site (grep evidence). Acceptance: `grep -rn ensure_repo_root_entity src/` shows one call site. | — | OPEN |
| CGAP-004 | blocker | G3 | decomposition (negative/boundary) | plan.md:451-456 covers worker-finishes-vs-cancel race; no criterion for two concurrent `cancel_job` calls | Concurrent-runs requirement only partially decomposed: the two-cancellers case (both read non-terminal, both write) has no stated acceptance. | Add an acceptance criterion to §B1: concurrent `cancel_job` on the same running job → one transitions to cancelled, the other catches `InvalidStateTransition`/sees terminal and returns `already_terminal` (idempotent); no error surfaced. | — | OPEN |
| CGAP-005 | blocker | G4 | decomposition (negative/boundary) | plan.md:192-194 handles authoring case-collision; repo `repo_note.py:279-287` confirms deactivate looks up by `entity_key` only (no `repository_key` filter) | Case-collision boundary decomposed for authoring but not for deactivation: under two case-colliding repos, the deterministic pick is consistent, but the plan never states deactivation's no-`repository_key`-filter lookup is safe (entity_key already encodes the canonical key, so a colliding repo's note is not reachable). Left unaddressed → reviewer cannot confirm coverage. | Add to §A1 edge cases: because deactivation derives `entity_key` from the same canonical key authoring used, the entity_key-only lookup remains correct under case-collision (the entity_key namespaces the canonical repo_key); acceptance: deactivate under the losing-case repo does not touch the winning-case repo's note. | — | OPEN |

### Cleanup List (Cycle 1)
- None beyond the blockers above (the matrix is otherwise fully addressed with `path:line` evidence).

### Acceptance-Criteria Table (Cycle 1)

| req_id | testable criterion present? | where |
| --- | --- | --- |
| A1 | yes | plan.md:185-190 (author FCSAPI→retrieve fcsapi; same-row upsert; deactivate mixed case; unknown errors) |
| A2 | yes | plan.md:237-245 |
| A3 | yes | plan.md:307-311 |
| A4 | yes | plan.md:342-346 |
| A5 | yes | plan.md:375-378 |
| B1 | yes (but B1.c partial — CGAP-001; concurrent-cancel missing — CGAP-004) | plan.md:442-449 |
| B2 | yes | plan.md:483-486 |
| B3 | yes | plan.md:534-538 |
| N5 | **no** (CGAP-002) | — |
| N6 | **no** (CGAP-003) | — |
| G3 | partial (CGAP-004) | plan.md:451-456 |
| G4 | partial (CGAP-005) | plan.md:192-194 |
| S1,S2 | n/a (scope-out) | plan.md:32-36, 624-626 |

**Cycle 1 verdict:** 5 blocker gaps (CGAP-001..005). One omission (N5/secrets), one traceability (N6/single-caller), two negative-boundary partials (G3 concurrent-cancel, G4 deactivate-collision), one decomposition+scope conflict (B1.c ingestion-only abort). Proceed to Cycle 1 Plan + Edits.

---

## Cycle 1 Plan

Edit `plan.md` only. Map each open CGAP to an exact edit:

- **CGAP-001** → §B1 "Exact change": add an explicit **scope statement + rationale** that cooperative abort is ingestion-only (the incident's heavy path), other job types (`repair`/`integrity_audit`/`compaction`) are *cancelled-on-record* (state flips, run completes, `execute_job` skips the terminal transition leaving the row `cancelled`); add an acceptance criterion for the non-ingestion cancel behavior.
- **CGAP-002** → add a "Security / secrets" line to Sequencing Phase 2 (or §A3): new files carry no secrets; config via overridable env; grep acceptance.
- **CGAP-003** → §A1: add single-caller note for `ensure_repo_root_entity` tuple widening + grep acceptance.
- **CGAP-004** → §B1 acceptance: add concurrent-`cancel_job` criterion.
- **CGAP-005** → §A1 edge cases: add deactivation-under-case-collision correctness statement + acceptance.

---

## Cycle 1 Edits

Applied to `plan.md`. Closure evidence:

| gap_id | edit | closure evidence (plan.md after edit) |
| --- | --- | --- |
| CGAP-001 | §B1 new "Scope of cooperative abort — ingestion only (LOCKED, explicit)" paragraph + non-ingestion acceptance criterion | §B1 now states 4 job types, ingestion-only abort with rationale, other 3 cancelled-on-record; acceptance "cancel_job on a running non-ingestion job sets the manifest to cancelled immediately … leaves the state cancelled" |
| CGAP-002 | New "## Non-functional: security / secrets" section before Sequencing | enumerates A3/A4/A5/B-tier as secret-free + grep acceptance |
| CGAP-003 | §A1 backward-compat note in `run_author_note` bullet | "ensure_repo_root_entity has exactly one caller … repo_note.py:164 … breaks no other site" + grep acceptance |
| CGAP-004 | §B1 concurrent-cancel acceptance criterion | "Two concurrent cancel_job calls on the same running job → exactly one performs the transition; the other … returns already_terminal: True" |
| CGAP-005 | §A1 edge-cases "Case-collision on the deactivation path (explicit)" | explains entity_key already encodes canonical key → entity_key-only lookup safe under collision + acceptance |

### Updated Blocker Gap Ledger (post Cycle 1 edits)

| gap_id | severity | req_id.obligation | status | closure evidence |
| --- | --- | --- | --- | --- |
| CGAP-001 | blocker | B1.c / B1 | CLOSED | §B1 ingestion-only-abort scope statement + non-ingestion criterion |
| CGAP-002 | blocker | N5 | CLOSED | new Security/secrets section + grep acceptance |
| CGAP-003 | blocker | N6 | CLOSED | §A1 single-caller note + grep acceptance |
| CGAP-004 | blocker | G3 | CLOSED | §B1 concurrent-cancel criterion |
| CGAP-005 | blocker | G4 | CLOSED | §A1 deactivate-collision statement + criterion |

## Cycle 1 Validation

- **Re-read each newly-covered requirement:** confirmed each edit lands a concrete mechanism or an explicit
  scope-out, not a hand-wave.
  - CGAP-001: scope statement is grounded in real registry (`server.py:6584-6587`, verified in Cycle 1
    grounding) and gives both a rationale and a testable non-ingestion criterion. Concrete.
  - CGAP-002: enumerates the actual new artifacts and their env-only config; criterion is a runnable grep.
  - CGAP-003: single-caller claim re-verified by grep this cycle (`ensure_repo_root_entity` → def at
    `repo_note.py:46` + one call at `:164`). Concrete.
  - CGAP-004/005: both add testable acceptance criteria tied to verified code behavior.
- **Re-decompose touched requirements:** B1 now decomposes into ingestion-abort vs non-ingestion
  cancelled-on-record (both covered); G3 now covers first-note race + restart-race + concurrent-cancel; G4
  covers authoring + deactivation collision.
- **Post-edit new-gap pass:** Did any edit create a new conflict or un-decomposed obligation?
  - The CGAP-001 scope-out introduces a NEW explicit out-of-scope item (instrument repair/integrity/compaction
    abort). That is now a **scoped-out requirement with rationale** — not a silent drop. It carries an
    acceptance criterion (non-ingestion cancel sets state and leaves it cancelled). No new blocker.
    Registered as **S3** in the inventory below.
  - The B1↔generic-cancel conflict in the Cycle 1 Conflict Register is now **reconciled** (ingestion aborts;
    others cancelled-on-record by design). No residual unreconciled conflict.
  - No edit changed a function signature beyond the already-traced `ensure_repo_root_entity` (single caller).
  - The Security/secrets grep-acceptance line had a stray quote typo in the command string — cosmetic, does
    not affect coverage (the criterion's intent is unambiguous). Noted as cleanup, not a blocker.
- **Every requirement still has an acceptance criterion:** yes (see Cycle 2 acceptance table).

**New scope item registered:**

| req_id | requirement | type | source |
| --- | --- | --- | --- |
| S3 | Cooperative in-flight abort for non-ingestion job types (repair/integrity_audit/compaction) is OUT (cancelled-on-record only) | scope | plan §B1 "Scope of cooperative abort — ingestion only" |

---

## Cycle 2 Assessment

Fresh full pass over the complete (now 8 explicit + 11 non-functional + 6 negative + 3 scope = ) requirement
set, all lenses, on the edited document. No edits permitted to declare convergence this cycle unless zero
blockers.

### Coverage Matrix (deltas from Cycle 1; all others remain `addressed` as in Cycle 1)

| req_id.obligation | status | addressed where |
| --- | --- | --- |
| B1.c | addressed (scoped) | §B1 ingestion-only abort + S3 scope-out for the other 3 types |
| N5 | addressed | new "Non-functional: security / secrets" section |
| N6 | addressed | §A1 single-caller backward-compat note |
| G3 | addressed | §B1 concurrent-cancel criterion + plan.md first-note race + B2 restart race |
| G4 | addressed | §A1 deactivation case-collision statement + acceptance |
| S3 | addressed | §B1 explicit scope-out with rationale + non-ingestion acceptance criterion |

### Conflict Register (Cycle 2)

| pair | tension | reconciliation |
| --- | --- | --- |
| B1.b generic `cancel_job` vs B1.c ingestion-only abort | tool cancels any job; only ingestion aborts in-flight | **Reconciled** in §B1: non-ingestion = cancelled-on-record (state flips, runs to completion, `execute_job` skips terminal transition); rationale given; criterion present. |
| (all Cycle 1 pairs) | — | remain reconciled (no edit disturbed them) |

No unreconciled conflicts.

### Blocker Gap Ledger (Cycle 2)

Fresh sweep, all lenses:
- **Elicitation completeness:** implied (N1,N2,N6,N8), non-functional (N3,N4,N5,N7,N9,N10,N11), negative
  (G1–G6) all inventoried and addressed; the new S3 captures the abort scope-out. No further implied
  requirement surfaced (e.g. "rollback" — present in plan Rollback section; "what reads the synthetic
  revision" — A2.e + retrieval-by-payload addressed).
- **Omission:** every requirement has a concrete mechanism or explicit scope-out. None mention-only.
- **Decomposition/partial:** B1 (ingestion vs non-ingestion), G3 (3 race sub-cases), G4 (author+deactivate)
  now fully decomposed. A1's five key-derived values each individually addressed (A1.a–.e).
- **Conflict:** reconciled (table above).
- **Acceptance criteria:** every requirement carries one (table below).
- **Scope explicitness:** S1, S2, S3 all explicit with rationale.
- **Traceability:** every plan mechanism traces to a req; the only signature change (ensure_repo_root_entity)
  is traced to its single caller. No orphan mechanism found.
- **Prioritization:** must-haves (A1/A2 keystone, B1/B3 incident) sequenced first (Phase 1); nice-to-haves
  (A3/A4/A5 local) Phase 2; ops follow-up Phase 3. Sane.

**Result: ZERO open blocker gaps.** No edits made this cycle.

### Acceptance-Criteria Table (Cycle 2 — complete)

| req_id | testable criterion present? | where |
| --- | --- | --- |
| A1 | yes | plan.md §A1 acceptance (FCSAPI→fcsapi; same-row upsert; mixed-case deactivate; unknown errors) + single-caller grep + deactivation-collision acceptance |
| A2 | yes | plan.md §A2 acceptance (one __note_anchor__ revision, zero files/chunks, retrievable, False still raises) |
| A3 | yes | plan.md §A3 acceptance (opt-in on/off, fail-open, no-cwd) |
| A4 | yes | plan.md §A4 acceptance (SKILL.md exists, lists, writes a note) |
| A5 | yes | plan.md §A5 acceptance (8-repo scan, count+path line, none-this-run, fail-open) |
| B1 | yes | plan.md §B1 acceptance (transition, ingestion abort, non-ingestion cancelled-on-record, concurrent-cancel idempotent, excluded from sweeps, already_terminal, guard) |
| B2 | yes | plan.md §B2 acceptance (young not reclaimed, old reclaimed, cancelled untouched, default 5min) |
| B3 | yes | plan.md §B3 acceptance (both columns set, conflict-update preserves, created flag) |
| N1 | yes | A1 author+retrieve same key |
| N2 | yes | same-row upsert / ON CONFLICT criteria across A1/A2/B1/B3 |
| N3 | yes | [SHARED] additive header + per-item notes; Rollback shows no migration to undo |
| N4 | yes | B2 conservative; B3.c preserves MAWF columns |
| N5 | yes | Security/secrets section grep acceptance |
| N6 | yes | §A1 single-caller grep |
| N7 | yes | guard honored (cancel_job, register_repository acceptance) |
| N8 | yes | A3 fail-open; A1 Stop-hook fail-open preserved |
| N9 | yes | Test plan section per item |
| N10 | yes | Locked Decision 14 + Sequencing deploy-boundary per item |
| N11 | yes | case-collision warning, threshold log, tool metrics |
| G1 | yes | "Repository not found" |
| G2 | yes | anchors to latest real revision |
| G3 | yes | first-note race + restart race + concurrent-cancel |
| G4 | yes | authoring deterministic pick + deactivation collision acceptance |
| G5 | yes | already_terminal idempotent |
| G6 | yes | young running row not reclaimed |
| S1 | n/a (scope-out + rationale) | plan.md In/Out-of-scope |
| S2 | n/a (scope-out + rationale) | plan.md In/Out-of-scope + Open Questions |
| S3 | scope-out + rationale + non-ingestion criterion | plan.md §B1 |

---

## Cycle 2 Validation

- Re-ran all 8 assessment lenses over the full requirement set on the edited document: zero blocker gaps.
- Post-edit new-gap pass from Cycle 1 produced exactly one new explicit scope item (S3), now covered.
- This cycle made **no edits**, so the hard-stop rule (a cycle that edited may not declare convergence) is
  satisfied: Cycle 1 edited; Cycle 2 is the fresh, no-edit full pass.
- Grounding: all `path:line` plan claims were verified against the real `memory-knowledge` repo in the Cycle 1
  grounding pass (repo_note.py, entity_key.py, jobs/*, ingestion.py, server.py, config.py, retrieval.py,
  migration 016, admin/mawf.py, entity_registrar.py, working-agreement scripts, ~/.claude/settings.json,
  ~/.codex/skills + config.toml) — no plan reference was found to be inaccurate or hallucinated.

---

## Final Convergence Check

A fresh full pass (Cycle 2) over the complete requirement set found **zero open blocker coverage gaps**, and
that pass made **no edits**. Convergence reached.

### Final Coverage Proof

| req_id | every obligation covered or scoped-out? | acceptance criterion present? | evidence |
| --- | --- | --- | --- |
| A1 | yes (a–f) | yes | plan.md §A1 |
| A2 | yes (a–e) | yes | plan.md §A2 |
| A3 | yes (a–d) | yes | plan.md §A3 |
| A4 | yes (a–b) | yes | plan.md §A4 |
| A5 | yes (a–c) | yes | plan.md §A5 |
| B1 | yes (a–f, ingestion abort + S3 scope-out) | yes | plan.md §B1 |
| B2 | yes (a–c) | yes | plan.md §B2 |
| B3 | yes (a–d) | yes | plan.md §B3 |
| N1–N11 | yes | yes | inventory + matrix |
| G1–G6 | yes | yes | inventory + matrix |
| S1 | scoped-out + rationale | n/a | plan.md In/Out-of-scope |
| S2 | scoped-out + rationale | n/a | plan.md In/Out-of-scope + Open Questions |
| S3 | scoped-out + rationale + criterion | yes (non-ingestion behavior) | plan.md §B1 |

### Convergence statement

Convergence = **breadth**: every requirement (decomposed into obligations) is either addressed by a concrete
plan mechanism or explicitly scoped-out with a rationale, and every requirement carries a testable acceptance
criterion. This does **not** assert each addressing actually holds end-to-end against the live runtime, stored
data, and the co-tenant harness — that is the `requirements-satisfaction-gap-loop` (depth) pass that should
run next.

### Intentionally excluded (with rationale)
- **S1** — Tier-C (X-2 secrets RBAC, X-3 data namespacing, X-4 own compute, X-6 ACR/storage split): strategic
  infra deferred to a separate plan (plan In/Out-of-scope).
- **S2** — P1-5 run-weekly-job-once: operational action, not a code change (plan Open Questions, optional).
- **S3** — cooperative in-flight abort for repair/integrity_audit/compaction: those are bounded maintenance
  sweeps, not the incident class; cancel still flips their state (cancelled-on-record). Low-priority follow-up.

### Cleanup (non-blocking)
- (Resolved) The Security/secrets grep-acceptance command string had a cosmetic stray-quote typo; corrected
  in-place. Coverage was unaffected either way.
