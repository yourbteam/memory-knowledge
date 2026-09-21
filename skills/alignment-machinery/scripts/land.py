#!/usr/bin/env python3
"""The sixth step of alignment-machinery: find where each approved rule lands in the harness.

A rule the owner approved says what should be true of a page. It does not make it true, and nothing
in the record says which rules already are. On 21 September two of twenty were answered by hand --
the agency's filing rows are re-added on every run because they are required fields of a calendar
month; the working record was already kept off the client page by one renderer -- and both answers
existed only in conversation until they were typed into a commit message. Eighteen would have gone
the same way.

    land.py open  --work <run> --harness <repo root>   -> the rules, pinned to the code read
    land.py ask   --work <run> --reader 1|2|3          -> one reader's questions, blind to the rest
    land.py read  --work <run> --answers <file>        -> keep one reader's answers
    land.py settle --work <run>                       -> what they agree on, and what is for Kamen
    land.py ask-owner --work <run>                    -> the disagreements, readings first
    land.py rule  --work <run> --id <rule> --choice already|needs-a-check --because "<his words>"
    land.py finish --work <run>                       -> the landed list, once nothing is unsettled
    land.py show  --work <run>                        -> what it holds, in a few lines

The question has two answers and no others: the harness already produces this, or a check must be
built. Bounded, so three readers who cannot see each other can agree or differ, and a difference
goes to Kamen rather than to a model.

One thing separates this step from the two before it. Its answers are claims about our own code, so
they can be checked against the code. An answer is refused unless it names a file inside the pinned
harness and quotes the line that decides it, and the quote must be found in that file verbatim. The
failure that matters here is a reader reporting a rule satisfied when it is not -- that silently
drops a rule the owner approved -- and a citation nobody can find is exactly what that failure
looks like.

The harness is pinned by the commit it was read at, because "already true" is worthless as a claim
about code that is not what runs.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from invoke import Refused  # noqa: E402  (one refusal shape for the whole machinery)

LANDING_VERSION = 1
#: the two answers, and what each means for the work
ANSWERS = {
    "already": "the harness already produces this; the rule holds behaviour that exists",
    "needs-a-check": "the harness does not produce this, or does not refuse its absence; a change "
                     "has to be built, and the citation names where",
}
#: the readers, and the model they run as
READERS = (1, 2, 3)
REQUIRED_MODEL = "claude-opus-5"
REQUIRED_REASONING = "high"
#: the model that writes a recommendation on a disagreement, having done no reading
RECOMMENDER = "claude-fable-5-1"
#: how a rule settled by Kamen is recorded
THE_OWNERS_RULING = "Kamen's ruling"
#: the shortest quotation that shows which line was read
SHORTEST_QUOTE = 12


def _ruled(work: pathlib.Path) -> dict:
    """The ruled list, refused unless the ruling step finished it."""
    target = work / "rules.json"
    if not target.is_file():
        raise Refused(f"work: {work} holds no rules.json — this step lands rules the owner ruled "
                      f"on; run `rule.py finish` first")
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Refused(f"work: {target} could not be read as JSON ({exc})") from None
    if value.get("machinery") != "alignment-machinery" or value.get("step") != "ruling":
        raise Refused(f"work: {target} was not written by this machinery's ruling step")
    if not value.get("rules"):
        raise Refused(f"work: {target} holds no rules — every candidate was rejected, so there is "
                      f"nothing to land")
    return value


def _commit(harness: pathlib.Path) -> str:
    """The commit the harness sits at, so a later reader knows which code was read."""
    try:
        done = subprocess.run(["git", "-C", str(harness), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Refused(f"harness: {harness} is not a git repository this machine can read "
                      f"({exc}); a landing is pinned to the commit it read, because 'already true' "
                      f"says nothing about code that is not what runs") from None
    return done.stdout.strip()


def _dirty(harness: pathlib.Path) -> list[str]:
    done = subprocess.run(["git", "-C", str(harness), "status", "--porcelain"],
                          capture_output=True, text=True)
    return [line[3:] for line in done.stdout.splitlines() if line.strip()]


def open_landing(work: pathlib.Path, harness: pathlib.Path) -> dict:
    """The rules to land, pinned to the harness and the commit they were read at."""
    ruled = _ruled(work)
    if not harness.is_dir():
        raise Refused(f"harness: {harness} is not a directory")
    at = _commit(harness)
    return {
        "machinery": "alignment-machinery",
        "step": "landing",
        "landing_version": LANDING_VERSION,
        "harness": {"root": str(harness), "commit": at,
                    "uncommitted_files": len(_dirty(harness))},
        "ruled_by": ruled["ruled_by"],
        "gathered_from": ruled["gathered_from"],
        "rules": [{"id": r["id"], "rule": r["rule"], "in_his_words": r["in_his_words"],
                   "clients": r["clients"], "passages": r["passages"], "lines": r["lines"],
                   "one_passage_that_shows_it": (r["shown_by"][0] if r["shown_by"] else None)}
                  for r in ruled["rules"]],
        "opened_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "next_step": f"ask each of the {len(READERS)} readers",
    }


def _open(work: pathlib.Path) -> dict:
    target = work / "landing.json"
    if not target.is_file():
        raise Refused(f"work: {work} holds no landing.json — run `land.py open --harness <root>` "
                      f"first, so the rules are pinned to the code that will be read")
    return json.loads(target.read_text(encoding="utf-8"))


def ask(work: pathlib.Path, reader: int) -> dict:
    """One reader's questions: every approved rule against the harness, blind to the others."""
    held = _open(work)
    return {
        "machinery": "alignment-machinery",
        "step": "landing",
        "reader": str(reader),
        "the_harness": held["harness"],
        "the_question": "Does the harness already produce this, or must a check be built?",
        "the_answers": ANSWERS,
        "how_to_answer": (
            "Answer every rule. Put 'already' or 'needs-a-check' in `answer`. Name the file you "
            "read in `file`, relative to the harness root, and put in `quote` the line from that "
            "file that decides it — copied exactly, at least "
            f"{SHORTEST_QUOTE} characters. Say in `because` what that line does, in one or two "
            "sentences. For 'needs-a-check', the file and quote name the place the check belongs, "
            "which is the code that produces or validates the thing the rule is about."),
        "the_test": (
            "'already' means a page built by this harness today comes out the way the rule says, "
            "and the code you quote is what makes that so. A field that merely exists is not "
            "enough: if a writer could produce a page that breaks the rule and nothing would "
            "refuse it, the answer is 'needs-a-check'."),
        "what_will_be_refused": (
            "A quote that is not in the file you name, a file that is not inside the harness, an "
            "answer that is not one of the two, an empty reason, and any rule left unanswered. "
            "Your citation is checked against the file, so do not reconstruct a line from memory."),
        "answer_with": {"reader": str(reader), "model": REQUIRED_MODEL,
                        "reasoning": REQUIRED_REASONING,
                        "rules": [{"id": "c-0001", "answer": None, "file": None, "quote": None,
                                   "because": None}]},
        "rules": held["rules"],
    }


def read_answers(work: pathlib.Path, answers: pathlib.Path) -> dict:
    """One reader's answers, with every citation checked against the harness it names."""
    held = _open(work)
    harness = pathlib.Path(held["harness"]["root"])
    if not answers.is_file():
        raise Refused(f"answers: {answers} is not a file")
    try:
        value = json.loads(answers.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Refused(f"answers: {answers} could not be read as JSON ({exc})") from None
    reader = str(value.get("reader") or "")
    if reader not in [str(r) for r in READERS]:
        raise Refused(f"reader: {reader!r} — this step is read by readers "
                      f"{', '.join(str(r) for r in READERS)}")
    if value.get("model") != REQUIRED_MODEL or value.get("reasoning") != REQUIRED_REASONING:
        raise Refused(f"model: these answers say they came from {value.get('model')!r} at "
                      f"{value.get('reasoning')!r} reasoning, and this step is read by "
                      f"{REQUIRED_MODEL!r} at {REQUIRED_REASONING!r}")

    wanted = [r["id"] for r in held["rules"]]
    given: dict[str, dict] = {}
    wrong: list[str] = []
    for answer in value.get("rules") or []:
        rid = answer.get("id")
        if rid in given:
            wrong.append(f"{rid}: answered twice")
            continue
        given[rid] = answer
    missing = [rid for rid in wanted if rid not in given]
    extra = [rid for rid in given if rid not in wanted]
    if missing:
        wrong.append(f"{len(missing)} rule(s) were not answered, the first being "
                     f"{', '.join(missing[:5])}")
    if extra:
        wrong.append(f"{', '.join(extra[:5])} is not a rule in this landing")

    for rid in wanted:
        answer = given.get(rid)
        if answer is None:
            continue
        if answer.get("answer") not in ANSWERS:
            wrong.append(f"{rid}: answered {answer.get('answer')!r}, and the answers are "
                         f"{' and '.join(repr(k) for k in ANSWERS)}")
        if not (answer.get("because") or "").strip():
            wrong.append(f"{rid}: gives no reason for its answer")
        named = (answer.get("file") or "").strip()
        quote = (answer.get("quote") or "").strip()
        if not named:
            wrong.append(f"{rid}: names no file; an answer about the harness cites the harness")
            continue
        here = (harness / named).resolve()
        if not str(here).startswith(str(harness.resolve())):
            wrong.append(f"{rid}: {named} resolves outside the harness at {harness}")
            continue
        if not here.is_file():
            wrong.append(f"{rid}: {named} is not a file in the harness at {harness}")
            continue
        if len(quote) < SHORTEST_QUOTE:
            wrong.append(f"{rid}: the quote {quote!r} is shorter than {SHORTEST_QUOTE} characters; "
                         f"copy enough of the line to show which one decides it")
            continue
        body = here.read_text(encoding="utf-8", errors="replace")
        if quote not in body:
            wrong.append(f"{rid}: {quote[:60]!r} is not in {named}; a citation nobody can find is "
                         f"how a rule gets reported satisfied when it is not, so copy the line "
                         f"from the file rather than reconstructing it")
    if wrong:
        raise Refused("; ".join(wrong))

    return {
        "machinery": "alignment-machinery",
        "step": "landing",
        "reader": reader,
        "read_by": {"model": REQUIRED_MODEL, "reasoning": REQUIRED_REASONING},
        "harness": held["harness"],
        "answers": [{"id": rid, "answer": given[rid]["answer"],
                     "file": given[rid]["file"].strip(), "quote": given[rid]["quote"].strip(),
                     "because": given[rid]["because"].strip()} for rid in wanted],
        "answered_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }


def _readings(work: pathlib.Path) -> dict[str, dict]:
    found = {}
    for reader in READERS:
        target = work / f"landing-{reader}.json"
        if target.is_file():
            found[str(reader)] = json.loads(target.read_text(encoding="utf-8"))
    return found


def _rulings(work: pathlib.Path) -> dict:
    target = work / "landing-rulings.json"
    return json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}


def settle(work: pathlib.Path) -> dict:
    """What the three agree on, and what is for Kamen."""
    held = _open(work)
    readings = _readings(work)
    absent = [str(r) for r in READERS if str(r) not in readings]
    if absent:
        raise Refused(f"readers: reader {', '.join(absent)} have not answered this landing yet — "
                      f"all {len(READERS)} read it before anything is settled")
    agreed, for_kamen, split = [], [], {}
    for rule in held["rules"]:
        said = {r: next(a["answer"] for a in readings[r]["answers"] if a["id"] == rule["id"])
                for r in sorted(readings)}
        if len(set(said.values())) == 1:
            agreed.append(rule["id"])
        else:
            for_kamen.append(rule["id"])
            split[rule["id"]] = said
    counts = {kind: sum(1 for rid in agreed
                        if next(a["answer"] for a in readings["1"]["answers"] if a["id"] == rid)
                        == kind) for kind in ANSWERS}
    return {"rules": len(held["rules"]), "agreed": len(agreed), "where_they_agree": counts,
            "for_kamen": for_kamen, "the_split_answers": split}


def ask_owner(work: pathlib.Path) -> dict:
    """The disagreements: the rule and the three readings first, then a recommendation."""
    held = _open(work)
    readings = _readings(work)
    standing = settle(work)
    ruled = _rulings(work)
    by_id = {r["id"]: r for r in held["rules"]}
    waiting = []
    for rid in standing["for_kamen"]:
        if rid in ruled:
            continue
        waiting.append({
            "rule_id": rid,
            "the_rule": by_id[rid]["rule"],
            "what_stands_behind_it": {"clients": by_id[rid]["clients"],
                                      "passages": by_id[rid]["passages"],
                                      "changed_lines": by_id[rid]["lines"]},
            "the_three_readings": [
                {"reader": r,
                 "answer": next(a["answer"] for a in readings[r]["answers"] if a["id"] == rid),
                 "file": next(a["file"] for a in readings[r]["answers"] if a["id"] == rid),
                 "quote": next(a["quote"] for a in readings[r]["answers"] if a["id"] == rid),
                 "because": next(a["because"] for a in readings[r]["answers"] if a["id"] == rid)}
                for r in sorted(readings)],
            "then_a_recommendation": None,
            "then_what_it_means_either_way": None,
            "kamens_ruling": None,
        })
    return {
        "machinery": "alignment-machinery",
        "step": "landing",
        "the_harness": held["harness"],
        "the_question": "Does the harness already produce this, or must a check be built?",
        "the_answers": ANSWERS,
        "for_the_recommender": (
            "Fill then_a_recommendation with one plain sentence naming which answer you would "
            "choose and why, and then_what_it_means_either_way with what follows for the work in "
            "each case. Every reading carries the file it read and the line it quoted; weigh those "
            "lines, not the confidence of the prose around them. A rule already satisfied costs "
            "nothing and a rule wrongly called satisfied is silently dropped, so say plainly when "
            "the citations do not settle it. Do not change anything above those fields."),
        "recommended_by": {"model": RECOMMENDER},
        "waiting_on_kamen": waiting,
    }


def rule_landing(work: pathlib.Path, rid: str, choice: str, because: str) -> dict:
    standing = settle(work)
    if rid not in standing["for_kamen"]:
        raise Refused(f"{rid}: the readers did not disagree about it, so there is nothing for Kamen "
                      f"to rule; a settled answer is not overturned by a later ruling")
    if choice not in ANSWERS:
        raise Refused(f"choice: {choice!r} — the answers are "
                      f"{', '.join(f'{k!r} ({v})' for k, v in ANSWERS.items())}")
    if not because.strip():
        raise Refused("because: a ruling is kept in Kamen's own words, so it cannot be empty")
    ruled = _rulings(work)
    if rid in ruled and ruled[rid]["answer"] != choice:
        raise Refused(f"{rid}: already carries his ruling of {ruled[rid]['answer']!r} because "
                      f"{ruled[rid]['because']!r}; a ruling is never written over")
    ruled[rid] = {"answer": choice, "because": because.strip(),
                  "ruled_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}
    (work / "landing-rulings.json").write_text(
        json.dumps(ruled, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": "ruled", "rule": rid, "answer": choice, "because": because.strip(),
            "still_waiting": [r for r in standing["for_kamen"] if r not in ruled]}


def finish(work: pathlib.Path) -> dict:
    """Where every approved rule lands, once nothing is unsettled."""
    held = _open(work)
    readings = _readings(work)
    standing = settle(work)
    ruled = _rulings(work)
    unruled = [r for r in standing["for_kamen"] if r not in ruled]
    if unruled:
        raise Refused(
            f"waiting on Kamen: {', '.join(unruled)} — the readers disagreed about "
            f"{len(unruled)} rule(s) and no model casts that vote; put them to him with "
            f"`ask-owner` and keep his answer with `rule`")

    landed = []
    for rule in held["rules"]:
        rid = rule["id"]
        if rid in ruled:
            answer, how, because = ruled[rid]["answer"], THE_OWNERS_RULING, ruled[rid]["because"]
            citations = [{"reader": r, "file": a["file"], "quote": a["quote"]}
                         for r in sorted(readings)
                         for a in readings[r]["answers"] if a["id"] == rid]
        else:
            first = next(a for a in readings["1"]["answers"] if a["id"] == rid)
            answer, how, because = first["answer"], f"{len(READERS)} readers agreeing", \
                first["because"]
            citations = [{"reader": r, "file": a["file"], "quote": a["quote"]}
                         for r in sorted(readings)
                         for a in readings[r]["answers"] if a["id"] == rid]
        landed.append({"id": rid, "rule": rule["rule"], "in_his_words": rule["in_his_words"],
                       "answer": answer, "settled_by": how, "because": because,
                       "clients": rule["clients"], "passages": rule["passages"],
                       "lines": rule["lines"], "cited": citations})

    counts = {
        "rules": len(held["rules"]),
        "already": sum(1 for r in landed if r["answer"] == "already"),
        "needs_a_check": sum(1 for r in landed if r["answer"] == "needs-a-check"),
        "ruled_by_kamen": len(ruled),
        "lines_needing_a_check": sum(r["lines"] for r in landed
                                     if r["answer"] == "needs-a-check"),
        "lines_already_true": sum(r["lines"] for r in landed if r["answer"] == "already"),
        "files_named": len({c["file"] for r in landed for c in r["cited"]}),
    }
    adds_up(counts)
    return {
        "machinery": "alignment-machinery",
        "step": "landing",
        "landing_version": LANDING_VERSION,
        "harness": held["harness"],
        "read_by": {"readers": len(READERS), "model": REQUIRED_MODEL,
                    "reasoning": REQUIRED_REASONING},
        "gathered_from": held["gathered_from"],
        "counts": counts,
        "landed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "landed": landed,
        "next_step": "apply the changes the harness does not yet produce",
    }


def adds_up(counts: dict) -> None:
    """Every rule carries one answer and every answer carries a citation, or nothing is written."""
    wrong = []
    if counts["already"] + counts["needs_a_check"] != counts["rules"]:
        wrong.append(f"{counts['rules']} rules and "
                     f"{counts['already'] + counts['needs_a_check']} carry an answer "
                     f"({counts['already']} already, {counts['needs_a_check']} needing a check)")
    if counts["rules"] and not counts["files_named"]:
        wrong.append("no answer names a file, so nothing here was read against the harness")
    if wrong:
        raise Refused("the landing does not add up, so it was not written — " + "; ".join(wrong))


def show(work: pathlib.Path) -> dict:
    target = work / "landed.json"
    if not target.is_file():
        held = _open(work)
        readings = _readings(work)
        return {"harness": held["harness"], "rules": len(held["rules"]),
                "readers_who_have_answered": sorted(readings),
                "next_step": ("run `land.py finish`" if len(readings) == len(READERS)
                              else f"ask the readers still to answer")}
    record = json.loads(target.read_text(encoding="utf-8"))
    return {"harness": record["harness"], "counts": record["counts"],
            "needs_a_check": [r["id"] for r in record["landed"]
                              if r["answer"] == "needs-a-check"],
            "next_step": record["next_step"]}


def write(work: pathlib.Path, filename: str, record: dict, same_on: tuple[str, ...],
          stamp: str) -> pathlib.Path:
    target = work / filename
    if target.is_file():
        standing = json.loads(target.read_text(encoding="utf-8"))
        if not all(standing.get(k) == record.get(k) for k in same_on):
            raise Refused(f"work: {work} already holds {filename} and this one differs from it; a "
                          f"run's record is never written over — give a fresh directory")
        record = dict(record, **{stamp: standing.get(stamp, record[stamp]),
                                 f"re_{stamp}": _dt.datetime.now(
                                     _dt.timezone.utc).isoformat(timespec="seconds")})
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="land.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    for action, help_text in (
            ("open", "pin the rules to the harness and the commit they will be read at"),
            ("ask", "one reader's questions, blind to the other readers"),
            ("read", "keep one reader's answers, every citation checked"),
            ("settle", "what the three agree on, and what is for Kamen"),
            ("ask-owner", "the disagreements, the readings first, then a recommendation"),
            ("rule", "keep Kamen's ruling on one disagreement, in his words"),
            ("finish", "write where every rule lands, once nothing is unsettled"),
            ("show", "what this landing holds, in a few lines")):
        step = sub.add_parser(action, help=help_text)
        step.add_argument("--work", required=True, help="the run directory the ruling wrote")
        if action == "open":
            step.add_argument("--harness", required=True, help="the harness repository's root")
        if action == "ask":
            step.add_argument("--reader", required=True, type=int, choices=list(READERS))
        if action == "read":
            step.add_argument("--answers", required=True, help="one reader's filled questions")
        if action == "rule":
            step.add_argument("--id", required=True, help="the rule he is ruling on")
            step.add_argument("--choice", required=True, help="already or needs-a-check")
            step.add_argument("--because", required=True, help="his own words")
    args = parser.parse_args(argv)
    work = pathlib.Path(args.work).resolve()

    try:
        if args.action == "open":
            record = open_landing(work, pathlib.Path(args.harness).resolve())
            target = write(work, "landing.json", record, ("rules", "harness"), "opened_at")
            print(json.dumps({"status": "opened", "landing": str(target),
                              "harness": record["harness"], "rules": len(record["rules"]),
                              "next_step": record["next_step"]}, indent=2, ensure_ascii=False))
        elif args.action == "ask":
            print(json.dumps(ask(work, args.reader), indent=2, ensure_ascii=False))
        elif args.action == "read":
            record = read_answers(work, pathlib.Path(args.answers).resolve())
            target = write(work, f"landing-{record['reader']}.json", record, ("answers",),
                           "answered_at")
            still = [str(r) for r in READERS if not (work / f"landing-{r}.json").is_file()]
            print(json.dumps({"status": "read", "reader": record["reader"],
                              "answers": str(target), "rules": len(record["answers"]),
                              "readers_still_to_read": still}, indent=2, ensure_ascii=False))
        elif args.action == "settle":
            print(json.dumps(settle(work), indent=2, ensure_ascii=False))
        elif args.action == "ask-owner":
            print(json.dumps(ask_owner(work), indent=2, ensure_ascii=False))
        elif args.action == "rule":
            print(json.dumps(rule_landing(work, args.id, args.choice, args.because),
                             indent=2, ensure_ascii=False))
        elif args.action == "finish":
            record = finish(work)
            target = write(work, "landed.json", record, ("landed", "counts"), "landed_at")
            print(json.dumps({"status": "landed", "landed": str(target),
                              "counts": record["counts"], "next_step": record["next_step"]},
                             indent=2, ensure_ascii=False))
        else:
            print(json.dumps(show(work), indent=2, ensure_ascii=False))
    except Refused as exc:
        print(json.dumps({"status": "refused", "because": str(exc)}, indent=2, ensure_ascii=False),
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
