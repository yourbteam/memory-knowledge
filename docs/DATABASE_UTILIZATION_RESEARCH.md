# Database Utilization Research

**Status:** Draft / research document
**Date:** 2026-06-02
**Scope:** How the three datastores (PostgreSQL, Qdrant, Neo4j) are currently used in the `memory-knowledge` platform.

> **Verification note.** All claims in this document are verified against source (file + line cited): connection setup, config, the Qdrant collection list, the Neo4j label/edge/constraint set, the initial PostgreSQL schema, the projection writers, the ingestion pipeline, the entity-key scheme, and startup/health behavior.

---

## 1. Overview

The platform is a tri-store code-intelligence system. Each store holds the **same entities** projected three different ways, linked by a shared identifier:

| Store | Role | Driver | Startup criticality |
|---|---|---|---|
| **PostgreSQL** | Canonical system of record + full-text search | `asyncpg` | **Hard requirement** — startup has no fallback |
| **Neo4j** | Structural graph (dependencies, calls, domain edges) | `neo4j` (async) | Degraded-allowed |
| **Qdrant** | Vector store for semantic search over embeddings | `qdrant-client` (async) | Degraded-allowed |

The shared identifier is documented below (§6). PostgreSQL is written **first** as the source of truth; Neo4j and Qdrant are projections derived from it.

---

## 2. PostgreSQL — Canonical Store

### 2.1 Client & connection
- Driver: `asyncpg`. Connection pool created in [`postgres.py`](src/memory_knowledge/db/postgres.py:10) via `init_postgres()`.
- Pool sizing, SSL, command timeout, and a PgBouncer/Supabase pooler workaround (`statement_cache_size=0` when the DSN contains `pooler.supabase.com`) are all handled in [`postgres.py:12`](src/memory_knowledge/db/postgres.py:12).
- Accessor `get_pg_pool()` and `close_postgres()` round out the module.

### 2.2 Config / env vars
Defined in [`config.py:11`](src/memory_knowledge/config.py:11):
- `database_url` (required, no default)
- `pg_pool_min_size` (5), `pg_pool_max_size` (20)
- `pg_ssl` (False), `pg_command_timeout` (30s)
- Remote-mode credential seeding from Azure Key Vault: `kv_pg_secret_name` = `db-postgres-url` ([`config.py:85`](src/memory_knowledge/config.py:85)).

### 2.3 Schema
The base schema is created in [`001_initial_schema.py`](migrations/versions/001_initial_schema.py) across **four schemas**: `catalog`, `memory`, `routing`, `ops`. There are **22 migrations total** (`001`–`022`); later migrations add `planning`, `analytics`, triage, intake, and MAWF (Multi-Agent Workflow) tables — see §7.

**`catalog` schema** (the projected codebase — verified against migration 001):
- `repositories` — `repository_key` (unique), `name`, `origin_url`
- `repo_revisions` — `commit_sha`, `branch_name`, `parent_sha`; unique on `(repository_id, commit_sha)`
- `branch_heads` — current head per branch; unique on `(repository_id, branch_name)`
- `retrieval_surfaces` — `surface_type` enum (`live_branch` / `release_branch` / `pinned_commit`)
- `entities` — **`entity_key UUID UNIQUE`** + `entity_type`, FKs to repository & revision. This is the cross-store join key.
- `files` — `file_path`, `language`, `size_bytes`, `checksum`; unique on `(repo_revision_id, file_path)`
- `symbols` — `symbol_name`, `symbol_kind`, `line_start/end`, `signature`; unique on `entity_id`
- `chunks` — `content_text`, **`content_tsv TSVECTOR`** (GIN-indexed), `chunk_type`, line range
- `summaries` — `summary_level`, `summary_text`, `summary_tsv` (GIN-indexed)
- `symbol_calls_symbol` — caller→callee edge table
- `file_imports_file` — importer→imported edge table

**`memory` schema** (learned knowledge):
- `learned_records` — note: uses BIGINT FKs `entity_id` / `scope_entity_id` / `evidence_entity_id` / `evidence_chunk_id` (the last two are `NOT NULL`), plus `memory_type`, `title`, `body_text`, `body_tsv` (GIN), `confidence NUMERIC(3,2)`, `applicability_mode`, `verification_status`, `supersedes_learned_record_id`, `is_active`. (It does **not** carry a UUID `entity_key` of its own in the base schema.)
- `working_sessions` — `session_key UUID UNIQUE`, start/end timestamps
- `working_observations` — `observation_type`, `observation_text`, FK to session

**`routing` schema** (query-strategy + feedback loop):
- `route_policies` — per `prompt_class`: ordered store preference (`first_store`, `second_store`, `third_store`), `allow_fanout`, `allow_graph_expansion`, `semantic_assist_enabled`, `confidence_threshold`, `fusion_strategy`, `rerank_strategy`. **Seeded** with 6 default policies (see §6.3).
- `route_executions` — audit trail: `run_id`, `prompt_class`, `stores_queried[]`, `fanout_used`, `result_count`, `duration_ms`
- `route_feedback` — `usefulness_score`, `precision_score`, `expansion_needed`, `notes`

**`ops` schema** (operational):
- `ingestion_runs` — `run_type`, `status`, timestamps, `error_text`
- `ingestion_run_items` — per-item status
- `job_manifests` — `job_id UUID UNIQUE`, `tool_name`, `state_code`, `job_type`, `attempt_number`, `checkpoint_data JSONB`, `correlation_id`

### 2.4 Operations
- **Writes:** split across [`projections/pg_writer.py`](src/memory_knowledge/projections/pg_writer.py) (chunks, branch heads, retrieval surfaces, ingestion run bookkeeping, route feedback), [`structure/entity_registrar.py`](src/memory_knowledge/structure/entity_registrar.py) (revisions, files, symbols, import/call edge tables), [`projections/summary_writer.py`](src/memory_knowledge/projections/summary_writer.py) (summaries), and [`projections/learned_memory_writer.py`](src/memory_knowledge/projections/learned_memory_writer.py) (learned records). All use `BATCH_SIZE = 250` ([`pg_writer.py:10`](src/memory_knowledge/projections/pg_writer.py:10)) and bulk `INSERT … SELECT … FROM UNNEST(...) ON CONFLICT … DO UPDATE` for idempotency ([`pg_writer.py:94`](src/memory_knowledge/projections/pg_writer.py:94)).
- **`tsvector` is computed inline at write time** — `to_tsvector('english', content_text)` on insert/update, not by a trigger ([`pg_writer.py:53`](src/memory_knowledge/projections/pg_writer.py:53), [`learned_memory_writer.py:52`](src/memory_knowledge/projections/learned_memory_writer.py:52)).
- **Reads:** repository resolution, branch-head lookup for incremental detection, and re-hydration joins (`catalog.chunks/summaries/symbols → catalog.entities`) all run from [`workflows/ingestion.py`](src/memory_knowledge/workflows/ingestion.py) (e.g. [`:479`](src/memory_knowledge/workflows/ingestion.py:479), [`:490`](src/memory_knowledge/workflows/ingestion.py:490), [`:300`](src/memory_knowledge/workflows/ingestion.py:300)); retrieval-time full-text search lives in [`workflows/retrieval.py`](src/memory_knowledge/workflows/retrieval.py).

### 2.5 Health
- Readiness probe runs `SELECT 1` with a 5s timeout; **failure sets overall status to `not_ready`** ([`health.py:33`](src/memory_knowledge/db/health.py:33)). PostgreSQL is treated as non-optional.

---

## 3. Neo4j — Structural Graph

### 3.1 Client & connection
- Driver: `neo4j` async. `init_neo4j()` builds the driver and calls `verify_connectivity()` ([`neo4j.py:15`](src/memory_knowledge/db/neo4j.py:15)).
- `apply_constraints()` creates a `entity_key IS UNIQUE` constraint for every node label ([`neo4j.py:26`](src/memory_knowledge/db/neo4j.py:26)).

### 3.2 Config / env vars
[`config.py:22`](src/memory_knowledge/config.py:22): `neo4j_uri`, `neo4j_user`, `neo4j_password` (all required), `neo4j_max_pool_size` (50). KV secret: `db-neo4j-password`.

### 3.3 Node labels & keys (verified)
12 labels in [`neo4j.py:9`](src/memory_knowledge/db/neo4j.py:9):
`Repository`, `Revision`, `File`, `Symbol`, `LearnedRule`, `WorkingSession`, `Module`, `DbTable`, `StoredProcedure`, `ApiEndpoint`, `Service`, `Task`.

Every node is keyed by a unique `entity_key`, **but the key is not always a UUID** ([`neo4j_projector.py:20`](src/memory_knowledge/projections/neo4j_projector.py:20)):
- `Repository.entity_key` = the `repository_key` string
- `Revision.entity_key` = the `commit_sha` string
- `File` / `Symbol` `.entity_key` = the deterministic UUIDv5 from `catalog.entities` (see §6.1)
- `Module` / `ApiEndpoint` `.entity_key` = a UUIDv5 derived in the ingestion workflow from the same namespace ([`ingestion.py:1157`](src/memory_knowledge/workflows/ingestion.py:1157), [`:1173`](src/memory_knowledge/workflows/ingestion.py:1173))

`DbTable`, `StoredProcedure`, `Service` are **additive labels applied to `Symbol` nodes**, not separate node types.

### 3.4 Graph structure & operations (verified)
Projection lives in [`projections/neo4j_projector.py`](src/memory_knowledge/projections/neo4j_projector.py) (all writes use `MERGE` for idempotency), with learned-rule and working-session projections in [`learned_memory_neo4j.py`](src/memory_knowledge/projections/learned_memory_neo4j.py) and [`working_memory_neo4j.py`](src/memory_knowledge/projections/working_memory_neo4j.py).

**Full relationship-type catalog (verified):**

| Edge | From → To | Source |
|---|---|---|
| `HAS_REVISION` | Repository → Revision | [`neo4j_projector.py:26`](src/memory_knowledge/projections/neo4j_projector.py:26) |
| `HAS_FILE` | Revision → File | [`:32`](src/memory_knowledge/projections/neo4j_projector.py:32) |
| `CONTAINS` | File → Symbol | [`:38`](src/memory_knowledge/projections/neo4j_projector.py:38) |
| `IMPORTS` | File → File | [`:82`](src/memory_knowledge/projections/neo4j_projector.py:82) |
| `CALLS` | Symbol → Symbol | [`:94`](src/memory_knowledge/projections/neo4j_projector.py:94) |
| `CONTAINS_FILE` | Module → File | [`:182`](src/memory_knowledge/projections/neo4j_projector.py:182) |
| `EXPOSES_ENDPOINT` | File → ApiEndpoint | [`:204`](src/memory_knowledge/projections/neo4j_projector.py:204) |
| `READS_TABLE` / `WRITES_TABLE` | File → DbTable | [`:225`](src/memory_knowledge/projections/neo4j_projector.py:225) |
| `EXTENDS` / `IMPLEMENTS` | Symbol → Symbol | [`:255`](src/memory_knowledge/projections/neo4j_projector.py:255) |
| `APPLIES_TO` | LearnedRule → (scope node) | [`learned_memory_neo4j.py:26`](src/memory_knowledge/projections/learned_memory_neo4j.py:26) |
| `DERIVED_FROM` | LearnedRule → (evidence node) | [`learned_memory_neo4j.py:40`](src/memory_knowledge/projections/learned_memory_neo4j.py:40) |
| `CONFLICTS_WITH` | LearnedRule ↔ LearnedRule | [`learned_memory_neo4j.py:75`](src/memory_knowledge/projections/learned_memory_neo4j.py:75) |

**Additive-label rules** ([`neo4j_projector.py:101`](src/memory_knowledge/projections/neo4j_projector.py:101)): `DbTable` for symbol kind `table`/`view`; `StoredProcedure` for kind `procedure`/`function` in a SQL file; `Service` for `class` symbols named `*Service`/`*Provider` or living under a `services/` path.

Used primarily by impact analysis ([`workflows/impact_analysis.py`](src/memory_knowledge/workflows/impact_analysis.py)) and the graph-expansion step of retrieval.

### 3.5 Startup & health
- **Startup:** wrapped in try/except — failure logs `neo4j_startup_degraded` and continues ([`server.py:5868`](src/memory_knowledge/server.py:5868)).
- **Readiness:** failure is reported as `degraded` (added to a `degraded` list) but does **not** flip overall status to `not_ready` ([`health.py:52`](src/memory_knowledge/db/health.py:52)).

---

## 4. Qdrant — Vector Store

### 4.1 Client & connection
- Driver: `AsyncQdrantClient`. `init_qdrant()` at [`qdrant.py:20`](src/memory_knowledge/db/qdrant.py:20).
- `ensure_collections()` creates any missing collections and payload indexes ([`qdrant.py:29`](src/memory_knowledge/db/qdrant.py:29)).
- A version-compatibility shim `semantic_query_points()` bridges `query_points()` vs. the older `search()` API ([`qdrant.py:68`](src/memory_knowledge/db/qdrant.py:68)).

### 4.2 Config / env vars
[`config.py:18`](src/memory_knowledge/config.py:18): `qdrant_url` (required), `qdrant_api_key` (optional). Vector geometry comes from the OpenAI block: `embedding_model` = `text-embedding-3-small`, `embedding_dimensions` = **1536** ([`config.py:43`](src/memory_knowledge/config.py:43)). KV secret: `db-qdrant-apikey`.

### 4.3 Collections (verified)
5 collections, all created with `size = embedding_dimensions` (1536) and `COSINE` distance ([`qdrant.py:11`](src/memory_knowledge/db/qdrant.py:11)):
1. `code_chunks`
2. `summary_units`
3. `learned_memory`
4. `routing_archetypes`
5. `triage_cases`

**Payload indexes** created on every collection ([`qdrant.py:46`](src/memory_knowledge/db/qdrant.py:46)): `repository_key`, `project_key`, `feature_key`, `request_kind`, `selected_workflow_name`, `policy_version`, `is_active` (BOOL), `branch_name`, `commit_sha` — all KEYWORD except `is_active`.

**Payload schemas** ([`qdrant_payload_schemas.py`](src/memory_knowledge/projections/qdrant_payload_schemas.py)):
- `CodeChunkPayload`: `entity_key`, `repository_key`, `commit_sha`, `branch_name`, `file_path`, `symbol_name?`, `chunk_type`, `is_active`, `retrieval_surface`, `content_kind="code_chunk"`
- `SummaryPayload`: `entity_key`, `repository_key`, `commit_sha`, `summary_level`, `is_active`, `content_kind="summary"`
- `LearnedMemoryPayload`: `entity_key`, `repository_key`, `memory_type`, `confidence`, `applicability_mode`, `scope_entity_key`, `is_active`, `content_kind="learned_rule"`

> Note: `ensure_collections()` creates **all nine payload indexes on every collection** indiscriminately ([`qdrant.py:46`](src/memory_knowledge/db/qdrant.py:46)). Five of them (`project_key`, `feature_key`, `request_kind`, `selected_workflow_name`, `policy_version`) are absent from the three verified payload models (§4.3) and so serve the `routing_archetypes` / `triage_cases` collections; on `code_chunks`/`summary_units`/`learned_memory` they are harmless but unused. Confirm which writer populates the routing/triage collections before relying on those indexes.

### 4.4 Operations (verified)
- **Point ID = the `entity_key` UUID string** in every collection ([`qdrant_projector.py:52`](src/memory_knowledge/projections/qdrant_projector.py:52), [`learned_memory_qdrant.py:44`](src/memory_knowledge/projections/learned_memory_qdrant.py:44)) — so a Qdrant point and its PostgreSQL/Neo4j counterparts share the same identifier directly.
- **Writes are per-collection:** `code_chunks` via [`qdrant_projector.py:25`](src/memory_knowledge/projections/qdrant_projector.py:25) (`BATCH_SIZE = 100`, embeddings from OpenAI via `embed()`); `summary_units` via [`summary_qdrant.py`](src/memory_knowledge/projections/summary_qdrant.py); `learned_memory` via [`learned_memory_qdrant.py:12`](src/memory_knowledge/projections/learned_memory_qdrant.py:12). Each writer validates its Pydantic payload model before upsert.
- **Soft delete, never hard delete:** stale points are flagged via `client.set_payload({"is_active": False}, …)` rather than removed — by filter for full re-ingestion ([`qdrant_projector.py:67`](src/memory_knowledge/projections/qdrant_projector.py:67)) or by point ID for invalidated learned rules ([`learned_memory_qdrant.py:50`](src/memory_knowledge/projections/learned_memory_qdrant.py:50)).
- **Reads:** filtered semantic search via the `semantic_query_points()` shim, with `models.Filter` conditions on indexed payload keys (`repository_key`, `branch_name`, `commit_sha`, `is_active`, …).

### 4.5 Startup & health
- **Startup:** try/except — failure logs `qdrant_startup_degraded` and continues ([`server.py:5876`](src/memory_knowledge/server.py:5876)). This matches the recent commit *"Allow Qdrant degraded startup"* (`823110a`).
- **Readiness:** `get_collections()` with 5s timeout. **Note an inconsistency:** unlike at startup, a readiness failure currently sets overall status to `not_ready` rather than `degraded` ([`health.py:42`](src/memory_knowledge/db/health.py:42)) — i.e. Qdrant is degraded-tolerant at boot but readiness-blocking afterward. Flagged for review.

---

## 5. Startup order & criticality (verified)

In the server lifespan ([`server.py:5864`](src/memory_knowledge/server.py:5864)):
1. (If remote) seed DB credentials from Azure Key Vault, then re-instantiate `Settings`.
2. `init_postgres()` — **no fallback**; an exception here aborts startup.
3. `init_neo4j()` + `apply_constraints()` — degraded-allowed.
4. `init_qdrant()` + `ensure_collections()` — degraded-allowed.

So PostgreSQL is the only store whose absence prevents the server from starting.

---

## 6. Cross-store linkage

### 6.1 The join key: `entity_key` (deterministic UUIDv5)
Entity keys are **not random** — they are `uuid5(NAMESPACE_MK, …)` over stable inputs, with a fixed namespace `b7e15163-2a0e-4e29-8f3a-d4b612c8a1f7` ([`identity/entity_key.py:6`](src/memory_knowledge/identity/entity_key.py:6)):
- file → `repo_key:commit_sha:file_path`
- symbol → `repo_key:commit_sha:file_path:symbol_name:symbol_kind`
- chunk → `repo_key:commit_sha:file_path:chunk_index`
- summary → `repo_key:commit_sha:<target_entity_key>:summary:<level>`
- learned record → `repo_key:memory_type:title_hash`

Because the key is a pure function of its inputs, **re-ingesting the same commit reproduces identical keys**, which is what makes the `ON CONFLICT`/`MERGE` upserts across all three stores idempotent. The same `entity_key` is the Postgres `catalog.entities.entity_key`, the Neo4j File/Symbol node key, and the Qdrant point ID — so a vector hit re-hydrates directly to a graph node and a canonical row with no mapping table.

> Learned records also get their own `catalog.entities` row (`entity_type='learned_record'`) with a UUIDv5 key ([`learned_memory_writer.py:32`](src/memory_knowledge/projections/learned_memory_writer.py:32)). This resolves the earlier "identity mismatch": Postgres references learned records internally by BIGINT `entity_id`/`scope_entity_id`, while Neo4j/Qdrant use the corresponding UUID `entity_key`/`scope_entity_key` — both point at the same `catalog.entities` rows.

### 6.2 Ingestion pipeline (verified — [`ingestion.py:454`](src/memory_knowledge/workflows/ingestion.py:454))
The workflow is checkpointed through six ordered phases ([`ingestion.py:82`](src/memory_knowledge/workflows/ingestion.py:82)): `initialized → canonical_complete → summaries_complete → chunk_embeddings_complete → summary_embeddings_complete → neo4j_complete`. The store write order is:

1. **Resolve & detect** (PG): look up the repository and the current branch head; diff against `old_sha` to choose **incremental vs. full** ([`:479`](src/memory_knowledge/workflows/ingestion.py:479)–[`:530`](src/memory_knowledge/workflows/ingestion.py:530)).
2. **Canonical write** (PG, source of truth): clone/checkout, parse, then bulk-upsert files → symbols → chunks and resolve import/call edge tables ([`:795`](src/memory_knowledge/workflows/ingestion.py:795)–[`:825`](src/memory_knowledge/workflows/ingestion.py:825)).
3. **Summaries** (PG): LLM-batched per language, persisted incrementally with their own checkpoint cursor ([`:1041`](src/memory_knowledge/workflows/ingestion.py:1041)).
4. **Embed + Qdrant `code_chunks`** ([`:1071`](src/memory_knowledge/workflows/ingestion.py:1071)), then **embed + Qdrant `summary_units`** ([`:1097`](src/memory_knowledge/workflows/ingestion.py:1097)).
5. **Deactivate superseded vectors** — full runs only — by flipping `is_active=False` on old code-chunk and summary points ([`:1109`](src/memory_knowledge/workflows/ingestion.py:1109)).
6. **Neo4j projection** (last): repository graph → dependency edges → additive labels → modules → API endpoints → SQL read/write edges → inheritance edges ([`:1118`](src/memory_knowledge/workflows/ingestion.py:1118)–[`:1257`](src/memory_knowledge/workflows/ingestion.py:1257)).
7. **Finalize** (PG): update branch head + `live_branch` retrieval surface, mark the ingestion run completed ([`:1265`](src/memory_knowledge/workflows/ingestion.py:1265)).

PostgreSQL is written first and is the only store whose failure aborts the run; Neo4j projection is skipped (with a warning) if the driver is unavailable ([`:1119`](src/memory_knowledge/workflows/ingestion.py:1119)).

### 6.2.1 Cross-store invalidation (verified)
Incremental runs keep the three stores consistent in two ways:
- **Per-file vector deactivation:** changed or deleted files have their existing `code_chunks` points flagged `is_active=False` before re-write ([`ingestion.py:622`](src/memory_knowledge/workflows/ingestion.py:622), [`:646`](src/memory_knowledge/workflows/ingestion.py:646)).
- **Learned-rule staleness cascade:** when a file changes, active `learned_records` scoped to that file are marked stale in **PG**, and the same `entity_key` is deactivated in **Qdrant** and **Neo4j** ([`ingestion.py:828`](src/memory_knowledge/workflows/ingestion.py:828)–[`:861`](src/memory_knowledge/workflows/ingestion.py:861)). This is the clearest example of a write fanning out across all three stores by shared key.

### 6.3 Routing ties the stores together
The seeded `routing.route_policies` rows ([`001_initial_schema.py:339`](migrations/versions/001_initial_schema.py:339)) encode **which store leads** per prompt class — verified values:

| prompt_class | first → second → third | fanout | graph_exp | semantic | threshold |
|---|---|---|---|---|---|
| `exact_lookup` | postgres → neo4j → qdrant | – | – | – | 0.80 |
| `conceptual_lookup` | qdrant → postgres → neo4j | ✓ | ✓ | ✓ | 0.50 |
| `impact_analysis` | neo4j → postgres → qdrant | ✓ | ✓ | – | 0.60 |
| `pattern_search` | qdrant → postgres → neo4j | – | – | ✓ | 0.50 |
| `decision_history` | postgres → qdrant → neo4j | – | – | ✓ | 0.50 |
| `mixed` | postgres → qdrant → neo4j | ✓ | ✓ | ✓ | 0.40 |

This is the clearest single artifact showing the intended division of labor: exact lookups lead with Postgres, conceptual/pattern queries lead with Qdrant, impact analysis leads with Neo4j.

### 6.4 Retrieval read path (verified — [`retrieval.py:650`](src/memory_knowledge/workflows/retrieval.py:650))
The `run()` orchestration:
1. **Resolve repo** → `repository_id` ([`:671`](src/memory_knowledge/workflows/retrieval.py:671)).
2. **Classify prompt** — keyword `classify_prompt` returns `(class, confidence)` ([`:43`](src/memory_knowledge/workflows/retrieval.py:43)); then `match_archetype` does a semantic lookup against the `routing_archetypes` collection (limit 1, `score_threshold=0.75`) and **overrides** the class if its score beats the keyword confidence ([`:678`](src/memory_knowledge/workflows/retrieval.py:678)).
3. **Load policy + surfaces** — `SELECT * FROM routing.route_policies WHERE prompt_class = $1 LIMIT 1`; the `is_default` retrieval surface supplies `commit_sha`/`branch_name` used **only for labeling and the freshness check** ([`:702`](src/memory_knowledge/workflows/retrieval.py:702)), not for filtering.
4. **Freshness check** — warns if the active surface is older than `max_surface_age_hours` (168h) ([`:710`](src/memory_knowledge/workflows/retrieval.py:710)).
5. **Query first store**, then **conditional fan-out** to the second store only if `allow_fanout` and `first_store_count < FANOUT_THRESHOLD` (5) ([`:741`](src/memory_knowledge/workflows/retrieval.py:741)).
6. **Optional Neo4j expansion** if `allow_graph_expansion`: seeds from ≤20 result keys, traverses `CONTAINS|HAS_FILE` (undirected) + `CALLS|IMPORTS` (directed) at depth 2 ([`:758`](src/memory_knowledge/workflows/retrieval.py:758), [`:278`](src/memory_knowledge/workflows/retrieval.py:278)).
7. **Summary searches** — `pg_summary_search` always; `qdrant_summary_search` **only if a query embedding already exists** ([`:776`](src/memory_knowledge/workflows/retrieval.py:776)).
8. **Fuse** via `rerank_results` ([`:293`](src/memory_knowledge/workflows/retrieval.py:293)): `combined_score = pg_score + qdrant_score + graph_boost`, where PG `ts_rank` is normalized to the **result-set max** (top PG hit → 1.0), Qdrant cosine is used as-is (absolute 0–1), summaries are weighted 0.8×, and graph adds +0.1 (already present) or +0.3 (graph-only discovery).
9. **Hydrate** top 40 (§4.4/F1), surface applicable learned rules (scoped by `repository_id` + `file_path` only, [`:807`](src/memory_knowledge/workflows/retrieval.py:807)), persist the route execution (skipped in remote read-only), and fire-and-forget auto-feedback.

**Routing collections (verified):**
- `routing_archetypes` is populated at startup by `load_archetypes` — ~26 fixed query templates per prompt class, deterministic UUIDv5 point IDs, re-upserted idempotently each boot ([`archetype_loader.py:55`](src/memory_knowledge/routing/archetype_loader.py:55), [`server.py:5917`](src/memory_knowledge/server.py:5917)). No accumulation (stable IDs, fixed set).
- `triage_cases` is a **separate subsystem** with its own canonical table `ops.triage_cases` (migration 010), projected to Qdrant by `triage_memory.py` and queried by `search_triage_cases` with semantic + lexical-fallback ranking. Its payload uses exactly the `project_key`/`feature_key`/`request_kind`/`selected_workflow_name`/`policy_version` keys — **resolving the §4.3 "extra index" question**. Notably, triage search **does** bound staleness via `max_age_days` (180) and recency weighting ([`triage_memory.py:122`](src/memory_knowledge/triage_memory.py:122)), unlike the code-retrieval path.

---

## 7. Schema evolution beyond the base (migrations 002–022)

The three-store core is established in migration 001. Later migrations extend mostly PostgreSQL (and add the `triage_cases` Qdrant collection + `Task` Neo4j label). Notable groups, by filename:
- `002` conceptual fanout, `003` auto-feedback flag
- `004` workflow tracking, `005` planning schema, `006`–`007` task scope/single-repository
- `008` analytics schema, `009` workflow findings
- `010`–`014` triage memory + outcome/lifecycle/policy/governance
- `015` intake sessions
- `016`–`022` MAWF (Multi-Agent Workflow): contract, task execution leases, artifact ref keys, workflow-runs-by-user, recoverable workflow runs, external task id, task artifact branch metadata

*This section is a filename-level inventory; the per-migration column details are not yet read into this document.*

---

## 8. Findings & follow-ups

### 8.1 High-confidence actionable findings

**F1 — PG-led retrieval serves stale, superseded, and deleted-file content (correctness).**
The retrieval stores are scoped inconsistently:
- Qdrant semantic/summary search filters `is_active=True` ([`retrieval.py:182`](src/memory_knowledge/workflows/retrieval.py:182), [`:248`](src/memory_knowledge/workflows/retrieval.py:248)) → only current data is served.
- PG full-text search is scoped by **`repository_id` only** — no branch/revision filter ([`retrieval.py:129`](src/memory_knowledge/workflows/retrieval.py:129), [`:150`](src/memory_knowledge/workflows/retrieval.py:150)) — and `catalog.chunks` **has no `is_active` column** (verified across all 22 migrations; chunks are never deactivated or deleted).
- `assemble_context_bundle` hydrates purely on `entity_key` with no scoping ([`retrieval.py:430`](src/memory_knowledge/workflows/retrieval.py:430)), then **stamps the *current* `commit_sha`/`branch_name` onto every result** ([`:485`](src/memory_knowledge/workflows/retrieval.py:485)) — mislabeling stale rows as current.

Because `entity_key` embeds `commit_sha` (§6.1), every full ingestion mints a new generation of chunks that all remain permanently full-text-searchable. Per §6.3, the `exact_lookup`, `decision_history`, and `mixed` route policies lead with or include Postgres, so those query classes can rank superseded/deleted content alongside live content and present it as current. **This is a silent answer-quality bug, not just storage bloat.**
→ **Fix:** scope `pg_fulltext_search` / `pg_summary_search` to the active retrieval surface's `repo_revision_id` (joining via `catalog.files.repo_revision_id`), or add an `is_active` flag to `catalog.chunks` and flip it during the ingestion deactivation step (step 5, §6.2) to mirror Qdrant.

**F2 — No garbage collection exists; all stores grow per-commit without bound (operational).**
There are **zero hard-deletes** of store data anywhere in the codebase — no Qdrant `delete`, no Neo4j `DETACH DELETE`, no `DELETE FROM catalog/memory` (the only `DELETE FROM` statements target triage/planning link tables). `repair_drift.repair` and `rebuild_revision` **only upsert/re-add missing projections** ([`repair_drift.py:103`](src/memory_knowledge/integrity/repair_drift.py:103), [`:252`](src/memory_knowledge/integrity/repair_drift.py:252)) — they cannot prune. With per-commit `entity_key`s, PG rows, Neo4j nodes, and inactive Qdrant points accumulate on every full ingestion forever.
→ **Fix:** add a compaction pass (delete Qdrant points / Neo4j nodes / PG rows for revisions older than the active surface, or where `is_active=false` beyond a retention window). The add-only `repair_rebuild` workflow ([`workflows/repair_rebuild.py`](src/memory_knowledge/workflows/repair_rebuild.py)) is the natural home.

**F3 — Deleted files orphan their PG rows and Neo4j nodes, and the audit cannot detect it (correctness/drift).**
On incremental ingestion, a deleted file only deactivates its **Qdrant** points ([`ingestion.py:622`](src/memory_knowledge/workflows/ingestion.py:622)); the `catalog.files`/`symbols` rows and Neo4j `File`/`Symbol` nodes (with their `CALLS`/`IMPORTS` edges) persist with no `is_active` marker, so they remain graph-traversable and PG-searchable (feeding F1). The integrity audit cannot catch this: `check_pg_neo4j` only verifies PG→Neo4j *presence* ([`check_pg_neo4j.py:53`](src/memory_knowledge/integrity/check_pg_neo4j.py:53)), and since PG also retains the deleted file's entity, the two stores stay "aligned."
→ **Fix:** extend the deleted-file branch to also remove/deactivate the PG rows and Neo4j nodes by `entity_key`; add a reverse (Neo4j→PG-current) orphan check to the audit.

**F4 — `pg_ssl=True` disables TLS certificate verification (security).**
[`postgres.py:14`](src/memory_knowledge/db/postgres.py:14) builds the SSL context with `check_hostname = False` and `verify_mode = CERT_NONE` — the connection is encrypted but accepts any server certificate (no MITM protection). `pg_ssl` is exactly the flag enabled for remote/prod (Supabase, Azure).
→ **Fix:** default to `CERT_REQUIRED` with the provider CA bundle; gate any relaxed mode behind a separate explicit setting.

**F5 — Qdrant readiness probe contradicts degraded-startup intent (likely bug).**
Qdrant is degraded-tolerant at boot ([`server.py:5876`](src/memory_knowledge/server.py:5876), reinforced by commit `823110a`), but a readiness-probe failure flips overall status to `not_ready` ([`health.py:42`](src/memory_knowledge/db/health.py:42)), unlike Neo4j which only reports `degraded` ([`health.py:52`](src/memory_knowledge/db/health.py:52)). Under an orchestrator this pulls the pod from rotation during a Qdrant outage despite the app being designed to serve degraded.
→ **Fix:** make Qdrant readiness report `degraded` like Neo4j (or make startup fail if Qdrant is truly critical).

**F6 — `exact_lookup` queries never touch the vector store (retrieval coverage).**
For `exact_lookup` the policy is `first_store=postgres`, `allow_fanout=FALSE`, `allow_graph_expansion=FALSE` (§6.3). In `run()` the query is embedded only when Qdrant is queried as first/fan-out store, so for this class the embedding is never computed → neither `qdrant_semantic_search` nor `qdrant_summary_search` runs ([`retrieval.py:727`](src/memory_knowledge/workflows/retrieval.py:727), [`:776`](src/memory_knowledge/workflows/retrieval.py:776)). **`exact_lookup` is therefore served purely from the unscoped PG full-text path** — maximum exposure to F1 with zero semantic grounding.
→ **Fix:** depends on F1; once PG is revision-scoped, consider enabling a semantic assist or graph expansion for `exact_lookup`, or document that it is deliberately lexical-only.

**F7 — Fusion sums incomparable score scales (ranking quality).**
`rerank_results` normalizes PG `ts_rank` to the **current result-set max** (so the best PG hit always contributes `1.0`, regardless of absolute relevance) and then sums it with absolute Qdrant cosine and a flat graph boost ([`retrieval.py:303`](src/memory_knowledge/workflows/retrieval.py:303)–[`:387`](src/memory_knowledge/workflows/retrieval.py:387)). A weak top-PG match can thus outrank a strong semantic match — and combined with F1, a stale PG chunk can land at the top.
→ **Fix:** use a comparable normalization (e.g. min-max or softmax per source, or RRF) before summing, and/or apply the policy's `confidence_threshold` (currently unused — see F8).

**F8 — Several seeded route-policy columns are dead config (maintainability/misleading).**
`run()` reads only `first_store`, `second_store`, `allow_fanout`, `allow_graph_expansion`. The seeded columns `third_store`, `semantic_assist_enabled`, `fusion_strategy`, `confidence_threshold` are **never referenced** in retrieval, and `rerank_strategy` is only written back as the literal `"score_sort"` ([`retrieval.py:842`](src/memory_knowledge/workflows/retrieval.py:842)), never read from the policy. So the third store in every policy (§6.3) is never queried, and the per-class confidence thresholds are never enforced.
→ **Fix:** either wire these columns into `run()` (notably `confidence_threshold` for filtering and `third_store` for a final fan-out tier) or drop them from the schema/seed to stop implying behavior that doesn't exist.

### 8.2 Lower-priority / documentation

- **Embedding model coupling** — collections are pinned to `embedding_dimensions = 1536` for `text-embedding-3-small` ([`config.py:43`](src/memory_knowledge/config.py:43)); there is no re-embedding/migration path. Document the constraint and guard before any model change.
- **Payload index superset** (§4.3 note) — nine indexes are created on all five collections; five keys are unused on the code/summary/learned collections. Harmless; serves routing/triage.

### 8.3 Resolved during verification
- **`learned_records` identity** (§6.1) — every learned record is a `catalog.entities` row with a UUIDv5 key; PG uses BIGINT FKs, Neo4j/Qdrant use the matching UUID. No real mismatch.
- **Projection/workflow detail** (§2.4, §3.4, §4.4, §6.2) — batch sizes, point-ID scheme, full Cypher edge catalog, and the 7-step ingestion sequence are verified with citations.
- **Read path** (§6.4) — the full `run()` orchestration, the `rerank_results` fusion math, the archetype override, and the routing/triage collections are now verified. The `routing_archetypes` writer/reader and the `triage_cases` subsystem are documented; the §4.3 "extra index" question is resolved (those keys serve `triage_cases`).

### 8.4 Research complete
All read- and write-path datastore behavior referenced by F1–F8 is verified against source. Remaining unread code (triage lifecycle scoring internals, the dead-letter/job-worker machinery) does not affect the three-store utilization picture or the findings above.
