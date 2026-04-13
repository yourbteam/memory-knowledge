# Scope

- Update `docs/roadmap.md` to include triage-memory.
- Make the entry reflect both shipped v1 functionality and the next planned follow-up phases.

# Implementation Steps

1. Inspect the current structure and tone of `docs/roadmap.md`.
2. Re-read the governing source artifacts for roadmap accuracy:
   - `Tasks/triage-roadmap-entry/analysis.md`
   - `docs/backlog.md`
   - `migrations/versions/010_triage_memory.py`
   - `src/memory_knowledge/triage_memory.py`
   - `src/memory_knowledge/server.py`
   - `tests/test_triage_memory.py`
3. Add a triage-memory roadmap entry that explicitly separates:
   - delivered v1 capabilities already shipped
   - planned follow-up phases that are still open backlog work
4. Treat the true future triage follow-up phases as backlog items:
   - `#15` triage outcome status normalization
   - `#16` triage re-embedding/backfill
   - `#17` confusion-cluster / clarification-recommendation tooling
   - `#19` stronger hybrid ranking
   Exclude `#18` from the planned-phase list because it is this roadmap-documentation task itself.
5. In the delivered v1 description, keep semantic-search wording precise:
   - triage cases are persisted canonically in PostgreSQL
   - semantic retrieval is best-effort via Qdrant
   - lexical fallback applies when semantic retrieval is unavailable, not as a general no-hit fallback
6. Re-read the updated roadmap entry for accuracy, tone alignment, and clear delivered-vs-planned boundaries.

# Validation

- Confirm `docs/roadmap.md` now contains a discoverable `triage` entry.
- Confirm the entry distinguishes shipped v1 capabilities from planned follow-up phases.
- Confirm the shipped v1 description matches the actual current surface:
  - migration `010_triage_memory`
  - four MCP tools
  - PostgreSQL case/feedback persistence
  - best-effort semantic retrieval with the precise lexical-fallback nuance
  - feedback-summary aggregation
- Confirm the planned section accurately reflects the open backlog follow-up phases rather than blending them into the delivered v1 description.
- Confirm the planned follow-up list maps to backlog items `#15`, `#16`, `#17`, and `#19`, and does not accidentally treat `#18` as a future phase.

# Affected Files

- `docs/roadmap.md`

--- Plan Verification Iteration 1 ---
Findings from verifier: 4
FIX NOW: 4 (plan updated)
IMPLEMENT LATER: 0 (plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)

--- Plan Verification Iteration 2 ---
Findings from verifier: 2
FIX NOW: 1 (plan updated)
IMPLEMENT LATER: 0 (plan updated)
ACKNOWLEDGE: 1 (no change)
DISMISS: 0 (no change)
