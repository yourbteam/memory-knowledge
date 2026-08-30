"""Turning extracted page text into units of meaning. Shared unchanged by every approach.

Measured on the fourteen pieces: cutting on the newline left 93 of 135 units ending mid-sentence;
joining the page and splitting on sentence ends left 0 of 83. A newline in a PDF extraction is a
layout break, not a meaning break.
"""
import re

SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z●•])")


def flow(text):
    """The page as one run, layout newlines removed."""
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip()


def units(text, min_chars=25):
    return [u.strip() for u in SENTENCE_END.split(flow(text)) if len(u.strip()) >= min_chars]


def covering(pick, text):
    """The units the pick overlaps, in order, with the flowed page and the pick's span."""
    page, p = flow(text), flow(pick)
    start = page.find(p)
    if start < 0:
        return page, p, None
    end = start + len(p)
    spans, at = [], 0
    for u in units(text, min_chars=1):
        i = page.find(u, at)
        if i < 0:
            continue
        spans.append((i, i + len(u), u)); at = i + len(u)
    return page, p, [u for a, b, u in spans if a < end and b > start]
