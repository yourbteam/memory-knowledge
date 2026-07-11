---
name: playbook-convergence-loop
description: Use only when Kamen explicitly asks Codex to autonomously run the full research, planning, implementation, and review chain to convergence. Creates a bounded autonomy envelope, independently hardens research and plans, implements without commits by default, reviews every in-scope working-tree surface, and loops from validated review gaps back to research until no requirement gap remains. Do not use for research-only, plan-only, review-only, or assessment requests.
---

# Playbook Convergence Loop

Run research -> research gates -> plan -> plan gates -> implementation -> review. Return validated review gaps to research and repeat. Tests are evidence, not the definition of convergence.

## Authorization Envelope

Explicit invocation authorizes edits only inside the objective, requirement set, hardened plan, named repositories, and recorded allowed paths. It does not authorize directive promotion without `lock it`, secrets, credentials, deployment, destructive actions, external messages, scope expansion, or commits unless separately approved. A new requirement or plan expansion creates an approval blocker and returns to research after approval.

Default `commit_policy` is `none`. Never commit because a nested skill historically requested it.

## State And Baseline

Before source edits:

1. Create/migrate one schema-v1 task state with `convergence_state.py` under `${XDG_STATE_HOME:-$HOME/.local/state}/kamen-convergence/<task-id>/`.
2. Record every Git repository and non-Git managed path that may change. Protect initial dirty paths with metadata/hashes only; never copy unrelated or secret contents.
3. Record immutable base state and mutable expected state. Track generated-region evidence for an approved dirty projection overlap.
4. Run `guard-baseline` before every edit, reviewer spawn, finding fix, verification command, install, or projection mutation. Stop on unexplained branch, HEAD, index, path, or tree drift.
5. Review the union of committed, staged, unstaged, and new in-scope files for every recorded surface.

## Delegation

The parent orchestrator is the only fixer and task-state writer. Verification agents inspect and report in assessment-only mode.

Fresh reasoning context excludes producer rationale, hidden expected answers, prior conversational reasoning, and producer explanations. It includes the objective, full assigned requirements, artifact, authoritative source roots, exact diff/runtime commands, raw findings, and raw closure evidence.

Parent-runtime spawn/wait/close capability determines subagent availability. A delegated agent is not expected to spawn children. If parent subagent tools are unavailable, stop rather than self-review.

Use `skills/_shared/STAGE_RESULT_CONTRACT.md` for every delegated result. The parent validates and records its envelope.

## Slot Lifecycle

Use `skills/_shared/agent_slot_ledger.py` serially, normally with `--max 1`:

1. `guard`, then `acquire --label <stage>`.
2. Spawn; immediately `bind-agent --label <stage> --agent-id <returned-id>`.
3. Wait and collect full output; `mark-completed --agent-id <id>`.
4. Call runtime `close_agent` with that exact returned id.
5. `mark-closed --agent-id <id> --close-evidence <previous-status>`, then `release --agent-id <id>`.

If spawn fails before an id, abandon the reservation. If bind fails after spawn, close the runtime agent, abandon with runtime id and close evidence, then release. Never use `reap` for a live/unknown agent. At iteration boundaries require zero active slots; compact released tombstones only after status proves zero.

## Stage Order

Read each named skill when its stage begins:

1. `research-playbook`
2. `doc-gap-closure-loop` in delegated assessment-only mode until PASS
3. `requirements-coverage-gap-loop` in delegated assessment-only mode until PASS
4. `requirements-satisfaction-gap-loop` in delegated assessment-only mode until PASS
5. `plan-playbook`
6. `verify-plan` using parent-managed verifier -> critic -> orchestrator-fix cycles until PASS
7. coverage then satisfaction assessment-only gates on the plan until PASS
8. `write-code-playbook`
9. independent execution verification using the plan's commands and success criteria
10. `verify-work` using parent-managed reviewer -> critic -> orchestrator-fix cycles

Every stage returns `PASS`, `GAPS`, `BLOCKED`, or `CAP_REACHED`.

- `PASS`: advance.
- `GAPS`: orchestrator fixes, increments the stage attempt, and delegates a fresh pass.
- `BLOCKED`: record exact unblock evidence and stop.
- `CAP_REACHED`: require continuation approval; never reinterpret it as PASS.

## Review Loop

Review against the objective, hardened research, hardened plan, all recorded diffs, runtime evidence, and every assigned requirement.

A gap finding shows correctness, coverage, contract alignment, runtime behavior, verification, or implementation completeness is not satisfied. Style, optional cleanup, and future improvements are non-gaps.

If any critic-validated gap remains, record it, increment the outer iteration, and return to research with the finding and violated requirement as first-class evidence. Stop only when independent review passes, every requirement is satisfied or explicitly excluded with approval, every gap/blocker is terminal, all required commands pass, and slot status is zero.

## Reporting

Lead with what now works and what it enables. Report closed gaps and raw verification evidence. Separate blockers from non-blocking notes. Never substitute stage/process labels for the practical result.
