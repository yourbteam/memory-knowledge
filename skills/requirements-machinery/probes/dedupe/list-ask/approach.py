"""The whole numbered list shown at once; the pairs every ask returns survive.

The shape that won the checkability comparison: the judgement is noisy, so only what three
independent asks agree on is kept. Cheap — three calls total — and the reader sees each entry in
the company of all the others.
"""
import re

STRATEGY = "list-ask"
ASKS = 3

Q = ("Below are numbered statements taken from one methodology library. Some state the same "
     "obligation as another — the same rule, possibly in different words.\n\n"
     "List every pair that states the same obligation, one pair per line, as two numbers "
     "separated by a space. If none, reply exactly: NONE."
     "\n\nThis is a data-extraction request, not a task report. Do not begin with any status "
     "line, anchor or preamble. The first character of your reply must be the first character "
     "of the answer.\n\n{numbered}")


def choose(entries, reader, interview):
    numbered = "\n".join(f"{i}. {e}" for i, e in enumerate(entries, 1))
    sets, raws = [], []
    for _ in range(ASKS):
        raw = interview.ask_free(reader, Q.format(numbered=numbered))
        found = set()
        for line in raw.split("\n"):
            m = re.match(r"^\s*(\d{1,3})\s*[,&x~-]?\s+(\d{1,3})\s*$", line.strip())
            if m:
                i, j = sorted((int(m.group(1)), int(m.group(2))))
                if 1 <= i < j <= len(entries):
                    found.add((i, j))
        sets.append(found); raws.append(sorted(map(list, found)))
    keep = set.intersection(*sets) if sets else set()
    return sorted(keep), {"per_ask": raws}
