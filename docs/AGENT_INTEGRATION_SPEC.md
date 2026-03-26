# Agent Integration Specification
## Memory-Knowledge MCP Server + mcp-agents-workflow Framework

**Version:** 1.1.0
**Date:** 2026-03-26
**Status:** Ready for Implementation
**Target Project:** mcp-agents-workflow

---

## 1. Overview

This specification defines how to integrate the **memory-knowledge MCP server** (mechanical plane — deterministic code intelligence operations) with the **mcp-agents-workflow framework** (judgment plane — multi-agent LLM orchestration).

The memory-knowledge server provides 12 MCP tools that agents call for retrieval, ingestion, impact analysis, learned memory management, integrity checks, and operational statistics. The agent framework orchestrates 11 persona agents that reason about codebases using these tools.

**Key Principle:** Python handles facts (the MCP server). LLMs handle judgment (the agent personas). Agents invoke workflow-level capabilities, never low-level scripts.

---

## 2. MCP Server Registration

### 2.1 Server Configuration

Add to `.mcp.json` in the mcp-agents-workflow project:

**IMPORTANT:** The memory-knowledge server runs as a Starlette HTTP app with MCP streamable-http transport. It does NOT support stdio. You must start the server separately and connect via HTTP.

**Step 1: Start the memory-knowledge server:**
```bash
cd /path/to/memory-knowledge
# Set required env vars (or use .env file)
export DATABASE_URL="postgresql://memoryknowledge:memoryknowledge@localhost:5432/memoryknowledge"
export QDRANT_URL="http://localhost:6333"
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"
export AUTH_MODE="codex"  # or "api_key" with OPENAI_API_KEY set
# Optional:
# export OPENAI_API_KEY="sk-..." (required when AUTH_MODE=api_key)
# export EMBEDDING_MODEL="text-embedding-3-small"
# export COMPLETION_MODEL="gpt-4o"
# export GENERATE_SUMMARIES="true"
# export REPO_CLONE_BASE_PATH="/tmp/memory-knowledge/repos"
# export SERVER_PORT="8000"
# export LOG_LEVEL="INFO"

uvicorn memory_knowledge.server:app --host 0.0.0.0 --port 8000
```

**Step 2: Register in `.mcp.json`:**
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

The MCP endpoint is at `/mcp/` (Starlette mount with `streamable_http_path="/"`).
Health check: `GET http://localhost:8000/health`
Readiness check: `GET http://localhost:8000/ready`

### 2.2 MCP Tool Namespace

All memory-knowledge tools are prefixed with `mcp__memory-knowledge__` when called from agents:

| MCP Tool Name | Agent Capability Declaration |
|---|---|
| `run_retrieval_workflow` | `mcp__memory-knowledge__run_retrieval_workflow` |
| `run_context_assembly_workflow` | `mcp__memory-knowledge__run_context_assembly_workflow` |
| `run_impact_analysis_workflow` | `mcp__memory-knowledge__run_impact_analysis_workflow` |
| `run_learned_memory_proposal_workflow` | `mcp__memory-knowledge__run_learned_memory_proposal_workflow` |
| `run_learned_memory_commit_workflow` | `mcp__memory-knowledge__run_learned_memory_commit_workflow` |
| `run_blueprint_refinement_workflow` | `mcp__memory-knowledge__run_blueprint_refinement_workflow` |
| `run_repo_ingestion_workflow` | `mcp__memory-knowledge__run_repo_ingestion_workflow` |
| `run_integrity_audit_workflow` | `mcp__memory-knowledge__run_integrity_audit_workflow` |
| `run_repair_rebuild_workflow` | `mcp__memory-knowledge__run_repair_rebuild_workflow` |
| `check_job_status` | `mcp__memory-knowledge__check_job_status` |
| `get_memory_stats` | `mcp__memory-knowledge__get_memory_stats` |
| `run_route_intelligence_workflow` | `mcp__memory-knowledge__run_route_intelligence_workflow` |

---

## 3. MCP Tool Reference

All tools return JSON with this base structure:
```json
{
  "run_id": "uuid",
  "tool_name": "string",
  "status": "success" | "error" | "not_implemented" | "submitted",
  "data": { ... },
  "error": "string or null",
  "duration_ms": 123
}
```

### 3.1 run_retrieval_workflow

**Purpose:** Retrieve evidence from the memory architecture for a given query.

**Parameters:**
| Name | Type | Required | Description |
|---|---|---|---|
| `repository_key` | string | yes | Repository identifier |
| `query` | string | yes | Free-text search query |
| `correlation_id` | string | no | Tracing ID |

**Response `data`:**
```json
{
  "repository_key": "string",
  "evidence": [
    {
      "entity_key": "uuid",
      "title": "string",
      "content_text": "string (code or summary text)",
      "chunk_type": "symbol | file",
      "line_start": 10,
      "line_end": 25,
      "file_path": "src/module.py",
      "symbol_name": "function_name | null",
      "symbol_kind": "function | class | null",
      "retrieval_score": 0.85,
      "retrieval_reason": "postgres | qdrant | both | summary",
      "source_store": "postgres | qdrant | both | summary",
      "commit_sha": "abc123 | null",
      "branch_name": "main | null"
    }
  ],
  "count": 15
}
```

**Usage Notes:**
- Evidence items are ranked by `retrieval_score` (descending)
- `source_store` tells you where the evidence came from (PG fulltext, Qdrant semantic, both, or summary)
- `content_text` contains the actual code chunk or summary text
- Up to 20 evidence items returned

---

### 3.2 run_context_assembly_workflow

**Purpose:** Build a structured evidence package with learned rules.

**Parameters:** Same as retrieval.

**Response `data`:**
```json
{
  "repository_key": "string",
  "exact_matches": [ ...evidence items... ],
  "semantic_matches": [ ...evidence items... ],
  "graph_expansions": [ ...evidence items found in BOTH PG and Qdrant (source_store=="both")... ],
  "summary_evidence": [ ...evidence items... ],
  "applicable_learned_rules": [
    {
      "entity_key": "uuid",
      "title": "Rule title",
      "memory_type": "convention | rule | pattern | caveat",
      "confidence": 0.9,
      "applicability_mode": "repository | file | symbol",
      "body_text": "The rule description...",
      "source": "neo4j | postgres"
    }
  ],
  "route_metadata": { "query": "...", "duration_ms": 150 },
  "total_evidence": 20
}
```

**Usage Notes:**
- Use this instead of raw retrieval when you need categorized evidence + learned rules
- `applicable_learned_rules` contains institutional knowledge that agents should consider
- Empty `applicable_learned_rules` is normal for repos without learned memory

---

### 3.3 run_impact_analysis_workflow

**Purpose:** Determine what a change affects via dependency graph traversal.

**Parameters:**
| Name | Type | Required | Description |
|---|---|---|---|
| `repository_key` | string | yes | Repository identifier |
| `query` | string | yes | Symbol name, file path, or entity_key to analyze |
| `correlation_id` | string | no | Tracing ID |

**Response `data`:**
```json
{
  "start_entity_key": "uuid",
  "query": "getUserById",
  "affected": [
    {
      "entity_key": "uuid",
      "entity_type": "file | symbol",
      "file_path": "src/auth.py",
      "symbol_name": "authenticate | null",
      "symbol_kind": "function | class | null",
      "distance": 1,
      "labels": ["Symbol"]
    }
  ],
  "count": 8
}
```

**Usage Notes:**
- `distance` = number of edges traversed (1 = direct dependent, 2+ = transitive)
- Traverses CALLS, IMPORTS, CONTAINS, HAS_FILE edges (not learned memory edges)
- Query resolution: tries symbol name → file path → Qdrant semantic fallback

---

### 3.4 run_learned_memory_proposal_workflow

**Purpose:** Propose a durable knowledge item backed by evidence.

**Parameters:**
| Name | Type | Required | Description |
|---|---|---|---|
| `repository_key` | string | yes | Repository identifier |
| `memory_type` | string | yes | "rule", "convention", "caveat", "pattern", "decision" |
| `title` | string | yes | Short label (< 500 chars) |
| `body_text` | string | yes | Full description (2-3 sentences) |
| `evidence_entity_key` | string | yes | UUID of chunk/symbol proving this rule |
| `scope_entity_key` | string | yes | UUID of file/symbol this rule applies to |
| `confidence` | float | no | 0.0-1.0 (default 0.5) |
| `applicability_mode` | string | no | "repository", "file", "symbol" (default "repository") |
| `correlation_id` | string | no | Tracing ID |

**Response `data`:**
```json
{
  "proposal_id": "uuid (use this for commit)",
  "learned_record_id": 42,
  "verification_status": "unverified"
}
```

**Usage Notes:**
- Creates an UNVERIFIED record in PostgreSQL only
- NOT yet in Qdrant or Neo4j (happens on commit/approve)
- `evidence_entity_key` must reference a real entity (chunk or symbol)
- `scope_entity_key` must reference a real entity (file or symbol)
- Use `proposal_id` when calling commit workflow

---

### 3.5 run_learned_memory_commit_workflow

**Purpose:** Approve, reject, or supersede a learned-memory proposal.

**Parameters:**
| Name | Type | Required | Description |
|---|---|---|---|
| `repository_key` | string | yes | Repository identifier |
| `proposal_id` | string | yes | UUID from proposal workflow |
| `approval_status` | string | yes | "approve", "reject", or "supersede" |
| `verification_notes` | string | no | Reason for decision |
| `supersedes_id` | string | no | UUID of old record (required for "supersede") |
| `correlation_id` | string | no | Tracing ID |

**Response `data` (varies by approval_status):**

When `approval_status="approve"`:
```json
{ "status": "verified", "entity_key": "uuid" }
```

When `approval_status="reject"`:
```json
{ "status": "rejected", "entity_key": "uuid" }
```

When `approval_status="supersede"`:
```json
{ "status": "superseded", "new_entity_key": "uuid", "old_entity_key": "uuid" }
```

**Usage Notes:**
- **approve**: embeds to Qdrant, projects to Neo4j, sets verification_status="verified"
- **reject**: deactivates record, sets verification_status="rejected"
- **supersede**: approves new, deactivates old, links via supersedes_learned_record_id

---

### 3.6 run_blueprint_refinement_workflow

**Purpose:** Iteratively refine an artifact using LLM.

**Parameters:**
| Name | Type | Required | Description |
|---|---|---|---|
| `repository_key` | string | yes | Repository identifier |
| `query` | string | yes | Artifact text + refinement instructions |
| `correlation_id` | string | no | Tracing ID |

**Response `data`:**
```json
{
  "refined_text": "The refined artifact content..."
}
```

---

### 3.7 run_repo_ingestion_workflow

**Purpose:** Ingest a repository commit (async background job).

**Parameters:**
| Name | Type | Required | Description |
|---|---|---|---|
| `repository_key` | string | yes | Repository identifier (must exist in catalog.repositories) |
| `commit_sha` | string | yes | Git commit SHA to ingest |
| `branch_name` | string | yes | Branch name |
| `correlation_id` | string | no | Tracing ID |

**Response:** `status: "submitted"`, `data: { "job_id": "uuid" }`

Poll `check_job_status` for completion. Final result includes `files_processed`, `chunks_created`, `summaries_created`, `run_type`.

---

### 3.8 run_integrity_audit_workflow

**Purpose:** Check cross-store consistency.

**Parameters:**
| Name | Type | Required | Description |
|---|---|---|---|
| `repository_key` | string | yes | Repository identifier |
| `correlation_id` | string | no | Tracing ID |

**Response `data`:** Four independent check reports (entity, PG-Qdrant, PG-Neo4j, freshness). Each may contain `"error"` key if that specific check failed.

---

### 3.9 run_repair_rebuild_workflow

**Purpose:** Repair projection drift (async background job).

**Parameters:**
| Name | Type | Required | Description |
|---|---|---|---|
| `repository_key` | string | yes | Repository identifier |
| `repair_scope` | string | no | "full" (default), "qdrant", or "neo4j" |
| `correlation_id` | string | no | Tracing ID |

**Response:** `status: "submitted"`, `data: { "job_id": "uuid" }`

---

### 3.10 check_job_status

**Purpose:** Poll async job status.

**Parameters:**
| Name | Type | Required | Description |
|---|---|---|---|
| `job_id` | string | yes | UUID from async tool submission |
| `correlation_id` | string | no | Tracing ID |

**Response `data`:** Full job manifest including `state_code`, `checkpoint_data` (contains WorkflowResult on completion), timestamps.

---

### 3.11 get_memory_stats

**Purpose:** Operational statistics for a repository.

**Parameters:**
| Name | Type | Required | Description |
|---|---|---|---|
| `repository_key` | string | yes | Repository identifier |
| `correlation_id` | string | no | Tracing ID |

**Response `data`:** Entity counts by type, learned record counts by status, Qdrant point counts per collection, Neo4j node/edge counts, recent ingestion history.

---

### 3.12 run_route_intelligence_workflow

**Purpose:** Routing metrics and history.

**Parameters:**
| Name | Type | Required | Description |
|---|---|---|---|
| `repository_key` | string | yes | Repository identifier |
| `query` | string | yes | Prompt to classify |
| `correlation_id` | string | no | Tracing ID |

**Response `data`:** prompt_class, total_executions, avg_result_count, avg_duration_ms, fanout_rate, graph_expansion_rate, feedback averages.

---

## 4. Agent Persona Specifications

### 4.1 Intake Router

| Field | Value |
|---|---|
| **name** | `intake-router` |
| **internal_code** | `INT-ROUTE` |
| **model** | `opus` |
| **decision_marker** | N/A (returns structured JSON) |
| **color** | `blue` |

**Capabilities:**
```yaml
capabilities:
  file_read: true
  file_search: true
  mcp_tools:
    - mcp__memory-knowledge__run_retrieval_workflow
    - mcp__memory-knowledge__run_route_intelligence_workflow
    - mcp__memory-knowledge__run_context_assembly_workflow
    - mcp__memory-knowledge__run_repo_ingestion_workflow
```

**Skills:** `project-context`, `memory-knowledge-ops`, `route-intelligence`

**Responsibilities:**
1. Classify the incoming prompt into task categories
2. Determine scope: single-agent vs multi-agent
3. Select orchestration workflow pattern (1 of 6)
4. Identify which personas are needed
5. Identify which memory-knowledge tools are needed
6. Create initial execution plan

**Stop Rule:** After classifying task and selecting workflow.

**Escalates If:** Confidence < 0.6, freshness concerns, policy conflict.

**Output Contract:**
```json
{
  "task_class": "codebase_question | change_planning | impact_analysis | memory_proposal | integrity_check",
  "workflow_pattern": "single-agent-direct | planner-worker-reviewer | specialist-swarm | iterative-refinement | memory-proposal | repair-aware",
  "required_personas": ["context-strategist", "codebase-analyst", "verifier"],
  "required_tools": ["run_retrieval_workflow", "run_context_assembly_workflow"],
  "confidence": 0.85,
  "needs_more_context": false,
  "escalation_reason": null
}
```

---

### 4.2 Context Strategist

| Field | Value |
|---|---|
| **name** | `context-strategist` |
| **internal_code** | `CTX-STRAT` |
| **model** | `opus` |
| **decision_marker** | N/A |
| **color** | `cyan` |

**Capabilities:**
```yaml
capabilities:
  file_read: true
  file_search: true
  mcp_tools:
    - mcp__memory-knowledge__run_retrieval_workflow
    - mcp__memory-knowledge__run_context_assembly_workflow
    - mcp__memory-knowledge__run_route_intelligence_workflow
```

**Skills:** `project-context`, `memory-knowledge-ops`, `retrieval-strategy`

**Responsibilities:**
1. Decide which memory layers to query (lexical, semantic, graph)
2. Decide retrieval mode: exact, semantic, graph, or mixed
3. Define the evidence bundle needed
4. Identify context gaps
5. Assemble the context package via `run_context_assembly_workflow`

**Stop Rule:** After sufficient context is assembled.

**Escalates If:** Evidence insufficient, retrieval surface stale, memory trust low.

**Output Contract:**
```json
{
  "retrieval_mode": "exact | semantic | graph | mixed",
  "evidence_bundle": { "...context_assembly response..." },
  "identified_gaps": ["No test coverage evidence found"],
  "confidence": 0.8,
  "recommendation": "Proceed with semantic retrieval focus"
}
```

---

### 4.3 Codebase Analyst

| Field | Value |
|---|---|
| **name** | `codebase-analyst` |
| **internal_code** | `CB-ANALYST` |
| **model** | `opus` |
| **decision_marker** | `CLEAN/ISSUES` |
| **color** | `green` |

**Capabilities:**
```yaml
capabilities:
  file_read: true
  file_search: true
  shell_commands:
    - "git:log"
    - "git:diff"
  mcp_tools:
    - mcp__memory-knowledge__run_retrieval_workflow
    - mcp__memory-knowledge__run_context_assembly_workflow
    - mcp__memory-knowledge__run_impact_analysis_workflow
```

**Skills:** `project-context`, `memory-knowledge-ops`, `code-analysis`, `evidence-grounding`

**Responsibilities:**
1. Interpret code evidence from context bundle
2. Identify relevant files, symbols, and modules
3. Explain implementation patterns
4. Identify likely change points
5. Identify risky assumptions

**Stop Rule:** When grounded findings are sufficient for the task.

**Output Contract:**
```json
{
  "objective": "Understand authentication implementation",
  "findings": [
    {
      "finding_id": "F1",
      "category": "implementation | pattern | risk | change_point",
      "description": "Authentication uses JWT tokens with 24h expiry",
      "evidence": {
        "entity_key": "uuid",
        "file_path": "src/auth.py",
        "line_range": [45, 62]
      },
      "confidence": 0.9
    }
  ],
  "assumptions": ["JWT library handles token validation"],
  "open_questions": ["Is refresh token rotation implemented?"],
  "confidence": 0.85
}
```

---

### 4.4 Architecture Agent

| Field | Value |
|---|---|
| **name** | `architecture-agent` |
| **internal_code** | `ARCH-AGT` |
| **model** | `opus` |
| **decision_marker** | `CLEAN/ISSUES` |
| **color** | `purple` |

**Capabilities:**
```yaml
capabilities:
  file_read: true
  file_search: true
  mcp_tools:
    - mcp__memory-knowledge__run_impact_analysis_workflow
    - mcp__memory-knowledge__run_retrieval_workflow
    - mcp__memory-knowledge__run_context_assembly_workflow
```

**Skills:** `project-context`, `memory-knowledge-ops`, `architecture-reasoning`

**Responsibilities:**
1. Reason at the system and subsystem level
2. Assess boundaries and coupling
3. Propose subsystem-level changes
4. Evaluate tradeoffs
5. Identify dependency and orchestration impact

---

### 4.5 Implementation Planner

| Field | Value |
|---|---|
| **name** | `implementation-planner` |
| **internal_code** | `IMPL-PLAN` |
| **model** | `opus` |
| **decision_marker** | `COMPLETE` |
| **color** | `yellow` |

**Capabilities:**
```yaml
capabilities:
  file_read: true
  file_write: true
  file_search: true
  shell_commands:
    - "git:log"
    - "git:diff"
  mcp_tools:
    - mcp__memory-knowledge__run_impact_analysis_workflow
    - mcp__memory-knowledge__run_retrieval_workflow
    - mcp__memory-knowledge__run_context_assembly_workflow
```

**Skills:** `project-context`, `memory-knowledge-ops`, `planning`, `change-sequencing`

**Responsibilities:**
1. Define change steps with file references
2. Sequence work correctly
3. Identify touched modules/files
4. Identify tests needed
5. Propose migration path
6. Identify risk and rollback concerns

**Produces Artifact:** `implementation-plan.md`

---

### 4.6 Verifier

| Field | Value |
|---|---|
| **name** | `verifier` |
| **internal_code** | `VRFY-AGT` |
| **model** | `sonnet` |
| **decision_marker** | `CLEAN/ISSUES` |
| **color** | `red` |

**Capabilities:**
```yaml
capabilities:
  file_read: true
  file_search: true
  mcp_tools:
    - mcp__memory-knowledge__run_retrieval_workflow
    - mcp__memory-knowledge__run_context_assembly_workflow
    - mcp__memory-knowledge__run_integrity_audit_workflow
```

**Skills:** `project-context`, `memory-knowledge-ops`, `verification-procedures`

**Responsibilities:**
1. Validate claims against evidence
2. Detect unsupported statements
3. Identify likely hallucinations
4. Identify missing evidence
5. Detect internal inconsistency

**Output Contract:**
```json
{
  "reviewed_claims": 12,
  "issues": [
    {
      "finding_id": "V1",
      "claim_under_review": "The function handles all edge cases",
      "issue_type": "unsupported | hallucination | missing_evidence | inconsistency",
      "impact": "high | medium | low",
      "evidence_status": "missing | weak | contradictory",
      "recommendation": "Verify error handling for null input"
    }
  ],
  "overall_status": "CLEAN | ISSUES",
  "confidence": 0.75
}
```

---

### 4.7 Critic

| Field | Value |
|---|---|
| **name** | `critic` |
| **internal_code** | `CRITIC` |
| **model** | `sonnet` |
| **decision_marker** | `CLEAN/ISSUES` |
| **color** | `orange` |

**Capabilities:**
```yaml
capabilities:
  file_read: true
```

**Skills:** `critic-categorization`, `prioritization`

**Responsibilities:**
1. Bucket findings into: FIX NOW, FIX LATER, ACKNOWLEDGE, DISMISS
2. Assess impact of each finding
3. Reduce noise
4. Prevent overcorrection

**Output Contract:**
```json
{
  "findings_processed": 8,
  "buckets": {
    "fix_now": [{ "finding_id": "V1", "relevance_reason": "...", "action": "..." }],
    "fix_later": [...],
    "acknowledge": [...],
    "dismiss": [...]
  },
  "summary": "2 critical issues found, 3 acknowledged, 3 dismissed"
}
```

---

### 4.8 Editor / Refiner

| Field | Value |
|---|---|
| **name** | `editor` |
| **internal_code** | `EDIT-AGT` |
| **model** | `opus` |
| **decision_marker** | `COMPLETE` |
| **color** | `teal` |

**Capabilities:**
```yaml
capabilities:
  file_read: true
  file_write: true
  file_search: true
  mcp_tools:
    - mcp__memory-knowledge__run_blueprint_refinement_workflow
```

**Skills:** `project-context`, `artifact-refinement`

**Responsibilities:**
1. Apply FIX NOW findings to artifacts
2. Apply FIX LATER findings
3. Preserve coherence of the original artifact
4. Track what was changed and what remains uncertain

---

### 4.9 Learned Memory Curator

| Field | Value |
|---|---|
| **name** | `learned-memory-curator` |
| **internal_code** | `LM-CURATOR` |
| **model** | `opus` |
| **decision_marker** | `COMPLETE` |
| **color** | `gold` |

**Capabilities:**
```yaml
capabilities:
  file_read: true
  file_search: true
  mcp_tools:
    - mcp__memory-knowledge__run_learned_memory_proposal_workflow
    - mcp__memory-knowledge__run_retrieval_workflow
    - mcp__memory-knowledge__run_context_assembly_workflow
```

**Skills:** `project-context`, `memory-knowledge-ops`, `memory-governance`

**Responsibilities:**
1. Review findings for durable patterns
2. Evaluate: Is it durable? Grounded? New? Appropriately scoped?
3. Propose via `run_learned_memory_proposal_workflow` if worthy
4. Reject with reason if not worthy

**Rejection Reasons:**
- `reject_ephemeral` — too temporary
- `reject_ungrounded` — insufficient evidence
- `reject_duplicate` — similar rule exists
- `reject_too_broad` — too vague
- `reject_not_reusable` — too context-specific
- `defer_for_evidence` — interesting but needs proof
- `supersede_existing` — replaces older rule

---

### 4.10 Orchestrator

| Field | Value |
|---|---|
| **name** | `orchestrator` |
| **internal_code** | `ORCH-AGT` |
| **model** | `opus` |
| **decision_marker** | N/A |
| **color** | `white` |

**Capabilities:**
```yaml
capabilities:
  file_read: true
  file_write: true
  file_search: true
  shell_commands:
    - "*"
  mcp_tools:
    - mcp__memory-knowledge__run_retrieval_workflow
    - mcp__memory-knowledge__run_context_assembly_workflow
    - mcp__memory-knowledge__run_impact_analysis_workflow
    - mcp__memory-knowledge__run_learned_memory_proposal_workflow
    - mcp__memory-knowledge__run_learned_memory_commit_workflow
    - mcp__memory-knowledge__run_blueprint_refinement_workflow
    - mcp__memory-knowledge__run_repo_ingestion_workflow
    - mcp__memory-knowledge__run_integrity_audit_workflow
    - mcp__memory-knowledge__run_repair_rebuild_workflow
    - mcp__memory-knowledge__check_job_status
    - mcp__memory-knowledge__get_memory_stats
    - mcp__memory-knowledge__run_route_intelligence_workflow
```

**Skills:** `project-context`, `memory-knowledge-ops`, `orchestration-control`

**Responsibilities:**
1. Coordinate multi-agent workflows
2. Choose workflow patterns
3. Trigger review loops
4. Manage learned-memory approval gates
5. Escalate to repair workflows when trust is low
6. Apply stopping policies

---

### 4.11 Final Response

| Field | Value |
|---|---|
| **name** | `final-response` |
| **internal_code** | `FINAL-RSP` |
| **model** | `sonnet` |
| **decision_marker** | N/A |
| **color** | `silver` |

**Capabilities:**
```yaml
capabilities:
  file_read: true
  mcp_tools:
    - mcp__memory-knowledge__run_retrieval_workflow
```

**Skills:** `synthesis`, `presentation`

**Responsibilities:**
1. Unify working outputs from all prior agents
2. Preserve correctness and nuance
3. Distinguish grounded facts from inferences
4. Present conclusions clearly
5. Recommend next steps

**Output Contract:**
```json
{
  "answer": "Main response text...",
  "grounded_facts": [
    { "fact": "Auth uses JWT", "evidence_entity_key": "uuid", "confidence": "high" }
  ],
  "inferences": ["Token rotation likely not implemented"],
  "uncertainties": ["Redis session store configuration unclear"],
  "recommended_next_steps": ["Review auth middleware", "Add token rotation"]
}
```

---

## 5. Orchestration Workflow Definitions

### 5.1 answer-codebase-question

**Pattern:** Planner → Worker → Reviewer

```yaml
name: answer-codebase-question
description: Answer a question about the codebase using memory-knowledge evidence
version: "1.0.0"

phases:
  - id: route
    name: Intake Routing
    agent: intake-router
    depends_on: []
    artifacts: []

  - id: context
    name: Context Assembly
    agent: context-strategist
    depends_on: [route]
    artifacts: [context-bundle.json]

  - id: analyze
    name: Code Analysis
    agent: codebase-analyst
    depends_on: [context]
    artifacts: [analysis-findings.md]
    on_issues: analyze

  - id: verify
    name: Verification
    agent: verifier
    depends_on: [analyze]
    artifacts: [verification-report.md]
    on_issues: analyze

  - id: respond
    name: Final Response
    agent: final-response
    depends_on: [verify]
    artifacts: [response.md]

settings:
  max_fix_iterations: 5
  timeout_minutes: 30
```

### 5.2 plan-change

**Pattern:** Planner → Worker → Reviewer

```yaml
name: plan-change
description: Create an implementation plan for a proposed change
version: "1.0.0"

phases:
  - id: route
    name: Intake Routing
    agent: intake-router
    depends_on: []

  - id: context
    name: Context Assembly
    agent: context-strategist
    depends_on: [route]
    artifacts: [context-bundle.json]

  - id: plan
    name: Implementation Planning
    agent: implementation-planner
    depends_on: [context]
    artifacts: [implementation-plan.md]

  - id: verify
    name: Plan Verification
    agent: verifier
    depends_on: [plan]
    artifacts: [verification-report.md]
    on_issues: plan

  - id: respond
    name: Final Response
    agent: final-response
    depends_on: [verify]
    artifacts: [response.md]

settings:
  max_fix_iterations: 5
  timeout_minutes: 30
```

### 5.3 analyze-impact

**Pattern:** Planner → Worker → Reviewer

```yaml
name: analyze-impact
description: Analyze the impact of a proposed change across the codebase
version: "1.0.0"

phases:
  - id: route
    name: Intake Routing
    agent: intake-router
    depends_on: []

  - id: context
    name: Context Assembly
    agent: context-strategist
    depends_on: [route]
    artifacts: [context-bundle.json]

  - id: impact
    name: Impact Analysis
    agent: architecture-agent
    depends_on: [context]
    artifacts: [impact-report.md]

  - id: verify
    name: Verification
    agent: verifier
    depends_on: [impact]
    artifacts: [verification-report.md]
    on_issues: impact

  - id: respond
    name: Final Response
    agent: final-response
    depends_on: [verify]
    artifacts: [response.md]

settings:
  max_fix_iterations: 3
  timeout_minutes: 20
```

### 5.4 refine-artifact

**Pattern:** Iterative Refinement Loop

```yaml
name: refine-artifact
description: Iteratively refine an artifact until the critic clears all findings
version: "1.0.0"

phases:
  - id: draft
    name: Initial Draft
    agent: implementation-planner
    depends_on: []
    artifacts: [artifact-draft.md]

  - id: verify
    name: Verification
    agent: verifier
    depends_on: [draft]
    artifacts: [verification-report.md]

  - id: critique
    name: Critic Review
    agent: critic
    depends_on: [verify]
    artifacts: [critic-report.md]
    on_issues: edit

  - id: edit
    name: Apply Edits
    agent: editor
    depends_on: [critique]
    artifacts: [artifact-draft.md]
    on_issues: verify

  - id: respond
    name: Final Response
    agent: final-response
    depends_on: [critique, edit]

settings:
  max_fix_iterations: 8
  timeout_minutes: 45
```

### 5.5 propose-learned-memory

**Pattern:** Memory Proposal Flow

```yaml
name: propose-learned-memory
description: Evaluate findings for durable knowledge and propose learned memory
version: "1.0.0"

phases:
  - id: curate
    name: Memory Curation
    agent: learned-memory-curator
    depends_on: []
    artifacts: [memory-proposal.json]

  - id: verify
    name: Verify Grounding
    agent: verifier
    depends_on: [curate]
    artifacts: [verification-report.md]
    on_issues: curate

  - id: critique
    name: Check Relevance
    agent: critic
    depends_on: [verify]
    artifacts: [critic-report.md]

  - id: approve
    name: Approval Gate
    description: >
      The ORCHESTRATOR (not the Curator) decides whether to approve.
      If approved, the Orchestrator calls run_learned_memory_commit_workflow
      with approval_status="approve". The Curator can only PROPOSE (unverified).
    agent: orchestrator
    depends_on: [critique]
    artifacts: [approval-decision.json]

settings:
  max_fix_iterations: 3
  timeout_minutes: 15
```

### 5.6 repair-and-resume

**Pattern:** Repair-Aware

```yaml
name: repair-and-resume
description: Detect inconsistency, repair memory, and resume original workflow
version: "1.0.0"

phases:
  - id: audit
    name: Integrity Audit
    agent: orchestrator
    depends_on: []
    artifacts: [audit-report.json]

  - id: repair
    name: Repair Drift
    agent: orchestrator
    depends_on: [audit]
    artifacts: [repair-report.json]

  - id: reassemble
    name: Reassemble Context
    agent: context-strategist
    depends_on: [repair]
    artifacts: [context-bundle.json]

settings:
  timeout_minutes: 30
```

---

## 6. Skills

### 6.1 memory-knowledge-ops

**Location:** `src/skills/memory-knowledge-ops/SKILL.md`

This skill teaches agents how to use the memory-knowledge MCP server tools. It should document:

1. **When to use each tool** — decision matrix
2. **Tool parameters** — what each parameter means
3. **Response interpretation** — how to read evidence bundles, impact reports, etc.
4. **Error handling** — what to do when tools return errors
5. **Async job patterns** — how to submit and poll long-running jobs
6. **Learned memory governance** — the proposal → verify → approve flow
7. **Context bundle structure** — how to use categorized evidence

### 6.2 retrieval-strategy

Teaches the Context Strategist how to choose between exact, semantic, graph, and mixed retrieval modes based on query characteristics.

### 6.3 evidence-grounding

Teaches workers how to ground claims in evidence from the memory-knowledge context bundles. Every claim must reference an `entity_key` and `file_path`.

### 6.4 memory-governance

Teaches the Learned Memory Curator the governance rules: durability, grounding, scope, confidence thresholds, rejection reasons.

### 6.5 orchestration-control

Teaches the Orchestrator how to choose workflow patterns, manage fix loops, trigger repair flows, and apply stopping policies.

---

## 7. Validators

### 7.1 output-contract-validator

Validates that agent outputs match their defined output contract (JSON schema validation).

### 7.2 evidence-grounding-validator

Validates that all claims in worker outputs reference real entity_keys from the context bundle.

### 7.3 memory-proposal-validator

Validates that memory proposals include all required fields and evidence references.

---

## 8. Quality Gates

| Gate | Condition | Enforcement |
|---|---|---|
| Evidence Sufficiency | Context bundle has ≥ 3 evidence items | Context Strategist escalates |
| Trustworthiness | Integrity audit passes (no missing points/nodes) | Orchestrator triggers repair |
| Role Discipline | Agent only calls tools in its capabilities list | Tool translator enforces |
| Review Threshold | High-impact findings require Verifier review | Orchestrator gates |
| Memory Threshold | Learned memory requires evidence + relevance + approval | Proposal flow enforces |
| Stop Condition | Iterative loops stop when Critic returns 0 FIX NOW | Workflow engine enforces |

---

## 9. Persona-to-Tool Permissions Matrix

| Persona | retrieval | context | impact | proposal | commit | refinement | ingestion | audit | repair | job_status | stats | route_intel |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Intake Router | ✓ | ✓ | | | | | ✓ | | | | | ✓ |
| Context Strategist | ✓ | ✓ | | | | | | | | | | ✓ |
| Codebase Analyst | ✓ | ✓ | ✓ | | | | | | | | | |
| Architecture Agent | ✓ | ✓ | ✓ | | | | | | | | | |
| Impl Planner | ✓ | ✓ | ✓ | | | | | | | | | |
| Verifier | ✓ | ✓ | | | | | | ✓ | | | | |
| Critic | | | | | | | | | | | | |
| Editor | | | | | | ✓ | | | | | | |
| LM Curator | ✓ | ✓ | | ✓ | | | | | | | | |
| Orchestrator | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Final Response | ✓ | | | | | | | | | | | |

---

## 10. Implementation Checklist

### In `mcp-agents-workflow` project:

- [ ] Add `memory-knowledge` to `.mcp.json`
- [ ] Create 11 persona `.md` files in `src/agents/`
- [ ] Create 6 workflow `.yaml` files in `src/workflow_orch/workflows/`
- [ ] Create `memory-knowledge-ops` skill in `src/skills/`
- [ ] Create `retrieval-strategy` skill
- [ ] Create `evidence-grounding` skill
- [ ] Create `memory-governance` skill
- [ ] Create `orchestration-control` skill
- [ ] Create output-contract validator
- [ ] Create evidence-grounding validator
- [ ] Create memory-proposal validator
- [ ] Add `memory-knowledge` LLM provider entry (if needed for tool discovery)
- [ ] Integration test: single-agent direct workflow (answer question)
- [ ] Integration test: planner-worker-reviewer workflow
- [ ] Integration test: iterative refinement loop
- [ ] Integration test: learned memory proposal flow
- [ ] Integration test: repair-aware workflow
- [ ] End-to-end test: ingest repo → ask question → get grounded answer

### In `memory-knowledge` project:

- [ ] Ensure MCP server starts cleanly via command line (`python -m memory_knowledge.server` or `uvicorn`)
- [ ] Verify all 12 tools respond correctly
- [ ] Ensure `.env.example` documents all required environment variables
- [ ] Test with at least one ingested Python repository
