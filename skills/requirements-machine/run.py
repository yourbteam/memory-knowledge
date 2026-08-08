#!/usr/bin/env python3
"""The requirements machinery, driven from one command.

Everything here already existed as separate tools, and the order they run in lived in one
conversation. That is not machinery — it is a habit. This owns the order, owns the gates, and
refuses to advance when a stage has not finished its job.

It does not do the reading. Reading a description and judging a requirement are the parts a model
does, and this hands each of them out as a work packet: a prompt, the exact input file, and the
directory the answers go in. It then checks the answers before the next stage starts. Every
narrowing this machinery has earned came from code fixing what gets looked at and a model judging
what it means; the runner is that division made permanent.

    python3 run.py --subject "<what is being described>" \
                   --description <file.md> --work <dir> [--built <repo>]

State lives in the work directory, so the command is re-runnable: a stage whose output is already
there and passes its gate is not run again. Stopping and resuming is the normal case, because two
of the stages need a person.

Stages, in order, each with the gate that must pass before the next begins:

  1  split        code   the description becomes obligations + leftover; the counts must balance
  2  oblige       model  every obligation ends in a requirement or a recorded dismissal
  3  leftover     model  the leftover is read on its own, by someone who cannot see stage 2
  4  pair         code   possible duplicates are found; no judgement is made
  5  merge        model  each pair judged twice, independently
  6  consolidate  code   only merges both judgements agreed are applied
  7  measure      model  every requirement gets one verdict against what is built
  8  report       code   nothing may be missing, and the two places a person decides are named

Run with no `--built` to stop after stage 6: that is the correct behaviour when nothing has been
built yet, and the first six stages are the whole answer.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: What each model stage is asked to do. Held here rather than in the caller's head, because a
#: stage whose instruction is retyped each time is a stage that drifts.
PACKETS = {
    "oblige": (
        "Read {skill}. Account for EVERY entry in {input}. For each write one file into {out} "
        "named <id>.json: either a requirement with the fields the skill lists plus "
        "'candidate_id', or a dismissal {{'candidate_id', 'not_a_requirement_because', "
        "'evidence'}}. Dismiss only for a reason you can point at in the text. Read only the "
        "description and this list — not the built system."
    ),
    "leftover": (
        "Read {skill}. The entries in {input} are every part of the description a first reader "
        "did NOT take, because none carries an obliging word. Find the places that oblige the "
        "subject to do something anyway — a definition it must honour, a fact stated about the "
        "output, a consequence named as a reason, a capability promised to a reader. Write one "
        "file per find into {out}, named after the entry id, with the skill's fields plus "
        "'candidate_id'. Finding nothing in a section is a legitimate result. Do not open the "
        "description itself or the built system."
    ),
    "merge": (
        "Judge every pair in {input}. Merge ONLY where the same thing must become true: two "
        "requirements can share a sentence, share almost every word, and still differ — one "
        "saying a section exists and the other what it must contain, one forbidding something "
        "and the other saying what to do instead. Write one file per pair into {out}: "
        "{{'left','right','verdict':'merge'|'keep both','surviving_requirement','why'}}. Read "
        "nothing but the pairs."
    ),
    "measure": (
        "Give every requirement in {input} exactly one verdict against what is actually built in "
        "{built}: 'already met', 'change', 'add', or 'remove'. Write one file per requirement "
        "into {out}: {{'candidate_id','verdict','evidence','what_must_change'}}. Read the code "
        "and the real output — a verdict from reasoning about what the code probably does is "
        "worthless. Do not rewrite or reinterpret a requirement; judge the one you were given."
    ),
}

#: A model stage is run twice, by readers who cannot see each other. Agreement is the only
#: evidence this machinery has ever accepted that a stage is reliable.
PASSES = 2


def _run(args: list[str]) -> dict[str, object]:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode not in (0, 1):
        raise SystemExit(f"{' '.join(args)}\n{result.stderr.strip()}")
    return json.loads(result.stdout)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _records_in(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return len([p for p in directory.glob("*.json") if p.name != "summary.json"])


def _packet(name: str, work: Path, **fields: object) -> dict[str, object]:
    """A stage a person or an agent has to run, stated completely enough to hand over."""

    return {
        "stage": name,
        "instruction": PACKETS[name].format(**fields),
        "waiting_for": str(fields.get("out")),
    }


def drive(subject: str, description: Path, work: Path, built: Path | None) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    skill = HERE / "FIRST-HALF-STEP-ONE.md"

    # 1 · split — code. The gate is arithmetic: nothing may be in neither list.
    split_path = work / "split.json"
    if not split_path.exists():
        _write(split_path, _run([
            sys.executable, str(HERE / "enumerate_obligations.py"),
            "--description", str(description),
        ]))
    split = json.loads(split_path.read_text(encoding="utf-8"))
    if not split["partition"]["balances"]:
        return {"stopped": "split", "why": "the description did not partition", "split": split["partition"]}

    obligations_in = work / "obligations.json"
    leftover_in = work / "leftover.json"
    _write(obligations_in, {"obligations": split["obligations"]})
    _write(leftover_in, {"leftover": split["leftover"]})

    # 2 and 3 · oblige and leftover — model, two passes each, run in either order.
    waiting = []
    for stage, source, count in (
        ("oblige", obligations_in, len(split["obligations"])),
        ("leftover", leftover_in, len(split["leftover"])),
    ):
        for index in range(1, PASSES + 1):
            out = work / f"{stage}-{index}"
            if stage == "oblige" and _records_in(out) < count:
                waiting.append(_packet(stage, work, skill=skill, input=source, out=out))
            elif stage == "leftover" and not out.is_dir():
                waiting.append(_packet(stage, work, skill=skill, input=source, out=out))
    if waiting:
        return {"stopped": "reading", "why": "a reading stage has not finished", "work": waiting}

    # The obligation stage's gate is coverage: every obligation accounted for, in both passes.
    for index in range(1, PASSES + 1):
        coverage = _run([
            sys.executable, str(HERE / "check_coverage.py"),
            "--candidates", str(obligations_in), "--records", str(work / f"oblige-{index}"),
        ])
        if not coverage["complete"]:
            return {"stopped": "coverage", "pass": index, "unaccounted": coverage["unaccounted"]}

    # 4 · pair — code. It proposes; it never merges.
    pairs_path = work / "pairs.json"
    if not pairs_path.exists():
        _write(pairs_path, _run([
            sys.executable, str(HERE / "pair_candidates.py"),
            "--records", str(work / "oblige-1"), "--records", str(work / "leftover-1"),
        ]))
    pairs = json.loads(pairs_path.read_text(encoding="utf-8"))

    # 5 · merge — model, twice.
    waiting = [
        _packet("merge", work, input=pairs_path, out=work / f"merge-{index}")
        for index in range(1, PASSES + 1)
        if _records_in(work / f"merge-{index}") < pairs["pairs_to_read"]
    ]
    if waiting:
        return {"stopped": "merging", "why": "a merge pass has not judged every pair",
                "pairs": pairs["pairs_to_read"], "work": waiting}

    # 6 · consolidate — code. Only merges every pass agreed on.
    final_path = work / "requirements.json"
    if not final_path.exists():
        _write(final_path, _run([
            sys.executable, str(HERE / "consolidate.py"),
            "--records", str(work / "oblige-1"), "--records", str(work / "leftover-1"),
            *sum((["--merges", str(work / f"merge-{i}")] for i in range(1, PASSES + 1)), []),
        ]))
    final = json.loads(final_path.read_text(encoding="utf-8"))

    if built is None:
        return {
            "subject": subject,
            "requirements": final["count"],
            "for_a_person": _decisions(final),
            "note": "nothing is built, so the requirements are what must be added. Stages 7 and 8 "
                    "do not apply.",
        }

    # 7 · measure — model, twice.
    waiting = [
        _packet("measure", work, input=final_path, out=work / f"measure-{index}", built=built)
        for index in range(1, PASSES + 1)
        if _records_in(work / f"measure-{index}") < final["count"]
    ]
    if waiting:
        return {"stopped": "measuring", "why": "a measuring pass has not judged every requirement",
                "requirements": final["count"], "work": waiting}

    # 8 · report — code. Nothing missing, and the disagreements named rather than resolved.
    verdicts: dict[str, dict[str, str]] = {}
    for index in range(1, PASSES + 1):
        for path in sorted((work / f"measure-{index}").glob("*.json")):
            if path.name == "summary.json":
                continue
            row = json.loads(path.read_text(encoding="utf-8"))
            verdicts.setdefault(str(row.get("candidate_id")), {})[f"pass-{index}"] = str(
                row.get("verdict"),
            )

    missing = [row["id"] for row in final["requirements"] if row["id"] not in verdicts]
    if missing:
        return {"stopped": "report", "why": "requirements with no verdict", "missing": missing}

    agreed = {rid: list(calls.values())[0] for rid, calls in verdicts.items()
              if len(set(calls.values())) == 1}
    split_calls = {rid: calls for rid, calls in verdicts.items() if len(set(calls.values())) > 1}

    return {
        "subject": subject,
        "requirements": final["count"],
        "add": sorted(r for r, v in agreed.items() if v == "add"),
        "change": sorted(r for r, v in agreed.items() if v == "change"),
        "remove": sorted(r for r, v in agreed.items() if v == "remove"),
        "already_met": sorted(r for r, v in agreed.items() if v == "already met"),
        "for_a_person": _decisions(final) + [
            {"kind": "verdicts disagree", "requirement": rid, "calls": calls}
            for rid, calls in sorted(split_calls.items())
        ],
    }


def _decisions(final: dict[str, object]) -> list[dict[str, object]]:
    """The places this machinery will not decide for anyone."""

    return [
        {"kind": "merge split between judgements", **row}
        for row in final.get("merges_refused_for_disagreement", [])
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--description", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--built", type=Path, default=None,
                        help="the repository to measure against; omit when nothing is built yet")
    args = parser.parse_args(argv)

    state = drive(
        args.subject, args.description.resolve(), args.work.resolve(),
        args.built.resolve() if args.built else None,
    )
    print(json.dumps(state, indent=2))
    return 1 if state.get("stopped") else 0


if __name__ == "__main__":
    raise SystemExit(main())
