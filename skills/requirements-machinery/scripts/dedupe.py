"""Two entries state the same obligation — decided by code where code has proof, by a reader where
only meaning decides, and by the owner where the evidence itself disagrees.

Champion of atom-5-dedupe round 2 (Tasks/intake-to-requirements-machinery/atom-5-dedupe), promoted
by the owner on 2026-08-24. The record behind each part:

- Code merges a pair sharing a 35+ character normalized substring or half its three-word shingles.
  On the frozen 28 entries: all three verbatim repeat pairs, zero wrong merges, zero calls.
- The reader is asked only about pairs code cannot see — word overlap at or above 0.15, below the
  shingle bar — with the shared-rule question: "is there an obligation BOTH statements state".
  Round 1 asked for mutual entailment instead, and the reader correctly answered NO to
  containments; four of six anchors went unfound. The corrected question found both reworded
  repeats it was shown, four votes out of four, twice independently.
- Four votes per pair. Four YES merges. Four NO stays apart — unless the pair's shingle cover is
  0.35 or more, textually half-identical, where a NO contradicts code's own evidence. That case,
  and any split vote, is genuine doubt and goes to the owner: the fields-list pair sat at cover
  0.49 with four NOs, and one unanchored pair voted YES-YES then YES-NO. Nothing is lost silently.
"""
import importlib.util
import re
from difflib import SequenceMatcher
from pathlib import Path

_here = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _here / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


interview = _load("interview")

ASKS = 4
JACCARD_FLOOR = 0.15     # below the weakest verified reworded repeat (0.172), measured
GRAY_COVER = 0.35        # a NO on a pair this textually shared contradicts the text itself

ASK = ("Two statements taken from the same methodology library:\n\nA. {a}\n\nB. {b}\n\n"
       "Is there an obligation that BOTH statements state — the same rule, even if one of them "
       "also states other rules, and even if the wording differs?\n\n"
       "Reply with exactly one word: YES or NO."
       "\n\nThis is a data-extraction request, not a task report. Do not begin with any status "
       "line, anchor or preamble. The first character of your reply must be Y or N.")


def norm(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def shingles(text, k=3):
    w = norm(text).split()
    return {" ".join(w[i:i + k]) for i in range(len(w) - k + 1)}


def cover(a, b):
    sa, sb = shingles(a), shingles(b)
    small = min(len(sa), len(sb)) or 1
    return len(sa & sb) / small


def code_merges(a, b):
    m = SequenceMatcher(None, norm(a), norm(b)).find_longest_match()
    return m.size >= 35 or cover(a, b) >= 0.5


def _jaccard(a, b):
    wa, wb = set(norm(a).split()), set(norm(b).split())
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


def verdict(votes, pair_cover):
    """The rule alone, decidable from recorded votes — how the champion was scored."""
    if votes.count("YES") == ASKS:
        return "merge"
    if votes.count("NO") == ASKS and pair_cover < GRAY_COVER:
        return "apart"
    return "owner"


def judge(entries, reader_command):
    """Returns (merge_pairs, owner_pairs, detail). Entries are texts; pairs are 1-based."""
    merged, owner, detail = set(), set(), []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = entries[i], entries[j]
            if code_merges(a, b):
                merged.add((i + 1, j + 1))
                detail.append({"pair": [i + 1, j + 1], "by": "code"})
            elif _jaccard(a, b) >= JACCARD_FLOOR:
                votes = []
                for _ in range(ASKS):
                    raw = interview.ask_free(reader_command, ASK.format(a=a, b=b),
                                             stage="dedupe", piece=f"{i + 1}-{j + 1}")
                    answer = next((re.sub(r"[^A-Z]", "", l.upper())
                                   for l in raw.split("\n")
                                   if re.sub(r"[^A-Z]", "", l.upper()) in ("YES", "NO")), None)
                    votes.append(answer)
                v = verdict(votes, cover(a, b))
                if v == "merge":
                    merged.add((i + 1, j + 1))
                elif v == "owner":
                    owner.add((i + 1, j + 1))
                detail.append({"pair": [i + 1, j + 1], "by": "reader", "votes": votes,
                               "cover": round(cover(a, b), 2), "verdict": v})
    return sorted(merged), sorted(owner), detail
