## Scope

Implement narrow readiness diagnostics hardening for dependency failures, with coverage for blank exception messages.

## Implementation Steps

1. Update `src/memory_knowledge/db/health.py`.
2. Add a helper for stable exception formatting in readiness responses.
3. Use the helper for PostgreSQL, Qdrant, and Neo4j readiness failures.
4. Add a focused async unit test covering a blank Neo4j exception string.

## Affected Files

- `src/memory_knowledge/db/health.py`
- `tests/test_health.py`

## Validation

Run the focused health test module locally:

- `pytest tests/test_health.py -q`

## Dependencies And Sequencing

- No schema, rollout, or remote changes required.
- If the test reveals broader assumptions about readiness formatting, keep fixes limited to diagnostics only.
