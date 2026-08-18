from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import local_multimodal_model_benchmark as benchmark


class FakeOllama:
    def __init__(
        self,
        *,
        installed: tuple[str, ...] = ("gemma4:26b-mlx",),
        content: str = '{"items":[{"label":"Column AC"}],"complete":true}',
        thinking: str | None = None,
    ) -> None:
        self.installed = list(installed)
        self.content = content
        self.thinking = thinking
        self.calls: list[tuple[str, object]] = []

    def version(self) -> str:
        self.calls.append(("version", None))
        return "0.31.1"

    def tags(self) -> list[str]:
        self.calls.append(("tags", None))
        return list(self.installed)

    def pull(self, model: str) -> None:
        self.calls.append(("pull", model))
        self.installed.append(model)

    def chat(
        self,
        *,
        model: str,
        prompt: str,
        images: list[str],
        response_schema: dict[str, object],
        options: dict[str, object],
        think: bool,
    ) -> dict[str, object]:
        self.calls.append(("chat", {
            "model": model,
            "prompt": prompt,
            "images": images,
            "response_schema": response_schema,
            "options": options,
            "think": think,
        }))
        message = {"content": self.content}
        if self.thinking is not None:
            message["thinking"] = self.thinking
        return {
            "message": message,
            "total_duration": 2_000_000_000,
            "load_duration": 500_000_000,
            "prompt_eval_count": 512,
            "prompt_eval_duration": 1_000_000_000,
            "eval_count": 40,
            "eval_duration": 400_000_000,
            "done": True,
            "done_reason": "stop",
        }


def _spec(tmp_path: Path, source: Path, **overrides: object) -> Path:
    output = tmp_path / "evidence.json"
    value: dict[str, object] = {
        "schema_version": 1,
        "model": "gemma4:26b-mlx",
        "endpoint": "http://127.0.0.1:11434",
        "pull_if_missing": True,
        "think": False,
        "timeout_seconds": 600,
        "output_path": str(output),
        "options": {"temperature": 0},
        "cases": [{
            "id": "annotation-map",
            "prompt": "Return every visible annotation label as structured JSON.",
            "source_files": [str(source)],
            "response_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["items", "complete"],
                "properties": {
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["label"],
                            "properties": {"label": {"type": "string"}},
                        },
                    },
                    "complete": {"type": "boolean"},
                },
            },
        }],
    }
    value.update(overrides)
    path = tmp_path / "benchmark-spec.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_existing_model_runs_one_case_and_writes_auditable_evidence(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"real-image-bytes")
    spec = _spec(tmp_path, source)
    client = FakeOllama()

    result = benchmark.run_benchmark(spec, client=client)

    assert result["status"] == "passed"
    assert result["model"] == "gemma4:26b-mlx"
    assert result["pulled_model"] is False
    assert result["models_before"] == ["gemma4:26b-mlx"]
    assert result["models_after"] == ["gemma4:26b-mlx"]
    assert result["spec"]["sha256"] == benchmark.sha256_file(spec)
    case = result["cases"][0]
    assert case["response_json"]["items"][0]["label"] == "Column AC"
    assert case["source_files"] == [{
        "path": str(source.resolve()),
        "sha256": benchmark.sha256_file(source),
        "size_bytes": len(b"real-image-bytes"),
    }]
    assert case["metrics"]["total_duration_ns"] == 2_000_000_000
    assert result["think"] is False
    chat = next(payload for name, payload in client.calls if name == "chat")
    assert chat["think"] is False
    assert json.loads((tmp_path / "evidence.json").read_text()) == result
    assert not any(name == "pull" for name, _ in client.calls)


def test_missing_model_is_pulled_without_removing_existing_models(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image")
    spec = _spec(tmp_path, source)
    client = FakeOllama(installed=("existing:model",))

    result = benchmark.run_benchmark(spec, client=client)

    assert result["pulled_model"] is True
    assert result["models_before"] == ["existing:model"]
    assert result["models_after"] == ["existing:model", "gemma4:26b-mlx"]
    assert ("pull", "gemma4:26b-mlx") in client.calls


def test_missing_source_fails_before_contacting_ollama_and_records_failure(tmp_path: Path) -> None:
    source = tmp_path / "missing.png"
    spec = _spec(tmp_path, source)
    client = FakeOllama()

    with pytest.raises(benchmark.BenchmarkError, match="source-file-missing"):
        benchmark.run_benchmark(spec, client=client)

    evidence = json.loads((tmp_path / "evidence.json").read_text())
    assert evidence["status"] == "failed"
    assert evidence["error"]["code"] == "source-file-missing"
    assert client.calls == []


def test_non_loopback_endpoint_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"image")
    spec = _spec(tmp_path, source, endpoint="https://models.example.com")

    with pytest.raises(benchmark.BenchmarkError, match="endpoint-not-loopback"):
        benchmark.run_benchmark(spec, client=FakeOllama())


def test_malformed_model_json_is_retained_as_failure_evidence(tmp_path: Path) -> None:
    source = tmp_path / "source.webp"
    source.write_bytes(b"image")
    spec = _spec(tmp_path, source)
    client = FakeOllama(content="not JSON")

    with pytest.raises(benchmark.BenchmarkError, match="model-response-not-json"):
        benchmark.run_benchmark(spec, client=client)

    evidence = json.loads((tmp_path / "evidence.json").read_text())
    assert evidence["status"] == "failed"
    assert evidence["error"]["code"] == "model-response-not-json"
    assert evidence["cases"][0]["response_raw"] == "not JSON"


def test_separate_thinking_channel_is_retained_as_failure_evidence(tmp_path: Path) -> None:
    source = tmp_path / "source.webp"
    source.write_bytes(b"image")
    spec = _spec(tmp_path, source, think=True)
    client = FakeOllama(content="", thinking="I am inspecting the annotations.")

    with pytest.raises(benchmark.BenchmarkError, match="model-response-not-json"):
        benchmark.run_benchmark(spec, client=client)

    case = json.loads((tmp_path / "evidence.json").read_text())["cases"][0]
    assert case["thinking_raw"] == "I am inspecting the annotations."
    assert case["thinking_sha256"] == benchmark.sha256_bytes(
        b"I am inspecting the annotations."
    )
    assert case["thinking_length_chars"] == 32


def test_model_json_that_breaks_requested_schema_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.jpeg"
    source.write_bytes(b"image")
    spec = _spec(tmp_path, source)
    client = FakeOllama(content='{"items":[],"complete":"yes"}')

    with pytest.raises(benchmark.BenchmarkError, match="model-response-schema-invalid"):
        benchmark.run_benchmark(spec, client=client)

    evidence = json.loads((tmp_path / "evidence.json").read_text())
    assert evidence["error"]["code"] == "model-response-schema-invalid"


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"image")
    spec = _spec(tmp_path, source)
    output = tmp_path / "evidence.json"
    output.write_text("immutable", encoding="utf-8")

    with pytest.raises(benchmark.BenchmarkError, match="output-path-already-exists"):
        benchmark.run_benchmark(spec, client=FakeOllama())

    assert output.read_text() == "immutable"


def test_no_argument_entrypoint_delegates_to_code_controlled_intake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(
        benchmark,
        "_launch_registered_intake",
        lambda: calls.append(True) or 23,
    )

    assert benchmark.main([]) == 23
    assert calls == [True]
