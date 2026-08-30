"""Shared by every obligations approach: one place that says what an obligation must satisfy."""
import re

MIN_CHARS = 25


def flat(s):
    return re.sub(r"\s+", " ", s).strip()


def grounded(lines, page_text, quotecheck):
    """Keep only lines that are verbatim on the page, long enough to mean something, and not
    contained in a line already kept. Atom 2 is locked: nothing that is not the page's own words."""
    keep = []
    for line in sorted({flat(x) for x in lines if x}, key=len, reverse=True):
        if len(line) < MIN_CHARS:
            continue
        if not quotecheck.check(line, page_text):
            continue
        if any(line in k for k in keep):
            continue
        keep.append(line)
    return sorted(keep)
