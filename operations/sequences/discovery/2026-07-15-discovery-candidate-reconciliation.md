# Sequence Discovery Log: discovery-candidate-reconciliation
ReadyAtUtc: 2026-07-15T18:45:00Z

DiscoveryId: discovery-782832ed-7fa4-5efe-9765-463303ecd2a2
Status: promoted
PromotedSequenceId: discovery-candidate-reconciliation
CreatedAtUtc: 2026-07-15T18:16:30Z
RegisteredSequenceMatch: none

## Intended Outcome

Inventory every discovery log, produce a frozen evidence-backed disposition manifest, execute approved promotions or absorptions through the canonical lifecycle, verify registered results, and remove terminal candidates from the active queue without deleting provenance.

## Why This Looks Repeatable

Discovery logs accumulate continuously and require the same deterministic audit, promotion, verification, blocker, successor, and cleanup path.

## Required Inputs, Auth, Or Environment


- The memory-knowledge repository root and a clean, readable Git HEAD for the audit snapshot.
- A complete generated disposition manifest reviewed and explicitly approved by Kamen before execute.
- For each promote row: sequence_id, use_when, operation_kind, automation_display, pass_signal, and max_qualification_runs required by the canonical lifecycle.
- For absorb or supersede rows: a concrete registered target and evidence that the reusable behavior is already preserved there.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| protected-controller-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --solution <solution> --reusable-behavior-changed yes --changed-artifact <path> | The sealed pre-change controller validates and records the exact corrected artifact set, then a successor run verifies it. | Use this immutable bootstrap path when the correction changes scripts/work_memory.py; never execute the changed controller to authorize itself. |
| bind-dependencies-from-file | python3 scripts/sequence_discovery_log.py set-dependencies --file operations/sequences/discovery/2026-07-15-discovery-candidate-reconciliation.md --dependencies-json /private/tmp/discovery-candidate-reconciliation-dependencies.json | The discovery manifest is updated from the JSON document at the supplied path. | --dependencies-json accepts a filesystem path, not inline JSON. |
| bootstrap-controller | Create scripts/discovery_candidate_reconciliation.py and tests/test_discovery_candidate_reconciliation.py before dependency binding and source-bundle selection. | The controller and test entry points exist before a guarded implementation run is selected. | Selection fails closed when a recorded executable is absent; scaffold the registered entry point first, then bind it into the discovery manifest. |
| verify-automation | scripts/run_pytest.sh tests/test_discovery_candidate_reconciliation.py tests/test_discovery_promotion_lifecycle.py -q | planned | Exercise complete inventory, manifest validation, fail-closed drift, lifecycle delegation, checkpointing, and non-destructive active-index cleanup. |
| execute-approved | python3 scripts/discovery_candidate_reconciliation.py execute --manifest <manifest> --active-index <active-index> | planned | Drive only approved promote rows through discovery_promotion_lifecycle.py; terminal non-promotion rows change only the generated active queue and never delete discovery provenance. |
| validate-dispositions | python3 scripts/discovery_candidate_reconciliation.py validate --manifest <manifest> | planned | Require exact candidate-set and HEAD match plus complete evidence-backed dispositions before execution. |
| audit-candidates | python3 scripts/discovery_candidate_reconciliation.py audit --output <manifest> | planned | Freeze repository HEAD and enumerate every discovery log with lifecycle, registry, blocker, readiness, and verification facts; no repository mutations. |

## Failure Handling


Fail before mutation when HEAD or the candidate set differs from the frozen manifest, any disposition is pending or lacks required evidence, a target sequence is missing, or an unexpected path appears. Execute candidates in manifest order with a durable checkpoint. On lifecycle failure, preserve the candidate log and checkpoint, catalog the blocker, stop the batch, correct the reusable boundary, and resume only through the canonical successor path. Never delete discovery logs; cleanup means excluding evidence-backed terminal rows from the generated active index.

## Verified Path


- Correction-bound successor a2dc4314-459f-4449-bdcb-450e6fdd2178 ran scripts/run_pytest.sh across reconciliation, promotion lifecycle, and work-memory correction tests: 74 passed in 0.23s; correction 9ad950ff-e4bd-5c7f-85d5-183efa6b5cf6 verified and blocker blk-822f5912321b9e00df07c17c closed.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
