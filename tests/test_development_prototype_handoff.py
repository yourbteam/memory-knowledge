from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/info-intake-machinery/scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[name] = module
    return module


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _fixture(tmp_path: Path):
    target = _load("development_target_binding")
    objective_mod = _load("development_objective")
    handoff = _load("development_prototype_handoff")
    intake = tmp_path / "intake"; intake.mkdir()
    (intake / "state.json").write_text('{"intake_id":"intake-1"}\n')
    assessment = intake / "assessment.json"
    assessment.write_text(json.dumps({"intake_id":"intake-1","claims":[{"claim_id":"claim-1","statement":"Add both inputs.","verdict":"confirmed","packet_sha256":"a"*64,"evidence_pointers":["one"]}]}, sort_keys=True)+"\n")
    repo = tmp_path / "repo"; repo.mkdir(); _git(repo,"init","-q"); _git(repo,"config","user.email","test@example.invalid"); _git(repo,"config","user.name","Test")
    (repo / "logic.py").write_text("value = left\n")
    _git(repo,"add","logic.py"); _git(repo,"commit","-q","-m","baseline")
    binding = target.build_binding(intake_root=intake,intake_id="intake-1",evidence_artifacts=["state.json","assessment.json"],repository=repo,surface_paths=["logic.py"])
    binding_path = intake / "binding.json"; target.write_binding(binding,binding_path)
    selection = {"outcome_id":"sum-inputs","outcome":"Add both inputs.","practical_value":"The total is complete.","reason":"The claim requires it.","claim_ids":["claim-1"]}
    objective = objective_mod.compile_objective(target_binding_path=binding_path,assessment_path=assessment,selection=selection)
    objective_path = intake / "objective.json"; objective_mod.write_objective(objective,objective_path)
    observation = {"verdict":"gap","criterion_ids":["claim-1"],"summary":"Only left is used.","practical_impact":"Totals are understated.","evidence":[{"path":"logic.py","line_start":1,"line_end":1,"quote":"value = left"}]}
    return handoff, objective_path, observation


def test_compile_and_verify_grounded_prototype_zero_handoff(tmp_path: Path) -> None:
    module, objective, observation = _fixture(tmp_path)
    value = module.compile_handoff(objective_path=objective,observation=observation,max_prototypes=4)
    output = tmp_path / "handoff.json"; module.write_handoff(value,output)
    assert module.verify_handoff(output) == value
    assert value["prototype_zero"]["verdict"] == "gap"
    assert value["prototype_envelope"]["authorization_status"] == "proposed"


def test_invented_quote_is_refused(tmp_path: Path) -> None:
    module, objective, observation = _fixture(tmp_path)
    observation["evidence"][0]["quote"] = "invented"
    with pytest.raises(module.HandoffError, match="does not match exact source"):
        module.compile_handoff(objective_path=objective,observation=observation,max_prototypes=4)
