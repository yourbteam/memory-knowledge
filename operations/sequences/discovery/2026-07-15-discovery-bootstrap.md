# Sequence Discovery Log: Discovery Bootstrap
ReadyAtUtc: 2026-07-15T17:30:35Z

DiscoveryId: discovery-1cd9d4cf-c214-58b4-b5a7-022f51a2d344
Status: promoted
PromotedSequenceId: discovery-bootstrap
CreatedAtUtc: 2026-07-15T17:30:00Z
RegisteredSequenceMatch: none

## Intended Outcome

Create the complete missing-sequence discovery bundle, bind receipts to that exact bundle, activate it, and start its first governed run through one fail-closed command.

## Why This Looks Repeatable

Every previously unknown operational sequence needs the same governed discovery bootstrap before its first command can run.

## Required Inputs, Auth, Or Environment

- A version-1 bootstrap spec containing the task identity, operation kind, fixed date, intended outcome, repeatability reason, complete initial command rows, and dependencies.
- A fresh directive-read state for the canonical memory-knowledge directives.
- An optional repository-roots mapping when the discovery references another repository.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| bootstrap-discovery | python3 scripts/discovery_bootstrap.py start --spec <spec-json> | required | Validate first; create the complete document and manifest before receipts; select and activate only that exact bundle; start one deterministic run. |
| bootstrap-cross-repository | python3 scripts/discovery_bootstrap.py start --spec <spec-json> --repo-roots-file <repo-roots-file> | required | Use when any dependency belongs to another repository. |
| verify-automation | scripts/run_pytest.sh tests/test_discovery_bootstrap.py tests/test_sequence_discovery_log.py tests/test_work_memory.py tests/test_sequence_guard.py tests/test_discovery_promotion_lifecycle.py tests/test_install_skills.py | passed | Prove strict validation, atomic retry/recovery, legacy compatibility, receipt and guard contracts, lifecycle promotion, and live skill installation behavior. |

## Failure Handling

- Validation and pre-existing-state conflicts fail before overwriting any artifact.
- Before a matching `run_started` ledger event exists, rollback removes only paths created by the current invocation.
- After ledger commit, retry the identical spec; deterministic run and event identities recover the committed run instead of creating another.
- A different request targeting the same discovery or task fails closed and must use a different fixed task id or dated discovery path.

## Verified Path

- The focused controller and compatibility suite passes through `scripts/run_pytest.sh`, which uses the repository virtual environment and writable temporary caches.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
