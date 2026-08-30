from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/system-alignment-assessment-machinery/scripts/intake_handoff_adapter.py"
SOURCE_HANDOFF = ROOT / "skills/info-intake-machinery/scripts/source_handoff.py"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def fixture(tmp_path: Path):
    source_handoff = load("test_system_alignment_source_handoff", SOURCE_HANDOFF)
    requester = tmp_path / "requester.json"
    requester.write_text('{"needs":"runtime alignment"}\n')
    request_spec = tmp_path / "request-spec.json"
    write(request_spec, {
        "schema_version": 1,
        "request_id": "alignment-source-1",
        "purpose": "Check observed behavior against the declared reference.",
        "requested_evidence": ["implementation projection"],
        "related_unit_ids": ["total"],
        "requester_path": str(requester),
    })
    request = source_handoff.create_request(request_spec)
    request_path = tmp_path / "request.json"
    source_handoff._write_once(request, request_path, "source request")
    source = tmp_path / "source.py"; source.write_text("print(42)\n")
    projection = tmp_path / "projection.txt"; projection.write_text("The source emits 42.\n")
    ledger = tmp_path / "ledger.jsonl"
    previous = None
    entries = []
    for sequence, payload in enumerate((
        {"request_id": request["request_id"], "source_sha256": sha(source)},
        {"request_id": request["request_id"], "projection_sha256": sha(projection)},
    ), start=1):
        body = {"sequence": sequence, "previous_entry_sha256": previous, **payload}
        entry = {**body, "entry_sha256": source_handoff._sha_bytes(source_handoff._canonical(body))}
        entries.append(entry); previous = entry["entry_sha256"]
    ledger.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in entries))
    return_spec = tmp_path / "return-spec.json"
    write(return_spec, {"schema_version": 1, "evidence_items": [{
        "item_id": "implementation",
        "immutable_source_path": str(source),
        "readable_projection_path": str(projection),
        "intake_ledger_path": str(ledger),
        "qualification": "readable_projection_complete",
    }]})
    returned = source_handoff.create_return(request_path, return_spec)
    handoff_path = tmp_path / "source-return.json"
    source_handoff._write_once(returned, handoff_path, "source return package")
    frozen = tmp_path / "input.json"; frozen.write_text('{"period":"fixed"}\n')
    adapter = tmp_path / "runner.py"; adapter.write_text("# runner identity\n")
    runner = {"adapter": {"path": str(adapter), "sha256": sha(adapter)}, "command": [
        "{python}", "{adapter}", "{frozen-input}", "{result-path}", "{telemetry-path}",
    ]}
    case = {"case_id": "fixed-period", "sequence": 1,
            "frozen_input": {"path": str(frozen), "sha256": sha(frozen)},
            "actual": runner, "reference": runner}
    return handoff_path, case, projection


def bindings(tmp_path: Path, cases: list[dict]) -> Path:
    path = tmp_path / ("bindings-ready.json" if cases else "bindings-gap.json")
    write(path, {"schema_version": 1, "package_id": "intake-fed-check", "subjects": [{
        "subject_id": "total", "sequence": 1, "label": "Total",
        "intent": "Observed total equals the reference total.",
        "evidence_item_ids": ["implementation"], "validation_cases": cases,
    }]})
    return path


def test_complete_handoff_becomes_same_neutral_runtime_package(tmp_path: Path):
    mod = load("intake_handoff_adapter_ready", SCRIPT)
    handoff, case, projection = fixture(tmp_path)
    value = mod.adapt(handoff, bindings(tmp_path, [case]))
    assert value["status"] == "assessment-ready"
    assert value["artifact_type"] == "system-alignment-evidence-package"
    assert any(item["path"] == str(projection) for item in value["subjects"][0]["supporting_evidence"])


def test_projection_only_handoff_returns_precise_runtime_gap(tmp_path: Path):
    mod = load("intake_handoff_adapter_gap", SCRIPT)
    handoff, _, _ = fixture(tmp_path)
    binding = bindings(tmp_path, [])
    value = mod.adapt(handoff, binding)
    assert value["status"] == "validation-bindings-required"
    assert value["requests"][0]["subject_id"] == "total"
    assert "runnable actual and reference adapters" in value["requests"][0]["request"]
    output = tmp_path / "gaps.json"
    mod._write_once(value, output)
    assert mod.verify(output) == value


def test_unknown_intake_evidence_identity_is_refused(tmp_path: Path):
    mod = load("intake_handoff_adapter_unknown", SCRIPT)
    handoff, case, _ = fixture(tmp_path)
    path = bindings(tmp_path, [case])
    value = json.loads(path.read_text())
    value["subjects"][0]["evidence_item_ids"] = ["invented"]
    write(path, value)
    try:
        mod.adapt(handoff, path)
    except mod.IntakeHandoffAdapterError as error:
        assert "unknown Info Intake evidence items" in str(error)
    else:
        raise AssertionError("invented evidence identity was accepted")
