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

| 7 | A Codex worker is one-shot, but the item brief did not carry the owner's already-given edit authority. Two r214 builders therefore spent 4.2 and 3.5 minutes loading the repository agreement, hit the sandboxed `uv` path, asked a question nobody could answer, and delivered nothing. A writable cache removed the first denial but exposed `uv` 0.9.28 panicking in macOS `SCDynamicStore` before pytest collection | add an explicit `--owner-approved` launch flag that relays only the bounded item authority and exclusions; give every worker a cache in its own scratch; set `UV_NO_SYNC=1` so the unchanged prescribed command uses the repository's prepared environment without dependency sync, network, or package mutation | the next builder recognized `envelope=approved` and did not ask again; the exact focused command reached pytest (`1 passed`), the repaired reader ran the prescribed command twice (`6 passed`, then `8 passed`), 52 machinery/client-projection checks passed, each installed client still requires its own runtime and forbids the other, and r214 passed both blind readers plus the final 1,161-test/572-subtest gate | 71 → **72 of 142 built** | 2 non-deliveries (7.7 minutes), one sandbox diagnosis, one missing reader seat restarted without rerunning the completed seat |

| 8 | r214's citation text had moved and appeared three times. The body shortcut correctly refused to guess, while the reader packet spent 15,274 characters listing definitions without naming those three matches, the caller that consumes them, or the transformations after that call. The first structural prototype also admitted 807 version-controlled task snapshots, filling its cap with historical copies | replace the broad definition dump with a bounded map built only from current source: every citation match up to the explicit cap and its enclosing symbol, deduplicated direct consumers, later calls in the same consumer, and direct test callers. Before the builder starts, record hashes of current symbols; blind readers receive the symbols mechanically changed since that before-image, never the builder's explanation or another reader's answer | on the captured r214 input the production helper generated the map in 0.48 seconds and 4,677 characters, named all three current matches inside `strategy_brief_prompt`, reached `_build_strategy_brief_body`, exposed the final `prepend_reading_legend` and validation calls, and listed 23 direct test callers. Seventeen focused machinery tests pass, including ambiguous matches, changed/added symbol detection, cap disclosure, blind-reader privacy, and exclusion of task snapshots | **72 of 142 built**, unchanged by machinery optimization | 1 rejected structural prototype; 807 historical copies excluded; no reader, test, or acceptance gate removed |
| 9 | Three acceptance checks recorded evidence without making it decisive: a non-pytest command could exit non-zero with no parsed `FAILED` line, reader citations only had to be present, and a previously collected test could disappear without blocking `built:true` | make the final command exit code a hard gate; resolve every yes citation to an in-repository file, existing line, and exact line text; block every disappeared test unless `rulings.json` authorizes that exact collected identity in the owner's words and records replacement or remaining coverage | eight captured refusal/approval cases exercise the production `drive()` verdict: one exit-7 command with no parsed failure, three citation failures (repository escape, missing line, mismatched text), and four disappeared-test cases (missing, wrong identity, missing coverage, exact approval). The full focused file passes 27 tests | **72 of 142 built**, unchanged; `built:true` is now stronger | 3 permissive gate classes found, 3 fixed; no semantic reader rule weakened |
| 10 | The bounded path map was opt-in for readers, each reader still had to turn it into a command, and stable worker rules plus repository facts were mixed into the item prose | make the producer-to-consumer manifest automatic for builder and both blind readers; derive a runnable focused-test command from direct callers; pre-chunk stable directives, repository context, and item task | focused production-path tests prove the before-image is captured by default, both blind packets contain the independent manifest and runnable command without the builder conclusion, the command uses the repository test entry point, and packet sections carry the prepared root/test/output/scratch facts. Twenty-seven focused tests pass. No live reader-duration reduction is claimed yet | **72 of 142 built**, unchanged by speed work | 3 packet/navigation gaps found, 3 fixed; live time saving remains unproved |
| 11 | A direct CLI proof imported `client_model_policy.py`, wrote `__pycache__` into the canonical managed skill tree, and made both client projection checks refuse the release it was trying to prove | the Implementation CLI disables bytecode writes before importing its local policy module, so its own normal entry point cannot mutate the canonical tree | the focused subprocess contract forces bytecode writing on before launching a staged copy, verifies the CLI turns it off before the local import, and leaves no cache. The original canonical cache was removed before projection regeneration | **72 of 142 built**, unchanged; release proof no longer changes its subject | 1 CLI import boundary found, 1 fixed |
| 12 | The declared three-attempt refusal brake existed only in the returned verdict. The receipt was written before the terminal handoff was added, and the unattended loop continued every `built:false` result; live r67 therefore opened attempt 7 after six valid refusals | write the terminal handoff into the third refusal receipt, return that receipt before any fourth builder or test run, and make the unattended loop stop on it; empty worker deliveries still create no refusal and relaunch the same attempt | four captured controller-path checks were red before the change and green after it: terminal persistence, no fourth builder, unattended stop, and empty-delivery retry. The full focused file passes 32 tests | **72 of 142 built**, unchanged; the next batch is bounded by the declared refusal limit | 6 substantive refused rounds and 1 attempt-7 launch exposed the missing brake |
| 13 | The new brake stopped before reading a later owner ruling, so live r194 remained terminal even after the owner settled the requirement. Its pending builder and reader outputs also predated and contradicted that ruling, while blind readers never received the ruling at all | bind attempts to the exact semantic ruling hash; require explicit `resume_after_terminal` after a terminal refusal; preserve stale active outputs and the stale test baseline in a ruling-history directory; give the exact semantic ruling to the builder and both blind readers; keep test-removal approvals out of reader context; persist terminal handoffs for both reader refusals and builders that changed nothing | the captured 64 MB r194 work state, copied without product execution, preserved four refusals and every stale active artifact, opened refusal number 5 as attempt 1 under the exact ruling, refreshed the baseline, and returned a builder packet quoting the ruling. Thirty-seven focused controller tests pass, including one-window-only, reader propagation, test-removal isolation, baseline refresh, and both terminal receipt paths | **85 of 142 built**, unchanged by the machinery repair; r194 can now consume the owner decision without erasing history or carrying a stale regression allowance | 1 real controller reproduction, 1 bounded implementation prototype, 3 review/live-monitoring edge fixes |
| 14 | Six r210 Codex builders exited without delivering. The watcher was the sole stdout reader, understood only Claude tool events, discarded every unknown Codex line, then wrote the already-drained remainder to the log. Controller restarts also reused launch names and overwrote earlier failures | drain stdout and stderr once and concurrently; preserve every raw line before adapting events; understand Codex item and terminal-failure events; include delivery identity and pid in each launch log name; repeat the terminal reason in the feed and launch result | a fake Codex subprocess emitted a command event, a capacity failure, stderr, and exit 1 twice. Both collision-proof logs retained every raw event and stderr line, the feed named the command and failure, neither delivery consumed an attempt, and all 39 focused controller tests passed | **86 of 142 built**, unchanged; the next real r210 launch can reveal its actual failure instead of destroying it | 6 opaque non-deliveries, 1 source-to-log trace, 1 focused subprocess proof |
| 15 | r56's builder replaced the controller's clean pre-change test receipt with its own summary-only JSON. The existing packet already said to write intermediates only in scratch, so the instruction was hand-waved; on the next controller pass `failed` was absent and the run crashed before either reader launched. The first protected restart then rejected an authentic r108 receipt because 85 historical completions predated the new receipt fields | move authoritative test and acceptance records outside the repository worker's writable area; treat item-side JSON as a projection; preserve and replace any worker-written projection; ignore forged completion; allow clean-baseline recovery only from the pre-launch feed, the neutral pre-builder test-symbol snapshot, and a fresh clean full-suite result; migrate pre-protection receipts once only when the prescribed before/after failures match and both reader seats answer every ordered part yes | the captured overwrite is reproduced in the focused controller test: it previously raises `KeyError`, now preserves the foreign JSON, restores the trusted baseline, and reaches checking. A forged `built:true` is removed rather than selected. Recovery accepts a zero-failure/no-disappeared-test case and refuses a disappeared pre-existing test. Legacy migration accepts the captured release shape with unchanged pre-existing failures and rejects a new failure or missing reader proof | **87 of 142 built**, unchanged; r56 can be recovered without trusting the worker's receipt, and accepted older work is not silently discarded | 2 live controller stops, 1 red reproduction, 2 retained prototypes plus one live-path refinement |
| 16 | Three of the next nine items were already green and both blind readers called every part true, but each then lost a full second round because its builder had renamed one pre-existing test and the identity gate ran only after the readers. Those rounds cost 23 minutes 55 seconds | project the exact protected identities to the builder, collect them again immediately after delivery, and refuse every unauthorized disappearance before launching either reader; carry every missing identity into the correction request while retaining the unchanged final disappearance gate | the captured rename path is red before and green after through production `drive()`: no reader directory is created, the exact missing identity reaches the next builder instruction, unchanged identities still launch both readers, and an exact owner-authorized removal still reaches `built:true` | **96 of 142 built**, unchanged by machinery optimization; affected items no longer spend a reader round on a mechanical refusal | 3 wasted reader pairs in 9 items; 1 production-path prototype, 4 boundary proofs |
| 17 | Two r158 builders independently said the requirement was already true, but each no-change refusal was written only to the inspectable item directory. The protected-state reader correctly rejected that untrusted file, deleted it, and relaunched attempt one, so the three-attempt brake could never fire | write controller-created no-change refusals through the same protected record boundary as semantic refusals, tests, and completion receipts; keep worker-authored refusal files untrusted | a successive-delivery reproduction runs production `drive()` after protection is active: red before because refusal one vanished; green after with protected attempts one, two, and three, the third returning the owner handoff and no fourth job. The forged-worker-refusal check remains green, and all 53 focused controller tests pass | **111 of 142 built**, unchanged; r158 can now reach the bounded owner handoff instead of permanently holding the remaining 31 items | 2 live no-change rounds; 1 captured production-path prototype; 1 controller-record call corrected |
| 18 | The ordering producer described each 55-record reader job as `pairs: 55`, while the shared launcher accepted only `expect` and defaulted to one. It killed the two live readers after 2 and 10 records, then the integrated ordering path relaunched them every twenty seconds with no total launch bound | make the ordering job contract carry `expect`, `wants`, and the already-delivered count; route both standalone and integrated ordering through one controller that permits at most three incomplete launch rounds and preserves every partial answer | the captured production handoff was red before and green after: a slow reader wrote one record, stayed alive, then completed all 55 without being terminated; a zero-delivery reader stopped after exactly three launches. All 55 focused controller tests pass | **111 of 142 built**, unchanged; the 55-pair ordering can now finish once instead of consuming readers in a relaunch loop | 2 readers killed mid-answer; 18 recorded relaunches in under 5 minutes; 2 controller gaps found, 2 fixed |

| 19 | The record of which files an item changed was the builder's own sentence about itself, compared with nothing. Across two finished batches the builders named 37 files where 44 had to move, then 21 where 43 had to move; a clean copy of the repository carrying only the named files failed 67 tests. The same list is what both blind readers are told changed, so every short list also narrowed the evidence they judged against. Both were found from outside — by cloning the repository and watching the suite fail — never by the machinery | ask version control instead of the worker: record what is uncommitted before the baseline test run, again before the builder starts, and once more the moment the delivery is seen; subtract what the baseline run alone writes, so the suite's own artifacts are not counted; keep the union of what moved and what was claimed, so nothing shown to a reader can be lost; record the claim and the difference beside it and say so in the feed | red before and green after through the production `drive()` on a real repository: a builder that moved two files and declared one previously produced `['src/target.py']` and now produces `['src/gate.py', 'src/target.py']`, with `changed_without_saying_so` naming the undeclared file and both blind readers handed it. A built system with no version control falls back to the claim and records `repository_watched: false`. Test artifacts written under a fresh name every run are excluded by watching the baseline run, and are included again when that watching is removed. All 58 focused controller tests pass | **111 of 142 built** on the ledger's subject, unchanged by this; on the second subject the batch finished 42 of 42 | 2 finished batches published on a hand-verified manifest; 1 red-before reproduction; 3 proofs |

| 20 | Entry 19's watching settled once per **item**. On its first live batch, r100's second builder wrote forty-eight lines into the engine's dispatch seam, declared no files, and the step reused the first attempt's "nothing moved": the item was refused for changing nothing while its change sat in the working tree, and the run was heading for a terminal refusal with real work unrecorded. The same hole existed across a ruling window, where attempt numbering restarts and an old window's observation would be read as the new attempt's | settle the observation per attempt, keeping the item's first before-image so an accepted attempt still names everything that moved since the item was taken up, including work an earlier refused attempt left behind; carry stale observations into the ruling-history directory with the rest of the preserved work | red before and green after through the production `drive()` on a real repository, reproducing r100 exactly: an attempt that declares nothing and moves nothing is refused, then a second attempt that moves a file and still declares nothing returns `checking the change` with that file named — the old code returns `building again`. All 59 focused controller tests pass | **0 of 68 parts built** on the pre-engagement subject; the batch was stopped at the owner's word and restarted on the fixed machine | 1 live batch stopped at item one; 2 refused attempts, one of them wrongly |

| 21 | Entry 20 carried the stale observations into the ruling-history directory — but only the copies in the item directory, and the controller reads the protected record, never the projection. r19's reopened window therefore read the first window's attempt-1 observation, written four hours earlier, and told both blind readers that two files had changed which that attempt never touched, while omitting the four it did. Its second attempt read the old window's second, naming files from a different builder entirely. The file baseline stayed at the refused window's too, so the first honest re-observation measured against a picture of the repository four and a half hours old and named 234 files, most of them written by the demo's own runs in between | retire the protected record beside its projection every time the epoch preserves one, listing what was retired in the history manifest; rotate the file baseline with the test baseline, so a refreshed window measures the change from its own start | red before and green after on the production `_activate_ruling_epoch`: with the retirement disabled the new window reads the old window's observation, and with it in place the controller reads nothing and settles the attempt for itself, the retired records kept under `ruling-history-2`. Live on the restarted run: the controller removed the untrusted projection, re-observed r19's second attempt itself and said in the feed *the builder's file list was short — said 5, moved 234*, where the stale record had said 2. All 61 focused controller tests pass | **5 of 34 built** on the pre-engagement subject, unchanged by this | 2 windows of attempts judged on another window's list; 1 live restart at the owner's word; 2 found, 2 fixed |

| 22 | The snapshot recorded each uncommitted file by size and modification time, and a modification time is not a change. The built system's own test command runs its packaging step, which stamps one fresh timestamp onto every source file it manages without rewriting a byte. On r91's second attempt the record therefore read **103 files moved where the builder had touched two** — 37 of them source and test files whose sizes were identical to the baseline's and whose clocks had all turned to the same instant, plus 34 folders from earlier demo runs. Both blind readers were handed that list | record what each file says beside its size — a content digest taken when the snapshot is taken — and compare on size and content, leaving the clock out of it; older two-part records keep their old meaning | red before and green after on the production `_repository_state` and `_moved`: a file whose modification time is pushed a second into the future is no longer reported as moved, and the same file rewritten still is. All 64 focused controller tests pass | **15 of 34 built** on the pre-engagement subject, unchanged by this | 1 live item read with a hundredfold file list; 1 record traced to identical sizes and one shared timestamp; 1 found, 1 fixed |

## Verdict, entry 22 — four causes, four instruments, and the distance is moving

Path A. The boundary has held through all four: the record still asks version control rather than
the worker, and no fix has re-opened an earlier one. Each cause was a different instrument — where
the answer is stored, how long it may stand, which copy is authority, and what counts as a change —
and this one was found by reading the live record rather than by an item accepted on a wrong list.
The distance is moving underneath it: 6 of 34 when the owner's scope went in, 15 now, nine straight
items with one builder round each and no verdict resting on a document outside the subject.

Path B. Four repairs to one record in two days is a record whose instrument is being discovered by
outage. The controller reconstructs, from outside, a fact the built system could report from
inside; every new thing that touches a file — a packaging step today, a formatter or a cache
tomorrow — is another cause waiting. The replacement is to stop reconstructing it: ask the built
system for its own diff at the moment of delivery and record that, which no timestamp, no cache and
no run folder can confuse.

**Verdict: Path A, because the goal's number moved nine items while these four were being fixed,
and none of the four cost an accepted item.** **The deciding fact:** whether a fifth instrument
appears in this batch's remaining nineteen items. If the record now names what moved without anyone
reading it by hand, the boundary is finished. If a fifth appears, Path B is right and the record
becomes the built system's own diff rather than the controller's reconstruction.

## Verdict, entry 21 — the same boundary, one layer further down

Path A. The boundary entries 19 and 20 drew is holding: the record is still taken from version
control rather than from the worker, and it is still settled per attempt. What failed here is not
that boundary but a rotation that stopped at the projection, and it was found by reading the live
feed against the protected directory rather than by an accepted item — before any verdict rested on
it. The distance did not move, and no reader verdict has to be withdrawn: the file list is
navigation, and r19's refusal quoted the current run's own deliverable, correctly.

Path B. This is the third fix to the change-observation in two days, and each was exposed by the
next live run rather than by the one before it. A record that needs a repair every time it meets a
new lifetime — item, attempt, ruling window — is a record whose lifetimes are being discovered one
outage at a time, and the cost is now measured in restarts of a batch that stands at 5 of 34.

**Verdict: Path A, because each of the three found a distinct lifetime and none re-opened an
earlier one, and this one cost no accepted item.** **The deciding fact:** whether the next
observation the machinery settles is right without a person reading it. If r19's remaining attempts
and the items after them record what moved without anyone checking the protected directory by hand,
the boundary is done. If a fourth lifetime appears, the record is the wrong shape and what replaces
it is a change the built repository itself reports, not one the controller reconstructs.

## Verdict, entry 20 — the fix was right and its lifetime was wrong

Path A. Entry 19's boundary is correct and this changed none of it: the record still asks version
control rather than the worker, and the union rule still refuses to narrow what the readers see.
What was wrong was how long one answer was allowed to stand — an item-lifetime cache over a
per-attempt fact. The defect was found by the machinery's own feed on the first batch that
exercised it, which is exactly the deciding fact entry 19 named, and it was found before a single
item was accepted on a wrong list.

Path B. This is a fix to a fix, one day apart, in the same few lines. A step whose caching lifetime
had to be discovered by a live refusal is a step that was not thought through on the paths its own
loop takes — the retry path existed before entry 19 was written, and the observation was fitted to
the happy one.

**Verdict: Path A, and Path B names the cost.** The evidence is that the second version was
demanded by the machinery's record rather than by a person cloning the repository, which is what
entry 19 asked for. **The deciding fact:** whether the restarted batch's next short list appears
in the feed as it happens, with the accepted item's record naming every file that moved.

## Verdict, entry 19 — the last unobserved worker claim, found from outside again

Path A. The judging has never been what failed. Both batches reached every item — 35 of 35, then
42 of 42 — and the two readers agreed throughout. What failed is one field whose source was a
worker's sentence, in a machinery that had already replaced exactly this kind of claim twice
before: test identities are collected either side of a build, and changed symbols are read from a
before-image. The same fix in the same shape closes the last one. It discards nothing and it
widens what the readers see rather than narrowing it.

Path B. Entries 4a, 15, 17, 18 and this one are one shape: a gate that fails permissive, found
from outside the machinery. Entry 6 named the deciding fact — whether the next gap would be found
by the machinery's own record — and this one was not: it was found by cloning the repository and
running the suite by hand. A machinery whose record can only be trusted when somebody checks it
against reality is not yet a record.

**Verdict: Path A, and Path B's fact is now the one to watch.** The class was swept: of the four
things a builder says about itself, its test changes were already observed, its prose is
explicitly a claim, and the file list was the only fact taken on trust — 1 found, 1 fixed. **The
deciding fact:** whether the next batch's discrepancy appears in the feed as it happens, rather
than in a hand-built manifest afterwards. If the next run publishes on the machinery's own list
without a person rebuilding it, the record has become one.

## Verdict, entry 18 — the ordering contract failed, not independent judgement

Path A. The live readers were doing the requested work and explicitly said they would finish all
55 records. The controller ended them because its producer and consumer used different names for
the same mechanical count. The same machinery had already advanced 111 of 142 build items, so the
ordering method can state what remains and has moved the goal. Fixing the handoff and bounding its
retry loop preserves every judgement and acceptance gate.

Path B. The approach would be wrong if readers given the corrected complete-slice contract still
looped or if their completed records produced an invalid order. That would show the ordering
instrument itself cannot converge, rather than its launcher ending valid work early.

**Verdict: Path A.** The production-path prototype makes one reader complete all 55 records and
the no-progress path stops after three launches. **The deciding fact:** the resumed live ordering
must either produce both complete 55-record passes and a valid order, or expose a new exact failure
without relaunching indefinitely.

## Verdict, entry 8 — remove navigation repetition without sharing judgement

The direct r214 proof also repeated an operator error from the preceding optimization: importing
the skill with the system Python wrote two bytecode files into the canonical skill tree. The
installer correctly refused generated artifacts; removing them then made the manifest that had
hashed them correctly refuse as stale. Direct probes of a managed skill must therefore set
`PYTHONDONTWRITEBYTECODE=1` before import, and projection generation must run only from the clean,
validated tree. This changes no worker path; it prevents proof tooling from changing what it proves.

Path A. The map performs only work whose answer is mechanical: where quoted text occurs now, which
definition encloses it, which functions call that definition, what is called later in the same
consumer, and which symbols differ from a before-image. It starts both readers sooner while leaving
them blind, free to read elsewhere, and subject to the same independent verdict and regression gate.

Path B. A semantic shortlist would be faster still, but it would make the machinery decide which
path matters and hand the same conclusion to builder and readers. That trades away the independence
that caught earlier universal-path failures and is not an optimization of this machinery.

**Verdict: Path A.** The generated r214 packet proves the right evidence is present and bounded;
it does not yet prove the expected three-to-five-minute live saving. **The next deciding fact:**
the next item must preserve two independent complete readings while reducing time from worker start
to the first relevant source or focused test compared with r214's recorded navigation intervals.

## Verdict, entry 7 — authority and execution environment belong at the launcher boundary

Path A. The workers were not refusing the requirement; they were correctly obeying a repository
contract that the machinery had failed to satisfy. Relaying the owner's existing bounded approval
removed no gate, and `UV_NO_SYNC=1` changed no test command or product environment: it prevented a
sandboxed reader from trying to synchronize dependencies the repository had already prepared.
The same item then crossed the real builder, two-reader, and regression path.

Path B. The successful builder still spent fifteen minutes, and the source-path reads remain the
largest repeatable cost after the launcher faults are removed. Preloading more code can save time
only when the citation resolves unambiguously; otherwise it risks steering all three readers to the
same incomplete boundary.

**Verdict: Path A.** The repair is mechanical and client-safe. **The next deciding fact:** whether
the next item reaches its first focused test without authority or `uv` remediation, while blind
readers still find any materially different path the builder missed.

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
