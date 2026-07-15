---
name: blocker-catalog
description: Use whenever a blocker appears during goal pursuit, verification, package operation, local-image testing, deployment, workflow execution, or playbook convergence work, and again when the blocker fix is implemented or verified.
---

# Blocker Catalog

Use the canonical event ledger immediately when an operational run fails. Do not leave
the failure only in chat, terminal history, or a project-specific Markdown diary.

## Open Before Fix

```bash
python3 scripts/blocker_catalog.py open \
  --run-id "<run-id>" --subject-id "<subject-id>" --step-id "<stable-step>" \
  --surface "<surface>" --error-signature "<stable error signature>" \
  --symptom "<practical symptom>" --evidence "<non-secret evidence>" \
  --impact "<blocked outcome>" --boundary "<suspected stable boundary>"
```

Retain every generated id. An exact retry supplies the same event/occurrence identities.
The blocker fingerprint is lineage-stable and automatically detects a closed recurrence.

## Correct And Verify

After editing the reusable artifact, call `work_memory.py correct` with the run,
blocker, occurrence, step, and every changed artifact. This records bundle A to B; it
does not allow stale A receipts to verify B. The correction must be recorded for the
blocker's current occurrence before transitioning `open` to
`fixed-awaiting-verification`. Then close the original run failed, create a fresh
successor selection for B, and run the same path.

Only a passed `same-path` verification naming the exact blocker/correction ids can move
the blocker to `verified`, then `closed` with `remaining_work=none`:

```bash
python3 scripts/blocker_catalog.py transition --run-id "<run-id>" --blocker-id "<blocker-id>" --to-status fixed-awaiting-verification
python3 scripts/blocker_catalog.py transition --run-id "<successor-run-id>" --blocker-id "<blocker-id>" --to-status verified --verification-event-id "<event-id>"
python3 scripts/blocker_catalog.py transition --run-id "<successor-run-id>" --blocker-id "<blocker-id>" --to-status closed --verification-event-id "<event-id>" --remaining-work none
```

## Recover A Legacy Stranded Blocker

Recovery is exceptional and only repairs a blocker already stranded in
`fixed-awaiting-verification` by a legacy premature transition. Record concrete evidence
that the captured event has no correction, then reopen the same occurrence:

```bash
python3 scripts/blocker_catalog.py recover \
  --run-id "<active-run-id>" --blocker-id "<blocker-id>" \
  --recovery-evidence "<evidence that the legacy transition preceded its correction>"
```

This is the only status transition back to `open`, and empty recovery evidence is
rejected. A correction is still forbidden while the blocker is fixed. After recovery,
follow the normal order: record the correction for the current occurrence, transition
to `fixed-awaiting-verification`, verify through a same-path successor, then close.

`operations/blockers/BLOCKERS.md` is generated. Never edit it as authority. On the next
matching task, use selection-reported eligible corrections before running commands;
stale, proxy-only, superseded, or different-bundle corrections are warnings only.
