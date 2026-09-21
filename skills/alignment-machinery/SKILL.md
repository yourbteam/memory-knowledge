---
name: alignment-machinery
description: Turn one client's returned document into candidate rules for every client, each ruled by a person before anything is carried onto a page. Use when a client sends back an edited version of a document the harness produced.
---

# Alignment machinery

A client sends back our document with their own wording in it. The cheap reading of that is a list of
corrections to copy onto their page. The expensive thing it actually contains is a set of rules about
how every page should be written, and those rules cannot be seen one line at a time.

This machinery exists because that second reading was being done by hand. On 20 September 2026 one
client returned two documents; ninety-nine lines changed on one and fifty-six on the other, and every
one of them was filed the same way, as this client's wording at this position. Nothing asked what any
of them implied. A rule she had shown us on one client that morning was missed on the other the same
day, and it took a correction from the owner to find it.

So the shape here is deliberate. Reading every changed line is what proves nothing was missed.
Deciding what the changes mean happens afterwards, across all of them at once, because several lines
can carry one rule and a rule is only visible by standing back. And no rule becomes a rule on a
model's say-so: a person rules on every candidate.

**What is mechanical and what needs a model.** Code pairs the documents, holds every difference,
counts, refuses, presents and records. A model does exactly two things: it says, for each difference,
whether it is this client's wording or evidence of a rule; and it names the candidate rules across the
whole set. In both, the model's answer is checked against a register the model did not write.

## The steps

| step | what it does | kind |
| --- | --- | --- |
| invocation | hands out its input contract, then holds the caller to it | mechanical |
| register | pairs the documents and holds every difference, dropping none | mechanical |
| disposition | marks each difference as this client's wording or evidence of a rule | hybrid |
| distillation | names candidate rules across the whole set, each citing its lines | hybrid |
| ruling | puts every candidate to a person and keeps the answer in their words | mechanical |
| gate | lets nothing reach a page before its ruling exists | mechanical |

Only `invocation` is built. The rest are not, and this file will say so until they are.

## Invocation

```bash
python3 <skill-dir>/scripts/invoke.py contract
python3 <skill-dir>/scripts/invoke.py validate --filled <file.json> [--root <repo>]
```

Asked with `contract`, it returns every input it needs with a sentence saying why, and a `value` of
`null` for each. Fill those values, keep every field, add none, and pass the file back with
`validate`.

It then checks, without judging anything: that both documents exist, are real files rather than
symlinks, can be read as paragraphs, and are not empty; that they are not the same document, because
two identical files mean the version they answered was not supplied; that the client and the sender
are named; that each label names a version, and that it is the version its own file carries; that
the date is a date; and that the run's record has a durable home inside a repository rather than a
temporary folder.

A refusal names the field, what came back, and what would satisfy it, and it names every problem it
found rather than the first. On acceptance it writes `inputs.json` into the run directory with both
documents pinned by their contents and by the paragraphs counted in them, and that file is what the
register reads. A record is never written over: an identical fill may be re-run, a changed one is
refused naming each field that moved, and a record written under an earlier contract is left alone.

## The pairing

One input is the one a caller gets wrong while every other field looks right: `our_document` is the
version the client was reading when they made these changes, not the newest version we hold. Five
models filling this contract blind produced five correct documents and three different readings of
that field, so it is checked rather than trusted.

Two versions of one document share most of their paragraphs. The share is counted, and a pair too far
apart to be two versions of anything is refused — the other client's page of the same step scores
0.36 and 0.39 where real pairs score 0.63 to 0.83.

Then the versions sitting beside the one the caller named are counted too, in both documents' folders
and the folders beside them. Two are left out, and the second matters: the returned document itself
under another name, and every version written after the return arrived. Our own regenerations carry
the client's words back, so a draft written the same evening answers their return perfectly — on 20
September the page we rebuilt at 18:10 matched her 14:07 return at 1.000, and the version she was
actually reading at 0.83. Time is what tells those apart.

A version that answers the return much better than the named one is not proof of a wrong pairing: our
drafts converge on a client's voice. It is a question the caller must have faced. So the machinery
refuses unless `pairing_evidence` names that version — either it is the one they were reading, or the
caller says why it is not.

## What it does not do

It does not send anything to a client, change a client's page, or decide that a candidate is a rule.
It does not read a document the caller did not name. Its output is a record and a set of questions for
a person.
