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


def test_judgment_requires_fixed_verdict_and_exact_unit_quote(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    source = CASES / "btm-roadmap"
    work = repo / "Tasks" / "run"
    _, manifest = module.open_run(
        source / "page.md",
        source / "state.json",
        "context.up.cd_s_002.tactical_roadmap",
        work,
    )
    unit = next(unit for unit in manifest["units"] if len(module.collapsed(unit["text"])) >= 25)
    cell_id = f"{unit['unit_id']}::buyer-read"
    with pytest.raises(module.Refusal, match="choose exactly one"):
        module.record_judgment(work, cell_id, "looks-good", unit["text"][:80])
    with pytest.raises(module.Refusal, match="not present"):
        module.record_judgment(work, cell_id, "revise", "invented evidence that is absent from this real unit")
    quote = module.collapsed(unit["text"])[5:90]
    recorded = module.record_judgment(work, cell_id, "revise", quote.replace(" ", "\n", 1))
    assert recorded["quote"] == quote
    assert recorded["verdict"] == "revise"
    with pytest.raises(module.Refusal, match="already has"):
        module.record_judgment(work, cell_id, "clear", quote)
