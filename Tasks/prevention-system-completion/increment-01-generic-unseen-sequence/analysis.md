# Increment 01 analysis: generic unseen-sequence execution

## Objective

Prove that a sequence not named in the frozen ten-owner implementation can be
hydrated into a closed executable contract and executed by the existing
crash-safe owner runtime without adding sequence-specific Python branches.

## Size and grounding

- Type: implementation.
- Size: standard.
- Repository: `memory-knowledge` only.
- Environment: local temporary filesystem only; no network, credentials,
  deployment, commit, or push.
- Required verification: verify-plan, focused tests, regression tests over the
  touched prevention surfaces, and verify-work.

## Proven baseline retained

- `sequence_candidate_contract.py` already provides deterministic candidate
  identity containing typed argv, repository-qualified source references,
  effect class, dependencies, and same-path verification evidence.
- `prevention_owner_runtime.py` already provides durable prepare/start/commit,
  three-way crash reconciliation, semantic terminal verification, terminal
  artifact/event recovery, and exactly-once terminalization.
- `prevention_adapters.py` already provides closed parameter validation,
  trusted-root resolution, typed binding receipts, and shell-free argv plans.
- `prevention_source_probes.py` already provides typed read-only source capture
  at a true external edge.

## Confirmed gaps this increment closes

1. Adapter selection is keyed to hard-coded `BASE_ARGV` owner ids.
2. Source-probe selection is keyed to hard-coded owner/profile maps.
3. Reconciliation and terminal provider lookup requires owner-specific symbols.
4. Controller execution requires a duration budget even when no real scarce
   resource is being reserved.
5. No closed materializer binds an observed candidate, approved parameter/root
   schema, effect observations, and terminal conditions into one generic
   executable contract.

## Stable design boundary

The generic path is contract-driven. A closed materialized contract owns:

- the exact candidate identity and fingerprint;
- an ordered argv template made only of literal tokens and named typed
  parameter references;
- the complete parameter schema and trusted repository-root bindings;
- the source-edge kind and exact read-only facts used for reconciliation;
- semantic terminal requirements;
- actual resource requirements, represented as an empty set for this local
  proof rather than fabricated duration.

The runtime interprets that fixed schema generically. It does not import or
branch on the new sequence id. The existing ten-owner path remains unchanged in
this increment.

## Proof sequence

The unseen fixture is a harmless local sequence that writes one JSON artifact
under a temporary trusted repository root. Its real local-state observer reads
the artifact without mutating it. The fixture exists only in tests; the generic
production code must contain no reference to its id.

This is not yet the daily production gateway. It proves the generic executable
contract boundary needed before wiring `sequence_checked_exec.py` in the next
increment.
