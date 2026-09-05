#!/usr/bin/env python3
"""Assess Atom 14 final validation from the composed candidate's measured metrics."""

import json
import pathlib
import sys


question = json.load(open(sys.argv[1]))
stdout = next(
    (item for item in question.get("execution_evidence", []) if item.get("id") == "candidate-stdout"),
    None,
)
result = {}
if stdout and stdout.get("path"):
    path = pathlib.Path(stdout["path"]).with_name("result.json")
    if path.is_file():
        result = json.loads(path.read_text())
metrics = result.get("metrics", {})
required = [
    "no-terminal-operator-use",
    "model-choice-refused",
    "native-auth-real-path",
    "cross-client-proof-verification",
    "untrusted-shell-secret-blocked",
    "controller-regression-pass",
    "historical-run-readable",
    "frozen-input-unchanged",
]
missing = [name for name in required if metrics.get(name) != 1]
verdict = "satisfied" if result.get("status") == "completed" and not missing else "not-satisfied"
reason = (
    "all native authorization, cross-client, regression, compatibility, and integrity checks passed"
    if not missing
    else f"measured checks failed: {missing}"
)
json.dump(
    {
        "case_id": question["case_id"],
        "verdict": verdict,
        "reason": reason,
        "evidence_pointers": ["candidate-stdout", "candidate-telemetry"],
    },
    open(sys.argv[2], "w"),
    sort_keys=True,
)
