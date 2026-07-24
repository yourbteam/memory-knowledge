# Increment 01 plan: generic unseen-sequence execution

## Fixed scope

Implement one contract-driven path by which an unseen sequence candidate can be
materialized, admitted without a duration budget when it declares no scarce
resource requirement, and executed through `OwnerRuntime` with real local-state
reconciliation and semantic terminal observation.

No owner-specific adapter, source-provider symbol, profile map row, or sequence
id branch may be added for the fixture.

## Implementation surface

1. Add `scripts/prevention_generic_contract.py`.
   - Define and validate one closed schema for a generic executable contract.
   - Require the exact normalized candidate identity and matching fingerprint.
   - Accept only literal argv tokens or named parameter references.
   - Bind every parameter reference to a materialized parameter schema and every
     path parameter to one declared trusted repository root.
   - Bind source edge kind, reconciliation facts, terminal facts, and an explicit
     `resource_requirements` list.
   - Reject unknown fields, unreferenced parameters, missing references, absolute
     authority, contract hash drift, and unsupported effect/source combinations.

2. Extend `scripts/prevention_adapters.py` at its generic boundary.
   - Recognize a validated generic contract by schema kind, not sequence id.
   - Reuse the existing parameter/root resolver.
   - Render the fixed argv template without shell parsing or arbitrary command
     input.
   - Add one generic reconciliation classifier and one generic semantic terminal
     verifier driven only by the contract-declared observations.
   - Preserve every existing ten-owner behavior unchanged.

3. Extend `scripts/prevention_source_probes.py`.
   - Construct a production observation transport from the validated generic
     contract's declared edge kind and provider ids.
   - Add a real read-only local-filesystem edge implementation whose allowed root
     and observed relative paths come from the materialized contract.
   - Preserve the existing frozen owner/profile source map for legacy owners.

4. Extend `scripts/prevention_owner_runtime.py` only where necessary to select
   the generic contract-driven handlers and transport.
   - Preserve effect identity, prepare-before-effect, reconciliation generations,
     semantic terminal evidence, and exactly-one terminal event/artifact.

5. Extend `scripts/prevention_controller.py`.
   - Admit a verified generic contract without consulting the ten-owner identity
     map.
   - If `resource_requirements` is empty, execute without `BudgetAuthority`.
   - Fail closed when non-empty resource requirements lack their corresponding
     authority; do not translate them into duration.
   - Preserve the legacy owner execution path unchanged.

6. Add `tests/prevention/test_generic_sequence_execution.py`.
   - Materialize an unseen sequence contract and assert the implementation files
     contain no branch or registration for its id.
   - Prove a valid typed parameter writes exactly one expected local artifact and
     reaches one semantic terminal event/artifact.
   - Prove unknown, missing, wrong-type, absolute, traversal, symlink-escape, and
     wrong-root parameters fail before effect execution.
   - Prove exit zero with a missing or semantically wrong artifact cannot
     terminalize.
   - Simulate crash after the effect, then prove reconciliation returns
     `ALREADY_APPLIED` and does not execute the effect twice.
   - Replay the same intent and prove the existing terminal result is reused with
     no second effect and no second terminal event.
   - Prove a changed candidate fingerprint or contract bytes are rejected.

## Verification

1. Run focused generic tests red before implementation where feasible, then green.
2. Run the existing owner runtime, adapter, source-probe, controller, and typed
   dispatch test surfaces through `scripts/run_pytest.sh`.
3. Run Python compilation or the repository's applicable lint check for touched
   modules.
4. Review the complete in-scope diff against this plan.
5. Run independent verify-work; the parent fixes only critic-validated in-scope
   findings and repeats focused verification.

## Terminal acceptance contract

This increment passes only if all of the following are proven on the same source
revision:

- the unseen sequence executes through `PreventionController` and `OwnerRuntime`;
- no production code names or branches on the unseen fixture id;
- no duration budget is constructed, derived, reserved, or required for it;
- parameter and trusted-root violations fail before the effect;
- crash recovery observes the real artifact and avoids duplicate execution;
- exit zero cannot bypass semantic artifact verification;
- exactly one terminal event and one matching terminal artifact exist;
- replay reuses that terminal result without another effect;
- existing focused prevention regressions pass;
- independent review has no actionable in-scope finding.

## Explicit exclusions

- `sequence_checked_exec.py` production gateway wiring.
- Git, Docker, credential, operator, browser, or remote source edges.
- Migration or activation of the original ten owners.
- Host interception or FD 198 work.
- Duration limits, estimated-time gates, or synthetic capacity.
- Commits, pushes, deployments, secrets, and phase-ledger changes.
