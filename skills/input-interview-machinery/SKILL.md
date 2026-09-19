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
`--contexts` must still supply complete source context for every question: later calls run in
fresh sessions. Never attach to the active desktop turn or run concurrent calls on that session.

Python asks each question, runs all eight lenses sequentially in separate fresh GPT sessions, and preserves
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
  cross-question effects in fresh sessions with the full saved interview context and copied final answers verbatim.
- `stopped`: deliver the partial handoff with unresolved questions visible.
- Failed/running state or an exception: inspect saved evidence and report the actual problem.
  Use `resume` after inspecting the failure. It retries only unfinished steps, preserving attempts
  and completed results. Do not edit answers manually or present partial execution as complete.

```sh
python3 <skill-dir>/scripts/input_interview.py user --run RUN --request-id ID
python3 <skill-dir>/scripts/input_interview.py reply --run RUN --request-id ID --reply REPLY.json
python3 <skill-dir>/scripts/input_interview.py next --run RUN
python3 <skill-dir>/scripts/input_interview.py resume --run RUN
python3 <skill-dir>/scripts/input_interview.py stop --run RUN --request-id ID --reply STOP.json
```

`next` recovers the saved next action and advances ready answers through final review.
`stop` requires an explicit owner stop while awaiting input. There is **no clarification-round
cap**: the operator controls the dialogue. These scripts are not an unattended desktop daemon;
the calling assistant must surface questions and deliver replies. Keep the user informed during
long calls. Model readiness means usable for the stated purpose within disclosed limits, not
a guarantee of perfect completeness.

## Durable recovery

Each call saves its exact input, attempt status, answer and session. A completed step is reused
only for the same input. Failed attempts remain separate. `resume` continues initial questions,
lenses, replies or final review; `next` reports a failure without retrying it. One execution lock
prevents concurrent writers. A fresh session gets the original question, latest accumulated answer,
source evidence and relevant owner feedback. Final checks get the complete saved interview.
No model history is required for lenses, follow-ups or final checks. A single supplied packet must
still fit the provider context window; recovery never silently truncates evidence.

## Incremental interview

Reuse a completed answer set after an atom assessment. The separate
`scripts/incremental-template.json` asks which original answers need updating, including indirect
consequences; all may remain unchanged. One model call makes an explicit keep/update judgment
for every original question. Python then runs only selected questions through the existing engine.

```sh
python3 <skill-dir>/scripts/input_interview.py incremental start --previous ANSWERS.json --assessment ASSESSMENT.json --goal GOAL.json --run NEW_DIRECTORY
python3 <skill-dir>/scripts/input_interview.py incremental continue --run DIRECTORY
```

Use `--prepare-only` on start for zero calls, or `--plan-only` on start/continue to stop after
selection. Optional `--settings` and `--template` apply at start. Selection uses the same frozen
model settings as the interview. Each selected question normally costs ten more calls before
any necessary clarification or revision; inspect selection when the authorized call budget is bounded.

Handle any returned question with existing user/reply commands against the returned
`interview_run`, then use incremental continue. The completed `current-answers.json` contains
all original questions, copies updated answers verbatim, preserves untouched entries and links
the previous snapshot, assessment and update decisions. It does not overwrite the previous file.
The affected-question pass examines all previous answers; subsequent cross-question review covers
selected questions only, with the full previous answer set provided as context. Do not describe
this as a fresh full interview or automatic promotion of current project state.
