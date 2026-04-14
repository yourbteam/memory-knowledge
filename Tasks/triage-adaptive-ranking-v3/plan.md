# Objective

Upgrade `search_triage_cases` from the current lightweight hybrid ranking into a more expressive adaptive ranking model that better reflects successful historic behavior.

# Scope

## In Scope

- featureized ranking model for triage case search
- repo-aware and project-aware signal weighting
- optional workflow-success priors
- deterministic diagnostics and regression tests

## Out Of Scope

- storage of synthesized policies
- automatic policy enforcement
- broad workflow analytics redesign outside triage-search consumption

# Implementation Steps

1. Formalize ranking features.
- Replace the current implicit score math with named feature components.
- Candidate features:
  - semantic similarity
  - lexical fallback baseline
  - repository match
  - project match
  - workflow historic success
  - request-kind historic success
  - clarification penalty
  - outcome-quality weight
  - recency decay

2. Add ranking-profile support.
- Allow default global weights plus repo-scoped overrides.
- Keep the first implementation static and configuration-backed or code-backed rather than learned online.
- This increment may consume lightweight policy priors that already exist in `triage_policy.py`, but it should do so through deterministic local weighting rather than remote tool calls or runtime policy writes.

3. Integrate additional historic signals.
- Pull in concrete first-pass priors from the current repo surface:
  - lifecycle state and lifecycle recency from `triage_memory.py`
  - lightweight policy-aligned behavior priors derived from the same local triage history
  - existing workflow/outcome success signals already persisted on triage cases and feedback rows
- Ensure low-signal or missing-prior cases degrade back to current behavior rather than failing.

4. Refactor ranking internals.
- Move score feature computation into dedicated helper functions or a ranking object.
- Preserve deterministic tie-breaking and current response contract.

5. Add diagnostics.
- Provide internal feature breakdowns for tests.
- Decide whether any ranking-explanation metadata should be included in returned rows or exposed only in debug/test paths.

6. Expand regression tests.
- repo-preference scenario
- project-preference scenario
- lifecycle-aware ordering scenario
- strong semantic match with poor historic outcomes
- weaker semantic match with consistently successful historic outcomes
- optional policy-prior ordering scenario if lightweight policy priors are consumed in this increment
- deterministic ties across multiple similar rows
- lexical fallback under missing semantic path

# Affected Files

- `src/memory_knowledge/triage_memory.py`
- optionally `src/memory_knowledge/triage_ranking.py`
- `tests/test_triage_memory.py`
- optionally a new ranking-focused test file

# Validation

- existing triage search contract remains stable
- ranking remains deterministic
- stronger historic-success signals improve ordering in covered test scenarios
- lifecycle-aware ranking signals improve ordering in covered test scenarios
- policy-prior signals, if enabled in this increment, improve ordering in covered test scenarios
- missing optional signals do not break search behavior
- lexical fallback still works when semantic retrieval is unavailable

# Dependencies And Sequencing

- should consume the lifecycle baseline already established in the current repo
- should explicitly keep policy-prior use lightweight and local to this ranking increment
- should be available before policy synthesis is treated as high-confidence guidance

--- Plan Verification Iteration 1 ---
Findings from verifier: 4
FIX NOW: 4 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 0 (no change)
