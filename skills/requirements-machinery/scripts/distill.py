"""The pen — one clean statement per rule family, with code proving no word was invented.

Atom 6. The scissors atoms proved every input verbatim; this is the first step allowed to write.
What makes writing safe here is the gate, not the writer: every content word and every number in
the statement must appear in the union of the family's verbatim anchors. A statement that says
"quarterly" when no anchor does is refused, and the refusal names the invented words and what
would satisfy it (G33). Ordinary inflections count as the same word, exactly as the splitter's
term rule in the requirements machine does.
"""
import importlib.util
import re
from pathlib import Path

_here = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _here / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


interview = _load("interview")

# Words a statement may use freely: grammar, not content. Everything else must trace.
GLUE = set("""a an and are as at be been before both but by can cannot each every for from has
have if in into is it its may must no nor not of on one only or per such that the their them
then these this those to under until upon when where which while will with within without""".split())

ASK = ("Below are {n} wordings of the same rule, taken verbatim from one methodology library:\n\n"
       "{numbered}\n\n"
       "Write the rule once, as a single clean requirement statement. Use ONLY words that appear "
       "in the wordings above — every field name, number and term must come from them; add "
       "nothing, invent nothing. One or two sentences.\n\n"
       "This is a data-extraction request, not a task report. Do not begin with any status line, "
       "anchor or preamble. The first character of your reply must be the first character of the "
       "statement.")

SEMANTIC_FIDELITY_ASK = (
    "Compare one proposed requirement statement with its verbatim source anchor or anchors. "
    "Judge meaning, not shared vocabulary. FAITHFUL means the statement preserves who did what "
    "to whom, polarity, direction, causality, permission, obligation, and scope. CHANGED means "
    "any of those relationships is reversed, denied, added, removed, or materially altered.\n\n"
    "--- VERBATIM ANCHORS ---\n{anchors}\n--- END ANCHORS ---\n\n"
    "--- PROPOSED STATEMENT ---\n{statement}\n--- END STATEMENT ---"
)


def _stems(text):
    out = {}
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in GLUE or len(w) < 3:
            continue
        stem = re.sub(r"(ing|ed|es|s|ly)$", "", w) if len(w) > 4 else w
        out.setdefault(stem, w)
    return out


def gate(statement, anchors):
    """Returns (ok, refusal). Every content word and number in the statement must trace to the
    anchors. The refusal names each invented word so a retry can act on it."""
    allowed = _stems(" ".join(anchors))
    invented = sorted({raw for stem, raw in _stems(statement).items() if stem not in allowed})
    numbers = sorted(set(re.findall(r"\d+", statement)) - set(re.findall(r"\d+", " ".join(anchors))))
    problems = invented + [f"number {n}" for n in numbers]
    if not problems:
        return True, None
    return False, (f"the statement uses {', '.join(repr(p) for p in problems)} which appear in "
                   f"none of its {len(anchors)} verbatim anchors — restate using only the "
                   f"anchors' own words, or drop the addition")


def _meaning_surface(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def semantic_fidelity(statement, anchors, reader_command, **labels):
    """Accept only a meaning-preserving rewrite; identical meaning surfaces need no reader."""
    if _meaning_surface(statement) == _meaning_surface(" ".join(anchors)):
        return True, None, {"method": "normalized-verbatim", "verdicts": []}
    prompt = SEMANTIC_FIDELITY_ASK.format(
        anchors="\n".join(f"{index}. {anchor}" for index, anchor in enumerate(anchors, 1)),
        statement=statement,
    )
    verdicts, transcripts = [], []
    for seat in (1, 2):
        verdict, transcript = interview.ask_choice(
            reader_command, prompt, ["FAITHFUL", "CHANGED"],
            stage=labels.get("stage", "distill"), piece=labels.get("piece"), seat=seat,
            preserve_raw=True,
        )
        verdicts.append(verdict)
        transcripts.append(transcript)
    record = {"method": "two-blind-readers", "verdicts": verdicts,
              "transcripts": transcripts}
    if verdicts == ["FAITHFUL", "FAITHFUL"]:
        return True, None, record
    return False, (
        "the statement did not preserve the anchors' meaning according to both blind readers "
        f"(verdicts: {verdicts}) — restate without reversing or changing who did what, "
        "polarity, direction, causality, permission, obligation, or scope"
    ), record


def write_one(anchors, reader_command, attempts=3, **labels):
    """Returns (statement, transcript). Only a statement the gate passes is returned."""
    numbered = "\n".join(f"{i}. {a}" for i, a in enumerate(anchors, 1))
    prompt = ASK.format(n=len(anchors), numbered=numbered)
    transcript = []
    refused_fragment_stems = []
    for _ in range(attempts):
        raw = interview.ask_free(reader_command, prompt, **labels)
        statement = raw.strip().split("\n")[0].strip()
        ok, refusal = gate(statement, anchors)
        # The length floor is a refusal too, and a refusal must say what was wrong (G33): the
        # first run recorded three attempts at "No downstream work begins otherwise." with
        # refusal None each time — the gate had passed and the silent floor rejected it, so the
        # retry changed nothing and the record explained nothing.
        # The floor guards against a fragment of a longer rule; it may not demand more
        # characters than the source material carries. On 2026-08-25 the 28-character anchor
        # "surfaces supporting evidence" trapped the pen: under 40 was a fragment, and every
        # word that would lengthen it was an invention the gate refuses. A statement at least
        # as long as its longest anchor is the whole rule, however short.
        if ok and len(statement) < 40 and len(statement) < max(len(a) for a in anchors):
            ok = False
            refusal = (f"the statement is {len(statement)} characters — a fragment, not a "
                       f"requirement; state the whole rule, including what it obliges and of what")
            refused_fragment_stems.append(set(_stems(statement)))
        # A rewrite that clears the floor by adding grammar words alone is the same fragment.
        # On the Step 5 run "Frame the problem → Insights defined." was refused at 37 characters
        # and "Frame the problem so that Insights defined." passed at 43 with identical content
        # stems — the floor measured size, never whether the retry added anything.
        elif ok and set(_stems(statement)) in refused_fragment_stems:
            ok = False
            refusal = ("the rewrite adds only grammar words to the refused fragment — its "
                       "content words are unchanged; state the whole rule, including what it "
                       "obliges and of what, or the family stays refused")
        fidelity = None
        if ok:
            ok, refusal, fidelity = semantic_fidelity(
                statement, anchors, reader_command, **labels)
        row = {"statement": statement[:200], "ok": ok, "refusal": refusal}
        if fidelity is not None:
            row["semantic_fidelity"] = fidelity
        transcript.append(row)
        if ok:
            return statement, transcript
        prompt = (ASK.format(n=len(anchors), numbered=numbered)
                  + f"\n\nYour previous attempt was refused: {refusal}")
    return None, transcript
