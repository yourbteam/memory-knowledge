# Plan — Capture & Jobs Fixes (Tier A + Tier B)

**Mode:** Implementation plan (decision-complete; no code shipped here). Created 2026-06-21.
**Source of findings:** `Tasks/brain-alignment-audit/alignment-audit.md` (§2 Tier A = P1-1..P1-7; §3/§4 Tier B = X-1, X-5).
**Repo:** `memory-knowledge` (Python MCP server; Supabase PG + Qdrant + Neo4j; deployed to Azure via `infra/azure-push.sh`).

> **Shared-infra flag (read first):** The brain is shared by Kamen's personal work (P1) **and** the
> `workflow-orch-app` / `up-harness` autonomous harness (P2), on one B3 plan, one PG, one corpus
> namespace. Items that change **server-side shared behavior** are flagged **[SHARED]** at the item
> header. Every shared change here is **additive / non-breaking** (new tools, widened lookups, new
> nullable-defaulted config, new state-machine edges) — no existing call site changes meaning.

---

## Objective

Make Kamen's personal-work capture loop actually function end-to-end (write **and** read-back),
without forcing full source ingestion; and make ingestion jobs stoppable so the recent incident
class (a long job that cannot be cancelled and auto-resumes across restarts) cannot recur.

Two tiers, eight items: **Tier A** (A1–A5) capture; **Tier B** (B1–B3) jobs/registration.

---

## In-scope / Out-of-scope

**In-scope:** A1 repo-key normalization; A2 notes-only revision/anchor path; A3 capture→recall loop;
A4 Codex capture mechanism; A5 `MK_SPARK_REPOS` + surface `spark-candidates.md`; B1 `running→cancelled`
+ cancel tool; B2 age-gated reclaim-on-start; B3 fix `register_repository` NOT-NULL columns.

**Out-of-scope — Tier C (explicitly OUT):** removing the harness's write access to the brain's KV
secrets (X-2); namespacing brain data by consumer / a separate brain instance (X-3); moving the brain
off the shared B3 plan to its own compute (X-4); shared ACR/storage split (X-6). Also OUT: P1-5
(run the weekly job once — an operational action, not a code change) beyond what A5 already touches.
These are strategic/infra decisions deferred to a separate plan, per audit §4 note "Tiers B/C are
build-bound … the next step is a plan."

---

## Locked Decisions (global; resolve all "could/maybe")

1. **A1 boundary = canonical resolution in `repo_note.py`, not in `auto_capture.py`.** The fix lives at
   the brain boundary (server-side), so *every* caller (the Stop-hook, the Codex skill, manual
   `author_repo_note`, and `deactivate_repo_note`) is fixed at once. `auto_capture.py:48`
   (`Path(cwd).name`) is left as-is; the brain resolves case-insensitively. Rationale: a client-only
   fix leaves the manual/skill/Codex paths broken and re-introduces the bug for any future caller.
2. **Case-insensitivity = case-insensitive *exact* match, not fuzzy.** Resolution rule: match
   `repository_key` ILIKE the input **with no wildcards** (i.e. `lower(repository_key) = lower($1)`),
   returning the **stored canonical key**. If 0 rows → the existing "Repository not found" error. If
   (pathologically) >1 rows differing only by case → pick the exact-case match if present, else the
   lowest `id` (deterministic), and log a warning. No new column is added (audit suggested "or store a
   canonical key" — rejected as heavier and migration-bound; the ILIKE-on-lower approach is additive
   and needs no schema change).
3. **A2 notes-only path = a new lightweight revision created on demand by `ensure_repo_root_entity`**,
   gated by a new parameter, **NOT** a new MCP tool and **NOT** full ingestion. The synthetic revision
   uses a fixed sentinel `commit_sha='__note_anchor__'` and `branch_name='__notes__'`, inserted via the
   existing `upsert_repo_revision` (`structure/entity_registrar.py:27`) which already upserts on
   `(repository_id, commit_sha)`. No source files/chunks/embeddings are created. Auto-create is **opt-in
   per call** (`auto_create_revision: bool`) and **defaults True for note authoring** so capture "just
   works"; `deactivate_repo_note` never creates a revision (read-only resolve).
4. **A2 does NOT auto-register unregistered repos.** If the repo row itself is absent
   (`catalog.repositories`), `author_repo_note` still errors ("Repository not found") — registering a
   repo is a deliberate act (and B3 fixes the registration tool). A2 only removes the *ingested-revision*
   precondition, which is the audit's stated keystone gap (P1-2). Registering the ~5 missing Codex repos
   is an operational follow-up using the now-fixed `register_repository` (B3), not part of this code change.
5. **A3 surfacing = a new hook script `hydrate_repo_memory.py` wired to `UserPromptSubmit`**, parallel to
   `hydrate_corpus.py`, calling `run_retrieval_workflow(repository_key, query)`. Repo is derived from
   `cwd` via the **same** canonical resolution as A1 (the brain resolves it; the hook passes raw cwd
   basename). It is **opt-in** via `MK_REPO_HYDRATE=1` and fail-open (any error/timeout → prints nothing,
   exit 0), mirroring `hydrate_corpus.py`'s contract. Rationale for hook-not-skill: the per-prompt hook
   is the only mechanism that fires automatically every prompt (a skill requires the agent to choose it);
   the audit's gap is precisely "rarely read back automatically."
6. **A4 Codex capture = install the existing `auto-capture` skill into `~/.codex/skills/auto-capture/`.**
   No Stop-hook for Codex (Codex has no session-end hook — audit P1-4). The skill file already exists at
   `working-agreement/auto-capture.skill.md`; installation = copying it to the Codex skills dir as
   `SKILL.md` and documenting it in `SETUP-codex.md`. This is a **local workstation** change, not a deploy.
7. **A5 `MK_SPARK_REPOS` real set (LOCKED):**
   `taggable-api,fcsapi,taggable-server,taggable-database,united-partners,agentic-trading,mcp-agents-workflow,memory-knowledge`.
   This is the union of the audit's hardcoded 3 + the Codex trusted projects (`~/.codex/config.toml`
   lines 33–46: mcp-agents-workflow, FCSAPI, memory-knowledge, taggable-database, taggable-api) + the
   audit-named missing repos (united-partners, agentic-trading). Set as an exported env var consumed by
   both `directive_spark.py:29` and `weekly_review.py:23` (both already read `MK_SPARK_REPOS`). Spark
   is fail-open per repo, so unregistered repos in the list simply yield no rows — safe.
8. **A5 surfacing `spark-candidates.md` = append a "Spark candidates" section to the weekly review's
   stderr summary**, listing the file path and a count of candidate lines, so the weekly run output
   tells Kamen to look. `weekly_review.py` already invokes `spark._run()` which writes the file; we add a
   post-spark read + summary print. No new file, no new tool.
9. **B1 cancel = cooperative DB-flag cancel + a new terminal `cancelled` state**, **not** asyncio task
   kill. A new MCP tool `cancel_job(job_id)` transitions `running→cancelled` (and `pending→cancelled`,
   `retrying→cancelled`). The ingestion worker checks the manifest state at each phase-checkpoint
   boundary and aborts cleanly if it has been set to `cancelled`. Rationale: the in-process
   `_background_tasks` set (`server.py:513`) is not keyed by `job_id`, so a specific asyncio task cannot
   be targeted; and the dispatcher path runs jobs the same way. A DB flag works for **both** execution
   paths and survives a restart. `cancelled` is terminal (no transition out of it), which prevents
   auto-retry (B1) and reclaim resurrection (B2).
10. **B1 `cancelled` is excluded from every re-enqueue/reclaim path.** `cancelled` is added as a terminal
    state in the transition guard with **no outgoing edges**; the retry sweep and reclaim only ever read
    `'failed'`/`'running'`, never `'cancelled'`, so no extra exclusion code is needed — verified against
    `job_retry_manager.py:50-88` and `dispatcher.py:62-82`.
11. **B2 age threshold = new setting `reclaim_running_min_age_seconds: int = 300` (5 min).** Reclaim only
    marks a `running` row failed if `started_utc < NOW() - interval`. Rationale: a fresh container restart
    that races a just-killed-but-recently-started job won't resurrect/clobber it within the grace window;
    5 min comfortably exceeds container cold-start. Uses the manifest's existing `started_utc` column
    (`001_initial_schema.py:286`, `DEFAULT NOW()` at insert; verified: nothing in `jobs/*.py` ever UPDATEs
    `started_utc` — the dispatcher poll sets only `state_code='running'`, so `started_utc` stays at creation).
    **Note (documented limitation):** `started_utc` is set at job *creation*, not at the running-transition.
    Creation time is *earlier* than the true running-start, so the age predicate (`started_utc < NOW() - interval`,
    i.e. reclaim if older than the threshold) trips **slightly earlier/stricter** than it would against a
    running-transition timestamp — never *more* lenient. This is still safe and conservative for the reclaim's
    purpose (don't nuke *recently created* jobs on restart): for these jobs creation ≈ running-start (the
    dispatcher claims and runs in the same poll), and a 5-min grace comfortably absorbs the small
    creation-vs-running gap. The only effect of the proxy is that a young job's grace clock starts at creation
    rather than at the running-transition — still well within the window. No schema change.
12. **B3 fix = make `register_repository` supply `mawf_repository_id` + `status_id`** inline (mirroring
    `admin/mawf.py:upsert_repository` lines 529–556), **not** delegate to the MAWF tool. Rationale:
    keeps the brain's own repo-registration path independent of the MAWF contract surface (audit's
    concern is the coupling); the inline insert is small and uses the same reference-value resolution.
13. **No AI attribution in any commit message.** (Constraint.) Commits authored as Kamen.
14. **Deploy boundary:** A2, A3 (server side of retrieval already deployed), B1, B2, B3 require an
    **Azure deploy** (`infra/azure-push.sh`) because they change server/`src` code. A1 requires a deploy
    (it changes `src/.../repo_note.py`). A3 hook script, A4 skill install, A5 env var are **local-only**
    (workstation), no deploy. See Sequencing.

---

## A1 — Capture repo-key normalization  **[SHARED]**

**Problem.** `auto_capture.py:48` derives `repo_key = Path(cwd).name` → `FCSAPI` (capitalized dir name),
but the registered key is `fcsapi`. Two distinct casing failures result:
- **Authoring:** `ensure_repo_root_entity` (`repo_note.py:58-61`) does an **exact-match**
  `WHERE repository_key = $1` for the repo row, which finds nothing → `ValueError("Repository not found: …")`
  (`repo_note.py:62-63`) → swallowed fail-open by the Stop-hook (`auto_capture.py:127`) → **silent zero capture**.
- **Deactivation:** `run_deactivate_note` does **not** filter by `repository_key` directly; it derives a
  deterministic `entity_key = learned_record_entity_key(repository_key, …)` (`repo_note.py:275`) and looks the
  note up by that key via `WHERE e.entity_key = $1` (the `catalog.entities` join, `repo_note.py:279-287`).
  Because the `entity_key` is computed from the **raw-cased** `repository_key`, a note authored under one casing
  is keyed differently than a deactivate call using another casing → "No repo note found" mismatch.

Net: both paths break on casing, but via different mechanisms (a `repository_key` lookup on authoring, an
`entity_key` derivation on deactivation); the fix must canonicalize the key on **both** paths.
Live evidence: fcsapi has 0 `unverified`/`note` records.

**Exact change.**
- `src/memory_knowledge/workflows/repo_note.py`:
  - Add a helper `_resolve_repository(pool, repository_key) -> asyncpg.Record | None` that runs:
    `SELECT id, repository_key FROM catalog.repositories WHERE lower(repository_key) = lower($1) ORDER BY (repository_key = $1) DESC, id ASC LIMIT 1`.
    (The `ORDER BY` prefers an exact-case hit, then lowest id — Locked Decision 2.)
  - In `ensure_repo_root_entity` (lines 58–64): replace the inline exact-match `fetchrow` with a call to
    `_resolve_repository`; if `None`, raise the existing `ValueError(f"Repository not found: {repository_key}")`.
    Use the **resolved canonical** `repo_row["repository_key"]` for the entity-key derivation and all
    downstream payloads (so the Qdrant `repository_key` payload and entity_key are canonical, matching
    what retrieval filters on — critical for read-back consistency).
  - In `run_author_note`: **thread the canonical key through the whole authoring path.** `ensure_repo_root_entity`
    must return the canonical `repository_key` it resolved (widen its return tuple from `(entity_key, entity_id)`
    to `(entity_key, entity_id, canonical_repository_key)`). **Backward-compat (verified):** `ensure_repo_root_entity`
    has exactly **one** caller in the codebase — `run_author_note` at `repo_note.py:164` (grep:
    `rg -n ensure_repo_root_entity src/` → its `def` plus the single call site). Widening the return tuple
    therefore breaks no other site; the change is genuinely additive. Bind it locally as `canonical_key` in
    `run_author_note` and use `canonical_key` (not the raw `repository_key` arg) for **every** key-derived value:
    - **`valid_from_revision_id` subquery (lines 169–174):** today it exact-matches `repository_key`
      (`WHERE repository_key = $1`). Resolve via `canonical_key` (reuse `_resolve_repository`'s `id` directly to
      avoid the subquery entirely, binding the resolved `repository_id`).
    - **The note's own `entity_key` (line 177):** today
      `entity_key = learned_record_entity_key(repository_key, memory_type, title_hash)` uses the **raw** arg.
      `learned_record_entity_key` is a pure `uuid5` of `f"{repo_key}:…"` with **no internal case-folding**
      (`identity/entity_key.py:30-31`), so `FCSAPI` and `fcsapi` yield **different** UUIDs. Change to
      `learned_record_entity_key(canonical_key, memory_type, title_hash)` so all casings collapse to one row
      (required by the same-row-upsert acceptance criterion) and so it matches what `run_deactivate_note`
      (canonicalized above) computes.
    - **The Qdrant payload (line 203):** today `embed_and_upsert_learned_record(..., repository_key=repository_key, …)`
      stores the **raw** key in the `learned_memory` payload that retrieval filters on. Change to
      `repository_key=canonical_key` so `run_retrieval_workflow("fcsapi", …)` (which filters by the canonical
      payload — `retrieval.py:851-875`) matches the stored note. This is the read-back-critical change.
    - `repository_root_entity_key` (`identity/entity_key.py:34-40`, used inside `ensure_repo_root_entity` at
      `repo_note.py:76`) is likewise case-sensitive; because `ensure_repo_root_entity` now derives it from the
      resolved canonical `repo_row["repository_key"]` (per the bullet above), the root anchor is also canonical.
  - In `run_deactivate_note` (lines 274–287): the deterministic `entity_key` is derived from
    `repository_key` at **line 275** (`entity_key = learned_record_entity_key(repository_key, memory_type, title_hash)`),
    and the note is then looked up by that `entity_key` via the `catalog.entities` join at lines 279–287
    (`WHERE e.entity_key = $1`) — there is **no** `repository_key` WHERE clause here. To stay symmetric with
    authoring, canonicalize **before** deriving the entity_key: call `_resolve_repository` first; if `None`,
    return the existing "No repo note found" error; else compute the `entity_key` from the **canonical**
    `row["repository_key"]` (i.e. `learned_record_entity_key(row["repository_key"], memory_type, title_hash)`)
    so it matches the key authoring wrote under. The existing entity_key-join lookup at lines 279–287 is
    otherwise unchanged.

**Acceptance criteria (testable).**
- Calling `author_repo_note(repository_key="FCSAPI", ...)` succeeds and the note is retrievable via
  `run_retrieval_workflow("fcsapi", <query>)` (canonical key), proving write+read use the same key.
- `author_repo_note("FcSaPi",...)` and `author_repo_note("fcsapi",...)` with the **same title** upsert to
  the **same** `learned_records` row (same entity_key), not two rows.
- `deactivate_repo_note("FCSAPI", title=...)` deactivates the note authored under any casing.
- Unknown repo (`author_repo_note("does-not-exist",...)`) still returns the "Repository not found" error.

**Edge cases / failure behavior.** Two repos differing only in case → deterministic pick (exact-case
else lowest id) + a `structlog` warning `repo_key_case_collision`. Empty/None key → unchanged validation
path. Fail-open behavior of the Stop-hook is preserved (this only makes the previously-failing lookup succeed).
**Case-collision on the deactivation path (explicit).** `run_deactivate_note` looks the note up by
`entity_key` alone — there is **no** `repository_key` WHERE clause (`repo_note.py:279-287`, verified). This
stays correct under a case-collision because the `entity_key` is a `uuid5` that *already encodes* the
canonical repo key (`learned_record_entity_key(canonical_key, …)`), and authoring writes under the **same**
canonical key resolved by the **same** `_resolve_repository` deterministic pick. So a note authored under
the winning-case repo and a deactivate call (under any casing that resolves to that same canonical key)
compute the identical `entity_key`; a *different* colliding repo (distinct canonical key, distinct id) yields
a different `entity_key` and is never reachable from the wrong repo. No `repository_key` filter is needed for
correctness here. **Acceptance:** with two repos colliding only by case, `deactivate_repo_note` invoked for
one canonical repo deactivates only that repo's note and never the other's.

**Verification.**
- Local: `pytest tests/test_repo_note.py` (extend with case-insensitive cases — see Test plan).
- Live (after deploy): from a session in `/Users/kamenkamenov/FCSAPI`, call `author_repo_note` with key
  `FCSAPI`; then `run_retrieval_workflow` with `fcsapi`; confirm the note surfaces in `repo_scoped_memory`.

---

## A2 — Notes-only "register a revision" path (keystone)  **[SHARED]**

**Problem.** `ensure_repo_root_entity` (`repo_note.py:66-73`) refuses to anchor a note unless the repo has
a `catalog.repo_revisions` row, and the only producer of one today is full source ingestion
(`run_repo_ingestion_workflow` → `_ingestion.run`), which embeds all source — the heavy/sensitive path that
caused the incident (audit P1-2, X-1). So capture is impossible on the ~5 unregistered/un-ingested Codex
repos and any repo Kamen hasn't deliberately ingested.

**Exact change.**
- `src/memory_knowledge/workflows/repo_note.py`, `ensure_repo_root_entity`:
  - Add parameter `auto_create_revision: bool = True`.
  - After resolving the repo (A1) and finding **no** revision (current lines 66–73): if
    `auto_create_revision` is True, create a synthetic note-anchor revision instead of raising:
    insert via the existing `catalog.repo_revisions` shape (mirror `entity_registrar.upsert_repo_revision`,
    `entity_registrar.py:27-49`) with
    `commit_sha='__note_anchor__'`, `branch_name='__notes__'`, `parent_sha=NULL`,
    `ON CONFLICT (repository_id, commit_sha) DO UPDATE SET branch_name = EXCLUDED.branch_name RETURNING id`.
    Import and reuse `upsert_repo_revision` directly (it already returns the id) — do not duplicate SQL.
    NOT-NULLs satisfied: `repository_id` (resolved), `commit_sha` (sentinel). `committed_utc` nullable,
    `created_utc` defaulted. If `auto_create_revision` is False and no revision exists, keep the existing
    raise (so callers that *want* the strict behavior — e.g. a future ingestion-only path — can opt out).
  - The `catalog.entities` insert (lines 79–90) already uses `repo_revision_id`; pass the synthetic id.
    `catalog.entities` NOT-NULLs (`entity_key`, `entity_type`, `repository_id`, `repo_revision_id`) are all
    satisfied; `external_hash` nullable.
- `run_author_note` `valid_from_revision_id` (lines 169–174): with A1's re-query it will now find the
  synthetic revision (latest by id) — correct: notes anchor to the note revision.
- **No new MCP tool.** `author_repo_note` already calls `ensure_repo_root_entity` with the default
  `auto_create_revision=True`, so the capability is on by default with zero server.py signature change.
- **`branch_heads` / `retrieval_surfaces`:** NOT touched. They are not on the repo-note read path
  (repo-note retrieval rides the `learned_memory` Qdrant search by `repository_key` payload —
  `repo_note.py:197-209`, `retrieval.py:851-875`), and both tables' NOT-NULL `repo_revision_id` would only
  matter if we wrote them, which we do not. Documented so the implementer doesn't add them.
  **Consequence (verified, load-bearing):** because `branch_heads` is left empty for a notes-only repo,
  every consumer that derives "latest commit" **via `branch_heads → repo_revisions`** sees the synthetic
  revision as invisible — confirmed for `list_repositories` (`server.py:963-969` LATERAL join through
  `branch_heads`, so `latest_commit` stays NULL — the MAWF/harness "latest commit" view is **not**
  corrupted) and for the freshness scheduler's enumeration (`ingestion_scheduler.py:26-37`, same
  `branch_heads` join). So the sentinel does **not** leak into those surfaces.
- **Sentinel-revision filter on direct latest-`repo_revisions` readers (REQUIRED — SGAP-001).** Two
  integrity paths read the latest revision **directly from `catalog.repo_revisions`** (NOT via
  `branch_heads`), so they DO pick up `__note_anchor__` for a notes-only repo and mis-behave:
  - `integrity/freshness_audit.py:27-37` (`SELECT rr.commit_sha … ORDER BY rr.created_utc DESC LIMIT 1`)
    → would set `latest_pg_commit='__note_anchor__'` and compare it to real Qdrant `commit_sha` payloads →
    **false "stale"** report.
  - `integrity/repair_drift.py:53-61` (`SELECT r.id, rr.id, rr.commit_sha, rr.branch_name … ORDER BY
    rr.created_utc DESC LIMIT 1`) → would tag rebuilt Qdrant/Neo4j points with `commit_sha='__note_anchor__'`
    and can drive `checkout_commit('__note_anchor__')` (`git/clone.py:80-82`) → **git error**.
  **Required implementation step:** add `AND rr.commit_sha <> '__note_anchor__'` to **both** of those
  latest-revision selects (and to any future "latest *real* revision" reader). After the filter, a
  notes-only repo yields `row is None` in both (the existing `if row is None` branches already handle that
  correctly: freshness returns an empty report — "no revisions ingested yet"; repair returns "No revisions
  found"). This keeps the synthetic revision a true no-op for the integrity surfaces.
  **Acceptance:** `check_freshness` / `rebuild_revision` on a registered-but-notes-only repo return the
  no-real-revision branch (`latest_pg_commit = NULL` / "No revisions found"), never `__note_anchor__`.

**§A2 interop — freshness scheduler must NOT auto-ingest notes-only repos (REQUIRED — SGAP-002).**
A2's whole intent is to enable capture **without** the heavy/sensitive full source ingestion that caused the
incident (audit X-1). But the freshness scheduler is an autonomous producer of ingestion jobs and is keyed
off `branch_heads`, **not** the synthetic revision: `ingestion_scheduler.py:26-37` enumerates
`catalog.repositories WHERE origin_url IS NOT NULL` (minus `mawf%`/`repo-%`/`idx-%` prefixes) LEFT JOIN
`branch_heads`. For a notes-only repo `bh.branch_name IS NULL`, so `_process_repo`
(`ingestion_scheduler.py:179-185`) takes the **bootstrap** path → `resolve_default_branch` →
`create_job("ingestion", …)` = **full source ingestion**. The synthetic `__note_anchor__` revision does
**not** prevent this (the scheduler never looks at `repo_revisions` for the enqueue decision). So a
notes-only repo that has an `origin_url` would be **autonomously full-ingested**, defeating A2's intent and
re-arming the incident class B1/B2 exist to contain.
Gating facts: `ingestion_scheduler_enabled` defaults **False** (`config.py:92`) and
`ingestion_scheduler_repo_allowlist` defaults empty = **all** origin_url repos (`config.py:96`). The **live
Azure value of `ingestion_scheduler_enabled` cannot be read from the repo** and is the one item needing
operational confirmation.
**Locked contract + required steps:**
1. **Registration contract for personal / notes-only repos (primary mechanism):** register them with
   `origin_url = NULL`. The scheduler filters `origin_url IS NOT NULL` (`ingestion_scheduler.py:31`), so a
   null-origin repo is **never enumerated** and can never be auto-ingested, while notes/capture work fully
   (capture does not use `origin_url`). This is the default path for the B3 operational follow-up
   (Phase 3): register the missing Codex/personal repos **without** an `origin_url` unless deliberate full
   ingestion is wanted.
2. **Defense-in-depth (belt-and-suspenders, implement if any notes-only repo must carry an `origin_url`):**
   exclude notes-only repos from `_ENUMERATE_SQL` by skipping repos whose only revision is the sentinel —
   add `AND EXISTS (SELECT 1 FROM catalog.repo_revisions rr2 WHERE rr2.repository_id = r.id AND
   rr2.commit_sha <> '__note_anchor__')` to the scheduler enumeration (so a repo with *only* the synthetic
   revision is not a scheduler candidate). This makes the protection independent of how `origin_url` was set.
3. **Verification step (operational):** before relying on (1) alone, confirm the live
   `ingestion_scheduler_enabled` value and the allowlist in the Azure deploy; record the result. If the
   scheduler is enabled AND any notes-only repo carries an `origin_url`, implement (2). If neither can be
   guaranteed, this becomes a **user decision** (accept scheduler-driven ingestion of those repos, or apply
   (1)/(2)).
**Acceptance:** with the freshness scheduler enabled, a registered notes-only repo (no real revision) is
**not** enqueued for ingestion — either because it has `origin_url IS NULL` (mechanism 1) or because the
enumeration excludes sentinel-only repos (mechanism 2).

**Acceptance criteria (testable).**
- For a **registered but never-ingested** repo, `author_repo_note` succeeds, creating exactly one
  `repo_revisions` row with `commit_sha='__note_anchor__'`, **zero** `catalog.files`/`catalog.chunks`
  rows, and **zero** source embeddings.
- Re-authoring on the same repo reuses the same synthetic revision (no duplicate revision rows).
- The note is retrievable via `run_retrieval_workflow` for that repo.
- A repo that *was* fully ingested still anchors to its **latest real** revision (the synthetic one is only
  created when none exists; if a real revision later lands with a higher id, new notes anchor to it — this
  matches existing "latest revision" semantics and is acceptable).
- `ensure_repo_root_entity(..., auto_create_revision=False)` on a no-revision repo still raises.

**Edge cases / failure behavior.** Concurrent first-note race → `ON CONFLICT (repository_id, commit_sha)`
makes revision creation idempotent. Repo absent entirely → "Repository not found" (Locked Decision 4).
A later full ingestion creating real revisions does not collide (different `commit_sha`). The sentinel
revision is inert for **source retrieval** (no files/chunks reference it) and for **`branch_heads`-keyed
readers** (`list_repositories`, the freshness-scheduler enumeration — both join through the empty
`branch_heads`). It is **NOT** inert for the two **direct** latest-`repo_revisions` readers
(`freshness_audit.py`, `repair_drift.py`): those must filter the sentinel per the REQUIRED step above
(SGAP-001). And it does **not** by itself stop the freshness scheduler from bootstrapping a full ingest of a
notes-only repo — see the §A2 freshness-scheduler interop step (SGAP-002).

**Verification.**
- Local: `pytest tests/test_repo_note.py` (add no-revision-auto-create case; assert no files/chunks).
- Live (after deploy): pick a registered-but-not-ingested repo (e.g. register `taggable-database` via B3,
  then) call `author_repo_note`; query PG `SELECT commit_sha FROM catalog.repo_revisions WHERE repository_id=...`
  → see `__note_anchor__`; `SELECT count(*) FROM catalog.files WHERE repo_revision_id=<that id>` → 0.

---

## A3 — Close the capture→recall loop (repo-scoped retrieval)

**Problem.** The per-prompt `UserPromptSubmit` hook only calls `corpus_query` (global Tier-2) via
`hydrate_corpus.py:41`; it never calls repo-scoped `run_retrieval_workflow`. So captured repo notes
surface only when an agent *deliberately* runs retrieval (audit P1-3) — the loop isn't closed automatically.

**Exact change.**
- New file `working-agreement/hydrate_repo_memory.py` (a sibling of `hydrate_corpus.py`, same structure):
  - Reads hook stdin JSON; takes `prompt` **and** `cwd`.
  - Derives raw repo key = basename of `cwd` (the brain canonicalizes it — A1).
  - Calls MCP tool `run_retrieval_workflow` with `{"repository_key": <raw key>, "query": prompt}`.
  - Parses the result; if `status == "success"` and the bundle contains repo-scoped memory, prints a
    `UserPromptSubmit` `additionalContext` block titled "# Repo memory — retrieved for this prompt"
    (context-only, Tier-1 directives remain authoritative — mirror `hydrate_corpus.py:66-71`).
  - **Opt-in:** does nothing unless `MK_REPO_HYDRATE=1`. **Fail-open:** any error/timeout/no-cwd/no-hits →
    print nothing, exit 0. Env tunables mirror `hydrate_corpus.py`: `CLAUDE_CORPUS_MCP_URL`,
    `CLAUDE_REPO_HYDRATE_TIMEOUT` (default 6), and a min-results guard.
- New wrapper `working-agreement/inject-repo-memory.sh` — an exact structural copy of `inject-corpus.sh`
  (verified shape, `inject-corpus.sh:1-18`): a bash wrapper that resolves the repo venv Python and the helper
  path from overridable env vars, guards both exist, runs the helper with stdin inherited and stderr
  suppressed, and always `exit 0`. Concretely:
  ```bash
  #!/usr/bin/env bash
  # Repo-scoped memory hydration: query the deployed brain with the prompt + cwd and inject
  # the repo's notes into Claude Code's context. Fail-open: exit 0 on any error.
  VENV_PY="${CLAUDE_REPO_HYDRATE_PYTHON:-/Users/kamenkamenov/memory-knowledge/.venv/bin/python}"
  HELPER="${CLAUDE_REPO_HYDRATE_HELPER:-/Users/kamenkamenov/memory-knowledge/working-agreement/hydrate_repo_memory.py}"
  [ -x "$VENV_PY" ] || exit 0
  [ -f "$HELPER" ] || exit 0
  "$VENV_PY" "$HELPER" 2>/dev/null
  exit 0
  ```
  (Same env-override + guard + `exit 0` contract as `inject-corpus.sh:10-18`.)
- **Register as a second hook** in `~/.claude/settings.json` by **appending** an entry to the existing
  `hooks.UserPromptSubmit` **array** (do not replace the file or the existing `inject-directives.sh` /
  corpus entries). Document in `SETUP-claude.md` (mirroring its existing block at `SETUP-claude.md:21-30`)
  the concrete entry, using the **absolute** path (no `~`):
  ```json
  { "hooks": [ { "type": "command", "command": "/Users/kamenkamenov/memory-knowledge/working-agreement/inject-repo-memory.sh" } ] }
  ```
  Multiple `UserPromptSubmit` array entries each run and each may add context (see Edge cases) — this is
  additive to the corpus/directives hooks.
- **Surfacing the extraction shape:** `run_retrieval_workflow` already returns the retrieval bundle; the
  script reads the repo-scoped slice (`repo_scoped_memory` per `retrieval.py:851-875`). If that key is
  absent/empty, print nothing.

**Acceptance criteria (testable).**
- With `MK_REPO_HYDRATE=1` and cwd in a repo that has an active note, submitting a prompt that semantically
  matches the note yields an `additionalContext` block containing the note body.
- With `MK_REPO_HYDRATE` unset, the script prints nothing and exits 0.
- Any brain error/timeout → nothing printed, exit 0 (never blocks the prompt).
- cwd not a known repo → nothing printed (brain returns no repo memory; fail-open).

**Edge cases / failure behavior.** Slow brain → timeout → silent. Two hooks both adding context → both
blocks appended (independent; ordering not significant). No double-deploy needed: server-side
`run_retrieval_workflow` already exists and is deployed.

**Verification.**
- Local dry-run: `echo '{"prompt":"<query>","cwd":"/Users/kamenkamenov/FCSAPI"}' | MK_REPO_HYDRATE=1 python working-agreement/hydrate_repo_memory.py`
  → prints the JSON additionalContext payload when a matching note exists.
- Confirm a fresh Claude session in that repo gets the repo-memory block.

---

## A4 — Codex capture path

**Problem.** Auto-capture's Stop-hook is Claude-only (`SETUP-autocapture.md:28` — "Codex has no
session-end hook → use Option 2 there"), and the `auto-capture` skill is **not** installed in
`~/.codex/skills` (verified: `~/.codex/skills/` exists with many skills but no `auto-capture/`). So Codex
(≈half the workflow) captures nothing (audit P1-4).

**Exact change (local workstation; no deploy).**
- Install the existing skill: create `~/.codex/skills/auto-capture/SKILL.md` from
  `working-agreement/auto-capture.skill.md` (content is ready; the front-matter `name: auto-capture` and
  description already match the Codex skill format used by sibling skills in that dir).
- Update `working-agreement/SETUP-codex.md`: add a "Capture (auto-capture skill)" section documenting the
  install path and that, on session close, Codex should invoke the `auto-capture` skill which writes
  `unverified` candidate notes via `author_repo_note` (now functional everywhere thanks to A1+A2).
- Update `working-agreement/SETUP-autocapture.md` Option 2: replace "install into your AI client's skills"
  with the concrete Codex path `~/.codex/skills/auto-capture/SKILL.md`.

**Acceptance criteria (testable).**
- `~/.codex/skills/auto-capture/SKILL.md` exists and its front-matter `name` is `auto-capture`.
- Listing Codex skills shows `auto-capture` available.
- In a Codex session in a registered repo (post-A1/A2), ending the session and invoking the skill writes
  at least one `unverified` note retrievable via `repo_scoped_memory`.

**Edge cases / failure behavior.** Repo not registered → skill (per its step 3) reports "not ingested,
skipping" — but with A2, registered repos no longer need ingestion, so the only skip case is an unregistered
repo. The skill is advisory (agent-invoked), so no fail-open machinery is needed.

**Verification.** `ls ~/.codex/skills/auto-capture/SKILL.md`; run a short Codex session, end it, check the
repo's `repo_scoped_memory`.

---

## A5 — `MK_SPARK_REPOS` real set + surface `spark-candidates.md`

**Problem.** Spark/weekly hardcode 3 repos (`directive_spark.py:28`, `weekly_review.py:23-24`) and no
`MK_SPARK_REPOS` is set, so patterns in other repos never surface (P1-6); and the weekly review runs spark
but never tells Kamen the candidates exist (P1-7) — `weekly_review.py` prints consolidation lines only.

**Exact change.**
- **Set the env var** (local; consumed by both scripts which already read `MK_SPARK_REPOS`): export
  `MK_SPARK_REPOS` = the Locked-Decision-7 list in the weekly-review launch context. Concretely, add the
  export to `working-agreement/weekly-review.sh` (the launchd wrapper) so the scheduled run picks it up,
  and document it in `SETUP-weekly-review.md`. No code change to `directive_spark.py`/`weekly_review.py`
  defaults (leave the 3-repo default as a fallback).
- **Surface the candidates** in `working-agreement/weekly_review.py`: after the spark step (`_run()` call,
  around lines 59–68), read the spark output path from the **already-loaded module object**
  `spark.OUT` (the module is loaded via `importlib.util.module_from_spec` into the local `spark` at
  `weekly_review.py:62-66`; `OUT` is a module-level `Path` constant at `directive_spark.py:31` — do **not**
  add a separate `import directive_spark`, which would load a second copy). If it
  exists, count non-empty candidate bullet lines (lines starting with `- `), and print to stderr:
  `[weekly-review] spark-candidates: <N> candidate(s) -> <abs path>` plus the first up-to-5 candidate
  titles. If the file is missing or empty, print `[weekly-review] spark-candidates: none this run`.

**Acceptance criteria (testable).**
- A weekly run with `MK_SPARK_REPOS` set scans all 8 repos (spark's `Repos scanned:` header lists them).
- The weekly run's stderr includes a `spark-candidates:` line with the count and the file path.
- With no candidates, the line reads `none this run` (no crash).
- Unregistered repos in the list don't error (spark is fail-open per repo).

**Edge cases / failure behavior.** Spark file write fails → the surface step prints "none this run"
(file-missing branch). Very long candidate file → only the first 5 titles are echoed (full file remains on
disk). Repo not in brain → that repo contributes 0 rows.

**Verification.**
- Local: `MK_SPARK_REPOS="taggable-api,fcsapi,taggable-server,taggable-database,united-partners,agentic-trading,mcp-agents-workflow,memory-knowledge" python working-agreement/weekly_review.py --date 2026-06-21 2>&1 | grep spark-candidates`
  → see the count/path line; `head working-agreement/spark-candidates.md` shows the 8-repo scan header.

---

## B1 — `running→cancelled` transition + cancel tool  **[SHARED]**

**Problem.** `state_transition_guard.py:3-8` allows `running → {completed, failed}` only — there is **no**
cancel edge. There is no MCP tool to stop a running job. The retry sweep (`job_retry_manager.py:50-88`) and
reclaim (`dispatcher.py:62-82`) auto-resurrect jobs. Net: Kamen cannot stop his own long ingestion (audit
X-1 — "this is the incident").

**Exact change.**
- `src/memory_knowledge/jobs/state_transition_guard.py`: add `cancelled` as a terminal target from all
  non-terminal states. New `VALID_TRANSITIONS`:
  - `"pending": {"running", "cancelled"}` (already has cancelled — keep)
  - `"running": {"completed", "failed", "cancelled"}`  ← **add `cancelled`**
  - `"retrying": {"running", "cancelled"}`  ← **add `cancelled`**
  - `"failed": {"retrying", "dead_letter"}` (unchanged)
  - No key for `"cancelled"` ⇒ terminal (empty allowed set) — re-cancel raises `InvalidStateTransition`,
    which the tool handles as idempotent (see below).
- `src/memory_knowledge/jobs/manifest_writer.py`, `update_job_state`: include `'cancelled'` in the
  terminal-set branch (line 68) so `completed_utc` is stamped on cancel:
  change `if state_code in ("completed", "failed", "dead_letter"):` →
  `if state_code in ("completed", "failed", "dead_letter", "cancelled"):`. Also accept an
  `error_code='cancelled'` / `error_text='Cancelled by operator.'` passed through.
- **New MCP tool** in `src/memory_knowledge/server.py` (mirror `check_job_status` shape, with write-guard):
  `cancel_job(job_id: str, correlation_id: str | None = None) -> str`:
  1. `bind_run_context`; `check_remote_write_guard(get_settings(), "cancel_job")` (cancel is a write).
  2. Read the manifest (`get_job_by_id`). Not found → error result.
  3. If current state is already terminal (`completed`/`failed`/`dead_letter`/`cancelled`) → return
     `status="success"` with `data={"job_id":..., "state_code": <current>, "already_terminal": True}`
     (idempotent; do not raise).
  4. Else call `update_job_state(pool, job_id, "cancelled", error_code="cancelled", error_text="Cancelled by operator.")`.
     Return success with the new state.
  Register with `@mcp.tool()` + `@track_tool_metrics("cancel_job")`.
- **Cooperative abort in the worker (ingestion):** in `src/memory_knowledge/workflows/ingestion.py`, the
  abort check must fire at **every** phase-checkpoint boundary, not a chosen subset. `ingestion.py` has **8**
  `await _save_ckpt(...)` call sites (verified: `rg -n "await _save_ckpt" src/memory_knowledge/workflows/ingestion.py`
  → lines 580, 916, 1088, 1107, 1145, 1170, 1187, 1346; line 579 is the `functools.partial` definition, not a
  call). **Lock — single chokepoint:** add the cancel re-check **inside** the `_save_ingestion_checkpoint`
  helper (`ingestion.py:165`, which `_save_ckpt` is a `functools.partial` of at `ingestion.py:579`) so all 8
  boundaries are covered by one edit and no site can be missed. The helper already receives `manifest_job_id`;
  when `manifest_job_id is not None`, after persisting the checkpoint it re-reads the manifest state
  (`SELECT state_code FROM ops.job_manifests WHERE job_id=$1`) and, if it equals `'cancelled'`, raises a
  sentinel `JobCancelled` exception (or returns a flag the caller checks immediately). The `run(...)` body
  catches that sentinel and returns a `WorkflowResult(status="error", error="cancelled", ...)` **without**
  calling `update_job_state` to a different state (the manifest is already `cancelled`, which is terminal).
  Expose the underlying predicate as a small helper `_is_cancelled(pool, job_id) -> bool` in `ingestion.py`,
  used by the checkpoint chokepoint. Because `execute_job`
  (`job_worker.py:59-70`) would otherwise try to set `failed` on an error result, guard it: in
  `execute_job`, before transitioning to `failed`/`completed`, re-read state and **skip** the transition if
  it is already `'cancelled'` (terminal). Lock: add at `job_worker.py` start of the result-handling block a
  check `current = SELECT state_code...; if current == 'cancelled': return result` so a cancelled job stays
  cancelled and no invalid transition is attempted. **Site precision (verified):** `execute_job` calls
  `update_job_state` at **three** places that would each raise `InvalidStateTransition` on a `cancelled`
  row — the error branch (`job_worker.py:63-69`, sets `failed`), the success branch
  (`job_worker.py:83-88`, sets `completed`), and the outer `except` (`job_worker.py:94-100`, sets `failed`).
  The cancelled-guard must short-circuit **all three** — either re-read `state_code` once immediately after
  `result` is obtained and before any `update_job_state` (return early when `'cancelled'`) **and** repeat the
  guard in the `except` path; or — simpler and race-free — make `update_job_state` itself a no-op when the
  current state is already `'cancelled'`. The plan accepts either; the no-op-in-`update_job_state` variant
  also protects any other caller and is the recommended form.

**Scope of cooperative abort — ingestion only (LOCKED, explicit).** The dispatcher registers **four**
job types (`server.py:6584-6587`): `ingestion` (`_ingestion.run`), `repair` (`_repair_rebuild.run`),
`integrity_audit` (`_integrity_audit.run`), `compaction` (`_compaction.run`). `cancel_job(job_id)` is
**generic** — it transitions *any* job to `cancelled`. The **cooperative in-flight abort** (the checkpoint
chokepoint above) is added **only to `ingestion`**, because ingestion is the long/heavy path that *is* the
incident (audit X-1; minutes-to-hours, the only job that OOM-restarts the shared B3 plan). For the other
three job types, `cancel_job` is **cancelled-on-record**: the manifest flips to `cancelled` immediately
(so it is never re-enqueued, retried, or reclaimed — B1.d), the in-flight workflow runs to its natural
end (these are short/bounded sweeps, not the incident class), and `execute_job`'s
already-`cancelled` guard (above) **skips** the terminal `completed`/`failed` transition so the row stays
`cancelled`. Rationale for not instrumenting all four: (a) the audit incident is specifically a long
ingestion; (b) integrity-audit/compaction/repair are bounded maintenance sweeps where one extra run is
harmless; (c) a single chokepoint in ingestion covers all 8 ingestion checkpoints with one edit, whereas
abort hooks in three more workflows would widen the blast radius of this [SHARED] change for little gain.
Instrumenting the other three with the same `_is_cancelled` predicate is an explicit, low-priority
follow-up, **out of scope for this plan**.

**Harness interop (verified — INV-3).** The co-tenant `workflow-orch-app` reads the shared brain's job
state and already treats `cancelled` correctly: its recovery scanner excludes non-recoverable states
(`mcp-agents-workflow/src/workflow_orch/mawf_recovery_scanner.py:18-23` lists only
queued/running/waiting_for_feedback/resume_pending — a `cancelled` job is never resurrected), its
terminal-status check already includes `cancelled` (`mawf_workflow_runs.py:300-305`), and its
active-status filters exclude it (`mcp_server.py:6868,13671,21189`). One **non-fatal** harness gap: the
job-poll terminal set at `mcp-agents-workflow/src/workflow_orch/mcp_server.py:8553`
(`{"success","completed","error","failed"}`) does **not** include `cancelled`, so a harness-initiated
ingestion that is cancelled will poll ~3× (≈0.6 s) before settling on a non-terminal/unknown read rather
than recognizing `cancelled`. This is a harness-side cosmetic delay, **out of scope for this repo**, and the
brain change is safe regardless (no brain path resurrects or mis-handles `cancelled`). Recorded so the
harness owner can add `cancelled` to that poll set.

**Acceptance criteria (testable).**
- `validate_transition("running", "cancelled")` returns None (allowed); `validate_transition("cancelled", "running")` raises.
- `cancel_job` on a `running` ingestion job transitions it to `cancelled` (verified in PG), and the
  background worker stops at the next checkpoint without flipping the state to `failed`/`completed`.
- `cancel_job` on a `running` **non-ingestion** job (`integrity_audit`/`compaction`/`repair`) sets the
  manifest to `cancelled` immediately; the workflow runs to completion but `execute_job` leaves the state
  `cancelled` (no flip to `completed`/`failed`), and the job is never re-enqueued/retried/reclaimed.
- Two **concurrent** `cancel_job` calls on the same running job → exactly one performs the
  `running→cancelled` transition; the other reads a terminal/`cancelled` current state (or catches
  `InvalidStateTransition`) and returns `already_terminal: True` — no error surfaced to either caller (B1
  cancel is idempotent under concurrency).
- A `cancelled` job is **never** picked up by the dispatcher poll (`state_code IN ('pending','retrying')`
  only — `dispatcher.py:119-126`), **never** retried (sweep reads `'failed'` — `job_retry_manager.py:63,76`),
  and **never** reclaimed (reclaim reads `'running'` — `dispatcher.py:79`).
- `cancel_job` on an already-completed/cancelled job returns success with `already_terminal: True` (idempotent).
- `cancel_job` honors the remote write guard (returns the guard envelope when remote writes are disabled).

**Edge cases / failure behavior.** Job finishes between the read and the cancel write → `update_job_state`
sees a terminal current state and `validate_transition(terminal, "cancelled")` raises; the tool catches
`InvalidStateTransition` and returns `already_terminal`. Worker mid-phase when cancelled → it completes the
current phase's in-flight unit, then aborts at the checkpoint (bounded extra work = one phase, acceptable).
A cancelled job's partial data remains (notes/chunks already written stay); this matches existing partial
semantics and is safe (no auto-resume).

**Verification.**
- Local: `pytest tests/` for the guard (extend `test_*` for the new edge) and a worker-abort unit test
  with a fake pool returning `cancelled`.
- Live (after deploy): start an ingestion (`run_repo_ingestion_workflow`), immediately `cancel_job(job_id)`,
  poll `check_job_status` → `cancelled`; wait > poll interval and confirm it does not return to `running`.

---

## B2 — Age-gate `reclaim_stale_running_jobs_on_start`  **[SHARED]**

**Problem.** `dispatcher._reclaim_stale_running` (`dispatcher.py:62-82`) marks **every** `running` row
`failed` on startup with no age threshold (`config.py:117` enables it). A fresh restart that races a
just-started job would clobber it; combined with the retry sweep this is part of the auto-resume incident
chain (audit X-1, B2).

**Exact change.**
- `src/memory_knowledge/config.py`: add `reclaim_running_min_age_seconds: int = 300` next to
  `reclaim_stale_running_jobs_on_start` (line 117). Additive, defaulted.
- `src/memory_knowledge/jobs/dispatcher.py`, `_reclaim_stale_running` (lines 73–81): add an age predicate
  to the UPDATE:
  `WHERE state_code = 'running' AND started_utc < NOW() - ($1 * INTERVAL '1 second')`, binding
  `self._settings.reclaim_running_min_age_seconds` (read via `getattr(self._settings, "reclaim_running_min_age_seconds", 300)`
  for safety). Log the threshold in the existing `dispatcher_reclaimed_stale_running` log line.

**Acceptance criteria (testable).**
- A `running` row with `started_utc = NOW()` (younger than threshold) is **not** reclaimed on start.
- A `running` row with `started_utc = NOW() - 10 min` **is** reclaimed (set `failed`, `error_code='orphaned_restart'`).
- A `cancelled` row is never touched (predicate is `state_code='running'`).
- With the setting at its default, behavior matches "reclaim jobs older than 5 minutes."

**Edge cases / failure behavior.** Setting absent on an old config object → `getattr` default 300. Clock
skew between app and DB → predicate uses DB `NOW()` on both sides (no app clock involved). A genuinely
orphaned but *recently created* job (< 5 min) survives one restart; it will be reclaimed on the next
restart after it ages past the threshold, or completed/failed normally — acceptable (conservative).

**Verification.**
- Local: extend `tests/test_dispatcher_reclaim.py` — assert the UPDATE query string now contains
  `started_utc <` and the interval bind; add a `test_config.py` assertion for the new default.
- Live (after deploy): verify a restart immediately after enqueuing a job does not flip it to `failed`.

---

## B3 — Fix `register_repository` NOT-NULL columns  **[SHARED]**

**Problem.** `register_repository` (`server.py:6156-6169`) inserts only
`(repository_key, name, origin_url)`, but migration 016
(`016_mawf_contract.py:143` and `:144`) made `catalog.repositories.mawf_repository_id` and `status_id`
NOT NULL with no DEFAULT (line 145 is the follow-on unique index, not a constraint). So every call hits a
NOT-NULL constraint violation (audit X-5 — "confirmed live this session"); only the MAWF
`mawf_upsert_repository` path supplies them.

**Exact change.**
- `src/memory_knowledge/server.py`, `register_repository` (the `INSERT` at lines 6157–6169):
  - Before the insert, resolve the active status id (mirror `admin/mawf.py:529`): import and call
    `from memory_knowledge.admin.mawf import _reference_id` →
    `status_id = await _reference_id(pool, "REPOSITORY_STATUS", "active")`.
    (`_reference_id` resolves `REPOSITORY_STATUS`/`active` to its `core.reference_values.id`; the `active`
    value is seeded by migration 016 line 62 — the `REPO_ACTIVE`/`active` row; line 63 is the `inactive` row.)
  - Replace the INSERT with (mirroring `admin/mawf.py:533-546`):
    ```
    INSERT INTO catalog.repositories
        (mawf_repository_id, repository_key, name, origin_url, status_id)
    VALUES (gen_random_uuid(), $1, $2, $3, $4)
    ON CONFLICT (repository_key) DO UPDATE
        SET name = EXCLUDED.name,
            origin_url = EXCLUDED.origin_url,
            updated_utc = NOW()
    RETURNING id, (xmax = 0) AS is_insert
    ```
    Bind `$4 = status_id`. (On update we intentionally do **not** overwrite `mawf_repository_id`/`status_id`
    — preserve any MAWF-owned values; only insert sets them. This keeps the brain's path non-destructive to
    MAWF-registered rows.)
  - The reference-type trigger `trg_repositories_reference_types` (016 line 229) validates `status_id`
    belongs to `REPOSITORY_STATUS` — satisfied by `_reference_id` resolution.

**Acceptance criteria (testable).**
- `register_repository("taggable-database", "taggable-database")` succeeds (no constraint violation) and the
  new row has non-null `mawf_repository_id` and a `status_id` resolving to `REPOSITORY_STATUS/active`.
- Re-calling `register_repository` for an existing key updates `name`/`origin_url`/`updated_utc` and leaves
  `mawf_repository_id`/`status_id` unchanged.
- The returned `data.created` flag is True on first insert, False on update (xmax check preserved).

**Edge cases / failure behavior.** `REPOSITORY_STATUS/active` reference value missing (pre-016 DB) →
`_reference_id` raises `ValueError`; surface it as the tool's error result (deploys run post-016, so this is
defensive only). Existing MAWF-registered repo → update path preserves MAWF columns. Remote write guard
honored (already present at `server.py:6150`).

**Verification.**
- Local: `pytest tests/` for any `register_repository` test (add one asserting both columns set); or a unit
  test with a fake pool capturing the INSERT column list.
- Live (after deploy): call `register_repository` for an unregistered Codex repo (e.g. `united-partners`),
  then `SELECT mawf_repository_id, status_id FROM catalog.repositories WHERE repository_key='united-partners'`
  → both non-null. (This also unblocks the A2 operational follow-up of registering the missing repos.)

---

## Non-functional: security / secrets

No secret, credential, API key, or token is introduced by any item in this plan (repo Guard Rail: "No
credentials, API keys, or secrets in any file"). Specifically:
- The new A3 files (`hydrate_repo_memory.py`, `inject-repo-memory.sh`) take **no** secrets: the brain
  endpoint and tunables come from overridable env vars only (`CLAUDE_CORPUS_MCP_URL`,
  `CLAUDE_REPO_HYDRATE_*`), exactly as `hydrate_corpus.py` / `inject-corpus.sh` already do; auth (if any) is
  whatever the existing MCP client transport already uses, unchanged.
- A4's `SKILL.md` is copied verbatim from the in-repo `auto-capture.skill.md` (no secret content).
- A5's `MK_SPARK_REPOS` is a plain repo-name list — not a secret — exported in `weekly-review.sh`.
- The B-tier server changes (`cancel_job`, reclaim age-gate, `register_repository`) add no new credentials;
  DB access uses the existing pool.
**Acceptance:** `git grep -nE '(secret|token|api[_-]?key|password|BEGIN .* PRIVATE KEY)'` over the added
files returns no literal credential. New hook/skill/env files are reviewed to contain only paths, env-var
names, and repo names.

---

## Sequencing & deploy plan

**Phase 1 — server-side code (one Azure deploy):** implement A1, A2, B1, B2, B3 together (all in `src/`),
run the full local test suite, then **one** `infra/azure-push.sh` deploy. Order within the branch:
B3 first (unblocks registering repos), then A1, then A2 (depends on A1's canonical resolution), then B1+B2
(independent of A1/A2). They share no conflicting lines.
- **Needs Azure deploy:** A1, A2, B1, B2, B3.

**Phase 2 — local workstation (no deploy):** after Phase 1 is live —
- A3: add `hydrate_repo_memory.py` + `inject-repo-memory.sh`; register the second `UserPromptSubmit` hook in
  `~/.claude/settings.json`; set `MK_REPO_HYDRATE=1`.
- A4: install `~/.codex/skills/auto-capture/SKILL.md`; update `SETUP-codex.md` / `SETUP-autocapture.md`.
- A5: export `MK_SPARK_REPOS` (Locked Decision 7) in `weekly-review.sh`; add the candidate-surfacing print in
  `weekly_review.py`.
- **Needs Azure deploy:** none (A3 calls already-deployed `run_retrieval_workflow`; A5 surfacing edit is in a
  locally-run script).

**Phase 3 — operational follow-up (no code):** using the now-fixed `register_repository` (B3), register the
missing Codex repos (taggable-database, united-partners, agentic-trading, mcp-agents-workflow,
memory-knowledge) so A2 capture works there. **Register notes-only / personal repos with `origin_url = NULL`**
(SGAP-002 mechanism 1) so the freshness scheduler never auto-ingests them; supply an `origin_url` only for a
repo you deliberately want full-ingested. **Confirm the live `ingestion_scheduler_enabled` value and the
`ingestion_scheduler_repo_allowlist` in the Azure deploy** and record it; if the scheduler is enabled and any
notes-only repo must carry an `origin_url`, ship the §A2 defense-in-depth enumeration filter (SGAP-002
mechanism 2) in the Phase-1 deploy. Optionally run the weekly job once (audit P1-5).

**Branching/commits:** work on a feature branch (e.g. `capture-and-jobs-fixes`); commit per item with
plain messages (no AI attribution). Do not push/deploy until Kamen asks.

---

## Rollback

- **A1/A2 (repo_note.py):** revert the file; the synthetic `__note_anchor__` revisions and any notes anchored
  to them remain valid data. A synthetic revision with no files is inert for source retrieval and for
  `branch_heads`-keyed readers, but the SGAP-001 sentinel filter in `freshness_audit.py`/`repair_drift.py`
  should be kept (or those repos not integrity-audited) even after a `repo_note.py` revert, since the
  synthetic rows persist. No migration to undo.
- **B1 (guard/worker/tool):** revert the three files. Any rows already in `cancelled` are terminal and inert;
  they will simply never be picked up (which is the desired end state regardless). No data migration.
- **B2 (config/dispatcher):** revert; reclaim returns to threshold-less behavior. No data change.
- **B3 (server.py):** revert; registration returns to broken (so only roll back if a regression appears —
  the fix is strictly additive to the INSERT). Rows created with the fix are valid.
- **A3/A4/A5 (local):** remove the new hook/skill/env; delete `hydrate_repo_memory.py` /
  `inject-repo-memory.sh`; un-register the hook. No server impact.
- **Deploy rollback:** `infra/azure-push.sh` redeploys; to roll back, redeploy the prior image tag
  (`--tag <previous>`).

---

## Test plan

**Local unit/integration (run before deploy):** `pytest` over the repo, with these additions/assertions —
- `tests/test_repo_note.py`: (A1) author with `FCSAPI`/`FcSaPi`/`fcsapi` resolves to one canonical key and
  one upserted record; deactivate by mixed case; unknown repo errors. (A2) no-revision repo auto-creates a
  `__note_anchor__` revision and writes zero files/chunks; `auto_create_revision=False` still raises.
- (SGAP-001) integrity sentinel filter: `tests/` for `freshness_audit.check_freshness` and
  `repair_drift.rebuild_revision` — a repo whose only revision is `__note_anchor__` returns the
  no-real-revision branch (`latest_pg_commit is None` / "No revisions found"), and the latest-revision
  SQL contains `commit_sha <> '__note_anchor__'`.
- (SGAP-002) freshness-scheduler exclusion: if mechanism 2 is shipped, `tests/` asserting
  `ingestion_scheduler._ENUMERATE_SQL` excludes a repo whose only revision is the sentinel (or that a
  null-`origin_url` repo is not enumerated).
- `tests/test_dispatcher_reclaim.py`: (B2) reclaim UPDATE includes the `started_utc <` age predicate; young
  job not reclaimed, old job reclaimed.
- `tests/test_config.py`: (B2) `reclaim_running_min_age_seconds` default == 300.
- New guard test: (B1) `running→cancelled` allowed, `cancelled→*` rejected; worker aborts when state is
  `cancelled` and does not attempt a `failed`/`completed` transition.
- New register test: (B3) INSERT supplies `mawf_repository_id` + `status_id`; conflict-update preserves them.
- (A5) `weekly_review.py` candidate-surfacing: with a fixture `spark-candidates.md`, the summary line reports
  the correct count and path; empty/missing file → "none this run".

**Local script dry-runs (Phase 2):**
- A3: piped-stdin dry run of `hydrate_repo_memory.py` (opt-in on/off, fail-open on bad URL).
- A4: confirm the skill file lands and lists.
- A5: run `weekly_review.py --date <today>` with `MK_SPARK_REPOS` set; grep the `spark-candidates:` line.

**Live smoke (after deploy):** A1 author+retrieve under `FCSAPI`; A2 note on a registered-not-ingested repo
+ verify zero files; B1 start+cancel ingestion + confirm no resume; B3 register a missing repo + verify both
columns; A3 fresh-session repo-memory block.

---

## Open questions

**None blocking.** All design choices are locked above. One **optional operational decision** for Kamen
(not required to build): whether Phase 3 should also **run the weekly job once now** (audit P1-5) to prove
the cadence — this is an ops action, not part of the code change, and can be done any time after Phase 2.
