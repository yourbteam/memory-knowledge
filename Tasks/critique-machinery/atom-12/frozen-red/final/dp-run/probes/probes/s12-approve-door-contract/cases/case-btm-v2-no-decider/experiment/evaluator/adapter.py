#!/usr/bin/env python3
"""Evidence-backed variant evaluator for the Step-6 feedback atoms.

The experiment machinery hands each candidate only its evidence pointers (stdout, stderr,
telemetry) and the SHA-256 of its result file; the result itself is read from the variant
directory beside the stdout evidence and accepted only when its digest matches. A variant
whose result cannot be found, does not match its declared digest, or carries no metrics
scores 0 everywhere — never a guessed number.
"""
import hashlib
import json
import pathlib
import sys


def _result_for(candidate):
    stdout = next((e for e in candidate.get("evidence", []) if e.get("id") == "stdout"), None)
    if stdout is None:
        return None
    path = pathlib.Path(stdout["path"]).with_name("result.json")
    if not path.is_file():
        return None
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != candidate.get("result_sha256"):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def main():
    request = json.load(open(sys.argv[1]))
    names = [m["name"] for m in request["metrics"]]
    scores = []
    for candidate in request["candidates"]:
        result = _result_for(candidate) or {}
        metrics = result.get("metrics") or {}
        if result.get("status") != "completed":
            metrics = {}
        scores.append({"variant_id": candidate["variant_id"],
                       "metrics": {name: float(metrics.get(name, 0)) for name in names}})
    json.dump({"schema_version": request["schema_version"], "scores": scores},
              open(sys.argv[2], "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
