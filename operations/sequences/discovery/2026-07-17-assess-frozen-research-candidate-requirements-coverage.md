# Sequence Discovery Log: assess frozen research candidate requirements coverage

DiscoveryId: discovery-687e6b25-4f3b-55af-9d9a-95b7b92bea39
Status: discovery
CreatedAtUtc: 2026-07-17T08:46:53Z
BootstrapRequestSha256: df761c4007ccbea6aa169783a32edeb45f2b818af22687e43b07bbf18acfde35
RegisteredSequenceMatch: none

## Intended Outcome

Verify the frozen payload identities and assess all atomic requirements against the requirements-coverage lens without editing research artifacts.

## Why This Looks Repeatable

Research-playbook lens assessments repeatedly verify canonical payload hashes and inspect frozen envelope evidence.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| read frozen requirements | jq . /Users/kamenkamenov/memory-knowledge/Tasks/prevention-system-completion/research/requirements.json | All atomic requirements, maturities, and acceptance intents are available. | Assessment-only read learned from the frozen envelope. |
| read frozen charter | jq . /Users/kamenkamenov/memory-knowledge/Tasks/prevention-system-completion/research-v2/charter.json | Frozen objective, scope, exclusions, and deliverables are available. | Assessment-only read learned from the frozen envelope. |
| verify candidate canonical hash | python3 /Users/kamenkamenov/memory-knowledge/skills/research-playbook/scripts/research_package.py hash-json /private/tmp/prevention-core-v2-candidate.json | canonical_json_sha256 equals b15d60f5f2fe04738753aa9c93347532d53320902462cab3536228dbc9b30768 | Use canonical JSON identity, not file SHA-256. |
| verify envelope canonical hash | python3 /Users/kamenkamenov/memory-knowledge/skills/research-playbook/scripts/research_package.py hash-json /Users/kamenkamenov/memory-knowledge/Tasks/prevention-system-completion/research-v2/work/envelope.json | canonical_json_sha256 equals 56b02c8927c7e628a692470dfb3a2730b7d2c9162e52630fbf142161f7ee0de0 | Use canonical JSON identity, not file SHA-256. |
| read candidate payload | jq . /private/tmp/prevention-core-v2-candidate.json | Candidate JSON is available for assessment. | Assessment-only read. |
| read envelope payload | jq . /Users/kamenkamenov/memory-knowledge/Tasks/prevention-system-completion/research-v2/work/envelope.json | Frozen charter, requirements, and authoritative evidence references are identified. | Assessment-only read. |
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
