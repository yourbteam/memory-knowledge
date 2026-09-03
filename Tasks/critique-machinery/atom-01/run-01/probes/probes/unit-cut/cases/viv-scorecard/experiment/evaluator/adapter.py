#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
scores = []
for candidate in request["candidates"]:
    outcome = candidate["outcome"]
    scores.append(
        {
            "variant_id": candidate["variant_id"],
            "metrics": {
                "boundary-correctness": int(outcome["correct"]),
                "territory-completeness": int(outcome["territory_complete"]),
                "judgeability": float(outcome["judgeable_ratio"]),
                "payload-grounding": float(outcome["payload_grounding_ratio"]),
            },
        }
    )
Path(sys.argv[2]).write_text(
    json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\n",
    encoding="utf-8",
)
