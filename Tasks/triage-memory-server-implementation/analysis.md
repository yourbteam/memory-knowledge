# Task Objective

Implement the server-side `memory-knowledge` support for triage prompt memory and similar-case retrieval so workflow-orch can call:

- `save_triage_case`
- `search_triage_cases`
- `record_triage_case_feedback`
- `get_triage_feedback_summary`

The requirements contract is defined in:

- `../mcp-agents-workflow/Tasks/memory-knowledge-triage-upgrade-spec/requirements-spec.md`

This task is specifically the `memory-knowledge` side:

- database schema and migrations
- MCP tool handlers
- retrieval/query logic
- feedback persistence
- tests

It is not the workflow-orch client binding work. That was implemented separately in `mcp-agents-workflow`.

# Source Artifacts Inspected

- `src/memory_knowledge/server.py`
- `migrations/versions/004_workflow_tracking.py`
- `migrations/versions/005_planning_schema.py`
- `migrations/versions/008_analytics_schema.py`
- `tests/test_workflow_runs.py`
- `tests/test_planning_tools.py`
- `src/memory_knowledge/routing/prompt_feature_extractor.py`
- `src/memory_knowledge/db/qdrant.py`
- `src/memory_knowledge/integrity/embedding_backfill.py`
- `src/memory_knowledge/projections/pg_writer.py`
- `src/memory_knowledge/admin/analytics.py`
- `../mcp-agents-workflow/Tasks/memory-knowledge-triage-upgrade-spec/requirements-spec.md`

# Current-State Findings

## 1. Tool exposure is centralized in `server.py`

This repo exposes MCP tools directly from `src/memory_knowledge/server.py` using:

- `@mcp.tool()`
- `@track_tool_metrics(...)`

Current tool styles in this file already cover patterns we should follow for triage-memory work:

- read-only retrieval tools
- write tools guarded by `check_remote_write_guard(...)`
- explicit `bind_run_context(...)` and `clear_run_context()`
- direct SQL against PostgreSQL via `get_pg_pool()`
- JSON string responses instead of Python dict returns

That means the triage-memory tools should be implemented as first-class tools in `server.py`, not as an external sidecar service.

## 2. This repo already has SQL persistence precedent, but the established architecture is thin MCP handlers plus module-level logic

The current codebase stores workflow tracking, analytics, and planning data directly in PostgreSQL using schema-qualified SQL such as:

- `ops.workflow_runs`
- `ops.workflow_phase_states`
- `ops.workflow_validator_results`
- `planning.*`
- `catalog.repositories`
- `core.reference_types` / `core.reference_values`

There is no evidence of a separate ORM abstraction for this work. But the established architecture is not “put everything in `server.py`.” Existing tools already keep `server.py` as the MCP surface while delegating business logic to modules such as:

- `memory_knowledge.admin.analytics`
- `memory_knowledge.admin.planning`
- `memory_knowledge.projections.pg_writer`

So the practical implementation path is:

- add new Alembic migration(s)
- add a dedicated triage-memory module for create/update/query behavior
- keep `server.py` as a thin validation / guard / response wrapper over that module
- test through fake pool fixtures similar to `tests/test_workflow_runs.py`

## 3. There is no existing triage-memory schema or tool surface

Repo search found no current implementation for:

- `save_triage_case`
- `search_triage_cases`
- `record_triage_case_feedback`
- `get_triage_feedback_summary`
- `triage_cases`
- `triage_case_feedback`

So this is net-new server functionality rather than an extension of an existing triage subsystem.

## 4. The closest implementation patterns are workflow tracking, route feedback, analytics, and planning

Relevant existing patterns:

- workflow tracking tools show how to validate request fields, resolve repository identity, upsert rows, and preserve partial-update semantics
- route feedback tools show how to persist quality/improvement signals as a separate write path
- analytics tools show how summary tools are exposed and how optional planning context is joined in
- planning tools show how repository scoping is enforced through `catalog.repositories` and planning associations

These patterns strongly suggest that triage-memory should be implemented with:

- a dedicated `ops`-schema storage surface
- repository-scoped rows tied to `catalog.repositories`
- explicit indexes for retrieval filters and summary queries
- a separate feedback table rather than overwriting the base triage decision row

## 5. The requirements spec defines four required MCP tools and concrete field-level contracts

The spec defines:

- persistent triage-case storage
- semantic retrieval with filters and ranking
- feedback write-back and outcome tracking
- summary analytics
- optional embeddings
- rollout phases

For this repo, the implementation needs to honor all four required MCP tools:

- `save_triage_case`
- `search_triage_cases`
- `record_triage_case_feedback`
- `get_triage_feedback_summary`

The storage and retrieval contracts are also more concrete than my first pass captured. The implementation must account for:

- workflow-orch request fields already emitted by the pushed client binding, including:
  - save payload fields such as `prompt_text`, `suggested_workflows`, `decision_source`, and `matched_case_ids`
  - search request knobs such as `limit`, `min_similarity`, `prefer_same_repository`, `include_corrected`, and `max_age_days`
  - feedback payload envelopes that expect `data.updated`
- storage fields such as:
  - `prompt_hash`
  - `request_kind`
  - `execution_mode`
  - `knowledge_mode`
  - `selected_workflow_name`
  - `selected_run_action`
  - `requires_clarification`
  - `clarifying_questions`
  - `fallback_route`
  - `confidence`
  - `reasoning_summary`
  - `project_key`
  - `feature_key`
  - `task_key`
  - `repository_key`
  - `actor_email`
  - `policy_version`
  - `workflow_catalog_version`
  - `created_utc`
- retrieval filters such as:
  - `project_key`
  - `feature_key`
  - `repository_key`
  - `request_kind`
  - `execution_mode`
  - `selected_workflow_name`
  - `selected_run_action`
  - `policy_version`
  - time window
- retrieval response fields such as:
  - `advisory_only`
  - `retrieval_summary`
  - `rows`
  - `warnings`
  - per-row `outcome_status`
  - per-row `outcome_confidence`
- response envelope fields already expected by workflow-orch:
  - `save_triage_case` returns `{ "data": { "triage_case_id": ..., "saved": true } }`
  - `record_triage_case_feedback` returns `{ "data": { "triage_case_id": ..., "updated": true } }`
- data-model support for optional triage embeddings and versioned re-embedding

So the implementation cannot stop at “persist some prompt rows and query them back.” It has to preserve the contract shape expected by workflow-orch and by the summary tool.

## 6. Semantic retrieval infrastructure already exists in this repo; the open question is triage-specific schema design

This repo already has concrete embedding and Qdrant patterns:

- prompt embedding for semantic routing support in `routing/prompt_feature_extractor.py`
- Qdrant collection setup in `db/qdrant.py`
- PG-to-Qdrant embedding backfill in `integrity/embedding_backfill.py`

So the biggest uncertainty is not whether semantic infrastructure exists. The actual open questions are:

- whether triage cases should get a new Qdrant collection or reuse an existing retrieval pattern
- what payload fields and indexes the triage collection needs
- how writes to `ops.triage_cases` and triage embeddings stay synchronized
- whether this task should include a triage embedding backfill / re-embedding path from day one

## 7. Summary-tool behavior has to follow this repo’s existing contract discipline

The recent analytics work in this repo already established explicit expectations around:

- empty-result behavior
- optional planning context shape
- grouping semantics
- tie-breakers / latest-row rules
- per-field optionality

`get_triage_feedback_summary` is part of the required contract, so it needs the same level of clarity as the existing analytics tools. We should not add a vague or underdefined summary tool just because the broader spec gives an example shape.

# Constraints

## 1. The MCP tool interface returns JSON text payloads

Tool handlers in `server.py` return JSON strings. The new triage-memory tools need to match that existing pattern so workflow-orch’s `call_tool_json(...)` continues to work without special casing.

## 2. Write tools must honor remote write guards

Existing write-oriented tools use:

- `check_remote_write_guard(get_settings(), tool_name)`

The new write tools must do the same:

- `save_triage_case`
- `record_triage_case_feedback`

Read-only search and summary tools should remain unguarded unless the repo already applies write-style restrictions to read-heavy admin tools.

## 3. Repository scoping must remain explicit

This repo already treats repository identity as a first-class contract via `catalog.repositories` and planning repository joins. Triage-case storage and retrieval should not bypass repository resolution or silently treat prompts as global if repository context is expected.

## 4. Tests need to follow existing fake-pool style

The fastest defensible test path in this repo is:

- add focused server tests with fake pool behavior
- assert SQL shape and payload normalization
- avoid introducing a large new integration-test harness just for this feature

# Risks And Unknowns

## 1. Triage-specific embedding design ambiguity

The repo already supports embeddings and Qdrant-backed semantic search. The remaining uncertainty is triage-specific design:

- collection name
- point IDs
- payload schema
- synchronization between PostgreSQL triage rows and Qdrant points
- how versioned re-embedding should be represented

## 2. Scope creep into triage-specific embedding plumbing

Even with existing embedding infrastructure, triage-specific semantic retrieval can still expand the task if it requires:

- MCP tools
- schema
- retrieval queries
- Qdrant collection setup
- embedding write path
- backfill / repair path
- tests

## 3. Feedback semantics can drift if not normalized

Workflow-orch now sends well-defined outcome statuses and a small set of payload fields. The server side needs to preserve:

- multiple feedback events over time
- latest effective outcome
- enough detail for future summary queries

Without a clean row model, retrieval ranking and future analytics will become inconsistent.

# Recommended Approach

1. Add a new task-scoped migration that creates:
   - `ops.triage_cases`
   - `ops.triage_case_feedback`
   - supporting indexes
   - any triage-embedding storage or linkage needed for semantic retrieval
2. Implement a dedicated triage-memory module for persistence, retrieval, feedback, and summary logic, keeping `server.py` thin.
3. Implement `save_triage_case` as a guarded write tool with deterministic normalization and a generated `triage_case_id`.
4. Implement `record_triage_case_feedback` as a guarded append-oriented write tool that also supports deriving the latest effective outcome per case.
5. Implement `search_triage_cases` using the repo’s existing embedding/Qdrant patterns, with explicit handling for:
   - semantic similarity
   - structured filters
   - advisory response shape
   - warnings and degraded behavior
6. Implement `get_triage_feedback_summary` from the same storage model in the same task, because it is part of the required MCP contract.
7. Test all new tools through server-level fake-pool tests and, where useful, helper-module tests.

# Initial Conclusion

This task is implementable in `memory-knowledge`, and the repo already has the core building blocks needed to do it:

- MCP tool surface patterns
- PostgreSQL operational schemas and migrations
- Qdrant-backed semantic retrieval infrastructure
- module-level business-logic patterns behind thin server handlers
- fake-pool server test patterns

The plan now needs to answer the remaining triage-specific design questions precisely:

- exact triage table and feedback table shapes
- whether triage embeddings live in PG, Qdrant, or both
- how semantic retrieval ranking and filter precedence are implemented
- how summary metrics are computed from latest-effective feedback
