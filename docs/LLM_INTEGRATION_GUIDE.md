# LLM Integration Guide
## Planning, Workflow Telemetry, Analytics, and Run Recovery

**Audience:** another LLM or agent framework integrating with the live `memory-knowledge` MCP server  
**Status:** live and deployed  
**Scope:** repo-owned integration surface after planning, workflow telemetry, and analytics upgrades

For the focused `mcp-agents-workflow` adoption guide for the V4 adaptive guidance surface, see `docs/MCP_AGENTS_WORKFLOW_V4_INTEGRATION.md`.

---

## 1. What This Server Now Does

The `memory-knowledge` server is no longer only a code-memory retrieval service.

It now has four integration surfaces that matter to an external LLM:

1. **Code-memory and retrieval**
   - evidence retrieval
   - context assembly
   - impact analysis
   - repository ingestion and repair
2. **Planning**
   - projects
   - features
   - tasks
   - project/feature repository scope management
   - external PM reference linking
3. **Workflow telemetry**
   - workflow runs
   - workflow phase states
   - workflow validator results
   - workflow findings
   - workflow critic decisions
   - suppression lookup for later verifier rounds
   - task-to-run linkage
   - actor-email run recovery
4. **Analytics**
   - aggregated workflow quality summaries
   - repeated finding-pattern summaries
   - agent failure-mode summaries
   - phase quality summaries
   - validator failure summaries
   - loop pattern summaries
   - quality grades
   - entropy/triage targets
5. **Adaptive triage and workflow guidance**
   - outcome-weighted routing summaries
   - required clarification policies
   - convergence intervention summaries
   - failure-mode playbooks
   - actor adaptation summaries
   - policy governance rollout summaries

If you are integrating another LLM, you should treat this server as:

- the canonical store for workflow run facts and planning state
- the retrieval/evidence layer for code intelligence
- the analytics/reporting layer for workflow quality
- the advisory policy layer for adaptive routing, clarification, convergence, and governance

Do **not** reimplement these data models in the external agent system if you can call the MCP tools directly.

---

## 2. Core Mental Model

### 2.1 Planning hierarchy

- A **project** is the top-level planning container.
- A project owns a set of repositories.
- A **feature** belongs to one project.
- A feature must be attached to one or more repositories already in that project.
- A **task** belongs to one project.
- A task belongs to exactly one repository.
- A task may optionally belong to one feature.
- If a task belongs to a feature, the task repository must also belong to that feature.

### 2.2 Workflow hierarchy

- A **workflow run** belongs to exactly one repository.
- A run can have multiple **artifacts**.
- A run can have multiple **phase states**, but phase-state analytics operate on the latest state per `(run_id, phase_id)`.
- A run can have multiple **validator results**, keyed by:
  - run
  - phase
  - validator code
  - attempt number
- A run can have multiple **findings**, keyed by:
  - run
  - phase
  - attempt
  - finding fingerprint
- A finding can have multiple append-only **critic decisions** over time.
- A task can be linked to one or more workflow runs.

### 2.3 Analytics hierarchy

Analytics are derived from persisted workflow facts. They do not infer missing data.

That means:

- if no phase states are written, phase analytics will be sparse
- if no validator results are written, validator and quality analytics will be sparse
- if only runs are written, run-recovery still works, but analytics completeness is reduced

---

## 3. Important Boundary: What This Repo Owns vs. What The External Integrator Owns

This repo owns:

- the database schema
- the MCP tools
- the storage contracts
- the summary/analytics logic
- the planning model

The external workflow/orchestrator LLM system owns:

- when to call these write tools
- which workflow phases exist
- which validator should emit which status
- correlation between its internal workflow lifecycle and these persisted facts

This is critical:

- `memory-knowledge` does **not** automatically observe your external workflow engine
- your orchestrator must call the write tools deliberately

If you never call:

- `save_workflow_phase_state`
- `save_workflow_validator_result`

then the advanced analytics layer will remain shallow even though the tools exist.

---

## 4. Runtime Guard Modes You Must Handle

Write-path tools are guarded when the server is pointed at remote databases.

That means:

- if the server is in remote mode and `ALLOW_REMOTE_WRITES` is not true, write tools return an error `WorkflowResult`
- if a destructive tool is used and `ALLOW_REMOTE_REBUILDS` is not true, destructive actions are blocked

For an integrator LLM, this means:

- do not assume write-capable behavior just because the tool exists
- handle write-tool errors explicitly
- surface the returned guard error instead of retrying blindly

The planning tools and workflow telemetry write tools are all subject to this guard.

---

## 5. Canonical Contracts You Must Respect

### 4.1 Workflow run status

Canonical run status is normalized through `status_id -> core.reference_values`.

Use these `status_code` values:

- `RUN_PENDING`
- `RUN_SUBMITTED`
- `RUN_RUNNING`
- `RUN_SUCCESS`
- `RUN_PARTIAL`
- `RUN_ERROR`
- `RUN_CANCELLED`

Preferred rule:

- always send `status_code`
- do not prefer legacy `status` unless you are dealing with an older caller

### 4.2 Phase status

Use only:

- `pending`
- `running`
- `success`
- `error`
- `cancelled`

### 4.3 Validator status

Use only:

- `VAL_PENDING`
- `VAL_PASSED`
- `VAL_FAILED`
- `VAL_SKIPPED`
- `VAL_ERROR`

### 4.4 Validator code

Current v1 accepted codes are strict:

- `OUTPUT_CONTRACT`
- `EVIDENCE_GROUNDING`
- `MEMORY_PROPOSAL`

Anything else is rejected.

### 4.5 Attempt numbering

Attempt numbering is 1-based.

- first real attempt = `1`
- never send `0`
- if you retry a validator or phase, increment the attempt

### 4.6 Actor identity

`actor_email` is the trigger actor identity, not internal subagent identity.

Use it for:

- reconnect/recovery
- actor-grouped analytics
- entropy targeting

If you omit it, analytics may bucket the run under `unknown`.

---

## 6. Tool Categories You Need To Know

You do not need every tool for every integration.

### 5.1 Planning tools

Core create/list tools:

- `create_project`
- `list_projects`
- `create_feature`
- `list_features`
- `create_task`
- `list_tasks`
- `get_backlog`

Project scope tools:

- `add_repository_to_project`
- `list_project_repositories`
- `remove_repository_from_project`

Feature scope tools:

- `add_repository_to_feature`
- `list_feature_repositories`
- `remove_repository_from_feature`

Linking tools:

- `link_task_to_workflow_run`
- `link_project_external_ref`
- `link_feature_external_ref`
- `link_task_external_ref`
- `link_repository_external_ref`

Lookup note:

- several planning tools also accept external project and feature references directly
- this is not limited to the explicit `link_*_external_ref` tools
- for example:
  - `create_feature`
  - `list_features`
  - `create_task`
  - `list_tasks`
  - project/feature scope tools
  can resolve by external refs when those mappings already exist

### 5.2 Workflow telemetry tools

Write tools:

- `save_workflow_run`
- `save_workflow_artifact`
- `save_workflow_phase_state`
- `save_workflow_validator_result`

Read tools:

- `get_workflow_run`
- `get_workflow_artifact`
- `list_workflow_runs`
- `list_workflow_runs_by_actor`
- `list_reference_values`

### 5.3 Analytics tools

- `get_agent_performance_summary`
- `get_phase_quality_summary`
- `get_validator_failure_summary`
- `get_loop_pattern_summary`
- `get_quality_grade_summary`
- `list_entropy_sweep_targets`

### 5.4 Adaptive policy and guidance tools

- `get_outcome_weighted_routing_summary`
- `get_clarification_policy`
- `get_required_clarification_policy`
- `get_behavior_policy_status`
- `get_policy_governance_rollout_summary`
- `get_convergence_recommendation_summary`
- `get_failure_mode_playbooks`
- `get_actor_adaptation_summary`
- `triage_request_with_memory`

---

## 7. Recommended Integration Responsibilities

If you are the external integrator LLM, divide responsibilities this way.

### 6.1 Use planning tools when you need durable work structure

Use planning tools when you need to express:

- what project work belongs to
- what repo a task belongs to
- what feature groups multiple tasks
- how to reconnect an execution trace to a planning record

Do not infer planning relationships only from workflow names.

### 6.2 Use workflow telemetry tools during execution

Use workflow telemetry tools to persist:

- run lifecycle
- phase lifecycle
- validator outcomes
- artifacts

Do this as the workflow executes, not only at the end.

### 6.3 Use analytics tools after you have real telemetry

Use analytics tools for:

- dashboards
- triage
- routing review attention
- identifying unstable workflows or actors

Do not expect analytics quality before the write path is being used consistently.

---

## 8. Recommended Write Sequence For A Real Workflow

This is the most important practical section.

If you are orchestrating a workflow, use this sequence.

### 7.1 Optional: create or resolve planning context

If the work item is already known:

- resolve project
- resolve feature if needed
- create or resolve task

If the work item is not yet in planning:

- `create_project` rarely
- `create_feature` when needed
- `create_task` for the concrete repo-scoped unit of work

### 7.2 Start the workflow run

Call `save_workflow_run` with:

- `repository_key`
- `run_id`
- `workflow_name`
- `status_code = RUN_RUNNING` or `RUN_SUBMITTED`
- `actor_email`
- `current_phase`
- `iteration_count`
- optional `task_description`
- optional `context_json`

Important:

- `workflow_name` is required on first write
- later partial updates can omit it
- `context_json` is MCP-object-shaped; send a JSON object, not a JSON string, over MCP

### 7.3 Persist phase transitions

When a phase starts or changes materially:

call `save_workflow_phase_state` with:

- `run_id`
- `phase_id`
- `status`
- optional `decision`
- optional `handoff_text`
- optional `attempts`
- optional `started_utc`
- optional `completed_utc`
- optional `error_text`
- optional `metrics_json`

Rules:

- first write for a phase requires `status`
- do not send both `error_text` and `clear_error_text=true`
- `attempts` must be `>= 1`

### 7.4 Persist validator outcomes

Whenever a validator is invoked:

call `save_workflow_validator_result` with:

- `run_id`
- `phase_id`
- `validator_code`
- `validator_name`
- `attempt_number`
- `status_code`
- optional `failure_reason_code`
- optional `failure_reason`
- optional `details_json`
- optional timestamps

Rules:

- validator codes are strict
- attempt number must be `>= 1`
- intentional inapplicability should be `VAL_SKIPPED`, not silence

### 7.5 Link the run to the planning task

Once you have both:

- task key
- run id

call `link_task_to_workflow_run`.

This is what enables:

- planning context in run recovery
- repo-safe task/run traceability

Important:

- the link is rejected if the task repository and workflow run repository do not match

### 7.6 Complete the run

Call `save_workflow_run` again with:

- same `run_id`
- updated `status_code`
- current phase if applicable
- iteration count if updated
- actor email

Use terminal values such as:

- `RUN_SUCCESS`
- `RUN_PARTIAL`
- `RUN_ERROR`
- `RUN_CANCELLED`

---

## 9. Recommended Planning Usage

### 8.1 Project

Projects are long-lived.

Create them once, not per run.

Use:

- `create_project`
- `add_repository_to_project`
- `list_project_repositories`

### 8.2 Feature

Features are project-scoped and can span multiple repos.

Use:

- `create_feature`
- `add_repository_to_feature`
- `list_feature_repositories`

Feature rules:

- must belong to one project
- must include at least one repo
- feature repos must already belong to the project

### 8.3 Task

Tasks are the most important planning object for workflow linkage.

Use:

- `create_task`
- `list_tasks`
- `link_task_to_workflow_run`

Task rules:

- a task belongs to exactly one project
- a task belongs to exactly one repository
- a task may optionally belong to one feature
- if it belongs to a feature, the task repo must be in that feature

This means:

- if work spans multiple repos, model it as multiple tasks
- do not create a multi-repo task

---

## 10. Recommended External PM Mapping Usage

If your LLM is integrating with ClickUp or another PM system, use external refs as lookup bridges.

You can link:

- project
- feature
- task
- repository

Use tools:

- `link_project_external_ref`
- `link_feature_external_ref`
- `link_task_external_ref`
- `link_repository_external_ref`

Best practice:

- local keys are canonical
- external IDs are alternate lookup inputs
- do not treat external IDs as the system of record for joins

This lets an LLM work in two modes:

1. internal-key-first
2. PM-external-ref-first

while the local database remains authoritative.

---

## 11. Run Recovery And Reconnect

This is a major upgrade surface and should be used explicitly.

If a user disconnects and only remembers their email:

call:

- `list_workflow_runs_by_actor(actor_email, include_terminal=false)`

The response includes:

- run ids
- workflow metadata
- normalized status fields
- phase metadata
- nested `planning_context` when available

`planning_context` can include:

- projects
- features
- tasks

Use this as the primary reconnect path.

Do not force users to remember raw run IDs if `actor_email` is available.

---

## 12. How To Read `get_workflow_run`

`get_workflow_run` is the canonical per-run inspection endpoint.

It returns:

- top-level run fields
- normalized status information
- `context_json`
- `phases`
- `artifacts`
- `validator_results`

You should use it when:

- debugging one workflow
- showing detailed run trace
- investigating validator behavior
- inspecting whether analytics inputs were actually written

This tool is particularly useful for diagnosing “why does analytics look empty?”

If `phases` or `validator_results` are empty here, the analytics layer is not the first thing to blame.

---

## 13. How To Use The Analytics Tools

All analytics tools are read-only.

They aggregate persisted workflow facts.

### 12.1 `get_agent_performance_summary`

Use this for grouped performance by:

- repository
- workflow
- actor email

Filters:

- `repository_key`
- `workflow_name`
- `actor_email`
- `since_utc`
- `until_utc`
- `include_planning_context`

Use when you want:

- who is triggering unstable runs
- actor/workflow quality over time

### 12.2 `get_phase_quality_summary`

Use this for grouped phase quality by:

- repository
- workflow
- phase

Use when you want:

- which phase is failing often
- which phase loops
- whether phase quality improved after a change

### 12.3 `get_validator_failure_summary`

Use this for validator-focused failure analysis.

Use when you want:

- which validator fails most
- whether one validator is noisy
- whether validator failures are concentrated in one workflow

### 12.4 `get_loop_pattern_summary`

Use this when you want to detect repeated iterations or retry-heavy runs.

Important:

- phase retry completeness is post-adoption
- loop thresholds are normalized server-side
- thresholds must be positive integers
- if omitted, the default effective thresholds are `[3, 5]`

### 12.5 `get_quality_grade_summary`

Use this for higher-level quality scoring and grade grouping.

This is derived from:

- terminal run status
- validator outcomes
- iteration counts
- phase attempts
- phase error text

Eligibility rule:

- only terminal runs are eligible
- and only runs with both persisted phase rows and persisted validator rows are eligible

So if a run exists but has no phases or no validator results, it can appear in run inspection but be excluded from grade analytics.

### 12.6 `list_entropy_sweep_targets`

Use this to prioritize what to inspect next.

This is the triage/review targeting tool.

It ranks by entropy score and groups by:

- repository
- workflow
- actor

Eligibility rule:

- the entropy target set is built from the same eligible graded-run population as `get_quality_grade_summary`
- so missing phase or validator telemetry excludes a run from entropy targeting

Use when you want:

- the worst recent buckets
- the best candidates for quality review

### 12.7 Adaptive policy and guidance reads

Use these once your producer is already persisting triage outcomes, phase states, validator results, and findings consistently.

`get_outcome_weighted_routing_summary`

- inspect route quality, failure rate, clarification rate, and route bias
- use it to understand whether a route should be preferred, treated neutrally, or avoided

`get_required_clarification_policy`

- inspect whether clarification should be treated as effectively required before routing
- this is stronger and more directly consumable than the broader `get_clarification_policy`

`get_convergence_recommendation_summary`

- inspect advisory interventions for retry-heavy workflows
- examples:
  - add grounding before retry
  - move validators earlier
  - insert a convergence checkpoint
  - escalate after a retry threshold

`get_failure_mode_playbooks`

- consume normalized next-step playbooks instead of reinterpreting findings, confusion clusters, and convergence summaries manually
- examples:
  - `REQUEST_CLARIFICATION`
  - `ESCALATE_TO_PLANNING_FIRST`
  - `RERUN_RETRIEVAL_CONTEXT`
  - `SUPPRESS_LOW_VALUE_NOISE`
  - `ESCALATE_TO_OPERATOR_REVIEW`

`get_actor_adaptation_summary`

- inspect whether a specific actor should get a more cautious or more streamlined posture
- use it only when the actor has enough history to avoid overfitting

`get_policy_governance_rollout_summary`

- inspect whether adaptive policy artifacts are still advisory, look stable enough for promotion, or need review due to drift or suppression
- this is the main operator-facing rollout/governance read for the adaptive layer

`triage_request_with_memory`

- now returns richer advisory fields:
  - `outcome_weighted_routes`
  - `required_clarification_policy`
  - `requires_clarification_recommendation`
  - `actor_adaptation` when `actor_email` is supplied

Recommended adoption pattern:

1. read these surfaces as advisory only
2. log them alongside actual route and retry decisions
3. compare them with outcomes
4. only then let them influence automatic routing or retry behavior

---

## 14. Coverage And Historical Completeness

Some analytics payloads include `coverage`.

Take this seriously.

Examples:

- `post_adoption_only`
- `run_metrics_complete__phase_retry_post_adoption_only`

Meaning:

- the tool is telling you whether the dataset is historically complete for that metric
- not all metrics are fully reconstructible for pre-adoption runs

Do not treat “empty” or “low count” as necessarily meaning “healthy.”

Sometimes it means:

- telemetry adoption is incomplete for older runs

---

## 15. Zero-Match Semantics

This is an intentional contract.

When analytics filters match no runs:

- the tool should still return `status=success`
- array-shaped outputs should be empty arrays

Examples:

- `summary: []`
- `targets: []`

Do **not** treat zero-match as an error condition.

This is safe and expected for:

- brand-new repos
- narrow filters
- future time windows
- one-off workflow names

---

## 16. Practical Patterns For An Integrator LLM

### 15.1 Good pattern: plan first, run second

1. Resolve or create project.
2. Resolve or create feature if needed.
3. Resolve or create task for one repo.
4. Start workflow run.
5. Persist phase states and validator results during execution.
6. Link task to run.
7. Complete run.
8. Use analytics later for review.

### 15.2 Good pattern: recovery-first

1. Ask user for email if they lost context.
2. Call `list_workflow_runs_by_actor`.
3. If a candidate run is found, inspect it with `get_workflow_run`.
4. Reconnect user to the task/project/feature context.

### 15.3 Good pattern: PM-system-first

1. Resolve project or feature through external refs.
2. Create or locate local planning records.
3. Link the local records back to PM refs.
4. Continue using local keys as canonical state.

### 15.4 Bad pattern: only write final run status

If you only call `save_workflow_run` at the end and never persist phases or validators:

- recovery is okay
- analytics quality is weak

### 15.5 Bad pattern: use workflow names as task identity

Do not assume:

- one workflow name = one task

Use explicit task creation and task-to-run linking.

---

## 17. Common Mistakes To Avoid

- Do not create multi-repo tasks.
- Do not send validator codes outside the accepted set.
- Do not send phase attempts starting at `0`.
- Do not rely on legacy `status` as canonical run state.
- Do not expect analytics to infer missing phase/validator telemetry.
- Do not assume a task can be linked to a run from a different repository.
- Do not ignore write-guard errors in remote mode.
- Do not treat planning state as part of repo-memory export/import.
- Do not expect this repo to automatically instrument your external orchestrator.
- Do not ignore `coverage` metadata in analytics responses.

---

## 18. Minimal Integration Payload Examples

### 17.1 Start a run

```json
{
  "repository_key": "fcsapi",
  "run_id": "8c3f3f75-45d2-4f3e-a4f3-9a8df47f2b52",
  "workflow_name": "implement-endpoint",
  "task_description": "Add customer balance endpoint",
  "status_code": "RUN_RUNNING",
  "actor_email": "engineer@company.com",
  "current_phase": "execution",
  "iteration_count": 1,
  "context_json": {
    "ticket": "API-142",
    "source": "agent-workflow"
  }
}
```

### 17.2 Save a phase

```json
{
  "run_id": "8c3f3f75-45d2-4f3e-a4f3-9a8df47f2b52",
  "phase_id": "execution",
  "status": "running",
  "attempts": 1,
  "decision": "continue",
  "metrics_json": {
    "files_touched": 3
  }
}
```

### 17.3 Save a validator result

```json
{
  "run_id": "8c3f3f75-45d2-4f3e-a4f3-9a8df47f2b52",
  "phase_id": "execution",
  "validator_code": "OUTPUT_CONTRACT",
  "validator_name": "Output Contract",
  "attempt_number": 1,
  "status_code": "VAL_PASSED",
  "details_json": {
    "checked": true
  }
}
```

### 17.4 Create a task

```json
{
  "project_key": "3aa36a6d-16d6-48c2-bf0d-8fa5306c4846",
  "feature_key": "0cd3c2a8-c6ff-4fae-bba5-9bc41dd6f6e4",
  "repository_key": "fcsapi",
  "title": "Implement customer balance endpoint",
  "task_status_code": "TASK_IN_PROGRESS",
  "priority_code": "PRIO_MEDIUM"
}
```

### 17.5 Recover runs by actor

```json
{
  "actor_email": "engineer@company.com",
  "include_terminal": false,
  "limit": 10
}
```

---

## 19. Best Integrator Strategy

If you are another LLM integrating with this system, the best default strategy is:

1. Treat local planning keys and run ids as canonical.
2. Use external PM refs only as lookup bridges.
3. Persist workflow telemetry continuously, not only at the end.
4. Link runs to tasks explicitly.
5. Use `actor_email` everywhere you can.
6. Use analytics only after the write path is adopted consistently.
7. Use `get_workflow_run` when diagnosing missing analytics.

If you follow those rules, you will use the upgraded `memory-knowledge` surface the way it was intended to be used.
