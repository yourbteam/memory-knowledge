"""Tests for the automatic session-close auto-capture helper (#2 option 1)."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_MOD = Path(__file__).resolve().parent.parent / "working-agreement" / "auto_capture.py"
_spec = importlib.util.spec_from_file_location("auto_capture", _MOD)
ac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ac)

_ROOT = Path(__file__).resolve().parent.parent


class FakeCompletions:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.answers.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(answer)))]
        )


def fake_client(*answers):
    completions = FakeCompletions(answers)
    return SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
        completions=completions,
    )


def test_repo_key_from_cwd():
    assert ac.repo_key_from_cwd("/Users/k/taggable-server") == "taggable-server"
    assert ac.repo_key_from_cwd(None) is None


def test_load_transcript_text(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(
        json.dumps({"message": {"role": "user", "content": "why did the build fail"}}) + "\n"
        + json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": "missing env var"}]}}) + "\n"
        + "not-json\n"
    )
    out = ac.load_transcript_text(str(t))
    assert "user: why did the build fail" in out
    assert "assistant: missing env var" in out


@pytest.mark.asyncio
async def test_opt_in_gate_off(monkeypatch):
    monkeypatch.delenv("MK_AUTOCAPTURE", raising=False)

    async def boom(*a, **k):
        raise AssertionError("must not run when gate off")

    monkeypatch.setattr(ac, "extract_lessons", boom)
    monkeypatch.setattr(ac, "write_candidates", boom)
    assert await ac._main() == 0  # no-op


@pytest.mark.asyncio
async def test_writes_candidates_when_enabled(monkeypatch):
    monkeypatch.setenv("MK_AUTOCAPTURE", "1")
    monkeypatch.setattr(ac, "read_payload", lambda: {"cwd": "/x/taggable-server", "transcript_path": "/x/t.jsonl"})
    monkeypatch.setattr(ac, "load_transcript_text", lambda p: "user: x\nassistant: y")
    captured = {}

    async def fake_extract(txt):
        return [{"title": "lesson A", "body": "do Y not X"}]

    async def fake_write(repo, lessons):
        captured["repo"] = repo
        captured["lessons"] = lessons
        return len(lessons)

    monkeypatch.setattr(ac, "extract_lessons", fake_extract)
    monkeypatch.setattr(ac, "write_candidates", fake_write)
    assert await ac._main() == 0
    assert captured["repo"] == "taggable-server"
    assert captured["lessons"][0]["title"] == "lesson A"


@pytest.mark.asyncio
async def test_numbered_model_answer_maps_to_unchanged_candidate_payload():
    client = fake_client(ac.parse_interview.__globals__["_valid_probe_answer"]())

    lessons = await ac.conduct_interview(client, "user: durable session evidence")

    assert lessons[0] == {
        "title": "Isolate Git dry-run writes",
        "body": "A temporary index alone still writes objects; isolate both stores.",
        "content_kind": "corrected-approach",
        "evidence_refs": [
            {
                "kind": "file",
                "file_path": "scripts/minimal_git_publish.py",
                "revision_commit": "a" * 40,
            },
            {"kind": "revision", "revision_commit": "b" * 40},
        ],
    }
    assert client.completions.calls[0]["messages"][0]["content"] == ac.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_prose_selection_is_rejected_then_actionably_retried():
    prose = ac.parse_interview.__globals__["_valid_probe_answer"]()
    prose["lessons"][0]["content_kind_selection"] = "corrected-approach"
    corrected = ac.parse_interview.__globals__["_valid_probe_answer"]()
    client = fake_client(prose, corrected)

    lessons = await ac.conduct_interview(client, "user: durable session evidence")

    assert len(lessons) == 2
    assert len(client.completions.calls) == 2
    correction = client.completions.calls[1]["messages"][-1]["content"]
    assert "content-kind selection returned 'corrected-approach'" in correction
    assert "Choose only numbers from the displayed menus" in correction


@pytest.mark.asyncio
async def test_zero_capture_does_not_retry():
    client = fake_client({"capture_selection": 1, "lessons": []})

    assert await ac.conduct_interview(client, "user: no durable lesson") == []
    assert len(client.completions.calls) == 1


@pytest.mark.asyncio
async def test_dry_run_never_writes_candidates(monkeypatch, capsys):
    monkeypatch.setenv("MK_AUTOCAPTURE", "1")
    monkeypatch.setenv("MK_AUTOCAPTURE_DRY_RUN", "1")
    monkeypatch.setattr(
        ac,
        "read_payload",
        lambda: {"cwd": "/x/taggable-server", "transcript_path": "/x/t.jsonl"},
    )
    monkeypatch.setattr(ac, "load_transcript_text", lambda path: "user: x")
    lesson = {
        "title": "lesson A",
        "body": "do Y not X",
        "content_kind": "corrected-approach",
        "evidence_refs": [{"kind": "revision", "revision_commit": "a" * 40}],
    }

    async def fake_extract(text):
        return [lesson]

    async def forbidden_write(*args, **kwargs):
        raise AssertionError("dry-run must not write candidates")

    monkeypatch.setattr(ac, "extract_lessons", fake_extract)
    monkeypatch.setattr(ac, "write_candidates", forbidden_write)

    assert await ac._main() == 0
    assert json.loads(capsys.readouterr().out) == {
        "repository_key": "taggable-server",
        "lessons": [lesson],
    }


@pytest.mark.asyncio
async def test_dry_run_surfaces_fail_open_diagnostics(monkeypatch, capsys):
    monkeypatch.setenv("MK_AUTOCAPTURE", "1")
    monkeypatch.setenv("MK_AUTOCAPTURE_DRY_RUN", "1")
    monkeypatch.setattr(
        ac,
        "read_payload",
        lambda: {"cwd": "/x/taggable-server", "transcript_path": "/x/t.jsonl"},
    )
    monkeypatch.setattr(ac, "load_transcript_text", lambda path: "user: x")

    async def failed_extract(text):
        raise RuntimeError("bounded probe failure")

    monkeypatch.setattr(ac, "extract_lessons", failed_extract)

    assert await ac._main() == 0
    assert "dry-run failed: RuntimeError: bounded probe failure" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_extraction_uses_subscription_boundary_and_not_public_api(monkeypatch):
    answer = ac.parse_interview.__globals__["_valid_probe_answer"]()
    observed = {}

    def fake_subscription(messages, schema):
        observed["messages"] = messages
        observed["schema"] = schema
        return json.dumps(answer)

    monkeypatch.setattr(ac, "complete_via_subscription", fake_subscription)

    lessons = await ac.extract_lessons("user: durable evidence")

    assert lessons[0]["content_kind"] == "corrected-approach"
    assert observed["messages"][0]["content"] == ac.SYSTEM_PROMPT
    assert observed["schema"] == ac.INTERVIEW_OUTPUT_SCHEMA
    source = _MOD.read_text(encoding="utf-8")
    assert "AsyncOpenAI" not in source
    assert "resolve_model_api_key" not in source
    assert "OPENAI_API_KEY" not in source
    assert "MK_AUTOCAPTURE_MODEL" not in source


def test_managed_skill_packages_the_exact_proven_runtime():
    skill_scripts = _ROOT / "skills" / "auto-capture" / "scripts"
    agreement = _ROOT / "working-agreement"

    assert (skill_scripts / "auto_capture.py").read_bytes() == (
        agreement / "auto_capture.py"
    ).read_bytes()
    assert (skill_scripts / "auto_capture_interview.py").read_bytes() == (
        agreement / "auto_capture_interview.py"
    ).read_bytes()
    assert (skill_scripts / "auto_capture_subscription.py").read_bytes() == (
        agreement / "auto_capture_subscription.py"
    ).read_bytes()


def test_stop_hook_defaults_to_installed_claude_runtime():
    hook = (_ROOT / "working-agreement" / "auto-capture-stop.sh").read_text()

    assert (
        "/Users/kamenkamenov/.claude/skills/auto-capture/scripts/auto_capture.py"
        in hook
    )
    assert 'MK_AUTOCAPTURE_DRY_RUN:-0' in hook
    assert 'MK_AUTOCAPTURE_NESTED:-0' in hook
    assert 'MK_CLIENT_KIND="${MK_CLIENT_KIND:-claude}"' in hook

    installed_hook = (
        _ROOT / "skills" / "auto-capture" / "scripts" / "auto-capture-stop.sh"
    ).read_text()
    assert 'SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"' in installed_hook
    assert 'HELPER="${MK_AUTOCAPTURE_HELPER:-$SCRIPT_DIR/auto_capture.py}"' in installed_hook
    assert installed_hook.count("PYTHONDONTWRITEBYTECODE=1") == 2
