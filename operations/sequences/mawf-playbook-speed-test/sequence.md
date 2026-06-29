# MAWF Playbook Speed Test Sequence

## Purpose

Drive the MAWF 4-playbook chain (Research → Plan → Write-code → Review) end to
end on the local image **as fast as possible by skipping the optional gates**,
stopping on the first blocker so it can be fixed with `/playbook-convergence-loop`
and re-entered by blast radius. This is the **fast smoke** of the chain spine.

The companion [`mawf-playbook-full-test`](../mawf-playbook-full-test/sequence.md)
runs the same chain but **approves** the optional gates and drives their
gap-closure + repair convergence. The two share one driver
(`scripts/mawf_playbook_test_sequence.py`); they differ only by `--gate-policy`.

## What "Skip Gates" Means Here

Grounded in the workflow YAMLs (2026-06-27), the chain has exactly **two**
optional gates. Speed **rejects** both, taking the clean/skip branch — and
RP-057 guarantees a reject completes the workflow cleanly, preserving the already
completed phases and their artifacts (no reset, no dropped `plan.md`):

| Workflow | Optional gate | Speed answer | Skipped |
| --- | --- | --- | --- |
| research-workflow | `ask-run-research-gap-closure` | **reject** | `research-gap-closure` |
| plan-workflow | `ask-run-gap-closure` | **reject** | `doc-gap-closure` + `coverage-gap-loop` + `satisfaction-gap-loop` |
| write-code-workflow | *(none)* | n/a | only automatic `on_issues` fix-loops still run |
| review-workflow | *(none)* | n/a | — |

**The lever is chain-mode.** Speed starts the chain in **`manual-handoff`** mode,
so each optional gate **stops** for an answer (`waiting_approval`). The driver's
`answer-gate --gate-policy speed` sends a **reject** → grounded in
`workflow_engine.reject_run` (:9436), a reject maps to `clean_answers[0]`
(`"no"`) → the gap-closure loop is **skipped**. (Full, by contrast, uses
`dark-factory`, where the gate auto-answers "run".)

The non-optional spine still runs in full. Speed never exercises the gap-closure
loops or the `playbook_repair` convergence — use Full for that.

## Use This Sequence When

- You need a fast end-to-end proof that the chain spine (research fan-out, plan
  draft/verify, write-code, review) works after a fix, without the slow
  gap-closure loops.
- You are bisecting which workflow a blocker lives in and want the quickest path
  to each handoff.
- You already proved the gap-closure path with Full and only need spine regression.

## Do Not Use This Sequence When

- The fix is **in** the gap-closure or `playbook_repair` path — use Full, which
  actually exercises it. Skipping the gates would give a false green.
- Docker is unavailable — report that blocker; do not substitute host-only runs.
- The local container is mid-run for another task — do not disturb it.

## Prerequisites

Same as Full: local image + container via the driver's `infra` step
([`local-workflow-orch-image`](../local-workflow-orch-image/sequence.md)),
operator JWT env file (default `/private/tmp/workflow-orch-local-operator-jwt.env`,
never printed), a task prompt file, and the task GUID.

**Auth hygiene (baked into the driver):** the operator reads `Path.cwd()/.env`
as a fallback auth source, and the repo-root `.env` carries token-key auth that
collides with the JWT secret (`AUTH_CONFIG_CONFLICT`). The driver always runs the
operator from a neutral `--operator-cwd` (default `/private/tmp`) and fails closed
if that dir has a `.env`. Do not run the operator from the repo root.

## Activation (G18)

```bash
uv run python scripts/directive_guard.py read --mode "mawf-playbook-speed-test"
uv run python scripts/sequence_guard.py activate \
  --sequence-id mawf-playbook-speed-test \
  --sequence-doc operations/sequences/mawf-playbook-speed-test/sequence.md
```

Guard each command from this document before running it, e.g.:

```bash
uv run python scripts/sequence_guard.py guard \
  --step "Answer research gate (reject/skip)" \
  --command "uv run python scripts/mawf_playbook_test_sequence.py answer-gate --gate-policy speed --task-guid <task> --workflow-name research-workflow --run-id <run>" \
  --source sequence_doc \
  --source-ref operations/sequences/mawf-playbook-speed-test/sequence.md
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
  --gate-policy speed --task-guid <task> \
  --repo /workspaces/<repo> --prompt-file <prompt> --task-action start_over
```

### 3. Per workflow: approve-start → poll → answer optional gate (REJECT/skip) → continue

In dark-factory mode each workflow run is created in `waiting_approval`
(verdict `waiting_start_approval`, all phases `pending`) and must be approved to
begin. This chain-start approval is **mandatory and policy-independent** — Speed
approves it too; it is **not** the optional gap-closure gate (which Speed
rejects).

For each workflow in order (research → plan → write-code → review):

```bash
# Poll the run; verdict tells you the next action
uv run python scripts/mawf_playbook_test_sequence.py poll \
  --task-guid <task> --run-id <run>

# verdict waiting_start_approval -> approve to begin executing phases (mandatory)
uv run python scripts/mawf_playbook_test_sequence.py approve-start \
  --task-guid <task> --workflow-name <workflow> --run-id <run>

# verdict waiting_gate -> REJECT the optional gap-closure gate (no-op for write-code/review)
uv run python scripts/mawf_playbook_test_sequence.py answer-gate \
  --gate-policy speed --task-guid <task> --workflow-name <workflow> --run-id <run>

# Advance to the next workflow
uv run python scripts/mawf_playbook_test_sequence.py continue \
  --task-guid <task> --completed-workflow <workflow>
```

Speed should not hit `COVERAGE_GAP` repairs (the loops are skipped). If a reject
ever resets a run or drops an artifact, that is an RP-057-class regression — stop
and treat it as a blocker.

### 4. On a blocker — stop and hand off

Any `blocked` verdict (driver exit code 2) means stop and follow
[`mawf-playbook-blocker-reentry`](../mawf-playbook-blocker-reentry/sequence.md):
`record-blocker` → `/playbook-convergence-loop` → choose re-entry mode by blast
radius → `reenter` → resume driving with `--gate-policy speed`.

## Guardable Command Shapes

Use these single-line shapes with `--source sequence_doc` (placeholders match any
token; token count must match):

```bash
uv run python scripts/mawf_playbook_test_sequence.py infra --code-project-source <path>
uv run python scripts/mawf_playbook_test_sequence.py start --gate-policy speed --task-guid <task> --repo <repo> --prompt-file <prompt> --task-action <action>
uv run python scripts/mawf_playbook_test_sequence.py poll --task-guid <task> --run-id <run>
uv run python scripts/mawf_playbook_test_sequence.py approve-start --task-guid <task> --workflow-name <workflow> --run-id <run>
uv run python scripts/mawf_playbook_test_sequence.py answer-gate --gate-policy speed --task-guid <task> --workflow-name <workflow> --run-id <run>
uv run python scripts/mawf_playbook_test_sequence.py continue --task-guid <task> --completed-workflow <workflow>
```

## Pass Signal

All four workflows reach `completed`, the chain reaches
`playbook_chain_complete`, **both optional gap-closure gates were rejected and
their loops were skipped without resetting any completed phase or dropping any
artifact**, Write-Code pushed a work branch, and Review completed against it —
with every blocker encountered en route cataloged and closed.

## Reuses / Does Not Reinvent

- Infra: `local-workflow-orch-image` harness via the driver's `infra` step.
- Operator actions: `dist/remote-mcp-operator/run.sh`.
- Blocker handling + re-entry: `mawf-playbook-blocker-reentry`.
- Blocker catalog: `software company workflows/implementation plans/phase-ledger-harness/mawf4-playbook-real-run-blocker-catalog.md`.
