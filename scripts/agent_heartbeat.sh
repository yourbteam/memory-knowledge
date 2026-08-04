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

# Refuse a heartbeat that can only count.
#
# 2026-08-04: three consecutive reports said "23 review events, no errors" — a number that is true
# whether the run is reviewing the right feature, re-reviewing the wrong one, or looping. Kamen:
# "don't you have a directive to watch what a run is actually doing instead of shallow cursory
# numbers." He does — observe the work itself: which item, which phase, which transition, which
# decision, which error. A count is a fine SUPPLEMENT and a worthless ONLY.
#
# So: at least one probe must return state rather than a tally. Counting probes stay allowed
# alongside it.
counting_re='(^|[|[:space:]])(wc[[:space:]]+-[a-z]*l|grep[[:space:]]+(-[a-zA-Z]*[[:space:]]+)*-[a-zA-Z]*c([[:space:]]|$)|uniq[[:space:]]+-c)'
if [ "${#probes[@]}" -gt 0 ]; then
  observing=0
  for probe in "${probes[@]}"; do
    if ! printf '%s' "$probe" | grep -Eq "$counting_re"; then observing=1; fi
  done
  if [ "$observing" -eq 0 ]; then
    {
      echo "agent_heartbeat.sh: every probe only counts, so this heartbeat cannot report what the"
      echo "run is DOING. The probes given were:"
      for probe in "${probes[@]}"; do echo "  - ${probe}"; done
      echo
      echo "Add at least one probe that returns state, not a tally. Any of these satisfies it:"
      echo "  - the work item and its phase   e.g. the newest run id and the phases it has produced"
      echo "  - a produced artifact           e.g. ls -la <run>/phases/<phase>/<output-file>"
      echo "  - decisions/transitions/errors  e.g. docker logs ... | grep -E 'WARNING|ERROR|decision'"
      echo "Counting probes may stay alongside it."
    } >&2
    exit 2
  fi
fi
if [ "$seconds" -lt 1 ] || [ "$seconds" -gt 3600 ]; then
  echo "agent_heartbeat.sh: --seconds must be between 1 and 3600, got '$seconds'" >&2
  exit 2
fi

sleep "$seconds"

echo "=== heartbeat $(date -u '+%Y-%m-%d %H:%M:%SZ')${label:+ · $label} (waited ${seconds}s) ==="
if [ "${#probes[@]}" -eq 0 ]; then
  echo "(no probe given — this heartbeat only re-invokes the agent)"
  exit 0
fi

for probe in "${probes[@]}"; do
  echo "--- probe: ${probe}"
  # Advisory by design: report the failure, keep the cadence alive.
  if ! output="$(eval "$probe" 2>&1)"; then
    echo "(probe exited non-zero — reporting what it produced)"
  fi
  if [ -z "${output//[[:space:]]/}" ]; then
    echo "(no output — say so plainly rather than inferring progress)"
  else
    printf '%s\n' "$output"
  fi
done
