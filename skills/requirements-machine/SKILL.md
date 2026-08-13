---
name: requirements-machine
description: Builds the requirements for a change, end to end, from a description of what the thing is for. Writes two documents — the requirements sorted into add, change, remove and already met, and a breakdown into parts, each one thing separately true or false of the build, with the line that proves an already-true part. Invoke this and follow it; do not run its tools by hand or in another order.
---

# Requirements machine

One command owns the order and the gates. This skill owns the one thing a command cannot do:
starting the readers it asks for, and starting them again until it asks for none.

This skill is the complete local controller for its requirements loop. Invoke it directly: do not
put `task-intake`, `sequence-runner`, registry selection, or sequence discovery around it solely
because it launches readers, resumes from its work directory, retries refused readings, or runs
for a long time. Its work directory is its state and telemetry. Use an operational sequence only
when the concrete run independently crosses an external boundary such as a remote system,
database, container/image, authentication, package/environment mutation, deployment, or
destructive cleanup.

**Do not run the tools in this folder by hand.** They were built in an order, each proved before
the next was designed, and the runner is where that order lives. Running one directly skips its
gate, and every gate here exists because something was silently dropped without it.

## What you need

- **subject** — the one thing being changed, named the way its owner names it.
- **description** — the document saying why it should exist, what it is given, what it must do,
  what it must produce, and when it is done. This machinery **consumes** a description; it does
  not write one and it does not repair one. If there is no such document, there are no
  requirements to build yet, and producing one is a separate machinery's job (see the boundary
  below).
- **work directory** — a fresh directory. State lives there and the run is resumable.
- **built** — the repository to measure against. Omit it when nothing is built yet.
- **reader command** — optional. It receives each instruction on standard input. When supplied,
  the controller launches every blind reader itself and runs until a terminal status. Installed
  client projections validate this command before launching anything.

## The loop

```
python3 run.py --subject "<subject>" --description <file.md> --work <dir> \
  [--built <repo>] [--reader-command '<command>']
```

1. Run it. A result has exactly one status: `complete`, `waiting_for_readers`, `blocked`, or
   `needs_owner`.
2. Without `--reader-command`, exit 2 and `waiting_for_readers` are the normal handback contract.
   The result carries a list under `work`. Each entry is one reading job: an
   instruction, the file to read, and the directory the answers go in.
3. **Launch one agent per job, all of them, in parallel.** Give each agent its `instruction`
   verbatim and nothing else. Two jobs of the same stage are two independent readers — never let
   one agent do both, and never tell either what the other found. Agreement between them is the
   only evidence this machinery accepts.
4. When they return, run the command again. It will either hand back the next jobs or finish.
5. Repeat until it stops handing back jobs.

With `--reader-command`, steps 2–5 are owned by the controller. It validates the installed client
runtime before launch, starts every job in the round in parallel, and stops on a terminal status.
Two rounds with no gate-visible progress return `blocked`; they never loop indefinitely.

### Live reader telemetry

While that autonomous loop runs, watch it with:

```text
tail -f <work>/feed.jsonl
```

Every reader launch appends `agent started`, safe streamed `agent` activity, any structured
`agent failure`, and `agent finished`. The events carry the machinery, stable stage/job, blind
reader seat, output identity, process id, duration, exit result, delivery status, raw-log name,
and—after delivery—the model and client harness from that reader's private `reader.json`.
Restarts append new events and use a process-qualified `launch-*.log`; they never overwrite an
earlier launch. The feed deliberately excludes the instruction, model prose, repository content,
and detailed error prose. Lossless stdout and stderr remain in the referenced private raw log for
diagnosis.

Nothing else is yours to decide. Do not re-order stages, do not skip a second pass because the
first looked good, and do not fix a stage's output by hand — if a gate refuses, the reading was
incomplete, and the answer is to run that reading again.

## What comes back

Two documents, always both. `requirements.md` is the requirements themselves, sorted into **add**,
**change**, **remove** and **already met** — the place the reasoning lives and where an argument
about scope happens. `what-to-build.md` is the same answer broken into parts: one entry per thing
that is separately true or false of the build, each already-true part carrying the line that makes
it true. That is what somebody picks up and implements.

Neither replaces the other. A requirement with no breakdown cannot be handed to anyone; a breakdown
with no requirements is a list of jobs with no reason behind them.

Without a repository to measure against, the split still runs and both documents are written; every
requirement and every part is classified as work to add.

Either way, a `for_a_person` list. It holds the only two questions this machinery refuses to
answer for anyone:

- a pair of requirements one judgement merged and another kept apart;
- a part the two answering passes answered differently — one sentence, with a yes and a no beside
  it, rather than a whole requirement with two labels.

Put those in front of the person who owns the goal. Everything else is decided.

## The boundary — what this machinery will not do

Before any requirement is written, the runner checks the description's factual claims against the
code and **refuses to advance while any of them is false**. That refusal is the whole of this
machinery's responsibility for the description. It names the wrong statements and hands them back.

It does not correct them, and it must not be made to. Writing a description, and repairing one this
gate rejects, belong to a **separate machinery, to be built separately** — Kamen's scoping, and the
reason is the same division that makes this one work: a machinery that both authors a document and
grades it has no independent reader left.

So a rejected description is not a defect in this machinery, and the absence of a repair stage here
is not an omission. On the subject this was built against, the gate rejected five times running —
seven false statements, then four, two, one, one — and each was repaired outside it before the gate
opened on the sixth. That is the intended shape.

## The tools the runner does not call

Three enumerators sit here that the loop above never runs: `enumerate_sets.py`,
`enumerate_candidates.py`, `enumerate_expectations.py`. They are the other direction of the same
question — instead of reading a description and asking what the build is missing, they enumerate
what a built thing produces and where it fails. That half is proven: six runs agreed on the same
set of thirty-one, and two independent runs picked the same fault out of a numbered list. The parts
stage now covers the same ground from the description's side, so they are unused rather than wrong.
Keep them; do not wire them into the runner without a run showing they find something the parts do
not.

Two tools were removed rather than kept: a word search meant to find what in the build bears on a
requirement, which scored requirements nothing addressed the same as ones already done; and a
checker meant to bound how fine a split may be, which refused twenty-three of twenty-four correct
splits. Both ran. Neither discriminated, and a tool that runs without discriminating is worse than
an absent one, because it looks like a check.

## Why it is shaped this way

Every narrowing here was earned by a run that went wrong first. Code fixes what gets looked at —
the set, the candidates, the sentences, the pairs — and a model judges what it means. When the
model was left to choose what to look at, two runs on the same subject produced answers with no
common denominator. When code fixed the material, the same two runs agreed.

`CHAIN-LEDGER.md` records each step, what proved it, and what it cost. Read it before changing
anything here.
