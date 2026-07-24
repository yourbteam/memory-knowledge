# Greenfield Recreate-Resume Sequence

<!-- BEGIN SEMANTIC INTAKE ENTRYPOINT -->
## Operator entry point

After selecting and activating this registered sequence, launch the shared controller with no
arguments:

```bash
python3 scripts/sequence_intake_launch.py
```

Answer only the semantic questions shown. Every question includes its response format, an example,
and constraints. The controller derives JSON, files, environment, flags, and argv; displays the
exact prepared operation; and requires a separate yes/no authorization before guarded dispatch.

Any argument-bearing commands below are machine-compatibility and verification evidence for the
deterministic adapter. Operators and agents must not construct or invoke those forms directly.
<!-- END SEMANTIC INTAKE ENTRYPOINT -->

## Purpose

Resume a **halted greenfield N3 program** on a **freshly RECREATED** local container in one command,
restoring every runtime credential/config that a `docker rm && docker run` wipes.

The durable stage-resume ([[gf-n3-dag-stage-resume]]) survives a `docker restart` (which keeps the
container's `/tmp`) for free. A **recreate** (`docker rm` + `docker run`, e.g. after an image rebuild)
creates a fresh writable layer, so `/tmp` and every runtime secret/config are gone. The durable PROGRAM
state is safe (it lives in the `yourbteam/lakmus-runtime` artifact repo, re-fetched on demand), but the
resume drive fails one restored-credential blocker at a time unless they are all restored first. This
sequence encodes that restoration so a recreate-resume is one command, not an afternoon of whack-a-mole.

## Use This Sequence When

- A greenfield N3 program halted and you need to resume it AFTER a container recreate (image rebuild,
  `docker rm`, or a fresh machine) — you have its `--program-drive-id` and `--decomposition-task-id`.
- You just rebuilt the `workflow-orch` image (carrying an engine fix) and must resume the same program.

## Do Not Use This Sequence When

- You only did a `docker restart` (state survives; `greenfield_resume_dag.py` alone is enough).
- You are starting a NEW program from a spec — use `greenfield-full-drive` instead.

## Steps (the script runs these in order; each fails loud, no secret is printed)

1. **Preflight** — docker up; host `az` logged in (needed to pull KV secrets).
2. **(optional) `--rebuild`** — build the image via `local-workflow-orch-image` (disk preflight/prune inside).
3. **Heal the durable operator env** (`ensure_local_operator_env.py`) — JWT + WS_URL + the static
   artifact-repo keys (`WORKFLOW_ORCH_ARTIFACT_REPO_ENABLED=true`,
   `WORKFLOW_ORCH_ARTIFACT_REPO_BRANCH_MODE=task_branch`, `WORKFLOW_ORCH_MEMORY_KNOWLEDGE_ENABLED=true`).
   Merges missing keys into an existing env file.
4. **Seed the MK bearer token** (`MEMORY_KNOWLEDGE_MCP_API_KEY`) from KV `hrness` into the env file if
   absent (else driveDag → `MEMORY_KNOWLEDGE_AUTH_UNAVAILABLE`).
5. **Recreate the container** from the full-config env file (`harness run --env-file`).
6a. **Reseed codex OAuth** from KV `hrness` (the review/producer stages call codex; a recreate wipes
   it, else review → `PROVIDER_PREFLIGHT_FAILED` codex 401 "Missing bearer").
6b. **Reseed git App auth** for BOTH the artifact repo (`yourbteam/lakmus-runtime`) AND the feature repo,
   KV `hrness`, restart after the last (else resume → `TASK_BRANCH_PROGRAM_STORE_REQUIRED`).
7. **Warm the artifact-repo clone (single-branch)** — removes any broken partial `/home/lakmus-runtime`
   then clones `--single-branch main` (~1s). No-op once `artifact_repository._clone` ships the
   `--single-branch` fix; required for an image built before it.
8. **Resume the DAG** (`greenfield_resume_dag.py`) — runs DETACHED server-side.

## Run

```bash
# From mcp-agents-workflow. Resume a halted program (image already built):
scripts/greenfield_recreate_resume.sh \
  --repo github:thebteambg/supermariobros \
  --program-drive-id <program-drive-id> \
  --decomposition-task-id mawf-task-<...> \
  --start-feature-index 0 --parallel-width 1

# After an engine change, rebuild first:
scripts/greenfield_recreate_resume.sh --rebuild --repo github:<owner>/<repo> \
  --program-drive-id <id> --decomposition-task-id mawf-task-<...>
```

## Inputs

- `--program-drive-id` (required) — the halted program's drive id.
- `--decomposition-task-id` (required) — the program's decomposition task (`mawf-task-…`), which owns
  the durable program tree in lakmus-runtime.
- `--repo` (required) — `github:<owner>/<repo>` of the FEATURE repo being built.
- Optional: `--rebuild`, `--container`, `--tag`, `--port`, `--keyvault`, `--start-feature-index`,
  `--parallel-width`, `--expected-spec-hash`.

## Pass Signal

- Script prints `[ok] recreate-resume launched; the DAG program drive runs detached server-side.`
- `docker logs <container>` shows `greenfield N3-DAG: starting feature feat-<k>` and, for an adopted
  feature, `greenfield N3: adopting deterministic claimed run <run> for <stage>` (durable stage
  adoption) — NOT `work branch unresolvable`.

## Failure Handling / Gotchas

- **`work branch unresolvable (fast+durable)`** — the finder must query origin by authed `ls-remote`,
  not a single-branch base clone (fixed in `mcp_server._greenfield_find_pushed_work_branch_by_task`).
- **`MEMORY_KNOWLEDGE_AUTH_UNAVAILABLE`** — step 4 (MK token) did not run; ensure host `az` is logged in.
- **`TASK_BRANCH_PROGRAM_STORE_REQUIRED`** — artifact-repo env keys missing (step 3).
- **WS `1011` / `pathspec 'main' did not match`** — a broken partial `/home/lakmus-runtime` from a
  timed-out clone; step 7 removes it first. Never run a competing clone into that path while the server
  is up.
- **Clone times out at 300s** — the artifact repo has one branch PER TASK (242+); a non-single-branch
  clone drags them all. Requires the `_clone --single-branch` fix; step 7 warms it meanwhile.
