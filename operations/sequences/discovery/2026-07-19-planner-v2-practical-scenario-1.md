# Sequence Discovery Log: Planner V2 Practical Scenario 1

DiscoveryId: discovery-e93efad8-f94a-5b35-8587-c2e517b14eb6
Status: discovery
CreatedAtUtc: 2026-07-19T15:28:29Z
BootstrapRequestSha256: 77c1515c147d8c39a58742ce3a3fff89a11f88ad520f97c8be8ce52522a70f3a
RegisteredSequenceMatch: none

## Intended Outcome

Prove whether Planner v2 can produce a plan that an independent implementer uses to complete one real bounded repository change without hidden context or manual rescue.

## Why This Looks Repeatable

Each Planner v2 behavioral scenario uses the same plan, independent implementation, real verification, correction, and clean rerun loop.

## Required Inputs, Auth, Or Environment

- The checked-out memory-knowledge repository and its current Planner v2 candidate.
- The checked-out agentic-trading repository as the real scenario target.
- One frozen bounded task selected from repository evidence before Planner v2 runs.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| inspect-real-candidates | rg -n TODO . | Identify bounded unresolved behaviors from the real repository rather than inventing a synthetic task. | Exclude generated, dependency, secret, and unrelated dirty surfaces from candidate selection. |
| capture-baseline | git status --short | Record the pre-scenario working-tree boundary so existing work is preserved. | The scenario may not revert or absorb unrelated changes. |
| run-planner-v2 | python3 scripts/evaluate_plan_playbook_v2.py show --run <run-dir> | Produce and retain one Planner v2 plan from the frozen real request and visible repository evidence. | Do not manually rescue or supplement the planner output before implementation. |
| independent-implementation | git diff --check | An independent implementer changes only the approved scenario surface using the plan and repository evidence. | Clarification requests and hidden-context dependencies are scenario failures and must be recorded. |
| real-verification | scripts/run_pytest.sh <test-path> | The repository-native focused behavior test passes on the implementation produced from the plan. | Observed planner failures become targeted behavioral corrections, not abstract score adjustments. |
| scenario-review | git diff --check | Independent review confirms the implementation satisfies every frozen acceptance criterion without out-of-scope work. | Rerun the same scenario cleanly after any Planner v2 correction before declaring it closed. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop at the first practical failure, catalog the observed symptom and evidence, correct the Planner v2 boundary that caused it, then rerun the same scenario from a clean isolated implementation state.

## Verified Path

- Scenario passes only when an independent implementer can build the requested behavior from the Planner v2 plan and the real repository verification plus independent review both pass.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
