# Chain ledger — goal: the directives are followed, not optionally

One entry per fix, appended, never rewritten. Every field is taken from what the system
recorded, not from memory. Written 2026-07-28, after arguing a direction-check from a
ledger that did not yet exist.

**Distance number:** anchor claims that are mechanically verified, of the eight fields in
the G0 anchor (`directives, mode, controller, envelope, ask, words, scope, exceptions`).
Counted from `require-directive-anchor.sh` and `require-directives-read.sh`. This morning
it was 0 — every claim was self-graded.

| # | what failed (recorded) | what was fixed | proof | distance | cost to find |
| --- | --- | --- | --- | --- | --- |
| 1 | Six consecutive replies carried no anchor at all; a commit ran without the registered-sequence rule surfacing | PreToolUse read gate + Stop anchor gate | the gate refused a 166-word message that declared 150 | 0 → 3 (`directives`, `envelope`+edits, `words`) | Kamen noticed and said so |
| 2 | G18 never surfaced on the one turn it governed | `trigger-rules.json` + PreToolUse delivery | fired on four real calls the same day | 3 → 4 (`controller` vs invocation) | one missed commit |
| 3 | Four recorded false positives: a test fixture quoting `git commit`, a `python -c` string, a heredoc, a `grep` | match the commands a line runs, not its text | red/green on those four real payloads; eight true positives still fire | 4 → 4 (precision, not coverage: 4 false positives → 0) | Kamen refused the shrug "inherent to matching strings" |
| 4 | `controller=` accepted an invocation 154 entries before the last context reset; `direction-check` skipped on a re-edit | staleness check against the reset; direction-check required on a file an earlier turn edited | seven cases pass, including the real transcript | 4 → 5 (`controller` truthfully, plus the router rule) | self-audit prompted by Kamen asking what is actually enforced |
| 5 | "starting it now" written as the closing sentence, repeatedly, with nothing started — the turn ends where the message ends, so the promise was about a turn only Kamen could begin | `ask=none` refused unless the turn applied an edit or launched a background process | five cases pass; a read-only turn claiming `ask=none` is refused, an edit or background launch passes | 5 → 6 (`ask`) | Kamen: "you say you are going to do something then stop" |

## What remains, named

`mode`, `scope`, and `exceptions` are not checkable from the transcript, and neither is the
truth of the outcome quoted in `envelope=approved:"…"`. Those four stay honest-but-unchecked.
Naming them is the point: an approach that cannot say what remains is the Path B signal.

Entry 5 was taken after the bound below was set, because Kamen asked for it directly. The
bound is his to lift, and he lifted it.

## Standing verdict (2026-07-28)

Path A. Entries 3 and 4 are fixes to earlier fixes, which is the Path B signal — but the
distance rose at every entry, the cost per entry fell, and the remainder is nameable. That
is hardening, not a chain.

The fact that would flip it: a fifth enforcement fix that does not raise the count, or a
remainder that can no longer be named.

**Bound (G25):** this goal is not the deliverable. The harness goal sat at 31/35 throughout
entries 1–4. No fifth enforcement fix before that number moves.
