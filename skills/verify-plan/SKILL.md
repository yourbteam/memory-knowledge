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

This skill verifies an existing plan from the current conversation or a plan file, then hardens it through a front-loaded implementation-surface map, a finite inventory of checkable plan obligations, deterministic checks, and progressive implementation-readiness passes until every in-scope obligation is supported or the iteration cap is reached.

The goal is one-shot implementation readiness without unnecessary multi-hour rediscovery loops. Efficiency comes from forcing the first pass to build a complete implementation coverage queue and a critic-approved obligation inventory, then forcing every later pass to consume the next highest-risk unsupported obligations. Later passes are not delta-only checks: they verify fixes, check regressions, and continue plan hardening until every obligation is supported.

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

### 2. Freeze the evidence and build the obligation inventory

Before the first verifier pass, freeze the current plan and authoritative evidence revision, then build a concise implementation-surface map, coverage queue, and finite verification-obligation inventory from that snapshot.

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

If the task is broad, group surfaces by subsystem. Do not expand beyond the task scope, but do not leave implementation-critical surfaces implicit.

Decompose each coverage item into the finite obligations that must hold for the plan to be implementation-ready. Each obligation must have:
- a stable obligation ID
- one owning coverage item ID
- one testable claim
- explicit section, evidence, and dependency bindings
- a binding hash derived from the exact bound content

The registries are task-local and content-addressed:
- plan-section records identify the plan path, line interval, and content hash
- evidence records identify the repository key, path, selector, and selected-content hash
- dependency records identify the repository key, path, selector, and selected-content hash

The ledger has one canonical active-plan identity. Its root `active_plan_sha256`,
`plan_verification.plan_sha256`, active inventory `plan_sha256`, and the SHA-256
of the repository-relative `target` bytes must all match. The root field may be
absent only in an empty initialized ledger; once present, disagreement is a
contract error rather than an alternate source of truth.

The evidence revision is independently recomputable. It is the canonical
SHA-256 of the active inventory's complete ordered `evidence_items` and
`dependencies` registries, and must match both the active inventory and
`plan_verification.evidence_revision_sha256`.

Every assessment evidence reference must resolve to an ID in the owning
obligation inventory and registry kind. A BLOCKED boundary must resolve its
`binding_id` in that same inventory, and its `observed_content_sha256` must
equal the frozen record's content hash. Shape-valid foreign or stale references
are invalid.

The critic must independently approve **inventory completeness** against the frozen plan and evidence before any obligation can count as supported. A never-reviewed, structurally valid inventory may produce exactly one bootstrap assignment so the first verifier/critic pair can create that approval. Until the paired critic approves the exact inventory, assessments do not establish coverage, another assignment is refused, and convergence is impossible. A rejected inventory must be rebuilt before assignment resumes. Store the decision in an exact critic snapshot at `.verify-plan/critic-outputs/<attempt-id>.json`; the ledger references both the snapshot hash and the approval hash. Coarse coverage status cannot establish completion.

Create a verification ledger JSON before iteration 1. Calculate SHA-256 identities for the frozen plan bytes and the frozen evidence-revision manifest, then use:

```bash
python3 scripts/verification_ledger.py init --kind plan --plan-sha256 <sha256> --evidence-revision-sha256 <sha256> --output <ledger.json>
```

Keep this ledger task-local when a task folder exists; otherwise keep it in `/tmp` and name it for the target plan. Populate its plan-section, evidence, dependency, obligation, inventory-approval, and critic-output records before iteration 1. Update it after every verifier, critic, and fix step.

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
- the exact assigned obligation IDs returned by `next-assignment`

The verifier must check from the viewpoint of the engineer who must implement the plan in this repo without asking follow-up questions.

Before every verifier pass, run:

```bash
python3 scripts/verification_ledger.py next-assignment <ledger.json> --limit <bounded-count>
```

Record the returned IDs as that iteration's assignment. The verifier must assess every assigned obligation ID exactly once as:
- `SUPPORTED`: the bound plan text and authoritative evidence prove the claim and no actionable finding contradicts it
- `GAP`: the claim is not satisfied and the assessment snapshots one or more immutable actionable findings
- `BLOCKED`: a named external boundary prevents assessment or satisfaction and the assessment records the exact binding, observed content hash, and required boundary change

BLOCKED never counts as complete. An assignment is invalid if it omits an assigned obligation, adds an unassigned obligation, or relies on a prose summary instead of the structured assessments.

For iteration 1, the verifier must check:
- Reference accuracy: file paths, method signatures, entity properties, service names, config entries, and line references
- Implementer clarity: anything that would force the implementer to guess, infer missing behavior, choose between plausible interpretations, or discover hidden scope during implementation
- Completeness and gaps: missing requirements, missing error handling, missing registrations, imports, migrations, config updates, and unresolved placeholders
- Internal consistency: contradictions across sections, wrong file state assumptions, and inconsistent approaches
- Hallucination detection: invented patterns, false technology claims, or architecture assertions not grounded in the codebase
- Obligation support: whether each assigned claim is proved by its section, evidence, and dependency bindings
- Inventory completeness: whether the finite obligation set fully represents the implementation surface and original requirements

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

Verifier output must include the structured obligation assessments plus a structured findings list. For each finding include:
- stable finding ID
- what is wrong
- where it appears in the plan
- evidence from the codebase or source material
- why this creates implementation risk or forces the implementer to guess
- affected implementation-surface map item
- affected coverage item ID
- every affected obligation ID
- whether the finding is new or carried from a prior iteration
- for new findings after iteration 1, whether it came from the coverage queue, was introduced by a fix, was newly revealed by a fix, or was missed in an already-checked coverage item

Critical rule for iteration 1: the verifier reports everything found in the inspected surfaces and does not self-filter for importance, but it does not need to assess every obligation in one pass if the complete inventory is explicit, approved, and prioritized.

Critical rule for iterations 2+: the verifier does not restart open-ended discovery. It must verify prior fixes, inspect changed sections, and consume a meaningful next slice of the coverage queue. New findings from a previously unchecked coverage item are expected and do not need to justify why they were not found earlier.

For iterations 2+, tell the verifier exactly which assigned obligation IDs are in that pass. The verifier may inspect their owning coverage items, bindings, prior fixes, and regressions, but must not re-open unrelated supported obligations unless it names a concrete reason and the ledger first resets those obligations.

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

The critic may approve a coverage exclusion only through the exact evidence-bound exclusion object. The helper derives `checked` and `fixed` from approved obligation history; neither the verifier nor critic authors those states directly.

The critic must additionally:
- approve or reject the finite obligation inventory and its completeness rationale
- approve or reject every verifier obligation assessment against the exact frozen bindings
- return one approval object per assessment with the obligation ID, binding hash, assessment fingerprint, decision, rationale, and evidence IDs
- return any coverage exclusion approval as an explicit, evidence-backed object

The parent writes each raw critic result as a canonical JSON snapshot under `.verify-plan/critic-outputs/` before copying any approval into the ledger. The ledger is invalid if a snapshot is missing, changed, or does not contain the referenced approval.

#### Step 3: Check convergence

Count actionable findings:
- `FIX NOW`
- `IMPLEMENT LATER`

If the actionable count is zero, run `next-assignment` again. Stop only when it returns no obligation IDs and `check --can-stop` succeeds.

If the actionable count is zero but unsupported obligations remain, continue with the next bounded obligation slice. Coverage items may be excluded only through an exact critic approval tied to the active plan, evidence revision, and inventory. BLOCKED obligations stop assignment and convergence until their named boundary changes and the inventory or binding is rebuilt.

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
- every affected obligation ID

Use the ledger to prevent the same issue from being rediscovered under a new label.

Findings are immutable snapshots for the obligation assessments that cite them. Resolving a finding changes only its live status. A `GAP` becomes satisfied only after a later assignment produces a critic-approved `SUPPORTED` assessment against the current binding. If any later finding names a previously supported obligation, reset that obligation and its coverage item to unverified and schedule it again.

After a plan edit, recompute the frozen plan hash and rebuild the active inventory. Reuse an obligation assessment only when its obligation ID, claim, and section, evidence, and dependency bindings are byte-identical and therefore retain the same binding hash. Any changed binding is selectively invalidated and reassigned. The helper derives `checked` and `fixed` coverage states from approved obligation history; callers must not author those states independently.

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
Obligations assessed this iteration: [obligation IDs]
Obligations remaining: [count by owning coverage risk]
```

### 5. Prefer implementation readiness over perfection churn

Stop only when there are no actionable findings that could cause a competent implementer to make the wrong change, miss required work, ship inconsistent behavior, or discover hidden scope during implementation; every non-excluded obligation in the critic-approved active inventory has a current critic-approved `SUPPORTED` assessment; no obligation is `GAP` or `BLOCKED`; and `check --can-stop` succeeds.

Do not continue merely because the plan could be more exhaustive, more polished, or include optional future work. If a finding broadens the task, make it an acknowledged future improvement instead of extending the loop.

If iterations 2+ produce new findings from previously unsupported obligations, that is expected progressive hardening. If a later finding contradicts a supported obligation, reset and reassess it; do not preserve a stale completion state. If broad findings keep escaping supported obligations, stop after the current iteration and report that the inventory or assessment quality failed instead of burning the full cap blindly.

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
| # | Mode | Verifier Findings | FIX NOW | IMPL LATER | ACK | DISMISS | Obligations Assessed | Obligations Remaining |
|---|------|-------------------|---------|------------|-----|---------|----------------------|-----------------------|
| 1 | inventory+slice | ...     | ...     | ...        | ... | ...     | ...                  | ...                   |

### Key Changes Made to Plan
1. [What was changed and why]

### Implementation Surface Coverage
1. [Major surfaces checked]

### Obligation Inventory
1. [Supported, gap, blocked, remaining, or critic-excluded obligations]

### Remaining (if not converged)
1. [Finding] — [why it wasn't resolved]
```

Present the updated plan sections after each iteration with changes, or the full updated plan if the edits are extensive.

## Guardrails

- The verifier must inspect the actual codebase or source files. It does not reason only from the plan text.
- The iteration-1 verifier does not self-filter findings.
- Later verifiers are progressive hardening passes: prior fixes, regressions, changed bindings, and the next obligation slice.
- The critic is the authority on actionability.
- `IMPLEMENT LATER` is treated the same as `FIX NOW`.
- Each iteration works on the updated plan from the prior iteration.
- Do not expand the scope, add features, or optimize beyond what the task requires.
- Preserve working sections; only change sections supported by validated findings.
- Prefer fixing structural defects with deterministic checks before spawning subagents.
- Maintain a findings ledger so repeated issues are not rediscovered under new wording.
- Maintain and validate the verification ledger JSON; do not rely on prose memory or coarse coverage status for completion.
- Assigned obligation IDs must be explicit, finite, and reconciled exactly to the verifier assessments and critic approvals.
- `SUPPORTED`, `GAP`, and `BLOCKED` are the only obligation assessment states; `BLOCKED` never counts as complete.
- Inventory completeness and every assessment require approval preserved in exact `.verify-plan/critic-outputs/` snapshots.
- Completion is derived from active obligation bindings; coarse coverage status cannot establish completion.
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
Verify the updated plan against the prior findings ledger, implementation-surface map, and critic-approved obligation inventory. Assess every assigned obligation ID exactly once as SUPPORTED, GAP, or BLOCKED against its frozen bindings. Focus on resolved findings, changed bindings, regressions, and the next highest-risk unsupported obligations. Do not restart open-ended discovery. New findings from unsupported obligations are valid progressive hardening findings; identify every affected obligation and coverage item.
```

## Suggested Critic Prompt Shape

Use a task framing like:

```text
Review the verifier findings against the actual codebase and classify each as FIX NOW, IMPLEMENT LATER, ACKNOWLEDGE, or DISMISS. Independently verify the evidence rather than trusting the verifier summary.

Judge each finding from the viewpoint of the implementation lead. A finding is FIX NOW if an implementer could reasonably make the wrong change, miss required work, or produce inconsistent behavior because the plan leaves too much implicit.

Also approve or reject inventory completeness and each assigned obligation assessment against its exact section, evidence, and dependency bindings. Return structured approval objects that the parent can preserve unchanged in the task-local critic snapshot.
```

For iterations 2+, add:

```text
For each new finding after iteration 1, also classify it as MISSED IN FIRST PASS, INTRODUCED BY FIX, NEWLY REVEALED, COVERAGE QUEUE, or SCOPE DRIFT. Treat SCOPE DRIFT as non-actionable unless the original scope explicitly requires it. Treat COVERAGE QUEUE as normal progressive hardening, not as a verifier failure.
```
