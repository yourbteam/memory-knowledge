# Objective

Implement the `memory-knowledge` server-side support for triage prompt memory so the repo exposes these MCP tools with stable contracts:

- `save_triage_case`
- `search_triage_cases`
- `record_triage_case_feedback`
- `get_triage_feedback_summary`

The implementation must satisfy both:

- the product contract in `../mcp-agents-workflow/Tasks/memory-knowledge-triage-upgrade-spec/requirements-spec.md`
- the already-pushed workflow-orch client binding in `../mcp-agents-workflow/src/workflow_orch/triage_memory.py`

# Scope

## In Scope

- PostgreSQL schema/migration for triage cases and triage feedback
- triage-memory server module(s) for persistence, retrieval, feedback, and summary logic
- MCP tool handlers in `src/memory_knowledge/server.py`
- Qdrant collection support for triage-case semantic retrieval
- tests for the four tool contracts and degraded behavior

## Out Of Scope

- changes in `mcp-agents-workflow`
- new workflow-orch client behavior beyond the already-pushed binding
- broad redesign of retrieval, analytics, or planning systems outside triage-memory
- advanced nice-to-haves from the spec such as clarification-question recommendation or confusion-cluster tools

# Design Decisions

## 1. Keep `server.py` thin

Follow the repo’s established pattern:

- `server.py` owns MCP registration, guards, run context binding, and response envelopes
- a dedicated triage-memory module owns SQL, retrieval logic, payload normalization, and summary calculations

Planned module:

- `src/memory_knowledge/triage_memory.py`

## 2. Store base records and feedback separately

Add:

- `ops.triage_cases`
- `ops.triage_case_feedback`

`ops.triage_cases` stores the normalized triage decision.
`ops.triage_case_feedback` stores append-only feedback events.

Latest effective outcome is derived from the newest feedback row per case, not overwritten into the base case row.

## 3. Use Qdrant for semantic retrieval

Do not invent a new retrieval engine. Reuse the repo’s existing embedding/Qdrant pattern.

Planned Qdrant collection:

- `triage_cases`

Collection requirements:

- cosine vector search
- payload fields for repository/project/feature/request-kind/workflow filters
- payload indexes at least for:
  - `repository_key`
  - `project_key`
  - `feature_key`
  - `request_kind`
  - `selected_workflow_name`
  - `policy_version`

## 4. Keep PostgreSQL authoritative for record structure

Qdrant is for similarity search and filter support.
PostgreSQL remains authoritative for:

- canonical triage case row
- feedback event log
- latest-effective outcome derivation
- summary analytics

# Schema Plan

## 1. Migration

Add a new Alembic migration after the current head that:

1. creates `ops.triage_cases`
2. creates `ops.triage_case_feedback`
3. creates indexes needed for:
   - repository-scoped search
   - project/feature filtering
   - workflow/action filtering
   - created-time lookback queries
   - feedback-by-case latest-row lookup

## 2. `ops.triage_cases`

Minimum columns:

- `id BIGSERIAL PRIMARY KEY`
- `triage_case_id UUID NOT NULL UNIQUE`
- `repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id)`
- `prompt_text TEXT NOT NULL`
- `prompt_hash TEXT NOT NULL`
- `request_kind VARCHAR(100) NOT NULL`
- `execution_mode VARCHAR(100) NOT NULL`
- `knowledge_mode VARCHAR(100) NOT NULL`
- `selected_workflow_name VARCHAR(255)`
- `suggested_workflows JSONB NOT NULL DEFAULT '[]'::jsonb`
- `selected_run_action VARCHAR(100)`
- `requires_clarification BOOLEAN NOT NULL DEFAULT FALSE`
- `clarifying_questions JSONB NOT NULL DEFAULT '[]'::jsonb`
- `fallback_route VARCHAR(255)`
- `confidence DOUBLE PRECISION`
- `reasoning_summary TEXT`
- `project_key VARCHAR(255)`
- `feature_key VARCHAR(255)`
- `task_key VARCHAR(255)`
- `actor_email TEXT`
- `policy_version VARCHAR(255)`
- `workflow_catalog_version VARCHAR(255)`
- `decision_source VARCHAR(100)`
- `matched_case_ids JSONB NOT NULL DEFAULT '[]'::jsonb`
- `created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Normalization rules:

- `selected_run_action` stays `NULL` unless the request kind is `run_operation`
- `suggested_workflows`, `clarifying_questions`, and `matched_case_ids` are always stored as arrays
- `prompt_hash` is derived server-side from `prompt_text`
- `policy_version` and `workflow_catalog_version` are nullable because the current workflow-orch client already sends them as `null`

## 3. `ops.triage_case_feedback`

Minimum columns:

- `id BIGSERIAL PRIMARY KEY`
- `triage_case_id UUID NOT NULL REFERENCES ops.triage_cases(triage_case_id) ON DELETE CASCADE`
- `outcome_status VARCHAR(100) NOT NULL`
- `successful_execution BOOLEAN`
- `human_override BOOLEAN`
- `correction_reason TEXT`
- `corrected_request_kind VARCHAR(100)`
- `corrected_execution_mode VARCHAR(100)`
- `corrected_selected_workflow_name VARCHAR(255)`
- `feedback_notes TEXT`
- `created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Latest-effective outcome rule:

- the most recent feedback row by `created_utc`, then `id`, is authoritative for a case
- cases with no feedback rows are treated as `pending` for search and summary purposes
- `outcome_confidence` is derived at read time from latest-effective `outcome_status`:
  - `pending` -> `null`
  - `confirmed_correct` -> `1.0`
  - `execution_failed_after_route` -> `0.75`
  - `insufficient_context` -> `0.5`
  - `corrected` -> `0.25`
  - `overridden_by_human` -> `0.0`

# Tool Contracts

## 1. `save_triage_case`

Implementation rules:

- guarded by `check_remote_write_guard(...)`
- validates required fields before any write
- resolves `repository_key` to `catalog.repositories.id`
- generates a UUID `triage_case_id`
- inserts a canonical row into `ops.triage_cases`
- writes an embedding/Qdrant point for the prompt text

Request assumptions:

- workflow-orch already sends:
  - `prompt_text`
  - `request_kind`
  - `execution_mode`
  - `knowledge_mode`
  - `selected_workflow_name`
  - `suggested_workflows`
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
  - nullable `policy_version`
  - nullable `workflow_catalog_version`
  - `decision_source`
  - `matched_case_ids`

Required save fields:

- `prompt_text`
- `request_kind`
- `execution_mode`
- `knowledge_mode`
- `suggested_workflows`
- `requires_clarification`
- `clarifying_questions`
- `repository_key`

Optional save fields:

- `selected_workflow_name`
- `selected_run_action`
- `task_key`
- `feature_key`
- `project_key`
- `fallback_route`
- `confidence`
- `reasoning_summary`
- `actor_email`
- `policy_version`
- `workflow_catalog_version`
- `decision_source`
- `matched_case_ids`

Response shape must be exactly:

```json
{
  "data": {
    "triage_case_id": "uuid-or-string",
    "saved": true
  }
}
```

## 2. `search_triage_cases`

Implementation rules:

- read-only tool
- returns an advisory response only
- uses Qdrant similarity search over triage-case prompt embeddings
- applies structured filters and ranking using both payload filters and PG-enriched outcome data

Request defaults when callers omit values:

- `limit = 5`
- `min_similarity = 0.65`
- `prefer_same_repository = true`
- `include_corrected = true`
- `max_age_days = 180`

Supported filters:

- `repository_key`
- `project_key`
- `feature_key`
- `request_kind`
- `execution_mode`
- `selected_workflow_name`
- `selected_run_action`
- `policy_version`
- lookback window via `max_age_days`

Ranking behavior:

1. same repository + high semantic similarity
2. same project + high semantic similarity
3. confirmed-correct outcomes
4. recency
5. same policy version

Down-rank rules:

- stale rows beyond the age threshold
- rows whose latest effective outcome is `corrected` or `overridden_by_human`
- mismatched policy version
- unrelated repository rows when same-repo rows exist

`include_corrected` behavior:

- `include_corrected = true`
  corrected and overridden rows remain eligible but are down-ranked
- `include_corrected = false`
  rows whose latest-effective outcome is `corrected` or `overridden_by_human` are hard-excluded from the final result set

Filter enforcement rules:

- Qdrant payload filtering is used for:
  - `repository_key`
  - `project_key`
  - `feature_key`
  - `request_kind`
  - `selected_workflow_name`
  - `policy_version`
- PostgreSQL post-selection filtering and enrichment is used for:
  - `execution_mode`
  - `selected_run_action`
  - `max_age_days` via `created_utc`
  - latest-effective feedback outcome

Search execution order:

1. query Qdrant for semantically similar candidate IDs using the supported payload filters
2. load and enrich those candidate IDs in PostgreSQL
3. apply relational/time-window filters and ranking adjustments in PostgreSQL
4. return the final advisory rows and summary

Degraded behavior:

- if no similar cases exist, return empty `rows` and empty/low-information summary, not an error
- if embeddings/search are unavailable, fall back to lexical/structured retrieval if practical in the same module
- if no fallback is practical, return:
  - `rows: []`
  - `warnings` explaining degraded search
  - `advisory_only: true`

Response shape must include:

- `data.advisory_only = true`
- `data.retrieval_summary` object with stable keys:
  - `returned`
  - `consensus_request_kind`
  - `consensus_workflow`
  - `consensus_strength`
- `data.rows` array
- `data.warnings` array

Each row must include at minimum:

- `triage_case_id`
- `prompt_text`
- `similarity_score`
- `request_kind`
- `execution_mode`
- `knowledge_mode`
- `selected_workflow_name`
- `selected_run_action`
- `requires_clarification`
- `confidence`
- `project_key`
- `feature_key`
- `repository_key`
- `policy_version`
- `created_utc`
- `outcome_status`
- `outcome_confidence`

## 3. `record_triage_case_feedback`

Implementation rules:

- guarded by `check_remote_write_guard(...)`
- validates the target `triage_case_id`
- inserts an append-only feedback row
- does not overwrite the base triage-case record

Supported request fields:

- `triage_case_id`
- `outcome_status`
- `successful_execution`
- `human_override`
- `correction_reason`
- `corrected_request_kind`
- `corrected_execution_mode`
- `corrected_selected_workflow_name`
- `feedback_notes`

Response shape must be exactly:

```json
{
  "data": {
    "triage_case_id": "uuid-or-string",
    "updated": true
  }
}
```

## 4. `get_triage_feedback_summary`

Implementation rules:

- read-only tool
- uses latest-effective feedback per triage case within the requested scope
- supports at least:
  - `repository_key`
  - `project_key`
  - `lookback_days`
  - `request_kind`

Summary output must include:

- `case_count`
- `confirmed_correct_rate`
- `corrected_rate`
- `human_override_rate`
- `clarification_rate`
- `top_misroutes`
- `top_problem_prompts`

Empty-scope behavior:

- return success with zero counts and empty arrays
- do not treat “no matching triage cases” as an error

Derivation rules:

- `clarification_rate` is the proportion of scoped triage cases where `requires_clarification = true`
- `top_misroutes` is derived only from cases whose latest-effective feedback row includes corrected route fields:
  - `from` = original stored `request_kind`
  - `to` = `corrected_request_kind`
  - group by (`from`, `to`)
  - order by descending count, then alphabetical (`from`, `to`)
- `top_problem_prompts` are raw `prompt_text` values, not clustered prompts:
  - include only cases whose latest-effective outcome is `corrected` or `overridden_by_human`
  - order by descending frequency, then most recent `created_utc`, then prompt text
- `lookback_days` defaults to `30` when omitted
- `lookback_days` is evaluated against `ops.triage_cases.created_utc`, not feedback timestamps
- `case_count` is the count of all scoped triage cases in that lookback window
- `confirmed_correct_rate`, `corrected_rate`, and `human_override_rate` all use `case_count` as the denominator, including cases whose latest-effective outcome is still `pending`

# File-Level Work Plan

## 1. `migrations/versions/<next>_triage_memory.py`

Add the new triage tables and indexes.

## 2. `src/memory_knowledge/db/qdrant.py`

Add `triage_cases` to the managed collection list and create needed payload indexes.

## 3. `src/memory_knowledge/triage_memory.py`

Add:

- case insert logic
- feedback insert logic
- latest-outcome derivation helpers
- search logic
- summary logic
- embedding/Qdrant write helper

## 4. `src/memory_knowledge/server.py`

Register and expose the four MCP tools as thin wrappers over the new module.

## 5. Tests

Add or update:

- `tests/test_triage_memory.py`
- optionally `tests/test_workflow_runs.py` only if some fixtures are better shared there

Required test coverage:

1. `save_triage_case` success
2. `save_triage_case` write guard handling
3. `save_triage_case` repository resolution failure
4. `search_triage_cases` success with advisory response shape
5. `search_triage_cases` empty result behavior
6. `search_triage_cases` degraded behavior when embeddings/search are unavailable
7. `record_triage_case_feedback` success
8. `record_triage_case_feedback` unknown case rejection
9. `get_triage_feedback_summary` success
10. `get_triage_feedback_summary` empty-scope behavior

# Validation Criteria

The implementation is complete for this task when:

1. All four required triage-memory MCP tools exist in `server.py`.
2. The request/response envelopes match the requirements spec and the workflow-orch client expectations.
3. Triage cases are durably stored in PostgreSQL with repository scoping.
4. Search returns advisory rows with structured outcome data.
5. Feedback writes are append-only and latest-effective outcome is derivable.
6. Summary metrics operate over the same stored case/feedback model.
7. Focused tests pass locally.

# Sequencing

Implement in this order:

1. migration
2. triage-memory helper module
3. Qdrant collection update
4. MCP server tool wrappers
5. tests
6. local verification

# Risks To Watch

- do not let search return malformed row shapes that break the workflow-orch normalizer
- do not collapse append-only feedback into destructive base-row updates
- do not make summary calculations depend on ambiguous latest-row semantics
- do not silently skip repository scoping
- do not ship a search tool whose degraded behavior differs from the already-pushed workflow-orch expectations
