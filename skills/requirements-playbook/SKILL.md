---
name: requirements-playbook
description: Use when a change needs a requirements document — what must become true, each with the definition of success that decides it, before anything is designed or built. Builds the list in rounds from a declared angle each time, closes only when two consecutive rounds add nothing, and rejects any candidate that fails the six-test grounding filter. Do not use to design a solution, plan an implementation, or review a diff.
---

# Requirements Playbook

A requirements document says what must become true for one named change, and, for each of those
things, the definition of success that decides whether it has become true. It is not a design, not a plan, and not a list of good intentions.

Two failures are known, repeatable, and are the reason this playbook exists:

* **Nothing complete arrives in one pass.** A single sweep always misses requirements that only
  become visible once the earlier ones are written down. So the document is built in rounds, and an
  objective gate — not a sense of doneness — decides when the rounds stop.
* **At the moment of writing, an abstract requirement is indistinguishable from a grounded one.**
  "The system should validate its inputs" and "the composer must not discard a five-minute draft
  over one missing field" feel equally real to the author. So every candidate passes a filter
  before it enters the document, and every rejection is recorded with the test it failed.

## Before the rounds

Write the header once. It does not change during the rounds.

| field | what it holds |
| --- | --- |
| subject | the one thing being changed, named the way the system names it |
| complaint | what you were told is wrong, verbatim, with who said it — and, after you have checked it, whether the record bears it out |
| goal | what becomes possible that is not possible now, in the owner's words |
| measure | the goal's one number, read from an artifact the owner can open, plus what part of it this subject can move |
| evidence base | the records the rounds draw from — run logs, code paths, prior findings |
| out of scope | what this document deliberately does not cover |

**The goal's number is usually not scoped to your subject.** It counts something larger — every
document a run produces, every check in a suite — and the subject is one contributor among many.
Record the number as it stands, then say in one line what part of it this subject can move and what
would still be wrong if the subject were perfect. Where the number is distorted — a denominator
that shrinks when the subject fails, a reading taken from a run that never produced the subject's
output — say so in the header. That distortion is a finding in its own right and belongs in front
of the owner, not silently inside a requirement.

If the evidence base is empty — no run, no log, no recorded failure — that is the first finding and
it outranks the document. Obtain a real record before writing requirements about behaviour nobody
has observed.

### The complaint you were handed is a report, not the boundary

Someone told you what is wrong — it is slow, it loses work, it refuses good documents. That
sentence is one witness statement. It is a lead to verify, and it is emphatically not the edge of
what you are looking for.

- ✅ Write the complaint into the header verbatim, as a claim with an author.
- ✅ Verify it against the record like any other claim: is it true, is it current, is it the
  largest thing wrong with the subject?
- ✅ Then set it aside and ask, of each source in turn, what *it* says is wrong with the subject —
  not whether it supports the complaint. The sources answer a question the complaint never asked.
- ✅ If the record shows something larger than the complaint, say so in the header and pursue it.
  The person who wrote the brief was reporting a symptom they could see.
- 🚫 No round whose candidates are all instances of the complaint. That is the complaint being
  restated in a longer form, not a requirements document.

Why this is here: on 2026-08-07 the same step was worked twice. One author was handed "it is slow,
it throws work away, runs die there" and produced twelve requirements, every one about speed,
waste or death. The other, working the same records without that sentence, found eight things the
first never looked for — including the two that mattered most to the owner. Neither author was
careless. The first one searched inside the sentence they were given.

### Name the sources, not "the evidence"

The evidence base is a list of named sources, written in the header, each one a place you can
open. Not "the logs" — which logs. Not "the code" — which paths.

Five kinds exist in any system like this one, and all five are declared or explicitly ruled out
with a reason:

1. **What every run recorded** — the durable run history, not the handful of log files someone
   handed you. This is the only place run mortality lives.
2. **The code that does the work** — the paths the subject actually executes.
3. **What the customer asked for in writing** — their own requirements, in their words.
4. **What the tests already pin** — what is already guaranteed, and what is not.
5. **What the person running it experiences** — the failure surface someone who cannot change the
   code is left holding.

### Prove the evidence base before the first round

An evidence base is a claim, not a fact — whether someone handed it to you or you chose it
yourself. Before any round runs, open it and find the subject in it. Name what you found: which
run, which line, which record. If it is not there, the base is wrong — go and find where the
subject actually lives, and say in the header what you changed and why.

**Do this for every declared source, one at a time. Not once for the whole base.** A source you
named and never opened is worse than one you never named: the header now claims it was consulted.
On 2026-08-07 a run declared five sources, proved only the run history, and its declared
customer-requirements document turned out to contain nothing about the subject at all — no mention
of it, not once. That was caught in round six by accident. Had the rounds closed at five, the
document would have shipped citing a source that had nothing to do with its subject.

Being cited is not being read. A source that contributed a phrase to somebody else's requirement
has not been read; a source you skimmed for the thing you already expected has not been read
either. Open it end to end, asking only what it says about this subject.

This step can fail, and failing it stops the rounds. That is the point. Twice on 2026-08-07 the
opposite happened: a requirements run handed four log files concluded the change was unnecessary,
because those logs do not contain the failures it was asked about — the truth was in a different
directory it only reached by going past what it was given. In the same session a round produced
nothing because the goal's measure counts two failing documents and names neither, so nothing could
be traced to the subject at all. Both would have shipped a confident document about the wrong
thing.

A base that cannot be shown to contain the subject's failures is not evidence that the subject is
where the problem is — and a requirements document for the wrong subject is worse than none,
because it is actionable.

## The round

Each round is one pass over the subject **from a declared angle**. The angle changes every round.
Repeating an angle is how a loop produces nothing new and then declares itself complete.

Angles, in this order, extended when the subject calls for it:

1. **What the record says failed.** Every distinct failure in the logs, each becoming a requirement
   that it stop happening.
2. **What each step does when something is wrong.** Not whether the rule it enforces is right —
   what it does with a failure. Disposition errors hide behind correct rules.
3. **What the person using this experiences.** Name that person concretely. A requirement they
   cannot satisfy is a defect in the requirement.
4. **What each definition of success would actually measure.** Read every requirement already
   accepted and ask what its definition of success proves. Where it proves the mechanism ran rather
   than the answer being right, that gap is a new requirement.
5. **What sits either side.** What upstream produces and downstream consumes, and what this change
   breaks or leaves stranded there.
6. **What the finished thing is, read as its recipient.** Open one document the subject actually
   produced — the newest, exactly as it was delivered — and read it from the top as the person
   receiving it. Not searching for a failure: reading. Ask what it is supposed to contain and
   whether it does.

   This angle is mandatory, and it is the one the other five cannot reach. The rounds hunt things
   going wrong, and the worst defect is usually an absence — nothing fails, nothing is logged,
   nobody is refused. On 2026-08-07 a complete run of this playbook produced fourteen requirements
   and missed the largest fact about the document: not one claim in any of the thirty-one published
   copies had ever been marked verified. No round could find it, because nothing was going wrong.

**When these six are spent and the gate is still open, derive the next angle from the register
itself** — do not invent one. Three that have worked:

- **One source, read alone.** Take a declared source that has produced little and go through it
  end to end asking only what it says about the subject. On 2026-08-07 this forced the round that
  finally read the tests, and it produced four requirements.
- **The failure census.** Count every distinct failure code the subject has ever produced, then
  ask of each: does an accepted requirement already cover it? The uncovered ones are the round.
- **What is half-changed already.** Uncommitted work, a comment describing a fix, a test marked
  skip. Each is somebody's unfinished answer to a problem nobody wrote down.

A derived angle is a real angle: on that same day rounds six, seven and eight each produced a
requirement the first five had missed.

**What makes an angle new.** An angle is new when it reads something the earlier rounds did not: a
different source, a different population, or a different reader. Calling it something else is not
enough. Before the round starts, write one line saying what it will read that no earlier round read.
If that line cannot be written, the angle is not new.

**Check that line against what the earlier rounds recorded, not against your memory of them.** A
round that claims to read something an earlier round already recorded reading is not new, whatever
it calls itself. On 2026-08-07 a late round claimed a source as unread that an earlier round had
explicitly recorded reading "end to end", and the register resolved the contradiction silently in
the late round's favour. One of the two statements is false, and which one it is has to be written
down: either the round is a re-read, or the earlier round's account of its sources needs correcting.

**The newness line names the earlier rounds it was checked against**, and a round whose population
is a subset of an earlier round's declared population is an audit however differently it is framed.
On 2026-08-07 a register closed on "three consecutive empty rounds"; one of the three re-read part
of round one's own declared population over round one's own source, and the gate in truth rested on
two. Self-graded newness is how a round becomes new by being called new.

A pass that re-reads an earlier round's population over the same sources is an **audit**, not a
round. Audits are worth running — they catch counts that have drifted — but they are recorded as
audits and **they do not count toward the completion gate**. On 2026-08-07 a run closed its gate on
two consecutive empty rounds, and one of the two was a re-reading of round one's failure census over
round one's own two sources. It could not have produced anything. The gate rested on one genuinely
new angle and a self-audit, and read as though it rested on two.

Within a round:

1. Produce candidates from that angle alone.
2. Discard any candidate already in the register — **including one already rejected**. Deduping
   only against accepted requirements makes rejected candidates return every round, and the loop
   never converges.

   **"Already covered" names the entry and shows its condition covers this cost.** Same subject, not
   the same requirement. On 2026-08-07 a candidate about a step calling the model after its budget
   was spent — fourteen runs, three and a half hours — was discarded as already covered by a
   requirement about refusals that name nothing to change. The two share a step and nothing else,
   and a finding proven in an earlier register left the document without a line recording it. If
   you cannot point at the condition that would fail while this cost persists, it is not covered.
3. Run each surviving candidate through the filter below.
4. Append accepted requirements and rejected candidates, with reasons, to the register.
5. Record the round's angle, the sources it drew on, and its counts: candidates, accepted,
   rejected, already-seen.

## The filter — what separates a real requirement from a synthetic one

Apply all six tests to every candidate. **One failure rejects it.** Record which test failed, and
record it honestly — a candidate rejected under the wrong test is a lie in the register.

1. **Evidence.** It names something the system actually recorded: a run, a log line, a measured
   count, an observed refusal, a code path that behaves this way. A requirement whose evidence is
   "this is good practice" has no evidence.

   **Where the system already answers the question, use its answer.** Before writing a query of
   your own, look for code in the repository that decides the same thing — a check, a validator, a
   measure — and run that. Cite the run of it. Your own count is a second opinion about a question
   the system has already settled, and when the two disagree it is usually yours that is wrong.

   On 2026-08-07 a verification struck three of fourteen requirements, and all three died the same
   way: the author had written a bespoke count where the repository already implemented the exact
   check. Run against the real one, the headline claim — that questions were being repeated with an
   identifier swapped — fired on **none** of the thirty-one published documents.

   **A fault in a document is evidence about whatever wrote it — find that first.** Trace the
   offending text to the step, the input, or the person that produced it before attributing it to
   the subject. On 2026-08-07 a register blamed the subject for a mid-sentence fragment that came
   from a hand-maintained input file three weeks stale, while the corrected text already sat in the
   system's own record.

   **Before concluding a mechanism does not work, establish that it ran.** The same register argued
   a guard was ineffective because the fault was still in the newest documents. The guard refuses
   both offending inputs when they are replayed through it; the runs in question were resumed part
   way and the guarded step has no activity at all in them. An output that predates a fix says
   nothing about the fix.

   **When a requirement settles a disagreement about an outside standard, the standard is the
   authority.** Not the customer's copy of it, and not the repository agreeing with itself. On
   2026-08-07 every brief cited the ban on advertising-value equivalents as the fifth Barcelona
   Principle; the customer's own playbook calls it the fourth. The requirement said: match the
   customer. But the Barcelona Principles are a published industry standard the customer does not
   own, the repository does not contain the edition the customer names, and the code line offered as
   corroboration turned out to be a comment about something else. Build that requirement and the
   harness prints the customer's number in front of the client's measurement lead, who may know it
   as the other one. Where the deciding source is not in hand, the requirement names the source that
   must be checked, or drops the contested detail — it never settles an outside question internally.

   **Settle a fact by reading, then test that the system honours it.** When a requirement turns on
   what is true of something outside the system — a standard, a customer's instruction, a
   regulation — open the source, read it, and write down what it says. The requirement then states
   the settled fact, and its test compares the documents against it. Searching for whether evidence
   exists is not reading evidence, and a test can never stand in for the reading. On 2026-08-07 a
   requirement said no numbered attribution may stand because the repository holds no copy of the
   standard; the repository holds a verified transcription of all seven principles, written as a
   plain numbered list, and the test looked for the words "Principle" followed by a number. It found
   two where it wanted five, concluded the standard was unheld, and would have deleted two hundred
   and twenty-one citations that the same file shows are correct. Read first, and the requirement
   becomes: every attribution matches the verified source — nothing deleted, and a wrong number
   caught.

   **Open one instance and confirm the subject produced it.** Not the file it appears in — the text
   itself. On 2026-08-07 a register charged the subject with a repeated question that fires on
   nineteen documents; in all nineteen the repetition is a legend a different composer writes, and
   the subject's own questions are invisible to the check that found it. The cost was real, in the
   wrong document, against the wrong step.

   **A count that comes from grouping states its key, and one member is opened by hand.** The same
   register reported sixty-one items carrying a prohibition flag. Sixty-one is the size of one
   bucket in a grouping by flag *combination*; the number carrying the flag is two hundred and
   fifty-five. It understated its own worst case fourfold, and the arithmetic was never wrong.

   **Open what you count.** It ran the test suite, counted nine failures, and read none of them.
   One of the nine was failing that day on exactly the input its largest claim turned on, and would
   have overturned it. A count is a number about evidence, not evidence.

2. **Failure case.** It states what goes wrong today and what that costs — time lost, a run
   stopped, a document that cannot be sent, a person blocked. "Could cause problems" is not a
   failure case.

   **The cost is a count over a named population: N of M, and M is stated.** Not "several runs",
   not "in some documents". Name the set you counted — every failed run, every published document
   of this kind, every refusal in the current window — and give both numbers. A cost with no
   denominator cannot be compared to any other cost, and cannot be checked.

   Counting the shape you have in mind rather than the whole class understates the damage. In the
   same verification, a requirement reported ten failures giving a refusal that named nothing to
   change; counted over all forty-eight failures, the real figure was forty-one.

   **M is the population that could exhibit the fault, and every record in it comes from a declared
   source.** Two ways this goes wrong, both on 2026-08-07:

   - *Dilution.* A cost read "fifty-seven of sixty-nine runs". Twelve of the sixty-nine contain
     nothing the fault could apply to, so the true reading is fifty-seven of fifty-seven — every
     affected run affected. A denominator padded with records that cannot fail makes a total
     failure look like a partial one.
   - *Undeclared records.* The same document's largest counts drew on a fourth store of run
     artefacts that appears in no source, and on runs of a different workflow that contributed
     nothing but denominator. If a record is counted, name the source it came from; if a source is
     added mid-run, declare it and prove it like the others before counting it.
   **Before rejecting a candidate as unsettleable, check what the deciding code actually needs.** A
   verdict a model produced is *recorded*; a function over that record is replayable without the
   model. On 2026-08-08 a register struck the single largest failure family — thirty-seven of the
   fifty-two runs this subject killed — saying its verdict came from a model call and could not be
   replayed offline. The function that raises the refusal takes the recorded verdict and the
   manifest and calls nothing; replayed over five hundred and forty-eight recorded verdicts it ran
   without a single error. The biggest defect in the subject was absent from the list on a claim
   about the code that was not true. Open the function, look at its arguments, and try it before
   writing that nothing can settle it.

   **Model the cheapest way to satisfy the requirement, then re-read the goal's measure.** If the
   laziest satisfying change leaves every document no better — or worse, makes the number rise while
   nothing improves — the requirement is not yet written. In the same register, a requirement that a
   failing step stop killing the run was satisfiable by returning an empty placeholder, which the
   goal's own checks score as a sendable document: forty-eight dead runs would have become forty-
   eight good numbers and no better documents. And where two honest repairs give different readings
   — removing repeated questions reaches every document, relabelling them reaches one fewer — the
   requirement names which.

3. **Definition of success.** It carries a condition someone other than the author can settle, and
   settle the same way twice. If the condition is a judgement — cleaner, clearer, more robust,
   better structured — the requirement dies here.

   **The condition is the thing that produced the cost, carried in the register and runnable
   again.** Not a sentence describing it. The register holds the command or the exact predicate —
   the pattern, the field, the comparison — and the cost is literally its output, so the two cannot
   drift apart. English goes beside it to say what it means, never in place of it.

   **A runnable test can still be the wrong test. Show that it measures the requirement's own
   words.** Take the requirement sentence, name the thing it says must become true, and say which
   part of the script decides it. Where the script decides something narrower, the requirement is
   rewritten to what the script actually settles — or the script is. On 2026-08-07 a requirement
   said no numbered attribution may stand unless it is traceable to a copy of the standard the
   repository holds; its script tested **file names** for the standard's name, so the repository's
   own verbatim transcription of that standard was invisible to it, and the requirement would have
   deleted a citation the transcription shows is correct. In the same document a requirement about
   claims the step registers carried a residue of ten that the code exempts by an explicit design
   decision and that originate upstream — the headline was this step's, the leftover was not, and
   only the headline had been put through the scope test.

   This is the defect that survived three rebuilds of one register on 2026-08-07, and it always
   looked the same. The author writes a measurement and runs it. Then, separately, writes a
   sentence describing what it did. Then reports the measurement's number as the sentence's result.
   Nobody ever runs the sentence, because a sentence has no run — so a rule saying "run the
   condition" degenerates into running the measurement a second time and calling it agreement.
   Where the two were finally checked apart, one condition asked that a question "name its claim in
   readable words" and passed nineteen hundred and sixty-five of the two and a half thousand
   questions its own cost calls broken, because the claim's identifier contains readable words.
   Another looked for `requires legal` where the record says `require Legal/Regulatory review`, and
   could not see a fifth of what it counted — including the example printed in the register beneath
   it. The tell is in the wording: every condition that failed this way is settled *by reading*;
   every one that held is a mechanical comparison — the same token, byte-identical after masking, a
   verbatim substring.

   Three ways a condition looks settleable and is not. All three were found in one register on
   2026-08-07, and the register had already caught the first by itself:

   - **It is already true today.** Three conditions in that document would have been passed by the
     current behaviour — one of them by fifteen of the nineteen runs it was written about. A
     condition today's system already satisfies measures nothing.

     **Settle this by running the condition, not by reading it.** Take the condition exactly as
     written, apply it to the output the subject actually produces, and record how many failures it
     returns. Set that number beside the requirement's own cost. A cost of fifty and a condition
     that fails nothing on the same data means the condition is wrong, whatever the author meant.
     On 2026-08-07 a requirement said a rewritten sentence must begin with a capital letter and end
     with terminal punctuation; the subject writes every rewrite as `UP analysis: <claim>`, so the
     condition passes on all one hundred and ninety-eight rewrites — including the fifty the same
     requirement counts as broken. Read as prose it is plainly right. Run, it fails nothing, and an
     implementer builds a check that can never fire.

     **The sentence names every step the script takes** — each masking, each strip, each threshold,
     each field it reads. A script does things the plain sentence does not mention, and those
     omitted steps are where a requirement stops meaning what it says. On 2026-08-08 a requirement
     read *no two owner questions are the same once that run's own claim identifiers are removed*;
     its script also removed the question's list number. Remove only the identifiers and nothing
     collides — so the requirement as written was already satisfied while its cost claimed two and a
     half thousand. In the same document, *the record names what was cut* was scripted as "the
     ledger contains the word truncated", which one word satisfies while naming nothing.

     **Every condition is settled on the next composition or on a replay — guards included.** A
     condition that reads only recorded documents returns the same answer after the change as
     before it, so it cannot see the break it exists to catch. On 2026-08-08 the guard protecting
     the one seam the repairs were most likely to break read two hundred and fifty frozen records,
     and would have reported the same two numbers whatever the new code wrote.

     **This is not optional and not a judgement call: every accepted requirement carries both
     numbers, side by side, in the register.** The cost the requirement claims, and the failures its
     condition actually returns when run. They must agree. Applied to some requirements and not
     others it catches nothing — on 2026-08-07 a register ran it where the mismatch was obvious and
     skipped it elsewhere, and two conditions survived that pass on the very cases their own costs
     call broken. One asked that a question name its claim in readable words; the claim's own
     identifier contains readable words, so nearly two thousand of the two and a half thousand bad
     questions pass. A requirement whose two numbers are not both written down is not finished.
   - **It can be met by shrinking what is measured.** One condition counted only sentences matched
     by their exact text, so rewording a sentence removed it from the count while the reader saw the
     same document. Where the population is defined by the thing being fixed, state the population
     independently of it.
   - **It cannot be settled from the register alone.** One condition pointed at "the full list
     recorded in the working notes" — a list in no file. Another asked whether a document discloses
     something, with no predicate for deciding it, in a set where most documents contain near
     misses. Whatever the condition needs in order to be settled, the register carries it.
   - **It is settled on history no fix can change.** One condition asked that a set of already
     recorded runs stop disagreeing with their own published documents. Those runs are finished;
     nothing built afterwards can alter them, so the condition can never be met however good the
     change is. A condition is settled on a replay, a re-run, or the next document produced — never
     on frozen output.

   And when an amendment changes a condition, **run these tests again on the amended wording.** On
   2026-08-07 an amendment closed one hole in a condition and the "already true today" answer was
   left as it stood for the original; four of the nineteen runs the requirement names already
   satisfy the amended version. An amendment is a new condition and is tested like one.
4. **Whose outcome.** It names who is better off and what they can do afterwards that they cannot
   do now. If the only beneficiary is the codebase, it is a preference.
5. **The context test.** Could this requirement have been written by someone who never looked at
   this system? If yes, it is synthetic — strike it. This is the sharpest of the six and the
   cheapest to apply: general engineering wisdom passes tests 1–4 by being dressed in local nouns,
   and fails this one immediately.
6. **The scope test.** Is this a condition on the *subject*, or on something upstream or
   downstream of it? A real defect belonging to a neighbouring step passes all five tests above —
   it has evidence, a cost, a settleable condition, and someone who benefits — and it still does
   not belong here. Reject it as out of scope, name where it does belong, and say so; the finding
   is worth keeping, just not in this document.

   Added 2026-08-07, after a run had to record several out-of-scope defects as failing the
   failure-case or the outcome test, which was not true of them. A rejection recorded for the
   wrong reason teaches the next reader the wrong lesson.

A candidate that restates a general principle survives only when it names the specific input, the
specific observed failure, and the specific definition of success. "Validate inputs" dies. "The four envelope keys
must be enforced where the answer is produced, because the run record shows two five-minute drafts
discarded for one missing key" survives.

## Repairs and guards — label every accepted requirement as one

Two different things pass the filter and they must not be confused.

- A **repair** stops something that is going wrong now. It has a cost today, and that cost is what
  justifies the change.
- A **guard** stops the change from breaking something that works now. It has no cost today; its
  cost is in the future, if the change lands carelessly.

Both are legitimate. Confusing them is not. On 2026-08-07 a list of fifteen carried three whose
"costs now" read "not yet a cost" and nothing marked them apart, so a reader counting the damage
would have counted three things that have never once gone wrong.

- ✅ Every accepted requirement carries a label: **repair** or **guard**.
- ✅ A repair states what it costs today, in time, in a stopped run, in a document that cannot be
  sent, or in a person blocked.
- ✅ A guard names the working behaviour it protects and shows that behaviour working today. A
  guard whose protected thing cannot be shown working is speculation and is struck.
- ✅ A guard's condition must still be satisfiable **after** the repairs in the same document land.
  A guard is written about the world the change creates, not the world it leaves. On 2026-08-07 a
  guard required that a resumed run reuse its saved draft — while two repairs in the same list
  change the instruction the step sends, and the code discards any saved draft whose instruction no
  longer matches. Landing those repairs makes that guard fail by construction, so as written it
  forbids the change it was written to protect. Either the guard covers the seam the change opens,
  or the document says what has to be migrated for it to hold.
- 🚫 No document made only of guards. If nothing is going wrong, there is no observed reason for
  the change, and the subject is wrong or the evidence base has not been proven.
- 🚫 No guard counted as damage when the cost of today's behaviour is reported.

## The completion gate

Two conditions, and both must hold.

**Every declared source has been read.** A source that produced no candidate — not one accepted,
not one rejected — has not been read, and the rounds cannot close while one is outstanding. This is
what makes completeness checkable instead of a feeling: the register shows, per source, what came
out of it.

Why it is here: on 2026-08-07 the same subject was run through this playbook twice. The two lists
differed by nine requirements, and every single difference traced to a source one run opened and
the other never did — one never read the run history and so never saw how often that step kills a
run; the other never read the customer's written requirements or asked what the person running it
sees. Neither author was careless. The gate simply let each of them stop when their own ideas ran
out.

**And two consecutive rounds produce no new accepted requirement.** Not two rounds with few; two
rounds with none.

- A round producing only rejected candidates counts as producing nothing.
- A round that only rewords an existing requirement counts as producing nothing. Rewording is not a
  new requirement.
- The counter resets to zero the moment a round produces one accepted requirement, whatever the
  round number.
- Running out of angles before the gate is met is not completion. Name a new angle from what the
  subject actually contains, and keep going.
- Running out of angles while a declared source is unread is not completion either. Read it; the
  angle it needs will be obvious once you have.
- Elapsed time, round count, and effort already spent are never reasons to stop.

**And the register's own numbers survive re-derivation.** The rounds can each be honest and the
document still be wrong. Before the gate closes, take the document apart:

- **Re-derive every count in it, from the record, without reading what you wrote.** Every "N of M",
  in rejected candidates as much as accepted requirements. A rejection resting on a false count is a
  requirement wrongly killed — on 2026-08-07 one turned on "none of the forty-three blocked runs
  records an error on the blocking step", and ten of the forty-three do.
- **Check that M is the population the sentence sits in.** A cost that day read "median sixteen
  calls per run", measured over the seventy-nine runs that reached the step, inside a paragraph
  about all one hundred and thirty. Over the population as written, the median was nine.
- **Reconcile every summary against the tables beneath it.** The same document declared thirty-one
  rejections; its round tables held thirty-three; a third table named twenty-seven. Add the tables
  up and take their answer.
- **Verify every name the register borrows from the system** — step numbers, phase names, file
  names, identifiers. That document had four neighbouring step numbers wrong throughout, which makes
  every finding about them unreadable to anyone who checks.

- **Check that every condition's script is actually in the document.** Not named, not described —
  present, in full, so a reader can run it. The register promises this and nothing enforces it: on
  2026-08-08 four conditions, including a whole guard and the claim about the goal's number, cited
  scripts the document did not contain, and only their author could settle them.
- **State the goal's number once.** If a later pass changes it, correct the earlier statement rather
  than leaving both. That same document carried three different figures for the same ceiling, the
  wrong one at the top where a builder reads first.
- **Map every rejection to the round that produced it, both ways.** Not a total that agrees — a
  mapping. On 2026-08-07 the table and the round counts both came to about the right number while
  three rejection rows belonged to no round at all, two rounds' rejections had no row, and one row
  cited a round the document does not contain. Totals can agree while the document is incoherent.
- **A claim about the goal's measure is tested, not reasoned.** The same document told its owner
  that a perfect subject would leave the goal's number where it stands. Removing the faults its own
  requirements name from the measured documents and re-reading the measure moves it. If the
  register says something about the number the owner steers by, it earns that sentence the way a
  requirement earns its cost: by producing the reading both ways.

  **Remove the fault everywhere it appears, not only from the subject's own document.** What the
  subject writes is quoted, copied and re-rendered by whatever reads it downstream, so a reading
  that repairs one copy still trips over the others. On 2026-08-07 a register put its ceiling a
  whole document too low for exactly that reason: it substituted a clean version of the subject's
  document into an otherwise frozen directory, while two further documents went on quoting the
  sentence that would no longer exist.
- **Where a cost states a population, name its members.** A count nobody can enumerate cannot be
  checked. On 2026-08-07 a requirement claimed twenty-one runs and listed nineteen ids; the true
  figure was nineteen, and the extra two were the same runs counted twice under a second check. If
  the list and the number disagree, the number is wrong.

Anything that fails here reopens the rounds. A corrected count can revive a candidate that was
rejected on the wrong number, and a revived candidate is a new accepted requirement, which resets
the counter to zero.

**Run this last, after the final round, and again if any round follows it.** It is an accounting of
the whole document, so it is worthless run over part of one. In that same register the recount was
performed and three more rounds were then appended; the totals it published were short by the rows
those rounds added, and the gate was declared on the stale figure.

## The register

One file per subject, appended to and never rewritten. It carries, in order: the header, the
accepted requirements, the rejected candidates with the test each failed, the round record, and the
evaluation pass with a verdict for every accepted requirement.

Each accepted requirement carries:

| field | what it holds |
| --- | --- |
| id | stable, referenced by the implementation |
| kind | repair or guard |
| requirement | what must become true — one sentence, no design in it |
| evidence | the record it came from |
| costs now | what today's behaviour costs |
| definition of success | the runnable predicate that decides it is met — the command or exact comparison, not a description of one — with the cost above it being that predicate's own output |
| whose outcome | who is better off, and what they can then do |

The rejected list is part of the document, not scratch. It is what stops a candidate being
re-proposed, and it is what shows the reader that the filter actually ran.

A rejection that rests on a measurement carries two more things, because a strike is a requirement
killed and it is the cheapest place for a document to go wrong. Both were breached on 2026-08-07,
in the same document, and each one buried a finding an earlier register had proven:

- **The object compared, named.** A candidate about the step resubmitting an identical document was
  struck on "one run of twenty-three", obtained by hashing the whole request object — text plus
  inventory plus questions plus attempt counters — which differs between attempts whenever a
  counter moves. Compared on the document itself, the thing the candidate is about, it is ten runs
  of nineteen.
- **The same standard for every candidate.** Another candidate was struck as "already true today"
  on the strength of a filter that exists only as an uncommitted change and has never run, in a
  document that struck a different candidate precisely because an uncommitted change cannot be
  shown working. A rule applied to one candidate and not its neighbour is not a rule.

## The evaluation pass — run it after the gate closes, before anything leaves

The gate says the rounds stopped producing. It says nothing about whether what they produced is
true. So every accepted requirement is re-opened once more, and this pass is not optional.

For each one, in order:

1. **Open the artefact it names.** The run record, the log line, the code path, the external
   document. Not your memory of writing it — the thing itself. A requirement whose artefact cannot
   be opened is struck here.
2. **Second-hand evidence fails.** A comment describing a measurement is not the measurement. A
   summary of a record is not the record. If what you can open is somebody's note about the fact
   rather than the fact, the requirement is struck, however plausible the note.
3. **Read the definition of success as a stranger.** Could someone with no memory of this work
   settle it, and settle it the same way twice? If not, it is struck.
4. **Ask what it is redundant with.** A requirement that follows automatically once two others hold
   is not a requirement; say which two.

Record a verdict per requirement in the register, with what you opened. A struck requirement stays
in the document with its reason. The filter catching something late is the filter working, not the
filter failing — and hiding a late strike is how a list becomes something nobody can trust.

## Approval

Requirements are not self-approved, and nothing is implemented from this document until the person
who owns the goal permits it. Two things about how that is asked:

- **Do not ask them to accept the list.** Deciding whether a requirement is correct is the author's
  work, not theirs; handing over a list of unjudged items and asking "do you accept these?" is the
  judging being passed upward. Run the evaluation pass, be certain, and say so.
- **Ask for permission to act, not for a verdict.** Present what stands, what was struck and why,
  and ask to implement. If you are not certain, do not ask — finish the evaluation first.

Present, in this order: the requirements that stand, the ones struck with their reasons, and the
two rounds that closed the gate. Never a bare count; a number is not a list.

## What this playbook does not do

It does not design the solution. A requirement says what must become true; how belongs to the
implementation controller. When a candidate can only be stated as a design ("use a JSON schema"),
restate it as the outcome it produces ("a contract failure cannot reach the validator") and let the
implementation choose the mechanism.
