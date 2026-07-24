# Sequence Discovery Log: independent-plan-critic-evidence-review

DiscoveryId: discovery-38830ded-1106-5bdb-bf84-eca97a4e4a81
Status: discovery
CreatedAtUtc: 2026-07-17T11:40:57Z
BootstrapRequestSha256: 0e7e58e795188a9c6adc7a3d5ef0aba9f412ee0e8c73670696444637d2642b1a
RegisteredSequenceMatch: none

## Intended Outcome

Independently adjudicate a bounded verifier finding set against the current plan and authoritative source evidence, then emit a schema-valid critic JSON.

## Why This Looks Repeatable

Verify-plan critic passes repeatedly inspect a plan, verifier envelope, registry contracts, implementation code, and hashes using the same bounded evidence workflow.

## Required Inputs, Auth, Or Environment

- current plan path and hash
- verifier JSON path and hash
- repository roots and named authoritative evidence
- critic output path

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| inventory evidence files | rg --files <path> | The bounded repository or directory file inventory is visible. | Use only on a task-scoped repository or directory path. |
| read bounded text evidence | sed -n <range> <path> | The requested bounded source lines are visible. | Use exact task evidence paths. |
| read structured evidence | jq <filter> <path> | The requested JSON structure is visible and parseable. | Use exact task evidence paths. |
| locate cited symbols | rg -n <pattern> <path> | Cited symbols and contracts are located with line numbers. | Use exact task evidence paths and bounded patterns. |
| verify artifact hash | shasum -a 256 <path> | The artifact SHA-256 is emitted for comparison. | Run on each supplied or produced artifact. |
| validate critic json | jq . /private/tmp/prevention-plan-critic-i2.json | The final critic artifact parses as JSON. | Validation only; artifact creation remains parent/critic owned. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

If a cited path or symbol is absent, preserve that absence as evidence and classify the verifier claim accordingly; do not invent a substitute. If a command fails mechanically, catalog the blocker before correcting or resuming.

## Verified Path

- All ten verifier findings are independently checked against the current plan and authoritative sources; the output parses and its SHA-256 is reported.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
