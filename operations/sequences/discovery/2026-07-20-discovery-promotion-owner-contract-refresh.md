# Sequence Discovery Log: Discovery Promotion Owner Contract Refresh

DiscoveryId: discovery-a303d6ac-e058-5f2c-915f-81487ba71690
Status: discovery
CreatedAtUtc: 2026-07-20T15:24:26Z
BootstrapRequestSha256: e94836c4039a7fd31d2c1343c2daf3ac6a9fd096f580349617071e215af0cb76
RegisteredSequenceMatch: none

## Intended Outcome

Refresh the approved executable-owner source binding after the verified discovery-promotion controller correction so registry loading and sequence promotion resume.

## Why This Looks Repeatable

Governed owner implementations require their approved source hash and materialized executable contract to move with an authorized correction.

## Required Inputs, Auth, Or Environment

- The approved controller correction hash 312fb94fbf3fd572604166501301aa1755c3c932d49f81f1bc4a8ba7018b8fda.
- The existing discovery-promotion-lifecycle owner proposal.
- The canonical owner contract materializer.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| refresh-approved-source-binding | python3 scripts/prevention_contract_materializer.py | The materialized owner executable contract matches the approved corrected lifecycle source hash. | Update the approved proposal source binding before materialization. |
| refresh-current-proof-corpus | .venv/bin/python scripts/prevention_owner_acceptance_producer.py --all-current | Every mechanically required current owner/profile/scenario proof is regenerated through the real acceptance path with per-profile progress. | The zero-input batch derives its complete work set from the current materialized contracts; callers supply no owner, profile, scenario, or JSON envelope. |
| rebuild-proof-projections | python3 scripts/prevention_owner_acceptance.py; python3 scripts/prevention_observable_materializer.py; python3 scripts/prevention_contract_materializer.py | The proof report, observable evidence, and executable contracts are rebuilt from current content-addressed traces and authenticated source bytes. | Run in this order; do not hand-edit generated projections. |
| verify-automation | scripts/run_pytest.sh tests/prevention/test_owner_contract_materialization.py tests/prevention/test_contracts_and_registry.py tests/prevention/test_owner_source_acceptance.py tests/test_discovery_promotion_lifecycle.py | Owner materialization, current proof selection, typed registry loading, and lifecycle regressions pass together. | No external model or product workflow is invoked. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop if the corrected source is not explicitly bound to Kamen's approved remediation decision, materialization changes unrelated owner semantics, or any registry/lifecycle test fails.

## Verified Path

- Materializer --check succeeds, typed registry loading accepts discovery-promotion-lifecycle, and the combined focused suite passes.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
