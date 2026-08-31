#!/usr/bin/env python3
"""Validate, back up, install, and verify repository-managed Codex skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MCP_NAME = "memory-knowledge"
MCP_ARGS = ["-y", "mcp-remote", "https://memory-knowledge.azurewebsites.net/mcp/"]


class BootstrapError(RuntimeError):
    """The bootstrap cannot continue without risking a partial installation."""


def _tree_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8") + b"\0")
        digest.update(item.read_bytes())
    return digest.hexdigest()


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def _managed_names(repo: Path) -> list[str]:
    manifest = repo / "skills" / "managed-skills.txt"
    return [
        line.strip()
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _unmanaged_hashes(root: Path, managed: set[str]) -> dict[str, str | None]:
    if not root.exists():
        return {}
    return {
        child.name: _tree_hash(child)
        for child in sorted(root.iterdir())
        if child.is_dir() and child.name not in managed
    }


def _validate(repo: Path, source: Path) -> None:
    checked = _run(
        [
            sys.executable,
            str(repo / "working-agreement" / "validate_skills.py"),
            "--skills-root",
            str(source),
            "--manifest",
            str(source / "managed-skills.txt"),
        ],
        cwd=repo,
    )
    if checked.returncode:
        detail = checked.stderr.strip() or checked.stdout.strip()
        raise BootstrapError(f"canonical skill validation refused before mutation: {detail}")


def _backup_managed(root: Path, names: list[str], backup_root: Path) -> Path | None:
    existing = [root / name for name in names if (root / name).exists()]
    if not existing:
        return None
    for path in existing:
        if path.is_symlink() or not path.is_dir():
            raise BootstrapError(f"managed destination is not a regular directory: {path}")
    identity = hashlib.sha256()
    for path in existing:
        identity.update(path.name.encode("utf-8") + b"\0")
        identity.update((_tree_hash(path) or "missing").encode("ascii"))
    backup_root.mkdir(parents=True, exist_ok=True)
    archive = backup_root / f"managed-skills-before-{identity.hexdigest()[:16]}.tar.gz"
    if archive.exists():
        return archive
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    with tarfile.open(temporary, "w:gz") as handle:
        for path in existing:
            handle.add(path, arcname=path.name, recursive=True)
    os.replace(temporary, archive)
    return archive


def _parity(repo: Path, codex_root: Path, report: Path) -> subprocess.CompletedProcess[str]:
    report.parent.mkdir(parents=True, exist_ok=True)
    return _run(
        [
            sys.executable,
            str(repo / "working-agreement" / "project_client_skills.py"),
            "check",
            "--client",
            "codex",
            "--installed-root",
            str(codex_root),
            "--report",
            str(report),
        ],
        cwd=repo,
    )


def mcp_spec(repo: Path, node_bin: Path | None = None) -> dict[str, Any]:
    wrapper = (repo / "scripts" / "mcp-remote-wrapper.sh").resolve()
    if not wrapper.is_file():
        raise BootstrapError(f"memory wrapper is missing: {wrapper}")
    path_parts = []
    if node_bin is not None:
        path_parts.append(str(node_bin.resolve()))
    path_parts.extend(["/usr/local/bin", "/usr/bin", "/bin"])
    return {
        "name": MCP_NAME,
        "transport": "stdio",
        "command": str(wrapper),
        "args": MCP_ARGS,
        "env": {"PATH": ":".join(path_parts)},
    }


def install(
    repo: Path,
    codex_root: Path,
    state_dir: Path,
    backup_root: Path,
    report: Path,
    *,
    source: Path | None = None,
) -> dict[str, Any]:
    repo = repo.resolve()
    source = (source or repo / "skills").resolve()
    names = _managed_names(repo)
    managed = set(names)
    _validate(repo, source)
    unmanaged_before = _unmanaged_hashes(codex_root, managed)
    parity_before_path = report.with_name(report.stem + "-before.json")
    before = _parity(repo, codex_root, parity_before_path)
    backup = _backup_managed(codex_root, names, backup_root)
    installed = _run(
        [
            sys.executable,
            str(repo / "working-agreement" / "install_skills.py"),
            "--source",
            str(source),
            "--manifest",
            str(source / "managed-skills.txt"),
            "--target",
            "codex",
            "--codex-root",
            str(codex_root),
            "--state-dir",
            str(state_dir),
        ],
        cwd=repo,
    )
    if installed.returncode:
        raise BootstrapError(installed.stderr.strip() or installed.stdout.strip())
    after = _parity(repo, codex_root, report)
    if after.returncode:
        raise BootstrapError(after.stdout.strip() or after.stderr.strip())
    unmanaged_after = _unmanaged_hashes(codex_root, managed)
    if unmanaged_after != unmanaged_before:
        raise BootstrapError("an unrelated skill directory changed during installation")
    result = {
        "schema_version": 1,
        "status": "installed",
        "managed_skill_count": len(names),
        "before_parity": before.returncode == 0,
        "after_parity": True,
        "backup": str(backup) if backup else None,
        "unmanaged_preserved": True,
        "report": str(report),
        "mcp": mcp_spec(repo),
    }
    report.with_name(report.stem + "-bootstrap.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def status(repo: Path, codex_root: Path, report: Path) -> dict[str, Any]:
    repo = repo.resolve()
    _validate(repo, repo / "skills")
    checked = _parity(repo, codex_root, report)
    return {
        "schema_version": 1,
        "status": "ready" if checked.returncode == 0 else "needs-install",
        "parity": checked.returncode == 0,
        "report": str(report),
        "mcp": mcp_spec(repo),
    }


def _experiment_repo() -> Path:
    candidate = Path(__file__).resolve().parents[1]
    if (candidate / "skills" / "managed-skills.txt").is_file():
        return candidate
    return Path("/Users/kamenkamenov/.codex/worktrees/07a5/memory-knowledge")


def _run_experiment_case(payload: dict[str, Any], result_path: Path) -> dict[str, Any]:
    repo = _experiment_repo()
    workspace = result_path.parent / "office-bootstrap-case"
    codex_root = workspace / "skills"
    state_dir = workspace / "state"
    backup_root = workspace / "backups"
    report = workspace / "parity.json"
    scenario = payload["scenario"]
    if scenario == "stale":
        stale = codex_root / "working-agreement"
        stale.mkdir(parents=True)
        (stale / "SKILL.md").write_text("stale managed skill\n", encoding="utf-8")
        system = codex_root / ".system"
        system.mkdir()
        (system / "sentinel.txt").write_text("preserve me\n", encoding="utf-8")
    if scenario in {"empty", "stale"}:
        result = install(repo, codex_root, state_dir, backup_root, report)
        return {
            "scenario": scenario,
            "expected_observed": True,
            "parity": result["after_parity"],
            "backup_created": bool(result["backup"]) if scenario == "stale" else result["backup"] is None,
            "unmanaged_preserved": result["unmanaged_preserved"],
            "mcp_spec_valid": result["mcp"]["args"] == MCP_ARGS,
            "external_backup_commands": 0,
        }
    if scenario == "corrupt":
        corrupt = workspace / "corrupt-skills"
        shutil.copytree(repo / "skills", corrupt)
        (corrupt / "working-agreement" / "SKILL.md").unlink()
        sentinel = codex_root / ".system" / "sentinel.txt"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("unchanged\n", encoding="utf-8")
        before = _tree_hash(codex_root)
        refused = False
        try:
            install(repo, codex_root, state_dir, backup_root, report, source=corrupt)
        except BootstrapError as error:
            refused = "validation refused before mutation" in str(error)
        return {
            "scenario": scenario,
            "expected_observed": refused and _tree_hash(codex_root) == before,
            "parity": False,
            "backup_created": False,
            "unmanaged_preserved": _tree_hash(codex_root) == before,
            "mcp_spec_valid": mcp_spec(repo)["args"] == MCP_ARGS,
            "external_backup_commands": 0,
        }
    raise BootstrapError(f"unknown experiment scenario: {scenario}")


def _experiment_entry() -> int:
    variant_id = os.environ["EXPERIMENT_VARIANT_ID"]
    input_path = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    result_path = Path(os.environ["EXPERIMENT_RESULT_PATH"])
    telemetry_path = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    try:
        outcome = _run_experiment_case(payload, result_path)
        status_value, error = "completed", None
    except Exception as failure:  # noqa: BLE001 - the experiment result must retain the boundary.
        outcome = {"scenario": payload.get("scenario"), "expected_observed": False}
        status_value, error = "failed", f"{type(failure).__name__}: {failure}"
    telemetry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sequence": 1,
                "event": "office_bootstrap_case_finished",
                "recorded_at": datetime.now(UTC).isoformat(),
                "variant_id": variant_id,
                "scenario": payload.get("scenario"),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "variant_id": variant_id,
                "status": status_value,
                "outcome": outcome,
                "metrics": {},
                "error": error,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if status_value == "completed" else 1


def main() -> int:
    if "EXPERIMENT_RESULT_PATH" in os.environ:
        return _experiment_entry()
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "install"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
        sub.add_argument("--codex-root", type=Path, default=Path.home() / ".codex" / "skills")
        sub.add_argument("--report", type=Path, required=True)
        if command == "install":
            sub.add_argument("--state-dir", type=Path, required=True)
            sub.add_argument("--backup-root", type=Path, required=True)
    spec = subparsers.add_parser("mcp-spec")
    spec.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    spec.add_argument("--node-bin", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "status":
            result = status(args.repo, args.codex_root, args.report)
        elif args.command == "install":
            result = install(
                args.repo, args.codex_root, args.state_dir, args.backup_root, args.report
            )
        else:
            result = mcp_spec(args.repo, args.node_bin)
    except BootstrapError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
