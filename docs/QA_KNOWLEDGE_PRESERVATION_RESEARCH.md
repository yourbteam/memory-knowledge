# Preserving & Hydrating Requirements-Refinement Q&A — Research & Design

**Status:** Research / design (no code yet). Basis for a later granular implementation plan.
**Goal:** Capture the question/answer pairs accumulated during the bug/feature implementation process (requirements refinement in the **mcp-agents-workflow / MAWF** system) as durable, searchable **domain knowledge** in memory-knowledge, and **hydrate** relevant prior Q&A when a new question arrives.
**Method:** Grounded in a 4-agent exploration of memory-knowledge (storage, retrieval, data model) and a direct exploration of the MAWF source repo. All claims carry `file:line` references.

---

## Locked decisions (from the requester)

1. **Source:** the Q&A comes from the **MAWF** requirements-refinement flow (not GitHub issues, not manual docs).
2. **Scope:** **per-repository** (Q&A is filtered to the asking repo, like `code_chunks`). No cross-repo/global store.
3. **Curation:** **trust-on-ingest** (active & searchable immediately; no verify/approve gate).
4. **Hydration UX:** **phased** — a standalone search tool now, fold into the route policy later.

These simplify the design substantially: per-repo scope means Q&A uses the standard `repository_key` filter; and because the store is **standalone** (its own `qa_pair_id`, no `catalog.entities` row — F0), there is no global-repo or `repo_revision_id` concern at all. Trust-on-ingest means no propose→verify lifecycle.

---

## Executive summary

- **The integration channel already exists.** MAWF ships a full MCP client to memory-knowledge (`mcp-agents-workflow/src/workflow_orch/knowledge_client.py:79` `MemoryKnowledgeClient`). Ingestion is therefore a **push**: add one MCP tool on the memory-knowledge side and MAWF calls it. No new transport, pull job, or polling.
- **The Q&A is already structured at the source.** MAWF's intake phase produces `answeredQuestionsByNode` — each entry is `{id (questionId), node, text (question), answerText, answeredInSequence}` — and the intake session carries a **`repository_key`** (`mcp-agents-workflow/src/workflow_orch/intake.py:235-293, 612`). That maps directly onto memory-knowledge's per-repo model.
- **Storage:** a **dedicated, standalone `qa_pairs` store** (one `memory.qa_pairs` table keyed by its own deterministic `qa_pair_id UUID` + a `qa_pairs` Qdrant collection), modeled exactly on the `triage_cases` precedent — *not* `learned_records` (mandatory code-evidence coupling) and **not** the `catalog.entities`/`entity_key` model (which requires a `repo_revision_id` Q&A doesn't have). See F0/F1 for the binding schema.
- **Hydration:** clone the proven **`search_triage_cases`** machinery into `search_qa_knowledge` (Phase 1), then optionally fuse Q&A into the route policy for "how/why" questions (Phase 2).

---

## Part A — What exists (grounded findings)

### A1. The closest analog — `learned_memory` — and why it does *not* fit as-is
`memory.learned_records` + the `learned_memory` Qdrant collection have the right *lifecycle* (propose→verify→commit→supersede, dual PG+Qdrant projection, `is_active`/`verified` gating — `workflows/learned_memory.py:50-341`), but three structural mismatches make reuse costly:

- **Mandatory code evidence.** `memory.learned_records.evidence_entity_id` and `evidence_chunk_id` are **NOT NULL** (`migrations/versions/001_initial_schema.py:327,333`) and enforced in `run_proposal` (`workflows/learned_memory.py:104-113`) — every record must point at an ingested *code chunk*. Q&A provenance is a task/issue/thread, not code. **This is the single biggest blocker.**
- **Closed type + single body.** `memory_type` is a hardcoded enum of code-intelligence categories (`learned_memory.py:29-36`); only `body_text` is embedded (`projections/learned_memory_qdrant.py:24`) — no first-class question/answer separation.
- **Wrong freshness model.** Validity is commit-revision-based (`valid_to_revision_id`, `lifecycle/staleness_checker.py:11-46`), not time/task-based.

### A2. The right precedent — `triage_cases`
`triage_cases` is a *dedicated table + dedicated Qdrant collection + repo-scoped projection* (`migrations/versions/010_triage_memory.py`, `triage_memory.py`). It is the established pattern for "store records keyed by a prompt and retrieve the ones similar to an incoming prompt," with:
- semantic search over a per-record collection embedding the prompt text (`triage_memory.py:search_triage_cases:708`),
- a `min_similarity` threshold (0.65) and time-based `_recency_score` (`:122-131`),
- an **optional** `repository_key` filter (`_qdrant_filter:681`) — i.e. it already supports cross-repo, but we will *require* `repository_key` for Q&A per the locked per-repo decision.

### A3. The retrieval / hydration path
The main fused retrieval (`workflows/retrieval.py:run:628`) queries **only `code_chunks` + `summary_units`**, each hard-filtered on `repository_key` AND `is_active` (`retrieval.py:179-190`), fused with scaled **RRF** (`rerank_results:300`, K=60), then hydrated from PG by `entity_key` (`assemble_context_bundle:371-467`, which **discards non-UUID entity_keys** — a hydration gate to note). The `learned_memory` collection is **never queried semantically** — learned rules reach answers only via PG/Neo4j by file scope (`context_assembly._fetch_applicable_learned_rules:21-79`).

**Route policy** (`routing.route_policies`, recalibrated for bge-base in `024_route_policy_recalibrate.py`): an incoming prompt is classified (`routing/prompt_feature_extractor.py:42`) into `exact_lookup | conceptual_lookup | impact_analysis | pattern_search | decision_history | mixed`. "How does X work" → **`pattern_search`**; "why was Y decided" → **`decision_history`**; both → **`mixed`**. All three have `semantic_assist_enabled=TRUE`, so a vector search already runs for them — the natural Phase-2 insertion point for Q&A.

**MCP entry points:** `run_retrieval_workflow` (`server.py:173`), `run_context_assembly_workflow` (`:194`, the richest "ask → context" tool), `search_triage_cases` (`:1475`, the semantic-over-past-prompts template).

### A4. The data model & embedding
- `catalog.entities` (`001:81-90`): `entity_key UUID UNIQUE`, `entity_type VARCHAR(50)` (**free text — no enum/CHECK**, so a new `qa_pair` type needs zero migration), `repository_id` and `repo_revision_id` **NOT NULL**.
- `entity_key` is deterministic **UUIDv5** under a fixed namespace (`identity/entity_key.py:6`); the learned-record key is **commit-independent** (`learned_record_entity_key:34` = `repo_key:memory_type:title_hash`) — the right shape for Q&A (not tied to a commit).
- Qdrant: `COLLECTIONS` (`db/qdrant.py:11-17`); `ensure_collections` only **creates** missing collections and applies the standard payload indexes (`repository_key`, `is_active`, `commit_sha`, `branch_name`, `file_path`, …) at 768-dim / COSINE (`:40-62`) — additive and safe. Payloads use a `content_kind` discriminator (`projections/qdrant_payload_schemas.py`).
- Embedding is self-hosted fastembed `BAAI/bge-base-en-v1.5` (768-dim) via `llm/openai_client.embed` → `local_embed` (`config.py:57-59`).

### A5. The MAWF integration (both sides)
**memory-knowledge already models the MAWF planning hierarchy:** `planning.{projects,features,tasks}` with `{project,feature,task}_repositories` join tables and `{...}_external_links` (issues/PRs) (`migrations/versions/…` create-table set), `ops.mawf_prompts` (refined task prompts, with `supersedes_prompt_id`/`correction_note` — `:150-159`), `planning.tasks.prompt_id`, `admin/mawf.py`. The "clarification" MCP tools (`get_required_clarification_policy` `server.py:1766`) are **routing policy** (what to ask, derived from triage feedback) — *not* a Q&A content store. So the Q&A content itself is **not yet in memory-knowledge**.

**MAWF (source) holds the Q&A:**
- `MemoryKnowledgeClient` (`knowledge_client.py:79`) — MCP/JSON-RPC-over-HTTP client to memory-knowledge, KV-authed (`settings.memory_knowledge.secret_name`), with `initialize`/`_send_jsonrpc`/session handling. **This is the ready-made push channel.**
- `intake.py` captures Q&A per workflow node: questions `{id, text, node}` (`:243-248`), answers as entries `{id, node, text (question), answerText, answeredInSequence}` (`:286-292`, answer built from `answer.get("text")` at `:290`), finalized via `_finalize` (`:323`) into `answeredQuestionsByNode = {node_key: [entry, …]}` (`:333`); `open_questions_by_node` tracks unanswered. The intake session carries `repository_key` (`:612`).

---

## Part B — Recommended design

### B1. Preserve — a dedicated, standalone, per-repo `qa_pairs` store
Patterned on `triage_cases` (a standalone table keyed by its own UUID + a dedicated collection), **not** `learned_records` (code-evidence coupling) and **not** the `catalog.entities`/`entity_key` model (`repo_revision_id NOT NULL`, which Q&A lacks — F0).

- **PG:** one `memory.qa_pairs` table keyed by a deterministic **`qa_pair_id UUID`** — **no `catalog.entities` row, no `entity_id`, no `entity_key`.** Columns: `repository_id` (NOT NULL FK), `feature_key`, `task_key`, `question`, `answer`, `question_hash`, `question_tsv`, `source JSONB`, `confidence`, `is_active`, `superseded_by` (reserved; unused in the v1 overwrite model), `created_utc`/`updated_utc`. **The binding DDL is F1.**
- **Identity & supersession:** `qa_pair_id = uuid5(NAMESPACE_MK, "qa:{repository_key}:{question_hash}")` (deterministic, commit-independent). Re-answering the same question maps to the same `qa_pair_id` and the same Qdrant point id → **overwrite (latest answer wins)**; no `is_active` flip, no orphan points (F8).
- **Provenance (`source` JSONB), canonical:** `{session_key, feature_key, task_key, node_key, question_id}` (all from the intake session/event — F5). Used everywhere in this doc.
- **Qdrant:** add `"qa_pairs"` to `COLLECTIONS` → auto-gets 768/COSINE + standard indexes. `QAPairPayload = {qa_pair_id, repository_key, feature_key, is_active, content_kind:"qa_pair"}`; **point id = `qa_pair_id`. Embed the question** (locked — Part C #1).

### B2. Ingest — a push MCP tool MAWF already can call
- New tool `ingest_qa_pairs(repository_key, pairs, source?)` on memory-knowledge — `pairs` is a list of `{question, answer, source?}`; the top-level `source` carries batch-level provenance (`session_key`/`feature_key`/`task_key`) merged into each pair's per-pair `source` (`node_key`/`question_id`). Exact contract: F4.
- MAWF's `knowledge_client` calls it when intake answers are finalized (`intake.py` `answeredQuestionsByNode`), using the intake's `repository_key`. Unknown `repository_key` → the tool returns a `status="error"` result (no silent drop), matching the `save_triage_case` precedent (`triage_memory.py:547`).
- Trust-on-ingest → write PG + embed the question + upsert the Qdrant point, active immediately. Idempotent via the deterministic `qa_pair_id`; a changed answer for the same question **overwrites** (same row, same point — F8).

### B3. Hydrate — phased
- **Phase 1 (standalone tool):** `search_qa_knowledge(repository_key, question, limit=5, min_similarity=0.65)` — clone `search_triage_cases` but **require** `repository_key`; embed the incoming question, vector-search `qa_pairs` with `repository_key`+`is_active` filter, return matched `{qa_pair_id, question, answer, confidence, source, score}` (F2). MAWF calls it during a *new* task's intake (closed loop: prior answers pre-inform new clarifying questions); any agent/MCP caller can use it too.
- **Phase 2 (route-policy fusion):** add a `qa_assist_enabled` boolean to `routing.route_policies` (mirroring `semantic_assist_enabled`), TRUE for `pattern_search`/`decision_history`/`mixed`; add a `qa_qdrant_search()` in `retrieval.py` and fuse it into `rerank_results` as a weighted source (weight ≈ summary's 0.8, capped to top 3–5 so it can't crowd code evidence). Note the two obstacles: the standard Qdrant helper hard-filters `repository_key` (fine here, since per-repo) and the PG hydration gate discards non-UUID keys (Q&A needs its own hydration branch or full text in payload).

### B4. The closed loop
intake (MAWF) captures Q&A → `ingest_qa_pairs` → `memory.qa_pairs` → next task's intake calls `search_qa_knowledge` and surfaces the prior answer. Domain knowledge compounds per repo over time.

---

## Walkthrough — practical scenarios (end-to-end)

Concrete examples using `taggable-server` as the repo. They show the actual data flowing through each component.

### Scenario A — Capturing knowledge (ingest)
An engineer runs a **bug fix** through MAWF. During intake the workflow asks a clarifying question:

> **Q (node `analysis`):** "When a tag is deleted, what should happen to assets that *only* had that tag?"
> **A (human):** "They become untagged but are NOT deleted — they show in the 'Untagged' smart folder. Hard-deleting a tag is blocked if more than 500 assets reference it."

On intake finalize, MAWF's existing `MemoryKnowledgeClient` makes one call (top-level `source` = batch provenance; per-pair `source` = node/question):
```
ingest_qa_pairs(repository_key="taggable-server",
  source={ session_key: "S-99", feature_key: "F-12", task_key: "T-4821" },
  pairs=[
   { question: "When a tag is deleted, what happens to assets that only had that tag?",
     answer:   "Untagged, not deleted; appear in 'Untagged' smart folder. Hard-delete blocked if >500 assets reference the tag.",
     source:   { node_key: "analysis", question_id: "q3" } }])
```
memory-knowledge computes `qa_pair_id = uuid5(NAMESPACE_MK, "qa:taggable-server:"+question_hash)` → writes the `memory.qa_pairs` row (merged `source = {session_key,feature_key,task_key,node_key,question_id}`) → embeds the **question** → upserts an active Qdrant point (id = `qa_pair_id`) scoped to `taggable-server`. Knowledge preserved; no verification step (trust-on-ingest).

### Scenario B — The payoff: reuse weeks later (closed loop)
A *different* engineer starts a **new feature** ("bulk tag cleanup"). Before asking the human, intake calls:
```
search_qa_knowledge(repository_key="taggable-server",
                    question="If we remove a tag during cleanup, do the assets get deleted too?")
```
The new question is phrased differently but matches semantically. Returned:
```
[{ qa_pair_id: "…", score: 0.83, confidence: 0.80,
   question: "When a tag is deleted, what happens to assets that only had that tag?",
   answer:   "Untagged, not deleted; ... Hard-delete blocked if >500 assets reference the tag.",
   source:   { session_key:"S-99", feature_key:"F-12", task_key:"T-4821", node_key:"analysis", question_id:"q3" } }]
```
MAWF surfaces this as known domain knowledge / pre-fills the answer instead of re-asking. The bug-fix answer is reused.

### Scenario C — Knowledge evolves (overwrite)
Later the policy changes (500 → 1,000). A new task re-answers the same question. Because `qa_pair_id = uuid5(NAMESPACE_MK, "qa:{repo}:{question_hash}")` is deterministic, the ingest lands on the **same row and the same Qdrant point** → the answer is **overwritten** (latest wins; no `is_active` flip, no orphan point — F8). Searches return only the current truth.

### Scenario D — An engineer or agent asks directly (no MAWF)
`search_qa_knowledge` is a plain MCP tool, callable from an IDE, a Claude agent, or CI:
> "How does taggable handle bulk tag operations — is it transactional?"

→ returns the preserved Q&A: *"Bulk tag/untag must be all-or-nothing in one DB transaction; partial application caused the duplicate-tag incident in March."* — domain knowledge that lives nowhere in code comments.

### Scenario E — Phase 2: auto-surface in normal retrieval
After folding Q&A into the route policy, no special tool is needed:
```
run_context_assembly_workflow(repository_key="taggable-server",
                              query="why are tag deletes blocked sometimes?")
```
→ classified `decision_history` ("why…") → the fused bundle **automatically includes** the relevant Q&A alongside code chunks and summaries, ranked together via RRF.

### Boundaries (what it deliberately is *not*)
- **Per-repo only** — `taggable-server` Q&A won't surface for `fcsapi`. Multi-repo features file Q&A under the intake's repo.
- **Trust-on-ingest** — whatever the refinement process answered becomes knowledge; quality rests on that process (mitigated by supersession + confidence, and a future feedback signal).
- **MAWF is the source** — capture is via the agents-workflow intake, not GitHub/doc scraping (possible later sources).

---

## Part C — Locked design decisions (resolved; implemented by Part F)
These were open during exploration and are now **locked**; Part F implements them, so the implementation plan inherits them with no further decisions to make.
1. **Embedding target = the question only** (best question↔question matching). Implemented in F2 (`embed_single(question, settings)`) / F8.
2. **Ingest granularity = per task** — one `ingest_qa_pairs` call carries all of a task's answered Q&A (F5 Option A).
3. **Provenance `source` = `{session_key, feature_key, task_key, node_key, question_id}`** (F1/F5). Linking the GitHub issue/PR via `planning.task_external_links` is **out of scope for v1** (future extension).
4. **Supersession = overwrite** — re-answering the same question (same deterministic `qa_pair_id`) overwrites in place (F8). An *edited* question (new `question_hash` → new `qa_pair_id`) creates a new row/point; the prior remains until compaction (accepted — Part D).

---

## Part D — Risks & considerations
- **Answer quality / noise:** trust-on-ingest means a wrong or speculative refinement answer becomes "knowledge." Mitigation: confidence field + supersession + (future) a lightweight feedback signal like triage's. Acceptable per the locked decision; worth revisiting if noise shows.
- **Question phrasing variance:** the same domain question asked differently won't dedupe (different `question_hash`). This is fine for retrieval (semantic search still matches) but can accrete near-duplicates; periodic compaction or an embedding-similarity dedupe is a later option.
- **Hydration gate:** the existing `assemble_context_bundle` discards non-UUID `entity_key`s — Phase 2 fusion needs a dedicated Q&A hydration path (Phase 1 standalone tool avoids this entirely).
- **MAWF coupling:** ingestion depends on MAWF's intake calling the new tool; the `MemoryKnowledgeClient` exists but the *call site* in `intake.py` is a MAWF-side change (cross-repo work).
- **Scope vs reality:** per-repo is the locked decision, but MAWF features/tasks can span repos (`feature_repositories`). A Q&A captured for a multi-repo feature will be ingested under the intake's `repository_key`; if that proves limiting, project/feature-scoped retrieval is a future extension (the planning hierarchy already supports it).

## Part F — Implementation research (one-shot detail)

Deep dive into the exact code patterns to clone, with `file:line` grounding. **Two findings here revise Part B:**

### F0. Two discoveries that simplify the build

1. **No entity coupling (revises B1).** The `triage_cases` precedent does **not** create a `catalog.entities` row, use `entity_key`, or touch revisions — it is a standalone table keyed by its own `triage_case_id UUID`, and the Qdrant point id is that same UUID (`triage_memory.py:427-431`, `save_triage_case:518-617`). This matters because `catalog.entities.repo_revision_id` is **NOT NULL** (`001:87`) and Q&A has no revision — so the entity route from B1 would force a synthetic revision. **Adopt the triage model:** `qa_pairs` is a standalone table with its own `qa_pair_id UUID` (deterministic — see F8); no `entity_type='qa_pair'`, no `entity_key`, no `repo_revision_id`. This removes the only real schema friction.

2. **The Q&A transcript is already persisted (revises ingestion).** memory-knowledge has a full intake subsystem — `ops.intake_sessions / intake_events / intake_distilled_context / intake_draft_revisions` (`migrations/versions/015_intake_sessions.py`), driven by `admin/intake.py` (`create_session:47`, `append_event:84`, `update_distilled_context:284`, `save_draft_revision:360`, `finalize_session:506`) and MCP tools `create_intake_session` (`server.py:4324`), `append_intake_event` (`:4370`), `get_intake_session_state` (`:4420`). MAWF already drives these — its `intake.py` "treats memory-knowledge as the durable source of truth." `ops.intake_events` is the immutable transcript (`session_key, sequence, role ∈ {user,assistant,system,tool}, event_type VARCHAR(80) (free-form), content_text, content_json`), scoped on the session by `repository_key/project_key/feature_key/task_key`. **So this feature is a projection + search layer over existing intake data, not a new transport.**

### F1. Schema — migration `026_qa_pairs.py` (head is currently `025`)
```sql
CREATE TABLE IF NOT EXISTS memory.qa_pairs (
    qa_pair_id      UUID PRIMARY KEY,                       -- deterministic uuid5 (F8); = Qdrant point id
    repository_id   BIGINT NOT NULL REFERENCES catalog.repositories(id),
    feature_key     VARCHAR(255),                           -- from source; mirrored to Qdrant payload for filtering
    task_key        VARCHAR(255),                           -- from source; stored only (NOT a Qdrant filter — GAP-006)
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    question_hash   TEXT NOT NULL,                          -- sha256 of the normalized question (F2)
    question_tsv    TSVECTOR,                               -- populated on write (F2); lexical fallback
    source          JSONB NOT NULL DEFAULT '{}'::jsonb,     -- canonical {session_key,feature_key,task_key,node_key,question_id}
    confidence      NUMERIC(3,2) NOT NULL DEFAULT 0.80,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    superseded_by   UUID REFERENCES memory.qa_pairs(qa_pair_id),  -- reserved; unused in v1 overwrite model (F8)
    created_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX ux_qa_pairs_repo_qhash ON memory.qa_pairs(repository_id, question_hash);
CREATE INDEX ix_qa_pairs_repo_active ON memory.qa_pairs(repository_id) WHERE is_active;
CREATE INDEX ix_qa_pairs_qtsv ON memory.qa_pairs USING GIN (question_tsv);
```
(`memory` schema already exists — `learned_records` lives there. Migration style: `op.execute("""…""")`, `revision="026_qa_pairs"` / `down_revision="025_ingestion_checkpoints"`.)

### F2. New module `src/memory_knowledge/qa_memory.py` (clone of `triage_memory.py`)
Mirror these triage functions, swapping table/collection/fields. **Deliberate deviation from the triage clone:** the point id is a *deterministic* `uuid5`, **not** triage's random `uuid.uuid4()` (`triage_memory.py:550`) — this is what makes ingest idempotent (F8). Do not copy the `uuid4()` line.

- `_resolve_repository_id(pool, repository_key)` — copy `triage_memory.py:397` (returns `None` if unknown).
- `_normalize_question(q)` = `" ".join(q.strip().lower().split())` (lowercase, trim, collapse every run of whitespace to a single space). `_question_hash(q)` = `hashlib.sha256(_normalize_question(q).encode()).hexdigest()` (same `sha256` pattern as `_prompt_hash:86`, **but hash the *normalized* question — `_prompt_hash` hashes raw text and must not be reused as-is**).
- `_qa_pair_id(repository_key, question_hash)` = `uuid.uuid5(NAMESPACE_MK, f"qa:{repository_key}:{question_hash}")` (import `NAMESPACE_MK` from `identity/entity_key.py:6`).
- `_qa_payload_from_row(row)` / `_qa_point_from_row(row, embedding)` — copy `:405-431`; payload = `{qa_pair_id, repository_key, feature_key, is_active: True, content_kind: "qa_pair"}`. **`task_key` is stored in PG only — not in the payload** (it is not a Qdrant filter field; GAP-006/F3).
- `_qdrant_filter(*, repository_key, feature_key=None)` — copy `:681`; **always** include `repository_key` (MatchValue) + `is_active=True`; optionally `feature_key`. **No `task_key`** (unindexed in Qdrant).
- `ingest_qa_pairs(pool, settings, *, repository_key, pairs, source=None, qdrant_client) -> dict` — modeled on `save_triage_case:518-617`:
  1. `repository_id = _resolve_repository_id(...)`; if `None` → `raise ValueError(f"Repository '{repository_key}' not found")` (precedent `triage_memory.py:547`; surfaced as `status="error"` by the MCP layer).
  2. For each `pair`: `q, a = pair["question"], pair["answer"]`; if either is blank → append `{"question": q, "reason": "empty question/answer"}` to `skipped` and continue. Merge provenance: `eff_source = {**(source or {}), **(pair.get("source") or {})}` (batch defaults, per-pair overrides).
  3. `qh = _question_hash(q)`; `qid = _qa_pair_id(repository_key, qh)`; `feature_key = eff_source.get("feature_key")`, `task_key = eff_source.get("task_key")`.
  4. PG upsert (single statement): `INSERT INTO memory.qa_pairs (qa_pair_id, repository_id, feature_key, task_key, question, answer, question_hash, question_tsv, source, confidence) VALUES ($1,$2,$3,$4,$5,$6,$7, to_tsvector('english',$5), $8::jsonb, 0.80) ON CONFLICT (repository_id, question_hash) DO UPDATE SET answer=EXCLUDED.answer, feature_key=EXCLUDED.feature_key, task_key=EXCLUDED.task_key, source=EXCLUDED.source, updated_utc=NOW()`. (`question`/`question_tsv` are intentionally **not** refreshed on conflict — the normalized `question_hash` is the conflict key, so the stored question is normalized-equivalent; the first-written raw form persists.)
  5. `embedding = await embed_single(q, settings)` (`openai_client.py:120`); `await qdrant_client.upsert(collection_name="qa_pairs", points=[_qa_point_from_row({"qa_pair_id": qid, "repository_key": repository_key, "feature_key": feature_key}, embedding)])`. Wrap embed+upsert in try/except + log (as triage `:604-615`); a Qdrant failure does **not** roll back the PG write (PG is canonical).
  6. Append `qid`; return `{"ingested": len(qa_pair_ids), "qa_pair_ids": [str(x) for x in qa_pair_ids], "skipped": skipped}`.
- `search_qa_knowledge(pool, settings, *, repository_key, question, limit=5, min_similarity=0.65, qdrant_client) -> dict` — modeled on `search_triage_cases:708-795`:
  1. Resolve repo; if unknown → return `{"advisory_only": True, "rows": [], "warnings": ["unknown repository"]}`.
  2. If `qdrant_client` is not None: `qe = await embed_single(question, settings)`; `results = await semantic_query_points(qdrant_client, collection_name="qa_pairs", query_vector=qe, limit=max(limit*5, limit), score_threshold=min_similarity, query_filter=_qdrant_filter(repository_key=repository_key))`; `candidates = [(str(r.id), float(r.score)) for r in results]`.
  3. **Lexical fallback** — **only** when `qdrant_client` is `None` or the semantic call raised (NOT when semantic ran and returned zero — that returns empty, matching `search_triage_cases:762-768`, to avoid surfacing weak keyword matches when semantic correctly found nothing): `SELECT qa_pair_id, ts_rank(question_tsv, plainto_tsquery('english',$2)) AS score FROM memory.qa_pairs WHERE repository_id=$1 AND is_active AND question_tsv @@ plainto_tsquery('english',$2) ORDER BY score DESC LIMIT $3`.
  4. Hydrate: `SELECT qa_pair_id, question, answer, confidence, source FROM memory.qa_pairs WHERE qa_pair_id = ANY($1) AND is_active` — **drop** candidate ids with no active row; attach each row's candidate `score` from the `(id, score)` map built in step 2; **re-sort in Python by score DESC** (PG `= ANY($1)` does not preserve order); take `limit`.
  5. Return `{"advisory_only": True, "rows": [{qa_pair_id, question, answer, confidence, source, score}], "warnings": [...]}` (empty `rows` when nothing matches).
- (Optional, for compaction parity) `reproject_qa_pairs(pool, qdrant, settings, repository_key)` — copy `:460`.

### F3. Qdrant collection
- Add `"qa_pairs"` to `COLLECTIONS` (`db/qdrant.py:11-17`). `ensure_collections` then auto-creates it at **768-dim / COSINE** and applies the standard payload indexes — which **already include `repository_key`, `feature_key`, `is_active`** (`db/qdrant.py:49-61`), so no index changes are needed. **`task_key` is NOT among the indexed fields** (`db/qdrant.py:49-61`), so it is not a Qdrant filter (GAP-006) and lives only in `memory.qa_pairs`. Add a `QAPairPayload` pydantic model in `projections/qdrant_payload_schemas.py` (mirror `LearnedMemoryPayload`): `qa_pair_id, repository_key, feature_key (optional), is_active, content_kind="qa_pair"`.

### F4. MCP tools (`server.py`) — clone the triage tool pattern (`save_triage_case:1380`, `search_triage_cases:1475`)
```python
@mcp.tool()
@track_tool_metrics("ingest_qa_pairs")
async def ingest_qa_pairs(repository_key: str, pairs: list[dict],
                          source: dict | None = None, correlation_id: str | None = None) -> str:
    # pairs: list of {"question": str, "answer": str, "source"?: {node_key, question_id}}.
    # source (top-level): batch provenance {session_key, feature_key, task_key} merged into each pair (F2/F5).
    # data returned = F2 shape: {"ingested": int, "qa_pair_ids": [...], "skipped": [{question, reason}]}.
    rid = new_run_id(); bind_run_context(rid, correlation_id, "ingest_qa_pairs")
    guard = check_remote_write_guard(get_settings(), "ingest_qa_pairs")   # WRITE tool → guard
    if guard is not None: guard.run_id = str(rid); return guard.model_dump_json()
    try:
        if not str(repository_key or "").strip() or not pairs:
            return WorkflowResult(run_id=str(rid), tool_name="ingest_qa_pairs", status="error", error="repository_key and non-empty pairs are required").model_dump_json()
        data = await _qa_memory.ingest_qa_pairs(get_pg_pool(), get_settings(),
                  repository_key=repository_key, pairs=pairs, source=source or {},
                  qdrant_client=get_qdrant_client())
        return WorkflowResult(run_id=str(rid), tool_name="ingest_qa_pairs", status="success", data=data).model_dump_json()
    except ValueError as exc:   # unknown repository_key (F2 step 1)
        return WorkflowResult(run_id=str(rid), tool_name="ingest_qa_pairs", status="error", error=str(exc)).model_dump_json()
    finally: clear_run_context()

@mcp.tool()
@track_tool_metrics("search_qa_knowledge")
async def search_qa_knowledge(repository_key: str, question: str, limit: int = 5,
                              min_similarity: float = 0.65, correlation_id: str | None = None) -> str:
    rid = new_run_id(); bind_run_context(rid, correlation_id, "search_qa_knowledge")   # READ → no guard
    try:
        if not str(question or "").strip():
            return WorkflowResult(run_id=str(rid), tool_name="search_qa_knowledge", status="error", error="question is required").model_dump_json()
        data = await _qa_memory.search_qa_knowledge(get_pg_pool(), get_settings(),
                  repository_key=repository_key, question=question, limit=limit,
                  min_similarity=min_similarity, qdrant_client=get_qdrant_client())
        return WorkflowResult(run_id=str(rid), tool_name="search_qa_knowledge", status="success", data=data).model_dump_json()
    finally: clear_run_context()
```
Add `from memory_knowledge import qa_memory as _qa_memory` near the other module imports.

### F5. Ingestion trigger — two options
The structured Q&A exists at the source as MAWF's `answeredQuestionsByNode` (`mcp-agents-workflow/src/workflow_orch/intake.py:333`), shaped `{node_key: [{id, node, text (question), answerText, answeredInSequence}, …]}` (`:286-292`, `:323`), and as `ops.intake_events` on the memory-knowledge side.
- **Option A — explicit push (recommended for one-shot reliability).** MAWF calls `ingest_qa_pairs` at intake finalize, flattening `answeredQuestionsByNode` — iterate `for node_key, entries in answeredQuestionsByNode.items(): for e in entries:` — to `[{question: e["text"], answer: e["answerText"]}]` with per-pair `source={node_key: <map key>, question_id: e["id"]}` and batch `source={session_key, feature_key, task_key}`, `repository_key` from the session (`intake.py:612`; confirm the finalize-path value — F11). No transcript parsing; a clean contract.
- **Option B — finalize hook (zero new MAWF call, more magical).** Extend `admin/intake.py:finalize_session:506` to read the session's answered Q&A (from `intake_events` or `intake_distilled_context`) and call the same `qa_memory.ingest_qa_pairs`. Cleaner UX but couples to MAWF's event_type/content_json conventions (which are free-form `VARCHAR(80)` — must be verified, see F11).
- **Recommendation:** ship **Option A** first (robust, explicit), consider B later once the event conventions are pinned.

### F6. MAWF-side changes (`mcp-agents-workflow`)
- `src/workflow_orch/knowledge_client.py`: add two thin wrappers mirroring `propose_learned_memory:476` / `query_knowledge:408`, both over the existing `call_tool_json` (`:358`):
  `ingest_qa_pairs(repository_key, pairs, source)` → `call_tool_json("ingest_qa_pairs", {...})`;
  `search_qa_knowledge(repository_key, question, limit, min_similarity)` → `call_tool_json("search_qa_knowledge", {...})`.
- `src/workflow_orch/intake.py`: at finalize (where `answeredQuestionsByNode` is produced, `:333`), call the ingest wrapper. Optionally, when generating a new clarifying question, call `search_qa_knowledge` first to pre-surface a prior answer (the closed loop, Scenario B).

### F7. Phase-2 hydration (route-policy fusion) — DEFERRED, out of scope for the v1 implementation plan
This phase is **not** part of the first implementation; the figures below (weights, thresholds) are **indicative**, to be tuned when Phase 2 is actually scoped. The v1 implementation is F1–F6, F8–F12 only.
- Add `qa_assist_enabled BOOLEAN DEFAULT FALSE` to `routing.route_policies` (migration), set TRUE for `pattern_search`/`decision_history`/`mixed` (`024_route_policy_recalibrate.py` is the recalibration precedent).
- In `workflows/retrieval.py`, add `qa_qdrant_search()` mirroring `qdrant_summary_search` and fuse into `rerank_results:300` as a weighted source (weight ≈ summary's 0.8, cap top 3–5). **Watch:** `assemble_context_bundle:381-388` discards non-UUID `entity_key`s, so Q&A needs a dedicated hydration branch or full text carried in the Qdrant payload (Phase-1 standalone tool sidesteps this entirely).

### F8. Idempotency & supersession
- `qa_pair_id = uuid5(NAMESPACE_MK, f"qa:{repository_key}:{question_hash}")` (reuse `identity/entity_key.py:6 NAMESPACE_MK`). Deterministic → re-answering the **same** question hits the same row (`ON CONFLICT (repository_id, question_hash)`) and the same Qdrant point id (upsert overwrites) → **latest answer wins, no orphan points, no accumulation.** This is the recommended simple model (overwrite). If answer *history* is later desired, switch to insert-new + set `superseded_by`/`is_active=False` on the old (the `learned_records` supersession pattern).
- An **edited question** (different `question_hash`) creates a new row/point; the old one remains until compaction. Acceptable; note it.

### F9. Tests (unit, fake pool/qdrant — clone `tests/test_triage_memory.py`)
Clone the fakes from `tests/test_triage_memory.py:13-42`: `FakeQdrant` (`async upsert(self, collection_name, points)` / `async search(**kwargs)`), `QueryPointsQdrant` (`async query_points(**kwargs)` returning objects with `.id`/`.score` — the path `semantic_query_points` takes), `EmptySearchQdrant`, plus its fake pool. Stub the qa SQL (the `INSERT … ON CONFLICT`, the hydrate `SELECT`, the lexical `SELECT`, and `_resolve_repository_id`'s `SELECT id`).
- `qa_memory.ingest_qa_pairs`: writes the row, computes deterministic `qa_pair_id`, embeds+upserts; re-ingest of the same question overwrites (one row, one point).
- `qa_memory.search_qa_knowledge`: builds the right `_qdrant_filter` (requires `repository_key`+`is_active`), thresholds at `min_similarity`, hydrates active rows, returns advisory bundle; empty result → advisory_only with no rows.
- `_question_hash` normalization (trivial phrasing variants collapse).
- MCP tools: `ingest_qa_pairs` honors the write guard; `search_qa_knowledge` rejects empty question.

### F10. File manifest & deploy ordering
**memory-knowledge (create):** `migrations/versions/026_qa_pairs.py`, `src/memory_knowledge/qa_memory.py`, `tests/test_qa_memory.py` (clone `tests/test_triage_memory.py`). **(edit):** `db/qdrant.py` (COLLECTIONS), `projections/qdrant_payload_schemas.py` (QAPairPayload), `server.py` (2 tools + import). **mcp-agents-workflow (edit):** `knowledge_client.py` (2 wrappers), `intake.py` (finalize call). **Deploy:** migration runs on memory-knowledge deploy (creates `memory.qa_pairs`); `ensure_collections` creates `qa_pairs` at startup — both additive, dispatcher/retrieval paths untouched. memory-knowledge ships first; MAWF wiring ships after the tools are live.

### F11. Verification items (confirm during implementation, not blockers)
- The exact MAWF event_type/role strings for question vs answer events in `ops.intake_events` — only needed if choosing Option B (finalize hook); Option A avoids this.
- Whether a MAWF feature/task spanning multiple repos should ingest the Q&A under each repo or just the session's `repository_key` (per-repo decision says the latter; revisit if limiting).
- `check_remote_write_guard` behavior for `ingest_qa_pairs` under the deployment's data-mode (writes are guarded in remote-read mode — confirm the ingest path is allowed in the MAWF-calling context).

### F12. Validation & acceptance
**Unit (memory-knowledge):** `.venv/bin/python -m pytest tests/test_qa_memory.py -q` → all pass (covers F9). Import smoke: `.venv/bin/python -c "import memory_knowledge.qa_memory, memory_knowledge.server"`.
**Migration:** single alembic head after adding `026` — verify the chain head is `026_qa_pairs` (same revision/down_revision scan used for `025`). After deploy: `SELECT to_regclass('memory.qa_pairs') IS NOT NULL` → `true`; `SELECT version_num FROM alembic_version` → `026_qa_pairs`; `feature_key`/`task_key`/`question_tsv` columns present.
**Collection:** after `ensure_collections` at startup, `"qa_pairs" in COLLECTIONS` and a Qdrant `count` on `qa_pairs` returns without error.
**Tools registered:** MCP `tools/list` includes `ingest_qa_pairs` and `search_qa_knowledge`; `git diff --check` clean on edited files.
**End-to-end acceptance:**
1. `ingest_qa_pairs(repo, source={session_key,feature_key,task_key}, pairs=[{question, answer, source:{node_key,question_id}}])` → `{"ingested":1, "qa_pair_ids":[id], "skipped":[]}`; a `memory.qa_pairs` row exists and a `qa_pairs` Qdrant point with `is_active=true`.
2. `search_qa_knowledge(repo, <paraphrase of the question>)` returns that row with `score ≥ 0.65`.
3. Re-`ingest_qa_pairs` of the **same** question with a new answer → still **one** row/point, answer overwritten (F8).
4. `search_qa_knowledge(repo, <unrelated question>)` → `rows: []`.
5. `ingest_qa_pairs(unknown_repo, …)` → `status:"error"` (no row written).

**No regression:** full suite green except the known pre-existing `test_config.py`/`test_guards.py` env failures; dispatcher/retrieval paths unchanged (`memory.qa_pairs` + the `qa_pairs` collection are additive).

## Key files
**memory-knowledge:** `workflows/learned_memory.py`, `projections/learned_memory_{writer,qdrant}.py`, `projections/summary_{writer,qdrant}.py`, `projections/qdrant_payload_schemas.py`, `identity/entity_key.py`, `db/qdrant.py`, `workflows/retrieval.py`, `workflows/context_assembly.py`, `routing/prompt_feature_extractor.py`, `triage_memory.py`, `server.py`, `admin/mawf.py`, `migrations/versions/001_initial_schema.py`, `…/010_triage_memory.py`, `…/024_route_policy_recalibrate.py`.
**mcp-agents-workflow:** `src/workflow_orch/knowledge_client.py`, `src/workflow_orch/intake.py`.
