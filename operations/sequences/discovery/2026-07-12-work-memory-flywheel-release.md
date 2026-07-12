# Sequence Discovery Log: work-memory-flywheel-release

DiscoveryId: discovery-87df1262-3559-590e-9102-27b64fd3c6ad
Status: discovery
CreatedAtUtc: 2026-07-12T06:30:53Z
RegisteredSequenceMatch: none

## Intended Outcome

Commit, push, migrate, deploy, and verify the memory-knowledge work-memory flywheel.

## Why This Looks Repeatable

Future memory-knowledge schema and agent-contract upgrades require the same controlled release path.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| final-git-status | git status --short | planned | Confirm only unrelated pre-existing dirty paths remain. |
| push-release-evidence | git push origin main | planned | Push final release evidence to origin/main. |
| commit-release-evidence | git commit -m 'chore: record work-memory release evidence' | planned | Commit the reusable release evidence without AI attribution. |
| check-release-evidence | git diff --cached --check | planned | Validate the evidence-only staged diff. |
| stage-release-evidence | git add operations/blockers/BLOCKERS.md operations/work-memory/events.jsonl operations/sequences/discovery/2026-07-12-work-memory-flywheel-release.dependencies.json operations/sequences/discovery/2026-07-12-work-memory-flywheel-release.md | planned | Stage only post-deploy ledger and discovery evidence. |
| release-summary | python3 scripts/work_memory.py summary --subject-id discovery-87df1262-3559-590e-9102-27b64fd3c6ad | planned | Read corrections and run metrics before closeout. |
| discovery-closeout | python3 scripts/sequence_discovery_log.py closeout --file operations/sequences/discovery/2026-07-12-work-memory-flywheel-release.md | planned | Verify discovery closeout is not overdue or blocked. |
| discovery-check | python3 scripts/sequence_discovery_log.py check --file operations/sequences/discovery/2026-07-12-work-memory-flywheel-release.md | planned | Refresh derived discovery lifecycle state. |
| probe-claude-discovery | python3 scripts/work_memory_contract_probe.py --skills-root /Users/kamenkamenov/.claude/skills --mode discovery | planned | Probe Claude discovery receipt behavior. |
| probe-claude-registered | python3 scripts/work_memory_contract_probe.py --skills-root /Users/kamenkamenov/.claude/skills --mode registered | planned | Probe Claude registered receipt behavior. |
| probe-codex-discovery | python3 scripts/work_memory_contract_probe.py --skills-root /Users/kamenkamenov/.codex/skills --mode discovery | planned | Probe Codex discovery receipt behavior. |
| probe-codex-registered | python3 scripts/work_memory_contract_probe.py --skills-root /Users/kamenkamenov/.codex/skills --mode registered | planned | Probe Codex registered receipt behavior. |
| probe-source-discovery | python3 scripts/work_memory_contract_probe.py --skills-root skills --mode discovery | planned | Probe source discovery receipt behavior. |
| probe-source-registered | python3 scripts/work_memory_contract_probe.py --skills-root skills --mode registered | planned | Probe source registered receipt behavior. |
| deploy-service | ./infra/azure-push.sh --tag work-memory-flywheel-20260712 | planned | Build, deploy, restart, migrate on startup, and health-check Azure. |
| install-both-clients | working-agreement/install-skills.sh --target both --accept-cross-client | planned | Transactionally reconcile Codex and Claude managed skills. |
| deploy-dry-run | ./infra/azure-push.sh --tag work-memory-flywheel-20260712 --dry-run | planned | Review Azure targets and commands without mutation. |
| push-feature | git push origin main | planned | Push the feature commit to origin/main. |
| commit-feature | git commit -m 'feat: add verified work-memory flywheel' | planned | Commit the complete work-memory upgrade without AI attribution. |
| review-staged-status | git status --short | planned | Confirm unrelated dirty paths remain unstaged. |
| review-staged-stat | git diff --cached --stat | planned | Review the staged feature scope before commit. |
| check-staged-diff | git diff --cached --check | planned | Reject whitespace errors in the exact staged surface. |
| stage-feature | git add --pathspec-from-file=/tmp/work-memory-release-paths.txt | planned | Stage only the converged feature and release discovery paths. |
| precommit-source-validator | working-agreement/validate-skills.sh | planned | Validate canonical managed skills before commit. |
| precommit-tests | env PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider | planned | Run the complete cache-suppressed suite before commit. |
| generate-release-pathspec | jq -r '.repositories["/Users/kamenkamenov/memory-knowledge"][], "operations/sequences/discovery/2026-07-12-work-memory-flywheel-release.dependencies.json", "operations/sequences/discovery/2026-07-12-work-memory-flywheel-release.md"' /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/work-memory-flywheel/review-surface.json > /tmp/work-memory-release-paths.txt | planned | Generate an exact staging list from the converged surface plus release evidence. |
| inspect-transactional-installer | sed -n '90,130p' working-agreement/INSTALL.md | planned | Read the exact dual-client validation and transactional installation commands. |
| inspect-review-surface | jq -r '.repositories["/Users/kamenkamenov/memory-knowledge"][]' /Users/kamenkamenov/Documents/Codex/2026-07-10/can-you-assess-both-the-working/work-memory-flywheel/review-surface.json | planned | Load the converged path inventory used for the commit. |
| inspect-git-status | git status --short | planned | Recheck all dirty paths before staging. |
| inspect-skill-install | rg -n -e install_skills -e managed-skills -e claude -e codex working-agreement/INSTALL.md scripts skills README.md | planned | Identify the canonical dual-client skill installation command. |
| inspect-deploy-script | sed -n '1,260p' infra/azure-push.sh | planned | Read the exact ACR, Web App, migration, restart, and health sequence. |
| inspect-deploy-doc | sed -n '131,155p' working-agreement/INSTALL.md | planned | Read the canonical service deployment contract. |
| inspect-release-entrypoints | rg -n -e alembic -e migration -e deploy -e Azure -e production -e install_skills README.md pyproject.toml docker-compose.yml scripts working-agreement -g '*.md' -g '*.py' -g '*.yml' -g '*.yaml' | planned | Inspect authoritative migration, deployment, and skill-install entry points before staging. |

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
