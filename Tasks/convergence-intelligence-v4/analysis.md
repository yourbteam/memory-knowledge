## Objective

Use prior workflow loops and validator behavior to recommend changes that reduce pointless retries and improve convergence.

## Problem

Current loop analytics summarize where retries happen, but they do not yet tell the orchestrator what intervention is most likely to help.

## Intended Upgrade

Model convergence behavior such as:

- retry patterns by workflow and phase
- validator ordering weaknesses
- intervention patterns that reduce loop count

## Practical Before/After

Before:
- loop analytics are retrospective

After:
- the system can recommend inserting a different phase, stronger grounding step, or earlier validator before another retry

## Likely Surfaces

- convergence heuristics
- workflow intervention recommendations
- loop-to-intervention mapping

## Current-State Grounding

- `src/memory_knowledge/admin/analytics.py` already exposes loop, validator, grade, and entropy analytics over workflow runs.
- The repo already persists the raw telemetry needed for convergence guidance: iteration counts, phase attempts, validator outcomes, run grades, and planning context.
- The main gap is synthesis. The existing analytics report where churn happened, but they do not translate repeated failure patterns into recommended operator or orchestrator interventions.

## Recommended Approach

- Reuse the workflow analytics facts instead of introducing new persistence or triage-side state.
- Add an advisory convergence summary that buckets runs by repository, workflow, and actor, then maps repeated reasons to recommended interventions.
- Include dominant retry phase and dominant failed validator so the orchestrator can decide whether to add grounding, move validators earlier, or escalate after a threshold.
