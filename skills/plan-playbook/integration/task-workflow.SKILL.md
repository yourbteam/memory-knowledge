---
name: task-workflow
description: Use when the user wants work organized as repo task folders under `Tasks/`, with each task containing `analysis.md` and `plan.md`, then executed with size-aware verification and closeout discipline.
metadata:
  short-description: Size-aware task folder workflow
---

# Task Workflow

## Overview

This skill defines the default execution process for this repository.

Each distinct piece of work is treated as a separate task under `Tasks/`, and each task progresses through analysis, planning, execution, and verification using a size-aware path rather than a one-size-fits-all sequence.

Use this skill whenever the user asks to start or continue a task in this repo unless they explicitly override the workflow.

Default execution mode is autonomous. Once a task starts, continue through the full workflow without stopping at each phase boundary unless:

- the user explicitly asks to pause
- a required verification skill cannot be run
- a blocker or ambiguity appears that cannot be resolved safely from repo context
- Planner requires research, implementation approval, or bounded continuation approval

## Relationship To `$task-intake`

When a task is new, ambiguous, or likely to benefit from explicit sizing, use `$task-intake` first.

`$task-intake` should supply:

- task slug
- task type
- task size
- grounding requirements
- required verification stages
- rollout requirements

If the user directly invokes `$task-workflow` without prior intake, perform a lightweight implicit classification before writing artifacts.

## Required Task Structure

For every task, create a folder under `Tasks/` using a short descriptive slug.

Each task folder must contain:

- `analysis.md`
- the Planner package rooted at `plan.md`

`analysis.md` is a non-package sibling. Planner owns every package file and its controller state beneath `<task-root>/.plan-playbook/`.

Recommended task folder naming:

- `Tasks/mssql-schema-migration`
- `Tasks/controller-mapping`
- `Tasks/foreign-key-inference`

If the user does not supply a task name, choose a short clear slug based on the work.

## Size Modes

Every task should be handled in one of these modes:

### `light`

Use for:

- small local fixes
- narrow docs changes
- isolated tests
- low-risk, small-blast-radius work

Default expectations:

- concise `analysis.md`
- focused validation
- verifier stages optional unless risk increases

### `standard`

Use for:

- normal feature work
- moderate multi-file changes
- meaningful contract or integration risk inside one repo

Default expectations:

- normal `analysis.md`
- Planner selects and enforces the applicable planning profile and all plan hardening
- `verify-analysis` and `verify-work` used when justified by risk or change size

### `heavy`

Use for:

- migrations
- production rollout
- remote environment or data changes
- architectural changes
- multi-system or high-blast-radius work

Default expectations:

- detailed `analysis.md`
- `verify-analysis` required
- Planner selects and enforces the applicable planning profile and all plan hardening
- `verify-work` required
- rollout and closeout sections required

The task-workflow size is an execution and analysis classification. It does not select a separate plan-hardening path or bypass the profile that Planner derives from grounded plan characteristics.

## Standard Sequence

Follow this order unless the user explicitly asks to skip or reorder steps:

### 1. Create or locate the task folder

- Ensure `Tasks/` exists at repo root.
- Create the task subfolder if it does not already exist.
- Reuse the existing task folder if the work is a continuation of the same task.

### 2. Write `analysis.md`

Capture:

- task objective
- task type and size
- current-state facts
- source artifacts inspected
- constraints, risks, and unknowns
- grounding requirements
- recommended approach

For `heavy` tasks, also include:

- rollout surfaces
- remote state dependencies
- operator or environment assumptions

### 3. Harden the analysis

After `analysis.md` has a serious first pass:

- `light`: optional unless risk increased during analysis
- `standard`: recommended when the analysis drives implementation choices
- `heavy`: required

If used, invoke:

```text
Use $verify-analysis to verify and harden the analysis in Tasks/<task-name>/analysis.md.
```

Do not stop to ask for permission to continue unless the user asked to pause.

### 4. Run the canonical planning lifecycle once

Invoke canonical `$plan-playbook` exactly once for the task root. Give it the objective, evidence, allowed repositories and paths, constraints, exclusions, and the existing caller-owned `Tasks/<task-name>/` directory. Do not run a second task-workflow planning path, direct `verify-plan`, requirements-coverage gate, or requirements-satisfaction gate over the same plan; Planner owns those stages and their revision lineage.

Planner owns drafting, its fixed hardening order, revision receipts, the implementation-approval payload, and package emission. Consume `plan.md` only when controller state is `EMITTED`, `.plan-package-invalidated.json` is absent, and this canonical read-only boundary succeeds:

```text
python3 skills/plan-playbook/scripts/plan_package.py validate-package <task-root>
```

Then call `show` and use the controller state as the only planning and authorization authority:

```text
python3 skills/plan-playbook/scripts/plan_package.py show <task-root>/.plan-playbook/state.json
```

While the package is drafting, hardening, `READY`, blocked, capped, or invalidated, the current content-addressed controller snapshot is the sole planning authority. An old root `plan.md` may remain as historical emission evidence but must not be presented, implemented, or resumed as current.

### 5. Obtain controller-owned implementation authorization

After every successful package validation, branch only from `show`:

- `NOT_REQUESTED`: run `prepare-implementation-authorization` at its deterministic request path.
- `AWAITING_RESPONSE`: exact-replay preparation if needed, present the existing request, and remain blocked pending a valid response.
- `AUTHORIZED`: do not prepare or prompt again; validate the existing authorization receipt.

For an ordinary task, present the state-bound request's exact granular changes, practical consequence, estimated cost, and required confirmation. Pass only the user's raw response bytes to `record-implementation-authorization`; do not synthesize approval, create a second task state, or persist a duplicate request or receipt identity.

```text
python3 skills/plan-playbook/scripts/plan_package.py prepare-implementation-authorization <plan-state-json> --out <plan-run-root>/authorizations/implementation-request-r<revision>.json
python3 skills/plan-playbook/scripts/plan_package.py record-implementation-authorization <plan-state-json> --request <plan-run-root>/authorizations/implementation-request-r<revision>.json --approval-response <raw-response-file>
python3 skills/plan-playbook/scripts/plan_package.py validate-implementation-authorization <plan-state-json> --authorization <plan-run-root>/authorizations/implementation-r<revision>.json
```

`EMITTED/AWAITING_RESPONSE` is `IMPLEMENTATION_APPROVAL_REQUIRED`. `EMITTED/AUTHORIZED` permits Write Code only after `validate-package` and `validate-implementation-authorization` both succeed. On restart, `AWAITING_RESPONSE` reuses the same request and remains blocked; `AUTHORIZED` resumes without another prompt only after revalidating the request, receipt, package, and controller state.

When task-workflow is delegated by `playbook-convergence-loop`, pass the frozen convergence state to `record-implementation-authorization`. The controller derives the same bounded authorization receipt from the outer authorization and task-workflow creates no second prompt.

Denial, missing evidence, changed package revision, changed scope, source-state drift, receipt tamper, or an invalidation marker blocks implementation.

### 6. Execute the plan

Before implementation starts or resumes, rerun both canonical validations. Then:

- implement the authorized plan
- make the required code, SQL, or documentation changes
- verify locally when possible
- keep work aligned to the validated plan unless new evidence forces a correction

### 7. Control plan drift and revision invalidation

If execution materially changes scope, sequence, contracts, interfaces, migration assumptions, rollout assumptions, or validation method, do not edit the emitted root package.

Call `prepare-revision`, edit only the deterministic non-authoritative proposal files beneath the controller run root, and record the legal `EMITTED -> DRAFTED` successor:

```text
python3 skills/plan-playbook/scripts/plan_package.py prepare-revision <plan-state-json> [--evidence-index <evidence-index-json>]
python3 skills/plan-playbook/scripts/plan_package.py record-revision <plan-state-json> --proposal <plan-run-root>/proposed-revisions/<next-revision>/
```

The revision invalidates the prior package and implementation authorization. Implementation remains blocked while state is not `EMITTED` or `.plan-package-invalidated.json` exists. Resume only after the successor snapshot completes all four Planner stages on one plan hash, `emit-package` commits the successor package, the matching marker is removed, and both package and successor implementation-authorization validation succeed.

Do not let implementation silently diverge from the recorded plan.

### 8. Verify the work

After implementation:

- `light`: optional unless the change surface grew or risk increased
- `standard`: recommended for code-bearing tasks; required when the change is risky enough to justify adversarial review
- `heavy`: required

If used, invoke:

```text
Use $verify-work to review every in-scope change surface, let the parent apply validated fixes, and repeat until convergence. Commit only when separately authorized for the exact repositories.
```

When delegated by `playbook-convergence-loop`, the hardened Planner package supplies bounded edit approval. Run its baseline guard before every edit, verification, review spawn, install, or projection write; use the shared stage-result verdicts; and keep the parent as sole fixer/state writer.

## Blocker Taxonomy

When blocked, classify the blocker explicitly as one of:

- `implementation blocker`
- `environment blocker`
- `access blocker`
- `verification blocker`
- `external dependency blocker`

Do not treat a non-code problem as if it were just a planning-quality problem.

## Authoring Guidance

### `analysis.md` should usually include

- task objective
- task type and size
- current-state findings
- source artifacts inspected
- constraints and unknowns
- risks and edge cases
- recommended approach

### The Planner package should include

- task scope and frozen requirements
- implementation steps and affected surfaces
- grounded decisions and evidence
- validation approach
- dependencies and sequencing
- the profile-required audits and package manifest

### Task closeout should usually include

At the end of the task, update the task artifact with a concise closeout state covering:

- implemented
- locally verified
- remotely verified
- deployed
- pushed
- follow-ups remaining

## Guardrails

- Do not start implementation before producing `analysis.md` and a valid authorized Planner package unless the user explicitly asks to bypass the workflow.
- Keep analysis and the package as living task artifacts under their respective ownership rules.
- Reuse the same task folder for follow-up work on the same objective.
- Create a new task folder when the objective materially changes.
- When writing task docs, prefer repo-relative references and concrete file names.
- If verification skills are unavailable, preserve the Planner terminal verdict and report the blocker; do not substitute a weaker planning path.
- Do not stop at phase boundaries by default, except at controller-owned research, approval, continuation, or blocker boundaries.
- Do not force `heavy` execution process onto obviously `light` work.
- Do not under-classify migration or rollout work as `light` just to move faster.
- Never treat a bare convergence enum, previous approval, or prior package revision as implementation authorization.

## Suggested Invocation Patterns

To start a task with explicit intake:

```text
Use $task-intake for a new task: <objective>, then proceed with $task-workflow.
```

To start directly:

```text
Use $task-workflow for a new task: <objective>.
```

To continue a task:

```text
Use $task-workflow to continue Tasks/<task-name>.
```

To continue a heavy task with explicit analysis and work verification:

```text
Use $task-workflow to continue Tasks/<task-name>, then use $verify-analysis and $verify-work at the appropriate stages. Planner owns all plan hardening.
```
