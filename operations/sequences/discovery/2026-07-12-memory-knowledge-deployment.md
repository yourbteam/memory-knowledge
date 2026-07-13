# Sequence Discovery Log: memory-knowledge deployment

DiscoveryId: discovery-9a1fa875-7fa9-5a17-b895-59a4fc576998
Status: discovery
CreatedAtUtc: 2026-07-12T19:23:53Z
RegisteredSequenceMatch: none

## Intended Outcome

deploy committed planning-contract release and migration

## Why This Looks Repeatable

memory-knowledge MCP releases require repeatable image, migration, rollout, and smoke verification

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify deployed app state | az webapp show --resource-group workflow-orch-rg --name memory-knowledge --query state --output tsv | pending | post-deploy Web App state check |
| deploy memory-knowledge | ./infra/azure-push.sh | pending | ACR build, Web App image update, restart, migration-on-startup, and health check |
| validate deployment script syntax | bash -n infra/azure-push.sh | pending | canonical script syntax preflight |
| read canonical deployment script and startup migration behavior | sed -n '1,220p' README.md; sed -n '1,260p' infra/azure-push.sh; sed -n '1,160p' docker/entrypoint.sh | pending | README indicates docker entrypoint applies migrations; inspect exact Azure push path |
| inspect deployment entrypoints | rg -n deploy Dockerfile docker-compose pyproject.toml README.md operations scripts | pending | discover repository-supported deployment path before execution |

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
