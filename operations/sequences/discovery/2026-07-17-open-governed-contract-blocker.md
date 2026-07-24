# Sequence Discovery Log: open-governed-contract-blocker

DiscoveryId: discovery-b6beb14e-0f13-511f-b8fa-7f14fbc56642
Status: discovery
CreatedAtUtc: 2026-07-17T20:29:18Z
BootstrapRequestSha256: 3a085b815ebe9ea4fc720b06e4703c31a5ad04c23682a9ccadc79e23894b8f9f
RegisteredSequenceMatch: none

## Intended Outcome

Open a confirmed contract-boundary blocker in the canonical work-memory ledger after the controller has created the governed run.

## Why This Looks Repeatable

Any implementation or convergence run can discover a stable contract blocker that must be durably cataloged before correction.

## Required Inputs, Auth, Or Environment

- A confirmed non-secret error signature, symptom, evidence, impact, stable boundary, subject id, step id, and surface.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| open-contract-blocker | python3 scripts/blocker_catalog.py open --run-id <run-id> --subject-id <subject-id> --step-id <step-id> --surface <surface> --error-signature <error-signature> --symptom <symptom> --evidence <evidence> --impact <impact> --boundary <boundary> | The command returns canonical blocker, occurrence, and event identities and regenerates the blocker view. | Use only non-secret evidence and retain every returned identity for correction and same-path verification. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

If the catalog rejects the run or payload, stop and correct the governed lifecycle or typed input; do not write the generated Markdown view manually.

## Verified Path

- The blocker-open event exists in the canonical ledger and the generated blocker view names the same blocker as open.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
