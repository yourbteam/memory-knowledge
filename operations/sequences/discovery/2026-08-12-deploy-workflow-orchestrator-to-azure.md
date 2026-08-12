# Sequence Discovery Log: Deploy Workflow Orchestrator to Azure

DiscoveryId: discovery-c5f31dd8-5d19-5d81-bf41-0203aa79ca86
Status: discovery
CreatedAtUtc: 2026-08-12T09:30:44Z
BootstrapRequestSha256: 13c29975115df81e60115b1ef7e933f400a0575ff24e307646133cea57204003
RegisteredSequenceMatch: none

## Intended Outcome

Build the approved committed Workflow Orchestrator revision, update the idle production Web App to its immutable image, restart it, and verify healthy service.

## Why This Looks Repeatable

The guarded production build, image update, restart, and verification recur for every approved Workflow Orchestrator release.

## Required Inputs, Auth, Or Environment

- The full approved Git commit identifier for the current Workflow Orchestrator checkout.
- An authenticated Azure CLI session with access to the registered production resource group, registry, storage account, and Web App.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| deploy-production | python3 scripts/workflow_orch_azure_deploy.py | The authorized immutable image is deployed only while idle and production health passes afterward. | The launcher pins the approved commit, requires explicit effect authorization, and checks idle both before dispatch and immediately before image mutation. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop before any production mutation when the revision, authorization, health shape, idle state, Azure build, image update, restart, or final health verification fails.

## Verified Path

- The zero-input launcher passes focused tests, then a live run proves both idle gates, immutable image deployment, restart, and post-deployment production health.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
