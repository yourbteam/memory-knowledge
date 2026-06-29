---
name: sequence-runner
description: Use before running any repeatable operational sequence for any project (the canonical registry lives in the memory-knowledge repo), especially local Docker image builds, deployment runbooks, Azure evidence pulls, database reloads, remote operator package runs, cleanup passes, or any multi-step command flow that should be selected from a registry instead of reconstructed from memory.
---

# Sequence Runner

Use this skill as the entry point for repeatable operational sequences.

## Workflow

1. Locate the sequences root: `${MK_SEQUENCES_ROOT:-$HOME/memory-knowledge}` (the `memory-knowledge` repo). Run the guard/discovery scripts from there.
2. Read `operations/sequences/SEQUENCES.md` under that root. A row's `automation` is `<repo-key>:<path>` — resolve the script in that repo (e.g. `mcp-agents-workflow:…`, `taggable-api:…`).
3. Pick exactly one matching sequence row by use case.
4. Read that sequence folder's `sequence.md`.
5. Activate the selected sequence with `scripts/sequence_guard.py activate`.
6. Before every operational command in the sequence, run `scripts/sequence_guard.py guard`.
7. Only run commands whose guard source is `sequence_doc`, `discovery_log`, `script`, or `tool_help`.
8. Run the documented script commands instead of inventing equivalent commands.
9. If a command fails, report the failed step and exact error, then follow the sequence document's failure handling.
10. If the run exposes a missing reusable step, update the sequence document or script before calling the sequence complete.

## Selection Rules

- For local Docker image build, health, or Codex-in-container checks, use `local-workflow-orch-image`.
- If no registered sequence matches, do not improvise as if a sequence exists. Create a discovery log under `operations/sequences/discovery/` before or during execution, then append validated steps as they are discovered.
- If a command is not in a sequence doc or discovery log, derive it from a checked-in script or explicit tool `--help` output and guard it as `script` or `tool_help`.
- Do not run repeatable operational commands from memory.
- Do not print secrets, token values, challenge codes, auth payloads, or private environment values.

## Missing Sequence Path

When no registered sequence matches, run:

```bash
uv run python scripts/sequence_discovery_log.py start --sequence-name "<short name>" --outcome "<intended outcome>" --why-repeatable "<why this will likely recur>"
```

Then append each real step that was executed or validated:

```bash
uv run python scripts/sequence_discovery_log.py append-step --file <log-path> --step "<step>" --command "<command or action>" --result "<result>" --note "<correction or note>"
```

Use the discovery log as raw evidence. Promote it to `operations/sequences/<sequence-id>/sequence.md` only after the commands, required inputs, failure handling, and verification evidence are stable.

## Command Guard

Registered sequence:

```bash
uv run python scripts/sequence_guard.py activate --sequence-id "<sequence-id>" --sequence-doc "operations/sequences/<sequence-id>/sequence.md"
uv run python scripts/sequence_guard.py guard --step "<step>" --command "<command>" --source sequence_doc --source-ref "operations/sequences/<sequence-id>/sequence.md"
```

Discovery sequence:

```bash
uv run python scripts/sequence_guard.py activate --sequence-id "<sequence-name>" --discovery-log "<log-path>"
uv run python scripts/sequence_guard.py guard --step "<step>" --command "<command>" --source discovery_log --source-ref "<log-path>"
```

If the needed command comes from a script or tool help instead of already-recorded prose, guard it explicitly:

```bash
uv run python scripts/sequence_guard.py guard --step "<step>" --command "<command>" --source script --source-ref "scripts/<script>.py"
uv run python scripts/sequence_guard.py guard --step "<step>" --command "<command>" --source tool_help --source-ref "<sequence-doc-or-log>" --evidence-text "<short non-secret help evidence>"
```

The guard must reject `source=memory`. Treat that rejection as a stop sign, not as a prompt to retry by hand.

## Reporting

When finished, report the selected sequence id or discovery log path, the sequence document used when one existed, the scripts run, pass/fail evidence, and any sequence updates made.
