# Sequence Discovery Log: taggable-dev-sql-client-ip

DiscoveryId: discovery-6aba8a9b-8d8b-57bc-bfb1-f8c0939e80d0
Status: discovery
CreatedAtUtc: 2026-07-28T08:41:57Z
RegisteredSequenceMatch: none

## Intended Outcome

A named Azure SQL firewall rule on server taggable-dev (resource group DB) admits the operator machine current outbound IP, so MigrationRunner query and the API can reach taggable-dev from this machine.

## Why This Looks Repeatable

The operator outbound IP changes with network/location, so every taggable-api task that must read or verify dev database state hits the same firewall rejection and needs the same list-check, add-rule, verify-connection steps.

## Required Inputs, Auth, Or Environment





- A firewall rule name approved by Kamen (never chosen by the agent)

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify-connection-and-record-outcome | dotnet tools/Taggable.MigrationRunner/bin/Debug/net9.0/Taggable.MigrationRunner.dll query "$CS" "SELECT name FROM sys.tables WHERE name IN (...)" | Rule created (Kamen Laptop 2026-07-28, 94.68.48.88/94.68.48.88). Connection succeeded on the next query; the firewall rejection did not recur. Schema read returned the expected Devices/TourDevices/DeviceType rows. | Corrections found while running: (1) sequence_guard guard requires the command to already appear in this discovery log, so append-step must precede guard; (2) appending invalidates the selection source bundle, so work_memory select + sequence_guard activate must be re-run after each append before guard will pass; (3) MigrationRunner needs DOTNET_ROLL_FORWARD=LatestMajor because it targets net9.0 and only 8.0/10.0 runtimes are installed; (4) UNION ALL over sys catalog views needs explicit COLLATE DATABASE_DEFAULT on text columns or it fails with a collation conflict. |
| add-client-ip-firewall-rule | az sql server firewall-rule create -g DB -s taggable-dev -n "Kamen Laptop 2026-07-28" --start-ip-address 94.68.48.88 --end-ip-address 94.68.48.88 | pending-execution | Recorded before running: sequence_guard requires the command to be grounded in this discovery log. Preceded by az sql server firewall-rule list -g DB -s taggable-dev (no rule covered this address) and curl api.ipify.org for the current outbound IP. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling


Connection still refused after adding the rule: Azure states a firewall change can take up to five minutes to take effect, so re-run the read once before investigating. If the outbound IP changed between reading it and creating the rule (VPN or network switch), re-read the IP and add a rule for the new one. If az sql server firewall-rule create returns AuthorizationFailed, the logged-in principal lacks rights on resource group DB. Never widen a rule to a range to make it pass; add the single address.

## Verified Path


- Verified through the same path Kamen uses: the MigrationRunner query that had been refused for this IP connected after the rule was added and returned the taggable-dev schema; writes through that same path then applied two migrations and a re-read confirmed them. Ledger verification event 0404ac9d-91b7-4002-b999-16ccbb661ead, correction d1add042-a9cd-4339-a848-7c676c83b6d3.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
