---
name: verify-plan
description: Use when the user wants a plan from the current conversation or a plan file verified and hardened for reference accuracy, implementer clarity, completeness, internal consistency, and hallucinations through an iterative verifier-critic-fix loop. Best for implementation, architecture, migration, and code change plans.
metadata:
  short-description: Iterative plan verification loop
---

# Verify Plan

## Convergence Delegation

When called by `playbook-convergence-loop`, verifier and critic agents are assessment-only. They receive the objective, requirements, plan, authoritative evidence, and raw findings, but not producer rationale or hidden answers. The parent guards the baseline, applies fixes, writes state, and returns the shared `PASS|GAPS|BLOCKED|CAP_REACHED` envelope. No commits by default.

## Overview

This skill verifies an existing plan from the current conversation or a plan file, then hardens it through a front-loaded implementation-surface map, deterministic checks, and progressive implementation-readiness passes until no actionable findings remain and the in-scope coverage queue is exhausted or the iteration cap is reached.

The goal is one-shot implementation readiness without unnecessary multi-hour rediscovery loops. Efficiency comes from forcing the first pass to build a complete implementation coverage queue and forcing every later pass to consume the next highest-risk unverified slice. Later passes are not delta-only checks: they verify fixes, check regressions, and continue plan hardening until the coverage queue is empty.

Use this for plans describing what to build or change. If the conversation does not clearly contain the target plan, ask the user to identify which plan to verify before proceeding.

## Workflow

### 1. Confirm the target plan

Identify the plan already present in the conversation context or the plan file the user wants checked.

Valid targets include:
- Plan mode outputs
- implementation plans
- architecture plans
- migration plans
- structured plan artifacts written to files

If multiple candidate plans exist, ask which one to verify. If no plan is visible, ask the user to provide or identify it.

### 2. Build the implementation-surface and coverage map

Before the first verifier pass, build a concise implementation-surface map and coverage queue from the target plan and repository.

The map must include every in-scope surface an implementer would need to touch or preserve, such as:
- files, directories, modules, packages, and generated artifacts
- entry points, routes, commands, jobs, services, validators, hooks, and scripts
- request/response contracts, schemas, database tables, migrations, config, environment variables, and feature flags
- tests, fixtures, docs, deployment steps, observability, logs, metrics, and rollback/recovery paths
- data flow, control flow, persistence flow, retry/error handling, and compatibility paths
- personas, workflow phases, artifact roles, or gate contracts when the plan changes workflow behavior

For each coverage item, record:
- item ID
- subsystem or artifact
- why it is in scope
- risk level: high, medium, or low
- source files or evidence to inspect
- implementation risk if missed
- status: unverified, checked, fixed, out of scope, or deferred by critic

If the task is broad, group surfaces by subsystem. Do not expand beyond the task scope, but do not leave implementation-critical surfaces implicit. The coverage queue is the control mechanism for convergence: a clean pass does not end the loop while high- or medium-risk in-scope items remain unverified.

Create a verification ledger JSON before iteration 1. Use `python3 scripts/verification_ledger.py init --kind plan` for the required shape. Keep this ledger task-local when a task folder exists; otherwise keep it in `/tmp` and name it for the target plan. Update it after every verifier, critic, and fix step.

Run `python3 scripts/verification_ledger.py check <ledger.json>` before spawning each verifier. Run `python3 scripts/verification_ledger.py check <ledger.json> --can-stop` before declaring convergence. If `--can-stop` reports blockers, continue the loop instead of producing a final summary.

### 3. Run deterministic prechecks

Before spawning a verifier, run cheap deterministic checks when they are applicable to the plan.

Examples:
- required headings or sections
- unresolved placeholders or draft language
- repo-relative path existence
- line-reference sanity
- referenced file/module/class/function existence
- artifact role names or schema names
- JSON/YAML parse checks
- known forbidden strings, malformed references, or contradiction markers

If a deterministic check finds a structural issue, fix it before the expensive verifier pass unless the issue changes the plan meaning. Log these as deterministic updates, not verifier findings.

Do not use deterministic checks as a substitute for implementation-readiness review. They only remove structure noise before reasoning-heavy review.

### 4. Run iterative verification

Run up to 10 iterations. Each iteration verifies the latest updated version of the plan, not the original.

Iteration 1 is a broad inventory and first high-yield implementation-readiness pass. Iterations 2+ are progressive hardening passes.

For each iteration:

#### Step 1: Delegate verification

Spawn a verifier subagent. Give it:
- the current plan text
- the task and plan scope
- the implementation-surface map
- the verification ledger JSON
- the findings ledger from prior iterations, if any
- the repo or files it must inspect

The verifier must check from the viewpoint of the engineer who must implement the plan in this repo without asking follow-up questions.

For iteration 1, the verifier must check:
- Reference accuracy: file paths, method signatures, entity properties, service names, config entries, and line references
- Implementer clarity: anything that would force the implementer to guess, infer missing behavior, choose between plausible interpretations, or discover hidden scope during implementation
- Completeness and gaps: missing requirements, missing error handling, missing registrations, imports, migrations, config updates, and unresolved placeholders
- Internal consistency: contradictions across sections, wrong file state assumptions, and inconsistent approaches
- Hallucination detection: invented patterns, false technology claims, or architecture assertions not grounded in the codebase
- Coverage: whether each relevant item in the implementation-surface map is addressed, preserved, explicitly excluded, or listed as unknown
- Coverage planning: whether the coverage queue is complete enough to drive later passes

The verifier should be especially strict about:
- scope boundaries: what is in scope, out of scope, or follow-up work
- caller-visible contracts: request/response fields, nullability, defaults, clearing behavior, error behavior, empty-result behavior
- implementation-path detail: which modules/files must change, which existing repo patterns must be followed, and what registrations/docs/tests/setup steps are required
- data semantics: fact grain, join paths, cardinality, dedupe rules, eligibility rules, ordering, and tie-breakers
- hidden assumptions: facts the plan assumes the implementer already knows from the codebase but does not state

For iterations 2+, the verifier must focus on:
- findings previously classified as actionable
- sections changed since the previous iteration
- regressions introduced by fixes
- implementation-surface map items affected by the changes
- the next highest-risk unchecked items in the coverage queue
- newly discovered implementation risks from those coverage items, newly exposed by a fix, or introduced as regressions

Verifier output must be a structured findings list. For each finding include:
- stable finding ID
- what is wrong
- where it appears in the plan
- evidence from the codebase or source material
- why this creates implementation risk or forces the implementer to guess
- affected implementation-surface map item
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

The critic must judge findings from an implementation-readiness perspective, not only factual correctness. A finding is `FIX NOW` if an implementer could reasonably make the wrong change, miss required work, or ship inconsistent behavior because the plan leaves too much implicit.

The critic must classify each finding as exactly one of:
- `FIX NOW`
- `IMPLEMENT LATER`
- `ACKNOWLEDGE`
- `DISMISS`

Treat `IMPLEMENT LATER` as actionable in the current iteration. Nothing is deferred.

For iterations 2+, the critic must also classify every new finding as one of:
- `MISSED IN FIRST PASS`: valid and should have been found earlier
- `INTRODUCED BY FIX`: valid regression from the latest update
- `NEWLY REVEALED`: valid because the fix exposed a previously hidden implementation issue
- `COVERAGE QUEUE`: valid issue from an in-scope coverage item not previously checked
- `SCOPE DRIFT`: not required for the current plan

`MISSED IN FIRST PASS`, `INTRODUCED BY FIX`, `NEWLY REVEALED`, and `COVERAGE QUEUE` may be actionable. `SCOPE DRIFT` must be `DISMISS` or `ACKNOWLEDGE`.

The critic must also approve coverage status changes. A high- or medium-risk item may move to `checked`, `out_of_scope`, or `deferred_by_critic` only when the critic agrees the inspected evidence is sufficient for that status.

#### Step 3: Check convergence

Count actionable findings:
- `FIX NOW`
- `IMPLEMENT LATER`

If the actionable count is zero and the coverage queue has no unchecked high- or medium-risk in-scope items, stop and produce the final summary.

If the actionable count is zero but the coverage queue still contains high- or medium-risk in-scope items, continue with the next coverage slice. Low-risk remaining items may be marked `deferred by critic` only when the critic explicitly agrees they would not cause a competent implementer to guess, miss required work, or ship inconsistent behavior.

#### Step 4: Update the plan

For every `FIX NOW` and `IMPLEMENT LATER` finding:
- re-read the relevant plan section and the source files that govern the correction
- replace wrong references with verified ones
- add missing sections or missing steps required by the task
- remove or replace hallucinated claims with verified facts
- expand incomplete coverage only enough to satisfy the original task
- resolve contradictions while preserving sections that passed verification

Do not gold-plate or expand scope beyond the task the plan is meant to satisfy.

Maintain a findings ledger after every update. The ledger must record:
- finding ID
- iteration first seen
- critic classification
- new-finding classification for iterations 2+
- action taken or reason no change was made
- section updated
- affected implementation-surface map item
- coverage item status after the update

Use the ledger to prevent the same issue from being rediscovered under a new label.

After updating the plan, update the verification ledger and run `python3 scripts/verification_ledger.py check <ledger.json>`. Do not start the next iteration with an invalid ledger.

#### Step 5: Log the iteration

After each iteration, append this log block:

```text
--- Plan Verification Iteration N ---
Findings from verifier: X
FIX NOW: Y (plan updated)
IMPLEMENT LATER: Z (promoted to FIX NOW, plan updated)
ACKNOWLEDGE: A (no change)
DISMISS: B (no change)
New after iteration 1: N (coverage queue: Q, missed in already-checked coverage: M, introduced by fix: I, newly revealed: R, scope drift: S)
Coverage checked this iteration: [coverage item IDs]
Coverage remaining: [high/medium item count, low item count]
```

### 5. Prefer implementation readiness over perfection churn

Stop only when there are no actionable findings that could cause a competent implementer to make the wrong change, miss required work, ship inconsistent behavior, or discover hidden scope during implementation, and the coverage queue has no unchecked high- or medium-risk in-scope items.

Do not continue merely because the plan could be more exhaustive, more polished, or include optional future work. If a finding broadens the task, make it an acknowledged future improvement instead of extending the loop.

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
## Plan Verification Summary

**Iterations completed:** N
**Total findings reviewed:** X
**Total plan updates applied:** Y
**Convergence:** YES/NO

### Iteration Log
| # | Mode | Verifier Findings | FIX NOW | IMPL LATER | ACK | DISMISS | Coverage Checked | Coverage Remaining |
|---|------|-------------------|---------|------------|-----|---------|------------------|--------------------|
| 1 | inventory+slice | ...     | ...     | ...        | ... | ...     | ...              | ...                |

### Key Changes Made to Plan
1. [What was changed and why]

### Implementation Surface Coverage
1. [Major surfaces checked]

### Coverage Queue
1. [Checked, remaining, deferred, or out-of-scope coverage items]

### Remaining (if not converged)
1. [Finding] — [why it wasn't resolved]
```

Present the updated plan sections after each iteration with changes, or the full updated plan if the edits are extensive.

## Guardrails

- The verifier must inspect the actual codebase or source files. It does not reason only from the plan text.
- The iteration-1 verifier does not self-filter findings.
- Later verifiers are progressive hardening passes: prior fixes, regressions, changed sections, and the next coverage-queue slice.
- The critic is the authority on actionability.
- `IMPLEMENT LATER` is treated the same as `FIX NOW`.
- Each iteration works on the updated plan from the prior iteration.
- Do not expand the scope, add features, or optimize beyond what the task requires.
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
Verify the attached plan against the actual codebase as the engineer who must implement it in this repo without asking follow-up questions. Find anything that would force the implementer to guess, infer missing behavior, choose between plausible interpretations, or discover hidden scope during implementation.

Check especially for:
- wrong references
- missing steps or missing required work
- contradictions
- unclear scope boundaries
- underspecified caller-visible contracts
- ambiguous data semantics such as grain, join path, cardinality, dedupe, ordering, or tie-breakers
- missing implementation-path details such as modules, registrations, migrations, config, tests, docs, or setup steps
- hidden assumptions not stated in the plan
- hallucinated claims not grounded in the repo

Do not fix anything. Do not self-filter.

For each finding, include:
- what is wrong
- where it appears in the plan
- concrete evidence from the files
- why this creates implementation risk
```

For iterations 2+, use a progressive hardening prompt shape:

```text
Verify the updated plan against the prior findings ledger, implementation-surface map, and coverage queue. Focus on resolved findings, changed sections, regressions, and the next highest-risk unchecked coverage items. Do not restart open-ended discovery. New findings from unchecked coverage items are valid progressive hardening findings; identify the coverage item for each one.
```

## Suggested Critic Prompt Shape

Use a task framing like:

```text
Review the verifier findings against the actual codebase and classify each as FIX NOW, IMPLEMENT LATER, ACKNOWLEDGE, or DISMISS. Independently verify the evidence rather than trusting the verifier summary.

Judge each finding from the viewpoint of the implementation lead. A finding is FIX NOW if an implementer could reasonably make the wrong change, miss required work, or produce inconsistent behavior because the plan leaves too much implicit.
```

For iterations 2+, add:

```text
For each new finding after iteration 1, also classify it as MISSED IN FIRST PASS, INTRODUCED BY FIX, NEWLY REVEALED, COVERAGE QUEUE, or SCOPE DRIFT. Treat SCOPE DRIFT as non-actionable unless the original scope explicitly requires it. Treat COVERAGE QUEUE as normal progressive hardening, not as a verifier failure.
```
