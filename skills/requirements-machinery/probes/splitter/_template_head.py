#!/usr/bin/env python3
"""Splitter candidate: STRATEGY.

Reads the frozen document from EXPERIMENT_INPUT_PATH, cuts it its own way, and checks that the
pieces put back together give the whole document. Then it locates anchors — lines the document
itself marks as obligations — and measures how much of each anchor's own neighbourhood survives
inside the same piece. An obligation separated from the lines around it cannot be read as an
obligation, whoever is reading. No model is involved: this is geometry, and it is decided in code.

Writes experiment-result-v1.
"""
import hashlib, json, os, re, subprocess, time
from pathlib import Path

FF = "\f"
ANCHORS = 12
CONTEXT = 4  # lines either side that an obligation needs to remain readable
OBLIGATION = re.compile(
    r"\b(must|required|mandatory|no more than|at least|record for every|shall)\b", re.I
)


def pages(text):
    parts = text.split(FF)
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def anchors_with_context(text):
    """Obligation lines the document itself carries, each with its native neighbourhood."""
    lines = text.split("\n")
    hits = [i for i, line in enumerate(lines)
            if OBLIGATION.search(line) and len(line.strip()) > 40]
    if len(hits) > ANCHORS:
        step = len(hits) / ANCHORS
        hits = [hits[int(i * step)] for i in range(ANCHORS)]
    out = []
    for i in hits:
        neighbourhood = [l.strip() for l in lines[max(0, i - CONTEXT): i + CONTEXT + 1]
                         if l.strip()]
        out.append({"line": lines[i].strip(), "neighbourhood": neighbourhood})
    return out


def telemetry(path, variant, seq, event, **kw):
    with open(path, "a") as fh:
        fh.write(json.dumps({"variant": variant, "seq": seq, "at": time.time(), "event": event, **kw}) + "\n")
        fh.flush()
