# Intake State Tools Analysis

## Classification

Heavy change. This adds durable database state, MCP tools, concurrency semantics, and tests across the memory-knowledge backend.

## Goal

Implement durable brainstorm intake storage for workflow-orch so each turn can be reconstructed from memory-knowledge without relying on a long-lived CLI/model conversation.

## Current State

- Memory-knowledge already exposes MCP tools through `src/memory_knowledge/server.py`.
- Existing planning and workflow tools persist tasks, workflow runs, and artifacts, but there is no durable intake session/event/draft model.
- Database schema changes are managed through Alembic migrations under `migrations/versions`.
- Tool responses use `WorkflowResult` and remote-write guard checks for write operations.

## Requirements Covered

- Durable intake session records before a repository or project exists.
- Append-only event log with per-session monotonic sequence and optional idempotency key.
- Mutable distilled context with optimistic revision checks and sequence-regression protection.
- Versioned draft revisions.
- Metadata-only asset references.
- Links from intake sessions to workflow runs and planning identity fields.
- MCP tools for create, append, state retrieval, distilled-context update, draft save, event listing, asset add, finalization, workflow link, and actor-based session recovery.
- Structured conflict diagnostics for revision conflicts and finalization conflicts.

## Constraints

- Do not store binary file/blob content in this slice.
- Do not implement prompting, summarization, UI, or workflow-orch transport.
- Preserve raw transcript separately from mutable working memory.
- Default state retrieval must avoid loading the full transcript.
- Avoid changing existing planning-task behavior.

## Implementation Surfaces

- Add migration `015_intake_sessions` for `ops.intake_*` tables and indexes.
- Add an intake persistence helper module under `src/memory_knowledge/admin/`.
- Register MCP tools in `src/memory_knowledge/server.py`.
- Add unit tests for persistence flow and tool response behavior.

## Risks

- Concurrent event append must serialize on the session row to keep sequence monotonic.
- JSONB handling must be explicit so asyncpg and tests behave consistently.
- Existing `WorkflowResult` shape does not expose top-level `ok`/`errorCode`; conflict details should be included in `data` while preserving the established response model.
