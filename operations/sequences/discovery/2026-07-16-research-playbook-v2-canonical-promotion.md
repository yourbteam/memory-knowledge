# Sequence Discovery Log: research-playbook-v2-canonical-promotion

DiscoveryId: discovery-e239c5e0-5bff-58b1-a62f-99f64e686baf
Status: discovery
CreatedAtUtc: 2026-07-16T07:22:34Z
BootstrapRequestSha256: cd7a223686ae8210ef1920ec4b10a319a9e31a002ac56be92247fd3277a004d1
RegisteredSequenceMatch: none

## Intended Outcome

Replace the canonical research-playbook with the validated V2 implementation, retire the V2 alias, preserve rollback state, install the canonical skill, and prove routing plus runtime behavior.

## Why This Looks Repeatable

Managed skill promotions require the same preflight, atomic replacement, rollback, installation, and verification boundaries.

## Required Inputs, Auth, Or Environment

- /private/tmp/research-playbook-v2-eval-20260716-evidence-link/score.json
- skills/research-playbook
- skills/research-playbook-v2
- skills/managed-skills.txt
- /Users/kamenkamenov/.codex/skills

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| record-controller-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id promotion-tests --changed-artifact <artifact> --solution <solution> --reusable-behavior-changed yes | failed run closed with correction awaiting successor verification | Bind the exact controller and discovery bundle drift before a successor run. |
| focused-preflight | scripts/run_pytest.sh tests/test_install_skills.py tests/test_validate_skills.py tests/test_research_playbook_v2.py -q | exit 0 | Prove the validated candidate and installer contracts before mutation. |
| promotion-tests | scripts/run_pytest.sh tests/test_promote_research_playbook.py -q | exit 0 | Prove dry-run, apply, verification, and rollback behavior of the promotion controller. |
| promotion-plan | python3 <promotion-controller> plan --repo-root /Users/kamenkamenov/memory-knowledge --installed-root /Users/kamenkamenov/.codex/skills --score /private/tmp/research-playbook-v2-eval-20260716-evidence-link/score.json --output /private/tmp/research-playbook-v2-promotion-plan.json | returns ok true with six completion gates and no mutation | Freeze exact source, destination, installed, reference, and rollback hashes. |
| promotion-apply | python3 <promotion-controller> apply --plan /private/tmp/research-playbook-v2-promotion-plan.json --backup-root /Users/kamenkamenov/.local/state/kamen-managed-skills/research-playbook-promotion-20260716 | returns ok true or restores all pre-promotion paths | Atomically replace canonical source, retire V2 source and installed alias, and install canonical skill. |
| post-promotion-validation | scripts/run_pytest.sh tests/test_install_skills.py tests/test_validate_skills.py tests/test_skill_contracts.py tests/test_research_playbook_v2.py tests/test_promote_research_playbook.py -q | exit 0 | Verify canonical identity, routing, controller behavior, and package contracts. |
| promotion-verify | python3 <promotion-controller> verify --plan /private/tmp/research-playbook-v2-promotion-plan.json --backup-root /Users/kamenkamenov/.local/state/kamen-managed-skills/research-playbook-promotion-20260716 | returns verdict PASS with all six gates true | Prove source and installed canonical hashes, absent V2 alias, routing, backup, and test evidence. |

## Failure Handling

Any failed mutation restores every path from the backup before returning nonzero. Any failed post-promotion gate stops without commit or push and leaves the rollback snapshot intact.

## Verified Path

- The canonical research-playbook source and installed tree have the same hash, research-playbook-v2 is absent from both, routing names only research-playbook, tests pass, and a fresh canonical invocation emits a valid package.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
