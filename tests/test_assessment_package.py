from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"skills/info-intake-machinery/scripts/assessment_package.py"
def _module():
    spec=importlib.util.spec_from_file_location("assessment_package_test",SCRIPT); module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module); return module
def _write(path,value): path.write_text(json.dumps(value,sort_keys=True)+"\n"); return path
def _fixture(tmp_path):
    module=_module()
    for contract in (module.charter_contract,module.evidence_contract,module.sufficiency_contract,module.verdict_contract,module.request_contract): contract.verify=lambda _path:{}
    charter=_write(tmp_path/"charter.json",{"assessment":{"purpose":"Are values correct?","decision":"Fix mismatches."}}); charter_value=json.loads(charter.read_text())
    evidence=_write(tmp_path/"evidence.json",{"unit_count":1,"units":[{"unit_id":"unit-1","label":"Total","subject":{"identity":"field-1","kind":"metric"}}]}); evidence_value=json.loads(evidence.read_text())
    sufficiency=_write(tmp_path/"sufficiency.json",{"charter_source":module._ref(charter,charter.read_bytes(),charter_value),"evidence_source":module._ref(evidence,evidence.read_bytes(),evidence_value),"unit_count":1,"gap_count":0,"gaps":[]}); sufficiency_value=json.loads(sufficiency.read_text())
    verdicts=_write(tmp_path/"verdicts.json",{"evidence_source":module._ref(evidence,evidence.read_bytes(),evidence_value),"sufficiency_source":module._ref(sufficiency,sufficiency.read_bytes(),sufficiency_value),"unit_count":1,"verdict_counts":{"aligned":0,"misaligned":1,"incomplete":0},"units":[{"unit_id":"unit-1","verdict":"misaligned","measure":"Expected 10, observed 11.","reason":"Difference 1.","evidence_ids":["criterion","observation","context"],"gap_ids":[],"missing_evidence":[]}]});
    requests=_write(tmp_path/"requests.json",{"sufficiency_source":module._ref(sufficiency,sufficiency.read_bytes(),sufficiency_value),"request_count":0,"covered_gap_ids":[],"requests":[]})
    return module,(charter,evidence,sufficiency,verdicts,requests)
def test_builds_verified_downstream_handoff(tmp_path):
    module,paths=_fixture(tmp_path); result=module.run(*paths,tmp_path/"work")
    assert result["summary"]=={"unit_count":1,"verdict_counts":{"aligned":0,"misaligned":1,"incomplete":0},"confirmed_misalignment_count":1,"incomplete_unit_count":0,"gap_count":0,"source_request_count":0}
    assert result["prototype_handoff"]["status"]=="ready"
    assert result["prototype_handoff"]["captured_cases"][0]["measure"]=="Expected 10, observed 11."
    assert result["experiment_handoff"]["candidate_case_ids"]==["assessment-unit-1"]
    assert module.verify(tmp_path/"work/assessment-package.json")==result
    assert len((tmp_path/"work/ledger.jsonl").read_text().splitlines())==2
def test_rejects_substituted_request_source(tmp_path):
    module,paths=_fixture(tmp_path); requests=paths[-1]; value=json.loads(requests.read_text()); value["sufficiency_source"]["sha256"]="wrong"; requests.write_text(json.dumps(value)+"\n")
    with pytest.raises(module.AssessmentPackageError,match="request sufficiency source"): module.run(*paths,tmp_path/"work")
