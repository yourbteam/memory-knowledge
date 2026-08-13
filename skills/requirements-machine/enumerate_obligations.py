#!/usr/bin/env python3
"""First half, step two: split a description into what obliges and what is left.

Step one of the first half produces one requirement from a description, and two runs given the
same description produced the same one. That proves a run can read a description; it does not
prove a run can read all of it. The second half hit exactly this wall: a numbered list was what
turned completeness from a feeling into a count.

An obligation announces itself in language — something *must* be true, must *never* happen, the
thing is *not done while* something holds — and those sentences can be found without knowing
anything about the subject. But a description also obliges things without ever using such a word,
and a reader that only sees the obliging sentences cannot find those.

So this does not filter. It **partitions**: every unit of the description lands in exactly one of
two numbered lists, and the tool states the arithmetic so the claim is checkable rather than
trusted. The obligations go to a run that turns each into a requirement or a recorded dismissal.
The leftover goes to a different run that sees nothing else — it cannot re-find what it never
sees, and anything it finds there is something the obliging words missed.

A unit is one sentence of prose, one table row, or one heading. Nothing is dropped for being
short, for sitting in a table, or for being a title; short and awkward units land in the leftover
rather than vanishing, because a list that quietly discards is not a partition.

Usage:  python3 enumerate_obligations.py --description <file.md> [--min-words 6]
Prints one JSON object with `obligations`, `leftover`, and a `partition` block that must balance.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

#: The ways a description says something is owed. Ordered longest-first so the most specific
#: marker wins when a sentence carries more than one.
_MARKERS = (
    "must never",
    "is not done while",
    "is not done until",
    "may not",
    "must not",
    "never",
    "must",
    "has to",
    "have to",
    "refuses",
    "refuse",
    "is required",
    "are required",
    "shall",
)

_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")

#: A sentence end. Deliberately blunt: a description written for a person uses full stops, and a
#: cleverer splitter would silently drop the sentences it disagreed with.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

#: Markdown decoration that changes nothing about what a sentence obliges.
_DECORATION = re.compile(r"[*_`]+")

_LIST_ITEM = re.compile(r"^\s*([-*+]|\d+\.)\s+")
_SOURCE = re.compile(r"^\s*_?Source:\s*`?([^`]+?)`?_?\s*$", re.IGNORECASE)


def _clean(text: str) -> str:
    return _DECORATION.sub("", text).strip()


def _sentences(block: str) -> list[str]:
    text = _clean(block)
    if not text:
        return []
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def _marker_in(sentence: str) -> str | None:
    lowered = sentence.lower()
    for marker in _MARKERS:
        # Word boundaries, so "must" does not match inside another word and "never" does not
        # match a heading like "Nevertheless".
        if re.search(rf"(?<![a-z]){re.escape(marker)}(?![a-z])", lowered):
            return marker
    return None


def _units(description: Path) -> list[dict[str, object]]:
    """Every unit of the description, in order, each tagged with the heading it sits under.

    A description written for a person is wrapped at some column, so a sentence rarely occupies
    one line. An earlier version of this cut obligations in half at the wrap and numbered the
    pieces separately; sentences are therefore assembled from whole paragraphs.
    """

    units: list[dict[str, object]] = []
    heading = ""
    depth = 0
    paragraph: list[str] = []
    awaiting_source: list[int] = []

    def add(row: dict[str, object]) -> None:
        units.append(row)
        awaiting_source.append(len(units) - 1)

    def flush() -> None:
        joined = " ".join(paragraph).strip()
        paragraph.clear()
        for sentence in _sentences(joined):
            add({"text": sentence, "under": heading, "under_depth": depth,
                 "kind": "sentence", "sources": []})

    for line in [*description.read_text(encoding="utf-8", errors="replace").splitlines(), ""]:
        match = _HEADING.match(line)
        source_match = _SOURCE.match(line)
        is_table = line.lstrip().startswith("|")
        starts_item = _LIST_ITEM.match(line) is not None
        blank = not line.strip()

        if match or source_match or is_table or blank or starts_item:
            flush()
        if source_match:
            source = source_match.group(1).strip()
            for index in awaiting_source:
                sources = units[index].setdefault("sources", [])
                if source not in sources:
                    sources.append(source)
            awaiting_source.clear()
            # The marker remains a unit so the partition arithmetic and stable ids do not change.
            units.append({"text": f"Source: {source}", "under": heading,
                          "under_depth": depth, "kind": "source", "sources": [source]})
            continue
        if match:
            # The heading is itself a unit — it can carry an obligation, and excluding it would
            # put part of the description in neither list.
            heading = _clean(match.group(2))
            # How deep the heading sits is kept because it is the only thing separating a
            # document's title from the sections it contains, and anything counting sections —
            # how many of them produced a requirement, say — otherwise counts the title as one.
            depth = len(match.group(1))
            add({"text": heading, "under": heading, "under_depth": depth,
                 "kind": "heading", "sources": []})
            continue
        if is_table:
            # A table row records something rather than obliging anyone, but it is still part of
            # the description, so it goes to the leftover reader rather than being discarded.
            add({"text": _clean(line), "under": heading, "under_depth": depth,
                 "kind": "table-row", "sources": []})
            continue
        if blank:
            continue
        paragraph.append(_LIST_ITEM.sub("", line).strip())

    flush()
    return units


def enumerate_obligations(description: Path, min_words: int) -> dict[str, object]:
    obligations: list[dict[str, object]] = []
    leftover: list[dict[str, object]] = []
    seen: set[str] = set()
    repeated = 0

    for unit in _units(description):
        key = str(unit["text"]).lower()
        if key in seen:
            # The same sentence twice is one obligation. It is counted so the partition still
            # balances against the number of units read.
            repeated += 1
            continue
        seen.add(key)

        marker = _marker_in(str(unit["text"])) if unit["kind"] == "sentence" else None
        long_enough = len(str(unit["text"]).split()) >= min_words
        if marker and long_enough:
            obligations.append({**unit, "marker": marker})
        else:
            leftover.append({**unit, "why_left": (
                "no obliging word" if not marker else "too short to state an obligation alone"
            ) if unit["kind"] == "sentence" else f"not prose: {unit['kind']}"})

    for index, row in enumerate(obligations, start=1):
        row["id"] = f"o{index}"
    for index, row in enumerate(leftover, start=1):
        row["id"] = f"L{index}"

    units_read = len(obligations) + len(leftover) + repeated
    return {
        "description": str(description),
        "obligations": obligations,
        "leftover": leftover,
        # The claim this tool makes is that nothing was dropped. It is stated as arithmetic so a
        # reader can check it instead of trusting it.
        "partition": {
            "units_read": units_read,
            "obligations": len(obligations),
            "leftover": len(leftover),
            "repeated_units_folded": repeated,
            "balances": len(obligations) + len(leftover) + repeated == units_read,
            "in_both": 0,
        },
        "headings_with_obligations": sorted({str(row["under"]) for row in obligations}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--description", type=Path, required=True)
    parser.add_argument("--min-words", type=int, default=6,
                        help="a sentence shorter than this goes to the leftover, never nowhere")
    args = parser.parse_args(argv)

    print(json.dumps(enumerate_obligations(args.description.resolve(), args.min_words), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
