#!/usr/bin/env python3
"""Atomically point Claude's Stop hook at the installed auto-capture package."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any

HOOK_BASENAME = "auto-capture-stop.sh"


class HookConfigurationError(RuntimeError):
    """Claude settings do not have a safely mergeable shape."""


def is_auto_capture_command(command: object) -> bool:
    if not isinstance(command, str):
        return False
    try:
        return any(Path(part).name == HOOK_BASENAME for part in shlex.split(command))
    except ValueError:
        return False


def desired_command(script_path: Path) -> str:
    return f"/bin/bash {shlex.quote(str(script_path.resolve()))}"


def reconcile(settings: dict[str, Any], command: str) -> tuple[dict[str, Any], bool]:
    updated = copy.deepcopy(settings)
    hooks = updated.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HookConfigurationError("settings hooks must be an object")
    stop = hooks.setdefault("Stop", [])
    if not isinstance(stop, list):
        raise HookConfigurationError("settings hooks.Stop must be an array")

    found = False
    groups = []
    for group in stop:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            groups.append(group)
            continue
        group_hooks = []
        for hook in group["hooks"]:
            if isinstance(hook, dict) and is_auto_capture_command(hook.get("command")):
                if found:
                    continue
                replacement = dict(hook)
                replacement.update({"type": "command", "command": command})
                group_hooks.append(replacement)
                found = True
            else:
                group_hooks.append(hook)
        if group_hooks:
            replacement_group = dict(group)
            replacement_group["hooks"] = group_hooks
            groups.append(replacement_group)
    if not found:
        groups.append({"hooks": [{"type": "command", "command": command}]})
    hooks["Stop"] = groups
    return updated, updated != settings


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HookConfigurationError(f"settings file is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise HookConfigurationError("settings root must be an object")
    return value


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    descriptor, raw_temp = tempfile.mkstemp(prefix=".auto-capture-settings-", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def configure(settings_path: Path, hook_path: Path, *, check: bool = False) -> bool:
    current = load_settings(settings_path)
    updated, changed = reconcile(current, desired_command(hook_path))
    if check:
        if changed:
            raise HookConfigurationError("Claude auto-capture hook configuration is stale")
        return False
    if changed:
        atomic_write(settings_path, updated)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, default=Path("~/.claude/settings.json").expanduser())
    parser.add_argument(
        "--hook", type=Path, default=Path(__file__).resolve().with_name(HOOK_BASENAME),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        changed = configure(args.settings.resolve(), args.hook.resolve(), check=args.check)
    except HookConfigurationError as exc:
        print(f"auto-capture hook configuration failed: {exc}")
        return 1
    print("auto-capture hook " + ("updated" if changed else "verified"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
