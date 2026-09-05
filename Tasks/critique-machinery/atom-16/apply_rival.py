#!/usr/bin/env python3
"""Atom 16 rival (approach unresolved-tolerated): apply to one source tree root.

Start tolerates any field whose leaf does not resolve, recording it as unresolved, and resolves
everything only at record-promotion. No `introduced` marker exists, so a misspelled field also
passes start.
"""
from __future__ import annotations

import sys
from pathlib import Path


def patch(path: Path, pairs: list[tuple[str, str]]) -> None:
    text = path.read_text()
    for old, new in pairs:
        assert text.count(old) == 1, (path.name, text.count(old), old[:70])
        text = text.replace(old, new)
    path.write_text(text)


def main(root: Path) -> int:
    controller = root / "skills/atom-building-machinery/scripts/atom_controller.py"
    patch(controller, [
        ('''    if len(segments) > 1:
        nested = _available_nested_keys(collections, segments[0])
        if segments[1] not in nested:
            raise AtomError(
                stage,
                f"field {field!r} does not resolve at {segments[1]!r}; available keys are {sorted(nested)!r}",
            )''',
         '''    unresolved = False
    if len(segments) > 1:
        nested = _available_nested_keys(collections, segments[0])
        if segments[1] not in nested:
            if stage == "record-promotion":
                raise AtomError(
                    stage,
                    f"field {field!r} does not resolve at {segments[1]!r}; available keys are {sorted(nested)!r}",
                )
            unresolved = True  # tolerated until promotion'''),
        ('''        target = segments[-1]
        if target not in collections[constant] and segments[0] not in collections[constant]:
            raise AtomError(
                stage,
                f"field {field!r} is not named by shape constant {constant!r}; "
                f"that constant provides {collections[constant]!r}",
            )
    return {"field": field, "shape": shape, "shape_source": f"{source_path_text}::{constant}"}''',
         '''        target = segments[-1]
        if not unresolved and target not in collections[constant] and segments[0] not in collections[constant]:
            raise AtomError(
                stage,
                f"field {field!r} is not named by shape constant {constant!r}; "
                f"that constant provides {collections[constant]!r}",
            )
    resolved = {"field": field, "shape": shape, "shape_source": f"{source_path_text}::{constant}"}
    if unresolved:
        resolved["unresolved"] = True
    return resolved'''),
    ])
    print("rival applied to", root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
