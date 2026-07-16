# Sequence Discovery Log: research playbook v2 mixed fixture remediation

DiscoveryId: discovery-223a62bb-62d5-5004-a1b6-cedb69d65585
Status: discovery
CreatedAtUtc: 2026-07-15T19:37:30Z
BootstrapRequestSha256: 478f5df8e9abd952bed25ecacfda34eb3ffb8c79c23fd2fb4c30067b0c27fcd9
RegisteredSequenceMatch: none

## Intended Outcome

Ground the mixed-maturity future-consumer planning boundary without changing its scope, maturity, or predicates.

## Why This Looks Repeatable

Blind fixture corrections must be cataloged, byte-bound, independently verified, and replayed before comparative scoring.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| open-blocker | python3 scripts/blocker_catalog.py open --run-id <run-id> --subject-id discovery-223a62bb-62d5-5004-a1b6-cedb69d65585 --step-id <step-id> --surface <surface> --error-signature <signature> --symptom <symptom> --evidence <evidence> --impact <impact> --boundary <boundary> | required | Bind `--subject-id` to this selected discovery/run subject; carry the mixed-maturity fixture identity in the blocker evidence and boundary fields. |
| edit-mixed-fixture | apply_patch tests/fixtures/research-playbook-v2/mixed-maturity | required | Edit only evidence.json, output-contract.json, and gold.json. |
| correct-mixed-fixture | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact tests/fixtures/research-playbook-v2/mixed-maturity/raw/evidence.json --changed-artifact tests/fixtures/research-playbook-v2/mixed-maturity/raw/output-contract.json --changed-artifact tests/fixtures/research-playbook-v2/mixed-maturity/gold.json --solution <solution> --reusable-behavior-changed yes | required | Bind exactly the three adjudicated fixture changes and close the failed predecessor atomically. |
| focused-tests | scripts/run_pytest.sh tests/test_research_playbook_v2.py -q | required | Prove fixture and evaluator contracts before replay. |

## Failure Handling

Stop at the first failed guard or command; do not edit any other fixture, skill, evaluator, controller, or research output.

## Verified Path

- The exact three-file correction is selected by a fresh successor, focused tests pass, and the mixed case is rerun through all independent roles.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
