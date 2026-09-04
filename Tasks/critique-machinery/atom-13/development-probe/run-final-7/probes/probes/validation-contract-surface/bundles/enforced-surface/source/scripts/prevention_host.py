#!/usr/bin/env python3
"""Authenticated host-capability admission for governed mechanical actions."""

from __future__ import annotations

import hashlib
import hmac
import json
import socket
import sys
from pathlib import Path
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

try:
    from scripts.prevention_contract import (
        ActionClass,
        GovernanceLevel,
        HostCapabilities,
        canonical_bytes,
        require_exact_keys,
        require_id,
        require_sha256,
        sha256_bytes,
    )
    from scripts.prevention_journal import JournalOwnership, PreventionJournal
except ModuleNotFoundError:  # direct script execution
    from prevention_contract import (
        ActionClass,
        GovernanceLevel,
        HostCapabilities,
        canonical_bytes,
        require_exact_keys,
        require_id,
        require_sha256,
        sha256_bytes,
    )
    from prevention_journal import JournalOwnership, PreventionJournal


RECEIPT_FIELDS = {
    "schema_version", "receipt_id", "session_id", "challenge_nonce", "config_sha256",
    "hook_sha256", "trusted", "enabled", "intercepted_classes", "withheld_classes",
    "granted_classes", "issued_at_utc", "expires_at_utc", "launcher_pid", "child_pid",
    "feature_inventory", "accepted_flags", "controller_sha256", "mac",
}
HOOK_REQUIRED_FIELDS = {
    "cwd", "hook_event_name", "model", "permission_mode", "session_id", "tool_input",
    "tool_name", "tool_use_id", "transcript_path", "turn_id",
}
HOOK_OPTIONAL_FIELDS = {"agent_id", "agent_type"}
PERMISSION_MODES = {"default", "acceptEdits", "plan", "dontAsk", "bypassPermissions"}
CONTROLLER_SOCKET_FD = 198
CONTROLLER_ADMISSION_FIELDS = {
    "schema_version", "message_kind", "host_capability_receipt",
}


class HostAdmissionError(ValueError):
    """Raised when host enforcement cannot be proved from an authenticated receipt."""


def authoritative_controller_sha256() -> str:
    return sha256_bytes(Path(__file__).resolve().read_bytes())


@dataclass(frozen=True)
class HookRequest:
    session_id: str
    turn_id: str
    cwd: str
    model: str
    permission_mode: str
    tool_name: str
    tool_use_id: str
    tool_input: Any
    transcript_path: str | None
    action_class: ActionClass

    def canonical_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "cwd": self.cwd,
            "model": self.model,
            "permission_mode": self.permission_mode,
            "tool_name": self.tool_name,
            "tool_use_id": self.tool_use_id,
            "tool_input": self.tool_input,
            "transcript_path": self.transcript_path,
            "action_class": self.action_class.value,
        }


def parse_hook_request(value: Any) -> HookRequest:
    if not isinstance(value, Mapping):
        raise HostAdmissionError("hook-input-not-object")
    actual = set(value)
    missing = HOOK_REQUIRED_FIELDS - actual
    extra = actual - HOOK_REQUIRED_FIELDS - HOOK_OPTIONAL_FIELDS
    if missing or extra:
        raise HostAdmissionError(
            f"hook-input-keys:missing={sorted(missing)}:extra={sorted(extra)}"
        )
    if value["hook_event_name"] != "PreToolUse":
        raise HostAdmissionError("wrong-hook-event")
    if value["permission_mode"] not in PERMISSION_MODES:
        raise HostAdmissionError("invalid-hook-permission-mode")
    for field in ("session_id", "turn_id", "model", "tool_name", "tool_use_id"):
        if not isinstance(value[field], str) or not value[field]:
            raise HostAdmissionError(f"invalid-hook-{field.replace('_', '-')}")
    if not isinstance(value["cwd"], str) or not value["cwd"].startswith("/"):
        raise HostAdmissionError("invalid-hook-cwd")
    if value["transcript_path"] is not None and not isinstance(value["transcript_path"], str):
        raise HostAdmissionError("invalid-hook-transcript-path")
    for field in HOOK_OPTIONAL_FIELDS & actual:
        if not isinstance(value[field], str):
            raise HostAdmissionError(f"invalid-hook-{field.replace('_', '-')}")
    tool_name = value["tool_name"]
    if tool_name == "Bash":
        action_class = ActionClass.BASH
    elif tool_name == "apply_patch":
        action_class = ActionClass.APPLY_PATCH
    elif tool_name.startswith("mcp__") and len(tool_name.split("__")) >= 3:
        action_class = ActionClass.MCP
    else:
        raise HostAdmissionError("unsupported-hook-tool-name")
    return HookRequest(
        session_id=value["session_id"],
        turn_id=value["turn_id"],
        cwd=value["cwd"],
        model=value["model"],
        permission_mode=value["permission_mode"],
        tool_name=tool_name,
        tool_use_id=value["tool_use_id"],
        tool_input=value["tool_input"],
        transcript_path=value["transcript_path"],
        action_class=action_class,
    )


def deny_hook(reason_code: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": require_id(reason_code, label="hook-denial-reason"),
        }
    }


def controller_hook_output(request: HookRequest, reply: Any) -> dict[str, Any]:
    if not isinstance(reply, Mapping):
        raise HostAdmissionError("controller-reply-not-object")
    if reply.get("permission_decision") == "deny":
        require_exact_keys(
            reply, {"schema_version", "tool_use_id", "permission_decision", "reason_code"},
            label="controller-deny-reply",
        )
        if reply["schema_version"] != 1 or reply["tool_use_id"] != request.tool_use_id:
            raise HostAdmissionError("controller-deny-reply-mismatch")
        return deny_hook(reply["reason_code"])
    require_exact_keys(
        reply,
        {
            "schema_version", "tool_use_id", "permission_decision", "decision_kind",
            "effective_sequence_id", "effective_implementation_id", "updated_input",
        },
        label="controller-allow-reply",
    )
    if (
        reply["schema_version"] != 1
        or reply["tool_use_id"] != request.tool_use_id
        or reply["permission_decision"] != "allow"
        or reply["decision_kind"] not in {
            "SELECT_SUCCESSOR", "SELECT_PROMOTED", "SELECT_REGISTERED"
        }
    ):
        raise HostAdmissionError("controller-allow-reply-mismatch")
    require_id(reply["effective_sequence_id"], label="effective-sequence-id")
    require_sha256(reply["effective_implementation_id"], label="effective-implementation-id")
    if reply["updated_input"] != request.tool_input:
        raise HostAdmissionError("cross-input-hook-rewrite-prohibited")
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": reply["updated_input"],
        }
    }


def invoke_controller(request: HookRequest, *, socket_fd: int = CONTROLLER_SOCKET_FD) -> dict[str, Any]:
    try:
        channel = socket.socket(fileno=socket_fd)
        channel.settimeout(5.0)
        channel.sendall(canonical_bytes(request.canonical_json()))
        response = b""
        while not response.endswith(b"\n"):
            chunk = channel.recv(65_536)
            if not chunk:
                break
            response += chunk
            if len(response) > 1_048_576:
                raise HostAdmissionError("controller-reply-too-large")
    except (OSError, TimeoutError) as exc:
        raise HostAdmissionError("controller-channel-unavailable") from exc
    finally:
        try:
            channel.close()
        except (OSError, UnboundLocalError):
            pass
    try:
        reply = json.loads(response)
    except json.JSONDecodeError as exc:
        raise HostAdmissionError("invalid-controller-reply-json") from exc
    return controller_hook_output(request, reply)


def run_pre_tool_hook(value: Any, *, socket_fd: int = CONTROLLER_SOCKET_FD) -> dict[str, Any]:
    try:
        return invoke_controller(parse_hook_request(value), socket_fd=socket_fd)
    except (HostAdmissionError, ValueError):
        return deny_hook("PREVENTION_CONTROLLER_DENIED")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise HostAdmissionError("invalid-host-receipt-timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HostAdmissionError("invalid-host-receipt-timestamp") from exc
    if result.tzinfo is None:
        raise HostAdmissionError("invalid-host-receipt-timestamp")
    return result.astimezone(UTC)


def _string_set(value: Any, *, field: str) -> frozenset[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise HostAdmissionError(f"invalid-{field}")
    if value != sorted(set(value)):
        raise HostAdmissionError(f"noncanonical-{field}")
    return frozenset(value)


def receipt_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    require_exact_keys(receipt, RECEIPT_FIELDS, label="host-capability-receipt")
    return {key: receipt[key] for key in sorted(RECEIPT_FIELDS - {"mac"})}


def sign_receipt(payload: Mapping[str, Any], key: bytes) -> dict[str, Any]:
    if len(key) != 32:
        raise HostAdmissionError("host-key-must-be-32-bytes")
    if "mac" in payload or set(payload) != RECEIPT_FIELDS - {"mac"}:
        raise HostAdmissionError("invalid-host-receipt-payload")
    mac = hmac.new(key, canonical_bytes(dict(payload)), hashlib.sha256).hexdigest()
    return {**dict(payload), "mac": mac}


def consume_controller_admission(
    value: Any,
    journal: PreventionJournal,
    *,
    key: bytes,
    now: datetime | None = None,
) -> tuple[HostCapabilities, dict[str, Any]]:
    """Authenticate the launcher's one-use receipt before any governed action."""
    if not isinstance(value, Mapping):
        raise HostAdmissionError("controller-admission-not-object")
    try:
        require_exact_keys(value, CONTROLLER_ADMISSION_FIELDS, label="controller-admission")
    except ValueError as exc:
        raise HostAdmissionError(str(exc)) from exc
    if value["schema_version"] != 1 or value["message_kind"] != "HOST_CAPABILITY_ADMISSION":
        raise HostAdmissionError("controller-admission-envelope-invalid")
    receipt = value["host_capability_receipt"]
    if not isinstance(receipt, Mapping):
        raise HostAdmissionError("controller-admission-receipt-invalid")
    try:
        payload = receipt_payload(receipt)
        verifier = HostCapabilityVerifier(
            journal,
            key=key,
            session_id=str(payload["session_id"]),
            challenge_nonce=str(payload["challenge_nonce"]),
            config_sha256=str(payload["config_sha256"]),
            hook_sha256=str(payload["hook_sha256"]),
            launcher_pid=payload["launcher_pid"],
            child_pid=payload["child_pid"],
        )
        capabilities = verifier.verify(receipt, now=now)
    except (KeyError, ValueError) as exc:
        if isinstance(exc, HostAdmissionError):
            raise
        raise HostAdmissionError("controller-admission-receipt-invalid") from exc
    return capabilities, {
        "schema_version": 1,
        "admission_decision": "accept",
        "receipt_id": payload["receipt_id"],
        "receipt_sha256": sha256_bytes(canonical_bytes(dict(receipt))),
    }


def read_inherited_receipt_key(*, environment: Mapping[str, str] | None = None) -> bytes:
    environment = environment or __import__("os").environ
    raw_fd = environment.get("WORKFLOW_ORCH_HOST_RECEIPT_KEY_FD")
    try:
        fd = int(raw_fd) if raw_fd is not None else -1
    except ValueError as exc:
        raise HostAdmissionError("controller-admission-key-fd-invalid") from exc
    if fd < 0:
        raise HostAdmissionError("controller-admission-key-fd-invalid")
    try:
        key = __import__("os").read(fd, 33)
    except OSError as exc:
        raise HostAdmissionError("controller-admission-key-unavailable") from exc
    if len(key) != 32:
        raise HostAdmissionError("controller-admission-key-invalid")
    return key


class HostCapabilityVerifier:
    """Controller-owned verifier; the HMAC key never crosses this typed boundary."""

    def __init__(
        self,
        journal: PreventionJournal,
        *,
        key: bytes,
        session_id: str,
        challenge_nonce: str,
        config_sha256: str,
        hook_sha256: str,
        launcher_pid: int,
        child_pid: int,
    ):
        if len(key) != 32:
            raise HostAdmissionError("host-key-must-be-32-bytes")
        self.journal = journal
        self._key = key
        self.session_id = require_id(session_id, label="session-id")
        self.challenge_nonce = require_id(challenge_nonce, label="challenge-nonce")
        self.config_sha256 = require_sha256(config_sha256, label="config-sha256")
        self.hook_sha256 = require_sha256(hook_sha256, label="hook-sha256")
        if isinstance(launcher_pid, bool) or not isinstance(launcher_pid, int) or launcher_pid <= 0:
            raise HostAdmissionError("invalid-launcher-pid")
        if isinstance(child_pid, bool) or not isinstance(child_pid, int) or child_pid <= 0:
            raise HostAdmissionError("invalid-child-pid")
        self.launcher_pid = launcher_pid
        self.child_pid = child_pid

    def verify(self, receipt: Mapping[str, Any], *, now: datetime | None = None) -> HostCapabilities:
        try:
            payload = receipt_payload(receipt)
        except ValueError as exc:
            raise HostAdmissionError(str(exc)) from exc
        mac = receipt.get("mac")
        if not isinstance(mac, str) or len(mac) != 64:
            raise HostAdmissionError("invalid-host-receipt-mac")
        expected_mac = hmac.new(self._key, canonical_bytes(payload), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected_mac):
            raise HostAdmissionError("host-receipt-authentication-failed")
        expected = {
            "schema_version": 1,
            "session_id": self.session_id,
            "challenge_nonce": self.challenge_nonce,
            "config_sha256": self.config_sha256,
            "hook_sha256": self.hook_sha256,
            "launcher_pid": self.launcher_pid,
            "child_pid": self.child_pid,
            "controller_sha256": authoritative_controller_sha256(),
        }
        for field, value in expected.items():
            if payload[field] != value:
                raise HostAdmissionError(f"host-receipt-{field.replace('_', '-')}-mismatch")
        receipt_id = require_id(payload["receipt_id"], label="receipt-id")
        events, _ = self.journal.replay()
        if any(event.get("evidence_ref") == f"host-receipt:{receipt_id}" for event in events):
            raise HostAdmissionError("host-receipt-replayed")
        issued = _timestamp(payload["issued_at_utc"])
        expires = _timestamp(payload["expires_at_utc"])
        now = (now or datetime.now(UTC)).astimezone(UTC)
        if issued > now or expires <= issued or expires <= now:
            raise HostAdmissionError("host-receipt-not-current")
        if type(payload["trusted"]) is not bool or type(payload["enabled"]) is not bool:
            raise HostAdmissionError("invalid-host-trust-state")
        intercepted = frozenset(ActionClass(item) for item in _string_set(
            payload["intercepted_classes"], field="intercepted-classes"
        ))
        withheld = frozenset(ActionClass(item) for item in _string_set(
            payload["withheld_classes"], field="withheld-classes"
        ))
        granted = frozenset(ActionClass(item) for item in _string_set(
            payload["granted_classes"], field="granted-classes"
        ))
        _string_set(payload["feature_inventory"], field="feature-inventory")
        _string_set(payload["accepted_flags"], field="accepted-flags")
        try:
            capabilities = HostCapabilities(
                session_id=self.session_id,
                challenge_nonce=self.challenge_nonce,
                config_sha256=self.config_sha256,
                hook_sha256=self.hook_sha256,
                trusted=payload["trusted"],
                enabled=payload["enabled"],
                intercepted_classes=intercepted,
                withheld_classes=withheld,
                granted_classes=granted,
                issued_at_utc=payload["issued_at_utc"],
                expires_at_utc=payload["expires_at_utc"],
                host_signature=mac,
            )
        except ValueError as exc:
            raise HostAdmissionError(str(exc)) from exc
        governance = (
            GovernanceLevel.FULLY_GOVERNED
            if capabilities.trusted and capabilities.enabled
            else GovernanceLevel.HOST_CAPABILITY_UNSATISFIED
        )
        if governance != GovernanceLevel.FULLY_GOVERNED:
            raise HostAdmissionError("host-capability-unsatisfied")
        receipt_hash = sha256_bytes(canonical_bytes(dict(receipt)))
        self.journal.append("host_capability_recorded", {
            "session_id": self.session_id,
            "challenge_nonce": self.challenge_nonce,
            "governance_level": governance.value,
            "config_sha256": self.config_sha256,
            "hook_sha256": self.hook_sha256,
            "intercepted_classes": sorted(item.value for item in intercepted),
            "withheld_classes": sorted(item.value for item in withheld),
            "granted_classes": sorted(item.value for item in granted),
            "expires_at_utc": payload["expires_at_utc"],
            "evidence_ref": f"host-receipt:{receipt_id}",
            "receipt_sha256": receipt_hash,
        })
        return capabilities

    def observe_action(
        self,
        capabilities: HostCapabilities,
        *,
        host_action_id: str,
        action_class: ActionClass,
        capability_manifest_sha256: str,
        observed_at_utc: str,
    ) -> dict[str, Any]:
        if capabilities.session_id != self.session_id:
            raise HostAdmissionError("host-action-session-mismatch")
        action_class = ActionClass(action_class)
        if action_class not in capabilities.intercepted_classes:
            raise HostAdmissionError("host-action-class-not-intercepted")
        return self.journal.append("host_action_observed", {
            "host_action_id": require_id(host_action_id, label="host-action-id"),
            "session_id": self.session_id,
            "action_class": action_class.value,
            "observed_at_utc": observed_at_utc,
            "capability_manifest_sha256": require_sha256(
                capability_manifest_sha256, label="capability-manifest-sha256"
            ),
        })


def _controller_journal_from_environment() -> PreventionJournal:
    import os
    try:
        root = Path(os.environ["WORKFLOW_ORCH_PREVENTION_RUN_ROOT"])
        ownership = json.loads(os.environ["WORKFLOW_ORCH_PREVENTION_OWNERSHIP"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise HostAdmissionError("controller-journal-context-unavailable") from exc
    if not isinstance(ownership, Mapping):
        raise HostAdmissionError("controller-journal-context-invalid")
    try:
        return PreventionJournal(root, JournalOwnership(**dict(ownership)))
    except (TypeError, ValueError) as exc:
        raise HostAdmissionError("controller-journal-context-invalid") from exc


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv != ["--launcher-controller"]:
        return 2
    try:
        value = json.load(sys.stdin)
        if isinstance(value, Mapping) and value.get("message_kind") == "HOST_CAPABILITY_ADMISSION":
            _capabilities, reply = consume_controller_admission(
                value, _controller_journal_from_environment(),
                key=read_inherited_receipt_key(),
            )
            sys.stdout.buffer.write(canonical_bytes(reply))
            return 0
        sys.stdout.buffer.write(canonical_bytes(run_pre_tool_hook(value)))
        return 0
    except (HostAdmissionError, ValueError, OSError, json.JSONDecodeError):
        sys.stdout.buffer.write(canonical_bytes(deny_hook("PREVENTION_CONTROLLER_DENIED")))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
