#!/usr/bin/env python3
"""Atom 19 rival (approach agreed-defects-only): the same command, but a run's located defects count only
the cells both blind seats called a defect, ignoring the owner's rulings of revise or reject on the
cells the seats disputed. It prints a smaller number than the report route for every run whose
owner queue carried defects (version 5: 16 instead of 25)."""
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_change  # noqa: E402

apply_change.main(root)
script = root / "skills/critique-machinery/scripts/critique.py"
text = script.read_text()
old = '''def _is_located_defect(cell: dict[str, Any]) -> bool:
    return cell.get("outcome") == "agreement-defect" or cell.get("resolved_verdict") in {"reject", "revise"}'''
new = '''def _is_located_defect(cell: dict[str, Any]) -> bool:
    return cell.get("outcome") == "agreement-defect"'''
assert text.count(old) == 1
script.write_text(text.replace(old, new))
print(f"rival applied to {root}")
