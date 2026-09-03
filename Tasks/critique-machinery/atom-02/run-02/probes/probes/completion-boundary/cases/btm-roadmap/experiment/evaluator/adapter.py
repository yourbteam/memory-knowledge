#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
scores = []
for candidate in request["candidates"]:
    outcome = candidate["outcome"]
    errors = [
        str(outcome.get("route_evidence", {}).get(route, {}).get("error", ""))
        for route in ("cell", "report", "document")
    ]
    actionable = sum(
        "matrix cells are unjudged" in error and "Judge every named unit/lens cell" in error
        for error in errors
    )
    scores.append(
        {
            "variant_id": candidate["variant_id"],
            "metrics": {
                "open-correctness": int(outcome["correct"]),
                "matrix-shape": int(outcome["matrix_shape_correct"]),
                "partial-visibility": int(outcome["partial_visible"]),
                "closed-result-routes": int(outcome["reporting_routes_refused"]),
                "actionable-refusals": actionable,
            },
        }
    )
Path(sys.argv[2]).write_text(
    json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\n",
    encoding="utf-8",
)
