# Chain ledger — the implementation machinery

Goal: the parts a requirements run says are still to be built get built, one proven step at a time.

Distance, one number, never redefined: **of the parts the requirements machinery marks still to
build, how many are grouped into a job somebody can actually pick up** — a job being the parts that
must become true together. Read from the grouping's own output.

The subject it is built against is the same one the requirements machinery was built against:
the strategy brief step. Its breakdown holds 183 parts still to build, spread over 92 requirements.

| # | what failed | what was fixed | proof | distance | cost to find |
| --- | --- | --- | --- | --- | --- |
| 1 | The parts are the right unit to prove and the wrong unit to build: 125 of the 183 sit in 56 requirements where nothing exists at all, and several of those describe one shared structure. "Every block carries exactly one state" cannot be built before the blocks exist | first attempt: group requirements by the distinctive words they share, the way the pairing tool finds duplicate requirements | **It does not work.** At every threshold nearly everything stands alone — 47 jobs of 52, then 64 of 72, then 88 of 90 — while whatever joins chains into one lump of 25 requirements, linked by pairs sharing nothing but "client" and "names" | 0 grouped | 1 tool, discarded |
| 1a | The relation was wrong, not the threshold. Similar wording is not what makes two things one job | code proposes the pairs worth reading and judges none of them; two readers who cannot see each other say which pairs are a real dependency of existence and which of the two must be built first; a pair joins only when both agree, and both name the same foundation | 549 pairs read from 4,186 possible comparisons, none dropped. The two readers answered **524 of 549 identically (95%)**; 17 pairs both called one job; 16 of those name the same foundation. 92 requirements became **76 jobs** — 14 of them multi-requirement, one pair left for a person | 0 → 183 parts in 76 jobs, 14 of which join work that would otherwise have been done in the wrong order | 2 reading runs |

| 2 | Re-run against the corrected breakdown, the pairing proposed 1,131 pairs from 10,011 comparisons over 142 requirements — double the first subject, and more than one reader finishes in a sitting. Lowering the net to fit the reader would change what gets looked at to suit the tool | the step hands back its own reader instructions instead of the driver writing them, and cuts the pairs into slices small enough to finish: three slices, each read twice, six jobs | the smallest slice is settled: both readers judged all 31 pairs, called the same 4 pairs one job and the same 27 separate, and named the same foundation on all four. The four 550-pair readers are still running | 0 grouped of 142 requirements | 1 emitter, 6 reading runs |
| 2a | Reading that result found a fault in the emitter before it could do harm: the assembling step intersects one pass against another, so six slice directories would have intersected three disjoint slices, found nothing in common and returned zero joins — an empty answer that looks like a finished one | the slices are collected back into two whole passes before assembling, and the step will not report itself finished until they are | not yet exercised — the collecting runs when the four large readers finish | 0 grouped of 142 requirements | 1 reading of the run |

| 3 | The assembling produced the lump the machinery had already been taught to avoid. Both readers agreed on 123 dependencies out of 1,131 pairs — 96 to 98 per cent identical verdicts, and where both said one job they named the same foundation 111 times of 112 — and the assembler then joined every join: **76 of the 142 requirements collapsed into one job of 137 parts** | it merges nothing. What two readers give when they say one of these must exist first is an order, not a grouping, so every requirement stays itself and carries what it stands on. The order comes out in rounds: everything that needs nothing, then everything the earlier rounds satisfy | re-assembled from the same readings, no re-reading: **142 requirements in 6 rounds of 68, 35, 24, 12, 2 and 1**, all 142 ordered, 123 dependencies kept, no cycle, one pair left for a person where both agreed on the dependency and named different foundations | 0 grouped → **142 of 142 in a build order** | 1 assembler, discarded |
| 3a | The steps only ran in the right order because the driver typed three commands in the right order, and on this same day the driver got that order wrong | one command owns the order and the gates: it proposes the pairs, hands back only the reading still outstanding, and puts the work in order when nothing is. It refuses to go on from a report that changed under it | run from an empty directory it stops at the reading and hands back six jobs; run against the finished directory it returns the six rounds. Both exercised | 142 of 142 in a build order | 1 driver |

| 4 | Nothing in the machinery changed the built system. The order says what to build; no step built anything | a step that takes the next item off the order — earliest round, smallest piece — records which of the built system's tests already fail *before* touching anything, hands the change to a builder given one requirement and nothing else, then has two blind readers answer the same sentences against the changed code | the first item, the controlled-topic register, was changed by the builder in one file. Test failures before: 8. After: the same 8, none new. The builder also named four things it noticed and left alone, including a later gate that still checks the full settled list | 0 of 142 built | 1 step, 1 build run |
| 4a | The step then declared it done, and the gate that said so was faulty. Both readers said yes — but one answered under the name `r108` and the other under `r108.p1`, and the gate grouped answers by name, so each name held one yes and the result read as unanimous. Every sentence had been read by exactly one reader | the reader is now given the exact name to answer under, and the gate requires one yes per reader per sentence, reports any sentence no reader answered, and reports any answer filed under a name no sentence has | the two readings were thrown away and re-handed on the new basis; the change to the built system was left untouched while they re-ran | 0 of 142 built — the earlier 'built' verdict is withdrawn | 1 reading of the verdict |

| 4b | The corrected gate was untested: the earlier verdict had been withdrawn and nothing had passed on the new basis | nothing — the two readings were re-handed with each sentence named, and the step re-judged | both readers answered under the required name, both yes with lines quoted; no test that passed before was failing. The step wrote its done record and took the next item by itself. The second item — the interview question set becoming a declared output — went through the same path with **no new gate invented**, which was entry 4's deciding fact | 0 → **2 of 142 built** | 2 build runs, 4 readings |

| 5 | The twenty-third item was refused and the machinery had no way to unblock it. The requirement forbade handing over a "not generated" notice in place of a brief; four committed tests required exactly that notice, and the build instruction forbids editing a test to agree with the change. The builder was right to stop — but the only channel for the owner's answer was the driver's message to the next builder, which is the seam this machinery exists to close | the step reads an optional `rulings.json` in the work directory, keyed by item, and appends the owner's words **verbatim** to that item's build instruction, telling the builder the ruling settles the question and that a test requiring the forbidden behaviour is now wrong and may be changed, named and explained | the ruling was written to disk and the step's handback confirmed it reached the instruction; the builder then changed the no-executor path to return an empty document under a blocked status, rewrote **four** tests (it found one the refusal had not named) and said which and why; no test that passed before was failing after; both blind readers answered yes under the exact part id, one of them running the changed code with no executor and getting `status='blocked'`, `markdown=''` | 22 → **23 of 142 built** | 1 refusal, 1 owner decision, 1 build run, 2 readings |

| 6 | The machinery was written down for someone else to run, and the writing had to carry rules the code did not hold: launch two readers and never one, never paraphrase the owner's ruling, never repair a stage's output by hand. Eleven hundred words of instruction, most of it asking a person to be careful. Kamen read it and asked why a self-contained machinery needs any of that | only the build step could start its own readers. The two others handed their reading back, so the blind-pair rule lived in prose. Both now take the same reader command and run their own readers, and the instruction shrank to the two commands plus the three things that are genuinely a person's: the reader, a ruling in the owner's words, and restarting it | the ordering step was run against the noticed report with a reader command and nothing else: it started its own readers, collected their answers and returned the finished order — 23 requirements in one round, nobody launching anything. The written instruction went from 1,133 words to 460 | 37 of 142 built, unchanged by this | 1 question from the owner |

## Verdict, entry 6 — a written rule is where a missing gate hides

Path A. The fault was found by a question, not a failure, and the fix removed prose rather than
adding it: the same rule is now kept by the code that writes the packets, which cannot forget. The
distance did not move and was not supposed to — the loop kept building throughout — and nothing was
discarded. The approach can say exactly what remains: 105 items and the 23 noticed ones.

Path B. Six entries, and this is the second time this machinery's own plumbing needed a second
version after the judging was already sound. A machinery that keeps discovering it left a rule in a
person's hands is a machinery being discovered, not known, and every such discovery has come from
outside — a reading of the verdict, a reading of the emitter, now a question from the owner. If the
next one also comes from outside, nothing in the machinery finds its own gaps.

**Verdict: Path A, and Path B names the pattern to watch.** The rule was replaced by the mechanism
that enforces it, which is the only kind of fix that survives being written down. **The deciding
fact:** whether the next gap is found by the machinery's own record rather than by somebody
noticing. The collector exists precisely to do that for the built system; nothing yet does it for
the machinery itself.

## Verdict, entry 5 — the first thing the machinery could not decide, and it still did not decide it

Path A. The refusal was correct and the machinery kept it correct: a builder that rewrites a test to
agree with itself proves nothing, so the block held until a person answered. What was missing was
not judgement but a channel, and the channel carries the owner's words rather than a summary of
them — the step quotes, it does not paraphrase. The builder then found a fourth test the refusal had
missed, which is what a builder given the real question does and a builder given a nudge does not.
The distance moved, and the same path took the next item without a new gate.

Path B. Four edits to this one step in a day, and this one adds a human in the loop to a machinery
whose whole claim is that it runs without one. If items keep needing rulings, the rulings file is
where the real work happens and the machinery is a queue with extra steps. Nothing yet says how
often this will be needed — one item in twenty-three is a number from a single day.

**Verdict: Path A, and Path B names the number to watch.** A ruling is not a fallback: it is the one
thing a machine must not invent, and putting it on disk in the owner's words makes the next run say
what this one said. **The deciding fact:** how many of the remaining 119 items need a ruling. If it
stays near one in twenty, the channel is a rare escape hatch working as intended. If it approaches
one in five, the requirements themselves are in conflict with the built system's tests, and that
conflict — not the build step — is the thing to fix.

## Verdict, entry 4 — the first change is real and the first verdict was not

Path A. The change itself stands on evidence the machinery collected: one file, no test that passed
before failing after, and a builder that stayed inside its one requirement and reported what it
declined to touch. The fault was in counting, not in judging, and it was found by reading the
verdict rather than by a failure downstream — which is the cheapest place to find it. The approach
can state exactly what remains: 141 more items, in an order that already exists.

Path B. This is the fourth step in this machinery and the third whose first version passed
something it should have refused. Every one of those was in the plumbing — how work reaches readers
and how their answers are counted — and a machinery whose gates keep being wrong in the same
direction is a machinery that reports success it has not earned. The cost is not falling: each step
so far has needed a second version before its number could be trusted.

**Verdict: Path A, and Path B names the real risk — the gates fail permissive.** Every one of these
faults would have let something through, never held something back. **The deciding fact:** whether
the next item's verdict survives its own reading without a new gate having to be added. If a third
gate has to be invented for item two, the pattern is the approach, not the instance.

## Verdict, entry 3 — the readers were never the problem; twice now the assembling was

Path A. Two attempts at assembling failed and both failures were cheap, measured, and produced the
correction rather than a knob: the first said similar wording is not a job, the second said an order
is not a grouping. The judging has never failed — it improved on doubling, from 95 per cent on the
first subject to 96 and 98 on this one, with 111 of 112 foundations agreed. The distance moved from
nothing to a real build order over the whole list, and the order is checkable: six rounds, no cycle,
one question for a person.

Path B. This is the third assembler for one step. A step whose output shape keeps changing is a
step whose purpose is not settled, and each attempt has cost a full reading run or a rewrite. If the
next thing built from the order shows the rounds do not matter — that the work could have been done
in any order without failing — then the whole step, readers included, was expensive decoration.

**Verdict: Path A, and Path B has the same deciding fact it had last time.** **The deciding fact:**
build one requirement from a late round and one from the first. If the late one could have been
built first without failing, the order is decoration and the step goes.

## Verdict, entry 2 — the plumbing failed twice and the judging did not fail at all

Path A. The judgement is holding: on the one slice that is settled, two blind readers agreed on
every one of 31 pairs and on all four foundations — better than the 95 per cent of the first
subject. Both faults were in carrying pairs to readers and answers back, not in what a reader is
asked, and each was independent of the other. The approach can state exactly what remains: four
readers, then the assembling.

Path B. It is the second edit to the same file in one sitting, and the second was caused by the
first. A step that needs its own plumbing corrected each time it meets a new size is a step whose
shape is being discovered rather than known, and the cost is rising: one emitter and six reading
runs to reach the same place two reading runs reached on the first subject.

**Verdict: Path A, because the second fault was found by reading rather than by a failed run, and
cost nothing.** **The deciding fact:** what the assembling returns when the four readers land. If
the two passes agree at anything like 95 per cent and the joins are comparable to the first
subject's 17, the instrument survived doubling. If agreement collapses, the wide net at this size is
the thing to change, not the plumbing.

## Verdict, entry 1 — the first prototype failed and the second is the machinery's own pattern

Path A. The failure was cheap, measured before anything was built on it, and it produced the
correction rather than a tuning knob: the replacement asks a different question, not the same
question more carefully. The result is the machinery's established division — code fixes what gets
looked at, a model judges what it means, two readers, agreement or nothing — and it landed at 95 per
cent agreement on its first run, higher than any first run in the requirements ledger.

Path B. Sixty-two of the seventy-six jobs are still a single requirement, so grouping consolidated
92 into 76 and no further. If most of the value was supposed to come from grouping, this is a thin
return for two reading runs, and the honest reading is that the parts were already mostly
independent and the whole step was unnecessary.

**Verdict: Path A, and Path B's number is the one to watch.** Fourteen jobs join work that would
otherwise be attempted in the wrong order, and each of those is a run that would have failed. **The
deciding fact:** whether building one grouped job proves the ordering mattered. If the first
multi-requirement job builds no better than its parts would have separately, grouping is decoration.
