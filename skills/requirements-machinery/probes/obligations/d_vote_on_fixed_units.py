"""Code cuts the page into fixed units; several independent asks vote on each unit; a unit needs a
majority to survive.

The comparison this was added to had already shown why. With the units completely fixed by code and
the identical question, the same page returned NONE once and the same two numbers twice. The
candidate set never moved — the judgement did. Fixing what gets looked at, which is what made the
coverage register, the quote check and the relevance pass work, is not sufficient here.

So this approach does not try to make one judgement reliable. It assumes the judgement is noisy and
takes the majority of several, which is the only thing that turns a noisy yes/no into a repeatable
one. Every surviving unit is still checked verbatim against the page, because atom 2 is locked.
"""
import re
STRATEGY = "vote-on-fixed-units"
VOTES = 5
MAJORITY = 3

ASK = ("Below is one page of a corporate communications methodology library, cut into numbered "
       "lines by code.\n\nWhich of these lines state an obligation on {target} — something it must "
       "contain, must say, or must be checked against?\n\n"
       "Reply with the numbers only, one per line, and nothing else. If none, reply exactly: NONE"
       "\n\n--- NUMBERED LINES ---\n{numbered}\n--- END ---")


def candidates(page_text, common):
    """The page cut into units by code alone. Same page in, same units out, every time."""
    return [line for line in (common.flat(r) for r in page_text.split("\n"))
            if len(line) >= common.MIN_CHARS]


def _numbers(raw, upper):
    picked = set()
    for line in raw.split("\n"):
        m = re.match(r"^\s*(\d{1,3})\s*[.):]?\s*$", line)
        if m and 1 <= int(m.group(1)) <= upper:
            picked.add(int(m.group(1)))
    return picked


def extract(page_text, target, reader, interview, quotecheck, common):
    units = candidates(page_text, common)
    if not units:
        return []
    numbered = "\n".join(f"{i}. {u}" for i, u in enumerate(units, 1))
    prompt = ASK.format(target=target, numbered=numbered[:9000])
    tally = {}
    for _ in range(VOTES):
        for n in _numbers(interview.ask_free(reader, prompt), len(units)):
            tally[n] = tally.get(n, 0) + 1
    kept = [units[n - 1] for n, votes in tally.items() if votes >= MAJORITY]
    return sorted(set(common.grounded(kept, page_text, quotecheck)))
