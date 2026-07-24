from __future__ import annotations

import json
import socket
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts import prevention_contract, prevention_host, prevention_journal


NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
KEY = b"k" * 32
SESSION_ID = "session-1"
NONCE = "challenge-1"
CONFIG_HASH = "a" * 64
HOOK_HASH = "b" * 64


def journal(tmp_path: Path) -> prevention_journal.PreventionJournal:
    return prevention_journal.PreventionJournal(
        tmp_path / "run",
        prevention_journal.JournalOwnership(
            task_id="task-123",
            run_id="4f642f31-f326-4b2c-92e4-753826ecad9f",
            branch_ref="task/task-123",
            worktree_id="c" * 64,
        ),
    )


def verifier(tmp_path: Path) -> prevention_host.HostCapabilityVerifier:
    return prevention_host.HostCapabilityVerifier(
        journal(tmp_path),
        key=KEY,
        session_id=SESSION_ID,
        challenge_nonce=NONCE,
        config_sha256=CONFIG_HASH,
        hook_sha256=HOOK_HASH,
        launcher_pid=100,
        child_pid=101,
    )


def payload(**changes):
    intercepted = ["APPLY_PATCH", "BASH", "MCP", "UNIFIED_SHELL"]
    withheld = ["NON_MCP_REMOTE", "SUBAGENT", "WEB_SEARCH_BROWSER"]
    base = {
        "schema_version": 1,
        "receipt_id": "receipt-1",
        "session_id": SESSION_ID,
        "challenge_nonce": NONCE,
        "config_sha256": CONFIG_HASH,
        "hook_sha256": HOOK_HASH,
        "trusted": True,
        "enabled": True,
        "intercepted_classes": intercepted,
        "withheld_classes": withheld,
        "granted_classes": sorted(intercepted + withheld),
        "issued_at_utc": (NOW - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (NOW + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "launcher_pid": 100,
        "child_pid": 101,
        "feature_inventory": ["hooks", "mcp"],
        "accepted_flags": ["--dangerously-bypass-hook-trust", "--enable", "--strict-config"],
        "controller_sha256": prevention_host.authoritative_controller_sha256(),
    }
    return {**base, **changes}


def signed(**changes):
    return prevention_host.sign_receipt(payload(**changes), KEY)


def hook_input(*, tool_name: str = "Bash", **changes):
    base = {
        "cwd": "/tmp/project",
        "hook_event_name": "PreToolUse",
        "model": "gpt-5",
        "permission_mode": "dontAsk",
        "session_id": SESSION_ID,
        "tool_input": {"command": "registered-command"},
        "tool_name": tool_name,
        "tool_use_id": "call-1",
        "transcript_path": None,
        "turn_id": "turn-1",
    }
    return {**base, **changes}


def test_authenticated_full_surface_receipt_is_recorded(tmp_path: Path):
    governed = verifier(tmp_path)

    capabilities = governed.verify(signed(), now=NOW)

    assert capabilities.trusted is True
    assert capabilities.intercepted_classes == {
        prevention_contract.ActionClass.APPLY_PATCH,
        prevention_contract.ActionClass.BASH,
        prevention_contract.ActionClass.MCP,
        prevention_contract.ActionClass.UNIFIED_SHELL,
    }
    events, _ = governed.journal.replay()
    assert events[0]["event_type"] == "host_capability_recorded"
    assert events[0]["governance_level"] == "FULLY_GOVERNED"
    assert events[0]["evidence_ref"] == "host-receipt:receipt-1"


def test_launcher_handoff_is_consumed_by_controller_before_actions(tmp_path: Path):
    governed_journal = journal(tmp_path)
    receipt = signed()
    envelope = {
        "schema_version": 1,
        "message_kind": "HOST_CAPABILITY_ADMISSION",
        "host_capability_receipt": receipt,
    }

    capabilities, reply = prevention_host.consume_controller_admission(
        envelope, governed_journal, key=KEY, now=NOW,
    )

    assert capabilities.session_id == SESSION_ID
    assert reply == {
        "schema_version": 1,
        "admission_decision": "accept",
        "receipt_id": "receipt-1",
        "receipt_sha256": prevention_contract.sha256_bytes(
            prevention_contract.canonical_bytes(receipt)
        ),
    }
    prevention_host.HostCapabilityVerifier(
        governed_journal,
        key=KEY,
        session_id=SESSION_ID,
        challenge_nonce=NONCE,
        config_sha256=CONFIG_HASH,
        hook_sha256=HOOK_HASH,
        launcher_pid=100,
        child_pid=101,
    ).observe_action(
        capabilities,
        host_action_id="action-after-admission",
        action_class=prevention_contract.ActionClass.BASH,
        capability_manifest_sha256="e" * 64,
        observed_at_utc=NOW.isoformat().replace("+00:00", "Z"),
    )
    events, _ = governed_journal.replay()
    assert [event["event_type"] for event in events] == [
        "host_capability_recorded", "host_action_observed",
    ]

    with pytest.raises(prevention_host.HostAdmissionError, match="replayed"):
        prevention_host.consume_controller_admission(
            envelope, governed_journal, key=KEY, now=NOW,
        )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda receipt: {**receipt, "config_sha256": "d" * 64},
        lambda receipt: {**receipt, "unknown": True},
    ],
)
def test_tampered_or_extra_receipt_fails_before_ledger_write(tmp_path: Path, mutator):
    governed = verifier(tmp_path)
    receipt = mutator(signed())

    with pytest.raises(prevention_host.HostAdmissionError):
        governed.verify(receipt, now=NOW)

    events, _ = governed.journal.replay()
    assert events == []


def test_uncovered_granted_class_and_expired_receipt_fail_closed(tmp_path: Path):
    governed = verifier(tmp_path)
    with pytest.raises(prevention_host.HostAdmissionError, match="uncovered"):
        governed.verify(signed(withheld_classes=[]), now=NOW)

    expired = signed(
        issued_at_utc=(NOW - timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
        expires_at_utc=(NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
    )
    with pytest.raises(prevention_host.HostAdmissionError, match="not-current"):
        governed.verify(expired, now=NOW)


def test_receipt_is_one_time_and_only_intercepted_actions_are_observed(tmp_path: Path):
    governed = verifier(tmp_path)
    receipt = signed()
    capabilities = governed.verify(receipt, now=NOW)

    with pytest.raises(prevention_host.HostAdmissionError, match="replayed"):
        governed.verify(receipt, now=NOW)
    governed.observe_action(
        capabilities,
        host_action_id="action-1",
        action_class=prevention_contract.ActionClass.BASH,
        capability_manifest_sha256="e" * 64,
        observed_at_utc=NOW.isoformat().replace("+00:00", "Z"),
    )
    with pytest.raises(prevention_host.HostAdmissionError, match="not-intercepted"):
        governed.observe_action(
            capabilities,
            host_action_id="action-2",
            action_class=prevention_contract.ActionClass.SUBAGENT,
            capability_manifest_sha256="e" * 64,
            observed_at_utc=NOW.isoformat().replace("+00:00", "Z"),
        )

    events, _ = governed.journal.replay()
    assert [event["event_type"] for event in events] == [
        "host_capability_recorded",
        "host_action_observed",
    ]


@pytest.mark.parametrize(
    ("tool_name", "action_class"),
    [
        ("Bash", prevention_contract.ActionClass.BASH),
        ("apply_patch", prevention_contract.ActionClass.APPLY_PATCH),
        ("mcp__memory__lookup", prevention_contract.ActionClass.MCP),
    ],
)
def test_official_hook_envelope_maps_supported_tool_names(tool_name, action_class):
    request = prevention_host.parse_hook_request(hook_input(tool_name=tool_name))
    assert request.action_class == action_class


def test_unknown_or_extra_hook_input_fails_closed_without_controller_channel():
    assert prevention_host.run_pre_tool_hook(hook_input(tool_name="browser")) == (
        prevention_host.deny_hook("PREVENTION_CONTROLLER_DENIED")
    )
    assert prevention_host.run_pre_tool_hook(hook_input(extra=True)) == (
        prevention_host.deny_hook("PREVENTION_CONTROLLER_DENIED")
    )


def test_hook_allows_only_same_input_selected_by_controller():
    controller_end, hook_end = socket.socketpair()
    request_value = hook_input(tool_name="apply_patch", tool_input={"patch": "registered"})

    def controller_reply():
        request = json.loads(controller_end.makefile("rb").readline())
        controller_end.sendall(json.dumps({
            "schema_version": 1,
            "tool_use_id": request["tool_use_id"],
            "permission_decision": "allow",
            "decision_kind": "SELECT_REGISTERED",
            "effective_sequence_id": "scoped-context-edit",
            "effective_implementation_id": "f" * 64,
            "updated_input": request["tool_input"],
        }).encode() + b"\n")
        controller_end.close()

    thread = threading.Thread(target=controller_reply)
    thread.start()
    output = prevention_host.run_pre_tool_hook(
        request_value, socket_fd=hook_end.detach()
    )
    thread.join()

    assert output == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": {"patch": "registered"},
        }
    }


def test_cross_input_rewrite_is_denied():
    request = prevention_host.parse_hook_request(hook_input())
    with pytest.raises(prevention_host.HostAdmissionError, match="cross-input"):
        prevention_host.controller_hook_output(request, {
            "schema_version": 1,
            "tool_use_id": request.tool_use_id,
            "permission_decision": "allow",
            "decision_kind": "SELECT_SUCCESSOR",
            "effective_sequence_id": "discovery-promotion-lifecycle",
            "effective_implementation_id": "f" * 64,
            "updated_input": {"command": "different"},
        })
