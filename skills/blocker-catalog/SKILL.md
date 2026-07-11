---
name: blocker-catalog
description: Use whenever a blocker appears during goal pursuit, verification, package operation, local-image testing, deployment, workflow execution, or playbook convergence work, and again when the blocker fix is implemented or verified.
---

# Blocker Catalog

Use this skill to make blockers durable and auditable instead of leaving them in chat,
terminal history, or scattered run notes.

## When To Use

Use this skill immediately when:

- a workflow, package, deployment, local image, auth, status, hydration, prompt, parser,
  phase-ledger, or verification issue blocks the current goal;
- the same failure fingerprint appears a second time;
- goal pursuit pauses for a `playbook-convergence-loop` remediation;
- a blocker fix is implemented, verified, or found incomplete.

## Required Behavior

Before fixing a blocker, create or update a catalog entry with:

- blocker id;
- workflow or surface;
- type;
- task id and run id when available;
- practical symptom;
- confirmed evidence;
- practical impact;
- confirmed or suspected boundary;
- current remaining work.

After implementing a fix, update the same entry with:

- fix status;
- solution summary;
- files or artifacts changed;
- verification evidence;
- remaining work, or `none` when fully verified.

Do not resume the main goal after a blocker fix until the catalog entry says whether the
fix was verified through the same path Kamen uses.

## Script

Use the repo helper instead of hand-formatting entries:

```bash
python3 scripts/blocker_catalog.py --catalog "<catalog.md>" add \
  --id "<ID>" \
  --title "<short title>" \
  --type "<workflow-runtime|operator-package|local-environment|deployment|quality-readiness|status-recovery>" \
  --workflow "<workflow or surface>" \
  --task-id "<task id if known>" \
  --run-id "<run id if known>" \
  --symptom "<what happened in practical terms>" \
  --evidence "<specific command/log/status/artifact evidence>" \
  --impact "<what this prevents or risks>" \
  --boundary "<stable boundary to inspect or fix>" \
  --remaining "<next action>" \
  --blocking-goal
```

When the fix is implemented:

```bash
python3 scripts/blocker_catalog.py --catalog "<catalog.md>" update \
  --id "<ID>" \
  --status "<fixed-awaiting-verification|verified|closed|superseded>" \
  --solution "<what changed and why it addresses the boundary>" \
  --changed "<files, artifacts, or operational sequence changed>" \
  --verification "<tests, package run, local image run, deploy proof, or other evidence>" \
  --remaining "<remaining work or none>"
```

## Default MAWF4 Catalog

For the current MAWF4 local-package validation goal, use:

```text
software company workflows/implementation plans/phase-ledger-harness/mawf4-playbook-real-run-blocker-catalog.md
```

The older issue-notes document may remain as narrative run history, but the blocker
catalog is the control surface for goal pauses, fixes, verification, and convergence.
