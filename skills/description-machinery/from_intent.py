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
                               [--owner-answers <file>] [--reader-command '<command>']
Run it, do whatever it hands back, run it again.
"""

from __future__ import annotations

import argparse
import hashlib
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
        "scratch": str(scratch),
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


def _answer_state(row: dict[str, object], sources: dict[Path, str]) -> str:
    answered = str(row.get("answered") or "").strip().lower()
    if answered == "no":
        return "no"
    if answered != "yes":
        return "invalid"
    quote = str(row.get("quote") or "")
    quoted_from = str(row.get("quoted_from") or "").strip()
    if not quote.strip() or not quoted_from:
        return "invalid"
    try:
        source = Path(quoted_from).resolve()
    except OSError:
        return "invalid"
    return "yes" if source in sources and quote in sources[source] else "invalid"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _input_state(
    intent: Path, context: list[Path], owner_answers: Path | None = None,
) -> dict[str, object]:
    def source(path: Path) -> dict[str, str]:
        resolved = path.resolve()
        return {"path": str(resolved), "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest()}

    return {
        "contract": 1,
        "intent": source(intent),
        "context": [source(path) for path in context],
        "owner_answers": source(owner_answers) if owner_answers else None,
        "questions_sha256": _digest(QUESTIONS),
    }


def _bind_input_state(work: Path, current: dict[str, object]) -> dict[str, object] | None:
    state_path = work / "input-state.json"
    if not state_path.exists():
        if any(work.iterdir()):
            return {
                "status": "blocked",
                "stopped": "unbound existing state",
                "why": "this populated work directory predates input binding",
                "use_fresh_work_directory": True,
            }
        state_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return None
    try:
        saved = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "blocked",
            "stopped": "invalid input state",
            "use_fresh_work_directory": True,
        }
    if saved != current:
        return {
            "status": "blocked",
            "stopped": "input changed",
            "why": "intent, context, or fixed description questions differ from this work state",
            "saved_binding": _digest(saved),
            "current_binding": _digest(current),
            "use_fresh_work_directory": True,
        }
    return None


def drive(
    intent: Path, work: Path, context: list[Path], owner_answers: Path | None = None,
) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    try:
        current_state = _input_state(intent, context, owner_answers)
    except OSError as error:
        return {"status": "blocked", "stopped": "source unavailable", "why": str(error)}
    state_result = _bind_input_state(work, current_state)
    if state_result:
        return state_result
    questions_path = work / "questions.json"
    if not questions_path.exists():
        questions_path.write_text(json.dumps({"questions": QUESTIONS}, indent=2), encoding="utf-8")
    context_path = work / "context.json"
    context_path.write_text(
        json.dumps({
            "context": [str(path) for path in context],
            "owner_answers": str(owner_answers) if owner_answers else None,
        }, indent=2), encoding="utf-8",
    )

    expected_question_ids = {question["id"] for question in QUESTIONS}
    pass_records = [_records(work / f"look-{index}") for index in range(1, PASSES + 1)]
    missing_question_ids = {
        str(index): sorted(expected_question_ids - set(found))
        for index, found in enumerate(pass_records, start=1)
        if expected_question_ids - set(found)
    }
    unexpected_question_ids = {
        str(index): sorted(set(found) - expected_question_ids)
        for index, found in enumerate(pass_records, start=1)
        if set(found) - expected_question_ids
    }
    waiting = [
        _packet(intent, context_path, questions_path, work / f"look-{index}")
        for index in range(1, PASSES + 1)
        if str(index) in missing_question_ids
    ]
    if waiting:
        return {"status": "waiting_for_readers", "stopped": "looking",
                "why": "a pass has not answered every question",
                "questions": len(QUESTIONS), "work": waiting,
                "missing_question_ids": missing_question_ids,
                "unexpected_question_ids": unexpected_question_ids}

    passes = pass_records
    source_paths = [intent.resolve(), *(path.resolve() for path in context)]
    if owner_answers:
        source_paths.append(owner_answers.resolve())
    try:
        sources = {path: path.read_text(encoding="utf-8") for path in source_paths}
    except OSError as error:
        return {
            "status": "blocked",
            "stopped": "source unavailable",
            "why": str(error),
        }
    states = [{question["id"]: _answer_state(found.get(question["id"], {}), sources)
               for question in QUESTIONS} for found in passes]
    invalid = [
        {"pass": pass_number, "question_id": question["id"]}
        for pass_number, found in enumerate(states, start=1)
        for question in QUESTIONS
        if found[question["id"]] == "invalid"
    ]
    if invalid:
        return {
            "status": "blocked",
            "stopped": "invalid source quotation",
            "why": "a claimed answer did not quote its named intent or context source exactly",
            "invalid_records": invalid,
        }
    answered, to_ask = [], []
    for question in QUESTIONS:
        rows = [pass_.get(question["id"], {}) for pass_ in passes]
        verdicts = [found[question["id"]] == "yes" for found in states]
        if all(verdicts):
            citations = [
                {
                    "quote": str(row.get("quote") or ""),
                    "quoted_from": str(Path(str(row.get("quoted_from"))).resolve()),
                }
                for row in rows
            ]
            citation_keys = {(row["quoted_from"], row["quote"]) for row in citations}
            if len(citation_keys) == 1:
                answered.append({**question, "citation": citations[0], "answers": citations})
            else:
                to_ask.append({
                    **question,
                    "why": "the readers cited different answers",
                    "reader_citations": citations,
                })
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

    def question_block(number: int, row: dict[str, object]) -> str:
        lines = [f"{number}. {row['asks']}", f"   _{row['why']}_"]
        for citation in row.get("reader_citations") or []:
            lines.append(f"   - `{citation['quoted_from']}`: {citation['quote']}")
        if row.get("one_reader_found"):
            lines.append(f"   - `{row.get('in')}`: {row['one_reader_found']}")
        return "\n".join(lines) + "\n\n"

    sheet = work / "to-ask.md"
    sheet.write_text(
        "# What only you can answer\n\n"
        f"About: {intent}\n\n"
        + ("Everything was answered by what you gave. Nothing to ask.\n" if not to_ask else
           "".join(question_block(number, row)
                   for number, row in enumerate(to_ask, start=1)))
        + ("\nWrite the missing or clarifying answers in a separate file, then start a fresh "
           "work directory with `--owner-answers <that-file>`. The prior reader state is bound "
           "to the sources it read and must not be reused.\n" if to_ask else ""),
        encoding="utf-8",
    )

    result: dict[str, object] = {
        "status": "needs_owner" if to_ask else "complete",
        "intent": str(intent),
        "context": [str(path) for path in context],
        "owner_answers": str(owner_answers) if owner_answers else None,
        "questions": len(QUESTIONS),
        "answered_by_what_was_given": len(answered),
        "to_ask": to_ask,
        "sheet": str(sheet),
        "answered": answered,
    }
    if not to_ask:
        description = work / "description.md"
        lines = ["# Description", "", f"About: {intent}", ""]
        for row in answered:
            citation = row["citation"]
            lines.extend([
                f"## {row['id']} — {row['asks']}",
                "",
                str(citation["quote"]),
                "",
                f"_Source: `{citation['quoted_from']}`_",
                "",
            ])
        description.write_text("\n".join(lines), encoding="utf-8")
        result["description"] = str(description)
    return result


def _exit_code(result: dict[str, object]) -> int:
    return {
        "complete": 0,
        "waiting_for_readers": 2,
        "blocked": 3,
        "needs_owner": 4,
    }.get(str(result.get("status") or ""), 3)


def _progress_key(result: dict[str, object]) -> str:
    return _digest({
        "status": result.get("status"),
        "stopped": result.get("stopped"),
        "missing_question_ids": result.get("missing_question_ids"),
        "work": [job.get("waiting_for") for job in result.get("work") or []],
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--context", type=Path, action="append", default=[])
    parser.add_argument("--owner-answers", type=Path, default=None,
                        help="a file containing answers supplied by the owner")
    parser.add_argument("--reader-command", default=None,
                        help="a command that reads; without it the packets are handed back")
    args = parser.parse_args(argv)

    owner_answers = args.owner_answers.resolve() if args.owner_answers else None
    intent = args.intent.resolve()
    work = args.work.resolve()
    context = [path.resolve() for path in args.context]
    result = drive(intent, work, context, owner_answers)
    if args.reader_command:
        import readers  # noqa: PLC0415 — imported here so the step runs without a reader too

        stuck, seen = 0, None
        while result.get("work"):
            here = _progress_key(result)
            stuck = stuck + 1 if here == seen else 0
            seen = here
            if stuck >= 2:
                result = {
                    **result,
                    "status": "blocked",
                    "stopped": "reading stalled",
                    "why": "a round of reading changed nothing twice over",
                }
                break
            readers._launch(result["work"], args.reader_command, work, work, "look")
            result = drive(intent, work, context, owner_answers)
    print(json.dumps(result, indent=2, default=str))
    return _exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
