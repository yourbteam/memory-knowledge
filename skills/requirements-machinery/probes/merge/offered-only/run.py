"""Compare ways of bounding the completion a merged obligation gets.

Atom 4 asks three cuts of the same page and merges their picks. A pick from the line cut can end
mid-sentence, so the merge completes it to the sentence it sits inside. On a table there are no
sentences — page 81's splitter reads the whole table as one 716-character "sentence" — and an
unbounded completion swallowed the page, then ate its own siblings as duplicates. That is what
stopped the live pass at eight of fourteen pages.

What varies here is only the bound on that completion. The picks are frozen, and the merge that
follows — drop exact repeats, keep the longest, drop anything contained in what is kept — is
identical for every approach. Fifteen anchors are statements the source makes about the Step 3
Measurement Brief, each verified verbatim on its own page and each reachable from the frozen picks.
An approach that loses one has lost a requirement. An approach that fuses two into one entry has
stopped being a list of requirements.
"""
import hashlib, importlib.util, json, os, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = 2   # the same material twice, because a merge rule that is not repeatable is not a rule


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


approach = _load("approach")
_reflow = _load("reflow")


def merge(picks, text):
    """The merge itself. Identical for every approach; only `approach.whole` differs."""
    completed = {approach.whole(p, text) for p in picks}
    kept = []
    for u in sorted(completed, key=len, reverse=True):
        if not any(u in k for k in kept):
            kept.append(u)
    return kept


def telemetry(path, variant, seq, event, **fields):
    with open(path, "a") as fh:
        fh.write(json.dumps({"variant": variant, "seq": seq, "at": time.time(),
                             "event": event, **fields}) + "\n")


def main():
    variant = os.environ["EXPERIMENT_VARIANT_ID"]
    src = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    result_path = Path(os.environ["EXPERIMENT_RESULT_PATH"])
    tel = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
    material = json.loads(src.read_text())
    pages, picks, anchors = material["pages"], material["picks"], material["anchors"]
    telemetry(tel, variant, 1, "start", strategy=approach.STRATEGY,
              input_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
              pages=len(pages), picks=sum(len(v) for v in picks.values()), anchors=len(anchors))

    runs = []
    for r in range(RUNS):
        entries = {pid: merge(picks[pid], pages[pid]) for pid in sorted(picks)}
        runs.append(entries)
        telemetry(tel, variant, 2 + r, "run", index=r + 1,
                  entries=sum(len(v) for v in entries.values()))
    entries = runs[0]
    repeatable = all(runs[i] == runs[0] for i in range(1, RUNS))

    off_page = [(pid, e) for pid in entries for e in entries[pid]
                if e not in _reflow.flow(pages[pid])]
    lost = [a for a in anchors
            if not any(a["text"] in e for e in entries.get(a["piece"], []))]
    buried = []
    for pid in entries:
        for e in entries[pid]:
            carried = [a["text"] for a in anchors if a["piece"] == pid and a["text"] in e]
            if len(carried) > 1:
                buried.append({"piece": pid, "entry": e[:120], "anchors": carried})
    # An entry the page continues with a lowercase word is a sentence the layout cut, not a
    # statement. A table cell is continued by the next cell, which starts with a capital or a
    # digit, so this counts the truncations without counting the rows. The anchors alone cannot
    # see this: they are fifteen statements, and a merge carries about thirty entries.
    cut = []
    for pid in entries:
        page = _reflow.flow(pages[pid])
        for e in entries[pid]:
            i = page.find(e)
            if i < 0:
                continue
            rest = page[i + len(e):].lstrip()
            if rest and rest[0].islower():
                cut.append({"piece": pid, "entry": e[-70:], "continues": rest[:40]})
    # Burial measured without the anchors. Every frozen pick is a reader saying "this is an
    # obligation". An entry that contains two picks which do not overlap each other has fused two
    # separate judgements into one line. Picks from different cuts that cover the same statement do
    # overlap, so a completion that merely reconciles two cuts is not counted against it.
    fused = []
    for pid in entries:
        page = _reflow.flow(pages[pid])
        spans = []
        for pk in picks[pid]:
            f = _reflow.flow(pk); i = page.find(f)
            if i >= 0:
                spans.append((i, i + len(f)))
        for e in entries[pid]:
            i = page.find(e)
            if i < 0:
                continue
            inside = sorted(sp for sp in spans if sp[0] >= i and sp[1] <= i + len(e))
            clusters, reach = 0, -1
            for a, b in inside:
                if a >= reach:
                    clusters += 1
                reach = max(reach, b)
            if clusters > 1:
                fused.append({"piece": pid, "entry": e[:110], "distinct_picks": clusters})
    chars = sum(len(e) for pid in entries for e in entries[pid])

    metrics = {"not-on-the-page": float(len(off_page)),
               "loses-an-anchor": float(len(lost)),
               "cut-mid-sentence": float(len(cut)),
               "fuses-obligations": float(sum(f["distinct_picks"] - 1 for f in fused)),
               "buries-anchors": float(len(buried)),
               "characters-carried": float(chars)}
    result_path.write_text(json.dumps({
        "schema_version": 1, "variant_id": variant, "status": "completed",
        "outcome": {"strategy": approach.STRATEGY, "repeatable": repeatable,
                    "entries": sum(len(v) for v in entries.values()),
                    "per_page": {pid: len(v) for pid, v in entries.items()},
                    "lost_anchors": [f'{a["piece"]}: {a["text"]}' for a in lost],
                    "buried": buried, "cut": cut, "fused": fused,
                    "longest_entry": max((len(e) for v in entries.values() for e in v), default=0),
                    "merged": entries},
        "metrics": metrics, "error": None}, ensure_ascii=False))
    telemetry(tel, variant, 2 + RUNS, "finish", **metrics)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps({
            "schema_version": 1, "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID"),
            "status": "failed", "outcome": {}, "metrics": {},
            "error": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)
