# Sequence Discovery Log: portable-office-client-parity

DiscoveryId: discovery-ad8664ac-4bf6-53de-9aea-074b5093bde6
Status: discovery
CreatedAtUtc: 2026-07-13T06:07:48Z
RegisteredSequenceMatch: none

## Intended Outcome

Build a secret-free transfer folder that brings Codex and Claude working-agreement, managed skills, hooks, and memory tooling to parity on another macOS machine

## Why This Looks Repeatable

The same client bootstrap is required on office machines and future replacement machines

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| Refresh published transfer folder | cp -R /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/. /Users/kamenkamenov/Downloads/codex-claude-office-parity-2026-07-13 | planned | Update the existing Downloads folder in place after final verified installer changes without nesting another directory |
| Remove repository history from transfer package | rm -f /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/payload/memory-knowledge.bundle | planned | Final security boundary: transfer the exact skills and commit pin; clone committed source from GitHub instead of carrying repository history |
| Create complete repository bundle | git -C /Users/kamenkamenov/memory-knowledge bundle create /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/payload/memory-knowledge.bundle main | planned | Stable correction: bundle the full reachable object graph directly from the canonical repository |
| Publish verified transfer folder | cp -R /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging /Users/kamenkamenov/Downloads/codex-claude-office-parity-2026-07-13 | planned | Copy only the verified secret-free package to Downloads |
| Create Downloads destination | mkdir -p /Users/kamenkamenov/Downloads | planned | Ensure the requested transfer destination exists |
| Run isolated package smoke test | /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/smoke-test-package.sh | planned | Prove bundle clone, transactional dual-client install, config merge, and all receipt probes without touching live client files |
| Validate Python syntax | python3 -m py_compile /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/configure_clients.py /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/verify-office-parity.py | planned | Reject Python syntax errors |
| Validate shell syntax | bash -n /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/install-office-parity.sh /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/smoke-test-package.sh | planned | Reject shell syntax errors |
| Mark package entrypoints executable | chmod +x /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/install-office-parity.sh /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/smoke-test-package.sh /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/configure_clients.py /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/verify-office-parity.py | planned | Make the one-command installer directly runnable |
| Create portable repository bundle | git -C /private/tmp/memory-knowledge-office-parity-shallow-20260713 bundle create /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/payload/memory-knowledge.bundle main | planned | Provide an exact self-contained committed source repository |
| Create clean shallow repository snapshot | git clone --depth 1 --branch main file:///Users/kamenkamenov/memory-knowledge /private/tmp/memory-knowledge-office-parity-shallow-20260713 | planned | Exclude every untracked local file and all credentials |
| Copy cross-client reconciliation evidence | cp /Users/kamenkamenov/memory-knowledge/tests/fixtures/work-memory/reconciliation.json /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/payload/reconciliation.json | planned | Preserve the exact Claude and Codex reconciliation contract |
| Copy canonical managed skills | cp -R /Users/kamenkamenov/memory-knowledge/skills /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/payload/skills | planned | Include all managed skill sources for inspection and recovery |
| Create package payload directory | mkdir -p /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/office-parity-package-staging/payload | planned | Prepare the secret-free transfer payload |

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
