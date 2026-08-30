"""Quote check: token-window. Both sides are reduced to lowercase word tokens, dropping punctuation
and hyphenation, and the quote's tokens must appear as one unbroken run inside the piece's."""
import re

STRATEGY = "token-window"


def _tokens(s):
    return re.findall(r"[a-z0-9]+", s.lower().replace("-", ""))


def check(quote, piece_text):
    q, p = _tokens(quote), _tokens(piece_text)
    if not q or len(q) > len(p):
        return False
    return any(p[i:i + len(q)] == q for i in range(len(p) - len(q) + 1))
