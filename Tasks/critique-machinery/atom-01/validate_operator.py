#!/usr/bin/env python3
"""Exercise the promoted Atom 1 CLI and preserve its exact process evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
CASES = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01"
OUT = Path(__file__).resolve().parent / "operator-validation"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(page: Path, state: Path, key: str, work: Path) -> dict[str, object]:
    command = [
        sys.executable,
        str(SCRIPT),
        "open",
        "--page",
        str(page),
        "--payload",
        str(state),
        "--key",
        key,
        "--work",
        str(work),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing existing validation directory: {OUT}")
    OUT.mkdir(parents=True)
    case_specs = (
        ("btm-roadmap", "context.up.cd_s_002.tactical_roadmap", "opened"),
        ("viv-scorecard", "context.up.cd_s_002.measurement_framework", "opened"),
        ("btm-roadmap-wrong-payload", "context.up.cd_s_002.measurement_framework", "refused"),
    )
    evidence: dict[str, dict[str, object]] = {}
    for case_id, key, expected in case_specs:
        source = CASES / case_id
        work = OUT / "runs" / case_id
        first = invoke(source / "page.md", source / "state.json", key, work)
        actual = "opened" if first["returncode"] == 0 else "refused"
        record: dict[str, object] = {"case_id": case_id, "expected": expected, "actual": actual, "first": first}
        if expected == "opened":
            manifest = work / "unit-manifest.json"
            reopen = invoke(source / "page.md", source / "state.json", key, work)
            record.update(
                {
                    "manifest_path": str(manifest),
                    "manifest_sha256": sha(manifest),
                    "reopen": reopen,
                    "satisfied": actual == expected and '"status": "reopened"' in str(reopen["stdout"]),
                }
            )
        else:
            record["satisfied"] = actual == expected and "page/payload mismatch" in str(first["stderr"])
        evidence[case_id] = record
    guard = invoke(
        CASES / "btm-roadmap/page.md",
        CASES / "btm-roadmap/state.json",
        "context.up.cd_s_002.tactical_roadmap",
        Path("/private/tmp/critique-machinery-outside-repo"),
    )
    incompatible = invoke(
        CASES / "viv-scorecard/page.md",
        CASES / "viv-scorecard/state.json",
        "context.up.cd_s_002.measurement_framework",
        OUT / "runs/btm-roadmap",
    )
    evidence["guards"] = {
        "repo_guard": guard,
        "immutable_reopen": incompatible,
        "satisfied": (
            guard["returncode"] == 2
            and "not nested inside a Git repository" in str(guard["stderr"])
            and incompatible["returncode"] == 2
            and "already contains a different unit-manifest.json" in str(incompatible["stderr"])
        ),
    }
    for case_id in ("btm-roadmap", "viv-scorecard", "btm-roadmap-wrong-payload"):
        path = OUT / f"{case_id}.json"
        path.write_text(json.dumps(evidence[case_id], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "guards.json").write_text(json.dumps(evidence["guards"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not all(bool(item["satisfied"]) for item in evidence.values()):
        raise SystemExit("operator validation failed; inspect operator-validation/*.json")
    print(json.dumps({"status": "passed", "cases": 3, "guards": 2}, sort_keys=True))


if __name__ == "__main__":
    main()
