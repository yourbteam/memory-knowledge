# Analysis: Tri-Database Local/Remote Integration

Gap analysis, impact assessment, and implementation requirements for supporting Supabase PostgreSQL, Qdrant Cloud, and Neo4j Aura alongside local Docker instances.

## 1. Current Architecture Assessment

### What Exists Today

The codebase has a clean, centralized database layer:

| Component | File | Pattern |
|---|---|---|
| PostgreSQL | `db/postgres.py` | `init_postgres()` → global `_pool` → `get_pg_pool()` |
| Qdrant | `db/qdrant.py` | `init_qdrant()` → global `_client` → `get_qdrant_client()` |
| Neo4j | `db/neo4j.py` | `init_neo4j()` → global `_driver` → `get_neo4j_driver()` |
| Settings | `config.py` | Pydantic `BaseSettings` from `.env` |
| Startup | `server.py:785-854` | Sequential init in Starlette lifespan |
| Shutdown | `server.py:861-881` | Reverse-order close |
| Health | `db/health.py` | Readiness probe tests all 3 DBs |

### What Works Well (Minimal Change Needed)

1. **No hardcoded hosts.** All connection strings are env-var-driven via Pydantic Settings. `DATABASE_URL`, `QDRANT_URL`, `NEO4J_URI` are already configurable.
2. **Single init point.** All 3 clients are created in `app_lifespan()` and retrieved via getter functions. No scattered ad-hoc client creation.
3. **Clean getter pattern.** 50+ functions receive `pool`/`qdrant_client`/`neo4j_driver` as parameters — they don't create connections themselves.
4. **Health checks exist.** `/ready` endpoint probes all 3 databases with 5s timeout.
5. **SSL support exists for PG.** `pg_ssl` boolean in config, passed as `ssl="require"` to asyncpg. Note: `ssl="require"` does NOT verify server certificates (uses `CERT_NONE`). This is standard for managed Postgres providers (Supabase, RDS) but worth documenting as a security trade-off.
6. **Qdrant API key support exists.** `qdrant_api_key` is already an optional config field.
7. **Docker networking is isolated.** The `.env` file uses Docker service names (`postgres`, `qdrant`, `neo4j`) not `localhost`. The compose services expose ports for external access.

### What's Missing (Gaps)

## 2. Gap Analysis

### Gap 1: No Mode Switch Concept

**Requirement:** `DATA_MODE=local|remote` with optional per-database overrides.

**Current state:** No concept of "mode" exists. Settings are flat — you either set `DATABASE_URL` to a local value or a remote value, but nothing validates consistency, logs the mode, or guards against accidents.

**Impact:** Medium. The config layer needs a new `data_mode` field, per-database mode resolution, and startup logging. No business logic changes — workflows don't care about mode.

**Files affected:**
- `config.py` — add `data_mode`, per-DB mode fields, mode resolution
- `server.py:785-854` — add startup mode summary logging

### Gap 2: No Remote Write Guard

**Requirement:** `ALLOW_REMOTE_WRITES=true` must be explicitly set before writes to remote databases are allowed.

**Current state:** No guard exists. If you point `DATABASE_URL` at a production Supabase instance, the system will happily ingest, rebuild, and modify data.

**Impact:** High safety concern.

**Decision:** Invocation blocking (not startup blocking). The server starts in remote mode and allows read operations (retrieval, context assembly, impact analysis). Write operations are rejected at call time unless `ALLOW_REMOTE_WRITES=true`. This enables read-only remote deployments for retrieval-only agents.

**Implementation approach:** A guard function (e.g., `_check_remote_write_allowed(settings)`) called at the top of each write-path MCP tool handler in `server.py`. For the 2 fire-and-forget writes embedded in `run_retrieval_workflow` (`persist_route_execution` and `_persist_auto_feedback`), the guard is checked inside `retrieval.py` using the `settings` parameter already passed to `run()` — if remote + no write permission, these writes are skipped silently.

**Write-path MCP tools requiring guards (13 total):**

| Tool | Write Type |
|---|---|
| `register_repository` | INSERT repository |
| `run_repo_ingestion_workflow` | Bulk INSERTs to all 3 DBs |
| `run_repair_rebuild_workflow` | Destructive re-projection |
| `rebuild_revision_workflow` | Destructive re-projection |
| `run_embedding_backfill` | Qdrant INSERTs |
| `run_integrity_audit_workflow` | Job manifest INSERT |
| `run_learned_memory_proposal_workflow` | INSERT learned record |
| `run_learned_memory_commit_workflow` | UPDATE learned record + projections |
| `create_working_session` | INSERT session |
| `record_working_observation` | INSERT observation |
| `end_working_session` | UPDATE session |
| `submit_route_feedback` | INSERT feedback |
| `import_repo_memory_tool` | Bulk INSERTs |

**Plus 2 embedded writes in `retrieval.py`:**
- `persist_route_execution` (INSERT route_executions)
- `_persist_auto_feedback` (INSERT route_feedback)

**Files affected:**
- `config.py` — add `allow_remote_writes`
- `server.py` — guard checks in 13 write-path MCP tool handlers (or a shared guard helper)
- `workflows/retrieval.py` — conditional skip for route execution + auto-feedback writes

### Gap 3: No Remote Rebuild Guard

**Requirement:** `ALLOW_REMOTE_REBUILDS=true` must be set separately from write permission before destructive operations.

**Current state:** No guard. `run_repair_rebuild_workflow` and `run_embedding_backfill` will happily wipe and recreate projections against any target.

**Impact:** High safety concern for production. These workflows delete/deactivate Qdrant points and Neo4j nodes in bulk.

**Implementation approach:** Guard checks in the MCP tool handlers in `server.py` for the 3 destructive tools: `run_repair_rebuild_workflow`, `rebuild_revision_workflow`, `run_embedding_backfill`. The guard fires before the workflow is called — the workflow files themselves don't need changes.

**Files affected:**
- `config.py` — add `allow_remote_rebuilds`
- `server.py` — guard checks in 3 destructive MCP tool handlers

### ~~Gap 4: Supabase Direct vs Pooled Connection Support~~ — ELIMINATED

**Decision:** Supabase Free tier (60 direct connections) with single `DATABASE_URL` pointing at direct connection (port 5432). No pooled connection logic needed. The asyncpg pool defaults to `max_size=20`, well within the 60 connection limit. Pooled support can be added later if scaling to Pro tier.

**No implementation needed.**

### Gap 5: No Qdrant HTTPS/gRPC Configuration — SKIP

**Impact:** None. The existing `qdrant_url` + `qdrant_api_key` fields already work for both local and Qdrant Cloud. The `AsyncQdrantClient` library handles HTTPS automatically based on URL scheme.

### Gap 6: No Neo4j Encrypted Connection Support — SKIP

**Impact:** None. The Neo4j Python driver handles encryption via URI scheme (`neo4j+s://`). No code change needed.

**Note:** APOC plugin is loaded in `docker-compose.yml` (`NEO4J_PLUGINS: '["apoc"]'`) but is **not used anywhere in application code** — zero APOC calls in `src/`. It can be safely removed from the Docker image and is not a concern for Neo4j Aura compatibility.

### Gap 6b: Docker Compose Blocks Remote Mode

**Requirement:** In remote mode, the server should start without local database containers.

**Current state:** `docker-compose.yml` lines 17-23 have hard `depends_on` with `service_healthy` conditions on all three local database services. If you try to `docker compose up server` pointed at remote databases, Compose will refuse to start the server until the local containers are healthy.

**Impact:** Operational blocker for remote mode when running via Docker Compose.

**Implementation approach:** Use Docker Compose profiles. Tag the DB services with `profiles: ["local"]`:
- Local mode: `docker compose --profile local up` — starts everything
- Remote mode: `docker compose up server` — starts only the server, connects to remote DBs

**Files affected:** `docker-compose.yml`

### Gap 7: No Startup Mode Summary

**Requirement:** Structured log at startup showing mode, effective config per DB, masked secrets.

**Current state:** Startup logs individual "postgres_connected", "qdrant_connected", "neo4j_connected" messages. No unified summary. No mode display. No secret masking.

**Impact:** Low effort, high operational value.

**Files affected:**
- `server.py` — add startup summary after all DBs connect

### Gap 8: No Environment Fingerprinting

**Requirement:** Fetch and log a harmless fingerprint per DB at startup (PG version, Qdrant version, Neo4j version) to catch accidental cross-environment connections.

**Current state:** No fingerprinting.

**Impact:** Low effort. Add version queries to the startup sequence.

**Files affected:**
- `server.py` or `db/health.py` — add version fetch per DB

### Gap 9: No Example Env Files for Remote

**Requirement:** `.env.local.example` and `.env.remote.example`.

**Current state:** Single `.env.example` with local Docker values.

**Impact:** Documentation task.

### Gap 10: Docker Compose Hardcoded Paths

**Current state:** `docker-compose.yml` has hardcoded macOS paths for repo mounts. Fine for current single-developer setup.

**Impact:** Not blocking. Defer.

### Gap 11: Azure Key Vault for DB Secrets

**Requirement:** DB connection secrets (DATABASE_URL, QDRANT_API_KEY, NEO4J_PASSWORD) should be sourced from Azure Key Vault, not plaintext env vars.

**Current state:** The codebase has existing Azure Key Vault integration in `credential_refresh.py` for Codex OAuth tokens (`seed_from_keyvault`, `writeback_to_keyvault`). This uses `azure-identity` and `azure-keyvault-secrets` which are already declared as dependencies in `pyproject.toml`. However, the KV integration is hardcoded to a single secret name (`cli-auth-codex`) and only handles Codex auth file format.

**Implementation approach:**
- Extract a generic `fetch_kv_secret(vault_name, secret_name) -> str` helper from the existing KV code
- Add new KV secret names to config: `kv_postgres_secret_name`, `kv_qdrant_secret_name`, `kv_neo4j_secret_name`
- In `app_lifespan()`, before calling `init_postgres`/`init_qdrant`/`init_neo4j`, seed DB secrets from KV into `os.environ` (or directly into the Settings object)
- The existing `DefaultAzureCredential` and `_StaticTokenCredential` patterns in `credential_refresh.py` can be reused

**Impact:** Medium. ~40-60 lines of new code plus config fields. The KV client scaffolding exists but needs to be generalized.

**Files affected:**
- `auth/credential_refresh.py` — extract generic KV helper
- `config.py` — add KV secret name fields
- `server.py` — seed DB secrets from KV before DB init

## 3. What Does NOT Need to Change

| Component | Why It's Fine |
|---|---|
| All 8 workflow `run()` functions | Receive clients as parameters — don't create connections |
| All 50+ projection/integrity functions | Same — receive clients as params |
| MCP tool handlers in server.py | Call `get_pg_pool()` etc. — will get whatever pool was initialized |
| Health checks | Already test all 3 DBs generically |
| Job dispatcher | Receives pool at `start()`, passes to workers |
| Alembic migrations | Already reads `DATABASE_URL` from env. Uses synchronous SQLAlchemy (not asyncpg) so pooled-connection issues don't apply. Just needs `sslmode=require` for remote. |
| Codex MCP client | Independent of DB layer |
| All test files | Mock DB connections, don't create real ones |

**The entire application layer (workflows, projections, admin, integrity) requires ZERO changes.** Only the infrastructure layer (config, db/, server startup) needs modification.

## 4. Impact Matrix

| Gap | Effort | Risk if Skipped | Files | Priority |
|---|---|---|---|---|
| 1. Mode switch | Low | Medium — no visibility | config.py, server.py | 1 |
| 2. Remote write guard | Low-Medium | **Critical** — accidental writes | config.py, server.py, retrieval.py | 1 |
| 3. Remote rebuild guard | Low | **Critical** — accidental data wipe | config.py, server.py | 1 |
| 6b. Docker Compose profiles | Low | **High** — server won't start in remote mode | docker-compose.yml | 1 |
| 11. Azure KV for DB secrets | Medium | Medium — plaintext secrets in env | credential_refresh.py, config.py, server.py | 2 |
| 7. Startup summary | Low | Low — operational blindness | server.py | 2 |
| 8. Environment fingerprint | Low | Low — accidental cross-env | server.py | 3 |
| 9. Example env files | Low | Low — onboarding friction | New files | 3 |
| ~~4. Supabase direct/pooled~~ | ~~Eliminated~~ | — | — | — |
| 5. Qdrant HTTPS/gRPC | Skip | None | — | — |
| 6. Neo4j encrypted | Skip | None | — | — |
| 10. Docker paths | Low | Low | docker-compose.yml | Defer |

## 5. Implementation Scope Assessment

### Minimum Viable Remote Support (Priority 1)

1. **Add `DATA_MODE` + per-DB mode overrides to config.py** (~30 lines)
2. **Add `ALLOW_REMOTE_WRITES` + `ALLOW_REMOTE_REBUILDS` to config.py** (~10 lines)
3. **Add write guard helper + checks in 13 write-path MCP handlers** (~30 lines)
4. **Add rebuild guard checks in 3 destructive MCP handlers** (~10 lines)
5. **Add conditional write skip in retrieval.py** for route execution + auto-feedback (~10 lines)
6. **Add startup mode summary logging** (~25 lines)
7. **Add Docker Compose profiles** (~15 lines of yaml changes)

**Total: ~130 lines of config/validation code + compose changes. Zero workflow changes.**

### Full Implementation (All Priorities)

Add Azure KV secret seeding, env fingerprinting, example env files. ~200-220 lines total plus documentation.

## 6. Decisions Made

| Question | Decision | Impact |
|---|---|---|
| Supabase plan | Free tier (500 MB, 60 direct connections) | Single direct connection string, no pooled logic needed. Gap 4 eliminated. |
| Qdrant Cloud | Free tier (1 GB) | URL + API key, already supported. No code changes. |
| Neo4j Aura | Free tier (200K nodes) | URI scheme handles encryption. APOC not used in code. No code changes. |
| Guard approach | Invocation blocking | Server starts in remote mode. Read operations work. Write operations rejected unless `ALLOW_REMOTE_WRITES=true`. Auto-feedback skipped silently in read-only remote. |
| Secrets management | Azure Key Vault | Extend existing KV integration to pull DB secrets at startup. New Gap 11. |

## 7. Risk Assessment

### Low Risk
- Mode switch concept (additive config, no behavior change)
- Startup logging (observability only)
- Example env files (documentation)

### Medium Risk
- Azure KV integration (new code but established pattern in codebase)

### Managed Risk
- Write/rebuild guards (safety nets, fail-closed design)

### No Risk
- Qdrant Cloud switch (URL + API key, already supported)
- Neo4j Aura switch (URI scheme handles encryption)

## 8. Open Questions

1. **Supabase connection string format:** Need the actual Supabase project URL and connection string to configure. What is the project ref?

2. **Qdrant Cloud cluster URL:** Need the cluster URL and API key for remote config.

3. **Neo4j Aura instance URI:** Need the Aura connection URI and credentials.
