"""Never synthesise a span. Replace a pick with the smallest unit some cut actually offered.

Seven of the 77 obligations the runs have recorded are offered by no cut at all: the completion
joined covering units into text that exists on the page but that nothing ever proposed as a unit.
This approach cannot do that. Every entry it returns is either a pick or a candidate one of the
four cuts put in front of a reader, so the merge can only ever choose, never compose.
"""
import importlib.util
from pathlib import Path

STRATEGY = "offered-only"
_here = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _here / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


_reflow, _cuts = _load("reflow"), _load("cuts")
_cache = {}


def _offered(text):
    key = id(text)
    if key not in _cache:
        units = []
        for cut in _cuts.CUTS.values():
            units += cut(text, 25)
        _cache[key] = sorted({_reflow.flow(u) for u in units}, key=len)
    return _cache[key]


def whole(pick, text):
    p = _reflow.flow(pick)
    for unit in _offered(text):          # sorted shortest first, so the first hit is the smallest
        if p in unit:
            return unit
    return p
