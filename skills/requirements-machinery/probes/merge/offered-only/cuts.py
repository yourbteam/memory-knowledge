"""One place that turns extracted page text into units of meaning.

A newline in a PDF extraction is a layout break, not a meaning break. Cutting on it produced, on the
real library: 93 of 135 units ending mid-sentence, and 17 of the 22 obligations atom 4 handed on.
Two lines that were one sentence were then judged as two statements, and the step above spent a
whole prototype reasoning about halves.

Measured on six admitted pages, units ending mid-sentence:

    cut on newline                        93 of 135
    join lines indented under their head  49 of 93
    join the page, split on sentence ends  0 of 83

The last one also repairs the table case rather than only the wrapped-paragraph case. Page 82's
"Measurement design — record for every KPI" and the four rows under it become one unit carrying all
nine field names, where the newline cut made them four headings with the title stranded above them.

The cost, stated: units are longer, and a heading merges with the bullets beneath it. For a
statement of what a document must contain, a heading and its bullets are one requirement, so this
is the shape wanted rather than a compromise.
"""
import collections
import re

SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u25cf\u2022])")


def flow(text):
    """The page as one run of text, layout newlines removed."""
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip()


def units(text, min_chars=25):
    """The page cut into units of meaning. Same page in, same units out, every time."""
    return [u.strip() for u in SENTENCE_END.split(flow(text)) if len(u.strip()) >= min_chars]


def sentence_crosses(piece, next_piece):
    """Does a sentence run from this piece into the next one?

    The first version of this check asked only whether a piece ended on punctuation, and flagged 31
    of the library's 104 — every page ending on a table row or a heading. That is a false alarm, not
    a defect: a table row is a whole unit that simply has no full stop. What matters is whether the
    text *continues*: this piece ends without terminal punctuation AND the next opens lower-case.
    On the library that happens at none of the 103 boundaries, so the page cut is safe there — and
    now the machinery can say so rather than assume it.
    """
    a, b = flow(piece), flow(next_piece)
    if not a or not b:
        return False
    return not a.rstrip().endswith((".", "!", "?", ")", ":")) and b[0].islower()


BULLET = ("\u25cf", "\u2022", "-", "*", "\u2013", "\u2014")


def by_line(text, min_chars=25):
    """Every display line on its own. Wrong for a wrapped sentence, right for a table row."""
    return [u for u in (flow(l) for l in text.split("\n")) if len(u) >= min_chars]


def by_indent(text, min_chars=25):
    """A line indented further than the line that opened the block continues it. Catches the
    two-column layout where a label sits at the margin and its text wraps beneath."""
    out, opened = [], None
    for raw in text.split("\n"):
        if not raw.strip():
            opened = None; continue
        indent = len(raw) - len(raw.expandtabs().lstrip())
        stripped = raw.strip()
        if out and opened is not None and indent > opened and not stripped.startswith(BULLET):
            out[-1] = out[-1] + " " + stripped
        else:
            out.append(stripped); opened = indent
    return [u for u in (flow(b) for b in out) if len(u) >= min_chars]


def by_sentence(text, min_chars=25):
    """The page joined and cut on sentence ends. Right for prose, and it swallows a table whole."""
    return units(text, min_chars)


def columns(text, min_lines=3, gutter=3, min_gap=12):
    """Where this page starts its columns, read off the page itself.

    A cell begins where text resumes after a run of spaces wide enough to be a gutter, at an
    offset that recurs down the page, far enough from the last column to hold a cell. Measured on
    the fourteen pieces: page 81 returns 0, 28, 64 and 107 — its four visible columns — and page 9
    returns 0 and 30, its label margin and its body. Pages 30, 80, 88 and 101 return nothing but
    the margin, and they are prose. There was no page in between.
    """
    hits = collections.Counter()
    for line in (l for l in text.split("\n") if l.strip()):
        for m in re.finditer(r"(?<=\s{%d})\S" % gutter, line):
            hits[m.start()] += 1
    cols = [0]
    for offset in sorted(o for o, n in hits.items() if n >= min_lines):
        if offset - cols[-1] >= min_gap:
            cols.append(offset)
    return cols


GUTTER = 3          # a column boundary is a gutter, not the single space between two words


def by_cell(text, min_chars=25):
    """A table's unit of meaning is a cell: one column of one row, read down.

    The three cuts before this one all read a table as prose. The line cut returns a display line
    carrying three cells side by side; the sentence cut finds no boundary at all and returns the
    whole table as one 716-character "sentence"; the indent cut joins page 9's two-column body into
    a single 1913-character block, 77% of the page. This cut is the only one that reads across the
    gutter instead of through it. On a page with no columns it returns nothing and says so by
    saying nothing — the other cuts own prose.

    A boundary is only cut where the line actually has a gutter at it. A line of prose running the
    full width of a table page is left whole rather than sliced mid-word, which is what happened to
    "baseline & Awareness" when the edge was applied blindly.
    """
    cols = columns(text)
    if len(cols) < 2:
        return []
    edges = cols + [10 ** 6]
    rows, row = [], None
    for line in (l for l in text.split("\n") if l.strip()):
        if line[:cols[1]].strip():
            row = [[] for _ in cols]; rows.append(row)
        if row is None:
            continue
        # A boundary only exists on this line where the line has a gutter at it. A line of prose
        # running the full width of a table page has no gutter anywhere, so it is not cut at all.
        here = [c for c in cols[1:] if 0 < c < len(line) and line[c:c + 1].strip()
                and c >= GUTTER and not line[c - GUTTER:c].strip()]
        bounds = [0] + here + [len(line)]
        for a, b in zip(bounds, bounds[1:]):
            piece = line[a:b].strip()
            if piece:
                row[cols.index(a) if a in cols else 0].append(piece)
    out = []
    for row in rows:
        for cell in row:
            unit = flow(" ".join(cell))
            if len(unit) >= min_chars:
                out.append(unit)
    return out


CUTS = {"line": by_line, "indent": by_indent, "sentence": by_sentence, "cell": by_cell}


def whole(pick, text, most=2.0):
    """The pick completed to the sentence, or run of sentences, it sits inside.

    A pick from the line cut can start mid-sentence and end mid-word, and it can straddle a
    sentence boundary. Completing it to the run of sentences it overlaps turns a fragment into the
    statement it came from: a 99-character pick on page 80 ending on "without an approved" grew to
    the 199-character statement carrying baseline, target, source and owner.

    The completion may finish a pick; it may not replace one. A page of table rows carries no
    sentence punctuation between its cells, so the splitter reads a whole table as a single
    "sentence" — 716 and 890 characters on page 81. Completing a picked row into that swallowed the
    page and collapsed two picks into one. Growth past `most` times the pick is therefore refused,
    and the pick is returned exactly as it was read. On the four pages measured, every real
    completion sat at or under 2x and every table swallow at 6.6x or more.
    """
    page, p = flow(text), flow(pick)
    start = page.find(p)
    if start < 0:
        return p
    end = start + len(p)
    spans, at = [], 0
    for u in units(text, min_chars=1):
        i = page.find(u, at)
        if i < 0:
            continue
        spans.append((i, i + len(u), u)); at = i + len(u)
    covering = [u for a, b, u in spans if a < end and b > start]
    if not covering:
        return p
    joined = " ".join(covering)
    return joined if len(joined) <= most * len(p) else p
