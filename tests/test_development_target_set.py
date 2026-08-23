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
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    sys.modules[name] = module
    return module


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _repo(root: Path, name: str) -> Path:
    repo = root / name; repo.mkdir(); _git(repo,"init","-q"); _git(repo,"config","user.email","test@example.invalid"); _git(repo,"config","user.name","Test")
    (repo / "surface.txt").write_text(name + "\n"); _git(repo,"add","surface.txt"); _git(repo,"commit","-q","-m","baseline")
    return repo


def test_exact_two_repository_set_round_trips(tmp_path: Path) -> None:
    binding_mod = _load("development_target_binding"); target_set = _load("development_target_set")
    intake = tmp_path / "intake"; intake.mkdir(); (intake / "state.json").write_text('{"intake_id":"one"}\n')
    paths = []
    for name in ("portal", "api"):
        value = binding_mod.build_binding(intake_root=intake,intake_id="one",evidence_artifacts=["state.json"],repository=_repo(tmp_path,name),surface_paths=["surface.txt"])
        path = intake / f"{name}.json"; binding_mod.write_binding(value,path); paths.append(path)
    value = target_set.compose_target_set(paths); output = intake / "set.json"; target_set.write_target_set(value,output)
    assert target_set.verify_target_set(output) == value
    assert [item["repository"].rsplit("/", 1)[-1] for item in value["members"]] == ["portal", "api"]


def test_duplicate_repository_is_refused(tmp_path: Path) -> None:
    binding_mod = _load("development_target_binding"); target_set = _load("development_target_set")
    intake = tmp_path / "intake"; intake.mkdir(); (intake / "state.json").write_text('{"intake_id":"one"}\n'); repo = _repo(tmp_path,"repo")
    value = binding_mod.build_binding(intake_root=intake,intake_id="one",evidence_artifacts=["state.json"],repository=repo,surface_paths=["surface.txt"])
    first = intake / "first.json"; second = intake / "second.json"; binding_mod.write_binding(value,first); binding_mod.write_binding(value,second)
    with pytest.raises(target_set.TargetSetError, match="repeats repository"):
        target_set.compose_target_set([first, second])
