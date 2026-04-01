# Agent Retrieval Protocol

How AI agents should interact with the memory-knowledge system to retrieve code intelligence, report quality, and build learned patterns over time.

## Quick Start (Minimal Integration)

After every retrieval, submit feedback using the `route_execution_id` from the response:

```
1. run_retrieval_workflow(repository_key, query) → response with route_execution_id
2. submit_route_feedback(route_execution_id, usefulness_score=0.8, precision_score=0.7)
```

This alone enables route intelligence to learn which prompt patterns and routing strategies work.

## Full Lifecycle

```
create_working_session(repository_key)
  │
  ├─ RETRIEVAL CYCLE (repeat as needed)
  │   ├─ run_retrieval_workflow(repository_key, query)
  │   │   → returns evidence, route_execution_id, applicable_learned_rules
  │   │
  │   ├─ Inspect results
  │   │   └─ record_working_observation(session_key, entity_key, "inspected", "what you found")
  │   │
  │   ├─ If results poor → rephrase
  │   │   └─ record_working_observation(session_key, entity_key, "query_rewrite",
  │   │        "from: original query | to: rephrased query")
  │   │
  │   └─ submit_route_feedback(route_execution_id, usefulness_score, precision_score,
  │        expansion_needed, notes)
  │
  ├─ Record findings
  │   └─ record_working_observation(session_key, entity_key, "issue_found" | "proposed_change_to", ...)
  │
  ├─ end_working_session(session_key)
  │
  └─ OPTIONAL: Propose a learned pattern
      └─ run_learned_memory_proposal_workflow(repository_key, memory_type, title,
           body_text, evidence_entity_key, scope_entity_key, confidence)
```

## Observation Types

Use with `record_working_observation(session_key, entity_key, observation_type, observation_text)`:

| Type | When to Use | Example |
|---|---|---|
| `inspected` | Read/examined an entity's code | "Reviewed the fleet KPI endpoint handler" |
| `hypothesized_about` | Formed a theory about behavior | "This function likely delegates to the data layer" |
| `proposed_change_to` | Identified a needed modification | "Null guard missing for company filter param" |
| `issue_found` | Discovered a bug or problem | "SQL injection possible in dynamic WHERE clause" |
| `plan_note` | Documented a plan step | "Need to also check the middleware chain" |
| `rejected_path` | Explored but discarded an approach | "Tried searching by class name, but it's a standalone function" |
| `query_rewrite` | Rephrased a query for better results | "from: email form handler \| to: rhea_send_contact_message wp_mail" |

## Memory Types

Use with `run_learned_memory_proposal_workflow(... memory_type=...)`:

| Type | Definition | Example |
|---|---|---|
| `prompt_pattern` | A query phrasing that consistently produces good retrieval results | "For KPI queries, include both endpoint name and data layer function name" |
| `retrieval_strategy` | Which search approach works best for a class of questions | "Database schema queries should use exact table/column names, not descriptions" |
| `common_issue` | A frequently encountered problem in the codebase | "WordPress forms have 7 distinct email paths — query Elementor and easy-real-estate handlers separately" |
| `entity_relationship` | A non-obvious connection between code entities | "Fleet KPI handlers in controllers/ always delegate to matching functions in data/" |
| `naming_convention` | A naming pattern that affects search effectiveness | "C# services use PascalCase but SQL procedures use snake_case — search both forms" |
| `architectural_pattern` | A high-level structural pattern | "All API endpoints follow controller → service → repository layering" |

## Feedback Scoring Guide

After using retrieval results, submit feedback with these scores:

| Scenario | usefulness | precision | expansion_needed | notes |
|---|---|---|---|---|
| Results answered the question directly | 0.9 | 0.8-1.0 | false | "answered from first retrieval" |
| Needed 2+ follow-up queries | 0.4 | 0.3-0.5 | true | "needed 3 queries, first too broad" |
| Results irrelevant, had to rephrase | 0.1 | 0.0-0.2 | false | "rephrased from X to Y" |
| Found code but needed more context | 0.6 | 0.7 | true | "code found but missing DB schema" |
| Zero results | 0.0 | 0.0 | true | "no results, function may be renamed" |

## Retrieval Response Schema

`run_retrieval_workflow` returns:

```json
{
  "evidence": [
    {
      "entity_key": "uuid",
      "title": "file or symbol name",
      "content_text": "code content",
      "file_path": "path/to/file.py",
      "retrieval_score": 1.45,
      "source_store": "postgres"
    }
  ],
  "count": 12,
  "route_execution_id": 285,
  "applicable_learned_rules": [
    {
      "entity_key": "uuid",
      "title": "Rule title",
      "memory_type": "prompt_pattern",
      "confidence": 0.8,
      "applicability_mode": "repository",
      "body_text": "Full rule description",
      "source": "postgres"
    }
  ]
}
```

**Note:** `route_execution_id` is an integer — pass it directly to `submit_route_feedback`. Rules sourced from Neo4j graph traversal only include `entity_key`, `title`, `memory_type`, `source` (no `body_text` or `confidence`).

## Example: Multi-Step Investigation

```
# Start session
create_working_session(repository_key="fcsapi")
→ session_key: "a1b2c3d4-..."

# First retrieval attempt
run_retrieval_workflow(repository_key="fcsapi", query="fleet KPI calculation")
→ route_execution_id: 290, 3 results about KPI endpoints

# Record what we inspected
record_working_observation(session_key="a1b2c3d4-...",
    entity_key="uuid-of-kpi-handler", observation_type="inspected",
    observation_text="Found fleet KPI endpoint but need the data layer function")

# Submit feedback — results were partial
submit_route_feedback(route_execution_id=290,
    usefulness_score=0.5, precision_score=0.6, expansion_needed=true,
    notes="found endpoint but not data access layer")

# Rephrase and try again
record_working_observation(session_key="a1b2c3d4-...",
    entity_key="uuid-of-kpi-handler", observation_type="query_rewrite",
    observation_text="from: fleet KPI calculation | to: GetFleetKPIData SQL query")

run_retrieval_workflow(repository_key="fcsapi", query="GetFleetKPIData SQL query")
→ route_execution_id: 291, 5 results including the data layer

# This retrieval worked well
submit_route_feedback(route_execution_id=291,
    usefulness_score=0.9, precision_score=0.8, expansion_needed=false,
    notes="found both endpoint and data layer with specific function name")

# Record finding
record_working_observation(session_key="a1b2c3d4-...",
    entity_key="uuid-of-data-function", observation_type="issue_found",
    observation_text="GetFleetKPIData doesn't handle null company filter")

# End session
end_working_session(session_key="a1b2c3d4-...")

# Propose a learned pattern from this experience
run_learned_memory_proposal_workflow(
    repository_key="fcsapi",
    memory_type="prompt_pattern",
    title="Fleet KPI queries need specific function names",
    body_text="When investigating KPI functionality, use specific function names like GetFleetKPIData rather than general terms like 'fleet KPI calculation'. The endpoint handlers in controllers/ delegate to data-layer functions with different naming.",
    evidence_entity_key="uuid-of-data-function",
    scope_entity_key="uuid-of-kpi-handler",
    confidence=0.7
)
```
