---
name: task-intake
description: Use when a new task should be classified before execution so the workflow can choose the right task folder, rigor level, and verification path.
metadata:
  short-description: Task classification and routing
---

# Task Intake

## Overview

This skill is the front-door intake layer for task execution.

Use it before `$task-workflow` when the task is new, ambiguous in scope, or likely to benefit from explicit sizing.

This skill does not replace analysis, planning, or execution. Its job is to classify the task and hand it off cleanly.

## Purpose

The intake step should determine:

- the task slug
- the task type
- the task size
- whether the task must be grounded to a specific repo and project
- whether rollout planning is required
- which verification stages are required

The output should be short, concrete, and operational.

## Mandatory Operation Classification

Allocate a stable task id and run the canonical classifier only before work crosses the governed
operational boundary: package or environment mutation, database or migration work, containers or
images, authentication or secrets, deployment, remote operators or systems, destructive cleanup,
workflow drives, long live tests, a proven recurrent command sequence, the same execution failure
fingerprint twice, or a genuinely unclear boundary. Run from the canonical `memory-knowledge` root:

```bash
python3 scripts/work_memory.py classify --task-id "<task-id>" --operation-kind "<kind>" --repeatable "<yes|no>" --meaningful-steps <N>
```

Kinds are `image|container|auth|deploy|workflow-drive|package|database|remote-operator|cleanup|other|read-only|single-test|single-build`.
Use the actual command flow, not the requested deliverable label. If the receipt says
`operational`, hand off to `sequence-runner` before commands. Do not self-declare an
exception or recreate the classifier logic in prose.

Do not invoke classification for the local-development fast path: repository reads/searches,
approved file edits, repository-local formatting or generation limited to approved files, diffs,
linters, type checks, bounded unit tests, or local installation of an approved managed artifact.
Shell use or three local steps alone do not make work operational. Fast-path work uses G26
preflight, the approved action, and direct verification.

## Classification Outputs

Produce the following:

### 1. Task Slug

Choose a short descriptive slug for `Tasks/<slug>`.

### 2. Task Type

Classify the task as one primary type:

- `exploratory`
- `implementation`
- `migration`
- `rollout`
- `documentation`
- `investigation`
- `workflow/process`

If a task spans multiple types, choose the dominant type and note the secondary concerns.

### 3. Task Size

Classify as exactly one of:

- `light`
- `standard`
- `heavy`

Use these rules:

#### `light`

Use for:
- small local fixes
- narrow documentation changes
- isolated test updates
- low-risk single-surface changes

Characteristics:
- small blast radius
- local validation is sufficient
- no production rollout complexity
- no important migration or multi-system coupling

#### `standard`

Use for:
- normal feature work
- moderate multi-file changes
- local implementation with meaningful validation needs
- tasks where a wrong plan could cause wasted work, but not a dangerous rollout

Characteristics:
- multiple files or subsystems in one repo
- normal code and test work
- some integration or contract risk
- rollout may matter, but is not the dominant challenge

#### `heavy`

Use for:
- schema or data migrations
- production rollout work
- remote environment changes
- architectural changes
- multi-subsystem or multi-repo coupling
- tasks where mistakes are expensive or operationally risky

Characteristics:
- non-trivial blast radius
- remote state matters
- explicit rollout and verification planning required
- stronger hardening required before execution

### 4. Grounding Requirements

State whether the task must be grounded to:

- a specific repository
- a specific project
- a specific environment

For planning or workflow features, grounding should be explicit whenever the task semantics depend on repo/project ownership.

### 5. Verification Requirements

Declare which stages are required:

- `verify-analysis`
- `verify-plan`
- `verify-work`

Default expectation:

- `light`: all optional unless risk is higher than it first appears
- `standard`: `verify-plan` required, others risk-based
- `heavy`: all three required

### 6. Rollout Requirements

Declare whether the task requires any of:

- local rollout section
- remote rollout section
- smoke verification section
- rollback or containment notes

## Handoff To `$task-workflow`

After classification, hand off to `$task-workflow` with a concise result block.

Recommended shape:

```text
Task intake result:
- slug: <task-slug>
- task id: <stable-task-id>
- operation receipt: <classification path/hash and verdict>
- type: <task-type>
- size: <light|standard|heavy>
- grounding: <repo/project/environment requirements>
- required verification: <stages>
- rollout requirements: <required sections>

Proceed with `$task-workflow` using this classification.
```

## Guardrails

- Do not do the full analysis or plan here.
- Do not start implementation here.
- Do not create several competing interpretations unless the ambiguity is real and execution-critical.
- Prefer a decisive classification over an elaborate discussion.
- If the task is clearly a continuation of an existing task folder, say that and hand off without creating a new objective.

## Decision Heuristics

Escalate to `heavy` when any of the following are true:

- remote database changes are involved
- production deployment is involved
- migrations are involved
- several systems must stay in sync
- rollback planning matters
- verifier churn would be expensive if discovered late

Prefer `light` only when failure is cheap and local.

When uncertain between `standard` and `heavy`, bias toward `heavy` if rollout or data integrity is part of the task.
