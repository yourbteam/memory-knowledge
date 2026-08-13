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

| 10 | The machinery ran end to end for the first time and its last stage was its weakest: two measuring passes agreed on only 68 of 91 verdicts | the runner's own measuring instruction now states what the readers had to guess: already met means every part is done and you can point at what does each part; half satisfied is a change; a partial attempt is a change and not an addition | pending — two runs are exercising the sharpened instruction | 68 of 91 agreed; the sharpening targets 13 of the 23 differences | 2 runs |

| 11 | Everything the machinery produced rested on a description nothing checked. Its factual claims were checked for the first time and seven of twenty-two were contradicted by the code | the description's marked facts are extracted and each must be cited — file, line, exact text — before any requirement is written; the check runs twice, by readers who cannot see each other | Rounds of wrong claims: 7, then 4, then 2, then 1. On the last round two independent readers returned identical verdicts on all twenty-nine, twenty-eight holding. The one failure was the document's own account of how often it had been checked | the requirements list is invalidated and being rebuilt from a description whose facts now hold | 6 verification runs, 3 corrections |
| 11a | Four verification rounds were spent on one footnote about how many rounds had been run — the extractor treated the section that *defines* the marks as if it made claims about the harness | a section that defines the marks is a section about the document; it is excluded structurally, by the shape of its own definition lines, not by name | 29 claims became 27, and the footnote is no longer among them | no change to the goal; it stops the loop burning rounds on itself | 1 run of the tool |

| 12 | The description's facts were repaired five times, and every repair was made by hand, outside the machinery. Nothing in the machinery says whose job that is, so a reader of it would take the gap for an omission | nothing in the reading stages was changed; the boundary Kamen set was written into the machinery's own instructions — this machinery consumes a description and refuses to advance on a false one; writing or repairing a description belongs to a separate machinery, tackled separately | The fifth round came back clean: two independent readers, blind to each other, returned `holds` on all twenty-seven claims with a cited file, line and quoted text behind each, and neither raised a `what_must_change`. The gate opened on its own and the reading stages were handed out | the deciding fact named in entry 11 is now recorded: the round came back with nothing wrong | 2 runs |

| 13 | The instruction each reader received was not the instruction the runner emitted. One sentence — write files as you go, you are one of two, do not read the other's directory — was being appended by hand every time, after a live reader was killed for looking idle when it was mid-read. SKILL.md demands the instruction be handed over verbatim, so the machinery's own rule was being broken by the only step it cannot do itself | the sentence was moved into the runner and is now appended to every packet the runner emits, so what a reader is told is what the machinery said | pending — the next stage handed out will carry it without anything added by hand | no change to the goal; it closes the last place where a person's wording reached a reader | 0 runs; found by being asked to confirm |

| 14 | Two readers were told not to look at each other and both wrote working files into the shared directory under the same obvious names. They overwrote each other's inputs mid-read. One noticed its own input had changed under it and said so; the other did not, so the breach was found by luck rather than by anything the machinery does | every reader is given a scratch directory of its own, created by the runner and named in its instruction, sitting beside the answers rather than inside them so the completeness gate still counts only answers | pending — the two measuring passes were set aside as evidence and re-handed with private scratch directories; the runner's printed instruction now names each reader's own directory | not comparable — the measuring numbers from the contaminated pair are withdrawn | 1 full run; found because a reader reported it |

| 15 | The measuring stage had never been run by two readers who were provably separate: the first attempt on this subject had them writing over each other's working files | nothing new was built; the stage was re-handed with the private scratch directories from entry 14 | Both readers finished all 143 and each reported, unprompted, that its working files stayed in its own directory and that it opened no sibling's. The shared directory holds only the machinery's own six files. Verdicts agree on 119 of 143; the report names the other 24 rather than resolving them | measuring agreement: 68 of 91 → 69 of 91 → 119 of 143, the first of the three from readers proved separate | 2 runs |

| 16 | The machinery names no model anywhere — deliberately, because whoever runs it supplies the reader, so running it from another tool reads it with that tool's model. What was missing is the other half: no record said which reader produced a verdict, so `119 of 143` cannot be set beside any later number | every packet now asks its reader to write what it is before finishing; the runner gathers those answers into the report and the document prints them at the top. Nothing chooses a model, and the wording says so, so the record is not later mistaken for a requirement | Re-ran the command: the report carries `read_by` and the document opens with a **Read by** line. For the two readers that finished before the change it reads "not recorded — this reader did not say what it was", which is the honest answer rather than a backfilled one | no change to the goal; it makes every future number comparable | 0 runs; found by Kamen asking which model the machinery picks |

| 17 | Twenty-four of 143 requirements went to a person because two readers split on how much of a half-built thing counts as done — the machinery deferring, not the document being honest | prototyped, not yet built in: each of the 24 was broken into parts — one thing separately true or false — and two readers answered each part yes or no with a cited line, with the verdict derived by arithmetic rather than chosen | 73 parts. The two readers agree on 59 of them, and the derived verdicts agree on **14 of the 24** — requirements on which the whole-requirement method had agreed on none, by definition. Judge one answered 20 yes, judge two 30 | measuring agreement on the hardest 24: 0 of 24 → 14 of 24 | 2 splitters + 2 judges |
| 17a | The first attempt asked whether two splitters split a requirement the same way. They did not — 13 of 24, every miss off by exactly one part, always the same direction, and never about substance | the question was wrong. The split is shared material, like the pairs the merge judges read; it does not have to be reproducible, it has to be the same for both judges | The judging run above used one split for both readers and produced the gain | no change | 2 splitters |
| 17b | A checker was written to bound how fine a split may be, from the requirement's own sentence | nothing kept — it refused 23 of 24 splits, including ones plainly correct, and its word test fired on 22 of 24 | measured on both splits and reported rather than tuned | no change | 1 tool, discarded |

| 18 | Parts were built into the machinery and run over all 143 requirements. The number they were built to move went the **wrong way**: agreement fell from 119 of 143 to 113 | nothing yet — the result is recorded before anything is changed | 143 requirements became 354 parts. The two readers agree on **299 of 354 parts (84%)**, but a requirement's verdict flips if any one of its parts flips, so requirement-level agreement fell. Of 44 one-part requirements, 5 still disagree — those cannot be split further. The envelope's stopping condition (agreement above 119) is **not met** | 119 of 143 → 113 of 143 | 1 splitter + 2 answerers |

| 19 | Entry 18 predicted the 55 disagreeing parts would mostly be code-versus-real-output, two readers citing different evidence for the same fact. **Measured: they are not.** 45 of the 55 have one reader citing a line for 'yes' and the other giving nothing at all for 'no'. Only 7 are the predicted code-versus-output split | the instruction's own asymmetry caused it: a 'yes' had to cite a line, a 'no' cited nothing. So half of every disagreement was unfalsifiable and nobody could tell which reader had looked in the right place. A 'no' must now name the nearest thing in the build and say why it does not satisfy the part, or say what it searched for and where; a bare 'no' is refused | pending — the first answering round was set aside as evidence and both passes were re-handed with the sharpened instruction | 113 of 143 stands until the round returns | 1 classification over the existing records |

| 20 | The sharpened instruction — a 'no' must name the nearest thing and say why it falls short — was run over all 354 parts by two fresh readers. **It made the number worse.** Disagreeing parts 55 → 64; requirement agreement 113 → 104 | nothing; the result is recorded before anything else is changed | Both rounds are on disk. Round one: 55 of 354 parts disagree, 113 of 143 requirements agree. Round two, same parts, same repository, sharpened instruction: 64 and 104. The yes-counts also moved between rounds by more than the instruction could explain — 160/135 then 172/140 — so run-to-run variation is of the same size as the effect being chased | 113 of 143 → 104 of 143 | 2 answering runs |

| 21 | Three rewordings of the answering stage had failed; the last made it worse. The disagreements were still going to a person untouched | a settling stage: code pairs the two answers with their citations and what each says it looked at, and two fresh readers settle each dispute against the build — citing the line that decides it and naming what the other side missed — or answer 'cannot settle'. A dispute counts as settled only when both settlers agree | 64 disputes, both settlers finished. They agree on 51 and every one of those is decided. Requirement agreement **104 → 137 of 143**; what goes to a person **33 → 9**. The settlers found things neither answering pass had: a whole cluster of disputes was one reader citing the wrong step — the publication phase — for facts about the composing one, and a guard both sides argued over is never reached because its caller returns first | 113 of 143 → 104 → **137 of 143** | 2 settling runs |

| 22 | The claim extractor read a bracket as a mark the sentence carries even when the sentence was only talking about marks. On the phase-58 rebuild it handed out 25 statements to check against the repository; two of them were the description's own bookkeeping — "every statement marked [in code] would be re-checked" and "no release step re-validates its [in code] statements" — and readers were sent looking in the code for a sentence about the description | the bracket is read by its punctuation, not by its words: a carried mark is a tag against a boundary — sentence start, sentence end, or a dash, colon or semicolon that already broke the grammar — and a mark with a word each side is a mention. Mentions are listed under `marks_mentioned_not_carried` rather than deleted, because the rule reads punctuation and will sometimes be wrong | run from an empty work directory against the same description: 25 claims → 23, and the two it stopped deriving are exactly the two above. One `[UP]` mark was reclassified with them and looks like a genuine tag — it appears in the mentioned list, where it can be seen. The pattern exists in one file, so that is the whole class: 1 found, 1 fixed | 25 statements to check → 23, two of which were never checkable | 1 prototype over the real description, no reader run |

| 23 | The citation checker resolved a citation by its line number, tolerating a drift of four lines. While the implementation machinery was building into the same repository the readers were reading, every quoted line moved further than that, and 16 true answers across two passes were refused for evidence that was still there. The refusal then handed back no work at all, so the run stopped until a person deleted the refused files by hand — the one thing nobody should do to a machinery's output | two changes. A citation is now its text in the file it names: exact line, then a window of four, then the whole file — and a quote occurring exactly once in that file *is* that line, wherever it moved to. More than one occurrence and none near the cited line stays refused, because which is meant genuinely cannot be decided. Separately, a refusal now sets its own answers aside into `answer-N-refused/` and re-emits the reading packet, so a refusal always leads somewhere | run over both real answer sets against the live repository, old checker beside new: pass 1 refused 4 → 0, pass 2 refused 12 → 1. The one that remains is the ambiguous shape the rule keeps: a quote carried on 67 lines of `runner.py`. A fabricated quote and a quote at an impossible line number both still refuse. The class is a citation resolved by position rather than content; it exists in one file — 1 found, 1 fixed | 16 refusals of true evidence → 1, and that one is genuinely ambiguous | 2 checker runs over records already on disk, no reader run |

| 24 | Six delivery contracts existed in prose but not in the controller: a greenfield run wrote no documents; the second blind reading was discarded; count-complete verification could carry the wrong claim and nonexistent citation; `remove` was unreachable; installed client runtime policy had no launch point; and an uncovered `o1` crashed instead of returning a state | the controller now splits greenfield requirements and writes both documents; accounts for and consolidates both obligation and leftover passes; uses exact identity/value/citation gates at all seven model stages; classifies false parts as add/change/remove and derives pure removal arithmetically; owns optional policy-checked reader launches; and exposes four finite terminal statuses with a bounded stall rule. The shared coverage sort accepts every enumerator prefix | 18 focused controller/runtime tests pass, including real CLI completion for greenfield and built removal, a real CLI refusal of nonexistent verification evidence, and proof that a refused client policy starts no process; 7 count/existence stage gates found and replaced, and the one prefix-assuming coverage sort found was fixed | promised delivery contracts: 0 of 6 executable end to end → 6 of 6 | 6 adaptive prototypes over four captured failures |

## Verdict, entry 21 — the disagreement was always decidable; nobody was looking at both answers

Path A. The largest single move in this ledger, and it came from applying the machinery's own
division one level further rather than from another instruction: the disagreement is material, so a
reader is given it. Nothing was discarded — both answering passes stand exactly as they were, and
the settling stage can only shrink what a person is handed, never manufacture agreement, because a
settled answer needs both settlers to say the same thing. The dominant cause it exposed is a real
defect in reading rather than a difference of taste: one reader had been citing a downstream step
for facts about the step under judgement.

Path B. Thirteen disputes the settlers themselves split on remain, and one settler decided
everything while the other refused one — so the settling stage has its own disagreement rate, and
stacking a reader on a reader could recurse without end. If the next subject's settlers split on a
third of the disputes, this is a ladder rather than a floor.

**Verdict: Path A.** **The deciding fact:** whether the settlers' own disagreement rate stays near
a fifth on a subject they have not seen. If it climbs, the answer is not a fourth reader; it is
that those parts are genuinely undecidable from a repository and belong with the person who owns
the goal, which is where they already go.

## Verdict, entry 20 — wording is not the lever on this stage

Path A. Two rounds is a small sample, the readers differed between rounds, and the reasoned 'no'
made every disagreement *arguable* even where it did not reduce the count — which is worth something
on its own, because a disagreement with reasons on both sides can be settled by a third reader while
a bare 'no' cannot.

Path B. This is now the third wording change to this stage and the record is unambiguous about the
first two: spelling out that half-satisfied is a change moved 68 → 69 of 91; demanding a reason for
'no' moved 55 → 64 of 354, the wrong way. Meanwhile the yes-count moved by twelve between two rounds
of the *same* instruction, so the noise is larger than any effect wording has produced. Instruction
is not the lever. The replacement is a stage that takes two answers and their evidence and settles
them — the machinery's own division applied here for the first time, since today the disagreement is
handed to a person rather than to a reader with both sides in front of it.

**Verdict: Path B, additive.** Nothing is discarded: both answering passes stay exactly as they are,
and a third reader is given the two answers and the lines behind them. **The deciding fact:** whether
a reader holding both sides settles more of them than it leaves. If it mostly abstains, the parts are
genuinely undecidable from the repository and the honest place for them is in front of Kamen.

## Verdict, entry 19 — the prediction was wrong and the record said so

Path A. The measurement took one pass over records already on disk and refuted the guess in entry
18 outright. The cause it found is inside this machinery's own instruction rather than in the
subject, it is one sentence to fix, and it explains the shape exactly: 45 of 55 disagreements had
one side carrying evidence and the other carrying none.

Path B. This is the second time the answering stage has been sharpened by wording, and the first
time — spelling out that half-satisfied is a change — moved the number by one. If demanding a reason
for 'no' moves it as little, then wording is not the lever on this stage at all, and the honest
replacement is a stage that adjudicates the two answers against each other rather than one that
hopes they converge.

**Verdict: Path A, and Path B has a date.** **The deciding fact:** whether the re-run's disagreement
count falls below 55. If it does not, the next fix is adjudication, not instruction.

## Verdict, entry 18 — the fix improved the question and lost the number

Path A. Every question a reader now answers is one a reader can answer, and 84 per cent of them
agree. What each disagreement hands over changed too: instead of a whole requirement with two
labels, it is one sentence with a yes and a no beside it. On the twenty-four that had defeated the
old method, fourteen now have an answer nobody had to choose. Nothing was discarded.

Path B. The measure this was built to move went backwards, and the reason is structural rather than
incidental: a requirement of five parts has five chances to disagree, so finer questions buy higher
per-question agreement and lower per-requirement agreement. If the goal is fewer things handed to a
person, splitting works against it, and the honest replacement is to hand over the *part* rather
than the requirement — which changes what the document is, not how it is judged.

**Verdict: neither path is carried yet, and one measurement decides it.** The five one-part
disagreements are the tell: they cannot be split further, and every one is two readers citing
different places for the same fact — code against real output. **The deciding fact:** whether the
55 disagreeing parts are mostly that same code-versus-output split. If they are, the next fix is
naming which evidence wins, not dividing further, and the number moves back on its own.

## Verdict, entry 17 — parts turn a stalemate into arithmetic

Path A. The distance moved on the exact number that was stuck: 0 of 24 → 14 of 24 on the hardest
set in the ledger. The mechanism is the machinery's own division applied one level down — the reader
answers a question small enough to have an answer, and code does the counting that used to be a
judgement. It discards nothing; the whole-requirement path still runs for anything unsplit.

Path B. Fourteen parts of seventy-three still split the two readers, so parts do not remove
disagreement, they move it somewhere narrower. If the next round shows the surviving disagreements
are the same kind — how much of a part counts — then splitting is recursive and the approach never
bottoms out; the replacement would be a stage that refuses a requirement whose parts cannot be
answered rather than one that keeps dividing.

**Verdict: Path A, promote and build it in.** **The deciding fact:** whether the 14 surviving part
disagreements are about *fact* — the code does or does not do this — or about *degree*. Fact
disagreements are two readers reading differently and shrink with citation. Degree disagreements
mean the split did not go deep enough, and that is Path B's evidence.

## Verdict, entry 16 — record the reader, never choose it

Path A. This is the same shape as entries 13 and 14: something the readers depend on lived outside
the machinery, and is moved inside it. It costs one sentence per packet and one field in the report,
discards nothing, and the first run after the change proved it by reporting two readers as
unrecorded rather than inventing an answer for them.

Path B. Recording the reader does not make two runs comparable on its own — a run read by one model
and a run read by another will differ for reasons no field explains, and the honest conclusion could
be that cross-run numbers are not comparable at all and should never be put side by side. Cost of
that reading: the ledger's central measure loses its meaning across tools.

**Verdict: Path A, and the concern is the reason for it.** The field does not make runs comparable;
it makes the incomparability visible, which is the only version of this that is honest. **The
deciding fact:** the first run from another tool. If its agreement count differs sharply from this
one's, the field has done its job by saying why — and the ledger will carry both numbers rather
than one.

## Verdict, entry 15 — the deciding fact from entry 14, answered

Path A. Entry 14 said the fix stands or falls on whether the re-run comes back with no reader
reporting anything unexpected in its inputs. Neither did, and both volunteered the confinement
without being asked to confirm it. Agreement rose to 119 of 143 — 83 per cent against 76 in the
sharpened-instruction round — and the machinery ran all eight stages without a stage being repaired
mid-run.

Path B. Two readers still disagree on 24 requirements, and every one of those is a place where the
document says "a person decides". If that number does not fall as the description improves, the
measuring stage is not converging, it is deferring, and the honest replacement is a stage that
splits each requirement into parts small enough that two readers cannot disagree.

**Verdict: Path A. The deciding fact for the next round:** whether the 24 have a shared shape. If
they are all one kind of judgement, that is a stage to sharpen; if they are 24 unrelated calls, the
document is telling the truth about where a person is needed.

## Verdict, entry 14 — independence has to be a place, not a promise

Path A. The fix is the ledger's own pattern: a thing the instruction merely asked for is made true by
structure instead. It is cheap, it discards nothing, and the contaminated verdicts are kept rather
than deleted, so the comparison can be made later if it is ever worth making.

Path B. The breach was found because one reader happened to notice its input had changed. Nothing in
the machinery detects contamination, and a separate directory only removes the one collision that
has been seen. If independence keeps failing in ways only a reader's own vigilance catches, the
honest replacement is a runner that gives each reader its own filesystem view rather than its own
folder, and the cost is real isolation machinery.

**Verdict: Path A, with Path B's concern recorded rather than dismissed.** **The deciding fact:**
whether the re-run comes back with no reader reporting anything unexpected in its inputs. If a
second contamination appears in a different shape, the folder is not the boundary and the isolation
argument wins.

## Verdict, entry 13 — the last hand-carried instruction

Path A. The distance is unaffected, and the fix is the same shape as every fix in this ledger: a
thing that lived in a person's habit is moved into the machinery. It is independent of everything
else, costs nothing to prove, and removes a gap that no gate could have caught, because no gate can
see what is added between the runner's output and the reader's input.

Path B. A machinery that still needs a person to launch its readers has a seam no amount of moving
text into the runner closes, and this fix could be read as decorating that seam rather than
removing it. The honest replacement would be a runner that spawns its own readers, at which point
the packet text is unambiguously the instruction.

**Verdict: Path A.** The seam is real but it is not what this fixes, and the fix makes the seam
narrower rather than wider: what crosses it is now data the runner produced, not prose a person
wrote. **The deciding fact:** whether anything else is being added by hand between the runner and
the readers. On this run there was exactly one such sentence, and after this change there is none.

## Verdict, entry 12 — the gate converged, and what it cannot do is now stated rather than implied

Path A. The deciding fact entry 11 named has landed: a round with nothing wrong among the
twenty-seven, agreed by two readers who could not see each other. Five rounds fell 7 → 4 → 2 → 1 →
1 → 0 with no round costing more than the one before, and no correction re-opened an earlier one.
The approach can say exactly what remains, and this entry adds no code at all — only the sentence
that says which machinery owns the repairs, so the next reader does not build the missing half by
accident inside this one.

Path B. The gate found errors five rounds running and every one was fixed by a person editing prose
by hand. A gate whose failures can only be cleared outside the machinery is a gate the machinery
cannot pass on its own, and the honest reading is that the description half is unbuilt rather than
delegated. Cost of that reading: a second machinery, of unknown size, before this one can run
unattended.

**Verdict: Path A, and Path B is not refuted — it is scheduled.** The gate converged on real
evidence, and the boundary is Kamen's own scoping decision, not a workaround for a defect. **The
deciding fact:** whether the next description this machinery is pointed at also needs hand repair
before the gate opens. One subject's description converging says the gate works; it does not yet
say a description can be produced that passes first time.

## Verdict, entry 11 — checking the description was the largest single gain, and it converged

Path A. The distance fell every round and the cost per round did not rise: seven wrong, four, two,
one. The corrections were independent of each other, and the last round is the strongest evidence
in the whole ledger — two readers, blind to each other, agreeing on twenty-nine verdicts. The one
remaining failure was not about the subject at all, and the fix for it was structural rather than
another patch.

Path B. Six verification runs and three corrections were spent before a single requirement was
rebuilt, and the last two rounds turned entirely on the document talking about itself. If the next
round finds a fresh error in the harness claims, the description is not converging, it is churning,
and the honest conclusion is that a document this size cannot be held true by re-reading it — it
would need to be smaller, or generated from the code rather than written about it.

**Verdict: Path A. The deciding fact:** whether the next round comes back with nothing wrong among
the twenty-seven claims about the harness. It has already come back clean twice on those; the only
failures since have been the footnote, which is now out of scope.

## Verdict, entry 10 — the last stage is the weakest, and its disagreement has one shape

Path A. Thirteen of the twenty-three differences are the same swap, already met against change.
A disagreement with one shape is an instruction that did not say something, not two readers seeing
different systems — the same diagnosis that held at entry 3, where one missing column settled a
split, and at entry 9, where both merge passes independently reached a stricter rule than the one
they were given and agreed on 94 of 95.

Path B. The measuring stage is the only one where a reader must hold a whole codebase in mind, and
no enumeration fixes what it looks at the way the sets, the candidates and the pairs were fixed
for every earlier stage. If the sharpening does not collapse the thirteen, the honest conclusion
is that this stage cannot be made reliable by instruction, and it needs its material fixed the way
the others were — a per-requirement packet of exactly the code and output that bears on it.

**The deciding fact:** whether the two fresh passes now agree on the thirteen. Ten or more
collapsing means the instruction was the gap. Fewer means the material is.

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
