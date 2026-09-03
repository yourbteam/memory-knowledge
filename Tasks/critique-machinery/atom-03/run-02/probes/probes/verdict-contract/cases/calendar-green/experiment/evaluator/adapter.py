#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
scores = []
for candidate in request["candidates"]:
    evidence_path = Path(candidate["evidence"][0]["path"])
    result_path = evidence_path.parent / "result.json"
    result_bytes = result_path.read_bytes()
    if hashlib.sha256(result_bytes).hexdigest() != candidate["result_sha256"]:
        raise RuntimeError(f"candidate result hash changed for {candidate['variant_id']}")
    outcome = json.loads(result_bytes)["outcome"]
    scores.append(
        {
            "variant_id": candidate["variant_id"],
            "metrics": {
                "lens-discrimination": int(outcome.get("classification_count", 0)),
                "grounded-verdicts": int(outcome.get("grounded_count", 0)),
                "actionable-handoffs": int(outcome.get("actionable_quote_count", 0)),
                "invalid-quote-refusal": int(bool(outcome.get("invalid_quote_refused"))),
            },
        }
    )
Path(sys.argv[2]).write_text(
    json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\n",
    encoding="utf-8",
)
