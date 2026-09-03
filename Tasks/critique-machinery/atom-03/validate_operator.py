#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = Path(__file__).resolve().parent
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
OUT = ATOM / "operator-validation"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    summaries = []
    for case_id in ("stale-door-red", "stale-door-green", "calendar-red", "calendar-green"):
        case_root = ATOM / "cases" / case_id
        case = json.loads((case_root / "case.json").read_text(encoding="utf-8"))
        work = OUT / "runs" / case_id
        opened = run(
            "open", "--page", str(case_root / "page.md"), "--payload", str(case_root / "state.json"),
            "--key", case["payload_key"], "--work", str(work),
        )
        if opened.returncode != 0:
            raise RuntimeError(opened.stderr)
        evidence = json.loads(
            (
                ATOM / "run-06/probes/probes/verdict-contract/cases" / case_id
                / "experiment/variants/variation-2/result.json"
            ).read_text(encoding="utf-8")
        )["outcome"]
        first = evidence["judgments"][0]
        rejected = run(
            "judge", "--work", str(work), "--id", first["cell_id"], "--verdict", "revise",
            "--quote", "fabricated words absent from the immutable unit",
        )
        if rejected.returncode != 2 or "not present in unit" not in rejected.stderr:
            raise RuntimeError(f"invalid quote did not refuse for {case_id}: {rejected.stdout} {rejected.stderr}")
        recorded = []
        for judgment in evidence["judgments"]:
            completed = run(
                "judge", "--work", str(work), "--id", judgment["cell_id"],
                "--verdict", judgment["verdict"], "--quote", judgment["quote"],
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr)
            recorded.append(json.loads(completed.stdout))
        summary = {
            "case_id": case_id,
            "opened": json.loads(opened.stdout),
            "invalid_quote_refused": True,
            "invalid_quote_error": rejected.stderr.strip(),
            "judgment_count": len(recorded),
            "expected_judgment_count": len(case["applicable_lenses"]),
            "verdicts": [item["verdict"] for item in recorded],
            "quotes_grounded": all(item.get("quote") and item.get("quote_sha256") for item in recorded),
            "source_model_evidence": str(
                Path("Tasks/critique-machinery/atom-03/run-06/probes/probes/verdict-contract/cases")
                / case_id / "experiment/variants/variation-2/result.json"
            ),
        }
        (OUT / f"{case_id}.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summaries.append(summary)
    (OUT / "summary.json").write_text(
        json.dumps({"status": "passed", "cases": summaries}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
