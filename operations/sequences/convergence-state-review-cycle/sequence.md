# convergence-state-review-cycle

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

Apply bounded convergence review state operations without manual JSON list encoding.

## Outcome

Apply a bounded convergence review-state operation list without hand-building JSON-array flags, then verify the resulting state.

## Required Inputs

- A schema-version-2 request containing a request id, trusted state path, initial state hash, expected final status, and uniquely identified ordered operations.
- A separate unconsumed authority receipt for every grant-autonomy or grant-scope-change operation.
- The fixed, hash-bound convergence_state.py helper from the executable owner contract.

## Commands

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| apply-review-cycle | python3 scripts/convergence_state_review_cycle.py apply --request <request-v2-json> | cycle_status APPLIED plus exact convergence_status | The source validates the initial hash, trusted repository/path bindings, ordered operation identities, final check, and exact final status. |
| dry-run-review-cycle | python3 scripts/convergence_state_review_cycle.py apply --request <request-json> --dry-run | The complete redacted argv plan is returned without changing convergence state. | Use before applying a new request shape; evidence and impact text are not printed. |
| verify-automation | scripts/run_pytest.sh tests/test_convergence_state_review_cycle.py | passed | Proves JSON-list serialization, preflight rejection, ordered one-shot execution, final checks, and actionable safe failures. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop on request/schema/hash/root/authority failure or the first helper rejection. Resume the identical content-addressed request only from the first operation without a matching semantic receipt; never duplicate a grant, baseline acceptance, stage record, or transition.

## Verification

- Focused tests and owner acceptance prove v2 rejection of legacy/absolute shapes, dry-run immutability, ordered apply, exact final status, semantic-negative rejection, and crash reconciliation.

Pass signal: CONVERGENCE STATE REVIEW CYCLE OK

Promoted from `2026-07-16-convergence-state-review-cycle`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
