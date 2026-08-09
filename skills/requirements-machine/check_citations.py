#!/usr/bin/env python3
"""Measuring stage: verify what a reader cited, and let the verdict follow from it.

Two readers given the same requirements and the same instruction agreed on sixty-nine verdicts of
ninety-one. Sharpening the wording moved that by one. Two lexical searches — plain, then by
co-occurrence — carried no signal at all: requirements both readers agreed nothing addresses
scored the same as ones both agreed are already done.

So code cannot classify this. What code can do is check a citation. A reader who says something
already addresses a requirement can be made to say *where*: a file, a line, and the text of that
line. That claim is checkable — the line either exists and says what was quoted, or it does not —
and the verdict then follows from the citation rather than from a label chosen freely.

  cites nothing            → nothing addresses it
  cites something          → something addresses it; whether it suffices is the reader's judgement
  cites something wrongly  → the record is refused and the reader is told exactly which line and
                             what was found there instead

This never overrules a reader on whether a requirement is satisfied. It refuses records whose
evidence does not exist, which is the part that was never checked before.

Usage:  python3 check_citations.py --records <dir> --built <repo>
Prints, per record, whether each citation resolves, and a refusal message for the ones that do not.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

#: How much of the quoted line must match. A reader retyping a line will normalise whitespace and
#: may trim it; demanding a byte-identical match would refuse honest citations.
def _normalise(text: str) -> str:
    return " ".join(text.split()).lower()


def _resolve(built: Path, citation: dict[str, object]) -> dict[str, object]:
    where = str(citation.get("where") or "").strip()
    line_no = citation.get("line")
    quoted = str(citation.get("text") or "").strip()

    if not where:
        return {"ok": False, "why": "the citation names no file"}
    path = built / where
    if not path.is_file():
        return {"ok": False, "why": f"no file at {where}"}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        return {"ok": False, "why": f"{where} could not be read: {error}"}

    if not isinstance(line_no, int) or not 1 <= line_no <= len(lines):
        return {"ok": False, "why": f"{where} has {len(lines)} lines; {line_no} is not one of them"}

    actual = lines[line_no - 1]
    if not quoted:
        return {"ok": True, "line": actual.strip(), "matched": "line exists; nothing was quoted"}
    if _normalise(quoted) in _normalise(actual):
        return {"ok": True, "line": actual.strip(), "matched": "exact"}

    # Readers cite a line and quote a nearby one often enough that a window is worth searching —
    # but the refusal must say what was actually there, or a retry cannot act on it.
    window = range(max(0, line_no - 4), min(len(lines), line_no + 3))
    for index in window:
        if _normalise(quoted) in _normalise(lines[index]):
            return {"ok": True, "line": lines[index].strip(), "matched": f"found at line {index + 1}"}
    return {
        "ok": False,
        "why": (
            f"{where}:{line_no} does not contain the quoted text. That line reads: "
            f"{actual.strip()[:160]!r}. Cite the line that actually carries what you are pointing "
            f"at, or say nothing addresses this requirement."
        ),
    }


def check(records: Path, built: Path) -> dict[str, object]:
    out, refused = [], []
    for path in sorted(records.glob("*.json")):
        if path.name == "summary.json":
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as error:
            refused.append({"file": path.name, "why": f"not readable as a record: {error}"})
            continue

        citations = record.get("citations") or []
        results = [_resolve(built, c) for c in citations if isinstance(c, dict)]
        bad = [r for r in results if not r["ok"]]

        row = {
            "id": str(record.get("candidate_id") or path.stem),
            "verdict": str(record.get("verdict") or ""),
            "citations": len(citations),
            "resolved": len(results) - len(bad),
            "unresolved": [r["why"] for r in bad],
            # The one thing the citation decides on its own.
            "follows_from_citations": "nothing addresses it" if not citations else
                                      "something addresses it",
        }
        # A record claiming something is done while citing nothing is unfalsifiable; refuse it.
        if citations == [] and row["verdict"] in {"already met", "change", "remove"}:
            row["unresolved"] = row["unresolved"] + [
                f"the verdict is {row['verdict']!r} but nothing is cited. Cite the file, line and "
                f"text that carries the behaviour, or the verdict is that nothing addresses this."
            ]
        if row["unresolved"]:
            refused.append(row)
        out.append(row)

    return {
        "built": str(built),
        "records": len(out),
        "refused": len(refused),
        "checked": out,
        "refusals": refused,
        "note": (
            "This checks that cited evidence exists and says what was quoted. Whether the cited "
            "thing satisfies the requirement remains the reader's judgement."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--built", type=Path, required=True)
    args = parser.parse_args(argv)

    result = check(args.records.resolve(), args.built.resolve())
    print(json.dumps(result, indent=2))
    return 1 if result["refused"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
