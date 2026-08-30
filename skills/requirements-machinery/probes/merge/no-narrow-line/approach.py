"""Complete the pick only while the completion stays inside wrapped prose.

Prose in this library wraps near a hundred characters, so a short display line in the middle of a
run is a table cell or a column, not a wrap. Measured on the pieces: the table blocks that swallowed
page 81 and page 87 average 14 to 17 characters a line; the prose runs average 54 to 104.
"""
import importlib.util
from pathlib import Path

STRATEGY = "no-narrow-line"
NARROW = 40
_spec = importlib.util.spec_from_file_location("reflow", Path(__file__).resolve().parent / "reflow.py")
_reflow = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_reflow)


def whole(pick, text):
    page, p, cov = _reflow.covering(pick, text)
    if not cov:
        return p
    joined = " ".join(cov)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    inside = [l for l in lines if l in joined]
    for l in inside[:-1]:
        if len(l) < NARROW:
            return p
    return joined
