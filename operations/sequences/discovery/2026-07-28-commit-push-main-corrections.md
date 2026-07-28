# Sequence Discovery Log: commit-push-main corrections

DiscoveryId: discovery-b15ca123-f8bb-5c68-9801-56f1023410f0
Status: discovery
CreatedAtUtc: 2026-07-28T19:10:35Z
RegisteredSequenceMatch: none

## Intended Outcome

Publish an approved file scope from a repository the machine registry does not yet list, and record the fix so the blocker closes.

## Why This Looks Repeatable

Every first publish of a new repository through commit-push-main hits the same registry gate, and every correction whose changed file lives outside memory-knowledge hits the same roots-manifest and run-close rules.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| close-correction-run-failed | python3 scripts/work_memory.py run-close --run-id <run> --result failed | The bound successor selection is then accepted and the blocker can reach verified. | Closing it 'passed' makes select --verification-successor-of return successor-predecessor-not-terminal. The ledger is append-only, so that run can never be re-closed and the blocker strands at fixed-awaiting-verification. Observed live 2026-07-28 on blk-1ab692114088d3bbc2129027. |
| declare-environment-surface | python3 scripts/work_memory.py correct --changed-environment-artifact <path> ... | Correction recorded with old_bundle_hash equal to new_bundle_hash. | A machine surface is in no sequence dependency bundle, so declaring it with --changed-artifact returns correction-artifact-drift-mismatch: bundle artifacts must exactly equal the drifted bundle set. |
| supply-roots-manifest-at-select | python3 scripts/work_memory.py select --task-id <id> --sequence-id commit-push-main --repo-roots-file <manifest> | The run then accepts a correction whose changed file lives outside memory-knowledge. | Supplying the manifest only to 'correct' returns repository-roots-mismatch: the run's roots are fixed at selection. Same lesson as operations/sequences/discovery/2026-07-14-up-harness-cd-s-002-live-verification.md. |
| register-target-repository | edit ~/.config/memory-knowledge/repositories.json to add the target repository root | The intake then offers and accepts mcp-agents-workflow; publish reached ok:true. | Symptom when missing: the intake Repository question answers 'Invalid answer: choose one of: memory-knowledge, united-partners'. The choice list is built from this machine registry plus the memory-knowledge default in work_memory._repo_roots, NOT from a list inside the sequence. Do NOT hand-run git add/git commit instead - that bypasses the exact-scope staging boundary this sequence exists to enforce, which is what protects unrelated working-tree changes. |
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
