---
name: requirements-machinery
description: Read one source document under a coverage guarantee. Cuts it into pieces, keeps a register of them, and refuses to produce any result while one piece is unanswered — so "we went through all of it" is a number the owner counts, not a claim the model makes. Every answer carries words verbatim from its own piece, checked by code. Two blind readers say which pieces bear on the document being built, and a piece they disagree on goes to the owner rather than being decided. Use when a requirement list, a field list, or any claim of completeness is being taken out of a document.
---

# Requirements machinery

One thing is true of everything this produces: **nothing comes out while any part of the source is
unread.** Not a warning beside the answer — no answer.

That exists because of a real failure. A client document was built to carry six fields; the source
names nine. Every check passed, the wrong number shipped, and nothing anywhere could say that three
were missing. The register is what makes that impossible to repeat quietly.

## The front door

**The work directory lives in the repository, never in a temp root.** A run's state is the paid
record of every reader call it made; the Step 3 build nearly lost 281 calls' worth to a scratchpad
flush. Use `Tasks/<task>/runs/<run-name>` — `cover.py` refuses a `--work` under `/tmp`,
`/private/tmp`, `/var/folders` or `$TMPDIR` before spending a reader (owner's standing rule,
2026-08-24).

The guard resolves symlinks and accepts only a nested path under the nearest `.git` directory or
worktree `.git` file. Exact temporary roots, their descendants, a repository root itself, ordinary
non-repository paths, files, and symlink escapes all fail before state or readers are touched;
nonexistent nested children are allowed because the machinery creates them durably inside the repo.

`open` creates one immutable run identity: an absolute source path and hash plus the exact piece
manifest. It never replaces existing state or a pieces directory. Every later command revalidates
the source bytes, registered piece hashes and character counts, and the exact piece filename set
before use; missing, changed, extra, symlinked, or non-UTF-8 artifacts fail with distinct drift
diagnostics. Recovery is a new nested work directory, never implicit cleanup.

`open` accepts PDF through the existing `pdftotext -layout` path and reads `.md` directly as strict
UTF-8. It refuses every other source suffix before creating state or piece artifacts. Markdown with
form feeds keeps those page boundaries unchanged. Without form feeds, a structured corpus whose
records use framed, sourced, consecutively numbered `ARTIFACT` provenance headers becomes one
piece per whole record; the preamble stays with the first record. Any declared `ARTIFACT` line that
does not satisfy that complete structure is refused before state exists. Ordinary Markdown without
form feeds or artifact declarations remains one piece.

```bash
python3 scripts/cover.py open   --source <document> --work <dir>
python3 scripts/cover.py status --work <dir>
python3 scripts/cover.py answer --work <dir> --piece p-0007 --by "reader-1" \
                                --quote "<words from the piece>" --what "..."
python3 scripts/cover.py relevance --work <dir> --target "<the document being built>" \
                                   --reader-command '<command>'
python3 scripts/cover.py bearing --work <dir>
python3 scripts/cover.py obligations --work <dir> --reader-command '<command>'
python3 scripts/cover.py obligation-list --work <dir>
python3 scripts/cover.py collapse --work <dir> --reader-command '<command>'
python3 scripts/cover.py requirements --work <dir> --reader-command '<command>'
python3 scripts/cover.py distill --work <dir> --reader-command '<command>'
python3 scripts/cover.py ask-owner --work <dir>
python3 scripts/cover.py answer-owner --work <dir> --id <decision-id> \
                                      --choice <offered-choice> --because "<owner's words>"
python3 scripts/cover.py correct-owner --work <dir> --id <recorded-decision-id> \
                                       --choice <offered-non-split-choice> \
                                       --because "<owner's corrected words>"
python3 scripts/cover.py replay-owner-split --work <dir> --id <decision-id> \
                                           --reader-command '<command>'
python3 scripts/cover.py run --work <dir> --target "<the document being built>" \
                             --out <requirements.md> --reader-command '<command>'
python3 scripts/cover.py document --work <dir> --out <requirements.md>
python3 scripts/cover.py report  --work <dir>
```

Use `run` as the normal continuation entrypoint. It derives the next incomplete stage from the
persisted coverage state, grounds every unanswered piece before relevance, advances every later
automatic stage, and exits only after presenting one owner ruling or writing the finished document.
Each grounded coverage answer is persisted immediately, so interruption resumes at the first
unanswered piece. Re-run the same command after each owner answer; completed reader work is reused
and no separate stage command is required.

`open` cuts the document and writes every piece to `<dir>/pieces/`. `report` refuses, naming what is
still unanswered, until nothing is. State lives in `<dir>`, so stopping and coming back later is the
same as never having stopped.

Manual answers and reader quotations share one grounding rule: after whitespace is collapsed, the
quote must occur verbatim in its piece and carry at least 25 characters. If the entire normalized
piece is shorter than 25 characters, quoting that whole piece is sufficient. Empty, whitespace-only,
short fragments from a longer piece, and nonmatching text are refused without changing the answer.

Every reader subprocess has a declared per-call execution bound: 180 seconds by default, or the
positive value (at most 3600 seconds) in `REQ_MACHINERY_READER_TIMEOUT_SECONDS`. A timeout or any
nonzero process exit stops the stage with exit code 4 before stdout can be interpreted or persisted
as a semantic answer. The private feed records `timeout`, `nonzero-exit`, `malformed-reply`, and
`valid-reply` as distinct outcomes; only a zero-exit reply reaches semantic validation.

Commands validate a supplied `--reader-command` at CLI entry, before reading resumed state or
deciding that cached results eliminate reader calls. The validated command identity carries its
exact spawn arguments downstream, so cold, resumed, and zero-call paths enforce one client policy.

The requirements stage persists a replayable checkability decision record before final assembly:
all three raw replies, each parsed selection and per-line validation, aggregate votes and final
dispositions, plus hashes binding the target, prompt, and numbered item set. Resume verifies the
record and spends no reader; any evidence or derived-field drift fails closed.

An owner-driven `split` gives every entered child the same record boundary. Because its YES/NO
asks may retry, the child record keeps every full raw attempt, its accepted or malformed parse,
the three-seat aggregate, and the same target, prompt, item, and record hashes. The ruling also
stores one integrity-bound split graph: the exact parent index and links, the exact child indexes,
and each child's statement and checkability-record hashes. A malformed seat is owner-visible doubt
rather than an implied NO. Every resumed command replays all split-child records and reconciles
the graph before it can spend a reader; a missing graph, unlinked parent or child, missing legacy
record, altered evidence, or derived-flag drift refuses with the affected ruling or child named.
A split never records while any non-redundant candidate duty is unconfirmed. A label-bearing
candidate is redundant only when the code-generated label-free subcandidate is confirmed; no
reader may silently classify another source duty as redundant. A new partial split leaves the
parent and owner queue unchanged. Replaying a terminal legacy partial split removes only that
ruling and its children, reopens the parent as pending, and preserves every unrelated item and
ruling.
Replay validates the exact persisted JSON shape before rebuilding it, so nulls, scalars, lists,
missing seats, malformed aggregates, and wrong field types become named controlled refusals rather
than internal exceptions.

Before accepting a pen rewrite, the lexical provenance gate is followed by a semantic-fidelity
gate. Punctuation-only or directly composed anchor wording passes deterministically. Any other
rewrite is accepted only when two blind readers both confirm that actor, action, object, polarity,
direction, causality, permission, obligation, and scope remain faithful to the verbatim anchors.
One changed or malformed verdict refuses the rewrite with an actionable reason.

`replay-owner-split` is the governed repair path for an already-recorded split. It accepts only the
newest integrity-bound split whose children form the terminal item suffix, rebuilds that one split
from the owner's recorded words, and leaves every unrelated item and ruling untouched. It is not a
general rollback and never starts a new requirements run.

`correct-owner` is the governed correction path for one recorded non-split owner ruling. It accepts
only a decision id already present in the active target's ruling map and one of that item's
originally offered non-split choices. Every guard runs before the single state write; the complete
prior ruling is appended to `history`, and every unrelated state value remains unchanged. A recorded
split is refused with `replay-owner-split` named as the required graph-and-children repair path.

## Public command surface

The entry point has seventeen public commands. The table is both the human contract and the input to
`scripts/contract_surface.py`; publication fails if its inventory differs from `cover.py`.

<!-- BEGIN PUBLIC COMMAND SURFACE -->
| command | category | boundary |
| --- | --- | --- |
| `open` | coverage | Registers one source and its complete piece manifest. |
| `status` | coverage | Shows coverage progress without disclosing answer bodies. |
| `answer` | coverage | Records one manually grounded piece answer. |
| `report` | coverage | Emits the complete coverage register only after every piece is answered. |
| `relevance` | extraction | Judges every covered piece against the active target. |
| `bearing` | extraction | Emits only the completed relevance account. |
| `obligations` | extraction | Extracts source-grounded obligations from admitted or unsettled pieces. |
| `obligation-list` | extraction | Emits the obligation account and names unresolved coverage. |
| `collapse` | extraction | Groups source obligations while preserving disputed pairs. |
| `requirements` | extraction | Derives candidate requirement rules from the collapsed source record. |
| `distill` | extraction | Produces the checkable requirement candidates presented for final decisions. |
| `ask-owner` | owner decision | Presents only decisions the machinery is not allowed to cast. |
| `answer-owner` | owner decision | Persists one offered choice in the owner's own words. |
| `correct-owner` | owner decision | Corrects one recorded non-split ruling while preserving its complete prior ruling in history. |
| `replay-owner-split` | owner decision | Rebuilds only the newest integrity-bound owner split while preserving every unrelated ruling and item. |
| `run` | document assembly | Derives and advances every automatic stage, stopping only for one owner ruling or the completed document. |
| `document` | document assembly | Applies completed owner rulings and writes the requirements document. |
<!-- END PUBLIC COMMAND SURFACE -->

Source coverage ends with a complete `report`. `relevance` through `obligation-list` interpret that
covered source; `collapse` through `distill` derive a requirements set from it. Those derived stages
do not acquire owner authority: every undecidable inclusion, merge, or casting choice remains in
`ask-owner`/`answer-owner`. `document` independently invokes the coverage report gate before it
consults that queue, so neither a direct call nor the autonomous controller can write an output
over unanswered pieces. Only after coverage is complete and the owner queue is empty may it
assemble the result.

**Public-output disclosure boundary.** While manual coverage is incomplete, public commands reveal
which pieces are answered and by whom, but never the stored `what` or grounding `quote`. `report`
refuses. Once every piece is answered, `report` emits the complete answer register.

**Private-state boundary.** `coverage.json`, the pieces, raw reader logs, and every other file under
`--work` are private operator state. `answer` persists `what` and `quote` immediately so the run can
resume. Anyone who can read that directory can therefore read them before completion. The public
refusal is not a filesystem-confidentiality guarantee: keep the repository and run directory
restricted to the operators allowed to see the source and intermediate answers.

`relevance` asks, of every piece the register holds, whether it bears on the document being built.
Two readers who cannot see each other answer, and a yes must come with the piece's own words, checked
against that piece. Five outcomes are kept apart, because collapsing any two of them hides something
the owner needs: **bears**, **does-not-bear**, **for-the-owner** (the two readers differed — the piece
is neither in nor out, and this machinery will not cast the deciding vote), **no-answer** (a reply
that never became one of the permitted values is not a verdict), and **yes-without-words** (the
reader may be right and merely unable to show it, which is not the same as being wrong).

A `no-answer` verdict never disappears. Obligation extraction reads that piece as unresolved,
collapse carries it even when it yields no lines, and the owner queue names the failed-answer
reason and offers only `admit` or `dismiss`. Document assembly remains blocked until that ruling;
the recorded choice and the exact piece identity remain in final provenance.

Obligation extraction records completion separately from its collection. An all-negative pass
therefore persists `complete: true` with an empty store and may advance to a zero-requirement
result; absent or partly processed state still refuses. An all-`no-answer` or mixed pass is also
complete as extraction, while its unresolved piece identities continue to block final assembly.

Every first-deduplication owner pair becomes a stable content-addressed owner item carrying both
complete statements, their piece identities, and the recorded reader evidence. It survives restart
and blocks assembly. `merge` emits one requirement with combined provenance; `keep-separate` emits
both, and either ruling is recorded in the document.

When a merged pair yields no verbatim shared rule, neither original is consumed. One stable
`shared-rule` owner item retains both source statements, piece identities, and every failed
extraction attempt. Finalization blocks until the owner chooses `keep-both`, `select-a`, or
`select-b`; every choice materializes a nonempty, source-traceable result.

Owner rulings compose as one decision set, not as independent instructions with hidden precedence.
If a later overlap or shared-rule selection would restore a source duty an earlier checkability
ruling dropped, that later selection reopens through the same owner interview with its prior answer
in history. Its correction offers each non-dropped side and `drop-both`; unrelated rulings remain
recorded. Finalization then materializes an identical selected duty once, combining its pages,
anchors, and owner notes, while distinct selected wording remains separate.

Checkability is always target-bound. The exact active target appears in the prompt and its
persisted replay record; target, prompt, and item hashes jointly define the decision identity.
Changing only the target therefore creates a different decision record, and Step 3 Measurement
Brief wording appears only when that is the run's actual target.

Document assembly treats an absent owner-ruling map as exactly the empty set only when the derived
owner queue is empty. A genuinely pending item still refuses. Thus a dispute-free run and the same
run with an explicitly stored empty map produce byte-identical documents.

It runs over the register's pieces, never over the document, so it cannot quietly judge a subset.
State is written after every piece, so a long run resumes where it stopped. Complete input receipts bind each
reader's batches to the exact source and target. Both relevance readers receive every complete
sentence batch; obligation batches preserve whole units and their global numbers, including long
units. No prefix is substituted for the complete piece. Missing answers remain incomplete.
Saved answers from before these receipts, or from changed inputs, cannot certify a new result:
open the source in a fresh work directory and rerun extraction. Existing runs and owner rulings
remain available for inspection.

`bearing` is how that answer comes out, and it obeys the same rule as everything else here: it
refuses while any piece is unjudged, naming how many and which. The verdicts printed during a run
are progress, not a result — without the gate, a run stopped halfway leaves a half-finished set that
reads exactly like a finished one.

`obligations` then takes, from each piece that bears, every line stating something the target must
contain, must say, or must be checked against. Code cuts the piece into numbered lines and the model
only says which of them are obligations, so the candidate set is never the model's to choose. Every
line kept is checked verbatim against the piece it came from.

Duplicate comparisons run at most four independent pairs concurrently. Votes within a pair stay
sequential and stop early only when disagreement or an unanswered vote makes the owner's decision
unavoidable. Exact-input checkpoints preserve each completed vote, so interrupted comparisons
resume without paying for those votes again. Source wording, target, reader command, and comparison
policy changes select different checkpoints. All unanimous merge/apart rules remain the same.

`obligation-list` hands that back, under the same rule again: it refuses while relevance is
unfinished, and while any admitted piece has not been read. When a piece is neither in nor out — the
two readers split, or a yes could not produce the page's own words — the list still comes out, but
it names those pieces, because a list that can still grow must not read as final.

**Naming the target matters more than it looks.** The library contains a Step 3 *final brief* beside
the Step 3 *Measurement Brief*, listed as separate deliverables of the same step. Asked about "the
Step 3 Measurement Brief", readers admitted a page that never mentions it, and gave a different
answer each time they were asked. Named as the library names it — the Measurement Brief of Step 3,
explicitly not the final brief and not the intake brief — the same page came back empty five times
out of five. If a run is unstable, look first at whether the target has a sibling.

## What decided its shape

Every empirical design assertion in this repository-owned source has an explicit disposition in
`evidence/empirical-claims.json`. Run `python3 scripts/empirical_claims.py validate --skill-root .`
before treating one as evidence. A `verified` disposition must replay from hash-bound frozen input,
raw outputs, criteria, scores, environment identity, and an explicitly non-automatic promotion
decision. An `unverified` disposition is not evidence: it records that the historical raw ledger is
absent instead of reconstructing or fabricating it. Source or evidence drift fails closed.

Nothing here was chosen by argument. Both parts were settled by running competing versions against
the real 104-page library under criteria fixed before the runs:

- **How the document is cut** — by page, at headings, or by block. Page won on both declared
  measures at once: it keeps 94.7% of the text surrounding each obligation with that obligation, and
  produces the fewest pieces. Cutting at headings loses 11% of that context and leaves 79 fragments
  too small to say anything about.
- **How the refusal works** — refusing only when a result is requested, or refusing every route into
  the register. The lenient one leaked three ways out of four: ask it about one piece, ask what it
  has, or ask it to write itself out, and it answered while the page you needed sat unread.

- **How relevance is asked** — plainly, or with the piece's own words required behind every yes.
  The two returned the *same verdicts*: same five yeses on the library, same refusals, and the
  disagreement each produced was the same page. What separated them is what they can hand over. On
  the library, five agreed yeses carried words in one and none in the other; on a second document,
  two against none. Requiring the words costs nothing in accuracy and is the whole difference between
  a page number and a sentence somebody can act on.

**One thing grounding does not do, proven rather than assumed.** It shows a claim is made of the
page's own words. It does not show the page is *about* the target. Pointed at a different agency
workflow, two blind readers both quoted its "Step 3.4 — Measurement framework" verbatim and both
admitted it — the two strongest guards here passing a false claim together. No wording fixes it: the
phrasing that excludes the lookalike also drops a library page that genuinely constrains the brief,
and a miss is the worst failure there is. What separates them is which document the page came from,
which is the owner's scoping call. So this machinery takes **one** named source of truth and judges
within it; `open` accepts exactly one source, and a foreign page cannot arise at run time.

The evidence, including the four criteria I got wrong before these, is in
`Tasks/intake-to-requirements-machinery/atom-1-prototype-0.md`,
`atom-2-prototype-0.md` and `atom-3-prototype-0.md`.

## What it does not decide

It does not cast an owner's decision. Readers may extract, compare, and phrase requirements, but a
split relevance call, an unresolved merge, or any other owner-queued choice remains unsettled until
`answer-owner` records one of the choices actually offered. The machinery can produce requirements
and assemble their document; it cannot silently turn model agreement into owner authority.


## Assess a finished requirements document

Run a separate, reference-relative assessment when an independently prepared reference is
available. This examines the finished Markdown itself. It does not establish that the reference
contains every duty in the source.

```sh
python3 scripts/assess_output.py --reference reference.json --document requirements.md --report assessment.json --reader-command '<configured reader command>'
```

Use the exact reader command required by the installed client's policy. The reference JSON has
`schema_version: 1`, `scope: "reference-relative"`, a `target`, a `source` object with `path` and
`sha256`, and nonempty `duties` containing unique `id` values and verbatim source `quote` values.
Relative source paths resolve beside the reference file. The source must be UTF-8 text, and its
hash and every quote are checked before any reader call.

Two independent readers assess each reference duty against the complete requirements list,
each requirement against all reference quotes, and each nonidentical requirement pair for
complete duplication. No input is clipped. A disagreement, unanswered call, or uncertain answer
remains uncertain. Identical statements count as duplicates directly. The report preserves each
reader's attempts, input hashes, omissions, unsupported requirements relative to the reference,
duplicate pairs, uncertainty, and the number of recorded owner rulings. It qualifies an output
only when none of those quality issues remains. Reader agreement does not prove the reference
exhaustive, and missing reference support does not by itself prove a duty was invented.

The input must use the machinery's numbered `## The requirements` section and its
`## Owner rulings (recorded)` section. Malformed or empty requirement inventories are refused.
The command creates an assessment report and leaves the source, reference, and document intact.
Up to four independent checks run concurrently; each check keeps its two blind reader seats.
For N requirements and D reference duties, the upper bound is two reader decisions for each of
D + N + N(N−1)/2 checks; exact duplicate pairs need no reader.
