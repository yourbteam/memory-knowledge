"""Whether an answered piece bears on the document being built.

The way of asking here won a comparison against a plainer one on two cases — the real library and
an unrelated workflow — recorded with `promotion_applied: false` in both. The approaches returned
the same verdicts; what separated them is that this one can show the page's own words behind every
yes, and the other could show none. Five yeses against zero on the library, two against zero on
the unrelated document.

One thing this does not do, proven rather than assumed: grounding does not establish that a page
is *about* the target. Fed a different agency's workflow, two blind readers both quoted its
"Step 3.4 - Measurement framework" verbatim and both admitted it. The words were real; the page
was not the target's. No wording of the question fixes that — the phrasing that excludes the
lookalike also drops a library page that genuinely constrains the brief. What separates them is
which document the page came from, and that is the owner's call. Kamen made it on 2026-08-23: one
named source of truth, and nothing else is considered. `cover.py open` takes exactly one source,
so at run time a foreign page cannot arise.
"""
import importlib.util
from pathlib import Path

# Loaded by path, not by name: cover.py runs from wherever the operator happens to be standing,
# and a plain import only works when that is this directory.
_spec = importlib.util.spec_from_file_location("interview", Path(__file__).resolve().parent / "interview.py")
interview = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(interview)

_rspec = importlib.util.spec_from_file_location(
    "reflow", Path(__file__).resolve().parent / "reflow.py")
_reflow = importlib.util.module_from_spec(_rspec)
_rspec.loader.exec_module(_reflow)

STRATEGY = "grounded"

QUESTION = (
    "Below is one page of a corporate communications methodology library.\n\n"
    "The target document is: {target}\n\n"
    "Does this page contain anything that constrains what that document must contain, must say, or "
    "must be checked against?\n\n"
    "--- PAGE ---\n{page}\n--- END PAGE ---"
)
QUOTE_QUESTION = (
    "You said this page constrains {target}.\n\n"
    "Quote the exact words from the page that do it."
    "\n\nThis is a data-extraction request, not a task report. Do not begin with any status line, anchor or preamble of any kind. The first character of your reply must be the first character of the answer.\n\n"
    "--- PAGE ---\n{page}\n--- END PAGE ---"
)
CHOICES = ["YES", "NO"]

# Kept apart deliberately, because collapsing any two of them hides something the owner needs.
BEARS, DOES_NOT, FOR_THE_OWNER, NO_ANSWER, NOT_GROUNDED = (
    "bears", "does-not-bear", "for-the-owner", "no-answer", "yes-without-words")


def verdict(seats):
    """The rule alone, over two seats already read. Kept apart from the asking so it can be
    re-derived over pieces already judged without one further reader call — which is what made the
    2026-08-23 correction free.

    Order matters here, and the first version had it wrong. It tested for an ungrounded yes before
    it tested whether the two readers disagreed, so a piece where one said yes and could not quote
    and the other said no came out as `yes-without-words`. Those readers did not agree about
    anything. A disagreement is the owner's whatever happened at the quoting step, so it is tested
    first now.

    Grounding is no longer all-or-nothing either. When both readers say a piece bears and one of
    them produces the page's own words, the piece is admitted carrying the words that exist. The
    first version voided that verified quote because the other seat could not produce one, and a
    page both readers admitted was dropped with real evidence attached to it.
    """
    if any(s["answer"] is None for s in seats):
        return NO_ANSWER
    if seats[0]["answer"] != seats[1]["answer"]:
        return FOR_THE_OWNER
    if seats[0]["answer"] == "NO":
        return DOES_NOT
    return BEARS if any(s["quote"] for s in seats) else NOT_GROUNDED


def judge(page_text, target, reader_command, quotecheck, piece=None):
    """Two readers who cannot see each other. Returns (verdict, seats).

    A disagreement is not resolved here and never will be: the piece is neither in nor out, and it
    goes to the owner. A reply that never became a permitted value is not a verdict either — it is
    recorded as no answer, so nobody is handed a decision that was never made. And a yes that
    nobody could ground does not become a no: it is its own outcome, because the readers may be
    right and merely unable to show it.
    """
    # The reader is shown the page with its layout newlines removed. Shown the raw extraction it
    # quotes a display line, and four of the nineteen quotes this pass first produced ended
    # mid-sentence. quotecheck flattens whitespace on both sides, so a quote taken from the
    # reflowed text still verifies against the piece as stored.
    shown = "\n".join(_reflow.units(page_text, min_chars=1))
    seats = []
    for seat in (1, 2):
        answer, transcript = interview.ask_choice(
            reader_command, QUESTION.format(target=target, page=shown[:6000]), CHOICES,
            stage="relevance", piece=piece, seat=seat)
        quote, quote_attempts, denied = None, [], False
        if answer == "YES":
            quote, qt = interview.ask_quote(
                reader_command, QUOTE_QUESTION.format(target=target, page=shown[:6000]),
                page_text, quotecheck, stage="relevance", piece=piece, seat=seat)
            # Recorded because the first version kept only the choice attempts, and on the two
            # pieces that failed at the quoting step the record could not say what came back.
            quote_attempts = [t["raw_first_line"] for t in qt]
            # An explicit no-such-words reply ended the quoting without a retry; the yes stands
            # ungrounded rather than pressed into a quote (the p-0004 coercion, 2026-08-25).
            denied = any(t.get("denied") for t in qt)
        seats.append({"seat": seat, "answer": answer, "quote": quote,
                      "attempts": [t["raw_first_line"] for t in transcript],
                      "quote_attempts": quote_attempts,
                      **({"denied": True} if denied else {})})
    return verdict(seats), seats
