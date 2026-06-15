# TPP Petkey Onboarding Rollout Analysis

## Task Objective

Onboard the local repository `tpp-petkey` into memory-knowledge locally first, validate the resulting repository memory, then export the repository-scoped PostgreSQL-backed memory artifact and import it into the remote PostgreSQL store, followed by the necessary rebuild/projection steps and remote smoke verification.

## Task Type And Size

- Type: `rollout`
- Secondary concerns: `migration`, `workflow/process`
- Size: `heavy`

This is heavy because it spans local onboarding, remote data movement, environment switching, and remote-state verification. Mistakes can pollute the remote memory store or produce a misleading partial rollout.

## Grounding Requirements

- Repository:
  - memory-knowledge: `/Users/kamenkamenov/memory-knowledge`
  - target repo: `/Users/kamenkamenov/tpp-petkey`
- Environment:
  - isolated local onboarding environment
  - current remote-backed environment
- Remote systems:
  - remote PostgreSQL
  - remote Qdrant
  - remote Neo4j

## Current-State Facts

- The target repo exists locally at `/Users/kamenkamenov/tpp-petkey`.
- Its origin is `https://github.com/thebteambg/tpp-petkey.git`.
- The previous rollout analysis captured `master` / `660bad2e58d8611ac9f68b0c18621a09a9d559e0`, which is no longer the desired ingestion source.
- The required ingestion source is the `main` branch; resolve and record the current `main` HEAD immediately before running ingestion.
- The stable repository identifier to use through registration, ingestion, export, and import is `repository_key: "tpp-petkey"`.
- The repo appears to be primarily C# / SQL based from the top-level layout:
  - `Api.Tpp`
  - `Web.Admin`
  - `Web.Km`
  - `Web.PartnerApi`
  - `Database`
  - multiple console apps and shared libraries
- The current `memory-knowledge` `.env` is pointed at remote infrastructure, not a local stack:
  - `DATA_MODE=remote`
  - remote `DATABASE_URL`
  - remote `QDRANT_URL`
  - remote `NEO4J_URI`
- `ALLOW_REMOTE_WRITES=true` is currently enabled in the active env, which increases the risk of accidental remote writes if local onboarding is attempted without isolating configuration.
- `ALLOW_REMOTE_REBUILDS=true` is also enabled in the active env, which increases the risk of accidental destructive rebuild/repair operations against remote infrastructure.
- `repo_clone_base_path` defaults to `/tmp/memory-knowledge/repos`.
- `MAX_IMPORT_SIZE_MB` in the active env is `200`.

## Relevant Existing Surfaces

### Onboarding / ingestion

- `register_repository`
- `run_repo_ingestion_workflow`
- `check_job_status`
- `list_repositories`
- `get_memory_stats`
- `run_retrieval_workflow`
- `run_integrity_audit_workflow`

### Export / import

- `export_repo_memory_tool`
- `import_repo_memory_tool`
- `run_repair_rebuild_workflow`

These tools are documented and implemented as repository-scoped memory transfer plus repair/reprojection surfaces.

### Important contract

- Export/import is for repository-scoped PostgreSQL memory and knowledge only.
- Planning tables and other operational state are intentionally out of scope for this pipeline.
- Export/import by itself does not repopulate Qdrant or Neo4j.

## Source Artifacts Inspected

- `docs/remote-rollout-runbook.md` (only partially relevant here; mainly for the export/import scope boundary around planning data)
- `docs/AGENT_INTEGRATION_SPEC.md`
- `src/memory_knowledge/admin/export_import.py`
- `src/memory_knowledge/server.py`
- `.env`
- local git state of `/Users/kamenkamenov/tpp-petkey`

## Constraints

- Local onboarding must not use the current remote-backed env by mistake.
- Local onboarding must not use the current remote-backed env by mistake, especially because both remote writes and remote rebuilds are enabled in the active `.env`.
- The target repo should be ingested at a known branch and commit:
  - `main`
  - the resolved `main` HEAD
- The export artifact must remain within the remote import size limit or the workflow must be adapted before remote import.
- Remote import must be treated as repo-memory transfer, not as a substitute for remote ingestion of operational/planning data.
- Remote import lands PostgreSQL-backed repo memory only; if remote smoke verification is expected to include retrieval, embeddings, or graph-backed behavior, a rebuild/reprojection step is required after import.

## Risks

### Environment-crossing risk

The main risk is accidental direct onboarding or destructive rebuild activity against remote infrastructure because the active env is already remote and both remote writes and remote rebuilds are enabled.

### Existing remote state risk

If `tpp-petkey` already exists remotely, the import path is still additive/upsert-based for the PostgreSQL repo-memory tables. The remaining risk is not basic import semantics, but whether existing remote state quality or conflicts make a purge-and-reseed approach preferable. Purge-and-reseed would be destructive and needs separate handling.

### Export-size risk

`tpp-petkey` may generate a large JSONL export because it is a multi-project .NET repository. The export size must be checked before remote import.

### Partial-validation risk

A successful ingestion job alone is not enough. Local retrieval and memory-stat checks are needed before treating the export as trustworthy.

### Neo4j remote degradation risk

Remote smoke verification may need to distinguish PostgreSQL-backed confirmation from Qdrant/Neo4j-backed confirmation, because export/import alone does not repopulate those stores.

## Unknowns

- Whether `tpp-petkey` is already registered in the remote repository catalog.
- Whether the export size will remain below the configured remote import limit.
- Whether the repo requires any parser/support adjustments to achieve acceptable local ingestion quality.
- Whether a local memory-knowledge stack is already available or must be brought up for this task.
- Whether remote smoke verification should stop at PostgreSQL-backed confirmation or explicitly include retrieval/graph checks after rebuild.

## Recommended Approach

Use a staged rollout:

1. Isolate a local onboarding environment from the current remote env.
2. Register and fully ingest `tpp-petkey` locally.
3. Validate local repository memory with repository listing, memory stats, and retrieval spot checks.
4. Export repository-scoped PostgreSQL memory as JSONL.
5. Switch to the remote env and verify remote preconditions.
6. Import the JSONL artifact into the remote PostgreSQL store.
7. If remote smoke verification is expected to cover retrieval, vector, or graph behavior, run the necessary rebuild/reprojection workflow after import.
8. Run remote smoke verification against the imported and, if needed, rebuilt repository state.

## Rollout Surfaces

- local env/config selection
- local repo clone path alignment
- local ingestion workflow
- local export artifact generation
- remote PostgreSQL import invocation
- optional remote rebuild/reprojection workflow
- remote smoke verification

## Operator Assumptions

- The operator can switch between local and remote environment configuration safely.
- The local repo path `/Users/kamenkamenov/tpp-petkey` is authoritative for grounding branch/origin facts, but ingestion itself operates via `repository_key` and the configured clone base path.
- The repository should be registered consistently as `repository_key: "tpp-petkey"`.
- Remote writes and remote rebuilds should only remain enabled during the phases that actually require them.

--- Analysis Verification Iteration 1 ---
Findings from verifier: 9
FIX NOW: 7 (analysis updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: 2 (no change)
DISMISS: 0 (no change)
