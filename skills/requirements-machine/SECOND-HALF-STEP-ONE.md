---
name: requirements-machine
description: Step one of the rebuilt requirements machinery. Produces exactly ONE grounded requirement for a named subject — what must become true, the cost today as a count over a named population, and a test that returns that count when run. Nothing else. Do not use it to produce a list, a register, or a plan.
---

# Requirements Machine — step one

This skill does one thing: **produce a single grounded requirement for a named subject.**

Not a list. Not a document. One requirement, complete enough that someone else could build
against it and settle it without asking you anything.

It is being built one step at a time and each step is proven before the next is designed.
Producing one requirement reliably is the first step; nothing above it matters until this holds.

## What you are given

- **subject** — the one thing being changed, named the way the system names it.
- **repository** — where the subject lives.
- **evidence** — where the system records what it did: run records, logs, published output,
  tests, the customer's own files. Whatever exists. Some subjects have all of these, some have
  almost none.
- **output path** — the file to write your record to.

## What you produce

One JSON object at the output path, with exactly these fields:

```
{
  "subject":       "the thing being changed, in the system's own words",
  "requirement":   "one sentence: what must become true. No design in it.",
  "population":    "the set the cost is counted over, defined so someone else could build the same set",
  "cost_now":      {"failing": <int>, "of": <int>},
  "test":          "the exact command or script that returns cost_now.failing when run today",
  "test_output":   "what the test printed when you ran it, verbatim",
  "whose_outcome": "who is better off, and what they can do afterwards that they cannot do now"
}
```

Every field is required. If one cannot be filled honestly, write `null` and add a sibling field
`blocked_because` saying why. An honest blank is a result; an invented value is not.

## How to produce it

1. **Read the evidence before deciding what the requirement is.** Open the records. The
   requirement comes out of what is there, not out of what a system like this usually needs.
2. **Write the test first, run it, and let its output decide the cost.** The cost is the number
   the test returns — never a number counted another way and then described.
3. **State the population so a stranger could build the same set.** Where it came from, what was
   included, what was excluded and why.
4. **Say the requirement in one sentence, in the words the subject's owner would use.**
5. **Check it is not already true.** If the test returns zero, this is not a requirement. Find
   another.
6. **Check the sentence and the test agree.** Read them as if you had written neither. If the
   test does something the sentence does not mention — a masking, a threshold, a field it looks
   at — either the sentence says so or the test stops doing it.

## What this step does not do

It does not run rounds, keep a register, reject candidates, or decide when a list is complete.
Those are later steps and they do not exist yet. Produce one requirement and stop.
