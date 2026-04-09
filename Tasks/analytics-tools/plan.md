# Plan: Analytics Tools

## Objective

Deliver a repo-ready workflow analytics upgrade for `memory-knowledge`.

“Repo-ready” means this repo will own:

- canonical persistence schema for missing analytics source data
- MCP write APIs for that data
- analytics helper queries
- MCP summary/query tools
- tests
- setup/deployment prerequisites for analytics-enabled environments

This repo will **not** claim to complete external orchestrator adoption. The actual workflow producer that calls the new write APIs lives outside this repo and remains a follow-up dependency.

The requested target set from the chat spec is:

- `get_agent_performance_summary`
- `get_phase_quality_summary`
- `get_validator_failure_summary`
- `get_loop_pattern_summary`
- `get_quality_grade_summary`
- `list_entropy_sweep_targets`

## Existing Tools Already Sufficient For Increment 2

The current repo already exposes operational workflow tools that are sufficient for Increment 2 style non-aggregated workflow inspection and recovery:

- `save_workflow_run`
- `save_workflow_artifact`
- `get_workflow_run`
- `get_workflow_artifact`
- `list_workflow_runs`
- `list_workflow_runs_by_actor`
- `list_reference_values`

These existing tools already cover:

- run persistence
- artifact persistence
- direct run inspection
- repository-scoped run listing
- actor-email run recovery
- lookup resolution for normalized reference/status values

Compatibility note for this upgrade:

- once `save_workflow_validator_result` exists, `get_workflow_run` must also surface persisted validator-result rows so direct per-run inspection/recovery remains complete instead of hiding newly persisted workflow telemetry

The new work in this task is specifically the missing aggregated analytics layer and the missing persistence required to support the more advanced summaries.

## Staged Delivery

The delivery sequence for this task is staged even though the final target set contains all six analytics tools.

### Stage 1: Recommended first batch

Implement first:

- `get_agent_performance_summary`
- `get_phase_quality_summary`
- `get_validator_failure_summary`
- `get_loop_pattern_summary`

and the missing persistence they require:

- `save_workflow_phase_state`
- `save_workflow_validator_result`
- `ops.workflow_validator_results`
- `WORKFLOW_VALIDATOR_STATUS`

### Stage 2: Later tools after prerequisites are in place

Implement after Stage 1 contracts and persistence are in place:

- `get_quality_grade_summary`
- `list_entropy_sweep_targets`

These remain part of the same repo-ready upgrade target, but they are staged after the first batch because they depend on the Stage 1 persistence/model work and on the v1 grading/ranking contracts defined in this plan.

## Locked V1 Contracts

These are explicit v1 contracts for this task because the referenced analytics spec file is not present in the repo.

### Workflow run status contract

Canonical run status is:

- `ops.workflow_runs.status_id -> core.reference_values`

The supported workflow run statuses are:

- `RUN_PENDING`
- `RUN_SUBMITTED`
- `RUN_RUNNING`
- `RUN_SUCCESS`
- `RUN_PARTIAL`
- `RUN_ERROR`
- `RUN_CANCELLED`

Analytics must not use legacy `ops.workflow_runs.status` as the canonical source.

### Phase status contract

New phase-state writes in this upgrade must use the raw status vocabulary:

- `pending`
- `running`
- `success`
- `error`
- `cancelled`

Phase summary bucketing is:

- `success`
- `error`
- `cancelled`
- `other`

Unknown raw phase statuses must be counted in `other`, not dropped.

### Attempt-number contract

For `ops.workflow_phase_states`:

- attempt numbering is 1-based for real phase executions
- the first persisted attempt is `1`
- schema/default behavior must be reconciled so omitted first-write attempts are stored as `1`, not `0`
- reconciliation approach: migration 008 must `ALTER TABLE ops.workflow_phase_states ALTER COLUMN attempts SET DEFAULT 1`, AND the write-path upsert must use `COALESCE($attempts, 1)` for first-write protection
- sparse updates preserve existing non-zero `attempts` unless an explicit newer value is supplied

### Validator contract

Each invoked validator must emit a result row.

Intentional non-applicability must emit:

- `VAL_SKIPPED`

not silence.

Validator status reference type:

- `WORKFLOW_VALIDATOR_STATUS`

Validator statuses:

- `VAL_PENDING`
- `VAL_PASSED`
- `VAL_FAILED`
- `VAL_SKIPPED`
- `VAL_ERROR`

These values must be seeded into `core.reference_values` as part of the analytics migration before `ops.workflow_validator_results.status_id` is used by writes or analytics queries.

Validator code normalization for v1:

- `output-contract-validator` -> `OUTPUT_CONTRACT`
- `evidence-grounding-validator` -> `EVIDENCE_GROUNDING`
- `memory-proposal-validator` -> `MEMORY_PROPOSAL`

These normalized codes become the v1 canonical identifiers for schema, API, tests, and analytics.

Canonical-code enforcement rule for v1:

- `save_workflow_validator_result` accepts only:
  - `OUTPUT_CONTRACT`
  - `EVIDENCE_GROUNDING`
  - `MEMORY_PROPOSAL`
- any other `validator_code` is rejected with an explicit `WorkflowResult` error

### Grading contract

The grading rubric in this plan is the v1 source of truth for this task.

Run-level score starts at `100` and applies:

- `-40` for terminal status `RUN_ERROR`
- `-40` for terminal status `RUN_CANCELLED`
- `-20` for terminal status `RUN_PARTIAL`
- `-25` if any validator result for the run has `VAL_FAILED`
- `-15` if any validator result for the run has `VAL_ERROR`
- `-10` if `iteration_count >= 3`
- `-10` if any phase row for the run has `attempts >= 3`
- `-10` if the latest persisted phase row for any phase has non-null `error_text`

Score-to-grade mapping:

- `A` for `>= 90`
- `B` for `>= 75`
- `C` for `>= 60`
- `D` for `>= 45`
- `F` for `< 45`

### Entropy ranking contract

The entropy ranking formula in this plan is the v1 source of truth for this task.

Run-level entropy score applies:

- `+40` if run grade is `D` or `F`
- `+25` if terminal status is `RUN_ERROR`
- `+20` if `iteration_count >= 3`
- `+15` if any phase row has `attempts >= 3`
- `+20` if any validator result for the run has `VAL_FAILED`
- `+10` if any validator result for the run has `VAL_ERROR`

Bucket scoring:

- compute run-level entropy score first
- group by `(repository_key, workflow_name, actor_email)`
- bucket `score` is the maximum run-level score in that bucket
- the bucket's representative "max-score run" is chosen by `score DESC`, then `started_utc DESC`, then `run_id DESC` as the deterministic tiebreaker
- bucket `latest_started_utc` is the most recent run start time in that bucket
- sort by `score DESC`, then `latest_started_utc DESC`

### Actor handling contract

Actor identity in this repo is trigger actor identity via `actor_email`, not internal subagent identity.

Actor-grouped outputs must:

- bucket null `actor_email` as the literal value `unknown`

## Canonical Fact Model

Every analytics tool must aggregate from a clearly defined fact grain.

### `run_fact`

One row per workflow run.

Source tables:

- `ops.workflow_runs`
- `core.reference_values`
- `catalog.repositories`

Fields:

- `run_id`
- `repository_key`
- `workflow_name`
- `actor_email` with null mapped to `unknown`
- normalized status code
- terminal flag
- `started_utc`
- `completed_utc`
- `duration_ms` only when both timestamps exist
- `iteration_count`

### `phase_fact`

One latest-state row per `(run_id, phase_id)`.

Source tables:

- `ops.workflow_phase_states`
- `ops.workflow_runs`
- `catalog.repositories`

Fields:

- `run_id`
- `repository_key`
- `workflow_name`
- `phase_id`
- raw `status`
- phase status bucket
- `decision`
- `attempts`
- `started_utc`
- `completed_utc`
- `duration_ms` only when both timestamps exist
- `error_text`

### `validator_fact`

One row per `(run_id, phase_id, validator_code, attempt_number)`.

Source tables:

- `ops.workflow_validator_results`
- `ops.workflow_runs`
- `catalog.repositories`
- `core.reference_values`

Fields:

- `run_id`
- `repository_key`
- `workflow_name`
- `phase_id`
- `validator_code`
- `validator_name`
- `attempt_number`
- normalized validator status code
- `failure_reason_code`
- `failure_reason`
- `created_utc`
- `started_utc`
- `completed_utc`

### `artifact_latest_fact`

One latest row per `(run_id, artifact_name)`.

Source tables:

- `ops.workflow_artifacts`
- `ops.workflow_runs`
- `catalog.repositories`

Important limitation:

- artifact history is latest-state only
- no tool may claim full per-iteration artifact history

### `run_grade_fact`

Derived, not persisted.

One row per eligible run, computed from:

- `run_fact`
- `phase_fact`
- `validator_fact`

Fields:

- `run_id`
- `repository_key`
- `workflow_name`
- `actor_email`
- `score`
- `grade`
- component breakdown used to compute the score

### Fact-query implementation structure

Implementation preference for v1:

- `src/memory_knowledge/admin/analytics.py` should own the analytics query layer
- each canonical fact should have one clearly named base query/helper rather than duplicating near-identical SQL across MCP tools
- preferred helper split:
  - one helper for `run_fact`
  - one helper for `phase_fact`
  - one helper for `validator_fact`
  - one helper for `artifact_latest_fact`
  - one helper for `run_grade_fact`
- per-tool helpers may compose those base helpers, but tools should not each redefine the fact SQL independently

Query-shape guidance:

- prefer raw SQL in `analytics.py` that mirrors the fact grains and response contracts in this plan
- do not hide core analytics semantics behind overly generic query-builder abstractions
- keep fact-building SQL and response-shaping Python separate:
  - SQL defines fact grain, joins, filters, buckets, ordering, and aggregates
  - Python maps rows into the MCP response envelopes and nested collection shapes
- planning enrichment should be implemented as a post-aggregation helper over the final bucket rows, not fused into every base fact query

Anti-patterns to avoid:

- copy-pasting slightly different fact SQL into multiple MCP tool handlers
- letting MCP tool handlers own the primary analytics SQL instead of `analytics.py`
- mixing planning many-to-many joins into the base aggregate SQL in a way that can change counts
- encoding caller-visible ordering or tie-break rules only in Python if the SQL can return non-deterministic row order

## Eligibility Matrix

Every tool must state which runs are eligible.

### `get_agent_performance_summary`

Eligible runs:

- all runs in `run_fact`

### `get_phase_quality_summary`

Eligible runs:

- only runs with at least one `phase_fact` row

### `get_validator_failure_summary`

Eligible runs:

- only runs with at least one `validator_fact` row

### `get_loop_pattern_summary`

Eligible runs:

- all runs in `run_fact`
- optionally enriched with `phase_fact` and `artifact_latest_fact` when present

### `get_quality_grade_summary`

Eligible runs:

- terminal runs only
- terminal status in:
  - `RUN_SUCCESS`
  - `RUN_PARTIAL`
  - `RUN_ERROR`
  - `RUN_CANCELLED`
- must also have post-adoption analytics telemetry present:
  - at least one phase row
  - at least one validator row
- if a run has zero validator rows, it is excluded from grade eligibility in v1

### `list_entropy_sweep_targets`

Eligible runs:

- same eligibility as `run_grade_fact`

Every tool whose eligibility excludes runs must expose:

- `eligible_run_count`
- `excluded_run_count`

and, for post-adoption-only tools:

- `coverage.historical_complete = false`
- `coverage.basis = "post_adoption_only"`

## Persistence Changes

### 1. `save_workflow_phase_state`

Purpose:

- persist phase execution state for a workflow run

Request shape:

```json
{
  "run_id": "uuid",
  "phase_id": "string",
  "status": "pending|running|success|error|cancelled",
  "decision": "string|null",
  "handoff_text": "string|null",
  "attempts": 1,
  "started_utc": "ISO-8601|null",
  "completed_utc": "ISO-8601|null",
  "error_text": "string|null",
  "clear_error_text": false,
  "metrics_json": {},
  "correlation_id": "uuid|null"
}
```

Response shape:

```json
{
  "run_id": "uuid",
  "tool_name": "save_workflow_phase_state",
  "status": "success",
  "data": {
    "run_id": "uuid",
    "phase_id": "string",
    "saved": true
  },
  "error": null,
  "duration_ms": 12
}
```

Write contract:

- first write for `(run_id, phase_id)` must include `status`
- if first write omits `attempts`, persist `1`
- this upgrade uses both: migration 008 changes DB default to `1` AND write-path uses `COALESCE($attempts, 1)`
- upsert must set `updated_utc = NOW()` on conflict, matching `save_workflow_artifact` pattern
- ON CONFLICT `(workflow_run_id, phase_id)` DO UPDATE SET field rules:
  - write path must use read/merge semantics, not raw `EXCLUDED.*` alone
  - `status` — required on first write, preserved on sparse updates
  - `decision` — preserved when omitted
  - `handoff_text` — preserved when omitted
  - `attempts` — preserved when omitted, first-write defaults to `1`
  - `started_utc` — preserved when omitted
  - `completed_utc` — preserved when omitted, never cleared in v1
  - `error_text` — preserved when omitted, cleared only by explicit `clear_error_text = true`
  - `metrics_json` — preserved when omitted; replaced when explicitly provided; explicit `null` is invalid in v1 and must return an explicit `WorkflowResult` error
  - `updated_utc` — `NOW()` (always overwritten)

Server behavior must match existing workflow write tools:

- `bind_run_context`
- `check_remote_write_guard`
- explicit `WorkflowResult` error when `run_id` cannot be resolved

### 2. `ops.workflow_validator_results`

Schema:

- `id BIGSERIAL PRIMARY KEY`
- `workflow_run_id BIGINT NOT NULL REFERENCES ops.workflow_runs(id) ON DELETE CASCADE`
- `phase_id VARCHAR(100) NOT NULL`
- `validator_code VARCHAR(100) NOT NULL`
- `validator_name VARCHAR(255) NOT NULL`
- `attempt_number INT NOT NULL`
- `status_id BIGINT NOT NULL REFERENCES core.reference_values(id)`
- `failure_reason_code VARCHAR(100)`
- `failure_reason TEXT`
- `details_json JSONB`
- `correlation_id UUID`
- `started_utc TIMESTAMPTZ`
- `completed_utc TIMESTAMPTZ`
- `created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Uniqueness:

- `UNIQUE (workflow_run_id, phase_id, validator_code, attempt_number)`

Rationale:

- preserve validator attempt history
- avoid latest-state/historical mismatch in grade and entropy logic

### 3. `save_workflow_validator_result`

Purpose:

- persist validator outcomes independently from generic phase-state rows

Request shape:

```json
{
  "run_id": "uuid",
  "phase_id": "string",
  "validator_code": "OUTPUT_CONTRACT|EVIDENCE_GROUNDING|MEMORY_PROPOSAL",
  "validator_name": "string",
  "attempt_number": 1,
  "status_code": "VAL_PENDING|VAL_PASSED|VAL_FAILED|VAL_SKIPPED|VAL_ERROR",
  "failure_reason_code": "string",
  "failure_reason": "string",
  "clear_failure_reason_code": false,
  "clear_failure_reason": false,
  "details_json": {},
  "clear_details_json": false,
  "started_utc": "ISO-8601|null",
  "completed_utc": "ISO-8601|null",
  "correlation_id": "uuid|null"
}
```

Response shape:

```json
{
  "run_id": "uuid",
  "tool_name": "save_workflow_validator_result",
  "status": "success",
  "data": {
    "run_id": "uuid",
    "phase_id": "string",
    "validator_code": "string",
    "attempt_number": 1,
    "saved": true
  },
  "error": null,
  "duration_ms": 12
}
```

Server behavior must match existing workflow write tools:

- `bind_run_context`
- `check_remote_write_guard`
- explicit `WorkflowResult` error when `run_id` cannot be resolved
- explicit `WorkflowResult` error when `status_code` cannot be resolved

Write semantics:

- same-key writes for `(workflow_run_id, phase_id, validator_code, attempt_number)` must upsert
- write path must use read/merge semantics, not raw `EXCLUDED.*` alone
- required fields must always be re-sent on update:
  - `phase_id`
  - `validator_code`
  - `validator_name`
  - `attempt_number`
  - `status_code`
- `validator_name` is display text for the canonical `validator_code`
- for a given persisted `(workflow_run_id, phase_id, validator_code, attempt_number)` row, `validator_name` may be updated on upsert, but analytics grouping remains keyed by canonical `validator_code`, not by `validator_name`
- implementations must not infer validator identity from `validator_name`; canonical identity is always `validator_code`
- optional field rules for v1:
  - `failure_reason_code` — preserved when omitted; replaced when explicitly provided; cleared only by explicit `clear_failure_reason_code = true`
  - `failure_reason` — preserved when omitted; replaced when explicitly provided; cleared only by explicit `clear_failure_reason = true`
  - `details_json` — preserved when omitted; replaced when explicitly provided; cleared only by explicit `clear_details_json = true`
  - `started_utc` — preserved when omitted; replaced when explicitly provided; never cleared in v1
  - `completed_utc` — preserved when omitted; replaced when explicitly provided; never cleared in v1
- explicit `null` for `failure_reason_code`, `failure_reason`, or `details_json` without the matching `clear_*` flag is invalid and must return an explicit `WorkflowResult` error
- if both a replacement value and its matching `clear_*` flag are provided, the request is invalid and must return an explicit `WorkflowResult` error
- `updated_utc` changes on every successful upsert of an existing row

### 4. `get_workflow_run` validator-result readback

Compatibility purpose:

- once validator-result writes exist, direct operational run inspection must return them without requiring callers to infer analytics state indirectly

Response contract addition:

- `get_workflow_run.data.validator_results` must be present
- if a run has no validator-result rows, `validator_results` is an empty array

Validator-result row shape:

```json
{
  "phase_id": "string",
  "validator_code": "string",
  "validator_name": "string",
  "attempt_number": 1,
  "status_code": "VAL_PENDING|VAL_PASSED|VAL_FAILED|VAL_SKIPPED|VAL_ERROR",
  "failure_reason_code": "string|null",
  "failure_reason": "string|null",
  "details_json": {},
  "started_utc": "ISO-8601|null",
  "completed_utc": "ISO-8601|null",
  "created_utc": "ISO-8601"
}
```

Ordering:

- `validator_results` sorts by `phase_id ASC`, then `validator_code ASC`, then `attempt_number ASC`, then `created_utc ASC`

Semantics:

- `status_code` is the canonical normalized validator status from `core.reference_values`
- `validator_results` is direct operational readback from `ops.workflow_validator_results`, not an aggregate
- `validator_results` must not change the existing `phases` or `artifacts` payload contracts

## Analytics Tool Contracts

Common filter inputs:

- `repository_key` optional
- `workflow_name` optional
- `actor_email` optional where relevant
- `since_utc` optional
- `until_utc` optional
- `limit` optional for list-style outputs only
- `include_planning_context` optional where explicitly supported below

Server registration pattern:

- all 6 analytics tools are read-only and must use `bind_run_context`/`clear_run_context` for observability and `@track_tool_metrics` for monitoring
- analytics tools must NOT use `check_remote_write_guard` — that gate is for write operations only, matching the existing read-only tool pattern (`get_workflow_run`, `list_workflow_runs`)

Time-window contract:

- run-level summaries (`get_agent_performance_summary`, `get_loop_pattern_summary`, `get_quality_grade_summary`, `list_entropy_sweep_targets`) filter by `run_fact.started_utc`
- phase-level summaries (`get_phase_quality_summary`) filter by `COALESCE(phase_fact.started_utc, phase_fact.completed_utc)`
- validator-level summaries (`get_validator_failure_summary`) filter by `COALESCE(validator_fact.started_utc, validator_fact.completed_utc, validator_fact.created_utc)`

No-match contract:

- if filters produce zero eligible rows, tools return `status = "success"` with an empty result collection (`summary: []` or `targets: []`)
- zero-match responses are not errors
- zero-match responses return `eligible_run_count = 0`
- zero-match responses return `excluded_run_count = 0`

Average-field contract:

- every `avg_duration_ms` averages only across rows in the bucket where duration is computable from both timestamps
- the denominator for `avg_duration_ms` is the count of rows with non-null computed duration, not total rows in the bucket
- if a bucket has no rows with computable duration, `avg_duration_ms = 0.0`

Nested collection determinism contract:

- `decision_counts` sorts by `count DESC`, then `decision ASC`
- null `decision` values bucket as the literal string `unknown`
- `failure_reason_counts` sorts by `count DESC`, then `failure_reason_code ASC`
- null `failure_reason_code` values bucket as the literal string `unknown`
- `threshold_counts` sorts by `threshold ASC`
- `phase_retry_counts` sorts by `max_attempts DESC`, then `phase_id ASC`
- `reason_codes` sort by this fixed vocabulary order:
  - `LOW_GRADE`
  - `RUN_ERROR`
  - `HIGH_ITERATION_COUNT`
  - `PHASE_RETRY_PRESSURE`
  - `VALIDATOR_FAILED`
  - `VALIDATOR_ERROR`
- `planning_context.projects` sorts by `project_key ASC`
- `planning_context.features` sorts by `feature_key ASC`
- `planning_context.tasks` sorts by `task_key ASC`

Per-tool request contracts:

### `get_agent_performance_summary` request

```json
{
  "repository_key": "string|null",
  "workflow_name": "string|null",
  "actor_email": "string|null",
  "since_utc": "ISO-8601|null",
  "until_utc": "ISO-8601|null",
  "include_planning_context": false
}
```

Applies to:

- all runs in `run_fact`

Actor filter semantics:

- `actor_email = "unknown"` means match rows where source `actor_email` is null and is bucketed to `unknown`
- any other `actor_email` value matches the literal stored email

### `get_phase_quality_summary` request

```json
{
  "repository_key": "string|null",
  "workflow_name": "string|null",
  "phase_id": "string|null",
  "since_utc": "ISO-8601|null",
  "until_utc": "ISO-8601|null"
}
```

Applies to:

- runs with at least one phase row

### `get_validator_failure_summary` request

```json
{
  "repository_key": "string|null",
  "workflow_name": "string|null",
  "validator_code": "string|null",
  "since_utc": "ISO-8601|null",
  "until_utc": "ISO-8601|null"
}
```

Applies to:

- runs with at least one validator row

### `get_loop_pattern_summary` request

```json
{
  "repository_key": "string|null",
  "workflow_name": "string|null",
  "since_utc": "ISO-8601|null",
  "until_utc": "ISO-8601|null",
  "loop_thresholds": [3, 5],
  "include_planning_context": false
}
```

Applies to:

- all runs in `run_fact`

### `get_quality_grade_summary` request

```json
{
  "repository_key": "string|null",
  "workflow_name": "string|null",
  "actor_email": "string|null",
  "since_utc": "ISO-8601|null",
  "until_utc": "ISO-8601|null",
  "include_planning_context": false
}
```

Applies to:

- eligible terminal runs only, per the grade eligibility contract

### `list_entropy_sweep_targets` request

```json
{
  "repository_key": "string|null",
  "workflow_name": "string|null",
  "actor_email": "string|null",
  "since_utc": "ISO-8601|null",
  "until_utc": "ISO-8601|null",
  "limit": 20,
  "include_planning_context": false
}
```

Applies to:

- same eligibility as `run_grade_fact`

### `get_agent_performance_summary`

Aggregate from:

- `run_fact`

Response rows:

```json
{
  "repository_key": "string",
  "workflow_name": "string",
  "actor_email": "string",
  "run_count": 0,
  "terminal_count": 0,
  "non_terminal_count": 0,
  "pending_count": 0,
  "submitted_count": 0,
  "running_count": 0,
  "success_count": 0,
  "partial_count": 0,
  "error_count": 0,
  "cancelled_count": 0,
  "avg_duration_ms": 0.0,
  "avg_iteration_count": 0.0,
  "planning_context": {
    "projects": [
      {
        "project_key": "string",
        "project_name": "string"
      }
    ],
    "features": [
      {
        "feature_key": "string",
        "feature_title": "string"
      }
    ],
    "tasks": [
      {
        "task_key": "string",
        "task_title": "string"
      }
    ]
  }
}
```

Ordering:

- `repository_key`
- `workflow_name`
- `actor_email`

Top-level `data` envelope:

```json
{
  "summary": [],
  "ordering": ["repository_key", "workflow_name", "actor_email"],
  "filters": {
    "repository_key": "string|null",
    "workflow_name": "string|null",
    "actor_email": "string|null",
    "since_utc": "ISO-8601|null",
    "until_utc": "ISO-8601|null",
    "include_planning_context": false
  },
  "eligible_run_count": 0,
  "excluded_run_count": 0
}
```

### `get_phase_quality_summary`

Aggregate from:

- `phase_fact`

Response rows:

```json
{
  "repository_key": "string",
  "workflow_name": "string",
  "phase_id": "string",
  "run_count": 0,
  "execution_count": 0,
  "success_count": 0,
  "error_count": 0,
  "cancelled_count": 0,
  "other_count": 0,
  "decision_counts": [
    {
      "decision": "string",
      "count": 0
    }
  ],
  "avg_attempts": 0.0,
  "avg_duration_ms": 0.0
}
```

Ordering:

- `repository_key`
- `workflow_name`
- `phase_id`

Semantics:

- `run_count` is the number of runs that reached the phase
- `execution_count` is the sum of persisted `attempts` for the phase rows in the bucket
- `success_count`, `error_count`, `cancelled_count`, `other_count`, and `decision_counts` are latest-outcome counts at phase-row grain, not per-attempt history

Top-level `data` envelope:

```json
{
  "summary": [],
  "ordering": ["repository_key", "workflow_name", "phase_id"],
  "coverage": {
    "historical_complete": false,
    "basis": "post_adoption_only"
  },
  "filters": {
    "repository_key": "string|null",
    "workflow_name": "string|null",
    "phase_id": "string|null",
    "since_utc": "ISO-8601|null",
    "until_utc": "ISO-8601|null"
  },
  "eligible_run_count": 0,
  "excluded_run_count": 0
}
```

### `get_validator_failure_summary`

Aggregate from:

- `validator_fact`

Response rows:

```json
{
  "repository_key": "string",
  "workflow_name": "string",
  "validator_code": "string",
  "validator_name": "string",
  "pending_count": 0,
  "pass_count": 0,
  "fail_count": 0,
  "error_count": 0,
  "skipped_count": 0,
  "failure_reason_counts": [
    {
      "failure_reason_code": "string",
      "count": 0
    }
  ]
}
```

Ordering:

- `repository_key`
- `workflow_name`
- `validator_code`

Top-level `data` envelope:

```json
{
  "summary": [],
  "ordering": ["repository_key", "workflow_name", "validator_code"],
  "coverage": {
    "historical_complete": false,
    "basis": "post_adoption_only"
  },
  "filters": {
    "repository_key": "string|null",
    "workflow_name": "string|null",
    "validator_code": "string|null",
    "since_utc": "ISO-8601|null",
    "until_utc": "ISO-8601|null"
  },
  "eligible_run_count": 0,
  "excluded_run_count": 0
}
```

### `get_loop_pattern_summary`

Aggregate from:

- `run_fact`
- `phase_fact`
- `artifact_latest_fact`

Inputs:

- `loop_thresholds` optional list of ints, default `[3, 5]`

Input normalization:

- if omitted or null, use default `[3, 5]`
- otherwise require positive integers only
- deduplicate repeated values
- sort ascending before evaluation
- if any item is non-integer or `<= 0`, return explicit `WorkflowResult` error
- if normalization yields an empty list, return explicit `WorkflowResult` error

Response rows:

```json
{
  "repository_key": "string",
  "workflow_name": "string",
  "run_count": 0,
  "avg_iteration_count": 0.0,
  "threshold_counts": [
    {
      "threshold": 3,
      "run_count": 0
    }
  ],
  "phase_retry_counts": [
    {
      "phase_id": "string",
      "runs_with_attempts_ge_2": 0,
      "max_attempts": 0
    }
  ],
  "max_latest_artifact_iteration": 0,
  "planning_context": {
    "projects": [
      {
        "project_key": "string",
        "project_name": "string"
      }
    ],
    "features": [
      {
        "feature_key": "string",
        "feature_title": "string"
      }
    ],
    "tasks": [
      {
        "task_key": "string",
        "task_title": "string"
      }
    ]
  }
}
```

Ordering:

- `repository_key`
- `workflow_name`

Semantics:

- `phase_retry_counts` is grouped by `phase_id` within each `(repository_key, workflow_name)` bucket
- `runs_with_attempts_ge_2` counts distinct `run_id` values whose latest `phase_fact` row for that `phase_id` has `attempts >= 2`
- `max_attempts` is the maximum latest-row `attempts` value observed for that `phase_id` across all runs in the bucket

Top-level `data` envelope:

```json
{
  "summary": [],
  "ordering": ["repository_key", "workflow_name"],
  "coverage": {
    "historical_complete": false,
    "basis": "run_metrics_complete__phase_retry_post_adoption_only"
  },
  "filters": {
    "repository_key": "string|null",
    "workflow_name": "string|null",
    "since_utc": "ISO-8601|null",
    "until_utc": "ISO-8601|null",
    "loop_thresholds": [3, 5],
    "include_planning_context": false
  },
  "eligible_run_count": 0,
  "excluded_run_count": 0
}
```

### `get_quality_grade_summary`

Aggregate from:

- `run_grade_fact`

Grouped output rule:

- compute run-level grades first
- then group by `(repository_key, workflow_name, actor_email)`
- `latest_run_grade` is taken from the latest run in the bucket by `started_utc DESC`, then `run_id DESC` as the deterministic tiebreaker

Response rows:

```json
{
  "repository_key": "string",
  "workflow_name": "string",
  "actor_email": "string",
  "run_count": 0,
  "avg_score": 0.0,
  "grade_distribution": {
    "A": 0,
    "B": 0,
    "C": 0,
    "D": 0,
    "F": 0
  },
  "latest_run_grade": "A|B|C|D|F",
  "component_averages": {
    "terminal_penalty": 0.0,
    "validator_failure_penalty": 0.0,
    "validator_error_penalty": 0.0,
    "iteration_penalty": 0.0,
    "phase_retry_penalty": 0.0,
    "phase_error_penalty": 0.0
  },
  "planning_context": {
    "projects": [
      {
        "project_key": "string",
        "project_name": "string"
      }
    ],
    "features": [
      {
        "feature_key": "string",
        "feature_title": "string"
      }
    ],
    "tasks": [
      {
        "task_key": "string",
        "task_title": "string"
      }
    ]
  }
}
```

Ordering:

- `repository_key`
- `workflow_name`
- `actor_email`

Top-level `data` envelope:

```json
{
  "summary": [],
  "ordering": ["repository_key", "workflow_name", "actor_email"],
  "coverage": {
    "historical_complete": false,
    "basis": "post_adoption_only"
  },
  "filters": {
    "repository_key": "string|null",
    "workflow_name": "string|null",
    "actor_email": "string|null",
    "since_utc": "ISO-8601|null",
    "until_utc": "ISO-8601|null",
    "include_planning_context": false
  },
  "eligible_run_count": 0,
  "excluded_run_count": 0
}
```

### `list_entropy_sweep_targets`

Aggregate from:

- run-level entropy scores first
- then bucket by `(repository_key, workflow_name, actor_email)`

Response rows:

```json
{
  "repository_key": "string",
  "workflow_name": "string",
  "actor_email": "string",
  "score": 0,
  "reason_codes": ["LOW_GRADE"],
  "supporting_metrics": {
    "max_score_run_grade": "A|B|C|D|F",
    "max_score_run_status": "RUN_ERROR",
    "max_score_run_iteration_count": 0,
    "max_score_run_phase_attempts": 0,
    "max_score_run_validator_failed_count": 0,
    "max_score_run_validator_error_count": 0
  },
  "latest_started_utc": "ISO-8601",
  "planning_context": {
    "projects": [
      {
        "project_key": "string",
        "project_name": "string"
      }
    ],
    "features": [
      {
        "feature_key": "string",
        "feature_title": "string"
      }
    ],
    "tasks": [
      {
        "task_key": "string",
        "task_title": "string"
      }
    ]
  }
}
```

Ordering:

- `score DESC`
- `latest_started_utc DESC`

Reason-code vocabulary for v1:

- `LOW_GRADE`
- `RUN_ERROR`
- `HIGH_ITERATION_COUNT`
- `PHASE_RETRY_PRESSURE`
- `VALIDATOR_FAILED`
- `VALIDATOR_ERROR`

Semantics:

- `score`, `reason_codes`, and `supporting_metrics` describe the bucket's deterministic max-score run, using the same tiebreaker defined in the entropy ranking contract above
- `latest_started_utc` is the most recent run start in the bucket and may belong to a different run

Top-level `data` envelope:

```json
{
  "targets": [],
  "ordering": ["score DESC", "latest_started_utc DESC"],
  "coverage": {
    "historical_complete": false,
    "basis": "post_adoption_only"
  },
  "filters": {
    "repository_key": "string|null",
    "workflow_name": "string|null",
    "actor_email": "string|null",
    "since_utc": "ISO-8601|null",
    "until_utc": "ISO-8601|null",
    "limit": 20,
    "include_planning_context": false
  },
  "eligible_run_count": 0,
  "excluded_run_count": 0
}
```

## Planning Enrichment Contract

Planning enrichment is optional and must be post-aggregation only.

Supported tools for v1 planning enrichment:

- `get_agent_performance_summary`
- `get_loop_pattern_summary`
- `get_quality_grade_summary`
- `list_entropy_sweep_targets`

Request contract:

- `include_planning_context` defaults to `false`
- when `false`, tools return the same core aggregates and empty `planning_context` arrays
- when `true`, tools attach `planning_context` post-aggregation without changing base counts

Response contract:

- `planning_context.projects[] = { project_key, project_name }`
- `planning_context.features[] = { feature_key, feature_title }`
- `planning_context.tasks[] = { task_key, task_title }`

Population rule:

- each object array contains distinct objects keyed by the local canonical key
- values are collected from workflow runs in the aggregate bucket after the bucket's base metrics are fully computed
- enrichment join path is:
  - `ops.workflow_runs.id -> planning.task_workflow_runs.workflow_run_id`
  - `planning.task_workflow_runs.task_id -> planning.tasks.id`
  - `planning.tasks.feature_id -> planning.features.id`
  - `planning.features.project_id -> planning.projects.id`
- all persisted `planning.task_workflow_runs.relation_type` values are eligible in v1
- `relation_type` does not filter or weight enrichment in v1 and is not surfaced in analytics responses

Rules:

- never aggregate directly across raw `planning.task_workflow_runs`
- never let a many-to-many planning join change the base summary counts
- if planning context is attached, attach it after the core aggregation is complete
- task-run links used for enrichment must already satisfy the write-side repo-match invariant below
- the `planning_context` object is always present for supported tools
- if no linked planning data exists for a bucket, `planning_context.projects`, `planning_context.features`, and `planning_context.tasks` are empty arrays
- repo-safe enrichment requires:
  - workflow run repository matches `planning.tasks.repository_id`

## `link_task_to_workflow_run` contract tightening

This analytics upgrade also tightens the existing task/run link contract because that relation is already consumed by non-analytics reads.

Write-side invariant:

- reject any link unless `ops.workflow_runs.repository_id = planning.tasks.repository_id`
- the write-path enforcement must live in the actual `link_task_to_workflow_run` implementation path (`src/memory_knowledge/server.py` and/or `src/memory_knowledge/admin/planning.py`), not only in tests or migration cleanup notes
- cross-repo link attempts must return an explicit `WorkflowResult` error from the MCP tool surface

Read-side invariant:

- any read path that joins `planning.task_workflow_runs` to attach planning context must also enforce `ops.workflow_runs.repository_id = planning.tasks.repository_id`
- this includes `list_workflow_runs_by_actor` and all analytics enrichment queries

Validation requirement:

- extend planning-link tests to reject cross-repo task/run links
- confirm `list_workflow_runs_by_actor` and analytics enrichment both observe only repo-safe links
- `list_workflow_runs_by_actor` must remain one row per workflow run even when multiple repo-safe task links exist
- if multiple repo-safe task links exist for the same run, actor-run recovery must aggregate planning context into nested objects rather than duplicate the run row

Legacy-data cleanup requirement:

- analytics migration 008 must delete or otherwise exclude any preexisting `planning.task_workflow_runs` rows where `ops.workflow_runs.repository_id <> planning.tasks.repository_id`
- cleanup outcome must be validated in tests or migration verification notes before claiming repo-safe enrichment/read behavior

## `list_workflow_runs_by_actor` dedupe contract

Actor-run recovery remains one row per workflow run.

Response row contract:

```json
{
  "run_id": "uuid",
  "repository_key": "string",
  "workflow_name": "string",
  "task_description": "string|null",
  "status_id": 0,
  "status": "string",
  "status_code": "string",
  "status_display_name": "string",
  "is_terminal": false,
  "current_phase": "string|null",
  "iteration_count": 0,
  "started_utc": "ISO-8601|null",
  "completed_utc": "ISO-8601|null",
  "artifact_count": 0,
  "planning_context": {
    "projects": [
      {
        "project_key": "string",
        "project_name": "string"
      }
    ],
    "features": [
      {
        "feature_key": "string",
        "feature_title": "string"
      }
    ],
    "tasks": [
      {
        "task_key": "string",
        "task_title": "string"
      }
    ]
  }
}
```

Read semantics:

- top-level response envelope remains:
  - `data.actor_email`
  - `data.count`
  - `data.runs`
- `data.count` is the number of deduped run rows returned after filtering and limit application
- `data.actor_email` echoes the requested actor filter value
- dedupe key is `run_id`
- `LIMIT` applies after dedupe on the base run row set
- top-level actor-run ordering remains `started_utc DESC`
- legacy flat row fields `task_key`, `task_title`, `feature_key`, `feature_title`, `project_key`, and `project_name` are removed from the public row contract and replaced by nested `planning_context`
- nested `planning_context` arrays follow the same deterministic sort rules defined above
- nested `planning_context.projects`, `planning_context.features`, and `planning_context.tasks` must each be distinct by canonical key
- actor-run recovery must not emit duplicate run rows because of multiple repo-safe task links

## Historical Data Policy

This upgrade uses a future-runs-only policy for phase, validator, grade, and entropy completeness.

Rules:

- pre-upgrade `ops.workflow_runs` and `ops.workflow_artifacts` remain valid for run-level and loop-level summaries
- `get_phase_quality_summary`, `get_validator_failure_summary`, `get_quality_grade_summary`, and `list_entropy_sweep_targets` are only historically complete after producer adoption of the new write APIs
- `get_loop_pattern_summary` is historically complete only for run-level iteration and latest-artifact metrics; `phase_retry_counts` are post-adoption-only
- no mandatory backfill is included because current persisted history is insufficient to reconstruct canonical phase/validator history deterministically
- until bootstrap ownership is reconciled in-repo, any path that relies on `docker/init-pg.sql` precreating workflow tables before Alembic is unsupported for this analytics upgrade
- this task must either reconcile or stamp bootstrap ownership as part of implementation, or explicitly fail analytics-ready Docker validation if that reconciliation is absent

Machine-readable coverage for affected tools:

- `coverage.historical_complete`
- `coverage.basis`
- `eligible_run_count`
- `excluded_run_count`

## Repo-Owned Delivery

This repo owns:

1. analytics persistence migration(s)
   - create `WORKFLOW_VALIDATOR_STATUS`
   - create `ops.workflow_validator_results`
   - `ALTER TABLE ops.workflow_phase_states ALTER COLUMN attempts SET DEFAULT 1`
   - `ALTER TABLE ops.workflow_phase_states ADD COLUMN created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - `ALTER TABLE ops.workflow_phase_states ADD COLUMN updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - `CREATE INDEX ix_workflow_runs_started_utc ON ops.workflow_runs(started_utc)`
   - `CREATE INDEX ix_workflow_phase_states_started_utc ON ops.workflow_phase_states(started_utc)`
   - `CREATE INDEX ix_workflow_validator_results_started_utc ON ops.workflow_validator_results(started_utc)`
   - `CREATE INDEX ix_workflow_validator_results_run ON ops.workflow_validator_results(workflow_run_id)`
   - downgrade must reverse all operations:
     - `DROP INDEX` all 4 new indexes
     - `DROP TABLE ops.workflow_validator_results`
     - `DELETE FROM core.reference_values WHERE reference_type_id = (SELECT id FROM core.reference_types WHERE internal_code = 'WORKFLOW_VALIDATOR_STATUS')`
     - `DELETE FROM core.reference_types WHERE internal_code = 'WORKFLOW_VALIDATOR_STATUS'`
     - `ALTER TABLE ops.workflow_phase_states DROP COLUMN updated_utc`
     - `ALTER TABLE ops.workflow_phase_states DROP COLUMN created_utc`
     - `ALTER TABLE ops.workflow_phase_states ALTER COLUMN attempts SET DEFAULT 0`
   - downgrade scope is schema/reference ownership only
   - downgrade does not define rollback behavior for live server code; write-path validation behavior, repo-match enforcement, and MCP request-contract rules remain governed by the application code present in the checked-out repo revision
2. analytics helper module
   - `src/memory_knowledge/admin/analytics.py`
   - structure `analytics.py` around reusable fact-query helpers plus thin per-tool response mappers
   - preferred layout:
     - fact-query helpers for `run_fact`, `phase_fact`, `validator_fact`, `artifact_latest_fact`, `run_grade_fact`
     - per-tool helpers for each of the 6 analytics responses
     - one planning-enrichment helper used only after base aggregates are complete
   - MCP tool handlers in `src/memory_knowledge/server.py` should stay thin:
     - validate inputs
     - call analytics helpers
     - wrap results in `WorkflowResult`
   - avoid placing primary analytics SQL directly in the MCP tool handlers
3. persistence helpers
   - phase-state writes
   - validator-result writes
   - task/run link validation for repo-safe planning joins
   - `get_workflow_run` validator-result readback so operational inspection stays aligned with the new write surface
4. MCP write tools
   - `save_workflow_phase_state`
   - `save_workflow_validator_result`
   - tighten `link_task_to_workflow_run` to enforce repo-match
5. MCP analytics tools
   - all six analytics tools
6. tests
   - extend `tests/test_workflow_runs.py` for `save_workflow_phase_state`, `save_workflow_validator_result`, `get_workflow_run` validator-result readback, and the deduped `list_workflow_runs_by_actor` response contract (persistence behavior, guard/error behavior, sparse update behavior, attempt contract, one-row-per-run semantics)
   - create `tests/test_analytics.py` for all 6 analytics tools
   - preferred test organization in `tests/test_analytics.py`:
     - one focused section/group per tool
     - shared fixtures only for setup/common fake rows, not for hiding tool-specific assertions
   - minimum per-tool test matrix:
     - `get_agent_performance_summary`
       - status-count aggregation
       - `avg_duration_ms` denominator behavior
       - actor `unknown` bucketing
       - zero-match success behavior
       - planning enrichment on/off behavior
     - `get_phase_quality_summary`
       - latest-row status bucketing
       - `execution_count` as sum of persisted attempts
       - `decision_counts` ordering and `unknown` bucketing
       - coverage envelope semantics
       - zero-match success behavior
     - `get_validator_failure_summary`
       - validator status counts
       - `failure_reason_counts` ordering and `unknown` bucketing
       - canonical validator-code behavior
       - coverage envelope semantics
       - zero-match success behavior
     - `get_loop_pattern_summary`
       - threshold normalization
       - threshold-count aggregation
       - `phase_retry_counts` grouping semantics
       - latest-artifact iteration behavior
       - planning enrichment on/off behavior
       - zero-match success behavior
     - `get_quality_grade_summary`
       - score calculation from the v1 rubric
       - grade distribution
       - deterministic `latest_run_grade`
       - component-average behavior
       - coverage and eligibility semantics
       - zero-match success behavior
     - `list_entropy_sweep_targets`
       - entropy-score calculation from the v1 rubric
       - deterministic representative max-score run behavior
       - `reason_codes` ordering
       - final bucket ordering and `limit` behavior
       - planning enrichment on/off behavior
       - zero-match success behavior
   - cross-tool analytics tests must also cover:
     - repo-safe planning enrichment rules
     - deterministic nested ordering for all nested collections
     - historical coverage flags/basis fields
     - `eligible_run_count` and `excluded_run_count` semantics
   - extend `tests/test_planning_tools.py` to reject cross-repo task/run links and verify repo-safe enrichment inputs
7. documentation updates to `docs/AGENT_INTEGRATION_SPEC.md`:
   - reconcile the doc to the actual MCP surface implemented in `src/memory_knowledge/server.py`, not to a stale 12->20 count delta
   - update the tool inventory, tool namespace table, tool detail sections, permissions matrix, and any count references so they match the live server surface after this upgrade
8. deployment/setup prerequisite documentation
   - update `docs/remote-rollout-runbook.md` so its expected migration list, smoke checks, and actor-run recovery notes match the post-analytics MCP surface and supported bootstrap path
9. bootstrap reconciliation for analytics-ready startup
   - preferred fix: make `docker/init-pg.sql` schema-bootstrap-safe and compatible with Alembic ownership
   - acceptable alternative: explicit Alembic stamping/bootstrap path documented and validated

## Adoption Boundary

External orchestrator adoption is outside this repo’s implementation scope.

Follow-up dependency:

- workflow execution code in the external project must call:
  - `save_workflow_phase_state`
  - `save_workflow_validator_result`

This repo is complete when it is repo-ready, not when external producers have been adopted.

## Deployment / Setup Prerequisites

For analytics-enabled environments, the supported fresh-install path is:

- `alembic upgrade head`

This plan requires explicit bootstrap reconciliation work between:

- `docker/init-pg.sql`
- `migrations/versions/004_workflow_tracking.py`
- `migrations/versions/005_planning_schema.py`
- `migrations/versions/006_task_project_scope.py`
- `migrations/versions/007_task_single_repository.py`

Known ownership drift:

- duplicate ownership of `ops.workflow_runs`
- duplicate ownership of `ops.workflow_artifacts`
- duplicate ownership of `ops.workflow_phase_states`
- `init-pg.sql` is completely missing the `core` schema (`core.reference_types`, `core.reference_values`)
- `init-pg.sql` is completely missing the `planning` schema (all planning tables, external link tables)
- `init-pg.sql` is missing post-migration-004 columns on `ops.workflow_runs`: `status_id`, `actor_email`
- `init-pg.sql` is missing all reference value seed data

The actual gap is not just "duplicate ownership" — `init-pg.sql` is frozen at the migration-004 schema level and is an incomplete, outdated subset of the current schema. Any reconciliation must account for the full scope above, not just the three workflow tables.

Completion requirement for this task:

- local analytics-ready startup must be validated through one explicit supported path
- if that path is Docker-based, bootstrap reconciliation or Alembic stamping must be implemented in-repo and verified
- if that path is non-Docker, the docs must mark raw Docker bootstrap as unsupported until a follow-up resolves ownership drift

This is a deployment/setup prerequisite, not core analytics business logic, but it is still part of the repo-ready upgrade because the analytics schema cannot be treated as complete while bootstrap remains ambiguous.

## Affected Files

- `migrations/versions/008_analytics_schema.py` new analytics migration (`down_revision = "007_task_single_repository"`)
- `src/memory_knowledge/admin/analytics.py`
- `src/memory_knowledge/admin/planning.py`
- `src/memory_knowledge/server.py`
- `tests/...` analytics-focused tests
- `docs/AGENT_INTEGRATION_SPEC.md`
- `docs/remote-rollout-runbook.md`
- `docker/init-pg.sql`
- `migrations/versions/004_workflow_tracking.py` if ownership drift is resolved in-repo
- `migrations/versions/005_planning_schema.py` if ownership drift is resolved in-repo
- `migrations/versions/006_task_project_scope.py` and `migrations/versions/007_task_single_repository.py` as verification references for the current planning repository-scope model

## Validation

1. Unit-test both new write tools for:
   - guard behavior
   - missing run/lookups
   - sparse update behavior
   - validator attempt history
2. Unit-test canonical fact-model queries.
3. Unit-test per-tool row schemas and ordering.
4. Unit-test coverage and eligibility counts.
5. Unit-test repo-safe planning enrichment.
6. Unit-test grading and entropy determinism from the v1 contract.
7. Verify docs/tool inventory updates are consistent with the new MCP surface.
8. Validate the chosen analytics-ready bootstrap/setup path, including the reconciliation or stamping strategy.

Implementation-readiness validation detail:

- validate that `src/memory_knowledge/server.py` MCP handlers remain thin wrappers over helpers in `src/memory_knowledge/admin/analytics.py`
- validate that canonical fact SQL is not duplicated across multiple tool handlers or helper paths
- validate that planning enrichment is applied post-aggregation and cannot change base counts
- validate that tool-level tests assert the caller-visible contracts defined in this plan, not only happy-path row presence

## Completion Criteria

Repo-ready completion:

- missing persistence schema is implemented
- both new write APIs are implemented and tested
- all six analytics tools are implemented and tested
- per-tool response schemas and ordering are fixed and documented
- eligibility and coverage semantics are surfaced
- setup/deployment prerequisites are documented
- MCP surface docs are updated

Producer-adopted completion is explicitly out of scope for this repo task.

## Plan Verification Iteration 1

Verifier loops on this task repeatedly surfaced recurring issue classes:

- missing or inconsistent tool contracts
- ambiguity about aggregation grain
- blurring of repo-owned work vs external adoption
- drift between setup/bootstrap and Alembic ownership
- row-schema placeholders that forced implementers to invent payloads

This rewritten plan resolves those classes structurally by:

- locking v1 contracts up front
- defining canonical fact grains
- separating repo-ready completion from producer adoption
- defining per-tool row schemas and ordering
- making planning enrichment post-aggregation only

## Plan Verification Iteration 2

Verifier loops on this task surfaced additional repo-grounded gaps:

- bootstrap reconciliation text was still under-scoped to migrations `004` and `005` even though the current planning repository-scope model is finalized in `006` and `007`
- the plan claimed existing operational inspection was sufficient without explicitly updating `get_workflow_run` to show the new validator-result telemetry
- deployment/runbook documentation scope did not explicitly include `docs/remote-rollout-runbook.md`, which already documents the supported Alembic path and `list_workflow_runs_by_actor` smoke checks
- planning-link test work was described generically instead of naming the actual current test file that owns that surface

These fixes tighten the plan to the repo's real current state without expanding scope beyond the analytics upgrade.

--- Plan Verification Iteration 2 ---
Findings from verifier: 4
FIX NOW: 4 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

## Plan Verification Iteration 3

Reviewer/critic re-check of the latest plan text found that the last verifier findings were already resolved in the current file:

- `get_workflow_run` validator-result readback is now explicitly called out in the compatibility note and repo-owned delivery scope
- deployment/setup prerequisites now reference the full migration chain through `007_task_single_repository`
- repo-owned documentation scope now explicitly includes `docs/remote-rollout-runbook.md`
- planning-link test scope now names `tests/test_planning_tools.py`

No additional plan edits were required in this iteration.

--- Plan Verification Iteration 3 ---
Findings from verifier: 4
FIX NOW: 0 (no change)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 4 (already resolved in current plan text)

## Plan Verification Iteration 4

Targeted contract review found additional plan-level ambiguities that would force implementers or callers to guess:

- `save_workflow_validator_result` optional sparse-update rules were still underspecified compared with `save_workflow_phase_state`
- planning enrichment described post-aggregation behavior but not the exact join path
- planning-context presence for supported tools needed an explicit empty-array contract when no linked planning rows exist
- `get_loop_pattern_summary.phase_retry_counts` needed explicit bucket aggregation semantics
- `avg_duration_ms` needed an explicit denominator rule
- zero-match behavior needed to be stated as a success contract rather than left implicit in examples
- `get_quality_grade_summary.latest_run_grade` needed a deterministic "latest" rule

These fixes tighten caller-visible contracts without expanding implementation scope.

--- Plan Verification Iteration 4 ---
Findings from verifier: 7
FIX NOW: 7 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

## Plan Verification Iteration 5

Adversarial re-check of the hardened plan surfaced narrower second-order issues:

- `list_entropy_sweep_targets` still needed a deterministic rule for choosing the representative max-score run when multiple runs in a bucket tie on entropy score
- the repo-match tightening for `link_task_to_workflow_run` needed to say explicitly that enforcement belongs in the real write path and must surface a caller-visible MCP error, not just appear in tests or cleanup notes

These fixes keep the plan caller-deterministic and implementation-grounded without expanding scope.

--- Plan Verification Iteration 5 ---
Findings from verifier: 2
FIX NOW: 2 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

## Plan Verification Iteration 6

Verifier/critic reconvergence on the Iteration 5 text found one remaining actionable contract gap:

- `save_workflow_validator_result` required a preserve-vs-clear distinction for nullable optional fields, but the plan still relied on explicit `null` even though the repo's MCP tool boundary uses optional parameters that collapse omission and `null` to the same runtime value

The plan now fixes that by using explicit clear flags for the validator fields that may be cleared in v1, matching the repo's existing pattern of using explicit clear controls when omission and clearing must be distinguished.

--- Plan Verification Iteration 6 ---
Findings from verifier: 2
FIX NOW: 1 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 1 (no change)

## Plan Verification Iteration 7

Fresh verifier/critic reconvergence on the Iteration 6 text found no remaining actionable issues.

The verifier returned `NO_FINDINGS`, and the separate critic independently confirmed `NO_ACTIONABLE_FINDINGS` against the live plan and repo context.

--- Plan Verification Iteration 7 ---
Findings from verifier: 0
FIX NOW: 0 (no change)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

## Plan Verification Iteration 8

Fresh verifier/critic reconvergence under the updated implementer-focused skill found no remaining actionable issues in the current live plan.

The verifier returned `NO_FINDINGS`, and the separate critic independently confirmed `NO_ACTIONABLE_FINDINGS` against the live plan and repo context.

--- Plan Verification Iteration 8 ---
Findings from verifier: 0
FIX NOW: 0 (no change)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

## Plan Verification Iteration 9

Fresh verifier/critic reconvergence on the post-polish plan additions found no remaining actionable issues.

The verifier returned `NO_FINDINGS`, and the separate critic independently confirmed `NO_ACTIONABLE_FINDINGS` against the live plan and repo context, including the new guidance around `analytics.py` structure, fact-query organization, and the expanded test matrix.

--- Plan Verification Iteration 9 ---
Findings from verifier: 0
FIX NOW: 0 (no change)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)
