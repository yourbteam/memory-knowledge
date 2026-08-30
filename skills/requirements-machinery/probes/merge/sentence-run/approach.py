"""Complete the pick to the whole run of sentences it overlaps. No bound.

This is what the live pass ran when it was stopped. It is here as the control because the question
is whether any bound beats it, and because its failure is the reason the question exists.
"""
import importlib.util
from pathlib import Path

STRATEGY = "sentence-run"
_spec = importlib.util.spec_from_file_location("reflow", Path(__file__).resolve().parent / "reflow.py")
_reflow = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_reflow)


def whole(pick, text):
    page, p, cov = _reflow.covering(pick, text)
    if not cov:
        return p
    return " ".join(cov)
