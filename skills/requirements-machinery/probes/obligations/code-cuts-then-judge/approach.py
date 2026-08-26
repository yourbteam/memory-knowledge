"""Code cuts the page into candidate lines and numbers them. The model never chooses the set —
it answers which numbers are obligations. The set cannot move between asks, because it is not
the model's to move. This is the shape that decided atoms 1, 2 and 3: code fixes what gets looked
at, a model judges what it means."""
import re
STRATEGY = "code-cuts-then-judge"

ASK = ("Below is one page of a corporate communications methodology library, cut into numbered "
       "lines by code.\n\nWhich of these lines state an obligation on {target} — something it must "
       "contain, must say, or must be checked against?\n\n"
       "Reply with the numbers only, one per line, and nothing else. If none, reply exactly: NONE"
       "\n\n--- NUMBERED LINES ---\n{numbered}\n--- END ---")


def candidates(page_text, common):
    """The page cut into units by code alone. Same page in, same units out, every time."""
    units = []
    for raw in page_text.split("\n"):
        line = common.flat(raw)
        if len(line) >= common.MIN_CHARS:
            units.append(line)
    return units


def extract(page_text, target, reader, interview, quotecheck, common):
    units = candidates(page_text, common)
    if not units:
        return []
    numbered = "\n".join(f"{i}. {u}" for i, u in enumerate(units, 1))
    raw = interview.ask_free(reader, ASK.format(target=target, numbered=numbered[:9000]))
    picked = []
    for line in raw.split("\n"):
        m = re.match(r"^\s*(\d{1,3})\s*[.):]?\s*$", line)
        if m:
            n = int(m.group(1))
            if 1 <= n <= len(units):
                picked.append(units[n - 1])
    return sorted(set(common.grounded(picked, page_text, quotecheck)))
