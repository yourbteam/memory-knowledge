from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/info-intake-machinery/scripts/source_handoff.py"


def _module():
    spec = importlib.util.spec_from_file_location("source_handoff", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["source_handoff"] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ledger(path: Path, request_id: str, source_sha: str, projection_sha: str) -> None:
    module = _module()
    entries = []
    previous = None
    for sequence, payload in enumerate((
        {"event": "source_bound", "request_id": request_id, "source_sha256": source_sha},
        {"event": "projection_bound", "request_id": request_id, "projection_sha256": projection_sha},
    ), start=1):
        body = {"sequence": sequence, "previous_entry_sha256": previous, **payload}
        entry = {**body, "entry_sha256": module._sha_bytes(module._canonical(body))}
        previous = entry["entry_sha256"]
        entries.append(entry)
    path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in entries), encoding="utf-8")


def _fixture(tmp_path: Path):
    module = _module()
    requester = tmp_path / "assessment-package.json"
    requester.write_text('{"status":"needs-source"}\n', encoding="utf-8")
    request_spec = tmp_path / "request-spec.json"
    _write_json(request_spec, {
        "schema_version": 1,
        "request_id": "request-000001",
        "purpose": "Provide implementation evidence for the current display value.",
        "requested_evidence": ["screen binding", "API envelope assembly"],
        "related_unit_ids": ["unit-000001"],
        "requester_path": str(requester),
    })
    request = module.create_request(request_spec)
    request_path = tmp_path / "source-request.json"
    module._write_once(request, request_path, "source request")
    source = tmp_path / "source.cs"
    projection = tmp_path / "projection.txt"
    source.write_bytes(b"public decimal CurrentValue => 42m;\n")
    projection.write_text("public decimal CurrentValue => 42m;\n", encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"
    _ledger(ledger, request["request_id"], _sha(source), _sha(projection))
    return module, requester, request_spec, request_path, source, projection, ledger


def test_real_request_return_round_trip_has_no_semantic_verdict(tmp_path: Path) -> None:
    module, _, _, request_path, source, projection, ledger = _fixture(tmp_path)
    spec = tmp_path / "return-spec.json"
    _write_json(spec, {
        "schema_version": 1,
        "evidence_items": [{
            "item_id": "evidence-000001",
            "immutable_source_path": str(source),
            "readable_projection_path": str(projection),
            "intake_ledger_path": str(ledger),
            "qualification": "readable_projection_complete",
        }],
    })

    package = module.create_return(request_path, spec)
    output = tmp_path / "source-return.json"
    module._write_once(package, output, "source return package")

    assert module.verify_return(output) == package
    assert package["request"]["request_id"] == "request-000001"
    assert package["evidence_items"][0]["immutable_source"]["sha256"] == _sha(source)
    assert package["evidence_items"][0]["readable_projection"]["sha256"] == _sha(projection)
    assert not module.FORBIDDEN_SEMANTIC_FIELDS.intersection(package)


def test_changed_request_bytes_refuse_before_return(tmp_path: Path) -> None:
    module, _, _, request_path, source, projection, ledger = _fixture(tmp_path)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["requested_evidence"][0] = "changed evidence"
    _write_json(request_path, request)
    spec = tmp_path / "return-spec.json"
    _write_json(spec, {
        "schema_version": 1,
        "evidence_items": [{
            "item_id": "evidence-000001",
            "immutable_source_path": str(source),
            "readable_projection_path": str(projection),
            "intake_ledger_path": str(ledger),
            "qualification": "readable_projection_complete",
        }],
    })

    with pytest.raises(module.SourceHandoffError, match="artifact digest changed"):
        module.create_return(request_path, spec)


def test_changed_projection_bytes_refuse_reverification(tmp_path: Path) -> None:
    module, _, _, request_path, source, projection, ledger = _fixture(tmp_path)
    spec = tmp_path / "return-spec.json"
    _write_json(spec, {
        "schema_version": 1,
        "evidence_items": [{
            "item_id": "evidence-000001",
            "immutable_source_path": str(source),
            "readable_projection_path": str(projection),
            "intake_ledger_path": str(ledger),
            "qualification": "readable_projection_complete",
        }],
    })
    package = module.create_return(request_path, spec)
    output = tmp_path / "source-return.json"
    module._write_once(package, output, "source return package")
    projection.write_text("changed projection\n", encoding="utf-8")

    with pytest.raises(module.SourceHandoffError, match="readable_projection bytes changed"):
        module.verify_return(output)


def test_ledger_must_bind_request_source_and_projection(tmp_path: Path) -> None:
    module, _, _, request_path, source, projection, ledger = _fixture(tmp_path)
    unrelated = tmp_path / "unrelated-ledger.jsonl"
    _ledger(unrelated, "another-request", _sha(source), _sha(projection))
    spec = tmp_path / "return-spec.json"
    _write_json(spec, {
        "schema_version": 1,
        "evidence_items": [{
            "item_id": "evidence-000001",
            "immutable_source_path": str(source),
            "readable_projection_path": str(projection),
            "intake_ledger_path": str(unrelated),
            "qualification": "readable_projection_complete",
        }],
    })

    with pytest.raises(module.SourceHandoffError, match="does not bind required value request-000001"):
        module.create_return(request_path, spec)


def test_multiple_items_preserve_declared_order_and_unique_identity(tmp_path: Path) -> None:
    module, _, _, request_path, source, projection, ledger = _fixture(tmp_path)
    second_source = tmp_path / "second.cs"
    second_projection = tmp_path / "second.txt"
    second_source.write_text("second source\n", encoding="utf-8")
    second_projection.write_text("second projection\n", encoding="utf-8")
    second_ledger = tmp_path / "second-ledger.jsonl"
    _ledger(second_ledger, "request-000001", _sha(second_source), _sha(second_projection))
    spec = tmp_path / "return-spec.json"
    _write_json(spec, {
        "schema_version": 1,
        "evidence_items": [
            {
                "item_id": "evidence-000001",
                "immutable_source_path": str(source),
                "readable_projection_path": str(projection),
                "intake_ledger_path": str(ledger),
                "qualification": "readable_projection_complete",
            },
            {
                "item_id": "evidence-000002",
                "immutable_source_path": str(second_source),
                "readable_projection_path": str(second_projection),
                "intake_ledger_path": str(second_ledger),
                "qualification": "readable_projection_complete",
            },
        ],
    })

    package = module.create_return(request_path, spec)

    assert [item["item_id"] for item in package["evidence_items"]] == [
        "evidence-000001",
        "evidence-000002",
    ]


def test_write_once_never_overwrites_a_handoff(tmp_path: Path) -> None:
    module, _, _, request_path, *_ = _fixture(tmp_path)
    request = module.verify_request(request_path)

    with pytest.raises(module.SourceHandoffError, match="already exists"):
        module._write_once(request, request_path, "source request")
