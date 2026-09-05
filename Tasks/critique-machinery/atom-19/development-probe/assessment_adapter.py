#!/usr/bin/env python3
"""Assess Atom 19 final validation from measured candidate facts."""

import json
import pathlib
import sys


question = json.load(open(sys.argv[1]))
stdout = next((item for item in question.get("execution_evidence", []) if item.get("id") == "candidate-stdout"), None)
result = {}
if stdout and stdout.get("path"):
    path = pathlib.Path(stdout["path"]).with_name("result.json")
    if path.is_file():
        result = json.loads(path.read_text())
required = [
    "exit-correct",
    "order-correct",
    "counts-correct",
    "counts-match-report-route",
    "deltas-correct",
    "comparability-correct",
    "refusal-names-items",
    "frozen-input-unchanged"
]
metrics = result.get("metrics", {})
missing = [name for name in required if metrics.get(name) != 1]
verdict = "satisfied" if result.get("status") == "completed" and not missing else "not-satisfied"
json.dump({
    "case_id": question["case_id"],
    "verdict": verdict,
    "reason": "all declared Atom 19 candidate facts passed" if not missing else f"measured checks failed: {missing}",
    "evidence_pointers": ["candidate-stdout", "candidate-telemetry"],
}, open(sys.argv[2], "w"), sort_keys=True)
