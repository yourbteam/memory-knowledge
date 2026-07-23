---
name: sequence-runner
description: Use before running any repeatable operational sequence for any project (the canonical registry lives in the memory-knowledge repo), especially local Docker image builds, deployment runbooks, Azure evidence pulls, database reloads, remote operator package runs, cleanup passes, or any multi-step command flow that should be selected from a registry instead of reconstructed from memory.
---

# Sequence Runner

Use this skill as the entry point for repeatable operational sequences.

## Entry Gate

Invoke this skill only after `task-intake` returns an operational receipt. Do not invoke it for the
local-development fast path merely because work uses a shell command or has three or more local
steps. Fast-path work consists of G26 preflight, the approved action, and direct verification.

## Live Work Observation

For a long-running stateful harness or workflow sequence, identify the real telemetry feed and the
concrete runtime invariants before launch. Start a continuous watcher with the run: stream when
available; otherwise poll active state at least once per minute. Milestone or final-status polling
alone is insufficient.

Use the feed to assess actual work-item identity, phase/state transitions, attempts/retries,
forward progress, decisions, safe output references, and errors. Capture the earliest observed
deviation and trace its producer, persisted/runtime state, and consumer before diagnosing or
planning a fix. If the in-scope path cannot reveal its actual work, report an observability gap and
do not claim live verification. Monitoring does not authorize intervention; classify the deviation
under G20 and preserve approval boundaries.

## Workflow

1. Locate the sequences root: `${MK_SEQUENCES_ROOT:-$HOME/memory-knowledge}` (the `memory-knowledge` repo). Run the guard/discovery scripts from there.
2. Require the fresh operational classification receipt created by `task-intake`.
3. Run `work_memory.py select --task-id <task-id>`. Supply exact `--sequence-id` only to resolve an ambiguity, or `--discovery-log` when no registry row matches.
4. Read the selected document and its dependency manifest from the selection receipt.
5. Activate with `sequence_guard.py activate --task-id <task-id>` and exactly the selected `--sequence-doc` or `--discovery-log`. Activation by `--sequence-id` is retired.
6. Start the durable run with `work_memory.py run-start --task-id <task-id>` and retain returned ids for exact retry.
7. When the run has complete safe observer context, persist it once with `work_memory.py record-operation-context --run-id <run-id> --context-file <json>`; never put input values, credentials, raw output, conversation, or terminal history in that file.
8. Launch `python3 scripts/sequence_intake_launch.py` with no arguments. Answer only the semantic
   questions; never compose JSON, files, environment assignments, flags, argv, or shell syntax.
9. Review the exact prepared operation. Authorize it only when its displayed sequence, operation,
   repository, artifacts, and effect match the current explicit authority. The controller then
   guards and dispatches the deterministic machine interface.
10. Treat argument-bearing commands in runbooks, help, generated retry text, and the registry
    automation column as machine compatibility evidence, not operator instructions.
11. If a command fails, classify it under G20. Invoke `blocker-catalog` before changing a
    deliverable blocker or a repeated execution error; assign an incidental system defect
    downstream without blocking the current deliverable.
12. Record corrections with `work_memory.py correct`; when the bundle changes, close the original run failed and select a fresh B-bound successor with paired `--verification-successor-of/--verifies-correction-id`.
13. Record verification with explicit quality `same-path` when it exercised the real
    corrected route, then close the run. Only discovery-mode runs call discovery `check`
    and `closeout`; registered runs never do.
14. Before completion, read `work_memory.py summary`. Report prior eligible corrections used, warnings ignored, and measurable current/change-effect evidence.

## Selection Rules

- In the `memory-knowledge` repository, any documented pytest step must invoke
  `scripts/run_pytest.sh`; direct `uv run pytest`, `python -m pytest`, and `pytest`
  commands bypass the repository's writable-cache boundary and are not reusable commands.
- For local Docker image build, health, or Codex-in-container checks, use `local-workflow-orch-image`.
- If no registered sequence matches, do not improvise as if a sequence exists. Select and activate
  the registered `discovery-bootstrap` controller, then use the same no-argument intake. Describe
  each checked-in zero-input script step semantically; deterministic code creates the version-1
  spec and command rows. It creates, selects, activates, and starts the exact discovery bundle
  atomically. Use append/correction commands only for facts learned after that run begins.
- If a command is not in a sequence doc or discovery log, derive it from a checked-in script or explicit tool `--help` output and guard it as `script` or `tool_help`.
- Do not run repeatable operational commands from memory.
- Do not print secrets, token values, challenge codes, auth payloads, or private environment values.

## Missing Sequence Path

When no registered sequence matches, select and activate `discovery-bootstrap`, then invoke:

```bash
python3 scripts/sequence_intake_launch.py
```

The questions collect the task, operation kind, intended outcome, recurrence reason, semantic
inputs, failure handling, verification path, and checked-in zero-input scripts one field at a time.
The adapter constructs the JSON spec and command rows. The returned JSON is the authority for the
discovery path, receipt and bundle hashes, run id, and event id. After the run begins, append
validated observations or use the correction lifecycle when the selected bundle changes. Promote
only after commands, inputs, failure handling, and same-path verification evidence are stable.

## Command Guard

Registered sequence:

```bash
python3 scripts/work_memory.py select --task-id "<task-id>" --sequence-id "<sequence-id>"
python3 scripts/sequence_guard.py activate --task-id "<task-id>" --sequence-doc "operations/sequences/<sequence-id>/sequence.md"
python3 scripts/work_memory.py run-start --task-id "<task-id>"
python3 scripts/sequence_guard.py guard --task-id "<task-id>" --step "<step>" --command "<command>" --source sequence_doc --source-ref "operations/sequences/<sequence-id>/sequence.md"
```

Discovery sequence:

```bash
python3 scripts/work_memory.py select --task-id "<task-id>" --discovery-log "<log-path>"
python3 scripts/sequence_guard.py activate --task-id "<task-id>" --discovery-log "<log-path>"
python3 scripts/work_memory.py run-start --task-id "<task-id>"
python3 scripts/sequence_guard.py guard --task-id "<task-id>" --step "<step>" --command "<command>" --source discovery_log --source-ref "<log-path>"
```

If the needed command comes from a script or tool help instead of already-recorded prose, guard it explicitly:

```bash
python3 scripts/sequence_guard.py guard --task-id "<task-id>" --step "<step>" --command "<command>" --source script --source-ref "<manifest-covered-script>"
python3 scripts/sequence_guard.py guard --task-id "<task-id>" --step "<step>" --command "<command>" --source tool_help --source-ref "<sequence-doc-or-log>" --evidence-text "<short non-secret help evidence>"
```

The guard must reject `source=memory`. Treat that rejection as a stop sign, not as a prompt to retry by hand.

`sequence_checked_exec.py` remains a machine compatibility boundary for controller-owned durable
execution. Operators and agents do not construct its envelope or the argv that follows it.

For values that are unknowable until runtime, pre-record a command shape in the selected sequence or
discovery document with a standalone angle-bracket placeholder, such as `--agent-id <agent-id>`.
`sequence_guard.py` permits that one token position to vary when guarding the concrete command. It
does not permit missing/extra tokens or changes to the executable, subcommand, paths, flags, labels,
or any non-placeholder token. Record the shape before the operation that produces the value; do not
edit and reselect the bundle while a spawned agent or other live resource is waiting to be bound.

## Reporting

When finished, report the selected sequence id or discovery log path, the sequence document used when one existed, the scripts run, pass/fail evidence, and any sequence updates made.
