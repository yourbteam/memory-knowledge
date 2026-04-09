# Plan: Task Workflow Readiness

## Scope

Establish a clean, evidence-based readiness position for running the upcoming analytics-tools task through the full `task-workflow` sequence.

This task does not change application code. It confirms workflow prerequisites, documents the actual constraints, and defines how the next task should be executed safely.

## Implementation Steps

1. Locate and continue the dedicated readiness task folder under `Tasks/`.
2. Write the first-pass `analysis.md` against the actual workflow skill definitions and the observed environment behavior.
3. Harden `analysis.md` explicitly through `verify-analysis`.
4. Write `plan.md` capturing the operating rules that the next task must follow.
5. Harden `plan.md` explicitly through `verify-plan`.
6. Conclude the readiness task with explicit guidance for the next analytics-tools task.

## Operating Rules for the Next Task

1. Use a separate task folder for the analytics-tools work.
2. Follow the normal sequence:
   - `analysis.md`
   - `verify-analysis`
   - `plan.md`
   - `verify-plan`
   - execution
   - `verify-work`
3. Treat delegated verification as available but potentially intermittent.
4. If a formal verification skill cannot run cleanly, state that explicitly rather than claiming it completed.
5. Expect occasional escalation requirements for repo inspection and validation commands; do not assume the analytics task can stay entirely within non-escalated sandbox execution.
6. Before running `verify-work`, make sure the implementation being reviewed is committed.
7. Before running `verify-work`, establish an unambiguous base commit and use the documented review scope:
   - `git diff <base_commit>...HEAD`
   - `git log --oneline <base_commit>..HEAD`
8. If the correct base commit or work session is ambiguous, stop and resolve that ambiguity instead of claiming `verify-work` completed.
9. Keep unrelated dirty-worktree changes out of the analytics task’s commit range.

## Affected Artifacts

- `Tasks/task-workflow-readiness/analysis.md`
- `Tasks/task-workflow-readiness/plan.md`

## Validation

1. `analysis.md` must accurately reflect the documented requirements from:
   - `task-workflow`
   - `verify-analysis`
   - `verify-plan`
   - `verify-work`
2. `plan.md` must stay within the readiness task scope and avoid drifting into analytics implementation.
3. The resulting guidance must be specific enough to start the analytics-tools task without another access-readiness pass.

## Completion Criteria

This readiness task is complete when:

- the readiness analysis has been hardened
- the readiness plan has been hardened
- we have a clear yes/no answer on whether the next task can run through the full workflow
- the constraints for `verify-work` and delegated verification are documented for the next task

--- Plan Verification Iteration 1 ---
Findings from verifier: 5
FIX NOW: 4 (plan updated)
IMPLEMENT LATER: 0 (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: 0 (no change)
DISMISS: 1 (no change)
