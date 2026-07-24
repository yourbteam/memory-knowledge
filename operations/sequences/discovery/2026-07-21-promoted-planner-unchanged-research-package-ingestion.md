# Sequence Discovery Log: Promoted Planner unchanged Research-package ingestion

DiscoveryId: discovery-e4c5ff56-41f6-5482-97ab-7de2166e4a7e
Status: discovery
CreatedAtUtc: 2026-07-21T07:01:13Z
BootstrapRequestSha256: 8b0c181f92db439270447afb6e1b2303454607aa4c6027b26efa85feba41631a
RegisteredSequenceMatch: none

## Intended Outcome

Consume the validated Scenario 1 Research package unchanged through the promoted Planner and emit a canonical decision-complete plan package.

## Why This Looks Repeatable

Every Research Playbook real-validation scenario must prove unchanged downstream Planner consumption.

## Required Inputs, Auth, Or Environment

- The validated six-file Scenario 1 Research package and planner charter.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| restore-nested-verification-ledger-asset | cp <source-path> <destination-path> | The named nested historical plan asset is restored at the exact relative path referenced by verification-ledger.json. | Run only after prepare-nested-ledger-asset-parent; source is the controller ledger snapshot's exact nested proposed-revision plan, destination is the matching task-root relative path, and no surrounding directory is copied. |
| prepare-nested-ledger-asset-parent | mkdir -p <task-root>/Tasks/<task>/.plan-playbook/proposed-revisions/<revision> | The exact nested asset destination exists before the named file copy. | Run this before restoring any nested proposed-revision plan; the restore remains narrow and never recursively copies the snapshot root. |
| restore-verification-ledger-assets | cp <snapshot-root>/verification-ledger.json <task-root>/verification-ledger.json | Restore the ledger and each referenced plan/critic asset by its exact relative path. | The snapshot root is inside the task root: never copy snapshot-root/. recursively into task-root. Copy verification-ledger.json, plan.md, Tasks/<task>/plan.md, and named .verify-plan/critic-outputs files individually. |
| bind-recovery-plan-agent-slot | python3 skills/_shared/agent_slot_ledger.py bind-agent /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1-recovery/hardening-slots.json --slot-id <slot-id> --agent-id <agent-id> | Bind a recovery-run assessment agent to its exact reserved slot. | Recovery hardening uses the isolated -recovery task root; substitute only the concrete slot and agent ids. |
| initialize-plan-from-research-package | python3 /Users/kamenkamenov/memory-knowledge/skills/plan-playbook/scripts/plan_package.py init /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/.plan-playbook/state.json --task-directory /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1 --charter /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/planner-charter.json --entry-mode RESEARCH_PACKAGE --task-size standard --approval-context ORDINARY --research-package /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/research-package | The canonical Planner validates and snapshots the unchanged Research package and initializes a SUBSTANTIAL run. | No manual requirements or evidence rewrite is supplied. |
| show-plan-state | python3 /Users/kamenkamenov/memory-knowledge/skills/plan-playbook/scripts/plan_package.py show /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/.plan-playbook/state.json | The persisted Planner state reopens and validates. | The supplied_input_root must bind the emitted Research package. |
| record-verification-ledger | python3 /Users/kamenkamenov/memory-knowledge/skills/plan-playbook/scripts/plan_package.py record-verification-ledger <absolute-state-path> --ledger <absolute-ledger-path> --expected-current-sha256 <current-ledger-sha256> | The controller snapshots the valid ledger and its contained assets. | Both state and ledger paths must be absolute; a relative ledger path makes the controller's asset authority root relative and returns `UNSAFE_PATH`. |
| project-verify-plan-ledger | python3 /Users/kamenkamenov/memory-knowledge/skills/plan-playbook/scripts/plan_package.py project-verify-plan-ledger <absolute-state-path> --ledger <absolute-ledger-path> --verifier-output <verifier-output> --critic-output <critic-output> --out <absolute-ledger-path> | The controller validates the successful pair and projects pre-critic findings into the shared ledger's post-critic identities. | Use this before `record-verification-ledger`; do not manually reconstruct finding or assessment fingerprints. |
| acquire-plan-agent-slot | python3 /Users/kamenkamenov/.codex/skills/_shared/agent_slot_ledger.py acquire /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/hardening-slots.json --label <stage-label> | Reserve one fresh assessment-only agent slot. | Capture the returned slot id; never mutate by reusable label afterward. |
| bind-plan-agent-slot | python3 /Users/kamenkamenov/.codex/skills/_shared/agent_slot_ledger.py bind-agent /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/hardening-slots.json --slot-id <slot-id> --agent-id <agent-id> | Bind the reserved slot to the exact runtime agent. | Run immediately after spawn. |
| complete-plan-agent-slot | python3 /Users/kamenkamenov/.codex/skills/_shared/agent_slot_ledger.py mark-completed /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/hardening-slots.json --slot-id <slot-id> | Record complete output collection. | Run only after the full agent result is captured. |
| close-plan-agent-slot | python3 /Users/kamenkamenov/.codex/skills/_shared/agent_slot_ledger.py mark-closed /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/hardening-slots.json --slot-id <slot-id> --close-evidence <close-evidence> | Record the runtime close result. | The evidence is the exact status returned by `close_agent`. |
| release-plan-agent-slot | python3 /Users/kamenkamenov/.codex/skills/_shared/agent_slot_ledger.py release /Users/kamenkamenov/agentic-trading/Tasks/research-playbook-real-validation-s1/hardening-slots.json --slot-id <slot-id> | Return the closed slot to zero-active state. | Required before the next role or round boundary. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop on the first Planner controller or role-contract failure, preserve exact evidence, catalog the blocker, and repair only the confirmed owning boundary.

## Verified Path

- The promoted Planner controller consumes the emitted Research package directory directly with entry mode RESEARCH_PACKAGE.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
