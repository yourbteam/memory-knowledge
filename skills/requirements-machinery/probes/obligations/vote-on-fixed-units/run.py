"""Compare ways of taking every obligation out of an admitted page.

The pieces are named here, not chosen at run time, and they come from the live relevance pass over
the one source of truth: four it admitted and four it rejected. The rejected four are what stops an
approach from winning by calling every line an obligation — that scores perfectly on coverage and
on grounding, and it is worthless.
"""
import hashlib, importlib.util, json, os, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FF = "\f"
TARGET = "the Step 3 Measurement Brief"
ADMITTED = [3, 5, 9, 17]      # p-0003, p-0005, p-0009, p-0017 — both readers said they bear
REJECTED = [1, 2, 4, 6]       # p-0001, p-0002, p-0004, p-0006 — both readers said they do not
RUNS_PER_PIECE = 2            # the same piece, twice, is how instability becomes visible


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


approach = _load("approach")
common = _load("_common")
quotecheck = _load("quotecheck")
_iv = _load("interview")


class Interview:
    """The probe's own free-text ask, so the shipped interview module is not edited before a
    winner exists. Everything determinate still goes through the real code interview."""

    def ask_free(self, reader, prompt):
        if not reader:
            return ""
        out = subprocess.run(reader.split(), input=prompt.encode(), capture_output=True)
        return out.stdout.decode("utf-8", "replace").strip()

    def _candidates(self, raw):
        return _iv._candidates(raw)

    ask_choice = staticmethod(_iv.ask_choice)
    ask_quote = staticmethod(_iv.ask_quote)


def telemetry(path, variant, seq, event, **fields):
    with open(path, "a") as fh:
        fh.write(json.dumps({"variant": variant, "seq": seq, "at": time.time(),
                             "event": event, **fields}) + "\n")


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
    iv = Interview()

    rows, seq = [], 1
    for kind, numbers in (("admitted", ADMITTED), ("rejected", REJECTED)):
        for n in numbers:
            page = pages[n - 1]
            sets = []
            for run in range(RUNS_PER_PIECE):
                got = approach.extract(page, TARGET, reader, iv, quotecheck, common)
                seq += 1
                telemetry(tel, variant, seq, "piece read", page=n, kind=kind, run=run + 1,
                          found=len(got), sample=(got[0][:60] if got else ""))
                sets.append(got)
            ungrounded = [g for s in sets for g in s if not quotecheck.check(g, page)]
            rows.append({"page": n, "kind": kind, "runs": sets,
                         "same": sets[0] == sets[1], "ungrounded": ungrounded})

    admitted_rows = [r for r in rows if r["kind"] == "admitted"]
    rejected_rows = [r for r in rows if r["kind"] == "rejected"]
    yielded = lambda r: any(len(s) > 0 for s in r["runs"])
    empty_admitted = [r["page"] for r in admitted_rows if not yielded(r)]
    unstable = [r["page"] for r in rows if not r["same"]]
    ungrounded = sum(len(r["ungrounded"]) for r in rows)
    share_adm = sum(1 for r in admitted_rows if yielded(r)) / len(admitted_rows)
    share_rej = sum(1 for r in rejected_rows if yielded(r)) / len(rejected_rows)
    found = sorted({g for r in admitted_rows for s in r["runs"] for g in s})

    metrics = {"pieces-yielding-nothing": float(len(empty_admitted)),
               "ungrounded-obligations": float(ungrounded),
               "separates-admitted-from-rejected": round(share_adm - share_rej, 3),
               "unstable-pieces": float(len(unstable)),
               "obligations-found": float(len(found))}
    result_path.write_text(json.dumps({
        "schema_version": 1, "variant_id": variant, "status": "completed",
        "outcome": {"strategy": approach.STRATEGY, "target": TARGET,
                    "admitted": ADMITTED, "rejected": REJECTED,
                    "yielded_nothing": empty_admitted, "unstable_pieces": unstable,
                    "share_admitted_yielding": round(share_adm, 3),
                    "share_rejected_yielding": round(share_rej, 3),
                    "obligations": found, "rows": rows},
        "metrics": metrics, "error": None}))
    telemetry(tel, variant, seq + 1, "finish", **metrics)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a stack trace is not a result; write one the machinery can read
        Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps({
            "schema_version": 1, "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID"),
            "status": "failed", "outcome": {}, "metrics": {},
            "error": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)
