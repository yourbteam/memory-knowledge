# MAWF Playbook Blocker Re-entry Sub-Sequence

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

Define the **shared** contract for what happens when either the Full or the
Speed test sequence hits a blocker while driving the MAWF 4-playbook chain:
stop, fix the blocker with `/playbook-convergence-loop`, then re-enter the chain
through the **narrowest re-entry mode the fix's blast radius allows**.

This sub-sequence is not run on its own. It is invoked by:

- [`mawf-playbook-full-test`](../mawf-playbook-full-test/sequence.md)
- [`mawf-playbook-speed-test`](../mawf-playbook-speed-test/sequence.md)

It exists so the blocker handling is identical and decision-complete for both,
and so re-entry mode is chosen by an explicit rubric instead of by guesswork.

## When A Blocker Is Declared

The driver (`scripts/mawf_playbook_test_sequence.py`) declares a blocker when a
`poll`, `continue`, or `repair` verdict is `blocked`, i.e. any of:

- run `status` is `failed`;
- `decisionType` is `playbook_repair_required`;
- `decisionType` is `playbook_terminal_output_unavailable`;
- the run hangs (no phase progress past the configured heartbeat) — treated as a
  blocker after one heartbeat with zero advancement.

When a blocker is declared, **stop driving**. Do not answer further gates, do not
continue, do not resume until the blocker is fixed.

## Step 1 — Capture The Blocker

Record it in the catalog so it is never lost to chat history (G17/G19):

```bash
uv run python scripts/mawf_playbook_test_sequence.py record-blocker \
  --rp-id RP-0XX --workflow <blocked-workflow> --run-id <run-id> \
  --gate-policy <full|speed> \
  --summary "<one-line symptom>" --evidence-file <path-to-evidence>
```

Capture, alongside it: the failed phase id, the operator envelope (`errorCode`,
`decisionType`), and the on-disk run state (phase statuses, missing artifacts).

## Step 2 — Fix With `/playbook-convergence-loop`

Hand the blocker to the convergence loop. Do **not** patch it inline from the
test driver — the test driver only detects and records; the fix lane is
separate (G19). The convergence loop must:

1. research the root cause to file:line certainty (no guessing),
2. run the research + plan hardening gates,
3. implement with tests (`uv run pytest`) and zero new `ruff` errors,
4. review independently/adversarially until zero gap findings,
5. commit (no `Co-Authored-By`).

## Step 3 — Choose The Re-entry Mode By Blast Radius

Pick the **narrowest** mode whose precondition holds. Narrower is cheaper and
preserves more proven work; only widen when the fix invalidates upstream output.

| Mode | Use when | Re-entry effect |
| --- | --- | --- |
| `resume` | The fix is contained to engine logic **at or after** the failure point. Already-completed phases and their artifacts in the **current run** remain valid and were not produced by the buggy path. | Resume the failed run in place — narrowest blast radius. |
| `restart-workflow` | The fix changes the **blocked workflow's** phase logic, artifacts, or gate semantics, so its prior phases must be re-produced — but **upstream** workflows' artifacts are still valid. | `start_over` only the blocked workflow; upstream handoffs are reused. |
| `start-over` | The fix changes research/scope/artifact-seeding or anything that **invalidates upstream artifacts** (e.g. how the work branch or session worktree is seeded), so earlier workflows can no longer be trusted. | Full task restart from research — widest blast radius. |

Decision tests, in order (stop at the first "yes"):

1. **Does the fix change how the failed run's already-completed phases would be
   produced?** No → the completed phases are still trustworthy → `resume`.
2. **Are only the blocked workflow's phases affected (upstream artifacts
   untouched and still valid)?** Yes → `restart-workflow`.
3. **Otherwise** (research/scope/seeding semantics changed, upstream output now
   suspect) → `start-over`.

If the fix touched engine or container config, rebuild the image first (the
`infra` step of the calling sequence) so the re-entry runs on the fixed code.

## Step 4 — Re-enter

```bash
# Narrowest: resume the failed run in place
uv run python scripts/mawf_playbook_test_sequence.py reenter --mode resume \
  --task-guid <task> --workflow-name <blocked-workflow> --run-id <run-id>

# Restart only the blocked workflow
uv run python scripts/mawf_playbook_test_sequence.py reenter --mode restart-workflow \
  --task-guid <task> --workflow-name <blocked-workflow> \
  --repo /workspaces/<repo> --prompt-file <prompt>

# Full task restart from research
uv run python scripts/mawf_playbook_test_sequence.py reenter --mode start-over \
  --task-guid <task> --gate-policy <full|speed> \
  --repo /workspaces/<repo> --prompt-file <prompt>
```

After re-entry, hand control back to the calling sequence and keep driving from
the re-entered point with the **same gate policy**.

## Guardable Command Shapes

Use these single-line shapes with `--source sequence_doc` (placeholders match any
token; token count must match):

```bash
uv run python scripts/mawf_playbook_test_sequence.py record-blocker --rp-id <rp> --workflow <workflow> --run-id <run> --gate-policy <policy> --summary <summary> --evidence-file <path>
uv run python scripts/mawf_playbook_test_sequence.py reenter --mode resume --task-guid <task> --workflow-name <workflow> --run-id <run>
uv run python scripts/mawf_playbook_test_sequence.py reenter --mode restart-workflow --task-guid <task> --workflow-name <workflow> --repo <repo> --prompt-file <prompt>
uv run python scripts/mawf_playbook_test_sequence.py reenter --mode start-over --task-guid <task> --gate-policy <policy> --repo <repo> --prompt-file <prompt>
```

## Same-Fingerprint Rule (G19)

If the **same** blocker fingerprint (same failed phase + same `errorCode`)
recurs after a fix + re-entry, do not retry the same re-entry. Re-open the
convergence loop and treat the recurrence as proof the root cause was not the
one fixed.

## Do Not

- Do not auto-fix from inside the test driver.
- Do not widen the re-entry mode "to be safe" when a narrower precondition holds
  — that hides whether the narrow path actually works.
- Do not skip `record-blocker`; an un-cataloged blocker is a lost regression.
- Do not print secrets, tokens, or auth payloads in evidence.
