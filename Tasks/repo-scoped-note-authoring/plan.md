# Plan: Repo-scoped note authoring (`author_repo_note`)

**Why this exists.** Folding the 6 projects' file-memory into the brain (gap #1 §1.4, Bucket B) is blocked: durable repo-scoped memory (`memory.learned_records`) is **entity-anchored and evidence-by-default**, so there is no way to author a free-text repo-*level* note. This plan adds that capability the right way.

**Mode:** Plan (feeds Write-code). Created 2026-06-20. Owner: memory-knowledge.

---

## Grounding (verified against the repo)
- `memory.learned_records` (`migrations/versions/001_initial_schema.py:207`) has **no `repository_id`**; it scopes via `scope_entity_id → catalog.entities(id)`. Columns `entity_id`, `scope_entity_id`, `evidence_entity_id`, `evidence_chunk_id` are **nullable**; `body_tsv` (TSVECTOR), `source_kind`, `confidence`, `verification_status`, `is_active` exist.
- `catalog.entities.entity_type` (`001:82-85`) is currently only `file` / `symbol` / `chunk` — **no repo-root entity**.
- `run_proposal` (`src/memory_knowledge/workflows/learned_memory.py:48`) **requires** `scope_entity_key` + `evidence_entity_key` to resolve to existing entities (raises `ValueError` otherwise) — so it cannot author an evidence-free note.
- Guardrail (`AGENTS.md`): *"inferred/generated memory is evidence by default; instruction-grade memory requires human confirmation or trusted import."* → a note must be marked **human-confirmed**, not dressed up as evidence.
- Embedding/retrieval: the corpus path (`workflows/corpus.py`) shows the embed→Qdrant + PG-enrich pattern to mirror; learned-record retrieval is via `workflows/context_assembly.py` (by `scope.entity_key`).

## Locked design (Option A — repo-root anchor)
Author repo-notes as `learned_records` anchored to a **new per-repo root entity**, marked human-asserted. Chosen over (B) anchoring to an arbitrary file (semantically wrong, fragile) and (C) a brand-new `repo_notes` table (duplicates retrieval/embedding infra).

1. **New entity type `repository`** in `catalog.entities`. One per repo, created at repo registration and backfilled for existing repos. This gives every repo a stable scope anchor with no misleading file association.
2. **`author_repo_note` workflow + MCP tool**: `author_repo_note(repository_key, title, body_text, memory_type="note", confidence=0.8)`:
   - resolve the repo's root entity (create if missing);
   - insert a `learned_records` row: `scope_entity_id = repo-root`, `entity_id = repo-root`, `evidence_entity_id = NULL`, `evidence_chunk_id = NULL`, `source_kind = 'operator_note'`, `verification_status = 'human_asserted'`, `is_active = true`, `confidence`, `body_tsv` populated, `entity_key = learned_record_entity_key(repository_key, memory_type, sha256(title)[:16])`.
   - **Evidence-free (CGAP-003):** unlike `run_proposal` (which *requires* an evidence entity **and** an associated chunk — `learned_memory.py` Steps 2 & 4 raise otherwise), `author_repo_note` deliberately inserts NULL evidence/chunk; the columns are nullable (`001:219-221`). The note is anchored only by `scope_entity_id = repo-root`.
   - **Project to all three stores in one human-asserted write (CGAP-001/004):** the existing flow splits propose (PG, `unverified`) → commit (Qdrant + Neo4j). A note is human-asserted, so author_repo_note lands it **active** and projects in one call, **reusing** the commit-path helpers: `learned_memory_qdrant` upsert (payload carries `repository_key` + `scope_entity_key` — `learned_memory_qdrant.py:31,35` — which is how retrieval isolates by repo) and `learned_memory_neo4j` MERGE `(lr)-[:APPLIES_TO]->(scope)` (`learned_memory_neo4j.py:25`). This means the **repo-root entity must exist in PG *and* Neo4j** (S1 creates it in both).
   - **Memory-type vocabulary (CGAP-002):** add `note` to `VALID_MEMORY_TYPES` (it is validated in `run_proposal`; an unknown type is rejected).
   - **Non-breaking (X-COMPAT):** purely additive — new entity_type value, new `VALID_MEMORY_TYPES` member, new tool; `run_proposal`/commit/existing learned-record paths untouched.
3. **Retrieval check**: confirm repo-note records surface via the existing repo-scoped retrieval (`run_retrieval_workflow`/`context_assembly`) filtered to the repo via the `repository_key` payload, and tolerate NULL evidence; add scoping/null-handling if the root-entity type needs it.

## Steps
- **S1 — Migration (PG + Neo4j root entity):** add `repository` to the entity-type vocabulary and add `note` to `VALID_MEMORY_TYPES`; create a root entity per existing repo in **both** PG (`catalog.entities`) and Neo4j (so `APPLIES_TO` can MERGE onto it), idempotently. *Acceptance:* every repo in `catalog.repositories` has exactly one `repository` entity in PG and a matching Neo4j node; re-running the migration creates no duplicates.
- **S2 — Workflow:** `workflows/repo_note.py::run_author_note(...)` — single human-asserted write that inserts the `learned_records` row (NULL evidence/chunk) **and** projects to Qdrant + Neo4j reusing the existing `learned_memory_qdrant`/`learned_memory_neo4j` helpers. *Acceptance:* fake-backed unit test asserts row fields (`source_kind='operator_note'`, `verification_status='human_asserted'`, `is_active=true`, scope=root, evidence NULL), the Qdrant payload carries `repository_key`, and the Neo4j `APPLIES_TO` MERGE is issued.
- **S3 — MCP tool:** `author_repo_note` in `server.py` wiring to the workflow (write-guarded via `check_remote_write_guard` like other writes). *Acceptance:* tool returns the new record's entity_key/id; server-wiring test green.
- **S4 — Retrieval isolation:** a note authored for repo X is returned by repo-scoped retrieval for X and **not** for repo Y (isolation via the `repository_key` payload), and null-evidence records don't break retrieval. *Acceptance:* fake-backed (or integration) test proving X-returns / Y-excludes.
- **S5 — Embedding parity + Deploy (X-DEPLOY, CGAP-005):** confirm the note embedding uses the same model/dimension as `learned_memory_qdrant`/corpus; ship to canonical Azure; verify the tool live. *Acceptance:* embed dim matches the learned-record collection; deployed endpoint authors + retrieves a test note.
- **S6 — Migrate Bucket B (idempotent):** for each of the 34 project file-memory notes, call `author_repo_note` with the right `repository_key` (entity_key from repo+type+title-hash → re-runs upsert, never duplicate — CGAP-006); after a note is confirmed retrievable, delete its file-memory file. *Acceptance:* each note retrievable in its repo and excluded from others; migrated file-memory files removed; re-running migrates nothing new.

## Open decisions
- **Anchor model:** **Option A confirmed (Kamen, 2026-06-20)** — new `repository` entity type. (Alternative C, a dedicated `memory.repo_notes` table, was declined.) No open decisions remain.

## Out of scope
- Auto-capture of notes (that's gap #2). This tool is the *write primitive* #2 and the §1.4 migration both build on.

## Risks
- Migration S1 touching `catalog.entities` is core — must be additive + idempotent + tested before deploy (G8).
- Embedding model must match the corpus/learned-record dimension (verify against settings).
