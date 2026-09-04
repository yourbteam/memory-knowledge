#!/usr/bin/env python3
"""Run one immutable, local-only multimodal model benchmark from a JSON spec."""

from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SPEC_KEYS = {
    "schema_version", "model", "endpoint", "pull_if_missing",
    "think", "timeout_seconds", "output_path", "options", "cases",
}
CASE_KEYS = {"id", "prompt", "source_files", "response_schema"}
SCHEMA_KEYS = {
    "type", "properties", "required", "items", "enum", "minItems",
    "maxItems", "minLength", "maxLength", "additionalProperties",
}
SCHEMA_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}
MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*")
CASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class BenchmarkError(RuntimeError):
    """The benchmark cannot produce passed evidence."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if detail is None else f"{code}:{detail}")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise BenchmarkError(code)
    return value.strip()


def _loopback_endpoint(value: Any) -> str:
    endpoint = _text(value, "endpoint-invalid")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.hostname is None
    ):
        raise BenchmarkError("endpoint-not-loopback")
    hostname = parsed.hostname.casefold()
    try:
        is_loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        is_loopback = hostname == "localhost"
    if not is_loopback:
        raise BenchmarkError("endpoint-not-loopback")
    try:
        port = parsed.port or 11434
    except ValueError as exc:
        raise BenchmarkError("endpoint-invalid") from exc
    host_for_url = f"[{hostname}]" if ":" in hostname else hostname
    return f"http://{host_for_url}:{port}"


def _validate_schema_definition(schema: Any, path: str = "$") -> dict[str, Any]:
    if not isinstance(schema, dict) or set(schema) - SCHEMA_KEYS:
        raise BenchmarkError("response-schema-invalid", path)
    schema_type = schema.get("type")
    if schema_type not in SCHEMA_TYPES:
        raise BenchmarkError("response-schema-invalid", f"{path}.type")
    normalized = dict(schema)
    if "enum" in schema and (
        not isinstance(schema["enum"], list) or not schema["enum"]
    ):
        raise BenchmarkError("response-schema-invalid", f"{path}.enum")
    if schema_type == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if (
            not isinstance(properties, dict)
            or any(not isinstance(key, str) or not key for key in properties)
            or not isinstance(required, list)
            or any(not isinstance(key, str) or key not in properties for key in required)
            or len(required) != len(set(required))
            or not isinstance(schema.get("additionalProperties", True), bool)
        ):
            raise BenchmarkError("response-schema-invalid", path)
        normalized["properties"] = {
            key: _validate_schema_definition(value, f"{path}.properties.{key}")
            for key, value in properties.items()
        }
    elif any(key in schema for key in ("properties", "required", "additionalProperties")):
        raise BenchmarkError("response-schema-invalid", path)
    if schema_type == "array":
        if "items" not in schema:
            raise BenchmarkError("response-schema-invalid", f"{path}.items")
        normalized["items"] = _validate_schema_definition(schema["items"], f"{path}.items")
        for key in ("minItems", "maxItems"):
            if key in schema and (
                not isinstance(schema[key], int)
                or isinstance(schema[key], bool)
                or schema[key] < 0
            ):
                raise BenchmarkError("response-schema-invalid", f"{path}.{key}")
        if schema.get("minItems", 0) > schema.get("maxItems", float("inf")):
            raise BenchmarkError("response-schema-invalid", path)
    elif any(key in schema for key in ("items", "minItems", "maxItems")):
        raise BenchmarkError("response-schema-invalid", path)
    if schema_type == "string":
        for key in ("minLength", "maxLength"):
            if key in schema and (
                not isinstance(schema[key], int)
                or isinstance(schema[key], bool)
                or schema[key] < 0
            ):
                raise BenchmarkError("response-schema-invalid", f"{path}.{key}")
        if schema.get("minLength", 0) > schema.get("maxLength", float("inf")):
            raise BenchmarkError("response-schema-invalid", path)
    elif any(key in schema for key in ("minLength", "maxLength")):
        raise BenchmarkError("response-schema-invalid", path)
    return normalized


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return value is None


def _validate_response(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    expected = str(schema["type"])
    if not _matches_type(value, expected):
        raise BenchmarkError("model-response-schema-invalid", f"{path}:expected-{expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise BenchmarkError("model-response-schema-invalid", f"{path}:enum")
    if expected == "object":
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                raise BenchmarkError("model-response-schema-invalid", f"{path}.{key}:required")
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                raise BenchmarkError(
                    "model-response-schema-invalid",
                    f"{path}:additional-{min(extras)}",
                )
        for key, child in properties.items():
            if key in value:
                _validate_response(value[key], child, f"{path}.{key}")
    elif expected == "array":
        minimum = schema.get("minItems", 0)
        maximum = schema.get("maxItems")
        if len(value) < minimum or (maximum is not None and len(value) > maximum):
            raise BenchmarkError("model-response-schema-invalid", f"{path}:item-count")
        for index, item in enumerate(value):
            _validate_response(item, schema["items"], f"{path}[{index}]")
    elif expected == "string":
        minimum = schema.get("minLength", 0)
        maximum = schema.get("maxLength")
        if len(value) < minimum or (maximum is not None and len(value) > maximum):
            raise BenchmarkError("model-response-schema-invalid", f"{path}:length")


def _source_evidence(raw_paths: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(raw_paths, list) or not raw_paths:
        raise BenchmarkError("source-files-required")
    evidence: list[dict[str, Any]] = []
    encoded: list[str] = []
    identities: set[Path] = set()
    for raw_path in raw_paths:
        path_text = _text(raw_path, "source-file-invalid")
        path = Path(path_text).expanduser()
        if not path.is_absolute():
            raise BenchmarkError("source-file-not-absolute", path_text)
        resolved = path.resolve()
        if resolved in identities:
            raise BenchmarkError("source-file-duplicate", str(resolved))
        identities.add(resolved)
        if not resolved.is_file():
            raise BenchmarkError("source-file-missing", str(resolved))
        if resolved.suffix.casefold() not in IMAGE_SUFFIXES:
            raise BenchmarkError("source-file-type-unsupported", str(resolved))
        raw = resolved.read_bytes()
        evidence.append({
            "path": str(resolved),
            "sha256": sha256_bytes(raw),
            "size_bytes": len(raw),
        })
        encoded.append(base64.b64encode(raw).decode("ascii"))
    return evidence, encoded


def _normalize_spec(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != SPEC_KEYS or raw.get("schema_version") != 1:
        raise BenchmarkError("benchmark-spec-shape-invalid")
    model = _text(raw.get("model"), "model-invalid")
    if MODEL_RE.fullmatch(model) is None:
        raise BenchmarkError("model-invalid")
    pull_if_missing = raw.get("pull_if_missing")
    think = raw.get("think")
    timeout_seconds = raw.get("timeout_seconds")
    if not isinstance(pull_if_missing, bool):
        raise BenchmarkError("pull-if-missing-invalid")
    if not isinstance(think, bool):
        raise BenchmarkError("think-invalid")
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or not 1 <= timeout_seconds <= 3600
    ):
        raise BenchmarkError("timeout-seconds-invalid")
    output_text = _text(raw.get("output_path"), "output-path-invalid")
    output_path = Path(output_text).expanduser()
    if not output_path.is_absolute():
        raise BenchmarkError("output-path-not-absolute")
    options = raw.get("options")
    if not isinstance(options, dict) or any(
        not isinstance(key, str) or not key for key in options
    ):
        raise BenchmarkError("options-invalid")
    try:
        json.dumps(options, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise BenchmarkError("options-invalid") from exc
    raw_cases = raw.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise BenchmarkError("cases-required")
    cases: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict) or set(raw_case) != CASE_KEYS:
            raise BenchmarkError("benchmark-case-shape-invalid")
        case_id = _text(raw_case.get("id"), "case-id-invalid")
        if CASE_ID_RE.fullmatch(case_id) is None or case_id in case_ids:
            raise BenchmarkError("case-id-invalid", case_id)
        case_ids.add(case_id)
        source_files, encoded_images = _source_evidence(raw_case.get("source_files"))
        cases.append({
            "id": case_id,
            "prompt": _text(raw_case.get("prompt"), "case-prompt-invalid"),
            "source_files": source_files,
            "encoded_images": encoded_images,
            "response_schema": _validate_schema_definition(raw_case.get("response_schema")),
        })
    return {
        "schema_version": 1,
        "model": model,
        "endpoint": _loopback_endpoint(raw.get("endpoint")),
        "pull_if_missing": pull_if_missing,
        "think": think,
        "timeout_seconds": timeout_seconds,
        "output_path": output_path.resolve(),
        "options": dict(options),
        "cases": cases,
    }


def _atomic_create_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False,
    ) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise BenchmarkError("output-path-already-exists", str(path)) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class OllamaClient:
    """Small stdlib client restricted by the caller to a loopback endpoint."""

    def __init__(self, endpoint: str, timeout_seconds: int) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def _request(self, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        data = None
        method = "GET"
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, allow_nan=False).encode("utf-8")
            method = "POST"
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.endpoint}{path}", data=data, headers=headers, method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read(1024).decode("utf-8", errors="replace")
            raise BenchmarkError("ollama-http-error", f"{exc.code}:{detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BenchmarkError("ollama-unavailable", str(exc)) from exc
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BenchmarkError("ollama-response-not-json", path) from exc
        if not isinstance(value, dict):
            raise BenchmarkError("ollama-response-shape-invalid", path)
        return value

    def version(self) -> str:
        return _text(self._request("/api/version").get("version"), "ollama-version-invalid")

    def tags(self) -> list[str]:
        models = self._request("/api/tags").get("models")
        if not isinstance(models, list):
            raise BenchmarkError("ollama-tags-invalid")
        names: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                raise BenchmarkError("ollama-tags-invalid")
            raw_name = item.get("name", item.get("model"))
            names.append(_text(raw_name, "ollama-tags-invalid"))
        return names

    def pull(self, model: str) -> None:
        response = self._request("/api/pull", {"model": model, "stream": False})
        if response.get("status") != "success":
            raise BenchmarkError("ollama-pull-incomplete")

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
        return self._request("/api/chat", {
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": images}],
            "format": response_schema,
            "options": options,
            "think": think,
            "stream": False,
        })


def _model_names(values: list[str]) -> list[str]:
    return sorted(set(values))


def _case_evidence(case: Mapping[str, Any], response: Mapping[str, Any], wall_seconds: float) -> dict[str, Any]:
    message = response.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise BenchmarkError("ollama-chat-response-invalid")
    content = message["content"]
    metrics = {"wall_seconds": round(wall_seconds, 6)}
    for source_key, evidence_key in (
        ("total_duration", "total_duration_ns"),
        ("load_duration", "load_duration_ns"),
        ("prompt_eval_count", "prompt_eval_count"),
        ("prompt_eval_duration", "prompt_eval_duration_ns"),
        ("eval_count", "eval_count"),
        ("eval_duration", "eval_duration_ns"),
    ):
        value = response.get(source_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[evidence_key] = value
    evidence = {
        "id": case["id"],
        "prompt": case["prompt"],
        "prompt_sha256": sha256_bytes(case["prompt"].encode("utf-8")),
        "source_files": case["source_files"],
        "response_schema": case["response_schema"],
        "response_raw": content,
        "response_sha256": sha256_bytes(content.encode("utf-8")),
        "metrics": metrics,
        "done": response.get("done"),
        "done_reason": response.get("done_reason"),
    }
    thinking = message.get("thinking")
    if thinking is not None:
        if not isinstance(thinking, str):
            raise BenchmarkError("ollama-chat-response-invalid")
        evidence.update({
            "thinking_raw": thinking,
            "thinking_sha256": sha256_bytes(thinking.encode("utf-8")),
            "thinking_length_chars": len(thinking),
        })
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        failure = BenchmarkError("model-response-not-json")
        failure.evidence = evidence  # type: ignore[attr-defined]
        raise failure from exc
    evidence["response_json"] = parsed
    try:
        _validate_response(parsed, case["response_schema"])
    except BenchmarkError as exc:
        exc.evidence = evidence  # type: ignore[attr-defined]
        raise
    return evidence


def run_benchmark(spec_path: Path, *, client: Any | None = None) -> dict[str, Any]:
    resolved_spec = Path(spec_path).expanduser().resolve()
    if not resolved_spec.is_file():
        raise BenchmarkError("benchmark-spec-missing", str(resolved_spec))
    spec_bytes = resolved_spec.read_bytes()
    try:
        raw_spec = json.loads(spec_bytes)
    except json.JSONDecodeError as exc:
        raise BenchmarkError("benchmark-spec-not-json") from exc
    output_path: Path | None = None
    if isinstance(raw_spec, dict) and isinstance(raw_spec.get("output_path"), str):
        candidate = Path(raw_spec["output_path"]).expanduser()
        if candidate.is_absolute():
            output_path = candidate.resolve()
            if output_path.exists():
                raise BenchmarkError("output-path-already-exists", str(output_path))
    started_at = _utc_now()
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "started_at_utc": started_at,
        "spec": {
            "path": str(resolved_spec),
            "sha256": sha256_bytes(spec_bytes),
        },
        "cases": [],
    }
    try:
        spec = _normalize_spec(raw_spec)
        output_path = spec["output_path"]
        if output_path.exists():
            raise BenchmarkError("output-path-already-exists", str(output_path))
        evidence.update({
            "model": spec["model"],
            "endpoint": spec["endpoint"],
            "pull_if_missing": spec["pull_if_missing"],
            "think": spec["think"],
            "options": spec["options"],
        })
        active_client = client or OllamaClient(spec["endpoint"], spec["timeout_seconds"])
        evidence["ollama_version"] = active_client.version()
        models_before = _model_names(active_client.tags())
        evidence["models_before"] = models_before
        if spec["model"] not in models_before:
            if not spec["pull_if_missing"]:
                raise BenchmarkError("model-not-installed", spec["model"])
            active_client.pull(spec["model"])
            evidence["pulled_model"] = True
        else:
            evidence["pulled_model"] = False
        models_after = _model_names(active_client.tags())
        evidence["models_after"] = models_after
        if spec["model"] not in models_after:
            raise BenchmarkError("model-unavailable-after-pull", spec["model"])
        if not set(models_before).issubset(models_after):
            raise BenchmarkError("existing-model-set-changed")
        for case in spec["cases"]:
            started = time.monotonic()
            response = active_client.chat(
                model=spec["model"],
                prompt=case["prompt"],
                images=case["encoded_images"],
                response_schema=case["response_schema"],
                options=spec["options"],
                think=spec["think"],
            )
            try:
                case_result = _case_evidence(case, response, time.monotonic() - started)
            except BenchmarkError as exc:
                partial = getattr(exc, "evidence", None)
                if isinstance(partial, dict):
                    evidence["cases"].append(partial)
                raise
            evidence["cases"].append(case_result)
        evidence["status"] = "passed"
        evidence["finished_at_utc"] = _utc_now()
        _atomic_create_json(output_path, evidence)
        return evidence
    except BenchmarkError as exc:
        evidence["status"] = "failed"
        evidence["finished_at_utc"] = _utc_now()
        evidence["error"] = {"code": exc.code}
        if exc.detail is not None:
            evidence["error"]["detail"] = exc.detail
        if output_path is not None and not output_path.exists():
            _atomic_create_json(output_path, evidence)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, help="Absolute or relative benchmark spec path")
    return parser


def _launch_registered_intake() -> int:
    try:
        from scripts import sequence_intake_launch
    except ModuleNotFoundError:
        import sequence_intake_launch  # type: ignore
    return sequence_intake_launch.main_for_sequence(
        "local-multimodal-model-benchmark", [],
    )


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        return _launch_registered_intake()
    args = _parser().parse_args(values)
    try:
        result = run_benchmark(Path(args.spec))
    except BenchmarkError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "detail": exc.detail}, sort_keys=True))
        return 1
    print(json.dumps({
        "ok": True,
        "status": result["status"],
        "model": result["model"],
        "output_path": json.loads(Path(args.spec).read_text())["output_path"],
        "case_count": len(result["cases"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
