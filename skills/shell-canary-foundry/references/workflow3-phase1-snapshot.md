# Workflow 3 Phase 1 Canary And Wrapper Snapshot

This reference records the proven Workflow 3 Phase 1 setup as of the snapshot used to create `shell-canary-foundry`.

## Target Phase

- Workflow: `acceptance-requirements-precode-workflow`.
- Workflow file: `src/workflow_orch/workflows/acceptance-requirements-precode-workflow.yaml`.
- Phase id: `atomize-requirements`.
- Phase name: `Atomize Requirements`.
- Phase type: `phase_ledger_loop`.
- Input source: `task_description`.
- Source coverage mode: `full_universe_coverage`.
- Output context key: `acceptance_precode.primitive_requirements`.
- Producer: `acceptance-precode-phase1-atomize-producer`, provider `codex`, model `gpt-5.4`, reasoning `high`.
- Verifier: `acceptance-precode-phase1-atomize-verifier`, provider `codex`, model `gpt-5.5`, reasoning `high`.
- Critic: `acceptance-precode-phase1-atomize-critic`, provider `codex`, model `gpt-5.5`, reasoning `high`.
- Max loops: `20`.
- Convergence: verifier findings empty and critic patches empty.
- Standalone status: standalone. It has no `depends_on` or `subscribes_to`, so the generic one-phase canary can run it directly.

## Prompt Fixture

- Prompt file used by the wrapper:
  `software company workflows/benchmarks/acceptance-precode/workflow3-phase1-live-inputs/workflow3-phase1-input-from-workflow2-feedback-run-b47fb9cd-hardened-packet.md`.
- Companion source ledger fixture:
  `software company workflows/benchmarks/acceptance-precode/workflow3-phase1-live-inputs/workflow3-phase1-input-from-workflow2-feedback-run-b47fb9cd-hardened-packet-ledger.json`.
- The canary reads prompt text through `phase_ledger_canary_lib.read_prompt`.
- `read_prompt` extracts the `## Original Request` section if present; otherwise it uses the full file text stripped.
- The wrapper does not synthesize prompt content. It passes the fixture path into the canary with `--prompt-file`.

## Canary Entrypoints

### Wrapper-Used Entrypoint

- Wrapper: `scripts/run_acceptance_phase1_producer_canary_threads.sh`.
- The wrapper calls `scripts/mcp_phase_ledger_phase_canary.py`, not the thin acceptance phase shim.
- The wrapper passes:
  - `--workflow-file src/workflow_orch/workflows/acceptance-requirements-precode-workflow.yaml`
  - `--phase-id atomize-requirements`
  - `--prompt-file software company workflows/benchmarks/acceptance-precode/workflow3-phase1-live-inputs/workflow3-phase1-input-from-workflow2-feedback-run-b47fb9cd-hardened-packet.md`

### Thin Phase-Specific Shim

- File: `scripts/mcp_acceptance_precode_phase1_canary.py`.
- Contents are intentionally tiny:
  - imports `PHASE1_ID` and `main_for_phase` from `mcp_acceptance_precode_canary_lib`;
  - calls `main_for_phase(PHASE1_ID, sys.argv[1:])`.
- The current Phase 1 wrapper does not call this file.

### Shared Acceptance Library

- File: `scripts/mcp_acceptance_precode_canary_lib.py`.
- It supports acceptance phases 1, 2, 3, 4, and 6 through `PHASE_CONFIGS`.
- It can build temporary workflows that include dependencies/subscriptions for non-standalone phases.
- It imports acceptance-owned duplicate/detail/packet coverage report functions.
- It stubs prerequisite roles in mock/live modes where needed.
- Use this family library for acceptance phases that cannot run with the standalone generic canary.

## Generic Canary Behavior

File: `scripts/mcp_phase_ledger_phase_canary.py`.

Key behavior:

- Builds a temporary workspace under `tempfile.mkdtemp(prefix="mcp-phase-ledger-phase-canary-")` unless `--workspace` is supplied.
- Loads the source workflow with `WorkflowDefinition.from_yaml_file`.
- Selects the requested phase with `--phase-id`, or the first phase if omitted.
- Requires the selected phase to be `phase_ledger_loop`.
- Rejects phases with `depends_on` or `subscribes_to`; this generic canary only supports standalone phases.
- Creates a temporary one-phase workflow named `<source-workflow-name>-<phase-id>-canary`.
- If `producer-mechanical` mode is active, sets the temporary phase loop `max_loops` to `1`.
- Writes `pyproject.toml` in the temp workspace.
- Disables memory-knowledge, MAWF intake, and artifact repo side effects with environment variables:
  - `WORKFLOW_ORCH_MEMORY_KNOWLEDGE_ENABLED=false`
  - `WORKFLOW_ORCH_MAWF_TASK_INTAKE_ENABLED=false`
  - `WORKFLOW_ORCH_ARTIFACT_REPO_ENABLED=false`
- Enters through MCP-style server calls:
  - `workflow.project.set`
  - `workflow.start`
  - `workflow.status` with `view=manager`
- Starts the workflow with:
  - `workflowName` = generated phase workflow name;
  - `taskGuid` = `--task-id` or default `mcp-phase-ledger-phase-canary`;
  - `taskDescription` = prompt fixture content;
  - `notify` = `[]`;
  - `notifyPhases` = `False`;
  - `useMemoryKnowledge` = `False`.
- Polls manager status until terminal status or `--max-polls`.
- Cancels still-running internal workflow tasks after polling.
- Reads the phase ledger from:
  `<taskDir>/workflows/<phase-workflow-name>/runs/<run-id>/phases/<phase-id>/phase-ledger.json`.

## Generic Canary CLI

Common arguments from `phase_ledger_canary_lib.add_common_args`:

- `--prompt-file`
- `--workflow-file`
- `--workspace`
- `--output`
- `--cleanup`
- `--live`

One-phase arguments:

- `--phase-id`
- `--task-id`, default `mcp-phase-ledger-phase-canary`
- `--poll-interval`, default `1.0`
- `--max-polls`, default `120`
- `--print-polls`

Role mode arguments:

- `--mode producer-mechanical`
- `--mode producer-verifier`
- `--mode full`
- `--live-producer-only`, compatibility alias for producer-mechanical
- `--live-producer-verifier-only`, compatibility alias for producer-verifier
- `--live`, compatibility path for full

Mode flag resolution:

- no live flags -> `mock`;
- `--live-producer-only` -> `producer-mechanical`;
- `--live-producer-verifier-only` -> `producer-verifier`;
- `--mode` wins when no compatibility alias is present;
- `--live` -> `full`;
- any non-mock mode makes the target phase live.

Mocking behavior in the generic canary:

- In mock mode, producer is mocked for names ending `-producer`.
- In mock mode and producer-mechanical mode, verifier is mocked as `[]` unless verifier-only mode is active.
- In mock, producer-mechanical, and producer-verifier modes, critic is mocked with:
  `{"accepted_findings": [], "rejected_findings": [], "producer_patches": []}`.
- In full mode, producer, verifier, and critic are live.

Generic mock producer output:

- Extracts text from the role prompt's `## SOURCE REQUEST` section.
- Splits non-empty source lines.
- Emits `AR-###` mock atomization records with `source_quote`, `detail`, and `reason`.
- This is generic and not acceptance-specific; live Phase 1 testing is what validates real `AAI-*` output.

## Generic Canary Result Fields

The result written to `--output` includes:

- `passed`
- `canaryType` = `mcp-phase-ledger-phase`
- `live`
- `liveMode`
- `producerOnly`
- `verifierOnly`
- `workspace`
- `sourceWorkflowFile`
- `phaseWorkflowFile`
- `sourceWorkflowName`
- `workflowName`
- `phaseId`
- `taskId`
- `taskDir`
- `runId`
- `phaseLedgerPath`
- `workflowStatus`
- `phaseStatus`
- `producerWritten`
- `producerCount`
- `producer`
- `verifierWritten`
- `verifierFindingCount`
- `verifier`
- `verifierFindings`
- `criticWritten`
- `criticAcceptedFindingCount`
- `criticRejectedFindingCount`
- `criticPatchCount`
- `critic`
- `criticAcceptedFindings`
- `criticRejectedFindings`
- `criticPatches`
- `managerGapCount`
- `coverage`
- `telemetryIntegrity`
- `telemetryEventTypes`
- `failureEvents`
- `pollCount`
- `snapshots`
- `telemetrySamples`
- `failures`

Failure conditions:

- non-producer-only workflow status is not completed;
- non-producer-only target phase status is not completed;
- telemetry integrity fails;
- failure telemetry events exist outside producer-only mode;
- producer section is missing;
- verifier section is missing in verifier-only mode;
- critic section is missing in full mode;
- manager-gap records remain;
- coverage report is not ok.

Coverage behavior:

- `full_universe_coverage`: checks producer source universe coverage plus atomized duplicate pairs.
- `evidence_only`: checks exact source quote presence.
- all other modes: checks source reconstruction.

## Wrapper Behavior

File: `scripts/run_acceptance_phase1_producer_canary_threads.sh`.

Inputs:

- positional `$1`: thread count, default `1`;
- positional `$2`: mode, default `full`;
- accepted modes: `mock`, `producer-mechanical`, `producer-verifier`, `full`.

Constants:

- `PHASE_NAME=phase1`
- `CANARY_SCRIPT=scripts/mcp_phase_ledger_phase_canary.py`
- `EXTRA_ARGS` contains workflow file, phase id, and prompt file listed above.

Output root:

- Default:
  `software company workflows/benchmarks/acceptance-precode/phase1-<mode>-threaded/<UTC-STAMP>`
- Override:
  `ACCEPTANCE_PHASE1_CANARY_OUTPUT_ROOT`
- Timestamp format:
  `date -u +"%Y%m%dT%H%M%SZ"`

Environment knobs:

- `ACCEPTANCE_PHASE1_CANARY_POLL_INTERVAL`, default `1.0`
- `ACCEPTANCE_PHASE1_CANARY_MAX_POLLS`, default `900`
- `ACCEPTANCE_PHASE1_CANARY_WORKER_TIMEOUT_SECONDS`, default `2400` in full mode and `1200` otherwise
- `ACCEPTANCE_PHASE1_CANARY_WORKER_KILL_GRACE_SECONDS`, default `5`
- `CODEX_STATE_HOME`, default `<output-root>/codex-state-home`
- `CLAUDE_STATE_HOME`, default host `$HOME`, fallback `<output-root>/claude-state-home` only when not explicitly supplied and host `.claude` is not writable
- `WORKFLOW_ORCH_CODEX_USE_EXEC`, default `true`
- `WORKFLOW_ORCH_CODEX_SANDBOX`, default `workspace-write`

Validation:

- thread count must be a positive integer;
- mode must be one of the four accepted modes;
- worker timeout and max polls must be positive integers;
- kill grace must be a non-negative integer;
- Codex sessions directory must be writable;
- Claude state directory must be writable after fallback handling.

State setup:

- creates output root;
- creates `$CODEX_STATE_HOME/.codex/sessions`;
- copies host `.codex/auth.json` and `.codex/config.toml` into the local Codex state when readable;
- chmods Codex state directories/files for user read/write/execute as appropriate;
- creates/chmods Claude state;
- exports `CLAUDE_STATE_HOME`, `WORKFLOW_ORCH_CODEX_USE_EXEC`, and `WORKFLOW_ORCH_CODEX_SANDBOX`;
- each worker sets:
  - `PYTHONPATH=src`
  - `TMPDIR=<run-dir>/tmp`
  - `HOME=<CODEX_STATE_HOME>`
  - `CODEX_HOME=<CODEX_STATE_DIR>`

Mode mapping:

- `mock` -> no extra live args;
- `producer-mechanical` -> `--live-producer-only`;
- `producer-verifier` -> `--live-producer-verifier-only`;
- `full` -> `--live`.

Per-run layout:

- `<output-root>/run-01`, `<output-root>/run-02`, etc.
- each run directory contains:
  - `tmp/`
  - `stdout.log`
  - `stderr.log`
  - `pid.txt`
  - `worker-pid.txt`
  - `exit-code.txt`
  - `timed-out.txt` if timeout occurs
  - `canary-result.json`
  - `summary.json`
  - `summarize.log`
  - `summarize.err`
  - copied `phase-ledger.json` when available
  - copied `*producer*.json`, `*verifier*.json`, and `*critic*.json` files from the phase ledger directory when available
  - extracted `producer.json`
  - `verifier.json`
  - `verifier-findings.json`
  - `critic.json`
  - `critic-accepted-findings.json`
  - `critic-rejected-findings.json`
  - `critic-patches.json`
  - `failure-events.json`
  - `telemetry-samples.json`

Per-run command shape:

```bash
PYTHONPATH=src TMPDIR=<run-dir>/tmp HOME=<CODEX_STATE_HOME> CODEX_HOME=<CODEX_STATE_DIR> \
  .venv/bin/python scripts/mcp_phase_ledger_phase_canary.py \
  --workflow-file src/workflow_orch/workflows/acceptance-requirements-precode-workflow.yaml \
  --phase-id atomize-requirements \
  --prompt-file software company workflows/benchmarks/acceptance-precode/workflow3-phase1-live-inputs/workflow3-phase1-input-from-workflow2-feedback-run-b47fb9cd-hardened-packet.md \
  <mode-args> \
  --max-polls <MAX_POLLS> \
  --poll-interval <POLL_INTERVAL> \
  --output <run-dir>/canary-result.json
```

Timeout behavior:

- wrapper tracks each worker process by PID;
- if elapsed seconds reach worker timeout:
  - writes `timed-out.txt`;
  - recursively collects child PIDs with `pgrep -P`;
  - sends `TERM` to descendants plus root;
  - sleeps kill grace;
  - sends `KILL` to survivors;
  - writes exit code `124`;
  - still runs summarization.

Summary behavior:

- `summarize_run` reads `canary-result.json` if present;
- writes per-run summary fields:
  - `runDir`
  - `resultPath`
  - `resultExists`
  - `timedOut`
  - `passed`
  - `canaryType`
  - `live`
  - `liveMode`
  - `producerOnly`
  - `verifierOnly`
  - `workflowStatus`
  - `phaseStatus`
  - `producerWritten`
  - `producerCount`
  - `sourceCoverageOk`
  - `failures`
  - `sourcePhaseLedgerPath`
- if timed out and no failure exists, injects a timeout failure message.
- copies ledger and role artifacts when `phaseLedgerPath` exists.
- writes extracted result sections listed above.

Aggregate behavior:

- reads all `run-*/summary.json`;
- adds fallback entries for run directories missing summaries;
- writes:
  - `outputRoot`
  - `runCount`
  - `passedCount`
  - `failedCount`
  - `timedOutCount`
  - `runs`
- prints the aggregate JSON and final result path line;
- exits nonzero if any worker process failed.

## Live Execution Permission Boundary

The wrapper prepares writable state and environment variables. It cannot grant Codex tool network permission by itself.

When running live modes from Codex, launch the wrapper through the tool with `sandbox_permissions=require_escalated` and a narrow prefix rule for the wrapper path.

## Last Known Successful Workflow 3 Phase 1 Run

- Command: `scripts/run_acceptance_phase1_producer_canary_threads.sh 1 full`
- Output root:
  `software company workflows/benchmarks/acceptance-precode/phase1-full-threaded/20260512T220111Z`
- Result: passed.
- Workflow status: completed.
- Phase status: completed.
- Producer count: `78`.
- Coverage: `ok: true`, `uncovered_source_span_count: 0`, `invalid_source_quote_count: 0`, `duplicate_pair_count: 0`.
- Manager gaps remaining: `0`.
- Telemetry events: `32`.
- Role sequence:
  - producer completed once;
  - verifier loop 1 found `16` findings;
  - critic loop 1 applied `32` patches;
  - verifier loop 2 found `0` findings;
  - critic loop 2 emitted `0` patches;
  - phase converged on loop 2.
- The emitted manager text was saved as the next prompt fixture:
  `software company workflows/benchmarks/acceptance-precode/workflow3-phase2-live-inputs/workflow3-phase2-input-from-phase1-run-cffc6ae5-primitive-requirements.md`.
