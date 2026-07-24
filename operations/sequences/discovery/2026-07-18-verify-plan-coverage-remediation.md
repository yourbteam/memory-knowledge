# Sequence Discovery Log: verify-plan-coverage-remediation

DiscoveryId: discovery-8fa1b6d2-203f-5ef6-ab78-cb4152e12935
Status: discovery
CreatedAtUtc: 2026-07-17T22:29:15Z
BootstrapRequestSha256: 980aa712a0fc535ebd491416e619b522d98f59278e0894c8e6265b90ba8b39e0
RegisteredSequenceMatch: none

## Intended Outcome

Identify and repair the verify-plan contract defect that permits repeated broad misses in already-checked coverage, then prove the corrected verifier on the blocked Plan Playbook V2 revision.

## Why This Looks Repeatable

Verifier coverage failures can recur on future plan-hardening runs and must be diagnosed, corrected, and same-path verified through a stable sequence.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| inspect-verifier-contract | rg -n -C 4 <pattern> skills/verify-plan/SKILL.md skills/verify-plan/scripts/verification_ledger.py | The producer, verifier, critic, ledger, and stop contracts governing coverage are traced. | Read-only diagnosis; no edits. |
| inspect-failure-evidence | jq <filter> Tasks/plan-playbook-assessment-v2/plan-verification-ledger.json | The exact pattern of checked surfaces, repeated missed findings, and state transitions is extracted. | Read-only diagnosis against the blocked run evidence. |
| run-root-cause-assessor | multi_agent_v1.spawn_agent verify-plan-coverage-root-cause | An independent assessment-only agent traces symptom, immediate cause, deeper cause, and stable fix boundary. | The parent retains edit authority and closes the agent after collecting evidence. |
| write-remediation-findings | apply_patch <research-findings-patch> | A bounded research artifact records confirmed cause-chain evidence and rejects speculative fixes. | No skill or runtime implementation changes. |
| run-findings-verifier | multi_agent_v1.spawn_agent verify-plan-coverage-findings | A fresh independent assessor confirms or rejects the root-cause findings against the same evidence. | Assessment-only. |
| write-remediation-plan | apply_patch <remediation-plan-patch> | A granular root-fix plan names each contract, helper, and test change with its reason. | Implementation remains approval-gated. |
| run-remediation-plan-verifier | multi_agent_v1.spawn_agent verify-plan-coverage-remediation-plan | A fresh assessor checks that the plan closes the confirmed cause without widening scope. | Assessment-only. |
| implement-approved-remediation | apply_patch <approved-remediation-patch> | Only the user-approved verifier-contract and focused-test changes are applied. | Requires granular G11 approval before execution. |
| run-focused-remediation-tests | scripts/run_pytest.sh <focused-test-paths> | Focused deterministic tests prove red-before and green-after behavior at the verifier contract boundary. | Use repository test wrapper only. |
| run-same-path-verifier | multi_agent_v1.spawn_agent verify-plan-envelope | The corrected verifier is exercised against the blocked Plan Playbook V2 plan and complete C01-C14 evidence. | Derive plan, inventory, and evidence identities directly from the active ledger at launch; never carry an identity from a summary or prior prompt. One same-path confirmation, followed by the ordinary downstream gates only if PASS. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| record-current-bundle-supersession | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id bind-current-verifier-remediation-bundle --changed-artifact operations/sequences/discovery/2026-07-18-verify-plan-coverage-remediation.md --supersedes-correction-id 95b2539a-557e-4195-90ad-7cabd963408e --solution <solution> --reusable-behavior-changed yes | The repaired controller is rebound to the current verifier-remediation bundle and the obsolete removed-artifact correction is explicitly superseded. | Preserves the rule that removed artifacts cannot be carried across later bundle hashes. |
| record-protected-correction-three-artifacts | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --changed-artifact <path> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when protected selected-bundle drift spans exactly three artifacts | Declare the complete drift set so the corrected successor binds every changed source without attributing unrelated drift to the fix. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Catalog every new failure before correction. A reusable-boundary edit records a correction, closes the predecessor failed, and requires a fresh correction-bound successor for same-path verification.

## Verified Path

- Independent root-cause confirmation, approved bounded implementation, focused red-before/green-after tests, and one same-path verifier run that no longer produces broad misses from already-checked coverage.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
