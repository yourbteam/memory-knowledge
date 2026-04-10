# Memory-Knowledge Prerequisites Plan

## Objective

Implement the repo-owned `memory-knowledge` prerequisites required by `/Users/kamenkamenov/mcp-agents-workflow/Tasks/verifier-critic-upgrades-requirements/memory-knowledge-prerequisites.md` so external workflow producers can:

- persist structured verifier/reviewer findings
- persist critic decisions about those findings
- query same-run suppressions for later verifier rounds
- query aggregated repeated finding patterns for learning and analytics

This plan is limited to this repo. It does not include changes in `mcp-agents-workflow`, but it must leave that repo with a stable integration contract it can call.

## Locked V1 Outcomes

This task is complete only when this repo provides:

1. first-class finding persistence
2. first-class critic-decision persistence
3. same-run suppression lookup
4. repeated-finding analytics
5. agent/finding analytics by stored agent identity rather than only `actor_email`
6. integration documentation that tells external producers exactly how to call the new tools

## Scope Boundary

Included:

- schema changes and reference values in this repo
- MCP write/query tools in this repo
- analytics helper queries in this repo
- tests in this repo
- integration doc updates in this repo

Excluded:

- prompt changes in `mcp-agents-workflow`
- producer-side wiring in `mcp-agents-workflow`
- retroactive parsing of old markdown artifacts into structured findings
- changing the existing phase-state or validator-result model beyond what is strictly needed for consistency

## Canonical V1 Data Model

### Reference types and values

Add new `core.reference_types` entries and seed `core.reference_values` for:

- `WORKFLOW_FINDING_KIND`
  - seed at least:
    - `HALLUCINATED_REFERENCE` / display `Hallucinated Reference` / sort `10` / terminal `false`
    - `FALSE_POSITIVE` / display `False Positive` / sort `20` / terminal `false`
    - `MISSING_REQUIREMENT` / display `Missing Requirement` / sort `30` / terminal `false`
    - `LOGIC_GAP` / display `Logic Gap` / sort `40` / terminal `false`
    - `DUPLICATE` / display `Duplicate` / sort `50` / terminal `false`
    - `UNVERIFIABLE` / display `Unverifiable` / sort `60` / terminal `false`
    - `LOW_PRIORITY_IMPROVEMENT` / display `Low Priority Improvement` / sort `70` / terminal `false`
    - `SCOPE_LEAK` / display `Scope Leak` / sort `80` / terminal `false`
    - `UNKNOWN` / display `Unknown` / sort `90` / terminal `false`
- `WORKFLOW_FINDING_DECISION_BUCKET`
  - seed at least:
    - `FIX_NOW` / display `Fix Now` / sort `10` / terminal `false`
    - `FIX_NOW_PROMOTED` / display `Fix Now Promoted` / sort `20` / terminal `false`
    - `VALID` / display `Valid` / sort `30` / terminal `false`
    - `ACKNOWLEDGE_OK` / display `Acknowledge OK` / sort `40` / terminal `false`
    - `DISMISS` / display `Dismiss` / sort `50` / terminal `false`
    - `FILTERED` / display `Filtered` / sort `60` / terminal `false`
- `WORKFLOW_FINDING_SUPPRESSION_SCOPE`
  - seed at least:
    - `RUN_LOCAL` / display `Run Local` / sort `10` / terminal `false`
- `WORKFLOW_FINDING_STATUS`
  - seed at least:
    - `OPEN` / display `Open` / sort `10` / terminal `false`
    - `RESOLVED` / display `Resolved` / sort `20` / terminal `true`
    - `SUPPRESSED` / display `Suppressed` / sort `30` / terminal `true`

These codes are the canonical stored values. API inputs should accept codes, not freeform labels.

### `ops.workflow_findings`

Add a first-class findings table keyed to repository and workflow run identity.

Required columns:

- `id BIGSERIAL PRIMARY KEY`
- `repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id) ON DELETE CASCADE`
- `workflow_run_id BIGINT NOT NULL REFERENCES ops.workflow_runs(id) ON DELETE CASCADE`
- `workflow_name VARCHAR(255) NOT NULL`
- `phase_id VARCHAR(255) NOT NULL`
- `agent_name VARCHAR(255) NOT NULL`
- `attempt_number INT NOT NULL`
- `artifact_name VARCHAR(255)`
- `artifact_iteration INT`
- `artifact_hash VARCHAR(255)`
- `finding_fingerprint VARCHAR(255) NOT NULL`
- `finding_title TEXT NOT NULL`
- `finding_message TEXT NOT NULL`
- `location TEXT`
- `evidence_text TEXT`
- `finding_kind_id BIGINT NOT NULL REFERENCES core.reference_values(id)`
- `severity VARCHAR(50)`
- `source_kind VARCHAR(100)`
- `status_id BIGINT NOT NULL REFERENCES core.reference_values(id)`
- `actor_email VARCHAR(255)`
- `context_json JSONB`
- `created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()`

V1 uniqueness / upsert contract:

- enforce uniqueness on:
  - `(workflow_run_id, phase_id, attempt_number, finding_fingerprint)`
- writes to the same key update the existing row in place
- repeated occurrences across later attempts create new rows because `attempt_number` changes

Add explicit indexes for expected query paths, at minimum:

- `(repository_id, workflow_run_id)`
- `(workflow_run_id, phase_id, attempt_number, finding_fingerprint)`
- `(repository_id, created_utc)`
- `(repository_id, agent_name, created_utc)`
- `(repository_id, finding_kind_id, created_utc)`

Validation rules:

- empty or whitespace-only `finding_fingerprint` is rejected
- `attempt_number` must be >= 1
- `phase_id` must be non-empty
- repository and run must resolve to the same repository
- if no explicit `status_code` is supplied, the server defaults the finding to `OPEN`

### `ops.workflow_finding_decisions`

Add an append-only critic-decision table.

Required columns:

- `id BIGSERIAL PRIMARY KEY`
- `repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id) ON DELETE CASCADE`
- `workflow_run_id BIGINT NOT NULL REFERENCES ops.workflow_runs(id) ON DELETE CASCADE`
- `workflow_finding_id BIGINT NOT NULL REFERENCES ops.workflow_findings(id) ON DELETE CASCADE`
- `workflow_name VARCHAR(255) NOT NULL`
- `critic_phase_id VARCHAR(255) NOT NULL`
- `critic_agent_name VARCHAR(255) NOT NULL`
- `attempt_number INT NOT NULL`
- `finding_fingerprint VARCHAR(255) NOT NULL`
- `decision_bucket_id BIGINT NOT NULL REFERENCES core.reference_values(id)`
- `actionable BOOLEAN NOT NULL`
- `reason_text TEXT`
- `evidence_text TEXT`
- `suppression_scope_id BIGINT REFERENCES core.reference_values(id)`
- `suppress_on_rerun BOOLEAN NOT NULL DEFAULT FALSE`
- `artifact_name VARCHAR(255)`
- `artifact_iteration INT`
- `artifact_hash VARCHAR(255)`
- `actor_email VARCHAR(255)`
- `context_json JSONB`
- `created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()`

V1 history policy:

- decisions are append-only
- do not upsert over older decision rows
- repeated decisions for the same fingerprint across phases or attempts are allowed and preserved

V1 write-dedup guard:

- reject exact duplicate inserts for the same:
  - `(workflow_finding_id, critic_phase_id, critic_agent_name, attempt_number, decision_bucket_id, created_utc)`
- if `created_utc` is omitted by the caller, the server provides `NOW()` and the request is treated as a new history row

This keeps true history while preventing accidental exact replay only when the caller intentionally supplies the same timestamp.

Deterministic enforcement:

- add a unique constraint on:
  - `(workflow_finding_id, critic_phase_id, critic_agent_name, attempt_number, decision_bucket_id, created_utc)`

Add explicit indexes for expected query paths, at minimum:

- `(repository_id, workflow_run_id)`
- `(workflow_finding_id, created_utc)`
- `(repository_id, decision_bucket_id, created_utc)`
- `(repository_id, suppress_on_rerun, created_utc)`
- `(repository_id, critic_phase_id, created_utc)`

## MCP Tool Contracts

### `save_workflow_finding`

Purpose:

- persist one structured verifier or reviewer finding

Required input:

- `repository_key`
- `run_id`
- `workflow_name`
- `phase_id`
- `agent_name`
- `attempt_number`
- `finding_fingerprint`
- `finding_title`
- `finding_message`

Optional input:

- `artifact_name`
- `artifact_iteration`
- `artifact_hash`
- `location`
- `evidence_text`
- `finding_kind_code`
- `severity`
- `source_kind`
- `status_code`
- `actor_email`
- `context_json`

Behavior:

- resolves `repository_key` and `run_id`
- verifies the resolved run belongs to the resolved repository
- rejects the write if `workflow_name` does not match the canonical workflow name on the resolved run
- validates reference codes where provided
- defaults omitted `finding_kind_code` to `UNKNOWN`
- defaults omitted `status_code` to `OPEN`
- upserts by `(run_id, phase_id, attempt_number, finding_fingerprint)`
- returns `WorkflowResult` with canonical IDs/keys for the stored row

### `save_workflow_finding_decision`

Purpose:

- persist one critic decision about one finding fingerprint

Required input:

- `repository_key`
- `run_id`
- `workflow_name`
- `critic_phase_id`
- `critic_agent_name`
- `attempt_number`
- `finding_fingerprint`
- `decision_bucket_code`
- `actionable`
- `suppress_on_rerun`

Optional input:

- `reason_text`
- `evidence_text`
- `suppression_scope_code`
- `finding_phase_id`
- `artifact_name`
- `artifact_iteration`
- `artifact_hash`
- `actor_email`
- `context_json`
- `created_utc`

Behavior:

- resolves repository and run and verifies they match
- rejects the write if `workflow_name` does not match the canonical workflow name on the resolved run
- validates `decision_bucket_code` against `WORKFLOW_FINDING_DECISION_BUCKET`
- validates `suppression_scope_code` against `WORKFLOW_FINDING_SUPPRESSION_SCOPE`
- defaults omitted `suppression_scope_code` to `RUN_LOCAL`
- resolves exactly one stored finding row for:
  - `run_id`
  - `attempt_number`
  - `finding_fingerprint`
- rejects the write if no matching finding exists
- if multiple findings match that tuple:
  - use optional `finding_phase_id` to disambiguate
  - reject the write if the target is still ambiguous
- inserts append-only history
- returns `WorkflowResult` with the new decision row ID

### `list_workflow_finding_suppressions`

Purpose:

- return findings that later verifier rounds should suppress within the same run

Required input:

- `repository_key`
- `run_id`
- `workflow_name`
- `phase_id`

Optional input:

- `artifact_name`
- `artifact_iteration`
- `artifact_hash`
- `limit`

V1 query rules:

- same-run suppression only
- resolve `repository_key` and `run_id` and reject if the run does not belong to the repository
- scope results to the requested `workflow_name`
- scope results to the requested `phase_id`
- only include decisions where:
  - `suppress_on_rerun = TRUE`
- `decision_bucket_code IN ('ACKNOWLEDGE_OK', 'DISMISS', 'FILTERED')`
- if artifact lineage inputs are provided:
  - filter to materially matching lineage fields
  - exact match on provided non-null lineage fields
- latest relevant decision wins per `finding_fingerprint`

Required output row fields:

- `finding_fingerprint`
- `finding_title`
- `location`
- `decision_bucket`
- `reason_text`
- `suppress_on_rerun`
- `artifact_name`
- `artifact_iteration`
- `artifact_hash`
- `created_utc`

The suppression response should also follow the repo's existing analytics/read-model envelope conventions by returning explicit:

- `ordering`
- `filters`
- query count metadata appropriate to the result set

If no matches exist, return success with `items: []`.

Like existing MCP read tools, the serialized response should still be a `WorkflowResult` wrapper with the described payload nested under top-level `data`.

### `get_finding_pattern_summary`

Purpose:

- aggregate repeated finding patterns for analytics and learning

Required input:

- `repository_key`

Optional input:

- `workflow_name`
- `phase_id`
- `agent_name`
- `finding_kind_code`
- `since_utc`
- `until_utc`
- `limit`

Required output:

- `summary`: array of rows including at least:
  - `finding_kind`
  - `agent_name`
  - `phase_id`
  - `occurrence_count`
  - `dismiss_count`
  - `acknowledge_count`
  - `actionable_count`
  - `top_fingerprints`
  - `top_locations`
  - `top_reason_texts`
- top-level coverage qualifiers:
  - `historical_complete: false`
  - `basis: finding_persistence_adoption_only`
- top-level envelope fields should also include:
  - `ordering`
  - `filters`
  - result-count metadata consistent with existing analytics helpers

If no matches exist, return success with `summary: []`.

Like existing MCP read tools, the serialized response should still be a `WorkflowResult` wrapper with the described payload nested under top-level `data`.

### `get_agent_failure_mode_summary`

Purpose:

- aggregate finding patterns by stored `agent_name` so downstream systems can see repeated failure modes per verifier/reviewer/critic identity

Required input:

- `repository_key`

Optional input:

- `workflow_name`
- `phase_id`
- `agent_name`
- `since_utc`
- `until_utc`
- `limit`

Required output:

- `summary`: array of rows including at least:
  - `agent_name`
  - `finding_kind`
  - `phase_id`
  - `finding_count`
  - `distinct_fingerprint_count`
  - `latest_seen_utc`
  - `dismiss_count`
  - `acknowledge_count`
  - `fix_now_count`
  - `critic_dismiss_rate`
  - `critic_actionable_rate`
  - `repeat_rate`
  - `top_examples`
- top-level coverage qualifiers matching the finding-pattern summary
- top-level envelope fields should also include:
  - `ordering`
  - `filters`
  - result-count metadata consistent with existing analytics helpers

If no matches exist, return success with `summary: []`.

Like existing MCP read tools, the serialized response should still be a `WorkflowResult` wrapper with the described payload nested under top-level `data`.

## Query / Analytics Design

Implementation should live in a new admin helper module adjacent to existing analytics helpers or extend the current analytics module if that keeps the workflow-related summaries cohesive.

V1 aggregation rules:

- repository scoping is mandatory
- all analytics group by stored local repository identity, never by freeform repository text
- join decision history by:
  - `workflow_finding_id`
- when a summary needs the latest decision state, use latest `created_utc`
- when a summary needs history counts, aggregate across all decision rows

Coverage rules:

- new finding analytics are post-adoption only
- return explicit coverage qualifiers instead of implying historical reconstruction

## Documentation Requirements

Update integration docs so an external producer LLM or service knows:

- the new MCP tools
- required payload fields
- reference codes to use
- same-run suppression behavior
- append-only decision-history behavior
- that producer adoption in `mcp-agents-workflow` is still required after this repo work lands

At minimum update:

- `docs/LLM_INTEGRATION_GUIDE.md`
- `docs/AGENT_INTEGRATION_SPEC.md`

## Implementation Sequence

1. Add a new Alembic migration for the reference types/values and `ops` tables.
2. Add low-level admin helpers for reference resolution and finding/decision persistence.
3. Add MCP write tools:
   - `save_workflow_finding`
   - `save_workflow_finding_decision`
4. Add suppression query helper and MCP tool:
   - `list_workflow_finding_suppressions`
5. Add analytics helpers and MCP tools:
   - `get_finding_pattern_summary`
   - `get_agent_failure_mode_summary`
6. Extend `get_workflow_run` only if there is already a clean pattern for nested finding/decision inclusion; otherwise keep this task scoped to the new dedicated tools.
7. Update integration docs.
8. Add targeted tests.
9. Run focused local verification.
10. Run `verify-work` on the isolated commit range after implementation is committed.

## Test Plan

Add targeted coverage for:

- migration creates new reference values and tables
- `save_workflow_finding` upsert behavior
- `save_workflow_finding` rejects empty fingerprints
- `save_workflow_finding` rejects repository/run mismatch
- `save_workflow_finding` rejects workflow-name mismatch
- `save_workflow_finding_decision` preserves append-only history
- `save_workflow_finding_decision` rejects exact duplicate writes deterministically
- suppression lookup returns only non-actionable same-run suppressions
- suppression lookup uses the latest relevant decision when multiple decision rows exist for one finding
- suppression lookup respects artifact lineage filters when provided
- zero-match suppression query returns success with `items: []`
- finding-pattern summary returns deterministic aggregates
- agent-failure summary groups by stored `agent_name`
- zero-match analytics return success with empty arrays
- remote write guard still applies to new write tools

## Acceptance Criteria

This task is done when all of the following are true:

1. A verifier/reviewer producer can write one structured finding row per finding.
2. A critic producer can write one structured decision row per finding decision.
3. A verifier can query same-run suppressible findings without parsing markdown artifacts.
4. Finding-pattern analytics work off structured finding/decision data.
5. Agent-level failure-mode analytics work off stored `agent_name`, not only `actor_email`.
6. The integration docs explain how an external producer should adopt the new tools.
7. Focused tests pass locally.

## Explicit Non-Goals For This Task

- modifying `mcp-agents-workflow`
- building automatic backfill from old artifacts
- inventing new suppression scopes beyond the v1 `RUN_LOCAL` baseline
- replacing phase-level `decision` telemetry with finding-level decisions
