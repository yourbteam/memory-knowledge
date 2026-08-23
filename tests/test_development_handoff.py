from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/info-intake-machinery/scripts/development_handoff.py"
SCRIPTS = SCRIPT.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _module():
    _load("development_target_binding")
    _load("development_objective")
    _load("development_prototype_handoff")
    _load("development_target_set")
    return _load("development_handoff")


def test_case_lineage_requires_exact_prototype_zero_criterion(tmp_path: Path) -> None:
    module = _module()
    case = tmp_path / "case.json"
    case.write_text('{"case_id":"works","source_criterion_id":"claim-1"}\n')
    manifest = {"atomic_step": {"captured_cases": [{
        "id": "works", "kind": "success", "source": str(case),
        "sha256": module._sha(case),
    }, {
        "id": "refuses", "kind": "failure", "source": str(case),
        "sha256": module._sha(case),
    }]}}

    with pytest.raises(module.DevelopmentHandoffError, match="identity changed"):
        module._validate_case_lineage(manifest, {"claim-1"})


def test_case_lineage_refuses_unselected_claim(tmp_path: Path) -> None:
    module = _module()
    success = tmp_path / "success.json"; failure = tmp_path / "failure.json"
    success.write_text('{"case_id":"works","source_criterion_id":"claim-other"}\n')
    failure.write_text('{"case_id":"refuses","source_criterion_id":"claim-other"}\n')
    manifest = {"atomic_step": {"captured_cases": [
        {"id":"works","kind":"success","source":str(success),"sha256":module._sha(success)},
        {"id":"refuses","kind":"failure","source":str(failure),"sha256":module._sha(failure)},
    ]}}
    with pytest.raises(module.DevelopmentHandoffError, match="not grounded"):
        module._validate_case_lineage(manifest, {"claim-1"})
