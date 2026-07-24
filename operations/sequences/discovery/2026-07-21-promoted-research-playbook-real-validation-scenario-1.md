# Sequence Discovery Log: Promoted Research Playbook real validation Scenario 1

DiscoveryId: discovery-e6b0b303-96b8-5b86-a7d1-821a5c4f11d3
Status: discovery
CreatedAtUtc: 2026-07-21T06:07:52Z
BootstrapRequestSha256: 69d517fbdf6338532a550599913f25fadaf5b94151699484bd4632cbbcc70ee9
RegisteredSequenceMatch: none

## Intended Outcome

Drive one real agentic-trading research assignment through the promoted Research Playbook, validate its package, and prove unchanged Planner consumption without evaluator fixtures.

## Why This Looks Repeatable

This is the first scenario in an approved three-scenario acceptance campaign for the promoted Research Playbook.

## Required Inputs, Auth, Or Environment

- Current agentic-trading source, tests, repository configuration, frozen charter, and requirements.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| initialize-research-state | python3 /Users/kamenkamenov/memory-knowledge/skills/research-playbook/scripts/research_package.py init /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/state.json --charter /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/charter.json --requirements /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/requirements.json --operational-maturity MIXED --evidence-availability /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/evidence-availability.json | A frozen canonical research state is initialized. | No evaluator fixture or prior task artifact is used. |
| record-candidate | python3 /Users/kamenkamenov/memory-knowledge/skills/research-playbook/scripts/research_package.py record-candidate /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/state.json --candidate <candidate-path> --envelope /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/core-envelope.json --evidence-availability /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/evidence-availability.json | The real core-research candidate and frozen input envelope are hash-bound. | Candidate path is produced by the independent core researcher. |
| record-role-attempt | python3 /Users/kamenkamenov/memory-knowledge/skills/research-playbook/scripts/research_package.py record-attempt /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/state.json --runtime-agent-id <agent-id> --role <role> --round <round> --candidate-hash <candidate-hash> --input-envelope-hash <envelope-hash> --status SUCCEEDED --output-hash <output-hash> --slot-closed --close-evidence <close-evidence-path> | The role attempt is recorded with output and close evidence. | Run once for each mandatory role. |
| record-lens | python3 /Users/kamenkamenov/memory-knowledge/skills/research-playbook/scripts/research_package.py record-lens /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/state.json --round <round> --lens <lens> --runtime-agent-id <agent-id> --candidate-hash <candidate-hash> --envelope-hash <envelope-hash> --terminal-envelope <lens-output-path> | One unchanged independent lens terminal envelope is recorded. | Run for all three promoted hardening lenses. |
| record-adjudication | python3 /Users/kamenkamenov/memory-knowledge/skills/research-playbook/scripts/research_package.py record-adjudication /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/state.json --round <round> --runtime-agent-id <agent-id> --candidate-hash <candidate-hash> --envelope-hash <envelope-hash> --adjudications <adjudication-path> | Raw lens findings receive independent dispositions. | Any FIX_IN_RESEARCH disposition requires a full fresh round. |
| emit-research-package | python3 /Users/kamenkamenov/memory-knowledge/skills/research-playbook/scripts/research_package.py emit-package /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/state.json /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/research-package --research <research-path> --evidence-index <evidence-index-path> --planner-readiness <planner-readiness-path> --planner-handoff <planner-handoff-path> | Exactly six package files are emitted after a terminal PASS. | Emission is forbidden for GAPS, BLOCKED, or CAP_REACHED. |
| validate-research-package | python3 /Users/kamenkamenov/memory-knowledge/skills/research-playbook/scripts/research_package.py validate-package /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/research-package | The emitted package validates without mutation. | This closes the Research Playbook portion before Planner ingestion. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop on the first controller or role-contract failure, preserve the exact failing artifact, catalog the blocker, and fix only its confirmed stable owning boundary before same-scenario re-entry.

## Verified Path

- Independent runtime subagents plus the promoted Research Playbook controller operate on the real agentic-trading repository and package; no evaluator fixture is the validation driver.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
