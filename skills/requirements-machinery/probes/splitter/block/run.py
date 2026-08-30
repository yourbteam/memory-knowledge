#!/usr/bin/env python3
"""One entrypoint, identical in every candidate and in the assembled machinery.

What it does depends on what sits beside it. With only a splitter it measures the cut. With only a
register it measures the refusal. With both — the assembled atomic step — it runs the operator path:
cut the document, build the register over the pieces, prove that nothing comes out while a piece is
unanswered, then answer them all and produce the result.
"""
import hashlib, importlib.util, json, os, re, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FF = "\f"
ANCHORS = 12
CONTEXT = 4
OBLIGATION = re.compile(r"\b(must|required|mandatory|no more than|at least|record for every|shall)\b", re.I)


def load(name):
    path = HERE / f"{name}.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract(src):
    return subprocess.run(["pdftotext", "-layout", str(src), "-"],
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")


def anchors_with_context(text):
    lines = text.split("\n")
    hits = [i for i, l in enumerate(lines) if OBLIGATION.search(l) and len(l.strip()) > 40]
    if len(hits) > ANCHORS:
        step = len(hits) / ANCHORS
        hits = [hits[int(i * step)] for i in range(ANCHORS)]
    return [{"line": lines[i].strip(),
             "neighbourhood": [l.strip() for l in lines[max(0, i - CONTEXT): i + CONTEXT + 1] if l.strip()]}
            for i in hits]


def telemetry(path, variant, seq, event, **kw):
    with open(path, "a") as fh:
        fh.write(json.dumps({"variant": variant, "seq": seq, "at": time.time(), "event": event, **kw}) + "\n")
        fh.flush()


def write(result_path, variant, status, outcome, metrics, error=None):
    result_path.write_text(json.dumps({"schema_version": 1, "variant_id": variant, "status": status,
                                       "outcome": outcome, "metrics": metrics, "error": error}))


def measure_split(text, splitter, tel, variant, seq):
    pieces = splitter.split(text)
    if re.sub(r"\s+", "", "".join(pieces)) != re.sub(r"\s+", "", text):
        return None, None, splitter.STRATEGY + " does not preserve the document"
    retained, detail = [], []
    for a in anchors_with_context(text):
        holder = next((p for p in pieces if a["line"] in p), None)
        kept = sum(1 for l in a["neighbourhood"] if holder and l in holder)
        retained.append(kept / len(a["neighbourhood"]))
        detail.append({"anchor": a["line"][:70], "kept": kept, "of": len(a["neighbourhood"])})
    telemetry(tel, variant, seq, "split measured", pieces=len(pieces), anchors=len(retained))
    if not retained:
        # A document with no obligation in it cannot score a cut. Say so; do not invent a number.
        return pieces, {"piece-count": float(len(pieces)), "detail": detail,
                        "context-retention-unmeasurable": "the document carries no obligation lines"}, None
    return pieces, {"context-retention": sum(retained) / len(retained), "piece-count": float(len(pieces)),
                    "detail": detail}, None


def main():
    variant = os.environ["EXPERIMENT_VARIANT_ID"]
    src = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    work = Path(os.environ["EXPERIMENT_WORK_DIR"])
    result_path = Path(os.environ["EXPERIMENT_RESULT_PATH"])
    tel = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
    splitter, register = load("splitter"), load("register")
    mode = "assembled" if splitter and register else ("splitter" if splitter else "register")
    telemetry(tel, variant, 1, "start", mode=mode, input_sha256=hashlib.sha256(src.read_bytes()).hexdigest())
    text = extract(src)

    if mode == "splitter":
        pieces, metrics, error = measure_split(text, splitter, tel, variant, 2)
        if error:
            write(result_path, variant, "failed", {}, {}, error)
            return 1
        detail = metrics.pop("detail")
        write(result_path, variant, "completed", {"strategy": splitter.STRATEGY, "anchors": detail}, metrics)
        telemetry(tel, variant, 3, "finish", **metrics)
        return 0

    # both remaining modes need a piece set; the register probe uses plain pages
    pieces_text = splitter.split(text) if splitter else [p + FF for p in text.split(FF) if p]
    pieces = [{"id": f"p-{i:04d}", "text": t} for i, t in enumerate(pieces_text, 1)]
    reg = register.Register(pieces)
    hole = pieces[81]["id"] if len(pieces) > 81 else pieces[-1]["id"]
    for p in pieces:
        if p["id"] != hole:
            reg.answer(p["id"], "read", by=f"reader-{variant}")
    telemetry(tel, variant, 2, "register built", pieces=len(pieces), unanswered=hole)

    # asking which pieces are answered, and by whom, is status and stays readable: it is how the
    # hole is found. It carries no answer, so it is not one of the routes tested for leaks.
    status = reg.status()
    unanswered_now = sorted(k for k, v in status.items() if not v["answered"])

    leaks, refusals = [], []
    routes = {"ask for the result": lambda: reg.report(),
              "ask about one answered piece": lambda: reg.answer_for(pieces[0]["id"]),
              "list everything answered": lambda: reg.all_answers(),
              "write the register out": lambda: reg.dump(work / "dump.json")}
    for name, route in routes.items():
        try:
            route()
            leaks.append(name)
            telemetry(tel, variant, 3, "leak", route=name)
        except register.Incomplete as refusal:
            refusals.append(str(refusal))
            telemetry(tel, variant, 3, "refused", route=name, message=str(refusal)[:160])

    names_the_hole = 1.0 if refusals and all(hole in r for r in refusals) else 0.0
    reg.answer(hole, "read", by=f"reader-{variant}")
    try:
        completed = reg.report()
    except register.Incomplete as refusal:
        write(result_path, variant, "failed", {}, {},
              "refused even with every piece answered: " + str(refusal))
        return 1

    sample = pieces[0]["id"]
    outcome = {"unanswered_piece": hole, "leaked_routes": leaks, "refusal_messages": refusals,
               "result_once_complete": completed,
               "status_while_incomplete": {"unanswered": unanswered_now,
                                           sample: status[sample]},
               "status_after": {sample: reg.status()[sample]}}
    if mode == "register":
        metrics = {"names-the-hole": names_the_hole, "leak-count": float(len(leaks))}
    else:
        _, split_metrics, _ = measure_split(text, splitter, tel, variant, 4)
        split_metrics.pop("detail", None)
        unmeasurable = split_metrics.pop("context-retention-unmeasurable", None)
        outcome["strategy"] = splitter.STRATEGY
        if unmeasurable:
            outcome["context_retention"] = "not measurable: " + unmeasurable
        metrics = {"names-the-hole": names_the_hole, "leak-count": float(len(leaks)), **split_metrics}
    write(result_path, variant, "completed", outcome, metrics)
    telemetry(tel, variant, 5, "finish", **metrics)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as failure:  # never a traceback where a result is contracted
        Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps(
            {"schema_version": 1, "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID", "unknown"),
             "status": "failed", "outcome": {}, "metrics": {},
             "error": f"{type(failure).__name__}: {failure}"}))
        raise SystemExit(1)
