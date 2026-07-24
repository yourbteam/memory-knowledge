# Sequence Discovery Log: frozen-research-package-coverage-assessment

DiscoveryId: discovery-a1a129a5-3156-5de8-a17a-8945525886e9
Status: discovery
CreatedAtUtc: 2026-07-17T10:19:29Z
BootstrapRequestSha256: 672452f56ff915078f58acf3d1bf9c94f15e7abb7f9e19f5396f28a225508145
RegisteredSequenceMatch: none

## Intended Outcome

Verify frozen package identities, assess requirements coverage, and validate the exact terminal lens envelope.

## Why This Looks Repeatable

The classified flow has multiple evidence and validation steps that must remain bounded to frozen inputs.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify candidate canonical hash | python3 /Users/kamenkamenov/.codex/skills/research-playbook/scripts/research_package.py hash-json /private/tmp/prevention-successor-core-candidate.json | Canonical JSON hash equals the supplied candidate identity. | Read-only identity check. |
| verify envelope canonical hash | python3 /Users/kamenkamenov/.codex/skills/research-playbook/scripts/research_package.py hash-json /Users/kamenkamenov/memory-knowledge/Tasks/prevention-system-completion/research-v3/work/envelope.json | Canonical JSON hash equals the supplied envelope identity. | Read-only identity check. |
| read frozen envelope | jq . /Users/kamenkamenov/memory-knowledge/Tasks/prevention-system-completion/research-v3/work/envelope.json | Full frozen envelope is available for bounded assessment. | No prior outputs or other lenses. |
| read successor candidate | jq . /private/tmp/prevention-successor-core-candidate.json | Full candidate is available for requirements-coverage assessment. | No prior outputs or other lenses. |
| read referenced frozen artifact | sed -n 1,10000p <file> | The referenced frozen charter or requirements artifact is available in full. | The concrete path is taken verbatim from the frozen envelope. |
| validate terminal envelope | jq -e 'keys == ["findings","verdict"] and (.verdict == "PASS" or .verdict == "GAPS" or .verdict == "BLOCKED") and (.findings == [.findings[]])' /private/tmp/prevention-successor-coverage.json | Terminal envelope has only verdict and findings with allowed top-level shapes. | Exact finding schema is assessed separately from the same JSON. |
| hash terminal envelope | shasum -a 256 /private/tmp/prevention-successor-coverage.json | A transport SHA-256 is available for the parent handoff. | Final response reports only hash, verdict, count, and finding IDs. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

TBD while discovering.

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
