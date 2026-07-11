---
name: verify-work
description: Use when recent implementation work needs independent accumulated-surface review, critic validation, targeted fixes by the parent orchestrator, and repeated verification until no actionable gaps remain. Reviews committed, staged, unstaged, and untracked in-scope work from a supplied or discovered baseline. Commits only with explicit commit-scoped approval.
---

# Verify Work

Review implementation against its objective, requirements, hardened plan, runtime evidence, and the complete authorized change surface. Tests support a PASS; they do not define one.

## Scope And Baseline

When the caller supplies convergence state or a baseline, use it without asking for a base commit. Immediately before each deterministic check, reviewer spawn, critic spawn, or finding fix, require its `guard-baseline` command to pass.

For every recorded repository, review committed changes since `base_head`, staged changes, unstaged changes, and untracked files inside allowed paths. Also review changed managed non-Git paths and generated-region evidence. Never infer that `git diff base...HEAD` is the whole task.

Without a supplied baseline, discover the smallest attributable baseline from the current task and ask one clarification only if attribution cannot be established safely.

## Delegation And Ownership

The parent orchestrator owns fixes, task state, baseline advancement, and commits. Reviewer and critic agents are assessment-only. Give them authoritative source roots, exact diff/runtime commands, requirements, plan, artifacts, and raw prior findings; withhold producer rationale, hidden expected answers, and conversational reasoning.

Parent-runtime spawn/wait/close capability determines whether delegation is available. A reviewer lacking child-spawn tools is expected. Follow the slot lifecycle in `skills/_shared/agent_slot_ledger.py`, including runtime close before logical release.

Every delegated result uses `skills/_shared/STAGE_RESULT_CONTRACT.md` and returns `PASS`, `GAPS`, `BLOCKED`, or `CAP_REACHED`.

## Review Cycle

Run up to 10 attempts unless the caller defines a lower cap.

1. Guard the baseline and run applicable deterministic checks.
2. Build or refresh the changed-surface and risk map.
3. Delegate an independent reviewer pass over assigned requirements and every in-scope surface.
4. Pass raw findings to a fresh critic with the same authoritative evidence.
5. The critic classifies each finding as `FIX NOW`, `ACKNOWLEDGE`, or `DISMISS`, with concrete file/line or runtime evidence and practical impact.
6. For actionable gaps, the parent guards again, applies only validated fixes, runs focused verification, advances the expected baseline, and repeats with a fresh reviewer.
7. At the cap return `CAP_REACHED`; continuation requires structured approval.

No agent edits in assessment-only mode. Do not commit by default. A commit requires explicit approval whose scope includes operation `commit`, the exact repository roots, and the current stage/outer iteration.

## PASS Contract

Return PASS only when every assigned requirement is satisfied or approved as excluded, no critic-validated gap remains, all high/medium risk surfaces are checked, required verification artifacts are linked, attribution guards pass, and all runtime agents are closed with zero active slots.

Lead with practical findings, then emit the shared machine-readable stage-result envelope.
