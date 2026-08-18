from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "skills"
    / "info-intake-machinery"
    / "scripts"
    / "run_projection_with_ollama.py"
)
SPEC = importlib.util.spec_from_file_location("run_projection_with_ollama", SCRIPT)
assert SPEC and SPEC.loader
OLLAMA_RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OLLAMA_RUNNER)

REAL_PURPOSE = (
    "the important thing the intake is for is the description in the red "
    "rectangles, but each description is related through its arrow to the "
    "element in the page underneath it came from"
)


class _Response:
    def __init__(self, value: dict[str, object]) -> None:
        self._body = json.dumps(value).encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_ollama_input_constrains_each_choice_and_preserves_rejection_feedback(
    tmp_path: Path,
) -> None:
    image = tmp_path / "region.png"
    image.write_bytes(b"immutable-image")
    requests: list[dict[str, object]] = []
    responses = iter([
        {"models": [{"name": "qwen3-vl:30b-a3b-instruct"}]},
        {"message": {"content": json.dumps({"answer": "not-an-option"})}},
        {"message": {"content": json.dumps({"answer": "readable"})}},
    ])

    def open_request(request: object, *, timeout: float) -> _Response:
        assert timeout == 120.0
        data = getattr(request, "data", None)
        if data is not None:
            requests.append(json.loads(data))
        return _Response(next(responses))

    model = OLLAMA_RUNNER.OllamaInterviewInput(
        model="qwen3-vl:30b-a3b-instruct",
        attachments=(image,),
        opener=open_request,
    )
    prompt = (
        "Question: Is this element readable?\n"
        "Answer type: choice\n"
        "Allowed values: readable, gap\n"
        "Answer: "
    )

    assert model(prompt) == "not-an-option"
    model.record_feedback(
        "Invalid answer: choose one of: readable, gap"
    )
    assert model(prompt) == "readable"

    first, second = requests
    assert first["format"]["properties"]["answer"] == {
        "enum": ["readable", "gap"],
        "type": "string",
    }
    assert first["messages"][-1]["images"]
    assert "Invalid answer: choose one of: readable, gap" in (
        second["messages"][-1]["content"]
    )
    assert first["think"] is False
    assert first["options"]["temperature"] == 0


def test_ollama_input_answers_provider_metadata_without_model_inference() -> None:
    def unexpected_request(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("provider metadata must not invoke the model")

    model = OLLAMA_RUNNER.OllamaInterviewInput(
        model="qwen3-vl:30b-a3b-instruct",
        attachments=(),
        opener=unexpected_request,
    )

    assert model(
        "Question id: reader_model\n"
        "Question: Which model is inspecting the frozen source?\n"
        "Answer type: string\n"
        "Answer: "
    ) == "qwen3-vl:30b-a3b-instruct"
    assert model(
        "Question id: reader_harness\n"
        "Question: Which harness is running this interview?\n"
        "Answer type: string\n"
        "Answer: "
    ) == "ollama-local-interview"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:11434",
        "http://example.com:11434",
        "http://127.0.0.1:11434/unexpected",
        "http://user@127.0.0.1:11434",
    ],
)
def test_ollama_input_rejects_non_loopback_or_ambiguous_endpoints(
    endpoint: str,
) -> None:
    with pytest.raises(OLLAMA_RUNNER.ProviderError):
        OLLAMA_RUNNER.OllamaInterviewInput(
            model="qwen3-vl:30b-a3b-instruct",
            attachments=(),
            endpoint=endpoint,
        )


def test_drive_one_region_uses_exact_saved_binding_and_requires_one_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "intake"
    journal = work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
    crop = work / "region.png"
    guide = work / "region.ownership.png"
    journal.parent.mkdir(parents=True)
    journal.write_text("", encoding="utf-8")
    crop.write_bytes(b"crop")
    guide.write_bytes(b"guide")
    counts = iter([3, 4])
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        OLLAMA_RUNNER.codex_runner,
        "load_request",
        lambda _work: (
            (crop, guide),
            [
                "python",
                "start_intake.py",
                "--work",
                str(work),
                "--projection-region-id",
                "region-r02-c01",
                "--run-projection-interview",
            ],
        ),
    )
    monkeypatch.setattr(
        OLLAMA_RUNNER.codex_runner,
        "_projection_region_journal",
        lambda _work, _command: journal,
    )
    monkeypatch.setattr(
        OLLAMA_RUNNER.codex_runner,
        "_projection_region_outcome_count",
        lambda _journal: next(counts),
    )

    class _Input:
        def __init__(self, **kwargs: object) -> None:
            captured["client"] = kwargs

        def __call__(self, _prompt: str) -> str:
            return "no"

        def record_feedback(self, message: str) -> None:
            captured.setdefault("feedback", []).append(message)

    def run_interview(selected_work: Path, **kwargs: object) -> dict[str, object]:
        captured["work"] = selected_work
        captured["run"] = kwargs
        return {
            "status": "waiting_for_model",
            "stopped": "projection_region_step_complete",
            "completed_region_id": "region-r02-c01",
        }

    monkeypatch.setattr(OLLAMA_RUNNER, "OllamaInterviewInput", _Input)
    monkeypatch.setattr(
        OLLAMA_RUNNER.start_intake,
        "run_first_projection_interview",
        run_interview,
    )

    result = OLLAMA_RUNNER.drive_one_region(
        work,
        model="qwen3-vl:30b-a3b-instruct",
    )

    assert result["completed_region_id"] == "region-r02-c01"
    assert captured["client"]["attachments"] == (crop, guide)
    assert captured["run"]["expected_region_id"] == "region-r02-c01"
    assert captured["run"]["region_binding_required"] is True
    assert captured["run"]["single_region"] is True


def test_drive_one_region_rejects_stale_or_unbound_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        OLLAMA_RUNNER.codex_runner,
        "load_request",
        lambda _work: (
            tmp_path / "region.png",
            ["python", "start_intake.py", "--run-projection-interview"],
        ),
    )

    with pytest.raises(
        OLLAMA_RUNNER.LaunchError,
        match="exactly one active region",
    ):
        OLLAMA_RUNNER.drive_one_region(
            tmp_path,
            model="qwen3-vl:30b-a3b-instruct",
        )


def test_real_interview_engine_rejects_invalid_choice_then_records_one_region(
    tmp_path: Path,
) -> None:
    work = tmp_path / "intake"
    supplied = tmp_path / "source.png"
    Image.new("RGB", (40, 40), "white").save(supplied, format="PNG")
    start = OLLAMA_RUNNER.start_intake
    opening = "There is a new intake"
    start.drive(work, opening)
    start.drive(work, opening, REAL_PURPOSE)
    purpose_answers = iter([
        "test-reader",
        "pytest",
        "yes",
        "The requested descriptions and relationships are explicit.",
        REAL_PURPOSE,
    ])
    purpose_result = start.run_purpose_interview(
        work,
        input_fn=lambda _prompt: next(purpose_answers),
        output_fn=lambda _message: None,
    )
    assert purpose_result["stopped"] == "awaiting_first_source"
    assert start.drive(work, opening, REAL_PURPOSE, supplied)["status"] == (
        "ready_for_projection"
    )
    waiting = start.drive(
        work, opening, REAL_PURPOSE, project_source=True,
    )
    assert waiting["stopped"] == "interviewing_first_projection"

    answers = iter([
        "not-an-option",
        "no",
    ])
    response_count = 0

    def open_request(request: object, *, timeout: float) -> _Response:
        nonlocal response_count
        assert timeout == 120.0
        if getattr(request, "data", None) is None:
            return _Response({
                "models": [{"name": "qwen3-vl:30b-a3b-instruct"}],
            })
        response_count += 1
        return _Response({
            "message": {"content": json.dumps({"answer": next(answers)})},
        })

    result = OLLAMA_RUNNER.drive_one_region(
        work,
        model="qwen3-vl:30b-a3b-instruct",
        opener=open_request,
    )

    assert result["completed_region_id"] == "region-r01-c01"
    assert response_count == 2
    journal_path = (
        work / "projection-interviews" / "attempt-000001" / "interview.jsonl"
    )
    entries = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
    ]
    rejected = [
        entry for entry in entries
        if entry["event"] == "answer_recorded" and not entry["accepted"]
    ]
    assert [(entry["raw"], entry["error"]) for entry in rejected] == [
        (
            "not-an-option",
            "region_element_more: choose one of: yes, no, gap",
        ),
    ]
    assert sum(
        entry["event"] == "region_outcome_recorded" for entry in entries
    ) == 1
    state, pending, completed = (
        OLLAMA_RUNNER.codex_runner.projection_interview._replay(
            entries,
            purpose=REAL_PURPOSE,
            contract=OLLAMA_RUNNER.codex_runner.projection_interview.CONTRACT,
        )
    )
    assert pending is None
    assert completed is False
    assert [item["region_id"] for item in state["region_outcomes"]] == [
        "region-r01-c01",
    ]
