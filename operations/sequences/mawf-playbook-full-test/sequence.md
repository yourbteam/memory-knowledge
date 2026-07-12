# MAWF Playbook Full Test Sequence

## Purpose

Drive the MAWF 4-playbook chain (Research → Plan → Write-code → Review) end to
end on the local image **through every optional gate**, stopping on the first
blocker so it can be fixed with `/playbook-convergence-loop` and re-entered by
blast radius. This is the **all-gates** regression test for engine/config changes.

The companion [`mawf-playbook-speed-test`](../mawf-playbook-speed-test/sequence.md)
runs the same chain but **skips** the optional gates. The two share one driver
(`scripts/mawf_playbook_test_sequence.py`); they differ only by `--gate-policy`.

## What "All Gates" Means Here — and how (chain mode)

Grounded in the workflow YAMLs (2026-06-27), the chain has exactly **two**
optional gates. Full runs the gap-closure loops behind both, driving their
`COVERAGE_GAP` → `playbook_repair` convergence to zero:

| Workflow | Optional gate | Full result | Runs |
| --- | --- | --- | --- |
| research-workflow | `ask-run-research-gap-closure` | **runs** | `research-gap-closure` |
| plan-workflow | `ask-run-gap-closure` | **runs** | `doc-gap-closure` + `coverage-gap-loop` + `satisfaction-gap-loop` |
| write-code-workflow | *(none)* | n/a | only automatic `on_issues` fix-loops |
| review-workflow | *(none)* | n/a | — |

**How the gate is answered "run".** Grounded in `workflow_engine.approve_run`
(:9404): an approve of an interactive gate defaults to `issues_answers[0]`
(`"yes"`) → the gap-closure loop **runs**; a reject (`reject_run` :9436) maps to
`clean_answers[0]` (`"no"`) → skipped. With the **discrete-action driver** the
operator's dark-factory auto-loop is not alive between calls, so the gate
**stops** for an explicit answer regardless of chain-mode — Full sends
`answer-gate --gate-policy full` (approve → run); Speed sends a reject (skip).
(Chain-mode is still set per policy, but the explicit `answer-gate` is what
deterministically drives the outcome.)

The non-optional spine (scope, fan-out angles, verify, synthesize, draft-plan,
verify-plan, implement, code-review, security-review, etc.) runs in both
policies. Full additionally exercises the gap-closure + repair convergence path
that Speed never touches.

## Use This Sequence When

- An engine/config fix must be proven against the **complete** chain including
  the gap-closure loops and `playbook_repair` convergence.
- You need evidence that approving the optional gates converges (does not loop
  on `COVERAGE_GAP` forever).
- A blocker was found by Speed and you want to confirm the all-gates path too.

## Do Not Use This Sequence When

- You only need a fast smoke of the spine — use the Speed sequence.
- Docker is unavailable — report that blocker; do not substitute host-only runs.
- The local container is mid-run for another task — do not disturb it.

## Prerequisites

- Local image + container per
  [`local-workflow-orch-image`](../local-workflow-orch-image/sequence.md), driven
  here via the driver's `infra` step.
- Operator JWT env file (default `/private/tmp/workflow-orch-local-operator-jwt.env`)
  with WS URL, JWT secret, repository key, actor email. Never printed.
- A task prompt file and the task GUID under test.

**Auth hygiene (baked into the driver):** the operator reads `Path.cwd()/.env`
as a fallback auth source, and the repo-root `.env` carries token-key auth
(`WORKFLOW_ORCH_USER_EMAIL`/`TOKEN_KEY`) that collides with the JWT secret
(`AUTH_CONFIG_CONFLICT`). The driver therefore always runs the operator from a
neutral `--operator-cwd` (default `/private/tmp`) and fails closed if that dir
contains a `.env`. Do not run the operator from the repo root.

## Activation (G18)

```bash
uv run python scripts/directive_guard.py read --mode "mawf-playbook-full-test"
python3 scripts/work_memory.py classify --task-id "<task-id>" --operation-kind workflow-drive --repeatable yes --meaningful-steps 3
python3 scripts/work_memory.py select --task-id "<task-id>" --sequence-id mawf-playbook-full-test
python3 scripts/sequence_guard.py activate --task-id "<task-id>" \
  --sequence-doc operations/sequences/mawf-playbook-full-test/sequence.md
```

Guard each command from this document before running it, e.g.:

```bash
python3 scripts/sequence_guard.py guard --task-id "<task-id>" \
  --step "Answer research gate (approve)" \
  --command "uv run python scripts/mawf_playbook_test_sequence.py answer-gate --gate-policy full --task-guid <task> --workflow-name research-workflow --run-id <run>" \
  --source sequence_doc \
  --source-ref operations/sequences/mawf-playbook-full-test/sequence.md
```

## Driver

All steps run through `scripts/mawf_playbook_test_sequence.py`. Add `--dry-run`
to any operator step to print the exact command without executing.

### 1. Infra — build the fixed image and recreate the container

```bash
uv run python scripts/mawf_playbook_test_sequence.py infra \
  --code-project-source /path/to/neocurrency-dashboard
```

### 2. Start Research

```bash
uv run python scripts/mawf_playbook_test_sequence.py start \
  --gate-policy full --task-guid <task> \
  --repo /workspaces/<repo> --prompt-file <prompt> --task-action start_over
```

### 3. Per workflow: approve-start → answer-gate APPROVE → continue

Each workflow run is created in `waiting_approval` (verdict
`waiting_start_approval`) and must be approved to begin (`approve-start`,
mandatory and policy-independent). It then runs to the optional gap-closure gate
and **stops** there waiting for an answer (the operator's dark-factory auto-loop
is not alive between discrete driver calls, so the gate does not auto-resolve).
Full **approves** it → `issues_answers[0]` ("yes") → the gap-closure loop **runs**.

Watch the gate with `pending-approvals` (`bash dist/remote-mcp-operator/run.sh
--auth-auto-refresh --agent-action pending-approvals`) — its `runId`/`phaseId`
tell you which run is waiting. For each workflow
(research → plan → write-code → review):

```bash
# At verdict waiting_start_approval -> approve to begin executing phases
uv run python scripts/mawf_playbook_test_sequence.py approve-start \
  --task-guid <task> --workflow-name <workflow> --run-id <run>

# At the gap-closure gate -> APPROVE to run it (no-op for write-code/review)
uv run python scripts/mawf_playbook_test_sequence.py answer-gate \
  --gate-policy full --task-guid <task> --workflow-name <workflow> --run-id <run>

# When research-gap-closure emits a COVERAGE_GAP (decision playbook_repair_required),
# drive it to convergence:
uv run python scripts/mawf_playbook_test_sequence.py repair \
  --task-guid <task> --repo /workspaces/<repo>

# When the decision is playbook_continuation_selection -> advance to the next workflow
uv run python scripts/mawf_playbook_test_sequence.py continue \
  --task-guid <task> --repo /workspaces/<repo> --branch main
```

If approving a gate produces `playbook_repair_required` (a `COVERAGE_GAP`
blocker), run the package-owned repair until it converges:

```bash
uv run python scripts/mawf_playbook_test_sequence.py repair \
  --task-guid <task> --completed-workflow <workflow>
```

### 4. On a blocker — stop and hand off

Any `blocked` verdict (driver exit code 2) means stop and follow
[`mawf-playbook-blocker-reentry`](../mawf-playbook-blocker-reentry/sequence.md):
`record-blocker` → `/playbook-convergence-loop` → choose re-entry mode by blast
radius → `reenter` → resume driving with `--gate-policy full`.

## Guardable Command Shapes

Use these single-line shapes with `--source sequence_doc` (placeholders match any
token; token count must match):

```bash
uv run python scripts/mawf_playbook_test_sequence.py infra --code-project-source <path>
uv run python scripts/mawf_playbook_test_sequence.py start --gate-policy full --task-guid <task> --repo <repo> --prompt-file <prompt> --task-action <action>
uv run python scripts/mawf_playbook_test_sequence.py poll --task-guid <task> --run-id <run>
uv run python scripts/mawf_playbook_test_sequence.py approve-start --task-guid <task> --workflow-name <workflow> --run-id <run>
uv run python scripts/mawf_playbook_test_sequence.py answer-gate --gate-policy full --task-guid <task> --workflow-name <workflow> --run-id <run>
uv run python scripts/mawf_playbook_test_sequence.py continue --task-guid <task> --completed-workflow <workflow>
uv run python scripts/mawf_playbook_test_sequence.py repair --task-guid <task> --completed-workflow <workflow>
```

## Pass Signal

All four workflows reach `completed`, the chain reaches
`playbook_chain_complete`, **both optional gap-closure gates were approved and
their loops ran to convergence** (no residual `COVERAGE_GAP`), Write-Code pushed
a work branch, and Review completed against it — with every blocker encountered
en route cataloged and closed.

## Reuses / Does Not Reinvent

- Infra: `local-workflow-orch-image` harness via the driver's `infra` step.
- Operator actions: `dist/remote-mcp-operator/run.sh`.
- Blocker handling + re-entry: `mawf-playbook-blocker-reentry`.
- Blocker catalog: `software company workflows/implementation plans/phase-ledger-harness/mawf4-playbook-real-run-blocker-catalog.md`.
