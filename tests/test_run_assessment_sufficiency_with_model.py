from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/info-intake-machinery/scripts/run_assessment_sufficiency_with_model.py"


def _module():
    spec = importlib.util.spec_from_file_location("assessment_sufficiency_runner", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_journal(path: Path, accepted: int, completed: bool = False) -> None:
    module = _module()
    journal = module._journal_module()
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    previous = None
    started = {"sequence": 1, "previous_entry_sha256": None, "event": "assessment_sufficiency_started"}
    started["entry_sha256"] = hashlib.sha256(journal._canonical(started)).hexdigest()
    entries.append(started)
    previous = started["entry_sha256"]
    for number in range(accepted):
        item = {"sequence": len(entries) + 1, "previous_entry_sha256": previous, "event": "unit_answer_recorded", "accepted": True}
        item["entry_sha256"] = hashlib.sha256(journal._canonical(item)).hexdigest()
        entries.append(item); previous = item["entry_sha256"]
    if completed:
        item = {"sequence": len(entries) + 1, "previous_entry_sha256": previous, "event": "assessment_sufficiency_completed"}
        item["entry_sha256"] = hashlib.sha256(journal._canonical(item)).hexdigest(); entries.append(item)
    path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in entries), encoding="utf-8")


def test_codex_argv_contains_one_exact_question_without_controller_command(tmp_path: Path) -> None:
    module = _module()
    question = {
        "unit": {"unit_id": "unit-1"},
        "obligations": [],
        "allowed_verdicts": ["sufficient", "insufficient", "cannot-assess"],
    }

    argv = module.build_structured_codex_argv(
        "/bin/codex", tmp_path, question, tmp_path / "schema.json", tmp_path / "response.json"
    )

    assert argv[:3] == ["/bin/codex", "exec", "--ignore-user-config"]
    assert '"unit_id": "unit-1"' in argv[-1]
    assert "assessment_sufficiency.py" not in argv[-1]


def test_codex_transport_is_schema_bound_and_noninteractive(tmp_path: Path) -> None:
    module = _module()
    schema = tmp_path / "schema.json"
    response = tmp_path / "response.json"
    question = {
        "unit": {"unit_id": "unit-000002"},
        "obligations": [],
        "allowed_verdicts": ["sufficient", "insufficient", "cannot-assess"],
    }

    argv = module.build_structured_codex_argv(
        "/bin/codex", tmp_path, question, schema, response
    )

    assert argv[argv.index("--output-schema") + 1] == str(schema)
    assert argv[argv.index("--output-last-message") + 1] == str(response)
    assert "PTY" not in argv[-1]
    assert "interactive command" not in argv[-1]


def test_run_requires_real_journal_advance(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    charter = tmp_path / "charter.json"; charter.write_text("{}")
    evidence = tmp_path / "evidence.json"; evidence.write_text("{}")
    monkeypatch.setattr(module, "_executable", lambda _client: "/bin/codex")
    fake = SimpleNamespace(
        AssessmentSufficiencyError=ValueError,
        prepare_question=lambda *_args: {
            "status": "question-ready",
            "question": {"unit": {"unit_id": "unit-1"}, "obligations": []},
            "response_schema": {"type": "object"},
        },
    )
    monkeypatch.setattr(module, "_controller_module", lambda: fake)

    with pytest.raises(module.AssessmentSufficiencyLaunchError, match="response.*missing"):
        module.run(charter, evidence, tmp_path / "work", max_units=1, model_run_fn=lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""), environ={"MK_CLIENT_KIND":"codex"})


def test_run_reports_only_verified_exact_progress(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    charter = tmp_path / "charter.json"; charter.write_text("{}")
    evidence = tmp_path / "evidence.json"; evidence.write_text("{}")
    work = tmp_path / "work"
    _write_journal(work / "interview.jsonl", 1)
    monkeypatch.setattr(module, "_executable", lambda _client: "/bin/codex")
    state = {"accepted": 1}

    def prepare(*_args):
        return {
            "status": "question-ready",
            "question": {"unit": {"unit_id": f"unit-{state['accepted'] + 1}"}, "obligations": []},
            "response_schema": {"type": "object"},
        }

    def submit(_charter, _evidence, _work, _raw):
        state["accepted"] += 1
        _write_journal(work / "interview.jsonl", state["accepted"])
        return {"status": "accepted", "accepted_unit_count": state["accepted"]}

    fake = SimpleNamespace(
        AssessmentSufficiencyError=ValueError,
        prepare_question=prepare,
        submit_response=submit,
    )
    monkeypatch.setattr(module, "_controller_module", lambda: fake)

    def advance(argv, **_kwargs):
        response_path = Path(argv[argv.index("--output-last-message") + 1])
        response_path.write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    result = module.run(charter, evidence, work, max_units=2, model_run_fn=advance, environ={"MK_CLIENT_KIND":"codex"})

    assert result["status"] == "paused"
    assert result["accepted_before"] == 1
    assert result["accepted_after"] == 3
    assert result["accepted_this_run"] == 2
