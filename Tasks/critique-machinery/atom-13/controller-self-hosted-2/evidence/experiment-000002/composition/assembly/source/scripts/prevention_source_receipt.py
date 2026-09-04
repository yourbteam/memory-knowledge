#!/usr/bin/env python3
"""Source-owned, crash-durable effect identity receipts.

The owner source writes PREPARED before its first mutation and APPLIED only
after its own semantic result exists.  Owner observers combine this receipt
with the authoritative domain state; the receipt never substitutes for that
state.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts.prevention_contract import canonical_bytes, sha256_bytes
except ModuleNotFoundError:  # direct source-script execution
    from prevention_contract import canonical_bytes, sha256_bytes


ROOT = Path(os.environ.get(
    "PREVENTION_SOURCE_RECEIPT_ROOT",
    "/private/tmp/prevention-owner-source-receipts",
))
FORBIDDEN_KEYS = frozenset({
    "password", "secret", "token", "api_key", "access_token",
    "refresh_token", "private_key", "credential", "credentials",
})


class SourceReceiptError(ValueError):
    """A source attempted an unbound or conflicting durable receipt write."""


def _sha256(value: str, label: str) -> str:
    if (
        not isinstance(value, str) or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SourceReceiptError(f"invalid-{label}")
    return value


def _safe(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(
            str(key).lower() not in FORBIDDEN_KEYS and _safe(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return all(_safe(item) for item in value)
    return value is None or isinstance(value, (str, int, float, bool))


def receipt_path(effect_id: str) -> Path:
    return ROOT / f"{_sha256(effect_id, 'effect-id')}.json"


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceReceiptError("source-receipt-invalid") from exc
    if not isinstance(value, dict) or raw != canonical_bytes(value):
        raise SourceReceiptError("source-receipt-noncanonical")
    return value


def _atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(dict(value))
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare(
    *, owner_sequence_id: str, profile_id: str, effect_id: str,
    preparation_artifact_sha256: str, source_identity: Mapping[str, Any],
) -> dict[str, Any]:
    _sha256(effect_id, "effect-id")
    _sha256(preparation_artifact_sha256, "preparation-artifact-sha256")
    if (
        not isinstance(owner_sequence_id, str) or not owner_sequence_id
        or not isinstance(profile_id, str) or not profile_id
        or not isinstance(source_identity, Mapping) or not _safe(source_identity)
    ):
        raise SourceReceiptError("source-receipt-identity-invalid")
    path = receipt_path(effect_id)
    identity = {
        "owner_sequence_id": owner_sequence_id,
        "profile_id": profile_id,
        "effect_id": effect_id,
        "preparation_artifact_sha256": preparation_artifact_sha256,
        "source_identity": dict(source_identity),
    }
    existing = _load(path)
    if existing is not None:
        if any(existing.get(name) != value for name, value in identity.items()):
            raise SourceReceiptError("source-receipt-identity-conflict")
        if existing.get("status") not in {"PREPARED", "APPLIED"}:
            raise SourceReceiptError("source-receipt-status-invalid")
        return existing
    receipt = {"schema_version": 1, **identity, "status": "PREPARED"}
    _atomic(path, receipt)
    return receipt


def complete(
    *, owner_sequence_id: str, profile_id: str, effect_id: str,
    preparation_artifact_sha256: str, source_identity: Mapping[str, Any],
    result_identity: Mapping[str, Any],
) -> dict[str, Any]:
    prepared = prepare(
        owner_sequence_id=owner_sequence_id,
        profile_id=profile_id,
        effect_id=effect_id,
        preparation_artifact_sha256=preparation_artifact_sha256,
        source_identity=source_identity,
    )
    if not isinstance(result_identity, Mapping) or not _safe(result_identity):
        raise SourceReceiptError("source-receipt-result-invalid")
    expected = {
        **{key: value for key, value in prepared.items() if key != "status"},
        "status": "APPLIED",
        "result_identity": dict(result_identity),
    }
    path = receipt_path(effect_id)
    existing = _load(path)
    if existing is not None and existing.get("status") == "APPLIED":
        if existing != expected:
            raise SourceReceiptError("source-receipt-result-conflict")
        return existing
    if existing != prepared:
        raise SourceReceiptError("source-receipt-prepared-state-conflict")
    _atomic(path, expected)
    return expected


def receipt_sha256(receipt: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(dict(receipt)))
