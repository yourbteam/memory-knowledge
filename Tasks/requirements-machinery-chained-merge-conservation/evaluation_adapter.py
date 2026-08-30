#!/usr/bin/env python3
"""Score experiment candidates from their code-owned outcomes."""

from __future__ import annotations

import json
import sys
from pathlib import Path


request = json.loads(Path(sys.argv[1]).read_text())
scores = []
metric_names = [item["name"] for item in request["metrics"]]
for candidate in request["candidates"]:
    outcome = candidate["outcome"]
    if metric_names[0] == "ancestry-complete":
        metrics = {
            "ancestry-complete": 1 if outcome["ancestry_complete"] else 0,
            "silent-losses": outcome["silent_losses"],
            "ambiguous-automerge": outcome["ambiguous_auto_merged"],
        }
    else:
        success_case = outcome["case_kind"] == "success"
        metrics = {
            "loss-detected": 1 if (outcome["accepted"] if success_case else outcome["refused"]) else 0,
            "false-refusals": 1 if success_case and outcome["refused"] else 0,
        }
    scores.append({"variant_id": candidate["variant_id"], "metrics": metrics})
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, indent=2, sort_keys=True) + "\n")
