# Sequence Discovery Log: unified-research-playbook-skill-creation

DiscoveryId: discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab
Status: discovery
CreatedAtUtc: 2026-07-14T15:47:36Z
RegisteredSequenceMatch: none

## Intended Outcome

Create and blind-validate a unified subagent-driven research-to-plan skill, then prepare replacement only after comparative success.

## Why This Looks Repeatable

Skill creation, validation fixtures, cache-safe installation, and successor promotion are a reusable multi-step workflow.

## Required Inputs, Auth, Or Environment

- Canonical skill source: `/Users/kamenkamenov/memory-knowledge/skills`.
- Codex projection target: `/Users/kamenkamenov/.codex/skills`.
- Explicit implementation approval for the side-by-side candidate; no promotion or router replacement.
- A fresh Codex task for explicit-v2 and ordinary-legacy routing checks after installation.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| start-run | python3 scripts/work_memory.py run-start --task-id unified-research-playbook-v2-20260714 | succeeded | Durable run `abdc515a-4bc9-48e3-a3c3-417d7c3be32b` started after activation. |
| activate-discovery | python3 scripts/sequence_guard.py activate --task-id unified-research-playbook-v2-20260714 --discovery-log operations/sequences/discovery/2026-07-14-unified-research-playbook-skill-creation.md | succeeded | Active receipt records the exact discovery source and bundle hash. |
| bind-discovery | python3 scripts/work_memory.py select --task-id unified-research-playbook-v2-20260714 --discovery-log operations/sequences/discovery/2026-07-14-unified-research-playbook-skill-creation.md | succeeded | Selection receipt bound the task to this discovery lineage. |
| select-sequence | python3 scripts/work_memory.py select --task-id unified-research-playbook-v2-20260714 | discovery-required | No registered sequence matched; discovery path is authoritative. |
| classify-task | python3 scripts/work_memory.py classify --task-id unified-research-playbook-v2-20260714 --operation-kind other --repeatable yes --meaningful-steps 8 | operational classification receipt created | Skill creation is a repeatable multi-step operation. |
| inspect-summary | python3 scripts/work_memory.py summary --subject-id discovery-3fd6cc31-5152-5c78-91fb-b6e946b2cdab | required | Use subject id, not task id. |
| open-blocker | python3 scripts/blocker_catalog.py open --run-id <run-id> --subject-id <subject-id> --step-id <step-id> --surface <surface> --error-signature <signature> --symptom <symptom> --evidence <evidence> --impact <impact> --boundary <boundary> | required | Catalog a blocker before changing the failed path. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required | Record a one-artifact managed-projection correction before successor selection. |
| record-correction-pair | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required | Record a two-artifact command-contract and dependency-manifest correction before successor selection. |
| record-correction-multiple | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --changed-artifact <path> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required | Record every artifact in a multi-artifact managed-projection correction before successor selection. |
| record-evaluator-contract-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --changed-artifact <path> --changed-artifact <path> --changed-artifact <path> --changed-artifact <path> --changed-artifact <path> --changed-artifact <path> --changed-artifact <path> --changed-artifact <path> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required | Record the evaluator, focused tests, public evaluation contract, six case contracts, and discovery command update as one blind-evaluation contract correction. |
| supersede-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --changed-artifact <path> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes --supersedes-correction-id <correction-id> | required | Replace a recorded correction when later remediation changes one of its artifact hashes before verification. |
| transition-fixed | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required | Mark an implemented correction as awaiting same-path verification. |
| transition-verified | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status verified --verification-event-id <event-id> | required | Bind successful same-path evidence to the blocker. |
| transition-closed | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status closed --verification-event-id <event-id> --remaining-work none | required | Close only after verified same-path evidence with no remaining work. |
| transition-non-gap | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status non-gap --non-gap-evidence <evidence> | required | Close an observed anomaly only when cited contract evidence proves it is the expected fail-closed behavior. |
| close-failed-run | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required | A corrected bundle cannot be verified by the stale predecessor run. |
| select-successor | python3 scripts/work_memory.py select --task-id unified-research-playbook-v2-20260714 --discovery-log operations/sequences/discovery/2026-07-14-unified-research-playbook-skill-creation.md --verification-successor-of <run-id> --verifies-correction-id <correction-id> | required | Bind the corrected B bundle to its A predecessor and correction. |
| initialize-candidate | python3 init_skill.py research-playbook-v2 --path /Users/kamenkamenov/memory-knowledge/skills --resources scripts,references --interface "display_name=Research Playbook V2" --interface "short_description=Bounded subagent research for one-shot plans" --interface "default_prompt=Use $research-playbook-v2 to produce a planner-ready research package." | required | Run from the canonical skill-creator `scripts` directory exactly once. |
| validate-candidate | uv run --project /Users/kamenkamenov/memory-knowledge --extra dev python quick_validate.py /Users/kamenkamenov/memory-knowledge/skills/research-playbook-v2 | required | Run from the canonical skill-creator `scripts` directory while using the repository's locked PyYAML runtime. |
| validate-managed | python3 working-agreement/validate_skills.py --skills-root skills --manifest skills/managed-skills.txt | required | Validate every canonical managed skill from the repository root. |
| test-focused | scripts/run_pytest.sh tests/test_install_skills.py tests/test_validate_skills.py tests/test_research_playbook_v2.py -q | required | Exercise selective installation, policy validation, and deterministic research state through the repository's writable-cache launcher. |
| test-full | uv run --extra dev pytest | required | Detect regressions across the canonical repository in the locked project environment. |
| snapshot-managed | python3 evaluate_research_playbook_v2.py snapshot-managed --manifest ../skills/managed-skills.txt --root /Users/kamenkamenov/.codex/skills --output <snapshot> | required | Run from `memory-knowledge/scripts` before and after installation. |
| snapshot-rebased-managed | python3 scripts/evaluate_research_playbook_v2.py snapshot-managed --manifest skills/managed-skills.txt --root /Users/kamenkamenov/.codex/skills --output <snapshot> | required | After an independently changed live projection is confirmed and Kamen approves rebasing, preserve that live state as the immediate pre-install baseline instead of overwriting it with an older sealed snapshot. |
| restore-managed | python3 scripts/evaluate_research_playbook_v2.py restore-managed --manifest skills/managed-skills.txt --root /Users/kamenkamenov/.codex/skills --expected /private/tmp/research-playbook-v2-20260714-before.json --plan operations/sequences/discovery/2026-07-14-unified-research-playbook-skill-creation.restore.json --backup-root /private/tmp/research-playbook-v2-20260714-failed-install-backup --output /private/tmp/research-playbook-v2-20260714-restored.json | required | Preflight exact recovery sources, preserve each listed file's state at write time, create and own any missing parents, move the failed v2 projection aside, and roll back unless the full managed snapshot exactly matches the sealed baseline. |
| install-codex | python3 working-agreement/install_skills.py --source skills --manifest skills/managed-skills.txt --target codex --only research-playbook-v2 | required | Add only the v2 Codex projection after pre-install hashes are captured; do not rewrite any existing managed projection. |
| compare-managed | python3 evaluate_research_playbook_v2.py compare-managed --before <snapshot> --after <snapshot> --allow-added research-playbook-v2 | required | Require every pre-existing managed projection to remain byte-identical. |
| compare-rebased-managed | python3 scripts/evaluate_research_playbook_v2.py compare-managed --before <snapshot> --after <snapshot> --allow-added research-playbook-v2 | required | Prove the selective v2 install added only `research-playbook-v2` while preserving the approved immediate live baseline byte-for-byte. |
| compare-restored | python3 evaluate_research_playbook_v2.py compare-managed --before /private/tmp/research-playbook-v2-20260714-before.json --after /private/tmp/research-playbook-v2-20260714-restored.json --exact | required | Prove the restored managed projection, including intentionally missing v2, exactly equals the sealed pre-install snapshot. |
| prepare-evaluation | python3 evaluate_research_playbook_v2.py prepare --fixtures ../tests/fixtures/research-playbook-v2 --output <output-dir> | required | Stage raw-only snapshots and lock the 18-execution matrix before any agent starts. |
| v2-init-state | python3 <package-controller> init <state> --charter <charter> --requirements <requirements> --operational-maturity <maturity> --evidence-availability <availability> --started-at <timestamp> | required | Freeze one case's charter, atomic requirements, maturity, and evidence boundary before spawning roles. |
| v2-record-candidate | python3 <package-controller> record-candidate <state> --candidate <candidate> --envelope <envelope> --evidence-availability <availability> --now <timestamp> | required | Materialize and hash the core research candidate and the common role envelope. |
| v2-record-attempt | python3 <package-controller> record-attempt <state> --runtime-agent-id <agent-id> --role <role> --round <round> --candidate-hash <hash> --input-envelope-hash <hash> --status <status> --output-hash <hash> --slot-closed --close-evidence <evidence> --now <timestamp> | required | Record every actual role attempt and its closed runtime slot. |
| v2-record-lens | python3 <package-controller> record-lens <state> --round <round> --lens <lens> --runtime-agent-id <agent-id> --candidate-hash <hash> --envelope-hash <hash> --terminal-envelope <terminal-envelope> --now <timestamp> | required | Bind each exact independent lens terminal envelope to the identical candidate and envelope. |
| v2-record-adjudication | python3 <package-controller> record-adjudication <state> --round <round> --runtime-agent-id <agent-id> --candidate-hash <hash> --envelope-hash <hash> --adjudications <adjudications> --now <timestamp> | required | Classify and deduplicate the complete raw-finding set independently. |
| v2-emit-package | python3 <package-controller> emit-package <state> <output-directory> --research <research> --evidence-index <evidence-index> --planner-readiness <planner-readiness> --planner-handoff <planner-handoff> --now <timestamp> | required | Emit the exact terminal six-file package only from validated PASS state and controller-validated planner readiness. |
| v2-show-state | python3 <package-controller> show <state> | required | Reload and validate persisted state before recording the package. |
| record-evaluation | python3 evaluate_research_playbook_v2.py record --run-dir <output-dir> --case-id <case-id> --arm <arm> --role <role> --agent-id <agent-id> --input-hash <hash> --output <path> --output-hash <hash> --slot-closed yes | required | Retain every execution; v2 research uses the canonical six-file package-tree hash. |
| score-evaluation | python3 evaluate_research_playbook_v2.py score --run-dir <output-dir> --fixtures <fixtures-dir> | required | Verify the separately retained fixture/gold hashes, then score hidden predicates and locked promotion thresholds only after all declared executions are recorded. |
| record-package-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <artifact-1> --changed-artifact <artifact-2> --changed-artifact <artifact-3> --changed-artifact <artifact-4> --changed-artifact <artifact-5> --solution <solution> --reusable-behavior-changed <yes-or-no> | required | Record the reusable six-file package-boundary correction before a successor run verifies it. |
| verify-run | python3 scripts/work_memory.py verify --run-id <run-id> --outcome passed --quality same-path --evidence <evidence> --blocker-id <blocker-id> --correction-id <correction-id> | required | Same-path verification binds the repaired run to the cataloged blocker. |
| verify-run-three | python3 scripts/work_memory.py verify --run-id <run-id> --outcome passed --quality same-path --evidence <evidence> --blocker-id <blocker-id> --correction-id <correction-id> --blocker-id <blocker-id> --correction-id <correction-id> --blocker-id <blocker-id> --correction-id <correction-id> | required | Atomically bind a successor selected for exactly three corrections to all three blocker/correction pairs. |
| close-passed-run | python3 scripts/work_memory.py run-close --run-id <run-id> --result passed | required | Close only after same-path evidence passes. |
| check-discovery | python3 scripts/sequence_discovery_log.py check --file operations/sequences/discovery/2026-07-14-unified-research-playbook-skill-creation.md | required | Evaluate discovery readiness after the verified run. |
| closeout-discovery | python3 scripts/sequence_discovery_log.py closeout --file operations/sequences/discovery/2026-07-14-unified-research-playbook-skill-creation.md | required | Close out only when discovery readiness permits it. |

## Failure Handling

- Open a canonical blocker before changing a failed operational path.
- Record reusable bundle corrections with `work_memory.py correct`.
- Close the stale predecessor run failed, select and activate a verification successor, and rerun the same path.
- Two identical failure fingerprints stop retries and require root-cause remediation.
- Spawn top-level evaluation agents serially and capture each returned runtime-agent ID before starting the next. If a batch spawn reports failure after partial creation, stop every duplicate writer and verify the completed output hash and ownership before recording it.
- Invoke v2 at the main task boundary, where spawn, wait, and close tools exist. The main task owns package state and launches the five independent role agents; a delegated agent without child-agent tools must return `BLOCKED` and is not a valid v2 orchestrator.
- If a successful historical restore is followed by a confirmed independent change to a live projection, do not restore over the newer state. Preserve the evidence of the historical restoration, obtain explicit approval to rebase, capture a fresh immediate baseline, selectively install only the candidate, and compare the immediate before/after snapshots.

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
