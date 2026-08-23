#!/usr/bin/env python3
"""Compile one evidence-bound development objective from a completed intake assessment."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import development_target_binding

CONTRACT = 1
ARTIFACT_TYPE = "info-intake-development-objective"
RESPONSE_FIELDS = {"outcome_id", "outcome", "practical_value", "reason", "claim_ids"}


class ObjectiveError(RuntimeError):
    """The development objective cannot be grounded in the bound intake."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObjectiveError(f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise ObjectiveError(f"{label} must contain one JSON object")
    return value


def _selection(value: object) -> dict[str, Any]:
    if type(value) is not dict or set(value) != RESPONSE_FIELDS:
        raise ObjectiveError(
            f"selection must contain exactly {sorted(RESPONSE_FIELDS)}"
        )
    for field in ("outcome_id", "outcome", "practical_value", "reason"):
        if type(value[field]) is not str or not value[field].strip():
            raise ObjectiveError(f"selection.{field} must be nonempty text")
    claim_ids = value["claim_ids"]
    if type(claim_ids) is not list or not claim_ids:
        raise ObjectiveError("selection.claim_ids must select at least one claim")
    if any(type(item) is not str or not item for item in claim_ids):
        raise ObjectiveError("selection.claim_ids must contain nonempty strings")
    if len(claim_ids) != len(set(claim_ids)):
        raise ObjectiveError("selection.claim_ids must be unique")
    return value


def compile_objective(
    *, target_binding_path: Path, assessment_path: Path, selection: object
) -> dict[str, object]:
    try:
        binding = development_target_binding.verify_binding(target_binding_path)
    except development_target_binding.BindingError as error:
        raise ObjectiveError(f"target binding is invalid: {error}") from None
    response = _selection(selection)
    assessment = _load(assessment_path, "assessment")
    intake = binding["intake"]
    root = Path(str(intake["root"])).resolve()
    assessment = assessment
    resolved = assessment_path.resolve()
    if root not in resolved.parents:
        raise ObjectiveError("assessment must stay inside the bound intake")
    relative = str(resolved.relative_to(root))
    recorded = {item["path"]: item for item in intake["evidence_artifacts"]}
    if relative not in recorded or recorded[relative]["sha256"] != _sha(resolved):
        raise ObjectiveError("assessment is not one of the exact bound intake artifacts")
    claim_list = assessment.get("claims")
    if type(claim_list) is not list:
        raise ObjectiveError("assessment must contain a claims list")
    claims = {
        item.get("claim_id"): item
        for item in claim_list
        if type(item) is dict and type(item.get("claim_id")) is str
    }
    if len(claims) != len(claim_list):
        raise ObjectiveError("assessment claim identities must be complete and unique")
    criteria: list[dict[str, object]] = []
    for sequence, claim_id in enumerate(response["claim_ids"], start=1):
        claim = claims.get(claim_id)
        if claim is None:
            raise ObjectiveError(f"selection names unknown claim: {claim_id}")
        if claim.get("verdict") != "confirmed":
            raise ObjectiveError(f"selection names claim without confirmed evidence: {claim_id}")
        statement = claim.get("statement")
        if type(statement) is not str or not statement.strip():
            raise ObjectiveError(f"confirmed claim has no statement: {claim_id}")
        criteria.append(
            {
                "sequence": sequence,
                "claim_id": claim_id,
                "criterion": statement,
                "packet_sha256": claim.get("packet_sha256"),
                "evidence_pointers": claim.get("evidence_pointers", []),
            }
        )
    body: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": ARTIFACT_TYPE,
        "target_binding": {
            "path": str(target_binding_path.resolve()),
            "sha256": _sha(target_binding_path),
            "artifact_sha256": binding["artifact_sha256"],
        },
        "assessment": {"path": relative, "sha256": _sha(resolved)},
        "selection": response,
        "objective": {
            key: response[key]
            for key in ("outcome_id", "outcome", "practical_value", "reason")
        },
        "criteria": criteria,
    }
    return {**body, "artifact_sha256": _sha_bytes(_canonical(body))}


def write_objective(value: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(_document(value))
    except FileExistsError:
        raise ObjectiveError(f"objective output already exists: {output}") from None


def verify_objective(path: Path) -> dict[str, object]:
    value = _load(path, "objective")
    if path.read_bytes() != _document(value):
        raise ObjectiveError("objective bytes are not canonical")
    expected = {
        "schema_version", "artifact_type", "target_binding", "assessment",
        "selection", "objective", "criteria", "artifact_sha256",
    }
    if set(value) != expected:
        raise ObjectiveError("objective fields changed from the exact contract")
    body = {key: value[key] for key in expected if key != "artifact_sha256"}
    if value["artifact_sha256"] != _sha_bytes(_canonical(body)):
        raise ObjectiveError("objective artifact digest changed")
    binding_path = Path(str(value["target_binding"]["path"]))
    binding = development_target_binding.verify_binding(binding_path)
    assessment_path = Path(str(binding["intake"]["root"])) / str(value["assessment"]["path"])
    rebuilt = compile_objective(
        target_binding_path=binding_path,
        assessment_path=assessment_path,
        selection=value["selection"],
    )
    if rebuilt != value:
        raise ObjectiveError("live evidence changed from the development objective")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--target-binding", required=True, type=Path)
    create.add_argument("--assessment", required=True, type=Path)
    create.add_argument("--selection", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("objective", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            value = compile_objective(
                target_binding_path=args.target_binding,
                assessment_path=args.assessment,
                selection=_load(args.selection, "selection"),
            )
            write_objective(value, args.output)
        else:
            value = verify_objective(args.objective)
    except ObjectiveError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "status": "created" if args.command == "create" else "verified",
        "artifact_sha256": value["artifact_sha256"],
        "outcome_id": value["objective"]["outcome_id"],
        "criterion_count": len(value["criteria"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
