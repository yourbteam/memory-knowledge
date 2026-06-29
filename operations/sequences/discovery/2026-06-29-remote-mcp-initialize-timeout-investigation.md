# Sequence Discovery Log: remote-mcp-initialize-timeout-investigation

Status: discovery
CreatedAtUtc: 2026-06-29T11:32:51Z
RegisteredSequenceMatch: none

## Intended Outcome

Diagnose why remote-mcp-operator initialize timed out before resuming task mawf-task-12b9bf8897d092f7a8ce70b7

## Why This Looks Repeatable

Remote MCP initialize timeouts can block employees before workflows start; the evidence collection and health/log checks should become reusable.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| Confirmed initialize timeout cause | App Service health, metrics, and logs review | confirmed app was running but unhealthy/slow during timeout window; health checks 100->40->0, avg response 18.6s->53.1s, memory 95-96%; logs show concurrent Claude CLI 1200s timeouts in run 89057229-71fb-4a0b-8ec8-90f294902e3e before workflow failed and service recovered | Employee task did not start; initialize timeout was caused by deployed service unresponsiveness from another long-running/failed workflow workload, not task prompt/branch/state. |
| Download App Service logs after recovery | az webapp log download --resource-group workflow-orch-rg --name workflow-orch-app --log-file /private/tmp/workflow-orch-app-logs-after-initialize-timeout.zip | planned before execution | Try to capture app/platform logs now that /health has recovered. |
| Recheck deployed health after metrics | curl --max-time 15 -sS https://workflow-orch-app-evbxebcccsd7fpgp.westeurope-01.azurewebsites.net/health | returned status ok; activeSessions=2; runningWorkflowCount=0; busyWorkflowCount=0 | Service recovered by follow-up health probe; employee can retry once package can initialize. |
| Fetch App Service plan pressure metrics | az monitor metrics list --resource /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/serverfarms/workflow-orch-plan --metric CpuPercentage,MemoryPercentage,HttpQueueLength,DiskQueueLength --interval PT5M --aggregation Average --output json | planned before execution | Check worker CPU, memory, and queue pressure during initialize timeout window. |
| List App Service plan metric definitions | az monitor metrics list-definitions --resource /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/serverfarms/workflow-orch-plan --query '[].name.value' --output tsv | planned before execution | Find real plan-level CPU/memory metrics. |
| Fetch App Service plan SKU result | az appservice plan show --resource-group workflow-orch-rg --name workflow-orch-plan --query '{sku:sku,numberOfWorkers:numberOfWorkers,maximumElasticWorkerCount:maximumElasticWorkerCount}' --output json | single-worker Basic B3 plan: sku.name=B3, tier=Basic, capacity=1 | App runs on one Basic B3 worker. |
| Fetch App Service plan SKU | az appservice plan show --resource-group workflow-orch-rg --name workflow-orch-plan --query '{sku:sku,numberOfWorkers:numberOfWorkers,maximumElasticWorkerCount:maximumElasticWorkerCount}' --output json | planned before execution | Interpret memory/CPU telemetry against plan capacity. |
| Fetch App Service appServicePlanId result | az webapp show --resource-group workflow-orch-rg --name workflow-orch-app --query appServicePlanId --output tsv | returned /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/serverfarms/workflow-orch-plan | Plan id found for sizing check. |
| Fetch App Service appServicePlanId | az webapp show --resource-group workflow-orch-rg --name workflow-orch-app --query appServicePlanId --output tsv | planned before execution | Correct field for plan id in Azure CLI webapp show. |
| Fetch App Service plan id result | az webapp show --resource-group workflow-orch-rg --name workflow-orch-app --query serverFarmId --output tsv | returned empty | Azure CLI output does not expose plan under serverFarmId for this query; use appServicePlanId. |
| Fetch App Service plan id | az webapp show --resource-group workflow-orch-rg --name workflow-orch-app --query serverFarmId --output tsv | planned before execution | Need plan sizing to interpret memory/CPU pressure. |
| Fetch App Service total request metrics | az monitor metrics list --resource /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/sites/workflow-orch-app --metric Requests,Http5xx,Http4xx --interval PT5M --aggregation Total --output json | planned before execution | Check request/error totals during unhealthy window. |
| Fetch App Service average metrics result | az monitor metrics list --resource /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/sites/workflow-orch-app --metric AverageResponseTime,MemoryWorkingSet,CpuTime,HealthCheckStatus --interval PT5M --aggregation Average --output json | health status dropped 100->40 at 11:28Z and 0 at 11:33Z/11:38Z; AverageResponseTime rose to 18.64s at 11:33Z and 53.07s at 11:38Z; memory around 4.9GB; CPU time elevated | Confirms deployed app was unhealthy/slow during initialize timeout window. |
| Fetch App Service average metrics | az monitor metrics list --resource /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/sites/workflow-orch-app --metric AverageResponseTime,MemoryWorkingSet,CpuTime,HealthCheckStatus --interval PT5M --aggregation Average --output json | planned before execution | Average gauge metrics for response latency/resource/health evidence. |
| Fetch App Service last-hour runtime metrics result | az monitor metrics list --resource /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/sites/workflow-orch-app --metric Requests,AverageResponseTime,Http5xx,MemoryWorkingSet,CpuTime,HealthCheckStatus --interval PT5M --aggregation Average,Total,Maximum --output json | CLI rejected comma-separated aggregation value | Correction: query Average and Total metrics separately. |
| Fetch App Service last-hour runtime metrics | az monitor metrics list --resource /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/sites/workflow-orch-app --metric Requests,AverageResponseTime,Http5xx,MemoryWorkingSet,CpuTime,HealthCheckStatus --interval PT5M --aggregation Average,Total,Maximum --output json | planned before execution | Check whether the Running app is overloaded, returning errors, or failing platform health checks. |
| List App Service metric definitions quoted | az monitor metrics list-definitions --resource /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/sites/workflow-orch-app --query '[].name.value' --output tsv | planned before execution | Quoted correction for zsh. |
| List App Service metric definitions result | az monitor metrics list-definitions --resource /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/sites/workflow-orch-app --query [].name.value --output tsv | local shell failed: zsh globbed [].name.value | Correction: quote the JMESPath query. |
| List App Service metric definitions | az monitor metrics list-definitions --resource /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/sites/workflow-orch-app --query [].name.value --output tsv | planned before execution | Use real Azure metric names before querying runtime telemetry. |
| Fetch App Service resource id result | az webapp show --resource-group workflow-orch-rg --name workflow-orch-app --query id --output tsv | returned /subscriptions/0000e83f-3d45-4ac5-a0cb-78b1b052ccd4/resourceGroups/workflow-orch-rg/providers/Microsoft.Web/sites/workflow-orch-app | Control plane can reach the app resource while data-plane /health times out. |
| Fetch App Service resource id | az webapp show --resource-group workflow-orch-rg --name workflow-orch-app --query id --output tsv | planned before execution | Needed for Azure metrics lookup after /health and initialize timeouts. |
| Collect Azure debug evidence bundle | scripts/azure_debug_evidence_collect.sh --resource-group workflow-orch-rg --app-name workflow-orch-app --task-id mawf-task-12b9bf8897d092f7a8ce70b7 --repo thebteambg/neocurrency-dashboard --workflow requirements-hardening-precode-workflow --error-code REMOTE_MCP_REQUEST_TIMEOUT --timeout-seconds 90 | planned before execution | Collect App Service metadata, sanitized settings, storage mounts, and focused logs for initialize timeout without invoking MCP read tools. |
| Fetch deployed health JSON with timeout | curl --max-time 15 -sS https://workflow-orch-app-evbxebcccsd7fpgp.westeurope-01.azurewebsites.net/health | planned before execution | Deterministic read-only health probe after untimed curl hung. |
| Record hanging health call | curl -sS https://workflow-orch-app-evbxebcccsd7fpgp.westeurope-01.azurewebsites.net/health | hung for more than 60 seconds; interrupted with Ctrl-C | A normal health response should be quick. This supports that the deployed service was not generally responsive, not just one user/task. |
| Fetch deployed health JSON | curl -sS https://workflow-orch-app-evbxebcccsd7fpgp.westeurope-01.azurewebsites.net/health | planned before execution | Read-only check for app responsiveness, runningWorkflowCount, busyWorkflowCount, and CLI credential health. |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
