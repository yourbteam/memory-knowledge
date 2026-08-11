---
name: description-machinery
description: Turns what a system's own work left behind — the notes builders wrote about what they saw and deliberately did not touch — into one description of the subject, quoted from those notes, that the requirements machinery can consume. It judges nothing itself: readers who cannot see each other decide what is a distinct thing, what is still work, what is already required, and when different people saw one fault; code only assembles and quotes.
---

# Description machinery

This is the first machinery in the chain. It produces the document the requirements machinery
consumes, and nothing else. It never writes requirements, never says what should be done, and never
puts a sentence of its own into what it hands on.

This skill is the complete local controller for its description loop. Invoke it directly: do not
put `task-intake`, `sequence-runner`, registry selection, or sequence discovery around it solely
because it launches readers, resumes from its output directory, retries refused readings, or runs
for a long time. Its output directory is its state and telemetry. Use an operational sequence only
when the concrete run independently crosses an external boundary such as a remote system,
database, container/image, authentication, package/environment mutation, deployment, or
destructive cleanup.

```
python3 collect_noticed.py --work <build-work-dir> --order <order.json> --out <dir> \
    --reader-command '<command>'
```

- **work** — the implementation machine's work directory, where every build left a record of what
  its builder noticed and deliberately did not change.
- **order** — the build list those builds came from, so a reader can say a thing is already
  required and drop it.
- **out** — a fresh directory. State lives there and the run is resumable.
- **reader-command** — a command that takes an instruction on standard input and carries it out.
  Given one, the step runs its own readers. This machinery never chooses a reader; you supply the
  command and every reader records what it is.

## What comes out

`noticed-description.md` — the thing to use. One entry per distinct observation, quoted exactly as
the builder wrote it, with every build that met it listed. **These are observations, not
requirements.** A builder's note is often a statement of fact — "eight tests already fail" — and
nobody can make a statement true. Put this through the requirements machinery, which is what turns
an observation into something with a check somebody else can run, and build from what that
produces.

`noticed-report.json` — the same list in build shape, for the rare case where the observations are
already requirements. Reaching for it first is how a builder gets handed a sentence it must refuse.

## How it decides, and what it refuses to decide

Six readers, in three pairs, and agreement or nothing:

1. Two read the same records and cut the prose into distinct things, each carrying words copied
   from the record. Code cannot do this: two-thirds of the notes number nothing, measured.
2. Code pairs each reader's things against the other's, within one note only. It proposes; it
   judges nothing.
3. Two judge every pair — same thing, still work in the built system, already covered by a
   requirement on the list.
4. Two more judge whether things different builders noticed separately are one thing. Without this
   step, one fault met by seventeen builders arrives as seventeen pieces of work; measured on the
   first real run, which produced forty-five candidates and twenty-three after joining.

Then code assembles and quotes. A thing enters only where both readers of a pair agreed.

Nothing here is yours except supplying the reader and starting it. If a stage's answer looks wrong,
run that reading again — never edit its output.
