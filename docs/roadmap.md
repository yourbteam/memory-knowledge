# Roadmap

## Recently Completed

### Analytics Tools Upgrade
**Status:** Implemented and shipped.
**Plan:** `Tasks/analytics-tools/plan.md`
**Delivered:**
- 2 new MCP write tools: `save_workflow_phase_state`, `save_workflow_validator_result`
- 6 analytics tools:
  - `get_agent_performance_summary`
  - `get_phase_quality_summary`
  - `get_validator_failure_summary`
  - `get_loop_pattern_summary`
  - `get_quality_grade_summary`
  - `list_entropy_sweep_targets`
- migration `008_analytics_schema`
- workflow/planning/analytics test coverage
- `get_workflow_run` validator-result readback
- analytics-facing `AGENT_INTEGRATION_SPEC` reconciliation
- analytics rollout runbook and supported bootstrap-path clarification

### Workflow Findings + LLM Integration
**Status:** Implemented.
**Plan:** `Tasks/memory-knowledge-prerequisites/plan.md`
**Delivered:**
- migration `009` workflow findings persistence
- findings administration/query layer
- server integration for findings surfaces
- LLM integration guide and workflow findings operator documentation
- auth/clone/runtime support required for external workflow producer adoption

### Triage Memory v1
**Status:** Implemented.
**Plan:** `Tasks/triage-memory-server-implementation/plan.md`
**Delivered:**
- migration `010_triage_memory`
- core triage tools:
  - `save_triage_case`
  - `search_triage_cases`
  - `record_triage_case_feedback`
  - `get_triage_feedback_summary`
- triage analysis tools:
  - `get_triage_confusion_clusters`
  - `get_triage_clarification_recommendations`
- normalized triage outcome statuses via `core.reference_values`
- historic triage re-embedding/backfill support
- explicit hybrid ranking for `search_triage_cases`

### Triage + Workflow Intelligence V3
**Status:** Implemented and rolled out.
**Plans:**
- `Tasks/triage-lifecycle-normalization-v3/plan.md`
- `Tasks/triage-policy-synthesis-v3/plan.md`
- `Tasks/triage-adaptive-ranking-v3/plan.md`
- `Tasks/triage-governance-composed-tools-v3/plan.md`
**Delivered:**
- stronger triage lifecycle modeling
- routing policy synthesis and clarification policy synthesis
- repository-aware behavioral profiles
- governance metadata and persisted policy artifacts
- higher-level integrator tools:
  - `refresh_triage_policy_artifacts`
  - `get_behavior_policy_status`
  - `triage_request_with_memory`
  - `finalize_triage_outcome`
- adaptive ranking improvements connected to prior outcomes and clarification signals

### Live Remote Rollout Validation
**Status:** Completed.
**Delivered:**
- remote migrations applied successfully
- live app deployed and restarted successfully
- `/health` verified
- readiness diagnostics exercised; current Neo4j readiness degradation is tracked under `Next Up`
- live MCP smoke checks completed against the deployed server

### Agent Integration Spec Reconciliation
**Status:** Completed.
**Delivered:**
- replaced stale count- and persona-heavy document structure
- reconciled the spec around the current live MCP surface
- documented planning, workflow telemetry, findings, analytics, triage memory, and triage policy tooling as one current integrator reference

### `docker/init-pg.sql` Bootstrap Deprecation
**Status:** Completed.
**Plan:** `Tasks/init-pg-bootstrap-reconciliation/plan.md`
**Delivered:**
- removed the legacy snapshot from the active local Docker bootstrap path
- documented `alembic upgrade head` as the supported PostgreSQL bootstrap path
- validated fresh local bootstrap against the current migration line
- kept `docker/init-pg.sql` only as a deprecated historical snapshot

### Remote Repository Knowledge Refresh
**Status:** Completed.
**Delivered:**
- refreshed and verified the active deployed repository catalog entries:
  - `css-fe`
  - `fcs-admin`
  - `fcsapi`
  - `taggable-server`
  - `millennium-wp`
- forced a full `millennium-wp` refresh onto commit `81d4458f83ab35e6d8fc8376e1bfbe5b5d665dbb`
- confirmed the authoritative `millennium-wp` full run completed and populated the current revision

### Ingestion Control-Plane Hardening
**Status:** Implemented, tested, and deployed.
**Delivered:**
- preserved exception type and traceback context for blank-message ingestion/job failures
- replaced vague blank terminal failures with actionable diagnostics
- prevented duplicate active ingestion submissions for the same repository, commit, branch, and tool shape
- validated the fix with focused tests and a disposable remote-DB integration test
- deployed image `workfloworchreg.azurecr.io/memory-knowledge:latest` digest `sha256:0d2bd9c2eeb024dd015821a79f9c463f153e753284b4fa268a47381ee0a7dc9b`

### Current Pending Work Closure
**Status:** Implemented, deployed, and verified.
**Plan:** `Tasks/current-pending-work-closure/plan.md`
**Delivered:**
- changed readiness semantics so PostgreSQL and Qdrant remain readiness gates while Neo4j graph projection reports explicit degraded status
- preserved actionable Neo4j readiness diagnostics, including blank-message exception types
- removed remote `fcsapi-remote-test` placeholder after guarded cleanup of disposable smoke-test planning, workflow, and triage rows
- verified the deployed repository catalog now contains only `css-fe`, `fcs-admin`, `fcsapi`, `millennium-wp`, and `taggable-server`
- deployed image `workfloworchreg.azurecr.io/memory-knowledge:latest` digest `sha256:8f948d0468b62bc278d6ccd3c9d2edf3a91c2daf2279da2b7b1993d49e32c7e5`
- verified `/health` returns OK and `/ready` returns HTTP 200 with `degraded: ["neo4j"]`

## Next Up

### Graceful Neo4j Degradation Across Tooling
**Priority:** High
**Status:** Proposed
**Problem:** Startup and readiness now allow Neo4j to be degraded while PostgreSQL and Qdrant remain healthy, but several MCP handlers still call `get_neo4j_driver()` directly before entering workflows. In a degraded Neo4j state, retrieval/context tools that could otherwise return PostgreSQL/Qdrant evidence may fail before they can degrade gracefully.
**Goal:** Make Neo4j optional for non-graph-critical paths, passing `None` or returning graph-specific warnings where appropriate instead of failing the full tool call.
**Expected outcome:**
- `run_retrieval_workflow` and `run_context_assembly_workflow` still return usable evidence when Neo4j is unavailable.
- graph-dependent tools clearly report unavailable graph capability instead of producing ambiguous runtime failures.
- readiness semantics and tool behavior match the same degradation contract.
**Likely files:** `src/memory_knowledge/server.py`, `src/memory_knowledge/workflows/retrieval.py`, `src/memory_knowledge/workflows/context_assembly.py`, `src/memory_knowledge/workflows/impact_analysis.py`, focused tests.

### Retrieval Policy Field Wiring
**Priority:** High
**Status:** Proposed
**Problem:** `routing.route_policies` models `third_store`, `semantic_assist_enabled`, `fusion_strategy`, and `rerank_strategy`, but retrieval currently uses only the first/second store and hardcodes persisted rerank strategy as `score_sort`.
**Goal:** Align retrieval behavior with the policy schema so route-policy rows are the real control plane for store order, fan-out, semantic assist, fusion, and reranking.
**Expected outcome:**
- `third_store` is honored when configured and useful.
- `semantic_assist_enabled` controls semantic auxiliary behavior instead of being passive metadata.
- `fusion_strategy` and `rerank_strategy` drive score combination and persisted route-execution metadata.
- route analytics reflect the policy actually executed.
**Likely files:** `src/memory_knowledge/workflows/retrieval.py`, route-policy tests, possibly seed-policy migration adjustments if defaults need normalization.

### Semantic Triage Memory In Main Advisory Path
**Priority:** High
**Status:** Proposed
**Problem:** `search_triage_cases` can use Qdrant semantic search, but `triage_request_with_memory` currently calls it with `qdrant_client=None`, forcing the high-level advisory path onto lexical/database matching.
**Goal:** Pass the Qdrant client into the high-level triage advisory flow so current routing advice benefits from semantic prior-case retrieval.
**Expected outcome:**
- `triage_request_with_memory` uses the same hybrid/semantic retrieval capability as direct `search_triage_cases`.
- advisory outputs improve for paraphrased or conceptually similar requests.
- fallback to lexical search remains available when Qdrant is unavailable.
**Likely files:** `src/memory_knowledge/server.py`, `src/memory_knowledge/triage_policy.py`, `src/memory_knowledge/triage_memory.py`, triage policy tests.

### Per-Database Remote Secret Seeding
**Priority:** Medium
**Status:** Proposed
**Problem:** DB secret seeding from Azure Key Vault is currently gated on `DATA_MODE=remote`. If the deployment uses `DATA_MODE=local` with a per-database override such as `QDRANT_MODE=remote`, the relevant remote secret may not be seeded.
**Goal:** Base DB secret seeding on each effective database mode, not only the global data mode.
**Expected outcome:**
- `DATABASE_URL`, `QDRANT_API_KEY`, and `NEO4J_PASSWORD` can be seeded independently when their respective effective modes are remote.
- mixed local/remote deployments behave predictably.
- startup logging makes the effective mode and seeded-secret status clear without exposing secret values.
**Likely files:** `src/memory_knowledge/server.py`, `src/memory_knowledge/config.py`, config/startup tests.

## External / Depends On Other Repos

### External Workflow Producer Adoption
**Problem:** The canonical workflow telemetry write surfaces exist in this repo, but the external workflow producer must adopt them before phase and validator analytics become richly populated in production usage.
**Goal:** Update the external orchestrator to call `save_workflow_phase_state` and `save_workflow_validator_result` during execution and validator passes.
**Depends on:** Separate implementation work outside this repository.

## Future

### Triage + Workflow Feedback Automation V4
**Status:** Implemented.
**Umbrella Plan:** `Tasks/triage-feedback-automation-v4/plan.md`
**Goal:** Move from passive reporting and reusable memory toward active routing, clarification, and convergence adaptation driven by persisted outcomes.
**Recommended delivery order:**
- `Tasks/outcome-weighted-routing-v4/plan.md`
- `Tasks/clarification-policy-learning-v4/plan.md`
- `Tasks/convergence-intelligence-v4/plan.md`
- `Tasks/failure-mode-playbooks-v4/plan.md`
- `Tasks/actor-team-adaptation-v4/plan.md`
- `Tasks/policy-governance-rollout-v4/plan.md`

### Outcome-Weighted Routing V4
**Plan:** `Tasks/outcome-weighted-routing-v4/plan.md`
**Status:** Implemented.
**Practical effect:** Route selection starts using downstream outcomes such as success rates, loop counts, and validator failures instead of relying mostly on prior case similarity and static policy artifacts.

### Clarification Policy Learning V4
**Plan:** `Tasks/clarification-policy-learning-v4/plan.md`
**Status:** Implemented.
**Practical effect:** Repeated ambiguity patterns become reusable clarification policy so the system asks the right questions before committing to a workflow.

### Convergence Intelligence V4
**Plan:** `Tasks/convergence-intelligence-v4/plan.md`
**Status:** Implemented.
**Practical effect:** Loop summaries become actionable convergence recommendations, helping orchestrators choose better interventions instead of repeating the same retry pattern.

### Failure-Mode Playbooks V4
**Plan:** `Tasks/failure-mode-playbooks-v4/plan.md`
**Status:** Implemented.
**Practical effect:** Recurring validator, finding, and routing failures get mapped to recommended next-step playbooks rather than remaining analytics-only observations.

### Actor/Team Adaptation V4
**Plan:** `Tasks/actor-team-adaptation-v4/plan.md`
**Status:** Implemented.
**Practical effect:** The platform can adapt route confidence, clarification needs, and workflow defaults based on stable actor or automation-source behavior patterns.

### Policy Governance And Rollout V4
**Plan:** `Tasks/policy-governance-rollout-v4/plan.md`
**Status:** Implemented.
**Practical effect:** Adaptive policies now have a consolidated governance summary showing rollout posture, drift, suppression pressure, and promotion-ready advisory candidates.

### Workflow Process Tooling
**Problem:** The internal task-process ergonomics have been improved through the new task intake and size-aware workflow skills, but the repository does not yet include templates or examples for `light`, `standard`, and `heavy` task artifacts.
**Goal:** Add reusable examples/templates if the team finds repeated task-authoring friction in practice.
