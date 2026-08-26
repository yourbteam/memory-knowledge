#!/usr/bin/env python3
"""Judge one quote-check approach against true and false quotes drawn from the frozen document.

The declared metric is deliberately the WEAKER of the two sides. A checker that refuses everything
scores perfectly on rejecting falsehoods and zero on accepting truth, so the weaker side is zero and
it cannot win. The same trap cost a run in atom 1; this is what stops it here.
"""
import hashlib, importlib.util, json, os, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, path=None):
    spec = importlib.util.spec_from_file_location(name, path or (HERE / f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cases = _load("_cases", HERE / "_cases.py")
checker = _load("quotecheck")


def telemetry(path, variant, seq, event, **kw):
    with open(path, "a") as fh:
        fh.write(json.dumps({"variant": variant, "seq": seq, "at": time.time(), "event": event, **kw}) + "\n")
        fh.flush()


def main():
    variant = os.environ["EXPERIMENT_VARIANT_ID"]
    src = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    result_path = Path(os.environ["EXPERIMENT_RESULT_PATH"])
    tel = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
    telemetry(tel, variant, 1, "start", strategy=checker.STRATEGY,
              input_sha256=hashlib.sha256(src.read_bytes()).hexdigest())

    text = subprocess.run(["pdftotext", "-layout", str(src), "-"],
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")
    true_cases, false_cases = cases.build(text)

    accepted_true = [c for c in true_cases if checker.check(c["quote"], c["text"])]
    accepted_false = [c for c in false_cases if checker.check(c["quote"], c["text"])]
    accepts_true = len(accepted_true) / len(true_cases) if true_cases else 0.0
    rejects_false = 1 - (len(accepted_false) / len(false_cases)) if false_cases else 0.0
    telemetry(tel, variant, 2, "judged", true_cases=len(true_cases), false_cases=len(false_cases),
              accepts_true=accepts_true, rejects_false=rejects_false)

    # A single accepted falsehood is a wrong requirement in the final list. It is counted, never
    # averaged: one miss in sixty-one reads as 0.98 and hides the one that matters.
    metrics = {"accepted-falsehoods": float(len(accepted_false)), "accepts-true": accepts_true}
    result_path.write_text(json.dumps({
        "schema_version": 1, "variant_id": variant, "status": "completed",
        "outcome": {"strategy": checker.STRATEGY, "true_cases": len(true_cases),
                    "false_cases": len(false_cases), "accepts_true": accepts_true,
                    "rejects_false": rejects_false,
                    "true_quotes_wrongly_refused": [c["piece"] for c in true_cases if c not in accepted_true][:5],
                    "false_quotes_wrongly_accepted": [{"piece": c["piece"], "why": c["why"]} for c in accepted_false][:5]},
        "metrics": metrics, "error": None}))
    telemetry(tel, variant, 3, "finish", **metrics)
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
