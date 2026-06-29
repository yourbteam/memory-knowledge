from __future__ import annotations

from pathlib import Path

import pytest

import scripts.sequence_guard as sequence_guard
from scripts.directive_guard import write_directive_read_state
from scripts.sequence_guard import main


@pytest.fixture(autouse=True)
def directive_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directives = tmp_path / "DIRECTIVES.md"
    directives.write_text("# Test directives\n", encoding="utf-8")
    state = tmp_path / "directive-state.json"
    write_directive_read_state(
        directives_path=directives,
        state_path=state,
        mode="sequence-guard-test",
    )
    monkeypatch.setattr(sequence_guard, "DEFAULT_DIRECTIVES_PATH", directives)
    monkeypatch.setattr(sequence_guard, "DEFAULT_DIRECTIVE_STATE_PATH", state)


def test_registered_sequence_command_passes_when_recorded(tmp_path: Path) -> None:
    sequence_doc = tmp_path / "operations/sequences/example/sequence.md"
    sequence_doc.parent.mkdir(parents=True)
    command = "uv run python scripts/example.py run"
    sequence_doc.write_text(f"# Example\n\n```bash\n{command}\n```\n", encoding="utf-8")
    state_path = tmp_path / "active-sequence.json"

    assert (
        main(
            [
                "activate",
                "--sequence-id",
                "example",
                "--sequence-doc",
                str(sequence_doc),
                "--state",
                str(state_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "guard",
                "--step",
                "Run example",
                "--command",
                command,
                "--source",
                "sequence_doc",
                "--source-ref",
                str(sequence_doc),
                "--state",
                str(state_path),
            ]
        )
        == 0
    )


def test_activate_fails_without_directive_state(tmp_path: Path) -> None:
    sequence_doc = tmp_path / "operations/sequences/example/sequence.md"
    sequence_doc.parent.mkdir(parents=True)
    sequence_doc.write_text("uv run python scripts/example.py run\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="directive read state not found"):
        main(
            [
                "activate",
                "--sequence-id",
                "example",
                "--sequence-doc",
                str(sequence_doc),
                "--state",
                str(tmp_path / "active-sequence.json"),
                "--directive-state",
                str(tmp_path / "missing-directive-state.json"),
            ]
        )


def test_registered_sequence_command_passes_when_matching_documented_shape(
    tmp_path: Path,
) -> None:
    sequence_doc = tmp_path / "operations/sequences/example/sequence.md"
    sequence_doc.parent.mkdir(parents=True)
    sequence_doc.write_text(
        "\n".join(
            [
                "# Example",
                "",
                "```bash",
                "uv run python scripts/example.py <command>",
                "uv run python scripts/example.py build --tag <image-tag>",
                "uv run python scripts/example.py stop --container <container-name>",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "active-sequence.json"
    main(
        [
            "activate",
            "--sequence-id",
            "example",
            "--sequence-doc",
            str(sequence_doc),
            "--state",
            str(state_path),
        ]
    )

    assert (
        main(
            [
                "guard",
                "--step",
                "Build image",
                "--command",
                "uv run python scripts/example.py build --tag workflow-orch:task-specific",
                "--source",
                "sequence_doc",
                "--source-ref",
                str(sequence_doc),
                "--state",
                str(state_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "guard",
                "--step",
                "Stop container",
                "--command",
                "uv run python scripts/example.py stop --container workflow-orch-task-specific",
                "--source",
                "sequence_doc",
                "--source-ref",
                str(sequence_doc),
                "--state",
                str(state_path),
            ]
        )
        == 0
    )
    with pytest.raises(SystemExit, match="command is not recorded"):
        main(
            [
                "guard",
                "--step",
                "Invent command from broad placeholder",
                "--command",
                "uv run python scripts/example.py invented",
                "--source",
                "sequence_doc",
                "--source-ref",
                str(sequence_doc),
                "--state",
                str(state_path),
            ]
        )


def test_memory_source_is_rejected(tmp_path: Path) -> None:
    sequence_doc = tmp_path / "operations/sequences/example/sequence.md"
    sequence_doc.parent.mkdir(parents=True)
    sequence_doc.write_text("uv run python scripts/example.py run\n", encoding="utf-8")
    state_path = tmp_path / "active-sequence.json"
    main(
        [
            "activate",
            "--sequence-id",
            "example",
            "--sequence-doc",
            str(sequence_doc),
            "--state",
            str(state_path),
        ]
    )

    with pytest.raises(SystemExit, match="command source must be one of"):
        main(
            [
                "guard",
                "--step",
                "Run example",
                "--command",
                "uv run python scripts/example.py run",
                "--source",
                "memory",
                "--source-ref",
                str(sequence_doc),
                "--state",
                str(state_path),
            ]
        )


def test_discovery_log_command_must_be_recorded(tmp_path: Path) -> None:
    discovery_log = tmp_path / "operations/sequences/discovery/example.md"
    discovery_log.parent.mkdir(parents=True)
    recorded = "python package.py --help"
    discovery_log.write_text(f"| step | command |\n| Inspect help | {recorded} |\n", encoding="utf-8")
    state_path = tmp_path / "active-sequence.json"
    main(
        [
            "activate",
            "--sequence-id",
            "example-discovery",
            "--discovery-log",
            str(discovery_log),
            "--state",
            str(state_path),
        ]
    )

    assert (
        main(
            [
                "guard",
                "--step",
                "Inspect help",
                "--command",
                recorded,
                "--source",
                "discovery_log",
                "--source-ref",
                str(discovery_log),
                "--state",
                str(state_path),
            ]
        )
        == 0
    )
    with pytest.raises(SystemExit, match="command is not recorded"):
        main(
            [
                "guard",
                "--step",
                "Invent command",
                "--command",
                "python package.py --made-up-flag",
                "--source",
                "discovery_log",
                "--source-ref",
                str(discovery_log),
                "--state",
                str(state_path),
            ]
        )


def test_script_source_must_invoke_named_script(tmp_path: Path) -> None:
    root = tmp_path
    script = root / "scripts/example.py"
    script.parent.mkdir()
    script.write_text("print('ok')\n", encoding="utf-8")
    sequence_doc = root / "operations/sequences/example/sequence.md"
    sequence_doc.parent.mkdir(parents=True)
    sequence_doc.write_text("Use scripts/example.py.\n", encoding="utf-8")
    state_path = tmp_path / "active-sequence.json"
    main(
        [
            "activate",
            "--sequence-id",
            "example",
            "--sequence-doc",
            str(sequence_doc),
            "--state",
            str(state_path),
        ]
    )

    assert (
        main(
            [
                "guard",
                "--step",
                "Run script",
                "--command",
                "uv run python scripts/example.py run",
                "--source",
                "script",
                "--source-ref",
                "scripts/example.py",
                "--root",
                str(root),
                "--state",
                str(state_path),
            ]
        )
        == 0
    )
    with pytest.raises(SystemExit, match="does not invoke source script"):
        main(
            [
                "guard",
                "--step",
                "Run something else",
                "--command",
                "uv run python scripts/other.py run",
                "--source",
                "script",
                "--source-ref",
                "scripts/example.py",
                "--root",
                str(root),
                "--state",
                str(state_path),
            ]
        )


def test_tool_help_source_requires_evidence_text(tmp_path: Path) -> None:
    sequence_doc = tmp_path / "operations/sequences/example/sequence.md"
    sequence_doc.parent.mkdir(parents=True)
    sequence_doc.write_text("Use package help before first command.\n", encoding="utf-8")
    state_path = tmp_path / "active-sequence.json"
    main(
        [
            "activate",
            "--sequence-id",
            "example",
            "--sequence-doc",
            str(sequence_doc),
            "--state",
            str(state_path),
        ]
    )

    with pytest.raises(SystemExit, match="tool_help evidence text is required"):
        main(
            [
                "guard",
                "--step",
                "Use help-derived command",
                "--command",
                "python package.py --agent-action status",
                "--source",
                "tool_help",
                "--source-ref",
                str(sequence_doc),
                "--state",
                str(state_path),
            ]
        )
    assert (
        main(
            [
                "guard",
                "--step",
                "Use help-derived command",
                "--command",
                "python package.py --agent-action status",
                "--source",
                "tool_help",
                "--source-ref",
                str(sequence_doc),
                "--evidence-text",
                "--agent-action status is listed by package --help",
                "--state",
                str(state_path),
            ]
        )
        == 0
    )
