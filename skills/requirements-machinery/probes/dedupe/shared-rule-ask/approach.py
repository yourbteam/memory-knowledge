"""Round 2: the corrected relation, on only what code cannot already see.

Round 1's pair-ask asked for mutual entailment and the reader correctly said NO to containments —
entry 16 carries three rules, one of which is entry 25's whole content. The relation dedupe needs
is a shared rule: is there an obligation both entries state. And code's half is settled, so the
reader is only asked about pairs the shingle rule does not already merge — the composition is in
the approach, exactly as atom 4 merged its cuts.
"""
import importlib.util, re
from pathlib import Path

STRATEGY = "shared-rule-ask"
ASKS_PER_PAIR = 2

Q = ("Two statements taken from the same methodology library:\n\nA. {a}\n\nB. {b}\n\n"
     "Is there an obligation that BOTH statements state — the same rule, even if one of them "
     "also states other rules, and even if the wording differs?\n\n"
     "Reply with exactly one word: YES or NO."
     "\n\nThis is a data-extraction request, not a task report. Do not begin with any status "
     "line, anchor or preamble. The first character of your reply must be Y or N.")

_spec = importlib.util.spec_from_file_location("shared", Path(__file__).resolve().parent / "shared.py")
_sh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_sh)


def _jac(a, b):
    wa, wb = set(_sh.norm(a).split()), set(_sh.norm(b).split())
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


def _code_pairs(entries):
    """The shingle rule, verbatim from the round-1 control: free and proven clean."""
    sh = [_sh.shingles(e) for e in entries]
    nm = [_sh.norm(e) for e in entries]
    out = set()
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            small = min(len(sh[i]), len(sh[j])) or 1
            if _sh.lcs(nm[i], nm[j]) >= 35 or len(sh[i] & sh[j]) / small >= 0.5:
                out.add((i + 1, j + 1))
    return out

def candidates(entries, code):
    # The floor sits below the weakest verified reworded repeat — (16,25) shares 0.172 of its
    # words — and pairs code already merges are never asked: the reader only judges what the
    # shingle rule cannot see.
    out = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            if (i + 1, j + 1) in code:
                continue
            if _jac(entries[i], entries[j]) >= 0.15:
                out.append((i + 1, j + 1))
    return out


def choose(entries, reader, interview):
    code = _code_pairs(entries)
    pairs, detail = set(code), []
    for i, j in candidates(entries, code):
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
            pairs.add((i, j))
        detail.append({"pair": [i, j], "votes": votes})
    return sorted(pairs), {"code_pairs": sorted(map(list, code)), "asked": detail}
