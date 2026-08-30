"""Complete the pick, but only while the completion finishes it rather than replaces it.

A completion that more than doubles what was picked is no longer finishing a sentence; on page 81
the table completions ran to 6.6 and 9.6 times the picked row.
"""
import importlib.util
from pathlib import Path

STRATEGY = "at-most-double"
MOST = 2.0
_spec = importlib.util.spec_from_file_location("reflow", Path(__file__).resolve().parent / "reflow.py")
_reflow = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_reflow)


def whole(pick, text):
    page, p, cov = _reflow.covering(pick, text)
    if not cov:
        return p
    joined = " ".join(cov)
    return joined if len(joined) <= MOST * len(p) else p
