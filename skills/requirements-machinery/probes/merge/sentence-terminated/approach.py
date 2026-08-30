"""Complete the pick only across text that actually ends sentences.

If any part of the run the pick overlaps does not end on a full stop, question or exclamation mark,
the splitter has not found a sentence there and the pick is returned as it was read.
"""
import importlib.util
from pathlib import Path

STRATEGY = "sentence-terminated"
_spec = importlib.util.spec_from_file_location("reflow", Path(__file__).resolve().parent / "reflow.py")
_reflow = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_reflow)


def whole(pick, text):
    page, p, cov = _reflow.covering(pick, text)
    if not cov:
        return p
    if not all(u.rstrip().endswith((".", "!", "?")) for u in cov):
        return p
    return " ".join(cov)
