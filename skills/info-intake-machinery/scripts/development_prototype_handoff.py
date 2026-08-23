#!/usr/bin/env python3
"""Compile a source-grounded Prototype 0 result and proposed PDI autonomy envelope."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import development_objective

CONTRACT = 1
ARTIFACT_TYPE = "info-intake-prototype-driven-implementation-handoff"
VERDICTS = {"satisfied", "gap", "cannot-assess"}
OBSERVATION_FIELDS = {
    "verdict", "criterion_ids", "summary", "practical_impact", "evidence"
}
EXCLUSIONS = [
    "commits", "pushes", "deployments", "destructive-actions", "credentials",
    "external-messages", "product-promotion-without-approval",
]


class HandoffError(RuntimeError):
    """Prototype 0 evidence cannot enter the downstream controller."""


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
        raise HandoffError(f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise HandoffError(f"{label} must contain one JSON object")
    return value


def compile_handoff(
    *, objective_path: Path, observation: object, max_prototypes: int
) -> dict[str, object]:
    try:
        objective = development_objective.verify_objective(objective_path)
    except development_objective.ObjectiveError as error:
        raise HandoffError(f"development objective is invalid: {error}") from None
    if type(max_prototypes) is not int or max_prototypes < 1:
        raise HandoffError("max_prototypes must be a positive integer")
    if type(observation) is not dict or set(observation) != OBSERVATION_FIELDS:
        raise HandoffError(
            f"observation must contain exactly {sorted(OBSERVATION_FIELDS)}"
        )
    if observation["verdict"] not in VERDICTS:
        raise HandoffError(f"observation.verdict must be one of {sorted(VERDICTS)}")
    for field in ("summary", "practical_impact"):
        if type(observation[field]) is not str or not observation[field].strip():
            raise HandoffError(f"observation.{field} must be nonempty text")
    criterion_ids = observation["criterion_ids"]
    if type(criterion_ids) is not list or not criterion_ids:
        raise HandoffError("observation.criterion_ids must select at least one criterion")
    if len(criterion_ids) != len(set(criterion_ids)):
        raise HandoffError("observation.criterion_ids must be unique")
    criteria = {item["claim_id"]: item for item in objective["criteria"]}
    selected: list[dict[str, object]] = []
    for criterion_id in criterion_ids:
        if criterion_id not in criteria:
            raise HandoffError(f"observation selects unknown criterion: {criterion_id}")
        selected.append(criteria[criterion_id])
    binding_path = Path(str(objective["target_binding"]["path"]))
    binding = _load(binding_path, "target binding")
    target = binding["target"]
    surfaces = {item["path"]: item for item in target["surface_files"]}
    evidence = observation["evidence"]
    if type(evidence) is not list or not evidence:
        raise HandoffError("observation.evidence must contain at least one source reference")
    grounded: list[dict[str, object]] = []
    for index, raw in enumerate(evidence):
        expected = {"path", "line_start", "line_end", "quote"}
        if type(raw) is not dict or set(raw) != expected:
            raise HandoffError(f"observation.evidence[{index}] must contain exactly {sorted(expected)}")
        relative = raw["path"]
        if relative not in surfaces:
            raise HandoffError(f"evidence path is outside the bound target surface: {relative}")
        source = Path(str(target["repository"])) / str(relative)
        if _sha(source) != surfaces[relative]["sha256"]:
            raise HandoffError(f"bound source changed: {relative}")
        lines = source.read_text(encoding="utf-8").splitlines()
        start, end = raw["line_start"], raw["line_end"]
        if type(start) is not int or type(end) is not int or start < 1 or end < start or end > len(lines):
            raise HandoffError(f"invalid evidence line range for {relative}")
        actual = "\n".join(lines[start - 1:end])
        if actual != raw["quote"]:
            raise HandoffError(f"evidence quote does not match exact source lines for {relative}")
        grounded.append({**raw, "source_sha256": surfaces[relative]["sha256"]})
    prototype_zero = {
        "verdict": observation["verdict"],
        "selected_criteria": selected,
        "summary": observation["summary"],
        "practical_impact": observation["practical_impact"],
        "evidence": grounded,
    }
    body: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": ARTIFACT_TYPE,
        "development_objective": {
            "path": str(objective_path.resolve()),
            "sha256": _sha(objective_path),
            "artifact_sha256": objective["artifact_sha256"],
        },
        "prototype_zero": prototype_zero,
        "prototype_envelope": {
            "authorization_status": "proposed",
            "outcome": objective["objective"]["outcome"],
            "stopping_condition": "Every selected intake criterion is satisfied through the real operator path.",
            "repository": target["repository"],
            "allowed_paths": [item["path"] for item in target["surface_files"]],
            "captured_success_case": {
                "expected": selected[0]["criterion"],
                "criterion_id": selected[0]["claim_id"],
            },
            "captured_failure_case": prototype_zero,
            "max_prototypes": max_prototypes,
            "excluded_actions": EXCLUSIONS,
        },
    }
    return {**body, "artifact_sha256": _sha_bytes(_canonical(body))}


def write_handoff(value: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(_document(value))
    except FileExistsError:
        raise HandoffError(f"handoff output already exists: {output}") from None


def verify_handoff(path: Path) -> dict[str, object]:
    value = _load(path, "handoff")
    if path.read_bytes() != _document(value):
        raise HandoffError("handoff bytes are not canonical")
    expected = {
        "schema_version", "artifact_type", "development_objective", "prototype_zero",
        "prototype_envelope", "artifact_sha256",
    }
    if set(value) != expected:
        raise HandoffError("handoff fields changed from the exact contract")
    body = {key: value[key] for key in expected if key != "artifact_sha256"}
    if value["artifact_sha256"] != _sha_bytes(_canonical(body)):
        raise HandoffError("handoff artifact digest changed")
    objective_path = Path(str(value["development_objective"]["path"]))
    observation = {
        "verdict": value["prototype_zero"]["verdict"],
        "criterion_ids": [item["claim_id"] for item in value["prototype_zero"]["selected_criteria"]],
        "summary": value["prototype_zero"]["summary"],
        "practical_impact": value["prototype_zero"]["practical_impact"],
        "evidence": [
            {key: item[key] for key in ("path", "line_start", "line_end", "quote")}
            for item in value["prototype_zero"]["evidence"]
        ],
    }
    rebuilt = compile_handoff(
        objective_path=objective_path,
        observation=observation,
        max_prototypes=value["prototype_envelope"]["max_prototypes"],
    )
    if rebuilt != value:
        raise HandoffError("live evidence changed from the Prototype 0 handoff")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--objective", required=True, type=Path)
    create.add_argument("--observation", required=True, type=Path)
    create.add_argument("--max-prototypes", required=True, type=int)
    create.add_argument("--output", required=True, type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("handoff", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            value = compile_handoff(
                objective_path=args.objective,
                observation=_load(args.observation, "observation"),
                max_prototypes=args.max_prototypes,
            )
            write_handoff(value, args.output)
        else:
            value = verify_handoff(args.handoff)
    except HandoffError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "status": "created" if args.command == "create" else "verified",
        "artifact_sha256": value["artifact_sha256"],
        "prototype_zero_verdict": value["prototype_zero"]["verdict"],
        "criterion_ids": [item["claim_id"] for item in value["prototype_zero"]["selected_criteria"]],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
