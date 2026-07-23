# Local Workflow-Orch Image Sequence

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

Build and locally validate the `workflow-orch` Docker image in the same repo before deploying or debugging container-specific runtime behavior. This sequence exists so local image work is not reconstructed from memory.

## Use This Sequence When

- A change affects server startup, container dependencies, CLI auth inside the container, workflow execution inside Docker, or deployment readiness.
- A deployed issue should be reproduced locally before another Azure deploy.
- A task needs proof that the local image exists and can serve `/health`.
- A task needs optional Codex auth seeding, GitHub App auth seeding, and Codex probe evidence inside the image.

## Do Not Use This Sequence When

- The task only needs unit tests and does not depend on container behavior.
- Docker is unavailable and the task has no container-runtime requirement. Report that blocker instead of replacing this sequence with host-only checks.
- The task would write live MAWF rows without first running the explicit `require-real-memory-knowledge --real-memory-knowledge` guard.

## Script

Primary script:

```bash
uv run python scripts/local_workflow_orch_image_harness.py <command>
```

Activate this sequence before running its operational commands:

```bash
uv run python scripts/directive_guard.py read --mode "local-workflow-orch-image"
python3 scripts/work_memory.py classify --task-id "<task-id>" --operation-kind container --repeatable yes --meaningful-steps 3
python3 scripts/work_memory.py select --task-id "<task-id>" --sequence-id local-workflow-orch-image
python3 scripts/sequence_guard.py activate --task-id "<task-id>" --sequence-doc operations/sequences/local-workflow-orch-image/sequence.md
```

Guard commands from this document before running them. Example:

```bash
python3 scripts/sequence_guard.py guard --task-id "<task-id>" --step "Build image" --command "uv run python scripts/local_workflow_orch_image_harness.py build --tag workflow-orch:local-sequence-check" --source sequence_doc --source-ref operations/sequences/local-workflow-orch-image/sequence.md
```

Supported commands are implemented in `scripts/local_workflow_orch_image_harness.py`:

- `build`
- `run`
- `health`
- `copy-code-project`
- `seed-codex-auth`
- `seed-git-auth`
- `probe-codex`
- `logs`
- `stop`
- `require-real-memory-knowledge`

## Inputs

Choose explicit values before running commands:

| input | default for local validation | notes |
| --- | --- | --- |
| image tag | `workflow-orch:local-sequence-check` | Use a task-specific tag when comparing builds. |
| container name | `workflow-orch-local-sequence-check` | Stop/remove this container after evidence is captured. |
| preferred host port | `18082` | Pass this as `--port`; if occupied, the harness falls back to a Docker-assigned host port and reports the actual port. |
| port file | `/private/tmp/workflow-orch-local-sequence-check.port` | Pass this as `--port-file` on `run` and `health` so the health step follows the actual selected port without guessing. |
| env file | `/private/tmp/workflow-orch-local-real-mk.env` | Required for `run`; do not print secret values. |
| Key Vault name | `AZURE_KEYVAULT_NAME` or explicit operator-approved name | Required for `seed-codex-auth` and `seed-git-auth`. |
| code project copy destination | parent directory of the desired checkout path | `copy-code-project` copies `<source basename>` under `--destination`; for `/Users/.../neocurrency-dashboard` to end at `/workspaces/neocurrency-dashboard/neocurrency-dashboard`, pass `--destination /workspaces/neocurrency-dashboard`. |

## Guardable Parameterized Command Shapes

Use these shapes with `source=sequence_doc` when the task needs explicit non-default values:

```bash
uv run python scripts/local_workflow_orch_image_harness.py build --tag <image-tag>
uv run python scripts/local_workflow_orch_image_harness.py run --tag <image-tag> --name <container-name> --port <preferred-host-port> --port-file <port-file> --env-file <env-file>
uv run python scripts/local_workflow_orch_image_harness.py health --port <host-port> --timeout-seconds <timeout-seconds>
uv run python scripts/local_workflow_orch_image_harness.py health --port-file <port-file> --timeout-seconds <timeout-seconds>
uv run python scripts/local_workflow_orch_image_harness.py copy-code-project --container <container-name> --source <source-path> --destination <destination-path>
uv run python scripts/local_workflow_orch_image_harness.py seed-codex-auth --container <container-name> --keyvault-name <keyvault-name>
uv run python scripts/local_workflow_orch_image_harness.py seed-git-auth --container <container-name> --keyvault-name <keyvault-name>
uv run python scripts/local_workflow_orch_image_harness.py probe-codex --container <container-name>
uv run python scripts/local_workflow_orch_image_harness.py logs --container <container-name> --tail <line-count>
uv run python scripts/local_workflow_orch_image_harness.py stop --container <container-name>
uv run python scripts/local_workflow_orch_image_harness.py require-real-memory-knowledge --real-memory-knowledge
docker image inspect <image-tag>
docker image inspect <image-tag> --format '{{.Id}} {{.Size}}'
```

## Minimal Build Verification

Use this when the task only requires proof that the image can be built.

```bash
uv run python scripts/local_workflow_orch_image_harness.py build --tag workflow-orch:local-sequence-check
docker image inspect workflow-orch:local-sequence-check
```

Pass criteria:

- The build command exits `0`.
- The script prints JSON with `"ok": true`.
- `docker image inspect` finds the built image.

## Full Runtime Verification

Use this when the task needs container startup and health evidence.

```bash
uv run python scripts/local_workflow_orch_image_harness.py build --tag workflow-orch:local-sequence-check
uv run python scripts/local_workflow_orch_image_harness.py run --tag workflow-orch:local-sequence-check --name workflow-orch-local-sequence-check --port 18082 --port-file /private/tmp/workflow-orch-local-sequence-check.port --env-file /private/tmp/workflow-orch-local-real-mk.env
uv run python scripts/local_workflow_orch_image_harness.py health --port-file /private/tmp/workflow-orch-local-sequence-check.port --timeout-seconds 180
```

Optional Codex-in-container verification:

```bash
uv run python scripts/local_workflow_orch_image_harness.py seed-codex-auth --container workflow-orch-local-sequence-check --keyvault-name "$AZURE_KEYVAULT_NAME"
uv run python scripts/local_workflow_orch_image_harness.py probe-codex --container workflow-orch-local-sequence-check
```

Required artifact-branch persistence verification for MAWF task-branch runs:

```bash
uv run python scripts/local_workflow_orch_image_harness.py seed-git-auth --container workflow-orch-local-sequence-check --keyvault-name "$AZURE_KEYVAULT_NAME"
```

Run `seed-git-auth` before starting any local workflow that must push task artifacts to the artifact repository. Without it, the container can create local task-worktree commits but cannot publish `task/*` branches, so restart/resume checks are not valid.

Always stop the container after evidence is captured:

```bash
uv run python scripts/local_workflow_orch_image_harness.py stop --container workflow-orch-local-sequence-check
```

Pass criteria:

- Build exits `0`.
- Run exits `0`, returns a container id, reports the actual host `port`, and writes the same value to the port file when `--port-file` is provided.
- If the preferred port is occupied or Docker reports the bind fingerprint, run still exits `0` using a Docker-assigned port; after a bind-failed Docker run, the harness removes only the failed same-name container before retrying, so no manual retry with another guessed port is needed.
- Health exits `0` and returns JSON from `/health` using either the explicit `--port` or the recorded `--port-file`.
- Optional Codex probes exit `0` and each probe has `"ok": true`.
- MAWF task-branch validation runs seed GitHub App auth before workflow start, and a fresh task branch exists on the artifact repository remote before restart/resume is considered proven.
- The container is stopped after evidence unless the active task explicitly needs it running.

## Failure Handling

| failing step | required response |
| --- | --- |
| `build` | Report the exact Docker build error and inspect the Dockerfile or dependency layer that failed. Do not deploy. |
| `run` | Confirm the env file exists and the container name is free. Port occupancy should be recovered by the harness through Docker-assigned fallback; if run still fails, report the exact Docker error. Do not replace this with host-only testing. |
| `health` | Run `logs --container <name> --tail 200`, report the startup failure, and stop the container unless further inspection needs it. |
| `seed-codex-auth` | Report that auth seeding failed without printing token material. Check Azure login and Key Vault access. |
| `seed-git-auth` | Report that GitHub App auth seeding failed without printing token material. Do not claim artifact-branch persistence or restart/resume readiness. |
| `probe-codex` | Report which probe failed and include only non-secret output snippets. |

## Evidence To Report

Report these fields in the final task summary when this sequence is used:

- sequence id: `local-workflow-orch-image`
- image tag
- build result
- health result when run
- Codex probe result when run
- GitHub App auth seed result when artifact persistence is part of the validation
- container cleanup result
- any sequence document or script change made because the run exposed a reusable-process gap
