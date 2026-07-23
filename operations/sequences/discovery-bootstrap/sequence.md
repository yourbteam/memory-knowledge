# discovery-bootstrap

<!-- BEGIN SEMANTIC INTAKE ENTRYPOINT -->
## Operator entry point

After selecting and activating this registered sequence, launch the shared controller with no
arguments:

```bash
python3 scripts/sequence_intake_launch.py
```

Answer only the semantic questions shown. Every question includes its response format, an example,
and constraints. The controller derives JSON, files, environment, flags, and argv; displays the
exact prepared operation; and requires a separate yes/no authorization before guarded dispatch.

Any argument-bearing commands below are machine-compatibility and verification evidence for the
deterministic adapter. Operators and agents must not construct or invoke those forms directly.
<!-- END SEMANTIC INTAKE ENTRYPOINT -->

## Use When

Create and activate a missing-sequence discovery from one validated spec without stale-bundle bootstrap churn

## Outcome

Create the complete missing-sequence discovery bundle, bind receipts to that exact bundle, activate it, and start its first governed run through one fail-closed command.

## Required Inputs

- A version-1 bootstrap spec containing the task identity, operation kind, fixed date, intended outcome, repeatability reason, complete initial command rows, and dependencies.
- A fresh directive-read state for the canonical memory-knowledge directives.
- An optional repository-roots mapping when the discovery references another repository.

## Commands

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

## Verification

- The focused controller and compatibility suite passes through `scripts/run_pytest.sh`, which uses the repository virtual environment and writable temporary caches.

Pass signal: Controller returns ok:true with one discovery, matching bundle/receipt hashes, and one started run

Promoted from `2026-07-15-discovery-bootstrap`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
