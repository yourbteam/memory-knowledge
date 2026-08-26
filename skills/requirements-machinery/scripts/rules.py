"""From proven same-rule pairs to a list where each rule appears once — scissors, never pen.

Every rule in the output is verbatim text: either a clean whole-sentence extraction code can
verify, or a quote the reader gives and code verifies against the entry it came from. Nothing is
rewritten. The pen — turning verbatim rules into polished requirement statements — is the tabled
distillation atom, not this.

Measured before building (prototype 0 on the 27 real pairs): code's span-expansion returns a
clean verbatim sentence for about a third of pairs and fragments like "markets. The final-brief
gate + the" for the rest — so code keeps only extractions it can verify (verbatim in the entry,
sentence-terminated, 25+ chars), and every other pair goes to the reader as a quote request.
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
dedupe = _load("dedupe")

QUOTE_ASK = ("Two statements taken from the same methodology library:\n\nA. {a}\n\nB. {b}\n\n"
             "They both state one shared rule. Quote that rule, word for word, exactly as it "
             "appears inside statement A — copy the words, change nothing.\n\n"
             "This is a data-extraction request, not a task report. Do not begin with any status "
             "line, anchor or preamble. The first character of your reply must be the first "
             "character of the quote.")


def _clean_sentence(rule, entry):
    """True only when the extraction is something code can stand behind."""
    return (rule and len(rule) >= 25 and rule in entry
            and rule.rstrip().endswith((".", "!", "?", ")")))


def code_rule(a, b):
    """The shared span expanded to the whole sentences of `a` that carry it — or None."""
    na, nb = dedupe.norm(a), dedupe.norm(b)
    m = SequenceMatcher(None, na, nb).find_longest_match()
    if m.size < 35:
        return None
    frag = na[m.a:m.a + m.size]
    sents = re.split(r"(?<=[.!?])\s+", a)
    hit = [snt for snt in sents
           if SequenceMatcher(None, dedupe.norm(snt), frag).find_longest_match().size
           >= min(30, len(frag))]
    rule = " ".join(hit)
    return rule if _clean_sentence(rule, a) else None


def reader_rule(a, b, reader_command, attempts=2):
    """The reader quotes the shared rule from `a`; code accepts only a verbatim quote."""
    transcript = []
    for source, other in ((a, b), (b, a)):
        for _ in range(attempts):
            raw = interview.ask_free(reader_command, QUOTE_ASK.format(a=source, b=other),
                                     stage="rules")
            transcript.append(raw[:200])
            for line in [raw] + raw.split("\n"):
                q = line.strip().strip('"“”')
                if len(q) >= 25 and q in source:
                    return q, transcript
    return None, transcript


def to_sentences(rule, entry):
    """The rule expanded to the whole sentence(s) of its entry that carry it.

    The first production run let "No downstream work begins otherwise." through as a rule — a
    whole sentence, but a half without its subject — and the checkable readers then unanimously
    refused the weekly-decision gate because its text arrived mangled. Expansion is the same
    completion the promoted merge rule performs for picks, aimed at the extraction."""
    sents = re.split(r"(?<=[.!?])\s+", entry)
    frag = dedupe.norm(rule)
    hit = [snt for snt in sents
           if SequenceMatcher(None, dedupe.norm(snt), frag).find_longest_match().size
           >= min(25, len(frag))]
    grown = " ".join(hit)
    return grown if grown and grown in entry and len(grown) >= len(rule) else rule


def extract(entries, merged_pairs, reader_command):
    """Returns (rules, unresolved_pairs, detail). Each rule: text + the 1-based entries backing it."""
    found = {}      # normalized rule -> {"text", "entries"}
    unresolved, detail = [], []
    for a, b in merged_pairs:
        rule = code_rule(entries[a - 1], entries[b - 1]) or code_rule(entries[b - 1], entries[a - 1])
        how = "code"
        if not rule:
            rule, transcript = reader_rule(entries[a - 1], entries[b - 1], reader_command)
            how = "reader"
            if not rule:
                unresolved.append([a, b])
                detail.append({"pair": [a, b], "by": how, "rule": None,
                               "attempts": transcript})
                continue
        rule = to_sentences(rule, entries[a - 1] if rule in entries[a - 1] else entries[b - 1])
        key = dedupe.norm(rule)
        # a rule containing an already-found rule, or contained by one, is the same rule
        merged_into = None
        for k in list(found):
            if key in k or k in key:
                merged_into = k if len(k) >= len(key) else key
                if merged_into != k:
                    found[key] = found.pop(k); found[key]["text"] = rule
                found[merged_into]["entries"].update({a, b})
                break
        if merged_into is None:
            found[key] = {"text": rule, "entries": {a, b}}
        detail.append({"pair": [a, b], "by": how, "rule": rule[:120]})
    rules = [{"text": v["text"], "entries": sorted(v["entries"])} for v in found.values()]
    return rules, unresolved, detail
