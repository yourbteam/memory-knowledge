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
    --tests '<the repo's own test command>' --reader-command '<command>' --items <N> \
    --with-body --prepare-universal-paths --repair-reader-records \
    --owner-approved
```

It works out what has to exist before what, writes that order once, then builds: earliest round first, one requirement to
one builder, the tests recorded before anything is touched, then the same sentences checked by two
readers who cannot see each other. An item counts only when the final test command exits zero,
nothing that passed before fails, no test disappears without an exact owner ruling, and both
readers say yes with repository-resolved citations. Parsed pytest failure names are diagnostics,
never a substitute for the command exit code. `--items` is how many items may finish unattended.

Give `--order <order.json>` instead of `--report` when the order already exists; `run.py` produces one on its own if you ever want it separately.

Use `--owner-approved` only after the owner explicitly approves the bounded machinery run. It
relays that existing authority to one-shot workers so they do not stop to ask again; it never
authorizes unrelated edits, commits, pushes, deployments, destructive actions, credentials,
external messages, or paths outside the item brief. The launcher also gives each worker a uv cache
inside that worker's own scratch directory and disables dependency synchronization there. The
repository's prepared environment is used without package mutation, so the prescribed test command
remains unchanged and works inside a sandboxed client; the machinery's own before/after gates still
run that same command normally.

The builder and both blind readers automatically receive a bounded mechanical path manifest
instead of a dump of every definition:
all current matches for each cited line up to the explicit cap, their enclosing symbols, direct
source consumers, calls made later in those consumers, and tests that call the same symbols.
The machinery records a neutral symbol before-image before the builder starts, then independently
derives the changed-symbol, consumer, transformation, and focused-test paths for each reader. The
manifest includes no builder explanation or sibling answer, never limits what a reader may inspect,
never contributes to the verdict, ignores task snapshots and generated environments, and says
plainly when a fixed cap requires opening the source. `--reader-map` remains accepted only for
command compatibility. The two-reader gate and the final test gate are unchanged.

The manifest also produces a runnable focused-test handoff from its direct test callers. Builders
and readers can exercise the changed behavior through the repository's real test entry point
without rediscovering setup. When no focused caller exists, it supplies the full test command and
says why. This handoff is navigation only and never contributes to acceptance. Every worker packet
pre-chunks stable worker directives, repository root, test command, output and scratch locations,
then the item task; workers do not need to reread broad standing-instruction files.

Every reader `yes` is resolved before acceptance: its path must remain inside the built repository,
its line must exist, and its quoted text must equal that repository line character for character.
Any non-zero final test exit, unresolved citation, or unapproved disappeared test refuses the item
with the exact failing identity and correction needed.

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
  write one yourself and never paraphrase one. A disappeared test requires a structured ruling
  under that item, keyed by the exact collected test identity, with `authorized: true`, the
  `owner_ruling`, and non-empty `replacement_or_remaining_coverage`. A ruling for another test or
  one without its coverage record does not authorize the disappearance:

  ```json
  {
    "r1": {
      "test_removals": {
        "tests/test_subject.py::test_old_path": {
          "authorized": true,
          "owner_ruling": "The obsolete path may be removed.",
          "replacement_or_remaining_coverage": "test_new_path covers the replacement."
        }
      }
    }
  }
  ```
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
