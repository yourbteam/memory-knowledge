# Tier-2 Working-Agreement Corpus — Implementation Plan

## Goal

A Tier-2 corpus store for working-agreement knowledge (directive rationale, playbook
detail, examples, reference) that is **written directly** (no code-ingestion, no
code-evidence coupling) and **retrieved by semantic search**. It complements the
always-injected Tier-1 `DIRECTIVES.md` by holding the larger corpus retrieved on demand.

## Why a new path (not learned-memory)

`run_learned_memory_proposal_workflow` requires an existing ingested-code `evidence_entity_key`
+ `scope_entity_key` in `catalog.entities`, and the evidence entity must have a row in
`catalog.chunks` (`src/memory_knowledge/workflows/learned_memory.py:92-109`). Working-agreement
knowledge is hand-authored, not chunks of an ingested repo, so there is nothing to point at.
It is also locked to a fixed `memory_type` enum (`learned_memory.py:29-36`) that has no
"directive/playbook" member. Hence a dedicated path and table.

## Requirements

- **R1** Store a corpus entry with: a kind, a title, body text, free-form tags, and a link
  slug binding it to a Tier-1 directive or playbook (e.g. `g2`, `research-playbook`).
- **R2** Write an entry directly via an MCP tool — no propose→commit approval step (the
  "Kamen confirms" gate lives in the working-agreement process, not the DB).
- **R3** Retrieve entries by semantic similarity via an MCP tool, optionally filtered by
  kind and/or link slug.
- **R4** Support updating an entry and superseding/deactivating an old one (soft, via
  `is_active` + `supersedes_key`), so the corpus can be refined in place.
- **R5** Persist to Postgres as source of truth and to Qdrant for semantic search. No Neo4j.
- **R6** Follow the repo's existing conventions: alembic migration (with `downgrade()`),
  schema placement, workflow + projection module layout, server.py MCP wiring, write-guard,
  and tests under `tests/`.
- **R7** Embed `body_text` with the repo's configured embedding model/dimension.
- **R8** Define the corpus's repository scoping (global vs repo-keyed).
- **R9** Generate a stable `entry_key` for new entries; re-writing the same logical entry updates it.
- **R10** Create/ensure the Qdrant collection before first upsert.
- **R11** Retrieval must exclude inactive/superseded entries.
- **R12** The write MCP tool must apply the remote-write guard.
- **R13** Handle bad input (invalid kind, missing body) and backend (embedding/Qdrant) failure.
- **R14** Define behavior when PG write succeeds but Qdrant write fails (consistency).
- **R15** Provide tests for the new path.
- **R16** The migration must drop the table on downgrade.

## Out of scope (explicit)

- Neo4j / graph relationships between entries (can be added later if directives need links).
- Propose→commit approval workflow (cut per R2).
- Migrating existing `working-agreement/` files into the corpus (a later data-load slice).
- Auto-ingestion or freshness/repair jobs for the corpus.
- **(R14) Automatic PG↔Qdrant drift reconciliation.** PG is authoritative. If the Qdrant
  upsert fails, the write tool returns an error (the entry exists in PG but is not yet
  searchable); reconciling that drift is left to the repo's existing integrity-audit/repair
  tooling, not built here. Rationale: keeps the new path small; drift handling already exists
  service-wide.

## Locked design decisions

1. **Table `memory.corpus_entries`** (the `memory` schema already holds `learned_records`,
   per `learned_memory.py:204`).
2. New alembic migration `027_corpus_schema.py` chaining off the real head `026_qa_pairs`
   (the migration line runs to 026; an existing `010_triage_memory.py` already uses 010).
3. PG + Qdrant only; no Neo4j projection.
4. Direct write; no propose→commit.
5. `kind` constrained to: `directive_rationale` · `playbook_detail` · `example` · `reference`.
6. Tagging: `tags jsonb` array + `link_slug text` (binds an entry to a directive/playbook).
7. MCP surface: one write tool `run_corpus_upsert_workflow` + one read tool `corpus_query`.
8. **Global corpus (R8):** not repository-scoped — no `repository_key` column; serves all
   projects (matching the Tier-1 directives' global scope). `corpus_query` is not repo-filtered.
9. **Embedding (R7):** the `corpus_entries` Qdrant collection uses the repo's configured
   embedding model/dimension from `Settings` (`BAAI/bge-base-en-v1.5`, 768, `config.py:57-59`).
10. **entry_key (R9):** deterministic — derived from `link_slug` + a hash of `title` (mirrors
    the `learned_record_entity_key` helper pattern), so re-writing the same logical entry
    upserts in place rather than duplicating.

## Schema (`memory.corpus_entries`)

| column | type | notes |
| --- | --- | --- |
| `id` | bigserial pk | internal id (mirrors learned_records integer id) |
| `entry_key` | uuid unique | stable external key |
| `kind` | text | one of the R5 enum values (CHECK constraint) |
| `title` | text | short label |
| `body_text` | text | the knowledge content (embedded for search) |
| `tags` | jsonb | array of strings, default `[]` |
| `link_slug` | text null | directive/playbook slug this entry supports |
| `confidence` | real null | optional authoring confidence |
| `is_active` | boolean | default true |
| `supersedes_key` | uuid null | prior entry this one replaces |
| `created_utc` | timestamptz | default now() |
| `updated_utc` | timestamptz | default now() |

Indexes: unique on `entry_key`; btree on `(link_slug)` and `(kind)` for filtered retrieval.

## Write path

- `src/memory_knowledge/projections/corpus_writer.py` — `upsert_corpus_entry(...)`,
  `supersede_corpus_entry(...)`, `deactivate_corpus_entry(...)` (PG writes; mirror
  `projections/learned_memory_writer.py`).
- `src/memory_knowledge/projections/corpus_qdrant.py` — `embed_and_upsert_corpus_entry(...)`,
  `deactivate_corpus_point(...)` (mirror `projections/learned_memory_qdrant.py`), into a new
  Qdrant collection `corpus_entries`. The Qdrant **point id is the `entry_key`** (same UUID as
  the PG row — mirror `learned_memory_qdrant.py:43`), so PG and Qdrant stay key-symmetric.
- `src/memory_knowledge/workflows/corpus.py` — `run_upsert(...)`: validate input, upsert to PG,
  then embed→Qdrant. Returns a `WorkflowResult` (mirror `workflows/learned_memory.py`).
- **Collection registration (R10 — SGAP-001):** add `corpus_entries` to the central `COLLECTIONS`
  list so `db/qdrant.py:ensure_collections()` creates it at startup (768-dim, cosine, dimension
  enforced by `_assert_collection_dims`). Do **not** create it ad-hoc per-write.
- **Payload indexes (R3 — SGAP-002):** `ensure_collections` must create payload indexes on
  `kind`, `link_slug`, and `is_active` for `corpus_entries`. Qdrant **rejects a filtered query
  whose field has no payload index** (`db/qdrant.py:84-90` comment) — without these, `corpus_query`'s
  filters throw at runtime.
- **Deactivation contract (R4/R11 — SGAP-003):** `deactivate_corpus_point` does
  `set_payload(is_active=False)` and **retains** the point (mirror
  `learned_memory_qdrant.py:48-55`); it does not delete it.

## Retrieval path

- `corpus_query` **embeds the query text with the same Settings embedding model as the write
  path (SGAP-004)** — otherwise cosine similarity over the collection is meaningless — then runs
  `query_points` on `corpus_entries` (mirror `workflows/impact_analysis.py:67`) with optional
  `kind` / `link_slug` payload filters, and **always filters `is_active=true` (R11)** so
  superseded/deactivated entries are never returned; returns ranked entries.

## Error behavior (R13)

- Invalid `kind` (not in the enum) or missing `body_text`/`title` → `run_upsert` returns a
  `WorkflowResult` with `status="error"` and a clear message (mirrors `learned_memory.py`'s
  validation returns); no PG/Qdrant write occurs.
- PG write succeeds but the Qdrant embed/upsert fails → return `status="error"`; the entry
  exists in PG (authoritative) but is reported as not yet searchable (see Out of scope R14).

## MCP wiring

- Register `run_corpus_upsert_workflow` and `corpus_query` in `src/memory_knowledge/server.py`
  alongside the existing learned-memory and knowledge tools.
- **Remote-write guard (R12):** `run_corpus_upsert_workflow` calls
  `check_remote_write_guard(get_settings(), "run_corpus_upsert_workflow")` before writing,
  exactly as the learned-memory write tools do (`server.py:251,289`).

## Build order (each its own slice)

1. Migration `027_corpus_schema.py` + table (with `downgrade()` dropping the table — R16).
2. PG writer (`corpus_writer.py`) + Qdrant projection (`corpus_qdrant.py`) + collection bootstrap.
3. Workflow (`corpus.py`) + MCP tools in `server.py`.
4. Tests under `tests/` for each slice (R15): migration up/down, writer upsert+supersede,
   retrieval filters, guard, and error paths.

## Acceptance criteria

- `alembic upgrade head` creates `memory.corpus_entries` with the columns/indexes above; `alembic
  downgrade` drops it (R16).
- Calling the write tool with a kind/title/body/tags/link_slug inserts a PG row and a Qdrant
  point in `corpus_entries`; an invalid kind or missing body returns an error with no write (R13).
- The write tool rejects remote writes unless `allow_remote_writes` is set (R12).
- `corpus_query` returns that entry for a semantically related query, respects `kind`
  and `link_slug` filters (which require their payload indexes — SGAP-002), and never returns
  `is_active=false` entries (R11).
- Superseding an entry sets `is_active=false` on the old PG row and calls `set_payload(is_active=false)`
  on its Qdrant point (point retained, not deleted — SGAP-003); the new entry is returned instead.
- Tests for the above pass (R15).
