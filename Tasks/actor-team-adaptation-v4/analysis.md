## Objective

Adapt routing and workflow defaults by actor or automation source when historical behavior differs materially.

## Problem

Current analytics can group by actor, but the system does not yet adapt behavior based on repeated actor-specific success or failure patterns.

## Intended Upgrade

Support actor-aware behavior such as:

- stronger clarification requirements for weakly grounded actors
- safer default workflow selection for noisy automation sources
- lighter handling for actors with consistently high-quality inputs

## Practical Before/After

Before:
- actor trends are visible only in reporting

After:
- actor history can influence route confidence, required context, and workflow defaults

## Likely Surfaces

- actor behavior policy artifacts
- actor-aware routing adjustments
- actor-level policy status and inspection reads

## Current-State Grounding

- The repo already stores `actor_email` on workflow runs and findings, and the analytics layer already groups quality, entropy, and convergence summaries by actor.
- Planning context is also already available on actor-scoped analytics, which gives a workable proxy for team context without adding a separate team directory.
- The main gap is synthesis and consumption: actor history is visible in analytics, but triage and orchestration do not yet use it to bias clarification posture or route confidence.

## Recommended Approach

- Add an actor adaptation synthesis module that converts actor-scoped analytics into an advisory posture such as `streamlined`, `balanced`, or `cautious`.
- Expose that posture through a dedicated read tool.
- Wire the adaptation summary into `triage_request_with_memory` when an `actor_email` is supplied so route confidence and clarification recommendations can adjust safely.
