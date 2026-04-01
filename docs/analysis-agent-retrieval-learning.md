# Analysis: Agent Retrieval Learning Loop

## Problem Statement

AI agents connecting to the memory-knowledge system issue retrieval queries but have no mechanism to report whether the results were useful. The system collects auto-feedback heuristics (result count, scores) but lacks the critical signal: **did the agent actually use the retrieved context to complete its task?**

Without this signal:
- We can't distinguish a query that returned 10 chunks the agent ignored from one that returned 3 chunks that solved the problem
- Prompt patterns that produce good results can't be identified and reinforced
- Prompt patterns that waste tokens on irrelevant results can't be corrected
- The learned_memory system (0 records) stays empty — no codified patterns for agents to learn from

## Current State

### Data Collection (Active)

| Signal | Source | What It Captures | What It Misses |
|---|---|---|---|
| route_executions | Every retrieval | prompt_text, prompt_class, result_count, stores, duration | Whether results were useful to the agent |
| auto_feedback | Every retrieval | Heuristic usefulness/precision scores | Actual usefulness — only structural signals |
| route_intelligence | On demand | Policy recommendations per prompt_class | Per-query quality, prompt pattern analysis |

### Tools Available But Unused (0 Records)

| Tool | Purpose | Status |
|---|---|---|
| create_working_session | Track an agent's investigation lifecycle | Never called |
| record_working_observation | Log what the agent inspected, hypothesized, found | Never called |
| get_working_session_context | Review all observations in a session | Never called |
| end_working_session | Close session, project to Neo4j graph | Never called |
| submit_route_feedback | Manual quality signal from the agent | Never called |
| run_context_assembly_workflow | Retrieval + learned rules + call chains | Never called |
| run_learned_memory_proposal_workflow | Propose patterns from observations | Never called |
| run_learned_memory_commit_workflow | Approve/reject proposed patterns | Never called |
| run_route_intelligence_workflow | Routing analytics and policy recommendations | Called but not part of agent loop |

### The Gap

```
Current:    Agent → query → retrieval → results → agent uses results → [nothing reported back]

Needed:     Agent → query → retrieval → results → agent uses results → feedback + observations
                                                                            ↓
                                                                    learned_memory proposals
                                                                            ↓
                                                                    approved patterns
                                                                            ↓
                                                          surfaced in future retrievals via context_assembly
```

## Available Infrastructure

### Working Sessions + Observations

The working session system tracks an agent's investigation:

```
create_working_session(repository_key) → session_key (UUID)

record_working_observation(session_key, entity_key, observation_type, observation_text)
  observation_types: inspected, hypothesized_about, proposed_change_to,
                     issue_found, plan_note, rejected_path, query_rewrite

end_working_session(session_key) → projects to Neo4j graph
```

This captures WHAT the agent looked at and WHAT it concluded — but currently no agent uses it.

### Learned Memory Pipeline

Two-phase pipeline: propose → commit

**Proposal** requires:
- `repository_key` — which repository the pattern applies to
- `memory_type` — category of pattern (validated against VALID_MEMORY_TYPES: "prompt_pattern", "retrieval_strategy", "common_issue", "entity_relationship", "naming_convention", "architectural_pattern")
- `title` — human-readable summary
- `body_text` — full pattern description (gets embedded for semantic search)
- `evidence_entity_key` — UUID of entity that proves the pattern
- `scope_entity_key` — UUID of entity the pattern applies to
- `confidence` — 0.0-1.0
- `applicability_mode` — "repository" (global) or entity-scoped

**Commit** requires:
- `repository_key` — which repository contains the proposal
- `proposal_id` — from proposal step
- `approval_status` — "approve", "reject", or "supersede"
- `verification_notes` — optional explanation of the decision
- `supersedes_id` — optional, links to a previous proposal being replaced

Once approved, the pattern is:
1. Embedded in Qdrant (semantic matching)
2. Projected to Neo4j (APPLIES_TO edges)
3. Surfaced during future retrievals via `context_assembly._fetch_applicable_learned_rules()`

### Route Feedback (Manual)

```
submit_route_feedback(route_execution_id, usefulness_score, precision_score, expansion_needed, notes)
```

The `route_execution_id` is returned in every retrieval response. Agents can submit quality signals that override/complement auto-feedback heuristics.

## Analysis: What Agents Need To Do

### Phase 1: Report Retrieval Quality (Minimal — No Code Changes)

The simplest improvement: agents call `submit_route_feedback` after using retrieval results.

**When to submit feedback:**

| Scenario | usefulness | precision | expansion_needed | notes |
|---|---|---|---|---|
| Retrieved context answered the question directly | 0.9 | 0.8-1.0 | false | "answered user question from first retrieval" |
| Had to issue 2+ follow-up queries to get enough context | 0.4 | 0.3-0.5 | true | "needed 3 queries, first was too broad" |
| Results were irrelevant, had to rephrase completely | 0.1 | 0.0-0.2 | false | "rephrased from X to Y, second query worked" |
| Retrieved code but also needed database schema context | 0.6 | 0.7 | true | "code found but missing DB schema" |
| Zero results, query was too specific | 0.0 | 0.0 | true | "no results for exact function name, was renamed" |

**Impact:** Manual feedback from agents carries stronger signal than auto-feedback heuristics. With 3+ manual entries per prompt_class, route_intelligence recommendations become grounded in actual usage.

**Limitation:** Requires every connecting agent to implement feedback logic. No pattern learning yet.

### Phase 2: Track Investigation Sessions (Observation Collection)

Agents wrap multi-step investigations in working sessions:

```
1. create_working_session("fcsapi") → session_key
2. run_retrieval_workflow("fcsapi", "how does fleet KPI work") → results
3. record_working_observation(session_key, entity_key_of_result, "inspected", "found fleet-kpi endpoint handler")
4. run_retrieval_workflow("fcsapi", "GetFleetKPIData function") → more results
5. record_working_observation(session_key, entity_key, "inspected", "found SQL query in data layer")
6. record_working_observation(session_key, entity_key, "issue_found", "function doesn't handle null company filter")
7. end_working_session(session_key)
```

**What this produces:**
- A trail of which entities the agent actually inspected (vs just retrieved)
- Hypothesis and issue annotations on specific entities
- Neo4j graph edges connecting sessions to entities
- Data that a proposal workflow can mine for patterns

**Impact:** Builds the evidence base needed for learned memory proposals. Also creates a reusable audit trail — when another agent asks a similar question, the session graph shows what was previously investigated.

### Phase 3: Propose Learned Patterns (Pattern Codification)

After enough observations accumulate, agents (or an automated workflow) analyze patterns and propose learned memory:

**Example patterns that could be proposed:**

| memory_type | title | body_text | confidence |
|---|---|---|---|
| prompt_pattern | "Fleet KPI queries need both endpoint and data layer" | "When asking about KPI functionality in FCSAPI, always query for both the HTTP handler and the underlying SQL/data access function. The handler delegates to a data layer function with different naming." | 0.7 |
| retrieval_strategy | "Database schema queries should use exact_lookup" | "Queries about database table structure, column names, or schema produce better results when phrased as exact identifiers (table names, column names) rather than conceptual descriptions." | 0.8 |
| common_issue | "WordPress forms have multiple email paths" | "The Millennium WordPress project has 7 distinct form-to-email paths. When investigating email handling, always query for both the Elementor widget handlers (rhea_*) and the easy-real-estate handlers (ere_*) separately." | 0.9 |

**How proposals would be generated:**

Option A — Agent self-proposes: After completing a task that required multiple retrievals, the agent reflects on what worked and proposes a pattern. This is the simplest path but requires agent-side logic.

Option B — Automated mining: A scheduled workflow analyzes route_executions + working_observations to find:
- Queries that were rephrased (same session, same entities, different prompt_text)
- Sessions where the agent inspected many entities before finding what it needed
- Prompt patterns that consistently produce high usefulness scores

Option C — Human review: A human reviews session transcripts and proposes patterns. The agent just collects observations; humans codify.

### Phase 4: Close the Loop (Patterns Surfaced in Retrieval)

Once patterns are approved via `run_learned_memory_commit_workflow`, they automatically appear in future retrievals via `context_assembly._fetch_applicable_learned_rules()`.

**Status (implemented):** `run_retrieval_workflow` now returns `applicable_learned_rules` in its response (added in commit 7530689). Agents no longer need a separate `run_context_assembly_workflow` call.

The context bundle from `run_context_assembly_workflow` includes:

```json
{
  "exact_matches": [...],
  "semantic_matches": [...],
  "graph_expansions": [...],
  "applicable_learned_rules": [
    {
      "entity_key": "uuid-of-rule",
      "title": "Fleet KPI queries need both endpoint and data layer",
      "memory_type": "prompt_pattern",
      "confidence": 0.7,
      "applicability_mode": "repository",
      "body_text": "When asking about KPI functionality...",
      "source": "postgres"
    }
  ]
}
```

**Note:** Rules sourced via Neo4j graph traversal only include `entity_key`, `title`, `memory_type`, `source` — they lack `body_text` and `confidence`. PG-sourced rules include all fields.

**Trade-off:** `run_context_assembly_workflow` returns learned rules but does NOT return `route_execution_id` (needed for `submit_route_feedback`). Agents needing both should call `run_retrieval_workflow` first (get route_execution_id, submit feedback), then `run_context_assembly_workflow` (get learned rules). Or, retrieval can be extended to surface rules directly (Gap 4).

## Gap Analysis: What's Missing

### Gap 1: No Agent Protocol Documentation

There is no specification telling connecting agents WHEN and HOW to use the session/feedback/proposal tools. Each agent team would need to independently figure out the API surface and implement their own integration logic.

**What's needed:** A concrete protocol spec defining:
- When to create/end sessions
- What observation_types to use and when
- When to submit route feedback (after every retrieval? only on failure?)
- How to structure feedback notes for maximum signal
- When to propose learned patterns vs leave for automated mining

### Gap 2: No Automated Pattern Mining

The proposal workflow requires explicit calls with specific entity_keys, memory_type, title, body_text, confidence. There is no automated analysis that mines route_executions or working_observations to discover patterns.

**What's needed:** A mining workflow that periodically:
- Finds sessions where the same entities were retrieved across multiple queries (query refinement pattern)
- Identifies prompt_text patterns that consistently score high/low usefulness
- Detects entity clusters that are always retrieved together (co-retrieval patterns)
- Generates proposal candidates with evidence

### Gap 3: No Prompt Rewriting Feedback

The system captures WHETHER a query worked (usefulness score) but not HOW the agent rephrased a failed query. If an agent queries "email form handler" and gets poor results, then rephrases to "rhea_send_contact_message wp_mail" and gets good results, that rewrite pattern is gold — but nothing captures it.

**What's needed:** Either:
- A `query_rewrite` observation_type that agents use to log the before/after
- Or automated detection: same session + same entity intersection between two queries = likely rewrite

### Gap 4: No Context Assembly Integration for Agents — RESOLVED

~~`run_retrieval_workflow` did not surface learned rules.~~

**Resolved:** `run_retrieval_workflow` now includes `applicable_learned_rules` in its response (commit 7530689). Agents get learned rules alongside evidence in a single call.

### Gap 5: No Defined Vocabulary for memory_type — RESOLVED

~~`memory_type` was freeform VARCHAR(50) with no validation.~~

**Resolved:** `VALID_MEMORY_TYPES` defined in `learned_memory.py` with validation in `run_proposal()` (commit 7530689). Valid types: `prompt_pattern`, `retrieval_strategy`, `common_issue`, `entity_relationship`, `naming_convention`, `architectural_pattern`.

### Gap 6: No Feedback on Learned Rule Quality

Once a learned rule is approved and surfaced, there's no mechanism to measure whether it actually helped. Did the agent follow the rule's advice? Did following it produce better results?

**What's needed:** A feedback loop on learned rules themselves — agents report whether a surfaced rule was helpful, which adjusts the rule's confidence score over time.

## Prioritized Recommendations

| Priority | Action | Effort | Impact |
|---|---|---|---|
| 1 | Write agent protocol spec (Phase 1 + 2) | Low — documentation only | Unblocks all agent integration |
| 2 | Add `query_rewrite` observation type | Low — 2 lines of code | Captures highest-value signal |
| 3 | Define memory_type vocabulary | Low — validation + documentation | Prevents inconsistent learned records |
| 4 | Surface learned rules in run_retrieval_workflow | Low-Medium — call existing function from retrieval | Closes the loop without requiring two API calls |
| 5 | Build automated pattern mining workflow | High — new workflow + heuristics | Generates proposals without human effort |
| 6 | Add learned rule effectiveness feedback | Medium — new feedback path | Makes learned rules self-correcting |

## Data Flow: Complete Learning Loop

```
AGENT TASK
  │
  ├─ create_working_session(repo)
  │
  ├─ RETRIEVAL CYCLE (may repeat)
  │   ├─ run_retrieval_workflow(query)
  │   │   ├─ [auto] route_execution logged
  │   │   ├─ [auto] auto_feedback generated
  │   │   └─ returns evidence + route_execution_id + applicable_learned_rules
  │   │
  │   ├─ Agent inspects results
  │   │   └─ record_working_observation(session, entity, "inspected", notes)
  │   │
  │   ├─ If results insufficient → rephrase query
  │   │   └─ record_working_observation(session, entity, "query_rewrite", "from X to Y")
  │   │
  │   └─ submit_route_feedback(route_execution_id, usefulness, precision)
  │
  ├─ Agent completes task
  │   └─ record_working_observation(session, entity, "issue_found" | "proposed_change_to", notes)
  │
  ├─ end_working_session(session)
  │
  └─ OPTIONAL: Agent proposes learned pattern
      └─ run_learned_memory_proposal_workflow(memory_type, title, body_text, evidence, scope, confidence)

BACKGROUND (periodic or triggered)
  │
  ├─ Pattern mining analyzes sessions + feedback
  │   └─ Auto-generates learned memory proposals
  │
  ├─ Human or automated approval
  │   └─ run_learned_memory_commit_workflow(proposal_id, "approve")
  │
  └─ Approved patterns embedded + projected
      └─ Surfaced in future retrievals via applicable_learned_rules
```
