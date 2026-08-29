---
name: task-intake
description: Classify only work that may cross the governed operational boundary, then send operational work to Sequence Runner and return local work to the Working Agreement mode route.
metadata:
  short-description: Operational-boundary classification
---

# Task Intake

Use this skill only when a requested action may cross the governed operational boundary or that
boundary is genuinely unclear. It does not own analysis, planning, implementation, review, or
task-folder creation.

## Run the canonical classifier

Allocate a stable task id and run from the canonical `memory-knowledge` root:

```bash
python3 scripts/work_memory.py classify --task-id "<task-id>" --operation-kind "<kind>" --repeatable "<yes|no>" --meaningful-steps <N>
```

Kinds are `image|container|auth|deploy|workflow-drive|package|database|remote-operator|cleanup|other|read-only|single-test|single-build`.
Use the actual command flow, not the requested deliverable label. Never recreate the classifier
decision in prose.

If the receipt says `operational`, hand the receipt to `sequence-runner` before commands. If it
says `fast-path`, return to the Working Agreement mode route:

- direct evidence inspection for Research or Review;
- `plan-playbook` for Plan;
- `prototype-driven-implementation` for Write code.

## Boundary

Classify before package or environment mutation, database or migration work, containers or images,
authentication or secrets, deployment, remote operators or systems, destructive cleanup, workflow
drives, long live tests, a proven recurrent command sequence, the same execution failure fingerprint
twice, or when the boundary is genuinely unclear.

Do not classify ordinary repository reads, approved local edits, diffs, linters, type checks,
bounded tests, or local installation of an approved managed artifact. Shell use or several local
steps alone do not make work operational.

A self-contained local machinery that owns its own launch, ordering, monitoring, retry,
verification, and stopping remains on the fast path unless its concrete operation independently
crosses the governed boundary.

## Output

Return the classifier receipt and exactly one route:

- `operational` → `sequence-runner`;
- `fast-path` → the Working Agreement mode controller.

Do not create a task folder, analysis document, plan, implementation, or alternate classification
record in this skill.
