---
name: remote-mcp-operator
description: Use when Codex needs to drive the sendable remote MCP operator package for real remote workflow-orch tasks, including task start, repo/project selection, status polling, continuation workflow starts, feedback submission, approvals, cancel/resume, and JSON-envelope interpretation while preserving AI reasoning outside the mechanical script.
---

# Remote MCP Operator

Use this skill to drive the packaged remote MCP operator for real remote `workflow-orch` task operations. The package is the mechanical MCP transport; the AI keeps responsibility for reasoning, action selection, result interpretation, and reporting.

## Use Boundary

- Use `--agent-action` for AI-driven calls.
- Do not use the interactive menu for structured AI operations.
- Do not ask the package to interpret the task, choose a workflow strategy, or infer success.
- Never print secrets, token keys, challenge codes, or auth values. For JWT task starts, pass `--actor-email <email>` or ensure `WORKFLOW_ORCH_ACTOR_EMAIL` is set so task intake has an actor.

## Package Selection

- Prefer `dist/remote-mcp-operator/remote_mcp_operator_tui.py` for real package validation and remote task operations.
- Rebuild once with `uv run python scripts/build_remote_mcp_operator_package.py` if the built script is missing or source/template files changed.
- Use `scripts/remote_mcp_operator_tui.py` only when debugging source behavior, and report that source path was used.
- Treat `dist/remote-mcp-operator` as the local runnable package. Its package-directory `.env` is the auth source of truth for local package use; do not rely on the repo root `.env` shadowing it.
- For Windows operators running the zip directly, use `run.ps1` or `python remote_mcp_operator_tui.py`; for macOS/Linux operators, use `run.sh` or `python3 remote_mcp_operator_tui.py`.

## Codex Network Execution

- Remote package actions contact the deployed MCP over HTTPS/WebSocket. In Codex, run these package commands with `exec_command` network escalation on the first attempt; do not first run them un-escalated and wait for DNS or connection failure.
- Use `sandbox_permissions="require_escalated"` with a concise justification such as "Allow the local remote-mcp-operator package to connect to the deployed Workflow Orchestrator." For repeatable package calls, request the prefix rule `["python3", "dist/remote-mcp-operator/remote_mcp_operator_tui.py"]`.
- This escalation is a Codex tool-call requirement and cannot be encoded inside `run.sh` or the Python package itself, because sandbox permission is decided before the shell script starts.

## Action Commands

Repo and mode selection from chat:

When a repo or chain mode is needed and the user has not specified it, do not
launch the interactive package selector. The package terminal is hidden inside
Codex tool execution and is not a user-visible interface.

Instead, task starts must advance through one gate at a time:

1. Authentication is first. If auth returns `challenge_required`, handle only
   auth refresh and challenge-code verification. Do not ask for repo or prompt
   while authentication is unresolved.
2. After authentication, confirm the repository. Call `task-start` without a
   prompt first. The package returns `decisionType: "repo_confirmation"` with
   repository options. Present the repository list every time the skill is
   triggered, even when `--repo` is already known; mark any returned
   `current: true` option as currently selected. Ask only for repository
   confirmation/selection at this gate.
3. Rerun with `--repo <selected-alias> --repo-confirmed`. The package then
   returns `decisionType: "branch_confirmation"` with the repository's branches.
   Present the branch list every time, even when `--branch` is already known;
   mark any returned `current: true` option as currently selected. Ask only for
   branch confirmation/selection at this gate. If the package skips this gate and
   returns `task_selection` directly, the branch list was unavailable or empty;
   proceed with the supplied branch or the package default branch.
4. Rerun with `--repo <selected-alias> --repo-confirmed --branch
   <selected-branch> --branch-confirmed`. The package then returns
   `decisionType: "task_selection"` with any incomplete tasks in that repository
   plus a final `Start new task` option. Present the numbered list; do not ask
   for a prompt at this gate. Keep `--branch-confirmed` on every subsequent
   rerun in this task-start flow.
5. If the user selects `Start new task`, rerun with
   `--task-selection-confirmed --task-choice new`. Only then, if the package
   returns `decisionType: "task_prompt_required"`, ask for the task prompt and
   write it to a local temp file. Use `/private/tmp/<descriptive-name>.txt` on
   macOS or `%TEMP%\<descriptive-name>.txt` on Windows.
6. Rerun with `--prompt-file <prompt-file>`. Use `manual-handoff` unless the
   user explicitly asks for another mode.
7. If the user selects an existing task, rerun with
   `--task-selection-confirmed --selected-task-id <task-id>`. The package will
   return `decisionType: "existing_task_resume_action"` with Resume and Start
   Over choices.

If a task-start result has `selectionRequired: true` and
`decisionType: "existing_task_resume_action"`:

1. Present option 1 as `Resume` with the returned current-stage description.
2. Present option 2 as `Start Over` with the returned preservation/reset
   description.
3. Ask the user to reply with `1` or `2`.
4. Rerun the package with `--selected-task-action resume` for option 1.
5. For option 2, rerun with `--selected-task-action start_over`; if the package
   returns `decisionType: "replacement_task_prompt_required"`, ask for the new
   replacement prompt, write it to a local temp file, and rerun with
   `--replacement-prompt-file <prompt-file>`.
6. Do not infer Resume just because an existing task or run is present.

Selected-task Resume does not trust the order returned by `workflow.runs.mine`.
It ranks known precode workflows by the fixed chain order before selecting the
next action. A completed upstream workflow always stops at the package-owned
handoff gates before any downstream workflow starts: first
`decisionType: "handoff_text_review"`, then
`decisionType: "continuation_workflow_selection"`. Manual handoff and dark
factory both use these gates; `afterFeedback`, Resume, or local assumptions are
not bypass authority for a direct continuation start.

When selected-task Resume returns a failed workflow state, do not treat
`failedTerminal` as a normal endpoint. The package may attempt same-run recovery
only when the restart phase is explicit and inside the safe recovery boundary.
For `requirements-hardening-precode-workflow`, accepted feedback in
`persist-requirements-hardening-feedback` is authoritative; do not resume from
`atomize-requirements`, do not infer an upstream restart phase, and do not start
a replacement Workflow 2 run after accepted feedback evidence exists. Only
report unrecoverable or recoverable feedback re-entry failure after the package
returns a recovery audit.

Playbook workflow operations use server-owned terminal state. For `playbook-start` selected-task resume and completed-run handling, the package must call `workflow.playbook.state`; do not reconstruct playbook terminal output, blocker records, continuation options, or run ranking from `workflow.runs.mine`, `workflow.status`, or `workflow.artifacts` in the Codex layer. For `playbook-repair`, the package must call `workflow.playbook.repair`; do not generate repair prompts or start repair workflows locally. If the server playbook tools are unavailable or return a fail-closed envelope, report that exact error and stop instead of falling back to package-local inference.

Legacy prompt-based duplicate handling may still return
`decisionType: "existing_task_action"` for direct `--prompt-file` starts. Treat
that as the older Continue/Start Over flow and rerun with
`--existing-task-action continue` or `--existing-task-action start_over`.

If a restarted task-start returns `checkpointType: "questions"` after the prompt
is supplied, treat it as recovered workflow state. Display the full returned
`questions[]` list, then ask the first unanswered question. Do not ask
Continue/Start Over in this path because the package already resolved the
existing task to a pending question checkpoint.

For standalone repo browsing, `list-repos` may still be used directly and the
same numbered chat-list rule applies.

If the repo list has only 2-3 options and a Codex host choice UI is actually
available in the current mode, it may be used by the Codex layer. Otherwise use
the numbered chat list. The package itself must not be expected to render a
Codex-native selector.

Always render the full branch/repo/option list as a plain numbered text list
directly in chat. List every returned option, never truncate to a preview, and
do not use a host option picker that hides any options. This applies regardless
of count.

List repos:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action list-repos
```

Set project:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action set-project --repo <repo-alias-or-org/repo>
```

Start or reuse the task precode chain:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action task-start --actor-email <actor-email>
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action task-start --repo <repo-alias-or-org/repo> --repo-confirmed --branch <branch> --branch-confirmed --actor-email <actor-email>
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action task-start --repo <repo-alias-or-org/repo> --repo-confirmed --branch <branch> --branch-confirmed --prompt-file <prompt-file> --actor-email <actor-email>
```

For slow cold-start auth responses, pass `--auth-timeout-seconds <seconds>` or
set `WORKFLOW_ORCH_OPERATOR_AUTH_TIMEOUT_SECONDS`; the packaged default is 60
seconds.

Present the next package-owned handoff for approval or edit:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action task-start --chain-mode manual-handoff --repo <repo-alias-or-org/repo> --repo-confirmed --branch <branch> --branch-confirmed --prompt-file <original-prompt-file> --actor-email <actor-email> --existing-task-action continue
```

Use this command after a package-owned workflow completes, after feedback is
submitted, or whenever a task-start checkpoint is already at `handoff` or
`continuation`. The expected package result is
`decisionType: "handoff_text_review"` with `handoffText`, `reviewStateId`,
`reviewStateVersion`, and `nextCommandTemplate`. Display `handoffText` in chat
and offer only approval or edit. Do not start a direct continuation workflow
until this handoff review path has accepted the handoff text.

Inspect status:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action status --run-id <workflow-run-id>
```

When a status or failed-terminal package result includes `failureSummary`, report
`failedPhaseId`, `failureClass`, `remainingFindingIds`, and `affectedItemIds`
before proposing or making fixes. If `failureClass` starts with
`phase_ledger_`, fetch both `phase-ledger.json` and `phase-debug-artifacts.json`
for the failed phase before diagnosing the code path.

List or retrieve artifacts:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action artifacts --run-id <workflow-run-id>
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action artifacts --run-id <workflow-run-id> --artifact <artifact-name> --phase <phase-id>
```

Retry artifact repository persistence for a completed run:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action artifacts-persist --task-id <task-guid> --run-id <workflow-run-id>
```

Recover task runs:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action runs-mine --task-id <task-guid>
```

List or describe workflows:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action workflow-list
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action workflow-describe --workflow-name <workflow-name>
```

Start a selected workflow against an existing task:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action workflow-start --workflow-name <workflow-name> --task-id <task-guid> --source-run-id <upstream-run-id> --repo <repo-alias-or-org/repo> --branch <branch> --prompt-file <workflow-input-file> --actor-email <actor-email>
```

Start a continuation workflow directly:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action continuation-start --workflow-name <workflow-name> --task-id <task-guid> --repo <repo-alias-or-org/repo> --branch <branch>
```

Legacy file-backed handoff review for direct continuation tests:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action continuation-start --continuation-mode review-handoff --workflow-name <workflow-name> --task-id <task-guid> --source-run-id <upstream-run-id> --handoff-file <handoff-file>
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action continuation-start --continuation-mode review-handoff --handoff-reviewed --workflow-name <workflow-name> --task-id <task-guid> --repo <repo-alias-or-org/repo> --branch <branch> --handoff-file <handoff-file>
```

Use that file-backed flow only when explicitly testing legacy direct
continuation behavior. For package-owned precode task chains, drive the returned
decision envelopes instead.

Submit feedback:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action feedback-submit --task-id <task-guid> --workflow-name <workflow-name> --run-id <workflow-run-id> --responses-json <responses-json>
```

When a package result has `checkpointType: "questions"`:

1. Display the full `questions[]` list in chat first.
2. Ask the user exactly one question at a time.
3. Keep the accumulated answers in memory and in the JSON list at
   `responsesJsonFile` when that path is present.
4. Do not submit feedback until every question has an answer, unless the user
   explicitly says to stop or submit partial answers.
5. Submit the complete list with the package `feedback-submit` command using
   the provided `taskId`, `workflowName`, `runId`, and `responsesJsonFile`.
6. After feedback is submitted successfully, continue with the provided
   `afterFeedback.command` when the user wants to proceed.

When a package result has `decisionType: "handoff_text_review"`:

1. Display the returned `handoffText` in chat.
2. Present only these numbered options:
   - `1 Accept handoff text`
   - `2 Make edits to the handoff text`
3. If the user selects option `2`, collect the edited handoff text in chat,
   write the returned handoff response JSON shape with `action: "edit"` and the
   edited `handoffText`, then run the returned `nextCommandTemplate` using
   `--agent-action handoff-review --handoff-response-json <json-file>`.
4. Display the returned edited text again with the same two numbered options.
5. If the user selects option `1`, write the handoff response JSON with
   `action: "accept"` and the accepted `handoffText`, then run the returned
   handoff-review command.
6. Do not ask the user to manually edit `handoffFile` for this path. The file is
   an inspectable package artifact only.

When a package result has `decisionType: "continuation_workflow_selection"`:

1. Display every returned option as a numbered list. These options may include
   all downstream workflows that have not completed, not just the fixed-chain
   next workflow.
2. Mark only the option with `recommended: true` as recommended.
3. Ask for one numeric selection.
4. Write the continuation response JSON with `checkpointKey`, `taskId`,
   `completedRunId`, `handoffArtifactName`, `reviewStateId`,
   `reviewStateVersion`, `selectedWorkflowName`, and the accepted `handoffText`.
5. Run the returned `nextCommandTemplate` using
   `--agent-action continuation-select --continuation-response-json <json-file>`.
6. Stop and report package errors for stale review state, invalid selection,
   missing code project context, empty handoff text, malformed JSON, or failed
   feedback submission.

Refresh expired user-token auth without editing `.env` manually:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --auth-refresh
```

For local user-driven runs where challenge-code prompting is acceptable, let the
package detect `challenge_required`, prompt for the emailed code, persist the new
token key, and retry the action once:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --auth-auto-refresh --agent-action <action>
```

Control a run:

```bash
python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --agent-action control --control-action <approve|reject|cancel|resume> --run-id <workflow-run-id> --reason <reason>
```

Select the smallest action that advances the user request.

## Prompt And Response Files

- Write task prompts to a local temp file unless the user requests a tracked fixture. Use `/private/tmp/<descriptive-name>.txt` on macOS or `%TEMP%\<descriptive-name>.txt` on Windows.
- Preserve the user prompt text without hidden instructions.
- Write feedback responses as a JSON list of `{ "question": "...", "answer": "..." }` objects.

## JSON Result Handling

- Parse stdout as JSON.
- Inspect `finalOk`, `action`, `toolCalls`, `result`, `diagnosticsPath`, `errorCode`, and `errorMessage`.
- Treat nonzero exit codes and `finalOk: false` as failed mechanical actions unless deliberately running the local missing-argument validation that expects `RUN_ID_REQUIRED`.

## Monitoring Rules

- Poll `status` every 30 seconds by default.
- Stop after 20 minutes by default unless the user asks for a different duration.
- Report each status transition and final terminal, blocked, or timed-out state.
- Use `runs-mine` when task id is known but run id is missing.

## Failure Rules

- If auth returns `challenge_required` during unattended AI work, stop the mechanical action and run or report `python3 dist/remote-mcp-operator/remote_mcp_operator_tui.py --auth-refresh`; this refreshes the loaded package `.env` without manual editing.
- If the user is present and wants the package to handle the challenge flow inline, rerun the same package action with `--auth-auto-refresh`; do not ask the user to edit `.env` manually.
- If stdout is not valid JSON, report invalid operator output and do not infer success from partial text.
- If the packaged script is missing, rebuild once, then retry the same command.
- For dependency/import failures, report the missing dependency and point to `packages/remote-mcp-operator/requirements.txt`; do not install dependencies unless the user explicitly asks.
- If local sandboxing blocks network access, request escalation for the packaged script command rather than switching to an unrelated path.

## Report Back

Report:

- Package path used.
- Action commands run, without secrets.
- Task id and workflow run ids discovered or started.
- Status transitions observed.
- Whether the requested workflow completed, blocked, failed, or timed out.
- Diagnostics path when available.
- Any required operator action, such as auth refresh or feedback answers.
