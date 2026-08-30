"""Quote check: line-anchored. The quote must match a run of whole lines of the piece, each line
compared with its own whitespace collapsed. A quote that starts or ends mid-line is refused."""
import re

STRATEGY = "line-anchored"


def _lines(s):
    return [re.sub(r"\s+", " ", l).strip() for l in s.split("\n") if l.strip()]


def check(quote, piece_text):
    q, p = _lines(quote), _lines(piece_text)
    if not q or len(q) > len(p):
        return False
    return any(p[i:i + len(q)] == q for i in range(len(p) - len(q) + 1))
