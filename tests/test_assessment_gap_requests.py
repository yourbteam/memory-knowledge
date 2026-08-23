from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"skills/info-intake-machinery/scripts/assessment_gap_requests.py"

def _module():
    spec=importlib.util.spec_from_file_location("assessment_gap_requests_test",SCRIPT); module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module); return module

def _fixture(tmp_path):
    module=_module(); gaps=[]
    for index,role in enumerate(("observation","criterion","observation","context"),1):
        gaps.append({"gap_id":f"gap-{index:06d}","unit_id":f"unit-{index}","obligation_id":f"unit-{index}:{role}","missing_evidence":f"missing {index}"})
    source=tmp_path/"sufficiency.json"; source.write_text(json.dumps({"gaps":gaps,"artifact_sha256":"source"},sort_keys=True)+"\n")
    module.sufficiency_contract.verify=lambda _path:{}
    return module,source

def test_groups_every_gap_into_three_operator_requests(tmp_path):
    module,source=_fixture(tmp_path)
    result=module.run(source,tmp_path/"work")
    assert result["gap_count"]==4
    assert result["request_count"]==3
    assert [item["role"] for item in result["requests"]]==["criterion","observation","context"]
    assert sorted(result["covered_gap_ids"])==[f"gap-{index:06d}" for index in range(1,5)]
    assert module.verify(tmp_path/"work/requests.json")==result
    assert len((tmp_path/"work/ledger.jsonl").read_text().splitlines())==2

def test_rerun_is_idempotent_but_source_change_is_refused(tmp_path):
    module,source=_fixture(tmp_path); work=tmp_path/"work"
    first=module.run(source,work); assert module.run(source,work)==first
    source.write_text("{}\n")
    with pytest.raises(module.AssessmentGapRequestError): module.run(source,work)

def test_verifier_rejects_missing_gap(tmp_path):
    module,source=_fixture(tmp_path); path=tmp_path/"work/requests.json"; module.run(source,path.parent)
    value=json.loads(path.read_text()); value["requests"][1]["gap_ids"].pop(); value["requests"][1]["missing_evidence"].pop(); path.write_text(json.dumps(value)+"\n")
    with pytest.raises(module.AssessmentGapRequestError,match="missing=.*gap-000003"): module.verify(path)
