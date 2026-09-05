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
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

_here = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _here / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


interview = _load("interview")
comparison_cache = _load("comparison_cache")
MAX_WORKERS = 4

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


def _owner_fixed(votes):
    return None in votes or ("YES" in votes and "NO" in votes)


def read_pair(a, b, reader_command, pair, *, cache_dir=None, namespace="", stage="dedupe"):
    """Resume the exact paid vote prefix; stop only when every completion means owner."""
    identity = {"left": a, "right": b, "reader_command": reader_command,
                "prompt": ASK, "asks": ASKS, "jaccard_floor": JACCARD_FLOOR,
                "gray_cover": GRAY_COVER, "namespace": namespace, "stage": stage,
                "policy": "unanimity-with-irrevocable-owner-v1"}
    with comparison_cache.checkpoint(cache_dir, identity) as (votes, save):
        while len(votes) < ASKS and not _owner_fixed(votes):
            raw = interview.ask_free(reader_command, ASK.format(a=a, b=b),
                                     stage=stage, piece=f"{pair[0]}-{pair[1]}")
            answer = next((re.sub(r"[^A-Z]", "", line.upper())
                           for line in raw.split("\n")
                           if re.sub(r"[^A-Z]", "", line.upper()) in ("YES", "NO")), None)
            votes.append(answer)
            save(votes)
    return votes, verdict(votes, cover(a, b))


def judge(entries, reader_command, *, cache_dir=None, namespace="", max_workers=MAX_WORKERS):
    """Independent pairs run concurrently; ordered output and unanimous verdicts stay stable."""
    if not isinstance(max_workers, int) or isinstance(max_workers, bool) or not 1 <= max_workers <= MAX_WORKERS:
        raise ValueError(f"comparison concurrency must be between 1 and {MAX_WORKERS}")
    planned = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = entries[i], entries[j]
            if code_merges(a, b):
                planned.append((i + 1, j + 1, "code"))
            elif _jaccard(a, b) >= JACCARD_FLOOR:
                planned.append((i + 1, j + 1, "reader"))
    def compare(row):
        i, j, kind = row
        if kind == "code":
            return {"pair": [i, j], "by": "code"}
        a, b = entries[i - 1], entries[j - 1]
        votes, decision = read_pair(a, b, reader_command, (i, j),
                                    cache_dir=cache_dir, namespace=namespace)
        return {"pair": [i, j], "by": "reader", "votes": votes,
                "cover": round(cover(a, b), 2), "verdict": decision}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        detail = list(executor.map(compare, planned))
    merged = [tuple(row["pair"]) for row in detail
              if row["by"] == "code" or row.get("verdict") == "merge"]
    owner = [tuple(row["pair"]) for row in detail if row.get("verdict") == "owner"]
    return sorted(merged), sorted(owner), detail
