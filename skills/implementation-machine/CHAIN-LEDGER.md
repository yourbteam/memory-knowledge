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
