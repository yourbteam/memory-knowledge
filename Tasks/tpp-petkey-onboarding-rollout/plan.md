# TPP Petkey Onboarding Rollout Plan

## Scope

This task covers:

- preparing an isolated local onboarding path for `tpp-petkey`
- ingesting and validating `tpp-petkey` locally in memory-knowledge
- exporting repository-scoped PostgreSQL-backed memory/knowledge
- importing that export into the remote PostgreSQL store
- running rebuild/reprojection if remote verification needs retrieval/vector/graph behavior
- running smoke verification against the remote-backed deployment

This task does not cover:

- planning-table migration or transfer
- changes to the export/import schema itself
- parser improvements unless they become a blocker during local validation

## Implementation Steps

### 1. Prepare local onboarding environment

- Create or select a local env profile for memory-knowledge with local PostgreSQL, Qdrant, and Neo4j.
- Ensure the active local env is not using the current remote-backed `.env`.
- Ensure the active local env is not inheriting the current remote guard posture:
  - `ALLOW_REMOTE_WRITES=true`
  - `ALLOW_REMOTE_REBUILDS=true`
- Confirm `repo_clone_base_path` behavior.
- Either:
  - place `tpp-petkey` under `/tmp/memory-knowledge/repos/tpp-petkey`, or
  - override only the clone base directory in a controlled way so the repo still resolves at `<repo_clone_base_path>/tpp-petkey`.
- Start the local stack and verify `/health` and `/ready`.

### 2. Register the repository locally

- Register:
  - `repository_key: "tpp-petkey"`
  - `name: "tpp-petkey"`
  - `origin_url: "https://github.com/thebteambg/tpp-petkey.git"`
- Confirm registration via `list_repositories`.

### 3. Run local ingestion

- Submit `run_repo_ingestion_workflow` with:
  - `repository_key: "tpp-petkey"`
  - `commit_sha: "<main HEAD>"`
  - `branch_name: "main"`
- Poll `check_job_status` until terminal success or a classified blocker appears.

### 4. Validate local repository memory

- Run `list_repositories` and confirm:
  - latest branch is `main`
  - latest commit is the selected `main` HEAD
- Run `get_memory_stats("tpp-petkey")`.
- Run a small retrieval smoke set against known code areas via `run_retrieval_workflow`.
- If confidence is still weak, run `run_integrity_audit_workflow("tpp-petkey")` and poll `check_job_status` to terminal completion before using the audit result in the validation decision.

Gate:
Only proceed to export if local ingestion is complete and the local memory looks credible.

### 5. Export local PostgreSQL-backed repo memory

- Run `export_repo_memory_tool("tpp-petkey")`.
- Save the JSONL output to a task-local artifact file.
- Record:
  - line count
  - file size
  - repository key
  - commit/branch tied to the export
- Compare artifact size to the remote import limit.

### 6. Prepare remote import

- Switch to the remote env explicitly.
- Verify the remote service is healthy enough for import.
- Check whether `tpp-petkey` already exists remotely via `list_repositories`.
- Treat the default remote import mode as additive/upsert-based.
- If remote state quality is bad enough that additive import is not acceptable, evaluate destructive cleanup separately.

Gate:
Do not proceed to destructive cleanup without explicit approval and a separate containment step.

### 7. Import into remote PostgreSQL

- Read the export artifact or join the exported `lines` into one newline-delimited UTF-8 string payload.
- Run `import_repo_memory_tool(data=<joined-jsonl-string>)` against the remote-backed server.
- Capture the import result summary and row counts by table where available.

### 8. Rebuild or reproject remote non-PostgreSQL surfaces when needed

- Decide whether remote verification is limited to PostgreSQL-backed confirmation or must include retrieval/vector/graph behavior.
- If remote verification must include retrieval/vector/graph behavior, run the appropriate rebuild/reprojection workflow after import and poll `check_job_status` until terminal completion.
- Use `run_repair_rebuild_workflow` or the narrower rebuild surface that matches the intended verification depth.

Gate:
Do not treat retrieval/graph-backed remote checks as valid until the required rebuild/reprojection step has completed successfully.

### 9. Run remote smoke verification

- Verify `/health`.
- Verify `/ready`.
- Run PostgreSQL-backed checks:
  - `list_repositories`
  - `get_memory_stats("tpp-petkey")`
- Confirm the remote repository view reflects:
  - repository key `tpp-petkey`
  - branch `main`
  - commit is the selected `main` HEAD
- If Step 8 was executed, also run:
  - retrieval spot checks via `run_retrieval_workflow`
  - any additional graph/vector checks justified by the rebuild scope

## Affected Files And Artifacts

Likely task artifacts:

- `Tasks/tpp-petkey-onboarding-rollout/analysis.md`
- `Tasks/tpp-petkey-onboarding-rollout/plan.md`
- task-local export artifact path to be created during execution

Likely runtime surfaces:

- local env selection / override files
- local clone path under `/tmp/memory-knowledge/repos`
- local and remote memory-knowledge MCP endpoints
- remote rebuild/reprojection workflows if retrieval-style verification is required

## Dependencies And Sequencing Notes

- Local environment isolation must happen before any onboarding commands.
- Local validation must happen before export.
- Export size verification must happen before remote import.
- Remote import only restores PostgreSQL-backed repo memory.
- Remote rebuild/reprojection must happen after remote import if retrieval/vector/graph verification is required.
- Async integrity-audit or rebuild steps must be polled with `check_job_status` before their outcomes are used as gates.
- Remote state inspection must happen before any destructive remote action.

## Local Rollout Section

- bring up local memory-knowledge dependencies
- confirm local service health
- register `tpp-petkey`
- run local ingestion
- validate locally
- produce export artifact

## Remote Rollout Section

- switch to remote env deliberately
- verify remote service health
- inspect existing remote repository state for `tpp-petkey`
- import repo-memory JSONL into remote PostgreSQL
- run rebuild/reprojection if needed for the chosen smoke depth
- run remote smoke verification

## Smoke Verification Section

### Local

- `list_repositories` includes `tpp-petkey`
- latest commit and branch match expected values
- `get_memory_stats("tpp-petkey")` returns non-empty repo memory
- retrieval spot checks return plausible evidence

### Remote

- `/health` returns OK
- `/ready` is acceptable for rollout continuation
- `list_repositories` includes `tpp-petkey`
- `get_memory_stats("tpp-petkey")` returns imported PostgreSQL-backed memory
- retrieval spot checks succeed only if rebuild/reprojection was executed first

## Rollback Or Containment Notes

- If local onboarding fails, stop before export and fix the local ingestion issue first.
- If export size exceeds the import limit, stop before remote import and choose a different transfer approach.
- If remote import fails, do not assume partial import is safe; inspect returned counts/errors before retrying.
- If remote PostgreSQL import succeeds but retrieval/graph checks fail, treat that as a rebuild/projection problem first, not automatically as an import failure.
- If remote verification fails after import or rebuild, contain the issue by avoiding any further repo-memory writes or rebuilds for `tpp-petkey` until state is understood.
- If destructive remote cleanup becomes necessary, treat it as a separate explicitly approved step.

## Blocker Taxonomy

- `environment blocker`: local stack not available or env isolation unclear
- `implementation blocker`: parser/ingestion failures prevent credible local memory
- `verification blocker`: local or remote smoke checks cannot establish trust
- `access blocker`: missing remote/local credentials or service access
- `external dependency blocker`: local or remote database/vector/graph services unavailable

## Validation Approach

- Validate local service health before local onboarding.
- Validate ingestion success via job polling plus repository/memory checks.
- Validate export by file size and line count.
- Validate remote PostgreSQL import by tool success plus PostgreSQL-backed smoke checks.
- Validate retrieval/graph-backed remote behavior only after rebuild/reprojection.

--- Plan Verification Iteration 1 ---
Findings from verifier: 5
FIX NOW: 2 (plan updated)
IMPLEMENT LATER: 2 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 1 (no change)
DISMISS: 0 (no change)

## Closeout Checklist

- local env isolated from remote
- repository registered locally
- local ingestion completed
- local memory validated
- export artifact created and measured
- remote pre-checks completed
- remote PostgreSQL import completed
- remote rebuild/reprojection completed if required
- remote smoke verification completed
- task artifact updated with execution results
