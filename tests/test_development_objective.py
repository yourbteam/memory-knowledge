from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "skills/info-intake-machinery/scripts"


def _module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _fixture(tmp_path: Path):
    target = _module("development_target_binding")
    sys.modules["development_target_binding"] = target
    objective = _module("development_objective")
    intake = tmp_path / "intake"
    intake.mkdir()
    (intake / "intake-state.json").write_text('{"intake_id":"intake-1"}\n')
    assessment = intake / "assessment.json"
    assessment.write_text(json.dumps({
        "intake_id": "intake-1",
        "claims": [
            {"claim_id": "claim-1", "statement": "Use the grounded value.", "verdict": "confirmed", "packet_sha256": "a" * 64, "evidence_pointers": ["source-1"]},
            {"claim_id": "claim-2", "statement": "Do not use the rejected value.", "verdict": "contradicted", "packet_sha256": "b" * 64, "evidence_pointers": ["source-2"]},
        ],
    }, sort_keys=True) + "\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "surface.py").write_text("VALUE = 1\n")
    _git(repo, "add", "surface.py")
    _git(repo, "commit", "-q", "-m", "baseline")
    binding = target.build_binding(
        intake_root=intake,
        intake_id="intake-1",
        evidence_artifacts=["intake-state.json", "assessment.json"],
        repository=repo,
        surface_paths=["surface.py"],
    )
    binding_path = intake / "target-binding.json"
    target.write_binding(binding, binding_path)
    selection = {
        "outcome_id": "grounded-dashboard",
        "outcome": "Implement the grounded dashboard value.",
        "practical_value": "The displayed value follows source evidence.",
        "reason": "The confirmed claim defines the required behavior.",
        "claim_ids": ["claim-1"],
    }
    return objective, binding_path, assessment, selection


def test_compiler_reconstructs_criteria_from_bound_confirmed_claims(tmp_path: Path) -> None:
    module, binding, assessment, selection = _fixture(tmp_path)
    value = module.compile_objective(
        target_binding_path=binding,
        assessment_path=assessment,
        selection=selection,
    )
    output = tmp_path / "objective.json"
    module.write_objective(value, output)

    assert module.verify_objective(output) == value
    assert value["criteria"] == [{
        "sequence": 1,
        "claim_id": "claim-1",
        "criterion": "Use the grounded value.",
        "packet_sha256": "a" * 64,
        "evidence_pointers": ["source-1"],
    }]


@pytest.mark.parametrize("claim_id, message", [
    ("unknown", "unknown claim"),
    ("claim-2", "without confirmed evidence"),
])
def test_unknown_or_unconfirmed_model_selection_is_refused(
    tmp_path: Path, claim_id: str, message: str
) -> None:
    module, binding, assessment, selection = _fixture(tmp_path)
    selection["claim_ids"] = [claim_id]

    with pytest.raises(module.ObjectiveError, match=message):
        module.compile_objective(
            target_binding_path=binding,
            assessment_path=assessment,
            selection=selection,
        )
