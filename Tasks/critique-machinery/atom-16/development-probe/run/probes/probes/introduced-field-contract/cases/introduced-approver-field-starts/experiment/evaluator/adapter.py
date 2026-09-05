#!/usr/bin/env python3
"""Score only hash-bound Atom 16 Development-Probe results."""

import hashlib
import json
import pathlib
import sys


def result_for(candidate):
    stdout = next((item for item in candidate.get("evidence", []) if item.get("id") == "stdout"), None)
    if stdout is None:
        return {}
    path = pathlib.Path(stdout["path"]).with_name("result.json")
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != candidate.get("result_sha256"):
        return {}
    return json.loads(path.read_text())


request = json.load(open(sys.argv[1]))
names = [item["name"] for item in request["metrics"]]
scores = []
for candidate in request["candidates"]:
    result = result_for(candidate)
    metrics = result.get("metrics", {}) if result.get("status") == "completed" else {}
    scores.append({"variant_id": candidate["variant_id"], "metrics": {
        name: float(metrics.get(name, 0)) for name in names
    }})
json.dump({"schema_version": request["schema_version"], "scores": scores}, open(sys.argv[2], "w"), sort_keys=True)
