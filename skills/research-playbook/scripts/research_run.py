#!/usr/bin/env python3
"""One-shot, resumable execution kernel for the research playbook."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

import research_package as controller


def _load_host_agent_runtime():
    import importlib.util
    module_path = Path(__file__).resolve().parents[3] / "skills" / "_shared" / "host_agent_runtime.py"
    spec = importlib.util.spec_from_file_location("host_agent_runtime", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("host_agent_runtime", module)
    spec.loader.exec_module(module)
    return module


host_runtime = _load_host_agent_runtime()


DRIVER_SCHEMA_VERSION = 1
ARGV_CONTRACT_VERSION = 1
MANDATORY_ROLES = (
    controller.CORE_RESEARCHER_ROLE,
    *controller.LENSES,
    controller.ADJUDICATOR_ROLE,
)
CORRECTABLE_FIELDS = {
    "research_markdown",
    "evidence_index",
    "requirement_statuses",
    "material_gaps",
    "planner_readiness_constraints",
}


class KernelError(ValueError):
    """Raised when the driver must fail closed."""


class UnprovenGenerationError(KernelError):
    """Raised when worker ownership or death cannot be proved safely."""


class Operation(str, Enum):
    INITIALIZE_SCOPE = "INITIALIZE_SCOPE"
    ADMIT_ROUND = "ADMIT_ROUND"
    LAUNCH_ROLE = "LAUNCH_ROLE"
    ACCEPT_ROLE_RESULT = "ACCEPT_ROLE_RESULT"
    REGISTER_CANDIDATE = "REGISTER_CANDIDATE"
    ACCEPT_LENS_RESULT = "ACCEPT_LENS_RESULT"
    ACCEPT_ADJUDICATION = "ACCEPT_ADJUDICATION"
    APPLY_CANDIDATE_CORRECTION = "APPLY_CANDIDATE_CORRECTION"
    FINALIZE_ROUND = "FINALIZE_ROUND"
    EMIT_PACKAGE = "EMIT_PACKAGE"
    TERMINATE = "TERMINATE"


class LeaseStatus(str, Enum):
    PRELAUNCH = "PRELAUNCH"
    RUNNING = "RUNNING"
    VALIDATED = "VALIDATED"
    CANCELLED = "CANCELLED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


def _read_json(path: Path | str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KernelError(f"cannot read JSON from {path}: {exc}") from exc


def _file_hash(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _state_hash(state: dict[str, Any]) -> str:
    return controller.canonical_hash(state)


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise KernelError(f"{field} must be a positive integer")
    return value


def mechanical_operation_fingerprint(
    operation: Operation,
    payload: Any,
    *,
    state_version: int,
    role: str | None,
    bundle_identity: str,
) -> str:
    return controller.canonical_hash(
        {
            "operation": operation.value,
            "payload_hash": controller.canonical_hash(payload),
            "state_version": state_version,
            "role": role,
            "schema_version": DRIVER_SCHEMA_VERSION,
            "bundle_identity": bundle_identity,
        }
    )


def apply_candidate_correction(candidate: Any, correction: Any) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise KernelError("base candidate must be an object")
    if not isinstance(correction, dict) or set(correction) != {"base_candidate_hash", "replacements"}:
        raise KernelError("candidate correction must contain only base_candidate_hash and replacements")
    if correction["base_candidate_hash"] != controller.canonical_hash(candidate):
        raise KernelError("candidate correction base hash does not match")
    replacements = correction["replacements"]
    if not isinstance(replacements, dict) or not replacements:
        raise KernelError("candidate correction replacements must be a non-empty object")
    unknown = set(replacements) - CORRECTABLE_FIELDS
    if unknown:
        raise KernelError(f"candidate correction contains forbidden fields: {sorted(unknown)}")
    if any(key.startswith("/") for key in replacements) or "patch" in correction:
        raise KernelError("raw patch operations are forbidden")
    rebuilt = copy.deepcopy(candidate)
    for key, value in replacements.items():
        rebuilt[key] = copy.deepcopy(value)
    return rebuilt


def validate_lens_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"verdict", "findings"}:
        raise KernelError("lens result must contain exactly verdict and findings")
    if value["verdict"] not in controller.LENS_VERDICTS or not isinstance(value["findings"], list):
        raise KernelError("lens result has invalid verdict or findings")
    return copy.deepcopy(value)


def validate_adjudication(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise KernelError("adjudication result must be an array of objects")
    return copy.deepcopy(value)


def admit_round(
    controller_state: dict[str, Any],
    *,
    round_number: int,
    role_timeout_seconds: int,
    termination_grace_seconds: int,
    now_epoch: float,
) -> dict[str, Any]:
    before = _state_hash(controller_state)
    budgets = controller_state["budgets"]
    if round_number > budgets["max_rounds"]:
        return {"admitted": False, "reason": "ROUND_BUDGET", "state_hash": before}
    if len(controller_state["attempts"]) + len(MANDATORY_ROLES) > budgets["max_attempts"]:
        return {"admitted": False, "reason": "ATTEMPT_BUDGET", "state_hash": before}
    task_window = role_timeout_seconds + termination_grace_seconds
    if task_window > budgets["max_minutes"] * 60:
        return {"admitted": False, "reason": "TIME_BUDGET", "state_hash": before}
    required = len(MANDATORY_ROLES) * task_window
    return {
        "admitted": True,
        "round": round_number,
        "mandatory_attempts": len(MANDATORY_ROLES),
        "mandatory_seconds": required,
        "state_hash": before,
    }


def build_codex_argv(config: dict[str, Any], schema: Path, result: Path) -> list[str]:
    return host_runtime.build_codex_exec_argv(
        config["codex_executable"], config["repository_root"], schema, result, config.get("model"),
    )


def build_claude_argv(config: dict[str, Any], schema: Path, result: Path) -> list[str]:
    del result  # Claude emits its result envelope on stdout; the adapter persists it.
    return host_runtime.build_claude_print_argv(
        config["claude_executable"],
        schema.read_text(),
        config["claude_max_turns"],
        config["claude_max_budget_usd"],
        allowed_tools=("Read", "Grep", "Glob"),
        disallowed_tools=("Edit", "Write", "Bash", "NotebookEdit"),
        supports_max_turns=bool(config.get("claude_supports_max_turns")),
    )


def build_host_argv(config: dict[str, Any], schema: Path, result: Path) -> list[str]:
    if config["runtime_adapter"] == "claude":
        return build_claude_argv(config, schema, result)
    return build_codex_argv(config, schema, result)


def preflight_host(executable: str, host: str) -> str:
    resolved = shutil.which(executable)
    if not resolved:
        raise KernelError(f"{host} executable not found: {executable}")
    resolved = str(Path(resolved).resolve())
    capabilities = host_runtime.probe_host(resolved, host)
    if not capabilities.available:
        raise KernelError(
            f"{host} capability preflight failed; missing={sorted(capabilities.missing_required_flags)}"
        )
    return resolved


def preflight_codex(executable: str) -> str:
    return preflight_host(executable, "codex")


class Metrics:
    def __init__(self, state: dict[str, Any], clock: Callable[[], float] = time.monotonic) -> None:
        self.state = state
        self.clock = clock

    def mechanical(self) -> "_MetricInterval":
        return _MetricInterval(self, "mechanical_intervals")

    def role_interval(self, started: float, ended: float) -> None:
        if ended < started:
            raise KernelError("role interval ended before it started")
        self.state["metrics"]["role_intervals"].append([started, ended])
        role_windows = self._merge(self.state["metrics"]["role_intervals"])
        mechanical_windows = self._merge(self.state["metrics"]["mechanical_intervals"])
        self.state["metrics"]["mechanical_intervals"] = self._subtract(
            mechanical_windows,
            role_windows,
        )

    def summarize(self) -> dict[str, float]:
        role_windows = self._merge(self.state["metrics"]["role_intervals"])
        mechanical_windows = self._merge(self.state["metrics"]["mechanical_intervals"])
        role_active = sum(end - start for start, end in role_windows)
        if any(
            max(mechanical_start, role_start) < min(mechanical_end, role_end)
            for mechanical_start, mechanical_end in mechanical_windows
            for role_start, role_end in role_windows
        ):
            raise KernelError("mechanical and role-active intervals overlap")
        mechanical = sum(end - start for start, end in mechanical_windows)
        total = mechanical + role_active
        ratio = mechanical / total if total else 0.0
        summary = {
            "mechanical_seconds": mechanical,
            "role_active_seconds": role_active,
            "total_seconds": total,
            "mechanical_ratio": ratio,
        }
        self.state["metrics"].update(summary)
        return summary

    @staticmethod
    def _merge(intervals: list[list[float]]) -> list[list[float]]:
        merged: list[list[float]] = []
        for start, end in sorted(intervals):
            if end < start:
                raise KernelError("metric interval ended before it started")
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return merged

    @staticmethod
    def _subtract(
        sources: list[list[float]],
        exclusions: list[list[float]],
    ) -> list[list[float]]:
        result: list[list[float]] = []
        for source_start, source_end in sources:
            cursor = source_start
            for excluded_start, excluded_end in exclusions:
                if excluded_end <= cursor:
                    continue
                if excluded_start >= source_end:
                    break
                if excluded_start > cursor:
                    result.append([cursor, min(excluded_start, source_end)])
                cursor = max(cursor, excluded_end)
                if cursor >= source_end:
                    break
            if cursor < source_end:
                result.append([cursor, source_end])
        return result


class _MetricInterval:
    def __init__(self, metrics: Metrics, target: str) -> None:
        self.metrics = metrics
        self.target = target
        self.started = 0.0

    def __enter__(self) -> "_MetricInterval":
        self.started = self.metrics.clock()
        return self

    def __exit__(self, *_: Any) -> None:
        ended = self.metrics.clock()
        if ended >= self.started:
            intervals = [[self.started, ended]]
            if self.target == "mechanical_intervals":
                intervals = self.metrics._subtract(
                    intervals,
                    self.metrics._merge(self.metrics.state["metrics"]["role_intervals"]),
                )
            self.metrics.state["metrics"][self.target].extend(intervals)
            duration = sum(end - start for start, end in intervals)
            self.metrics.state["metrics"]["events"].append(
                {"event": "mechanical_duration", "at": time.time(), "seconds": duration}
            )


class SlotLedger:
    VALID_SUCCESSOR_STATES = {
        "reserved": {"reserved", "running", "completed", "closed", "abandoned", "released"},
        "running": {"running", "completed", "closed", "released"},
        "completed": {"completed", "closed", "released"},
        "closed": {"closed", "released"},
        "released": {"released"},
    }
    VALID_PRE_STATES = {
        "acquire": set(),
        "bind-agent": {"reserved"},
        "mark-completed": {"running"},
        "mark-closed": {"running", "completed"},
        "release": {"closed", "abandoned"},
    }

    def __init__(self, script: Path, path: Path, state: dict[str, Any], persist: Callable[[], None]) -> None:
        self.script = script
        self.path = path
        self.state = state
        self.persist = persist

    def _status(self) -> dict[str, Any]:
        completed = subprocess.run(
            [sys.executable, str(self.script), "status", str(self.path), "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def transition(
        self,
        operation: str,
        *,
        label: str,
        expected: str,
        runtime_agent_id: str | None = None,
        args: Iterable[str] = (),
    ) -> str:
        key = f"slot:{label}:{operation}:{expected}"
        entry = self.state["journal"].get(key)
        status = self._status()
        matches = [slot for slot in status["slots"] if slot.get("label") == label]
        if len(matches) > 1:
            raise KernelError(f"slot label is not unique: {label}")
        slot = matches[0] if matches else None
        if entry and any(
            (
                entry.get("operation") != operation,
                entry.get("label") != label,
                entry.get("expected") not in (None, expected),
                entry.get("runtime_agent_id") not in (None, runtime_agent_id),
            )
        ):
            raise KernelError(f"slot journal identity conflicts with transition: {key}")
        if entry and entry["status"] == "COMMITTED":
            if slot is None or slot["id"] != entry["slot_id"]:
                raise KernelError(f"committed slot transition lacks its exact slot: {key}")
            if runtime_agent_id is not None and slot.get("agent_id") != runtime_agent_id:
                raise KernelError(f"committed slot transition has a different runtime agent: {key}")
            if slot["state"] not in self.VALID_SUCCESSOR_STATES[expected]:
                raise KernelError(f"committed slot transition has an invalid successor state: {key}")
            return entry["slot_id"]
        expected_agent_matches = runtime_agent_id is None or (
            slot is not None and slot.get("agent_id") == runtime_agent_id
        )
        if slot is not None and slot["state"] == expected and expected_agent_matches:
            slot_id = slot["id"]
        else:
            if operation == "acquire":
                if slot is not None:
                    raise KernelError(f"prepared acquire conflicts with existing slot state: {slot['state']}")
            elif slot is None or slot["state"] not in self.VALID_PRE_STATES[operation]:
                actual = "missing" if slot is None else slot["state"]
                raise KernelError(
                    f"prepared slot transition has conflicting pre-state: {operation} from {actual}"
                )
            self.state["journal"][key] = {
                "status": "PREPARED",
                "operation": operation,
                "label": label,
                "expected": expected,
                "runtime_agent_id": runtime_agent_id,
            }
            self.persist()
            command = [sys.executable, str(self.script), operation, str(self.path), "--label", label, *args]
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
            if operation == "acquire":
                slot_id = completed.stdout.strip().split()[1]
            else:
                refreshed = self._status()
                found = [slot for slot in refreshed["slots"] if slot.get("label") == label]
                slot_id = found[0]["id"] if found else entry["slot_id"] if entry else "released"
        self.state["journal"][key] = {
            "status": "COMMITTED",
            "operation": operation,
            "label": label,
            "slot_id": slot_id,
            "expected": expected,
            "runtime_agent_id": runtime_agent_id,
        }
        self.persist()
        return slot_id


@dataclass
class RoleHandle:
    role: str
    round_number: int
    runtime_agent_id: str
    slot_label: str
    lease_id: str
    started: float
    immediate_result: Any = None


class ScriptedAdapter:
    def __init__(self, driver: "ResearchDriver", fixture: Any) -> None:
        if not isinstance(fixture, dict) or not isinstance(fixture.get("results"), list):
            raise KernelError("fake fixture must contain a results array")
        self.driver = driver
        self.results = list(fixture["results"])

    def start(self, role: str, prompt: Path, schema: Path, result: Path, lease: dict[str, Any]) -> None:
        del prompt, schema
        index = lease.get("fixture_index")
        if index is None:
            index = self.driver.state["fake_cursor"]
            lease["fixture_index"] = index
            self.driver.state["fake_cursor"] += 1
            self.driver.persist()
        if index >= len(self.results):
            raise KernelError(f"fake fixture has no result for {role}")
        item = self.results[index]
        if item.get("role") != role:
            raise KernelError(f"fake fixture expected {item.get('role')} but driver requested {role}")
        if item.get("error"):
            raise KernelError(str(item["error"]))
        controller.atomic_write(result, copy.deepcopy(item["result"]))
        lease["result_completed_epoch"] = result.stat().st_mtime
        lease["status"] = LeaseStatus.RUNNING.value
        self.driver.persist()

    def reconcile(self, handle: RoleHandle, lease: dict[str, Any]) -> Any:
        del handle
        return _read_json(lease["temp_result_path"])


class ClaudeExecAdapter:
    """Bounded synchronous Claude assessment adapter.

    Claude `--print` has no fork/exec supervision contract like `codex exec`; the run is
    bounded by argv (`--max-turns`, `--max-budget-usd`) plus a subprocess timeout, and the
    kernel keeps sole ownership of leases and the slot ledger.
    """

    def __init__(self, driver: "ResearchDriver") -> None:
        self.driver = driver

    def start(self, role: str, prompt: Path, schema: Path, result: Path, lease: dict[str, Any]) -> None:
        config = self.driver.config
        argv = build_claude_argv(config, schema, result)
        prompt_text = _read_json(prompt)["prompt"]
        try:
            completed = subprocess.run(
                argv,
                input=prompt_text,
                cwd=config["repository_root"],
                capture_output=True,
                text=True,
                timeout=config["role_timeout_seconds"],
            )
        except subprocess.TimeoutExpired as exc:
            raise KernelError(f"{role} claude run timed out after {config['role_timeout_seconds']}s") from exc
        if completed.returncode != 0:
            raise KernelError(f"{role} claude run failed with exit {completed.returncode}")
        try:
            envelope = json.loads(completed.stdout)
        except ValueError as exc:
            raise KernelError(f"{role} claude run returned a non-JSON result envelope") from exc
        if not isinstance(envelope, dict) or envelope.get("type") != "result" or envelope.get("is_error"):
            raise KernelError(f"{role} claude run reported an error envelope")
        value = host_runtime._extract_structured(envelope, _read_json(schema))
        if value is None:
            raise KernelError(f"{role} claude run produced no schema-valid structured output")
        controller.atomic_write(result, value)
        lease["result_completed_epoch"] = result.stat().st_mtime
        lease["claude_session_id"] = envelope.get("session_id")
        lease["status"] = LeaseStatus.RUNNING.value
        self.driver.persist()

    def reconcile(self, handle: RoleHandle, lease: dict[str, Any]) -> Any:
        del handle
        return _read_json(lease["temp_result_path"])


class CodexExecAdapter:
    def __init__(self, driver: "ResearchDriver") -> None:
        self.driver = driver

    def start(self, role: str, prompt: Path, schema: Path, result: Path, lease: dict[str, Any]) -> None:
        read_fd, write_fd = os.pipe()
        lease["status"] = LeaseStatus.PRELAUNCH.value
        self.driver.persist()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(write_fd)
                authorized = os.read(read_fd, 1)
                os.close(read_fd)
                if authorized != b"1":
                    os._exit(75)
                os.setsid()
                self.driver.worker_exec(role, prompt, schema, result, lease["lease_id"])
            except BaseException:
                os._exit(76)
        os.close(read_fd)
        lease["child_pid"] = pid
        lease["expected_pgid"] = pid
        lease["status"] = LeaseStatus.RUNNING.value
        self.driver.persist()
        try:
            os.write(write_fd, b"1")
        finally:
            os.close(write_fd)
        return None

    @staticmethod
    def _claim_matches(lease: dict[str, Any]) -> bool:
        claim_path = Path(lease["claim_path"])
        if not claim_path.is_file():
            return False
        try:
            claim = _read_json(claim_path)
        except (KernelError, OSError, ValueError):
            return False
        return (
            claim.get("lease_id") == lease["lease_id"]
            and claim.get("pid") == lease["child_pid"]
            and claim.get("pgid") == lease["expected_pgid"]
            and claim.get("role") == lease["role"]
            and claim.get("runtime_agent_id") == lease["runtime_agent_id"]
            and claim.get("slot_id") == lease["slot_id"]
            and claim.get("prompt_hash") == lease["prompt_hash"]
            and claim.get("schema_hash") == lease["schema_hash"]
            and claim.get("argv_hash") == lease["argv_hash"]
        )

    @staticmethod
    def _lock_is_held(lease: dict[str, Any]) -> bool:
        with Path(lease["lock_path"]).open("a+b") as lock_handle:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            return False

    def _signal_lease(self, lease: dict[str, Any], now: float) -> None:
        grace = self.driver.config["termination_grace_seconds"]
        if now >= lease["deadline_epoch"] and lease.get("term_sent_epoch") is None:
            if not self._claim_matches(lease):
                raise UnprovenGenerationError("timeout claim does not match the exact generation")
            if not self._lock_is_held(lease):
                return
            try:
                os.killpg(lease["child_pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass
            lease["term_sent_epoch"] = now
            self.driver.persist()
        if now >= lease["deadline_epoch"] + grace and lease.get("kill_sent_epoch") is None:
            if not self._claim_matches(lease):
                raise UnprovenGenerationError("kill claim does not match the exact generation")
            if not self._lock_is_held(lease):
                return
            try:
                os.killpg(lease["child_pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
            lease["kill_sent_epoch"] = now
            self.driver.persist()

    def _enforce_lens_window(self, now: float) -> None:
        context = self.driver.state.get("context") or {}
        for lease_id in context.get("lens_leases", {}).values():
            lease = self.driver.state["leases"].get(lease_id)
            if lease and lease.get("status") == LeaseStatus.RUNNING.value:
                self._signal_lease(lease, now)

    def reconcile(self, handle: RoleHandle, lease: dict[str, Any]) -> Any:
        pid = lease["child_pid"]
        child_reaped = False
        non_parent = False

        def process_exists() -> bool:
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return False
            except PermissionError:
                return True

        def completed_value() -> tuple[bool, Any | None]:
            lock_path = Path(lease["lock_path"])
            with lock_path.open("a+b") as lock_handle:
                try:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return False, None
                try:
                    if not child_reaped and not self._claim_matches(lease) and not non_parent:
                        return False, None
                    if not child_reaped and not self._claim_matches(lease) and non_parent:
                        launch = self.driver.state["journal"].get(f"launch:{lease['lease_id']}", {})
                        if launch.get("status") == "PREPARED" and not process_exists():
                            raise KernelError("unauthorized generation exited before model invocation")
                        raise UnprovenGenerationError(
                            "generation lock is free but exact worker ownership is unproven"
                        )
                    result_path = Path(lease["temp_result_path"])
                    if not result_path.is_file():
                        raise KernelError("codex worker exited without a generation result")
                    return True, _read_json(result_path)
                finally:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

        while True:
            try:
                waited, _status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                waited, _status = 0, 0
                non_parent = True
            if waited == pid:
                child_reaped = True
            completed, value = completed_value()
            if completed:
                return value
            now = time.time()
            if handle.role in controller.LENSES:
                self._enforce_lens_window(now)
            else:
                self._signal_lease(lease, now)
            if lease.get("kill_sent_epoch") is not None and now - lease["kill_sent_epoch"] >= 1.0:
                completed, value = completed_value()
                if completed:
                    return value
                raise UnprovenGenerationError(
                    "generation lock remains held after bounded termination"
                )
            time.sleep(0.05)


class ResearchDriver:
    def __init__(self, args: argparse.Namespace, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.args = args
        self.run_dir = Path(args.run_dir).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.run_dir / "driver-state.json"
        self.controller_path = self.run_dir / "controller-state.json"
        self.slot_path = self.run_dir / "agent-slots.json"
        self.clock = clock
        self.state = self._load_or_initialize()
        self.config = self.state["config"]
        self.metrics = Metrics(self.state, clock)
        repo = Path(__file__).resolve().parents[3]
        self.slot_script = repo / "skills/_shared/agent_slot_ledger.py"
        self.slots = SlotLedger(self.slot_script, self.slot_path, self.state, self.persist)
        if self.config["runtime_adapter"] == "fake":
            self.adapter: Any = ScriptedAdapter(self, _read_json(args.fixture))
        elif self.config["runtime_adapter"] == "claude":
            self.adapter = ClaudeExecAdapter(self)
        else:
            self.adapter = CodexExecAdapter(self)

    def _frozen_inputs(self) -> dict[str, Any]:
        values = {
            "charter": controller.canonical_hash(_read_json(self.args.charter)),
            "requirements": controller.canonical_hash(_read_json(self.args.requirements)),
            "evidence_availability": controller.canonical_hash(_read_json(self.args.evidence_availability)),
            "resume_token": hashlib.sha256(self.args.resume_token.encode("utf-8")).hexdigest(),
            "operational_maturity": self.args.operational_maturity,
            "repository_root": str(Path(self.args.repository_root).resolve()),
            "output_directory": str(Path(self.args.output_directory).resolve()),
            "runtime_adapter": self.args.runtime_adapter,
            "codex_executable": self.args.codex_executable,
            "model": self.args.model,
            "role_timeout_seconds": self.args.role_timeout_seconds,
            "termination_grace_seconds": self.args.termination_grace_seconds,
        }
        if self.args.runtime_adapter == "fake":
            if not self.args.fixture:
                raise KernelError("fake runtime adapter requires --fixture")
            values["fixture"] = controller.canonical_hash(_read_json(self.args.fixture))
        if self.args.runtime_adapter == "claude":
            values["claude_executable"] = self.args.claude_executable
            values["claude_max_turns"] = self.args.claude_max_turns
            values["claude_max_budget_usd"] = self.args.claude_max_budget_usd
        return values

    def _load_or_initialize(self) -> dict[str, Any]:
        frozen = self._frozen_inputs()
        role_timeout = _require_positive_int(self.args.role_timeout_seconds, "role_timeout_seconds")
        grace = _require_positive_int(self.args.termination_grace_seconds, "termination_grace_seconds")
        executable = self.args.codex_executable
        if self.args.runtime_adapter == "codex":
            executable = preflight_codex(executable)
        config = {
            "runtime_adapter": self.args.runtime_adapter,
            "codex_executable": executable,
            "repository_root": str(Path(self.args.repository_root).resolve()),
            "model": self.args.model,
            "role_timeout_seconds": role_timeout,
            "termination_grace_seconds": grace,
            "argv_contract_version": ARGV_CONTRACT_VERSION,
        }
        if self.args.runtime_adapter == "claude":
            config["claude_executable"] = preflight_host(self.args.claude_executable, "claude")
            config["claude_max_turns"] = _require_positive_int(self.args.claude_max_turns, "claude_max_turns")
            config["claude_max_budget_usd"] = self.args.claude_max_budget_usd
            probed = host_runtime.probe_host(config["claude_executable"], "claude")
            config["claude_supports_max_turns"] = "--max-turns" in probed.supported_flags
        if self.state_path.exists():
            state = _read_json(self.state_path)
            if (
                state.get("schema_version") != DRIVER_SCHEMA_VERSION
                or state.get("frozen_inputs") != frozen
                or state.get("config") != config
            ):
                raise KernelError("resume inputs do not match the frozen run")
            return state
        state = {
            "schema_version": DRIVER_SCHEMA_VERSION,
            "run_id": controller.stable_id("research-run", frozen, config),
            "status": "IN_PROGRESS",
            "next_operation": Operation.INITIALIZE_SCOPE.value,
            "frozen_inputs": frozen,
            "config": config,
            "round": 0,
            "context": None,
            "fake_cursor": 0,
            "journal": {},
            "leases": {},
            "mechanical_failures": {},
            "research_finding_closures": {},
            "metrics": {"mechanical_intervals": [], "role_intervals": [], "events": []},
            "result": {},
        }
        controller.atomic_write(self.state_path, state)
        return state

    def persist(self) -> None:
        controller.atomic_write(self.state_path, self.state)

    def _event(self, name: str, **fields: Any) -> None:
        self.state["metrics"]["events"].append({"event": name, "at": time.time(), **fields})

    def _reconcile_controller_effect(
        self,
        key: str,
        expected: dict[str, Any],
    ) -> dict[str, Any] | None:
        state = controller.load_state(self.controller_path)
        kind = expected["kind"]
        if kind == "candidate":
            candidate_id = controller.stable_id(
                "candidate",
                state["package_id"],
                expected["candidate_hash"],
                expected["envelope_hash"],
            )
            record = state["candidates"].get(candidate_id)
            if record is not None:
                comparable = {
                    "candidate_hash": record["candidate_hash"],
                    "envelope_hash": record["envelope_hash"],
                    "candidate_payload": record["candidate_payload"],
                    "envelope_payload": record["envelope_payload"],
                    "evidence_availability": record["evidence_availability"],
                }
                if comparable != {name: expected[name] for name in comparable}:
                    raise KernelError(f"prepared controller effect conflicts with durable state: {key}")
                return {"verdict": state["verdict"], "reason": "CANDIDATE_RECONCILED", **record}
        elif kind == "attempt":
            record = next(
                (
                    item
                    for item in state["attempts"]
                    if item["runtime_agent_id"] == expected["runtime_agent_id"]
                ),
                None,
            )
            if record is not None:
                comparable = {name: value for name, value in record.items() if name != "recorded_at"}
                if comparable != {name: expected[name] for name in comparable}:
                    raise KernelError(f"prepared controller effect conflicts with durable state: {key}")
                return {"verdict": state["verdict"], "reason": "ATTEMPT_RECONCILED", **record}
        elif kind == "lens":
            round_record = next(
                (
                    item
                    for item in state["rounds"]
                    if item["round_number"] == expected["round_number"]
                ),
                None,
            )
            record = round_record["lenses"].get(expected["lens"]) if round_record else None
            if record is not None:
                terminal = controller.validate_lens_terminal_envelope(
                    expected["lens"], expected["terminal_envelope"]
                )
                comparable = {name: value for name, value in record.items() if name != "recorded_at"}
                wanted = {
                    "lens_result_id": controller.stable_id(
                        "lens-result",
                        state["package_id"],
                        expected["round_number"],
                        expected["lens"],
                        expected["candidate_hash"],
                        expected["envelope_hash"],
                    ),
                    "lens": expected["lens"],
                    "runtime_agent_id": expected["runtime_agent_id"],
                    "verdict": terminal["verdict"],
                    "candidate_hash": expected["candidate_hash"],
                    "envelope_hash": expected["envelope_hash"],
                    "raw_findings": terminal["findings"],
                }
                if comparable != wanted:
                    raise KernelError(f"prepared controller effect conflicts with durable state: {key}")
                return {"verdict": state["verdict"], "reason": "LENS_RECONCILED", **record}
        elif kind == "adjudication":
            round_record = next(
                (
                    item
                    for item in state["rounds"]
                    if item["round_number"] == expected["round_number"]
                ),
                None,
            )
            record = round_record.get("adjudication") if round_record else None
            if record is not None:
                normalized = controller._normalize_adjudications(
                    controller._all_raw_findings(round_record),
                    expected["adjudications"],
                )
                comparable = {name: value for name, value in record.items() if name != "recorded_at"}
                wanted = {
                    "adjudication_id": controller.stable_id(
                        "adjudication",
                        state["package_id"],
                        expected["round_number"],
                        expected["runtime_agent_id"],
                        expected["candidate_hash"],
                        expected["envelope_hash"],
                    ),
                    "runtime_agent_id": expected["runtime_agent_id"],
                    "candidate_hash": expected["candidate_hash"],
                    "envelope_hash": expected["envelope_hash"],
                    "findings": normalized,
                }
                if comparable != wanted:
                    raise KernelError(f"prepared controller effect conflicts with durable state: {key}")
                return copy.deepcopy(state["result"])
        elif kind == "cap" and state["verdict"] == "CAP_REACHED":
            if state["result"].get("reason") != expected["reason"]:
                raise KernelError(f"prepared controller effect conflicts with durable state: {key}")
            return copy.deepcopy(state["result"])
        return None

    def _controller_mutation(
        self,
        key: str,
        expected: dict[str, Any],
        operation: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        entry = self.state["journal"].get(key)
        if entry and entry["status"] == "COMMITTED":
            if entry.get("expected") != expected:
                raise KernelError(f"committed controller effect identity changed: {key}")
            return copy.deepcopy(entry["result"])
        if entry and entry["status"] == "PREPARED":
            if entry.get("expected") != expected:
                raise KernelError(f"prepared controller effect identity changed: {key}")
            reconciled = self._reconcile_controller_effect(key, expected)
            if reconciled is not None:
                entry.update(
                    status="COMMITTED",
                    after_hash=_file_hash(self.controller_path),
                    result=copy.deepcopy(reconciled),
                    reconciled=True,
                )
                self._event("checkpoint_resume", effect=key)
                self.persist()
                return reconciled
            if _file_hash(self.controller_path) != entry["before_hash"]:
                raise KernelError(f"prepared controller effect has a conflicting pre-state: {key}")
        before = _file_hash(self.controller_path)
        self.state["journal"][key] = {
            "status": "PREPARED",
            "before_hash": before,
            "expected": copy.deepcopy(expected),
        }
        self.persist()
        result = controller.mutate_file(self.controller_path, operation)
        self.state["journal"][key] = {
            "status": "COMMITTED",
            "before_hash": before,
            "after_hash": _file_hash(self.controller_path),
            "expected": copy.deepcopy(expected),
            "result": copy.deepcopy(result),
        }
        self.persist()
        return result

    def _initialize_controller(self) -> None:
        charter = _read_json(self.args.charter)
        requirements = _read_json(self.args.requirements)
        evidence = _read_json(self.args.evidence_availability)
        controller_expected = {
            "kind": "initialize-controller",
            "charter_hash": controller.canonical_hash(charter),
            "requirements_hash": controller.canonical_hash(requirements),
            "evidence_hash": controller.canonical_hash(evidence),
            "operational_maturity": self.args.operational_maturity,
        }
        controller_key = "initialize:controller"
        controller_entry = self.state["journal"].get(controller_key)
        if controller_entry and controller_entry.get("expected") != controller_expected:
            raise KernelError("controller initialization identity changed")
        if controller_entry and controller_entry["status"] == "COMMITTED":
            if not self.controller_path.is_file() or _file_hash(self.controller_path) != controller_entry["after_hash"]:
                raise KernelError("committed controller initialization no longer matches durable state")
        else:
            if controller_entry is None:
                self.state["journal"][controller_key] = {
                    "status": "PREPARED",
                    "before_hash": _file_hash(self.controller_path) if self.controller_path.is_file() else None,
                    "expected": controller_expected,
                }
                self.persist()
            result = controller.initialize_file(
                self.controller_path,
                charter,
                requirements,
                self.args.operational_maturity,
                evidence,
            )
            if result.get("verdict") != "IN_PROGRESS" or result.get("reason") not in {
                "INITIALIZED",
                "SCOPE_UNCHANGED",
            }:
                raise KernelError("controller initialization did not preserve the exact frozen scope")
            self.state["journal"][controller_key] = {
                "status": "COMMITTED",
                "before_hash": self.state["journal"][controller_key]["before_hash"],
                "after_hash": _file_hash(self.controller_path),
                "expected": controller_expected,
                "result": copy.deepcopy(result),
            }
            self.persist()
        slot_expected = {"kind": "initialize-slot-ledger", "version": 2, "max": 4}
        slot_key = "initialize:slot-ledger"
        slot_entry = self.state["journal"].get(slot_key)
        if slot_entry and slot_entry.get("expected") != slot_expected:
            raise KernelError("slot-ledger initialization identity changed")
        if slot_entry and slot_entry["status"] == "COMMITTED":
            if not self.slot_path.is_file() or _file_hash(self.slot_path) != slot_entry["after_hash"]:
                raise KernelError("committed slot-ledger initialization no longer matches durable state")
        else:
            if slot_entry is None:
                self.state["journal"][slot_key] = {
                    "status": "PREPARED",
                    "before_hash": _file_hash(self.slot_path) if self.slot_path.is_file() else None,
                    "expected": slot_expected,
                }
                self.persist()
            if not self.slot_path.exists():
                subprocess.run(
                    [sys.executable, str(self.slot_script), "init", str(self.slot_path), "--max", "4"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            slot_state = _read_json(self.slot_path)
            if slot_state != {"version": 2, "max": 4, "slots": []}:
                raise KernelError("prepared slot-ledger initialization conflicts with durable state")
            self.state["journal"][slot_key] = {
                "status": "COMMITTED",
                "before_hash": self.state["journal"][slot_key]["before_hash"],
                "after_hash": _file_hash(self.slot_path),
                "expected": slot_expected,
            }
            self.persist()
        self.state["next_operation"] = Operation.ADMIT_ROUND.value
        self.persist()

    def _envelope(self) -> dict[str, Any]:
        controller_state = controller.load_state(self.controller_path)
        return {
            "schema_version": DRIVER_SCHEMA_VERSION,
            "package_id": controller_state["package_id"],
            "scope_hash": controller_state["scope_hash"],
            "budget": copy.deepcopy(controller_state["budgets"]),
            "repository_root": self.config["repository_root"],
            "config_hash": controller.canonical_hash(self.config),
        }

    def _schema_for(self, role: str, round_number: int) -> dict[str, Any]:
        raw_finding = {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(controller.RAW_FINDING_REQUIRED_FIELDS),
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "fingerprint": {"type": "string", "minLength": 1},
                "lens": {"enum": list(controller.LENSES)},
                "originating_stage": {"const": "RESEARCH"},
                "requirement_ids": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "type": {"enum": sorted(controller.FINDING_TYPES)},
                "materiality": {"enum": sorted(controller.MATERIALITIES)},
                "practical_consequence": {"type": "string", "minLength": 1},
                "evidence": {
                    "oneOf": [
                        {"type": "string", "minLength": 1},
                        {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                    ]
                },
                "proposed_disposition": {"enum": sorted(controller.DISPOSITIONS)},
                "status": {"enum": sorted(controller.FINDING_STATUSES)},
                "evidence_limitation": {"type": "string", "minLength": 1},
                "closure_evidence": {
                    "oneOf": [
                        {"type": "string", "minLength": 1},
                        {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                    ]
                },
            },
        }
        if role in controller.LENSES:
            return {
                "type": "object",
                "additionalProperties": False,
                "required": ["verdict", "findings"],
                "properties": {
                    "verdict": {"enum": sorted(controller.LENS_VERDICTS)},
                    "findings": {"type": "array", "items": raw_finding},
                },
            }
        if role == controller.ADJUDICATOR_ROLE:
            return {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["raw_finding", "finding_type", "materiality", "disposition"],
                    "properties": {
                        "raw_finding": raw_finding,
                        "finding_type": {"enum": sorted(controller.FINDING_TYPES)},
                        "materiality": {"enum": sorted(controller.MATERIALITIES)},
                        "disposition": {"enum": sorted(controller.DISPOSITIONS)},
                    },
                },
            }
        if round_number > 1:
            return {
                "type": "object",
                "additionalProperties": False,
                "required": ["base_candidate_hash", "replacements"],
                "properties": {
                    "base_candidate_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "replacements": {"type": "object", "minProperties": 1},
                },
            }
        return {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(CORRECTABLE_FIELDS),
            "properties": {
                "research_markdown": {"type": "string"},
                "evidence_index": {"type": "array", "items": {"type": "object"}},
                "requirement_statuses": {"type": "array", "items": {"type": "object"}},
                "material_gaps": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "planner_readiness_constraints": {"type": "array", "items": {"type": "object"}},
            },
        }

    def _prompt_for(self, role: str, round_number: int, candidate: Any, findings: Any) -> str:
        references = Path(__file__).resolve().parents[1] / "references"
        contract = {
            "charter_and_maturity": (references / "charter-and-maturity.md").read_text(encoding="utf-8"),
            "planner_handoff": (references / "planner-handoff.md").read_text(encoding="utf-8"),
            "lenses_and_findings": (references / "lenses-and-findings.md").read_text(encoding="utf-8"),
        }
        if role == controller.CORE_RESEARCHER_ROLE:
            instruction = (
                "Produce the complete first candidate." if round_number == 1 else
                "Return only the closed structured correction object for the supplied adjudicated FIX_IN_RESEARCH findings."
            )
            visible_findings = findings if round_number > 1 else []
        elif role in controller.LENSES:
            instruction = (
                f"Independently execute only the {role} lens. Do not infer or reuse another lens or adjudicator conclusion."
            )
            visible_findings = []
        else:
            instruction = "Independently adjudicate the current round's raw lens findings; do not edit the candidate."
            visible_findings = findings
        frozen_controller = controller.load_state(self.controller_path)
        return controller.canonical_json(
            {
                "instruction": instruction,
                "role": role,
                "round": round_number,
                "candidate": candidate,
                "findings_visible_to_this_role": visible_findings,
                "charter": copy.deepcopy(frozen_controller["charter"]),
                "requirements": copy.deepcopy(frozen_controller["requirements"]),
                "envelope": self._envelope(),
                "contracts": contract,
                "required_output_schema": self._schema_for(role, round_number),
            }
        )

    def _slot_open(self, label: str, runtime_id: str) -> str:
        slot_id = self.slots.transition("acquire", label=label, expected="reserved")
        self.slots.transition(
            "bind-agent",
            label=label,
            expected="running",
            runtime_agent_id=runtime_id,
            args=("--agent-id", runtime_id),
        )
        return slot_id

    def _slot_close(self, label: str, runtime_id: str, close_path: Path, success: bool) -> None:
        if success:
            self.slots.transition(
                "mark-completed",
                label=label,
                expected="completed",
                runtime_agent_id=runtime_id,
            )
        self.slots.transition(
            "mark-closed",
            label=label,
            expected="closed",
            runtime_agent_id=runtime_id,
            args=("--close-evidence", str(close_path)),
        )
        self.slots.transition(
            "release",
            label=label,
            expected="released",
            runtime_agent_id=runtime_id,
        )

    def _start_role(self, role: str) -> RoleHandle:
        with self.metrics.mechanical():
            context = self.state["context"]
            round_number = context["round"]
            candidate = context.get("candidate") or context.get("base_candidate")
            findings = (
                context.get("current_lens_findings", [])
                if role == controller.ADJUDICATOR_ROLE
                else context.get("prior_findings", [])
            )
            attempt = sum(
                1
                for lease in self.state["leases"].values()
                if lease["round"] == round_number and lease["role"] == role
            ) + 1
            payload = {
                "role": role,
                "round": round_number,
                "attempt": attempt,
                "candidate_hash": controller.canonical_hash(candidate) if candidate is not None else None,
            }
            fingerprint = mechanical_operation_fingerprint(
                Operation.LAUNCH_ROLE,
                payload,
                state_version=self.state["schema_version"],
                role=role,
                bundle_identity=self.state["run_id"],
            )
            if fingerprint in self.state["mechanical_failures"]:
                self._event("superseded_prevention", fingerprint=fingerprint, role=role)
                self.persist()
                raise KernelError("superseded mechanical operation fingerprint cannot be dispatched")
            for prior in self.state["mechanical_failures"].values():
                if (
                    prior.get("round") == round_number
                    and prior.get("role") == role
                    and not prior.get("successor_fingerprint")
                ):
                    prior["successor_fingerprint"] = fingerprint
            lease_id = controller.stable_id("lease", self.state["run_id"], round_number, role, attempt)
            runtime_id = (
                f"research-worker:{self.state['run_id']}:{round_number}:{role}:"
                f"{attempt}:{lease_id[-8:]}"
            )
            label = f"{self.state['run_id']}:{round_number}:{role}:{attempt}"
            slot_id = self._slot_open(label, runtime_id)
            role_dir = self.run_dir / "roles" / lease_id
            role_dir.mkdir(parents=True, exist_ok=True)
            prompt = role_dir / "prompt.json"
            schema = role_dir / "schema.json"
            result = role_dir / "result.json"
            lock_path = role_dir / "generation.lock"
            lock_path.touch(exist_ok=True)
            controller.atomic_write(prompt, {"prompt": self._prompt_for(role, round_number, candidate, findings)})
            controller.atomic_write(schema, self._schema_for(role, round_number))
            prompt_hash = _file_hash(prompt)
            schema_hash = _file_hash(schema)
            argv_hash = controller.canonical_hash(build_host_argv(self.config, schema, result))
            lease = {
                "lease_id": lease_id,
                "role": role,
                "round": round_number,
                "attempt": attempt,
                "runtime_agent_id": runtime_id,
                "slot_id": slot_id,
                "slot_label": label,
                "fingerprint": fingerprint,
                "status": LeaseStatus.PRELAUNCH.value,
                "started_monotonic": None,
                "started_epoch": None,
                "deadline_epoch": None,
                "lock_path": str(lock_path),
                "claim_path": str(role_dir / "claim.json"),
                "temp_result_path": str(result),
                "prompt_hash": prompt_hash,
                "schema_hash": schema_hash,
                "argv_hash": argv_hash,
            }
            self.state["leases"][lease_id] = lease
            self.state["journal"][f"launch:{lease_id}"] = {
                "status": "PREPARED",
                "lease_id": lease_id,
                "fingerprint": fingerprint,
                "role": role,
                "runtime_agent_id": runtime_id,
                "slot_id": slot_id,
                "prompt_hash": prompt_hash,
                "schema_hash": schema_hash,
                "argv_hash": argv_hash,
            }
            self._bind_lease_to_context(role, lease_id)
            self._event(
                "registered_dispatch",
                role=role,
                round=round_number,
                attempt=attempt,
                fingerprint=fingerprint,
            )
            self.persist()
        lease["started_monotonic"] = self.clock()
        lease["started_epoch"] = time.time()
        context = self.state["context"]
        task_key = f"{round_number}:{role}"
        task_deadlines = context.setdefault("task_deadline_epochs", {})
        if task_key not in task_deadlines:
            task_cap_seconds = controller.load_state(self.controller_path)["budgets"]["max_minutes"] * 60
            task_deadlines[task_key] = lease["started_epoch"] + min(
                self.config["role_timeout_seconds"],
                task_cap_seconds - self.config["termination_grace_seconds"],
            )
        lease["deadline_epoch"] = task_deadlines[task_key]
        try:
            self.adapter.start(role, prompt, schema, result, lease)
        except Exception as exc:
            lease["status"] = LeaseStatus.FAILED.value
            lease["launch_error"] = str(exc)
        self.state["journal"][f"launch:{lease_id}"]["status"] = "COMMITTED"
        self.persist()
        return RoleHandle(role, round_number, runtime_id, label, lease_id, lease["started_monotonic"])

    def _bind_lease_to_context(self, role: str, lease_id: str) -> None:
        context = self.state["context"]
        if role == controller.CORE_RESEARCHER_ROLE:
            context["core_lease"] = lease_id
            context["pending_lease"] = lease_id
            self.state["next_operation"] = Operation.ACCEPT_ROLE_RESULT.value
        elif role in controller.LENSES:
            context["lens_leases"][role] = lease_id
            if len(context["lens_leases"]) == len(controller.LENSES):
                context["lens_accept_queue"] = [
                    lens for lens in controller.LENSES if lens not in context["lens_outputs"]
                ]
                if not context["lens_accept_queue"]:
                    raise KernelError("lens launch has no unaccepted role to reconcile")
                context["pending_lease"] = context["lens_leases"][context["lens_accept_queue"][0]]
                self.state["next_operation"] = Operation.ACCEPT_ROLE_RESULT.value
            else:
                self.state["next_operation"] = Operation.LAUNCH_ROLE.value
        else:
            context["adjudicator_lease"] = lease_id
            context["pending_lease"] = lease_id
            self.state["next_operation"] = Operation.ACCEPT_ROLE_RESULT.value

    def _close_role_interval(self, lease: dict[str, Any]) -> None:
        if lease.get("role_interval_closed") or lease.get("started_monotonic") is None:
            return
        result_path = Path(lease["temp_result_path"])
        completed_epoch = lease.get("result_completed_epoch")
        if completed_epoch is None and result_path.is_file():
            completed_epoch = result_path.stat().st_mtime
        if completed_epoch is not None and lease.get("started_epoch") is not None:
            duration = max(0.0, completed_epoch - lease["started_epoch"])
            ended = lease["started_monotonic"] + duration
        else:
            ended = self.clock()
        self.metrics.role_interval(lease["started_monotonic"], ended)
        lease["role_interval_closed"] = True
        lease["ended_monotonic"] = ended
        self._event(
            "role_duration",
            role=lease["role"],
            round=lease["round"],
            seconds=ended - lease["started_monotonic"],
        )

    def _validate_role_output(self, handle: RoleHandle, value: Any) -> Any:
        try:
            Draft202012Validator(self._schema_for(handle.role, handle.round_number)).validate(value)
        except ValidationError as exc:
            raise KernelError(f"{handle.role} result violates its exact schema: {exc.message}") from exc
        context = self.state["context"]
        if handle.role == controller.CORE_RESEARCHER_ROLE:
            candidate = (
                value
                if handle.round_number == 1
                else apply_candidate_correction(context["base_candidate"], value)
            )
            probe = controller.load_state(self.controller_path)
            controller.record_candidate(
                probe,
                candidate,
                context["envelope"],
                evidence_availability=probe["evidence_availability"],
            )
        elif handle.role in controller.LENSES:
            value = controller.validate_lens_terminal_envelope(handle.role, value)
        else:
            probe = controller.load_state(self.controller_path)
            round_record = next(
                item for item in probe["rounds"] if item["round_number"] == handle.round_number
            )
            normalized = controller._normalize_adjudications(
                controller._all_raw_findings(round_record),
                value,
            )
            candidate = controller._candidate_by_hashes(
                probe,
                context["candidate_hash"],
                context["envelope_hash"],
            )
            controller._require_candidate_gap_classification(candidate["candidate_payload"], normalized)
        return copy.deepcopy(value)

    def _reconcile_role(self, handle: RoleHandle) -> tuple[Any | None, str | None]:
        lease = self.state["leases"][handle.lease_id]
        if handle.lease_id in self.state.setdefault("validated_results", {}):
            return copy.deepcopy(self.state["validated_results"][handle.lease_id]), None
        if handle.lease_id in self.state.setdefault("accepted_results", {}):
            return copy.deepcopy(self.state["accepted_results"][handle.lease_id]), None
        if lease.get("failure_error"):
            return None, lease["failure_error"]
        if lease.get("launch_error"):
            self._close_role_interval(lease)
            self.persist()
            return None, lease["launch_error"]
        try:
            value = self.adapter.reconcile(handle, lease)
            value = self._validate_role_output(handle, value)
            self._close_role_interval(lease)
            lease["status"] = LeaseStatus.VALIDATED.value
            self.state["validated_results"][handle.lease_id] = copy.deepcopy(value)
            self.persist()
            return value, None
        except UnprovenGenerationError:
            raise
        except Exception as exc:
            self._close_role_interval(lease)
            lease["failure_error"] = str(exc)
            self.persist()
            return None, lease["failure_error"]

    def _complete_role_success(self, handle: RoleHandle) -> None:
        lease = self.state["leases"][handle.lease_id]
        if handle.lease_id in self.state.setdefault("accepted_results", {}):
            return
        if lease["status"] not in {LeaseStatus.VALIDATED.value, LeaseStatus.SUCCEEDED.value}:
            raise KernelError("role success requires a validated generation result")
        close_path = Path(lease["temp_result_path"]).with_name("close.json")
        controller.atomic_write(close_path, {"status": "completed", "lease_id": handle.lease_id})
        lease["status"] = LeaseStatus.SUCCEEDED.value
        self._slot_close(handle.slot_label, handle.runtime_agent_id, close_path, True)
        self.state["accepted_results"][handle.lease_id] = copy.deepcopy(
            self.state["validated_results"][handle.lease_id]
        )
        for record in self.state["mechanical_failures"].values():
            if record.get("round") == handle.round_number and record.get("role") == handle.role:
                record.update(
                    status="SUPERSEDED_PERMANENTLY",
                    verification_runtime_id=handle.runtime_agent_id,
                )
        self.persist()

    def _record_failed_role(self, handle: RoleHandle, error: str) -> None:
        lease = self.state["leases"][handle.lease_id]
        lease["status"] = LeaseStatus.CANCELLED.value
        lease["failure_error"] = error
        self.persist()
        close_path = Path(lease["temp_result_path"]).with_name("close.json")
        controller.atomic_write(
            close_path,
            {"status": "failed", "lease_id": handle.lease_id, "error": error},
        )
        self._slot_close(handle.slot_label, handle.runtime_agent_id, close_path, False)
        context = self.state["context"]
        candidate_hash = context.get("candidate_hash")
        if candidate_hash is None and context.get("base_candidate") is not None:
            candidate_hash = controller.canonical_hash(context["base_candidate"])
        close_evidence = _read_json(close_path)
        expected_attempt = {
            "kind": "attempt",
            "runtime_agent_id": handle.runtime_agent_id,
            "role": handle.role,
            "round": handle.round_number,
            "candidate_hash": candidate_hash,
            "input_envelope_hash": context["envelope_hash"],
            "status": "FAILED",
            "output_hash": None,
            "slot_closed": True,
            "close_evidence": close_evidence,
        }
        self._controller_mutation(
            f"attempt:{handle.runtime_agent_id}",
            expected_attempt,
            lambda state: controller.record_attempt(
                state,
                runtime_agent_id=handle.runtime_agent_id,
                role=handle.role,
                round_number=handle.round_number,
                candidate_hash=candidate_hash,
                input_envelope_hash=context["envelope_hash"],
                status="FAILED",
                output_hash=None,
                slot_closed=True,
                close_evidence=close_evidence,
            ),
        )
        self.state["mechanical_failures"][lease["fingerprint"]] = {
            "status": "FAILED_UNVERIFIED",
            "successor": Operation.LAUNCH_ROLE.value,
            "evidence": str(close_path),
            "round": handle.round_number,
            "role": handle.role,
        }
        self._event("role_failed", role=handle.role, round=handle.round_number, error=error)
        self._sync_round_reservation()
        self.persist()

    def _sync_round_reservation(self) -> None:
        context = self.state.get("context")
        if not context or "mandatory_reservation" not in context:
            return
        controller_state = controller.load_state(self.controller_path)
        attempted = {
            item["role"]
            for item in controller_state["attempts"]
            if item["round"] == context["round"]
        }
        context["mandatory_reservation"]["remaining_roles"] = [
            role for role in MANDATORY_ROLES if role not in attempted
        ]

    def _role_handle(self, lease_id: str) -> RoleHandle:
        lease = self.state["leases"][lease_id]
        return RoleHandle(
            lease["role"],
            lease["round"],
            lease["runtime_agent_id"],
            lease["slot_label"],
            lease_id,
            lease["started_monotonic"],
        )

    def worker_exec(self, role: str, prompt: Path, schema: Path, result: Path, lease_id: str) -> None:
        lease = _read_json(self.state_path)["leases"][lease_id]
        lock_path = Path(lease["lock_path"])
        lock_path.touch(exist_ok=True)
        lock_fd = os.open(lock_path, os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os._exit(77)
        durable = _read_json(self.state_path)
        refreshed = durable["leases"].get(lease_id)
        launch = durable["journal"].get(f"launch:{lease_id}")
        if (
            not refreshed
            or not launch
            or launch.get("status") not in {"PREPARED", "COMMITTED"}
            or refreshed["status"] != LeaseStatus.RUNNING.value
            or refreshed["role"] != role
            or launch.get("lease_id") != lease_id
            or launch.get("role") != role
            or launch.get("runtime_agent_id") != refreshed["runtime_agent_id"]
            or launch.get("slot_id") != refreshed["slot_id"]
            or launch.get("prompt_hash") != refreshed["prompt_hash"]
            or launch.get("schema_hash") != refreshed["schema_hash"]
            or launch.get("argv_hash") != refreshed["argv_hash"]
            or _file_hash(prompt) != refreshed["prompt_hash"]
            or _file_hash(schema) != refreshed["schema_hash"]
            or controller.canonical_hash(build_codex_argv(self.config, schema, result))
            != refreshed["argv_hash"]
        ):
            os._exit(78)
        slot_status = self.slots._status()
        slot_matches = [
            slot
            for slot in slot_status["slots"]
            if slot["id"] == refreshed["slot_id"]
            and slot.get("label") == refreshed["slot_label"]
            and slot.get("agent_id") == refreshed["runtime_agent_id"]
            and slot["state"] == "running"
        ]
        if len(slot_matches) != 1:
            os._exit(79)
        controller.atomic_write(
            refreshed["claim_path"],
            {
                "lease_id": lease_id,
                "pid": os.getpid(),
                "pgid": os.getpgrp(),
                "role": role,
                "runtime_agent_id": refreshed["runtime_agent_id"],
                "slot_id": refreshed["slot_id"],
                "prompt_hash": refreshed["prompt_hash"],
                "schema_hash": refreshed["schema_hash"],
                "argv_hash": refreshed["argv_hash"],
            },
        )
        flags = fcntl.fcntl(lock_fd, fcntl.F_GETFD)
        fcntl.fcntl(lock_fd, fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)
        prompt_fd = os.open(prompt, os.O_RDONLY)
        os.dup2(prompt_fd, 0)
        if prompt_fd != 0:
            os.close(prompt_fd)
        argv = build_codex_argv(self.config, schema, result)
        os.execvpe(argv[0], argv, os.environ.copy())

    def _record_attempt(
        self,
        handle: RoleHandle,
        candidate_hash: str,
        envelope_hash: str,
        output: Any,
    ) -> None:
        lease = self.state["leases"][handle.lease_id]
        output_hash = controller.canonical_hash(output)
        close = _read_json(Path(lease["temp_result_path"]).with_name("close.json"))
        key = f"attempt:{handle.runtime_agent_id}"
        expected_attempt = {
            "kind": "attempt",
            "runtime_agent_id": handle.runtime_agent_id,
            "role": handle.role,
            "round": handle.round_number,
            "candidate_hash": candidate_hash,
            "input_envelope_hash": envelope_hash,
            "status": "SUCCEEDED",
            "output_hash": output_hash,
            "slot_closed": True,
            "close_evidence": close,
        }
        self._controller_mutation(
            key,
            expected_attempt,
            lambda state: controller.record_attempt(
                state,
                runtime_agent_id=handle.runtime_agent_id,
                role=handle.role,
                round_number=handle.round_number,
                candidate_hash=candidate_hash,
                input_envelope_hash=envelope_hash,
                status="SUCCEEDED",
                output_hash=output_hash,
                slot_closed=True,
                close_evidence=close,
            ),
        )

    def _expected_artifact_hashes(self, candidate: dict[str, Any]) -> dict[str, str]:
        state = controller.load_state(self.controller_path)
        passing_round = max(
            (item for item in state["rounds"] if controller._round_complete(item)),
            key=lambda item: item["round_number"],
        )
        indexed = controller._indexed_evidence_ids(candidate["evidence_index"])
        readiness = controller._planner_readiness_by_id(
            state,
            candidate["planner_readiness_constraints"],
            indexed,
        )
        requirements = controller._emitted_requirements(state, passing_round, readiness)
        handoff = (
            "# Planner handoff\n\n"
            "Implement the validated research findings and readiness obligations exactly.\n"
        )
        payloads = {
            "research.md": candidate["research_markdown"].encode("utf-8"),
            "requirements.json": controller._json_payload(requirements),
            "evidence-index.json": controller._json_payload(candidate["evidence_index"]),
            "findings.json": controller._json_payload(passing_round["adjudication"]["findings"]),
            "planner-handoff.md": handoff.encode("utf-8"),
        }
        return {name: controller._bytes_hash(payload) for name, payload in payloads.items()}

    def _verify_emitted_package(
        self,
        target: Path,
        expected_artifact_hashes: dict[str, str],
    ) -> dict[str, Any] | None:
        expected_files = set(controller.EMITTED_FILES)
        if not target.is_dir() or {path.name for path in target.iterdir() if path.is_file()} != expected_files:
            return None
        manifest = _read_json(target / "manifest.json")
        controller_state = controller.load_state(self.controller_path)
        if (
            not isinstance(manifest, dict)
            or set(manifest) != {
                "schema_version",
                "package_id",
                "terminal_verdict",
                "candidate_hash",
                "envelope_hash",
                "artifact_hashes",
                "budget_use",
                "lifecycle_evidence",
                "emitted_at",
            }
            or manifest.get("schema_version") != controller.SCHEMA_VERSION
            or manifest.get("package_id") != controller_state["package_id"]
            or manifest.get("terminal_verdict") != "PASS"
            or manifest.get("candidate_hash") != controller_state["result"]["candidate_hash"]
            or manifest.get("envelope_hash") != controller_state["result"]["envelope_hash"]
            or manifest.get("artifact_hashes") != expected_artifact_hashes
            or manifest.get("lifecycle_evidence") != controller_state["attempts"]
        ):
            return None
        budget_use = manifest.get("budget_use")
        if (
            not isinstance(budget_use, dict)
            or set(budget_use)
            != {"rounds_used", "rounds_max", "attempts_used", "attempts_max", "workflow_minutes_used", "minutes_max_per_task"}
            or budget_use["rounds_used"] != max(item["round_number"] for item in controller_state["rounds"])
            or budget_use["rounds_max"] != controller_state["budgets"]["max_rounds"]
            or budget_use["attempts_used"] != len(controller_state["attempts"])
            or budget_use["attempts_max"] != controller_state["budgets"]["max_attempts"]
            or budget_use["minutes_max_per_task"] != controller_state["budgets"]["max_minutes"]
            or not isinstance(budget_use["workflow_minutes_used"], (int, float))
            or budget_use["workflow_minutes_used"] < 0
        ):
            return None
        for name, expected_hash in expected_artifact_hashes.items():
            if _file_hash(target / name) != expected_hash:
                return None
        return {
            "verdict": "PASS",
            "reason": "PACKAGE_RECONCILED",
            "output_directory": str(target),
            "file_hashes": {name: _file_hash(target / name) for name in sorted(expected_files)},
        }

    def _emit(self, candidate: dict[str, Any]) -> dict[str, Any]:
        target = Path(self.args.output_directory).resolve()
        key = f"emit:{controller.canonical_hash(candidate)}"
        expected_artifacts = self._expected_artifact_hashes(candidate)
        expected_identity = {
            "target": str(target),
            "candidate_hash": controller.canonical_hash(candidate),
            "artifact_hashes": expected_artifacts,
        }
        entry = self.state["journal"].get(key)
        if entry and entry["status"] == "COMMITTED":
            if entry.get("expected") != expected_identity:
                raise KernelError("committed package identity changed")
            if self._verify_emitted_package(target, expected_artifacts) is None:
                raise KernelError("committed package no longer matches its exact manifest")
            return copy.deepcopy(entry["result"])
        if entry and entry["status"] == "PREPARED":
            if entry.get("expected") != expected_identity:
                raise KernelError("prepared package identity changed")
            reconciled = self._verify_emitted_package(target, expected_artifacts)
            if reconciled is not None:
                entry.update(status="COMMITTED", result=copy.deepcopy(reconciled), reconciled=True)
                self._event("checkpoint_resume", effect=key)
                self.persist()
                return reconciled
        self.state["journal"][key] = {
            "status": "PREPARED",
            "expected": copy.deepcopy(expected_identity),
        }
        self.persist()
        if target.exists():
            raise KernelError("existing package directory does not match the prepared emission")
        handoff = "# Planner handoff\n\nImplement the validated research findings and readiness obligations exactly.\n"
        result = controller.emit_package(
            controller.load_state(self.controller_path),
            target,
            research_markdown=candidate["research_markdown"],
            evidence_index=candidate["evidence_index"],
            planner_readiness=candidate["planner_readiness_constraints"],
            planner_handoff_markdown=handoff,
        )
        verified = self._verify_emitted_package(target, expected_artifacts)
        if verified is None:
            raise KernelError("emitted package failed exact manifest/file verification")
        self.state["journal"][key] = {
            "status": "COMMITTED",
            "expected": copy.deepcopy(expected_identity),
            "result": result,
        }
        self.persist()
        return result

    def _initialize_operation(self) -> None:
        self._initialize_controller()
        self._event("initialized", run_id=self.state["run_id"])

    def _admit_operation(self) -> None:
        controller_state = controller.load_state(self.controller_path)
        round_number = max([item["round_number"] for item in controller_state["rounds"]], default=0) + 1
        admission = admit_round(
            controller_state,
            round_number=round_number,
            role_timeout_seconds=self.config["role_timeout_seconds"],
            termination_grace_seconds=self.config["termination_grace_seconds"],
            now_epoch=time.time(),
        )
        if not admission["admitted"]:
            self._event("admission_rejected", **admission)
            terminal = self._controller_mutation(
                f"cap:{round_number}:{admission['reason']}",
                {"kind": "cap", "reason": admission["reason"]},
                lambda package: controller._cap(package, admission["reason"], None),
            )
            self.state["context"] = {"terminal_result": terminal}
            self.state["next_operation"] = Operation.TERMINATE.value
            return
        base_candidate = None
        prior_findings: list[dict[str, Any]] = []
        if controller_state["candidates"]:
            base_candidate = copy.deepcopy(list(controller_state["candidates"].values())[-1]["candidate_payload"])
        if controller_state["rounds"]:
            latest = max(controller_state["rounds"], key=lambda item: item["round_number"])
            prior_findings = copy.deepcopy((latest.get("adjudication") or {}).get("findings", []))
        envelope = self._envelope()
        self.state["round"] = round_number
        self.state["context"] = {
            "round": round_number,
            "phase": "CORE",
            "base_candidate": base_candidate,
            "prior_findings": prior_findings,
            "envelope": envelope,
            "envelope_hash": controller.canonical_hash(envelope),
            "candidate": None,
            "candidate_hash": None,
            "core_lease": None,
            "lens_leases": {},
            "task_deadline_epochs": {},
            "lens_outputs": {},
            "current_lens_findings": [],
            "adjudicator_lease": None,
            "pending_lease": None,
            "mandatory_reservation": {
                "attempts": len(MANDATORY_ROLES),
                "seconds": admission["mandatory_seconds"],
                "remaining_roles": list(MANDATORY_ROLES),
            },
        }
        self.state["next_operation"] = Operation.LAUNCH_ROLE.value

    def _launch_operation(self) -> None:
        context = self.state["context"]
        phase = context["phase"]
        if phase == "CORE":
            self._start_role(controller.CORE_RESEARCHER_ROLE)
            return
        if phase == "LENSES":
            for role in controller.LENSES:
                if role not in context["lens_leases"]:
                    self._start_role(role)
                    return
        if phase == "ADJUDICATOR":
            self._start_role(controller.ADJUDICATOR_ROLE)
            return
        raise KernelError(f"LAUNCH_ROLE is invalid for phase {phase}")

    def _retry_or_stop(self, handle: RoleHandle) -> None:
        state = controller.load_state(self.controller_path)
        self._sync_round_reservation()
        reservation = self.state["context"]["mandatory_reservation"]
        role_attempts = [
            item for item in state["attempts"]
            if item["round"] == handle.round_number and item["role"] == handle.role
        ]
        remaining_attempts = len(reservation["remaining_roles"])
        capacity_ok = len(state["attempts"]) + 1 + remaining_attempts <= state["budgets"]["max_attempts"]
        task_key = f"{handle.round_number}:{handle.role}"
        deadline = self.state["context"].get("task_deadline_epochs", {}).get(task_key)
        time_ok = isinstance(deadline, (int, float)) and time.time() < deadline
        if (
            len(role_attempts) <= state["budgets"]["max_role_retries"]
            and capacity_ok
            and time_ok
        ):
            context = self.state["context"]
            if handle.role == controller.CORE_RESEARCHER_ROLE:
                context["core_lease"] = None
            elif handle.role in controller.LENSES:
                context["lens_leases"].pop(handle.role, None)
                context.pop("lens_accept_queue", None)
            else:
                context["adjudicator_lease"] = None
            context["pending_lease"] = None
            self.state["next_operation"] = Operation.LAUNCH_ROLE.value
            return
        reason = (
            "ATTEMPT_BUDGET"
            if not capacity_ok
            else "TIME_BUDGET"
            if not time_ok
            else "ROLE_RETRY_BUDGET"
        )
        terminal = self._controller_mutation(
            f"cap:{self.state['context']['round']}:{reason}",
            {"kind": "cap", "reason": reason},
            lambda package: controller._cap(package, reason, None),
        )
        self.state["context"]["terminal_result"] = terminal
        self.state["next_operation"] = Operation.TERMINATE.value

    def _accept_role_operation(self) -> None:
        lease_id = self.state["context"].get("pending_lease")
        if not lease_id:
            raise KernelError("ACCEPT_ROLE_RESULT lacks a pending lease")
        handle = self._role_handle(lease_id)
        value, error = self._reconcile_role(handle)
        with self.metrics.mechanical():
            if error is not None:
                self._record_failed_role(handle, error)
                self._retry_or_stop(handle)
                return
            context = self.state["context"]
            context["pending_lease"] = None
            if handle.role == controller.CORE_RESEARCHER_ROLE:
                context["core_output"] = copy.deepcopy(value)
                self.state["next_operation"] = (
                    Operation.REGISTER_CANDIDATE.value
                    if handle.round_number == 1
                    else Operation.APPLY_CANDIDATE_CORRECTION.value
                )
            elif handle.role in controller.LENSES:
                context["pending_lens_role"] = handle.role
                context["pending_lens_output"] = validate_lens_result(value)
                self.state["next_operation"] = Operation.ACCEPT_LENS_RESULT.value
            else:
                context["adjudication_output"] = validate_adjudication(value)
                self.state["next_operation"] = Operation.ACCEPT_ADJUDICATION.value

    def _apply_correction_operation(self) -> None:
        context = self.state["context"]
        if context["base_candidate"] is None:
            raise KernelError("candidate correction lacks a base candidate")
        context["candidate"] = apply_candidate_correction(context["base_candidate"], context["core_output"])
        self.state["next_operation"] = Operation.REGISTER_CANDIDATE.value

    def _register_candidate_operation(self) -> None:
        context = self.state["context"]
        if context.get("candidate") is None:
            output = context["core_output"]
            if not isinstance(output, dict):
                raise KernelError("core researcher must return a candidate object")
            context["candidate"] = copy.deepcopy(output)
        candidate = context["candidate"]
        candidate_hash = controller.canonical_hash(candidate)
        envelope_hash = controller.canonical_hash(context["envelope"])
        availability = controller.load_state(self.controller_path)["evidence_availability"]
        expected_candidate = {
            "kind": "candidate",
            "candidate_hash": candidate_hash,
            "envelope_hash": envelope_hash,
            "candidate_payload": copy.deepcopy(candidate),
            "envelope_payload": copy.deepcopy(context["envelope"]),
            "evidence_availability": copy.deepcopy(availability),
        }
        result = self._controller_mutation(
            f"candidate:{candidate_hash}:{envelope_hash}",
            expected_candidate,
            lambda state: controller.record_candidate(
                state,
                candidate,
                context["envelope"],
                evidence_availability=state["evidence_availability"],
            ),
        )
        context["candidate_hash"] = result["candidate_hash"]
        context["envelope_hash"] = result["envelope_hash"]
        if context["round"] > 1:
            for finding in context["prior_findings"]:
                if finding.get("disposition") != "FIX_IN_RESEARCH":
                    continue
                fingerprint = finding["finding_fingerprint"]
                self.state["research_finding_closures"][fingerprint] = {
                    "status": "CORRECTION_APPLIED",
                    "source_round": context["round"] - 1,
                    "correcting_round": context["round"],
                    "base_candidate_hash": controller.canonical_hash(context["base_candidate"]),
                    "replacement_candidate_hash": context["candidate_hash"],
                }
        core = self._role_handle(context["core_lease"])
        self._complete_role_success(core)
        self._record_attempt(core, context["candidate_hash"], context["envelope_hash"], context["core_output"])
        self._sync_round_reservation()
        context["phase"] = "LENSES"
        self.state["next_operation"] = Operation.LAUNCH_ROLE.value

    def _accept_lens_operation(self) -> None:
        context = self.state["context"]
        role = context["pending_lens_role"]
        output = context["pending_lens_output"]
        handle = self._role_handle(context["lens_leases"][role])
        self._complete_role_success(handle)
        self._record_attempt(handle, context["candidate_hash"], context["envelope_hash"], output)
        self._sync_round_reservation()
        self._controller_mutation(
            f"lens:{context['round']}:{role}:{context['candidate_hash']}",
            {
                "kind": "lens",
                "round_number": context["round"],
                "lens": role,
                "runtime_agent_id": handle.runtime_agent_id,
                "candidate_hash": context["candidate_hash"],
                "envelope_hash": context["envelope_hash"],
                "terminal_envelope": copy.deepcopy(output),
            },
            lambda state: controller.record_lens_result(
                state,
                round_number=context["round"],
                lens=role,
                runtime_agent_id=handle.runtime_agent_id,
                candidate_hash=context["candidate_hash"],
                envelope_hash=context["envelope_hash"],
                terminal_envelope=output,
            ),
        )
        context["lens_outputs"][role] = output
        context["current_lens_findings"].extend(copy.deepcopy(output["findings"]))
        context.pop("pending_lens_role")
        context.pop("pending_lens_output")
        queue = context["lens_accept_queue"]
        if queue and queue[0] == role:
            queue.pop(0)
        if queue:
            context["pending_lease"] = context["lens_leases"][queue[0]]
            self.state["next_operation"] = Operation.ACCEPT_ROLE_RESULT.value
        else:
            context["phase"] = "ADJUDICATOR"
            self.state["next_operation"] = Operation.LAUNCH_ROLE.value

    def _accept_adjudication_operation(self) -> None:
        context = self.state["context"]
        output = context["adjudication_output"]
        handle = self._role_handle(context["adjudicator_lease"])
        self._complete_role_success(handle)
        self._record_attempt(handle, context["candidate_hash"], context["envelope_hash"], output)
        self._sync_round_reservation()
        context["adjudication_result"] = self._controller_mutation(
            f"adjudication:{context['round']}:{context['candidate_hash']}",
            {
                "kind": "adjudication",
                "round_number": context["round"],
                "runtime_agent_id": handle.runtime_agent_id,
                "candidate_hash": context["candidate_hash"],
                "envelope_hash": context["envelope_hash"],
                "adjudications": copy.deepcopy(output),
            },
            lambda state: controller.record_adjudication(
                state,
                round_number=context["round"],
                runtime_agent_id=handle.runtime_agent_id,
                candidate_hash=context["candidate_hash"],
                envelope_hash=context["envelope_hash"],
                adjudications=output,
            ),
        )
        self.state["next_operation"] = Operation.FINALIZE_ROUND.value

    def _finalize_round_operation(self) -> None:
        result = self.state["context"]["adjudication_result"]
        if result["verdict"] == "PASS":
            for closure in self.state["research_finding_closures"].values():
                if closure["status"] == "CORRECTION_APPLIED":
                    closure.update(
                        status="VERIFIED_CLOSED",
                        verification_round=self.state["context"]["round"],
                        verification_candidate_hash=self.state["context"]["candidate_hash"],
                    )
            self.state["next_operation"] = Operation.EMIT_PACKAGE.value
        elif result["verdict"] == "IN_PROGRESS":
            self.state["context"] = None
            self.state["next_operation"] = Operation.ADMIT_ROUND.value
        else:
            self.state["context"]["terminal_result"] = result
            self.state["next_operation"] = Operation.TERMINATE.value

    def _emit_operation(self) -> None:
        context = self.state["context"]
        emitted = self._emit(context["candidate"])
        context["terminal_result"] = {**context["adjudication_result"], **emitted}
        self.state["next_operation"] = Operation.TERMINATE.value

    def _terminal_response(self) -> dict[str, Any]:
        entry = self.state["journal"].get("terminal")
        if not entry or entry.get("status") != "COMMITTED":
            raise KernelError("terminated driver lacks a committed terminal identity")
        manifest_hash = entry["response_base"].get("package_manifest_hash")
        if manifest_hash is not None:
            context = self.state.get("context") or {}
            candidate = context.get("candidate")
            target = Path(self.args.output_directory).resolve()
            if (
                candidate is None
                or self._verify_emitted_package(
                    target,
                    self._expected_artifact_hashes(candidate),
                )
                is None
                or _file_hash(target / "manifest.json") != manifest_hash
            ):
                raise KernelError("terminal package no longer matches its committed identity")
        expected = {
            **copy.deepcopy(entry["response_base"]),
            "driver_state_hash": _file_hash(self.state_path),
        }
        result_path = self.run_dir / "terminal-result.json"
        if result_path.is_file():
            actual = _read_json(result_path)
            if actual != expected:
                raise KernelError("terminal result conflicts with the committed terminal identity")
            return actual
        controller.atomic_write(result_path, expected)
        return expected

    def _terminate(self, result: dict[str, Any]) -> dict[str, Any]:
        if self.state["status"] == "TERMINATED":
            return self._terminal_response()
        controller_state = controller.load_state(self.controller_path)
        controller_result = controller_state["result"]
        if controller_state["verdict"] not in {"PASS", "BLOCKED", "CAP_REACHED"}:
            raise KernelError("TERMINATE requires an authoritative controller terminal state")
        for field in ("verdict", "candidate_hash", "envelope_hash", "actionable_fingerprints"):
            if result.get(field) != controller_result[field]:
                raise KernelError(f"terminal result is not bound to controller field: {field}")
        allowed_reasons = {controller_result["reason"]}
        if controller_state["verdict"] == "PASS":
            allowed_reasons = {"PACKAGE_EMITTED", "PACKAGE_RECONCILED"}
            committed_emissions = [
                entry
                for key, entry in self.state["journal"].items()
                if key.startswith("emit:") and entry.get("status") == "COMMITTED"
            ]
            candidate = (self.state.get("context") or {}).get("candidate")
            if (
                len(committed_emissions) != 1
                or candidate is None
                or self._verify_emitted_package(
                    Path(self.args.output_directory).resolve(),
                    self._expected_artifact_hashes(candidate),
                )
                is None
            ):
                raise KernelError("controller PASS requires a committed verified package emission")
        if result.get("reason") not in allowed_reasons:
            raise KernelError("terminal result reason is not bound to the controller terminal state")
        slot_status = self.slots._status()
        active = [slot for slot in slot_status["slots"] if slot["state"] != "released"]
        if active:
            raise KernelError(f"terminal state requires zero active slots: {[slot['id'] for slot in active]}")
        started = self.clock()
        self._event("run_completion", verdict=result.get("verdict"))
        self.state["status"] = "TERMINATED"
        self.state["next_operation"] = Operation.TERMINATE.value
        self.state["result"] = copy.deepcopy(result)
        ended = self.clock()
        self.state["metrics"]["mechanical_intervals"].append([started, ended])
        metrics = self.metrics.summarize()
        metrics_path = self.run_dir / "metrics.json"
        controller.atomic_write(metrics_path, {"schema_version": 1, **metrics, "events": self.state["metrics"]["events"]})
        manifest_path = Path(self.args.output_directory).resolve() / "manifest.json"
        response_base = {
            **copy.deepcopy(result),
            "run_id": self.state["run_id"],
            "controller_state_hash": _file_hash(self.controller_path),
            "package_manifest_hash": _file_hash(manifest_path) if manifest_path.is_file() else None,
            "metrics_path": str(metrics_path),
            "metrics": metrics,
        }
        self.state["journal"]["terminal"] = {
            "status": "COMMITTED",
            "response_base": copy.deepcopy(response_base),
        }
        self.persist()
        return self._terminal_response()

    def _dispatch(self, operation: Operation) -> None:
        handlers: dict[Operation, Callable[[], None]] = {
            Operation.INITIALIZE_SCOPE: self._initialize_operation,
            Operation.ADMIT_ROUND: self._admit_operation,
            Operation.LAUNCH_ROLE: self._launch_operation,
            Operation.APPLY_CANDIDATE_CORRECTION: self._apply_correction_operation,
            Operation.REGISTER_CANDIDATE: self._register_candidate_operation,
            Operation.ACCEPT_LENS_RESULT: self._accept_lens_operation,
            Operation.ACCEPT_ADJUDICATION: self._accept_adjudication_operation,
            Operation.FINALIZE_ROUND: self._finalize_round_operation,
            Operation.EMIT_PACKAGE: self._emit_operation,
        }
        if operation == Operation.ACCEPT_ROLE_RESULT:
            self._accept_role_operation()
            self.persist()
            return
        if operation == Operation.TERMINATE:
            result = (self.state.get("context") or {}).get("terminal_result", self.state.get("result", {}))
            self._terminate(result)
            return
        handler = handlers.get(operation)
        if handler is None:
            raise KernelError(f"operation is not registered: {operation.value}")
        if operation == Operation.LAUNCH_ROLE:
            handler()
            with self.metrics.mechanical():
                self._event("mechanical_operation", operation=operation.value)
                self.persist()
        else:
            with self.metrics.mechanical():
                handler()
            self._event("mechanical_operation", operation=operation.value)
            self.persist()

    def run(self) -> dict[str, Any]:
        lock_path = self.run_dir / "driver.lock"
        with lock_path.open("a+b") as lock_handle:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise KernelError("another driver owns the run's single-writer lock") from exc
            if self.state["status"] == "TERMINATED":
                return self._terminal_response()
            for _ in range(200):
                raw_operation = self.state.get("next_operation")
                try:
                    operation = Operation(raw_operation)
                except (TypeError, ValueError) as exc:
                    raise KernelError(f"unregistered persisted operation: {raw_operation}") from exc
                self._dispatch(operation)
                if self.state["status"] == "TERMINATED":
                    return self._terminal_response()
            raise KernelError("operation dispatch cap reached")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    drive = sub.add_parser("drive")
    drive.add_argument("--run-dir", required=True)
    drive.add_argument("--charter", required=True)
    drive.add_argument("--requirements", required=True)
    drive.add_argument("--operational-maturity", required=True, choices=sorted(controller.OPERATIONAL_MATURITIES))
    drive.add_argument("--evidence-availability", required=True)
    drive.add_argument("--repository-root", required=True)
    drive.add_argument("--output-directory", required=True)
    drive.add_argument("--runtime-adapter", choices=("codex", "claude", "fake"), default="codex")
    drive.add_argument("--resume-token", required=True)
    drive.add_argument("--role-timeout-seconds", type=int, required=True)
    drive.add_argument("--termination-grace-seconds", type=int, default=5)
    drive.add_argument("--codex-executable", default="codex")
    drive.add_argument("--claude-executable", default="claude")
    drive.add_argument("--claude-max-turns", type=int, default=8)
    drive.add_argument("--claude-max-budget-usd", default="1.00")
    drive.add_argument("--model")
    drive.add_argument("--fixture")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = ResearchDriver(args).run()
    except (KernelError, controller.ResearchPackageError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"verdict": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
