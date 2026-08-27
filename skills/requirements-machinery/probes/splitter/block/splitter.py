"""Splitter: block. Cuts a document into pieces. Code only, no judgement."""
import re

FF = "\f"
STRATEGY = "block"


def pages(text):
    parts = text.split(FF)
    if parts and parts[-1] == "":
        parts.pop()
    return parts


MIN_CHARS = 400


def split(text, min_chars=MIN_CHARS):
    out, buf = [], []
    for page_text in pages(text):
        for block in re.split(r"\n\s*\n", page_text):
            buf.append(block)
            if sum(len(b) for b in buf) >= min_chars:
                out.append("\n\n".join(buf))
                buf = []
        buf.append(FF)
    if buf:
        out.append("\n\n".join(buf))
    return out
