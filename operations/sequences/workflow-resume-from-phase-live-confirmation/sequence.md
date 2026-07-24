# workflow-resume-from-phase-live-confirmation

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

A persisted United Partners workflow must continue from its exact first unfinished phase while preserving completed phase state and streaming the structured live watcher feed.

## Outcome

Resume a persisted United Partners workflow from its first unfinished phase, preserve completed phase state, stream the structured watcher feed, and end at completion or the first persisted deviation.

## Required Inputs

- A persisted non-completed United Partners workflow run.
- The exact first unfinished phase id reported by that run.
- A client key whose configured workflow matches the source run.
- The managed Python runtime and command-backed role adapter for live execution.
- Write authority for the client's persisted state directory.

## Commands

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| preflight-resume-driver | env PYTHONPATH=src /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_client_regeneration.py --help | The driver exposes --resume-run and --from-phase together. | Run in the united-partners repository with the existing managed Python runtime. |
| resume-from-first-unfinished-phase | env PYTHONPATH=src 'UP_HARNESS_AGENT_COMMAND=/Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/codex_role_command.py' UP_HARNESS_AGENT_MAX_ATTEMPTS=3 UP_HARNESS_AGENT_TIMEOUT_SECONDS=600 UP_HARNESS_CODEX_TIMEOUT_SECONDS=600 /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_client_regeneration.py --client <client> --resume-run <persisted-run-id> --from-phase <first-unfinished-phase> | A new child preserves every completed source phase, starts at the named first unfinished phase, streams watcher activity, and reaches completion or one persisted diagnosable deviation. | The driver validates the workflow identity and boundary before model work and launches scripts/watch_run.py automatically. |
| verify-automation | env -C /Users/kamenkamenov/united-partners PYTHONPATH=src /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests.unit.test_workflow_resume tests.unit.test_client_regeneration_resume -v | The resume boundary and observed client-regeneration entry point pass their deterministic regression suites. | The command binds its own united-partners working directory; no model call is made. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Fail before model work when the source is completed, belongs to another workflow, the phase is unknown, the phase is not the first unfinished boundary, downstream state already exists, or the watcher cannot bind the emitted child identity. During execution, retain the child state and stop at the first persisted deviation; catalog and correct that stable boundary before another live successor.

## Verification

- Three real executions used the same driver: phase-20 resume from up-run-96aecc52ba4d, corrected phase-20 resume from up-run-bca4c0d9a7bf, and phase-33 resume from up-run-78d991b5036c. The deterministic resume suites provide the repeatable promotion check; a registered phase-33 successor supplies current live confirmation.

Pass signal: A new child preserves all completed source phases, begins at the requested first unfinished phase, and reaches completion or one persisted diagnosable deviation while watcher telemetry remains active.

Promoted from `2026-07-20-workflow-resume-from-phase-live-confirmation`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
