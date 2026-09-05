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

_cspec = importlib.util.spec_from_file_location("reader_coverage", Path(__file__).resolve().parent / "reader_coverage.py")
coverage = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(coverage)

STRATEGY = "code-cuts-then-judge"
MIN_CHARS = 1

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


def candidate_units(piece_text):
    """Return the deterministic units each obligation-reader cut receives."""
    return {name: cut(piece_text, MIN_CHARS) for name, cut in _reflow.CUTS.items()}


def _ask_one_cut(candidates, target, reader_command, piece_text, quotecheck, piece=None,
                 receipts=None):
    """Every complete unit is offered; malformed replies fail instead of becoming empty picks."""
    picked = []
    for batch in coverage.unit_batches(candidates):
        numbered = "\n".join(row["line"] for row in batch)
        raw = interview.ask_free(reader_command, ASK.format(target=target, numbered=numbered),
                                 stage="obligations", piece=piece)
        ids = {row["id"] for row in batch}
        selected = []
        if raw.strip() != "NONE":
            lines = raw.strip().splitlines()
            if not lines:
                raise ValueError("obligation reader returned no answer; input coverage is incomplete")
            for line in lines:
                match = re.fullmatch(r"\s*(\d+)\s*[.):]?\s*", line)
                if not match or int(match.group(1)) not in ids:
                    raise ValueError("obligation reader returned an invalid selection; input coverage is incomplete")
                selected.append(int(match.group(1)))
        chosen = [row["text"] for row in batch if row["id"] in selected]
        if any(not quotecheck.check(unit, piece_text) for unit in chosen):
            raise ValueError("selected obligation does not match its source")
        picked.extend(chosen)
        if receipts is not None:
            receipts.append({"unit_ids": sorted(ids), "shown_sha256": coverage.digest(numbered),
                             "shown_characters": len(numbered), "selected_ids": sorted(set(selected)),
                             "answer": raw})
    return list(dict.fromkeys(picked))


def extract(piece_text, target, reader_command, quotecheck, admitted_on=(), piece=None):
    """Returns (obligations, units_offered, picks_by_cut).

    `admitted_on` carries the verbatim quotes the relevance pass admitted this piece on; they
    are unioned with the picks so the two passes cannot contradict each other about the page.

    The active code-owned cuts in reflow.CUTS determine the candidate set. Every
    nonempty unit is offered intact, across as many numbered batches as necessary.
    Oversized indivisible units travel alone instead of being dropped or clipped.
    Each cut retains its selected units and source-bound batch receipts.

    Selections are expanded to their surrounding source statement and contained
    duplicates are removed. The reader-call cost is the number of batches across
    the active cuts, rather than a fixed number of calls per piece.

    Historical comparison notes below describe superseded cuts and candidate filtering;
    current batching offers all structural units intact. These notes retain their
    original wording for the unverified empirical claim inventory.

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
    picked, offered, by_cut = [], 0, {}
    for name, candidates in candidate_units(piece_text).items():
        offered += len(candidates)
        receipts = []
        mine = _ask_one_cut(candidates, target, reader_command, piece_text, quotecheck, piece=piece,
                            receipts=receipts)
        by_cut[name] = {"offered": len(candidates), "picked": mine,
                        "coverage": coverage.receipt(piece_text, target, receipts)}
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
