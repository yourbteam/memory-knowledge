## Objective

Turn repeated ambiguity and clarification failures into reusable clarification policy.

## Problem

The system can already summarize confusion clusters and clarification recommendations, but it does not yet convert those patterns into stronger default clarification behavior.

## Intended Upgrade

Persist clarification policies that capture:

- common ambiguity clusters
- required missing fields
- recommended clarification prompts
- confidence and freshness of the recommendation

## Practical Before/After

Before:
- ambiguity patterns are visible but mostly advisory

After:
- the routing layer can ask the right clarifying questions before committing to a workflow

## Likely Surfaces

- persisted clarification policy artifacts
- new read contract for required clarifications
- stronger use of confusion-cluster history in triage decisioning

## Current-State Grounding

- `src/memory_knowledge/triage_policy.py` already computes clarification policies and persists them through `refresh_triage_policy_artifacts`.
- `src/memory_knowledge/triage_memory.py` already exposes confusion clusters and clarification recommendations, so the repo has the raw ambiguity evidence needed for this slice.
- The main gap is that clarification policy is still too passive. It lacks explicit missing-field guidance, freshness weighting, and a single read surface that tells an integrator when clarification should be treated as required.

## Recommended Approach

- Strengthen the existing clarification policy payload instead of inventing a second policy table.
- Infer reusable missing-field hints from recurring clarification questions.
- Add a dedicated `get_required_clarification_policy` read tool that returns the strongest applicable clarification contract.
- Surface that contract directly in `triage_request_with_memory` so an integrator can ask clarifying questions before committing to a workflow.
