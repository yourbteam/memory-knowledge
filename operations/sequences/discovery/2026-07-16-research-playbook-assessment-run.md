# Sequence Discovery Log: research-playbook-assessment-run

DiscoveryId: discovery-4e9833f6-2fc1-56d1-8c64-0d58ea2f2091
Status: discovery
CreatedAtUtc: 2026-07-16T17:55:08Z
BootstrapRequestSha256: 95670cd2e6c5b598476b39def6a193c4ae2a7942080c657e6e6c2f464e386971
RegisteredSequenceMatch: none

## Intended Outcome

Produce a controller-validated six-file research package assessing whether plan-playbook supports grounded one-shot implementation planning.

## Why This Looks Repeatable

The upgraded research playbook will be reused to assess other workflow skills through the same charter, independent-agent, lens, adjudication, and package-emission lifecycle.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| freeze-charter | python3 skills/research-playbook/scripts/research_package.py init <state> --charter <charter> --requirements <requirements> --operational-maturity CURRENT_RUNTIME --evidence-availability <evidence-availability> | Immutable charter and atomic requirements recorded. | No post-freeze scope or maturity changes are allowed. |
| run-core-research | multi_agent_v1.spawn_agent <core-research-envelope> | Fresh assessment-only core researcher returns one structured candidate. | The parent retains all artifact writes and lifecycle evidence. |
| record-candidate | python3 skills/research-playbook/scripts/research_package.py record-candidate <state> --candidate <candidate> --envelope <envelope> | Candidate and common-envelope canonical hashes recorded. | Record the closed core-agent attempt against the same hashes. |
| run-three-lenses | multi_agent_v1.spawn_agent <identical-envelope-plus-role-specific-lens> | Three fresh independent lens agents return exact terminal envelopes. | Spawn concurrently and prevent cross-lens visibility. |
| record-lenses | python3 skills/research-playbook/scripts/research_package.py record-lens <state> --round <round> --lens <lens> --runtime-agent-id <agent-id> --candidate-hash <candidate-hash> --envelope-hash <envelope-hash> --terminal-envelope <terminal-envelope> | All three lens envelopes and closed attempts recorded. | Every candidate material-gap ID must appear in at least one lens finding. |
| adjudicate | multi_agent_v1.spawn_agent <adjudication-envelope> | Fresh independent adjudicator classifies every raw finding. | The adjudicator proposes dispositions and never edits the candidate. |
| record-adjudication | python3 skills/research-playbook/scripts/research_package.py record-adjudication <state> --round <round> --runtime-agent-id <agent-id> --candidate-hash <candidate-hash> --envelope-hash <envelope-hash> --adjudications <adjudications> | Deduplicated finding dispositions and terminal verdict recorded. | Only parent-applied FIX_IN_RESEARCH findings can trigger a fresh full round. |
| emit-and-verify-package | python3 skills/research-playbook/scripts/research_package.py emit-package <state> <output-directory> --research <research-markdown> --evidence-index <evidence-index> --planner-readiness <planner-readiness> --planner-handoff <planner-handoff-markdown> | Controller emits and validates exactly six planner-ready package files. | Close every runtime agent and require zero active slots before completion. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop on malformed agent output, unavailable evidence, scope mutation, lifecycle leakage, or controller rejection; catalog the blocker before retrying and allow at most one retry per role within the shared caps.

## Verified Path

- Controller-valid PASS package, complete agent close evidence, all three lenses PASS on one candidate hash, and final package hashes validate.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
