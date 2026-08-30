#!/usr/bin/env python3
"""Judge the composed winners on the exact success and failure cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path


request = json.loads(Path(sys.argv[1]).read_text())
outcome = request["execution_result"]["outcome"]
case_id = request["case_id"]
if case_id == "step7-chain-preserved":
    satisfied = (
        outcome.get("accepted") is True
        and outcome.get("ancestry_complete") is True
        and outcome.get("six_type_ids") == [11, 27]
        and outcome.get("ambiguous_auto_merged") == 0
        and not outcome.get("missing")
        and not outcome.get("duplicates")
        and not outcome.get("unknown")
    )
    reason = "all 35 source identities survive exactly once and both six-type wordings reach the terminal lineage"
else:
    satisfied = (
        outcome.get("refused") is True
        and 11 in outcome.get("missing", [])
        and 27 in outcome.get("missing", [])
    )
    reason = "the historical silently lossy output is refused and identifies both missing six-type sources"
response = {
    "case_id": case_id,
    "verdict": "satisfied" if satisfied else "not-satisfied",
    "reason": reason,
    "evidence_pointers": ["execution-result"],
}
Path(sys.argv[2]).write_text(json.dumps(response, indent=2, sort_keys=True) + "\n")
