#!/usr/bin/env python3
"""Judge one way of asking whether a page bears on a named target document.

Ten pages, fixed by rule, each read by two readers who cannot see each other. Two things are
measured and neither is my opinion:

  misses-the-obvious  pages that carry the target's own section heading and are still called
                      irrelevant. A floor: whatever else it does, it must not miss those.
  reader-disagreement pages where the two blind readers differ. Under the approved envelope those
                      pages are neither in nor out — they go to the owner — so a way of asking that
                      produces more of them costs the owner more of his time.
"""
import hashlib, importlib.util, json, os, re, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = "the Step 3 measurement brief — the one-page brief UP must produce for a client campaign"
PAGES = 10
FF = "\f"


def _load(name, path=None):
    spec = importlib.util.spec_from_file_location(name, path or (HERE / f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


approach = _load("relevance")
quotecheck = _load("quotecheck")
interview = _load("_interview", HERE / "_interview.py")


def telemetry(path, variant, seq, event, **kw):
    with open(path, "a") as fh:
        fh.write(json.dumps({"variant": variant, "seq": seq, "at": time.time(), "event": event, **kw}) + "\n")
        fh.flush()


OBVIOUS_IN_SAMPLE = 4


def choose(pages):
    """Four pages that name the target, six that do not, so the sample can fail in both directions.

    The first version took every page naming the target and left one page that did not — nine
    obvious out of ten. Nothing could have gone wrong in the other direction.
    """
    named = [i for i, t in enumerate(pages, 1) if re.search(r"measurement brief", t, re.I)]
    step = max(1, len(named) // OBVIOUS_IN_SAMPLE)
    obvious = named[::step][:OBVIOUS_IN_SAMPLE]
    rest = [i for i in range(1, len(pages) + 1) if i not in named]
    fill = max(0, PAGES - len(obvious))
    filler = rest[:: max(1, len(rest) // max(1, fill))][:fill]
    return sorted(set(obvious + filler))[:PAGES], set(obvious)


def ask(reader, prompt):
    out = subprocess.run(reader.split(), input=prompt.encode(), capture_output=True)
    return out.stdout.decode("utf-8", "replace")


def main():
    variant = os.environ["EXPERIMENT_VARIANT_ID"]
    src = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    result_path = Path(os.environ["EXPERIMENT_RESULT_PATH"])
    tel = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
    reader = os.environ.get("PIECE_READER_COMMAND")
    telemetry(tel, variant, 1, "start", strategy=approach.STRATEGY,
              input_sha256=hashlib.sha256(src.read_bytes()).hexdigest())

    text = subprocess.run(["pdftotext", "-layout", str(src), "-"],
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")
    pages = [p for p in text.split(FF) if p.strip()]
    chosen, obvious = choose(pages)
    telemetry(tel, variant, 2, "pages chosen", pages=chosen, obvious=sorted(obvious))

    rows, seq = [], 2
    for n in chosen:
        page = pages[n - 1]
        verdicts, unread, ungrounded_yes = [], [], []
        for seat in (1, 2):
            question = approach.QUESTION.format(target=TARGET, page=page[:6000])
            answer, tr = interview.ask_choice(reader, question, approach.CHOICES)
            seq += 1
            telemetry(tel, variant, seq, "page read", page=n, seat=seat, answer=answer,
                      attempts=len(tr), refused=[t["raw_first_line"] for t in tr if t["accepted"] is None])
            bears, quote, ungrounded = (answer == "YES") if answer else None, None, False
            if answer == "YES" and approach.NEEDS_QUOTE:
                qq = approach.QUOTE_QUESTION.format(target=TARGET, page=page[:6000])
                quote, qtr = interview.ask_quote(reader, qq, page, quotecheck)
                seq += 1
                telemetry(tel, variant, seq, "quote asked", page=n, seat=seat,
                          quote=(quote or "")[:70], attempts=len(qtr))
                # A yes that cannot produce the page's own words is not a yes. But it is also not
                # the same failure as a reply nobody could read, and the first version counted it
                # as one. On the unrelated document that inverted the result: grounded refused an
                # ungrounded claim on page 6, scored 1.0 unreadable for doing so, and lost at a
                # higher rank than the metric where plain-yesno's unsupported claim showed up.
                # Refusing is the mechanism working. It is recorded, and it is not a fault.
                if quote is None:
                    bears, ungrounded = None, True
            if bears is None:
                (ungrounded_yes if ungrounded else unread).append(
                    {"seat": seat, "attempts": [t["raw_first_line"] for t in tr]})
            verdicts.append({"bears": bears, "quote": quote})
        rows.append({"page": n, "obvious": n in obvious, "ungrounded_yes": ungrounded_yes,
                     "seat1": verdicts[0]["bears"], "seat2": verdicts[1]["bears"],
                     "unread": unread, "quotes": [v["quote"] for v in verdicts]})

    # Three outcomes, kept apart. A reply nobody could read is not a difference of judgement:
    # sending it to the owner as one would hand him a decision nobody actually made.
    unreadable = [r for r in rows if r["unread"]]
    both_answered = [r for r in rows if not r["unread"] and not r["ungrounded_yes"]]
    disagreements = [r for r in both_answered if r["seat1"] != r["seat2"]]
    agreed_yes = {r["page"] for r in both_answered if r["seat1"] is True and r["seat2"] is True}
    missed = sorted(p for p in obvious if p in {r["page"] for r in both_answered} and p not in agreed_yes)

    # The three metrics above are all satisfied by an approach that answers YES to every page:
    # it misses nothing obvious, its two seats never disagree, and every reply reads cleanly.
    # Checked against this run's own recorded rows, not reasoned about: always-YES scored
    # 0.0 / 0.0 / 0.0 — a perfect card for a mechanism with no judgement in it.
    #
    # The fix has to be a metric whose honest direction is maximize, because the machinery ranks
    # lexicographically and "fewest claims" would reward an approach that never notices a page
    # unless the page names the target. So the measure is separation, not abstinence: how far the
    # pages naming the target outrun the pages that do not.
    #
    #     always YES   1.00 - 1.00 = 0.00
    #     always NO    0.00 - 0.00 = 0.00
    #     discriminating approach          high
    #
    # Both blanket answers collapse to zero from opposite sides. A genuine find on an unnamed page
    # costs one share and no more, which is the right price: page 84 — KPI modules by campaign
    # type — is a find, not a fault, and the measure must not punish it into hiding.
    named_yes = len(agreed_yes & obvious)
    unnamed = [r for r in both_answered if r["page"] not in obvious]
    claimed = [r for r in unnamed if r["seat1"] is True and r["seat2"] is True]
    seen_obvious = [p for p in obvious if p in {r["page"] for r in both_answered}]
    share_named = named_yes / len(seen_obvious) if seen_obvious else 0.0
    share_unnamed = len(claimed) / len(unnamed) if unnamed else 0.0
    # The two approaches returned the same verdict on every page of the ten-page sample: same five
    # agreed yeses, same four agreed noes, same single disagreement. All four metrics above tie
    # exactly, and a full lexicographic tie is broken by variant id — alphabetically, which would
    # let an accident decide a real question.
    #
    # What they differ on is not the verdict. It is whether a yes can be traced to the page's own
    # words. That is not a preference: atom 2 is locked, and its guarantee is that nothing is
    # accepted without words verified against the piece they came from. An agreed yes with no
    # quote cannot be handed to whoever writes the requirement.
    #
    # Declared here rather than argued in a report, because the machinery ranks and I do not.
    # Stated plainly for the record: the ten-page sample was already read when this metric was
    # written. The formal run has not happened, so it is still declared before the run that
    # decides — but it was not declared blind, and the record should not pretend otherwise.
    traceless = [r for r in both_answered
                 if r["seat1"] is True and r["seat2"] is True and not any(r["quotes"] or [])]
    metrics = {"misses-the-obvious": float(len(missed)),
               "unreadable-replies": float(len(unreadable)),
               "separates-named-from-unnamed": round(share_named - share_unnamed, 3),
               "yes-without-words": float(len(traceless)),
               "reader-disagreement": float(len(disagreements))}
    result_path.write_text(json.dumps({
        "schema_version": 1, "variant_id": variant, "status": "completed",
        "outcome": {"strategy": approach.STRATEGY, "target": TARGET, "pages": chosen,
                    "obvious_pages": sorted(obvious), "missed_obvious": missed,
                    "disagreed_on": [r["page"] for r in disagreements],
                    "no_answer_on": [{"page": r["page"], "seats": r["unread"]} for r in unreadable],
                    "yes_refused_for_lack_of_words": [r["page"] for r in rows if r["ungrounded_yes"]],
                    "unnamed_pages_claimed": [r["page"] for r in claimed],
                    "yes_without_words": [r["page"] for r in traceless], "share_named": round(share_named, 3), "share_unnamed": round(share_unnamed, 3),
                    "rows": rows},
        "metrics": metrics, "error": None}))
    telemetry(tel, variant, seq + 1, "finish", **metrics)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as failure:
        Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps(
            {"schema_version": 1, "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID", "unknown"),
             "status": "failed", "outcome": {}, "metrics": {},
             "error": f"{type(failure).__name__}: {failure}"}))
        raise SystemExit(1)
