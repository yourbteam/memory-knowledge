# Goal Declaration Sequence

<!-- BEGIN SEMANTIC INTAKE ENTRYPOINT -->
## Operator entry point

After selecting and activating this registered sequence, launch the shared controller with no
arguments:

```bash
python3 scripts/sequence_intake_launch.py
```

Answer only the semantic questions shown. Every question includes its response format, an example,
and constraints. The controller derives JSON, files, environment, flags, and argv; displays the
exact prepared operation; and requires a separate yes/no authorization before guarded dispatch.

Any argument-bearing commands below are machine-compatibility and verification evidence for the
deterministic adapter. Operators and agents must not construct or invoke those forms directly.
<!-- END SEMANTIC INTAKE ENTRYPOINT -->

## Purpose

Give a repository one declared goal, the KPIs it is judged by, and a durable record of every
reading — so a report cannot name a goal nobody set or a number nobody measured.

This exists because of what happened on 2026-08-06. The goal changed in conversation — "make the
harness reliable so the output docs it produces can be sent to UP" — while the number still being
reported came from a string hardcoded inside a per-project reporting script. Nothing declared the
goal, so nothing could check that the report matched it. The same morning, that number had moved
303 → 302 → 303 on identical bytes, because it was produced by a model judging one requirement at
a time and the verdict was banked from a single answer. Kamen: "this yo yo that you are reporting
now up and down depletes the whole purpose of tracking progress and makes you look completely
stupid."

## Use This Sequence When

- The goal of the work changes, or a goal is being set for the first time in a repository.
- A new KPI is needed for the goal in force.
- A report is due and the KPI has not been read since the last change that could move it.

## Do Not Use This Sequence When

- The goal is unchanged and the number is current: run `report`, not `set`.
- The question is what a single run did. That is the run's own record, not the goal store.

## Steps

1. **Declare or replace the goal** — zero-argument interview. Replacing a goal in force requires a
   reason; the old goal, its KPIs and all its readings are kept and marked superseded.

   ```bash
   python3 ~/memory-knowledge/scripts/goal_tracker.py --repo "$PWD" set
   ```

2. **Take a reading** — runs the KPI's own declared producer and records what it returned,
   including the items that failed and what failed about them.

   ```bash
   python3 ~/memory-knowledge/scripts/goal_tracker.py --repo "$PWD" measure --kpi <kpi-id>
   ```

3. **Render the report** — the three lines, every figure read from the store.

   ```bash
   python3 ~/memory-knowledge/scripts/goal_tracker.py --repo "$PWD" report
   ```

4. **Inspect the whole record** when a finding needs the history rather than the latest number.

   ```bash
   python3 ~/memory-knowledge/scripts/goal_tracker.py --repo "$PWD" show
   ```

## What The Gate Enforces

`working-agreement/require-drive-report-truth.sh` calls `goal_tracker.py check --goal-line` for any
repository that carries `.goal/goal.json`. A reply whose GOAL line is not the one the store renders
is refused, with the store's own line quoted back. Proven on two transcripts identical but for that
line: the declared line passed, the previous goal's line was blocked.

## Verification

The sequence is working when, from a repository with a declared goal:

- `report` prints a GOAL line naming the declared KPI's question and a value read from the store;
- a KPI that has never been read prints `not yet measured`, never `0`;
- a reading taken after the measured set grew prints `not comparable` with both totals, never a
  delta computed across different denominators;
- the gate refuses a GOAL line that was typed rather than rendered.

Covered by `tests/test_goal_tracker.py`.
