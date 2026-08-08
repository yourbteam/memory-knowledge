---
name: requirements-machine
description: Builds the requirements for a change, end to end, from a description of what the thing is for. Produces what must be added, changed or removed — and when nothing is built yet, what must be added. Invoke this and follow it; do not run its tools by hand or in another order.
---

# Requirements machine

One command owns the order and the gates. This skill owns the one thing a command cannot do:
starting the readers it asks for, and starting them again until it asks for none.

**Do not run the tools in this folder by hand.** They were built in an order, each proved before
the next was designed, and the runner is where that order lives. Running one directly skips its
gate, and every gate here exists because something was silently dropped without it.

## What you need

- **subject** — the one thing being changed, named the way its owner names it.
- **description** — the document saying why it should exist, what it is given, what it must do,
  what it must produce, and when it is done. If there is no such document, there are no
  requirements to build yet: write it first, from what the client wrote and what you decide
  deliberately, and have the deciding parts ratified by the person who owns the goal.
- **work directory** — a fresh directory. State lives there and the run is resumable.
- **built** — the repository to measure against. Omit it when nothing is built yet.

## The loop

```
python3 run.py --subject "<subject>" --description <file.md> --work <dir> [--built <repo>]
```

1. Run it.
2. If it returns `stopped`, it hands back a list under `work`. Each entry is one reading job: an
   instruction, the file to read, and the directory the answers go in.
3. **Launch one agent per job, all of them, in parallel.** Give each agent its `instruction`
   verbatim and nothing else. Two jobs of the same stage are two independent readers — never let
   one agent do both, and never tell either what the other found. Agreement between them is the
   only evidence this machinery accepts.
4. When they return, run the command again. It will either hand back the next jobs or finish.
5. Repeat until it stops handing back jobs.

Nothing else is yours to decide. Do not re-order stages, do not skip a second pass because the
first looked good, and do not fix a stage's output by hand — if a gate refuses, the reading was
incomplete, and the answer is to run that reading again.

## What comes back

With a repository to measure against: every requirement sorted into **add**, **change**,
**remove**, or **already met**.

Without one: the requirements themselves, which are the things to add.

Either way, a `for_a_person` list. It holds the only two questions this machinery refuses to
answer for anyone:

- a pair of requirements one judgement merged and another kept apart;
- a requirement the two measuring passes gave different verdicts.

Put those in front of the person who owns the goal. Everything else is decided.

## Why it is shaped this way

Every narrowing here was earned by a run that went wrong first. Code fixes what gets looked at —
the set, the candidates, the sentences, the pairs — and a model judges what it means. When the
model was left to choose what to look at, two runs on the same subject produced answers with no
common denominator. When code fixed the material, the same two runs agreed.

`CHAIN-LEDGER.md` records each step, what proved it, and what it cost. Read it before changing
anything here.
