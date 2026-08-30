"""Splitter: page. Cuts a document into pieces. Code only, no judgement."""
import re

FF = "\f"
STRATEGY = "page"


def pages(text):
    parts = text.split(FF)
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def split(text):
    return [p + FF for p in pages(text)]
