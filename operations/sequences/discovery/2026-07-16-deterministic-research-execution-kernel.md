# Sequence Discovery Log: deterministic research execution kernel

DiscoveryId: discovery-08d700a5-f04c-5ea7-b227-2d5718437f6b
Status: discovery
CreatedAtUtc: 2026-07-16T21:01:32Z
BootstrapRequestSha256: 19acb216b495df004ff070cc78fc5443b5c22f7395d8bc3ca959ce0addc0a9b0
RegisteredSequenceMatch: none

## Intended Outcome

Run the complete research-playbook lifecycle through one typed, resumable, fail-closed controller without model-authored JSON patching or reconstructed command chains.

## Why This Looks Repeatable

Every implementation-bound research task repeats initialization, candidate registration, fixes, gates, adjudication, budget checks, resume, and terminal emission.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| bind-research-agent | python3 skills/_shared/agent_slot_ledger.py bind-agent /Users/kamenkamenov/mcp-agents-workflow/Tasks/deterministic-research-execution-kernel/agent-slots.json --slot-id <slot-id> --agent-id <agent-id> | Runtime agent is bound to its exact acquired slot. | Shape recorded before any agent acquisition. |
| mark-research-agent-completed | python3 skills/_shared/agent_slot_ledger.py mark-completed /Users/kamenkamenov/mcp-agents-workflow/Tasks/deterministic-research-execution-kernel/agent-slots.json --slot-id <slot-id> | Completed output is durably recorded for the exact slot. | Use after collecting full output. |
| mark-research-agent-closed | python3 skills/_shared/agent_slot_ledger.py mark-closed /Users/kamenkamenov/mcp-agents-workflow/Tasks/deterministic-research-execution-kernel/agent-slots.json --slot-id <slot-id> --close-evidence <previous-status> | Runtime close evidence is durably recorded. | Use only after runtime close. |
| release-research-agent | python3 skills/_shared/agent_slot_ledger.py release /Users/kamenkamenov/mcp-agents-workflow/Tasks/deterministic-research-execution-kernel/agent-slots.json --slot-id <slot-id> | The exact closed slot is released. | Use after mark-closed. |
| inspect-controller-contract | python3 skills/research-playbook/scripts/research_package.py --help | The authoritative current controller command surface is available. | Read-only preflight against the existing controller. |
| verify-current-boundary | scripts/run_pytest.sh tests/test_research_playbook_v2.py tests/test_sequence_observer.py tests/test_sequence_observer_end_to_end.py | The current controller and observer baseline passes before changes. | Uses the repository test launcher. |
| verify-deterministic-kernel | scripts/run_pytest.sh tests/test_research_run.py tests/test_research_playbook_v2.py tests/test_sequence_observer.py tests/test_sequence_observer_end_to_end.py | Typed transitions, correction blocking, budget admission, resume, metrics, and end-to-end behavior pass. | Final bounded verification surface. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Fail before mutation on request or schema errors; persist completed transitions for idempotent resume; reject known failed action shapes and infeasible rounds; never fall back to raw JSON or textual patching.

## Verified Path

- One request drives a fixture research run, survives interruption, applies a typed correction, prevents a known failed action shape, and reaches a validated terminal result without manual artifact edits.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
