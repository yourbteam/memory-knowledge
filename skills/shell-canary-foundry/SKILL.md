---
name: shell-canary-foundry
description: Use when creating or auditing shell-based workflow phase canaries and threaded canary wrapper scripts. Grounds new canary/wrapper scaffolds in the Workflow 3 Phase 1 live canary pattern, including prompt fixtures, modes, output roots, writable state setup, telemetry/ledger capture, timeout handling, and result summaries.
---

# Shell Canary Foundry

Use this skill before creating or auditing a shell-based workflow phase canary wrapper.

This skill creates or audits canary/wrapper scaffolding only. It does not run live canaries, change personas, change providers/models, change workflow YAML, or interpret phase output quality. Use `shell-canary-runner` after this skill when the canary needs to be executed.

For the full source snapshot this skill is based on, read `references/workflow3-phase1-snapshot.md`.

## Modes

- Create mode: build missing canary/wrapper files for one workflow phase from the proven Workflow 3 Phase 1 pattern.
- Audit mode: inspect existing canary/wrapper files and report gaps against the proven pattern.

## Grounding Rule

Before creating or auditing, inspect the current repo files:

- target workflow YAML;
- target phase id, type, dependencies, subscriptions, input source, source coverage mode, output context key, provider/model values;
- existing phase canary script, if any;
- existing threaded wrapper script, if any;
- prompt fixture document the wrapper uses or should use;
- generic canary helpers: `scripts/mcp_phase_ledger_phase_canary.py` and `scripts/phase_ledger_canary_lib.py`;
- any workflow-family shared canary library, if the target phase is not standalone.

Do not infer runtime path from filenames. The wrapper command is the source of truth for what canary script actually runs.

## Required Decisions

If a required value cannot be discovered from files, ask for it before drafting:

- workflow file path;
- phase id;
- prompt fixture path;
- wrapper script path;
- output benchmark root;
- phase-specific environment variable prefix;
- whether the target phase is standalone or needs upstream phase fixtures;
- whether the wrapper should support `mock`, `producer-mechanical`, `producer-verifier`, and `full`.

Do not choose or change provider/model values.

## Create Checklist

For a standalone `phase_ledger_loop` phase like Workflow 3 Phase 1:

- create or update a thin phase canary script only if the repo convention needs one;
- make the threaded wrapper call `scripts/mcp_phase_ledger_phase_canary.py`;
- pass `--workflow-file`, `--phase-id`, and `--prompt-file` as explicit wrapper `EXTRA_ARGS`;
- keep mock mode as the default no-live path and map live modes exactly:
  - `mock` -> no live args;
  - `producer-mechanical` -> `--live-producer-only`;
  - `producer-verifier` -> `--live-producer-verifier-only`;
  - `full` -> `--live`;
- write outputs under a workflow/phase benchmark root using a UTC timestamp and `run-NN` directories;
- set writable `CODEX_HOME`, `HOME`, and `.codex/sessions` under the output root;
- copy host `.codex/auth.json` and `.codex/config.toml` when readable;
- set `WORKFLOW_ORCH_CODEX_USE_EXEC=true` and `WORKFLOW_ORCH_CODEX_SANDBOX=workspace-write` unless the wrapper already has an approved reason not to;
- make `.claude` writable or fall back to an output-root `claude-state-home` when no explicit `CLAUDE_STATE_HOME` was supplied;
- validate positive integer thread count, max polls, worker timeout, and kill grace;
- enforce per-worker timeout and terminate child process trees with `TERM`, grace sleep, then `KILL`;
- write per-run `stdout.log`, `stderr.log`, `pid.txt`, `worker-pid.txt`, `exit-code.txt`, `timed-out.txt` on timeout, `canary-result.json`, `summary.json`, and copied role/ledger JSON artifacts;
- write `aggregate-summary.json` with run counts, pass/fail counts, timeout counts, and per-run summaries;
- exit nonzero if any worker process fails.

For a non-standalone phase:

- do not force the standalone generic canary unless the target can run without upstream outputs;
- use or create a workflow-family shared canary library that builds a temporary workflow with dependencies/subscriptions and stubs upstream phases in live modes;
- preserve the same wrapper mechanics as the standalone pattern.

## Audit Checklist

Report findings against these categories:

- Entry path: wrapper calls the intended canary and passes the intended workflow, phase, and prompt file.
- Prompt fixture: prompt file exists and matches the target phase input shape.
- Modes: `mock`, `producer-mechanical`, `producer-verifier`, and `full` are supported or an explicit reason is recorded.
- State setup: Codex and Claude writable state handling is present.
- Timeouts: per-worker timeout, max-polls, poll interval, kill grace, process tree termination, and timeout summaries are present.
- Output layout: output root, per-run files, copied ledger/role artifacts, summary, and aggregate summary are present.
- Result fields: summaries expose pass/fail, live mode, workflow/phase status, producer count, source coverage, failures, and ledger path.
- Telemetry and ledger review support: canary result includes snapshots and telemetry samples, and wrapper copies phase ledger plus producer/verifier/critic artifacts.
- Failure handling: provider errors, failed telemetry events, manager gaps, source coverage failure, missing producer/verifier/critic output, and timeouts are surfaced.

## Safety Rules

- Do not run live canaries from this skill. Hand off to `shell-canary-runner` for execution.
- Do not stage or commit canary run output directories unless the user explicitly asks for benchmark artifacts.
- Do not commit Codex skill files as project repo changes.
- Do not modify provider/model settings while creating canaries or wrappers.
- Do not hide that shell scripts cannot grant Codex network permission by themselves; live wrapper execution still needs tool escalation from the caller.

## Report Format

For create mode, report:

- files created or changed;
- target workflow and phase;
- prompt fixture path;
- supported modes;
- output root pattern;
- validation command to run next.

For audit mode, report:

- entrypoint truth;
- missing or mismatched mechanics;
- risk level for each gap;
- exact smallest fix surface;
- whether the wrapper is ready for `shell-canary-runner`.
