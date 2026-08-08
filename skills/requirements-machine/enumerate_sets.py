#!/usr/bin/env python3
"""Step two: enumerate the sets a requirement's cost could be counted over.

Step one measured what a model does reliably and what it does not. Four runs of it, same
subject, same evidence: all four found a real fault and wrote a test that returned the number
they wrote down. But each invented its own population, and two runs that chose the *same*
fault reported it as 721 of 974 and as 342 of 476. One fault, two sizes, nothing comparable.

So the set is not the model's to invent. This enumerates the sets that actually exist, by
structure rather than by knowing anything about this particular system: it finds the places
where the repository repeats itself — a directory shape that occurs many times, a filename
that recurs across them — and counts the members of each. A requirement then names one of
these, and two requirements naming the same one are comparable by construction.

It knows nothing about strategy briefs, runs, or phases. It is given a root and, optionally,
a token to keep only the sets whose paths mention it.

Usage:  python3 enumerate_sets.py --root <dir> [--about <token>] [--min-members 3]
Prints one JSON object: {"root":…, "about":…, "sets":[{"id","pattern","members","example"}…]}
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

#: Directory and file names that are somebody's cache, environment, or version control rather
#: than a record of what the subject did. Counting them makes a set nobody can act on.
_SKIP = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "site-packages", ".idea", ".vscode", "dist", "build", ".tox",
}

#: A path segment that varies per member of a set — an id, a hash, a date, a number. Replacing
#: it with a placeholder is what turns many concrete paths into one pattern.
_VARIABLE = re.compile(
    r"^("
    r"[0-9a-f]{8,}"                      # hex ids and hashes
    r"|[0-9]{1,4}(-[0-9]{2}){0,2}"       # numbers and dates
    r"|[a-z]+-run-[0-9a-z]+"             # prefixed run ids
    r"|[0-9]+-.*"                        # ordinal-prefixed names
    r")$",
    re.I,
)


def _is_nested_copy(path: Path, root: Path) -> bool:
    """True when the path runs through a directory holding a copy of the tree above it.

    The first run of this over a real repository returned, above every real set, ten variants
    of the same shape reached through nested snapshot directories — one tree containing a copy
    of a tree containing a copy of a tree. They are not sets anyone can act on; they are the
    same files counted again at a deeper address. A directory name that appears twice in one
    path is the structural tell, and it needs no knowledge of what the copies are for.
    """

    parts = path.relative_to(root).parts[:-1]
    if len(set(parts)) != len(parts):
        return True
    # A directory named like the root is the root copied inside itself. The first run found a
    # hundred of these — snapshots taken by other tooling — each re-counting the same records
    # under a longer address, and the largest of them sat above the real sets in the listing.
    return root.name in parts


#: A segment that is an ordinal followed by a name — a numbered step in a sequence. Only the
#: ordinal varies; the name is what the segment is. Replacing the whole segment collapsed every
#: step of a run into one set, and step three could then not address a single named step at all.
_ORDINAL_NAME = re.compile(r"^[0-9]+-(.+)$")


def _shape(path: Path, root: Path) -> str:
    """The path with its varying segments replaced, so members of one set share a shape."""
    parts = []
    for part in path.relative_to(root).parts:
        ordinal = _ORDINAL_NAME.match(part)
        if ordinal:
            parts.append(f"*-{ordinal.group(1)}")
        elif _VARIABLE.match(part):
            parts.append("*")
        else:
            parts.append(part)
    return "/".join(parts)


def _members_containing(members: list[Path], marker: str) -> int:
    """How many members carry the marker — the narrowing, counted rather than asserted.

    Two runs measuring the same fault over the same set reported it as twenty of twenty and
    twenty of thirty-one: the same twenty documents, one run silently dropping the eleven that
    cannot exhibit the fault at all and the other keeping them. Which is right depends on the
    requirement, but the numbers must not depend on the run, so both are computed here and the
    requirement says which it is using.
    """

    found = 0
    for member in members:
        try:
            if marker in member.read_text(encoding="utf-8", errors="replace"):
                found += 1
        except OSError:
            continue
    return found


def enumerate_sets(
    root: Path,
    about: str | None,
    min_members: int,
    contains: str | None = None,
) -> list[dict[str, object]]:
    shapes: dict[str, list[Path]] = defaultdict(list)

    for path in root.rglob("*"):
        if any(part in _SKIP for part in path.parts):
            continue
        if not path.is_file():
            continue
        if _is_nested_copy(path, root):
            continue
        shape = _shape(path, root)
        if "*" not in shape:
            continue                      # a one-off file is not a set
        shapes[shape].append(path)

    sets = []
    for shape, members in sorted(shapes.items()):
        if len(members) < min_members:
            continue
        if about and about.lower() not in shape.lower():
            continue
        entry: dict[str, object] = {
            "id": shape,
            "pattern": shape,
            "members": len(members),
            # How deep the set sits. A run's finished documents sit beside its manifest; its
            # working records sit inside a directory per step. One run counted the step's own
            # drafts and another the published documents, both truthfully; the depth is the
            # thing that distinguishes them, so it is on the record and can be cited.
            "depth": shape.count("/"),
            "example": str(sorted(members)[0].relative_to(root)),
        }
        if contains is not None:
            with_marker = _members_containing(members, contains)
            entry["members_containing"] = with_marker
            entry["members_not_containing"] = len(members) - with_marker
            entry["marker"] = contains
        sets.append(entry)
    sets.sort(key=lambda entry: (-int(entry["members"]), str(entry["id"])))
    return sets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--about", default=None, help="keep only sets whose path mentions this")
    parser.add_argument("--min-members", type=int, default=3)
    parser.add_argument("--contains", default=None,
                        help="also count, per set, how many members carry this text")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    print(json.dumps({
        "root": str(root),
        "about": args.about,
        "sets": enumerate_sets(root, args.about, args.min_members, args.contains),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
