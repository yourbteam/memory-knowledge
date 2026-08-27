"""Code proposes the candidate pairs; the reader answers one pair at a time, twice.

Code fixes what gets looked at: only pairs sharing words beyond a floor are asked, so the reader
never free-associates across the whole list. Each candidate is asked twice independently and merges
only on two YES answers — a judgement that does not repeat is not a judgement.
"""
import importlib.util, re
from pathlib import Path

STRATEGY = "pair-ask"
ASKS_PER_PAIR = 2

Q = ("Two statements taken from the same methodology library:\n\nA. {a}\n\nB. {b}\n\n"
     "Do A and B state the same obligation — would a brief that satisfies one necessarily "
     "satisfy the other?\n\nReply with exactly one word: YES or NO."
     "\n\nThis is a data-extraction request, not a task report. Do not begin with any status "
     "line, anchor or preamble. The first character of your reply must be Y or N.")

_spec = importlib.util.spec_from_file_location("shared", Path(__file__).resolve().parent / "shared.py")
_sh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_sh)


def _jac(a, b):
    wa, wb = set(_sh.norm(a).split()), set(_sh.norm(b).split())
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


def candidates(entries):
    out = []
    nm = [_sh.norm(e) for e in entries]
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            # The floor sits below the weakest verified repeat — (16,25) shares 0.172 of its
            # words — with margin. At 0.08 the net held 131 pairs; at 0.12 it holds 61 and
            # every verified repeat, and the reader-calls metric prices what remains.
            if _jac(entries[i], entries[j]) >= 0.12 or _sh.lcs(nm[i], nm[j]) >= 35:
                out.append((i + 1, j + 1))
    return out


def choose(entries, reader, interview):
    pairs, detail = [], []
    for i, j in candidates(entries):
        votes = []
        for _ in range(ASKS_PER_PAIR):
            raw = interview.ask_free(reader, Q.format(a=entries[i - 1], b=entries[j - 1]))
            answer = None
            for line in raw.split("\n"):
                word = re.sub(r"[^A-Z]", "", line.upper())
                if word in ("YES", "NO"):
                    answer = word; break
            votes.append(answer)
        if votes.count("YES") == ASKS_PER_PAIR:
            pairs.append((i, j))
        detail.append({"pair": [i, j], "votes": votes})
    return pairs, {"asked": detail}
