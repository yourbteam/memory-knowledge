from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
CASES = ROOT / "Tasks/critique-machinery/evidence/cases/atom-01"


def load_module():
    spec = importlib.util.spec_from_file_location("critique_machinery", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_real_pages_build_exact_fixed_lens_matrix(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    for case, key in (
        ("btm-roadmap", "context.up.cd_s_002.tactical_roadmap"),
        ("viv-scorecard", "context.up.cd_s_002.measurement_framework"),
    ):
        source = CASES / case
        work = repo / "Tasks" / case
        status, manifest = module.open_run(source / "page.md", source / "state.json", key, work)
        assert status == "opened"
        matrix = json.loads((work / "matrix.json").read_text())
        assert matrix["lenses"] == list(module.LENSES)
        assert len(matrix["cells"]) == len(manifest["units"]) * len(module.LENSES)
        assert module.matrix_status(work)["status"] == "partial"


def test_every_reporting_route_refuses_partial_matrix(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    source = CASES / "btm-roadmap"
    work = repo / "Tasks" / "run"
    module.open_run(
        source / "page.md",
        source / "state.json",
        "context.up.cd_s_002.tactical_roadmap",
        work,
    )
    matrix = json.loads((work / "matrix.json").read_text())
    matrix["cells"][0]["status"] = "judged"
    (work / "matrix.json").write_bytes(module.canonical(matrix))
    status = module.matrix_status(work)
    assert status["status"] == "partial"
    assert status["unjudged_count"] == status["cell_count"] - 1
    for route in ("cell", "report", "document"):
        with pytest.raises(module.Refusal, match="matrix cells are unjudged"):
            module.reporting_route(work, route, matrix["cells"][0]["cell_id"])
