"""Take a determinate answer from a model the way the harness already does it.

The model is shown the question, the exact permitted answers, and nothing else it may return. An
answer outside that set is refused with a message naming what would satisfy it, and the question is
asked again. Every rejected attempt is kept.

Prompting is not enforcement. This is the enforcement.
"""
import re
import subprocess

ATTEMPTS = 3


def ask_choice(reader_command, question, choices, *, attempts=ATTEMPTS):
    """Returns (answer, transcript). answer is one of choices, or None if none was ever given."""
    allowed = ", ".join(choices)
    transcript = []
    prompt = (
        f"{question}\n\n"
        f"Answer with exactly one of these values and nothing else: {allowed}\n"
        f"Your entire reply must be that one value, on its own, with no heading, preamble, "
        f"explanation or punctuation."
    )
    for attempt in range(1, attempts + 1):
        if not reader_command:
            return None, transcript
        out = subprocess.run(reader_command.split(), input=prompt.encode(), capture_output=True)
        raw = out.stdout.decode("utf-8", "replace").strip()
        value = _match(raw, choices)
        transcript.append({"attempt": attempt, "raw_first_line": raw.split("\n")[0][:120],
                           "accepted": value})
        if value is not None:
            return value, transcript
        prompt = (
            f"That answer was refused: it was not one of the permitted values.\n"
            f"You replied: {raw.splitlines()[0][:120] if raw else '(nothing)'}\n\n"
            f"{question}\n\n"
            f"Reply with exactly one of: {allowed}. Nothing before it, nothing after it."
        )
    return None, transcript


def _match(raw, choices):
    """A reply counts only if one permitted value stands alone on some line of it.

    Deliberately strict, and tested against real reply shapes:

        'YES'                          accepted
        'YES.'  '"NO"'  'yes'          accepted — punctuation and case are not the answer
        'directives=...\n\nYES'        accepted — a header above the answer does not hide it,
                                       which is the failure that started this
        'Based on the page:\nYES'      accepted
        'YES, because the page ...'    REFUSED
        'The answer is YES'            REFUSED

    A value buried in a sentence is refused rather than fished out, because "not YES" and "YES
    would be wrong" both contain YES. The refusal restates the requirement and asks again, which
    costs one call; guessing wrong costs a wrong answer nobody can see.
    """
    for line in raw.split("\n"):
        candidate = line.strip().strip('"').rstrip(".").upper()
        for choice in choices:
            if candidate == choice.upper():
                return choice
    return None


MIN_QUOTE_CHARS = 25


def _candidates(raw):
    """Every span of the reply that could be a quote, longest first.

    ask_choice is deliberately strict because a permitted value buried in prose is unsafe to fish
    out — "not YES" contains YES. A quote is the opposite case: quotecheck verifies it character
    for character against the page, so a span that verifies IS the page's own words no matter what
    surrounded it. Strictness here bought nothing and cost everything. Taking only the first line
    of the reply meant that when the reader answered

        directives=working-agreement/DIRECTIVES.md@2026-08-03; mode=Research; ...

        1. "No research starts until the brief and the measurement brief are approved in writing."
        2. "the mandatory Measurement Brief (baseline, target, source, owner - see Step 10)."

    the header was tested, failed, and six verbatim quotes below it were never looked at. Three
    attempts, three refusals, and a yes downgraded to no-answer on a page the reader had read
    correctly every time.
    """
    out = []
    for m in re.finditer(r'[\"\u201c]([^\"\u201d]{4,})[\"\u201d]', raw):
        out.append(m.group(1))
    for line in raw.split("\n"):
        line = re.sub(r'^\s*(?:[-*\u2022]|\d+[.)])\s*', "", line).strip().strip('"\u201c\u201d')
        if line:
            out.append(line)
    seen, uniq = set(), []
    for c in sorted(out, key=len, reverse=True):
        if c not in seen:
            seen.add(c); uniq.append(c)
    return uniq


def ask_quote(reader_command, question, page_text, quotecheck, *, attempts=ATTEMPTS):
    """Ask for words that are on the page, and refuse anything that is not.

    Every span of the reply is offered to quotecheck and the longest that verifies wins. A short
    fragment is not enough: a handful of common words appears on almost any page, so a span must
    carry MIN_QUOTE_CHARS of the page before it counts as grounding anything.
    """
    transcript = []
    prompt = (
        f"{question}\n\n"
        f"Reply with the exact words copied from the page and nothing else."
    )
    for attempt in range(1, attempts + 1):
        if not reader_command:
            return None, transcript
        out = subprocess.run(reader_command.split(), input=prompt.encode(), capture_output=True)
        raw = out.stdout.decode("utf-8", "replace").strip()
        tried = _candidates(raw)
        hit = next((c for c in tried
                    if len(re.sub(r"\s+", " ", c).strip()) >= MIN_QUOTE_CHARS
                    and quotecheck.check(c, page_text)), None)
        transcript.append({"attempt": attempt, "raw_first_line": raw.split("\n")[0][:120],
                           "candidates_tried": len(tried), "accepted": hit})
        if hit:
            return hit, transcript
        prompt = (
            f"That answer was refused: none of it was found on the page.\n"
            f"Nothing in your reply of {len(tried)} line(s) matched the page character for character.\n\n"
            f"{question}\n\n"
            f"Copy the words exactly as they appear on the page."
        )
    return None, transcript
