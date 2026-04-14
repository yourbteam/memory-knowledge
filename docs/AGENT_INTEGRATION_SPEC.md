# Agent Integration Specification
## Memory-Knowledge MCP Server

**Version:** 2.0.0  
**Date:** 2026-04-14  
**Status:** Current integration reference  
**Primary audience:** another LLM or agent framework integrating with the live `memory-knowledge` MCP server  
**Target external project:** `mcp-agents-workflow`

---

## 1. Purpose

This document describes what the `memory-knowledge` MCP server exposes today, how an external LLM should use those tools, and which contracts matter for correct integration.

Treat this server as three things at once:

1. the code-memory and retrieval layer for repository intelligence
2. the canonical persistence layer for planning, workflow telemetry, findings, and triage history
3. the reporting and analytics layer derived from persisted workflow and triage facts

Do not mirror these models in another orchestrator if you can call the MCP tools directly. The best integration pattern is:

- external LLM/orchestrator owns judgment, sequencing, and phase logic
- `memory-knowledge` owns persisted facts, retrieval, normalization, and summaries

---

## 2. Transport And Connection Model

### 2.1 Transport

The server is a Starlette HTTP application using MCP streamable HTTP transport.

- It is **not** a stdio MCP server.
- Start the server separately.
- Connect to it over HTTP.

Local MCP endpoint:

- `http://localhost:8000/mcp/`

Operational endpoints:

- `GET /health`
- `GET /ready`

### 2.2 Example `.mcp.json`

```json
{
  "mcpServers": {
    "memory-knowledge": {
      "type": "http",
      "url": "http://localhost:8000/mcp/"
    }
  }
}
```

### 2.3 Tool Namespace

From an MCP client, tools are typically exposed under the `mcp__memory-knowledge__...` namespace.

Example:

- `mcp__memory-knowledge__run_retrieval_workflow`
- `mcp__memory-knowledge__save_workflow_run`
- `mcp__memory-knowledge__triage_request_with_memory`

---

## 3. Integration Mental Model

### 3.1 What this repo owns

This repo owns:

- normalized persistence schemas
- MCP tool contracts
- workflow telemetry and findings storage
- planning model
- triage memory and policy artifacts
- analytics and summarization logic
- remote-write guard behavior

### 3.2 What the external integrator owns

The external LLM or workflow system owns:

- phase definitions
- validator sequencing
- when to call write tools
- retry policy
- convergence policy
- how to turn returned facts into agent behavior

This boundary matters:

- `memory-knowledge` does not observe your external workflow automatically
- analytics only become rich if the producer writes structured workflow and triage facts deliberately

---

## 4. Tool Families

This section is the authoritative integrator-facing grouping of the current server surface.

### 4.1 Retrieval And Reasoning

Use these tools to inspect the codebase and gather grounded evidence.

| Tool | Purpose |
|---|---|
| `run_retrieval_workflow` | Retrieve ranked evidence for a repository query |
| `run_context_assembly_workflow` | Return categorized evidence plus applicable learned rules |
| `run_impact_analysis_workflow` | Traverse graph relationships to estimate change impact |
| `run_blueprint_refinement_workflow` | Refine an artifact or blueprint text |
| `run_route_intelligence_workflow` | Return routing intelligence and prior route metrics |
| `check_job_status` | Poll async job state after background submissions |
| `get_memory_stats` | Return repository-level operational memory statistics |

### 4.2 Learned Memory Lifecycle

Use these only when you want to persist durable repository knowledge.

| Tool | Purpose |
|---|---|
| `run_learned_memory_proposal_workflow` | Propose a grounded learned-memory item |
| `run_learned_memory_commit_workflow` | Approve, reject, or supersede a learned-memory proposal |

### 4.3 Ingestion And Repair

Use these to build or repair the repo memory graph and vector layers.

| Tool | Purpose |
|---|---|
| `run_repo_ingestion_workflow` | Submit async ingestion for a specific repository revision |
| `run_integrity_audit_workflow` | Check cross-store consistency and freshness |
| `run_repair_rebuild_workflow` | Submit async repair for drifted projections |
| `rebuild_revision_workflow` | Rebuild a specific revision’s projections |
| `run_embedding_backfill` | Backfill embeddings for missing or historical data |

### 4.4 Repository Administration

These tools manage repository registration and lifecycle.

| Tool | Purpose |
|---|---|
| `list_repositories` | Enumerate known repositories |
| `register_repository` | Create or update repository registration |
| `purge_repository` | Remove repository data |

### 4.5 Planning

These tools persist the planning hierarchy used by tasks, features, projects, and repository scope.

| Tool | Purpose |
|---|---|
| `create_project` | Create a project |
| `link_project_external_ref` | Attach an external PM/system reference to a project |
| `list_projects` | List projects |
| `add_repository_to_project` | Scope a repository into a project |
| `list_project_repositories` | List project repositories |
| `remove_repository_from_project` | Remove a repository from a project |
| `create_feature` | Create a feature under a project |
| `link_feature_external_ref` | Attach an external PM/system reference to a feature |
| `list_features` | List features |
| `add_repository_to_feature` | Scope a repository into a feature |
| `list_feature_repositories` | List feature repositories |
| `remove_repository_from_feature` | Remove a repository from a feature |
| `create_task` | Create a task under a project and repository |
| `link_task_external_ref` | Attach an external PM/system reference to a task |
| `list_tasks` | List tasks |
| `link_repository_external_ref` | Attach an external system reference to a repository |
| `link_task_to_workflow_run` | Link a task to a workflow run |
| `get_backlog` | Return a planning/backlog-oriented view |

### 4.6 Workflow Telemetry Writes

These are the canonical producer-side write surfaces for workflow execution facts.

| Tool | Purpose |
|---|---|
| `save_workflow_run` | Create or update a workflow run |
| `save_workflow_artifact` | Create or update a named run artifact |
| `save_workflow_phase_state` | Create or update phase state by `(run_id, phase_id)` |
| `save_workflow_validator_result` | Persist validator results by run/phase/code/attempt |
| `save_workflow_finding` | Persist verifier or reviewer findings |
| `save_workflow_finding_decision` | Persist critic decisions and suppression decisions |

### 4.7 Workflow Telemetry Reads

Use these for reconnect, UI, reporting, and post-run review.

| Tool | Purpose |
|---|---|
| `get_workflow_run` | Fetch a run with nested phases and validator results |
| `get_workflow_artifact` | Fetch one artifact for a run |
| `list_workflow_runs` | List runs with filters |
| `list_workflow_runs_by_actor` | List runs by actor with nested planning context |
| `list_reference_values` | Read normalized code sets |
| `list_workflow_finding_suppressions` | Read suppression rules and finding suppression state |

### 4.8 Workflow Analytics

These are read-only summaries over persisted workflow telemetry and findings.

| Tool | Purpose |
|---|---|
| `get_agent_performance_summary` | Aggregate performance by agent |
| `get_phase_quality_summary` | Summarize quality by workflow phase |
| `get_validator_failure_summary` | Summarize validator failure patterns |
| `get_loop_pattern_summary` | Summarize retry and loop behavior |
| `get_quality_grade_summary` | Summarize quality grades |
| `list_entropy_sweep_targets` | Find actors/runs worth deeper review |
| `get_finding_pattern_summary` | Summarize recurring findings |
| `get_agent_failure_mode_summary` | Summarize agent-specific failure modes |

### 4.9 Triage Memory

These tools persist and query case-based routing memory.

| Tool | Purpose |
|---|---|
| `save_triage_case` | Persist a triage decision case |
| `search_triage_cases` | Retrieve similar prior triage cases |
| `record_triage_case_feedback` | Record outcome feedback on a triage case |
| `get_triage_feedback_summary` | Aggregate triage outcomes and correction rates |
| `get_triage_confusion_clusters` | Surface repeated confusion or overlap patterns |
| `get_triage_clarification_recommendations` | Suggest repeated clarification prompts |

### 4.10 Triage Policy And Adaptive Routing

These tools turn triage history into reusable routing and clarification guidance.

| Tool | Purpose |
|---|---|
| `get_routing_policy_recommendations` | Recommend routing policy adjustments |
| `get_clarification_policy` | Synthesize clarification guidance |
| `get_required_clarification_policy` | Return the strongest matching clarification contract for a route |
| `list_triage_behavior_profiles` | Summarize repository/project behavior profiles |
| `refresh_triage_policy_artifacts` | Recompute persisted triage policy artifacts |
| `get_behavior_policy_status` | Report current policy artifact freshness/status |
| `get_policy_governance_rollout_summary` | Summarize policy rollout posture, drift, suppression, and promotion candidates |
| `get_outcome_weighted_routing_summary` | Summarize route quality, failure rates, and route bias by request/workflow shape |
| `triage_request_with_memory` | Use persisted triage memory to guide current request routing |
| `finalize_triage_outcome` | Record final triage outcome and optionally refresh policy artifacts |

### 4.11 Adaptive Workflow And Triage Guidance

These tools synthesize workflow and triage history into actionable advisory guidance.

| Tool | Purpose |
|---|---|
| `get_convergence_recommendation_summary` | Turn loop, validator, and grade history into convergence interventions |
| `get_failure_mode_playbooks` | Map recurring failure signatures to normalized next-step playbooks |
| `get_actor_adaptation_summary` | Derive actor-aware routing and clarification posture from historical behavior |

### 4.12 Working Memory And Feedback

These tools store transient working-session memory and route feedback.

| Tool | Purpose |
|---|---|
| `create_working_session` | Start a working session |
| `record_working_observation` | Add observations to working memory |
| `get_working_session_context` | Read working-session context |
| `end_working_session` | Close a working session |
| `submit_route_feedback` | Persist route feedback for later routing intelligence |

### 4.13 Export And Import

These tools are for repo memory and knowledge transfer, not planning tables.

| Tool | Purpose |
|---|---|
| `export_repo_memory_tool` | Export memory/knowledge for repository-scoped codebase data |
| `import_repo_memory_tool` | Import memory/knowledge for repository-scoped codebase data |

---

## 5. The Most Important Contracts

### 5.1 Planning hierarchy

The planning model is strict:

- a `project` is the top-level planning container
- a project owns a set of repositories
- a `feature` belongs to exactly one project
- a feature can be scoped to one or more repositories already attached to that project
- a `task` belongs to one project and one repository
- a task may optionally belong to one feature
- if a task belongs to a feature, the task repository must also belong to that feature

The practical integrator rule is:

- create project once
- attach repositories to the project
- create features under the project as needed
- ground every task to a specific repository

### 5.2 Workflow run statuses

Preferred write pattern:

- send `status_code`
- do not depend on legacy `status` names unless interacting with older producers

Canonical workflow run status codes:

- `RUN_PENDING`
- `RUN_SUBMITTED`
- `RUN_RUNNING`
- `RUN_SUCCESS`
- `RUN_PARTIAL`
- `RUN_ERROR`
- `RUN_CANCELLED`

### 5.3 Phase statuses

Only use:

- `pending`
- `running`
- `success`
- `error`
- `cancelled`

### 5.4 Validator statuses

Use normalized validator status codes from `WORKFLOW_VALIDATOR_STATUS`.

The expected production values are:

- `VAL_PENDING`
- `VAL_PASSED`
- `VAL_FAILED`
- `VAL_SKIPPED`
- `VAL_ERROR`

If you need certainty in a running environment, read them with:

- `list_reference_values("WORKFLOW_VALIDATOR_STATUS")`

### 5.5 Validator codes

Current accepted validator codes are strict:

- `OUTPUT_CONTRACT`
- `EVIDENCE_GROUNDING`
- `MEMORY_PROPOSAL`

Anything else is rejected by the write surface.

### 5.6 Attempt numbering

Attempt numbering is 1-based.

- first real attempt is `1`
- never write `0`
- increment attempt number on retries

This rule matters for:

- `save_workflow_phase_state`
- `save_workflow_validator_result`
- `save_workflow_finding`

### 5.7 Actor identity

`actor_email` is the human or top-level trigger actor identity, not an internal subagent label.

Use it consistently for:

- reconnect and recovery
- actor-grouped analytics
- entropy targeting
- workload slicing by operator or automation source

If it is omitted, analytics may collapse into weaker or `unknown` buckets.

---

## 6. What External Producers Must Persist

If you want analytics and workflow recovery to be useful, the external producer should write more than just runs.

### 6.1 Minimum viable telemetry

At minimum, write:

- `save_workflow_run`

This gives you:

- run history
- basic reconnect/recovery
- actor-based lookup

### 6.2 Recommended workflow telemetry

For meaningful workflow analytics, also write:

- `save_workflow_phase_state`
- `save_workflow_validator_result`

This gives you:

- phase quality summaries
- validator failure summaries
- loop and retry pattern analytics
- more meaningful run detail in `get_workflow_run`

### 6.3 Full findings loop

For reviewer/verifier/critic loops, also write:

- `save_workflow_finding`
- `save_workflow_finding_decision`

This gives you:

- recurrent finding patterns
- agent failure mode summaries
- suppression and critic-decision history

### 6.4 Triage loop

For adaptive routing and clarification, use:

- `save_triage_case`
- `record_triage_case_feedback` or `finalize_triage_outcome`
- `refresh_triage_policy_artifacts` when you want policy artifacts refreshed explicitly

This gives you:

- case-based routing memory
- clarification recommendations
- behavior policy synthesis

---

## 7. Read Contracts That Matter Most

### 7.1 `get_workflow_run`

This is the canonical run read surface.

Important current behavior:

- returns nested `phases`
- returns nested `validator_results`
- should be your first read when reconstructing a run

### 7.2 `list_workflow_runs_by_actor`

Use this for reconnect, operator history, and entropy targeting.

Important current behavior:

- returns nested `planning_context`
- do not depend on legacy flat planning fields

### 7.3 Analytics zero-match behavior

Analytics tools should still return successful envelopes when filters match no data.

External callers should expect:

- success status
- empty arrays or empty summaries
- no need to treat zero-match as an error condition

---

## 8. Findings And Critic Integration

### 8.1 Finding lifecycle

A finding is not just a free-text comment.

A persisted finding should represent:

- workflow run
- phase
- attempt number
- stable fingerprint
- title and message
- optional artifact/location/evidence context
- optional severity and kind codes

### 8.2 Critic decision lifecycle

Critic decisions are append-only judgments over findings.

Use them to record:

- keep/fix-now style decisions
- dismissal decisions
- suppression decisions
- rationale for later reviewer passes

### 8.3 Suppression lookups

Use `list_workflow_finding_suppressions` when later loops need to know whether a finding pattern is intentionally suppressed.

---

## 9. Triage Integration Guidance

### 9.1 When to use triage memory

Use triage memory when your orchestrator needs to decide:

- what kind of request this is
- whether clarification is needed
- which workflow should be selected
- whether prior cases suggest a better route

### 9.2 Write/read cycle

Recommended cycle:

1. call `triage_request_with_memory` or `search_triage_cases`
2. choose routing decision
3. persist the case with `save_triage_case`
4. after execution, record the outcome with `finalize_triage_outcome`
5. read policy surfaces such as:
   - `get_routing_policy_recommendations`
   - `get_clarification_policy`
   - `get_required_clarification_policy`
   - `get_outcome_weighted_routing_summary`
   - `list_triage_behavior_profiles`
   - `get_behavior_policy_status`
   - `get_policy_governance_rollout_summary`

### 9.3 V4 adaptive guidance

The current triage and workflow guidance layer is advisory but materially richer than earlier versions.

Important V4 reads:

- `get_outcome_weighted_routing_summary`
  - inspect route quality, failure rate, clarification rate, and route bias
- `get_required_clarification_policy`
  - determine whether clarification should be treated as effectively required for a route
- `get_convergence_recommendation_summary`
  - inspect loop-driven intervention guidance such as moving validators earlier or adding grounding before retry
- `get_failure_mode_playbooks`
  - consume normalized next-step playbooks instead of interpreting findings and confusion clusters manually
- `get_actor_adaptation_summary`
  - inspect whether a given actor should get a more cautious or more streamlined posture
- `get_policy_governance_rollout_summary`
  - inspect which adaptive policies are only advisory, which look stable, and which need review

`triage_request_with_memory` now also returns richer advisory context:

- `outcome_weighted_routes`
- `required_clarification_policy`
- `requires_clarification_recommendation`
- `actor_adaptation` when `actor_email` is supplied

Integration rule:

- do not blindly auto-enforce these advisory outputs on first adoption
- log and inspect them first
- once the external orchestrator is confident in the signals, selectively wire them into route choice, clarification prompting, and retry intervention

### 9.4 Outcome normalization

Triage outcome statuses are normalized. Do not invent arbitrary outcome strings without aligning them to the currently supported reference values and server expectations.

If in doubt, keep your producer aligned with the existing tooling already in this repo and use current response patterns as the source of truth.

---

## 10. Remote Guard Behavior

Write-path tools are guarded when the server points at remote databases.

Important guard rules:

- if remote mode is active and `ALLOW_REMOTE_WRITES` is not enabled, write tools return an error `WorkflowResult`
- destructive or rebuild-style operations also require `ALLOW_REMOTE_REBUILDS`

For an external integrator, this means:

- tool existence does not imply write permission
- inspect error responses explicitly
- do not blind-retry blocked writes
- surface guard failures to the operator or controlling workflow

---

## 11. Recommended Integration Patterns

### 11.1 Codebase question

Recommended sequence:

1. `run_retrieval_workflow` or `run_context_assembly_workflow`
2. optionally `run_impact_analysis_workflow`
3. synthesize answer externally
4. propose learned memory only if the conclusion is durable and grounded

### 11.2 Implementation workflow telemetry

Recommended sequence:

1. `save_workflow_run` at submission/start
2. `save_workflow_phase_state` as phases advance
3. `save_workflow_validator_result` after validators complete
4. `save_workflow_finding` for concrete findings
5. `save_workflow_finding_decision` for critic results
6. `get_workflow_run` and analytics tools for review and reporting

### 11.3 Triage-assisted routing

Recommended sequence:

1. `triage_request_with_memory`
2. `save_triage_case`
3. execute selected route
4. `finalize_triage_outcome`
5. read policy recommendation tools when tuning behavior

### 11.4 Planning-grounded feature execution

Recommended sequence:

1. ensure project exists
2. ensure repository is attached to project
3. create or resolve feature if needed
4. create task grounded to one repository
5. link workflow runs back to the task with `link_task_to_workflow_run`

---

## 12. Common Integrator Mistakes

- Treating the server as stdio MCP instead of HTTP MCP
- Writing only `save_workflow_run` and expecting rich analytics
- Using ad hoc status strings instead of normalized status codes
- Using subagent names instead of stable `actor_email`
- Sending attempt number `0`
- Treating analytics zero-match responses as failures
- Reimplementing planning or workflow schemas outside the server instead of calling the canonical write tools
- Using export/import for planning tables rather than repository-scoped memory/knowledge data

---

## 13. Current Practical Recommendation

If another LLM is integrating today, the most important surfaces to adopt are:

- retrieval and context assembly for grounded code reasoning
- planning tools for project/feature/task grounding
- workflow telemetry writes for runs, phases, and validators
- findings and decision writes for reviewer loops
- analytics reads for operator summaries and convergence monitoring
- triage memory and policy tools for adaptive routing

That combination is the current intended operating model of this repo.
