# Proactive sequence observer — planner-ready research

## Result

The bounded feature is an advisory, deterministic observer that consumes canonical non-secret operational evidence and returns exactly one outcome: `NO_CANDIDATE`, `LINK_REGISTERED`, `LINK_DISCOVERY`, or `PROPOSE_DISCOVERY`. It never executes commands, requests credentials, advances readiness, promotes discoveries, or registers sequences.

The 30 frozen requirements cover the full path from durable evidence production through eligibility, correctness, value, identity, deduplication, discovery creation, lifecycle preservation, safety, concurrency, auditability, compatibility, and verification. The final coverage and satisfaction gates pass. The only non-pass raw finding is a planner decision: no general command dispatcher exists today, so the planner must choose the bounded future invoker-integration point without giving the observer dispatch authority.

## Confirmed current state

- `sequence_guard.py` proves pre-dispatch authorization, selected source, provenance class, step identity, receipt chain, and bundle freshness, but does not execute or persist a command result.
- `work_memory.py` durably records runs, blockers, corrections, bundle transitions, verification, terminal events, and promotion, but no guarded-command observation. Classification, selection, and active receipts are temporary.
- A general checked dispatcher and an observer hook do not currently exist.
- G17 can make a one-step external operation observer-eligible even when current task classification produces no durable operational run.
- Current bundle hashes, discovery IDs, and bootstrap request hashes prove integrity, not semantic equivalence across tasks.
- Discovery readiness and sibling verification consumers do not all use one final-effective ordered-event rule.
- Bootstrap writes discovery documents, manifests, receipts, active state, and ledger state sequentially; ledger atomicity does not prove cross-store atomicity.
- The sequence-flywheel research defines the shared `CandidateIdentity`, execution-claimed/execution-returned ordering, and versioned final-effective verification contracts. Their implementation is an explicit upstream prerequisite, not assumed current behavior.

## Stable ownership boundaries

- Guard: command authority and one of the four canonical provenance classes.
- Future command-invoker adapter: correlate guard authorization with safe `execution_claimed` and `execution_returned` evidence from the actual invoker. The observer is never the invoker.
- Work memory: validated, durable, repository-qualified observation and decision records.
- Observer: bounded evidence reduction, eligibility, value, suppression, shared identity consumption, deduplication, and advisory disposition.
- Discovery bootstrap/log: canonical candidate creation, append, structure, and readiness inputs.
- Promotion lifecycle: blocker/correction/successor handling, qualification, atomic promotion, and fresh registered verification.

## Fixed requirement decisions

- Incomplete, unordered, unproven, secret-bearing, or inferred steps fail closed.
- Observer-derived records retain one original guard provenance class; they are not a fifth authority class.
- Registered matching is first, active-discovery matching second, and proposal creation last.
- The observer consumes the sequence-flywheel `CandidateIdentity`; it does not define a second fingerprint and never treats operation-kind fallback as semantic equivalence.
- The active-discovery population must be generated and freshness-checked. `ACTIVE.md` is not authoritative.
- Existing durable metrics may support recurrence, duration, blockers, corrections, pass rate, and verification rate. Unsupported claims such as time saved receive `UNKNOWN` and no credit unless a safe durable producer is added.
- Versioned observer/flywheel records use one final-effective reducer across discovery readiness, registered selection, correction selection, lifecycle verification, and feedback. Legacy v1 interpretation remains unchanged unless explicitly migrated.
- Observer failure cannot change the originating task/run result.
- Observed repositories remain read-only; observer and discovery state is owned by memory-knowledge.

## Verification boundary

Focused tests must cover each OBS requirement. One canonical end-to-end proof must start with grounded observations, create or reuse a discovery through canonical interfaces, traverse unchanged readiness and promotion gates, obtain fresh registered same-path verification, resume safely, and then return `LINK_REGISTERED`. Effectful-command tests assert zero observer dispatch.

## Exclusions

No transcript or terminal-history mining, secret/personal capture, model or network dependency, external service, deployment, cross-repository write, directive or phase-ledger change, backlog cleanup, automatic promotion, or general workflow/work-memory redesign is permitted.
