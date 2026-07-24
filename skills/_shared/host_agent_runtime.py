#!/usr/bin/env python3
"""Host-neutral bounded assessment-agent runtime for Codex and Claude.

One small boundary owns host differences: capability probing, argv construction,
bounded execution, structured-output validation, and agent-slot ledger lifecycle.
Assessment roles only — the parent controller remains the sole state writer.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

SCHEMA_VERSION = 1
CODEX_REQUIRED_FLAGS = ("--ephemeral", "--sandbox", "--cd", "--output-schema", "--output-last-message")
# Live claude 2.1.126 --help has no --max-turns; boundedness is carried by --max-budget-usd
# plus the adapter timeout, and --max-turns is emitted only when the probe proves it exists.
CLAUDE_REQUIRED_FLAGS = ("--print", "--output-format", "--json-schema", "--max-budget-usd",
                         "--allowedTools", "--disallowedTools", "--permission-mode", "--no-session-persistence")
CLAUDE_OPTIONAL_FLAGS = ("--max-turns",)
LEDGER_SCRIPT = Path(__file__).with_name("agent_slot_ledger.py")


@dataclass(frozen=True)
class HostCapabilities:
    schema_version: Literal[1]
    host: Literal["codex", "claude"]
    executable: str
    version: str
    help_sha256: str
    supported_flags: tuple[str, ...]
    missing_required_flags: tuple[str, ...]
    available: bool


@dataclass(frozen=True)
class HostAgentRequest:
    schema_version: Literal[1]
    host: Literal["codex", "claude"]
    executable: str
    role: str
    prompt_path: Path
    working_directory: Path
    allowed_read_roots: tuple[Path, ...]
    allowed_tools: tuple[str, ...]
    disallowed_tools: tuple[str, ...]
    timeout_seconds: int
    max_turns: int
    max_budget_usd: Decimal
    output_schema: dict[str, object]
    slot_id: str
    attempt_id: str


@dataclass(frozen=True)
class CompletionEvidence:
    process_terminal: bool
    host_terminal: bool
    ledger_completed: bool
    ledger_closed: bool
    ledger_released: bool


@dataclass(frozen=True)
class HostAgentResult:
    schema_version: Literal[1]
    host: Literal["codex", "claude"]
    role: str
    attempt_id: str
    slot_id: str
    runtime_agent_id: str | None
    session_id: str | None
    status: Literal["SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED",
                    "CAPABILITY_MISSING", "INVALID_OUTPUT", "LEDGER_ERROR"]
    exit_code: int | None
    started_at_utc: str
    completed_at_utc: str
    output: dict[str, object] | None
    output_sha256: str | None
    diagnostic_code: str | None
    completion_evidence: CompletionEvidence
    slot_released: bool


class RequestError(ValueError):
    """The request violates the locked contract; nothing was launched."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_request(request: HostAgentRequest) -> None:
    if request.schema_version != SCHEMA_VERSION: raise RequestError("schema_version must be 1")
    if request.host not in ("codex", "claude"): raise RequestError("host must be codex or claude")
    if not Path(request.executable).is_absolute(): raise RequestError("executable must be absolute")
    if not request.role: raise RequestError("role must be non-empty")
    if not request.prompt_path.is_absolute() or not request.prompt_path.is_file():
        raise RequestError("prompt_path must be an absolute regular file")
    if not request.working_directory.is_absolute() or not request.working_directory.is_dir():
        raise RequestError("working_directory must be an absolute directory")
    if not request.allowed_read_roots or not all(p.is_absolute() and p.is_dir() for p in request.allowed_read_roots):
        raise RequestError("allowed_read_roots must be non-empty absolute directories")
    if request.timeout_seconds <= 0: raise RequestError("timeout_seconds must be positive")
    if request.max_turns <= 0: raise RequestError("max_turns must be positive")
    if request.max_budget_usd <= 0: raise RequestError("max_budget_usd must be positive")
    if not isinstance(request.output_schema, dict): raise RequestError("output_schema must be a JSON Schema object")
    if not request.slot_id: raise RequestError("slot_id must be non-empty")
    if not request.attempt_id: raise RequestError("attempt_id must be non-empty")


def probe_host(executable: str, host: str) -> HostCapabilities:
    if host not in ("codex", "claude"): raise RequestError("host must be codex or claude")
    required = CODEX_REQUIRED_FLAGS if host == "codex" else CLAUDE_REQUIRED_FLAGS
    help_argv = [executable, "exec", "--help"] if host == "codex" else [executable, "--help"]
    version = ""
    help_text = ""
    ok = False
    if Path(executable).is_absolute() and (Path(executable).is_file() or shutil.which(executable)):
        try:
            helped = subprocess.run(help_argv, capture_output=True, text=True, timeout=20)
            help_text = helped.stdout + helped.stderr
            versioned = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=20)
            version = (versioned.stdout + versioned.stderr).strip().splitlines()[0] if (versioned.stdout + versioned.stderr).strip() else ""
            ok = helped.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
    optional = CLAUDE_OPTIONAL_FLAGS if host == "claude" else ()
    supported = tuple(flag for flag in (*required, *optional) if flag in help_text)
    missing = tuple(flag for flag in required if flag not in help_text)
    return HostCapabilities(
        schema_version=1, host=host, executable=executable, version=version,
        help_sha256=hashlib.sha256(help_text.encode()).hexdigest(),
        supported_flags=supported, missing_required_flags=missing,
        available=bool(ok and not missing),
    )


def build_codex_exec_argv(executable: str, working_directory: str | Path, schema_path: str | Path,
                          result_path: str | Path, model: str | None = None) -> list[str]:
    """Single authority for the bounded read-only `codex exec` assessment argv shape."""
    argv = [executable, "exec", "--ephemeral", "--sandbox", "read-only", "--color", "never",
            "--cd", str(working_directory), "--output-schema", str(schema_path),
            "--output-last-message", str(result_path)]
    if model: argv += ["--model", model]
    argv.append("-")
    return argv


def build_claude_print_argv(executable: str, schema_json: str, max_turns: int, max_budget_usd: str,
                            allowed_tools: tuple[str, ...] = (), disallowed_tools: tuple[str, ...] = (),
                            add_dirs: tuple[str, ...] = (), supports_max_turns: bool = False) -> list[str]:
    """Single authority for the bounded `claude --print` assessment argv shape."""
    argv = [executable, "--print", "--output-format", "json", "--json-schema", schema_json,
            "--max-budget-usd", str(max_budget_usd),
            "--permission-mode", "default", "--no-session-persistence"]
    if supports_max_turns: argv[5:5] = ["--max-turns", str(max_turns)]
    if allowed_tools: argv += ["--allowedTools", ",".join(allowed_tools)]
    if disallowed_tools: argv += ["--disallowedTools", ",".join(disallowed_tools)]
    for root in add_dirs: argv += ["--add-dir", str(root)]
    return argv


def build_argv(request: HostAgentRequest, schema_path: Path, codex_result_path: Path | None,
               capabilities: HostCapabilities | None = None) -> list[str]:
    if request.host == "codex":
        return build_codex_exec_argv(request.executable, request.working_directory, schema_path, codex_result_path)
    add_dirs = tuple(str(root) for root in request.allowed_read_roots if root != request.working_directory)
    supports_max_turns = bool(capabilities and "--max-turns" in capabilities.supported_flags)
    return build_claude_print_argv(request.executable, json.dumps(request.output_schema, sort_keys=True),
                                   request.max_turns, str(request.max_budget_usd),
                                   request.allowed_tools, request.disallowed_tools, add_dirs, supports_max_turns)


def schema_violations(schema: dict, value: object, path: str = "$") -> list[str]:
    """Bounded structural JSON-Schema subset: type, required, properties, items, enum."""
    problems: list[str] = []
    kind = schema.get("type")
    kinds = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    if kind == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        problems.append(f"{path}: expected integer")
    elif kind == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        problems.append(f"{path}: expected number")
    elif kind in kinds and not isinstance(value, kinds[kind]):
        problems.append(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: value not in enum")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value: problems.append(f"{path}.{key}: required property missing")
        for key, sub in schema.get("properties", {}).items():
            if key in value: problems += schema_violations(sub, value[key], f"{path}.{key}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            problems += schema_violations(schema["items"], item, f"{path}[{index}]")
    return problems


def _ledger(ledger_path: Path, *args: str) -> None:
    completed = subprocess.run([sys.executable, str(LEDGER_SCRIPT), *args[:1], str(ledger_path), *args[1:]],
                               capture_output=True, text=True, timeout=30)
    if completed.returncode != 0:
        raise RuntimeError(f"ledger {args[0]} failed: exit {completed.returncode}")


def _extract_structured(envelope: dict, schema: dict) -> dict | None:
    for candidate in (envelope.get("structured_output"), envelope.get("result")):
        if isinstance(candidate, str):
            try: candidate = json.loads(candidate)
            except ValueError: candidate = None
        if isinstance(candidate, dict) and not schema_violations(schema, candidate):
            return candidate
    return None


def run_assessment(request: HostAgentRequest, ledger_path: Path) -> HostAgentResult:
    validate_request(request)
    started = _utc_now()
    evidence = {"process_terminal": False, "host_terminal": False,
                "ledger_completed": False, "ledger_closed": False, "ledger_released": False}

    def result(status: str, *, runtime_agent_id=None, session_id=None, exit_code=None,
               output=None, diagnostic_code=None) -> HostAgentResult:
        output_sha = hashlib.sha256(json.dumps(output, sort_keys=True).encode()).hexdigest() if output is not None else None
        return HostAgentResult(
            schema_version=1, host=request.host, role=request.role, attempt_id=request.attempt_id,
            slot_id=request.slot_id, runtime_agent_id=runtime_agent_id, session_id=session_id,
            status=status, exit_code=exit_code, started_at_utc=started, completed_at_utc=_utc_now(),
            output=output, output_sha256=output_sha,
            diagnostic_code=None if status == "SUCCEEDED" else (diagnostic_code or status.lower()),
            completion_evidence=CompletionEvidence(**evidence), slot_released=evidence["ledger_released"])

    capabilities = probe_host(request.executable, request.host)
    if not capabilities.available:
        return result("CAPABILITY_MISSING",
                      diagnostic_code="capability-missing:" + (",".join(capabilities.missing_required_flags) or "executable"))

    status = None
    exit_code = None
    session_id = None
    output = None
    diagnostic = None
    with tempfile.TemporaryDirectory(prefix="host-agent-") as raw:
        temp = Path(raw)
        schema_path = temp / "schema.json"
        schema_path.write_text(json.dumps(request.output_schema, sort_keys=True))
        codex_result = temp / "result.json"
        argv = build_argv(request, schema_path, codex_result, capabilities)
        try:
            with request.prompt_path.open("rb") as prompt_handle:
                completed = subprocess.run(argv, stdin=prompt_handle,
                                           cwd=request.working_directory, capture_output=True, text=True,
                                           timeout=request.timeout_seconds)
            evidence["process_terminal"] = True
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            status, diagnostic = "TIMED_OUT", f"timeout:{request.timeout_seconds}s"
        except KeyboardInterrupt:
            status, diagnostic = "CANCELLED", "caller-cancelled"
        except OSError as exc:
            evidence["process_terminal"] = True
            status, exit_code, diagnostic = "FAILED", None, f"launch-oserror:{type(exc).__name__}"
        if status is None:
            if request.host == "codex":
                if codex_result.is_file():
                    evidence["host_terminal"] = True
                    try: payload = json.loads(codex_result.read_text())
                    except ValueError: payload = None
                    if exit_code == 0 and isinstance(payload, dict) and not schema_violations(request.output_schema, payload):
                        output = payload
            else:
                try: envelope = json.loads(completed.stdout)
                except ValueError: envelope = None
                if isinstance(envelope, dict) and envelope.get("type") == "result":
                    evidence["host_terminal"] = True
                    session_id = envelope.get("session_id")
                    if exit_code == 0 and not envelope.get("is_error"):
                        output = _extract_structured(envelope, request.output_schema)
            if exit_code != 0:
                status, diagnostic = "FAILED", f"exit:{exit_code}"
            elif output is None:
                status, diagnostic = "INVALID_OUTPUT", "structured-output-missing-or-schema-invalid"
            else:
                status = "SUCCEEDED"
    runtime_agent_id = session_id or f"{request.host}-attempt-{request.attempt_id}"
    try:
        _ledger(ledger_path, "bind-agent", "--slot-id", request.slot_id, "--agent-id", runtime_agent_id)
        if status == "SUCCEEDED":
            _ledger(ledger_path, "mark-completed", "--slot-id", request.slot_id)
            evidence["ledger_completed"] = True
        _ledger(ledger_path, "mark-closed", "--slot-id", request.slot_id,
                "--close-evidence", f"host={request.host};status={status};attempt={request.attempt_id}")
        evidence["ledger_closed"] = True
        _ledger(ledger_path, "release", "--slot-id", request.slot_id)
        evidence["ledger_released"] = True
    except RuntimeError as exc:
        return result("LEDGER_ERROR" if status == "SUCCEEDED" else status,
                      runtime_agent_id=runtime_agent_id, session_id=session_id, exit_code=exit_code,
                      output=output, diagnostic_code=f"ledger-lifecycle:{exc}" if status == "SUCCEEDED" else diagnostic)
    return result(status, runtime_agent_id=runtime_agent_id, session_id=session_id,
                  exit_code=exit_code, output=output, diagnostic_code=diagnostic)
