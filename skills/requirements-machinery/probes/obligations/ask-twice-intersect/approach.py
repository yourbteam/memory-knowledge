"""Two blind readers list obligations; only what both produced survives."""
STRATEGY = "ask-twice-intersect"

ASK = ("Below is one page of a corporate communications methodology library.\n\n"
       "List every distinct obligation this page places on {target} — one per line, each copied "
       "verbatim from the page, nothing else.\n\n--- PAGE ---\n{page}\n--- END PAGE ---")


def extract(page_text, target, reader, interview, quotecheck, common):
    seats = []
    for _ in (1, 2):
        raw = interview.ask_free(reader, ASK.format(target=target, page=page_text[:6000]))
        seats.append(set(common.grounded(interview._candidates(raw), page_text, quotecheck)))
    # An obligation only one reader saw is not kept. Cheap stability, paid for in coverage.
    return sorted(seats[0] & seats[1])
