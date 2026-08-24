from __future__ import annotations

import json

from scripts import directive_guard, script_intake


def test_default_directives_path_follows_the_running_controller_checkout():
    expected = (
        directive_guard.Path(directive_guard.__file__).resolve().parents[1]
        / "working-agreement/DIRECTIVES.md"
    )

    assert directive_guard.DEFAULT_DIRECTIVES_PATH == expected


def test_no_argument_read_uses_intake_answers_directly(
    monkeypatch, tmp_path, capsys,
):
    directives = tmp_path / "DIRECTIVES.md"
    directives.write_text("# Directives\n")
    state = tmp_path / "state.json"
    seen = []

    def collect(spec):
        seen.append(spec)
        return {
            "command_name": "read",
            "mode": "prototype-intake",
            "directives_path": str(directives),
            "state": str(state),
        }

    monkeypatch.setattr(directive_guard.script_intake, "collect", collect)

    assert directive_guard.main([]) == 0
    assert seen == [directive_guard.INTAKE_SPEC]
    assert json.loads(state.read_text())["mode"] == "prototype-intake"
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_no_argument_check_uses_typed_integer_from_intake(
    monkeypatch, tmp_path, capsys,
):
    directives = tmp_path / "DIRECTIVES.md"
    directives.write_text("# Directives\n")
    state = tmp_path / "state.json"
    directive_guard.write_directive_read_state(
        directives_path=directives,
        state_path=state,
        mode="prototype-intake",
    )
    monkeypatch.setattr(
        directive_guard.script_intake,
        "collect",
        lambda spec: {
            "command_name": "check",
            "directives_path": str(directives),
            "state": str(state),
            "max_age_minutes": 5,
        },
    )

    assert directive_guard.main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["state"]["maxAgeMinutes"] == 5


def test_existing_explicit_argument_path_remains_compatible(tmp_path, capsys):
    directives = tmp_path / "DIRECTIVES.md"
    directives.write_text("# Directives\n")
    state = tmp_path / "state.json"

    assert directive_guard.main([
        "read",
        "--mode",
        "legacy-explicit",
        "--directives-path",
        str(directives),
        "--state",
        str(state),
    ]) == 0
    assert json.loads(state.read_text())["mode"] == "legacy-explicit"
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_no_argument_intake_cancellation_fails_closed(monkeypatch, capsys):
    def cancel(spec):
        raise script_intake.IntakeCancelled("intake-cancelled")

    monkeypatch.setattr(directive_guard.script_intake, "collect", cancel)

    assert directive_guard.main([]) == 130
    assert json.loads(capsys.readouterr().err) == {
        "ok": False,
        "error": "intake-cancelled",
    }
