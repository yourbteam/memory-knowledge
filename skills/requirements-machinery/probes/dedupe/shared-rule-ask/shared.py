"""What every dedupe approach shares: normalization and the true longest common substring."""
import re
from difflib import SequenceMatcher


def norm(text):
    """Lowercase words only — punctuation and layout become spaces, so 'baseline+target' and
    'baseline, target' read the same."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def lcs(a, b):
    m = SequenceMatcher(None, a, b).find_longest_match()
    return m.size


def shingles(text, k=3):
    w = norm(text).split()
    return {" ".join(w[i:i + k]) for i in range(len(w) - k + 1)}
