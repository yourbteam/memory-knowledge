#!/usr/bin/env python3
"""Validate both managed client projections through their installed public operator paths."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = Path(__file__).resolve().parent
SOURCE = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01/btm-roadmap"
OUT = ATOM / "installed-validation"
REASON = "UP supplies no roadmap-shaped benchmark"
INSTALLS = {
    "codex": Path("/Users/kamenkamenov/.codex/skills/critique-machinery"),
    "claude": Path("/Users/kamenkamenov/.claude/skills/critique-machinery"),
}


def tree_hash(path: Path) -> str:
    value = hashlib.sha256()
    for item in sorted(
        candidate for candidate in path.rglob("*")
        if candidate.is_file() and "__pycache__" not in candidate.parts and candidate.suffix not in {".pyc", ".pyo"}
    ):
        value.update(item.relative_to(path).as_posix().encode() + b"\0")
        value.update(item.read_bytes())
    return value.hexdigest()


def call(skill: Path, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["python3", "scripts/critique.py", *args], cwd=skill, text=True, capture_output=True)
    if ok and result.returncode != 0:
        raise SystemExit(result.stderr)
    if not ok and result.returncode == 0:
        raise SystemExit(f"expected refusal from {skill}: {args}")
    return result


if OUT.exists():
    raise SystemExit(f"refusing to replace installed validation evidence: {OUT}")
OUT.mkdir(parents=True)
manifest = json.loads((ROOT / "working-agreement/client-skill-projections.json").read_text())
expected = manifest["entries"]["critique-machinery"]["projected_tree_sha256_by_client"]
clients = []
for client, skill in INSTALLS.items():
    client_out = OUT / client
    client_out.mkdir()
    work = client_out / "run"
    opened = json.loads(call(
        skill,
        "open", "--page", str(SOURCE / "page.md"),
        "--payload", f"{SOURCE / 'state.json'}#context.up.cd_s_002.tactical_roadmap",
        "--work", str(work), "--no-reference", REASON,
    ).stdout)
    status = json.loads(call(skill, "status", "--work", str(work)).stdout)
    matrix = json.loads((work / "matrix.json").read_text())
    benchmark = next(cell for cell in matrix["cells"] if cell["lens"] == "benchmark-vs-reference")
    read_cell = json.loads(call(skill, "read-cell", "--work", str(work), "--id", benchmark["cell_id"]).stdout)
    document = call(skill, "document", "--work", str(work), ok=False)
    policy = json.loads((skill / "client-model-policy.json").read_text())
    actual_hash = tree_hash(skill)
    record = {
        "client": client,
        "installed_path": str(skill),
        "installed_tree_sha256": actual_hash,
        "projected_tree_sha256": expected[client],
        "parity_state": "MATCH" if actual_hash == expected[client] else "DRIFT",
        "required_runtime": policy["required_runtime"],
        "fail_closed": policy["fail_closed"],
        "opened": opened,
        "status": status,
        "benchmark_read_cell": read_cell,
        "document_refusal": document.stderr.strip(),
        "reader_evidence_exists": (work / "reader-evidence").exists(),
    }
    checks = [
        record["parity_state"] == "MATCH",
        policy["required_runtime"] == ("codex exec" if client == "codex" else "claude -p"),
        policy["fail_closed"] is True,
        status["cell_count"] == 175,
        status["unjudged_count"] == 150,
        status["benchmark_no_reference_count"] == 25,
        status["benchmark_no_reference_reason"] == REASON,
        read_cell["status"] == "not-applicable",
        "150 matrix cells are unjudged" in document.stderr,
        not record["reader_evidence_exists"],
    ]
    record["status"] = "passed" if all(checks) else "failed"
    (client_out / "validation.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    clients.append(record)

summary = {"status": "passed" if all(item["status"] == "passed" for item in clients) else "failed", "model_calls": 0, "clients": clients}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
if summary["status"] != "passed":
    raise SystemExit(json.dumps(summary, sort_keys=True))
print(json.dumps({"status": "passed", "clients": [item["client"] for item in clients]}, sort_keys=True))
