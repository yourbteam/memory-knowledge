#!/usr/bin/env python3
"""Bind immutable intake evidence to one clean development repository and surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

CONTRACT = 1
ARTIFACT_TYPE = "info-intake-development-target-binding"


class BindingError(RuntimeError):
    """The intake-to-target binding cannot be trusted."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise BindingError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def _relative(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise BindingError(f"{label} must be a nonempty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise BindingError(f"{label} must be canonical and relative; received {value!r}")
    return value


def _record_files(root: Path, paths: list[str], label: str) -> list[dict[str, object]]:
    if type(paths) is not list or not paths:
        raise BindingError(f"{label} must contain at least one relative path")
    recorded: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, raw in enumerate(paths):
        relative = _relative(raw, f"{label}[{index}]")
        if relative in seen:
            raise BindingError(f"{label} repeats {relative!r}")
        seen.add(relative)
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise BindingError(f"{label} file is missing or not regular: {relative}")
        recorded.append(
            {"path": relative, "sha256": _sha(path), "size": path.stat().st_size}
        )
    return recorded


def _record_intake(
    intake_root: Path, intake_id: str, evidence_artifacts: list[str]
) -> dict[str, object]:
    root = intake_root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise BindingError("intake root must be an existing non-symlink directory")
    if type(intake_id) is not str or not intake_id:
        raise BindingError("intake_id must be a nonempty string")
    recorded = _record_files(root, evidence_artifacts, "evidence_artifacts")
    for item in recorded:
        path = root / str(item["path"])
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and "intake_id" in value:
            if value["intake_id"] != intake_id:
                raise BindingError(
                    f"evidence artifact belongs to another intake: {item['path']}"
                )
    return {
        "intake_id": intake_id,
        "root": str(root),
        "evidence_artifacts": recorded,
    }


def _record_target(repository: Path, surface_paths: list[str]) -> dict[str, object]:
    repo = repository.resolve()
    if not repo.is_dir() or repo.is_symlink():
        raise BindingError("repository must be an existing non-symlink directory")
    git_root = Path(_git(repo, "rev-parse", "--show-toplevel")).resolve()
    if git_root != repo:
        raise BindingError(f"repository must be the git root; received {repo}")
    status = _git(repo, "status", "--porcelain")
    if status:
        raise BindingError("repository baseline is not clean")
    return {
        "repository": str(repo),
        "git_head": _git(repo, "rev-parse", "HEAD"),
        "git_tree": _git(repo, "rev-parse", "HEAD^{tree}"),
        "worktree": "clean",
        "surface_files": _record_files(repo, surface_paths, "surface_paths"),
    }


def build_binding(
    *,
    intake_root: Path,
    intake_id: str,
    evidence_artifacts: list[str],
    repository: Path,
    surface_paths: list[str],
) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": CONTRACT,
        "artifact_type": ARTIFACT_TYPE,
        "intake": _record_intake(intake_root, intake_id, evidence_artifacts),
        "target": _record_target(repository, surface_paths),
    }
    return {**body, "artifact_sha256": _sha_bytes(_canonical(body))}


def write_binding(binding: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(_document(binding))
    except FileExistsError:
        raise BindingError(f"binding output already exists: {output}") from None


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BindingError(f"binding is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise BindingError("binding must contain one JSON object")
    if path.read_bytes() != _document(value):
        raise BindingError("binding bytes are not canonical")
    return value


def verify_binding(path: Path) -> dict[str, object]:
    value = _load(path)
    expected = {"schema_version", "artifact_type", "intake", "target", "artifact_sha256"}
    if set(value) != expected:
        raise BindingError("binding fields changed from the exact contract")
    if value["schema_version"] != CONTRACT or value["artifact_type"] != ARTIFACT_TYPE:
        raise BindingError("binding contract identity is unsupported")
    body = {key: value[key] for key in expected if key != "artifact_sha256"}
    if value["artifact_sha256"] != _sha_bytes(_canonical(body)):
        raise BindingError("binding artifact digest changed")
    intake = value["intake"]
    target = value["target"]
    if type(intake) is not dict or type(target) is not dict:
        raise BindingError("binding intake and target must be objects")
    rebuilt = build_binding(
        intake_root=Path(str(intake["root"])),
        intake_id=str(intake["intake_id"]),
        evidence_artifacts=[str(item["path"]) for item in intake["evidence_artifacts"]],
        repository=Path(str(target["repository"])),
        surface_paths=[str(item["path"]) for item in target["surface_files"]],
    )
    if rebuilt != value:
        raise BindingError("live intake evidence or target baseline changed from the binding")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--intake", required=True, type=Path)
    create.add_argument("--intake-id", required=True)
    create.add_argument("--evidence-artifact", action="append", required=True)
    create.add_argument("--repository", required=True, type=Path)
    create.add_argument("--surface", action="append", required=True)
    create.add_argument("--output", required=True, type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("binding", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            binding = build_binding(
                intake_root=args.intake,
                intake_id=args.intake_id,
                evidence_artifacts=args.evidence_artifact,
                repository=args.repository,
                surface_paths=args.surface,
            )
            write_binding(binding, args.output)
        else:
            binding = verify_binding(args.binding)
    except BindingError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "verified" if args.command == "verify" else "created",
                "artifact_sha256": binding["artifact_sha256"],
                "intake_id": binding["intake"]["intake_id"],
                "repository": binding["target"]["repository"],
                "surface_count": len(binding["target"]["surface_files"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
