# One-shot planner handoff — proactive sequence observer

## Goal

Produce a granular implementation plan for OBS-001 through OBS-030 exactly. The result must preserve reusable operational knowledge early, correctly, and durably while remaining advisory and bounded.

## Non-goals

Do not redesign general telemetry, task classification, workflows, promotion, or the registry. Do not execute or replay observed commands, request credentials, mine chat/terminal history, weaken lifecycle gates, clean the discovery backlog, deploy anything, add model/network authority, or write to observed repositories.

## Required planning order

1. Verify or schedule the sequence-flywheel prerequisites: one shared `CandidateIdentity`, execution-claimed/execution-returned correlation contract, and versioned final-effective verification contract. Do not invent observer-specific alternatives.
2. Choose the future command-invoker integration point. No general dispatcher exists today. The chosen contract must bind a guard authorization identity to actual invocation/result evidence, including eligible one-step external operations, while keeping the observer unable to dispatch.
3. Define additive safe observation and decision schemas in memory-knowledge, including deterministic identities, retention, provenance derivation, resource caps, and failure taxonomy.
4. Plan the deterministic evaluator: terminal/checkpoint trigger, completeness, eligibility, value with `UNKNOWN`/no-credit semantics, registered-first match, freshness-checked active-discovery match, suppression, and the four outcomes.
5. Route proposals and evidence attachment only through canonical discovery interfaces; preserve readiness, blocker, correction, successor, promotion, and registered verification authority.
6. Reconcile cross-store crash windows and concurrency with explicit recovery or transaction mechanics; do not assume current bootstrap is fully atomic.
7. Map every PO obligation to an implementation change and focused verification, then add exactly one full candidate-to-registered-reuse proof.

## Fixed constraints

- Future observer behavior is `FUTURE_SYSTEM`; do not claim it exists.
- Missing result evidence returns no proposal.
- Observer-derived provenance retains one of the four guard authority classes plus derivation identity.
- Semantic collisions and missing legacy identity fail closed and remain auditable.
- `ACTIVE.md` is a human snapshot, not the active-discovery source of truth.
- Legacy v1 behavior remains readable and unchanged unless an explicit migration is planned.
- The observer cannot alter the originating run result or any promotion predicate.

## Planner-owned decisions

- Exact invoker-integration entry point and safe authorization/result schema.
- Exact additive persistence location and versioning.
- Exact numeric evidence, runtime, and candidate caps.
- Exact deterministic value weights/thresholds within the evidence rules.
- Exact generated active-discovery membership and freshness mechanism.
- Exact transaction/recovery design across decision, discovery, manifest, receipts, and ledger.

Any requirement, repository, external dependency, effect, or validation beyond this handoff is a scope change and must stop for approval.
