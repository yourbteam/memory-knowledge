## Objective

Govern adaptive routing and clarification policies so they can be reviewed, approved, versioned, and rolled back safely.

## Problem

As adaptation gets stronger, silent policy drift becomes risky unless recommendation and activation are separated.

## Intended Upgrade

Add governance over policy changes:

- proposal
- review
- approval
- activation
- rollback

## Practical Before/After

Before:
- adaptive logic risks becoming opaque if made stronger

After:
- policy changes can be inspected and controlled before becoming active behavior

## Likely Surfaces

- policy proposal records
- approval metadata
- versioned policy activation state
- rollback capability

## Current-State Grounding

- The repo already persists governance metadata on triage policy artifacts: `rollout_stage`, `drift_state`, `is_suppressed`, `confidence_threshold`, `minimum_evidence_threshold`, `last_reviewed_utc`, and `governance_notes`.
- Current behavior already separates advisory recommendations from trusted rollout through `rollout_stage`, but the inspection surface is still low-level and artifact-centric.
- The main gap is a governance summary that tells an operator what is stable, what is promotion-ready, and what needs review across the current adaptive policy set.

## Recommended Approach

- Reuse the existing `ops.triage_policy_artifacts` governance fields.
- Add a consolidated rollout summary read tool that computes stable advisory candidates, suppression pressure, and next governance actions.
- Keep this slice read-only and advisory. Explicit approval writes can come later if the user wants them.
