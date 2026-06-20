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
   - insert a `learned_records` row: `scope_entity_id = repo-root`, `evidence_entity_id = NULL`, `source_kind = 'operator_note'`, `verification_status = 'human_asserted'`, `is_active = true`, `confidence`, `body_tsv` populated;
   - embed `body_text` and upsert to Qdrant with a **repo-scoped payload** (mirror `corpus.py`/`run_proposal` embedding), so it's retrievable.
   - **Non-breaking (X-COMPAT):** purely additive — new entity_type, new tool; `run_proposal`/existing learned-record paths untouched.
3. **Retrieval check**: confirm repo-note records surface via the existing repo-scoped retrieval (`run_retrieval_workflow`/`context_assembly`) filtered to the repo; add scoping if the root-entity type needs handling.

## Steps
- **S1 — Migration:** add `repository` to the entity-type vocabulary; create a root entity per existing repo (idempotent). *Acceptance:* every repo in `catalog.repositories` has exactly one `repository` entity.
- **S2 — Workflow:** `workflows/repo_note.py::run_author_note(...)` (insert + embed). *Acceptance:* unit test with fakes asserts the row fields (`source_kind`, `verification_status`, scope=root, evidence NULL) + an embed call.
- **S3 — MCP tool:** `author_repo_note` in `server.py` wiring to the workflow (write-guarded like other writes). *Acceptance:* tool returns the new record's entity/id; covered by a server-wiring test.
- **S4 — Retrieval:** verify a note authored for repo X is returned by repo-scoped retrieval for X and **not** for repo Y. *Acceptance:* an integration check (or fake-backed test) proving repo isolation.
- **S5 — Deploy (X-DEPLOY):** ship to the canonical Azure endpoint; verify the tool live.
- **S6 — Migrate Bucket B:** for each of the 34 project file-memory notes, call `author_repo_note` with the right `repository_key`; then delete the migrated file-memory files (their content now lives repo-scoped in the brain). *Acceptance:* notes retrievable per-repo; file-memory dirs emptied of migrated notes.

## Open decision for Kamen (G2)
- **Anchor model:** Option A (new `repository` entity type) as locked above — **recommended**. Alternative C (dedicated `memory.repo_notes` table) is cleaner-separated but re-implements embedding+retrieval. Confirm A, or pick C.

## Out of scope
- Auto-capture of notes (that's gap #2). This tool is the *write primitive* #2 and the §1.4 migration both build on.

## Risks
- Migration S1 touching `catalog.entities` is core — must be additive + idempotent + tested before deploy (G8).
- Embedding model must match the corpus/learned-record dimension (verify against settings).
