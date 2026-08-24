#!/usr/bin/env python3
"""Compose exact per-repository target bindings into one immutable target set."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import development_target_binding

CONTRACT = 1
ARTIFACT_TYPE = "info-intake-development-target-set"


class TargetSetError(RuntimeError):
    """The multi-repository development target set cannot be trusted."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TargetSetError(f"target set is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise TargetSetError("target set must contain one JSON object")
    return value


def compose_target_set(binding_paths: list[Path]) -> dict[str, object]:
    if type(binding_paths) is not list or len(binding_paths) < 2:
        raise TargetSetError("target set requires at least two repository bindings")
    members: list[dict[str, object]] = []
    repositories: set[str] = set()
    intake_id: str | None = None
    evidence: object | None = None
    for index, path in enumerate(binding_paths):
        try:
            binding = development_target_binding.verify_binding(path)
        except development_target_binding.BindingError as error:
            raise TargetSetError(f"binding[{index}] is invalid: {error}") from None
        repository = str(binding["target"]["repository"])
        if repository in repositories:
            raise TargetSetError(f"target set repeats repository: {repository}")
        repositories.add(repository)
        member_intake_id = str(binding["intake"]["intake_id"])
        member_evidence = binding["intake"]["evidence_artifacts"]
        if intake_id is None:
            intake_id = member_intake_id
            evidence = member_evidence
        elif member_intake_id != intake_id or member_evidence != evidence:
            raise TargetSetError("all repository bindings must use the same intake evidence")
        members.append({
            "sequence": index + 1,
            "binding_path": str(path.resolve()),
            "binding_sha256": _sha(path),
            "binding_artifact_sha256": binding["artifact_sha256"],
            "repository": repository,
            "git_head": binding["target"]["git_head"],
            "git_tree": binding["target"]["git_tree"],
            "surface_files": binding["target"]["surface_files"],
        })
    body: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": ARTIFACT_TYPE,
        "intake_id": intake_id,
        "members": members,
    }
    return {**body, "artifact_sha256": _sha_bytes(_canonical(body))}


def write_target_set(value: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(_document(value))
    except FileExistsError:
        raise TargetSetError(f"target-set output already exists: {output}") from None


def verify_target_set(path: Path) -> dict[str, object]:
    value = _load(path)
    if path.read_bytes() != _document(value):
        raise TargetSetError("target set bytes are not canonical")
    expected = {"schema_version", "artifact_type", "intake_id", "members", "artifact_sha256"}
    if set(value) != expected:
        raise TargetSetError("target set fields changed from the exact contract")
    body = {key: value[key] for key in expected if key != "artifact_sha256"}
    if value["artifact_sha256"] != _sha_bytes(_canonical(body)):
        raise TargetSetError("target set artifact digest changed")
    rebuilt = compose_target_set([Path(item["binding_path"]) for item in value["members"]])
    if rebuilt != value:
        raise TargetSetError("live repository binding changed from the target set")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--binding", action="append", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("target_set", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            value = compose_target_set(args.binding)
            write_target_set(value, args.output)
        else:
            value = verify_target_set(args.target_set)
    except TargetSetError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "status": "created" if args.command == "create" else "verified",
        "artifact_sha256": value["artifact_sha256"],
        "repository_count": len(value["members"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
