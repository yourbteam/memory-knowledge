"""Every obligation an admitted piece places on the target.

Chosen by comparison against three alternatives on four pieces the relevance pass admitted and four
it rejected, each asked twice, with `promotion_applied: false` on the record. It was the only one
that left every rejected piece empty while every admitted piece yielded, and the only one stable on
seven of the eight. Its card: nothing ungrounded, separation 1.00, one unstable piece, ten
obligations. The three it beat:

  ask twice and keep what both say   separation 0.50, unstable on five of eight
  rounds until two come back empty   separation 0.75, unstable on five of eight, most found (19)
  vote across five asks, majority 3  left two admitted pieces empty — it suppressed real
                                     obligations rather than steadying them

The one unstable piece was diagnosed rather than tolerated. Page 5 never mentions the Measurement
Brief; it constrains the Step 3 *final brief*, which the library lists as a separate deliverable of
the same step. The model returning nothing was right, and the once it returned two lines it had
conflated siblings. Naming the target as the source names it took that piece to nothing five times
out of five. So the instability lived in what the target was called, not in this code.

What this does not do: it does not write the requirements document. That is built in rounds, with
its own grounding tests, by whoever owns that. This produces the grounded material for it — the
page's own words, each tied to the piece it came from.
"""
import importlib.util
import re
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "interview", Path(__file__).resolve().parent / "interview.py")
interview = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(interview)

_rspec = importlib.util.spec_from_file_location(
    "reflow", Path(__file__).resolve().parent / "reflow.py")
_reflow = importlib.util.module_from_spec(_rspec)
_rspec.loader.exec_module(_reflow)

STRATEGY = "code-cuts-then-judge"
MIN_CHARS = 25

ASK = ("Below is one page of a corporate communications methodology library, cut into numbered "
       "lines by code.\n\nWhich of these lines state an obligation on {target} — something it must "
       "contain, must say, or must be checked against?\n\n"
       "Reply with the numbers only, one per line, and nothing else. If none, reply exactly: NONE"
       "\n\nThis is a data-extraction request, not a task report. Do not begin with any status line, anchor or preamble of any kind. The first character of your reply must be the first character of the answer."
       "\n\n--- NUMBERED LINES ---\n{numbered}\n--- END ---")


def flat(s):
    return re.sub(r"\s+", " ", s).strip()


def units(piece_text):
    """The piece cut into candidate units by code alone. Same piece in, same units out, every
    time — the model is never the one deciding what the candidates are.

    Cut on sentence ends, not on newlines. A newline here is a layout break: on six admitted pages
    it left 93 of 135 units ending mid-sentence, and 17 of the 22 obligations this pass first handed
    on. Cutting on sentence ends left none of 83, and it keeps a table's title with its rows rather
    than stranding it above them."""
    return _reflow.units(piece_text, MIN_CHARS)


def _ask_one_cut(candidates, target, reader_command, piece_text, quotecheck, piece=None):
    """One cut, one ask. Returns what it picked, verified verbatim against the piece."""
    if not candidates:
        return []
    numbered = "\n".join(f"{i}. {u}" for i, u in enumerate(candidates, 1))
    raw = interview.ask_free(reader_command, ASK.format(target=target, numbered=numbered[:9000]),
                             stage="obligations", piece=piece)
    picked = []
    for line in raw.split("\n"):
        m = re.match(r"^\s*(\d{1,3})\s*[.):]?\s*$", line)
        if m and 1 <= int(m.group(1)) <= len(candidates):
            picked.append(candidates[int(m.group(1)) - 1])
    return [u for u in dict.fromkeys(picked) if quotecheck.check(u, piece_text)]


def extract(piece_text, target, reader_command, quotecheck, admitted_on=(), piece=None):
    """Returns (obligations, units_offered, picks_by_cut).

    `admitted_on` carries the verbatim quotes the relevance pass admitted this piece on; they
    are unioned with the picks so the two passes cannot contradict each other about the page.

    The page is cut four ways and each cut is asked on its own, because no single cut is right for
    a whole page. Measured on the ten admitted pages: cutting by line left 17 of 22 obligations
    ending mid-sentence; cutting by sentence left none but lost page 81 entirely, four asks out of
    four, because its tables carry no full stops between their cells and became single blocks of
    716 and 890 characters that nothing picks; cutting by indentation joined page 9's two-column
    body into one block of 1913 characters, 77% of the page. None of those three reads across a
    gutter, so the fourth cuts a table into its cells. No cut is wrong — they fail on different
    pages.

    All four run, and their picks are merged. Every pick is first expanded to the sentence, or run
    of sentences, it sits inside, which turns a fragment into the statement it came from. Then an
    entry another entry already contains is dropped.

    Each cut's own picks are kept beside the merged answer. A merge rule compared later then costs
    no reader at all — the first comparison had to be argued from two cuts because the third's picks
    were never written down.

    The cost is four asks per piece instead of one.
    """
    # A candidate that is most of the page is the page, not a unit of meaning. Offering it lets a
    # single pick absorb every other pick as contained: page 9's indent cut produced one block of
    # 1,913 characters — 77% of its page — and the merged result was the page back. Measured over
    # all 99 recorded picks, nothing real comes close: the largest genuine statement is 34% of its
    # page (588 chars). The 600-character floor keeps a short page's one whole statement offerable.
    page_len = len(_reflow.flow(piece_text))
    picked, offered, by_cut = [], 0, {}
    for name, cut in _reflow.CUTS.items():
        candidates = [u for u in cut(piece_text, MIN_CHARS)
                      if len(u) <= 600 or len(u) <= 0.5 * page_len]
        offered += len(candidates)
        mine = _ask_one_cut(candidates, target, reader_command, piece_text, quotecheck, piece=piece)
        by_cut[name] = {"offered": len(candidates), "picked": mine}
        picked += mine

    # The quotes that admitted this piece are obligations two blind relevance readers already
    # found and verified verbatim on this same page. They join the picks in code, before the
    # merge — never through the ask. Without this, the obligations ask silently re-litigated
    # relevance: ten blind asks on page 81 picked nothing while both readers had quoted "Every
    # activity must connect vertically to an objective" off it, and three admitted pages read as
    # empty. Naming the quote inside the ask instead was measured and rejected: page 23 swung
    # from 0 picks to 23, a led answer rather than a found one.
    for q in admitted_on:
        if quotecheck.check(q, piece_text):
            picked.append(q)
    promoted = {_reflow.whole(u, piece_text) for u in picked}
    kept = []
    for u in sorted(promoted, key=len, reverse=True):
        if quotecheck.check(u, piece_text) and not any(u in k for k in kept):
            kept.append(u)
    return sorted(kept), offered, by_cut
