#!/usr/bin/env python3
"""Turn what the builders noticed and left alone into work the machinery can order and build.

Every build hands back one requirement's change and a note of what else the builder saw and
deliberately did not touch — that separation is the whole reason a builder can be trusted with one
sentence. But for twenty-four builds those notes went into the item's own record and nothing ever
read them. A builder found the same family of fault a built requirement had already been proven
against, said so, and it stopped there. Noticing without a path to work is a filing cabinet.

So this step exists, and it is deliberately not a shortcut: the notes are prose, and prose is not
work. Two-thirds of the twenty-four records number nothing, so code cannot cut them into things —
measured, not assumed. Deciding what distinct thing a paragraph describes is a judgement, which
means a reader, which means the same rule as everywhere else: two readers who cannot see each
other, and agreement or nothing.

That is arranged in the machinery's own pattern, because the units have to be the same for both
readers before their answers can be compared at all:

  1 · notice   — model, twice. Each pass reads the same records and lists the distinct things it
                 finds, each carrying words quoted from the record.
  2 · pair     — code. Within one source record, every pass-1 thing is paired with every pass-2
                 thing. Code proposes; it judges nothing.
  3 · judge    — model, twice, over those pairs: are these two the same thing, is it still work in
                 the built system, and does a requirement already on the list cover it.
  4 · report   — code. A pair both passes call the same thing, still work, and not already on the
                 list becomes a candidate requirement, and its sentence is the *builder's* words,
                 quoted — no reader's wording is carried forward, and no wording of mine is.

The output is written in the shape the requirements machinery's own report has, so run.py can be
pointed straight at it and the proven path — pair, read the dependencies, order, build, verify —
runs over these exactly as it ran over the first hundred and forty-two. The loop closes.

Usage:  python3 collect_noticed.py --work <build-work-dir> --order <order.json> --out <dir>
Run it, do whatever it hands back, run it again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pair_requirements  # noqa: E402
import readers  # noqa: E402

PASSES = 2

#: Said to the readers who cut the prose into things. They are asked to quote, never to paraphrase:
#: the sentence that ends up in front of a builder has to be the words of the builder who saw it.
NOTICE = (
    "Read {records}. It holds, for each item the machinery has already built, the note its builder "
    "wrote about what it saw and deliberately did not change. Your job is to separate those notes "
    "into distinct things — one thing being one fault, gap or question that could be worked on by "
    "itself. Write one file per thing into {out}, named freely, holding "
    "{{'source_item': '<the build item id the note came from>', 'quote': '<the words from that "
    "note that state this thing, copied exactly, long enough to stand alone>', 'in_your_words': "
    "'<one sentence saying what would have to become true>'}}. Copy the quote character for "
    "character from the record; do not tidy it. A note may hold one thing or six. Read nothing but "
    "{records}."
)

#: Said to the readers who judge the proposed pairs.
JUDGE = (
    "Judge every pair in {pairs_file}. Each pair holds two descriptions of something a builder "
    "noticed, taken from the same builder's note by two readers who could not see each other, "
    "together with the note itself. For each pair answer three things. First: are these two the "
    "same thing, or two different things the same note happens to mention? Second, only if they "
    "are the same thing: is it still work in the built system — something that is not true today "
    "and could be made true? Third: is it already covered by a requirement on the current build "
    "list, {order_file}, which holds every requirement this machinery is already working through? "
    "Name the requirement id if so. Write one file per pair into {out}: "
    "{{'pair_id','same_thing':'yes'|'no','is_work':'yes'|'no'|null,'covered_by':'<requirement "
    "id>'|null,'why'}}. Read nothing but the pairs file and the build list."
)

#: Said to the readers who decide whether two candidates from different builders are one thing.
#: Measured, not assumed: the first run of this step produced forty-five candidates of which
#: seventeen were the same sentence about the same eight failing tests, written by seventeen
#: builders who each met them. Pairing inside one note cannot see that, because it only ever
#: compares two readings of the same paragraph. Handing that list on would have put seventeen
#: builders on one fault.
SAME = (
    "Judge every pair in {pairs_file}. Each pair holds two things different builders noticed while "
    "changing different parts of the same system. For each pair answer one question: are these the "
    "same thing — would one change make both of them stop being true — or are they two separate "
    "pieces of work that happen to be described alike? The same eight failing tests met by two "
    "builders is one thing. Two different faults in the same file are two. Write one file per pair "
    "into {out}: {{'pair_id','same_thing':'yes'|'no','why'}}. Read nothing but the pairs file."
)

#: Said only to a reader that has a twin, which here is every reader.
BLIND = (
    " You are one of two independent readers of this same input: do not open any sibling output or "
    "scratch directory, and do not look for what the other found. Agreement between two readers who "
    "could not see each other is the only evidence this machinery accepts."
)

HOW_TO_READ = (
    " Write files as you go — the first ten before doing further reading — so progress is visible; "
    "a reader that writes nothing until the end cannot be told apart from one that has stopped. "
    "Put every working, scratch or intermediate file in {scratch} and nowhere else — that "
    "directory is yours alone. Before you finish, write {scratch}/reader.json holding "
    "{{'model': '<the model you are, as you are identified>', 'harness': '<the tool you are "
    "running inside>'}}. This machinery never chooses a reader — whoever runs it supplies one, so "
    "the record has to say who read it."
)


def _gather(work: Path) -> list[dict[str, str]]:
    records = []
    for change in sorted(work.glob("build-*/change.json")):
        try:
            record = json.loads(change.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        note = str(record.get("left_alone") or "").strip()
        if note:
            records.append({"item": change.parent.name.removeprefix("build-"), "note": note})
    return records


def _load(directory: Path) -> list[dict[str, object]]:
    out = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "reader.json":
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


def _identity_coverage(
    directory: Path, expected: set[str], key: str = "pair_id",
) -> dict[str, list[str]]:
    counts: dict[str, int] = {}
    for record in _load(directory):
        identity = str(record.get(key) or "")
        counts[identity] = counts.get(identity, 0) + 1
    found = set(counts)
    return {
        "missing": sorted(expected - found),
        "unexpected": sorted(found - expected),
        "duplicated": sorted(identity for identity in expected if counts.get(identity, 0) > 1),
    }


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _input_state(work: Path, order_file: Path, records: list[dict[str, str]]) -> dict[str, object]:
    resolved_order = order_file.resolve()
    return {
        "contract": 1,
        "build_work": str(work.resolve()),
        "records": records,
        "order": {
            "path": str(resolved_order),
            "sha256": hashlib.sha256(resolved_order.read_bytes()).hexdigest(),
        },
    }


def _bind_input_state(out: Path, current: dict[str, object]) -> dict[str, object] | None:
    state_path = out / "input-state.json"
    if not state_path.exists():
        if any(out.iterdir()):
            return {
                "status": "blocked",
                "stopped": "unbound existing state",
                "why": "this populated output directory predates input binding",
                "use_fresh_output_directory": True,
            }
        state_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return None
    try:
        saved = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "blocked",
            "stopped": "invalid input state",
            "use_fresh_output_directory": True,
        }
    if saved != current:
        return {
            "status": "blocked",
            "stopped": "input changed",
            "why": "builder notes or the order differ from this output state",
            "saved_binding": _digest(saved),
            "current_binding": _digest(current),
            "use_fresh_output_directory": True,
        }
    return None


def _job(instruction: str, out: Path, scratch: Path, stage: str, count: int) -> dict[str, object]:
    scratch.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    return {
        "stage": stage,
        "instruction": instruction + BLIND + HOW_TO_READ.format(scratch=scratch),
        "waiting_for": str(out),
        "scratch": str(scratch),
        "records": count,
    }


def collect(work: Path, order_file: Path, out: Path) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    records = _gather(work)
    if not records:
        return {"status": "complete", "outcome": "nothing_was_noticed",
                "why": "no build record in this work directory carries a note of what its builder "
                       "left alone"}

    try:
        current_state = _input_state(work, order_file, records)
    except OSError as error:
        return {"status": "blocked", "stopped": "source unavailable", "why": str(error)}
    state_result = _bind_input_state(out, current_state)
    if state_result:
        return state_result

    records_file = out / "noticed-records.json"
    if not records_file.exists():
        records_file.write_text(json.dumps({"records": records}, indent=2), encoding="utf-8")

    # 1 · notice — model, twice over the same records.
    jobs = []
    for number in range(1, PASSES + 1):
        found = out / f"noticed-{number}"
        if _load(found):
            continue
        jobs.append(_job(NOTICE.format(records=records_file, out=found), found,
                         out / f"noticed-{number}-scratch", "notice", len(records)))
    if jobs:
        return {"status": "waiting_for_readers",
                "stopped": "reading what the builders noticed", "records": len(records),
                "outstanding": len(jobs), "work": jobs}

    # 2 · pair — code. Within one source record only: two readers describing the same note are
    # comparable; two readers describing different notes are not, and pairing them would only
    # invite a reader to invent a connection.
    passes = [_load(out / f"noticed-{number}") for number in range(1, PASSES + 1)]
    notes = {record["item"]: record["note"] for record in records}
    invalid = [
        {
            "pass": pass_number,
            "source_item": str(thing.get("source_item") or ""),
            "quote": str(thing.get("quote") or ""),
        }
        for pass_number, found in enumerate(passes, start=1)
        for thing in found
        if (
            str(thing.get("source_item") or "") not in notes
            or not str(thing.get("quote") or "").strip()
            or str(thing.get("quote") or "")
            not in notes.get(str(thing.get("source_item") or ""), "")
        )
    ]
    if invalid:
        return {
            "status": "blocked",
            "stopped": "invalid source quotation",
            "why": "a noticed thing did not quote its named builder note exactly",
            "invalid_records": invalid,
        }
    by_item: dict[str, list[list[dict[str, object]]]] = {}
    for index, found in enumerate(passes):
        for thing in found:
            item = str(thing.get("source_item"))
            by_item.setdefault(item, [[] for _ in range(PASSES)])[index].append(thing)

    pairs = []
    for item in sorted(by_item):
        first, second = by_item[item][0], by_item[item][1]
        for left_index, left in enumerate(first):
            for right_index, right in enumerate(second):
                pairs.append({
                    "pair_id": f"{item}-{left_index}-{right_index}",
                    "source_item": item,
                    "note": notes.get(item, ""),
                    "left": left,
                    "right": right,
                })

    pairs_file = out / "noticed-pairs.json"
    if not pairs_file.exists():
        pairs_file.write_text(json.dumps({"pairs": pairs}, indent=2), encoding="utf-8")
    pairs = json.loads(pairs_file.read_text(encoding="utf-8"))["pairs"]

    # 3 · judge — model, twice over the proposed pairs.
    jobs = []
    expected_pair_ids = {str(pair["pair_id"]) for pair in pairs}
    missing_pair_ids: dict[str, list[str]] = {}
    unexpected_pair_ids: dict[str, list[str]] = {}
    for number in range(1, PASSES + 1):
        judged = out / f"judged-{number}"
        coverage = _identity_coverage(judged, expected_pair_ids)
        if coverage["duplicated"]:
            return {
                "status": "blocked",
                "stopped": "duplicate pair judgement",
                "why": "one reader returned more than one judgement for an expected pair",
                "pass": number,
                "duplicated_pair_ids": coverage["duplicated"],
            }
        if not coverage["missing"]:
            continue
        missing_pair_ids[str(number)] = coverage["missing"]
        if coverage["unexpected"]:
            unexpected_pair_ids[str(number)] = coverage["unexpected"]
        jobs.append(_job(
            JUDGE.format(pairs_file=pairs_file, order_file=order_file, out=judged),
            judged, out / f"judged-{number}-scratch", "judge", len(pairs)))
    if jobs:
        return {"status": "waiting_for_readers",
                "stopped": "judging what was noticed", "records": len(records),
                "pairs": len(pairs), "outstanding": len(jobs), "work": jobs,
                "missing_pair_ids": missing_pair_ids,
                "unexpected_pair_ids": unexpected_pair_ids}

    # 4 · report — code. Both passes must call a pair the same thing, still work, and not already
    # required. The sentence carried forward is the builder's own quoted words: a reader decided
    # that this is work, and never what the work is said to be.
    said: dict[str, list[dict[str, object]]] = {}
    for number in range(1, PASSES + 1):
        for verdict in _load(out / f"judged-{number}"):
            said.setdefault(str(verdict.get("pair_id")), []).append(verdict)

    by_pair = {pair["pair_id"]: pair for pair in pairs}
    kept, already, split, not_work = [], [], [], []
    for pair_id, pair in sorted(by_pair.items()):
        verdicts = said.get(pair_id, [])
        if len(verdicts) != PASSES:
            return {
                "status": "blocked",
                "stopped": "incomplete pair judgement",
                "pair_id": pair_id,
                "answers": len(verdicts),
            }
        if {str(v.get("same_thing")) for v in verdicts} != {"yes"}:
            split.append(pair_id)
            continue
        covering = [str(v.get("covered_by")) for v in verdicts if v.get("covered_by")]
        if covering:
            already.append({"pair_id": pair_id, "covered_by": sorted(set(covering))})
            continue
        if {str(v.get("is_work")) for v in verdicts} != {"yes"}:
            not_work.append(pair_id)
            continue
        kept.append(pair)

    # One source item can yield the same thing through several pairs — the same note read into two
    # things by one reader and three by the other makes six pairs. Keep one per quoted passage.
    seen: set[tuple[str, str]] = set()
    rows = []
    for pair in kept:
        quote = str(pair["left"].get("quote") or "").strip()
        key = (pair["source_item"], quote[:200])
        if not quote or key in seen:
            continue
        seen.add(key)
        rid = f"n{len(rows) + 1}"
        rows.append({
            "requirement_id": rid,
            "requirement": quote,
            "part_id": f"{rid}.p1",
            "part": quote,
            "answer": "no",
            "noticed_while_building": pair["source_item"],
        })

    # 5 · the same thing seen by different builders is one piece of work, not many. Everything up
    # to here compares two readings of one note, so it cannot see that seventeen builders each
    # wrote down the same eight failing tests. Code proposes which candidates are worth comparing,
    # using the same wide net the requirements pairing uses, and judges none of them.
    same_pairs_file = out / "same-pairs.json"
    if not same_pairs_file.exists():
        proposed = pair_requirements.propose(
            {"part_answers": rows}, floor=0.15, cap=10 ** 6,
        )
        same_pairs_file.write_text(json.dumps({"pairs": [
            {"pair_id": f"{p['left']}-{p['right']}", "left": p["left"], "right": p["right"],
             "left_text": p["left_requirement"], "right_text": p["right_requirement"]}
            for p in proposed["pairs"]
        ]}, indent=2), encoding="utf-8")
    same_pairs = json.loads(same_pairs_file.read_text(encoding="utf-8"))["pairs"]

    jobs = []
    expected_same_ids = {str(pair["pair_id"]) for pair in same_pairs}
    missing_same_ids: dict[str, list[str]] = {}
    unexpected_same_ids: dict[str, list[str]] = {}
    for number in range(1, PASSES + 1):
        same = out / f"same-{number}"
        coverage = _identity_coverage(same, expected_same_ids)
        if coverage["duplicated"]:
            return {
                "status": "blocked",
                "stopped": "duplicate cross-builder judgement",
                "why": "one reader returned more than one judgement for an expected pair",
                "pass": number,
                "duplicated_pair_ids": coverage["duplicated"],
            }
        if not coverage["missing"]:
            continue
        missing_same_ids[str(number)] = coverage["missing"]
        if coverage["unexpected"]:
            unexpected_same_ids[str(number)] = coverage["unexpected"]
        jobs.append(_job(SAME.format(pairs_file=same_pairs_file, out=same),
                         same, out / f"same-{number}-scratch", "same", len(same_pairs)))
    if jobs and same_pairs:
        return {"status": "waiting_for_readers",
                "stopped": "deciding which of these are one thing", "records": len(records),
                "candidates_before_joining": len(rows), "pairs": len(same_pairs),
                "outstanding": len(jobs), "work": jobs,
                "missing_pair_ids": missing_same_ids,
                "unexpected_pair_ids": unexpected_same_ids}

    joined: dict[str, str] = {}
    agreed = 0
    for pair in same_pairs:
        calls = [v for number in range(1, PASSES + 1)
                 for v in _load(out / f"same-{number}")
                 if str(v.get("pair_id")) == pair["pair_id"]]
        if len(calls) < PASSES or {str(c.get("same_thing")) for c in calls} != {"yes"}:
            continue
        agreed += 1
        # Keep the earlier of the two, so a run over the same input joins the same way twice.
        left = joined.get(pair["left"], pair["left"])
        right = joined.get(pair["right"], pair["right"])
        first, second = sorted((left, right), key=lambda r: int(r.lstrip("n")))
        for name, to in list(joined.items()):
            if to == second:
                joined[name] = first
        joined[second] = first

    by_id = {row["requirement_id"]: row for row in rows}
    for row in rows:
        rid = row["requirement_id"]
        if joined.get(rid) and joined[rid] != rid:
            by_id[joined[rid]].setdefault("also_noticed_while_building", []).append(
                row["noticed_while_building"])
    rows = [row for row in rows if joined.get(row["requirement_id"], row["requirement_id"])
            == row["requirement_id"]]

    # What comes out here is not yet requirements. The sentence carried forward is the builder's
    # own words, and a builder's note is often a statement — "eight tests already fail" — which
    # nobody can make true. Measured: the first item this produced was refused by its builder for
    # exactly that reason, and it was right to refuse. So the list is also written as a description,
    # which is what the requirements machinery consumes, and that machinery is what turns an
    # observation into something with a check somebody else can run.
    description = out / "noticed-description.md"
    lines = ["# What the builders noticed and left alone", "",
             "Each entry below is quoted from the note a builder wrote while making one requirement",
             "true. They are observations, not requirements: some are faults, some are questions,",
             "some are statements of fact about the built system. Nothing here has a check yet.", ""]
    for row in rows:
        seen_by = [row["noticed_while_building"], *(row.get("also_noticed_while_building") or [])]
        lines.append(f"## {row['requirement_id']} — noticed while building "
                     f"{', '.join(sorted(set(seen_by)))}")
        lines.append("")
        lines.append(row["requirement"].strip())
        lines.append("")
    description.write_text("\n".join(lines), encoding="utf-8")

    report = out / "noticed-report.json"
    report.write_text(json.dumps({
        "subject": "what the builders noticed and left alone",
        "part_answers": rows,
    }, indent=2), encoding="utf-8")

    return {
        "status": "complete",
        "records": len(records),
        "pairs": len(pairs),
        "same_thing_both_passes": len(kept),
        "already_on_the_build_list": already,
        "read_as_different_things": len(split),
        "judged_not_work": len(not_work),
        "candidates": len(rows),
        "joined_as_one_thing": agreed,
        "report": str(report),
        "description": str(description),
        "then_first": (
            "these are observations, not requirements. Put the description through the "
            "requirements machinery, which is what gives each one a check somebody else can run, "
            "and build from what it produces"
        ),
        "then": ("run run.py with --report this file and a fresh --work directory: the same "
                 "pairing, dependency reading, ordering and building runs over these"),
    }


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
        "missing_pair_ids": result.get("missing_pair_ids"),
        "work": [job.get("waiting_for") for job in result.get("work") or []],
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True,
                        help="the build work directory holding build-*/change.json")
    parser.add_argument("--order", type=Path, required=True,
                        help="the build list, so a reader can say a thing is already required")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reader-command", default=None,
                        help="a command that takes an instruction on standard input and carries "
                             "it out. Given one, this runs its own readers instead of handing the "
                             "jobs back. It never picks the reader.")
    args = parser.parse_args(argv)

    work, order, out = args.work.resolve(), args.order.resolve(), args.out.resolve()
    if not args.reader_command:
        result = collect(work, order, out)
        print(json.dumps(result, indent=2))
        return _exit_code(result)

    stuck, seen = 0, None
    while True:
        result = collect(work, order, out)
        jobs = result.get("work")
        if not jobs:
            print(json.dumps(result, indent=2, default=str))
            return _exit_code(result)
        here = _progress_key(result)
        stuck = stuck + 1 if here == seen else 0
        seen = here
        if stuck >= 2:
            result["status"] = "blocked"
            result["stopped"] = "reading stalled"
            result["why"] = "a round of reading changed nothing twice over"
            print(json.dumps(result, indent=2, default=str))
            return _exit_code(result)
        readers._launch(jobs, args.reader_command, out, out, "read")


if __name__ == "__main__":
    raise SystemExit(main())
