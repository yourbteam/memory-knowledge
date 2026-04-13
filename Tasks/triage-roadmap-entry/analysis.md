# Task Objective

Add roadmap coverage for the newly introduced triage-memory upgrade and its next planned follow-up phases.

# Current-State Findings

- `docs/roadmap.md` currently has no `triage` references.
- The repo now contains a shipped triage-memory feature:
  - migration `010_triage_memory`
  - four MCP tools:
    - `save_triage_case`
    - `search_triage_cases`
    - `record_triage_case_feedback`
    - `get_triage_feedback_summary`
  - canonical PostgreSQL case/feedback persistence
  - best-effort Qdrant embedding + semantic retrieval, with lexical fallback only when semantic retrieval is unavailable
  - feedback-summary aggregation
  - tests in `tests/test_triage_memory.py`
- The backlog already identifies several follow-up phases for triage-memory:
  - status normalization
  - re-embedding/backfill
  - confusion-cluster / clarification-recommendation tooling
  - stronger hybrid ranking

# Source Artifacts Inspected

- `docs/roadmap.md`
- `docs/backlog.md`
- `migrations/versions/010_triage_memory.py`
- `src/memory_knowledge/triage_memory.py`
- `src/memory_knowledge/server.py`
- `tests/test_triage_memory.py`

# Constraints

- This task is documentation-only.
- The roadmap entry should describe what is already implemented versus what remains planned.
- The roadmap should stay aligned with actual repo state and not imply unfinished work is complete.

# Risks And Edge Cases

- The roadmap could overstate the maturity of triage-memory if it does not distinguish shipped v1 from follow-up work.
- The roadmap could become redundant with backlog text if it turns into an issue list instead of a roadmap entry.

# Recommended Approach

- Add a concise roadmap section for triage-memory.
- Split it into:
  - delivered v1 capabilities
  - next follow-up phases
- Keep the language product/roadmap oriented rather than implementation-changelog oriented.

--- Analysis Verification Iteration 1 ---
Findings from verifier: 2
FIX NOW: 1 (analysis updated)
IMPLEMENT LATER: 0 (analysis updated)
ACKNOWLEDGE: 1 (no change)
DISMISS: 0 (no change)

--- Analysis Verification Iteration 2 ---
Findings from verifier: 2
FIX NOW: 1 (analysis updated)
IMPLEMENT LATER: 0 (analysis updated)
ACKNOWLEDGE: 1 (no change)
DISMISS: 0 (no change)
