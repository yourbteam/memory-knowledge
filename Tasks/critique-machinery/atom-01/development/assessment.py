#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


question = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
outcome = question["execution_result"]["outcome"]
correct = bool(outcome.get("correct"))
response = {
    "case_id": question["case_id"],
    "verdict": "satisfied" if correct else "not-satisfied",
    "reason": (
        f"Observed {outcome.get('actual')!r} against expected {outcome.get('expected')!r}; "
        f"territory_complete={outcome.get('territory_complete')!r}."
    ),
    "evidence_pointers": ["execution-result"],
}
Path(sys.argv[2]).write_text(json.dumps(response, sort_keys=True) + "\n", encoding="utf-8")
