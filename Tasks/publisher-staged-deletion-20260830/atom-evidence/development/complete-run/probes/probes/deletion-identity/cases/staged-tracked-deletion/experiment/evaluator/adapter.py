import json, sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text())
scores = []
for candidate in request["candidates"]:
    correct = bool(candidate["outcome"].get("correct"))
    scores.append({
        "variant_id": candidate["variant_id"],
        "metrics": {
            "boundary-correctness": int(correct),
            "deletion-specificity": int(correct and candidate["variant_id"] == "diff-deletion-membership"),
        },
    })
Path(sys.argv[2]).write_text(json.dumps({"schema_version": 1, "scores": scores}, sort_keys=True) + "\n")
