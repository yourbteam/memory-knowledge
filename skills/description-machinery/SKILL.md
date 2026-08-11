---
name: description-machinery
description: "Turns an owner's intent and available context, or the notes builders left behind, into one source-quoted description that Requirements Machinery can consume. Readers judge meaning; deterministic code fixes the questions, source boundary, pair identities, input state, agreement gates, and final assembly."
---

# Description machinery

This is the first machinery in the chain. It produces the description Requirements Machinery
consumes. It never writes requirements or decides what should be built. Every subject statement it
hands on is an exact quotation from the owner's intent, supplied context, owner answers, or a
builder note.

This skill is the complete local controller for its description loops. Invoke the applicable front
door directly: do not
put `task-intake`, `sequence-runner`, registry selection, or sequence discovery around it solely
because it launches readers or resumes. Its work/output directory is its state and telemetry.

## Front door 1 — intent and context

Use this for ordinary or greenfield work:

```text
python3 from_intent.py --intent <file> --context <path> --work <fresh-dir> \
    --reader-command '<command>'
```

The intent is always required. Context is optional and repeatable. Code fixes eight questions a
usable description must answer. Two blind readers independently answer each question only by
quoting the supplied files.

If context cannot answer everything, the result has `status: needs_owner` and `to-ask.md` contains
only the unresolved questions. Put the owner's answers in a separate file, then start a **fresh**
work directory:

```text
python3 from_intent.py --intent <file> --context <path> --owner-answers <file> \
    --work <new-fresh-dir> --reader-command '<command>'
```

The owner-answer file is an authorized source, not an instruction to improvise. A question enters
the final `description.md` only when both readers cite the same exact passage from the same
authorized file. Code writes the fixed question heading, exact quotation, and source path. It
carries no reader paraphrase into the description.

## Front door 2 — what builders left alone

Use this after Implementation Machinery has accumulated `left_alone` notes:

```text
python3 collect_noticed.py --work <build-work-dir> --order <order.json> --out <fresh-dir> \
    --reader-command '<command>'
```

- `work` is the Implementation Machinery work directory.
- `order` is its build list, used to recognize observations already required.
- `out` is a fresh resumable state directory.
- `reader-command` receives an instruction on standard input. The machinery never chooses it.

Six readers work in three blind pairs:

1. Two split builder notes into distinct observations, quoting the note exactly.
2. Code pairs the two readings within each note.
3. Two judge every expected pair: same thing, still work, already required.
4. Two judge whether observations from different builders are one piece of work.

Code verifies every quote against its builder note and verifies that every expected pair identity
has exactly one judgement from each reader. Count alone never completes a stage. The primary output
is `noticed-description.md`; `noticed-report.json` is the same observations in build-shaped JSON.

## State and changed inputs

Both front doors write `input-state.json` before accepting reader output. It binds the state
directory to the exact contents and identities of its inputs. Reusing the directory with changed
intent, context, owner answers, builder notes, fixed questions, or order returns `status: blocked`.
Start a fresh directory; the machinery never deletes or silently reinterprets old reader state.
A populated legacy directory without a binding is also refused.

## Status and exit contract

| `status` | Exit | Meaning | Next action |
|---|---:|---|---|
| `complete` | 0 | The description exists, or no builder note contained an observation. | Consume the returned description path, if present. |
| `waiting_for_readers` | 2 | One or more jobs are under `work`. | Run every job independently, then invoke the same command again. |
| `blocked` | 3 | Input changed, a source/citation is invalid, a pair is duplicated, or reading stalled. | Follow `why`; use a fresh state directory where instructed. |
| `needs_owner` | 4 | Supplied sources cannot settle every description question. | Answer `to-ask.md`, then use `--owner-answers` with a fresh work directory. |

Without `reader-command`, exit 2 is the normal handback contract. Launch one independent agent per
job, all jobs of the stage in parallel, with each `instruction` verbatim. Never let one reader see
another's output. With `reader-command`, the controller continues until a terminal status and
blocks after two unchanged reading rounds.

Never hand-edit a reader result to cross a gate. A refusal is evidence: rerun the reader where the
result says to, or start fresh when the input binding or source contract requires it.
