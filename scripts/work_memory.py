#!/usr/bin/env python3
"""Canonical work-only memory ledger, receipts, bundles, and run lifecycle."""

from __future__ import annotations

import argparse
import base64
import fcntl
import fnmatch
import hashlib
import json
import os
import re
import statistics
import sys
import tempfile
import urllib.parse
import uuid
from collections import Counter, defaultdict
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from scripts import sequence_candidate_contract as candidate_contract
    from scripts import prevention_registry
except ModuleNotFoundError:  # direct script execution
    import sequence_candidate_contract as candidate_contract
    import prevention_registry


SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "operations/work-memory/events.jsonl"
BLOCKER_VIEW = ROOT / "operations/blockers/BLOCKERS.md"
REGISTRY = ROOT / "operations/sequences/SEQUENCES.md"
RECEIPT_ROOT = Path("/private/tmp/work-memory")
HOST_THREAD_ENV = "CODEX_THREAD_ID"
CLIENT_KIND_ENV = "MK_CLIENT_KIND"
CLIENT_SESSION_ENV = "MK_CLIENT_SESSION_ID"
# Claude Code exports CLAUDE_CODE_SESSION_ID. The original constant read CLAUDE_SESSION_ID, a name
# nothing sets, so the schema-v2 claude writer path below was unreachable from a real Claude session
# and every governed command failed with the codex-only error. Canonical name first, legacy second.
CLAUDE_SESSION_ENV = "CLAUDE_CODE_SESSION_ID"
CLAUDE_SESSION_ENV_LEGACY = "CLAUDE_SESSION_ID"
CLAUDE_SESSION_ENVS = (CLAUDE_SESSION_ENV, CLAUDE_SESSION_ENV_LEGACY)
CLIENT_KINDS = {"codex", "claude"}
OWNERSHIP_SCHEMA_VERSIONS = {1, 2}
OWNERSHIP_EVENT_TYPES = {
    "task_writer_claimed", "task_writer_handoff_recorded", "legacy_run_writer_bound",
}
V1_RUN_OWNERSHIP_FIELDS = {
    "task_id", "writer_thread_id", "ownership_generation",
    "ownership_event_id", "ownership_sha256",
}
V2_RUN_OWNERSHIP_FIELDS = {
    "task_id", "writer_id", "writer_client_kind", "writer_session_id",
    "ownership_generation", "ownership_event_id", "ownership_sha256",
}
V2_EVENT_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "task_writer_claimed": (
        {"task_id", "writer_id", "writer_client_kind", "writer_session_id",
         "ownership_generation"}, set(),
    ),
    "task_writer_handoff_recorded": (
        {"task_id", "from_writer_id", "to_writer_id", "to_writer_client_kind",
         "to_writer_session_id", "ownership_generation", "previous_ownership_event_id"},
        {"previous_classification_receipt_hash", "refreshed_classification_receipt_hash",
         "previous_selection_receipt_hash", "refreshed_selection_receipt_hash",
         "previous_active_state_hash", "refreshed_active_state_hash"},
    ),
}
PRE_RUN_BLOCKER_EVENT_TYPES = {
    "pre_run_blocker_opened", "pre_run_correction_recorded",
    "pre_run_verification_recorded", "pre_run_blocker_transitioned",
}
HANDOFF_REFRESH_FIELDS = {
    "previous_classification_receipt_hash", "refreshed_classification_receipt_hash",
    "previous_selection_receipt_hash", "refreshed_selection_receipt_hash",
    "previous_active_state_hash", "refreshed_active_state_hash",
}
OPERATION_KINDS = {
    "image", "container", "auth", "deploy", "workflow-drive", "package",
    "database", "remote-operator", "cleanup", "other", "read-only",
    "single-test", "single-build",
}
ALWAYS_OPERATIONAL = {"image", "container", "auth", "deploy", "workflow-drive"}
CONDITIONAL_OPERATIONAL = {"package", "database", "remote-operator", "cleanup", "other"}
NON_OPERATIONAL = {"read-only", "single-test", "single-build"}
BOOTSTRAP_TRUST_ANCHORS = (
    "scripts/work_memory.py",
    "scripts/work_memory_bootstrap.py",
    "scripts/work_memory_bootstrap_launcher.py",
)
SEQUENCE_INTAKE_CONTROL_DEPENDENCIES = (
    "operations/sequences/sequence-intake-contracts.json",
    "scripts/regenerate_intake_contracts.py",
)
ACTIVE_TRUST_SNAPSHOT_FIELDS = (
    ("scripts/work_memory.py", "sealed_controller_sha256", "sealed_controller_b64"),
    ("scripts/work_memory_bootstrap.py", "bootstrap_sha256", "sealed_bootstrap_b64"),
    (
        "scripts/work_memory_bootstrap_launcher.py",
        "bootstrap_launcher_sha256",
        "sealed_bootstrap_launcher_b64",
    ),
)
EVENT_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "task_writer_claimed": (
        {"task_id", "writer_thread_id", "ownership_generation"}, set(),
    ),
    "task_writer_handoff_recorded": (
        {"task_id", "from_writer_thread_id", "to_writer_thread_id",
         "ownership_generation", "previous_ownership_event_id"},
        {"previous_classification_receipt_hash", "refreshed_classification_receipt_hash",
         "previous_selection_receipt_hash", "refreshed_selection_receipt_hash",
         "previous_active_state_hash", "refreshed_active_state_hash"},
    ),
    "legacy_run_writer_bound": (
        {"task_id", "run_id", "writer_thread_id", "ownership_generation",
         "ownership_event_id", "ownership_sha256", "classification_receipt_hash",
         "selection_receipt_hash"}, set(),
    ),
    "run_started": (
        {"run_id", "subject_id", "lineage_id", "mode", "operation_kind", "source_bundle",
         "source_bundle_hash", "classification_receipt_hash", "selection_receipt_hash",
         "started_at_utc"},
        {"predecessor_run_id", "verifies_correction_ids", "repository_roots",
         "task_id", "writer_thread_id", "ownership_generation",
         "ownership_event_id", "ownership_sha256",
         "writer_id", "writer_client_kind", "writer_session_id"},
    ),
    "blocker_opened": (
        {"run_id", "blocker_id", "occurrence_id", "fingerprint", "subject_id", "lineage_id",
         "step_id", "surface", "symptom", "evidence", "impact", "boundary", "status"}, set(),
    ),
    "pre_run_blocker_opened": (
        {"task_id", "ownership_event_id", "blocker_id", "occurrence_id", "fingerprint",
         "subject_id", "lineage_id", "step_id", "surface", "symptom", "evidence",
         "impact", "boundary", "status"}, set(),
    ),
    "pre_run_correction_recorded": (
        {"task_id", "ownership_event_id", "blocker_id", "occurrence_id", "correction_id",
         "step_id", "changed_artifacts", "changed_artifact_hashes", "solution",
         "reusable_behavior_changed"}, {"supersedes_correction_id"},
    ),
    "pre_run_verification_recorded": (
        {"task_id", "ownership_event_id", "blocker_id", "occurrence_id", "correction_id",
         "verification_command", "outcome", "quality", "evidence",
         "changed_artifact_hashes"}, set(),
    ),
    "pre_run_blocker_transitioned": (
        {"task_id", "ownership_event_id", "blocker_id", "occurrence_id", "from_status",
         "to_status"}, {"verification_event_id", "remaining_work"},
    ),
    "blocker_recurred": (
        {"run_id", "blocker_id", "occurrence_id", "previous_status", "status", "evidence"}, set(),
    ),
    "blocker_assigned_downstream": (
        {"run_id", "blocker_id", "occurrence_id", "classification",
         "downstream_owner", "evidence"}, set(),
    ),
    "correction_recorded": (
        {"run_id", "blocker_id", "occurrence_id", "correction_id", "subject_id", "lineage_id",
         "step_id", "changed_artifacts", "changed_artifact_hashes", "reusable_behavior_changed",
         "solution"}, {"supersedes_correction_id", "supersedes_correction_ids",
                       "primary_correction_id",
                       # A fix can change the ENVIRONMENT a sequence depends on (machine config,
                       # host registry) rather than a file in the sequence's own dependency bundle.
                       # Those surfaces can never drift-match the bundle, so they are recorded and
                       # hashed separately instead of being forced through the bundle drift gate.
                       "environment_artifacts", "environment_artifact_hashes"},
    ),
    "correction_preservation_recorded": (
        {"target_task_id", "preserved_task_id", "subject_id", "lineage_id",
         "target_correction_id", "preserved_correction_ids",
         "target_transition_event_id", "target_verification_event_id",
         "target_bundle_hash",
         "target_writer_thread_id", "target_ownership_generation",
         "target_ownership_event_id", "target_ownership_sha256",
         "preserved_writer_thread_id", "preserved_ownership_generation",
         "preserved_ownership_event_id", "preserved_ownership_sha256"}, set(),
    ),
    "bundle_transition_recorded": (
        {"lineage_id", "old_bundle_hash", "new_bundle_hash", "transition_reason"},
        {"run_id", "correction_ids", "changed_artifacts", "changed_artifact_hashes",
         "discovery_id", "promoted_sequence_id",
         # An environment-surface correction changes no bundle file, so the bundle hash does not
         # move. The transition is still recorded (every downstream consumer links a correction to
         # its transition) but names the environment surface instead of a bundle change.
         "environment_artifacts", "environment_artifact_hashes"},
    ),
    "verification_recorded": (
        {"run_id", "subject_id", "lineage_id", "source_bundle_hash", "outcome", "quality",
         "evidence", "blocker_ids", "correction_ids", "changed_artifact_hashes"},
        # A verified environment-surface correction carries no bundle hashes; its proof binds to
        # the environment hashes instead.
        {"environment_artifact_hashes"},
    ),
    "blocker_transitioned": (
        {"run_id", "blocker_id", "from_status", "to_status"},
        {"verification_event_id", "remaining_work", "supersession_evidence", "non_gap_evidence",
         "reopen_evidence", "recovery_evidence", "reconciliation_basis_event_id"},
    ),
    "run_closed": (
        {"run_id", "subject_id", "lineage_id", "result", "completed_at_utc", "correction_count",
         "blocker_ids", "sequence_updated", "verification_quality"}, set(),
    ),
    "run_abandoned": (
        {"run_id", "subject_id", "lineage_id", "completed_at_utc", "reason"}, set(),
    ),
    "discovery_promoted": (
        {"discovery_id", "sequence_id", "lineage_id", "old_bundle_hash", "new_bundle_hash",
         "promoted_at_utc"}, set(),
    ),
    "operation_context_recorded": (
        {"context_id", "run_id", "subject_id", "lineage_id", "source_bundle_hash",
         "repository_roots_hash", "intended_outcome", "repeatability_reason",
         "repeatability_evidence_ids", "required_inputs", "dependencies", "failure_handling",
         "verification_contract", "effect_class", "environment_annotations",
         "semantic_flag_annotations", "volatility_annotations"}, set(),
    ),
    "execution_claimed": (
        {"execution_id", "context_id", "run_id", "subject_id", "lineage_id",
         "source_bundle_hash", "step_ordinal", "step_id", "argv", "command_sha256",
         "command_source", "source_ref", "repository_roots_hash", "operation_kind",
         "effect_class", "claimed_at_utc"}, set(),
    ),
    "execution_returned": (
        {"execution_id", "context_id", "run_id", "subject_id", "lineage_id",
         "source_bundle_hash", "exit_code", "result", "returned_at_utc"}, set(),
    ),
    "observer_decision_recorded": (
        {"decision_id", "observer_version", "rule_version", "config_hash",
         "trigger_event_id", "trigger_type", "ledger_snapshot_hash", "evidence_event_ids",
         "evidence_set_hash", "candidate_identity", "candidate_fingerprint", "eligibility",
         "value_components", "threshold", "considered_registered_ids",
         "considered_discovery_ids", "disposition", "target_kind", "target_id",
         "suppression", "cap_cursor", "safe_failure_code"}, set(),
    ),
    "observer_bootstrap_result_recorded": (
        {"bootstrap_attempt_id", "attempt_ordinal", "decision_id",
         "bootstrap_request_sha256", "outcome", "safe_error_code", "retryable",
         "discovery_id", "lineage_id", "run_id", "source_bundle_hash",
         "document_path", "manifest_path"}, set(),
    ),
    "observer_candidate_linked": (
        {"link_id", "decision_id", "candidate_fingerprint", "target_kind",
         "target_id", "link_kind"}, set(),
    ),
}
PREVENTION_OWNERSHIP_FIELDS = {"task_id", "run_id", "branch_ref", "worktree_id"}
PREVENTION_EVENT_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "action_intent_recorded": (
        {"intent_id", "requested_sequence_id", "requested_implementation_id",
         "compatibility_key", "action_class", "parameters"}, set(),
    ),
    "action_eligibility_recorded": (
        {"intent_id", "registry_sha256", "owner_sequence_id", "owner_contract_sha256",
         "recurrence_policy", "availability_policy", "eligibility",
         "ineligible_reason_code"}, set(),
    ),
    "host_capability_recorded": (
        {"session_id", "challenge_nonce", "governance_level", "config_sha256", "hook_sha256",
         "intercepted_classes", "withheld_classes", "granted_classes", "expires_at_utc",
         "evidence_ref", "receipt_sha256"}, set(),
    ),
    "host_action_observed": (
        {"host_action_id", "session_id", "action_class", "observed_at_utc",
         "capability_manifest_sha256"}, set(),
    ),
    "dispatch_selected": (
        {"intent_id", "decision_id", "decision_kind", "effective_sequence_id",
         "effective_implementation_id", "selected_owner_sequence_id",
         "selected_owner_contract_sha256", "reason_code", "selector_milliseconds"}, set(),
    ),
    "dispatch_rejected": (
        {"intent_id", "decision_id", "decision_kind", "reason_code", "selector_milliseconds"}, set(),
    ),
    "predecessor_prohibited": (
        {"compatibility_key", "failure_fingerprint", "predecessor_sequence_id",
         "predecessor_implementation_id", "successor_sequence_id", "successor_implementation_id",
         "verification_event_id"}, set(),
    ),
    "budget_admitted": (
        {"reservation_id", "owner_sequence_id", "unit_budget", "reserved_vector",
         "remaining_vector_before", "lease_expires_at_utc"}, set(),
    ),
    "budget_rejected": (
        {"owner_sequence_id", "unit_budget", "required_vector", "remaining_vector",
         "failed_dimensions", "reason_code"}, set(),
    ),
    "transition_prepared": ({"journal_id", "transition", "state_hash"}, set()),
    "transition_committed": (
        {"journal_id", "transition", "state_hash", "prepared_event_id"}, set(),
    ),
    "effect_prepared": (
        {"journal_id", "effect_id", "idempotency_key", "effect_kind", "owner_sequence_id",
         "implementation_id", "effect_task_id", "effect_run_id", "effect_branch_ref",
         "effect_worktree_id", "transition_prepared_event_id", "owner_contract_sha256",
         "reconciler_sha256", "preparation_artifact_sha256"}, set(),
    ),
    "effect_committed": (
        {"journal_id", "effect_id", "prepared_event_id", "attempt_generation",
         "execution_started_event_id", "result_hash", "exit_status"}, set(),
    ),
    "effect_reconciled": (
        {"journal_id", "effect_id", "prepared_event_id", "attempt_generation",
         "owner_contract_sha256", "reconciler_sha256", "preparation_artifact_sha256",
         "reconciliation", "reconciliation_artifact_sha256",
         "observable_ownership_sha256", "evidence_sha256"},
        {"prior_reconciliation_event_id"},
    ),
    "effect_execution_authorized": (
        {"journal_id", "effect_id", "attempt_generation", "prior_generation",
         "not_applied_reconciliation_event_id", "owner_contract_sha256",
         "authorization_sha256"}, set(),
    ),
    "effect_execution_started": (
        {"journal_id", "effect_id", "attempt_generation",
         "execution_authorized_event_id", "owner_contract_sha256"}, set(),
    ),
    "owner_binding_recorded": (
        {"intent_id", "effect_id", "owner_sequence_id", "owner_contract_sha256",
         "parameter_name", "receipt_id", "binding_kind", "provider_id",
         "key_or_resource_id", "version_id", "scope_sha256",
         "value_fingerprint_sha256", "consumable", "binding_receipt_sha256"},
        {"expires_at_utc"},
    ),
    "authorization_receipt_consumed": (
        {"receipt_id", "provider_id", "version_id", "scope_sha256", "intent_id",
         "effect_id", "owner_sequence_id", "owner_contract_sha256",
         "effect_prepared_event_id"}, set(),
    ),
    "child_delegation_recorded": (
        {"delegation_id", "parent_effect_id", "parent_owner_sequence_id",
         "child_owner_sequence_id", "child_intent_id", "blocker_id",
         "verification_event_id", "mode"}, set(),
    ),
    "child_delegation_consumed": (
        {"delegation_id", "parent_effect_id", "child_effect_id", "child_intent_id",
         "effect_prepared_event_id"}, set(),
    ),
    "owner_terminal": (
        {"effect_id", "owner_sequence_id", "owner_contract_sha256", "result_kind",
         "result_hash", "terminal_evidence_sha256", "terminal_artifact_sha256",
         "semantic_verdict"},
        {"effect_committed_event_id", "attempt_generation", "execution_started_event_id",
         "reconciliation_event_id", "reconciliation_artifact_sha256"},
    ),
    "registered_reuse_recorded": (
        {"intent_id", "decision_id", "compatibility_key", "sequence_id", "implementation_id",
         "promotion_event_id", "registered_verification_event_id", "pre_dispatch"}, set(),
    ),
    "prevented_failure_recorded": (
        {"intent_id", "decision_id", "compatibility_key", "failure_fingerprint",
         "predecessor_implementation_id", "prohibition_event_id"},
        {"successor_implementation_id"},
    ),
    "timing_interval_recorded": (
        {"interval_id", "timing_class", "started_at_utc", "ended_at_utc",
         "duration_milliseconds"}, {"intent_id", "decision_id"},
    ),
}
for _event_type, (_required, _optional) in PREVENTION_EVENT_FIELDS.items():
    EVENT_FIELDS[_event_type] = (_required | PREVENTION_OWNERSHIP_FIELDS, _optional)
PREVENTION_EVENT_TYPES = frozenset(PREVENTION_EVENT_FIELDS)
BASE_FIELDS = {"schema_version", "event_id", "event_type", "recorded_at_utc"}
FORBIDDEN_KEYS = {
    "person", "people", "contact", "relationship", "profile", "diary", "journal",
    "transcript", "conversation_history", "chat_history", "message_history",
    "password", "passwd", "secret", "token", "api_key", "access_token", "refresh_token",
    "private_key", "credential", "credentials", "auth_payload",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.I),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"(?:\?|&)sig=[^&\s]+", re.I),
)
PERSONAL_PATTERNS = (
    re.compile(r"\b(?:my|our|his|her|their)\s+(?:wife|husband|partner|mother|father|family|health)\b", re.I),
    re.compile(r"\b(?:i|we|[A-Z][a-z]+)\s+(?:prefer|prefers|like|likes|love|loves|hate|hates|feel|feels|went|visited|ate|slept)\b", re.I),
    re.compile(r"\b(?:diary|journal)\s+entry\b", re.I),
    re.compile(r"\b(?:user|personal)\s+profile\b", re.I),
)
CREDENTIAL_ARGUMENT_NAMES = {
    "password", "passwd", "secret", "token", "api_key", "access_token",
    "refresh_token", "private_key", "credential", "credentials", "auth_payload",
}


REGISTRY_GOVERNANCE_LEVEL = os.environ.get(
    "WORK_MEMORY_REGISTRY_GOVERNANCE_LEVEL", "FULLY_GOVERNED"
)


def configure_root(root: Path, *, registry_governance_level: str | None = None) -> None:
    """Rebind canonical repository-owned paths for an isolated invocation or test root."""
    global ROOT, LEDGER, BLOCKER_VIEW, REGISTRY, REGISTRY_GOVERNANCE_LEVEL
    registry_governance_level = registry_governance_level or os.environ.get(
        "WORK_MEMORY_REGISTRY_GOVERNANCE_LEVEL", "FULLY_GOVERNED"
    )
    if registry_governance_level not in {"FULLY_GOVERNED", "UNGOVERNED_DIAGNOSTIC"}:
        raise ValueError("invalid-registry-governance-level")
    ROOT = root.resolve()
    LEDGER = ROOT / "operations/work-memory/events.jsonl"
    BLOCKER_VIEW = ROOT / "operations/blockers/BLOCKERS.md"
    REGISTRY = ROOT / "operations/sequences/SEQUENCES.md"
    REGISTRY_GOVERNANCE_LEVEL = registry_governance_level


class WorkMemoryError(Exception):
    def __init__(self, code: str, exit_code: int = 3):
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise WorkMemoryError("invalid-timestamp", 2) from exc
    if parsed.tzinfo is None:
        raise WorkMemoryError("invalid-timestamp", 2)
    return parsed.astimezone(UTC)


def require_uuid(value: Any, field: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise WorkMemoryError(f"invalid-{field}", 2) from exc


def require_id(value: Any, field: str) -> str:
    text = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", text):
        raise WorkMemoryError(f"invalid-{field}", 2)
    return text


def _require_hash(value: Any, field: str) -> str:
    text = str(value or "")
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise WorkMemoryError(f"invalid-{field}", 2)
    return text


def host_thread_id() -> str:
    value = os.environ.get(HOST_THREAD_ENV)
    if not value:
        raise WorkMemoryError("host-codex-thread-id-required", 4)
    canonical = require_uuid(value, "host-codex-thread-id")
    if canonical != value:
        raise WorkMemoryError("invalid-host-codex-thread-id", 4)
    return canonical


WRITER_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "memory-knowledge:work-memory:writer")


def claude_session_id() -> str | None:
    """The host-exported Claude session, canonical name first so the writer id stays stable across
    a session regardless of which name a caller happens to set."""
    for name in CLAUDE_SESSION_ENVS:
        value = os.environ.get(name)
        if value:
            return value
    return None


def writer_identity() -> dict[str, Any]:
    """Versioned host/session identity. Legacy CODEX_THREAD_ID stays a schema-v1 writer;
    a Claude session (or any explicit client identity) is a schema-v2 writer whose neutral
    ledger UUID is derived from client kind plus session, so cross-client records cannot collide."""
    kind = os.environ.get(CLIENT_KIND_ENV)
    if kind is not None and kind not in CLIENT_KINDS:
        raise WorkMemoryError("invalid-client-kind", 4)
    session = os.environ.get(CLIENT_SESSION_ENV)
    if kind is None:
        if os.environ.get(HOST_THREAD_ENV):
            thread = host_thread_id()
            return {"schema_version": 1, "writer_client_kind": "codex",
                    "writer_session_id": thread, "writer_id": thread}
        claude_session = claude_session_id()
        if claude_session:
            kind, session = "claude", claude_session
        else:
            raise WorkMemoryError("writer-identity-required", 4)
    elif kind == "codex" and not session:
        thread = host_thread_id()
        return {"schema_version": 1, "writer_client_kind": "codex",
                "writer_session_id": thread, "writer_id": thread}
    elif kind == "claude" and not session:
        session = claude_session_id()
    if not session:
        raise WorkMemoryError("client-session-id-required", 4)
    canonical = require_uuid(session, "client-session-id")
    writer_id = str(uuid.uuid5(WRITER_ID_NAMESPACE, f"{kind}:{canonical}"))
    return {"schema_version": 2, "writer_client_kind": kind,
            "writer_session_id": canonical, "writer_id": writer_id}


def _ownership_sha256(
    task_id: str, writer_thread_id: str, generation: int, ownership_event_id: str,
) -> str:
    return sha256_bytes(canonical_bytes({
        "task_id": task_id,
        "writer_thread_id": writer_thread_id,
        "ownership_generation": generation,
        "ownership_event_id": ownership_event_id,
    }))


def _ownership_sha256_v2(
    task_id: str, writer_id: str, writer_client_kind: str, writer_session_id: str,
    generation: int, ownership_event_id: str,
) -> str:
    return sha256_bytes(canonical_bytes({
        "task_id": task_id,
        "writer_id": writer_id,
        "writer_client_kind": writer_client_kind,
        "writer_session_id": writer_session_id,
        "ownership_generation": generation,
        "ownership_event_id": ownership_event_id,
    }))


def _state_ownership_sha256(task_id: str, state: dict[str, Any]) -> str:
    if state.get("schema_version") == 2:
        return _ownership_sha256_v2(
            task_id, state["writer_thread_id"], state["writer_client_kind"],
            state["writer_session_id"], state["ownership_generation"],
            state["ownership_event_id"],
        )
    return _ownership_sha256(
        task_id, state["writer_thread_id"], state["ownership_generation"],
        state["ownership_event_id"],
    )


def _ownership_receipt_fields(task_id: str, state: dict[str, Any]) -> dict[str, Any]:
    if state.get("schema_version") == 2:
        return {
            "writer_id": state["writer_thread_id"],
            "writer_client_kind": state["writer_client_kind"],
            "writer_session_id": state["writer_session_id"],
            "ownership_generation": state["ownership_generation"],
            "ownership_event_id": state["ownership_event_id"],
            "ownership_sha256": _state_ownership_sha256(task_id, state),
        }
    return {
        "writer_thread_id": state["writer_thread_id"],
        "ownership_generation": state["ownership_generation"],
        "ownership_event_id": state["ownership_event_id"],
        "ownership_sha256": _state_ownership_sha256(task_id, state),
    }


def _prefixed_ownership_receipt_fields(
    prefix: str, task_id: str, state: dict[str, Any],
) -> dict[str, Any]:
    return {f"{prefix}_{key}": value
            for key, value in _ownership_receipt_fields(task_id, state).items()}


def _ownership_snapshot(
    events: Sequence[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str | None]]:
    tasks: dict[str, dict[str, Any]] = {}
    runs: dict[str, str | None] = {}
    starts: dict[str, dict[str, Any]] = {}
    for event in events:
        kind = event["event_type"]
        if kind == "task_writer_claimed":
            task_id = event["task_id"]
            if task_id in tasks or event["ownership_generation"] != 1:
                raise WorkMemoryError("task-writer-already-claimed", 3)
            if event.get("schema_version") == 2:
                tasks[task_id] = {
                    "schema_version": 2,
                    "writer_thread_id": event["writer_id"],
                    "writer_client_kind": event["writer_client_kind"],
                    "writer_session_id": event["writer_session_id"],
                    "ownership_generation": 1,
                    "ownership_event_id": event["event_id"],
                }
            else:
                tasks[task_id] = {
                    "writer_thread_id": event["writer_thread_id"],
                    "ownership_generation": 1,
                    "ownership_event_id": event["event_id"],
                }
            continue
        if kind == "task_writer_handoff_recorded":
            task_id = event["task_id"]
            current = tasks.get(task_id)
            if event.get("schema_version") == 2:
                from_writer = event["from_writer_id"]
                to_writer = event["to_writer_id"]
            else:
                from_writer = event["from_writer_thread_id"]
                to_writer = event["to_writer_thread_id"]
            if (
                current is None
                or from_writer != current["writer_thread_id"]
                or event["previous_ownership_event_id"] != current["ownership_event_id"]
                or event["ownership_generation"] != current["ownership_generation"] + 1
                or to_writer == from_writer
            ):
                raise WorkMemoryError("invalid-task-writer-handoff", 3)
            if event.get("schema_version") == 2:
                tasks[task_id] = {
                    "schema_version": 2,
                    "writer_thread_id": to_writer,
                    "writer_client_kind": event["to_writer_client_kind"],
                    "writer_session_id": event["to_writer_session_id"],
                    "ownership_generation": event["ownership_generation"],
                    "ownership_event_id": event["event_id"],
                }
            else:
                tasks[task_id] = {
                    "writer_thread_id": to_writer,
                    "ownership_generation": event["ownership_generation"],
                    "ownership_event_id": event["event_id"],
                }
            continue
        if kind == "run_started":
            run_id = event["run_id"]
            starts[run_id] = event
            present = (V1_RUN_OWNERSHIP_FIELDS | V2_RUN_OWNERSHIP_FIELDS) & set(event)
            if not present:
                runs[run_id] = None
                continue
            family = V2_RUN_OWNERSHIP_FIELDS if "writer_id" in event else V1_RUN_OWNERSHIP_FIELDS
            if present != family:
                raise WorkMemoryError("incomplete-run-writer-binding", 2)
            task_id = event["task_id"]
            current = tasks.get(task_id)
            if current is None:
                raise WorkMemoryError("run-task-writer-unclaimed", 3)
            expected = {"task_id": task_id, **_ownership_receipt_fields(task_id, current)}
            if set(expected) != family or any(event.get(key) != value for key, value in expected.items()):
                raise WorkMemoryError("run-task-writer-binding-mismatch", 3)
            runs[run_id] = task_id
            continue
        if kind == "legacy_run_writer_bound":
            task_id = event["task_id"]
            run_id = event["run_id"]
            start = starts.get(run_id)
            current = tasks.get(task_id)
            if start is None or runs.get(run_id) is not None:
                raise WorkMemoryError("legacy-run-not-unbound", 3)
            if current is None:
                raise WorkMemoryError("legacy-run-task-writer-unclaimed", 3)
            if current.get("schema_version") == 2:
                raise WorkMemoryError("legacy-run-writer-binding-mismatch", 3)
            expected = _ownership_receipt_fields(task_id, current)
            if (
                event["writer_thread_id"] != expected["writer_thread_id"]
                or event["ownership_generation"] != expected["ownership_generation"]
                or event["ownership_event_id"] != expected["ownership_event_id"]
                or event["ownership_sha256"] != expected["ownership_sha256"]
                or event["classification_receipt_hash"] != start["classification_receipt_hash"]
                or event["selection_receipt_hash"] != start["selection_receipt_hash"]
            ):
                raise WorkMemoryError("legacy-run-writer-binding-mismatch", 3)
            runs[run_id] = task_id
    return tasks, runs


def _secret_variants(value: str) -> list[str]:
    decoded = value
    for _ in range(3):
        next_value = urllib.parse.unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    fragments = [decoded]
    for separator in ("=", ":"):
        if separator in decoded:
            fragments.append(decoded.split(separator, 1)[1])
    variants = list(dict.fromkeys(fragments))
    for fragment in fragments:
        compact = fragment.strip()
        if not re.fullmatch(r"[A-Za-z0-9_+/=-]{16,}", compact):
            continue
        try:
            padding = "=" * (-len(compact) % 4)
            raw = base64.urlsafe_b64decode(compact + padding)
            revealed = raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if revealed not in variants:
            variants.append(revealed)
    return variants


def _validate_execution_argv(argv: list[str]) -> None:
    for index, token in enumerate(argv):
        key = re.split(r"[=:]", token, maxsplit=1)[0]
        normalized = key.lstrip("-").lower().replace("-", "_")
        if normalized in CREDENTIAL_ARGUMENT_NAMES:
            raise WorkMemoryError(f"prohibited-credential-argument:$.argv[{index}]", 2)
        for variant in _secret_variants(token):
            try:
                structured = json.loads(variant)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(structured, (dict, list)):
                _validate_work_only(structured, f"$.argv[{index}]")


WORK_MEMORY_ARRAY_MAX_ITEMS = 100
SOURCE_BUNDLE_MAX_ITEMS = 4096
OBSERVER_EVIDENCE_MAX_ITEMS = 512


def _validate_work_only(
    value: Any, path: str = "$", *, array_limits: Mapping[str, int] | None = None,
) -> None:
    limits = array_limits or {}
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise WorkMemoryError(f"prohibited-memory-shape:{path}.{key}", 2)
            _validate_work_only(
                child, f"{path}.{key}", array_limits=limits,
            )
    elif isinstance(value, list):
        maximum = limits.get(path, WORK_MEMORY_ARRAY_MAX_ITEMS)
        if len(value) > maximum:
            raise WorkMemoryError(f"work-memory-array-too-large:{path}", 2)
        for index, child in enumerate(value):
            _validate_work_only(
                child, f"{path}[{index}]", array_limits=limits,
            )
    elif isinstance(value, str):
        if len(value) > 4000:
            raise WorkMemoryError(f"work-memory-text-too-large:{path}", 2)
        variants = _secret_variants(value)
        if any(pattern.search(item) for item in variants for pattern in SECRET_PATTERNS):
            raise WorkMemoryError(f"prohibited-secret-shape:{path}", 2)
        if any(pattern.search(item) for item in variants for pattern in PERSONAL_PATTERNS):
            raise WorkMemoryError(f"prohibited-memory-shape:{path}", 2)


def _validate_event_shape(event: dict[str, Any]) -> None:
    if not isinstance(event, dict):
        raise WorkMemoryError("event-must-be-object", 2)
    event_type = event.get("event_type")
    if event_type not in EVENT_FIELDS:
        raise WorkMemoryError("unknown-event-type", 2)
    version = event.get("schema_version")
    if version == 2 and event_type in V2_EVENT_FIELDS:
        required, optional = V2_EVENT_FIELDS[event_type]
    else:
        required, optional = EVENT_FIELDS[event_type]
    allowed = BASE_FIELDS | required | optional
    missing = (BASE_FIELDS | required) - set(event)
    extra = set(event) - allowed
    if missing:
        raise WorkMemoryError("missing-event-fields:" + ",".join(sorted(missing)), 2)
    if extra:
        raise WorkMemoryError("unknown-event-fields:" + ",".join(sorted(extra)), 2)
    if version != SCHEMA_VERSION and not (version == 2 and event_type in V2_EVENT_FIELDS):
        raise WorkMemoryError("unsupported-event-schema", 2)
    require_uuid(event["event_id"], "event-id")
    parse_utc(event["recorded_at_utc"])
    array_limits = None
    if event_type == "run_started":
        array_limits = {"$.source_bundle": SOURCE_BUNDLE_MAX_ITEMS}
    elif event_type == "observer_decision_recorded":
        array_limits = {"$.evidence_event_ids": OBSERVER_EVIDENCE_MAX_ITEMS}
    _validate_work_only(event, array_limits=array_limits)
    _validate_event_values(event)


def _require_list(event: dict[str, Any], field: str, *, nonempty: bool = False) -> list[Any]:
    value = event.get(field)
    if not isinstance(value, list) or (nonempty and not value):
        raise WorkMemoryError(f"invalid-{field.replace('_', '-')}", 2)
    return value


def _optional_list(event: dict[str, Any], field: str) -> list[Any]:
    """An absent optional list field reads as empty; a present one must be a real list."""
    if field not in event:
        return []
    return _require_list(event, field)


def _superseded_correction_ids(event: dict[str, Any]) -> set[str]:
    single = event.get("supersedes_correction_id")
    multiple = event.get("supersedes_correction_ids")
    if single is not None and multiple is not None:
        raise WorkMemoryError("ambiguous-superseded-corrections", 2)
    if single is not None:
        require_uuid(single, "supersedes-correction-id")
        return {single}
    if multiple is None:
        return set()
    values = _require_list(event, "supersedes_correction_ids", nonempty=True)
    if len(values) != len(set(values)):
        raise WorkMemoryError("duplicate-superseded-correction-id", 2)
    for value in values:
        require_uuid(value, "supersedes-correction-id")
    return set(values)


def _active_correction_artifacts_preserved(
    correction_rows: Iterable[dict[str, Any]],
    failed_start: dict[str, Any], current_start: dict[str, Any],
) -> bool:
    if failed_start["source_bundle_hash"] == current_start["source_bundle_hash"]:
        return True
    failed_bundle = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in failed_start["source_bundle"]
    }
    current_bundle = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in current_start["source_bundle"]
    }
    saw_artifact = False
    for correction in correction_rows:
        artifacts = correction["changed_artifacts"]
        hashes = correction["changed_artifact_hashes"]
        if not artifacts:
            return False
        saw_artifact = True
        for artifact, expected_hash in zip(artifacts, hashes, strict=True):
            identity = _artifact_identity(artifact)
            if (
                failed_bundle.get(identity) != expected_hash
                or current_bundle.get(identity) != expected_hash
            ):
                return False
    return saw_artifact


def _failed_retry_verification(
    events: Sequence[dict[str, Any]], *, run_id: str, blocker_id: str,
    occurrence_id: str, supersedes_correction_ids: Iterable[str],
) -> dict[str, Any] | None:
    """Return the failed same-path proof authorizing a correction retry, if exact."""
    correction_rows = [
        event for event in events
        if event["event_type"] == "correction_recorded"
    ]
    superseded = {
        correction_id
        for event in correction_rows
        for correction_id in _superseded_correction_ids(event)
    }
    active = {
        event["correction_id"]: event
        for event in correction_rows
        if event["blocker_id"] == blocker_id
        and event["occurrence_id"] == occurrence_id
        and event["correction_id"] not in superseded
    }
    requested = set(supersedes_correction_ids)
    if not active or requested != set(active):
        return None
    starts = {
        event["run_id"]: event for event in events
        if event["event_type"] == "run_started"
    }
    current_start = starts.get(run_id)
    if current_start is None:
        return None
    ancestor_ids: set[str] = set()
    cursor = current_start.get("predecessor_run_id")
    while cursor is not None and cursor not in ancestor_ids:
        ancestor_ids.add(cursor)
        cursor = starts.get(cursor, {}).get("predecessor_run_id")
    terminal_ancestor_ids = {
        event["run_id"] for event in events
        if event["event_type"] == "run_closed"
        and event["result"] == "failed"
        and event["verification_quality"] == "same-path"
    }
    for event in reversed(events):
        if not (
            event["event_type"] == "verification_recorded"
            and (
                event["run_id"] == run_id
                or event["run_id"] in ancestor_ids
                and event["run_id"] in terminal_ancestor_ids
            )
            and event["subject_id"] == current_start["subject_id"]
            and event["lineage_id"] == current_start["lineage_id"]
            and event["outcome"] == "failed"
            and event["quality"] == "same-path"
            and blocker_id in event["blocker_ids"]
            and set(active) <= set(event["correction_ids"])
        ):
            continue
        failed_start = starts[event["run_id"]]
        if _active_correction_artifacts_preserved(
            active.values(), failed_start, current_start,
        ):
            return event
    return None


def _validate_event_values(event: dict[str, Any]) -> None:
    kind = event["event_type"]
    for field in ("run_id", "occurrence_id", "correction_id", "predecessor_run_id"):
        if field in event and event[field] is not None:
            require_uuid(event[field], field.replace("_", "-"))
    if kind in OWNERSHIP_EVENT_TYPES:
        require_id(event["task_id"], "task-id")
        v2_ownership = event.get("schema_version") == 2
        if kind == "task_writer_claimed":
            if v2_ownership:
                require_uuid(event["writer_id"], "writer-id")
                require_uuid(event["writer_session_id"], "writer-session-id")
                if event["writer_client_kind"] not in CLIENT_KINDS:
                    raise WorkMemoryError("invalid-writer-client-kind", 2)
            else:
                require_uuid(event["writer_thread_id"], "writer-thread-id")
            if event["ownership_generation"] != 1:
                raise WorkMemoryError("invalid-ownership-generation", 2)
        elif kind == "task_writer_handoff_recorded":
            if v2_ownership:
                require_uuid(event["from_writer_id"], "from-writer-id")
                require_uuid(event["to_writer_id"], "to-writer-id")
                require_uuid(event["to_writer_session_id"], "to-writer-session-id")
                if event["to_writer_client_kind"] not in CLIENT_KINDS:
                    raise WorkMemoryError("invalid-writer-client-kind", 2)
            else:
                require_uuid(event["from_writer_thread_id"], "from-writer-thread-id")
                require_uuid(event["to_writer_thread_id"], "to-writer-thread-id")
            require_uuid(event["previous_ownership_event_id"], "previous-ownership-event-id")
            if (
                isinstance(event["ownership_generation"], bool)
                or not isinstance(event["ownership_generation"], int)
                or event["ownership_generation"] < 2
            ):
                raise WorkMemoryError("invalid-ownership-generation", 2)
            refresh_fields = HANDOFF_REFRESH_FIELDS
            present_refresh_fields = refresh_fields & set(event)
            if present_refresh_fields:
                if present_refresh_fields not in (
                    {
                        "previous_classification_receipt_hash",
                        "refreshed_classification_receipt_hash",
                    },
                    {
                        "previous_classification_receipt_hash",
                        "refreshed_classification_receipt_hash",
                        "previous_selection_receipt_hash",
                        "refreshed_selection_receipt_hash",
                    },
                    refresh_fields,
                ):
                    raise WorkMemoryError("incomplete-task-writer-refresh-binding", 2)
                for field in present_refresh_fields:
                    _require_hash(event[field], field.replace("_", "-"))
        else:
            require_uuid(event["writer_thread_id"], "writer-thread-id")
            require_uuid(event["ownership_event_id"], "ownership-event-id")
            _require_hash(event["ownership_sha256"], "ownership-sha256")
            _require_hash(event["classification_receipt_hash"], "classification-receipt-hash")
            _require_hash(event["selection_receipt_hash"], "selection-receipt-hash")
            if (
                isinstance(event["ownership_generation"], bool)
                or not isinstance(event["ownership_generation"], int)
                or event["ownership_generation"] < 1
            ):
                raise WorkMemoryError("invalid-ownership-generation", 2)
    if kind in PREVENTION_EVENT_TYPES:
        require_id(event["task_id"], "task-id")
        _require_hash(event["worktree_id"], "worktree-id")
        branch_ref = event["branch_ref"]
        if not isinstance(branch_ref, str) or not branch_ref.startswith("task/"):
            raise WorkMemoryError("invalid-task-branch-ref", 2)
        for field in (
            "requested_implementation_id", "compatibility_key", "config_sha256", "hook_sha256",
            "receipt_sha256", "capability_manifest_sha256", "effective_implementation_id",
            "registry_sha256", "owner_contract_sha256", "selected_owner_contract_sha256",
            "predecessor_implementation_id", "successor_implementation_id", "state_hash",
            "effect_id", "idempotency_key", "implementation_id", "effect_worktree_id",
            "result_hash", "failure_fingerprint", "reconciler_sha256",
            "preparation_artifact_sha256", "reconciliation_artifact_sha256",
            "observable_ownership_sha256", "evidence_sha256", "authorization_sha256",
            "scope_sha256", "value_fingerprint_sha256", "binding_receipt_sha256",
            "terminal_evidence_sha256", "terminal_artifact_sha256",
        ):
            if field in event and event[field] is not None:
                _require_hash(event[field], field.replace("_", "-"))
        if "action_class" in event and event["action_class"] not in {
            "BASH", "APPLY_PATCH", "MCP", "UNIFIED_SHELL", "WEB_SEARCH_BROWSER",
            "SUBAGENT", "NON_MCP_REMOTE",
        }:
            raise WorkMemoryError("invalid-action-class", 2)
        if kind == "dispatch_selected" and event["decision_kind"] not in {
            "SELECT_SUCCESSOR", "SELECT_PROMOTED", "SELECT_REGISTERED",
        }:
            raise WorkMemoryError("invalid-selected-decision-kind", 2)
        if kind == "dispatch_rejected" and event["decision_kind"] != "REJECT":
            raise WorkMemoryError("invalid-rejected-decision-kind", 2)
        if kind == "action_eligibility_recorded":
            recurrence = event["recurrence_policy"]
            availability = event["availability_policy"]
            eligibility = event["eligibility"]
            reason = event["ineligible_reason_code"]
            if recurrence not in {"ONE_SHOT", "RECURRENT", "NOT_APPLICABLE"}:
                raise WorkMemoryError("invalid-recurrence-policy", 2)
            if availability not in {"AVAILABLE", "UNAVAILABLE", "CUSTODIAN_EVIDENCE_REQUIRED"}:
                raise WorkMemoryError("invalid-availability-policy", 2)
            if type(eligibility) is not bool:
                raise WorkMemoryError("invalid-eligibility", 2)
            reasons = {
                "RECURRENCE_ONE_SHOT", "RECURRENCE_NOT_APPLICABLE",
                "AVAILABILITY_UNAVAILABLE", "AVAILABILITY_CUSTODIAN_EVIDENCE_REQUIRED",
                "OWNER_CONTRACT_UNRESOLVED", "UNREGISTERED_ACTION_CLASS",
            }
            if eligibility:
                if recurrence != "RECURRENT" or availability != "AVAILABLE" or reason is not None:
                    raise WorkMemoryError("invalid-eligible-action-facts", 2)
                if event["owner_contract_sha256"] is None:
                    raise WorkMemoryError("eligible-action-owner-contract-unresolved", 2)
            elif reason not in reasons:
                raise WorkMemoryError("invalid-ineligible-reason-code", 2)
        if kind == "effect_reconciled" and event["reconciliation"] not in {
            "ALREADY_APPLIED", "NOT_APPLIED", "INDETERMINATE",
        }:
            raise WorkMemoryError("invalid-effect-reconciliation", 2)
        if kind in {
            "effect_committed", "effect_reconciled", "effect_execution_authorized",
            "effect_execution_started",
        }:
            generation = event["attempt_generation"]
            minimum = 0 if kind == "effect_reconciled" else 1
            if isinstance(generation, bool) or not isinstance(generation, int) or generation < minimum:
                raise WorkMemoryError("invalid-attempt-generation", 2)
        if kind == "effect_execution_authorized":
            prior = event["prior_generation"]
            if (
                isinstance(prior, bool) or not isinstance(prior, int) or prior < 0
                or event["attempt_generation"] != prior + 1
            ):
                raise WorkMemoryError("noncontiguous-attempt-generation", 2)
        if kind == "owner_binding_recorded" and type(event["consumable"]) is not bool:
            raise WorkMemoryError("invalid-binding-consumable", 2)
        if kind == "owner_terminal":
            result_kind = event["result_kind"]
            executed_fields = {
                "effect_committed_event_id", "attempt_generation", "execution_started_event_id"
            }
            recovered_fields = {"reconciliation_event_id", "reconciliation_artifact_sha256"}
            if event["semantic_verdict"] != "PASS":
                raise WorkMemoryError("owner-terminal-semantic-verdict-not-pass", 2)
            if result_kind == "EXECUTED_RESULT":
                if not executed_fields <= set(event) or recovered_fields & set(event):
                    raise WorkMemoryError("invalid-executed-owner-terminal-fields", 2)
            elif result_kind == "RECOVERED_RESULT":
                if not recovered_fields <= set(event) or executed_fields & set(event):
                    raise WorkMemoryError("invalid-recovered-owner-terminal-fields", 2)
            else:
                raise WorkMemoryError("invalid-owner-terminal-result-kind", 2)
        if kind == "registered_reuse_recorded" and event["pre_dispatch"] is not True:
            raise WorkMemoryError("registered-reuse-not-pre-dispatch", 2)
        if kind == "timing_interval_recorded":
            started = parse_utc(event["started_at_utc"])
            ended = parse_utc(event["ended_at_utc"])
            duration = event["duration_milliseconds"]
            if (
                isinstance(duration, bool) or not isinstance(duration, int) or duration < 0
                or int((ended - started).total_seconds() * 1000) != duration
            ):
                raise WorkMemoryError("invalid-timing-duration", 2)
    if kind == "run_started":
        if event["mode"] not in {"registered", "discovery"} or event["operation_kind"] not in OPERATION_KINDS:
            raise WorkMemoryError("invalid-run-start-enum", 2)
        source_bundle = _require_list(event, "source_bundle")
        identities: set[tuple[str, str]] = set()
        for item in source_bundle:
            if (
                not isinstance(item, dict)
                or set(item) != {"repository_key", "path", "sha256"}
                or not isinstance(item["repository_key"], str)
                or not item["repository_key"]
                or not isinstance(item["path"], str)
                or not item["path"]
            ):
                raise WorkMemoryError("invalid-source-bundle-entry", 2)
            _require_hash(item["sha256"], "source-bundle-entry-sha256")
            identity = (item["repository_key"], item["path"])
            if identity in identities:
                raise WorkMemoryError("duplicate-source-bundle-entry", 2)
            identities.add(identity)
        if "repository_roots" in event:
            roots = event["repository_roots"]
            if (
                not isinstance(roots, dict) or not roots
                or any(
                    not isinstance(key, str) or not key
                    or not isinstance(value, str) or not Path(value).is_absolute()
                    for key, value in roots.items()
                )
            ):
                raise WorkMemoryError("invalid-repository-roots", 2)
        if ("predecessor_run_id" in event) != ("verifies_correction_ids" in event):
            raise WorkMemoryError("incomplete-successor-binding", 2)
        if "verifies_correction_ids" in event:
            _require_list(event, "verifies_correction_ids", nonempty=True)
        present = (V1_RUN_OWNERSHIP_FIELDS | V2_RUN_OWNERSHIP_FIELDS) & set(event)
        family = V2_RUN_OWNERSHIP_FIELDS if "writer_id" in event else V1_RUN_OWNERSHIP_FIELDS
        if present and present != family:
            raise WorkMemoryError("incomplete-run-writer-binding", 2)
        if present:
            require_id(event["task_id"], "task-id")
            if "writer_id" in event:
                require_uuid(event["writer_id"], "writer-id")
                require_uuid(event["writer_session_id"], "writer-session-id")
                if event["writer_client_kind"] not in CLIENT_KINDS:
                    raise WorkMemoryError("invalid-writer-client-kind", 2)
            else:
                require_uuid(event["writer_thread_id"], "writer-thread-id")
            require_uuid(event["ownership_event_id"], "ownership-event-id")
            _require_hash(event["ownership_sha256"], "ownership-sha256")
            if (
                isinstance(event["ownership_generation"], bool)
                or not isinstance(event["ownership_generation"], int)
                or event["ownership_generation"] < 1
            ):
                raise WorkMemoryError("invalid-ownership-generation", 2)
    elif kind in {"blocker_opened", "pre_run_blocker_opened", "blocker_recurred"}:
        if event["status"] != "open":
            raise WorkMemoryError("invalid-blocker-open-status", 2)
        if kind == "pre_run_blocker_opened":
            require_id(event["task_id"], "task-id")
            require_uuid(event["ownership_event_id"], "ownership-event-id")
        if kind == "blocker_recurred" and event["previous_status"] != "closed":
            raise WorkMemoryError("invalid-recurrence-state", 2)
    elif kind == "blocker_assigned_downstream":
        if event["classification"] != "incidental-system-defect":
            raise WorkMemoryError("invalid-downstream-blocker-classification", 2)
        for field in ("downstream_owner", "evidence"):
            if not isinstance(event[field], str) or not event[field].strip():
                raise WorkMemoryError("invalid-downstream-blocker-assignment", 2)
    elif kind == "correction_recorded":
        # Optional: absent means empty, so every correction recorded before this field existed
        # still validates unchanged.
        environment = _optional_list(event, "environment_artifacts")
        environment_hashes = _optional_list(event, "environment_artifact_hashes")
        # changed_artifacts may be empty ONLY for an environment-surface correction; a correction
        # that names nothing at all stays rejected.
        artifacts = _require_list(
            event, "changed_artifacts", nonempty=not environment,
        )
        hashes = _require_list(
            event, "changed_artifact_hashes", nonempty=not environment,
        )
        if (
            len(artifacts) != len(hashes)
            or len(environment) != len(environment_hashes)
            or not isinstance(event["reusable_behavior_changed"], bool)
        ):
            raise WorkMemoryError("invalid-correction-artifacts", 2)
        for artifact in artifacts:
            _artifact_identity(artifact)
        for artifact in environment:
            _artifact_identity(artifact)
        for value in environment_hashes:
            _require_hash(value, "environment-artifact-hash")
        _superseded_correction_ids(event)
        if "primary_correction_id" in event:
            require_uuid(event["primary_correction_id"], "primary-correction-id")
            if event["primary_correction_id"] == event["correction_id"]:
                raise WorkMemoryError("self-linked-co-correction", 2)
    elif kind == "pre_run_correction_recorded":
        require_id(event["task_id"], "task-id")
        require_uuid(event["ownership_event_id"], "ownership-event-id")
        if "supersedes_correction_id" in event:
            require_uuid(
                event["supersedes_correction_id"],
                "supersedes-correction-id",
            )
            if event["supersedes_correction_id"] == event["correction_id"]:
                raise WorkMemoryError("self-superseding-pre-run-correction", 2)
        artifacts = _require_list(event, "changed_artifacts", nonempty=True)
        hashes = _require_list(event, "changed_artifact_hashes", nonempty=True)
        if len(artifacts) != len(hashes) or not isinstance(event["reusable_behavior_changed"], bool):
            raise WorkMemoryError("invalid-pre-run-correction-artifacts", 2)
        for artifact in artifacts:
            _artifact_identity(artifact)
        for value in hashes:
            _require_hash(value, "changed-artifact-hash")
    elif kind == "pre_run_verification_recorded":
        require_id(event["task_id"], "task-id")
        require_uuid(event["ownership_event_id"], "ownership-event-id")
        if event["outcome"] not in {"passed", "failed"} or event["quality"] != "same-command":
            raise WorkMemoryError("invalid-pre-run-verification-enum", 2)
        if not isinstance(event["verification_command"], str) or not event["verification_command"].strip():
            raise WorkMemoryError("invalid-pre-run-verification-command", 2)
        for value in _require_list(event, "changed_artifact_hashes", nonempty=True):
            _require_hash(value, "changed-artifact-hash")
    elif kind == "pre_run_blocker_transitioned":
        require_id(event["task_id"], "task-id")
        require_uuid(event["ownership_event_id"], "ownership-event-id")
        if "verification_event_id" in event:
            require_uuid(event["verification_event_id"], "verification-event-id")
        target = event["to_status"]
        required = {
            "fixed-awaiting-verification": set(),
            "verified": {"verification_event_id"},
            "closed": {"verification_event_id", "remaining_work"},
        }
        if target not in required or not required[target] <= set(event):
            raise WorkMemoryError("invalid-pre-run-blocker-transition", 2)
    elif kind == "correction_preservation_recorded":
        require_id(event["target_task_id"], "target-task-id")
        require_id(event["preserved_task_id"], "preserved-task-id")
        if event["target_task_id"] == event["preserved_task_id"]:
            raise WorkMemoryError("correction-preservation-distinct-tasks-required", 2)
        require_id(event["subject_id"], "subject-id")
        require_id(event["lineage_id"], "lineage-id")
        require_uuid(event["target_correction_id"], "target-correction-id")
        require_uuid(event["target_transition_event_id"], "target-transition-event-id")
        require_uuid(event["target_verification_event_id"], "target-verification-event-id")
        _require_hash(event["target_bundle_hash"], "target-bundle-hash")
        preserved_ids = _require_list(
            event, "preserved_correction_ids", nonempty=True,
        )
        if len(preserved_ids) != len(set(preserved_ids)):
            raise WorkMemoryError("duplicate-preserved-correction", 2)
        for correction_id in preserved_ids:
            require_uuid(correction_id, "preserved-correction-id")
        if event["target_correction_id"] in preserved_ids:
            raise WorkMemoryError("self-preserved-correction", 2)
        for prefix in ("target", "preserved"):
            require_uuid(event[f"{prefix}_writer_thread_id"], f"{prefix}-writer-thread-id")
            require_uuid(event[f"{prefix}_ownership_event_id"], f"{prefix}-ownership-event-id")
            _require_hash(event[f"{prefix}_ownership_sha256"], f"{prefix}-ownership-sha256")
            generation = event[f"{prefix}_ownership_generation"]
            if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
                raise WorkMemoryError(f"invalid-{prefix}-ownership-generation", 2)
    elif kind == "bundle_transition_recorded":
        reason = event["transition_reason"]
        if reason == "correction":
            required = {"run_id", "correction_ids", "changed_artifacts", "changed_artifact_hashes"}
            prohibited = {"discovery_id", "promoted_sequence_id"}
            if not required <= set(event) or prohibited & set(event):
                raise WorkMemoryError("invalid-correction-transition", 2)
            ids = _require_list(event, "correction_ids", nonempty=True)
            environment = _optional_list(event, "environment_artifacts")
            environment_hashes = _optional_list(event, "environment_artifact_hashes")
            # Bundle artifacts may be empty ONLY for an environment-surface correction, and then
            # the bundle must genuinely be unchanged. A bundle that moved must still name its files.
            arts = _require_list(
                event, "changed_artifacts", nonempty=not environment,
            )
            hashes = _require_list(
                event, "changed_artifact_hashes", nonempty=not environment,
            )
            if (
                not ids
                or len(arts) != len(hashes)
                or len(environment) != len(environment_hashes)
            ):
                raise WorkMemoryError("invalid-correction-transition", 2)
            if environment and not arts and event["old_bundle_hash"] != event["new_bundle_hash"]:
                raise WorkMemoryError("environment-transition-moved-the-bundle", 2)
            for artifact in (*arts, *environment):
                _artifact_identity(artifact)
            for value in environment_hashes:
                _require_hash(value, "environment-artifact-hash")
        elif reason == "promotion":
            required = {"discovery_id", "promoted_sequence_id", "correction_ids"}
            prohibited = {"run_id", "changed_artifacts", "changed_artifact_hashes"}
            if not required <= set(event) or prohibited & set(event) or event["correction_ids"] != []:
                raise WorkMemoryError("invalid-promotion-transition", 2)
        else:
            raise WorkMemoryError("invalid-transition-reason", 2)
    elif kind == "verification_recorded":
        if event["outcome"] not in {"passed", "failed"} or event["quality"] not in {"proxy", "same-path"}:
            raise WorkMemoryError("invalid-verification-enum", 2)
        blockers = _require_list(event, "blocker_ids")
        corrections = _require_list(event, "correction_ids")
        hashes = _require_list(event, "changed_artifact_hashes")
        environment_hashes = _optional_list(event, "environment_artifact_hashes")
        for value in environment_hashes:
            _require_hash(value, "environment-artifact-hash")
        # A correction attests EITHER bundle artifacts or an environment surface, so either kind of
        # hash discharges the binding.
        attested = bool(hashes) or bool(environment_hashes)
        investigation_proof = (
            bool(blockers)
            and not corrections
            and not attested
            and event["quality"] == "same-path"
        )
        correction_proof = (
            bool(blockers) == bool(corrections)
            and bool(corrections) == attested
        )
        if not investigation_proof and not correction_proof:
            raise WorkMemoryError("incomplete-verification-binding", 2)
    elif kind == "blocker_transitioned":
        if "verification_event_id" in event:
            require_uuid(event["verification_event_id"], "verification-event-id")
        target = event["to_status"]
        expected_optional = {
            "open": set(),
            "fixed-awaiting-verification": set(),
            "verified": {"verification_event_id"},
            "closed": {"verification_event_id", "remaining_work"},
            "superseded": {"supersession_evidence"},
            "non-gap": {"non_gap_evidence"},
        }
        if target not in expected_optional or not expected_optional[target] <= set(event):
            raise WorkMemoryError("invalid-blocker-transition-fields", 2)
        optional_present = set(event) & EVENT_FIELDS[kind][1]
        if target == "open":
            reopen_fields = optional_present & {"reopen_evidence", "recovery_evidence"}
            if len(reopen_fields) != 1:
                raise WorkMemoryError("invalid-blocker-transition-fields", 2)
            expected_optional[target] = (
                reopen_fields | (
                    {"verification_event_id"}
                    if "verification_event_id" in optional_present else set()
                )
            )
        if "reconciliation_basis_event_id" in optional_present:
            if target not in {"verified", "closed"}:
                raise WorkMemoryError("invalid-blocker-transition-fields", 2)
            expected_optional[target].add("reconciliation_basis_event_id")
        if target == "non-gap" and "verification_event_id" in optional_present:
            expected_optional[target].add("verification_event_id")
        if optional_present != expected_optional[target] or (target == "closed" and event["remaining_work"] != "none"):
            raise WorkMemoryError("invalid-blocker-transition-fields", 2)
        if target == "open":
            evidence = event[next(iter(expected_optional[target]))]
            if not isinstance(evidence, str) or not evidence.strip():
                raise WorkMemoryError("reopen-evidence-required", 2)
    elif kind == "run_closed":
        if event["result"] not in {"passed", "failed"} or event["verification_quality"] not in {"none", "proxy", "same-path"}:
            raise WorkMemoryError("invalid-run-close-enum", 2)
        if not isinstance(event["correction_count"], int) or event["correction_count"] < 0:
            raise WorkMemoryError("invalid-correction-count", 2)
    elif kind == "operation_context_recorded":
        require_uuid(event["context_id"], "context-id")
        _require_hash(event["source_bundle_hash"], "source-bundle-hash")
        _require_hash(event["repository_roots_hash"], "repository-roots-hash")
        try:
            candidate_contract.normalize_operation_context({
                key: event[key] for key in (
                    "intended_outcome", "repeatability_reason", "repeatability_evidence_ids",
                    "required_inputs", "dependencies", "failure_handling", "verification_contract",
                    "effect_class", "environment_annotations", "semantic_flag_annotations",
                    "volatility_annotations",
                )
            })
        except candidate_contract.CandidateContractError as exc:
            raise WorkMemoryError(exc.code, 2) from exc
    elif kind == "execution_claimed":
        require_uuid(event["execution_id"], "execution-id")
        require_uuid(event["context_id"], "context-id")
        _require_hash(event["source_bundle_hash"], "source-bundle-hash")
        _require_hash(event["repository_roots_hash"], "repository-roots-hash")
        _require_hash(event["command_sha256"], "command-sha256")
        if (
            not isinstance(event["step_ordinal"], int) or event["step_ordinal"] < 0
            or event["command_source"] not in candidate_contract.PROVENANCE_CLASSES
            or event["operation_kind"] not in OPERATION_KINDS
            or event["effect_class"] not in candidate_contract.EFFECT_CLASSES
        ):
            raise WorkMemoryError("invalid-execution-claim", 2)
        require_id(event["step_id"], "step-id")
        argv = _require_list(event, "argv", nonempty=True)
        if any(not isinstance(item, str) or "\x00" in item or "\r" in item or "\n" in item for item in argv):
            raise WorkMemoryError("invalid-execution-argv", 2)
        _validate_execution_argv(argv)
        _artifact_identity(event["source_ref"])
        parse_utc(event["claimed_at_utc"])
    elif kind == "execution_returned":
        require_uuid(event["execution_id"], "execution-id")
        require_uuid(event["context_id"], "context-id")
        _require_hash(event["source_bundle_hash"], "source-bundle-hash")
        if not isinstance(event["exit_code"], int) or event["result"] not in {"passed", "failed"}:
            raise WorkMemoryError("invalid-execution-return", 2)
        if event["result"] != ("passed" if event["exit_code"] == 0 else "failed"):
            raise WorkMemoryError("execution-result-mismatch", 2)
        parse_utc(event["returned_at_utc"])
    elif kind == "observer_decision_recorded":
        require_uuid(event["decision_id"], "decision-id")
        require_uuid(event["trigger_event_id"], "trigger-event-id")
        for field in ("config_hash", "ledger_snapshot_hash", "evidence_set_hash"):
            _require_hash(event[field], field.replace("_", "-"))
        if (
            event["observer_version"] != 1 or event["rule_version"] != 1
            or event["trigger_type"] != "run_closed"
            or event["disposition"] not in {
                "NO_CANDIDATE", "LINK_REGISTERED", "LINK_DISCOVERY", "PROPOSE_DISCOVERY",
            }
            or event["target_kind"] not in {None, "registered", "discovery"}
            or not isinstance(event["threshold"], int) or event["threshold"] < 0
        ):
            raise WorkMemoryError("invalid-observer-decision-enum", 2)
        _require_list(event, "evidence_event_ids")
        _require_list(event, "value_components")
        _require_list(event, "considered_registered_ids")
        _require_list(event, "considered_discovery_ids")
        if (event["target_kind"] is None) != (event["target_id"] is None):
            raise WorkMemoryError("invalid-observer-decision-target", 2)
        if (event["candidate_identity"] is None) != (event["candidate_fingerprint"] is None):
            raise WorkMemoryError("invalid-observer-candidate-binding", 2)
        if event["candidate_identity"] is not None:
            try:
                candidate_contract.validate_candidate_identity(
                    event["candidate_identity"], event["candidate_fingerprint"],
                )
            except candidate_contract.CandidateContractError as exc:
                raise WorkMemoryError(exc.code, 2) from exc
        eligibility = event["eligibility"]
        if (
            not isinstance(eligibility, dict)
            or set(eligibility) != {"version", "eligible", "triggers", "reasons"}
            or eligibility["version"] != 1 or not isinstance(eligibility["eligible"], bool)
            or not isinstance(eligibility["triggers"], list)
            or not isinstance(eligibility["reasons"], list)
        ):
            raise WorkMemoryError("invalid-observer-eligibility", 2)
        for component in event["value_components"]:
            if (
                not isinstance(component, dict)
                or set(component) != {"name", "status", "value", "evidence_event_ids"}
                or component["status"] not in {"KNOWN", "UNKNOWN"}
                or not isinstance(component["value"], int) or component["value"] < 0
                or not isinstance(component["evidence_event_ids"], list)
            ):
                raise WorkMemoryError("invalid-observer-value-component", 2)
        suppression = event["suppression"]
        if (
            not isinstance(suppression, dict)
            or set(suppression) != {"rule_version", "suppressed", "reason", "expires_at_utc"}
            or suppression["rule_version"] != 1
            or not isinstance(suppression["suppressed"], bool)
        ):
            raise WorkMemoryError("invalid-observer-suppression", 2)
        if suppression["expires_at_utc"] is not None:
            parse_utc(suppression["expires_at_utc"])
        cursor = event["cap_cursor"]
        if cursor is not None and (
            not isinstance(cursor, dict) or set(cursor) != {"recorded_at_utc", "event_id"}
        ):
            raise WorkMemoryError("invalid-observer-cap-cursor", 2)
    elif kind == "observer_bootstrap_result_recorded":
        require_uuid(event["bootstrap_attempt_id"], "bootstrap-attempt-id")
        require_uuid(event["decision_id"], "decision-id")
        _require_hash(event["bootstrap_request_sha256"], "bootstrap-request-sha256")
        if (
            not isinstance(event["attempt_ordinal"], int) or event["attempt_ordinal"] < 0
            or event["outcome"] not in {"succeeded", "failed"}
            or not isinstance(event["retryable"], bool)
        ):
            raise WorkMemoryError("invalid-observer-bootstrap-result", 2)
        success_fields = (
            "discovery_id", "lineage_id", "run_id", "source_bundle_hash",
            "document_path", "manifest_path",
        )
        if event["outcome"] == "succeeded":
            if event["safe_error_code"] is not None or any(event[field] is None for field in success_fields):
                raise WorkMemoryError("invalid-observer-bootstrap-success", 2)
            require_uuid(event["run_id"], "run-id")
            _require_hash(event["source_bundle_hash"], "source-bundle-hash")
        elif any(event[field] is not None for field in success_fields) or event["safe_error_code"] is None:
            raise WorkMemoryError("invalid-observer-bootstrap-failure", 2)
    elif kind == "observer_candidate_linked":
        require_uuid(event["link_id"], "link-id")
        require_uuid(event["decision_id"], "decision-id")
        _require_hash(event["candidate_fingerprint"], "candidate-fingerprint")
        if event["target_kind"] not in {"registered", "discovery"} or event["link_kind"] not in {"existing", "proposed"}:
            raise WorkMemoryError("invalid-observer-link", 2)


def parse_ledger_bytes(data: bytes) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_no, raw in enumerate(data.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WorkMemoryError(f"malformed-ledger-line:{line_no}", 3) from exc
        try:
            _validate_event_shape(event)
        except WorkMemoryError as exc:
            raise WorkMemoryError(f"invalid-ledger-line:{line_no}:{exc.code}", 3) from exc
        events.append(event)
    validate_lifecycle(
        events,
        legacy_premature_fixed_event_ids={event["event_id"] for event in events},
        legacy_open_terminal_event_ids={
            event["event_id"] for event in events
            if event["event_type"] == "run_closed"
        },
        legacy_post_terminal_event_ids={event["event_id"] for event in events},
        legacy_nonopen_correction_event_ids={event["event_id"] for event in events},
        legacy_unverified_reopen_event_ids={event["event_id"] for event in events},
    )
    return events


def _validate_new_event_policy(event: dict[str, Any]) -> None:
    if (
        event["event_type"] == "blocker_transitioned"
        and event["to_status"] == "non-gap"
        and "verification_event_id" not in event
    ):
        raise WorkMemoryError("non-gap-verification-required", 2)
    if (
        event["event_type"] == "blocker_transitioned"
        and event["to_status"] == "open"
        and "reopen_evidence" in event
        and "verification_event_id" not in event
    ):
        raise WorkMemoryError("reopen-verification-required", 2)


def _event_index(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = event["event_id"]
        if event_id in index and index[event_id] != event:
            raise WorkMemoryError("event-id-conflict", 3)
        index[event_id] = event
    return index


def validate_prevention_lifecycle(events: list[dict[str, Any]]) -> None:
    prevention = [event for event in events if event["event_type"] in PREVENTION_EVENT_TYPES]
    if not prevention:
        return
    ownership = {
        tuple(event[field] for field in sorted(PREVENTION_OWNERSHIP_FIELDS))
        for event in prevention
    }
    if len(ownership) != 1:
        raise WorkMemoryError("mixed-prevention-journal-ownership", 3)
    intents: set[str] = set()
    eligibilities: set[str] = set()
    decisions_by_intent: set[str] = set()
    prepared_transitions: set[str] = set()
    prepared_effects: set[str] = set()
    prepared_by_effect: dict[str, dict[str, Any]] = {}
    reconciled_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    reconciled_by_event: dict[str, dict[str, Any]] = {}
    authorized_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    started_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    committed_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    committed_by_event: dict[str, dict[str, Any]] = {}
    terminal_effects: set[str] = set()
    delegations_by_id: dict[str, dict[str, Any]] = {}
    consumed_delegations: set[str] = set()
    for event in prevention:
        kind = event["event_type"]
        if kind == "action_intent_recorded":
            if event["intent_id"] in intents:
                raise WorkMemoryError("duplicate-prevention-intent", 3)
            intents.add(event["intent_id"])
        elif kind == "action_eligibility_recorded":
            if event["intent_id"] not in intents:
                raise WorkMemoryError("eligibility-before-intent", 3)
            if event["intent_id"] in eligibilities:
                raise WorkMemoryError("duplicate-action-eligibility", 3)
            eligibilities.add(event["intent_id"])
        elif kind in {"dispatch_selected", "dispatch_rejected"}:
            if event["intent_id"] not in intents:
                raise WorkMemoryError("dispatch-before-intent", 3)
            if event["intent_id"] not in eligibilities:
                raise WorkMemoryError("dispatch-before-eligibility", 3)
            if event["intent_id"] in decisions_by_intent:
                raise WorkMemoryError("duplicate-terminal-dispatch-decision", 3)
            decisions_by_intent.add(event["intent_id"])
        elif kind == "transition_prepared":
            prepared_transitions.add(event["event_id"])
        elif kind == "transition_committed":
            if event["prepared_event_id"] not in prepared_transitions:
                raise WorkMemoryError("transition-commit-before-prepare", 3)
        elif kind == "effect_prepared":
            if event["transition_prepared_event_id"] not in prepared_transitions:
                raise WorkMemoryError("effect-before-transition-prepare", 3)
            if event["effect_id"] in prepared_by_effect:
                raise WorkMemoryError("duplicate-effect-prepared", 3)
            prepared_effects.add(event["event_id"])
            prepared_by_effect[event["effect_id"]] = event
        elif kind == "effect_reconciled":
            if event["prepared_event_id"] not in prepared_effects:
                raise WorkMemoryError("effect-terminal-before-prepare", 3)
            prepared = prepared_by_effect.get(event["effect_id"])
            if prepared is None or any(
                event[field] != prepared[field]
                for field in (
                    "owner_contract_sha256", "reconciler_sha256",
                    "preparation_artifact_sha256",
                )
            ):
                raise WorkMemoryError("effect-reconciliation-identity-mismatch", 3)
            key = (event["effect_id"], event["attempt_generation"])
            if key in reconciled_by_key:
                raise WorkMemoryError("duplicate-effect-reconciled", 3)
            prior_id = event.get("prior_reconciliation_event_id")
            if prior_id is not None:
                prior = reconciled_by_event.get(prior_id)
                if (
                    prior is None
                    or prior["effect_id"] != event["effect_id"]
                    or prior["attempt_generation"] >= event["attempt_generation"]
                ):
                    raise WorkMemoryError("invalid-prior-reconciliation-link", 3)
            reconciled_by_key[key] = event
            reconciled_by_event[event["event_id"]] = event
        elif kind == "effect_execution_authorized":
            key = (event["effect_id"], event["attempt_generation"])
            if key in authorized_by_key:
                raise WorkMemoryError("duplicate-effect-execution-authorized", 3)
            reconciliation = reconciled_by_event.get(
                event["not_applied_reconciliation_event_id"]
            )
            if (
                reconciliation is None
                or reconciliation["effect_id"] != event["effect_id"]
                or reconciliation["attempt_generation"] != event["prior_generation"]
                or reconciliation["reconciliation"] != "NOT_APPLIED"
                or reconciliation["owner_contract_sha256"]
                != event["owner_contract_sha256"]
            ):
                raise WorkMemoryError("execution-authorization-without-not-applied", 3)
            authorized_by_key[key] = event
        elif kind == "effect_execution_started":
            key = (event["effect_id"], event["attempt_generation"])
            if key in started_by_key:
                raise WorkMemoryError("duplicate-effect-execution-started", 3)
            authorization = authorized_by_key.get(key)
            if (
                authorization is None
                or authorization["event_id"] != event["execution_authorized_event_id"]
                or authorization["owner_contract_sha256"]
                != event["owner_contract_sha256"]
            ):
                raise WorkMemoryError("effect-start-without-authorization", 3)
            started_by_key[key] = event
        elif kind == "effect_committed":
            if event["prepared_event_id"] not in prepared_effects:
                raise WorkMemoryError("effect-terminal-before-prepare", 3)
            key = (event["effect_id"], event["attempt_generation"])
            if key in committed_by_key:
                raise WorkMemoryError("duplicate-effect-committed", 3)
            started = started_by_key.get(key)
            if (
                started is None
                or started["event_id"] != event["execution_started_event_id"]
            ):
                raise WorkMemoryError("effect-commit-without-same-generation-start", 3)
            committed_by_key[key] = event
            committed_by_event[event["event_id"]] = event
        elif kind == "owner_terminal":
            effect_id = event["effect_id"]
            if effect_id in terminal_effects:
                raise WorkMemoryError("duplicate-owner-terminal", 3)
            prepared = prepared_by_effect.get(effect_id)
            if (
                prepared is None
                or prepared["owner_sequence_id"] != event["owner_sequence_id"]
                or prepared["owner_contract_sha256"] != event["owner_contract_sha256"]
            ):
                raise WorkMemoryError("owner-terminal-effect-identity-mismatch", 3)
            if event["result_kind"] == "EXECUTED_RESULT":
                committed = committed_by_event.get(event["effect_committed_event_id"])
                key = (effect_id, event["attempt_generation"])
                started = started_by_key.get(key)
                if (
                    committed is None
                    or committed["effect_id"] != effect_id
                    or committed["attempt_generation"] != event["attempt_generation"]
                    or started is None
                    or started["event_id"] != event["execution_started_event_id"]
                ):
                    raise WorkMemoryError("executed-terminal-provenance-mismatch", 3)
            else:
                reconciliation = reconciled_by_event.get(event["reconciliation_event_id"])
                if (
                    reconciliation is None
                    or reconciliation["effect_id"] != effect_id
                    or reconciliation["reconciliation"] != "ALREADY_APPLIED"
                    or reconciliation["reconciliation_artifact_sha256"]
                    != event["reconciliation_artifact_sha256"]
                    or any(key[0] == effect_id for key in committed_by_key)
                ):
                    raise WorkMemoryError("recovered-terminal-provenance-mismatch", 3)
            terminal_effects.add(effect_id)
        elif kind == "child_delegation_recorded":
            delegation_id = event["delegation_id"]
            if delegation_id in delegations_by_id:
                raise WorkMemoryError("duplicate-child-delegation", 3)
            parent = prepared_by_effect.get(event["parent_effect_id"])
            parent_starts = [
                started for (effect_id, _), started in started_by_key.items()
                if effect_id == event["parent_effect_id"]
            ]
            if (
                parent is None
                or parent["owner_sequence_id"] != event["parent_owner_sequence_id"]
                or len(parent_starts) != 1
                or any(key[0] == event["parent_effect_id"] for key in committed_by_key)
                or event["parent_effect_id"] in terminal_effects
            ):
                raise WorkMemoryError("delegation-parent-not-active-started", 3)
            delegations_by_id[delegation_id] = event
        elif kind == "child_delegation_consumed":
            delegation_id = event["delegation_id"]
            if delegation_id in consumed_delegations:
                raise WorkMemoryError("duplicate-child-delegation-consumption", 3)
            delegation = delegations_by_id.get(delegation_id)
            child_prepared = prepared_by_effect.get(event["child_effect_id"])
            if (
                delegation is None
                or child_prepared is None
                or delegation["parent_effect_id"] != event["parent_effect_id"]
                or delegation["child_intent_id"] != event["child_intent_id"]
                or child_prepared["event_id"] != event["effect_prepared_event_id"]
                or child_prepared["owner_sequence_id"]
                != delegation["child_owner_sequence_id"]
            ):
                raise WorkMemoryError("child-delegation-consumption-mismatch", 3)
            consumed_delegations.add(delegation_id)


def _validate_correction_preservation_records(
    events: Sequence[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Replay explicit preservation edges and return preserved-id -> record."""
    _, run_tasks = _ownership_snapshot(events)
    correction_rows: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, event in enumerate(events):
        if event["event_type"] == "correction_recorded":
            correction_rows[event["correction_id"]].append((index, event))
    corrections = {
        correction_id: rows[0]
        for correction_id, rows in correction_rows.items()
        if len(rows) == 1
    }
    correction_transition_rows: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, event in enumerate(events):
        if event["event_type"] != "bundle_transition_recorded":
            continue
        for correction_id in event.get("correction_ids", []):
            correction_transition_rows[correction_id].append((index, event))
    transitions = {
        event["event_id"]: (index, event)
        for index, event in enumerate(events)
        if event["event_type"] == "bundle_transition_recorded"
    }
    verifications = {
        event["event_id"]: (index, event)
        for index, event in enumerate(events)
        if event["event_type"] == "verification_recorded"
    }
    superseded = {
        correction_id
        for _, correction in corrections.values()
        for correction_id in _superseded_correction_ids(correction)
    }
    task_states: dict[str, dict[str, Any]] = {}
    preservation_by_correction: dict[str, dict[str, Any]] = {}
    blocker_states: dict[str, str] = {}

    for index, event in enumerate(events):
        kind = event["event_type"]
        if kind == "task_writer_claimed":
            v2_claim = event.get("schema_version") == 2
            task_states[event["task_id"]] = {
                "writer_thread_id": event["writer_id"] if v2_claim else event["writer_thread_id"],
                "ownership_generation": event["ownership_generation"],
                "ownership_event_id": event["event_id"],
            }
            continue
        if kind == "task_writer_handoff_recorded":
            v2_handoff = event.get("schema_version") == 2
            task_states[event["task_id"]] = {
                "writer_thread_id": event["to_writer_id"] if v2_handoff else event["to_writer_thread_id"],
                "ownership_generation": event["ownership_generation"],
                "ownership_event_id": event["event_id"],
            }
            continue
        if kind in {"blocker_opened", "blocker_recurred"}:
            blocker_states[event["blocker_id"]] = "open"
            continue
        if kind == "blocker_transitioned":
            blocker_states[event["blocker_id"]] = event["to_status"]
            continue
        if kind != "correction_preservation_recorded":
            continue

        target_state = task_states.get(event["target_task_id"])
        preserved_state = task_states.get(event["preserved_task_id"])
        if target_state is None or preserved_state is None:
            raise WorkMemoryError("correction-preservation-task-unclaimed", 3)
        if event["target_task_id"] == event["preserved_task_id"]:
            raise WorkMemoryError("correction-preservation-distinct-tasks-required", 3)
        expected_receipts = {
            **_prefixed_ownership_receipt_fields(
                "target", event["target_task_id"], target_state,
            ),
            **_prefixed_ownership_receipt_fields(
                "preserved", event["preserved_task_id"], preserved_state,
            ),
        }
        if any(event[key] != value for key, value in expected_receipts.items()):
            raise WorkMemoryError("correction-preservation-receipt-mismatch", 3)
        if target_state["writer_thread_id"] != preserved_state["writer_thread_id"]:
            raise WorkMemoryError("correction-preservation-owner-mismatch", 3)

        if len(correction_rows.get(event["target_correction_id"], [])) != 1:
            raise WorkMemoryError("ambiguous-preservation-target-correction", 3)
        target_entry = corrections.get(event["target_correction_id"])
        if target_entry is None or target_entry[0] >= index:
            raise WorkMemoryError("preservation-target-correction-not-found", 3)
        target_index, target = target_entry
        if run_tasks.get(target["run_id"]) != event["target_task_id"]:
            raise WorkMemoryError("preservation-target-task-mismatch", 3)
        if (
            target["subject_id"] != event["subject_id"]
            or target["lineage_id"] != event["lineage_id"]
            or target["correction_id"] in superseded
        ):
            raise WorkMemoryError("preservation-target-context-mismatch", 3)
        originating_transitions = [
            entry
            for entry in correction_transition_rows.get(
                event["target_correction_id"], []
            )
            if entry[1].get("changed_artifacts") == target["changed_artifacts"]
            and entry[1].get("changed_artifact_hashes")
            == target["changed_artifact_hashes"]
        ]
        if len(originating_transitions) != 1:
            raise WorkMemoryError("ambiguous-preservation-target-transition", 3)
        transition_entry = transitions.get(event["target_transition_event_id"])
        if (
            transition_entry is None
            or transition_entry != originating_transitions[0]
            or transition_entry[0] >= index
        ):
            raise WorkMemoryError("preservation-target-transition-not-found", 3)
        transition_index, transition = transition_entry
        if (
            transition.get("transition_reason") != "correction"
            or event["target_correction_id"] not in transition.get("correction_ids", [])
            or transition.get("run_id") != target["run_id"]
            or transition["lineage_id"] != event["lineage_id"]
            or transition["new_bundle_hash"] != event["target_bundle_hash"]
            or transition.get("changed_artifacts") != target["changed_artifacts"]
            or transition.get("changed_artifact_hashes")
            != target["changed_artifact_hashes"]
        ):
            raise WorkMemoryError("preservation-target-transition-mismatch", 3)
        verification_entry = verifications.get(event["target_verification_event_id"])
        if verification_entry is None or verification_entry[0] >= index:
            raise WorkMemoryError("preservation-target-verification-not-found", 3)
        verification_index, verification = verification_entry
        if not target_index < transition_index < verification_index < index:
            raise WorkMemoryError("correction-preservation-order-mismatch", 3)
        if (
            verification["outcome"] != "passed"
            or verification["quality"] != "same-path"
            or verification["subject_id"] != event["subject_id"]
            or verification["lineage_id"] != event["lineage_id"]
            or verification["source_bundle_hash"] != event["target_bundle_hash"]
            or event["target_correction_id"] not in verification["correction_ids"]
            or target["blocker_id"] not in verification["blocker_ids"]
            or run_tasks.get(verification["run_id"]) != event["target_task_id"]
        ):
            raise WorkMemoryError("preservation-target-verification-mismatch", 3)
        if blocker_states.get(target["blocker_id"]) != "closed":
            raise WorkMemoryError("preservation-target-blocker-not-closed", 3)

        for preserved_id in event["preserved_correction_ids"]:
            if len(correction_rows.get(preserved_id, [])) != 1:
                raise WorkMemoryError("ambiguous-preserved-correction", 3)
            preserved_entry = corrections.get(preserved_id)
            if preserved_entry is None or preserved_entry[0] >= target_index:
                raise WorkMemoryError("preserved-correction-not-earlier", 3)
            _, preserved = preserved_entry
            if run_tasks.get(preserved["run_id"]) != event["preserved_task_id"]:
                raise WorkMemoryError("preserved-correction-task-mismatch", 3)
            if (
                preserved["subject_id"] != event["subject_id"]
                or preserved["lineage_id"] != event["lineage_id"]
                or preserved_id in superseded
            ):
                raise WorkMemoryError("preserved-correction-context-mismatch", 3)
            if preserved_id in preservation_by_correction:
                raise WorkMemoryError("conflicting-correction-preservation", 3)
            cursor = event["target_correction_id"]
            seen = {preserved_id}
            while cursor in preservation_by_correction:
                if cursor in seen:
                    raise WorkMemoryError("correction-preservation-cycle", 3)
                seen.add(cursor)
                cursor = preservation_by_correction[cursor]["target_correction_id"]
            if cursor in seen:
                raise WorkMemoryError("correction-preservation-cycle", 3)
            preservation_by_correction[preserved_id] = event
    return preservation_by_correction


def validate_lifecycle(
    events: list[dict[str, Any]],
    *,
    legacy_premature_fixed_event_ids: set[str] | None = None,
    legacy_open_terminal_event_ids: set[str] | None = None,
    legacy_post_terminal_event_ids: set[str] | None = None,
    legacy_nonopen_correction_event_ids: set[str] | None = None,
    legacy_unverified_reopen_event_ids: set[str] | None = None,
) -> None:
    event_index = _event_index(events)
    _ownership_snapshot(events)
    _validate_correction_preservation_records(events)
    validate_prevention_lifecycle(events)
    legacy_premature_fixed_event_ids = legacy_premature_fixed_event_ids or set()
    legacy_open_terminal_event_ids = legacy_open_terminal_event_ids or set()
    legacy_post_terminal_event_ids = legacy_post_terminal_event_ids or set()
    legacy_nonopen_correction_event_ids = (
        legacy_nonopen_correction_event_ids or set()
    )
    legacy_unverified_reopen_event_ids = legacy_unverified_reopen_event_ids or set()
    runs: dict[str, dict[str, Any]] = {}
    blockers: dict[str, str] = {}
    blocker_meta: dict[str, dict[str, Any]] = {}
    blocker_occurrences: dict[str, str] = {}
    blocker_occurrence_runs: dict[str, str] = {}
    blocker_verified_evidence: dict[str, str] = {}
    downstream_assignments: dict[str, dict[str, Any]] = {}
    legacy_stranded_fixed_sources: dict[str, str] = {}
    failed_verification_reopens: dict[str, set[str]] = {}
    corrections: dict[str, dict[str, Any]] = {}
    verifications: dict[str, dict[str, Any]] = {}
    pre_run_corrections: dict[str, dict[str, Any]] = {}
    superseded_pre_run_corrections: set[str] = set()
    pre_run_verifications: dict[str, dict[str, Any]] = {}
    contexts: dict[str, dict[str, Any]] = {}
    executions: dict[str, dict[str, Any]] = {}
    returned: set[str] = set()
    decisions: dict[str, dict[str, Any]] = {}
    bootstrap_attempts: set[str] = set()
    links: set[str] = set()
    for event in events:
        kind = event["event_type"]
        run_id = event.get("run_id")
        if kind in OWNERSHIP_EVENT_TYPES:
            continue
        if kind in PREVENTION_EVENT_TYPES:
            continue
        if kind == "run_started":
            if run_id in runs:
                raise WorkMemoryError("duplicate-run-start", 3)
            runs[run_id] = {"start": event, "terminal": None, "blockers": set(), "corrections": [], "verifications": [], "context": None, "execution_ordinals": set()}
            continue
        if run_id is not None:
            if run_id not in runs:
                raise WorkMemoryError("event-before-run-start", 3)
            if (
                runs[run_id]["terminal"] is not None
                and event["event_id"] not in legacy_post_terminal_event_ids
            ):
                raise WorkMemoryError("event-after-terminal", 3)
        if kind in {"blocker_opened", "pre_run_blocker_opened"}:
            if event["blocker_id"] in blockers:
                raise WorkMemoryError("duplicate-blocker-open", 3)
            blockers[event["blocker_id"]] = "open"
            blocker_meta[event["blocker_id"]] = event
            blocker_occurrences[event["blocker_id"]] = event["occurrence_id"]
            if run_id is not None:
                blocker_occurrence_runs[event["blocker_id"]] = run_id
            legacy_stranded_fixed_sources.pop(event["blocker_id"], None)
            if run_id is not None:
                runs[run_id]["blockers"].add(event["blocker_id"])
        elif kind == "blocker_recurred":
            if blockers.get(event["blocker_id"]) != "closed":
                raise WorkMemoryError("invalid-blocker-recurrence", 3)
            blockers[event["blocker_id"]] = "open"
            blocker_occurrences[event["blocker_id"]] = event["occurrence_id"]
            blocker_occurrence_runs[event["blocker_id"]] = run_id
            blocker_verified_evidence.pop(event["blocker_id"], None)
            downstream_assignments.pop(event["blocker_id"], None)
            legacy_stranded_fixed_sources.pop(event["blocker_id"], None)
            runs[run_id]["blockers"].add(event["blocker_id"])
        elif kind == "blocker_assigned_downstream":
            blocker_id = event["blocker_id"]
            occurrence_id = blocker_occurrences.get(blocker_id)
            has_correction = any(
                item["blocker_id"] == blocker_id
                and item["occurrence_id"] == occurrence_id
                for item in corrections.values()
            )
            if (
                blockers.get(blocker_id) != "open"
                or occurrence_id != event["occurrence_id"]
                or blocker_occurrence_runs.get(blocker_id) != run_id
                or blocker_id in downstream_assignments
                or has_correction
            ):
                raise WorkMemoryError("invalid-downstream-blocker-assignment", 3)
            downstream_assignments[blocker_id] = event
        elif kind == "correction_recorded":
            pending_retry = failed_verification_reopens.get(event["blocker_id"])
            if (
                blockers.get(event["blocker_id"]) != "open"
                and event["event_id"] not in legacy_nonopen_correction_event_ids
            ):
                raise WorkMemoryError("correction-for-nonopen-blocker", 3)
            if event["blocker_id"] in downstream_assignments:
                raise WorkMemoryError("correction-for-downstream-blocker", 3)
            if event["correction_id"] in corrections:
                raise WorkMemoryError("duplicate-correction-id", 3)
            if not _superseded_correction_ids(event) <= set(corrections):
                raise WorkMemoryError("unknown-superseded-correction", 3)
            if (
                pending_retry is not None
                and _superseded_correction_ids(event) != pending_retry
            ):
                raise WorkMemoryError("failed-verification-retry-correction-mismatch", 3)
            primary_correction_id = event.get("primary_correction_id")
            if primary_correction_id is not None:
                primary = corrections.get(primary_correction_id)
                if (
                    primary is None
                    or primary["run_id"] != event["run_id"]
                    or primary["blocker_id"] == event["blocker_id"]
                    or primary["subject_id"] != event["subject_id"]
                    or primary["lineage_id"] != event["lineage_id"]
                    or primary["changed_artifacts"] != event["changed_artifacts"]
                    or primary["changed_artifact_hashes"] != event["changed_artifact_hashes"]
                    or primary["solution"] != event["solution"]
                    or primary["reusable_behavior_changed"]
                    != event["reusable_behavior_changed"]
                ):
                    raise WorkMemoryError("co-correction-primary-mismatch", 3)
            corrections[event["correction_id"]] = event
            runs[run_id]["corrections"].append(event)
            if pending_retry is not None:
                del failed_verification_reopens[event["blocker_id"]]
        elif kind == "pre_run_correction_recorded":
            blocker = blocker_meta.get(event["blocker_id"])
            current_status = blockers.get(event["blocker_id"])
            supersedes_id = event.get("supersedes_correction_id")
            superseded_correction = (
                pre_run_corrections.get(supersedes_id)
                if supersedes_id is not None else None
            )
            if (
                current_status not in {"open", "fixed-awaiting-verification"}
                or blocker is None
                or blocker.get("event_type") != "pre_run_blocker_opened"
                or event["task_id"] != blocker["task_id"]
                or event["ownership_event_id"] != blocker["ownership_event_id"]
                or event["occurrence_id"] != blocker_occurrences[event["blocker_id"]]
                or event["correction_id"] in pre_run_corrections
            ):
                raise WorkMemoryError("invalid-pre-run-correction-binding", 3)
            if current_status == "open" and supersedes_id is not None:
                raise WorkMemoryError("invalid-pre-run-correction-supersession", 3)
            if current_status == "fixed-awaiting-verification" and (
                superseded_correction is None
                or supersedes_id in superseded_pre_run_corrections
                or superseded_correction["blocker_id"] != event["blocker_id"]
                or superseded_correction["occurrence_id"] != event["occurrence_id"]
            ):
                raise WorkMemoryError("invalid-pre-run-correction-supersession", 3)
            if supersedes_id is not None:
                superseded_pre_run_corrections.add(supersedes_id)
            pre_run_corrections[event["correction_id"]] = event
        elif kind == "pre_run_verification_recorded":
            correction = pre_run_corrections.get(event["correction_id"])
            if (
                correction is None
                or event["correction_id"] in superseded_pre_run_corrections
                or event["task_id"] != correction["task_id"]
                or event["ownership_event_id"] != correction["ownership_event_id"]
                or event["blocker_id"] != correction["blocker_id"]
                or event["occurrence_id"] != correction["occurrence_id"]
                or event["changed_artifact_hashes"] != correction["changed_artifact_hashes"]
                or event["event_id"] in pre_run_verifications
            ):
                raise WorkMemoryError("invalid-pre-run-verification-binding", 3)
            pre_run_verifications[event["event_id"]] = event
        elif kind == "pre_run_blocker_transitioned":
            current = blockers.get(event["blocker_id"])
            blocker = blocker_meta.get(event["blocker_id"])
            valid = {
                "open": {"fixed-awaiting-verification"},
                "fixed-awaiting-verification": {"verified"},
                "verified": {"closed"},
            }
            if (
                blocker is None
                or blocker.get("event_type") != "pre_run_blocker_opened"
                or current != event["from_status"]
                or event["to_status"] not in valid.get(current, set())
                or event["task_id"] != blocker["task_id"]
                or event["ownership_event_id"] != blocker["ownership_event_id"]
                or event["occurrence_id"] != blocker_occurrences[event["blocker_id"]]
            ):
                raise WorkMemoryError("invalid-pre-run-blocker-transition", 3)
            matching = [
                item for item in pre_run_corrections.values()
                if item["blocker_id"] == event["blocker_id"]
                and item["occurrence_id"] == event["occurrence_id"]
                and item["correction_id"]
                not in superseded_pre_run_corrections
            ]
            if current == "open" and len(matching) != 1:
                raise WorkMemoryError("pre-run-blocker-correction-required", 3)
            if current in {"fixed-awaiting-verification", "verified"}:
                verification = pre_run_verifications.get(event.get("verification_event_id"))
                if (
                    verification is None
                    or verification["outcome"] != "passed"
                    or verification["quality"] != "same-command"
                    or len(matching) != 1
                    or verification["correction_id"] != matching[0]["correction_id"]
                    or (current == "verified" and event.get("remaining_work") != "none")
                ):
                    raise WorkMemoryError("invalid-pre-run-transition-verification", 3)
            blockers[event["blocker_id"]] = event["to_status"]
        elif kind == "verification_recorded":
            start = runs[run_id]["start"]
            if event["subject_id"] != start["subject_id"] or event["lineage_id"] != start["lineage_id"]:
                raise WorkMemoryError("verification-run-binding-mismatch", 3)
            if event["source_bundle_hash"] != start["source_bundle_hash"]:
                raise WorkMemoryError("verification-bundle-mismatch", 3)
            if event["correction_ids"]:
                run_corrections = {item["correction_id"]: item for item in runs[run_id]["corrections"]}
                successor_ids = set(start.get("verifies_correction_ids", []))
                available = set(run_corrections) | successor_ids
                if set(event["correction_ids"]) != available:
                    raise WorkMemoryError("verification-correction-mismatch", 3)
                selected = [corrections[item] for item in event["correction_ids"] if item in corrections]
                if len(selected) != len(event["correction_ids"]):
                    raise WorkMemoryError("verification-correction-not-found", 3)
                if set(event["blocker_ids"]) != {item["blocker_id"] for item in selected}:
                    raise WorkMemoryError("verification-blocker-mismatch", 3)
                expected_hashes = [value for item in selected for value in item["changed_artifact_hashes"]]
                if event["changed_artifact_hashes"] != expected_hashes:
                    raise WorkMemoryError("verification-artifact-hash-mismatch", 3)
            elif event["blocker_ids"]:
                if (
                    event["quality"] != "same-path"
                    or not set(event["blocker_ids"]) <= runs[run_id]["blockers"]
                ):
                    raise WorkMemoryError(
                        "invalid-investigation-verification", 3,
                    )
            elif runs[run_id]["blockers"] or runs[run_id]["corrections"]:
                raise WorkMemoryError("clean-verification-after-correction", 3)
            verifications[event["event_id"]] = event
            runs[run_id]["verifications"].append(event)
        elif kind == "operation_context_recorded":
            start = runs[run_id]["start"]
            if (
                runs[run_id]["context"] is not None
                or event["context_id"] in contexts
                or event["subject_id"] != start["subject_id"]
                or event["lineage_id"] != start["lineage_id"]
                or event["source_bundle_hash"] != start["source_bundle_hash"]
                or event["effect_class"] not in candidate_contract.EFFECT_CLASSES
            ):
                raise WorkMemoryError("operation-context-binding-mismatch", 3)
            contexts[event["context_id"]] = event
            runs[run_id]["context"] = event
        elif kind == "execution_claimed":
            start = runs[run_id]["start"]
            context = contexts.get(event["context_id"])
            if (
                context is None or context["run_id"] != run_id
                or event["execution_id"] in executions
                or event["step_ordinal"] in runs[run_id]["execution_ordinals"]
                or event["subject_id"] != start["subject_id"]
                or event["lineage_id"] != start["lineage_id"]
                or event["source_bundle_hash"] != start["source_bundle_hash"]
                or event["repository_roots_hash"] != context["repository_roots_hash"]
                or event["operation_kind"] != start["operation_kind"]
                or event["effect_class"] != context["effect_class"]
            ):
                raise WorkMemoryError("execution-claim-binding-mismatch", 3)
            executions[event["execution_id"]] = event
            runs[run_id]["execution_ordinals"].add(event["step_ordinal"])
        elif kind == "execution_returned":
            claim = executions.get(event["execution_id"])
            if (
                claim is None or event["execution_id"] in returned
                or event["context_id"] != claim["context_id"]
                or event["run_id"] != claim["run_id"]
                or event["subject_id"] != claim["subject_id"]
                or event["lineage_id"] != claim["lineage_id"]
                or event["source_bundle_hash"] != claim["source_bundle_hash"]
            ):
                raise WorkMemoryError("execution-return-binding-mismatch", 3)
            returned.add(event["execution_id"])
        elif kind == "observer_decision_recorded":
            trigger = event_index.get(event["trigger_event_id"])
            if (
                trigger is None or trigger["event_type"] != "run_closed"
                or event["decision_id"] in decisions
            ):
                raise WorkMemoryError("observer-decision-trigger-mismatch", 3)
            decisions[event["decision_id"]] = event
        elif kind == "observer_bootstrap_result_recorded":
            if (
                event["decision_id"] not in decisions
                or event["bootstrap_attempt_id"] in bootstrap_attempts
            ):
                raise WorkMemoryError("observer-bootstrap-result-binding-mismatch", 3)
            bootstrap_attempts.add(event["bootstrap_attempt_id"])
        elif kind == "observer_candidate_linked":
            decision = decisions.get(event["decision_id"])
            binding_matches = (
                decision is not None
                and (
                    (
                        event["link_kind"] == "existing"
                        and decision["target_kind"] == event["target_kind"]
                        and decision["target_id"] == event["target_id"]
                    )
                    or (
                        event["link_kind"] == "proposed"
                        and decision["disposition"] == "PROPOSE_DISCOVERY"
                        and decision["target_kind"] is None
                        and decision["target_id"] is None
                        and event["target_kind"] == "discovery"
                    )
                )
            )
            if (
                not binding_matches or event["link_id"] in links
                or decision["candidate_fingerprint"] != event["candidate_fingerprint"]
            ):
                raise WorkMemoryError("observer-link-binding-mismatch", 3)
            links.add(event["link_id"])
        elif kind == "blocker_transitioned":
            current = blockers.get(event["blocker_id"])
            if current != event["from_status"]:
                raise WorkMemoryError("blocker-from-status-mismatch", 3)
            valid = {
                "open": {"open", "fixed-awaiting-verification", "superseded", "non-gap"},
                "fixed-awaiting-verification": {"open", "verified", "superseded"},
                "verified": {"closed"},
            }
            if event["to_status"] not in valid.get(current, set()):
                raise WorkMemoryError("invalid-blocker-status-transition", 3)
            if current == "open" and event["to_status"] == "open":
                occurrence_run_id = blocker_occurrence_runs[event["blocker_id"]]
                occurrence_id = blocker_occurrences[event["blocker_id"]]
                occurrence_run = runs[occurrence_run_id]
                current_run = runs[run_id]
                blocker = blocker_meta[event["blocker_id"]]
                has_current_correction = any(
                    item["blocker_id"] == event["blocker_id"]
                    and item["occurrence_id"] == occurrence_id
                    for item in corrections.values()
                )
                if (
                    "recovery_evidence" not in event
                    or occurrence_run_id == run_id
                    or occurrence_run["terminal"] is None
                    or current_run["terminal"] is not None
                    or current_run["start"]["subject_id"] != blocker["subject_id"]
                    or current_run["start"]["lineage_id"] != blocker["lineage_id"]
                    or has_current_correction
                ):
                    raise WorkMemoryError("invalid-open-blocker-recovery", 3)
                blocker_occurrence_runs[event["blocker_id"]] = run_id
                downstream_assignments.pop(event["blocker_id"], None)
                runs[run_id]["blockers"].add(event["blocker_id"])
            if current == "open" and event["to_status"] == "fixed-awaiting-verification":
                occurrence_id = blocker_occurrences[event["blocker_id"]]
                has_current_correction = any(
                    item["blocker_id"] == event["blocker_id"]
                    and item["occurrence_id"] == occurrence_id
                    for item in corrections.values()
                )
                if (
                    event["blocker_id"] in failed_verification_reopens
                    or not has_current_correction
                    and event["event_id"] not in legacy_premature_fixed_event_ids
                ):
                    raise WorkMemoryError("blocker-correction-required", 3)
                if has_current_correction:
                    legacy_stranded_fixed_sources.pop(event["blocker_id"], None)
                else:
                    legacy_stranded_fixed_sources[event["blocker_id"]] = event["event_id"]
            if current == "fixed-awaiting-verification" and event["to_status"] == "open":
                if "recovery_evidence" in event:
                    if event["blocker_id"] not in legacy_stranded_fixed_sources:
                        raise WorkMemoryError("recovery-source-not-legacy-stranded", 3)
                    del legacy_stranded_fixed_sources[event["blocker_id"]]
                else:
                    verification = verifications.get(event.get("verification_event_id"))
                    if (
                        verification is None
                        and event["event_id"] in legacy_unverified_reopen_event_ids
                    ):
                        blockers[event["blocker_id"]] = event["to_status"]
                        continue
                    occurrence_id = blocker_occurrences[event["blocker_id"]]
                    superseded = {
                        correction_id
                        for item in corrections.values()
                        for correction_id in _superseded_correction_ids(item)
                    }
                    active = {
                        item["correction_id"]: item
                        for item in corrections.values()
                        if item["blocker_id"] == event["blocker_id"]
                        and item["occurrence_id"] == occurrence_id
                        and item["correction_id"] not in superseded
                    }
                    current_start = runs[run_id]["start"]
                    ancestor_ids: set[str] = set()
                    cursor = current_start.get("predecessor_run_id")
                    while cursor is not None and cursor not in ancestor_ids:
                        ancestor_ids.add(cursor)
                        cursor = runs.get(cursor, {}).get("start", {}).get(
                            "predecessor_run_id"
                        )
                    verification_run = (
                        runs.get(verification["run_id"]) if verification is not None else None
                    )
                    current_run_verification = (
                        verification is not None and verification["run_id"] == run_id
                    )
                    closed_failed_ancestor = (
                        verification is not None
                        and verification["run_id"] in ancestor_ids
                        and verification_run is not None
                        and verification_run["terminal"] is not None
                        and verification_run["terminal"]["event_type"] == "run_closed"
                        and verification_run["terminal"]["result"] == "failed"
                        and verification_run["terminal"]["verification_quality"] == "same-path"
                    )
                    if (
                        verification is None
                        or not (current_run_verification or closed_failed_ancestor)
                        or verification["subject_id"] != current_start["subject_id"]
                        or verification["lineage_id"] != current_start["lineage_id"]
                        or verification["outcome"] != "failed"
                        or verification["quality"] != "same-path"
                        or event["blocker_id"] not in verification["blocker_ids"]
                        or not active
                        or not set(active) <= set(verification["correction_ids"])
                        or not _active_correction_artifacts_preserved(
                            active.values(), verification_run["start"], current_start,
                        )
                    ):
                        raise WorkMemoryError("invalid-failed-verification-reopen", 3)
                    failed_verification_reopens[event["blocker_id"]] = set(active)
            if current == "fixed-awaiting-verification" and event["to_status"] == "superseded":
                candidates = {
                    item["correction_id"]
                    for item in corrections.values()
                    if item["blocker_id"] == event["blocker_id"]
                }
                superseded = {
                    correction_id
                    for item in corrections.values()
                    for correction_id in _superseded_correction_ids(item)
                }
                if not candidates or not candidates <= superseded:
                    raise WorkMemoryError("blocker-correction-not-superseded", 3)
            verification_id = event.get("verification_event_id")
            if verification_id and event["to_status"] != "open":
                verification = verifications.get(verification_id)
                reconciliation_basis = event.get("reconciliation_basis_event_id")
                is_reconciliation = reconciliation_basis is not None
                transition_start = runs[event["run_id"]]["start"]
                if (
                    not verification or verification["outcome"] != "passed"
                    or verification["quality"] != "same-path"
                    or event["blocker_id"] not in verification["blocker_ids"]
                ):
                    raise WorkMemoryError("invalid-transition-verification", 3)
                if event["to_status"] == "non-gap":
                    if (
                        verification["run_id"] != event["run_id"]
                        or verification["correction_ids"]
                        or verification["changed_artifact_hashes"]
                        or is_reconciliation
                    ):
                        raise WorkMemoryError(
                            "invalid-non-gap-verification", 3,
                        )
                    blockers[event["blocker_id"]] = event["to_status"]
                    continue
                if is_reconciliation:
                    if (
                        reconciliation_basis != verification_id
                        or transition_start["subject_id"]
                        != "blocker-backlog-reconciliation"
                    ):
                        raise WorkMemoryError(
                            "invalid-blocker-reconciliation-authority", 3,
                        )
                elif verification["run_id"] != event["run_id"]:
                    raise WorkMemoryError("invalid-transition-verification", 3)
                candidates = [item for item in corrections.values() if item["blocker_id"] == event["blocker_id"]]
                superseded = {
                    correction_id
                    for item in candidates
                    for correction_id in _superseded_correction_ids(item)
                }
                active = [item for item in candidates if item["correction_id"] not in superseded]
                active_ids = {item["correction_id"] for item in active}
                successor = runs[verification["run_id"]]["start"]
                if (
                    not active_ids
                    or not active_ids <= set(verification["correction_ids"])
                    or not active_ids <= set(successor.get("verifies_correction_ids", []))
                    or verification["lineage_id"] != blocker_meta[event["blocker_id"]]["lineage_id"]
                ):
                    raise WorkMemoryError("verification-successor-binding-mismatch", 3)
                if (
                    is_reconciliation
                    and current == "verified"
                    and blocker_verified_evidence.get(event["blocker_id"])
                    != verification_id
                ):
                    raise WorkMemoryError(
                        "blocker-reconciliation-verification-mismatch", 3,
                    )
                if event["to_status"] == "verified":
                    blocker_verified_evidence[event["blocker_id"]] = verification_id
            blockers[event["blocker_id"]] = event["to_status"]
        elif kind in {"run_closed", "run_abandoned"}:
            start = runs[run_id]["start"]
            if event["subject_id"] != start["subject_id"] or event["lineage_id"] != start["lineage_id"]:
                raise WorkMemoryError("terminal-run-binding-mismatch", 3)
            if kind == "run_closed":
                open_blockers = sorted(
                    blocker_id for blocker_id in runs[run_id]["blockers"]
                    if blockers.get(blocker_id) == "open"
                    and blocker_id not in downstream_assignments
                )
                if open_blockers and event["event_id"] not in legacy_open_terminal_event_ids:
                    raise WorkMemoryError("terminal-run-has-open-blockers", 3)
                if event["correction_count"] != len(runs[run_id]["corrections"]):
                    raise WorkMemoryError("terminal-correction-count-mismatch", 3)
                quality = runs[run_id]["verifications"][-1]["quality"] if runs[run_id]["verifications"] else "none"
                if event["verification_quality"] != quality:
                    raise WorkMemoryError("terminal-verification-quality-mismatch", 3)
            runs[run_id]["terminal"] = event


def stage_event_batch(existing: bytes, request: dict[str, Any]) -> tuple[bytes, bytes, dict[str, Any]]:
    """Pure, non-locking reducer used by transact and promotion."""
    if set(request) != {"schema_version", "expected_ledger_hash", "events"} or request.get("schema_version") != 1:
        raise WorkMemoryError("invalid-transact-request", 2)
    if not isinstance(request.get("events"), list) or not request["events"]:
        raise WorkMemoryError("empty-event-batch", 2)
    previous_hash = sha256_bytes(existing)
    if request["expected_ledger_hash"] is not None and request["expected_ledger_hash"] != previous_hash:
        raise WorkMemoryError("ledger-hash-conflict", 3)
    current = parse_ledger_bytes(existing)
    by_id = _event_index(current)
    added: list[dict[str, Any]] = []
    idempotent: list[str] = []
    for event in request["events"]:
        _validate_event_shape(event)
        prior = by_id.get(event["event_id"])
        if prior is not None:
            if prior != event:
                raise WorkMemoryError("event-id-conflict", 3)
            idempotent.append(event["event_id"])
            continue
        _validate_new_event_policy(event)
        by_id[event["event_id"]] = event
        added.append(event)
    result_events = current + added
    validate_lifecycle(
        result_events,
        legacy_premature_fixed_event_ids=set(_event_index(current)),
        legacy_open_terminal_event_ids={
            event["event_id"] for event in current
            if event["event_type"] == "run_closed"
        },
        legacy_post_terminal_event_ids=set(_event_index(current)),
        legacy_nonopen_correction_event_ids=set(_event_index(current)),
        legacy_unverified_reopen_event_ids=set(_event_index(current)),
    )
    ledger_bytes = b"".join(canonical_bytes(event) for event in result_events)
    ledger_hash = sha256_bytes(ledger_bytes)
    view_bytes = render_blocker_view(result_events, ledger_hash).encode()
    response = {
        "ok": True, "previous_ledger_hash": previous_hash, "ledger_hash": ledger_hash,
        "event_ids": [event["event_id"] for event in request["events"]],
        "idempotent_event_ids": idempotent, "blocker_view_hash": sha256_bytes(view_bytes),
    }
    return ledger_bytes, view_bytes, response


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        tmp.unlink(missing_ok=True)


def _authorize_event_batch(
    existing_events: list[dict[str, Any]],
    requested_events: list[dict[str, Any]],
    writer_thread_id: str | None,
) -> None:
    tasks, runs = _ownership_snapshot(existing_events)
    blocker_tasks: dict[str, str | None] = {}
    blocker_meta = {
        event["blocker_id"]: event
        for event in existing_events
        if event["event_type"] in {"blocker_opened", "pre_run_blocker_opened"}
    }
    run_starts = {
        event["run_id"]: event
        for event in existing_events
        if event["event_type"] == "run_started"
    }
    for event in existing_events:
        if event["event_type"] == "blocker_opened":
            blocker_tasks[event["blocker_id"]] = runs.get(event["run_id"])
        elif event["event_type"] == "pre_run_blocker_opened":
            blocker_tasks[event["blocker_id"]] = event["task_id"]
        elif (
            event["event_type"] == "blocker_transitioned"
            and event.get("from_status") == "open"
            and event.get("to_status") == "open"
            and "recovery_evidence" in event
            and blocker_tasks.get(event["blocker_id"]) is None
            and runs.get(event["run_id"]) is not None
        ):
            blocker_tasks[event["blocker_id"]] = runs[event["run_id"]]
    by_id = _event_index(existing_events)
    additions: list[dict[str, Any]] = []
    for event in requested_events:
        _validate_event_shape(event)
        prior = by_id.get(event["event_id"])
        if prior is not None:
            if prior != event:
                raise WorkMemoryError("event-id-conflict", 3)
            continue
        additions.append(event)
    if (
        any(event["event_type"] == "task_writer_handoff_recorded" for event in additions)
        and len(additions) != 1
    ):
        raise WorkMemoryError("task-writer-handoff-must-be-atomic", 3)

    for event in additions:
        kind = event["event_type"]
        v2_ownership = event.get("schema_version") == 2
        if kind == "task_writer_claimed":
            task_id = event["task_id"]
            claimed_writer = event["writer_id"] if v2_ownership else event["writer_thread_id"]
            if claimed_writer != writer_thread_id:
                raise WorkMemoryError("task-writer-host-mismatch", 4)
            if task_id in tasks:
                raise WorkMemoryError("task-writer-already-claimed", 4)
            state = {
                "writer_thread_id": writer_thread_id,
                "ownership_generation": 1,
                "ownership_event_id": event["event_id"],
            }
            if v2_ownership:
                state.update({
                    "schema_version": 2,
                    "writer_client_kind": event["writer_client_kind"],
                    "writer_session_id": event["writer_session_id"],
                })
            tasks[task_id] = state
            continue
        if kind == "task_writer_handoff_recorded":
            task_id = event["task_id"]
            current = tasks.get(task_id)
            from_writer = event["from_writer_id"] if v2_ownership else event["from_writer_thread_id"]
            if (
                current is None
                or current["writer_thread_id"] != writer_thread_id
                or from_writer != writer_thread_id
                or event["previous_ownership_event_id"] != current["ownership_event_id"]
                or event["ownership_generation"] != current["ownership_generation"] + 1
            ):
                raise WorkMemoryError("task-writer-handoff-not-authorized", 4)
            new_state = {
                "writer_thread_id": event["to_writer_id"] if v2_ownership else event["to_writer_thread_id"],
                "ownership_generation": event["ownership_generation"],
                "ownership_event_id": event["event_id"],
            }
            if v2_ownership:
                new_state.update({
                    "schema_version": 2,
                    "writer_client_kind": event["to_writer_client_kind"],
                    "writer_session_id": event["to_writer_session_id"],
                })
            expected_refresh, _ = _handoff_refresh_plan(
                task_id, current, new_state,
            )
            present_refresh = {
                key: event[key] for key in HANDOFF_REFRESH_FIELDS if key in event
            }
            if present_refresh != expected_refresh:
                raise WorkMemoryError("task-writer-handoff-refresh-mismatch", 4)
            tasks[task_id] = new_state
            continue
        if kind == "legacy_run_writer_bound":
            task_id = event["task_id"]
            current = tasks.get(task_id)
            if current is None or current["writer_thread_id"] != writer_thread_id:
                raise WorkMemoryError("task-writer-not-owner", 4)
            if event["writer_thread_id"] != writer_thread_id:
                raise WorkMemoryError("legacy-run-writer-host-mismatch", 4)
            if event["run_id"] not in runs or runs[event["run_id"]] is not None:
                raise WorkMemoryError("legacy-run-not-unbound", 4)
            _, class_hash, _ = load_receipt(
                task_id, "classification", require_fresh=False,
            )
            _, selection_hash, _ = load_receipt(
                task_id, "selection", require_fresh=False,
            )
            if (
                event["classification_receipt_hash"] != class_hash
                or event["selection_receipt_hash"] != selection_hash
            ):
                raise WorkMemoryError("legacy-run-receipt-binding-mismatch", 4)
            runs[event["run_id"]] = task_id
            continue
        if kind == "run_started":
            # Require the ownership fields the event's own schema carries. A schema-v2 writer
            # binds writer_id/kind/session; only schema-v1 binds writer_thread_id.
            required = {
                "task_id", "ownership_generation",
                "ownership_event_id", "ownership_sha256",
            } | (
                {"writer_id", "writer_client_kind", "writer_session_id"}
                if "writer_id" in event
                else {"writer_thread_id"}
            )
            if not required <= set(event):
                raise WorkMemoryError("new-run-writer-binding-required", 4)
            task_id = event["task_id"]
            current = tasks.get(task_id)
            if current is None or current["writer_thread_id"] != writer_thread_id:
                raise WorkMemoryError("task-writer-not-owner", 4)
            expected = _ownership_receipt_fields(task_id, current)
            if any(event[key] != value for key, value in expected.items()):
                raise WorkMemoryError("run-task-writer-binding-mismatch", 4)
            runs[event["run_id"]] = task_id
            run_starts[event["run_id"]] = event
            continue

        if kind == "pre_run_blocker_opened":
            task_id = event["task_id"]
            current = tasks.get(task_id)
            if (
                current is None
                or current["writer_thread_id"] != writer_thread_id
                or current["ownership_event_id"] != event["ownership_event_id"]
            ):
                raise WorkMemoryError("pre-run-blocker-ownership-mismatch", 4)
            blocker_id = event["blocker_id"]
            if blocker_id in blocker_tasks:
                raise WorkMemoryError("duplicate-blocker-open", 3)
            blocker_tasks[blocker_id] = task_id
            continue

        if kind in PRE_RUN_BLOCKER_EVENT_TYPES:
            task_id = event["task_id"]
            current = tasks.get(task_id)
            opened = blocker_meta.get(event["blocker_id"])
            if (
                current is None
                or current["writer_thread_id"] != writer_thread_id
                or current["ownership_event_id"] != event["ownership_event_id"]
                or opened is None
                or opened.get("event_type") != "pre_run_blocker_opened"
                or opened["task_id"] != task_id
                or opened["ownership_event_id"] != event["ownership_event_id"]
                or opened["occurrence_id"] != event["occurrence_id"]
            ):
                raise WorkMemoryError("pre-run-blocker-binding-mismatch", 4)
            continue

        if kind == "correction_preservation_recorded":
            if event["target_task_id"] == event["preserved_task_id"]:
                raise WorkMemoryError(
                    "correction-preservation-distinct-tasks-required", 4,
                )
            target_state = tasks.get(event["target_task_id"])
            preserved_state = tasks.get(event["preserved_task_id"])
            if (
                target_state is None
                or preserved_state is None
                or target_state["writer_thread_id"] != writer_thread_id
                or preserved_state["writer_thread_id"] != writer_thread_id
            ):
                raise WorkMemoryError("correction-preservation-owner-mismatch", 4)
            expected = {
                **_prefixed_ownership_receipt_fields(
                    "target", event["target_task_id"], target_state,
                ),
                **_prefixed_ownership_receipt_fields(
                    "preserved", event["preserved_task_id"], preserved_state,
                ),
            }
            if any(event[key] != value for key, value in expected.items()):
                raise WorkMemoryError("correction-preservation-receipt-mismatch", 4)
            continue

        if kind in PREVENTION_EVENT_TYPES:
            continue

        task_id: str | None = None
        run_id = event.get("run_id")
        if run_id is not None:
            if run_id not in runs:
                raise WorkMemoryError("event-before-run-start", 3)
            task_id = runs[run_id]
            if task_id is None:
                raise WorkMemoryError("legacy-run-writer-binding-required", 4)
        if task_id is not None:
            current = tasks.get(task_id)
            if current is None or current["writer_thread_id"] != writer_thread_id:
                raise WorkMemoryError("task-writer-not-owner", 4)

        linked_blocker_ids: list[str] = []
        if kind in {"verification_recorded", "run_closed"}:
            linked_blocker_ids = list(event["blocker_ids"])
        elif "blocker_id" in event:
            linked_blocker_ids = [event["blocker_id"]]
        if kind == "blocker_opened":
            blocker_id = event["blocker_id"]
            if blocker_id in blocker_tasks:
                raise WorkMemoryError("duplicate-blocker-open", 3)
            blocker_tasks[blocker_id] = task_id
        else:
            for blocker_id in linked_blocker_ids:
                opened = blocker_meta.get(blocker_id)
                start = run_starts.get(run_id) if run_id is not None else None
                adopts_legacy_blocker = (
                    kind == "blocker_transitioned"
                    and event.get("from_status") == "open"
                    and event.get("to_status") == "open"
                    and "recovery_evidence" in event
                    and blocker_tasks.get(blocker_id) is None
                    and task_id is not None
                    and opened is not None
                    and start is not None
                    and opened["subject_id"] == start["subject_id"]
                    and opened["lineage_id"] == start["lineage_id"]
                )
                if adopts_legacy_blocker:
                    blocker_tasks[blocker_id] = task_id
                elif blocker_tasks.get(blocker_id) != task_id:
                    raise WorkMemoryError("cross-task-blocker-mutation", 4)


def _batch_requires_host_thread(events: Sequence[dict[str, Any]]) -> bool:
    return any(
        event.get("event_type") in OWNERSHIP_EVENT_TYPES
        or event.get("event_type") == "correction_preservation_recorded"
        or event.get("event_type") in PRE_RUN_BLOCKER_EVENT_TYPES
        or event.get("event_type") == "run_started"
        or (
            event.get("event_type") not in PREVENTION_EVENT_TYPES
            and "run_id" in event
        )
        for event in events
    )


def _resolve_ledger_view_pair(
    ledger: Path | None, view: Path | None,
) -> tuple[Path, Path]:
    resolved_ledger = (ledger or LEDGER).resolve()
    resolved_view = (view or BLOCKER_VIEW).resolve()
    canonical_ledger = resolved_ledger == LEDGER.resolve()
    canonical_view = resolved_view == BLOCKER_VIEW.resolve()
    if canonical_ledger != canonical_view:
        raise WorkMemoryError("ledger-view-authority-mismatch", 4)
    if not canonical_ledger and (ledger is None or view is None):
        raise WorkMemoryError("custom-ledger-view-pair-required", 4)
    if resolved_ledger == resolved_view:
        raise WorkMemoryError("ledger-view-path-conflict", 4)
    return resolved_ledger, resolved_view


def transact(
    request: dict[str, Any], ledger: Path | None = None, view: Path | None = None,
) -> dict[str, Any]:
    requested_events = request.get("events", [])
    ledger, view = _resolve_ledger_view_pair(ledger, view)
    lock = ledger.with_suffix(ledger.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    handoff_task_ids = {
        event["task_id"] for event in requested_events
        if event.get("event_type") == "task_writer_handoff_recorded"
    }
    if len(handoff_task_ids) > 1:
        raise WorkMemoryError("task-writer-handoff-must-be-atomic", 3)
    receipt_context = (
        _task_receipt_lock(next(iter(handoff_task_ids)))
        if handoff_task_ids else nullcontext()
    )
    with receipt_context:
        with lock.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            existing = ledger.read_bytes() if ledger.exists() else b""
            writer_thread_id = (
                writer_identity()["writer_id"] if _batch_requires_host_thread(requested_events) else None
            )
            _authorize_event_batch(
                parse_ledger_bytes(existing), requested_events, writer_thread_id,
            )
            ledger_bytes, view_bytes, response = stage_event_batch(existing, request)
            _atomic_write(ledger, ledger_bytes)
            try:
                _atomic_write(view, view_bytes)
            except OSError as exc:
                raise WorkMemoryError("view-write-failed:ledger-committed", 5) from exc
    return response


def render_blocker_view(events: list[dict[str, Any]], ledger_hash: str) -> str:
    blockers: dict[str, dict[str, Any]] = {}
    for event in events:
        if event["event_type"] in {"blocker_opened", "pre_run_blocker_opened"}:
            blockers[event["blocker_id"]] = dict(event)
        elif event["event_type"] == "blocker_recurred" and event["blocker_id"] in blockers:
            blockers[event["blocker_id"]].update(status="open", evidence=event["evidence"])
            blockers[event["blocker_id"]].pop("classification", None)
            blockers[event["blocker_id"]].pop("downstream_owner", None)
        elif event["event_type"] == "blocker_transitioned" and event["blocker_id"] in blockers:
            blockers[event["blocker_id"]]["status"] = event["to_status"]
            if event["to_status"] == "open" and "recovery_evidence" in event:
                blockers[event["blocker_id"]].pop("classification", None)
                blockers[event["blocker_id"]].pop("downstream_owner", None)
        elif event["event_type"] == "pre_run_blocker_transitioned" and event["blocker_id"] in blockers:
            blockers[event["blocker_id"]]["status"] = event["to_status"]
        elif event["event_type"] == "blocker_assigned_downstream" and event["blocker_id"] in blockers:
            blockers[event["blocker_id"]].update(
                classification=event["classification"],
                downstream_owner=event["downstream_owner"],
            )
    lines = ["# Work Blockers", "", f"Ledger-SHA256: `{ledger_hash}`", "",
             "This file is generated from `operations/work-memory/events.jsonl`.", ""]
    for blocker_id in sorted(blockers):
        item = blockers[blocker_id]
        lines.extend([
            f"## {blocker_id}", "", f"- Status: `{item['status']}`",
            f"- Subject: `{item['subject_id']}`", f"- Step: `{item['step_id']}`",
            f"- Surface: `{item['surface']}`", f"- Symptom: {item['symptom']}",
            f"- Evidence: {item['evidence']}",
        ])
        if "classification" in item:
            lines.extend([
                f"- Classification: `{item['classification']}`",
                f"- Downstream owner: `{item['downstream_owner']}`",
            ])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def load_ledger(path: Path | None = None) -> tuple[list[dict[str, Any]], str]:
    path = path or LEDGER
    data = path.read_bytes() if path.exists() else b""
    return parse_ledger_bytes(data), sha256_bytes(data)


def blocker_view_stale(ledger_hash: str, view: Path = BLOCKER_VIEW) -> bool:
    if not view.is_file():
        return True
    match = re.search(r"Ledger-SHA256: `([0-9a-f]{64})`", view.read_text(errors="replace"))
    return match is None or match.group(1) != ledger_hash


def semantic_discovery_bytes(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    required = ["CreatedAtUtc:", "## Intended Outcome", "## Why This Looks Repeatable",
                "## Required Inputs, Auth, Or Environment", "## Commands And Observations",
                "## Failure Handling", "## Verified Path", "## Promotion Readiness"]
    if not all(marker in text for marker in required):
        raise WorkMemoryError("invalid-discovery-document", 3)
    lines = [line for line in text.splitlines() if not re.match(
        r"^(Status|ReadyAtUtc|PromotedSequenceId|SuccessfulRuns|LastValidatedAtUtc):", line
    )]
    return ("\n".join(lines).rstrip() + "\n").encode()


def _repo_roots(
    path: str | None = None, *, snapshot: dict[str, str] | None = None,
) -> dict[str, Path]:
    if path and snapshot is not None:
        raise WorkMemoryError("conflicting-repo-roots", 2)
    if snapshot is not None:
        raw: Any = snapshot
    else:
        source = Path(path or os.environ.get("MK_REPO_ROOTS_FILE", "~/.config/memory-knowledge/repositories.json")).expanduser()
        raw = json.loads(source.read_text()) if source.is_file() else {}
    if not isinstance(raw, dict) or any(
        not isinstance(key, str) or not key or not isinstance(value, str) or not value
        for key, value in raw.items()
    ):
        raise WorkMemoryError("invalid-repo-roots", 2)
    roots = {str(key): Path(value).expanduser().resolve() for key, value in raw.items()}
    roots.setdefault("memory-knowledge", ROOT.resolve())
    return roots


def _safe_file(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise WorkMemoryError("dependency-path-escape", 3)
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise WorkMemoryError("dependency-path-escape", 3) from exc
    if not resolved.is_file():
        raise WorkMemoryError("missing-dependency", 3)
    return resolved


def _artifact_identity(value: Any) -> tuple[str, str]:
    """Return the repository-qualified identity stored in correction events."""
    if isinstance(value, str):
        return "memory-knowledge", value
    if (
        isinstance(value, dict)
        and set(value) == {"repository_key", "path"}
        and isinstance(value["repository_key"], str)
        and isinstance(value["path"], str)
        and value["repository_key"]
        and value["path"]
    ):
        return value["repository_key"], value["path"]
    raise WorkMemoryError("invalid-changed-artifact-identity", 2)


def resolve_bundle(
    *, mode: str, subject_id: str, document: Path, manifest: Path,
    repo_roots_file: str | None = None, repository_roots: dict[str, str] | None = None,
    include_bootstrap_trust_anchors: bool = False,
) -> tuple[list[dict[str, str]], str, str]:
    roots = _repo_roots(repo_roots_file, snapshot=repository_roots)
    seen: dict[tuple[str, str], str] = {}
    stack: list[str] = []
    entries: list[dict[str, str]] = []

    def add(repo_key: str, relative: str, raw_path: Path, *, semantic: bool = False) -> None:
        key = (repo_key, relative)
        data = semantic_discovery_bytes(raw_path) if semantic else raw_path.read_bytes()
        digest = sha256_bytes(data)
        if key in seen:
            if seen[key] != digest:
                raise WorkMemoryError("duplicate-bundle-file", 3)
            return
        seen[key] = digest
        entries.append({"repository_key": repo_key, "path": relative, "sha256": digest})

    def visit(sequence_id: str, doc: Path, manifest_path: Path, discovery: bool = False) -> str:
        if sequence_id in stack:
            raise WorkMemoryError("dependency-cycle", 3)
        stack.append(sequence_id)
        if not manifest_path.is_file():
            raise WorkMemoryError("missing-dependency-manifest", 3)
        try:
            manifest_data = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as exc:
            raise WorkMemoryError("invalid-dependency-manifest", 3) from exc
        base_manifest_keys = {"schema_version", "lineage_id", "dependencies"}
        candidate_manifest_keys = {
            "candidate_identity", "candidate_fingerprint", "observer_provenance",
        }
        manifest_keys = set(manifest_data)
        if (
            manifest_data.get("schema_version") != 1
            or frozenset(manifest_keys) not in {
                frozenset(base_manifest_keys),
                frozenset(base_manifest_keys | candidate_manifest_keys),
            }
        ):
            raise WorkMemoryError("invalid-dependency-manifest", 3)
        if candidate_manifest_keys <= manifest_keys:
            try:
                candidate_contract.validate_candidate_identity(
                    manifest_data["candidate_identity"],
                    manifest_data["candidate_fingerprint"],
                )
            except candidate_contract.CandidateContractError as exc:
                raise WorkMemoryError(exc.code, 3) from exc
        lineage = require_id(manifest_data["lineage_id"], "lineage-id")
        if not isinstance(manifest_data["dependencies"], list):
            raise WorkMemoryError("invalid-dependency-manifest", 3)
        doc_rel = str(doc.resolve().relative_to(ROOT))
        manifest_rel = str(manifest_path.resolve().relative_to(ROOT))
        add("memory-knowledge", doc_rel, doc, semantic=discovery)
        add("memory-knowledge", manifest_rel, manifest_path)
        for dep in manifest_data["dependencies"]:
            if not isinstance(dep, dict) or set(dep) != {"kind", "repository_key", "path_or_sequence_id"}:
                raise WorkMemoryError("invalid-dependency-entry", 3)
            dep_kind, repo_key, value = dep["kind"], dep["repository_key"], dep["path_or_sequence_id"]
            if dep_kind == "sequence":
                child_doc = ROOT / "operations/sequences" / value / "sequence.md"
                child_manifest = child_doc.with_name("dependencies.json")
                visit(value, child_doc, child_manifest)
            elif dep_kind in {"file", "glob"}:
                if repo_key not in roots:
                    raise WorkMemoryError("missing-repository-root", 3)
                repo_root = roots[repo_key]
                paths = [_safe_file(repo_root, value)] if dep_kind == "file" else sorted(repo_root.glob(value))
                if not paths or any(not path.is_file() for path in paths):
                    raise WorkMemoryError("unmatched-dependency-glob", 3)
                for path in paths:
                    relative = str(path.resolve().relative_to(repo_root.resolve()))
                    add(repo_key, relative, path)
            else:
                raise WorkMemoryError("invalid-dependency-kind", 3)
        stack.pop()
        return lineage

    lineage_id = visit(subject_id, document.resolve(), manifest.resolve(), mode == "discovery")
    if ("memory-knowledge", "scripts/sequence_intake_launch.py") in seen:
        for relative in SEQUENCE_INTAKE_CONTROL_DEPENDENCIES:
            add("memory-knowledge", relative, _safe_file(roots["memory-knowledge"], relative))
    if include_bootstrap_trust_anchors:
        for relative in BOOTSTRAP_TRUST_ANCHORS:
            if ("memory-knowledge", relative) not in seen:
                add("memory-knowledge", relative, _safe_file(roots["memory-knowledge"], relative))
    entries.sort(key=lambda item: (item["repository_key"], item["path"], item["sha256"]))
    document_text = document.read_text(encoding="utf-8")
    control_scripts = {
        "scripts/work_memory.py", "scripts/sequence_guard.py",
        "scripts/sequence_discovery_log.py", "scripts/blocker_catalog.py",
        "scripts/directive_guard.py",
    }
    reference_pattern = re.compile(
        r"(?P<absolute>/(?:[A-Za-z0-9_.{}<>-]+/)*(?:scripts|tools|dist)/"
        r"[A-Za-z0-9_.*?/{<>}-]+\.(?:py|sh))|"
        r"(?<![A-Za-z0-9_.*?/{<>}-])"
        r"(?:(?P<repo>[A-Za-z0-9_.-]+):)?(?P<relative>"
        r"(?:[A-Za-z0-9_.*?{<>}-]+/)*(?:scripts|tools|dist)/"
        r"[A-Za-z0-9_.*?/{<>}-]+\.(?:py|sh))"
    )
    for match in reference_pattern.finditer(document_text):
        repo_key = match.group("repo") or ""
        referenced_path = match.group("absolute") or match.group("relative")
        if match.group("absolute"):
            absolute = Path(referenced_path).resolve()
            root_matches: list[tuple[int, str, str]] = []
            for candidate_key, root in roots.items():
                try:
                    relative = str(absolute.relative_to(root.resolve()))
                except ValueError:
                    continue
                root_matches.append((len(root.parts), candidate_key, relative))
            if not root_matches:
                raise WorkMemoryError(
                    f"executable-outside-manifest::{referenced_path}", 3
                )
            _, repo_key, referenced_path = max(root_matches)
        if referenced_path in control_scripts or "<" in referenced_path or ">" in referenced_path:
            continue
        covered = any(
            (not repo_key or item["repository_key"] == repo_key)
            and (item["path"] == referenced_path or fnmatch.fnmatch(item["path"], referenced_path))
            for item in entries
        )
        if not covered:
            raise WorkMemoryError(f"executable-outside-manifest:{repo_key}:{referenced_path}", 3)
    bundle_hash = sha256_bytes(canonical_bytes(entries))
    return entries, bundle_hash, lineage_id


def registry_rows(
    path: Path | None = None, *, selected_sequence_id: str | None = None
) -> tuple[list[dict[str, Any]], str]:
    selected = path or REGISTRY
    if REGISTRY_GOVERNANCE_LEVEL == "UNGOVERNED_DIAGNOSTIC":
        return prevention_registry.legacy_fixture_rows(
            selected, governance_level=REGISTRY_GOVERNANCE_LEVEL
        )
    return prevention_registry.registry_rows(
        selected, selected_sequence_id=selected_sequence_id
    )


def receipt_path(task_id: str, name: str) -> Path:
    require_id(task_id, "task-id")
    return RECEIPT_ROOT / task_id / f"{name}.json"


@contextmanager
def _task_receipt_lock(task_id: str):
    require_id(task_id, "task-id")
    lock = RECEIPT_ROOT / task_id / ".writer-receipts.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def write_receipt(task_id: str, name: str, payload: dict[str, Any]) -> tuple[Path, str]:
    path = receipt_path(task_id, name)
    data = canonical_bytes(payload)
    with _task_receipt_lock(task_id):
        validate_ownership_receipt(task_id, payload)
        _atomic_write(path, data)
    return path, sha256_bytes(data)


def load_receipt(task_id: str, name: str, *, require_fresh: bool = True) -> tuple[dict[str, Any], str, Path]:
    path = receipt_path(task_id, name)
    if not path.is_file():
        raise WorkMemoryError(f"missing-{name}-receipt", 4)
    data = path.read_bytes()
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise WorkMemoryError(f"invalid-{name}-receipt", 4) from exc
    if payload.get("task_id") != task_id:
        raise WorkMemoryError("receipt-task-mismatch", 4)
    if require_fresh and parse_utc(payload["expires_at_utc"]) <= datetime.now(UTC):
        raise WorkMemoryError("expired-receipt", 4)
    return payload, sha256_bytes(data), path


def _canonical_ownership_events() -> list[dict[str, Any]]:
    raw = LEDGER.read_bytes() if LEDGER.is_file() else b""
    return parse_ledger_bytes(raw)


def task_writer_state(task_id: str) -> dict[str, Any] | None:
    require_id(task_id, "task-id")
    tasks, _ = _ownership_snapshot(_canonical_ownership_events())
    return tasks.get(task_id)


def require_task_writer(task_id: str) -> dict[str, Any]:
    identity = writer_identity()
    state = task_writer_state(task_id)
    if state is None:
        raise WorkMemoryError("task-writer-unclaimed", 4)
    if state["writer_thread_id"] != identity["writer_id"]:
        raise WorkMemoryError("task-writer-not-owner", 4)
    return state


def _identity_claim_event(task_id: str, identity: dict[str, Any]) -> dict[str, Any]:
    if identity["schema_version"] == 2:
        event = _event(
            "task_writer_claimed", task_id=task_id, writer_id=identity["writer_id"],
            writer_client_kind=identity["writer_client_kind"],
            writer_session_id=identity["writer_session_id"], ownership_generation=1,
        )
        event["schema_version"] = 2
        return event
    return _event(
        "task_writer_claimed", task_id=task_id, writer_thread_id=identity["writer_id"],
        ownership_generation=1,
    )


def _identity_claim_state(identity: dict[str, Any], event_id: str) -> dict[str, Any]:
    state = {
        "writer_thread_id": identity["writer_id"],
        "ownership_generation": 1,
        "ownership_event_id": event_id,
    }
    if identity["schema_version"] == 2:
        state.update({
            "schema_version": 2,
            "writer_client_kind": identity["writer_client_kind"],
            "writer_session_id": identity["writer_session_id"],
        })
    return state


def _claim_task_writer(task_id: str) -> dict[str, Any]:
    identity = writer_identity()
    state = task_writer_state(task_id)
    if state is not None:
        if state["writer_thread_id"] != identity["writer_id"]:
            raise WorkMemoryError("task-writer-not-owner", 4)
        return state
    event = _identity_claim_event(task_id, identity)
    try:
        transact({
            "schema_version": 1, "expected_ledger_hash": None, "events": [event],
        })
    except WorkMemoryError as exc:
        if exc.code != "task-writer-already-claimed":
            raise
        raced = task_writer_state(task_id)
        if raced is None or raced["writer_thread_id"] != identity["writer_id"]:
            raise WorkMemoryError("task-writer-not-owner", 4) from exc
        return raced
    return _identity_claim_state(identity, event["event_id"])


def validate_ownership_receipt(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    state = require_task_writer(task_id)
    expected = _ownership_receipt_fields(task_id, state)
    if any(payload.get(key) != value for key, value in expected.items()):
        raise WorkMemoryError("stale-task-writer-receipt", 4)
    return state


def validate_run_writer_continuity(
    events: list[dict[str, Any]], task_id: str, run_id: str,
    start: dict[str, Any], ownership_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Prove a run still belongs to the task whose current owner holds the receipts."""
    tasks, run_tasks = _ownership_snapshot(events)
    state = tasks.get(task_id)
    if state is None or run_tasks.get(run_id) != task_id:
        raise WorkMemoryError("run-writer-continuity-mismatch", 4)
    expected_ownership = _ownership_receipt_fields(task_id, state)
    if any(
        ownership_receipt.get(key) != value
        for key, value in expected_ownership.items()
    ):
        raise WorkMemoryError("run-writer-continuity-mismatch", 4)
    if start.get("task_id") == task_id:
        return start
    binding = next((
        event for event in events
        if event["event_type"] == "legacy_run_writer_bound"
        and event["task_id"] == task_id
        and event["run_id"] == run_id
    ), None)
    if binding is None:
        raise WorkMemoryError("legacy-run-writer-binding-mismatch", 4)
    if (
        binding["classification_receipt_hash"]
        != start.get("classification_receipt_hash")
        or binding["selection_receipt_hash"]
        != start.get("selection_receipt_hash")
    ):
        raise WorkMemoryError("legacy-run-writer-binding-mismatch", 4)
    return binding


def validate_legacy_run_binding(
    events: list[dict[str, Any]], task_id: str, run_id: str,
    start: dict[str, Any], ownership_receipt: dict[str, Any],
) -> dict[str, Any]:
    binding = validate_run_writer_continuity(
        events, task_id, run_id, start, ownership_receipt,
    )
    if binding.get("event_type") != "legacy_run_writer_bound":
        raise WorkMemoryError("legacy-run-writer-binding-mismatch", 4)
    return binding


def cmd_classify(args: argparse.Namespace) -> dict[str, Any]:
    if args.operation_kind not in OPERATION_KINDS or args.meaningful_steps < 0:
        raise WorkMemoryError("invalid-classification-input", 2)
    state = _claim_task_writer(args.task_id)
    repeatable = args.repeatable == "yes"
    operational = (
        args.operation_kind in ALWAYS_OPERATIONAL
        or (args.operation_kind in CONDITIONAL_OPERATIONAL and (repeatable or args.meaningful_steps >= 3))
        or (args.operation_kind in NON_OPERATIONAL and (repeatable or args.meaningful_steps >= 3))
    )
    now = datetime.now(UTC).replace(microsecond=0)
    payload = {
        "schema_version": 1, "task_id": args.task_id, "operation_kind": args.operation_kind,
        "repeatable": repeatable, "meaningful_steps": args.meaningful_steps,
        "verdict": "operational" if operational else "non-operational",
        "reason": "repeatable-or-multistep" if operational else "bounded-non-operational",
        **_ownership_receipt_fields(args.task_id, state),
        "created_at_utc": now.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (now + timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
    }
    path, digest = write_receipt(args.task_id, "classification", payload)
    return {**payload, "classification_path": str(path), "classification_receipt_hash": digest}


def _preserved_artifact_effective_hashes(
    preserved: dict[str, Any], target: dict[str, Any],
    *, bundle_paths: set[tuple[str, str]], roots: dict[str, Path],
) -> dict[tuple[str, str], str]:
    target_hashes = {
        _artifact_identity(artifact): artifact_hash
        for artifact, artifact_hash in zip(
            target["changed_artifacts"], target["changed_artifact_hashes"], strict=True,
        )
    }
    effective: dict[tuple[str, str], str] = {}
    for artifact, preserved_hash in zip(
        preserved["changed_artifacts"], preserved["changed_artifact_hashes"], strict=True,
    ):
        artifact_key = _artifact_identity(artifact)
        if artifact_key not in bundle_paths:
            raise WorkMemoryError("preserved-correction-artifact-outside-bundle", 3)
        repository_key, relative = artifact_key
        if repository_key not in roots:
            raise WorkMemoryError("missing-repository-root", 3)
        current_hash = sha256_bytes(
            _safe_file(roots[repository_key], relative).read_bytes()
        )
        if current_hash == preserved_hash:
            effective[artifact_key] = preserved_hash
            continue
        target_hash = target_hashes.get(artifact_key)
        if target_hash is None:
            raise WorkMemoryError("preservation-overwrite-not-declared", 3)
        if current_hash != target_hash:
            raise WorkMemoryError("preservation-target-artifact-hash-mismatch", 3)
        effective[artifact_key] = target_hash
    return effective


def _pre_run_correction_bridges_selected_bundle(
    events: list[dict[str, Any]],
    predecessor: dict[str, Any],
    source_bundle: list[dict[str, str]],
) -> bool:
    task_id = predecessor.get("task_id")
    if not isinstance(task_id, str):
        return False
    task_states, _ = _ownership_snapshot(events)
    task_state = task_states.get(task_id)
    if task_state is None:
        return False

    blocker_states: dict[str, str] = {}
    for event in events:
        blocker_id = event.get("blocker_id")
        if (
            event["event_type"] == "pre_run_blocker_opened"
            and event.get("task_id") == task_id
        ):
            blocker_states[blocker_id] = "open"
        elif (
            event["event_type"] == "pre_run_blocker_transitioned"
            and blocker_id in blocker_states
        ):
            blocker_states[blocker_id] = event["to_status"]

    correction_rows = [
        event
        for event in events
        if event["event_type"] == "pre_run_correction_recorded"
        and event.get("task_id") == task_id
        and event.get("ownership_event_id")
        == task_state["ownership_event_id"]
    ]
    superseded = {
        correction_id
        for event in correction_rows
        for correction_id in _superseded_correction_ids(event)
    }
    active_rows = [
        event
        for event in correction_rows
        if event["correction_id"] not in superseded
        and blocker_states.get(event["blocker_id"])
        in {"fixed-awaiting-verification", "verified", "closed"}
    ]
    if not active_rows:
        return False

    related = [
        event
        for event in events
        if event.get("run_id") == predecessor["run_id"]
    ]
    try:
        prior_bundle, prior_hash, _ = _effective_correction_bundle(
            predecessor,
            related,
        )
    except WorkMemoryError:
        return False
    prior_map = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in prior_bundle
    }
    current_map = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in source_bundle
    }
    drifted = {
        key
        for key in prior_map.keys() | current_map.keys()
        if prior_map.get(key) != current_map.get(key)
    }
    corrected: dict[tuple[str, str], str] = {}
    for correction in active_rows:
        for artifact, artifact_hash in zip(
            correction["changed_artifacts"],
            correction["changed_artifact_hashes"],
            strict=True,
        ):
            key = _artifact_identity(artifact)
            if key in drifted:
                corrected[key] = artifact_hash
    return (
        bool(drifted)
        and drifted == set(corrected)
        and all(current_map.get(key) == value for key, value in corrected.items())
        and any(
            event["event_type"] == "bundle_transition_recorded"
            and event.get("run_id") == predecessor["run_id"]
            and event.get("new_bundle_hash") == prior_hash
            for event in related
        )
    )


def _validate_successor_corrections(
    events: list[dict[str, Any]], *, lineage_id: str, source_bundle: list[dict[str, str]],
    predecessor_run_id: str, correction_ids: Sequence[str], repo_roots_file: str | None = None,
    repository_roots: dict[str, str] | None = None,
    source_bundle_hash: str | None = None,
) -> None:
    if len(set(correction_ids)) != len(correction_ids):
        raise WorkMemoryError("duplicate-successor-correction", 2)

    predecessor = next((
        event for event in events
        if event["event_type"] == "run_started" and event["run_id"] == predecessor_run_id
    ), None)
    if predecessor is None:
        raise WorkMemoryError("successor-predecessor-not-found", 3)
    if predecessor["lineage_id"] != lineage_id:
        raise WorkMemoryError("successor-predecessor-lineage-mismatch", 3)
    if not any(
        event["event_type"] in {"run_closed", "run_abandoned"}
        and event.get("run_id") == predecessor_run_id
        for event in events
    ):
        raise WorkMemoryError("successor-predecessor-not-terminal", 3)

    blocker_states: dict[str, str] = {}
    current_occurrences: dict[str, str] = {}
    for event in events:
        blocker_id = event.get("blocker_id")
        if (
            event["event_type"] in {"blocker_opened", "pre_run_blocker_opened"}
            and event["lineage_id"] == lineage_id
        ):
            blocker_states[blocker_id] = "open"
            current_occurrences[blocker_id] = event["occurrence_id"]
        elif event["event_type"] == "blocker_recurred" and blocker_id in blocker_states:
            blocker_states[blocker_id] = "open"
            current_occurrences[blocker_id] = event["occurrence_id"]
        elif event["event_type"] in {"blocker_transitioned", "pre_run_blocker_transitioned"} and blocker_id in blocker_states:
            blocker_states[blocker_id] = event["to_status"]

    correction_rows = [
        event for event in events
        if event["event_type"] == "correction_recorded" and event["lineage_id"] == lineage_id
    ]
    superseded = {
        correction_id
        for event in correction_rows
        for correction_id in _superseded_correction_ids(event)
    }
    active = {
        event["correction_id"]: event
        for event in correction_rows if event["correction_id"] not in superseded
    }
    bundle_paths = {
        (item["repository_key"], item["path"])
        for item in source_bundle
    }
    bundle_hashes = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in source_bundle
    }
    predecessor_bundle_paths = {
        (item["repository_key"], item["path"])
        for item in predecessor["source_bundle"]
    }
    roots = _repo_roots(repo_roots_file, snapshot=repository_roots)
    effective_bundle_hash = source_bundle_hash or sha256_bytes(canonical_bytes(source_bundle))
    correction_transitions = [
        event
        for event in events
        if event["event_type"] == "bundle_transition_recorded"
        and event.get("transition_reason") == "correction"
    ]
    transition_hashes = {
        correction_id: event["new_bundle_hash"]
        for event in correction_transitions
        for correction_id in event.get("correction_ids", [])
    }
    predecessor_transitions = [
        event
        for event in correction_transitions
        if event.get("run_id") == predecessor_run_id
    ]
    pre_run_bridge = _pre_run_correction_bridges_selected_bundle(
        events,
        predecessor,
        source_bundle,
    )
    if (
        predecessor_transitions
        and (
            predecessor_transitions[-1]["new_bundle_hash"]
            == effective_bundle_hash
            or pre_run_bridge
        )
    ):
        effective_transition_ids = [
            *predecessor.get("verifies_correction_ids", []),
            *predecessor_transitions[-1].get("correction_ids", []),
        ]
        for correction_id in dict.fromkeys(effective_transition_ids):
            transition_hashes[correction_id] = effective_bundle_hash
    preservation_records = _validate_correction_preservation_records(events)

    def raw_artifact_matches(artifact: Any, expected_hash: str) -> bool:
        repository_key, relative = _artifact_identity(artifact)
        if repository_key not in roots:
            return False
        try:
            raw_hash = sha256_bytes(_safe_file(roots[repository_key], relative).read_bytes())
        except WorkMemoryError:
            return False
        return raw_hash == expected_hash

    for correction_id in correction_ids:
        correction = active.get(correction_id)
        if correction is None:
            raise WorkMemoryError("successor-correction-not-active", 3)
        effective_artifact_hashes = {
            _artifact_identity(artifact): expected_hash
            for artifact, expected_hash in zip(
                correction["changed_artifacts"],
                correction["changed_artifact_hashes"], strict=True,
            )
        }
        transition_matches_effective_bundle = (
            transition_hashes.get(correction_id) == effective_bundle_hash
        )
        if transition_matches_effective_bundle:
            effective_artifact_hashes = {
                artifact_key: bundle_hashes.get(
                    artifact_key,
                    expected_hash,
                )
                for artifact_key, expected_hash
                in effective_artifact_hashes.items()
            }
        if not transition_matches_effective_bundle:
            preservation = preservation_records.get(correction_id)
            if preservation is not None:
                target_id = preservation["target_correction_id"]
                target = active.get(target_id)
                if (
                    target is None
                    or target_id in correction_ids
                    or preservation["target_bundle_hash"] != effective_bundle_hash
                    or transition_hashes.get(target_id) != effective_bundle_hash
                ):
                    raise WorkMemoryError("successor-correction-preservation-mismatch", 3)
                effective_artifact_hashes = _preserved_artifact_effective_hashes(
                    correction, target, bundle_paths=bundle_paths, roots=roots,
                )
            else:
                # Corrections seal raw artifact bytes. Discovery documents may use a
                # semantic hash in the source bundle, so require membership there
                # and compare the correction hash against the file itself.
                current_artifacts_match = all(
                    _artifact_identity(artifact) in bundle_paths
                    and raw_artifact_matches(artifact, expected_hash)
                    for artifact, expected_hash in zip(
                        correction["changed_artifacts"],
                        correction["changed_artifact_hashes"],
                        strict=True,
                    )
                )
                if not current_artifacts_match:
                    raise WorkMemoryError("successor-correction-bundle-mismatch", 3)
        blocker_id = correction["blocker_id"]
        if blocker_states.get(blocker_id) != "fixed-awaiting-verification":
            raise WorkMemoryError("successor-correction-not-awaiting-verification", 3)
        if correction["occurrence_id"] != current_occurrences.get(blocker_id):
            raise WorkMemoryError("successor-correction-occurrence-mismatch", 3)
        for artifact, expected_hash in zip(
            correction["changed_artifacts"], correction["changed_artifact_hashes"], strict=True,
        ):
            repository_key, relative = _artifact_identity(artifact)
            artifact_key = (repository_key, relative)
            if artifact_key not in bundle_paths:
                if artifact_key not in predecessor_bundle_paths:
                    raise WorkMemoryError("successor-correction-artifact-outside-bundle", 3)
                if transition_matches_effective_bundle:
                    continue
            if repository_key not in roots:
                raise WorkMemoryError("missing-repository-root", 3)
            raw_hash = sha256_bytes(_safe_file(roots[repository_key], relative).read_bytes())
            effective_expected_hash = effective_artifact_hashes[artifact_key]
            if raw_hash != effective_expected_hash:
                raise WorkMemoryError("successor-correction-artifact-hash-mismatch", 3)


def _require_predecessor_task_ownership(
    events: Sequence[dict[str, Any]], predecessor_run_id: str, task_id: str,
) -> None:
    _, run_tasks = _ownership_snapshot(events)
    predecessor_task_id = run_tasks.get(predecessor_run_id)
    if predecessor_task_id is None:
        raise WorkMemoryError("predecessor-run-writer-binding-required", 4)
    if predecessor_task_id != task_id:
        raise WorkMemoryError("cross-task-successor-selection", 4)


def _successor_selection_request(
    events: Sequence[dict[str, Any]], predecessor_run_id: str,
) -> dict[str, Any]:
    """Derive every successor identity from the closed corrected predecessor."""

    starts = [
        event for event in events
        if event["event_type"] == "run_started"
        and event["run_id"] == predecessor_run_id
    ]
    if len(starts) != 1:
        raise WorkMemoryError("successor-predecessor-not-found", 3)
    start = starts[0]
    mode = start.get("mode")
    if mode not in {"registered", "discovery"}:
        raise WorkMemoryError("successor-predecessor-mode-invalid", 3)
    terminal = [
        event for event in events
        if event.get("run_id") == predecessor_run_id
        and event["event_type"] in {"run_closed", "run_abandoned"}
    ]
    if (
        len(terminal) != 1
        or terminal[0]["event_type"] != "run_closed"
        or terminal[0].get("result") != "failed"
    ):
        raise WorkMemoryError("successor-predecessor-not-terminal", 3)
    lineage_id = start.get("lineage_id")
    predecessor_transitions = [
        event for event in events
        if event["event_type"] == "bundle_transition_recorded"
        and event.get("transition_reason") == "correction"
        and event.get("run_id") == predecessor_run_id
    ]
    if predecessor_transitions:
        source_transition = predecessor_transitions[-1]
    else:
        inherited_transitions = [
            event for event in events
            if event["event_type"] == "bundle_transition_recorded"
            and event.get("transition_reason") == "correction"
            and event.get("lineage_id") == lineage_id
            and event.get("new_bundle_hash") == start.get("source_bundle_hash")
        ]
        if not inherited_transitions:
            raise WorkMemoryError("successor-correction-not-found", 3)
        source_transition = inherited_transitions[-1]
    transition_ids = source_transition.get("correction_ids")
    if (
        not isinstance(transition_ids, list)
        or not transition_ids
        or len(transition_ids) != len(set(transition_ids))
    ):
        raise WorkMemoryError("successor-correction-set-invalid", 3)
    inherited_ids = start.get("verifies_correction_ids", [])
    if (
        not isinstance(inherited_ids, list)
        or len(inherited_ids) != len(set(inherited_ids))
        or any(not isinstance(item, str) for item in inherited_ids)
    ):
        raise WorkMemoryError("successor-correction-set-invalid", 3)
    cumulative_ids = list(dict.fromkeys([*inherited_ids, *transition_ids]))
    correction_rows = [
        event
        for event in events
        if event["event_type"] == "correction_recorded"
        and event.get("lineage_id") == lineage_id
        and isinstance(event.get("correction_id"), str)
    ]
    superseded = {
        correction_id
        for correction in correction_rows
        for correction_id in _superseded_correction_ids(correction)
    }
    blocker_states: dict[str, str] = {}
    blocker_occurrences: dict[str, str] = {}
    for event in events:
        blocker_id = event.get("blocker_id")
        if not isinstance(blocker_id, str):
            continue
        if (
            event["event_type"] in {
                "blocker_opened", "pre_run_blocker_opened",
            }
            and event.get("lineage_id") == lineage_id
        ):
            blocker_states[blocker_id] = "open"
            blocker_occurrences[blocker_id] = event["occurrence_id"]
        elif (
            event["event_type"] == "blocker_recurred"
            and blocker_id in blocker_states
        ):
            blocker_states[blocker_id] = "open"
            blocker_occurrences[blocker_id] = event["occurrence_id"]
        elif (
            event["event_type"] in {
                "blocker_transitioned", "pre_run_blocker_transitioned",
            }
            and blocker_id in blocker_states
        ):
            blocker_states[blocker_id] = event["to_status"]
    correction_by_id = {
        correction["correction_id"]: correction
        for correction in correction_rows
    }
    candidate_ids = [
        correction_id for correction_id in cumulative_ids
        if correction_id not in superseded
    ]
    if not candidate_ids or any(
        correction_id not in correction_by_id for correction_id in candidate_ids
    ):
        raise WorkMemoryError("successor-correction-set-invalid", 3)
    active_ids: list[str] = []
    for correction_id in candidate_ids:
        correction = correction_by_id[correction_id]
        blocker_state = blocker_states.get(correction["blocker_id"])
        if blocker_state in {"verified", "closed"}:
            continue
        if blocker_state != "fixed-awaiting-verification":
            raise WorkMemoryError(
                "successor-correction-not-awaiting-verification", 3,
            )
        if (
            blocker_occurrences.get(correction["blocker_id"])
            != correction["occurrence_id"]
        ):
            raise WorkMemoryError(
                "successor-correction-occurrence-mismatch", 3,
            )
        active_ids.append(correction_id)
    if not active_ids:
        raise WorkMemoryError(
            "successor-correction-not-awaiting-verification", 3,
        )
    task_id = start.get("task_id")
    subject_id = start.get("subject_id")
    repository_roots = start.get("repository_roots")
    if (
        not isinstance(task_id, str)
        or not task_id
        or not isinstance(subject_id, str)
        or not subject_id
        or not isinstance(repository_roots, dict)
    ):
        raise WorkMemoryError("successor-predecessor-identity-invalid", 3)
    discovery_log: str | None = None
    sequence_id: str | None = subject_id
    if mode == "discovery":
        sequence_id = None
        candidates: list[Path] = []
        for artifact in start.get("source_bundle", []):
            if not isinstance(artifact, dict):
                continue
            repository_key = artifact.get("repository_key")
            relative = artifact.get("path")
            if (
                not isinstance(repository_key, str)
                or repository_key not in repository_roots
                or not isinstance(relative, str)
                or not relative.endswith(".md")
            ):
                continue
            document = _safe_file(
                Path(repository_roots[repository_key]), relative,
            )
            match = re.search(
                r"^DiscoveryId:\s*(\S+)\s*$", document.read_text(), re.M,
            )
            if match and match.group(1) == subject_id:
                candidates.append(document.resolve())
        if len(candidates) != 1:
            raise WorkMemoryError(
                "successor-discovery-document-invalid", 3,
            )
        discovery_log = str(candidates[0])
    return {
        "task_id": task_id,
        "sequence_id": sequence_id,
        "discovery_log": discovery_log,
        "verification_successor_of": predecessor_run_id,
        "verifies_correction_ids": active_ids,
        "repository_roots": repository_roots,
    }


def cmd_select(args: argparse.Namespace) -> dict[str, Any]:
    predecessor_run_id = getattr(args, "verification_successor_of", None)
    if not predecessor_run_id:
        return _cmd_select_for_task(args)
    events, _ = load_ledger()
    request = _successor_selection_request(events, predecessor_run_id)
    requested_task_id = getattr(args, "task_id", None)
    requested_sequence_id = getattr(args, "sequence_id", None)
    requested_discovery_log = getattr(args, "discovery_log", None)
    requested_corrections = list(
        getattr(args, "verifies_correction_id", None) or []
    )
    if (
        requested_sequence_id is not None
        and requested_sequence_id != request["sequence_id"]
    ):
        raise WorkMemoryError("successor-sequence-input-mismatch", 3)
    if (
        requested_discovery_log is not None
        and str(Path(requested_discovery_log).resolve())
        != request["discovery_log"]
    ):
        raise WorkMemoryError("successor-discovery-input-mismatch", 3)
    if (
        requested_corrections
        and requested_corrections != request["verifies_correction_ids"]
    ):
        raise WorkMemoryError("successor-correction-input-mismatch", 3)
    forwarded = argparse.Namespace(**vars(args))
    forwarded.task_id = request["task_id"]
    forwarded.sequence_id = request["sequence_id"]
    forwarded.discovery_log = request["discovery_log"]
    forwarded.fingerprint = None
    forwarded.verification_successor_of = predecessor_run_id
    forwarded.verifies_correction_id = request["verifies_correction_ids"]
    forwarded.repo_roots_file = None
    forwarded.repository_roots = request["repository_roots"]
    result = _cmd_select_for_task(forwarded)
    return {
        **result,
        "requested_task_id": requested_task_id,
        "task_identity_source": "predecessor-run",
    }


def cmd_select_successor(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    request = _successor_selection_request(
        events, args.predecessor_run_id,
    )
    result = _cmd_select_for_task(argparse.Namespace(
        task_id=request["task_id"],
        sequence_id=request["sequence_id"],
        discovery_log=request["discovery_log"],
        fingerprint=None,
        verification_successor_of=args.predecessor_run_id,
        verifies_correction_id=request["verifies_correction_ids"],
        repo_roots_file=None,
        repository_roots=request["repository_roots"],
    ))
    return {
        **result,
        "requested_task_id": None,
        "task_identity_source": "predecessor-run",
    }


def _cmd_select_for_task(args: argparse.Namespace) -> dict[str, Any]:
    classification, class_hash, _ = load_receipt(args.task_id, "classification")
    state = validate_ownership_receipt(args.task_id, classification)
    if classification["verdict"] != "operational":
        raise WorkMemoryError("classification-is-not-operational", 4)
    if args.sequence_id and args.discovery_log:
        raise WorkMemoryError("selection-source-conflict", 2)
    if args.discovery_log:
        # An explicitly selected discovery bundle is the remediation boundary
        # for stale or broken registered artifacts.  Loading the registered
        # owner registry here creates a deadlock: registry repair cannot start
        # because the stale registry prevents selecting its discovery run.
        rows: list[dict[str, str]] = []
        registry_hash = sha256_bytes(canonical_bytes(rows))
    else:
        rows, registry_hash = registry_rows(
            selected_sequence_id=args.sequence_id
        )
    events, ledger_hash = load_ledger()
    candidates = [row for row in rows if classification["operation_kind"] in row["operation_kinds"].split(",")]
    fingerprint_row = None
    fingerprint_link: tuple[str, int, str, str] | None = None
    if args.fingerprint and not args.sequence_id and not args.discovery_log:
        opened = {
            event["blocker_id"]: event for event in events
            if event["event_type"] in {"blocker_opened", "pre_run_blocker_opened"}
            and event["fingerprint"] == args.fingerprint
        }
        states = {blocker_id: "open" for blocker_id in opened}
        verified_at: dict[str, str] = {}
        for event in events:
            blocker_id = event.get("blocker_id")
            if blocker_id not in opened:
                continue
            if event["event_type"] == "blocker_recurred":
                states[blocker_id] = "open"
            elif event["event_type"] in {"blocker_transitioned", "pre_run_blocker_transitioned"}:
                states[blocker_id] = event["to_status"]
                if event["to_status"] in {"verified", "closed"}:
                    verified_at[blocker_id] = event["recorded_at_utc"]
        successful_runs = Counter(
            event["subject_id"] for event in events
            if event["event_type"] == "run_closed" and event["result"] == "passed"
        )
        linked = [
            (verified_at.get(blocker_id, "1970-01-01T00:00:00Z"),
             successful_runs[opened[blocker_id]["subject_id"]],
             opened[blocker_id]["subject_id"], blocker_id)
            for blocker_id, status in states.items() if status in {"verified", "closed"}
        ]
        linked.sort(key=lambda item: (
            -parse_utc(item[0]).timestamp(), -item[1], item[2], item[3]
        ))
        if linked:
            fingerprint_link = linked[0]
            fingerprint_row = next(
                (row for row in rows if row["sequence_id"] == fingerprint_link[2]), None
            )
            if fingerprint_row is None:
                raise WorkMemoryError("fingerprint-linked-sequence-missing", 4)
    explicit = False
    if args.discovery_log:
        document = Path(args.discovery_log).resolve()
        mode = "discovery"
        match = re.search(r"^DiscoveryId:\s*(\S+)\s*$", document.read_text(), re.M)
        if not match:
            raise WorkMemoryError("discovery-id-missing", 3)
        subject_id = match.group(1)
        manifest = document.with_suffix(".dependencies.json")
    else:
        if args.sequence_id:
            matching = [row for row in candidates if row["sequence_id"] == args.sequence_id]
            if not matching:
                raise WorkMemoryError("sequence-not-valid-for-operation", 3)
            row, explicit = matching[0], True
        elif fingerprint_row is not None:
            row = fingerprint_row
        elif len(candidates) == 1:
            row = candidates[0]
        elif not candidates:
            raise WorkMemoryError("discovery-required", 3)
        else:
            raise WorkMemoryError("ambiguous-sequence:" + ",".join(sorted(r["sequence_id"] for r in candidates)), 3)
        subject_id, mode = row["sequence_id"], "registered"
        document = ROOT / row["folder"] / "sequence.md"
        manifest = document.with_name("dependencies.json")
    repository_roots = getattr(args, "repository_roots", None)
    bundle, bundle_hash, lineage = resolve_bundle(
        mode=mode, subject_id=subject_id, document=document, manifest=manifest,
        repo_roots_file=args.repo_roots_file, repository_roots=repository_roots,
        include_bootstrap_trust_anchors=True,
    )
    if mode == "registered" and row["lineage_id"] != lineage:
        raise WorkMemoryError("registry-manifest-lineage-mismatch", 3)
    if fingerprint_row is not None:
        starts = {
            event["run_id"]: event for event in events
            if event["event_type"] == "run_started"
            and event["subject_id"] == subject_id
            and event["source_bundle_hash"] == bundle_hash
        }
        verified_runs = {
            event["run_id"] for event in events
            if event["event_type"] == "verification_recorded"
            and event["run_id"] in starts and event["outcome"] == "passed"
            and event["quality"] == "same-path"
            and event["source_bundle_hash"] == bundle_hash
        }
        current_success = any(
            event["event_type"] == "run_closed" and event["run_id"] in verified_runs
            and event["result"] == "passed"
            for event in events
        )
        if not current_success:
            raise WorkMemoryError("fingerprint-linked-sequence-stale", 4)
    opened = {
        event["blocker_id"]: event for event in events
        if event["event_type"] in {"blocker_opened", "pre_run_blocker_opened"}
        and event["lineage_id"] == lineage
        and (not args.fingerprint or event["fingerprint"] == args.fingerprint)
    }
    blocker_states = {blocker_id: "open" for blocker_id in opened}
    for event in events:
        blocker_id = event.get("blocker_id")
        if blocker_id not in opened:
            continue
        if event["event_type"] == "blocker_recurred":
            blocker_states[blocker_id] = "open"
        elif event["event_type"] in {"blocker_transitioned", "pre_run_blocker_transitioned"}:
            blocker_states[blocker_id] = event["to_status"]
    correction_rows = [
        event for event in events if event["event_type"] == "correction_recorded"
        and event["lineage_id"] == lineage and event["blocker_id"] in opened
    ]
    superseded = {
        correction_id
        for event in correction_rows
        for correction_id in _superseded_correction_ids(event)
    }
    latest = {
        event["correction_id"]: event for event in correction_rows
        if event["correction_id"] not in superseded
    }
    eligible: list[dict[str, Any]] = []
    for verification in events:
        if (
            verification["event_type"] != "verification_recorded"
            or verification["outcome"] != "passed" or verification["quality"] != "same-path"
            or verification["source_bundle_hash"] != bundle_hash
        ):
            continue
        for correction_id in verification["correction_ids"]:
            correction = latest.get(correction_id)
            if correction is None or blocker_states.get(correction["blocker_id"]) not in {"verified", "closed"}:
                continue
            if (
                correction["blocker_id"] not in verification["blocker_ids"]
            ):
                continue
            eligible.append({
                "blocker_id": correction["blocker_id"], "correction_id": correction_id,
                "solution": correction["solution"], "changed_artifacts": correction["changed_artifacts"],
                "verification_event_id": verification["event_id"],
                "verified_at_utc": verification["recorded_at_utc"],
            })
    eligible.sort(key=lambda item: (item["verified_at_utc"], item["blocker_id"]), reverse=True)
    recent_runs = [
        event for event in events if event["event_type"] == "run_started"
        and event["lineage_id"] == lineage
    ]
    recent_runs.sort(key=lambda event: (event["started_at_utc"], event["run_id"]), reverse=True)
    now = datetime.now(UTC).replace(microsecond=0)
    successor_ids = args.verifies_correction_id or []
    if bool(args.verification_successor_of) != bool(successor_ids):
        raise WorkMemoryError("incomplete-successor-selection", 2)
    if args.verification_successor_of:
        _require_predecessor_task_ownership(
            events, args.verification_successor_of, args.task_id,
        )
        _validate_successor_corrections(
            events, lineage_id=lineage, source_bundle=bundle,
            predecessor_run_id=args.verification_successor_of,
            correction_ids=successor_ids,
            repo_roots_file=args.repo_roots_file, repository_roots=repository_roots,
            source_bundle_hash=bundle_hash,
        )
    reason = "successor-verification" if args.verification_successor_of else (
        "fingerprint-link" if fingerprint_row is not None else
        ("explicit-override" if explicit else "operation-kind-match")
    )
    payload = {
        "schema_version": 1, "task_id": args.task_id, "created_at_utc": now.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (now + timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
        "classification_receipt_hash": class_hash, "registry_hash": registry_hash,
        "ledger_hash": ledger_hash, "mode": mode, "subject_id": subject_id, "lineage_id": lineage,
        "document": str(document), "manifest": str(manifest), "source_bundle": bundle,
        "source_bundle_hash": bundle_hash, "selection_reason": reason, "explicit_override": explicit,
        "relevant_blocker_ids": sorted(opened),
        "recent_run_ids": [event["run_id"] for event in recent_runs[:10]],
        "eligible_corrections": eligible,
        "repository_roots_file": args.repo_roots_file,
        "predecessor_run_id": args.verification_successor_of,
        "verifies_correction_ids": list(successor_ids),
        **_ownership_receipt_fields(args.task_id, state),
    }
    if repository_roots is not None:
        payload["repository_roots"] = repository_roots
    path, digest = write_receipt(args.task_id, "selection", payload)
    return {**payload, "selection_path": str(path), "selection_receipt_hash": digest}


def _event(kind: str, event_id: str | None = None, **fields: Any) -> dict[str, Any]:
    return {"schema_version": 1, "event_id": event_id or str(uuid.uuid4()), "event_type": kind,
            "recorded_at_utc": utc_now(), **fields}


def _validate_active_trust_snapshots(
    active: dict[str, Any], selection: dict[str, Any],
    *, allow_legacy_missing_launcher: bool = False,
) -> None:
    if not any(hash_field in active for _, hash_field, _ in ACTIVE_TRUST_SNAPSHOT_FIELDS):
        return
    selected = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in selection.get("source_bundle", [])
    }
    for path, hash_field, snapshot_field in ACTIVE_TRUST_SNAPSHOT_FIELDS:
        expected = selected.get(("memory-knowledge", path))
        if expected is None or active.get(hash_field) != expected:
            raise WorkMemoryError("active-trust-snapshot-hash-mismatch", 4)
        encoded = active.get(snapshot_field)
        if (
            encoded is None
            and allow_legacy_missing_launcher
            and snapshot_field == "sealed_bootstrap_launcher_b64"
        ):
            continue
        try:
            snapshot = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError) as exc:
            raise WorkMemoryError("active-trust-snapshot-invalid", 4) from exc
        if sha256_bytes(snapshot) != expected:
            raise WorkMemoryError("active-trust-snapshot-invalid", 4)


def _handoff_refresh_plan(
    task_id: str, old_state: dict[str, Any], new_state: dict[str, Any],
) -> tuple[dict[str, str], list[tuple[Path, str, bytes]]]:
    ownership = _ownership_receipt_fields(task_id, new_state)
    classification, class_hash, class_path = load_receipt(
        task_id, "classification", require_fresh=False,
    )
    expected_old = _ownership_receipt_fields(task_id, old_state)
    if any(classification.get(key) != value for key, value in expected_old.items()):
        raise WorkMemoryError("stale-task-writer-receipt", 4)
    refreshed_classification = {**classification, **ownership}
    class_bytes = canonical_bytes(refreshed_classification)
    refreshed_class_hash = sha256_bytes(class_bytes)
    metadata = {
        "previous_classification_receipt_hash": class_hash,
        "refreshed_classification_receipt_hash": refreshed_class_hash,
    }
    writes = [(class_path, class_hash, class_bytes)]

    selection_path = receipt_path(task_id, "selection")
    if not selection_path.is_file():
        return metadata, writes
    selection, selection_hash, _ = load_receipt(
        task_id, "selection", require_fresh=False,
    )
    if (
        selection.get("classification_receipt_hash") != class_hash
        or any(selection.get(key) != value for key, value in expected_old.items())
    ):
        raise WorkMemoryError("task-writer-handoff-receipt-chain-mismatch", 4)
    refreshed_selection = {
        **selection, **ownership,
        "classification_receipt_hash": refreshed_class_hash,
    }
    selection_bytes = canonical_bytes(refreshed_selection)
    refreshed_selection_hash = sha256_bytes(selection_bytes)
    metadata.update({
        "previous_selection_receipt_hash": selection_hash,
        "refreshed_selection_receipt_hash": refreshed_selection_hash,
    })
    writes.append((selection_path, selection_hash, selection_bytes))

    active_path = receipt_path(task_id, "active")
    if not active_path.is_file():
        return metadata, writes
    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkMemoryError("invalid-active-state", 4) from exc
    stable_active = {
        "task_id": task_id, "mode": selection["mode"],
        "subject_id": selection["subject_id"], "lineage_id": selection["lineage_id"],
        "document": str(Path(selection["document"]).resolve()),
        "source_bundle_hash": selection["source_bundle_hash"],
        "classification_receipt_hash": class_hash,
        "selection_receipt_hash": selection_hash,
        **expected_old,
    }
    if any(active.get(key) != value for key, value in stable_active.items()):
        raise WorkMemoryError("task-writer-handoff-active-state-mismatch", 4)
    _validate_active_trust_snapshots(active, selection)
    active_bytes_before = canonical_bytes(active)
    refreshed_active = {
        **active, **ownership,
        "classification_receipt_hash": refreshed_class_hash,
        "selection_receipt_hash": refreshed_selection_hash,
    }
    active_bytes = canonical_bytes(refreshed_active)
    metadata.update({
        "previous_active_state_hash": sha256_bytes(active_bytes_before),
        "refreshed_active_state_hash": sha256_bytes(active_bytes),
    })
    writes.append((active_path, sha256_bytes(active_bytes_before), active_bytes))
    return metadata, writes


def _apply_owner_refresh_plan(
    task_id: str, writes: list[tuple[Path, str, bytes]],
) -> None:
    with _task_receipt_lock(task_id):
        states: list[tuple[Path, bytes, bytes]] = []
        for path, expected_hash, data in writes:
            current = path.read_bytes() if path.is_file() else b""
            current_hash = sha256_bytes(current)
            target_hash = sha256_bytes(data)
            if current_hash not in {expected_hash, target_hash}:
                raise WorkMemoryError("task-writer-refresh-cas-mismatch", 4)
            states.append((path, current, data))
        for path, current, data in states:
            if current != data:
                _atomic_write(path, data)


def cmd_task_writer_refresh(args: argparse.Namespace) -> dict[str, Any]:
    state = require_task_writer(args.task_id)
    events = _canonical_ownership_events()
    handoff = next((
        item for item in reversed(events)
        if item["event_type"] == "task_writer_handoff_recorded"
        and item["task_id"] == args.task_id
        and item["event_id"] == state["ownership_event_id"]
    ), None)
    if handoff is None:
        raise WorkMemoryError("task-writer-refresh-handoff-not-found", 4)
    ownership = _ownership_receipt_fields(args.task_id, state)
    writes: list[tuple[Path, str, bytes]] = []

    class_path = receipt_path(args.task_id, "classification")
    class_data = class_path.read_bytes() if class_path.is_file() else b""
    class_hash = sha256_bytes(class_data)
    if class_hash not in {
        handoff.get("previous_classification_receipt_hash"),
        handoff.get("refreshed_classification_receipt_hash"),
    }:
        raise WorkMemoryError("task-writer-refresh-classification-mismatch", 4)
    try:
        classification = json.loads(class_data)
    except json.JSONDecodeError as exc:
        raise WorkMemoryError("invalid-classification-receipt", 4) from exc
    refreshed_classification = {**classification, **ownership}
    class_bytes = canonical_bytes(refreshed_classification)
    refreshed_class_hash = sha256_bytes(class_bytes)
    if refreshed_class_hash != handoff.get("refreshed_classification_receipt_hash"):
        raise WorkMemoryError("task-writer-refresh-classification-mismatch", 4)
    writes.append((class_path, handoff["previous_classification_receipt_hash"], class_bytes))

    if "previous_selection_receipt_hash" in handoff:
        selection_path = receipt_path(args.task_id, "selection")
        selection_data = selection_path.read_bytes() if selection_path.is_file() else b""
        selection_hash = sha256_bytes(selection_data)
        if selection_hash not in {
            handoff["previous_selection_receipt_hash"],
            handoff["refreshed_selection_receipt_hash"],
        }:
            raise WorkMemoryError("task-writer-refresh-selection-mismatch", 4)
        try:
            selection = json.loads(selection_data)
        except json.JSONDecodeError as exc:
            raise WorkMemoryError("invalid-selection-receipt", 4) from exc
        refreshed_selection = {
            **selection, **ownership,
            "classification_receipt_hash": refreshed_class_hash,
        }
        selection_bytes = canonical_bytes(refreshed_selection)
        refreshed_selection_hash = sha256_bytes(selection_bytes)
        if refreshed_selection_hash != handoff["refreshed_selection_receipt_hash"]:
            raise WorkMemoryError("task-writer-refresh-selection-mismatch", 4)
        writes.append((
            selection_path, handoff["previous_selection_receipt_hash"], selection_bytes,
        ))

        if "previous_active_state_hash" in handoff:
            active_path = receipt_path(args.task_id, "active")
            active_data = active_path.read_bytes() if active_path.is_file() else b""
            active_hash = sha256_bytes(active_data)
            if active_hash not in {
                handoff["previous_active_state_hash"],
                handoff["refreshed_active_state_hash"],
            }:
                raise WorkMemoryError("task-writer-refresh-active-state-mismatch", 4)
            try:
                active = json.loads(active_data)
            except json.JSONDecodeError as exc:
                raise WorkMemoryError("invalid-active-state", 4) from exc
            _validate_active_trust_snapshots(active, selection)
            refreshed_active = {
                **active, **ownership,
                "classification_receipt_hash": refreshed_class_hash,
                "selection_receipt_hash": refreshed_selection_hash,
            }
            active_bytes = canonical_bytes(refreshed_active)
            if sha256_bytes(active_bytes) != handoff["refreshed_active_state_hash"]:
                raise WorkMemoryError("task-writer-refresh-active-state-mismatch", 4)
            writes.append((
                active_path, handoff["previous_active_state_hash"], active_bytes,
            ))
    _apply_owner_refresh_plan(args.task_id, writes)
    return {"ok": True, "task_id": args.task_id, **ownership}


def cmd_task_writer_handoff(args: argparse.Namespace) -> dict[str, Any]:
    identity = writer_identity()
    to_client_kind = getattr(args, "to_client_kind", None)
    if to_client_kind is None and not args.to_thread_id:
        raise WorkMemoryError("invalid-to-writer-thread-id", 2)
    state = require_task_writer(args.task_id)
    event_id = args.event_id or str(uuid.uuid4())
    if to_client_kind is not None:
        if to_client_kind not in CLIENT_KINDS:
            raise WorkMemoryError("invalid-writer-client-kind", 2)
        to_session_id = require_uuid(
            getattr(args, "to_session_id", None), "to-writer-session-id",
        )
        target_writer_id = str(uuid.uuid5(WRITER_ID_NAMESPACE, f"{to_client_kind}:{to_session_id}"))
        new_state = {
            "schema_version": 2,
            "writer_thread_id": target_writer_id,
            "writer_client_kind": to_client_kind,
            "writer_session_id": to_session_id,
            "ownership_generation": state["ownership_generation"] + 1,
            "ownership_event_id": event_id,
        }
    else:
        target_thread_id = require_uuid(args.to_thread_id, "to-writer-thread-id")
        if target_thread_id != args.to_thread_id:
            raise WorkMemoryError("invalid-to-writer-thread-id", 2)
        new_state = {
            "writer_thread_id": target_thread_id,
            "ownership_generation": state["ownership_generation"] + 1,
            "ownership_event_id": event_id,
        }
    refresh_metadata, refresh_writes = _handoff_refresh_plan(
        args.task_id, state, new_state,
    )
    if to_client_kind is not None:
        event = _event(
            "task_writer_handoff_recorded", event_id,
            task_id=args.task_id,
            from_writer_id=identity["writer_id"],
            to_writer_id=new_state["writer_thread_id"],
            to_writer_client_kind=new_state["writer_client_kind"],
            to_writer_session_id=new_state["writer_session_id"],
            ownership_generation=new_state["ownership_generation"],
            previous_ownership_event_id=state["ownership_event_id"],
            **refresh_metadata,
        )
        event["schema_version"] = 2
    else:
        event = _event(
            "task_writer_handoff_recorded", event_id,
            task_id=args.task_id,
            from_writer_thread_id=identity["writer_id"],
            to_writer_thread_id=new_state["writer_thread_id"],
            ownership_generation=new_state["ownership_generation"],
            previous_ownership_event_id=state["ownership_event_id"],
            **refresh_metadata,
        )
    result = transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [event],
    })
    _apply_owner_refresh_plan(args.task_id, refresh_writes)
    return {
        **result, "task_id": args.task_id,
        **_ownership_receipt_fields(args.task_id, new_state),
    }


def cmd_legacy_run_writer_claim(args: argparse.Namespace) -> dict[str, Any]:
    writer_thread_id = host_thread_id()
    classification, class_hash, _ = load_receipt(
        args.task_id, "classification", require_fresh=False,
    )
    selection, selection_hash, _ = load_receipt(
        args.task_id, "selection", require_fresh=False,
    )
    events = _canonical_ownership_events()
    start, related = _run_state(events, args.run_id)
    if any(item["event_type"] in {"run_closed", "run_abandoned"} for item in related):
        raise WorkMemoryError("legacy-run-is-terminal", 3)
    existing_binding = next((
        item for item in events
        if item["event_type"] == "legacy_run_writer_bound"
        and item["run_id"] == args.run_id and item["task_id"] == args.task_id
    ), None)
    old_class_hash = (
        existing_binding["classification_receipt_hash"]
        if existing_binding else class_hash
    )
    old_selection_hash = (
        existing_binding["selection_receipt_hash"]
        if existing_binding else selection_hash
    )
    if (
        start["classification_receipt_hash"] != old_class_hash
        or start["selection_receipt_hash"] != old_selection_hash
    ):
        raise WorkMemoryError("legacy-run-receipt-binding-mismatch", 4)
    active_path = (
        Path(args.state).resolve() if getattr(args, "state", None)
        else receipt_path(args.task_id, "active")
    )
    if not active_path.is_file():
        raise WorkMemoryError("legacy-active-state-not-found", 4)
    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkMemoryError("invalid-legacy-active-state", 4) from exc
    stable_active = {
        "task_id": args.task_id,
        "mode": selection["mode"],
        "subject_id": selection["subject_id"],
        "lineage_id": selection["lineage_id"],
        "document": str(Path(selection["document"]).resolve()),
        "source_bundle_hash": selection["source_bundle_hash"],
    }
    if (
        any(active.get(key) != value for key, value in stable_active.items())
        or active.get("classification_receipt_hash")
        not in {old_class_hash, class_hash}
        or active.get("selection_receipt_hash")
        not in {old_selection_hash, selection_hash}
        or not active.get("sealed_controller_b64")
        or not active.get("sealed_bootstrap_b64")
    ):
        raise WorkMemoryError("legacy-active-state-binding-mismatch", 4)
    _validate_active_trust_snapshots(
        active, selection, allow_legacy_missing_launcher=True,
    )
    state = task_writer_state(args.task_id)
    batch: list[dict[str, Any]] = []
    if state is None:
        claim = _event(
            "task_writer_claimed", task_id=args.task_id,
            writer_thread_id=writer_thread_id, ownership_generation=1,
        )
        batch.append(claim)
        state = {
            "writer_thread_id": writer_thread_id,
            "ownership_generation": 1,
            "ownership_event_id": claim["event_id"],
        }
    elif state["writer_thread_id"] != writer_thread_id:
        raise WorkMemoryError("task-writer-not-owner", 4)
    ownership = _ownership_receipt_fields(args.task_id, state)
    if existing_binding is None:
        binding = _event(
            "legacy_run_writer_bound", args.event_id,
            task_id=args.task_id, run_id=args.run_id,
            classification_receipt_hash=old_class_hash,
            selection_receipt_hash=old_selection_hash,
            **ownership,
        )
        batch.append(binding)
        result = transact({
            "schema_version": 1, "expected_ledger_hash": None, "events": batch,
        })
    else:
        binding = existing_binding
        validate_run_writer_continuity(
            events, args.task_id, args.run_id, start,
            {**selection, **ownership},
        )
        result = {
            "ok": True, "event_ids": [binding["event_id"]],
            "idempotent_event_ids": [binding["event_id"]],
        }
    classification = {**classification, **ownership}
    _, new_class_hash = write_receipt(args.task_id, "classification", classification)
    selection = {
        **selection, **ownership, "classification_receipt_hash": new_class_hash,
    }
    _, new_selection_hash = write_receipt(args.task_id, "selection", selection)
    upgraded_active = {
        **active,
        "classification_receipt_hash": new_class_hash,
        "selection_receipt_hash": new_selection_hash,
        **ownership,
    }
    with _task_receipt_lock(args.task_id):
        validate_ownership_receipt(args.task_id, upgraded_active)
        _atomic_write(active_path, canonical_bytes(upgraded_active))
    return {
        **result, "task_id": args.task_id, "run_id": args.run_id,
        "legacy_run_writer_binding_event_id": binding["event_id"],
        "classification_receipt_hash": new_class_hash,
        "selection_receipt_hash": new_selection_hash,
        "active_state_path": str(active_path),
        **ownership,
    }


def _deterministic_event(
    events: list[dict[str, Any]], kind: str, event_id: str, *,
    time_fields: tuple[str, ...] = (), **fields: Any,
) -> dict[str, Any]:
    """Reuse an exact deterministic event without regenerating persisted timestamps."""
    prior = next((event for event in events if event["event_id"] == event_id), None)
    if prior is not None:
        volatile = {"recorded_at_utc", *time_fields}
        stable_prior = {key: value for key, value in prior.items() if key not in volatile}
        expected = {
            "schema_version": 1, "event_id": event_id, "event_type": kind, **fields,
        }
        if stable_prior != expected:
            raise WorkMemoryError("event-id-conflict", 3)
        return prior
    timed = {field: utc_now() for field in time_fields}
    return _event(kind, event_id, **fields, **timed)


def _run_state(events: list[dict[str, Any]], run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    related = [event for event in events if event.get("run_id") == run_id]
    start = next((event for event in related if event["event_type"] == "run_started"), None)
    if start is None:
        raise WorkMemoryError("run-not-found", 3)
    return start, related


def cmd_run_start(args: argparse.Namespace) -> dict[str, Any]:
    classification, class_hash, _ = load_receipt(args.task_id, "classification")
    selection, selection_hash, _ = load_receipt(args.task_id, "selection")
    state = validate_ownership_receipt(args.task_id, classification)
    validate_ownership_receipt(args.task_id, selection)
    if selection["classification_receipt_hash"] != class_hash:
        raise WorkMemoryError("receipt-chain-mismatch", 4)
    repository_roots = selection.get("repository_roots") or {
        key: str(path)
        for key, path in _repo_roots(selection.get("repository_roots_file")).items()
    }
    bundle, digest, lineage = resolve_bundle(
        mode=selection["mode"], subject_id=selection["subject_id"], document=Path(selection["document"]),
        manifest=Path(selection["manifest"]),
        repository_roots=repository_roots, include_bootstrap_trust_anchors=True,
    )
    if digest != selection["source_bundle_hash"] or lineage != selection["lineage_id"]:
        raise WorkMemoryError("stale-selection-bundle", 4)
    if selection.get("predecessor_run_id"):
        events, _ = load_ledger()
        _require_predecessor_task_ownership(
            events, selection["predecessor_run_id"], args.task_id,
        )
        _validate_successor_corrections(
            events, lineage_id=lineage, source_bundle=bundle,
            predecessor_run_id=selection["predecessor_run_id"],
            correction_ids=selection["verifies_correction_ids"],
            repository_roots=repository_roots,
            source_bundle_hash=digest,
        )
    run_id = args.run_id or str(uuid.uuid4())
    fields: dict[str, Any] = {
        "run_id": run_id, "subject_id": selection["subject_id"], "lineage_id": lineage,
        "mode": selection["mode"], "operation_kind": classification["operation_kind"],
        "source_bundle": bundle, "source_bundle_hash": digest,
        "repository_roots": repository_roots,
        "classification_receipt_hash": class_hash, "selection_receipt_hash": selection_hash,
        "started_at_utc": utc_now(),
        "task_id": args.task_id, **_ownership_receipt_fields(args.task_id, state),
    }
    if selection.get("predecessor_run_id"):
        fields["predecessor_run_id"] = selection["predecessor_run_id"]
        fields["verifies_correction_ids"] = selection["verifies_correction_ids"]
    event = _event("run_started", args.event_id, **fields)
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "run_id": run_id, "event_id": event["event_id"]}


def _run_repository_roots_hash(start: dict[str, Any]) -> str:
    roots = start.get("repository_roots") or {"memory-knowledge": str(ROOT.resolve())}
    return sha256_bytes(canonical_bytes(roots))


def cmd_record_operation_context(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    start, related = _run_state(events, args.run_id)
    if any(item["event_type"] in {"run_closed", "run_abandoned"} for item in related):
        raise WorkMemoryError("run-is-terminal", 3)
    raw = json.loads(Path(args.context_file).read_text(encoding="utf-8"))
    try:
        context = candidate_contract.normalize_operation_context(raw)
    except candidate_contract.CandidateContractError as exc:
        raise WorkMemoryError(exc.code, 2) from exc
    context_id = candidate_contract.deterministic_uuid(
        f"memory-knowledge:observer:context:{args.run_id}:{start['source_bundle_hash']}"
    )
    event_id = candidate_contract.deterministic_uuid(
        f"memory-knowledge:observer:context-event:{context_id}"
    )
    event = _deterministic_event(
        events,
        "operation_context_recorded", event_id, context_id=context_id, run_id=args.run_id,
        subject_id=start["subject_id"], lineage_id=start["lineage_id"],
        source_bundle_hash=start["source_bundle_hash"],
        repository_roots_hash=_run_repository_roots_hash(start), **context,
    )
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "event_id": event_id, "context_id": context_id,
            "already_recorded": event_id in result["idempotent_event_ids"]}


def cmd_execution_claim(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    start, related = _run_state(events, args.run_id)
    context = next((item for item in related if item["event_type"] == "operation_context_recorded" and item["context_id"] == args.context_id), None)
    if context is None:
        raise WorkMemoryError("operation-context-not-found", 3)
    if any(item["event_type"] in {"run_closed", "run_abandoned"} for item in related):
        raise WorkMemoryError("run-is-terminal", 3)
    try:
        argv = json.loads(args.argv_json)
    except json.JSONDecodeError as exc:
        raise WorkMemoryError("invalid-execution-argv", 2) from exc
    if not isinstance(argv, list) or not argv or any(not isinstance(item, str) for item in argv):
        raise WorkMemoryError("invalid-execution-argv", 2)
    command_hash = sha256_bytes(canonical_bytes(argv))
    execution_id = candidate_contract.deterministic_uuid(
        f"memory-knowledge:observer:execution:{args.context_id}:{args.step_ordinal}:{command_hash}"
    )
    event_id = candidate_contract.deterministic_uuid(
        f"memory-knowledge:observer:claim:{execution_id}"
    )
    event = _deterministic_event(
        events,
        "execution_claimed", event_id, execution_id=execution_id, context_id=args.context_id,
        run_id=args.run_id, subject_id=start["subject_id"], lineage_id=start["lineage_id"],
        source_bundle_hash=start["source_bundle_hash"], step_ordinal=args.step_ordinal,
        step_id=args.step_id, argv=argv, command_sha256=command_hash,
        command_source=args.command_source,
        source_ref={"repository_key": args.source_ref_repository, "path": args.source_ref_path},
        repository_roots_hash=args.repository_roots_hash,
        operation_kind=start["operation_kind"], effect_class=context["effect_class"],
        time_fields=("claimed_at_utc",),
    )
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "event_id": event_id, "execution_id": execution_id,
            "already_recorded": event_id in result["idempotent_event_ids"]}


def cmd_execution_return(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    claim = next((item for item in events if item["event_type"] == "execution_claimed" and item["execution_id"] == args.execution_id), None)
    if claim is None:
        raise WorkMemoryError("execution-claim-not-found", 3)
    event_id = candidate_contract.deterministic_uuid(
        f"memory-knowledge:observer:return:{args.execution_id}"
    )
    event = _deterministic_event(
        events,
        "execution_returned", event_id, execution_id=args.execution_id,
        context_id=claim["context_id"], run_id=claim["run_id"], subject_id=claim["subject_id"],
        lineage_id=claim["lineage_id"], source_bundle_hash=claim["source_bundle_hash"],
        exit_code=args.exit_code, result="passed" if args.exit_code == 0 else "failed",
        time_fields=("returned_at_utc",),
    )
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "event_id": event_id, "execution_id": args.execution_id,
            "already_recorded": event_id in result["idempotent_event_ids"]}


def _append_observer_record(
    path: str, *, event_type: str, domain_id: str, event_label: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkMemoryError(f"invalid-{event_label}-json", 2) from exc
    required, optional = EVENT_FIELDS[event_type]
    if not isinstance(payload, dict) or set(payload) != required | optional:
        raise WorkMemoryError(f"invalid-{event_label}-fields", 2)
    event_id = candidate_contract.deterministic_uuid(
        f"memory-knowledge:observer:event:{event_type}:{payload[domain_id]}"
    )
    events, _ = load_ledger()
    event = _event(
        event_type, event_id,
        recorded_at_utc=_observer_recorded_at(event_type, payload, events),
        **payload,
    )
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {
        **result,
        "event_id": event_id,
        domain_id: payload[domain_id],
        "already_recorded": event_id in result["idempotent_event_ids"],
    }


def _observer_recorded_at(
    event_type: str, payload: dict[str, Any], events: list[dict[str, Any]],
) -> str:
    if event_type == "observer_decision_recorded":
        source = next((
            event for event in events if event["event_id"] == payload["trigger_event_id"]
        ), None)
        if source is None or source["event_type"] != "run_closed":
            raise WorkMemoryError("observer-decision-trigger-mismatch", 3)
        return source["completed_at_utc"]
    decision = next((
        event for event in events
        if event["event_type"] == "observer_decision_recorded"
        and event["decision_id"] == payload["decision_id"]
    ), None)
    if decision is None:
        raise WorkMemoryError("observer-record-decision-not-found", 3)
    return decision["recorded_at_utc"]


def cmd_observer_decision_append(args: argparse.Namespace) -> dict[str, Any]:
    return _append_observer_record(
        args.decision_file, event_type="observer_decision_recorded",
        domain_id="decision_id", event_label="observer-decision",
    )


def cmd_observer_bootstrap_result_append(args: argparse.Namespace) -> dict[str, Any]:
    return _append_observer_record(
        args.result_file, event_type="observer_bootstrap_result_recorded",
        domain_id="bootstrap_attempt_id", event_label="observer-bootstrap-result",
    )


def cmd_observer_link_append(args: argparse.Namespace) -> dict[str, Any]:
    return _append_observer_record(
        args.link_file, event_type="observer_candidate_linked",
        domain_id="link_id", event_label="observer-link",
    )


def _artifact_hashes(
    paths: Iterable[Any], repo_roots_file: str | None = None,
    repository_roots: dict[str, str] | None = None,
) -> tuple[list[Any], list[str]]:
    roots = (
        _repo_roots(repo_roots_file)
        if repository_roots is None
        else _repo_roots(snapshot=repository_roots)
    )
    artifacts: list[Any] = []
    hashes: list[str] = []
    for raw in paths:
        if isinstance(raw, dict):
            repository_key, relative = _artifact_identity(raw)
            if repository_key not in roots:
                raise WorkMemoryError(
                    "changed-artifact-outside-repository",
                    2,
                )
            path = _safe_file(roots[repository_key], relative)
            artifacts.append(
                relative if repository_key == "memory-knowledge"
                else {"repository_key": repository_key, "path": relative}
            )
            hashes.append(sha256_bytes(path.read_bytes()))
            continue
        path = Path(raw).resolve()
        if not path.is_file():
            raise WorkMemoryError("changed-artifact-not-found", 2)
        matches: list[tuple[int, str, str]] = []
        for repository_key, root in roots.items():
            try:
                relative = str(path.relative_to(root))
            except ValueError:
                continue
            matches.append((len(root.parts), repository_key, relative))
        if not matches:
            raise WorkMemoryError("changed-artifact-outside-repository", 2)
        _, repository_key, relative = max(matches)
        artifacts.append(
            relative if repository_key == "memory-knowledge"
            else {"repository_key": repository_key, "path": relative}
        )
        hashes.append(sha256_bytes(path.read_bytes()))
    return artifacts, hashes


def _environment_artifact_hashes(
    paths: Iterable[Any], repo_roots_file: str | None = None,
    repository_roots: dict[str, str] | None = None,
) -> tuple[list[Any], list[str]]:
    """Hash host files while preserving repository identity when one applies."""
    roots = (
        _repo_roots(repo_roots_file)
        if repository_roots is None
        else _repo_roots(snapshot=repository_roots)
    )
    artifacts: list[Any] = []
    hashes: list[str] = []
    for raw in paths:
        if isinstance(raw, dict):
            nested_artifacts, nested_hashes = _artifact_hashes(
                [raw], repo_roots_file, repository_roots,
            )
            artifacts.extend(nested_artifacts)
            hashes.extend(nested_hashes)
            continue
        if not isinstance(raw, (str, os.PathLike)):
            raise WorkMemoryError("invalid-changed-artifact-identity", 2)
        unresolved = Path(raw).expanduser()
        if not unresolved.is_absolute():
            raise WorkMemoryError("environment-artifact-path-not-absolute", 2)
        path = unresolved.resolve()
        if not path.is_file():
            raise WorkMemoryError("changed-artifact-not-found", 2)
        matches: list[tuple[int, str, str]] = []
        for repository_key, root in roots.items():
            try:
                relative = str(path.relative_to(root))
            except ValueError:
                continue
            matches.append((len(root.parts), repository_key, relative))
        if matches:
            _, repository_key, relative = max(matches)
            artifacts.append(
                relative if repository_key == "memory-knowledge"
                else {"repository_key": repository_key, "path": relative}
            )
        else:
            artifacts.append({
                "repository_key": "host-environment",
                "path": str(path),
            })
        hashes.append(sha256_bytes(path.read_bytes()))
    return artifacts, hashes


def _effective_correction_bundle(
    start: dict[str, Any],
    related: Sequence[dict[str, Any]],
    *,
    stop_before_event_id: str | None = None,
) -> tuple[list[dict[str, str]], str, list[str]]:
    """Reduce the run's ordered cumulative correction transitions."""
    rows = {
        (item["repository_key"], item["path"]): dict(item)
        for item in start["source_bundle"]
    }
    order = [
        (item["repository_key"], item["path"])
        for item in start["source_bundle"]
    ]
    effective_hash = start["source_bundle_hash"]
    inherited_correction_ids = list(start.get("verifies_correction_ids", []))
    correction_ids: list[str] = list(inherited_correction_ids)
    for transition in related:
        if transition.get("event_id") == stop_before_event_id:
            break
        if (
            transition["event_type"] != "bundle_transition_recorded"
            or transition.get("transition_reason") != "correction"
        ):
            continue
        if transition["old_bundle_hash"] != effective_hash:
            raise WorkMemoryError("noncumulative-correction-transition", 3)
        transition_ids = list(transition["correction_ids"])
        if (
            inherited_correction_ids
            and transition_ids[:len(correction_ids)] != correction_ids
        ):
            within_run_ids = correction_ids[len(inherited_correction_ids):]
            if transition_ids[:len(within_run_ids)] == within_run_ids:
                transition_ids = [
                    *inherited_correction_ids,
                    *transition_ids,
                ]
        if (
            correction_ids
            and transition_ids[:len(correction_ids)] != correction_ids
        ):
            raise WorkMemoryError("noncumulative-correction-transition", 3)
        for artifact, artifact_hash in zip(
            transition["changed_artifacts"],
            transition["changed_artifact_hashes"],
            strict=True,
        ):
            key = _artifact_identity(artifact)
            if key not in rows:
                order.append(key)
            rows[key] = {
                "repository_key": key[0],
                "path": key[1],
                "sha256": artifact_hash,
            }
        effective_hash = transition["new_bundle_hash"]
        correction_ids = transition_ids
    return [rows[key] for key in order], effective_hash, correction_ids


def cmd_correct(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    start, related = _run_state(events, args.run_id)
    co_blocker_ids = list(getattr(args, "co_blocker_id", None) or [])
    if (
        len(co_blocker_ids) != len(set(co_blocker_ids))
        or args.blocker_id in co_blocker_ids
    ):
        raise WorkMemoryError("duplicate-co-blocker", 2)
    run_starts = {
        event["run_id"]: event for event in events
        if event["event_type"] == "run_started"
    }
    blocker_contexts: dict[str, dict[str, Any]] = {}
    for blocker_id in co_blocker_ids:
        opened = None
        status = occurrence_id = occurrence_run_id = None
        for event in events:
            if event.get("blocker_id") != blocker_id:
                continue
            if event["event_type"] == "blocker_opened":
                opened, status = event, "open"
                occurrence_id, occurrence_run_id = event["occurrence_id"], event["run_id"]
            elif event["event_type"] == "blocker_recurred":
                status = "open"
                occurrence_id, occurrence_run_id = event["occurrence_id"], event["run_id"]
            elif event["event_type"] == "blocker_transitioned":
                status = event["to_status"]
                if status == "open" and "recovery_evidence" in event:
                    occurrence_run_id = event["run_id"]
        if opened is None:
            raise WorkMemoryError("unknown-co-blocker", 3)
        occurrence_start = run_starts.get(occurrence_run_id)
        if occurrence_run_id != args.run_id:
            primary_task = start.get("task_id")
            occurrence_task = occurrence_start.get("task_id") if occurrence_start else None
            if (
                primary_task is not None and occurrence_task is not None
                and primary_task != occurrence_task
            ):
                raise WorkMemoryError("co-blocker-different-task", 3)
            raise WorkMemoryError("co-blocker-different-run", 3)
        if (
            opened["subject_id"] != start["subject_id"]
            or opened["lineage_id"] != start["lineage_id"]
        ):
            raise WorkMemoryError("co-blocker-lineage-mismatch", 3)
        blocker_contexts[blocker_id] = {
            "opened": opened,
            "occurrence_id": occurrence_id,
            "status": status,
        }
    repository_roots = start.get("repository_roots")
    if repository_roots is not None and args.repo_roots_file:
        supplied_roots = {
            key: str(path) for key, path in _repo_roots(args.repo_roots_file).items()
        }
        if supplied_roots != repository_roots:
            raise WorkMemoryError("repository-roots-mismatch", 4)
    artifacts, hashes = _artifact_hashes(
        args.changed_artifact or [],
        args.repo_roots_file if repository_roots is None else None,
        repository_roots=repository_roots,
    )
    declared_environment = getattr(args, "changed_environment_artifact", None) or []
    environment_artifacts, environment_hashes = (
        _environment_artifact_hashes(
            declared_environment,
            args.repo_roots_file if repository_roots is None else None,
            repository_roots=repository_roots,
        )
        if declared_environment else ([], [])
    )
    environment_fields: dict[str, Any] = (
        {
            "environment_artifacts": environment_artifacts,
            "environment_artifact_hashes": environment_hashes,
        }
        if environment_artifacts else {}
    )
    correction_id = (
        require_uuid(args.correction_id, "correction-id")
        if args.correction_id else str(uuid.uuid4())
    )
    co_correction_ids = {
        blocker_id: str(uuid.uuid5(uuid.UUID(correction_id), blocker_id))
        for blocker_id in co_blocker_ids
    }
    supersedes = args.supersedes_correction_id or []
    co_supersedes_values = (
        getattr(args, "co_supersedes_correction_id", None) or []
    )
    if co_supersedes_values and len(co_supersedes_values) != len(co_blocker_ids):
        raise WorkMemoryError("co-superseded-correction-count-mismatch", 2)
    co_supersedes = (
        {
            blocker_id: require_uuid(value, "co-supersedes-correction-id")
            for blocker_id, value in zip(
                co_blocker_ids, co_supersedes_values, strict=True,
            )
        }
        if co_supersedes_values else {}
    )
    existing = next((
        event for event in events
        if event["event_type"] == "correction_recorded"
        and event["correction_id"] == correction_id
    ), None)
    if existing is None and any(
        event["event_type"] == "correction_recorded"
        and event["correction_id"] in set(co_correction_ids.values())
        for event in events
    ):
        raise WorkMemoryError("co-correction-id-conflict", 3)
    if existing is None and any(
        context["status"] != "open" for context in blocker_contexts.values()
    ):
        raise WorkMemoryError("co-blocker-not-open", 3)
    if existing is not None:
        expected = {
            "run_id": args.run_id,
            "blocker_id": args.blocker_id,
            "occurrence_id": args.occurrence_id,
            "step_id": args.step_id,
            "changed_artifacts": artifacts,
            "changed_artifact_hashes": hashes,
            **environment_fields,
            "solution": args.solution,
            "reusable_behavior_changed": args.reusable_behavior_changed == "yes",
        }
        if any(existing.get(key) != value for key, value in expected.items()):
            raise WorkMemoryError("correction-id-conflict", 3)
        if _superseded_correction_ids(existing) != set(supersedes):
            raise WorkMemoryError("correction-id-conflict", 3)
        for blocker_id in co_blocker_ids:
            context = blocker_contexts[blocker_id]
            co_correction = next((
                event for event in events
                if event["event_type"] == "correction_recorded"
                and event["correction_id"] == co_correction_ids[blocker_id]
            ), None)
            expected_co = {
                **expected,
                "blocker_id": blocker_id,
                "occurrence_id": context["occurrence_id"],
                "step_id": context["opened"]["step_id"],
                "primary_correction_id": correction_id,
            }
            if (
                co_correction is None
                or any(co_correction.get(key) != value for key, value in expected_co.items())
                or _superseded_correction_ids(co_correction)
                != (
                    {co_supersedes[blocker_id]}
                    if blocker_id in co_supersedes else set()
                )
            ):
                raise WorkMemoryError("correction-id-conflict", 3)
        existing_transitions = [
            event for event in events
            if event["event_type"] == "bundle_transition_recorded"
            and correction_id in event.get("correction_ids", [])
            and event.get("changed_artifacts") == existing["changed_artifacts"]
            and event.get("changed_artifact_hashes")
            == existing["changed_artifact_hashes"]
        ]
        if not existing_transitions:
            raise WorkMemoryError("existing-correction-transition-not-found", 3)
        if len(existing_transitions) != 1:
            raise WorkMemoryError("correction-id-conflict", 3)
        existing_transition = existing_transitions[0]
        effective_bundle, effective_hash, prior_correction_ids = (
            _effective_correction_bundle(
                start, related,
                stop_before_event_id=existing_transition["event_id"],
            )
        )
        expected_transition_ids = [
            *prior_correction_ids,
            correction_id, *(co_correction_ids[item] for item in co_blocker_ids),
        ]
        if (
            existing_transition.get("correction_ids") != expected_transition_ids
            or existing_transition.get("run_id") != args.run_id
            or existing_transition.get("lineage_id") != start["lineage_id"]
            or existing_transition.get("old_bundle_hash") != effective_hash
            or existing_transition.get("transition_reason") != "correction"
            or existing_transition.get("changed_artifacts") != artifacts
            or existing_transition.get("changed_artifact_hashes") != hashes
        ):
            raise WorkMemoryError("correction-id-conflict", 3)
        if args.finalize_failed_run:
            blocker_ids = [args.blocker_id, *co_blocker_ids]
            blocker_states = {blocker_id: "open" for blocker_id in blocker_ids}
            for event in events:
                blocker_id = event.get("blocker_id")
                if blocker_id not in blocker_states:
                    continue
                if event["event_type"] in {"blocker_opened", "blocker_recurred"}:
                    blocker_states[blocker_id] = "open"
                elif event["event_type"] == "blocker_transitioned":
                    blocker_states[blocker_id] = event["to_status"]
            terminal_events = [
                event for event in related
                if event["event_type"] in {"run_closed", "run_abandoned"}
            ]
            finalized = (
                len(terminal_events) == 1
                and terminal_events[0]["event_type"] == "run_closed"
                and terminal_events[0]["result"] == "failed"
                and all(
                    blocker_states[blocker_id] == "fixed-awaiting-verification"
                    for blocker_id in blocker_ids
                )
            )
            if not finalized:
                if terminal_events or any(
                    blocker_states[blocker_id] != "open" for blocker_id in blocker_ids
                ):
                    raise WorkMemoryError(
                        "existing-correction-finalization-conflict", 3,
                    )
                bundle_paths = {
                    item["path"]
                    for item in start["source_bundle"]
                    if item["repository_key"] == "memory-knowledge"
                }
                if start["mode"] == "registered":
                    document_relative = (
                        f"operations/sequences/{start['subject_id']}/sequence.md"
                    )
                else:
                    document_relative = None
                    for relative in sorted(bundle_paths):
                        if not relative.endswith(".dependencies.json"):
                            continue
                        candidate_manifest = ROOT / relative
                        try:
                            candidate = json.loads(
                                candidate_manifest.read_text(encoding="utf-8")
                            )
                        except (OSError, json.JSONDecodeError):
                            continue
                        if candidate.get("lineage_id") == start["lineage_id"]:
                            document_relative = (
                                relative.removesuffix(".dependencies.json") + ".md"
                            )
                            break
                    if document_relative is None:
                        raise WorkMemoryError(
                            "correction-subject-document-not-found", 3,
                        )
                if document_relative not in bundle_paths:
                    raise WorkMemoryError("correction-subject-document-not-found", 3)
                document = ROOT / document_relative
                manifest = (
                    document.with_name("dependencies.json")
                    if start["mode"] == "registered"
                    else document.with_suffix(".dependencies.json")
                )
                current_bundle, current_hash, current_lineage = resolve_bundle(
                    mode=start["mode"], subject_id=start["subject_id"],
                    document=document, manifest=manifest,
                    repo_roots_file=(
                        args.repo_roots_file if repository_roots is None else None
                    ),
                    repository_roots=repository_roots,
                    include_bootstrap_trust_anchors=True,
                )
                old_map = {
                    (item["repository_key"], item["path"]): item["sha256"]
                    for item in effective_bundle
                }
                current_map = {
                    (item["repository_key"], item["path"]): item["sha256"]
                    for item in current_bundle
                }
                drifted = {
                    key for key in old_map.keys() | current_map.keys()
                    if old_map.get(key) != current_map.get(key)
                }
                artifact_keys = {
                    _artifact_identity(artifact) for artifact in artifacts
                }
                if (
                    current_lineage != start["lineage_id"]
                    or current_hash != existing_transition.get("new_bundle_hash")
                    or artifact_keys != drifted
                ):
                    raise WorkMemoryError(
                        "existing-correction-bundle-mismatch", 3,
                    )
                verification_quality = next(
                    (
                        event["quality"] for event in reversed(related)
                        if event["event_type"] == "verification_recorded"
                    ),
                    "none",
                )
                finalization_events = [
                    _event(
                        "blocker_transitioned", run_id=args.run_id,
                        blocker_id=blocker_id, from_status="open",
                        to_status="fixed-awaiting-verification",
                    )
                    for blocker_id in blocker_ids
                ]
                finalization_events.append(_event(
                    "run_closed", run_id=args.run_id,
                    subject_id=start["subject_id"], lineage_id=start["lineage_id"],
                    result="failed", completed_at_utc=utc_now(),
                    correction_count=sum(
                        event["event_type"] == "correction_recorded"
                        for event in related
                    ),
                    blocker_ids=sorted({
                        event["blocker_id"] for event in related
                        if "blocker_id" in event
                    }),
                    sequence_updated=True,
                    verification_quality=verification_quality,
                ))
                result = transact({
                    "schema_version": 1, "expected_ledger_hash": None,
                    "events": finalization_events,
                })
                return {
                    **result, "correction_id": correction_id,
                    "event_id": existing["event_id"], "already_recorded": False,
                    "finalized_existing": True,
                    "changed_artifact_hashes": hashes,
                    "new_bundle_hash": existing_transition["new_bundle_hash"],
                    "transition_event_id": existing_transition["event_id"],
                    "co_correction_ids": [
                        co_correction_ids[item] for item in co_blocker_ids
                    ],
                }
        return {
            "ok": True, "correction_id": correction_id,
            "event_id": existing["event_id"], "already_recorded": True,
            "changed_artifact_hashes": hashes,
            "new_bundle_hash": existing_transition["new_bundle_hash"],
            "transition_event_id": existing_transition["event_id"],
            "co_correction_ids": [
                co_correction_ids[item] for item in co_blocker_ids
            ],
        }
    if any(event["event_type"] in {"run_closed", "run_abandoned"} for event in related):
        raise WorkMemoryError("run-is-terminal", 3)
    bundle_paths = {
        item["path"]
        for item in start["source_bundle"]
        if item["repository_key"] == "memory-knowledge"
    }
    if start["mode"] == "registered":
        document_relative = f"operations/sequences/{start['subject_id']}/sequence.md"
    else:
        document_relative = None
        for relative in sorted(bundle_paths):
            if not relative.endswith(".dependencies.json"):
                continue
            candidate_manifest = ROOT / relative
            try:
                candidate = json.loads(candidate_manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if candidate.get("lineage_id") == start["lineage_id"]:
                document_relative = relative.removesuffix(".dependencies.json") + ".md"
                break
        if document_relative is None:
            raise WorkMemoryError("correction-subject-document-not-found", 3)
    if document_relative not in bundle_paths:
        raise WorkMemoryError("correction-subject-document-not-found", 3)
    document = ROOT / document_relative
    manifest = document.with_name("dependencies.json") if start["mode"] == "registered" else document.with_suffix(".dependencies.json")
    new_bundle, new_hash, _ = resolve_bundle(
        mode=start["mode"], subject_id=start["subject_id"], document=document,
        manifest=manifest,
        repo_roots_file=args.repo_roots_file if repository_roots is None else None,
        repository_roots=repository_roots,
        include_bootstrap_trust_anchors=True,
    )
    effective_bundle, effective_hash, prior_correction_ids = (
        _effective_correction_bundle(start, related)
    )
    old_map = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in effective_bundle
    }
    new_map = {
        (item["repository_key"], item["path"]): item["sha256"]
        for item in new_bundle
    }
    drifted = {
        key for key in old_map.keys() | new_map.keys()
        if old_map.get(key) != new_map.get(key)
    }
    artifact_keys = {_artifact_identity(artifact) for artifact in artifacts}
    if artifact_keys != drifted:
        raise WorkMemoryError("correction-artifact-drift-mismatch", 3)
    # An environment surface (machine config, host registry) is not a member of the sequence's
    # dependency bundle, so it can never appear in `drifted` and cannot be attested by the gate
    # above. It is hashed on its own. Declaring a real bundle file here would let a caller dodge
    # the drift equality, so that is rejected outright.
    bundle_keys = old_map.keys() | new_map.keys()
    environment_keys = {_artifact_identity(item) for item in environment_artifacts}
    if environment_keys & bundle_keys:
        raise WorkMemoryError("environment-artifact-is-bundle-dependency", 3)
    if not artifact_keys and not environment_keys:
        raise WorkMemoryError("correction-declares-no-artifact", 3)
    supersession_fields: dict[str, Any] = {}
    if len(supersedes) == 1:
        supersession_fields["supersedes_correction_id"] = supersedes[0]
    elif supersedes:
        supersession_fields["supersedes_correction_ids"] = supersedes
    for blocker_id, old_correction_id in co_supersedes.items():
        old_correction = next((
            event for event in events
            if event["event_type"] == "correction_recorded"
            and event["correction_id"] == old_correction_id
        ), None)
        if (
            old_correction is None
            or old_correction.get("blocker_id") != blocker_id
            or old_correction.get("occurrence_id")
            != blocker_contexts[blocker_id]["occurrence_id"]
        ):
            raise WorkMemoryError("co-superseded-correction-not-found", 3)
    correction = _event(
        "correction_recorded", args.event_id, run_id=args.run_id, blocker_id=args.blocker_id,
        occurrence_id=args.occurrence_id, correction_id=correction_id, subject_id=start["subject_id"],
        lineage_id=start["lineage_id"], step_id=args.step_id, changed_artifacts=artifacts,
        changed_artifact_hashes=hashes, reusable_behavior_changed=args.reusable_behavior_changed == "yes",
        solution=args.solution, **environment_fields, **supersession_fields,
    )
    co_corrections = [
        _event(
            "correction_recorded", run_id=args.run_id, blocker_id=blocker_id,
            occurrence_id=blocker_contexts[blocker_id]["occurrence_id"],
            correction_id=co_correction_ids[blocker_id], subject_id=start["subject_id"],
            lineage_id=start["lineage_id"],
            step_id=blocker_contexts[blocker_id]["opened"]["step_id"],
            changed_artifacts=artifacts, changed_artifact_hashes=hashes,
            reusable_behavior_changed=args.reusable_behavior_changed == "yes",
            solution=args.solution, **environment_fields, primary_correction_id=correction_id,
            **(
                {"supersedes_correction_id": co_supersedes[blocker_id]}
                if blocker_id in co_supersedes else {}
            ),
        )
        for blocker_id in co_blocker_ids
    ]
    new_correction_ids = [
        correction_id, *(co_correction_ids[item] for item in co_blocker_ids),
    ]
    correction_ids = [*prior_correction_ids, *new_correction_ids]
    transition = _event(
        "bundle_transition_recorded", args.transition_event_id, lineage_id=start["lineage_id"],
        old_bundle_hash=effective_hash, new_bundle_hash=new_hash, transition_reason="correction",
        run_id=args.run_id, correction_ids=correction_ids, changed_artifacts=artifacts,
        changed_artifact_hashes=hashes, **environment_fields,
    )
    batch = [correction, *co_corrections, transition]
    if args.finalize_failed_run:
        blocker_states: dict[str, str] = {}
        correction_blockers: dict[str, str] = {}
        for event in events:
            blocker_id = event.get("blocker_id")
            if event["event_type"] in {"blocker_opened", "blocker_recurred"}:
                blocker_states[blocker_id] = "open"
            elif event["event_type"] == "blocker_transitioned" and blocker_id in blocker_states:
                blocker_states[blocker_id] = event["to_status"]
            elif event["event_type"] == "correction_recorded":
                correction_blockers[event["correction_id"]] = event["blocker_id"]
        primary_status = blocker_states.get(args.blocker_id)
        retry_verification = (
            _failed_retry_verification(
                events, run_id=args.run_id, blocker_id=args.blocker_id,
                occurrence_id=args.occurrence_id,
                supersedes_correction_ids=supersedes,
            )
            if primary_status == "fixed-awaiting-verification" else None
        )
        if retry_verification is not None:
            batch.insert(0, _event(
                "blocker_transitioned", run_id=args.run_id,
                blocker_id=args.blocker_id,
                from_status="fixed-awaiting-verification", to_status="open",
                verification_event_id=retry_verification["event_id"],
                reopen_evidence=(
                    "The bound same-path verification failed; this occurrence requires "
                    "a superseding correction."
                ),
            ))
        for old_correction_id in supersedes:
            old_blocker_id = correction_blockers.get(old_correction_id)
            if old_blocker_id is None:
                raise WorkMemoryError("superseded-correction-not-found", 3)
            old_status = blocker_states.get(old_blocker_id)
            if old_status == "closed":
                continue
            if old_status not in {"open", "fixed-awaiting-verification"}:
                raise WorkMemoryError("superseded-blocker-not-active", 3)
            if old_blocker_id == args.blocker_id and retry_verification is not None:
                continue
            batch.append(_event(
                "blocker_transitioned", run_id=args.run_id,
                blocker_id=old_blocker_id, from_status=old_status, to_status="superseded",
                supersession_evidence=(
                    f"Correction {old_correction_id} is explicitly superseded by {correction_id}."
                ),
            ))
        if primary_status not in {"open", "fixed-awaiting-verification"}:
            raise WorkMemoryError("correction-for-nonopen-blocker", 3)
        if primary_status == "fixed-awaiting-verification" and retry_verification is None:
            raise WorkMemoryError("correction-for-nonopen-blocker", 3)
        batch.append(_event(
            "blocker_transitioned", run_id=args.run_id,
            blocker_id=args.blocker_id, from_status="open",
            to_status="fixed-awaiting-verification",
        ))
        for blocker_id in co_blocker_ids:
            batch.append(_event(
                "blocker_transitioned", run_id=args.run_id,
                blocker_id=blocker_id, from_status="open",
                to_status="fixed-awaiting-verification",
            ))
        blockers = sorted({event["blocker_id"] for event in related if "blocker_id" in event})
        verification_quality = next(
            (
                event["quality"]
                for event in reversed(related)
                if event["event_type"] == "verification_recorded"
            ),
            "none",
        )
        batch.append(_event(
            "run_closed", run_id=args.run_id, subject_id=start["subject_id"],
            lineage_id=start["lineage_id"], result="failed", completed_at_utc=utc_now(),
            correction_count=sum(
                event["event_type"] == "correction_recorded" for event in related
            ) + len(new_correction_ids),
            blocker_ids=blockers, sequence_updated=True,
            verification_quality=verification_quality,
        ))
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": batch})
    return {**result, "correction_id": correction_id, "event_id": correction["event_id"],
            "transition_event_id": transition["event_id"], "old_bundle_hash": effective_hash,
            "new_bundle_hash": new_hash, "changed_artifact_hashes": hashes,
            "co_correction_ids": [co_correction_ids[item] for item in co_blocker_ids]}


def cmd_preserve_corrections(args: argparse.Namespace) -> dict[str, Any]:
    source_bundle = getattr(args, "authenticated_source_bundle", None)
    source_bundle_hash = getattr(args, "authenticated_source_bundle_hash", None)
    if not isinstance(source_bundle, list) or not isinstance(source_bundle_hash, str):
        raise WorkMemoryError("correction-preservation-bootstrap-required", 4)
    if args.task_id == args.preserved_task_id:
        raise WorkMemoryError("correction-preservation-distinct-tasks-required", 2)
    events, _ = load_ledger()
    tasks, run_tasks = _ownership_snapshot(events)
    target_state = tasks.get(args.task_id)
    preserved_state = tasks.get(args.preserved_task_id)
    if target_state is None or preserved_state is None:
        raise WorkMemoryError("correction-preservation-task-unclaimed", 4)
    if target_state["writer_thread_id"] != preserved_state["writer_thread_id"]:
        raise WorkMemoryError("correction-preservation-owner-mismatch", 4)

    preserved_ids = list(args.preserved_correction_id or [])
    if not preserved_ids or len(preserved_ids) != len(set(preserved_ids)):
        raise WorkMemoryError("duplicate-preserved-correction", 2)
    if args.target_correction_id in preserved_ids:
        raise WorkMemoryError("self-preserved-correction", 2)
    correction_rows: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, ledger_event in enumerate(events):
        if ledger_event["event_type"] == "correction_recorded":
            correction_rows[ledger_event["correction_id"]].append(
                (index, ledger_event),
            )
    if len(correction_rows.get(args.target_correction_id, [])) != 1:
        if not correction_rows.get(args.target_correction_id):
            raise WorkMemoryError("preservation-target-correction-not-found", 3)
        raise WorkMemoryError("ambiguous-preservation-target-correction", 3)
    target_index, target = correction_rows[args.target_correction_id][0]
    if any(len(correction_rows.get(correction_id, [])) != 1 for correction_id in preserved_ids):
        if any(not correction_rows.get(correction_id) for correction_id in preserved_ids):
            raise WorkMemoryError("preserved-correction-not-found", 3)
        raise WorkMemoryError("ambiguous-preserved-correction", 3)
    preserved = [correction_rows[correction_id][0][1] for correction_id in preserved_ids]
    if target is None:
        raise WorkMemoryError("preservation-target-correction-not-found", 3)
    if run_tasks.get(target["run_id"]) != args.task_id:
        raise WorkMemoryError("preservation-target-task-mismatch", 3)
    if any(
        run_tasks.get(correction["run_id"]) != args.preserved_task_id
        for correction in preserved if correction is not None
    ):
        raise WorkMemoryError("preserved-correction-task-mismatch", 3)
    if any(
        correction["subject_id"] != target["subject_id"]
        or correction["lineage_id"] != target["lineage_id"]
        for correction in preserved if correction is not None
    ):
        raise WorkMemoryError("preserved-correction-context-mismatch", 3)
    target_transitions = [
        (index, ledger_event) for index, ledger_event in enumerate(events)
        if ledger_event["event_type"] == "bundle_transition_recorded"
        and ledger_event.get("transition_reason") == "correction"
        and args.target_correction_id in ledger_event.get("correction_ids", [])
    ]
    if not target_transitions:
        raise WorkMemoryError("preservation-target-transition-not-found", 3)
    if len(target_transitions) != 1:
        raise WorkMemoryError("ambiguous-preservation-target-transition", 3)
    target_transition_index, target_transition = target_transitions[0]
    if (
        target_transition["new_bundle_hash"] != source_bundle_hash
        or target_transition.get("run_id") != target["run_id"]
        or target_transition.get("changed_artifacts") != target["changed_artifacts"]
        or target_transition.get("changed_artifact_hashes")
        != target["changed_artifact_hashes"]
    ):
        raise WorkMemoryError("preservation-target-transition-mismatch", 3)
    target_verification_entry = next((
        (index, ledger_event) for index, ledger_event in enumerate(events)
        if ledger_event["event_type"] == "verification_recorded"
        and ledger_event["event_id"] == args.target_verification_event_id
    ), None)
    if target_verification_entry is None:
        raise WorkMemoryError("preservation-target-verification-not-found", 3)
    target_verification_index, target_verification = target_verification_entry
    if not target_index < target_transition_index < target_verification_index:
        raise WorkMemoryError("correction-preservation-order-mismatch", 3)
    if (
        target_verification["outcome"] != "passed"
        or target_verification["quality"] != "same-path"
        or target_verification["subject_id"] != target["subject_id"]
        or target_verification["lineage_id"] != target["lineage_id"]
        or target_verification["source_bundle_hash"] != source_bundle_hash
        or args.target_correction_id not in target_verification["correction_ids"]
        or target["blocker_id"] not in target_verification["blocker_ids"]
        or run_tasks.get(target_verification["run_id"]) != args.task_id
    ):
        raise WorkMemoryError("preservation-target-verification-mismatch", 3)
    blocker_status = None
    for ledger_event in events:
        if ledger_event.get("blocker_id") != target["blocker_id"]:
            continue
        if ledger_event["event_type"] in {"blocker_opened", "blocker_recurred"}:
            blocker_status = "open"
        elif ledger_event["event_type"] == "blocker_transitioned":
            blocker_status = ledger_event["to_status"]
    if blocker_status != "closed":
        raise WorkMemoryError("preservation-target-blocker-not-closed", 3)
    run_start = next(
        event for event in events
        if event["event_type"] == "run_started" and event["run_id"] == target["run_id"]
    )
    roots = _repo_roots(snapshot=run_start.get("repository_roots"))
    bundle_paths = {
        (item["repository_key"], item["path"]) for item in source_bundle
    }
    for artifact, expected_hash in zip(
        target["changed_artifacts"], target["changed_artifact_hashes"], strict=True,
    ):
        repository_key, relative = _artifact_identity(artifact)
        if (repository_key, relative) not in bundle_paths:
            raise WorkMemoryError("preservation-target-artifact-outside-bundle", 3)
        if repository_key not in roots:
            raise WorkMemoryError("missing-repository-root", 3)
        current_hash = sha256_bytes(
            _safe_file(roots[repository_key], relative).read_bytes()
        )
        if current_hash != expected_hash:
            raise WorkMemoryError("preservation-target-artifact-hash-mismatch", 3)
    for correction in preserved:
        assert correction is not None
        _preserved_artifact_effective_hashes(
            correction, target, bundle_paths=bundle_paths, roots=roots,
        )

    event = _event(
        "correction_preservation_recorded", args.event_id,
        target_task_id=args.task_id, preserved_task_id=args.preserved_task_id,
        subject_id=target["subject_id"], lineage_id=target["lineage_id"],
        target_correction_id=args.target_correction_id,
        preserved_correction_ids=preserved_ids,
        target_transition_event_id=target_transition["event_id"],
        target_verification_event_id=target_verification["event_id"],
        target_bundle_hash=source_bundle_hash,
        **_prefixed_ownership_receipt_fields("target", args.task_id, target_state),
        **_prefixed_ownership_receipt_fields(
            "preserved", args.preserved_task_id, preserved_state,
        ),
    )
    result = transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [event],
    })
    return {
        **result, "event_id": event["event_id"],
        "target_correction_id": args.target_correction_id,
        "preserved_correction_ids": preserved_ids,
        "target_bundle_hash": source_bundle_hash,
    }


def cmd_verify(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    start, related = _run_state(events, args.run_id)
    corrections = args.correction_id or []
    blockers = args.blocker_id or []
    if len(corrections) != len(blockers):
        raise WorkMemoryError("paired-correction-blocker-required", 2)
    artifact_hashes: list[str] = []
    environment_artifact_hashes: list[str] = []
    for correction_id in corrections:
        match = next((event for event in events if event["event_type"] == "correction_recorded" and event["correction_id"] == correction_id), None)
        if match is None:
            raise WorkMemoryError("correction-not-found", 3)
        artifact_hashes.extend(match["changed_artifact_hashes"])
        environment_artifact_hashes.extend(
            match.get("environment_artifact_hashes") or []
        )
    event = _event(
        "verification_recorded", args.event_id, run_id=args.run_id, subject_id=start["subject_id"],
        lineage_id=start["lineage_id"], source_bundle_hash=start["source_bundle_hash"],
        outcome=args.outcome, quality=args.quality, evidence=args.evidence,
        blocker_ids=blockers, correction_ids=corrections, changed_artifact_hashes=artifact_hashes,
        **(
            {"environment_artifact_hashes": environment_artifact_hashes}
            if environment_artifact_hashes else {}
        ),
    )
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "event_id": event["event_id"], "changed_artifact_hashes": artifact_hashes}


def cmd_run_close(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    start, related = _run_state(events, args.run_id)
    corrections = [event for event in related if event["event_type"] == "correction_recorded"]
    blockers = sorted({event["blocker_id"] for event in related if "blocker_id" in event})
    verifications = [event for event in related if event["event_type"] == "verification_recorded"]
    transitions = [event for event in events if event["event_type"] == "bundle_transition_recorded" and event.get("run_id") == args.run_id]
    event = _event(
        "run_closed", args.event_id, run_id=args.run_id, subject_id=start["subject_id"],
        lineage_id=start["lineage_id"], result=args.result, completed_at_utc=utc_now(),
        correction_count=len(corrections), blocker_ids=blockers, sequence_updated=bool(transitions),
        verification_quality=verifications[-1]["quality"] if verifications else "none",
    )
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    observer_result: dict[str, Any] = {"ok": True, "status": "DISABLED"}
    observer_mode = getattr(args, "observer", "auto")
    has_context = any(item["event_type"] == "operation_context_recorded" for item in related)
    if observer_mode == "enabled" or (
        observer_mode == "auto" and has_context and os.environ.get("MK_SEQUENCE_OBSERVER_DISABLED") != "1"
    ):
        try:
            try:
                from scripts import sequence_observer
            except ModuleNotFoundError:
                import sequence_observer  # type: ignore
            observer_result = sequence_observer.observe_committed_run(args.run_id)
        except Exception as exc:  # the committed terminal result is never rolled back
            observer_result = {
                "ok": False, "status": "OBSERVER_FAILED",
                "safe_error_code": str(getattr(exc, "code", type(exc).__name__)),
            }
    return {
        **result, "event_id": event["event_id"],
        "metrics": summarize(events + [event], start["subject_id"], start["source_bundle_hash"]),
        "observer": observer_result,
    }


def cmd_run_abandon(args: argparse.Namespace) -> dict[str, Any]:
    events, _ = load_ledger()
    start, _ = _run_state(events, args.run_id)
    event = _event("run_abandoned", args.event_id, run_id=args.run_id, subject_id=start["subject_id"],
                   lineage_id=start["lineage_id"], completed_at_utc=utc_now(), reason=args.reason)
    result = transact({"schema_version": 1, "expected_ledger_hash": None, "events": [event]})
    return {**result, "event_id": event["event_id"]}


def _run_records(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    for event in events:
        run_id = event.get("run_id")
        if event["event_type"] == "run_started":
            runs[run_id] = {"start": event, "events": [event], "terminal": None}
        elif run_id in runs:
            runs[run_id]["events"].append(event)
            if event["event_type"] in {"run_closed", "run_abandoned"}:
                runs[run_id]["terminal"] = event
    return list(runs.values())


def _metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [record for record in records if record["terminal"] and record["terminal"]["event_type"] == "run_closed"]
    verification_events = [event for record in closed for event in record["events"] if event["event_type"] == "verification_recorded"]
    corrections = [event for record in closed for event in record["events"] if event["event_type"] == "correction_recorded"]
    fingerprints: dict[str, set[str]] = defaultdict(set)
    blocker_fingerprints = {
        event["blocker_id"]: event["fingerprint"]
        for record in records for event in record["events"]
        if event["event_type"] == "blocker_opened"
    }
    durations: list[int] = []
    first_pass = 0
    passed = 0
    for record in closed:
        terminal, start = record["terminal"], record["start"]
        passed += terminal["result"] == "passed"
        has_fix = any(event["event_type"] in {"correction_recorded", "blocker_opened", "blocker_recurred"} for event in record["events"])
        first_pass += terminal["result"] == "passed" and not has_fix
        durations.append(int((parse_utc(terminal["completed_at_utc"]) - parse_utc(start["started_at_utc"])).total_seconds() * 1000))
        for event in record["events"]:
            if event["event_type"] == "blocker_opened":
                fingerprints[event["fingerprint"]].add(start["run_id"])
            elif event["event_type"] == "blocker_recurred" and event["blocker_id"] in blocker_fingerprints:
                fingerprints[blocker_fingerprints[event["blocker_id"]]].add(start["run_id"])
    denominator = len(closed)
    return {
        "closed_runs": denominator, "pass_rate": [passed, denominator],
        "first_pass_success_rate": [first_pass, denominator],
        "corrections_per_run": [len(corrections), denominator],
        "repeated_blocker_count": sum(len(ids) >= 2 for ids in fingerprints.values()),
        "same_path_verification_rate": [sum(event["outcome"] == "passed" and event["quality"] == "same-path" for event in verification_events), len(verification_events)],
        "median_duration_ms": int(statistics.median(durations)) if durations else None,
    }


def _ratio_direction(old: list[int], new: list[int], higher_better: bool) -> str:
    old_n, old_d = old; new_n, new_d = new
    if old_d == 0 or new_d == 0:
        return "unchanged" if old_d == new_d else "mixed"
    delta = new_n * old_d - old_n * new_d
    if delta == 0:
        return "unchanged"
    improved = delta > 0 if higher_better else delta < 0
    return "improved" if improved else "regressed"


def _compare(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    left, right = _metrics(before), _metrics(after)
    speed = "unchanged"
    if left["median_duration_ms"] != right["median_duration_ms"]:
        speed = "improved" if right["median_duration_ms"] < left["median_duration_ms"] else "regressed"
    components = {
        "pass_rate": _ratio_direction(left["pass_rate"], right["pass_rate"], True),
        "first_pass_success_rate": _ratio_direction(left["first_pass_success_rate"], right["first_pass_success_rate"], True),
        "corrections_per_run": _ratio_direction(left["corrections_per_run"], right["corrections_per_run"], False),
        "same_path_verification_rate": _ratio_direction(left["same_path_verification_rate"], right["same_path_verification_rate"], True),
        "repeated_blocker_count": "improved" if right["repeated_blocker_count"] < left["repeated_blocker_count"] else ("regressed" if right["repeated_blocker_count"] > left["repeated_blocker_count"] else "unchanged"),
    }
    values = set(components.values())
    quality = "mixed" if {"improved", "regressed"} <= values else ("improved" if "improved" in values else ("regressed" if "regressed" in values else "unchanged"))
    pair = {speed, quality}
    overall = "mixed" if "mixed" in pair or {"improved", "regressed"} <= pair else ("improved" if "improved" in pair else ("regressed" if "regressed" in pair else "unchanged"))
    return {"before": left, "after": right, "component_directions": components,
            "speed_status": speed, "quality_status": quality, "overall_status": overall}


def summarize(events: list[dict[str, Any]], subject_id: str, bundle_hash: str | None = None) -> dict[str, Any]:
    records = [record for record in _run_records(events) if record["start"]["subject_id"] == subject_id]
    if bundle_hash:
        records = [record for record in records if record["start"]["source_bundle_hash"] == bundle_hash]
    closed = [record for record in records if record["terminal"] and record["terminal"]["event_type"] == "run_closed"]
    closed.sort(key=lambda record: (record["start"]["started_at_utc"], record["start"]["run_id"]))
    result = {"subject_id": subject_id, "source_bundle_hash": bundle_hash,
              "metrics": _metrics(closed), "abandoned_runs": sum(
                  1
                  for record in records
                  if record["terminal"]
                  and record["terminal"]["event_type"] == "run_abandoned"
              ),
              "history_status": "insufficient-history", "trend": None, "change_effects": []}
    if len(closed) >= 6:
        result["history_status"] = "sufficient"
        result["trend"] = _compare(closed[-6:-3], closed[-3:])
    transitions = [event for event in events if event["event_type"] == "bundle_transition_recorded" and event["transition_reason"] == "correction"]
    all_records = _run_records(events)
    for transition in transitions:
        transition_run = next((r for r in all_records if r["start"]["run_id"] == transition["run_id"]), None)
        operation_kind = transition_run["start"]["operation_kind"] if transition_run else None
        before = [r for r in all_records if r["start"]["lineage_id"] == transition["lineage_id"] and r["start"]["operation_kind"] == operation_kind and r["start"]["source_bundle_hash"] == transition["old_bundle_hash"] and r["start"]["started_at_utc"] <= transition["recorded_at_utc"] and r["terminal"] and r["terminal"]["event_type"] == "run_closed"][-3:]
        after = [r for r in all_records if r["start"]["lineage_id"] == transition["lineage_id"] and r["start"]["operation_kind"] == operation_kind and r["start"]["source_bundle_hash"] == transition["new_bundle_hash"] and r["start"]["started_at_utc"] > transition["recorded_at_utc"] and r["terminal"] and r["terminal"]["event_type"] == "run_closed"][:3]
        effect: dict[str, Any] = {"transition_event_id": transition["event_id"], "correction_ids": transition["correction_ids"], "old_bundle_hash": transition["old_bundle_hash"], "new_bundle_hash": transition["new_bundle_hash"]}
        if not transition_run or not transition_run["terminal"]:
            effect["status"] = "transition-run-not-terminal"
        elif len(before) < 3 or len(after) < 3:
            effect["status"] = "insufficient-cross-version-history"
        else:
            effect.update(status="sufficient", comparison=_compare(before, after))
        result["change_effects"].append(effect)
    return result


def cmd_transact(args: argparse.Namespace) -> dict[str, Any]:
    raw = sys.stdin.read() if args.request_json == "-" else Path(args.request_json).read_text()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkMemoryError("invalid-request-json", 2) from exc
    return transact(
        request,
        Path(args.ledger).resolve() if args.ledger else None,
        Path(args.view).resolve() if args.view else None,
    )


def cmd_merge_ledger(args: argparse.Namespace) -> dict[str, Any]:
    """Append only events authorized by the canonical ledger's current writer state.

    Ownership history is never trusted merely because it appears in an imported file.
    A multi-writer source must first have its claims and handoffs recorded through the
    canonical ledger; the current owner may then import its still-unseen events.
    """
    target, view = _resolve_ledger_view_pair(
        Path(args.ledger).resolve() if args.ledger else None,
        Path(args.view).resolve() if args.view else None,
    )
    source = Path(args.source_ledger).resolve()
    lock = target.with_suffix(target.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        existing = target.read_bytes() if target.exists() else b""
        source_bytes = source.read_bytes() if source.is_file() else b""
        target_events = parse_ledger_bytes(existing)
        source_events = parse_ledger_bytes(source_bytes)
        target_by_id = _event_index(target_events)
        unseen: list[dict[str, Any]] = []
        for event in source_events:
            prior = target_by_id.get(event["event_id"])
            if prior is not None:
                if prior != event:
                    raise WorkMemoryError("ledger-event-identity-conflict", 4)
                continue
            target_by_id[event["event_id"]] = event
            unseen.append(event)
        reconcile_persisted_source = bool(
            getattr(args, "reconcile_persisted_source", False)
        )
        if unseen and not reconcile_persisted_source:
            writer_thread_id = (
                writer_identity()["writer_id"] if _batch_requires_host_thread(unseen) else None
            )
            _authorize_event_batch(target_events, unseen, writer_thread_id)
        merged = target_events + unseen
        persisted_event_ids = (
            {event["event_id"] for event in target_events + source_events}
            if reconcile_persisted_source
            else set(_event_index(target_events))
        )
        validate_lifecycle(
            merged,
            legacy_premature_fixed_event_ids={
                event["event_id"] for event in target_events + source_events
            },
            legacy_open_terminal_event_ids={
                event["event_id"] for event in (
                    target_events + source_events
                    if reconcile_persisted_source
                    else target_events
                )
                if event["event_type"] == "run_closed"
            },
            legacy_post_terminal_event_ids=persisted_event_ids,
            legacy_nonopen_correction_event_ids=persisted_event_ids,
            legacy_unverified_reopen_event_ids=persisted_event_ids,
        )
        ledger_bytes = b"".join(canonical_bytes(event) for event in merged)
        ledger_hash = sha256_bytes(ledger_bytes)
        view_bytes = render_blocker_view(merged, ledger_hash).encode()
        _atomic_write(target, ledger_bytes)
        _atomic_write(view, view_bytes)
    return {
        "ok": True,
        "previous_ledger_hash": sha256_bytes(existing),
        "ledger_hash": ledger_hash,
        "blocker_view_hash": sha256_bytes(view_bytes),
        "appended_event_count": len(unseen),
    }


def cmd_summary(args: argparse.Namespace) -> dict[str, Any]:
    events, digest = load_ledger(Path(args.ledger).resolve() if args.ledger else LEDGER)
    return {**summarize(events, args.subject_id, args.source_bundle_hash),
            "ledger_hash": digest, "view_stale": blocker_view_stale(digest)}


def cmd_repair_view(args: argparse.Namespace) -> dict[str, Any]:
    ledger, view = _resolve_ledger_view_pair(
        Path(args.ledger).resolve() if args.ledger else None,
        Path(args.view).resolve() if args.view else None,
    )
    lock = ledger.with_suffix(ledger.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        events, digest = load_ledger(ledger)
        data = render_blocker_view(events, digest).encode()
        _atomic_write(view, data)
    return {"ok": True, "ledger_hash": digest, "blocker_view_hash": sha256_bytes(data)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    classify = sub.add_parser("classify")
    classify.add_argument("--task-id", required=True); classify.add_argument("--operation-kind", required=True, choices=sorted(OPERATION_KINDS))
    classify.add_argument("--repeatable", required=True, choices=["yes", "no"]); classify.add_argument("--meaningful-steps", required=True, type=int)
    classify.set_defaults(func=cmd_classify)
    select = sub.add_parser("select")
    select.add_argument("--task-id", required=True); select.add_argument("--sequence-id"); select.add_argument("--discovery-log")
    select.add_argument("--fingerprint"); select.add_argument("--verification-successor-of"); select.add_argument("--verifies-correction-id", action="append")
    select.add_argument("--repo-roots-file"); select.set_defaults(func=cmd_select)
    select_successor = sub.add_parser("select-successor")
    select_successor.add_argument("--predecessor-run-id", required=True)
    select_successor.set_defaults(func=cmd_select_successor)
    handoff = sub.add_parser("task-writer-handoff")
    handoff.add_argument("--task-id", required=True)
    handoff.add_argument("--to-thread-id")
    handoff.add_argument("--to-client-kind", choices=sorted(CLIENT_KINDS))
    handoff.add_argument("--to-session-id")
    handoff.add_argument("--event-id")
    handoff.set_defaults(func=cmd_task_writer_handoff)
    transact_p = sub.add_parser("transact")
    transact_p.add_argument("--request-json", required=True); transact_p.add_argument("--ledger"); transact_p.add_argument("--view")
    transact_p.set_defaults(func=cmd_transact)
    merge_ledger = sub.add_parser("merge-ledger")
    merge_ledger.add_argument("--source-ledger", required=True)
    merge_ledger.add_argument("--ledger"); merge_ledger.add_argument("--view")
    merge_ledger.add_argument("--reconcile-persisted-source", action="store_true")
    merge_ledger.set_defaults(func=cmd_merge_ledger)
    run_start = sub.add_parser("run-start")
    run_start.add_argument("--task-id", required=True); run_start.add_argument("--run-id"); run_start.add_argument("--event-id")
    run_start.set_defaults(func=cmd_run_start)
    operation_context = sub.add_parser("record-operation-context")
    operation_context.add_argument("--run-id", required=True)
    operation_context.add_argument("--context-file", required=True)
    operation_context.set_defaults(func=cmd_record_operation_context)
    execution_claim = sub.add_parser("execution-claim")
    execution_claim.add_argument("--run-id", required=True); execution_claim.add_argument("--context-id", required=True)
    execution_claim.add_argument("--step-ordinal", required=True, type=int); execution_claim.add_argument("--step-id", required=True)
    execution_claim.add_argument("--argv-json", required=True)
    execution_claim.add_argument("--command-source", required=True, choices=sorted(candidate_contract.PROVENANCE_CLASSES))
    execution_claim.add_argument("--source-ref-repository", required=True); execution_claim.add_argument("--source-ref-path", required=True)
    execution_claim.add_argument("--repository-roots-hash", required=True)
    execution_claim.set_defaults(func=cmd_execution_claim)
    execution_return = sub.add_parser("execution-return")
    execution_return.add_argument("--execution-id", required=True); execution_return.add_argument("--exit-code", required=True, type=int)
    execution_return.set_defaults(func=cmd_execution_return)
    observer_decision = sub.add_parser("observer-decision-append")
    observer_decision.add_argument("--decision-file", required=True)
    observer_decision.set_defaults(func=cmd_observer_decision_append)
    observer_bootstrap = sub.add_parser("observer-bootstrap-result-append")
    observer_bootstrap.add_argument("--result-file", required=True)
    observer_bootstrap.set_defaults(func=cmd_observer_bootstrap_result_append)
    observer_link = sub.add_parser("observer-link-append")
    observer_link.add_argument("--link-file", required=True)
    observer_link.set_defaults(func=cmd_observer_link_append)
    correct = sub.add_parser("correct")
    correct.add_argument("--run-id", required=True); correct.add_argument("--blocker-id", required=True); correct.add_argument("--occurrence-id", required=True)
    correct.add_argument("--co-blocker-id", action="append")
    correct.add_argument("--step-id", required=True); correct.add_argument("--changed-artifact", action="append")
    correct.add_argument(
        "--changed-environment-artifact", action="append",
        help="a machine/host surface the fix changed (config or registry outside any sequence "
             "dependency bundle); hashed and recorded separately from bundle drift",
    )
    correct.add_argument("--solution", required=True); correct.add_argument("--reusable-behavior-changed", choices=["yes", "no"], required=True)
    correct.add_argument("--supersedes-correction-id", action="append")
    correct.add_argument("--co-supersedes-correction-id", action="append")
    correct.add_argument("--correction-id"); correct.add_argument("--event-id"); correct.add_argument("--transition-event-id")
    correct.add_argument("--repo-roots-file"); correct.add_argument("--finalize-failed-run", action="store_true")
    correct.set_defaults(func=cmd_correct)
    preserve = sub.add_parser("preserve-corrections")
    preserve.add_argument("--task-id", required=True)
    preserve.add_argument("--preserved-task-id", required=True)
    preserve.add_argument("--target-correction-id", required=True)
    preserve.add_argument("--target-verification-event-id", required=True)
    preserve.add_argument("--preserved-correction-id", action="append", required=True)
    preserve.add_argument("--event-id")
    preserve.set_defaults(func=cmd_preserve_corrections)
    verify = sub.add_parser("verify")
    verify.add_argument("--run-id", required=True); verify.add_argument("--outcome", choices=["passed", "failed"], required=True)
    verify.add_argument("--quality", choices=["proxy", "same-path"], required=True); verify.add_argument("--evidence", required=True)
    verify.add_argument("--blocker-id", action="append"); verify.add_argument("--correction-id", action="append"); verify.add_argument("--event-id")
    verify.set_defaults(func=cmd_verify)
    close = sub.add_parser("run-close")
    close.add_argument("--run-id", required=True); close.add_argument("--result", choices=["passed", "failed"], required=True); close.add_argument("--event-id")
    close.add_argument("--observer", choices=["auto", "enabled", "disabled"], default="auto")
    close.set_defaults(func=cmd_run_close)
    abandon = sub.add_parser("run-abandon")
    abandon.add_argument("--run-id", required=True); abandon.add_argument("--reason", required=True); abandon.add_argument("--event-id")
    abandon.set_defaults(func=cmd_run_abandon)
    summary = sub.add_parser("summary")
    summary.add_argument("--subject-id", required=True); summary.add_argument("--source-bundle-hash"); summary.add_argument("--ledger")
    summary.set_defaults(func=cmd_summary)
    repair = sub.add_parser("repair-view")
    repair.add_argument("--ledger"); repair.add_argument("--view"); repair.set_defaults(func=cmd_repair_view)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = args.func(args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except WorkMemoryError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
