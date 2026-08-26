"""Ask again until two consecutive rounds add nothing new. The shape Kamen locked for
requirements generally: nothing complete arrives in one pass."""
STRATEGY = "rounds-until-dry"
MAX_ROUNDS = 6

FIRST = ("Below is one page of a corporate communications methodology library.\n\n"
         "List every distinct obligation this page places on {target} — one per line, each copied "
         "verbatim from the page, nothing else.\n\n--- PAGE ---\n{page}\n--- END PAGE ---")
AGAIN = ("Below is one page of a corporate communications methodology library.\n\n"
         "These obligations on {target} have already been taken from it:\n\n{have}\n\n"
         "List any further distinct obligation the page places on {target} that is not already "
         "listed — one per line, each copied verbatim from the page. If there are none, reply "
         "exactly: NONE\n\n--- PAGE ---\n{page}\n--- END PAGE ---")


def extract(page_text, target, reader, interview, quotecheck, common):
    found, dry = [], 0
    for round_no in range(MAX_ROUNDS):
        if round_no == 0:
            prompt = FIRST.format(target=target, page=page_text[:6000])
        else:
            prompt = AGAIN.format(target=target, page=page_text[:6000],
                                  have="\n".join(f"- {f}" for f in found))
        raw = interview.ask_free(reader, prompt)
        fresh = [g for g in common.grounded(interview._candidates(raw), page_text, quotecheck)
                 if g not in found]
        if not fresh:
            dry += 1
            if dry == 2:
                break
        else:
            dry = 0
            found.extend(fresh)
    return sorted(found)
