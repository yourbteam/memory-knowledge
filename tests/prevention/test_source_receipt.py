from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import prevention_source_receipt
from scripts.prevention_contract import canonical_bytes


def test_source_receipt_is_prepared_before_completion_and_replays_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(prevention_source_receipt, "ROOT", tmp_path)
    identity = {"repository": "repo-1", "prestate": "a" * 64}
    values = {
        "owner_sequence_id": "commit-push-main",
        "profile_id": "publish",
        "effect_id": "e" * 64,
        "preparation_artifact_sha256": "f" * 64,
        "source_identity": identity,
    }

    prepared = prevention_source_receipt.prepare(**values)
    path = prevention_source_receipt.receipt_path("e" * 64)
    applied = prevention_source_receipt.complete(
        **values, result_identity={"commit": "1" * 40}
    )
    replay = prevention_source_receipt.complete(
        **values, result_identity={"commit": "1" * 40}
    )

    assert prepared["status"] == "PREPARED"
    assert applied == replay
    assert applied["status"] == "APPLIED"
    assert path.read_bytes() == canonical_bytes(applied)
    assert json.loads(path.read_text(encoding="utf-8")) == applied


def test_source_receipt_rejects_identity_drift_and_secret_shaped_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(prevention_source_receipt, "ROOT", tmp_path)
    base = {
        "owner_sequence_id": "owner",
        "profile_id": "mode",
        "effect_id": "e" * 64,
        "preparation_artifact_sha256": "f" * 64,
    }
    prevention_source_receipt.prepare(**base, source_identity={"target": "one"})

    with pytest.raises(
        prevention_source_receipt.SourceReceiptError, match="identity-conflict"
    ):
        prevention_source_receipt.prepare(
            **base, source_identity={"target": "two"}
        )
    with pytest.raises(
        prevention_source_receipt.SourceReceiptError, match="identity-invalid"
    ):
        prevention_source_receipt.prepare(
            **{**base, "effect_id": "a" * 64},
            source_identity={"token": "forbidden"},
        )
