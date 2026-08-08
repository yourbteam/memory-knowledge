# Chain ledger — the requirements machine

Goal: a general machinery whose runs produce the same requirement for the same subject.

Distance, one number, never redefined: **of the three fields that decide a requirement — the
population it counts over, the cost it reports, and the fault it names — how many are identical
across two independent runs on the same subject.** Read from the run records themselves.

| # | what failed | what was fixed | proof | distance | cost to find |
| --- | --- | --- | --- | --- | --- |
| 1 | Four unconstrained runs on one subject invented four populations and three faults; two runs on the *same* fault reported it as 721 of 974 and 342 of 476 | `enumerate_sets.py` — the sets a cost can be counted over are enumerated by structure, not chosen by the run | Six later runs all named the same set, all reported 31 members and the same narrowing to 20; two on the same fault produced identical per-document numbers | 0 of 3 → 2 of 3 | 4 runs |
| 1a | First enumeration returned 425 sets, the top of the list all nested snapshot copies of the same records | skip any path with a repeated directory segment, and any path carrying the root's own name | 161 sets, real records at the top | no change | 1 run of the tool |
| 2 | Two runs given the fixed set still picked different faults — c9 and c1 | `enumerate_candidates.py` — the candidate faults inside a set are enumerated, numbered, and handed to the run | Runs L and M both worked from the list and cited ids; still disagreed | 2 of 3 → 2 of 3 | 2 runs |
| 2a | First enumeration returned 298 candidates, 212 held by exactly one member | ids and numbers inside a heading normalised; heading level recorded, so a document's top sections are not listed beside its own subject matter | 45 top-level candidates, 223 content headings separated out | no change | 1 run of the tool |
| 3 | The disagreement had one cause: some sections this step never wrote, others it wrote and a later step discarded. One run dug that out of the source by hand; the other did not | `--produced-by` — each absence is attributed to the named step or to something downstream, by comparing the published record with the record the step itself wrote | Runs N and O, independent, both chose c9, both reported 6 failing of 31, and each re-derived the attribution over all 31 pairs itself rather than trusting the column | 2 of 3 → 3 of 3 | 2 runs |
| 3a | The step's own outputs could not be addressed at all — `58-compose-llm-strategy-brief` was collapsed to `*`, merging every step of a run into one set | in `_shape`, an ordinal-prefixed segment keeps its name: `*-compose-llm-strategy-brief` | the step's own set appears, 55 members | no change | 1 run of the tool |

| 4 | Every number above came from one subject in one client's records, and every delta was found by running against those same records — the agreement might be fitting, not machinery | nothing built; the tools were pointed at a subject they had never seen, a second client's briefs | Runs P and Q, independent, both chose c1 and both reported 5 failing of 12; no new structural property had to be added first | 3 of 3, reproduced on a second subject | 2 runs |

| 5 | Pointed at the subject it was commissioned for, the whole machinery returned an empty document — 45 candidates, all correctly dismissed. It can only say what is wrong with what exists, and Kamen's correction named why: the playbook has two halves, and the half that says what the thing *should* do did not exist | nothing in the machinery was changed; the missing source was built — a description of the step drawn from what United Partners wrote, from published briefs, from the code, and from decisions stated deliberately, taken from four seats and then attacked twice | 91 adversarial findings, 89 fixed in the text and 2 carried as open questions, each accounted for in the document's own table; the reader question — the one generating most of the contradictions — was put to Kamen and ratified | not comparable — the first half has no measurement yet | 4 readings, 2 attacks, 1 rewrite |

| 6 | The first half had a source but no step: nothing could turn the description into a requirement | step one of the first half — one requirement taken only from the description, with its source quoted, its check written, and what the check would need before it is possible at all | Runs A1 and A2, independent, forbidden to open the repository: both chose the same rule, both quoted the same sentence of the description, both said a program can decide the check, and both named the same three things that would have to be recorded first. The sentences differ in wording only | first half: 0 of 3 → 3 of 3 on its first pair | 2 runs |

| 7 | One requirement produced twice proves a run can read a description, not that it can read all of it. The first half had no way to say what remained | the obligations a description states are enumerated by code — every sentence that obliges something, numbered, under its heading — and the same coverage check the second half uses now counts requirements and recorded dismissals over either list | Fifty-five obligations found across twenty-two headings. Runs B1 and B2, independent and forbidden the repository, each accounted for all fifty-five with zero unaccounted; both produced 41 requirements and 14 dismissals; 53 of the 55 dispositions are identical | first half: 3 of 3 on one requirement → complete over the whole description | 2 runs |

| 8 | The obligation reader was a filter: it took the sentences carrying an obliging word and the rest of the description went nowhere. A requirement stated as a plain fact was invisible, and nothing said so | it was made a partition — every unit lands in exactly one of two numbered lists, and the tool prints the arithmetic instead of asking to be trusted. Nothing is dropped for being short, a heading, or a table row; it goes to the other list | 477 units read = 55 obligations + 414 leftover + 8 repeated sentences, balances true. The 55 are the identical set the earlier filter produced, so nothing already proven is invalidated | unchanged, and the unknown is now named: 414 units nobody has read | 1 run of the tool |

| 9 | Three passes now produce requirements for one subject and they overlap. Merging them is a judgement, and doing it inside a producing run was already unreliable — each run had dismissed five duplicates by hand and the two split on one | code does the searching and never the judging: it scores every pair, hands over the ones worth reading whole, and proposes nothing. A separate pass decides each pair | 104 requirements, 5,356 possible comparisons reduced to 95 pairs. Two independent merge passes returned 14 and 13 merges; 94 of the 95 verdicts are identical. Both kept apart the pair sharing 93% of its words, both naming the same reason: one forbids quoting from mid-sentence fragments, the other says what to do when a fragment is all there is | first half: complete list → complete list with its duplicates named | 2 runs |

## Verdict, entry 9 — Kamen's caution was the right test, and it held

Path A. The merge layer discriminates rather than merely being cautious: the same passes that kept
the 93%-overlap pair apart merged a rule whose two versions differed only in that one enumerated
what the other named collectively. Both independently arrived at a stricter rule than the one they
were given — merge only where each requirement demands everything the other demands — and both
caught the same subset traps: a compound fail-closed rule paired with each of its halves, an input
declaration paired with the output constraint that consumes it, a container paired with its
contents.

The single disagreement is worth keeping: the status-line pair, which is the requirement both
step-one runs chose on their own. One pass merged it, the other held that the two sides differ.
That is the one pair a person should read.

**What the pairwise format cannot record**, named by one pass rather than hidden: where one
requirement strictly contains another, both were kept, because there is no way to write a partial
absorption in a verdict about two things.

## Verdict, entry 8 — Kamen's two additions are both right, for different reasons

**Path A — true defects on a sound approach.** Both additions are additive and neither discards
anything. The leftover pass makes an unknown set knowable, which is the one move this ledger has
never regretted: the enumerated sets at entries 1 and 3, and the obligation list at entry 7, each
turned a judgement into a count and each held. The partition is the same move applied to the reader
itself — its coverage claim is now checkable arithmetic rather than a property of its regular
expressions.

**Path B — the approach will not reach the goal.** The reader has now been changed twice, and a
third change would mean the language markers are the wrong instrument: a description could oblige
things in ways no word list catches, and each miss would be found only by another pass. If the
leftover pass returns a large number of real requirements, the marker list is not a reader, it is a
sampler, and the first half needs a form the description is filled into rather than prose to be
mined.

**Verdict: Path A, and the deciding fact is what the leftover pass returns.** A handful of found
requirements means the markers caught most of it and the pass is the backstop it was meant to be. A
flood means the markers were never the right instrument.

**On dedup, and Kamen's caution.** It belongs after the leftover pass, not before: merging a list
that is still growing hides the additions. And it runs over the finished requirements, never over
the obligations — two sentences can state one obligation while two requirements taken from them
differ in what must become true. Both runs at entry 7 deliberately kept two near-identical rules
apart; a merger that cannot reproduce that distinction is wrong, and that is its test.

## Verdict, entry 7 — the first half can say what remains

Path A. Both runs closed the list, with the same split, and the only difference is which of one
mirrored pair of sentences carries the requirement and which is dismissed as its duplicate — the
same obligation either way. Two deltas were needed on first contact, both structural and both
caught by running against a real description rather than reasoned about: a bookkeeping table whose
rows quote obligations without stating any, and sentences cut in half at the line wrap.

**What is now true.** The first half produces a complete, counted list of what the step must do,
taken from the description and nothing else. The second half measures what exists. Neither has yet
been asked to produce the thing Kamen actually described: the requirements that must be **added,
changed or removed** to close the distance between them.

## Verdict, entry 6 — the first half behaves like the second did

Path A. The first pair agreed on all three things that decide a requirement here: which rule, what
the check is, and what the check needs. That is where the second half arrived only after two
corrections, and it arrived there immediately — because the description does for the first half
what the enumerated set did for the second: it fixes the material the run chooses from.

What that does **not** prove: that the pair would agree on the *second* requirement, or the tenth.
One run choosing the same first rule as another may only mean the description leads with it. The
next question is the same one the second half faced at step three — whether a run can dispose of
every candidate the description contains, not just produce one from it.

## Verdict, entry 5 — the first half gets built the way the second was

**Path A — a true defect on a sound approach.** Nothing built so far is discarded. The five proven
steps become the measuring instrument for the second half, which is exactly what they were always
for; they were simply asked to do the first half's job as well, and could not. The distance the
ledger has tracked never fell back. And step one of the first half is the same shape as step one of
the second — produce one grounded item, then measure where two runs drift — which is the strongest
available reason to expect it to behave the same way.

**Path B — the approach will not reach the goal.** Everything above rests on one document written
by one process. If two runs reading it produce unrelated requirements, the description is not a
source a machine can work from, and the first half needs a different foundation — a form the
description is filled into, rather than prose to be interpreted. That would be additive, not
destructive: the description's content survives into whatever replaces its shape.

**Verdict: Path A, and the deciding fact is the next run pair.** Whether two independent runs, given
this description and nothing else, produce the same requirement. If they do not, the question is
whether they disagree about the *same* thing — as they did at step three, where one missing column
settled it — or about different things each time, which is Path B.

## Verdict, entry 4 — the machinery is not fitted to one subject

Path A. The tools ran unchanged on records that shaped none of them, and two independent runs
agreed on all three fields there too. The fitting concern is answered.

The same exercise exposed the blind spot in real data rather than in argument: of five unseen
record sets tried, **three returned zero candidates** — every member structurally identical. Where
a set is uniformly wrong, this machinery finds nothing to require. That is not a defect to fix
here; it is the sentence any completeness claim has to carry.

Completeness is now the next step, and it was not before this entry.

## Verdict, entry 3 — settled by the runs

Path A. The deciding fact came back: both runs picked c9, both reported 6 of 31, and the sentences
differ only in wording. The distance is 3 of 3 — two independent runs on one subject now agree on
the set, the cost, and the fault.

What the runs still do not settle, and the next step must: **one requirement is not a document.**
The enumerator finds one kind of fault — a structural property some members of a set have and
others do not. It cannot see a fault every member shares, and it cannot see one that is not
structural at all. A completeness claim has to state that boundary, not hide it.

The argument as it stood before the runs came back is kept below, because the verdict is only
worth what the losing argument was.

## What comes next — completeness, or generality first

**Completeness.** It is the thing between one requirement and a document, and it is now countable:
45 top-level candidates, each attributed. Cost: new code, and a new claim about what the count
covers.

**Generality.** Every number in this ledger comes from one subject in one client's records, and
every delta was found by running against those same records — heading levels, ordinal step names,
the produced-by pairing. Two runs agreeing on *this* subject does not show the machinery agrees on
another; it may show the machinery has been fitted to this one. Cost: two runs on a subject the
tools have never seen. No new code.

**Verdict: generality first.** It is the cheaper of the two, it needs nothing built, and a
completeness count is worth nothing if the list it counts is an artefact of one repository. Two
other brief sets already exist in the enumeration — 12 members and 5 — and neither has been used
to shape anything.

**The deciding fact:** whether two runs on an unseen subject agree on set, cost, and fault without
a new structural property having to be added first. If a new property is needed, the fitting
concern is real and completeness waits.

**Path A — true defects on a sound approach.** The distance moved 0 of 3 → 2 of 3 and has not
fallen back. Nothing has been discarded: every delta is additive, and each earlier proven property
still holds. The approach can state exactly what remains — one field, the fault. The rows marked
`a` are the tool meeting real data for the first time, not corrections of a wrong idea.

**Path B — the approach will not reach the goal.** Every delta is a new structural property that
code must know, and each was discovered only by running against real data. If the supply of such
properties is unbounded, the third field never closes and each round costs another pair of runs.
Entry 2 is the evidence: it cost two runs and moved the distance not at all.

**The deciding fact:** if N and O pick the same id, Path A is confirmed and the distance is 3 of 3.
If they disagree, the question is whether the cause is the *same* missing property or a *new* one —
a new one each time is Path B.
