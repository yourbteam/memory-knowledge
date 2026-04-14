## Objective

Upgrade routing so request selection is influenced by downstream outcomes, not just similarity and prior case retrieval.

## Problem

Current routing can reuse similar triage history and policy artifacts, but repeated downstream failures are still mostly visible after the fact.

## Intended Upgrade

Add explicit outcome-weighted routing behavior using signals such as:

- run success vs partial/error rates
- validator failure rates
- loop counts
- human override frequency
- clarification rates

## Practical Before/After

Before:
- a similar prior request can be retrieved, but route choice is still relatively shallow

After:
- request classes that repeatedly fail under aggressive routing are automatically biased toward safer workflows

## Likely Surfaces

- triage policy artifact inputs
- adaptive routing score adjustments
- route outcome aggregation by repository/project/request shape
- new reporting or inspection tool for adaptive routing weights

## Current-State Grounding

- `src/memory_knowledge/triage_policy.py` already computes routing recommendations from triage outcome and lifecycle quality.
- `src/memory_knowledge/triage_memory.py` already uses historical outcome/lifecycle signals inside triage case ranking.
- The missing surface is not raw data collection. It is explicit route-risk summarization and an operator-facing read tool that exposes the adaptive routing state directly.
- The ranking path also lacked an explicit route-failure penalty feature, which made outcome-aware behavior harder to inspect and reason about.

## Recommended Approach

- Extend the existing policy aggregation layer with an outcome-weighted route summary grouped by request kind, workflow, and run action.
- Add a dedicated MCP read tool for that summary instead of inventing a parallel policy system.
- Tighten ranking with an explicit route-failure penalty derived from historical failed/corrected/overridden/clarification-heavy routes.
- Expose the top outcome-weighted routes in `triage_request_with_memory` so integrators can see why a route is being favored or avoided.
