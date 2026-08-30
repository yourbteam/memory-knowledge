#!/usr/bin/env python3
"""Rank reconciliation candidates from their code-owned outcomes."""

import json
import sys
from pathlib import Path


request = json.loads(Path(sys.argv[1]).read_text())
metric_names = [item["name"] for item in request["metrics"]]
scores = []
for candidate in request["candidates"]:
    outcome = candidate["outcome"]
    if metric_names[0] == "controller-complete":
        chain = outcome["chain"]
        metrics = {
            "controller-complete": 1 if outcome.get("controller_available") and outcome.get("exit_codes") == [0, 0] else 0,
            "runtime-pinned": 1 if outcome.get("runtime_identity") == "snapshot" else 0,
            "policy-drift-survived": 1 if outcome.get("policy_drift_survived") else 0,
            "chain-complete": 1 if chain.get("valid") and chain.get("represented_count") == 35 and chain.get("six_type_ids") == [11, 27] else 0,
        }
    else:
        metrics = {
            "reader-boundary-complete": 1 if outcome.get("full_outer_boundary") else 0,
            "client-policy-correct": 1 if outcome.get("recommended_reader_correct") and outcome.get("client_runtime_preserved") else 0,
            "shared-chain-present": 1 if outcome.get("chain_modules_present") else 0,
        }
    scores.append({"variant_id": candidate["variant_id"], "metrics": metrics})
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, indent=2, sort_keys=True) + "\n")
