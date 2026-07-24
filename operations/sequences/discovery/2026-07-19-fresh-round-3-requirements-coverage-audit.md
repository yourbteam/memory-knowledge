# Sequence Discovery Log: Fresh round-3 requirements coverage audit

DiscoveryId: discovery-08c49c5b-540f-5e85-827c-95ce006f7dba
Status: discovery
CreatedAtUtc: 2026-07-19T13:35:01Z
BootstrapRequestSha256: 86855ec929e6f179d016bcf33ccdc8b26069af639aef77e95a9ac45230af8a34
RegisteredSequenceMatch: none

## Intended Outcome

Read only the authorized round-3 candidate, envelope, immutable research-v3 charter/requirements, and authoritative evidence; verify hashes and assess coverage of all mapped duties and observables.

## Why This Looks Repeatable

The governed classifier requires provenance for this multi-step read-only evidence audit.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| locate-authorized-inputs | rg --files | Authorized input paths are located without reading excluded prior-round contents. | Filter path names in command output; do not open prior rounds, lenses, adjudication, conversation, or edits. |
| verify-authorized-hash | shasum -a 256 <path> | Candidate and envelope hashes match the controller-provided canonical hashes. | Run once per authorized JSON path. |
| read-authorized-input | sed -n '1,100000p' <path> | Each authorized input is read completely. | Use only candidate round 3, envelope round 3, immutable research-v3 charter/requirements, and authoritative evidence. |
| inspect-json-structure | jq 'keys' <path> | Authorized JSON structure is enumerated for deterministic mapping checks. | Use only candidate round 3 or envelope round 3. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop on hash mismatch or missing authorized source; do not substitute prior-round or conversation evidence.

## Verified Path

- Exact canonical hash verification followed by complete authorized-source reads and independent 129-duty coverage mapping.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
