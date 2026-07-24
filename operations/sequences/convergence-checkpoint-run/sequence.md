# convergence-checkpoint-run

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

Apply a convergence baseline checkpoint, then dispatch one typed, content-addressed child owner through the prevention controller; serialize only the shared ledger/view pair and fail on any other drift.

## Outcome

Resume-safe checkpoint application followed by exactly one typed child owner terminal artifact and one parent terminal artifact.

## Required Inputs

- A convergence state file whose memory-knowledge baseline already allows the canonical ledger and blocker view.
- An approval id authorizing accept-baseline for operations/work-memory/events.jsonl and operations/blockers/BLOCKERS.md.
- A typed child intent bound to an executable owner contract, validated parameters, guard receipt, and complete child UnitBudget.
- The canonical memory-knowledge repository root and installed convergence_state.py helper.

## Commands

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| checkpoint-source | python3 scripts/convergence_checkpoint_run.py --state <state-file> --repo <memory-knowledge-root> --approval-id <approval-id> --child-intent-json <canonical-json> | structured CHECKPOINT_APPLIED envelope | This source applies only the checkpoint. It never executes child argv or claims parent terminal success. |
| typed-child | prevention controller child composition | one semantic child terminal artifact linked to the parent | The controller derives child implementation, compatibility, parameters, budget, and dispatch from the frozen child owner contract. |
| verify-automation | scripts/run_pytest.sh tests/test_convergence_checkpoint_run.py tests/prevention/test_owner_runtime.py tests/prevention/test_full_unit_admission.py | passed | Proves serialization, typed-child rejection, crash resume, composed admission, and semantic parent terminalization. |

## Failure Handling

Stop before checkpoint mutation on invalid inputs, incomplete child contract/budget, lock timeout, approval rejection, unrelated drift, or guard failure. After an applied checkpoint, resume only the same typed child; never accept the baseline again for that effect.

## Verification

- The source test uses a real fcntl writer race and proves that no caller argv is accepted or executed.
- Owner acceptance requires one exact child semantic terminal artifact and one parent terminal artifact, including crash-after-checkpoint resume without duplicate checkpoint or child execution.

Pass signal: semantic parent terminal artifact with linked child terminal artifact

Promoted from `2026-07-16-convergence-checkpoint-run`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
