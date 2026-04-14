# Objective

Prepare V3 work that upgrades triage retrieval from the current lightweight hybrid ranking into a stronger adaptive ranking model that uses operational outcome signals more effectively.

# Current-State Findings

- `search_triage_cases` already uses a hybrid score, but the weighting is intentionally simple:
  - semantic or lexical baseline
  - optional project preference boost
  - outcome confidence adjustment
  - clarification penalty
  - recency boost
- The ranking logic is local to [src/memory_knowledge/triage_memory.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/triage_memory.py).
- Canonical lifecycle state is now part of the ranking-adjacent read surface. `triage_memory.py` stores and projects `lifecycle_state`, `lifecycle_updated_utc`, and `superseded_by_case_id`, and migration `012_triage_decision_lifecycle_state` backfills that state for historic cases.
- A policy-synthesis surface now also exists elsewhere in the repo through [src/memory_knowledge/triage_policy.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/triage_policy.py) and the corresponding MCP tools in [src/memory_knowledge/server.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/server.py), but `search_triage_cases` does not yet consume those policy priors or behavior profiles.
- Existing tests cover determinism and current weighting behavior, but there is no richer adaptive ranking framework.
- There is no per-repository or per-project ranking profile.
- There is still no explicit use of workflow success/failure patterns, policy priors, or validator/finding data inside triage ranking itself, even though some of those signals now exist elsewhere in the repo.

# Source Artifacts Inspected

- [src/memory_knowledge/triage_memory.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/triage_memory.py)
- [src/memory_knowledge/triage_policy.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/triage_policy.py)
- [src/memory_knowledge/server.py](/Users/kamenkamenov/memory-knowledge/src/memory_knowledge/server.py)
- [migrations/versions/012_triage_decision_lifecycle_state.py](/Users/kamenkamenov/memory-knowledge/migrations/versions/012_triage_decision_lifecycle_state.py)
- [migrations/versions/013_triage_policy_artifacts.py](/Users/kamenkamenov/memory-knowledge/migrations/versions/013_triage_policy_artifacts.py)
- [tests/test_triage_memory.py](/Users/kamenkamenov/memory-knowledge/tests/test_triage_memory.py)
- [tests/test_triage_policy.py](/Users/kamenkamenov/memory-knowledge/tests/test_triage_policy.py)
- [docs/roadmap.md](/Users/kamenkamenov/memory-knowledge/docs/roadmap.md)

# Scope

## In Scope

- improved ranking feature design for `search_triage_cases`
- repo-aware and project-aware ranking profiles
- stronger signal integration from triage and workflow outcomes
- validation criteria for ranking behavior and deterministic ordering

## Out Of Scope

- policy artifact storage
- lifecycle-state schema design
- automatic enforcement decisions

# Gaps To Close

1. Current ranking is too shallow for long-term adaptive behavior.
2. There is no explicit success-rate prior per workflow or request kind.
3. There is no repo-specific ranking profile.
4. There is no connection from workflow telemetry to triage ranking.
5. There is no framework for tuning and validating ranking feature weights.

# Constraints

- Ranking must remain deterministic for the same inputs and dataset state.
- Existing tool contracts should stay stable.
- Ranking features should be explainable in the returned output or internal diagnostics.
- Zero-match and low-signal cases must still degrade safely.

# Risks

- Adding too many ranking signals without diagnostics will make results opaque.
- Cross-repo priors can degrade local accuracy if repo-specific behavior is ignored.
- Overweighting historical success can suppress novel but correct decisions.
- If ranking is not tested rigorously, subtle behavior regressions will be hard to detect.

# Recommended Approach

- Introduce a structured ranking feature model rather than ad hoc constant tweaks.
- Keep feature weights explicit and testable.
- Start with additive outcome-informed features before introducing self-tuning or learning loops.
- Add ranking diagnostics that can be inspected in tests and optionally returned in debug-oriented contexts.

# Proposed Deliverables

- ranking feature extraction helpers
- repository/project ranking profile support
- richer score components using:
  - semantic similarity
  - outcome quality
  - repo/project affinity
  - workflow success priors
  - clarification cost
  - recency
- expanded regression tests for ranking scenarios and deterministic ties

# Sequencing Notes

- Should consume the canonical lifecycle semantics that now already exist in the repo.
- Can proceed alongside policy synthesis evolution, but should be explicit about whether it consumes current policy priors in this increment or leaves that for a later pass.

--- Analysis Verification Iteration 1 ---
Findings from verifier: 4
FIX NOW: 4 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)
