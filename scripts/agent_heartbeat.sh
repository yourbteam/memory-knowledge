#!/usr/bin/env bash
# Agent heartbeat — the wake-up that actually fires.
#
# WHY THIS EXISTS
#   On 2026-08-01 a scheduled wake-up was armed to bring the agent back every five minutes. It
#   never fired once across sixteen hours; Kamen found the session silent. On 2026-08-03/04 the
#   same cadence was held for a full night — roughly forty consecutive reports, no misses — using
#   this shape instead: a BACKGROUND JOB THAT ENDS. The host notifies the agent when a background
#   command completes, and that completion notification is the wake-up. A scheduler promising to
#   return is not a wake-up; an ending is.
#
#   So: never rely on a scheduled/deferred wake-up for a long-running watch. Background THIS
#   script and let it finish.
#
# HOW AN AGENT USES IT
#   Run it as a BACKGROUND command (Claude Code: Bash with run_in_background: true). When it
#   exits, the completion notification re-invokes the agent, which reads the output, reports
#   honestly, and arms the next one. One heartbeat per turn — chaining them is the whole point.
#
#   Its stdout IS the report material: a UTC timestamp, then whatever the probe printed.
#
# USAGE
#   agent_heartbeat.sh [--seconds N] [--label TEXT] [--probe 'shell command'] ...
#
#   --seconds N     how long to wait before waking (default 270 — 4.5 min, inside a 5-minute
#                   reporting ceiling with room for the turn itself)
#   --label TEXT    what this heartbeat is watching, echoed into the output
#   --probe CMD     a command whose output describes the current state. Repeatable; each runs in
#                   order after the wait. Probes are advisory: a failing probe is reported, never
#                   fatal, because a heartbeat that dies on a bad probe stops the cadence — which
#                   is the exact failure this script exists to prevent.
#
# EXAMPLE (watching a container-side drive)
#   scripts/agent_heartbeat.sh --label "feat-11 re-drive" \
#     --probe 'docker logs --since 5m my-container 2>&1 | grep -c requirement-verdict' \
#     --probe 'pgrep -f greenfield_drive_dag.py | head -1'
#
# NOTES
#   - No secrets are printed by this script; a probe that prints secrets is the probe's fault.
#   - Exit status is always 0 unless the arguments are malformed: the heartbeat's job is to WAKE,
#     not to judge. What it observed goes in the text for the agent to judge.
set -uo pipefail

seconds=270
label=""
probes=()

while [ $# -gt 0 ]; do
  case "$1" in
    --seconds) seconds="${2:-}"; shift 2 ;;
    --label)   label="${2:-}";   shift 2 ;;
    --probe)   probes+=("${2:-}"); shift 2 ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "agent_heartbeat.sh: unknown argument '$1' — expected --seconds, --label or --probe" >&2
       exit 2 ;;
  esac
done

case "$seconds" in
  ''|*[!0-9]*) echo "agent_heartbeat.sh: --seconds must be a whole number of seconds, got '$seconds'" >&2
               exit 2 ;;
esac

sleep "$seconds"

echo "=== heartbeat $(date -u '+%Y-%m-%d %H:%M:%SZ')${label:+ · $label} (waited ${seconds}s) ==="
if [ "${#probes[@]}" -eq 0 ]; then
  echo "(no probe given — this heartbeat only re-invokes the agent)"
  exit 0
fi

observed=0
for probe in "${probes[@]}"; do
  echo "--- probe: ${probe}"
  # Advisory by design: report the failure, keep the cadence alive.
  if ! output="$(eval "$probe" 2>&1)"; then
    echo "(probe exited non-zero — reporting what it produced)"
  fi
  stripped="${output//[[:space:]]/}"
  if [ -z "$stripped" ]; then
    echo "(no output — say so plainly rather than inferring progress)"
  else
    printf '%s\n' "$output"
    # Did this probe return STATE, or only a tally? Judged from what came back, not from how the
    # command was written: a pattern over command text is scope I choose, and choosing the scope is
    # the failure this guard exists to catch (docs/gf-art-chain-ledger.md, 2026-08-04 05:55 —
    # two of my own checks inspected less than they claimed). `python3 -c 'print(len(x))'` and
    # `grep -c foo | tr -d " "` both return a bare number while matching no counting pattern.
    case "$stripped" in
      *[!0-9]*) observed=1 ;;
    esac
  fi
done

if [ "$observed" -eq 0 ]; then
  {
    echo
    echo "!! Every probe returned only a number or nothing, so this heartbeat cannot say what the"
    echo "   run is DOING — only how much of something there was. A count is true whether the run"
    echo "   works the right item, repeats the wrong one, or loops."
    echo
    echo "   Replace or add a probe that returns state. Any of these satisfies it:"
    echo "     - what the run PRODUCED         e.g. the findings/verdicts its last stage wrote"
    echo "     - a produced artifact           e.g. ls -la <run>/phases/<phase>/<output-file>"
    echo "     - decisions/transitions/errors  e.g. docker logs ... | grep -E 'WARNING|ERROR|decision'"
    echo "   Counting probes may stay alongside one that observes."
    echo
    echo "   NOTE, and this check CANNOT catch it for you: a stage name is not a number, so"
    echo "   'stage 10 of 13' passes this gate and is still a progress statistic. On 2026-08-04"
    echo "   four consecutive reports said which review stage was running; Kamen asked whether the"
    echo "   heartbeat had been adjusted 'so you do not only report numbers as stats'. Position is"
    echo "   not content. Probe what the run WROTE — its findings, verdicts, decisions — and report"
    echo "   those."
  }
  exit 3
fi
