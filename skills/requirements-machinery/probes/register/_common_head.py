#!/usr/bin/env python3
"""Register candidate: STRATEGY.

Builds a register over the frozen document's pieces and is then probed four ways while one piece is
deliberately left unanswered. Counts how many of those routes hand back data anyway, and whether the
refusal names the exact piece that is missing. Writes experiment-result-v1.
"""
import hashlib, json, os, re, subprocess, time
from pathlib import Path

FF = "\f"


def pieces_of(src):
    text = subprocess.run(["pdftotext", "-layout", str(src), "-"],
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")
    parts = text.split(FF)
    if parts and parts[-1] == "":
        parts.pop()
    return [{"id": f"p-{i:04d}", "text": t} for i, t in enumerate(parts, 1)]


def telemetry(path, variant, seq, event, **kw):
    with open(path, "a") as fh:
        fh.write(json.dumps({"variant": variant, "seq": seq, "at": time.time(), "event": event, **kw}) + "\n")
        fh.flush()


class Incomplete(Exception):
    pass
