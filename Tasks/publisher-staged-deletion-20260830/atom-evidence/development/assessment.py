import json, sys
from pathlib import Path

question = json.loads(Path(sys.argv[1]).read_text())
outcome = question["execution_result"]["outcome"]
correct = bool(outcome.get("correct"))
response = {
    "case_id": question["case_id"],
    "verdict": "satisfied" if correct else "not-satisfied",
    "reason": "The assembled publisher classified the captured manifest path correctly." if correct else "The assembled publisher misclassified the captured manifest path.",
    "evidence_pointers": ["execution-result"],
}
Path(sys.argv[2]).write_text(json.dumps(response, sort_keys=True) + "\n")
