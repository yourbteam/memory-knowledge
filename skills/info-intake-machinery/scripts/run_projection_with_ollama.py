#!/usr/bin/env python3
"""Answer one bound Info Intake projection region through local Ollama."""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable


def _load_sibling(name: str, filename: str) -> object:
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().with_name(filename),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{filename} is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


codex_runner = _load_sibling(
    "info_intake_codex_runner_for_ollama", "run_projection_with_codex.py",
)
start_intake = _load_sibling(
    "info_intake_start_for_ollama", "start_intake.py",
)


class ProviderError(ValueError):
    """The configured local model provider cannot supply a valid answer."""


class LaunchError(ValueError):
    """The saved intake cannot execute one region through this provider."""


def _validated_endpoint(endpoint: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(endpoint)
        _ = parsed.port
    except ValueError as error:
        raise ProviderError("the Ollama endpoint is invalid") from error
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderError(
            "the Ollama endpoint must be an uncredentialed loopback HTTP origin"
        )
    return endpoint.rstrip("/")


def _answer_schema(prompt: str) -> dict[str, object]:
    answer_type: str | None = None
    choices: list[str] | None = None
    minimum: int | None = None
    maximum: int | None = None
    for line in prompt.splitlines():
        if line.startswith("Answer type: "):
            answer_type = line.removeprefix("Answer type: ").strip()
        elif line.startswith("Allowed values: "):
            choices = [
                item.strip()
                for item in line.removeprefix("Allowed values: ").split(",")
                if item.strip()
            ]
        elif line.startswith("Allowed range: "):
            parts = line.removeprefix("Allowed range: ").split(" through ")
            if len(parts) == 2:
                try:
                    minimum, maximum = (int(item.strip()) for item in parts)
                except ValueError as error:
                    raise ProviderError("the interview integer range is invalid") from error
    if answer_type == "choice" and choices:
        answer: dict[str, object] = {"type": "string", "enum": choices}
    elif answer_type == "integer" and minimum is not None and maximum is not None:
        answer = {
            "type": "integer",
            "minimum": minimum,
            "maximum": maximum,
        }
    elif answer_type == "string":
        answer = {"type": "string", "minLength": 1}
    else:
        raise ProviderError("the code-controlled interview answer contract is missing")
    return {
        "type": "object",
        "properties": {"answer": answer},
        "required": ["answer"],
        "additionalProperties": False,
    }


def _question_id(prompt: str) -> str | None:
    for line in prompt.splitlines():
        if line.startswith("Question id: "):
            value = line.removeprefix("Question id: ").strip()
            return value or None
    return None


class OllamaInterviewInput:
    """Translate one rendered code question into one schema-bound Ollama answer."""

    def __init__(
        self,
        *,
        model: str,
        attachments: tuple[Path, ...],
        endpoint: str = "http://127.0.0.1:11434",
        timeout: float = 120.0,
        num_ctx: int = 32768,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        if not model.strip():
            raise ProviderError("an installed Ollama model name is required")
        self.model = model.strip()
        self.attachments = tuple(Path(path).resolve() for path in attachments)
        self.endpoint = _validated_endpoint(endpoint)
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._opener = opener
        self._model_checked = False
        self._history: list[dict[str, str]] = []
        self._feedback: list[str] = []

    def _request(self, path: str, payload: dict[str, object] | None = None) -> object:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if data is None else "POST",
        )
        try:
            response_context = self._opener(request, timeout=self.timeout)
            with response_context as response:
                body = response.read()
        except (OSError, urllib.error.URLError) as error:
            raise ProviderError(f"Ollama request failed: {error}") from error
        try:
            return json.loads(body)
        except (TypeError, json.JSONDecodeError) as error:
            raise ProviderError("Ollama returned invalid JSON") from error

    def _ensure_model_installed(self) -> None:
        if self._model_checked:
            return
        value = self._request("/api/tags")
        models = value.get("models") if isinstance(value, dict) else None
        installed = {
            candidate
            for item in models if isinstance(item, dict)
            for candidate in (item.get("name"), item.get("model"))
            if isinstance(candidate, str)
        } if isinstance(models, list) else set()
        if self.model not in installed:
            raise ProviderError(
                f"Ollama model is not installed: {self.model}; no download was attempted"
            )
        self._model_checked = True

    def _encoded_images(self) -> list[str]:
        encoded: list[str] = []
        for attachment in self.attachments:
            try:
                encoded.append(base64.b64encode(attachment.read_bytes()).decode("ascii"))
            except OSError as error:
                raise ProviderError(
                    f"the immutable model attachment is unavailable: {attachment}"
                ) from error
        return encoded

    def record_feedback(self, message: str) -> None:
        if message:
            self._feedback.append(message)

    def __call__(self, prompt: str) -> str:
        question_id = _question_id(prompt)
        if question_id == "reader_model":
            return self.model
        if question_id == "reader_harness":
            return "ollama-local-interview"
        self._ensure_model_installed()
        schema = _answer_schema(prompt)
        feedback = ""
        if self._feedback:
            feedback = (
                "\n\nDeterministic controller feedback from the previous answer:\n"
                + "\n".join(self._feedback)
            )
            self._feedback.clear()
        user_content = prompt + feedback
        current: dict[str, object] = {
            "role": "user",
            "content": user_content,
            "images": self._encoded_images(),
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer exactly one code-controlled information-intake "
                        "question using the attached evidence. Return only the "
                        "requested JSON object. For choices, select exactly one "
                        "allowed value. Do not invent additional questions or fields."
                    ),
                },
                *self._history,
                current,
            ],
            "format": schema,
            "options": {"num_ctx": self.num_ctx, "temperature": 0},
            "think": False,
            "stream": False,
        }
        value = self._request("/api/chat", payload)
        message = value.get("message") if isinstance(value, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ProviderError("Ollama response lost its message content")
        try:
            answer_object = json.loads(content)
        except json.JSONDecodeError as error:
            raise ProviderError("Ollama answer is not valid JSON") from error
        if (
            not isinstance(answer_object, dict)
            or set(answer_object) != {"answer"}
            or isinstance(answer_object["answer"], bool)
            or not isinstance(answer_object["answer"], (str, int))
        ):
            raise ProviderError("Ollama answer does not match the one-answer envelope")
        answer = answer_object["answer"]
        self._history.extend([
            {"role": "user", "content": user_content},
            {
                "role": "assistant",
                "content": json.dumps({"answer": answer}, separators=(",", ":")),
            },
        ])
        return str(answer)


def _bound_region_id(command: list[str]) -> str:
    if not command or command[-1] != "--run-projection-interview":
        raise LaunchError("the saved request is not a projection interview")
    positions = [
        index for index, value in enumerate(command)
        if value == "--projection-region-id"
    ]
    if (
        len(positions) != 1
        or positions[0] + 1 >= len(command)
        or "--projection-obligation-id" in command
    ):
        raise LaunchError("the saved request is not bound to exactly one active region")
    region_id = command[positions[0] + 1]
    if not region_id or region_id.startswith("--"):
        raise LaunchError("the saved request is not bound to exactly one active region")
    return region_id


def drive_one_region(
    work: Path,
    *,
    model: str,
    endpoint: str = "http://127.0.0.1:11434",
    timeout: float = 120.0,
    num_ctx: int = 32768,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> dict[str, object]:
    """Add exactly one outcome for the intake's currently bound region."""

    selected_work = work.expanduser().resolve()
    try:
        attachment, command = codex_runner.load_request(selected_work)
        region_id = _bound_region_id(command)
        journal = codex_runner._projection_region_journal(selected_work, command)
        if journal is None:
            raise LaunchError("the saved request lost its projection journal")
        outcomes_before = codex_runner._projection_region_outcome_count(journal)
    except codex_runner.LaunchError as error:
        raise LaunchError(str(error)) from error
    attachments = attachment if isinstance(attachment, tuple) else (attachment,)
    model_input = OllamaInterviewInput(
        model=model,
        attachments=attachments,
        endpoint=endpoint,
        timeout=timeout,
        num_ctx=num_ctx,
        opener=opener,
    )
    result = start_intake.run_first_projection_interview(
        selected_work,
        input_fn=model_input,
        output_fn=model_input.record_feedback,
        single_region=True,
        expected_region_id=region_id,
        region_binding_required=True,
    )
    if (
        result.get("status") != "waiting_for_model"
        or result.get("stopped") != "projection_region_step_complete"
        or result.get("completed_region_id") != region_id
    ):
        detail = result.get("why") if isinstance(result, dict) else None
        raise LaunchError(
            f"the bound region did not complete{': ' + str(detail) if detail else ''}"
        )
    outcomes_after = codex_runner._projection_region_outcome_count(journal)
    if outcomes_after - outcomes_before != 1:
        raise LaunchError("the local model stage did not add exactly one region outcome")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--num-ctx", type=int, default=32768)
    args = parser.parse_args()
    try:
        result = drive_one_region(
            args.work,
            model=args.model,
            endpoint=args.endpoint,
            timeout=args.timeout,
            num_ctx=args.num_ctx,
        )
    except (LaunchError, ProviderError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
