"""Tests for the automatic session-close auto-capture helper (#2 option 1)."""
import importlib.util
import json
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "working-agreement" / "auto_capture.py"
_spec = importlib.util.spec_from_file_location("auto_capture", _MOD)
ac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ac)


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
