# Agent Heartbeat Sequence

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

Keep an agent returning to a long-running watch on a fixed cadence, so a live drive, build, or
deploy is never left unobserved and Kamen is never left without a report.

This sequence exists because the obvious mechanism does not work. On 2026-08-01 a scheduled
wake-up was armed to return every five minutes; it fired zero times in sixteen hours and the
session went silent until Kamen intervened. On the night of 2026-08-03/04 the same cadence was
held for roughly forty consecutive reports with no misses using a different shape: a **background
job that ends**. The host emits a completion notification when a background command finishes, and
that notification is what re-invokes the agent.

The rule this encodes: **a promise to come back is not a wake-up; an ending is.**

## Use This Sequence When

- Any work will exceed about five minutes without the agent otherwise being re-invoked: a live
  workflow drive, an image build, a deploy, a long test run, a remote job.
- An agent must satisfy a maximum-reporting-interval rule while work runs unattended.
- A watch must survive across many turns without the agent choosing when to look.

## Do Not Use This Sequence When

- The work completes inside one turn, or the harness already re-invokes the agent on completion
  (a tracked background task that notifies on its own does not need a second heartbeat).
- The wait is for an event the agent can subscribe to directly.

## Script

Primary script: `memory-knowledge:scripts/agent_heartbeat.sh`

It waits, then runs each probe and prints what the probe produced, prefixed by a UTC timestamp.
It is deliberately dumb: it observes and reports, it does not judge.

## Steps

1. **Arm it as a background command.** In Claude Code that is the Bash tool with
   `run_in_background: true`. Foreground defeats the entire mechanism — the wake-up IS the
   completion notification.
2. **Choose the wait.** Default `--seconds 270` (4.5 minutes) sits inside a five-minute reporting
   ceiling and leaves room for the turn itself. Range accepted: 1–3600.
3. **Give it probes that answer "what is the run DOING".** Each `--probe` is a shell command; they
   run in order after the wait. At least one must **return** state rather than a tally — judged
   from what the probes actually returned, not from how they were written. When every probe comes
   back empty or purely numeric the heartbeat still wakes you (the cadence is never broken) and
   exits 3 with a refusal naming what to write instead.

   Judging the output rather than the command text is deliberate. The first version pattern-matched
   `grep -c` and `wc -l`, which is scope chosen by the author — and choosing the scope is the very
   failure this guard exists to catch. `python3 -c 'print(len(x))'` and `grep -c foo | tr -d " "`
   both return a bare number while matching no counting pattern; both are now caught.

   A count is a fine supplement and a worthless only. On 2026-08-04 three consecutive reports said
   "23 review events, no errors" — true whether the run is reviewing the right feature, re-reviewing
   the wrong one, or looping. Kamen: *"don't you have a directive to watch what a run is actually
   doing instead of shallow cursory numbers."* Probes that satisfy the check:

   - the work item and its phase — the newest run id and the phases it has produced
   - a produced artifact — `ls -la <run>/phases/<phase>/<output-file>`
   - decisions, transitions and errors — `docker logs … | grep -E 'WARNING|ERROR|decision'`
4. **When it completes, report honestly and re-arm.** One heartbeat per turn. If nothing advanced,
   say nothing advanced — the script prints `(no output …)` rather than silence precisely so the
   report cannot round a stall up into progress.

## Machine compatibility (verification evidence — do not invoke directly)

```bash
scripts/agent_heartbeat.sh --seconds 270 --label "feat-11 re-drive" \
  --probe 'docker logs --since 5m workflow-orch-local-sequence-check 2>&1 | grep -c requirement-verdict' \
  --probe 'pgrep -f greenfield_drive_dag.py | head -1'
```

## Failure Handling

- **A probe fails or prints nothing.** Reported, never fatal. A heartbeat that dies on a bad probe
  stops the cadence, which is the failure this sequence exists to prevent.
- **Every probe returned only a number (exit 3).** The wake-up still happened; the report is the
  problem. Add a probe that returns state and re-arm. Verified 2026-08-04: a python one-liner
  printing a length, and a count laundered through `tr`, both exit 3; a probe naming the run and
  its phase exits 0; a count alongside such a probe exits 0.
- **Malformed `--seconds`.** Exits 2 with a message naming the bad value; nothing is armed. Fix the
  argument and re-arm.
- **The heartbeat was armed in the foreground.** No completion notification arrives and the agent
  goes silent. Re-arm in the background.
- **A scheduled/deferred wake-up was used instead.** Treat as the known-broken path (2026-08-01,
  zero fires in sixteen hours). Replace it with this sequence.

## Verification

- Bad-argument path: `scripts/agent_heartbeat.sh --seconds abc` → exit 2, message names `'abc'`.
- Real path, 2026-08-04 05:22:52Z: a 2-second run with a failing probe, an empty probe and a good
  probe printed the timestamped header, `(probe exited non-zero …)`, `(no output …)`, then `alive`,
  and exited 0.
- Live cadence evidence: 2026-08-03/04, roughly forty consecutive heartbeats re-invoked the agent
  across a full greenfield feature re-drive with no missed interval.

## Pass Signal

The background command completes, the agent is re-invoked by that completion, and the output opens
with `=== heartbeat <UTC timestamp> …`.
