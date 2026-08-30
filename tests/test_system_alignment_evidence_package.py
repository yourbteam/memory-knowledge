from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/system-alignment-assessment-machinery/scripts/evidence_package.py"


def module():
    spec = importlib.util.spec_from_file_location("evidence_package", SCRIPT)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules["evidence_package"] = value
    spec.loader.exec_module(value)
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path: Path, *, executable: bool = True) -> dict:
    source = tmp_path / "source.txt"
    source.write_text("Observed total must equal reference total.\n")
    frozen = tmp_path / "input.json"
    frozen.write_text('{"period":"2026-07-16/2026-07-31"}\n')
    adapter = tmp_path / "adapter.py"
    adapter.write_text("# captured adapter identity\n")
    runner = {"adapter": {"path": str(adapter), "sha256": sha(adapter)}, "command": ["{python}", "{adapter}", "{frozen-input}", "{result-path}", "{telemetry-path}"]}
    cases = [{"case_id": "period", "sequence": 1, "frozen_input": {"path": str(frozen), "sha256": sha(frozen)}, "actual": runner, "reference": runner}] if executable else []
    return {"schema_version": 1, "package_id": "standalone-check", "purpose": "Compare an observed value with its reference.", "sources": [{"path": str(source), "sha256": sha(source)}], "subjects": [{"subject_id": "total", "sequence": 1, "label": "Total", "intent": "Observed equals reference.", "supporting_evidence": [{"path": str(source), "sha256": sha(source)}], "validation_cases": cases}]}


def test_executable_neutral_package_round_trips(tmp_path: Path):
    mod = module()
    value = mod.admit(fixture(tmp_path))
    assert value["status"] == "assessment-ready"
    output = tmp_path / "package.json"
    mod.write_once(value, output)
    assert mod.verify(output) == value


def test_public_cli_creates_and_verifies_package(tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(fixture(tmp_path), indent=2, sort_keys=True) + "\n")
    output = tmp_path / "package.json"
    created = subprocess.run(
        [sys.executable, str(SCRIPT), "create", "--spec", str(spec_path), "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    verified = subprocess.run(
        [sys.executable, str(SCRIPT), "verify", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert verified.returncode == 0, verified.stderr


def test_static_only_subject_cannot_claim_assessment_ready(tmp_path: Path):
    mod = module()
    with pytest.raises(mod.EvidencePackageError, match="at least one runnable actual/reference case"):
        mod.admit(fixture(tmp_path, executable=False))


def test_changed_frozen_input_refuses_fresh_verification(tmp_path: Path):
    mod = module()
    spec = fixture(tmp_path)
    value = mod.admit(spec)
    output = tmp_path / "package.json"
    mod.write_once(value, output)
    Path(spec["subjects"][0]["validation_cases"][0]["frozen_input"]["path"]).write_text("changed\n")
    with pytest.raises(mod.EvidencePackageError, match="bytes changed"):
        mod.verify(output)
