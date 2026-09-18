---
name: input-interview-machinery
description: Collect reusable question-template answers from a context-bearing model, refine each through eight fixed lenses, route missing information to the operator, and export the final answers as JSON. Use when another skill or task needs a structured input interview.
---

# Input Interview Machinery

Use `python3 <skill-dir>/scripts/input_interview.py` as the entry point. Runtime is
self-contained Python standard library, plus an authenticated Codex CLI at
`/Applications/ChatGPT.app/Contents/Resources/codex`. Default: GPT-5.5, high reasoning.
Only the Codex provider is implemented. Never silently substitute a model or provider.

## Start

Read [the input formats](references/inputs.md) to create or edit the calling skill's
question template and supply its real task context. Store templates and run output
in the caller's workspace, outside the installed skill. The bundled `scripts/questions.json`
is a one-question example, not the complete atom-selection intake.

```sh
python3 <skill-dir>/scripts/input_interview.py start --questions QUESTIONS.json --contexts CONTEXTS.json --run NEW_RUN_DIRECTORY
```

Optional `--settings SETTINGS.json` freezes model settings for this run. Alternatively,
`--caller-session ID` resumes an explicit **idle Codex CLI session** with the task context;
`--contexts` then supplies optional additional evidence. Never attach to the active desktop
turn or run concurrent calls on that session. Without a session, supply contexts for every
question; each question receives its own persistent model session.

Python asks each question, runs all eight lenses sequentially in its session, and preserves
every answer version. The interviewed model owns readiness. There is no separate assessor
trying to judge completeness without the task context. Do not replace sequential lenses
with a single combined call, reinterpret readiness in caller code, or invent missing evidence.

## Continue automatically

Read the final JSON action after any progress events. The calling assistant is the UI adapter:

- `resolve_input`: inspect the exact request. Supply available, authorized source evidence
  through `reply`. If the missing fact or decision belongs to the user, run `user` and invoke
  `functions.request_user_input_async` with the returned tool arguments. Ask only that question.
- `ask_user`: surface the returned question if it has not already been sent, and wait for the
  actual answer. Preserve its request ID. Do not resubmit the question on every poll.
- On the user's answer or correction, save it verbatim in the reply format and run `reply`
  immediately. Do not ask for another “proceed.” Drift feedback goes to the same interviewed
  model; it is not an instruction to stop unless the user explicitly ends the interview.
- `complete`: give the calling skill the returned `handoff` file. Python has checked
  cross-question effects in the original sessions and copied final answers verbatim.
- `stopped`: deliver the partial handoff with unresolved questions visible.
- Failed/running state or an exception: inspect saved evidence and report the actual problem.
  Do not repeat model calls blindly, edit answers manually, or present partial execution as complete.

```sh
python3 <skill-dir>/scripts/input_interview.py user --run RUN --request-id ID
python3 <skill-dir>/scripts/input_interview.py reply --run RUN --request-id ID --reply REPLY.json
python3 <skill-dir>/scripts/input_interview.py next --run RUN
python3 <skill-dir>/scripts/input_interview.py stop --run RUN --request-id ID --reply STOP.json
```

`next` recovers the saved next action and advances ready answers through final review.
`stop` requires an explicit owner stop while awaiting input. There is **no clarification-round
cap**: the operator controls the dialogue. These scripts are not an unattended desktop daemon;
the calling assistant must surface questions and deliver replies. Keep the user informed during
long calls. Model readiness means usable for the stated purpose within disclosed limits, not
a guarantee of perfect completeness.
