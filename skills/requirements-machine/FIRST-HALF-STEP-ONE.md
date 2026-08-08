---
name: requirements-machine-first-half-step-one
description: Step one of the first half of the requirements machinery. Given a description of what a subject is FOR, produces exactly ONE requirement — what must become true, taken only from the description, with a check someone could apply to a future output. It never looks at what has been built. Do not use it to produce a list, a register, or a plan.
---

# Requirements machine — first half, step one

The machinery has two halves. The second half asks what is wrong with what exists; it is built and
proven. This is the first half, and it asks the question that comes before: **what must this thing
do at all.**

The two are not merged. The first half sets the standard. The second half measures what exists
against that standard. The final requirements are what must be added, changed or removed to close
the distance. When nothing has been built, only the first half runs, and it must be complete on its
own.

This skill does one thing: **produce a single requirement from the description of a subject.**

Not a list. Not a document. One requirement, complete enough that someone else could build against
it and settle it without asking you anything.

## Why it may not look at what exists

The second half of this machinery, pointed at a real subject, returned an empty document: every
candidate fault was correctly dismissed, because the subject did what its code asked of it. A
machinery that reads only the records can only ever ask whether a thing is consistent with itself.
The standard has to come from somewhere the records cannot reach.

So: **do not read the built thing, and do not let what it currently does shape what you write.** If
you find yourself writing a requirement because you noticed the code does not do it, you are in the
second half by accident, and the requirement will inherit the shape of the existing solution.

## What you are given

- **subject** — the one thing being described, named the way its owner names it.
- **description** — the document that says why the subject should exist, what it is given, what it
  must do, what it must produce, and when it is done.
- **output path** — the file to write your record to.

Nothing else. No repository, no records, no published output.

## What you produce

One JSON object at the output path, with exactly these fields:

```
{
  "subject":        "the thing being described, in its owner's own words",
  "requirement":    "one sentence: what must become true. No design in it.",
  "source":         "the exact words in the description this comes from, quoted",
  "source_kind":    "one of: what the client wrote | observed in real output | read in code | a decision stated in the description",
  "whose_outcome":  "who is better off, and what they can do afterwards that they cannot do now",
  "check":          "what a person or a program does to a future output to decide whether this holds",
  "check_kind":     "one of: a program can decide it | a person must read and judge it",
  "check_needs":    "what would have to be recorded or produced for the check to be possible at all; null when it is possible today",
  "not_already_covered": "why this is not already said by another part of the description"
}
```

Every field is required. If one cannot be filled honestly, write `null` and add a sibling field
`blocked_because` saying why. An honest blank is a result; an invented value is not.

## How to produce it

1. **Read the whole description before choosing.** The requirement comes out of what is there, not
   out of what a subject like this usually needs.
2. **Take one thing the description says must be true, and state it as one sentence.** In the
   owner's words, not the system's. No design in it — say what must become true, never how.
3. **Quote the source.** The exact words in the description, and which of the four kinds of
   statement it is. A requirement whose source you cannot quote is one you invented.
4. **Write the check before you are satisfied with the sentence.** What would someone do to a
   future output to decide whether this holds? If the honest answer is that a person must read it
   and judge, say so — that is a legitimate answer and marking it is what stops a judgement being
   dressed up as a test.
5. **Say what the check needs that does not exist yet.** Many of the description's rules cannot be
   checked at all without something being recorded that nobody records today. Naming that is part
   of the requirement, not a footnote to it.
6. **Read the sentence and the check as if you had written neither.** If the check decides something
   the sentence does not say, either the sentence says it or the check stops doing it.
7. **Check it is not already covered** by another statement in the description, said differently.

## What this step does not do

It does not look at what has been built. It does not count anything. It does not run rounds, keep a
register, reject candidates, or decide when a list is complete. Those are later steps, and the ones
that exist belong to the other half. Produce one requirement and stop.
