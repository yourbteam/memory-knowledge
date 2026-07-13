---
name: sequence-runner
description: Use before running any repeatable operational sequence for any project (the canonical registry lives in the memory-knowledge repo), especially local Docker image builds, deployment runbooks, Azure evidence pulls, database reloads, remote operator package runs, cleanup passes, or any multi-step command flow that should be selected from a registry instead of reconstructed from memory.
---

# Sequence Runner

Use this skill as the entry point for repeatable operational sequences.

## Workflow

1. Locate the sequences root: `${MK_SEQUENCES_ROOT:-$HOME/memory-knowledge}` (the `memory-knowledge` repo). Run the guard/discovery scripts from there.
2. Require the fresh operational classification receipt created by `task-intake`.
3. Run `work_memory.py select --task-id <task-id>`. Supply exact `--sequence-id` only to resolve an ambiguity, or `--discovery-log` when no registry row matches.
4. Read the selected document and its dependency manifest from the selection receipt.
5. Activate with `sequence_guard.py activate --task-id <task-id>` and exactly the selected `--sequence-doc` or `--discovery-log`. Activation by `--sequence-id` is retired.
6. Start the durable run with `work_memory.py run-start --task-id <task-id>` and retain returned ids for exact retry.
7. Before every operational command, run `sequence_guard.py guard --task-id <task-id>`.
7. Only run commands whose guard source is `sequence_doc`, `discovery_log`, `script`, or `tool_help`.
8. Run the documented script commands instead of inventing equivalent commands.
9. If a command fails, invoke `blocker-catalog` before changing anything, then follow documented failure handling.
10. Record corrections with `work_memory.py correct`; when the bundle changes, close the original run failed and select a fresh B-bound successor with paired `--verification-successor-of/--verifies-correction-id`.
11. Record verification with explicit quality `same-path` when it exercised the real
    corrected route, then close the run. Only discovery-mode runs call discovery `check`
    and `closeout`; registered runs never do.
12. Before completion, read `work_memory.py summary`. Report prior eligible corrections used, warnings ignored, and measurable current/change-effect evidence.

## Selection Rules

- For local Docker image build, health, or Codex-in-container checks, use `local-workflow-orch-image`.
- If no registered sequence matches, do not improvise as if a sequence exists. Create a discovery log under `operations/sequences/discovery/` before or during execution, then append validated steps as they are discovered.
- If a command is not in a sequence doc or discovery log, derive it from a checked-in script or explicit tool `--help` output and guard it as `script` or `tool_help`.
- Do not run repeatable operational commands from memory.
- Do not print secrets, token values, challenge codes, auth payloads, or private environment values.

## Missing Sequence Path

When no registered sequence matches, run:

```bash
python3 scripts/sequence_discovery_log.py start --sequence-name "<short name>" --outcome "<intended outcome>" --why-repeatable "<why this will likely recur>"
```

Then append each real step that was executed or validated:

```bash
python3 scripts/sequence_discovery_log.py append-step --file <log-path> --step "<step>" --command "<command or action>" --result "<result>" --note "<correction or note>"
```

Use the discovery log as raw evidence. Promote it to `operations/sequences/<sequence-id>/sequence.md` only after the commands, required inputs, failure handling, and verification evidence are stable.

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

For values that are unknowable until runtime, pre-record a command shape in the selected sequence or
discovery document with a standalone angle-bracket placeholder, such as `--agent-id <agent-id>`.
`sequence_guard.py` permits that one token position to vary when guarding the concrete command. It
does not permit missing/extra tokens or changes to the executable, subcommand, paths, flags, labels,
or any non-placeholder token. Record the shape before the operation that produces the value; do not
edit and reselect the bundle while a spawned agent or other live resource is waiting to be bound.

## Reporting

When finished, report the selected sequence id or discovery log path, the sequence document used when one existed, the scripts run, pass/fail evidence, and any sequence updates made.
