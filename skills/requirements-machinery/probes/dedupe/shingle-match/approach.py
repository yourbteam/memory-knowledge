"""Code alone: a pair merges on a shared verbatim statement or shared normalized word-runs.

The hypothesis: after punctuation is normalized away, even the reworded repeats share enough
three-word runs to be caught without a reader. Deterministic and free; it cannot see a rule
restated with none of its words.
"""
import importlib.util
from pathlib import Path

STRATEGY = "shingle-match"
_spec = importlib.util.spec_from_file_location("shared", Path(__file__).resolve().parent / "shared.py")
_sh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_sh)


def choose(entries, reader, interview):
    pairs, detail = [], []
    sh = [_sh.shingles(e) for e in entries]
    nm = [_sh.norm(e) for e in entries]
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            span = _sh.lcs(nm[i], nm[j])
            small = min(len(sh[i]), len(sh[j])) or 1
            cover = len(sh[i] & sh[j]) / small
            if span >= 35 or cover >= 0.5:
                pairs.append((i + 1, j + 1))
                detail.append({"pair": [i + 1, j + 1], "span": span, "cover": round(cover, 2)})
    return pairs, {"merged_on": detail}
