#!/usr/bin/env python3
"""Step five: the faults a set cannot show you about itself.

Steps two to four find a fault by disagreement — a section most members carry and a few do not.
Pointed at the real subject that machinery returned an empty document: forty-five candidates, all
dismissed, nothing to require. That is a true answer to the question it asks and a useless one,
because the question has a floor. When every member of a set is wrong in the same way, the set
agrees with itself perfectly and the enumeration sees nothing at all.

So the standard has to come from outside the set. It is already written down: the code that
produces these documents names the sections it will write, and the code that reads them names the
sections it will look for. Both are string literals a machine can collect. A marker the code
depends on that no member carries is a fault the whole set shares — the exact shape the earlier
steps are blind to. The two counts are reported separately because they mean different things:
one says the writer never delivered, the other says a reader is looking for something nobody
writes, which is worse and quieter.

Usage:  python3 enumerate_expectations.py --root <dir> --pattern '<set id>' --source <dir> [...]
Prints one JSON object listing every marker the source expects, with how many members carry it.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from enumerate_candidates import members_of

#: A name that says its value is a place in a document rather than ordinary text. Collecting by
#: name as well as by shape catches the marker that is stored once and used far away, which is
#: precisely the kind a reader depends on silently.
_MARKER_NAMES = ("HEADING", "SECTION", "TITLE", "MARKER", "LABEL")


def _looks_like_marker(value: str) -> bool:
    """A string that names a place in a markdown document."""
    text = value.strip()
    if not text or len(text) > 120 or "\n" in text:
        return False
    return text.startswith("#")


def _markers_in(path: Path) -> dict[str, list[str]]:
    """Every document marker this source file writes down, and how it referred to it."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, ValueError):
        return {}

    found: dict[str, list[str]] = {}

    def remember(value: str, named: str | None) -> None:
        text = value.strip()
        # A heading is the same place whether or not it is written with its hashes.
        bare = text.lstrip("#").strip()
        if not bare:
            return
        found.setdefault(bare, [])
        if named and named not in found[bare]:
            found[bare].append(named)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            marker_name = next(
                (n for n in names if any(part in n.upper() for part in _MARKER_NAMES)), None,
            )
            if marker_name and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str) and node.value.value.strip():
                    remember(node.value.value, marker_name)
                    continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _looks_like_marker(node.value):
                remember(node.value, None)

    return found


def enumerate_expectations(
    root: Path, pattern: str, sources: list[Path],
) -> dict[str, object]:
    members = members_of(root, pattern)
    texts = []
    for member in members:
        try:
            texts.append(member.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue

    expected: dict[str, dict[str, object]] = {}
    for source in sources:
        files = sorted(source.rglob("*.py")) if source.is_dir() else [source]
        for path in files:
            for marker, names in _markers_in(path).items():
                row = expected.setdefault(marker, {"marker": marker, "named_by": [], "in": []})
                for name in names:
                    if name not in row["named_by"]:
                        row["named_by"].append(name)
                where = str(path)
                if where not in row["in"]:
                    row["in"].append(where)

    rows = []
    for marker, row in expected.items():
        carried = sum(1 for text in texts if marker in text)
        rows.append({
            **row,
            "members_carrying": carried,
            "members": len(texts),
            # A marker the code names and nobody carries is the whole set failing together.
            "whole_set_gap": carried == 0,
        })

    rows.sort(key=lambda r: (int(r["members_carrying"]), str(r["marker"])))
    return {
        "pattern": pattern,
        "members": len(texts),
        "expectations": rows,
        "whole_set_gaps": [r["marker"] for r in rows if r["whole_set_gap"]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pattern", required=True, help="a set id printed by enumerate_sets.py")
    parser.add_argument("--source", type=Path, action="append", required=True,
                        help="a file or directory of code that writes or reads these documents")
    args = parser.parse_args(argv)

    print(json.dumps(enumerate_expectations(
        args.root.resolve(), args.pattern, [s.resolve() for s in args.source],
    ), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
