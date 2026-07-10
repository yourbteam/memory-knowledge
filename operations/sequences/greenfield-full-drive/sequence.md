# Greenfield Full Drive Sequence

## Purpose

Run the WHOLE local greenfield end-to-end drive as one reusable command instead of hand-chaining
docker + auth + drive steps from memory. Composes the `local-workflow-orch-image` primitives
(build / run / seed-auth) with operator-env regeneration and the greenfield evaluation/DAG drivers,
with real exit-code checks and a branch-target safety gate.

Automation: `mcp-agents-workflow:scripts/greenfield_full_drive.sh`.

## Use This Sequence When

- Driving a greenfield job (spec → N1 evaluation → N2 decomposition → N3 feature DAG) on the local
  container, e.g. the supermariobros/BT-000023 benchmark.
- Re-driving after an engine change (rebuild image → recreate container → re-drive).
- You need the S1c feature-code merges to target a NON-default branch (keep a benchmark's `main`
  untouched) — pass `--branch <test-branch>` (create it off main first).

## Do Not Use This Sequence When

- Docker is unavailable — report the blocker instead of host-only checks.
- A workflow is currently RUNNING on the container — the script refuses to recreate (health
  `runningWorkflowCount > 0`); wait or stop it first.

## Steps (the script runs these in order; each fails loud)

0. **Preflight** — docker up; env-file + spec present; `docker container/image prune` (RP-068 disk
   guard); free-space report.
1. **Build** — `local_workflow_orch_image_harness.py build --tag <tag>` with a REAL exit-code check
   (never `| tail`, which masked a failed build as success). The Dockerfile retries the flaky
   `playwright install --with-deps chromium` step 3× so a transient CDN hiccup does not sink the build.
2. **Recreate container** — refuse if a workflow is running; `docker rm -f`; harness `run` on the
   requested port; assert the port is the requested one (not a docker-assigned fallback).
3. **Health** — poll `/health` until `status: ok`.
4. **Auth** — `seed-codex-auth` + `seed-git-auth` (Key Vault `hrness`); regenerate the operator env
   for the NEW container JWT secret (`ensure_local_operator_env.py --force`).
5. **Drive** — `greenfield_evaluation_drive.py start --repo <repo> --prompt-file <spec> [--branch X]`
   (N1 auto-chains N2+N3 server-side), or `--drive-dag` to resume the N3 DAG when the universe exists.
6. **Verify** — print health counts + the exact `docker logs` grep to watch, including the
   **branch-target gate**.

## Run

```bash
uv run python scripts/directive_guard.py read --mode "greenfield-full-drive"
uv run python scripts/sequence_guard.py activate --sequence-id greenfield-full-drive \
  --sequence-doc operations/sequences/greenfield-full-drive/sequence.md

# Full drive onto a test branch (benchmark main stays untouched):
scripts/greenfield_full_drive.sh \
  --repo thebteambg/supermariobros \
  --spec /tmp/rtm_mini4_spec.json \
  --branch gf-mergethrough-20260710

# After an engine change but image already built: --skip-build. Resume N3 DAG: --drive-dag.
scripts/greenfield_full_drive.sh --repo <r> --branch <b> --drive-dag
```

## Inputs

- `--repo owner/repo` (required), `--spec <butler-job.json>` (required unless `--drive-dag`),
  `--branch <target>` (optional; S1c merges + per-feature base target it — GF-N3-BRANCH-OVERRIDE).
- `--tag`, `--env-file` (default `~/.workflow-orch/workflow-orch-local-real-mk.env`),
  `--keyvault` (default `hrness`), `--container`, `--port` (default 18082).
- Flags: `--skip-build`, `--skip-auth`, `--no-fresh`, `--drive-dag`.

## Pass Signal

Script prints `[ok] sequence complete`; the drive is detached server-side. Then, BEFORE any S1c
merge, the branch-target gate must hold:

```bash
docker logs <container> 2>&1 | grep -a "program-drive READY"
# must read: "... driving feature-0 (task ...) research-workflow engine-side onto branch '<your --branch>'."
```

If it says `main` when you passed `--branch`, ABORT — the override did not survive N1 resolve-repo
(see backlog GF-N3-BRANCH-OVERRIDE) — and fix before letting any merge run.

## Failure Handling / Gotchas

- **Flaky build** (`playwright install ... returned a non-zero code: 1`): the Dockerfile now retries
  3×. If it still fails after 3, it is a real network/apt issue — re-run the sequence (the retry is
  transparent). NEVER pipe the build through `| tail` (masks the exit code).
- **Port 18082 held**: the harness `run` falls back to a docker-assigned port; the operator env's
  `WORKFLOW_ORCH_WS_URL` is hardcoded to 18082, so the drive can't reach a fallback port. The script
  asserts the requested port and fails if it differs — free 18082 (`docker rm -f` any holder) and retry.
- **Stale MK lease / dedup** (`playbook_active_run`, "deduped to existing task"): a prior drive's MK
  task/lease is reused. Release an orphaned non-expired lease with
  `mcp__memory_knowledge.mawf_release_task_execution_lease` (reason `stale_reclaimed`), or drive a
  FRESH spec (new job id) to avoid dedup. See backlog GF-N3-LEASE-ORPHAN, GF-N3-UNIVERSE-RESUME.
- **New container = new JWT secret**: step 4 regenerates the operator env; skipping it makes the
  drivers fail auth against the new container.
