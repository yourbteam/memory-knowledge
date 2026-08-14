# Sequence Discovery Log: Info intake real dashboard canary

DiscoveryId: discovery-3d2f9b01-7d10-5cbf-9319-94598d025383
Status: discovery
CreatedAtUtc: 2026-08-14T05:45:53Z
BootstrapRequestSha256: 1b71f2360fd9199f009970172520ccf81dbd45a3954fda9f727892a3051a100a
RegisteredSequenceMatch: none

## Intended Outcome

Transform the supplied dashboard sources into complete AI-readable projections with immutable-source ledger coverage and a grounded first-layer terminal.

## Why This Looks Repeatable

Operators will repeatedly start new intakes from one or more mixed source types that require the same governed projection workflow.

## Required Inputs, Auth, Or Environment

- An operator decision to start a new intake or resume an existing intake.
- The intake work directory where immutable state and ledger artifacts will be stored.
- Whether this invocation should continue to the next external boundary or stop after a positive number of completed visual regions.
- The operator's exact opening words.
- The operator's plain-language purpose for what must become AI-readable.
- The first operator-supplied source as one existing local file or one public URL.
- Any later text, local file, or public URL requested by a code-controlled clarification question.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| run-info-intake-canary | uv run python skills/info-intake-machinery/scripts/run_intake.py | grounded first-layer terminal or code-declared bounded region pause | The repository-managed Python environment supplies the declared projection dependencies. Code conducts every operator and model answer through typed boundaries, counts only persisted region outcomes, and fails closed before an ungrounded projection, pause, or terminal. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop at the first invalid, changed, missing, or unsupported boundary while preserving the immutable sources, rejected answers, ledger lineage, and exact failure evidence.

## Verified Path

- Run the zero-input launcher on a fresh real intake and verify its final terminal is first_layer_complete, every source has a ledgered projection outcome, and the ledger hash chain and immutable artifacts validate unchanged.
- For a bounded canary, select `region_limit`, supply a positive region count, verify the launcher pauses only after that many new immutable `region_outcome_recorded` events, then resume through the same zero-input launcher.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
