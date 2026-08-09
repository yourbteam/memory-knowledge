#!/usr/bin/env python3
"""Before any requirement is written: pull out the description's claims about how things are.

Everything this machinery produces rests on one description, and the description is the only part
nothing checked. It mixes four kinds of statement: what the client wrote, what was observed in
real output, what was read in the code, and what somebody decided. The first two and the last are
records or choices. The third is a claim about the world today, and a wrong one poisons every
requirement built on it.

That is not hypothetical. The description said the step is handed the results of an evidence
check. It is not — that check runs afterwards. Requirements were written expecting something that
never arrives, and nothing in the machinery would have caught it.

So this reads the description, separates its statements by the mark each carries, and hands the
factual ones out to be cited. The citation is then verified by the same checker the measuring
stage uses: file, line, exact text. A statement nobody can cite is not a fact about the code — it
is an observation, a decision, or an error, and it must be relabelled before anything rests on it.

The marks are read from the description itself, in square brackets, so a description using its own
vocabulary works. A description that marks nothing yields nothing to check, and that is reported
rather than passed over in silence.

Usage:  python3 extract_claims.py --description <file.md> [--fact-mark 'in code']
Prints every marked statement grouped by mark, and the factual ones as items needing a citation.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from enumerate_obligations import _units

#: A mark the description puts on a statement to say where it came from, written in brackets.
_MARK = re.compile(r"\[([a-z][a-z ,—-]{1,40})\]", re.I)

#: Marks that record a choice rather than a claim about the world. They are listed so a reader can
#: see how much of the description is decision rather than fact, which is worth knowing on its own.
_NOT_A_SOURCE = {"decision", "ratified"}


def _carried(text: str, match: re.Match[str]) -> bool:
    """Is this bracket the sentence's own mark, or a bracket the sentence is talking about?

    A mark that is carried is a tag: it sits where the sentence is not — at the start, at the end,
    or against a dash, colon or semicolon that has already broken the grammar. A mark that is only
    mentioned sits inside the grammar, with a word each side, and reads as a noun or an adjective:
    "every statement marked [in code] would be re-checked", "no step re-validates its [in code]
    statements". Both of those went out as claims to be cited on the run that made this necessary,
    and a reader was sent looking in the repository for a sentence about the description itself.
    """

    before = text[: match.start()].rstrip()
    after = text[match.end():].lstrip()
    if not before or not after:
        return True
    return not ((before[-1].isalnum() or before[-1] in ")\"'") and after[0].isalnum())


def extract(description: Path, fact_mark: str) -> dict[str, object]:
    by_mark: dict[str, list[dict[str, object]]] = defaultdict(list)
    units = list(_units(description))

    # The section that defines the marks is about the document, not about the subject. Its
    # sentences carry marks only because they explain them, and checking them against the code
    # sends a reader looking for something the code was never going to say: four rounds of
    # verification were spent on one footnote about how many rounds had been run. It is found
    # structurally — the heading under which the marks are defined — not by name.
    defining: set[str] = set()
    for unit in units:
        text = str(unit["text"])
        if unit["kind"] == "sentence" and re.match(r"^\s*\[[a-z][a-z ,—-]{1,40}\]\s*[—-]", text, re.I):
            defining.add(str(unit["under"]))

    mentioned: list[dict[str, object]] = []
    for unit in units:
        if unit["kind"] != "sentence":
            continue
        if unit["under"] in defining:
            continue
        text = str(unit["text"])
        for match in _MARK.finditer(text):
            mark = match.group(1).strip().lower()
            if mark.startswith("ratified"):
                mark = "ratified"
            row = {"text": text, "under": unit["under"]}
            if _carried(text, match):
                by_mark[mark].append(row)
            else:
                # Not dropped, listed. The rule is a reading of punctuation and it will sometimes
                # be wrong; a mark that quietly disappeared would take the misreading with it.
                mentioned.append(dict(row, mark=mark))

    facts = []
    for index, row in enumerate(by_mark.get(fact_mark.lower(), []), start=1):
        facts.append({
            "id": f"f{index}",
            "claim": row["text"],
            "under": row["under"],
            "needs": "a citation: the file, the line number, and that line's exact text",
        })

    return {
        "description": str(description),
        "marks_found": {mark: len(rows) for mark, rows in sorted(by_mark.items())},
        "fact_mark": fact_mark,
        "claims_to_cite": facts,
        "marks_mentioned_not_carried": mentioned,
        "decisions_not_facts": sorted(m for m in by_mark if m in _NOT_A_SOURCE),
        "note": (
            "Only marked statements are listed. A description that marks nothing gives this "
            "nothing to check — which is itself worth knowing before requirements are built."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--description", type=Path, required=True)
    parser.add_argument("--fact-mark", default="in code",
                        help="the mark the description uses for a claim about the code as it is")
    args = parser.parse_args(argv)

    print(json.dumps(extract(args.description.resolve(), args.fact_mark), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
