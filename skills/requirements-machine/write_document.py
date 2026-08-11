#!/usr/bin/env python3
"""The last stage: turn the verdicts into the document itself.

Everything before this produces records — one file per requirement, one per verdict, all of it
correct and none of it readable. For one whole run the machinery's final act was to print a list of
identifiers to a terminal, and whether it had produced a requirements document depended on whether
somebody remembered to redirect the output. A result nobody can open is not a deliverable.

So this writes the document. It invents nothing: every line comes from a record on disk, and the
one judgement it makes — which section a requirement belongs in — is the verdict the two measuring
passes already agreed on. Where they did not agree, the requirement goes to the section for a
person, carrying both calls, rather than being sorted by whichever reader is listed first.

The order inside a section is the order the requirements were produced, so two runs of this tool
over the same records produce the same document byte for byte.

Usage:  python3 write_document.py --report <report.json> --requirements <requirements.json> \
                                  --out <document.md>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

#: The sections, in the order a reader needs them: what is missing, what is wrong, what to take out,
#: what is already true, and last the places nobody but the goal's owner can settle. The wording is
#: the reader's, not the machinery's — "add" as a heading tells a reader nothing on its own.
SECTIONS = [
    ("add", "To add — nothing in the build addresses these"),
    ("change", "To change — something addresses these, but not enough of it"),
    ("remove", "To remove — the build does this and should not"),
    ("already_met", "Already true — kept so the list is the whole picture, not only the work"),
]


def _requirement_block(row: dict[str, object]) -> list[str]:
    lines = [f"### {row['id']} · {row['requirement']}", ""]
    check = str(row.get("check") or "").strip()
    if check:
        lines += [f"**How to tell it is met.** {check}", ""]
    came_from = row.get("from") or []
    if came_from:
        lines += [f"*From the description: {', '.join(str(x) for x in came_from)}.*", ""]
    return lines


#: What the reader's yes/no means for the person who has to build it. The whole point of the part
#: is that this is a fact rather than a grading: the part is either true of the build or it is not.
_STATE = {
    "no": "to build",
    "yes": "already true",
    "split": "unsettled — the two readers answered differently",
}


def _parts_document(report: dict[str, object], requirements: list[dict[str, object]]) -> list[str]:
    """The document whose unit is the part.

    A requirement is a paragraph; a part is a job. Whoever implements this needs the job — one
    thing that is separately true or false, with the line that proves it if it is already true.
    Grouping the parts under their requirement keeps the reason visible without making the reason
    the unit. Ordering is the order the parts were produced, so two runs over the same records
    produce the same document.
    """

    by_id = {str(row["id"]): row for row in requirements}
    rows = report.get("part_answers") or []
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["requirement_id"]), []).append(row)

    tally = {key: 0 for key in _STATE}
    for row in rows:
        tally[str(row.get("answer", "split"))] = tally.get(str(row.get("answer", "split")), 0) + 1

    out = [
        f"## What must be built — {tally['no']} of {len(rows)} parts",
        "",
        "Each entry below is one thing that is separately true or false of the build today. That is "
        "the unit deliberately: a requirement is a paragraph, and a part is a job. A part marked "
        "already true carries the line that makes it true, so it can be checked rather than taken "
        "on trust.",
        "",
    ]

    for rid in sorted(grouped, key=lambda r: (len(r), r)):
        requirement = by_id.get(rid)
        heading = requirement["requirement"] if requirement else "(requirement not found)"
        out += [f"### {rid} · {heading}", ""]
        if requirement and requirement.get("check"):
            out += [f"*How to tell the whole of it is met: {requirement['check']}*", ""]
        for row in grouped[rid]:
            state = _STATE.get(str(row.get("answer")), str(row.get("answer")))
            out.append(f"- **[{state}]** {row['part']}")
            # Only a part that is actually true gets the line that makes it true. The evidence
            # travels with every part, because a disputed part has a line behind one of its two
            # answers — but printing it under a job still to build read as "already done by" beside
            # "[to build]", which is the opposite of what the run concluded.
            evidence = row.get("evidence") if str(row.get("answer")) == "yes" else None
            if isinstance(evidence, dict) and evidence.get("where"):
                where = str(evidence["where"]).split("/")[-1]
                out.append(f"  - already done by `{where}:{evidence.get('line')}` — "
                           f"`{str(evidence.get('text') or '').strip()[:120]}`")
            if str(row.get("answer")) == "split":
                calls = ", ".join(f"{k}: {v}" for k, v in sorted((row.get("calls") or {}).items()))
                out.append(f"  - the two readers answered {calls}; nobody resolved it for you")
                seen = row.get("evidence")
                if isinstance(seen, dict) and seen.get("where"):
                    where = str(seen["where"]).split("/")[-1]
                    out.append(f"  - the one that said yes pointed at `{where}:{seen.get('line')}`")
        out.append("")

    return out


def compose(report: dict[str, object], requirements: list[dict[str, object]]) -> str:
    by_id = {str(row["id"]): row for row in requirements}
    # A requirement in more than one verdict list would silently appear twice; the report cannot
    # produce that today, but a document that quietly duplicates is worse than one that refuses.
    seen: set[str] = set()

    if report.get("measured_against_build", True):
        provenance = (
            "Produced by the requirements machinery from the subject's description, measured "
            "against the build. Every requirement below was read out of the description by two "
            "readers who could not see each other, and given its verdict by two more. Nothing "
            "here was written by hand."
        )
    else:
        provenance = (
            "Produced by the requirements machinery from the subject's description. Nothing is "
            "built yet, so every requirement and every separately testable part is work to add. "
            "The reading still ran twice and the shared parts split still ran; measuring readers "
            "were not invented for a build that does not exist."
        )

    out = [
        f"# Requirements — {report['subject']}",
        "",
        provenance,
        "",
    ]

    # Who read it belongs in the document, not only in the records beside it. The machinery does
    # not choose a reader — it is run from somewhere, and that somewhere supplies one — so a
    # document that does not say what read it cannot be compared with the next one.
    read_by = report.get("read_by") or {}
    if read_by:
        out += ["**Read by.**", ""]
        for stage, who in sorted(read_by.items()):
            if isinstance(who, dict):
                model = who.get("model") or "unnamed"
                harness = who.get("harness")
                out.append(f"- {stage} — {model}{f', running in {harness}' if harness else ''}")
            else:
                out.append(f"- {stage} — {who}")
        out.append("")

    counts = ", ".join(
        f"{len(report.get(key) or [])} {title.split(' — ')[0].lower()}" for key, title in SECTIONS
    )
    out += [
        f"**{report['requirements']} requirements**: {counts}, and "
        f"{len(report.get('for_a_person') or [])} for the person who owns the goal.",
        "",
    ]

    for key, title in SECTIONS:
        ids = list(report.get(key) or [])
        out += [f"## {title}", ""]
        if not ids:
            out += ["None.", ""]
            continue
        for rid in ids:
            row = by_id.get(str(rid))
            if row is None:
                out += [f"### {rid}", "", "*This requirement is not in the requirements file.*", ""]
                continue
            if rid in seen:
                out += [f"### {rid}", "", "*Listed twice by the report; shown once.*", ""]
                continue
            seen.add(str(rid))
            out += _requirement_block(row)

    out += [
        "## For the person who owns the goal",
        "",
        "The machinery refuses to settle these. They are not oversights; they are the two places "
        "where agreement was not reached and guessing would hide it.",
        "",
    ]
    people = report.get("for_a_person") or []
    if not people:
        out += ["None.", ""]
    for item in people:
        kind = str(item.get("kind"))
        if kind == "verdicts disagree":
            rid = str(item.get("requirement"))
            row = by_id.get(rid)
            calls = ", ".join(f"{k}: {v}" for k, v in sorted((item.get("calls") or {}).items()))
            out += [
                f"### {rid} · {row['requirement'] if row else 'requirement not found'}",
                "",
                f"One reader called it **{calls}**. Both cited real lines; they differ on how much "
                "of the requirement counts as done.",
                "",
            ]
            if row and row.get("check"):
                out += [f"**How to tell it is met.** {row['check']}", ""]
        else:
            out += [
                f"### Two requirements, one judgement merged and the other kept apart",
                "",
                f"- {item.get('left')}",
                f"- {item.get('right')}",
                "",
            ]
            for why in item.get("why") or []:
                out += [f"> {why}", ""]

    return "\n".join(out).rstrip() + "\n"


def compose_parts(report: dict[str, object], requirements: list[dict[str, object]]) -> str:
    """The second document: the same answer, written as jobs rather than as requirements.

    Two documents, not one with two halves. The requirements document is what the breakdown is made
    from and what an argument about scope is had over; the parts document is what somebody picks up
    and builds. Collapsing them would mean the thing you reason with and the thing you work from are
    the same length, and one of them would end up unread.
    """

    out = [
        f"# What to build — {report['subject']}",
        "",
        "The requirements for this subject, broken into parts: each entry is one thing that is "
        "separately true or false of the build today. This is the breakdown of the requirements "
        "document beside it, which stays the place the reasoning lives.",
        "",
    ]
    out += _parts_document(report, requirements)
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--parts-out", type=Path, default=None,
                        help="where the breakdown goes; written in addition to --out, never "
                             "instead of it")
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    final = json.loads(args.requirements.read_text(encoding="utf-8"))
    document = compose(report, final["requirements"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(document, encoding="utf-8")

    written = {
        "document": str(args.out),
        "requirements": report["requirements"],
        "lines": len(document.splitlines()),
    }
    if args.parts_out is not None and report.get("part_answers"):
        breakdown = compose_parts(report, final["requirements"])
        args.parts_out.write_text(breakdown, encoding="utf-8")
        written["breakdown"] = str(args.parts_out)
        written["parts"] = report.get("parts")

    print(json.dumps(written, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
