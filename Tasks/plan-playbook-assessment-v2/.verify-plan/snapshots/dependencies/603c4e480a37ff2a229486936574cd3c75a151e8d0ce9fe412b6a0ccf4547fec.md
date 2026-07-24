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
- `plan.md`

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
- concise `plan.md`
- focused validation
- verifier stages optional unless risk increases

### `standard`

Use for:
- normal feature work
- moderate multi-file changes
- meaningful contract or integration risk inside one repo

Default expectations:
- normal `analysis.md`
- normal `plan.md`
- `verify-plan` required
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
- detailed `plan.md`
- `verify-analysis` required
- `verify-plan` required
- `verify-work` required
- rollout and closeout sections required

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

### 4. Write `plan.md`

Turn the analysis into an execution plan that is concrete, scoped, and implementation-oriented.

Every plan should include:
- task scope
- implementation steps
- affected files or artifacts
- validation approach
- dependencies or sequencing notes

`heavy` plans must also include:
- implementation section
- local rollout section
- remote rollout section when relevant
- smoke verification section
- rollback or containment notes when relevant
- closeout checklist

### 5. Harden the plan

After `plan.md` has a serious first pass:

- `light`: optional unless the plan carries meaningful risk
- `standard`: required
- `heavy`: required

If used, invoke:

```text
Use $verify-plan to verify and harden the plan in Tasks/<task-name>/plan.md.
```

Do not stop to ask for permission to continue unless the user asked to pause.

### 6. Execute the plan

After the plan is sufficiently hardened:
- implement the plan
- make the required code, SQL, or documentation changes
- verify locally when possible
- keep work aligned to the validated plan unless new evidence forces a correction

### 7. Control plan drift

If execution materially changes any of the following, update `plan.md` before continuing:

- scope
- sequence
- contracts or interfaces
- migration assumptions
- rollout assumptions
- validation method

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

When delegated by `playbook-convergence-loop`, the hardened plan supplies bounded edit approval. Run its baseline guard before every edit, verification, review spawn, install, or projection write; use the shared stage-result verdicts; and keep the parent as sole fixer/state writer.

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

### `plan.md` should usually include

- task scope
- implementation steps
- affected files or artifacts
- validation approach
- dependencies or sequencing notes

### Task closeout should usually include

At the end of the task, update the task artifact with a concise closeout state covering:

- implemented
- locally verified
- remotely verified
- deployed
- pushed
- follow-ups remaining

## Guardrails

- Do not start implementation before producing `analysis.md` and `plan.md` unless the user explicitly asks to bypass the workflow.
- Keep analysis and plan as living task artifacts, not one-off chat outputs.
- Reuse the same task folder for follow-up work on the same objective.
- Create a new task folder when the objective materially changes.
- When writing task docs, prefer repo-relative references and concrete file names.
- If verification skills are unavailable, still follow the same sequence and note that the hardening step could not be run.
- Do not stop at phase boundaries by default. The workflow is meant to execute end-to-end autonomously.
- Do not force `heavy` process onto obviously `light` work.
- Do not under-classify migration or rollout work as `light` just to move faster.

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

To continue a heavy task with explicit hardening:

```text
Use $task-workflow to continue Tasks/<task-name>, then use $verify-analysis, $verify-plan, and $verify-work at the appropriate stages.
```
