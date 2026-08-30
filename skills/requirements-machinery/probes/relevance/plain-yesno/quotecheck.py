"""Quote check: exact. The quote must appear in the piece as a substring, once whitespace is
collapsed. Nothing else is forgiven."""
import re

STRATEGY = "exact"


def _flat(s):
    return re.sub(r"\s+", " ", s).strip()


def check(quote, piece_text):
    return _flat(quote) in _flat(piece_text)
