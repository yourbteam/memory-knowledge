#!/usr/bin/env python3
"""The fifth step of alignment-machinery: put every named change to the owner, one at a time.

The distillation wrote a list of distinct changes to the way pages are built, each carrying the
passages that show it. Not one of them is a rule yet. Three models had a hand in that list -- one
proposed the changes, three read every passage against them, one wrote advice on the few they
differed on -- and the whole machinery exists because a change to how every client's page is built
is not a thing a model decides.

    rule.py next    --work <run>                          -> the next change, with its evidence
    rule.py answer  --work <run> --change <id> --choice approved|rejected|reworded \\
                    --because "<his words>" [--wording "<his sentence>"]
    rule.py show    --work <run>                          -> what is answered and what is not
    rule.py finish  --work <run>                          -> the ruled list, once none is unanswered

This step casts no vote and writes no answer of its own. It presents one change with the client's
words and ours underneath it, takes back what the owner said, and keeps it verbatim. A change he
has not answered stays a candidate and is reported as one; `finish` refuses while any remain.

A ruling is never written over. The same answer may be recorded again -- a command re-run, a
session resumed -- but a different one is refused, naming the answer that stands and what it says.
That is the difference between a record of what he decided and a record of the last thing anybody
typed.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from invoke import Refused  # noqa: E402  (one refusal shape for the whole machinery)

RULING_VERSION = 1
#: what the owner may answer, and what each answer means for the work
ANSWERS = {
    "approved": "this is how pages of this kind are built from now on, in the words as written",
    "rejected": "this is not a rule; the lines behind it were this client's wording after all",
    "reworded": "the change is right and the sentence is not; his wording replaces it",
}
#: how many of a change's own passages are shown with it, most recent client first
SHOW_AT_MOST = 6


def _named(work: pathlib.Path) -> dict:
    """The written list of changes, refused unless the distillation finished it."""
    target = work / "changes.json"
    if not target.is_file():
        raise Refused(f"work: {work} holds no changes.json — this step rules on a list the "
                      f"distillation finished; run `distil.py name` first")
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Refused(f"work: {target} could not be read as JSON ({exc})") from None
    if value.get("machinery") != "alignment-machinery" or value.get("step") != "distillation":
        raise Refused(f"work: {target} was not written by this machinery's distillation")
    if not value.get("changes"):
        raise Refused(f"work: {target} names no changes, so there is nothing to rule on")
    return value


def _rulings(work: pathlib.Path) -> dict:
    target = work / "rulings.json"
    return json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}


def _evidence(change: dict) -> list[dict]:
    """A few of the passages behind a change, spread across the clients that show it."""
    by_client: dict[str, list[dict]] = {}
    for shown in change["shown_by"]:
        by_client.setdefault(shown["client"], []).append(shown)
    picked: list[dict] = []
    while len(picked) < SHOW_AT_MOST and any(by_client.values()):
        for client in sorted(by_client):
            if by_client[client] and len(picked) < SHOW_AT_MOST:
                picked.append(by_client[client].pop(0))
    return [{"client": p["client"], "where_it_sits": p["section"],
             "what_they_wrote": p["theirs"], "what_we_wrote": p["ours"],
             "settled_by": p["settled_by"]} for p in picked]


def nxt(work: pathlib.Path) -> dict:
    """The next change he has not answered, with the evidence he is answering on."""
    named = _named(work)
    ruled = _rulings(work)
    waiting = [c for c in named["changes"] if c["id"] not in ruled]
    if not waiting:
        return {"status": "nothing waiting", "changes": len(named["changes"]),
                "answered": len(ruled), "next_step": "run `rule.py finish`"}
    change = max(waiting, key=lambda c: (c["lines"], c["passages"]))
    return {
        "machinery": "alignment-machinery",
        "step": "ruling",
        "the_question": "Is this how pages of this kind should be built from now on?",
        "the_answers": ANSWERS,
        "answered_so_far": f"{len(ruled)} of {len(named['changes'])}",
        "the_change": change["change"],
        "change_id": change["id"],
        "why_it_is_one_change": change["why_it_is_one_change"],
        "what_stands_behind_it": {"clients": change["clients"], "passages": change["passages"],
                                  "changed_lines": change["lines"]},
        "the_evidence": _evidence(change),
        "how_to_answer": (
            "`rule.py answer --change <id> --choice approved|rejected|reworded --because "
            "\"<your words>\"`, and with `reworded` add `--wording \"<your sentence>\"`. Your "
            "words are kept as you write them; nothing here writes an answer for you."),
    }


def answer(work: pathlib.Path, change_id: str, choice: str, because: str,
           wording: str | None) -> dict:
    """One answer, in his words, kept and never written over."""
    named = _named(work)
    known = {c["id"]: c for c in named["changes"]}
    if change_id not in known:
        raise Refused(f"change: {change_id!r} is not in this list; the changes are "
                      f"{', '.join(sorted(known))}")
    if choice not in ANSWERS:
        raise Refused(f"choice: {choice!r} — the answers are "
                      f"{', '.join(f'{k!r} ({v})' for k, v in ANSWERS.items())}")
    if not because.strip():
        raise Refused("because: a ruling is kept in Kamen's own words, so it cannot be empty")
    if choice == "reworded" and not (wording or "").strip():
        raise Refused(f"wording: {choice!r} says the sentence is wrong and his replaces it, so the "
                      f"replacement sentence is required; the sentence as it stands is "
                      f"{known[change_id]['change']!r}")
    if choice != "reworded" and (wording or "").strip():
        raise Refused(f"wording: a replacement sentence was given with {choice!r}, which keeps the "
                      f"sentence as written; answer 'reworded' to replace it, or drop the wording")

    standing = _rulings(work)
    fresh = {"answer": choice, "because": because.strip(),
             "wording": wording.strip() if choice == "reworded" else None}
    if change_id in standing:
        held = standing[change_id]
        same = all(held.get(k) == fresh[k] for k in ("answer", "because", "wording"))
        if not same:
            raise Refused(
                f"{change_id}: already carries his ruling of {held['answer']!r} because "
                f"{held['because']!r}; a ruling is never written over. If the answer has genuinely "
                f"changed, that is a new ruling on a fresh directory, not an edit to this one")
        fresh = dict(held, re_answered_at=_dt.datetime.now(
            _dt.timezone.utc).isoformat(timespec="seconds"))
    else:
        fresh["answered_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        fresh["it_stood_on"] = {"clients": known[change_id]["clients"],
                                "passages": known[change_id]["passages"],
                                "changed_lines": known[change_id]["lines"]}
        fresh["the_sentence_he_answered"] = known[change_id]["change"]
    standing[change_id] = fresh
    (work / "rulings.json").write_text(
        json.dumps(standing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": "answered", "change": change_id, "answer": choice,
            "because": fresh["because"],
            "still_waiting": [c["id"] for c in named["changes"] if c["id"] not in standing]}


def show(work: pathlib.Path) -> dict:
    named = _named(work)
    ruled = _rulings(work)
    counts = {kind: sum(1 for r in ruled.values() if r["answer"] == kind) for kind in ANSWERS}
    return {
        "changes": len(named["changes"]),
        "answered": len(ruled),
        "still_candidates": [c["id"] for c in named["changes"] if c["id"] not in ruled],
        "his_answers": counts,
        "lines_behind_the_approved": sum(
            c["lines"] for c in named["changes"]
            if ruled.get(c["id"], {}).get("answer") in ("approved", "reworded")),
        "next_step": ("run `rule.py next`" if len(ruled) < len(named["changes"])
                      else "run `rule.py finish`"),
    }


def finish(work: pathlib.Path) -> dict:
    """The ruled list, once every change carries his answer."""
    named = _named(work)
    ruled = _rulings(work)
    waiting = [c["id"] for c in named["changes"] if c["id"] not in ruled]
    if waiting:
        raise Refused(
            f"waiting on Kamen: {', '.join(waiting)} — {len(waiting)} change(s) have no answer and "
            f"a change nobody ruled on is still a candidate, not a rule; put them to him with "
            f"`rule.py next` and keep his answers with `rule.py answer`")

    rules = []
    for change in named["changes"]:
        his = ruled[change["id"]]
        if his["answer"] == "rejected":
            continue
        rules.append({
            "id": change["id"],
            "rule": his["wording"] if his["answer"] == "reworded" else change["change"],
            "in_his_words": his["answer"] == "reworded",
            "he_said": his["because"],
            "answered_at": his["answered_at"],
            "clients": change["clients"],
            "passages": change["passages"],
            "lines": change["lines"],
            "shown_by": change["shown_by"],
        })
    counts = {
        "changes_put_to_him": len(named["changes"]),
        "rules": len(rules),
        "approved_as_written": sum(1 for r in ruled.values() if r["answer"] == "approved"),
        "approved_in_his_wording": sum(1 for r in ruled.values() if r["answer"] == "reworded"),
        "rejected": sum(1 for r in ruled.values() if r["answer"] == "rejected"),
        "lines_behind_the_rules": sum(r["lines"] for r in rules),
        "lines_put_to_him": sum(c["lines"] for c in named["changes"]),
    }
    adds_up(counts)
    return {
        "machinery": "alignment-machinery",
        "step": "ruling",
        "ruling_version": RULING_VERSION,
        "ruled_by": "Kamen Kamenov",
        "gathered_from": named["gathered_from"],
        "counts": counts,
        "ruled_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "rules": rules,
        "he_rejected": [{"id": cid, "sentence": next(c["change"] for c in named["changes"]
                                                     if c["id"] == cid),
                         "he_said": r["because"]}
                        for cid, r in sorted(ruled.items()) if r["answer"] == "rejected"],
        "next_step": "gate",
    }


def adds_up(counts: dict) -> None:
    """Every change he was shown carries one of his answers, or nothing is written."""
    answered = (counts["approved_as_written"] + counts["approved_in_his_wording"]
                + counts["rejected"])
    wrong = []
    if answered != counts["changes_put_to_him"]:
        wrong.append(f"{counts['changes_put_to_him']} changes were put to him and {answered} carry "
                     f"an answer ({counts['approved_as_written']} approved, "
                     f"{counts['approved_in_his_wording']} reworded, {counts['rejected']} rejected)")
    if counts["rules"] != counts["approved_as_written"] + counts["approved_in_his_wording"]:
        wrong.append(f"{counts['rules']} rules were written from "
                     f"{counts['approved_as_written'] + counts['approved_in_his_wording']} "
                     f"approvals")
    if counts["lines_behind_the_rules"] > counts["lines_put_to_him"]:
        wrong.append(f"the rules claim {counts['lines_behind_the_rules']} lines and only "
                     f"{counts['lines_put_to_him']} were put to him")
    if wrong:
        raise Refused("the ruling does not add up, so it was not written — " + "; ".join(wrong))


def write(work: pathlib.Path, record: dict) -> pathlib.Path:
    target = work / "rules.json"
    if target.is_file():
        standing = json.loads(target.read_text(encoding="utf-8"))
        if not all(standing.get(k) == record.get(k) for k in ("rules", "counts", "he_rejected")):
            raise Refused(f"work: {work} already holds a ruled list of "
                          f"{standing.get('counts', {}).get('rules')} rule(s), and this one differs "
                          f"from it; a run's record is never written over — give a fresh directory")
        record = dict(record, ruled_at=standing.get("ruled_at", record["ruled_at"]),
                      re_ruled_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"))
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rule.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    for action, help_text in (
            ("next", "the next change he has not answered, with its evidence"),
            ("answer", "keep his answer on one change, in his words"),
            ("show", "what is answered and what is still a candidate"),
            ("finish", "write the ruled list, once none is unanswered")):
        step = sub.add_parser(action, help=help_text)
        step.add_argument("--work", required=True, help="the run directory the distillation wrote")
        if action == "answer":
            step.add_argument("--change", required=True, help="the change he is answering")
            step.add_argument("--choice", required=True, help="approved, rejected or reworded")
            step.add_argument("--because", required=True, help="his own words")
            step.add_argument("--wording", help="his sentence, when he reworded it")
    args = parser.parse_args(argv)
    work = pathlib.Path(args.work).resolve()

    try:
        if args.action == "next":
            print(json.dumps(nxt(work), indent=2, ensure_ascii=False))
        elif args.action == "answer":
            print(json.dumps(answer(work, args.change, args.choice, args.because, args.wording),
                             indent=2, ensure_ascii=False))
        elif args.action == "show":
            print(json.dumps(show(work), indent=2, ensure_ascii=False))
        else:
            record = finish(work)
            target = write(work, record)
            print(json.dumps({"status": "ruled", "rules": str(target),
                              "counts": record["counts"], "next_step": record["next_step"]},
                             indent=2, ensure_ascii=False))
    except Refused as exc:
        print(json.dumps({"status": "refused", "because": str(exc)}, indent=2, ensure_ascii=False),
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
