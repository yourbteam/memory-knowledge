# Plan: Deploy memory-knowledge to Azure Web App

## Overview

Deploy the memory-knowledge MCP server as a Docker container on Azure App Service, reusing the existing infrastructure from workflow-orch-app.

## Decisions

- **Location:** West Europe
- **App Service Plan:** Reuse `workflow-orch-plan` (B3 Basic, shared with workflow-orch-app)
- **Container Registry:** Reuse `workfloworchreg` ACR
- **Key Vault:** Reuse `hrness` vault
- **Auth mode:** `AUTH_MODE=codex` — the `cli-auth-codex` secret in Key Vault is seeded to `~/.codex/auth.json` at startup, same pattern as workflow-orch-app. **Requires a code fix:** move KV seeding BEFORE auth validation in server.py's `app_lifespan`.
- **Summaries:** Disabled in production (`GENERATE_SUMMARIES=false`) — summaries pre-generated locally and imported
- **Git repos:** Not mounted — data arrives via export/import pipeline
- **MCP auth:** `MCP_API_KEY` set and stored in Key Vault

## Step 1: Build and Push Docker Image

```bash
az acr login --name workfloworchreg
docker build --platform linux/amd64 -t workfloworchreg.azurecr.io/memory-knowledge:latest .
docker push workfloworchreg.azurecr.io/memory-knowledge:latest
```

Note: `--platform linux/amd64` required because local machine is ARM (Apple Silicon) but Azure App Service runs x86_64.

## Step 2: Create Web App

```bash
# Note: webapp names must be globally unique. az webapp create will error if taken.
az webapp create \
  --name memory-knowledge \
  --resource-group workflow-orch-rg \
  --plan workflow-orch-plan \
  --deployment-container-image-name workfloworchreg.azurecr.io/memory-knowledge:latest
```

## Step 3: Configure Container Registry

```bash
ACR_PASSWORD=$(az acr credential show --name workfloworchreg --query "passwords[0].value" -o tsv)

az webapp config container set \
  --name memory-knowledge \
  --resource-group workflow-orch-rg \
  --docker-registry-server-url https://workfloworchreg.azurecr.io \
  --docker-registry-server-user workfloworchreg \
  --docker-registry-server-password "$ACR_PASSWORD"
```

## Step 4: Enable Key Vault Access (BEFORE app settings)

The web app needs a managed identity to resolve Key Vault references in app settings. This MUST happen before Step 6.

```bash
az webapp identity assign --name memory-knowledge --resource-group workflow-orch-rg

PRINCIPAL_ID=$(az webapp identity show --name memory-knowledge --resource-group workflow-orch-rg --query principalId -o tsv)

az keyvault set-policy --name hrness --object-id "$PRINCIPAL_ID" --secret-permissions get list
```

## Step 5: Generate and Store Secrets in Key Vault

```bash
# MCP API key for endpoint auth
MCP_KEY=$(openssl rand -base64 32)
az keyvault secret set --vault-name hrness --name memory-knowledge-mcp-api-key --value "$MCP_KEY"

# Codex auth already exists in KV as 'cli-auth-codex' (shared with workflow-orch-app)
# No need to create it — it's seeded to ~/.codex/auth.json at startup

# Database connection secrets
az keyvault secret set --vault-name hrness --name mk-database-url --value "postgresql://postgres.ghymkmramwjwatkgsawp:***@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
az keyvault secret set --vault-name hrness --name mk-qdrant-api-key --value "***"
az keyvault secret set --vault-name hrness --name mk-neo4j-password --value "***"
```

## Step 6: Configure App Settings

```bash
az webapp config appsettings set --name memory-knowledge --resource-group workflow-orch-rg --settings \
  DATA_MODE=remote \
  ALLOW_REMOTE_WRITES=true \
  ALLOW_REMOTE_REBUILDS=false \
  AUTH_MODE=codex \
  AZURE_KEYVAULT_NAME=hrness \
  DATABASE_URL="@Microsoft.KeyVault(VaultName=hrness;SecretName=mk-database-url)" \
  PG_SSL=true \
  QDRANT_URL="https://6cf5d3c4-fc0d-4ea7-968a-5c319a0dd87e.europe-west3-0.gcp.cloud.qdrant.io:6333" \
  QDRANT_API_KEY="@Microsoft.KeyVault(VaultName=hrness;SecretName=mk-qdrant-api-key)" \
  NEO4J_URI="neo4j+s://1f9c5ae5.databases.neo4j.io" \
  NEO4J_USER="1f9c5ae5" \
  NEO4J_PASSWORD="@Microsoft.KeyVault(VaultName=hrness;SecretName=mk-neo4j-password)" \
  GENERATE_SUMMARIES=false \
  MCP_API_KEY="@Microsoft.KeyVault(VaultName=hrness;SecretName=memory-knowledge-mcp-api-key)" \
  EMBEDDING_MODEL=text-embedding-3-small \
  EMBEDDING_DIMENSIONS=1536 \
  SUPPORTED_LANGUAGES='["python","csharp","sql","typescript","php"]' \
  MAX_IMPORT_SIZE_MB=200 \
  ENVIRONMENT=production \
  LOG_LEVEL=INFO \
  WEBSITES_PORT=8000 \
  WEBSITES_CONTAINER_START_TIME_LIMIT=300 \
  WEBSITES_ENABLE_APP_SERVICE_STORAGE=false \
  WEBSITE_HEALTHCHECK_MAXPINGFAILURES=5 \
  WEBSITE_HTTPLOGGING_RETENTION_DAYS=3
```

## Step 7: Configure Web App Settings

```bash
az webapp update --name memory-knowledge --resource-group workflow-orch-rg --https-only true
az webapp config set --name memory-knowledge --resource-group workflow-orch-rg \
  --always-on true \
  --min-tls-version 1.2 \
  --ftps-state FtpsOnly \
  --generic-configurations '{"healthCheckPath": "/health"}'
```

## Step 8: Verify Deployment

```bash
# Check container logs
az webapp log tail --name memory-knowledge --resource-group workflow-orch-rg

# Check health
curl https://memory-knowledge.azurewebsites.net/health

# Check readiness (all 3 DBs)
curl https://memory-knowledge.azurewebsites.net/ready

# Test retrieval
curl -X POST https://memory-knowledge.azurewebsites.net/mcp/ \
  -H "Authorization: Bearer $MCP_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"run_retrieval_workflow","arguments":{"repository_key":"fcsapi","query":"fleet KPI"}}}'
```

## Pre-Deployment Code Fix: Seed Codex Auth from KV Before Validation

In `server.py` `app_lifespan`, the Codex auth validation (line 858) crashes if `~/.codex/auth.json` doesn't exist. In Azure, this file is seeded from Key Vault — but currently `seed_from_keyvault` is only called inside `CodexTokenManager.start()` (line 954), which runs AFTER auth validation. The DB secret seeding block (lines 875-889) only handles `DATABASE_URL`/`QDRANT_API_KEY`/`NEO4J_PASSWORD` — it does NOT touch the codex auth file.

**Fix:** Add a NEW call to `seed_from_keyvault` BEFORE the auth validation block at line 858:

```python
# In app_lifespan, BEFORE the auth validation block:

# Seed Codex auth from Key Vault if in remote/Azure mode
if settings.auth_mode == "codex" and settings.azure_keyvault_name:
    from memory_knowledge.auth.credential_refresh import seed_from_keyvault
    seed_status = await seed_from_keyvault(
        settings.azure_keyvault_name, settings.codex_auth_path
    )
    logger.info("codex_kv_seed_result", status=seed_status)

# THEN the existing auth validation:
if settings.auth_mode == "codex":
    await codex_token_provider(settings.codex_auth_path)
    ...
```

This is NOT moving existing code — it's adding a new call. The existing DB secret seeding (lines 875-889) stays where it is. The `CodexTokenManager` (line 954) still handles ongoing refresh and KV writeback after startup.

## What's NOT Needed in Production

- Codex CLI (`@openai/codex` npm package) — still in Docker image but unused since `GENERATE_SUMMARIES=false`
- Git repo mounts — no local repos, data via import
- `ALLOW_REMOTE_REBUILDS` — left false unless explicit repair needed
- `docker-compose.yml` / `docker-compose.override.yml` — only for local dev
