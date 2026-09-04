#!/usr/bin/env python3
"""Shared experiment entrypoint for the Step-6 feedback atoms.

Byte-identical across every atom's candidate bundles and composed assemblies, one
command shape: <frozen-input> <result-path> <telemetry-path>. The tree's
scripts/atom_check.py owns the contract under test through one function,
``apply(case) -> {"refusal": str|None, "rendered": str, "pack": dict}``: it validates
the case's payload under the atom's rule, and renders the fragment the rule adds.

Metrics, emitted every case, judged against the case's declared ``expect``:
verdict-correct (refused exactly when the expectation says refused),
refusal-actionable (the refusal carries every declared marker; vacuous on accepts),
render-correct (every declared fragment present, in the declared order; vacuous when
the case declares none), prose-untouched (the payload's model prose is never edited by
code — the boxes the case names still carry their original bytes).
"""
import importlib.util
import json
import os
import pathlib
import sys
import time


_SEQUENCE = {"next": int(os.environ.get("EXPERIMENT_TELEMETRY_SEQUENCE_START", "1"))}


def _telemetry(path, event, message, evidence=b"", **observations):
    """Operator telemetry in the candidate wrapper's contract (experiment machinery,
    development-probe candidates): one JSON line per event with a monotonic sequence,
    the active variant, a message, one evidence digest and an observations object.
    Events: work_completed, decision_recorded, operator_rejected, operator_error."""
    import hashlib
    record = {
        "schema_version": 1,
        "sequence": _SEQUENCE["next"],
        "event": event,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID", "control"),
        "message": message,
        "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
        "observations": observations,
    }
    _SEQUENCE["next"] += 1
    with open(path, "a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()


def main():
    frozen_input, result_path, telemetry_path = sys.argv[1:4]
    tree = pathlib.Path(__file__).resolve().parent
    variant = os.environ.get("EXPERIMENT_VARIANT_ID", "control")
    case = json.load(open(frozen_input))
    expect = case["expect"]
    metrics, outcome = {}, {}
    try:
        spec = importlib.util.spec_from_file_location(
            "atom_check", tree / "scripts" / "atom_check.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        before = json.dumps(case.get("pack") or {}, sort_keys=True)
        refusal, rendered = None, ""
        try:
            report = module.apply(json.loads(json.dumps(case)))
            rendered = report.get("rendered") or ""
            outcome["pack_keys"] = sorted((report.get("pack") or {}).keys())
        except ValueError as err:
            refusal = str(err)

        if expect["result"] == "refused":
            metrics["verdict-correct"] = 1 if refusal is not None else 0
            markers = expect.get("refusal_must_contain") or []
            metrics["refusal-actionable"] = (
                1 if refusal is not None and all(m in refusal for m in markers) else 0)
            metrics["render-correct"] = 1
            outcome["refusal"] = (refusal or "")[:300]
        else:
            metrics["verdict-correct"] = 1 if refusal is None else 0
            metrics["refusal-actionable"] = 1
            fragments = expect.get("rendered_must_contain") or []
            ordered = expect.get("rendered_order") or []
            ok = all(f in rendered for f in fragments)
            for first, second in ordered:
                ok = ok and (first in rendered and second in rendered
                             and rendered.index(first) < rendered.index(second))
            absent = expect.get("rendered_must_not_contain") or []
            ok = ok and not any(f in rendered for f in absent)
            metrics["render-correct"] = 1 if ok else 0
            if refusal is not None:
                outcome["refusal"] = refusal[:300]
        # the model's prose is never edited in place: the original pack is unchanged
        metrics["prose-untouched"] = (
            1 if json.dumps(case.get("pack") or {}, sort_keys=True) == before else 0)
        outcome["rendered_head"] = rendered[:200]
        outcome["metrics"] = dict(metrics)
    except Exception as exc:
        _telemetry(telemetry_path, "operator_error",
                   f"the contract crashed on case {case.get('case_id')}: {str(exc)[:200]}",
                   evidence=str(exc).encode("utf-8"), case_id=case.get("case_id"),
                   correction=("fix scripts/atom_check.py so apply(case) returns the contract "
                               "result or raises ValueError with an actionable refusal"))
        with open(result_path, "w") as handle:
            json.dump({"schema_version": 1, "variant_id": variant, "status": "failed",
                       "outcome": {}, "metrics": {}, "error": str(exc)[:500]}, handle)
        return 1
    _telemetry(telemetry_path, "work_completed",
               f"applied the contract to case {case.get('case_id')} "
               f"(expected {expect.get('result')})",
               evidence=json.dumps(outcome, sort_keys=True, ensure_ascii=False).encode("utf-8"),
               case_id=case.get("case_id"), **metrics)
    _telemetry(telemetry_path, "decision_recorded",
               "verdict " + ("refused" if outcome.get("refusal") else "accepted")
               + f" against expected {expect.get('result')}",
               evidence=json.dumps(metrics, sort_keys=True).encode("utf-8"),
               case_id=case.get("case_id"), verdict_correct=metrics.get("verdict-correct"))
    with open(result_path, "w") as handle:
        json.dump({"schema_version": 1, "variant_id": variant, "status": "completed",
                   "outcome": outcome, "metrics": metrics, "error": None}, handle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
