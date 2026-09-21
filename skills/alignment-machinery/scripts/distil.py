#!/usr/bin/env python3
"""The fourth step of alignment-machinery: gather what the dispositions called rules.

Every step before this one works on one returned document. This one does not, and that is the
whole reason it exists: a rule is rarely visible inside a single return. On 20 September a rule
the client had shown us on one client that morning was missed on the other the same day, because
each return was read on its own.

    distil.py gather --work <new directory> --from <run> --from <run> [--from <run>]
    distil.py show   --work <directory>

So the one way a caller can get this step wrong is not which document they named -- the earlier
steps already settled that -- but which set of runs. Leave one return out and what comes back is a
smaller answer wearing every mark of a complete one. Nothing in it would say a return was missing.

That is what this hand-over is for. It takes the runs by name, refuses anything that is not a
finished disposition of this machinery at the current version, recomputes each record's arithmetic
against the register the disposition did not write, and then looks in the folders those runs came
from: if another finished disposition of the current version is sitting there unnamed, it refuses
and names it. Superseded records from an earlier version of the step are left alone, because they
are history rather than an omission.

What it writes is one gathered record: every passage the readers called evidence of a rule, with
the client it came from, the client's words and ours, the heading it sat under and the reason
given. It names no rule and groups nothing. That is the step after this.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from dispose import DISPOSITION_VERSION, READERS, check  # noqa: E402
from invoke import Refused  # noqa: E402  (one refusal shape for the whole machinery)

GATHER_VERSION = 1
#: the mark this step carries forward; the other mark is this client's own wording and stays behind
THE_RULE_MARK = "evidence-of-a-rule"
#: how the disposition records a passage the readers split on, which Kamen and no model settled
THE_OWNERS_RULING = "Kamen's ruling"


def _record(run: pathlib.Path) -> dict:
    """One run's finished disposition, refused unless it is one this step may read."""
    target = run / "disposition.json"
    if not target.is_file():
        raise Refused(f"{run.name}: holds no disposition.json — this step gathers runs the "
                      f"disposition finished; run `dispose.py finish` on it first, or leave it out")
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Refused(f"{run.name}: {target} could not be read as JSON ({exc})") from None
    if value.get("machinery") != "alignment-machinery" or value.get("step") != "disposition":
        raise Refused(f"{run.name}: {target} was not written by this machinery's disposition")
    version = value.get("disposition_version")
    if version != DISPOSITION_VERSION:
        raise Refused(
            f"{run.name}: its disposition was written by version {version} of the step and this "
            f"machinery is at version {DISPOSITION_VERSION}. Version {version} was answered by one "
            f"reader; the mark on every passage here would be a single model's reading. Run the "
            f"disposition again on a fresh directory rather than gathering a superseded record")
    readers = (value.get("read_by") or {}).get("readers")
    if readers != len(READERS):
        raise Refused(f"{run.name}: its disposition was read by {readers} reader(s) and this step "
                      f"gathers records read by {len(READERS)}")
    return value


def _reconciles(run: pathlib.Path, value: dict) -> None:
    """The record's arithmetic, recomputed against the register the disposition did not write."""
    register = run / "differences.json"
    if not register.is_file():
        raise Refused(f"{run.name}: holds a disposition but no differences.json, so its counts "
                      f"cannot be checked against the register they were marked from")
    held = json.loads(register.read_text(encoding="utf-8"))
    check(value["counts"], held["counts"])
    marked = sum(1 for d in value["differences"] if d.get("disposition"))
    if marked != value["counts"]["differences"]:
        raise Refused(f"{run.name}: its counts say {value['counts']['differences']} differences "
                      f"carry a mark and {marked} of them do")


def _unnamed(runs: list[pathlib.Path]) -> list[pathlib.Path]:
    """Finished records of this version sitting beside the named runs and left out of the set.

    A missing return is the one failure this step cannot show in its own output, so it is the one
    thing looked for rather than trusted. Only records this step would accept count: a superseded
    one is history, and an unfinished run is not an omission.
    """
    named = {run.resolve() for run in runs}
    found: list[pathlib.Path] = []
    for folder in sorted({run.resolve().parent for run in runs}):
        for beside in sorted(folder.iterdir()):
            if not beside.is_dir() or beside.resolve() in named:
                continue
            target = beside / "disposition.json"
            if not target.is_file():
                continue
            try:
                value = json.loads(target.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if (value.get("machinery") == "alignment-machinery"
                    and value.get("step") == "disposition"
                    and value.get("disposition_version") == DISPOSITION_VERSION
                    and (value.get("read_by") or {}).get("readers") == len(READERS)):
                found.append(beside)
    return found


def gather(work: pathlib.Path, runs: list[pathlib.Path]) -> dict:
    """Every passage the readers called evidence of a rule, across the whole set."""
    if not runs:
        raise Refused("from: name the runs to gather — a rule is rarely visible inside one return, "
                      "so this step reads them together")
    seen: dict[pathlib.Path, pathlib.Path] = {}
    for run in runs:
        if run.resolve() in seen:
            raise Refused(f"from: {run.name} was named twice")
        seen[run.resolve()] = run

    records = []
    for run in runs:
        value = _record(run)
        _reconciles(run, value)
        records.append((run, value))

    left_out = _unnamed(runs)
    if left_out:
        raise Refused(
            f"beside the runs you named, {', '.join(p.name for p in left_out)} holds a finished "
            f"disposition of this machinery that was not named. A rule shows itself across returns, "
            f"so a set with one missing produces a smaller answer with every mark of a complete "
            f"one. Name it too, or move it out of the way")

    passages: list[dict] = []
    for run, value in records:
        differences = {d["id"]: d for d in value["differences"]}
        for passage in value["passages"]:
            if passage["answer"] != THE_RULE_MARK:
                continue
            mine = [differences[d] for d in
                    next(p["differences"] for p in json.loads(
                        (run / "differences.json").read_text(encoding="utf-8"))["passages"]
                        if p["id"] == passage["passage"])]
            passages.append({
                "id": f"r-{len(passages) + 1:04d}",
                "client": value["client"],
                "returned_label": value["returned_label"],
                "our_label": value["our_label"],
                "run": run.name,
                "passage": passage["passage"],
                "kind": passage["kind"],
                "section": passage.get("section"),
                "settled_by": passage["settled_by"],
                "reason": passage["reason"],
                "quote": passage["quote"],
                "theirs": [d["theirs"] for d in mine if d.get("theirs")],
                "ours": [d["ours"] for d in mine if d.get("ours")],
                "differences": [d["id"] for d in mine],
            })

    counts = {
        "runs": len(records),
        "clients": len({value["client"] for _, value in records}),
        "rule_passages": len(passages),
        "rule_differences": sum(len(p["differences"]) for p in passages),
        "ruled_by_kamen": sum(1 for p in passages if p["settled_by"] == THE_OWNERS_RULING),
        "sections": len({(p["client"], p["section"]) for p in passages}),
    }
    adds_up(counts, records)
    return {
        "machinery": "alignment-machinery",
        "step": "distillation",
        "gather_version": GATHER_VERSION,
        "gathered_from": [{"run": run.name, "client": value["client"],
                           "returned_label": value["returned_label"],
                           "passages": value["counts"]["passages"],
                           "rule_passages": value["counts"]["passages_evidence-of-a-rule"]}
                          for run, value in records],
        "counts": counts,
        "gathered_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "passages": passages,
        "next_step": "the candidate rules, named across the whole set",
    }


def adds_up(counts: dict, records: list[tuple[pathlib.Path, dict]]) -> None:
    """Nothing the dispositions marked a rule is dropped on the way in, or nothing is written."""
    expected = sum(value["counts"]["passages_evidence-of-a-rule"] for _, value in records)
    if counts["rule_passages"] != expected:
        raise Refused(f"the gathering does not add up, so it was not written — the dispositions "
                      f"mark {expected} passages as evidence of a rule and {counts['rule_passages']} "
                      f"were gathered")
    differences = sum(value["counts"][THE_RULE_MARK] for _, value in records)
    if counts["rule_differences"] != differences:
        raise Refused(f"the gathering does not add up, so it was not written — the dispositions "
                      f"mark {differences} differences as evidence of a rule and "
                      f"{counts['rule_differences']} were gathered")


def write(work: pathlib.Path, record: dict) -> pathlib.Path:
    work.mkdir(parents=True, exist_ok=True)
    target = work / "gathered.json"
    if target.is_file():
        standing = json.loads(target.read_text(encoding="utf-8"))
        same = all(standing.get(k) == record.get(k) for k in
                   ("gathered_from", "counts", "passages"))
        if not same:
            raise Refused(
                f"work: {work} already holds a gathering of "
                f"{standing.get('counts', {}).get('rule_passages')} rule passages from "
                f"{len(standing.get('gathered_from', []))} run(s), and this one differs from it; a "
                f"run's record is never written over — give a fresh directory")
        record = dict(record, gathered_at=standing.get("gathered_at", record["gathered_at"]),
                      re_gathered_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"))
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def show(work: pathlib.Path) -> dict:
    target = work / "gathered.json"
    if not target.is_file():
        raise Refused(f"work: {work} holds no gathered.json — run `distil.py gather` first")
    record = json.loads(target.read_text(encoding="utf-8"))
    where: dict[str, int] = {}
    for passage in record["passages"]:
        seat = f"{passage['client']} · {passage['section'] or '(no heading above it)'}"
        where[seat] = where.get(seat, 0) + 1
    refused = work / "refused.json"
    turned_away = json.loads(refused.read_text(encoding="utf-8")) if refused.is_file() else []
    return {
        "gathered_from": record["gathered_from"],
        "counts": record["counts"],
        "where_they_sit": dict(sorted(where.items(), key=lambda item: -item[1])[:12]),
        "what_was_refused": [{"what": r["what"], "at": r["refused_at"], "because": r["because"]}
                             for r in turned_away],
        "next_step": record["next_step"],
    }



# --- naming the changes -------------------------------------------------------------------------
#
# The gathering holds 162 passages that each carry knowledge about how a page should be built. They
# are not 162 changes: the same change appears on every calendar slot, on every line we hold. What
# follows turns them into the distinct changes, and it is deliberately not one model's grouping.
#
# Grouping cannot be put to three blind readers. Asked to group 162 things, three readers return
# three different sets of groups and there is nothing to compare — agreement is not even defined.
# So the work is split. One model that does no judging reads the whole gathering and proposes the
# candidate changes. Then every passage is put to three readers who cannot see each other as one
# bounded question with the same answers every time: which of these changes does this line belong
# under, or none of them. Those answers are comparable, so agreement means something, and a split
# goes to Kamen exactly as it does in the step before.

#: the model that reads the whole gathering and proposes the changes; it judges no passage
PROPOSER = "claude-fable-5-1"
#: the readers who place each passage, and the reasoning they run at
REQUIRED_MODEL = "claude-opus-5"
REQUIRED_REASONING = "high"
READERS = (1, 2, 3)
#: how a passage settled by Kamen is recorded, so a model's vote can never be mistaken for his
THE_OWNERS_RULING_ON_A_PLACEMENT = "Kamen's ruling"


def _gathering(work: pathlib.Path) -> dict:
    target = work / "gathered.json"
    if not target.is_file():
        raise Refused(f"work: {work} holds no gathered.json — run `distil.py gather` first")
    return json.loads(target.read_text(encoding="utf-8"))


def brief(work: pathlib.Path) -> dict:
    """What the proposing model is given: the whole gathering, and what a change has to be."""
    held = _gathering(work)
    return {
        "machinery": "alignment-machinery",
        "step": "distillation",
        "for_the_proposer": (
            "Read every passage below. Each one is a change a client made that three readers "
            "judged to carry knowledge about how a page should be built, not this client's "
            "wording. They are not one change each: the same change appears in many places. Name "
            "the distinct changes."),
        "what_a_change_is": (
            "One sentence saying what should be true of a page of this kind, with no client in it "
            "— no client name, no campaign, no product, no person. If the sentence only makes "
            "sense for one client it is not a change to how pages are built."),
        "the_rules_you_work_under": [
            "Propose the changes you can see and no more. A change nobody's lines support is not "
            "a change.",
            "Do not place the passages. Another set of readers does that, blind to you, and they "
            "will refuse a change that no passage belongs under.",
            "Two changes that would always be made together are one change.",
            "A change that would be made without the other is its own change.",
        ],
        "answer_with": {
            "proposed_by": {"model": PROPOSER},
            "candidates": [{"id": "c-0001", "change": None, "why_it_is_one_change": None}],
        },
        "clients_in_this_gathering": sorted({p["client"] for p in held["passages"]}),
        "counts": held["counts"],
        "passages": [{"id": p["id"], "client": p["client"], "section": p["section"],
                      "theirs": p["theirs"], "ours": p["ours"], "the_reason_given": p["reason"]}
                     for p in held["passages"]],
    }


def take_proposal(work: pathlib.Path, filled: pathlib.Path) -> dict:
    """The proposed changes, refused unless each is a sentence with no client in it."""
    held = _gathering(work)
    if not filled.is_file():
        raise Refused(f"candidates: {filled} is not a file")
    try:
        value = json.loads(filled.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Refused(f"candidates: {filled} could not be read as JSON ({exc})") from None
    by = (value.get("proposed_by") or {}).get("model")
    if by != PROPOSER:
        raise Refused(f"proposed_by: the changes say they were proposed by {by!r} and this step "
                      f"has them proposed by {PROPOSER!r}")
    candidates = value.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise Refused("candidates: no changes were proposed; a gathering with passages in it "
                      "carries at least one change")

    clients = sorted({p["client"] for p in held["passages"]})
    labels = sorted({word.lower() for p in held["passages"]
                     for word in (p["returned_label"] or "").split() if len(word) > 3})
    wrong = []
    seen = set()
    for index, candidate in enumerate(candidates, start=1):
        cid = candidate.get("id")
        if not cid:
            wrong.append(f"the change at position {index} has no id")
            continue
        if cid in seen:
            wrong.append(f"{cid}: two changes carry that id")
        seen.add(cid)
        change = (candidate.get("change") or "").strip()
        if not change:
            wrong.append(f"{cid}: has no sentence saying what should be true of a page")
            continue
        named = [c for c in clients if c.lower() in change.lower()]
        named += [w for w in labels if w in change.lower() and w not in ("step", "toolkit",
                                                                         "final", "execution")]
        if named:
            wrong.append(f"{cid}: its sentence names {', '.join(sorted(set(named)))}, so it says "
                         f"how one client's page should read rather than how a page is built")
        if not (candidate.get("why_it_is_one_change") or "").strip():
            wrong.append(f"{cid}: does not say why it is one change rather than several")
    if wrong:
        raise Refused("; ".join(wrong))

    return {
        "machinery": "alignment-machinery",
        "step": "distillation",
        "gather_version": held["gather_version"],
        "proposed_by": {"model": PROPOSER},
        "candidates": [{"id": c["id"], "change": c["change"].strip(),
                        "why_it_is_one_change": c["why_it_is_one_change"].strip()}
                       for c in candidates],
        "proposed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }


def _proposal(work: pathlib.Path) -> dict:
    target = work / "proposal.json"
    if not target.is_file():
        raise Refused(f"work: {work} holds no proposal.json — run `distil.py brief`, give it to "
                      f"the proposing model, and keep its answer with `distil.py propose` first")
    return json.loads(target.read_text(encoding="utf-8"))


def ask(work: pathlib.Path, reader: int) -> dict:
    """One reader's questions: every passage against every proposed change, blind to the others.

    The question allows more than one answer, and that is the correction this step needed rather
    than a convenience. Asked which single change a passage belonged under, three readers split on
    22 of 162 -- and every one of those 22 was a block that renamed its labels, added a new
    paragraph and dropped our working rows at once. The readers were not disagreeing about the
    facts; the question let only one of them through. One real change drew no evidence at all,
    because the rows it describes never disappear on their own.
    """
    held = _gathering(work)
    proposal = _proposal(work)
    return {
        "machinery": "alignment-machinery",
        "step": "distillation",
        "reader": str(reader),
        "the_question": "Which of these changes does this passage show? All that apply, or none.",
        "the_changes": proposal["candidates"],
        "how_to_answer": (
            "Answer every passage. Put in `shows` the id of every change this passage shows, in "
            "any order -- one, several, or an empty list when it shows none of them. A passage "
            "that renames its labels and also adds a new paragraph shows both, and saying so is "
            "the point of the question. Say in `because` what in the passage shows each one you "
            "named, in one or two sentences. Do not add, rename or merge the changes; they were "
            "proposed by a model that judged no passage, and a change nothing shows is dropped by "
            "the arithmetic rather than by you."),
        "the_test": (
            "A passage shows a change when the passage contains something that making that change "
            "to the way pages are built would produce. Judge each change on its own: that another "
            "change is also visible in the same passage is not a reason to leave this one out, and "
            "a change that is merely consistent with the passage but produces nothing in it is not "
            "shown."),
        "answer_with": {"reader": str(reader), "model": REQUIRED_MODEL,
                        "reasoning": REQUIRED_REASONING,
                        "passages": [{"id": "r-0001", "shows": ["c-0001"], "because": None}]},
        "passages": [{"id": p["id"], "client": p["client"], "section": p["section"],
                      "theirs": p["theirs"], "ours": p["ours"], "the_reason_given": p["reason"]}
                     for p in held["passages"]],
    }


def read_placements(work: pathlib.Path, answers: pathlib.Path) -> dict:
    """One reader's answers, checked against the gathering and the proposal it did not write."""
    held = _gathering(work)
    proposal = _proposal(work)
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

    allowed = {c["id"] for c in proposal["candidates"]}
    wanted = [p["id"] for p in held["passages"]]
    given: dict[str, dict] = {}
    wrong: list[str] = []
    for answer in value.get("passages") or []:
        pid = answer.get("id")
        if pid in given:
            wrong.append(f"{pid}: answered twice")
            continue
        given[pid] = answer
    missing = [pid for pid in wanted if pid not in given]
    extra = [pid for pid in given if pid not in wanted]
    if missing:
        wrong.append(f"{len(missing)} passage(s) were not answered, the first being "
                     f"{', '.join(missing[:5])}")
    if extra:
        wrong.append(f"{', '.join(extra[:5])} is not in this gathering")
    for pid in wanted:
        answer = given.get(pid)
        if answer is None:
            continue
        shows = answer.get("shows")
        if isinstance(shows, str):
            wrong.append(f"{pid}: `shows` came back as the single value {shows!r}; it is a list of "
                         f"every change this passage shows, so write [{shows!r}] even when there "
                         f"is only one, and [] when there are none")
            continue
        if not isinstance(shows, list):
            wrong.append(f"{pid}: `shows` came back as {type(shows).__name__}; it is a list of the "
                         f"change ids this passage shows, and an empty list when it shows none")
            continue
        unknown = [c for c in shows if c not in allowed]
        if unknown:
            wrong.append(f"{pid}: names {', '.join(str(c) for c in unknown)}, which "
                         f"{'are' if len(unknown) > 1 else 'is'} not among the proposed changes; "
                         f"the changes are {', '.join(sorted(allowed))}")
        if len(set(shows)) != len(shows):
            wrong.append(f"{pid}: names the same change twice")
        if not (answer.get("because") or "").strip():
            wrong.append(f"{pid}: gives no reason for the changes it names")
    if wrong:
        raise Refused("; ".join(wrong))

    return {
        "machinery": "alignment-machinery",
        "step": "distillation",
        "reader": reader,
        "read_by": {"model": REQUIRED_MODEL, "reasoning": REQUIRED_REASONING},
        "placements": [{"id": pid, "shows": sorted(set(given[pid]["shows"])),
                        "because": given[pid]["because"].strip()} for pid in wanted],
        "placed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }


def _readings(work: pathlib.Path) -> dict[str, dict]:
    found = {}
    for reader in READERS:
        target = work / f"placement-{reader}.json"
        if target.is_file():
            found[str(reader)] = json.loads(target.read_text(encoding="utf-8"))
    return found


def _pair(passage: str, change: str) -> str:
    """One passage weighed against one change: the thing the readers actually agree or differ on."""
    return f"{passage}+{change}"


def _votes(work: pathlib.Path) -> tuple[dict, dict, list]:
    """For every passage and every change, what each reader said."""
    held = _gathering(work)
    proposal = _proposal(work)
    readings = _readings(work)
    absent = [str(r) for r in READERS if str(r) not in readings]
    if absent:
        raise Refused(f"readers: reader {', '.join(absent)} have not answered this gathering yet — "
                      f"all {len(READERS)} read it before anything is settled")
    shown = {r: {p["id"]: set(p["shows"]) for p in readings[r]["placements"]} for r in readings}
    votes: dict[str, dict[str, bool]] = {}
    for passage in held["passages"]:
        for candidate in proposal["candidates"]:
            key = _pair(passage["id"], candidate["id"])
            votes[key] = {r: candidate["id"] in shown[r][passage["id"]] for r in sorted(shown)}
    return votes, readings, held["passages"]


def settle(work: pathlib.Path) -> dict:
    """What the three agree on, change by change, and what is for Kamen."""
    votes, _, _ = _votes(work)
    shows, does_not, for_kamen = [], [], []
    for key, said in votes.items():
        answers = set(said.values())
        if answers == {True}:
            shows.append(key)
        elif answers == {False}:
            does_not.append(key)
        else:
            for_kamen.append(key)
    return {
        "pairings": len(votes),
        "they_agree_it_shows": len(shows),
        "they_agree_it_does_not": len(does_not),
        "for_kamen": sorted(for_kamen),
        "the_split_answers": {k: votes[k] for k in sorted(for_kamen)},
    }


def _rulings(work: pathlib.Path) -> dict:
    target = work / "placement-rulings.json"
    return json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}


def ask_owner(work: pathlib.Path) -> dict:
    """The disagreements: the client's words and ours first, then the readings, then advice."""
    votes, readings, passages = _votes(work)
    proposal = _proposal(work)
    by_id = {c["id"]: c for c in proposal["candidates"]}
    standing = settle(work)
    ruled = _rulings(work)
    waiting = []
    for key in standing["for_kamen"]:
        if key in ruled:
            continue
        pid, cid = key.split("+")
        passage = next(p for p in passages if p["id"] == pid)
        waiting.append({
            "pairing": key,
            "the_change": by_id[cid],
            "client": passage["client"],
            "where_it_sits": passage["section"],
            "what_they_wrote": passage["theirs"],
            "what_we_wrote": passage["ours"],
            "why_it_was_called_a_rule": passage["reason"],
            "the_three_readings": [
                {"reader": r,
                 "says_it_shows_this_change": votes[key][r],
                 "and_named_in_all": sorted(next(p["shows"] for p in readings[r]["placements"]
                                                 if p["id"] == pid)),
                 "because": next(p["because"] for p in readings[r]["placements"]
                                 if p["id"] == pid)}
                for r in sorted(readings)],
            "then_a_recommendation": None,
            "then_what_it_means_either_way": None,
            "kamens_ruling": None,
        })
    return {
        "machinery": "alignment-machinery",
        "step": "distillation",
        "the_question": "Does this passage show this change — yes or no?",
        "the_answers": {"yes": "the passage contains something this change would produce",
                        "no": "it does not, whatever else the passage also shows"},
        "for_the_recommender": (
            "Fill then_a_recommendation with one plain sentence saying yes or no and why, and "
            "then_what_it_means_either_way with what follows for the work in each case. Judge this "
            "change on its own: a passage may show several changes, so the fact that another "
            "change is also visible is not a reason to answer no, and a change needing evidence is "
            "not a reason to answer yes. Write for someone who has not read the page. Do not "
            "change anything above those fields: they are the evidence, and they come first so "
            "the ruling is made on them."),
        "recommended_by": {"model": PROPOSER},
        "waiting_on_kamen": waiting,
    }


def rule_placement(work: pathlib.Path, key: str, choice: str, because: str) -> dict:
    standing = settle(work)
    if key not in standing["for_kamen"]:
        raise Refused(f"{key}: the readers did not disagree about it, so there is nothing for "
                      f"Kamen to rule; a settled answer is not overturned by a later ruling")
    if choice not in ("yes", "no"):
        raise Refused(f"choice: {choice!r} — the answers are 'yes' (the passage shows this change) "
                      f"and 'no' (it does not)")
    if not because.strip():
        raise Refused("because: a ruling is kept in Kamen's own words, so it cannot be empty")
    ruled = _rulings(work)
    if key in ruled and ruled[key]["answer"] != choice:
        raise Refused(f"{key}: already carries Kamen's ruling of {ruled[key]['answer']!r}; a "
                      f"ruling is never written over")
    ruled[key] = {"answer": choice, "because": because.strip(),
                  "ruled_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}
    (work / "placement-rulings.json").write_text(
        json.dumps(ruled, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": "ruled", "pairing": key, "answer": choice, "because": because.strip(),
            "still_waiting": [k for k in standing["for_kamen"] if k not in ruled]}


def name(work: pathlib.Path) -> dict:
    """The changes, each carrying the passages that show it — once nothing is unsettled."""
    held = _gathering(work)
    proposal = _proposal(work)
    votes, readings, passages = _votes(work)
    standing = settle(work)
    ruled = _rulings(work)
    unruled = [k for k in standing["for_kamen"] if k not in ruled]
    if unruled:
        raise Refused(
            f"waiting on Kamen: {', '.join(unruled)} — the readers disagreed about "
            f"{len(unruled)} passage-and-change pairing(s) and no model casts that vote; put them "
            f"to him with `ask-owner` and keep his answer with `rule`")

    settled: dict[str, bool] = {}
    how: dict[str, str] = {}
    for key, said in votes.items():
        if key in ruled:
            settled[key] = ruled[key]["answer"] == "yes"
            how[key] = THE_OWNERS_RULING_ON_A_PLACEMENT
        else:
            settled[key] = all(said.values())
            how[key] = f"{len(READERS)} readers agreeing"

    by_passage = {p["id"]: p for p in held["passages"]}
    changes = []
    for candidate in proposal["candidates"]:
        proved = []
        for passage in held["passages"]:
            key = _pair(passage["id"], candidate["id"])
            if not settled[key]:
                continue
            source = by_passage[passage["id"]]
            proved.append({
                "passage": passage["id"], "client": source["client"],
                "section": source["section"], "theirs": source["theirs"], "ours": source["ours"],
                "settled_by": how[key],
                "because": (ruled[key]["because"] if key in ruled else
                            next(p["because"] for p in readings["1"]["placements"]
                                 if p["id"] == passage["id"])),
                "differences": source["differences"]})
        if proved:
            changes.append({"id": candidate["id"], "change": candidate["change"],
                            "why_it_is_one_change": candidate["why_it_is_one_change"],
                            "clients": sorted({p["client"] for p in proved}),
                            "passages": len(proved),
                            "lines": sum(len(p["differences"]) for p in proved),
                            "shown_by": proved})
    unsupported = [c["id"] for c in proposal["candidates"]
                   if not any(settled[_pair(p["id"], c["id"])] for p in held["passages"])]
    nowhere = [{"passage": p["id"], "client": by_passage[p["id"]]["client"],
                "section": by_passage[p["id"]]["section"],
                "theirs": by_passage[p["id"]]["theirs"], "ours": by_passage[p["id"]]["ours"]}
               for p in held["passages"]
               if not any(settled[_pair(p["id"], c["id"])] for c in proposal["candidates"])]

    counts = {
        "gathered_passages": held["counts"]["rule_passages"],
        "gathered_lines": held["counts"]["rule_differences"],
        "proposed": len(proposal["candidates"]),
        "pairings": len(votes),
        "pairings_it_shows": sum(1 for v in settled.values() if v),
        "pairings_it_does_not": sum(1 for v in settled.values() if not v),
        "pairings_ruled_by_kamen": len(ruled),
        "changes": len(changes),
        "dropped_with_nothing_behind_them": len(unsupported),
        "passages_showing_nothing": len(nowhere),
        "passages_showing_more_than_one": sum(
            1 for p in held["passages"]
            if sum(1 for c in proposal["candidates"] if settled[_pair(p["id"], c["id"])]) > 1),
    }
    adds_up_placements(counts, len(held["passages"]))
    return {
        "machinery": "alignment-machinery",
        "step": "distillation",
        "gather_version": held["gather_version"],
        "proposed_by": proposal["proposed_by"],
        "read_by": {"readers": len(READERS), "model": REQUIRED_MODEL,
                    "reasoning": REQUIRED_REASONING},
        "gathered_from": held["gathered_from"],
        "counts": counts,
        "dropped": unsupported,
        "named_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "changes": changes,
        "showing_nothing": nowhere,
        "next_step": "ruling",
    }


def adds_up_placements(counts: dict, passages: int) -> None:
    """Every passage weighed against every change, each pairing answered once, or nothing written."""
    wrong = []
    if counts["pairings"] != passages * counts["proposed"]:
        wrong.append(f"{passages} passages against {counts['proposed']} changes is "
                     f"{passages * counts['proposed']} pairings and {counts['pairings']} were "
                     f"weighed")
    answered = counts["pairings_it_shows"] + counts["pairings_it_does_not"]
    if answered != counts["pairings"]:
        wrong.append(f"{counts['pairings']} pairings and {answered} carry an answer "
                     f"({counts['pairings_it_shows']} shows, "
                     f"{counts['pairings_it_does_not']} does not)")
    if counts["changes"] + counts["dropped_with_nothing_behind_them"] != counts["proposed"]:
        wrong.append(f"{counts['proposed']} changes were proposed and "
                     f"{counts['changes'] + counts['dropped_with_nothing_behind_them']} were "
                     f"either kept or dropped")
    if wrong:
        raise Refused("the naming does not add up, so it was not written — " + "; ".join(wrong))


def write_one(work: pathlib.Path, filename: str, record: dict, same_on: tuple[str, ...],
              stamp: str) -> pathlib.Path:
    """A record of this run, never written over by a different one."""
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


def keep_refusal(work: pathlib.Path, what: str, offered: pathlib.Path, because: str) -> None:
    """What a model offered and why it was refused, kept in the run.

    The other refusals in this machinery answer a caller who mistyped something: they are read,
    the command is run again, and nothing was learnt. These two refuse a model's judgement, and
    that is evidence about the work rather than about the typing. A model that tries three times
    to say a change without naming a client and cannot is telling us the change is probably not a
    change to how pages are built -- and if the refusal only ever reaches a terminal, nobody sees
    it. So it is written down beside the run, appended and never replaced.
    """
    if not work.is_dir():
        return
    target = work / "refused.json"
    standing = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else []
    try:
        content = json.loads(offered.read_text(encoding="utf-8")) if offered.is_file() else None
    except json.JSONDecodeError:
        content = offered.read_text(encoding="utf-8")[:4000] if offered.is_file() else None
    standing.append({
        "what": what,
        "refused_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "because": because,
        "what_was_offered": content,
    })
    target.write_text(json.dumps(standing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="distil.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    step = sub.add_parser("gather", help="every passage the dispositions called a rule, in one place")
    step.add_argument("--work", required=True, help="a fresh directory for this gathering")
    step.add_argument("--from", dest="runs", action="append", default=[], metavar="RUN",
                      help="a run the disposition finished; give one for every return in the set")
    for action, help_text in (
            ("brief", "the whole gathering, for the model that proposes the changes"),
            ("propose", "keep the proposed changes"),
            ("ask", "one reader's questions, blind to the other readers"),
            ("read", "keep one reader's placements"),
            ("settle", "what the three agree on, and what is for Kamen"),
            ("ask-owner", "the splits, the evidence first, then a recommendation"),
            ("rule", "keep Kamen's ruling on one split, in his words"),
            ("name", "write the changes once nothing is unsettled"),
            ("show", "what this run holds, in a few lines")):
        step = sub.add_parser(action, help=help_text)
        step.add_argument("--work", required=True, help="the run directory the gathering wrote")
        if action == "propose":
            step.add_argument("--candidates", required=True, help="the proposing model's answer")
        if action == "ask":
            step.add_argument("--reader", required=True, type=int, choices=list(READERS))
        if action == "read":
            step.add_argument("--answers", required=True, help="one reader's filled questions")
        if action == "rule":
            step.add_argument("--id", required=True, help="the passage-and-change pairing")
            step.add_argument("--choice", required=True, help="yes or no")
            step.add_argument("--because", required=True, help="his own words")
    args = parser.parse_args(argv)
    work = pathlib.Path(args.work).resolve()

    try:
        if args.action == "gather":
            runs = [pathlib.Path(run).resolve() for run in args.runs]
            record = gather(work, runs)
            target = write(work, record)
            print(json.dumps({"status": "gathered", "gathering": str(target),
                              "counts": record["counts"], "next_step": record["next_step"]},
                             indent=2, ensure_ascii=False))
        elif args.action == "brief":
            print(json.dumps(brief(work), indent=2, ensure_ascii=False))
        elif args.action == "propose":
            record = take_proposal(work, pathlib.Path(args.candidates).resolve())
            target = write_one(work, "proposal.json", record, ("candidates",), "proposed_at")
            print(json.dumps({"status": "proposed", "proposal": str(target),
                              "changes": len(record["candidates"]),
                              "next_step": f"ask each of the {len(READERS)} readers"},
                             indent=2, ensure_ascii=False))
        elif args.action == "ask":
            print(json.dumps(ask(work, args.reader), indent=2, ensure_ascii=False))
        elif args.action == "read":
            record = read_placements(work, pathlib.Path(args.answers).resolve())
            target = write_one(work, f"placement-{record['reader']}.json", record,
                               ("placements",), "placed_at")
            still = [str(r) for r in READERS if not (work / f"placement-{r}.json").is_file()]
            print(json.dumps({"status": "read", "reader": record["reader"],
                              "placements": str(target),
                              "passages": len(record["placements"]),
                              "readers_still_to_read": still}, indent=2, ensure_ascii=False))
        elif args.action == "settle":
            print(json.dumps(settle(work), indent=2, ensure_ascii=False))
        elif args.action == "ask-owner":
            print(json.dumps(ask_owner(work), indent=2, ensure_ascii=False))
        elif args.action == "rule":
            print(json.dumps(rule_placement(work, args.id, args.choice, args.because),
                             indent=2, ensure_ascii=False))
        elif args.action == "name":
            record = name(work)
            target = write_one(work, "changes.json", record, ("changes", "counts"), "named_at")
            print(json.dumps({"status": "named", "changes": str(target),
                              "counts": record["counts"], "dropped": record["dropped"],
                              "next_step": record["next_step"]}, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(show(work), indent=2, ensure_ascii=False))
    except Refused as exc:
        if args.action in ("propose", "read"):
            keep_refusal(work,
                         "the proposed changes" if args.action == "propose"
                         else "one reader's placements",
                         pathlib.Path(args.candidates if args.action == "propose"
                                      else args.answers).resolve(),
                         str(exc))
        print(json.dumps({"status": "refused", "because": str(exc)}, indent=2, ensure_ascii=False),
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
