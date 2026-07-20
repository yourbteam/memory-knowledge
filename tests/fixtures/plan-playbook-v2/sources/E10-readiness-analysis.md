## Objective

Harden readiness dependency diagnostics so transient dependency failures do not surface as blank `error: ` strings.

## Task Type And Size

- Type: diagnostics hardening
- Size: light

## Current-State Facts

- The live `/ready` endpoint previously returned `{"status":"not_ready","postgres":"ok","qdrant":"ok","neo4j":"error: "}` immediately after restart.
- The current readiness implementation in `src/memory_knowledge/db/health.py` formats dependency failures with `f"error: {exc}"`.
- If an exception's string representation is empty, the endpoint returns an empty diagnostic payload.
- Live logs confirmed Neo4j startup connectivity was healthy, so the observed issue was not persistent credential or network failure.

## Source Artifacts Inspected

- `src/memory_knowledge/db/health.py`
- `src/memory_knowledge/db/neo4j.py`
- Azure live container logs downloaded on 2026-04-14

## Constraints And Risks

- Keep the change narrow and low-risk.
- Do not change readiness semantics beyond better diagnostics.
- Preserve existing `status` transitions and dependency checks.

## Recommended Approach

Add a small helper in `src/memory_knowledge/db/health.py` that formats dependency exceptions using:

- exception class name
- `str(exc)` when present
- `repr(exc)` fallback when the message is blank

Also add a focused unit test that reproduces a blank exception string and verifies the readiness payload remains informative.
