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
3. **Give it probes that answer "what is true now".** Each `--probe` is a shell command; they run
   in order after the wait. Prefer probes that read the system's own record (container logs, a
   process check, a produced artifact) over anything inferred.
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
