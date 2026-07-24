from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import convergence_state_review_cycle as cycle
from scripts import prevention_source_receipt


def _write_helper(path: Path) -> None:
    path.write_text(
        """from __future__ import annotations
import json
import sys
from pathlib import Path

log = Path(__file__).with_suffix('.log')
with log.open('a', encoding='utf-8') as handle:
    handle.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1] == 'status':
    print(json.dumps({'status': 'review'}))
else:
    print(json.dumps({'ok': True}))
""",
        encoding="utf-8",
    )


def _case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    helper = tmp_path / "helper.py"
    state = tmp_path / "state.json"
    request = tmp_path / "request.json"
    repository = tmp_path / "memory-knowledge"
    repository.mkdir()
    _write_helper(helper)
    state.write_text(json.dumps({
        "schema_version": 4,
        "status": "review",
        "repositories": {str(repository): {}},
    }), encoding="utf-8")
    monkeypatch.setattr(cycle, "RUNTIME_TEMP_ROOT", tmp_path)
    monkeypatch.setattr(cycle, "TASK_ARTIFACT_ROOT", tmp_path / "Tasks")
    monkeypatch.setattr(cycle, "HELPER_PATH", helper)
    monkeypatch.setattr(cycle, "HELPER_SHA256", hashlib.sha256(helper.read_bytes()).hexdigest())
    monkeypatch.setattr(cycle, "OPERATION_RECEIPT_ROOT", tmp_path / "operation-receipts")
    monkeypatch.setattr(cycle, "AUTHORITY_APPROVAL_ROOT", tmp_path / "authority-approvals")
    payload = {
        "schema_version": 2,
        "request_id": "11111111-1111-5111-8111-111111111111",
        "state": "runtime-temp/state.json",
        "initial_state_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
        "expected_final_status": "review",
        "operations": [{
            "operation_id": "22222222-2222-5222-8222-222222222222",
            "kind": "status",
        }],
    }
    request.write_text(json.dumps(payload), encoding="utf-8")
    return helper, state, request, payload


def test_v2_apply_executes_ordered_operation_and_exact_final_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, state, request, _ = _case(tmp_path, monkeypatch)

    result = cycle.apply_request(SimpleNamespace(
        request=str(request), helper=str(helper), dry_run=False,
        prevention_effect_id=None, prevention_preparation_sha256=None,
    ))

    assert result["cycle_status"] == "APPLIED"
    assert result["convergence_status"] == "review"
    assert result["operation_count"] == 1
    calls = [json.loads(line) for line in helper.with_suffix(".log").read_text().splitlines()]
    assert [call[0] for call in calls] == ["status", "check", "status"]


def test_dry_run_preserves_exact_initial_state_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, state, request, _ = _case(tmp_path, monkeypatch)
    before = state.read_bytes()

    result = cycle.apply_request(SimpleNamespace(
        request=str(request), helper=str(helper), dry_run=True,
        prevention_effect_id=None, prevention_preparation_sha256=None,
    ))

    assert result["cycle_status"] == "DRY_RUN"
    assert state.read_bytes() == before
    assert not helper.with_suffix(".log").exists()


def test_legacy_v1_request_is_rejected_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, _, request, _ = _case(tmp_path, monkeypatch)
    request.write_text(json.dumps({
        "schema_version": 1, "state": "runtime-temp/state.json",
        "operations": [{"kind": "status"}],
    }), encoding="utf-8")

    with pytest.raises(cycle.ReviewCycleError, match="invalid-review-cycle-request"):
        cycle.apply_request(SimpleNamespace(
            request=str(request), helper=str(helper), dry_run=False,
        ))
    assert not helper.with_suffix(".log").exists()


def test_absolute_nested_state_path_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, state, request, payload = _case(tmp_path, monkeypatch)
    payload["state"] = str(state)
    request.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(cycle.ReviewCycleError, match="state-is-not-a-file"):
        cycle.apply_request(SimpleNamespace(
            request=str(request), helper=str(helper), dry_run=False,
        ))


def test_duplicate_operation_ids_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, _, request, payload = _case(tmp_path, monkeypatch)
    payload["operations"].append(dict(payload["operations"][0]))
    request.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(cycle.ReviewCycleError, match="operation-ids"):
        cycle.apply_request(SimpleNamespace(
            request=str(request), helper=str(helper), dry_run=False,
        ))


def test_source_receipt_binds_v2_request_and_semantic_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, _, request, _ = _case(tmp_path, monkeypatch)
    monkeypatch.setattr(prevention_source_receipt, "ROOT", tmp_path / "receipts")

    result = cycle.apply_request(SimpleNamespace(
        request=str(request), helper=str(helper), dry_run=False,
        prevention_effect_id="e" * 64,
        prevention_preparation_sha256="f" * 64,
    ))

    receipt = json.loads(
        prevention_source_receipt.receipt_path("e" * 64).read_text(encoding="utf-8")
    )
    assert receipt["status"] == "APPLIED"
    assert receipt["result_identity"]["cycle_status"] == "APPLIED"
    assert receipt["result_identity"]["convergence_status"] == "review"
    assert result["preventionSourceReceiptSha256"] == (
        prevention_source_receipt.receipt_sha256(receipt)
    )


def test_prepared_operation_is_semantically_reconciled_without_reexecution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, state, request, payload = _case(tmp_path, monkeypatch)
    operation = {
        "operation_id": "33333333-3333-5333-8333-333333333333",
        "kind": "record-gap", "id": "gap-1", "requirement_ids": ["req-1"],
        "source_stage": "review", "impact": "bounded impact",
        "evidence": "bounded evidence",
    }
    payload["operations"] = [operation]
    request.write_text(json.dumps(payload), encoding="utf-8")
    request_sha256 = hashlib.sha256(request.read_bytes()).hexdigest()
    operation_sha256 = hashlib.sha256(
        json.dumps(operation, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    journal = {
        "schema_version": 1, "request_id": payload["request_id"],
        "request_sha256": request_sha256,
        "initial_state_sha256": payload["initial_state_sha256"],
        "entries": [{
            "operation_id": operation["operation_id"], "kind": operation["kind"],
            "input_sha256": operation_sha256, "status": "PREPARED",
            "pre_state_sha256": payload["initial_state_sha256"],
        }],
    }
    cycle._atomic_json(cycle._operation_receipt_path(payload, None), journal)
    state_payload = json.loads(state.read_text())
    state_payload["gaps"] = {"gap-1": {
        "requirement_ids": ["req-1"], "source_stage": "review",
        "impact": "bounded impact", "evidence": "bounded evidence",
    }}
    state.write_text(json.dumps(state_payload), encoding="utf-8")

    result = cycle.apply_request(SimpleNamespace(
        request=str(request), helper=str(helper), dry_run=False,
        prevention_effect_id=None, prevention_preparation_sha256=None,
    ))

    assert result["cycle_status"] == "APPLIED"
    calls = [json.loads(line) for line in helper.with_suffix(".log").read_text().splitlines()]
    assert [call[0] for call in calls] == ["check", "status"]


def test_grant_requires_and_consumes_exact_external_authority_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper, _, request, payload = _case(tmp_path, monkeypatch)
    operation = {
        "operation_id": "44444444-4444-5444-8444-444444444444",
        "kind": "grant-autonomy", "id": "grant-1",
        "repository_keys": ["memory-knowledge"],
        "allowed_paths": ["scripts/tool.py"], "stage": "review",
        "evidence": "exact external approval",
        "authority_approval_receipt_id": "55555555-5555-5555-8555-555555555555",
    }
    payload["operations"] = [operation]
    request.write_text(json.dumps(payload), encoding="utf-8")
    receipt_path = cycle.AUTHORITY_APPROVAL_ROOT / (
        operation["authority_approval_receipt_id"] + ".json"
    )
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(json.dumps({
        "authority_approval_receipt_id": operation["authority_approval_receipt_id"],
        "grant_kind": "autonomy", "grant_id": "grant-1",
        "repository_keys": ["memory-knowledge"],
        "allowed_paths_sha256": hashlib.sha256(
            (json.dumps(["scripts/tool.py"], separators=(",", ":")) + "\n").encode()
        ).hexdigest(),
        "stage": "review",
        "evidence_sha256": hashlib.sha256(
            operation["evidence"].encode()
        ).hexdigest(),
        "approved_by": "Kamen", "approved_at_utc": "2026-07-19T00:00:00Z",
    }), encoding="utf-8")

    result = cycle.apply_request(SimpleNamespace(
        request=str(request), helper=str(helper), dry_run=False,
        prevention_effect_id=None, prevention_preparation_sha256=None,
    ))

    assert result["cycle_status"] == "APPLIED"
    assert not receipt_path.exists()
    assert (cycle.AUTHORITY_APPROVAL_ROOT / "consumed" / (
        operation["authority_approval_receipt_id"] + "." +
        operation["operation_id"] + ".json"
    )).is_file()
