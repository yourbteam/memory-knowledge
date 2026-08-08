#!/usr/bin/env python3
"""First half, step four: put the requirements that might be duplicates in front of a reader.

Three passes now produce requirements for one subject — the obliging sentences, and two readings
of everything the obliging words left behind. They overlap: a prohibition was taken from one
sentence and the definition that makes it decidable from another, and both became requirements.
Merging them is a judgement no regular expression can make.

But the *search* is not a judgement, and it is the part a reader does badly. Comparing every
requirement against every other is hundreds of comparisons, and a reader who has to do them all
will skim. So code does the search and hands over only the pairs worth looking at, with the whole
of both requirements, and the reader decides.

The rule this exists to protect: **merge only where the same thing must become true.** Two
requirements can quote the same sentence, share most of their words, and still be different — one
saying a section exists and the other saying what it must contain. In the run that motivated this,
two near-identical rules were deliberately kept apart by both readers, and a merger that cannot
reproduce that distinction is wrong. So this proposes; it never merges.

Usage:  python3 pair_candidates.py --records <dir> [--records <dir> ...] [--floor 0.35]
Prints one JSON object: every requirement read, and the candidate pairs with their overlap.
"""

from __future__ import annotations

import argparse
import json
import re
from itertools import combinations
from pathlib import Path

#: Words that carry no distinguishing weight in a requirement sentence. Kept short deliberately:
#: an aggressive stop list makes unrelated requirements look alike, which is the failure that
#: costs most here.
_COMMON = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "is", "are", "be", "it", "its",
    "that", "this", "for", "with", "by", "as", "at", "from", "must", "not", "never", "any",
    "every", "each", "so", "than", "which", "what", "when", "where", "who", "whom", "was",
}

_WORD = re.compile(r"[a-z][a-z'-]+")


def _terms(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.lower()) if word not in _COMMON}


def _overlap(left: set[str], right: set[str]) -> float:
    """How much two requirements share, as a fraction of the smaller one.

    Deliberately not the symmetric measure: a short requirement wholly contained in a longer one
    is exactly the case worth showing a reader, and a symmetric score buries it.
    """

    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _load(directories: list[Path]) -> list[dict[str, object]]:
    records = []
    for directory in directories:
        for path in sorted(directory.glob("*.json")):
            if path.name == "summary.json":
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if not isinstance(record, dict):
                continue
            if record.get("not_a_requirement_because"):
                continue          # a dismissal is not a requirement and has nothing to merge with
            requirement = str(record.get("requirement") or "").strip()
            if not requirement:
                continue
            records.append({
                "id": f"{directory.name}:{record.get('candidate_id') or path.stem}",
                "from": directory.name,
                "requirement": requirement,
                "source": str(record.get("source") or ""),
                "check": str(record.get("check") or ""),
            })
    return records


def pair_candidates(directories: list[Path], floor: float) -> dict[str, object]:
    records = _load(directories)
    terms = {row["id"]: _terms(str(row["requirement"])) for row in records}
    by_id = {row["id"]: row for row in records}

    pairs = []
    for left, right in combinations(sorted(by_id), 2):
        score = _overlap(terms[left], terms[right])
        same_source = by_id[left]["source"] and by_id[left]["source"] == by_id[right]["source"]
        if score < floor and not same_source:
            continue
        pairs.append({
            "left": left,
            "right": right,
            "overlap": round(score, 3),
            # Two requirements quoting the same sentence are worth a look whatever their wording
            # shares, because one of them is often the sentence's other half.
            "same_source_sentence": bool(same_source),
            "left_requirement": by_id[left]["requirement"],
            "right_requirement": by_id[right]["requirement"],
            "left_check": by_id[left]["check"],
            "right_check": by_id[right]["check"],
        })

    pairs.sort(key=lambda row: (-float(row["overlap"]), str(row["left"]), str(row["right"])))
    return {
        "requirements": len(records),
        "sources": [str(d) for d in directories],
        "floor": floor,
        "comparisons": len(records) * (len(records) - 1) // 2,
        "pairs_to_read": len(pairs),
        "pairs": pairs,
        "note": (
            "These are candidates, not merges. Merge only where the same thing must become true; "
            "two requirements can share a sentence and still differ in what they require."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, action="append", required=True)
    parser.add_argument("--floor", type=float, default=0.35,
                        help="the share of the smaller requirement's words that must be common")
    args = parser.parse_args(argv)

    print(json.dumps(
        pair_candidates([d.resolve() for d in args.records], args.floor), indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
