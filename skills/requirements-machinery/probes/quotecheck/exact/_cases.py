"""Build true and false quotes from the frozen document itself. Code only, no judgement.

Sampling is fixed by position so every approach is judged on the same set. Nothing is invented.

The first version of this file was wrong and the checkers caught it: it filtered a piece's lines to
the long ones and then joined those, producing "true" quotes made of lines that are not adjacent in
the document. All three approaches refused them, correctly, and the score read as an 85% failure to
accept truth. The quotes were the failure. Adjacency is now taken from the piece itself.
"""
import re

FF = "\f"
SAMPLES = 20


def pieces(text):
    parts = [p for p in text.split(FF) if p.strip()]
    return [{"id": f"p-{i:04d}", "text": t} for i, t in enumerate(parts, 1)]


def _adjacent_run(piece):
    """Two consecutive substantial lines, exactly as they sit in the piece."""
    lines = piece["text"].split("\n")
    for i in range(len(lines) - 1):
        if len(lines[i].strip()) > 30 and len(lines[i + 1].strip()) > 30:
            return "\n".join(lines[i:i + 2]), i
    return None, None


def build(text):
    ps = pieces(text)
    step = max(1, len(ps) // SAMPLES)
    chosen = [ps[i] for i in range(0, len(ps), step)][:SAMPLES]
    true_cases, false_cases = [], []
    for n, piece in enumerate(chosen):
        run, _ = _adjacent_run(piece)
        if not run:
            continue
        t = piece["text"]
        # --- true, in three shapes the document really contains ---
        true_cases.append({"piece": piece["id"], "quote": run, "text": t, "shape": "verbatim"})
        true_cases.append({"piece": piece["id"], "quote": re.sub(r"\s+", " ", run), "text": t,
                           "shape": "same words, spacing collapsed"})
        words = run.split()
        if len(words) > 6:
            true_cases.append({"piece": piece["id"], "quote": " ".join(words[2:-2]), "text": t,
                               "shape": "the middle of the run, starting mid-line"})
        # --- false, in three shapes that look plausible ---
        target = max(range(len(words)), key=lambda i: len(words[i]))
        mutated = list(words); mutated[target] = "flerbin"
        false_cases.append({"piece": piece["id"], "quote": " ".join(mutated), "text": t,
                            "why": "one word replaced with a word not in the document"})
        if len(words) > 8:
            reordered = words[:2] + words[4:6] + words[2:4] + words[6:]
            false_cases.append({"piece": piece["id"], "quote": " ".join(reordered), "text": t,
                                "why": "the document's own words, put in a different order"})
        # punctuation that changes the meaning while keeping every word
        if "no more than" in t.lower():
            line = next((l for l in t.split("\n") if "no more than" in l.lower()), None)
            if line:
                false_cases.append({"piece": piece["id"],
                                    "quote": re.sub(r"(?i)no more than", "no, more than", line.strip()),
                                    "text": t,
                                    "why": "same words, one comma turns a cap into its opposite"})
        # a word the document breaks across a line, quoted whole
        broken = re.search(r"(\w{3,})-\n\s*(\w{3,})", t)
        if broken:
            true_cases.append({"piece": piece["id"],
                               "quote": broken.group(1) + broken.group(2),
                               "text": t, "shape": "a word the document hyphenates across a line"})
        other = chosen[(n + 3) % len(chosen)]
        other_run, _ = _adjacent_run(other)
        if other_run and other["id"] != piece["id"]:
            false_cases.append({"piece": piece["id"], "quote": other_run, "text": t,
                                "why": f"really from {other['id']}"})
    return true_cases, false_cases
