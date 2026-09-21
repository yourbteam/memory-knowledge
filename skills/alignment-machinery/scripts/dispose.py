#!/usr/bin/env python3
"""The third step of alignment-machinery: say what each thing the client changed actually is.

The register holds every difference between the two documents, grouped into the passages they
arrived in. This step puts each passage to three readers who cannot see each other, and keeps their
answers to one question:

    is this the client's own wording here, or is it evidence of a rule for every page?

    dispose.py ask     --work <run> [--reader 1|2|3]     -> the questions, for one reader
    dispose.py read    --work <run> --answers <file>     -> keep one reader's answers
    dispose.py settle  --work <run>                      -> what agrees, and what is for Kamen
    dispose.py ask-owner  --work <run>                   -> the splits, her words first
    dispose.py rule    --work <run> --id <passage> --choice <answer> --because "<his words>"
    dispose.py show    --work <run>                      -> what it holds, in a few lines

Three readers, and no model casts the deciding vote. Where all three agree the answer stands with
its three reasons. Where they split, the passage goes to Kamen: he sees the client's words and ours
first, then all three readings, then one plain recommendation written by a different model that did
no judging — in that order, so he judges the passage rather than the advice. A recommendation that
arrives before the evidence is how a ruling becomes a rubber stamp.

Code does everything except the judgement: it presents the passage, records each answer against the
difference it answers, refuses while any passage is unanswered or any split is unruled, and checks
every answer against the register the model did not write.

Nothing here decides that anything is a rule. The candidates are named in the step after this.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from invoke import Refused  # noqa: E402  (one refusal shape for the whole machinery)

DISPOSITION_VERSION = 2

#: Three, because two can only disagree — they cannot show which way a passage leans. Measured on
#: B Team's return of 20 September: two independent readings of the same 53 passages agreed on 52
#: and split on one, so the queue this puts to Kamen is small and the splits in it are real.
READERS = (1, 2, 3)

#: The two answers, and what each one means. A third option would be a way of not answering.
ANSWERS = {
    "clients-own-wording": "how this client wants this thing said, on this page, for this company; "
                           "it says nothing about how other clients' pages should be written",
    "evidence-of-a-rule": "a way every page of this kind should be written, for every client; "
                          "our way of producing these pages has to change, not just this page",
}

#: Judged on 21 September 2026 against the classes the record itself named for Maria's Vivacom
#: return: two models were run blind over the same eighteen real passages and neither lost a rule
#: class, so the choice was made on cost, by Kamen. Recorded here because an answer file produced
#: by a different model is refused rather than quietly accepted.
REQUIRED_MODEL = "claude-opus-5"
REQUIRED_REASONING = "high"

_SPACE = re.compile(r"\s+")


def _collapsed(text: str) -> str:
    return _SPACE.sub(" ", text or "").strip().lower()


def _held(work: pathlib.Path) -> dict:
    record = work / "differences.json"
    if not record.is_file():
        raise Refused(f"work: {work} holds no differences.json — the disposition runs on a register "
                      f"the register step wrote; run `register.py hold` first")
    held = json.loads(record.read_text(encoding="utf-8"))
    for field in ("differences", "passages", "counts", "client", "returned_label", "our_label"):
        if field not in held:
            raise Refused(f"work: {record} is missing {field} — it was not written by this "
                          f"machinery's register, or it was written by hand")
    return held


def ask(work: pathlib.Path, reader: int) -> dict:
    """The questions, one per passage, in the register's own order, for one reader.

    Each reader gets the same question and sees no other reader's answers. That is the whole of the
    method: three readings of the same words, kept apart, so a wobble shows as a split instead of
    settling itself.
    """
    if reader not in READERS:
        raise Refused(f"reader: {reader} — this step is read by readers {', '.join(map(str, READERS))}, "
                      f"each one blind to the others")
    held = _held(work)
    differences = {d["id"]: d for d in held["differences"]}
    questions = []
    for passage in held["passages"]:
        mine = [differences[i] for i in passage["differences"]]
        questions.append({
            "passage": passage["id"],
            "kind": passage["kind"],
            "section": passage["section"],
            "differences": passage["differences"],
            "ours": [d["ours"] for d in mine if d["ours"]],
            "theirs": [d["theirs"] for d in mine if d["theirs"]],
            "answer": None,
            "reason": None,
            "quote": None,
        })
    return {
        "machinery": "alignment-machinery",
        "step": "disposition",
        "disposition_version": DISPOSITION_VERSION,
        "reader": reader,
        "client": held["client"],
        "returned_label": held["returned_label"],
        "our_label": held["our_label"],
        "ours_is": held.get("ours_is"),
        "the_question": "For each passage: is this the client's own wording here, or is it evidence "
                        "of a rule that should hold on every page we produce of this kind?",
        "the_answers": ANSWERS,
        "how_to_answer": "Fill answer, reason and quote on every passage and pass the file back with "
                         "`dispose.py record --answers <file>`. The quote must be words that appear "
                         "in that passage's own ours or theirs — it is what ties the judgement to the "
                         "line it judged. Judge the passage; the step after this reads the whole set, "
                         "so a rule does not have to be carried by every line that shows it. You are "
                         "one of three readers answering these same passages separately; answer what "
                         "you see, not what you think the others will say.",
        "answer_with": {"model": REQUIRED_MODEL, "reasoning": REQUIRED_REASONING},
        "the_test": "Take the change and remove everything particular to this client — their name, "
                    "their campaign, their products, their people. If what is left still says how a "
                    "page should be built, it is evidence of a rule. If nothing is left, it is this "
                    "client's own wording. Apply that same test to every passage.",
        "passages": questions,
    }


def read_answers(work: pathlib.Path, answers_path: pathlib.Path) -> dict:
    """One reader's answers: every passage answered, every answer tied to words the register holds."""
    held = _held(work)
    try:
        filled = json.loads(answers_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Refused(f"answers: {answers_path} could not be read as JSON ({exc})") from None

    reader = filled.get("reader") if isinstance(filled, dict) else None
    if reader not in READERS:
        raise Refused(f"reader: {reader!r} — an answer file says which of the {len(READERS)} readers "
                      f"wrote it, so three readings cannot be mistaken for one")
    declared = filled.get("answer_with") if isinstance(filled, dict) else None
    if not isinstance(declared, dict) or declared.get("model") != REQUIRED_MODEL \
            or declared.get("reasoning") != REQUIRED_REASONING:
        raise Refused(
            f"answer_with: {declared!r} — this step's judgement is made by {REQUIRED_MODEL} at "
            f"{REQUIRED_REASONING} reasoning, and the answer file says which produced it. Answer "
            f"with that model and declare it, or the record would claim a judgement nothing made")

    given = {}
    for entry in (filled.get("passages") or []):
        if not isinstance(entry, dict) or "passage" not in entry:
            raise Refused(f"passages: {entry!r} has no 'passage' — keep each passage's own name on it")
        if entry["passage"] in given:
            raise Refused(f"passages: {entry['passage']} answered twice — one answer per passage")
        given[str(entry["passage"])] = entry

    by_id = {p["id"]: p for p in held["passages"]}
    differences = {d["id"]: d for d in held["differences"]}
    missing = [p for p in by_id if p not in given]
    unknown = [p for p in given if p not in by_id]
    refusals = []
    if missing:
        refusals.append(f"unanswered: {', '.join(sorted(missing)[:8])}"
                        + (f" and {len(missing) - 8} more" if len(missing) > 8 else "")
                        + f" — {len(missing)} of {len(by_id)} passages carry no answer, and a register "
                          f"is dispositioned whole or not at all")
    if unknown:
        refusals.append(f"not in this register: {', '.join(sorted(unknown)[:8])} — an answer names a "
                        f"passage the register does not hold")

    marks = {}
    for pid, entry in sorted(given.items()):
        if pid not in by_id:
            continue
        answer = str(entry.get("answer") or "")
        if answer not in ANSWERS:
            refusals.append(f"{pid}: answer {entry.get('answer')!r} — answer with one of "
                            f"{', '.join(ANSWERS)}")
            continue
        reason = str(entry.get("reason") or "").strip()
        if len(reason) < 12:
            refusals.append(f"{pid}: reason {entry.get('reason')!r} — say in one sentence why this is "
                            f"{answer}; a mark with no reason cannot be weighed by the person who rules")
            continue
        quote = _collapsed(str(entry.get("quote") or ""))
        words = " ".join(_collapsed(differences[i].get("ours") or "") + " "
                         + _collapsed(differences[i].get("theirs") or "")
                         for i in by_id[pid]["differences"])
        # A few words, unless the passage itself is shorter than that: a calendar cell holding one
        # code is the whole of what there is to quote, and refusing it would be refusing the client's
        # own page for being terse.
        shortest = min((len(_collapsed(differences[i].get(side) or "")) or 999)
                       for i in by_id[pid]["differences"] for side in ("ours", "theirs"))
        if len(quote) < min(8, shortest):
            refusals.append(f"{pid}: quote {entry.get('quote')!r} — quote the words being judged, at "
                            f"least a few of them, from this passage's own ours or theirs; where the "
                            f"passage holds fewer than that, quote all of it")
            continue
        if quote not in words:
            refusals.append(f"{pid}: the quote {entry.get('quote')!r} is not in this passage — quote "
                            f"the words the register holds for it, so the judgement can be traced to "
                            f"the line it judged")
            continue
        marks[pid] = {"answer": answer, "reason": reason, "quote": str(entry.get("quote")).strip()}

    if refusals:
        raise Refused(" | ".join(refusals))

    return {"reader": reader, "client": held["client"], "passages": marks,
            "read_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}


def _readings(work: pathlib.Path) -> dict[int, dict]:
    """What each reader has said so far, read back from its own file."""
    out = {}
    for reader in READERS:
        path = work / f"reading-{reader}.json"
        if path.is_file():
            out[reader] = json.loads(path.read_text(encoding="utf-8"))
    return out


def settle(work: pathlib.Path) -> dict:
    """Where the three agree, and where they do not. No model casts the deciding vote."""
    held = _held(work)
    readings = _readings(work)
    missing = [r for r in READERS if r not in readings]
    if missing:
        raise Refused(f"readers: {', '.join('reader ' + str(r) for r in missing)} have not read this "
                      f"register yet — all {len(READERS)} read it before anything is settled")
    agreed, split = {}, {}
    for passage in held["passages"]:
        pid = passage["id"]
        answers = {r: readings[r]["passages"][pid]["answer"] for r in READERS}
        if len(set(answers.values())) == 1:
            agreed[pid] = {"answer": answers[READERS[0]],
                           "readings": {str(r): readings[r]["passages"][pid] for r in READERS}}
        else:
            split[pid] = {"answers": {str(r): answers[r] for r in READERS},
                          "readings": {str(r): readings[r]["passages"][pid] for r in READERS}}
    return {"agreed": agreed, "split": split, "held": held}


def _rulings(work: pathlib.Path) -> dict:
    """Kamen's rulings on the splits, in his own words, read back from their own file."""
    path = work / "rulings.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def ask_owner(work: pathlib.Path) -> dict:
    """The splits, put to Kamen in the order that lets him judge the passage rather than the advice.

    Her words first, then all three readings, then one recommendation from a model that did no
    judging. The order is the point: a recommendation read before the evidence is a ruling made by
    the recommender.
    """
    outcome = settle(work)
    held, ruled = outcome["held"], _rulings(work)
    differences = {d["id"]: d for d in held["differences"]}
    passages = {p["id"]: p for p in held["passages"]}
    waiting = []
    for pid, split in outcome["split"].items():
        if pid in ruled:
            continue
        mine = [differences[i] for i in passages[pid]["differences"]]
        waiting.append({
            "passage": pid,
            "where_it_sits": passages[pid]["section"],
            "what_she_wrote": [d["theirs"] for d in mine if d["theirs"]],
            "what_we_wrote": [d["ours"] for d in mine if d["ours"]],
            "the_three_readings": [
                {"reader": r, "answer": split["readings"][r]["answer"],
                 "because": split["readings"][r]["reason"], "quoting": split["readings"][r]["quote"]}
                for r in sorted(split["readings"])],
            "then_a_recommendation": None,
            "then_what_it_means_either_way": None,
            "kamens_ruling": None,
        })
    return {
        "machinery": "alignment-machinery",
        "step": "disposition",
        "client": held["client"],
        "returned_label": held["returned_label"],
        "the_question": "Is this the client's own wording here, or evidence of a rule for every page?",
        "the_answers": ANSWERS,
        "for_the_recommender": "Fill then_a_recommendation with one plain sentence naming which answer "
                               "you would choose and why, and then_what_it_means_either_way with what "
                               "follows for the work in each case. Write for someone who has not read "
                               "the page. Do not change anything above those fields: what she wrote, "
                               "what we wrote and the three readings are the evidence, and they come "
                               "first so the ruling is made on them.",
        "recommended_by": {"model": "claude-fable-5-1"},
        "waiting_on_kamen": waiting,
    }


def rule(work: pathlib.Path, passage: str, choice: str, because: str) -> dict:
    """Keep Kamen's ruling on one split, in his words."""
    outcome = settle(work)
    if passage not in outcome["split"]:
        raise Refused(f"{passage}: the three readers agree on it, so there is nothing to rule; "
                      f"rulings are kept only where they split")
    if choice not in ANSWERS:
        raise Refused(f"choice: {choice!r} — rule with one of {', '.join(ANSWERS)}")
    words = (because or "").strip()
    if len(words) < 3:
        raise Refused(f"because: {because!r} — keep the ruling in his own words, however few")
    ruled = _rulings(work)
    ruled[passage] = {"answer": choice, "because": words,
                      "ruled_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}
    (work / "rulings.json").write_text(json.dumps(ruled, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    return {"status": "ruled", "passage": passage, "answer": choice, "because": words,
            "still_waiting": sorted(set(outcome["split"]) - set(ruled))}


def finish(work: pathlib.Path) -> dict:
    """The disposition, once the three agree or Kamen has ruled on every split."""
    outcome = settle(work)
    held, ruled = outcome["held"], _rulings(work)
    unruled = sorted(set(outcome["split"]) - set(ruled))
    if unruled:
        raise Refused(f"waiting on Kamen: {', '.join(unruled[:8])}"
                      + (f" and {len(unruled) - 8} more" if len(unruled) > 8 else "")
                      + f" — the readers split on {len(unruled)} passage(s) and no model casts that "
                        f"vote; put them to him with `ask-owner` and keep his answer with `rule`")
    marks = {}
    for pid, agreed in outcome["agreed"].items():
        first = agreed["readings"][str(READERS[0])]
        marks[pid] = {"answer": agreed["answer"], "settled_by": "three readers agreeing",
                      "reason": first["reason"], "quote": first["quote"],
                      "readings": agreed["readings"]}
    for pid, split in outcome["split"].items():
        marks[pid] = {"answer": ruled[pid]["answer"], "settled_by": "Kamen's ruling",
                      "reason": ruled[pid]["because"],
                      "quote": split["readings"][str(READERS[0])]["quote"],
                      "readings": split["readings"]}
    marked = [{
        "id": d["id"], "passage": d["passage"], "kind": d["kind"], "section": d["section"],
        "ours": d["ours"], "theirs": d["theirs"],
        "disposition": marks[d["passage"]]["answer"],
        "settled_by": marks[d["passage"]]["settled_by"],
        "reason": marks[d["passage"]]["reason"],
        "quote": marks[d["passage"]]["quote"],
    } for d in held["differences"]]
    counts = {
        "differences": len(marked),
        "passages": len(marks),
        "evidence-of-a-rule": sum(1 for m in marked if m["disposition"] == "evidence-of-a-rule"),
        "clients-own-wording": sum(1 for m in marked if m["disposition"] == "clients-own-wording"),
        "passages_evidence-of-a-rule": sum(1 for m in marks.values()
                                           if m["answer"] == "evidence-of-a-rule"),
        "passages_the_readers_agreed": len(outcome["agreed"]),
        "passages_kamen_ruled": len(outcome["split"]),
    }
    check(counts, held["counts"])
    return {
        "machinery": "alignment-machinery",
        "step": "disposition",
        "disposition_version": DISPOSITION_VERSION,
        "client": held["client"],
        "returned_label": held["returned_label"],
        "our_label": held["our_label"],
        "read_by": {"readers": len(READERS), "model": REQUIRED_MODEL,
                    "reasoning": REQUIRED_REASONING},
        "counts": counts,
        "marked_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "passages": [dict(marks[p["id"]], passage=p["id"], section=p["section"], kind=p["kind"])
                     for p in held["passages"]],
        "differences": marked,
        "next_step": "distillation",
    }


def check(counts: dict, register: dict) -> None:
    """Every difference the register holds carries exactly one mark, or nothing is written."""
    wrong = []
    if counts["differences"] != register["differences"]:
        wrong.append(f"the register holds {register['differences']} differences and "
                     f"{counts['differences']} carry a mark")
    if counts["passages"] != register["passages"]:
        wrong.append(f"the register holds {register['passages']} passages and {counts['passages']} "
                     f"were answered")
    both = counts["evidence-of-a-rule"] + counts["clients-own-wording"]
    if both != counts["differences"]:
        wrong.append(f"{counts['differences']} differences carry marks that add up to {both}")
    if wrong:
        raise Refused("the disposition does not add up, so it was not written — " + "; ".join(wrong))


def write(work: pathlib.Path, record_value: dict) -> pathlib.Path:
    target = work / "disposition.json"
    if target.is_file():
        standing = json.loads(target.read_text(encoding="utf-8"))
        same = all(standing.get(k) == record_value.get(k) for k in
                   ("client", "counts", "differences", "passages"))
        if not same:
            raise Refused(
                f"work: {work} already holds a disposition of "
                f"{standing.get('counts', {}).get('differences')} differences, and this one differs "
                f"from it; a run's record is never written over — give a fresh directory, or leave "
                f"the judgement that was made")
        record_value = dict(record_value, marked_at=standing.get("marked_at", record_value["marked_at"]),
                            re_marked_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"))
    target.write_text(json.dumps(record_value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def show(work: pathlib.Path) -> dict:
    target = work / "disposition.json"
    if not target.is_file():
        raise Refused(f"work: {work} holds no disposition.json — run `dispose.py finish` first")
    value = json.loads(target.read_text(encoding="utf-8"))
    check(value["counts"], _held(work)["counts"])
    sections: dict[str, int] = {}
    for passage in value["passages"]:
        if passage["answer"] == "evidence-of-a-rule":
            where = passage.get("section") or "(no heading above it)"
            sections[where] = sections.get(where, 0) + 1
    return {
        "client": value["client"],
        "returned": value["returned_label"],
        "ours": value["our_label"],
        "read_by": value["read_by"],
        "counts": value["counts"],
        "where_the_rules_show": dict(sorted(sections.items(), key=lambda item: -item[1])[:12]),
        "next_step": value["next_step"],
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dispose.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    for action, help_text in (
            ("ask", "the questions for one reader, blind to the others"),
            ("read", "keep one reader's answers"),
            ("settle", "what the three agree on, and what is for Kamen"),
            ("ask-owner", "the splits, her words first, then the readings, then a recommendation"),
            ("rule", "keep Kamen's ruling on one split, in his words"),
            ("finish", "write the disposition once nothing is unsettled"),
            ("show", "what the disposition holds, in a few lines")):
        step = sub.add_parser(action, help=help_text)
        step.add_argument("--work", required=True, help="the run directory the register wrote")
        if action == "ask":
            step.add_argument("--reader", required=True, type=int, choices=list(READERS))
        if action == "read":
            step.add_argument("--answers", required=True, help="one reader's filled questions")
        if action == "rule":
            step.add_argument("--id", required=True, help="the passage he is ruling on")
            step.add_argument("--choice", required=True, help="the answer he chose")
            step.add_argument("--because", required=True, help="his own words")
    args = parser.parse_args(argv)
    work = pathlib.Path(args.work).resolve()

    try:
        if args.action == "ask":
            print(json.dumps(ask(work, args.reader), indent=2, ensure_ascii=False))
        elif args.action == "read":
            value = read_answers(work, pathlib.Path(args.answers))
            target = work / f"reading-{value['reader']}.json"
            if target.is_file():
                standing = json.loads(target.read_text(encoding="utf-8"))
                if standing.get("passages") != value["passages"]:
                    raise Refused(f"work: reader {value['reader']} has already read this register and "
                                  f"this reading differs from it; a reading is never written over — "
                                  f"give a fresh directory, or leave the reading that was made")
            target.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            outcome = None
            try:
                outcome = settle(work)
            except Refused:
                pass
            print(json.dumps({"status": "read", "reader": value["reader"], "reading": str(target),
                              "passages": len(value["passages"]),
                              "readers_still_to_read": [r for r in READERS
                                                        if not (work / f"reading-{r}.json").is_file()],
                              "agreed": len(outcome["agreed"]) if outcome else None,
                              "for_kamen": sorted(outcome["split"]) if outcome else None},
                             indent=2, ensure_ascii=False))
        elif args.action == "settle":
            outcome = settle(work)
            print(json.dumps({"agreed": len(outcome["agreed"]), "for_kamen": sorted(outcome["split"]),
                              "the_split_answers": {p: v["answers"] for p, v in outcome["split"].items()}},
                             indent=2, ensure_ascii=False))
        elif args.action == "ask-owner":
            print(json.dumps(ask_owner(work), indent=2, ensure_ascii=False))
        elif args.action == "rule":
            print(json.dumps(rule(work, args.id, args.choice, args.because), indent=2,
                             ensure_ascii=False))
        elif args.action == "finish":
            value = finish(work)
            target = write(work, value)
            print(json.dumps({"status": "marked", "disposition": str(target),
                              "counts": value["counts"], "next_step": value["next_step"]},
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
