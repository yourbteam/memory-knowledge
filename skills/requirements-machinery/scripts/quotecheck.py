"""Quote check: exact. The quote must appear in the piece as a substring, once whitespace is
collapsed. Nothing else is forgiven."""
import re

STRATEGY = "exact"
MIN_GROUNDING_CHARS = 25


def normalize(s):
    return re.sub(r"\s+", " ", s).strip()


def validated(quote, piece_text, *, min_chars=1):
    """Return the normalized verbatim quote, or None when it is not substantive grounding.

    A source shorter than the declared floor remains answerable only by quoting that whole source.
    """
    quote = normalize(quote)
    piece = normalize(piece_text)
    if not quote or not piece:
        return None
    required = min(min_chars, len(piece))
    return quote if len(quote) >= required and quote in piece else None


def check(quote, piece_text):
    return validated(quote, piece_text) is not None


def grounding(quote, piece_text):
    return validated(quote, piece_text, min_chars=MIN_GROUNDING_CHARS)
