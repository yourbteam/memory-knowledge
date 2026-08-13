# Chain ledger — the description machinery

Name settled by Kamen, 10 August 2026: **description machinery**.

Goal: whatever already exists that says something about a subject becomes one description of that
subject which the requirements machinery can consume without a person rewriting it first. The
material differs every time — code, logs, a conversation, notes left by an earlier run — and the
output is always the same one document.

What it takes in, settled with Kamen on 10 August 2026:

- **An intent**, always — what needs to be done or achieved, in the owner's words.
- **Context**, when any exists — code, logs, records, notes left by an earlier run, a conversation.

The machinery holds a fixed set of questions a description must answer. It looks for each answer in
the context first and quotes what it finds; whatever the context does not answer, it asks the
operator, and the answer is quoted the same way. Nothing is filled in by guessing, and every line of
the finished document points at either something in the context or something the operator said.
Greenfield is simply the case where the context answers nothing and every question goes to a person.

Two real subjects exist, and both are the test:

1. **The one that worked.** The phase-58 description was written by hand and the requirements
   machinery consumed it, producing 142 requirements still to build. That is the shape to reach.
2. **The one that does not yet work.** Twenty-three observations collected from the notes builders
   wrote while making requirements true. They are quoted exactly, which is honest, and they are
   statements rather than requirements — "eight tests already fail" is not something anybody can
   make true. A builder handed one refused it, correctly.

Distance, one number, never redefined: **of the observations that go in, how many come out of the
requirements machinery as an accepted requirement with a check somebody else can run.** Read from
the requirements machinery's own document, not from this one. It starts at zero of twenty-three.

The division is the same as the other two machineries: code fixes what gets looked at and judges
nothing; a model judges what things mean; two readers who cannot see each other, and agreement or
nothing. What is new here is the question — not "is this true of the built system" but "is this
sayable in a way the next machinery can work from".

| # | what failed | what was fixed | proof | distance | cost to find |
| --- | --- | --- | --- | --- | --- |
| 1 | The first thing this machinery produced — twenty-three observations quoted from builders' notes, assembled into one document — was handed to the requirements machinery to see what it could make of it | nothing yet; this entry is the measurement, not a fix | the requirements machinery read the document and found **three** sentences stating something was wanted. Sixty-seven sentences were left over as description with nothing to act on. Both obligation readers answered all three identically | 0 of 23 through | 1 run of the requirements machinery |

| 2 | Entry 1 read only the front of the requirements machinery — the three obligations it found — and called the document inert on that. The run had never been taken to the end | nothing here; the fix that unblocked it was in the requirements machinery, whose citation gate refused true evidence because another machinery was moving the lines underneath it | the same document, taken all the way through: 3 obligations and 30 more found in the leftover became **33 requirements**, split into 43 parts, each answered twice by readers who could not see each other. 32 of the 33 carry a verdict — 24 to add, 4 to change, 4 already met — and 2 items go to a person. Nobody rewrote the document between the two machineries | **0 of 23 → 22 of 23.** Every accepted requirement names the unit it came from, and every unit records the observation it sits under. Twenty-two of the twenty-three are named, each by a requirement carrying a verdict. Only n45 produced nothing, and correctly: it is a builder reporting that he changed no code and ran nothing, so there is nothing in it anybody could make true. **This number was reported wrong three times first** — 33 (counts requirements, not observations), 15 (read the reference as a line number in the description when it is an index into a list), and 21 (resolved only the references beginning `leftover-`, so the observations that arrived as obligations vanished). Nobody should be computing it by hand: the run should print it | 1 reader on one refused part, after the gate was repaired; four hand computations of one number before it was right |

## Verdict, entry 2 — inert was the wrong word; the front door was

Entry 1 measured three of twenty-three and concluded the material could not carry what the next
machinery needs. Run to the end, the same material produced thirty-three requirements. The thirty
that entry 1 missed came out of the **leftover** — the sentences the obliging stage had nothing to
do with — read separately by a reader who could not see the first. So the document was not inert.
The obligation stage is narrow by design, and reading only its output mistook one stage's scope for
the document's worth.

This is the second time in one day a number was reported from a stage rather than from the end of
the run, and both times the stage's number was worse than the truth. A measurement taken before a
run finishes is not a small version of the real one.

**What it does not settle:** whether these thirty-three are *good* requirements. They have checks
and citations, and two readers agreed on thirty-two of them — that is what the requirements
machinery guarantees and no more. Whether a description assembled from builders' notes yields
requirements worth building is decided by the implementation machinery consuming them, not here.

## Verdict, entry 1 — the document is honest and inert

What went in was true: every line quoted from somebody who saw the thing. What went in was also unusable, and the number says how unusable — three of twenty-three. An observation states what *is*; the next machinery can only work from what is *wanted*. Quoting faithfully preserves the first and never produces the second.

This does not move the boundary between the machineries. Deciding whether something is a real requirement, and what its check is, stayed with the requirements machinery and worked — it took the three and made requirements of them, with checks. The gap is upstream of that: nothing turned "here is what I saw" into "here is what is wanted".

**The deciding fact for step one:** whether an observation can be turned into a statement of what is wanted using only the words of the observation and the owner's intent — with no invention. If two blind readers, given one observation each, cannot agree on what is wanted without adding anything, then the material genuinely does not carry it and the operator has to be asked.

## 11 August 2026 — the general front door and deterministic gates became executable

Five captured cases were run through the real Python functions before changes: invented quotations
were accepted by both routes, wrong pair identities satisfied file counts and dropped an expected
observation, changed context reused an old answer, and eight accepted questions produced no
description. The fixes were retained only after each case turned green:

1. A claimed quotation now names an authorized source and occurs there exactly. Builder-note quotes
   are checked against the named note before pairing.
2. Within-note, cross-builder, and fixed-question stages complete by their exact expected identity
   sets rather than by file count.
3. `input-state.json` binds resumable state to intent, context, owner answers, fixed questions,
   builder notes, and order content. Changed or unbound legacy state fails closed and requires a
   fresh directory; nothing is deleted.
4. `from_intent.py` accepts a dedicated owner-answer file. Two readers must cite the same exact
   passage for every fixed question before code emits `description.md`; missing or differing
   answers remain in `to-ask.md`.
5. Both CLIs expose `complete`, `waiting_for_readers`, `blocked`, and `needs_owner`, mapped to exit
   codes 0, 2, 3, and 4. Stall detection follows the remaining identity set rather than job count.

Proof through the documented entry points: eighteen Description behavioral tests include
subprocess completion of both CLIs. The accumulated Description, Implementation, client-policy,
projection, parity, and installation surface passes **75 tests**. This proves the deterministic
contracts and fixture-backed real paths; it does not claim a live supplied model's semantic quality.

## 13 August 2026 — reader work became continuously observable

The real reader launcher was run twice before the change. Both launches wrote the same
`launch-read-1.log`, so only the last history survived, and no `feed.jsonl` existed while either
reader worked. The launcher now appends and flushes start, safe activity, structured failure, and
finish events for every blind reader job. Stage, seat, output, pid, duration, exit, delivery,
model, harness, and the unique raw-log name stay attached to that job without entering any
judgement gate. Prompt text, repository content, model prose, and error prose stay out of the
feed; lossless output stays in the referenced raw log.

Proof through the real launcher: a controlled reader was held open after emitting a tool event,
and the start and activity lines were readable before it was released. One successful launch and
two repeated failures then left three distinct logs; success recorded its model/harness and
delivery, both failures retained their raw details, and the feed contained none of the supplied
private text. The full Description and Requirements machinery tests passed together.
