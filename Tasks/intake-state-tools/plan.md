# Intake State Tools Plan

## Steps

1. Add Alembic migration for intake sessions, events, distilled context, draft revisions, asset refs, and workflow links.
2. Add intake persistence helpers with validation, JSON serialization, optimistic concurrency, idempotent append/finalize behavior, and compact state retrieval.
3. Register MCP tools in `server.py` using existing `WorkflowResult`, metrics, and remote-write guard patterns.
4. Add tests covering the full minimum viable flow plus second-slice tools.
5. Run targeted tests and compile checks.
6. Review git diff and keep unrelated dirty files out of the final change set.

## Verification

- `python3 -m compileall src/memory_knowledge`
- `python3 -m pytest tests/test_intake_tools.py -q`
- If broader impact appears likely, run the nearest existing server/tool tests.

## Closeout Criteria

- All required MCP tools are registered.
- Schema supports required lookup paths and idempotency/concurrency constraints.
- Conflict/failure cases return explicit structured diagnostics.
- Task artifacts document the implementation and verification.
