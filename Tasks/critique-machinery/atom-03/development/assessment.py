#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


question = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
telemetry_ref = next(item for item in question["execution_evidence"] if item["id"] == "candidate-telemetry")
telemetry_path = Path(telemetry_ref["path"])
telemetry_bytes = telemetry_path.read_bytes()
if hashlib.sha256(telemetry_bytes).hexdigest() != telemetry_ref["sha256"]:
    raise RuntimeError("candidate telemetry changed after the assessment question was frozen")
telemetry = json.loads(telemetry_bytes)
result_path = telemetry_path.parent / "result.json"
result_bytes = result_path.read_bytes()
if hashlib.sha256(result_bytes).hexdigest() != telemetry["evidence_sha256"]:
    raise RuntimeError("candidate result is not the evidence bound by operator telemetry")
outcome = json.loads(result_bytes)["outcome"]
lens_count = len(outcome.get("lenses", []))
satisfied = bool(
    outcome.get("correct")
    and outcome.get("classification_correct")
    and outcome.get("grounded_count") == lens_count
    and outcome.get("actionable_quote_count") == lens_count
    and outcome.get("invalid_quote_refused")
)
response = {
    "case_id": question["case_id"],
    "verdict": "satisfied" if satisfied else "not-satisfied",
    "reason": (
        f"Observed correct classifications={outcome.get('classification_count')}/{lens_count}, "
        f"grounded={outcome.get('grounded_count')}/{lens_count}, actionable={outcome.get('actionable_quote_count')}/{lens_count}, "
        f"invalid quote refusal={outcome.get('invalid_quote_refused')}."
    ),
    "evidence_pointers": ["candidate-telemetry"],
}
Path(sys.argv[2]).write_text(json.dumps(response, sort_keys=True) + "\n", encoding="utf-8")
