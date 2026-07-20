#!/usr/bin/env python3
"""Canonical directory-tree digest for new ``tree_sha256`` identities."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path


def _file_records(root: Path) -> list[dict[str, str]]:
    records: list[tuple[bytes, dict[str, str]]] = []

    def visit(directory: Path) -> None:
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISLNK(mode):
                    raise ValueError(f"symlink entry is not allowed: {path}")
                if stat.S_ISDIR(mode):
                    visit(path)
                    continue
                if not stat.S_ISREG(mode):
                    raise ValueError(f"non-regular entry is not allowed: {path}")
                if entry.name == ".DS_Store":
                    continue
                relative = path.relative_to(root).as_posix()
                relative_bytes = relative.encode("utf-8")
                records.append((relative_bytes, {
                    "path": relative,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }))

    visit(root)
    records.sort(key=lambda item: item[0])
    return [record for _, record in records]


def TREE_SHA256_V1(root: str | Path) -> str:
    """Hash a directory using the canonical ``TREE_SHA256_V1`` contract."""
    requested_root = Path(root)
    if requested_root.is_symlink():
        raise ValueError(f"tree root must not be a symlink: {requested_root}")
    try:
        resolved_root = requested_root.resolve(strict=True)
    except (FileNotFoundError, RuntimeError) as exc:
        raise ValueError(f"tree root cannot be resolved: {requested_root}") from exc
    if not resolved_root.is_dir():
        raise ValueError(f"tree root must be a directory: {requested_root}")

    canonical = json.dumps(
        _file_records(resolved_root),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
