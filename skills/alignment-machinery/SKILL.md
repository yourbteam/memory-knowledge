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
| landing | says, for each approved rule, whether the harness already produces it or a check must be built | hybrid |
| gate | lets nothing reach a page before its ruling exists | mechanical |

`invocation`, `register`, `disposition`, `distillation`, `ruling` and `landing` are built — six of
seven. The gate is not, and this file will say so until it is: nothing yet stops a page being built
while a rule it should answer to has no ruling.

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

## The register

```bash
python3 <skill-dir>/scripts/register.py hold --work <run directory>
python3 <skill-dir>/scripts/register.py show --work <run directory>
```

It reads the run the invocation accepted, checks both documents are still the exact files that were
accepted, and lines them up paragraph by paragraph. What comes out is one ordered list: every
paragraph the client changed, added or removed, with their words and ours verbatim and the heading it
sits under. It judges nothing and it drops nothing.

Differences are grouped by the stretch they arrived from, and each stretch is marked rewritten, cut
or inserted. That grouping is not decoration. On Vivacom's return of 20 September the ungrouped
record said 184 paragraphs removed, and every one of those 184 turned out to sit inside a passage she
had rewritten — the record was making a claim about the client that the documents did not support.
Grouped, the same return reads as 96 passages, the largest being 93 paragraphs of ours answered by 8
of hers under her calendar heading, which is what that return actually was.

One promise is made and therefore checked rather than trusted: every paragraph of both documents is
accounted for exactly once. The arithmetic is written into the record and recomputed every time it is
read, and nothing is written when it does not add up.

## Disposition

```bash
python3 <skill-dir>/scripts/dispose.py ask    --work <run directory> --reader 1
python3 <skill-dir>/scripts/dispose.py read   --work <run directory> --answers <file>
python3 <skill-dir>/scripts/dispose.py settle --work <run directory>
python3 <skill-dir>/scripts/dispose.py ask-owner --work <run directory>
python3 <skill-dir>/scripts/dispose.py rule   --work <run directory> --id <passage> \
        --choice <answer> --because "<his words>"
python3 <skill-dir>/scripts/dispose.py finish --work <run directory>
```

Every passage the register holds is put to one question, and the only two answers are: this is the
client's own wording here, or this is evidence of a rule for every page. The question carries the
test with it — take the change, remove everything particular to this client, and if what is left
still says how a page should be built, it is evidence of a rule.

Three readers answer, each blind to the other two, each quoting the words it judged. That number is
not decoration. A single reader gave a different answer on the same passages from one run to the
next, which is not a method; three readers and a stated test are what make the answer belong to the
evidence rather than to the run.

Where all three agree, the answer stands with its three reasons. Where they split, no model casts
the deciding vote. The passage goes to Kamen, and what reaches him is the client's words and ours
first, then all three readings, then one plain recommendation written by a different model that did
no judging — in that order, because a recommendation read before the evidence is a ruling made by
the recommender. `finish` refuses while any split is unruled, naming each one.

On Maria's three Step 9 returns of 20 September the method ran over 898 changed lines in 181
passages. Two returns came out unanimous. The third split on seven passages and went to Kamen, who
ruled six as rules for every page and one as her own wording. Nineteen of the 898 lines are the
client's own wording; the rest are evidence of a rule.

One check is worth naming because it fired both ways. A quote must be the passage's own words, and
enough of them — a reader answering a long paragraph with one word has not shown what it judged. The
minimum yields where the passage itself is shorter, because B Team's calendar cells hold nothing but
a four-letter code, and eleven correct answers were refused before it did.

## Distillation

```bash
python3 <skill-dir>/scripts/distil.py gather --work <new directory> --from <run> --from <run>
python3 <skill-dir>/scripts/distil.py brief   --work <run>      # for the proposing model
python3 <skill-dir>/scripts/distil.py propose --work <run> --candidates <file>
python3 <skill-dir>/scripts/distil.py ask     --work <run> --reader 1
python3 <skill-dir>/scripts/distil.py read    --work <run> --answers <file>
python3 <skill-dir>/scripts/distil.py settle  --work <run>
python3 <skill-dir>/scripts/distil.py ask-owner --work <run>
python3 <skill-dir>/scripts/distil.py rule    --work <run> --id <passage+change> \
        --choice yes|no --because "<his words>"
python3 <skill-dir>/scripts/distil.py name    --work <run>
```

Every step before this one works on one returned document. This one does not, and that is why it
exists: a rule is rarely visible inside a single return. So the one thing a caller can get wrong
here is not which document they named but which set of runs — leave one out and what comes back is
a smaller answer wearing every mark of a complete one. `gather` therefore takes the runs by name,
refuses anything that is not a finished disposition at the current version, recomputes each
record's arithmetic against the register the disposition did not write, and then looks in the
folders those runs came from: another finished record sitting there unnamed is refused by name.
Records from a superseded version of the step are left alone as history.

The passages the readers called evidence of a rule are not one change each. The same change appears
on every calendar slot, on every line held. Naming the distinct changes is a grouping job, and
grouping cannot be put to three blind readers — asked to group 162 things, three readers return
three different sets of groups and agreement is not even defined. So the work is split. One model
that does no judging reads the whole gathering and proposes the changes, each a sentence with no
client in it; a sentence naming a client is refused, because a change that only makes sense for one
client is the thing this machinery exists to tell apart. Then every passage goes to three readers
who cannot see each other, as one question with the same answers every time.

**The question allows more than one answer, and that is a correction the data forced.** Asked which
single change a passage belonged under, the readers split on 22 of 162 — and every one of those 22
was a block that renamed its labels, added a new paragraph and dropped the agency's working rows at
once. They were not disagreeing about the facts; the question let only one through. One real change
drew no evidence at all, because the rows it describes never disappear on their own. Asked instead
which changes a passage shows, all that apply, the same three readers split on 8 of 3,564
pairings, that change carried 28 passages, and 80 of the 162 passages named more than one.

Agreement is counted change by change. Where the three agree the answer stands; where they differ,
that one pairing goes to Kamen with the client's words and ours first, then the three readings,
then one recommendation from a model that did no judging — and that recommender is told in terms
not to reason from which change needs evidence, because the first one did exactly that. `name`
refuses while any pairing is unruled, and proves that every passage was weighed against every
change and each pairing answered once.

## Ruling

```bash
python3 <skill-dir>/scripts/rule.py next   --work <run directory>
python3 <skill-dir>/scripts/rule.py answer --work <run directory> --change <id> \
        --choice approved|rejected|reworded --because "<his words>" [--wording "<his sentence>"]
python3 <skill-dir>/scripts/rule.py show   --work <run directory>
python3 <skill-dir>/scripts/rule.py finish --work <run directory>
```

Nothing the distillation named is a rule yet. Three models had a hand in that list — one proposed
the changes, three read every passage against them, one wrote advice where they differed — and a
change to how every client's page is built is the one thing their agreement cannot settle. So this
step puts each change to the owner alone. No model recommends an answer here.

It reads the written list and presents one change at a time, heaviest evidence first, with the
client's words against ours beneath it and the count of clients, passages and changed lines behind
it. Three answers: approved, rejected, or approved with his own sentence replacing the proposed
one. A change he has not answered stays a candidate and is reported as one, and `finish` refuses
while any remain. A ruling is never written over — the same answer may be recorded again, a
different one is refused naming the answer that stands — because a record of the last thing typed
is not a record of what he decided. Each ruling keeps the sentence he answered and the evidence
that stood behind it at the time.

On the twenty-two changes distilled from Maria's three Step 9 returns: twenty rules, eighteen
approved as written, two in his own wording, two rejected, and 2,248 of the 2,252 changed lines
standing behind a rule.

Two things came out of that ruling which nothing upstream could see. One candidate contradicted a
rule he had approved twenty minutes earlier — the working record staying off the client page — and
no model weighing the candidates against each other would have caught it, because each was read
against the client's documents rather than against the other candidates. And the question he asked
while ruling, which rules the harness already satisfies and which need building, is not answerable
from a client's return at all: the answer is a fact about our own code, and it comes from tracing
the harness once per rule.

## Landing

```bash
python3 <skill-dir>/scripts/land.py open  --work <run directory> --harness <repo root>
python3 <skill-dir>/scripts/land.py ask   --work <run directory> --reader 1
python3 <skill-dir>/scripts/land.py read  --work <run directory> --answers <file>
python3 <skill-dir>/scripts/land.py settle --work <run directory>
python3 <skill-dir>/scripts/land.py ask-owner --work <run directory>
python3 <skill-dir>/scripts/land.py rule  --work <run directory> --id <rule> \
        --choice already|needs-a-check --because "<his words>"
python3 <skill-dir>/scripts/land.py finish --work <run directory>
python3 <skill-dir>/scripts/land.py show  --work <run directory>
```

A rule the owner approved is a decision, not yet a change to how a page is built. Two of his rules
can read alike and mean opposite things for the work: one describes what the harness already does
for every client, and the other describes something that has to be built. Nothing in a client's
return tells those apart, because the answer is not in the client's document at all — it is a fact
about our own code. So this step asks one question per approved rule: does the harness already
produce this, or must a check be built, and where.

It reads the ruled list the ruling step finished in the same run, and takes one declared input
beyond it — the harness's own root, pinned by the commit it was read at and by the count of files
left uncommitted beside it. A claim that something is already true is worthless against code that
is not what runs.

Three readers who cannot see each other answer every rule, and an answer is refused unless it names
the place in the harness and quotes the line that decides it, checked as a literal substring of
that file. That check is the whole difference between a falsifiable claim and a believed one: a
citation nobody can find is how a rule gets reported satisfied when it is not. Where the three
agree the answer stands with its citations; where they differ the rule goes to the owner with the
readings first and then a recommendation from a model that did no reading. `finish` refuses while
any rule is unanswered or any disagreement unruled.

On the twenty rules from Maria's three Step 9 returns: twelve the harness already produces,
standing behind 1,879 of the changed lines, and eight needing a check, standing behind 369.
Eighteen were unanimous and two went to Kamen, who ruled both as needing a check. Sixty citations
were given and every one was found verbatim — fifty-eight of them in a single file, and two in the
page screens, which is itself an answer about where this step of the harness is decided.

Two things the readers found while reading are kept in the record and are not rules, because nobody
asked for them: a structural check still looks for a label the page stopped printing, and our own
build-workflow table prints internal phase names on a client page.

## What it does not do

It does not send anything to a client, change a client's page, or decide that a candidate is a rule.
It does not read a document the caller did not name. Its output is a record and a set of questions for
a person.
