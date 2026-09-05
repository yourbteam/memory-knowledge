#!/usr/bin/env python3
"""Atom 17 rival (approach already-resolves-tolerated-everywhere): drop the refusal at every stage,
including start, so an introduced flag on an existing field is never questioned."""
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
controller = root / "skills/atom-building-machinery/scripts/atom_controller.py"
text = controller.read_text()
for old, new in (
    ("    elif pending and len(segments) == 1:\n        raise AtomError(", "    elif pending and len(segments) == 1 and False:\n        raise AtomError("),
    ("        elif pending:\n            raise AtomError(\n                stage,\n                f\"introduced field {field!r} already resolves at {segments[1]!r}",
     "        elif pending and False:\n            raise AtomError(\n                stage,\n                f\"introduced field {field!r} already resolves at {segments[1]!r}"),
):
    assert text.count(old) == 1, old[:60]
    text = text.replace(old, new)
controller.write_text(text)
print(f"rival applied to {root}")
