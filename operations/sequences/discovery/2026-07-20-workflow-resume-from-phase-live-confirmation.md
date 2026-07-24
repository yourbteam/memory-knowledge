# Sequence Discovery Log: Workflow Resume From Phase Live Confirmation
ReadyAtUtc: 2026-07-20T15:21:36Z

DiscoveryId: discovery-9c0393de-2d1b-5744-8e85-2f519d56edea
Status: promoted
PromotedSequenceId: workflow-resume-from-phase-live-confirmation
CreatedAtUtc: 2026-07-20T14:59:38Z
BootstrapRequestSha256: c7f05b6d8d8d1840332f353f588ae48221a3bb36f61900586b25e7f48659593b
RegisteredSequenceMatch: none

## Intended Outcome

Resume a persisted United Partners workflow from its first unfinished phase, preserve completed phase state, stream the structured watcher feed, and end at completion or the first persisted deviation.

## Why This Looks Repeatable

The same checked-in resume driver and watcher path has already been used for three live continuations at phase 20 and phase 33, and future phase corrections need the same bounded confirmation without replaying completed phases.

## Required Inputs, Auth, Or Environment

- A persisted non-completed United Partners workflow run.
- The exact first unfinished phase id reported by that run.
- A client key whose configured workflow matches the source run.
- The managed Python runtime and command-backed role adapter for live execution.
- Write authority for the client's persisted state directory.

## Commands And Observations

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

## Verified Path

- Three real executions used the same driver: phase-20 resume from up-run-96aecc52ba4d, corrected phase-20 resume from up-run-bca4c0d9a7bf, and phase-33 resume from up-run-78d991b5036c. The deterministic resume suites provide the repeatable promotion check; a registered phase-33 successor supplies current live confirmation.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
