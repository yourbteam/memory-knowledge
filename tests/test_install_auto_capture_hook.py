from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

MODULE = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "auto-capture"
    / "scripts"
    / "install_claude_hook.py"
)
SPEC = importlib.util.spec_from_file_location("install_claude_hook", MODULE)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def test_reconcile_replaces_legacy_target_preserves_others_and_deduplicates(tmp_path: Path) -> None:
    desired = tmp_path / "installed" / "auto-capture-stop.sh"
    settings = {
        "theme": "dark",
        "hooks": {
            "Stop": [
                {"hooks": [{
                    "type": "command",
                    "command": "/old/repo/working-agreement/auto-capture-stop.sh",
                }]},
                {"matcher": "", "hooks": [{"type": "command", "command": "/keep/anchor.sh"}]},
                {"hooks": [{"type": "command", "command": "/duplicate/auto-capture-stop.sh"}]},
            ],
            "PreToolUse": [{"hooks": [{"type": "command", "command": "/keep/gate.sh"}]}],
        },
    }

    updated, changed = installer.reconcile(settings, installer.desired_command(desired))

    commands = [
        hook["command"]
        for group in updated["hooks"]["Stop"]
        if isinstance(group, dict)
        for hook in group.get("hooks", [])
        if isinstance(hook, dict) and "command" in hook
    ]
    assert changed is True
    assert sum(installer.is_auto_capture_command(command) for command in commands) == 1
    assert installer.desired_command(desired) in commands
    assert "/keep/anchor.sh" in commands
    assert updated["hooks"]["PreToolUse"] == settings["hooks"]["PreToolUse"]
    assert updated["theme"] == "dark"
    assert settings["hooks"]["Stop"][0]["hooks"][0]["command"].startswith("/old/")


def test_configure_is_atomic_and_idempotent(tmp_path: Path) -> None:
    settings_path = tmp_path / ".claude" / "settings.json"
    hook_path = tmp_path / "skills" / "auto-capture" / "scripts" / "auto-capture-stop.sh"
    hook_path.parent.mkdir(parents=True)
    hook_path.write_text("#!/usr/bin/env bash\n")
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"existing": 1}))

    assert installer.configure(settings_path, hook_path) is True
    first = settings_path.read_bytes()
    assert installer.configure(settings_path, hook_path) is False
    assert settings_path.read_bytes() == first
    assert installer.configure(settings_path, hook_path, check=True) is False


def test_check_fails_closed_on_stale_configuration(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text("{}")

    with pytest.raises(installer.HookConfigurationError, match="configuration is stale"):
        installer.configure(settings, tmp_path / "auto-capture-stop.sh", check=True)
