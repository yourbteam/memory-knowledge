#!/usr/bin/env python3
"""Take an intent, and find out what nothing given can answer about it.

The other half of this machinery starts from material that already exists and turns it into a
description. This half starts where there is no material — somebody wants a thing built and
nothing describes it yet — and that is the ordinary case, not the exotic one.

What a description has to answer is not invented here. It is taken from the one description that
has been proved to work: the hand-written phase-58 description, which the requirements machinery
consumed and turned into a hundred and forty-two requirements with checks. Its own headings are
the questions, because a description missing any of them was never shown to produce anything.

The division is the machinery's usual one. Code holds the questions, decides nothing about the
answers, and refuses a record that neither answers nor declines. A model reads the intent and
whatever context there is and, for each question, either quotes what answers it or says plainly
that nothing given does. What is left over is not a failure — it is the list of things only the
person who wants the thing can say, and it is the whole output of this step.

  1 · look    — model, twice. Each pass answers every question from the intent and the context
                alone, quoting, or says nothing given answers it.
  2 · gather  — code. A question both passes answered is answered; a question either pass could
                not answer goes on the list for the operator; the two disagreeing is itself a
                question for the operator, stated as the disagreement.

Nothing is invented at any point. A model that cannot find an answer says so; it never supplies
one, and the gate below refuses a record that quotes nothing while claiming an answer.

Usage:  python3 from_intent.py --intent <file> --work <dir> [--context <path> ...]
                               [--reader-command '<command>']
Run it, do whatever it hands back, run it again.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PASSES = 2

#: The questions a description must answer, taken from the headings of the one description that
#: the requirements machinery has been proved to consume. The words are deliberately the plain
#: ones a person would use, because the answers come back from a person.
QUESTIONS: list[dict[str, str]] = [
    {"id": "q1", "asks": "What is this thing for — what becomes possible that is not possible now?"},
    {"id": "q2", "asks": "Who reads or receives what it produces, and what do they do with it?"},
    {"id": "q3", "asks": "What is it given to work from, and where does each of those come from?"},
    {"id": "q4", "asks": "What must it do with what it is given?"},
    {"id": "q5", "asks": "What must it produce, and what does that thing look like?"},
    {"id": "q6", "asks": "How does anybody tell it is done, and who decides?"},
    {"id": "q7", "asks": "What must it never do, and what makes it stop rather than guess?"},
    {"id": "q8", "asks": "What is deliberately not settled here, and left to whoever builds it?"},
]

LOOK = (
    "Answer each question in {questions} about the intent stated in {intent}, using only that "
    "intent and the context listed in {context} — nothing else, and nothing you know about how "
    "such things are usually done. Write one file per question into {out} named <id>.json holding "
    "{{'id','answered': 'yes'|'no', 'answer', 'quoted_from', 'quote'}}. An 'answered' of 'yes' MUST "
    "carry 'quote': the words, copied exactly, from the intent or from a context file, and "
    "'quoted_from': which file they came from. If nothing you were given answers the question, "
    "'answered' is 'no', 'answer' is empty, and you say in 'quote' what you looked for and where "
    "you looked. A plausible answer you composed yourself is the one thing this step must never "
    "produce: the person who wants this thing built is going to be asked every question you answer "
    "'no' to, and a made-up answer means they are never asked. Guessing here is worse than an "
    "empty answer, because it cannot be told apart from a real one afterwards. When the context is "
    "empty, every answer is 'no', and that is a correct and complete result, not a failure."
)

BLIND = (
    " You are one of two independent readers of this same input: do not open any sibling output or "
    "scratch directory, and do not look for what the other found. Agreement between two readers who "
    "could not see each other is the only evidence this machinery accepts."
)

HOW_TO_READ = (
    " Put every working, scratch or intermediate file in {scratch} and nowhere else — that "
    "directory is yours alone. Before you finish, write {scratch}/reader.json holding "
    "{{'model': '<the model you are, as you are identified>', 'harness': '<the tool you are "
    "running inside>'}}. This machinery never chooses a reader — whoever runs it supplies one, so "
    "the record has to say who read it."
)


def _packet(intent: Path, context: Path, questions: Path, out: Path) -> dict[str, object]:
    scratch = out.parent / f"{out.name}-scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    return {
        "stage": "look",
        "instruction": LOOK.format(questions=questions, intent=intent, context=context, out=out)
        + BLIND + HOW_TO_READ.format(scratch=scratch),
        "waiting_for": str(out),
    }


def _records(directory: Path) -> dict[str, dict[str, object]]:
    if not directory.is_dir():
        return {}
    found = {}
    for path in sorted(directory.glob("*.json")):
        if path.name == "reader.json":
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        found[str(row.get("id") or path.stem)] = row
    return found


def _answered(row: dict[str, object]) -> bool:
    # An answer with nothing quoted is a composed one, whatever it says about itself. The whole
    # value of this step is that an unanswered question reaches the person who can answer it, and
    # a composed answer is exactly how it would not.
    return str(row.get("answered")).strip().lower() == "yes" and bool(str(row.get("quote") or "").strip())


def drive(intent: Path, work: Path, context: list[Path]) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    questions_path = work / "questions.json"
    if not questions_path.exists():
        questions_path.write_text(json.dumps({"questions": QUESTIONS}, indent=2), encoding="utf-8")
    context_path = work / "context.json"
    context_path.write_text(
        json.dumps({"context": [str(path) for path in context]}, indent=2), encoding="utf-8",
    )

    waiting = [
        _packet(intent, context_path, questions_path, work / f"look-{index}")
        for index in range(1, PASSES + 1)
        if len(_records(work / f"look-{index}")) < len(QUESTIONS)
    ]
    if waiting:
        return {"stopped": "looking", "why": "a pass has not answered every question",
                "questions": len(QUESTIONS), "work": waiting}

    passes = [_records(work / f"look-{index}") for index in range(1, PASSES + 1)]
    answered, to_ask = [], []
    for question in QUESTIONS:
        rows = [pass_.get(question["id"], {}) for pass_ in passes]
        verdicts = [_answered(row) for row in rows]
        if all(verdicts):
            answered.append({**question, "answers": [
                {"answer": row.get("answer"), "quote": row.get("quote"),
                 "quoted_from": row.get("quoted_from")} for row in rows
            ]})
        elif not any(verdicts):
            to_ask.append({**question, "why": "nothing given answers it",
                           "looked": [row.get("quote") for row in rows]})
        else:
            # One reader found an answer and the other did not. That disagreement is not something
            # code can settle and it is not something to average: it goes to the operator as the
            # question it is, with what the one who found something says it found.
            found = rows[verdicts.index(True)]
            to_ask.append({**question, "why": "one reader found an answer and the other did not",
                           "one_reader_found": found.get("quote"),
                           "in": found.get("quoted_from")})

    sheet = work / "to-ask.md"
    sheet.write_text(
        "# What only you can answer\n\n"
        f"About: {intent}\n\n"
        + ("Everything was answered by what you gave. Nothing to ask.\n" if not to_ask else
           "".join(f"{number}. {row['asks']}\n   _{row['why']}_\n\n"
                   for number, row in enumerate(to_ask, start=1))),
        encoding="utf-8",
    )

    return {
        "intent": str(intent),
        "context": [str(path) for path in context],
        "questions": len(QUESTIONS),
        "answered_by_what_was_given": len(answered),
        "to_ask": to_ask,
        "sheet": str(sheet),
        "answered": answered,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--context", type=Path, action="append", default=[])
    parser.add_argument("--reader-command", default=None,
                        help="a command that reads; without it the packets are handed back")
    args = parser.parse_args(argv)

    result = drive(args.intent.resolve(), args.work.resolve(),
                   [path.resolve() for path in args.context])
    if result.get("work") and args.reader_command:
        import readers  # noqa: PLC0415 — imported here so the step runs without a reader too

        result["readers"] = readers._launch(
            result["work"], args.reader_command, args.work.resolve(), args.work.resolve(), "look",
        )
        result = drive(args.intent.resolve(), args.work.resolve(),
                       [path.resolve() for path in args.context])
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
