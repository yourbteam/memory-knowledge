"""Leave every pick exactly as the reader picked it.

The honest baseline. It cannot swallow a table and it cannot invent, and it keeps every fragment
the line cut produced — so it says plainly what completion is buying.
"""
import importlib.util
from pathlib import Path

STRATEGY = "no-completion"
_spec = importlib.util.spec_from_file_location("reflow", Path(__file__).resolve().parent / "reflow.py")
_reflow = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_reflow)


def whole(pick, text):
    return _reflow.flow(pick)
