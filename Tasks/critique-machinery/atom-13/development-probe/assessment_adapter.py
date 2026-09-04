#!/usr/bin/env python3
"""Assess final validation from the composed candidate's measured metrics."""

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
metrics = result.get("metrics", {})
required = [
    "direct-contract-correct",
    "refusal-actionable",
    "owner-waiver-request-bound",
    "contract-surface-visible",
    "frozen-input-unchanged",
]
missing = [name for name in required if metrics.get(name) != 1]
verdict = "satisfied" if result.get("status") == "completed" and not missing else "not-satisfied"
reason = "all measured start, waiver, visibility, and immutability checks passed" if not missing else f"measured checks failed: {missing}"
json.dump({
    "case_id": question["case_id"],
    "verdict": verdict,
    "reason": reason,
    "evidence_pointers": ["candidate-stdout", "candidate-telemetry"],
}, open(sys.argv[2], "w"), sort_keys=True)
