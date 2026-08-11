---
name: implementation-machine
description: Builds what a requirements breakdown says is still to build, into a real system, one item at a time. It orders the work, hands one requirement at a time to a builder, records which tests already failed before anything was touched, and counts an item only when two blind readers each say every part of it is true of the changed code. Give it a reader command and it runs itself.
---

# Implementation machine

Give it the requirements machine's report and a command that runs a reader. It does the rest.

This skill is the complete local controller for its build loop. Invoke it directly: do not put
`task-intake`, `sequence-runner`, registry selection, or sequence discovery around it solely
because it launches builders/readers, monitors a feed, retries refused work, or runs for a long
time. Its work directory and feed are its state and telemetry. Use an operational sequence only
when the concrete build independently crosses an external boundary such as a deployment, remote
system, database, container/image, authentication, package/environment mutation, or destructive
cleanup.

```
python3 build_next.py --report <requirements-report.json> --work <dir> --built <repo> \
    --tests '<the repo's own test command>' --reader-command '<command>' --items <N>
```

It works out what has to exist before what, writes that order once, then builds: earliest round first, one requirement to
one builder, the tests recorded before anything is touched, then the same sentences checked by two
readers who cannot see each other. An item counts only when nothing that passed before fails and
both readers say yes, citing the code. `--items` is how many items may finish unattended.

Give `--order <order.json>` instead of `--report` when the order already exists; `run.py` produces one on its own if you ever want it separately.

Without `--reader-command` it hands the reading back instead of running it. Then, and only then,
launch **one agent per job, all of them, in parallel**, each given its `instruction` verbatim and
nothing else — two jobs of one stage are two independent readers, and agreement between readers who
could not see each other is the only evidence this machinery accepts.

## Three things are yours

- **The reader.** The machine never chooses one; you supply the command and every reader records
  what it was.
- **A ruling.** When a builder refuses because the requirement and the system's own tests disagree,
  only the owner can say which is wrong. Put their answer **in their words** in `rulings.json` in
  the work directory, keyed by item id. It is quoted verbatim into the build instruction. Never
  write one yourself and never paraphrase one.
- **Starting it again.** It stops at `--items`, or when a round of reading changes nothing.

Everything else — which item is next, what the builder is told, whether an item counts — is the
machine's, and a gate that refuses means run that reading again, never fix its output by hand.

## What the builders noticed

Each build reports what else it saw and deliberately did not touch. Those notes are not this
machinery's to turn into work: the `description-machinery` skill takes them, has them read, and
produces the description the requirements machinery consumes. What that chain returns comes back
here as an ordinary build list.

`CHAIN-LEDGER.md` records every failure this machinery has had and what each cost. Read it before
changing anything here.
