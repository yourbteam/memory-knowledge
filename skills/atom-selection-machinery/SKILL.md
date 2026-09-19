---
name: atom-selection-machinery
description: Choose one next atom from a completed input-interview JSON using four separate evidence lenses, comparative selection and dependency-based distillation. Produces a recommendation for atom building; does not conduct intake or execute the selected work.
---

# Atom Selection Machinery

Run `python3 <skill-dir>/scripts/atom_selection.py`. The package is self-contained:
Python standard library and an authenticated Codex CLI. Default downstream model:
GPT-6 Astra, medium reasoning, six fresh calls. Never silently substitute models.

## Supply the input

Use the existing completed input-interview handoff. Do not rerun intake after each
atom. When a separate intake is needed, use Input Interview Machinery with GPT-5.5
high and the calling task's question template. Updating answers is a separate task.

Save the current owner-approved **delivery goal** in a text file. The selector is
the machinery choosing work, not an additional goal competing with that delivery.
Do not infer a new goal or change the frozen answers. The goal file lets an explicit
owner correction override historical goal wording without rewriting the evidence.

```sh
python3 <skill-dir>/scripts/atom_selection.py start --input HANDOFF.json --goal GOAL.txt --run NEW_RUN_DIRECTORY --prepare-only
python3 <skill-dir>/scripts/atom_selection.py resume --run RUN_DIRECTORY
python3 <skill-dir>/scripts/atom_selection.py status --run RUN_DIRECTORY
```

Preparation sends nothing. Starting without `--prepare-only` also executes. Obtain
any required payload/destination approval before execution. A fresh run makes six
calls: obstacles, reusable work, dependencies, unresolved questions, selection, then
distillation. Every lens receives the whole saved input. Selection receives it plus
all four outputs. Distillation receives the input and selected proposal.

Read [configuration and output](references/interface.md) when preparing custom
settings or consuming the handoff. Use `--settings` and `--prompts` to freeze custom
JSON files; defaults are beside the script. These settings govern downstream only.

## Read the result

The final action points to `handoff.json` and `atom.md`. Explain the one chosen job,
why it helps the delivery goal, and what establishes completion. Inspect whether
the distilled result actually separates dependent work. A completed six-call run
means a recommendation was produced, not that the recommendation is correct or
the selected work has been performed.

All model outputs remain fallible. In particular, the unresolved-question lens is
supplementary, not exhaustive; selection retains the complete input. If the target
or another prerequisite remains unresolved, surface the exact question. A saved
question is not an established fact. Do not hide it by reporting readiness.

Keep selection separate from permission to execute. Give the reviewed recommendation
to the calling assistant or Atom Building Machinery only with the applicable owner
authorization; its build-admission process supplies allowed paths and captured cases.
Do not fabricate those fields from a prose recommendation or launch a successor.

## Recovery

Progress events identify the active stage. On failure inspect `state.json` and its
call attempt, report the actual error, then explicitly resume if retry is authorized.
No automatic retries. Completed answers are reused only with unchanged frozen inputs,
prompts, settings and runtime. Failed attempts remain saved. A provider-completed call
can be recovered after a local interruption without paying again. A run lock prevents
concurrent writers. For changed input or settings, start a new run. Never edit a run
to make an old result appear current. Repeating resume on a complete run makes no calls.
