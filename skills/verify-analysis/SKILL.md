---
name: verify-analysis
description: Use when the user wants a prior analysis in the current conversation verified and hardened for factual accuracy, completeness, conclusion quality, and scope consistency through an iterative verifier-critic-fix loop. Best for analyses of code, architecture, security, personas, configs, dependencies, or process evaluations. Not for implementation plans.
metadata:
  short-description: Iterative analysis verification loop
---

# Verify Analysis

## Convergence Delegation

When called by `playbook-convergence-loop`, verifier and critic agents are assessment-only and use the shared stage-result envelope. They can inspect authoritative evidence but receive no producer rationale or hidden answers. The parent alone edits the analysis and state; nested agents never commit or fix.

## Overview

This skill verifies an existing analysis from the current conversation, then hardens it through a front-loaded inventory, deterministic checks, and progressive verification passes until no actionable findings remain and the in-scope coverage queue is exhausted or the iteration cap is reached.

The goal is high confidence without unnecessary multi-hour rediscovery loops. Efficiency comes from forcing the first pass to build a complete coverage queue and forcing every later pass to consume the next highest-risk unverified slice. Later passes are not delta-only checks: they verify fixes, check regressions, and continue source-grounded hardening until the coverage queue is empty.

Use this for analyses of what currently exists. Do not use it for plans describing what to build. If the conversation does not clearly contain the target analysis, ask the user to identify which analysis to verify before proceeding.

## Workflow

### 1. Confirm the target analysis

Identify the analysis already present in the conversation context.

Valid targets include:
- KPI gap analyses
- security audits
- dependency analyses
- architecture or process evaluations
- trade-off comparisons
- codebase health assessments

If multiple candidate analyses exist, ask which one to verify. If no analysis is visible, ask the user to provide or identify it.

### 2. Build the scope, evidence, and coverage map

Before the first verifier pass, build a concise scope map and coverage queue from the target analysis and the repository.

The scope map must include every in-scope surface the verifier should consider, such as:
- files and directories
- workflow names and phases
- artifact roles and artifact filenames
- validators, gates, scripts, and hooks
- personas or agent prompts
- persistence, logging, status, memory, or telemetry surfaces
- runtime recovery, retry, routing, or handoff paths

For each coverage item, record:
- item ID
- subsystem or artifact
- why it is in scope
- risk level: high, medium, or low
- source files or evidence to inspect
- status: unverified, checked, fixed, out of scope, or deferred by critic

If the analysis scope is broad, the map should group surfaces by subsystem. Do not expand beyond the user's stated analysis scope, but do not let important in-scope surfaces remain implicit. The coverage queue is the control mechanism for convergence: a clean pass does not end the loop while high- or medium-risk in-scope items remain unverified.

Create a verification ledger JSON before iteration 1. Use `python3 scripts/verification_ledger.py init --kind analysis` for the required shape. Keep this ledger task-local when a task folder exists; otherwise keep it in `/tmp` and name it for the target analysis. Update it after every verifier, critic, and fix step.

Run `python3 scripts/verification_ledger.py check <ledger.json>` before spawning each verifier. Run `python3 scripts/verification_ledger.py check <ledger.json> --can-stop` before declaring convergence. If `--can-stop` reports blockers, continue the loop instead of producing a final summary.

### 3. Run deterministic prechecks

Before spawning a verifier, run cheap deterministic checks when they are applicable to the analysis.

Examples:
- required headings or sections
- placeholder or draft-language rules
- repo-relative path existence
- line-reference sanity
- artifact role names
- JSON parse/schema checks
- known forbidden strings or malformed references

If a deterministic check finds a structural issue, fix it before the expensive verifier pass unless the issue changes the analysis meaning. Log these as deterministic updates, not verifier findings.

Do not use deterministic checks as a substitute for source inspection. They are only a fast way to remove structure noise before reasoning-heavy review.

### 4. Run iterative verification

Run up to 10 iterations. Each iteration verifies the latest updated version of the analysis, not the original.

Iteration 1 is a broad inventory and first high-yield pass. Iterations 2+ are progressive hardening passes.

For each iteration:

#### Step 1: Delegate verification

Spawn a verifier subagent. Give it:
- the current analysis text
- the analysis scope
- the scope and evidence map
- the verification ledger JSON
- the findings ledger from prior iterations, if any
- the repo or files it must inspect

For iteration 1, the verifier must check:
- Factual accuracy: every concrete claim about files, behavior, signatures, config, line references, or quoted text
- Completeness: missed files, code paths, dependencies, edge cases, or downstream effects inside the stated scope
- Conclusion validity: whether conclusions and severity claims follow from the evidence
- Scope consistency: whether evaluation depth and criteria are applied consistently across the analysis
- Coverage: whether the analysis addresses each relevant item in the scope map or explicitly marks it out of scope or unknown
- Coverage planning: whether the coverage queue is complete enough to drive later passes

For iterations 2+, the verifier must focus on:
- findings previously classified as actionable
- sections changed since the previous iteration
- regressions introduced by fixes
- the next highest-risk unchecked items in the coverage queue
- newly discovered issues from those coverage items, newly exposed by a fix, or introduced as regressions

Verifier output must be a structured findings list. For each finding include:
- stable finding ID
- what is wrong or missing
- where it appears in the analysis
- evidence from the codebase or source material
- affected scope-map item
- affected coverage item ID
- whether the finding is new or carried from a prior iteration
- for new findings after iteration 1, whether it came from the coverage queue, was introduced by a fix, was newly revealed by a fix, or was missed in an already-checked coverage item

Critical rule for iteration 1: the verifier reports everything found in the inspected surfaces and does not self-filter for importance, but it does not need to fully exhaust every coverage item in one pass if the coverage queue is explicit and prioritized.

Critical rule for iterations 2+: the verifier does not restart open-ended discovery. It must verify prior fixes, inspect changed sections, and consume a meaningful next slice of the coverage queue. New findings from a previously unchecked coverage item are expected and do not need to justify why they were not found earlier.

For iterations 2+, tell the verifier exactly which coverage item IDs are assigned for that pass. The verifier may inspect supporting files needed for those IDs, prior fixes, and regressions, but must not re-open unrelated checked items unless it names a concrete reason.

#### Step 2: Delegate criticism

Spawn a critic subagent and pass it the verifier findings plus the relevant repo context. The critic must independently inspect the source material instead of trusting the verifier blindly.

For each finding, the critic checks:
- relevance
- evidence quality
- impact
- actionability

The critic must classify each finding as exactly one of:
- `FIX NOW`
- `IMPLEMENT LATER`
- `ACKNOWLEDGE`
- `DISMISS`

Treat `IMPLEMENT LATER` as actionable in the current iteration. Nothing is deferred.

For iterations 2+, the critic must also classify every new finding as one of:
- `MISSED IN FIRST PASS`: valid and should have been found earlier
- `INTRODUCED BY FIX`: valid regression from the latest update
- `NEWLY REVEALED`: valid because the fix exposed a previously hidden issue
- `COVERAGE QUEUE`: valid issue from an in-scope coverage item not previously checked
- `SCOPE DRIFT`: not required for the current analysis

`MISSED IN FIRST PASS`, `INTRODUCED BY FIX`, `NEWLY REVEALED`, and `COVERAGE QUEUE` may be actionable. `SCOPE DRIFT` must be `DISMISS` or `ACKNOWLEDGE`.

The critic must also approve coverage status changes. A high- or medium-risk item may move to `checked`, `out_of_scope`, or `deferred_by_critic` only when the critic agrees the inspected evidence is sufficient for that status.

#### Step 3: Check convergence

Count actionable findings:
- `FIX NOW`
- `IMPLEMENT LATER`

If the actionable count is zero and the coverage queue has no unchecked high- or medium-risk in-scope items, stop and produce the final summary.

If the actionable count is zero but the coverage queue still contains high- or medium-risk in-scope items, continue with the next coverage slice. Low-risk remaining items may be marked `deferred by critic` only when the critic explicitly agrees they do not affect correctness, completeness, evidence quality, or scope consistency for the current analysis.

#### Step 4: Update the analysis

For every `FIX NOW` and `IMPLEMENT LATER` finding:
- re-read the relevant source files
- correct factual errors
- add missed gaps supported by evidence
- revise conclusions that do not match the evidence
- expand under-examined sections only enough to reach consistent depth within the original scope
- preserve sections that passed verification

Do not expand the scope beyond what the analysis originally set out to examine.

Maintain a findings ledger after every update. The ledger must record:
- finding ID
- iteration first seen
- critic classification
- new-finding classification for iterations 2+
- action taken or reason no change was made
- section updated
- coverage item status after the update

Use the ledger to prevent the same issue from being rediscovered under a new label.

After updating the analysis, update the verification ledger and run `python3 scripts/verification_ledger.py check <ledger.json>`. Do not start the next iteration with an invalid ledger.

#### Step 5: Log the iteration

After each iteration, append this log block:

```text
--- Analysis Verification Iteration N ---
Findings from verifier: X
FIX NOW: Y (analysis updated)
IMPLEMENT LATER: Z (promoted to FIX NOW, analysis updated)
ACKNOWLEDGE: A (no change)
DISMISS: B (no change)
New after iteration 1: N (coverage queue: Q, missed in already-checked coverage: M, introduced by fix: I, newly revealed: R, scope drift: S)
Coverage checked this iteration: [coverage item IDs]
Coverage remaining: [high/medium item count, low item count]
```

### 5. Prefer convergence over perfection churn

Stop only when there are no actionable correctness, completeness, evidence, or scope-consistency findings and the coverage queue has no unchecked high- or medium-risk in-scope items.

Do not continue merely because the analysis could be more exhaustive, more polished, or more future-looking. If a finding would broaden the scope, make it an acknowledged future improvement instead of extending the loop.

If iterations 2+ produce new findings from unchecked coverage-queue items, that is healthy progressive hardening. If they keep producing broad new findings from already-checked coverage items, stop after the current iteration and report that verifier coverage failed for those items instead of burning the full cap blindly.

### 6. Respect the iteration cap

Primary cap: 10 iterations.

If actionable findings still remain after iteration 10, stop and ask:

```text
There are still N actionable findings after 10 iterations. Should I continue for up to 10 more?
```

Only continue if the user approves.

## Required Output

When the loop ends, produce:

```text
## Analysis Verification Summary

**Iterations completed:** N
**Total findings reviewed:** X
**Total analysis updates applied:** Y
**Convergence:** YES/NO

### Iteration Log
| # | Mode | Verifier Findings | FIX NOW | IMPL LATER | ACK | DISMISS | Coverage Checked | Coverage Remaining |
|---|------|-------------------|---------|------------|-----|---------|------------------|--------------------|
| 1 | inventory+slice | ...     | ...     | ...        | ... | ...     | ...              | ...                |

### Key Changes Made to Analysis
1. [What was changed and why]

### Scope Coverage
1. [Major surfaces checked]

### Coverage Queue
1. [Checked, remaining, deferred, or out-of-scope coverage items]

### Remaining (if not converged)
1. [Finding] — [why it wasn't resolved]
```

Also present the updated analysis sections when changes were made during the loop.

## Guardrails

- The verifier must inspect the actual codebase or source files. It does not reason only from the analysis text.
- The iteration-1 verifier does not self-filter findings.
- Later verifiers are progressive hardening passes: prior fixes, regressions, changed sections, and the next coverage-queue slice.
- The critic is the authority on actionability.
- `IMPLEMENT LATER` is treated the same as `FIX NOW`.
- Each iteration works on the updated analysis from the prior iteration.
- Do not add new KPIs, evaluation targets, or criteria outside the original scope.
- Preserve working sections; only change sections supported by validated findings.
- Prefer fixing structural defects with deterministic checks before spawning subagents.
- Maintain a findings ledger so repeated issues are not rediscovered under new wording.
- Maintain and validate the verification ledger JSON; do not rely on prose memory for coverage.
- Require any new finding after iteration 1 to name its source: coverage queue, introduced by fix, newly revealed, missed in already-checked coverage, or scope drift.
- Never treat a clean delta/regression check as convergence while in-scope coverage remains.
- Reviewer and fixer must stay separate. The main agent performs fixes, but verification must be delegated to a verifier subagent.
- Determine subagent availability from the parent runtime's spawn/wait/close capability. A delegated agent lacking child-spawn tools is expected. If the parent runtime lacks delegation, say so and stop rather than collapsing verifier, critic, and fixer into one role.

## Suggested Verifier Prompt Shape

Use a task framing like:

```text
Verify the attached analysis against the actual codebase. Find factual errors, missed gaps, unsupported conclusions, and scope inconsistency. Do not fix anything. Do not self-filter. For each finding, include what is wrong or missing, where it appears in the analysis, and concrete evidence from the files.
```

For iterations 2+, use a progressive hardening prompt shape:

```text
Verify the updated analysis against the prior findings ledger, scope map, and coverage queue. Focus on resolved findings, changed sections, regressions, and the next highest-risk unchecked coverage items. Do not restart open-ended discovery. New findings from unchecked coverage items are valid progressive hardening findings; identify the coverage item for each one.
```

## Suggested Critic Prompt Shape

Use a task framing like:

```text
Review the verifier findings against the actual codebase and classify each as FIX NOW, IMPLEMENT LATER, ACKNOWLEDGE, or DISMISS. Independently verify the evidence rather than trusting the verifier summary.
```

For iterations 2+, add:

```text
For each new finding after iteration 1, also classify it as MISSED IN FIRST PASS, INTRODUCED BY FIX, NEWLY REVEALED, COVERAGE QUEUE, or SCOPE DRIFT. Treat SCOPE DRIFT as non-actionable unless the original scope explicitly requires it. Treat COVERAGE QUEUE as normal progressive hardening, not as verifier failure.
```
