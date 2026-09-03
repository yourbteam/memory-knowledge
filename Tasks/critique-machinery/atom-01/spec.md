# Atom 1 — unit enumeration

## Outcome

`critique.py open` binds one delivered Markdown page to one structured object in its stored state,
refuses a non-repository run location or incompatible reopen, and freezes a complete unit manifest.
Every non-empty rendered block belongs to exactly one unit, and every unit retains its payload path
and hashes.

## Frozen real cases

| Case | Kind | SHA-256 | Expected |
| --- | --- | --- | --- |
| `btm-roadmap` | success | `b8d29d78cdfc446ed5d165ccb6bfba89bb2b0e12696bc3ee81ab1b8c9cab6db8` | opened |
| `viv-scorecard` | success | `faf056757b70468c5b6723f46831d898ae78134916c5d4701c0260b27d39c6e3` | opened |
| `btm-roadmap-wrong-payload` | failure | `72445fcc17d9093970266ae4ffd35a1e2fb104ae44eae9ebc8ab2820bbb522e4` | refused page/payload mismatch |

The failure case is the owner-approved controlled negative: unchanged BTM Step 12 page bytes paired
with the real `measurement_framework` object in the same real BTM state. No content was invented.

## Competing approaches

1. `payload-records`: cut at stored top-level objects and list records, then assign each rendered
   block to the stored record with the strongest word overlap.
2. `rendered-sections`: cut at rendered Markdown headings, then bind each section to the stored
   record with the strongest word overlap.

## Criteria fixed before execution

Rank in this order across all three cases:

1. Boundary correctness: both authentic pairs open and the approved mismatched pair refuses.
2. Territory completeness: every non-empty rendered block is assigned exactly once.
3. Judgeability: maximize non-empty units between 10 and 500 words.
4. Payload grounding: maximize units whose territory shares words with their bound stored record.

Stable approach id breaks a true tie. The runner preserves both raw outputs.

## Stopping condition

The complete Development-Probe run passes every frozen case, the winner is promoted unchanged,
and the actual `open` CLI repeats all three outcomes plus the repository-location and immutable-
reopen refusals.
