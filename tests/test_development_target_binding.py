from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/info-intake-machinery/scripts/development_target_binding.py"


def _module():
    spec = importlib.util.spec_from_file_location("development_target_binding", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], text=True, capture_output=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    intake = tmp_path / "intake"
    intake.mkdir()
    (intake / "intake-state.json").write_text(
        json.dumps({"intake_id": "intake-real", "phase": "terminal"}) + "\n"
    )
    (intake / "assessment.json").write_text(
        json.dumps({"intake_id": "intake-real", "status": "terminal"}) + "\n"
    )
    repo = tmp_path / "product"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "Tests")
    surface = repo / "src/dashboard.py"
    surface.parent.mkdir()
    surface.write_text("DASHBOARD = True\n")
    _git(repo, "add", "src/dashboard.py")
    _git(repo, "commit", "-q", "-m", "baseline")
    return intake, repo


def test_build_and_verify_binds_generic_intake_artifacts_to_clean_target(tmp_path: Path) -> None:
    module = _module()
    intake, repo = _fixture(tmp_path)
    output = tmp_path / "target-binding.json"

    binding = module.build_binding(
        intake_root=intake,
        intake_id="intake-real",
        evidence_artifacts=["intake-state.json", "assessment.json"],
        repository=repo,
        surface_paths=["src/dashboard.py"],
    )
    module.write_binding(binding, output)

    assert module.verify_binding(output) == binding
    assert [item["path"] for item in binding["intake"]["evidence_artifacts"]] == [
        "intake-state.json",
        "assessment.json",
    ]
    assert binding["target"]["surface_files"][0]["path"] == "src/dashboard.py"
    assert binding["target"]["worktree"] == "clean"


def test_wrong_repository_surface_is_refused(tmp_path: Path) -> None:
    module = _module()
    intake, repo = _fixture(tmp_path)

    with pytest.raises(module.BindingError, match="missing or not regular"):
        module.build_binding(
            intake_root=intake,
            intake_id="intake-real",
            evidence_artifacts=["intake-state.json"],
            repository=repo,
            surface_paths=["src/not-dashboard.py"],
        )


def test_changed_evidence_fails_live_verification_without_overwriting_binding(
    tmp_path: Path,
) -> None:
    module = _module()
    intake, repo = _fixture(tmp_path)
    output = tmp_path / "target-binding.json"
    binding = module.build_binding(
        intake_root=intake,
        intake_id="intake-real",
        evidence_artifacts=["intake-state.json"],
        repository=repo,
        surface_paths=["src/dashboard.py"],
    )
    module.write_binding(binding, output)
    original = output.read_bytes()
    (intake / "intake-state.json").write_text(
        json.dumps({"intake_id": "intake-real", "phase": "changed"}) + "\n"
    )

    with pytest.raises(module.BindingError, match="changed from the binding"):
        module.verify_binding(output)
    assert output.read_bytes() == original


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    module = _module()
    output = tmp_path / "target-binding.json"
    output.write_text("existing\n")

    with pytest.raises(module.BindingError, match="already exists"):
        module.write_binding({"new": True}, output)
    assert output.read_text() == "existing\n"
