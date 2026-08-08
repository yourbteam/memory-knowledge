#!/usr/bin/env python3
"""Step three: enumerate the candidate faults inside one set.

Step two fixed *what* a requirement counts over. Six runs then agreed on the set and on the
numbers — but each still invented *which* fault to require away, so no two runs produced the
same requirement. Inventing the candidate is the last place the machinery is free-handed.

A set is a group of records the system produced the same way. Anything the set does not do
uniformly is a candidate: a heading twenty of thirty-one documents carry, a key present in some
records and missing in others. That is the whole rule, and it needs no knowledge of what the
records are for. A property every member has is not a candidate — nothing is inconsistent. A
property no member has cannot be seen from inside the set at all, and this does not pretend to
find those.

Usage:  python3 enumerate_candidates.py --root <dir> --pattern '<set id from enumerate_sets>'
Prints one JSON object: {"pattern":…, "members":N, "candidates":[{"id","property","present",
"absent","example_absent"}…], "universal":[…]}
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

#: An ISO-8601 instant written into a record. A published document does not say when it was
#: written, but the records beside it do, and that is the only date worth anything: a file's
#: modification time is when it was last copied, which for a whole repository is one afternoon.
_INSTANT = re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-9]{2}:[0-9]{2}:[0-9]{2}[0-9.:+Z-]*")

from enumerate_sets import _SKIP, _is_nested_copy, _shape

#: A markdown heading. The heading set is what a document promises to contain, so a heading some
#: members carry and others do not is the set failing to do one thing uniformly.
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

#: An id or a number inside a heading. The first run over a real set returned two hundred and
#: twelve candidates held by exactly one member, and most were one heading per claim id or per
#: topic id — the same section repeated under a different name. Replacing the varying token is
#: what step two already does to path segments, applied inside the text.
_VARYING_TOKEN = re.compile(r"[0-9a-f]{8,}|[0-9]+", re.I)


def _headings(text: str) -> set[str]:
    found = set()
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            # The level goes in the name. A document's promised structure is its top sections;
            # what is nested inside them is that document's own subject matter, and the two must
            # not land in one list as if they were the same kind of thing.
            level = len(match.group(1))
            found.add(f"heading:{level}:{_VARYING_TOKEN.sub('*', match.group(2))}")
    return found


def _json_keys(value: object, prefix: str = "") -> set[str]:
    """Every key path in a record. A key some records carry and others do not is a candidate."""

    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            found.add(f"key:{path}")
            found |= _json_keys(child, path)
    elif isinstance(value, list):
        # The index is not part of the shape; a list of three and a list of four are the same
        # record. Only what is inside them can differ meaningfully.
        for child in value:
            found |= _json_keys(child, f"{prefix}[]")
    return found


def _properties(path: Path) -> set[str] | None:
    """What this member does. None when the file is a shape this step cannot read yet."""

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if path.suffix.lower() in {".md", ".markdown", ".txt"}:
        return _headings(text)
    if path.suffix.lower() == ".json":
        try:
            return _json_keys(json.loads(text))
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def members_of(root: Path, pattern: str) -> list[Path]:
    members = []
    for path in root.rglob("*"):
        if any(part in _SKIP for part in path.parts):
            continue
        if not path.is_file():
            continue
        if _is_nested_copy(path, root):
            continue
        if _shape(path, root) == pattern:
            members.append(path)
    return sorted(members)


def _variables(path: Path, root: Path) -> tuple[str, ...]:
    """The segments of this path that vary between members of its set."""

    parts = path.relative_to(root).parts
    shape = _shape(path, root).split("/")
    return tuple(part for part, slot in zip(parts, shape) if slot == "*")


def _source_index(root: Path, pattern: str) -> dict[str, set[str]]:
    """What each member of an upstream set does, keyed by the first varying segment.

    A published record and the working record it was made from belong to different sets but to
    the same run, and the run id is the first thing that varies in both. Pairing on it is what
    lets a missing section be attributed: absent from the published record and present in the
    record the named step itself produced means the step did its part and something after it
    did not.
    """

    index: dict[str, set[str]] = {}
    for member in members_of(root, pattern):
        variables = _variables(member, root)
        if not variables:
            continue
        properties = _properties(member)
        if properties is None:
            continue
        index.setdefault(variables[0], set()).update(properties)
    return index


def _produced_at(member: Path) -> str | None:
    """When the run that wrote this member ran, from the records the run wrote beside it.

    Two runs disposing of the same candidate split twice, and both splits were the same
    disagreement: one counted a record written by code that has since changed, the other refused
    to. Neither was wrong — the date was simply not on the table. Without it a cost can include
    records no fix can ever repair, and a requirement whose count cannot reach zero cannot be
    settled by the person who builds it.
    """

    found = []
    for sibling in sorted(member.parent.glob("*.json")):
        try:
            text = sibling.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found.extend(_INSTANT.findall(text))
    return min(found) if found else None


def _rule_last_changed(contract: Path, needle: str) -> str | None:
    """When the subject's source last gained or lost this exact text.

    The contract file as a whole changes constantly, so its last commit says nothing about any
    one section. What a candidate is governed by is the line that names it, and git can find the
    commit that added or removed that line without anyone knowing what the line means.
    """

    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", f"-S{needle}", "--", contract.name],
            cwd=contract.parent, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    stamp = result.stdout.strip()
    return stamp or None


def enumerate_candidates(
    root: Path,
    pattern: str,
    produced_by: str | None = None,
    contract: Path | None = None,
) -> dict[str, object]:
    members = members_of(root, pattern)
    source = _source_index(root, produced_by) if produced_by else None
    holders: dict[str, list[Path]] = defaultdict(list)
    readable: list[Path] = []
    unreadable: list[Path] = []

    for member in members:
        properties = _properties(member)
        if properties is None:
            unreadable.append(member)
            continue
        readable.append(member)
        for name in properties:
            holders[name].append(member)

    total = len(readable)
    candidates = []
    universal = []
    for name, present in sorted(holders.items()):
        if len(present) == total:
            universal.append(name)
            continue
        absent = [member for member in readable if member not in present]
        row: dict[str, object] = {
            "property": name,
            "present": len(present),
            "absent": len(absent),
            # A name is easier to argue about than a count. One member that does not do the
            # thing is what a reader opens first when they doubt the candidate.
            "example_absent": str(absent[0].relative_to(root)),
            "example_present": str(present[0].relative_to(root)),
        }
        if source is not None:
            # Of the members missing this, how many had it when the named step handed it on.
            # Those are not the step's failures however true the absence is.
            lost_after = 0
            missing_from_source = 0
            for member in absent:
                variables = _variables(member, root)
                held = source.get(variables[0]) if variables else None
                if held is None:
                    continue
                if name in held:
                    lost_after += 1
                else:
                    missing_from_source += 1
            row["absent_and_lost_after_the_step"] = lost_after
            row["absent_and_missing_from_the_step"] = missing_from_source
        if contract is not None:
            # The text the rule is written as, without the heading level this tool added.
            needle = name.split(":", 2)[-1]
            changed = _rule_last_changed(contract, needle)
            row["rule_last_changed"] = changed
            if changed:
                older = sum(
                    1 for member in absent
                    if (stamp := _produced_at(member)) is not None and stamp < changed
                )
                undated = sum(1 for member in absent if _produced_at(member) is None)
                row["absent_written_before_the_rule"] = older
                row["absent_written_after_the_rule"] = len(absent) - older - undated
                row["absent_undated"] = undated
        candidates.append(row)

    # Widest gap first: the property most of the set does and a few do not is the sharpest
    # inconsistency, and the order must not depend on the run.
    candidates.sort(key=lambda row: (-int(row["present"]), str(row["property"])))
    for index, row in enumerate(candidates, start=1):
        row["id"] = f"c{index}"

    return {
        "pattern": pattern,
        "members": len(members),
        "members_read": total,
        "members_unreadable": [str(path.relative_to(root)) for path in unreadable],
        "candidates": candidates,
        "universal": universal,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pattern", required=True, help="a set id printed by enumerate_sets.py")
    parser.add_argument("--produced-by", default=None,
                        help="the set the named step itself wrote, so an absence can be "
                             "attributed to that step or to something after it")
    parser.add_argument("--contract", type=Path, default=None,
                        help="the tracked source file that decides what the set must contain, so "
                             "each candidate carries when its own rule last changed")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    contract = args.contract.resolve() if args.contract else None
    print(json.dumps(
        enumerate_candidates(root, args.pattern, args.produced_by, contract), indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
