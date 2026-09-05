#!/usr/bin/env python3
"""Atom 18 rival (approach advisory-report-only): the same checks, but `consistency` writes an advisory
report file in the run and records no cells, so nothing reaches located, the owner queue, or the
findings document."""
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_change  # noqa: E402

apply_change.main(root)
script = root / "skills/critique-machinery/scripts/critique.py"
text = script.read_text()
old = '''        for seat in READER_SEATS:
            batch_id = f"code-{cell['unit_id']}"'''
new = '''        (work / "consistency-report.json").write_bytes(canonical({"unit": cell["unit_id"], "facts": facts}))
        continue
        for seat in READER_SEATS:
            batch_id = f"code-{cell['unit_id']}"'''
assert text.count(old) == 1
script.write_text(text.replace(old, new))
print(f"rival applied to {root}")
