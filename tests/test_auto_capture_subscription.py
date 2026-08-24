from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE = Path(__file__).resolve().parents[1] / "working-agreement" / "auto_capture_subscription.py"
SPEC = importlib.util.spec_from_file_location("auto_capture_subscription", MODULE)
assert SPEC is not None and SPEC.loader is not None
subscription = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subscription)


SCHEMA = {
    "type": "object",
    "required": ["capture_selection", "lessons"],
    "properties": {
        "capture_selection": {"type": "integer"},
        "lessons": {"type": "array"},
    },
}
ANSWER = {"capture_selection": 1, "lessons": []}
MESSAGES = [
    {"role": "system", "content": "Choose numbered values."},
    {"role": "user", "content": "Assess this session."},
]


def test_active_client_is_explicit_or_host_derived() -> None:
    assert subscription.active_client({"MK_CLIENT_KIND": "codex", "CLAUDECODE": "1"}) == "codex"
    assert subscription.active_client({"CLAUDECODE": "1"}) == "claude"
    assert subscription.active_client({}) == "codex"
    with pytest.raises(subscription.SubscriptionCompletionError, match="must be codex or claude"):
        subscription.active_client({"MK_CLIENT_KIND": "api"})


def test_codex_subscription_completion_uses_stdin_and_isolated_structured_output() -> None:
    observed = {}

    def runner(argv, **kwargs):
        observed.update({"argv": argv, **kwargs})
        result = Path(argv[argv.index("--output-last-message") + 1])
        result.write_text(json.dumps(ANSWER), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    assert json.loads(subscription.complete(
        MESSAGES, SCHEMA, client="codex", runner=runner, which=lambda _: "/bin/codex",
    )) == ANSWER
    assert observed["argv"][-1] == "-"
    assert "--ignore-user-config" in observed["argv"]
    assert "--ignore-rules" in observed["argv"]
    assert "--ephemeral" in observed["argv"]
    assert observed["input"] == (
        "<system>\nChoose numbered values.\n</system>\n\n"
        "<user>\nAssess this session.\n</user>"
    )
    assert observed["env"]["MK_AUTOCAPTURE"] == "0"
    assert observed["env"]["MK_AUTOCAPTURE_NESTED"] == "1"
    assert "Assess this session." not in observed["argv"]


def test_claude_subscription_completion_disables_tools_hooks_and_persistence() -> None:
    observed = {}

    def runner(argv, **kwargs):
        observed.update({"argv": argv, **kwargs})
        envelope = {"type": "result", "is_error": False, "structured_output": ANSWER}
        return SimpleNamespace(returncode=0, stdout=json.dumps(envelope), stderr="")

    assert json.loads(subscription.complete(
        MESSAGES, SCHEMA, client="claude", runner=runner, which=lambda _: "/bin/claude",
    )) == ANSWER
    assert observed["argv"][:2] == ["/bin/claude", "-p"]
    assert observed["argv"][observed["argv"].index("--tools") + 1] == ""
    assert observed["argv"][observed["argv"].index("--setting-sources") + 1] == ""
    assert "--no-session-persistence" in observed["argv"]
    assert observed["input"].endswith("</user>")
    assert "Assess this session." not in observed["argv"]


def test_subscription_boundary_contains_no_public_api_sdk() -> None:
    source = MODULE.read_text(encoding="utf-8")
    assert "AsyncOpenAI" not in source
    assert "api.openai.com" not in source
    assert "Anthropic(" not in source


def test_client_failure_is_actionable_without_leaking_prompt() -> None:
    def runner(*_args, **_kwargs):
        return SimpleNamespace(returncode=7, stdout="", stderr="subscription expired\n")

    with pytest.raises(
        subscription.SubscriptionCompletionError,
        match="codex subscription client exited 7: subscription expired",
    ):
        subscription.complete(
            MESSAGES, SCHEMA, client="codex", runner=runner, which=lambda _: "/bin/codex",
        )


def test_client_failure_never_substitutes_stdout_for_diagnostics() -> None:
    def runner(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout="Assess this session. secret transcript contents",
            stderr="",
        )

    with pytest.raises(
        subscription.SubscriptionCompletionError,
        match="codex subscription client exited 1: no stderr returned",
    ) as caught:
        subscription.complete(
            MESSAGES, SCHEMA, client="codex", runner=runner, which=lambda _: "/bin/codex",
        )
    assert "secret transcript" not in str(caught.value)


def test_client_failure_discards_terminal_controls_after_real_error() -> None:
    def runner(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="real failure\n\x1b[?25h")

    with pytest.raises(
        subscription.SubscriptionCompletionError,
        match="codex subscription client exited 1: real failure",
    ):
        subscription.complete(
            MESSAGES, SCHEMA, client="codex", runner=runner, which=lambda _: "/bin/codex",
        )


def test_probe_debug_can_expose_bounded_failure_streams(monkeypatch) -> None:
    monkeypatch.setenv("MK_AUTOCAPTURE_DEBUG", "1")

    def runner(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="bounded stdout", stderr="\x1b[?25h")

    with pytest.raises(subscription.SubscriptionCompletionError) as caught:
        subscription.complete(
            MESSAGES, SCHEMA, client="codex", runner=runner, which=lambda _: "/bin/codex",
        )
    assert "stderr_tail='\\x1b[?25h'" in str(caught.value)
    assert "stdout_tail='bounded stdout'" in str(caught.value)
