#!/usr/bin/env python3
"""Deterministic state controller for a bounded research package."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA_VERSION = 1
HASH_CONTRACT = "sha256-canonical-json-utf8-no-trailing-newline-v1"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
LENSES = (
    "INTERNAL_READINESS",
    "REQUIREMENTS_COVERAGE",
    "REQUIREMENTS_SATISFACTION",
)
LENS_VERDICTS = {"PASS", "GAPS", "BLOCKED"}
PACKAGE_VERDICTS = {"IN_PROGRESS", "PASS", "BLOCKED", "CAP_REACHED"}
OPERATIONAL_MATURITIES = {"CURRENT_RUNTIME", "FUTURE_SYSTEM", "MIXED"}
ATOMIC_OPERATIONAL_MATURITIES = {"CURRENT_RUNTIME", "FUTURE_SYSTEM"}
EVIDENCE_AVAILABILITIES = {
    "AVAILABLE",
    "MISSING_REQUIRED",
    "NOT_YET_APPLICABLE",
    "EXTERNAL_BLOCKED",
}
RESEARCH_VALUE_TYPES = {"boolean", "number", "string", "array", "object", "null"}
FINDING_TYPES = {
    "FACT_GAP",
    "REQUIREMENT_GAP",
    "SATISFACTION_GAP",
    "CONTRADICTION",
    "EVIDENCE_LIMIT",
    "SCOPE_CHANGE",
    "PLANNER_DECISION",
    "NON_GAP",
}
MATERIALITIES = {"BLOCKER", "PLANNING", "CLEANUP"}
DISPOSITIONS = {
    "FIX_IN_RESEARCH",
    "HANDOFF_TO_PLANNER",
    "REQUEST_SCOPE_APPROVAL",
    "BLOCKED_ON_EVIDENCE",
    "ACCEPT_LIMITATION",
    "MERGE_DUPLICATE",
    "REJECT_NON_GAP",
}
FINDING_STATUSES = {"OPEN", "CLOSED"}
RAW_FINDING_REQUIRED_FIELDS = {
    "id",
    "fingerprint",
    "lens",
    "originating_stage",
    "requirement_ids",
    "type",
    "materiality",
    "practical_consequence",
    "evidence",
    "proposed_disposition",
    "status",
}
RAW_FINDING_OPTIONAL_FIELDS = {"evidence_limitation", "closure_evidence"}
PASS_BLOCKING_DISPOSITIONS = {
    "FIX_IN_RESEARCH",
    "REQUEST_SCOPE_APPROVAL",
    "BLOCKED_ON_EVIDENCE",
}
ATTEMPT_STATUSES = {"SUCCEEDED", "FAILED"}
CORE_RESEARCHER_ROLE = "CORE_RESEARCHER"
ADJUDICATOR_ROLE = "ADJUDICATOR"
REQUIRED_ROLES = (CORE_RESEARCHER_ROLE, *LENSES, ADJUDICATOR_ROLE)
MAX_ROUNDS = 3
MAX_ATTEMPTS = 15
MAX_MINUTES = 60
MAX_ROLE_RETRIES = 1
CHARTER_BUDGET_FIELDS = {
    "maximum_candidate_rounds": ("max_rounds", MAX_ROUNDS, False),
    "maximum_agent_spawn_attempts": ("max_attempts", MAX_ATTEMPTS, False),
    "maximum_elapsed_minutes": ("max_minutes", MAX_MINUTES, False),
    "maximum_retries_per_role": ("max_role_retries", MAX_ROLE_RETRIES, True),
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIREMENT_FIELDS = {
    "id",
    "text",
    "source",
    "operational_maturity",
    "evidence_availability",
    "acceptance_intent",
    "scope_id",
    "research_value_type",
    "planner_obligations",
}


class ResearchPackageError(ValueError):
    """Raised when an operation violates the research-package contract."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | str | None) -> datetime:
    if value is None:
        return utc_now()
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ResearchPackageError("timestamps must include a timezone")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime | str | None = None) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _reject_non_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ResearchPackageError("canonical JSON does not permit non-finite numbers")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ResearchPackageError("canonical JSON object keys must be strings")
            _reject_non_finite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_non_finite(item)


def canonical_json(value: Any) -> str:
    """Return UTF-8-compatible canonical JSON for hashing and comparisons."""
    _reject_non_finite(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ResearchPackageError(f"value is not canonical-JSON serializable: {exc}") from exc


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def hash_json_file(path: Path | str) -> dict[str, str]:
    source = Path(path)
    value = _read_json(str(source))
    return {
        "hash_contract": HASH_CONTRACT,
        "canonical_json_sha256": canonical_hash(value),
        "file_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def stable_id(kind: str, *identity: Any) -> str:
    if not kind or not re.fullmatch(r"[a-z][a-z0-9-]*", kind):
        raise ResearchPackageError("stable ID kind must be lowercase kebab-case")
    return f"{kind}-{canonical_hash(list(identity))[:24]}"


def atomic_write(path: Path | str, state: dict[str, Any]) -> None:
    """Atomically replace a state file with deterministic, human-readable JSON."""
    target = Path(path)
    canonical_json(state)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _validate_maturity(value: str) -> None:
    if value not in OPERATIONAL_MATURITIES:
        raise ResearchPackageError("operational_maturity must be CURRENT_RUNTIME, FUTURE_SYSTEM, or MIXED")


def _validate_evidence_availability(value: Any) -> None:
    if isinstance(value, str):
        if value not in EVIDENCE_AVAILABILITIES:
            raise ResearchPackageError(
                "evidence availability must be AVAILABLE, MISSING_REQUIRED, NOT_YET_APPLICABLE, or EXTERNAL_BLOCKED"
            )
        return
    if isinstance(value, list):
        for item in value:
            _validate_evidence_availability(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            _validate_evidence_availability(item)
        return
    raise ResearchPackageError("evidence_availability must be a status, list, or object")


def budget_values(charter: Any) -> dict[str, int]:
    """Return the immutable controller budget declared by a frozen charter."""
    if not isinstance(charter, dict):
        raise ResearchPackageError("charter must be an object")
    raw_budget = charter.get("budget")
    if raw_budget is None:
        raw_budget = {
            source: default
            for source, (_target, default, _allow_zero) in CHARTER_BUDGET_FIELDS.items()
        }
    if not isinstance(raw_budget, dict):
        raise ResearchPackageError("charter budget must be an object")
    expected_fields = set(CHARTER_BUDGET_FIELDS)
    if set(raw_budget) != expected_fields:
        missing = sorted(expected_fields - set(raw_budget))
        unsupported = sorted(set(raw_budget) - expected_fields)
        raise ResearchPackageError(
            f"charter budget must contain exactly the four governed fields; "
            f"missing={missing}, unsupported={unsupported}"
        )
    values: dict[str, int] = {}
    for source, (target, default, allow_zero) in CHARTER_BUDGET_FIELDS.items():
        value = raw_budget[source]
        if isinstance(value, bool) or not isinstance(value, int) or value < (0 if allow_zero else 1):
            qualifier = "a non-negative integer" if allow_zero else "a positive integer"
            raise ResearchPackageError(f"charter budget {source} must be {qualifier}")
        values[target] = value
    return values


def _research_value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise ResearchPackageError("research_value must be a canonical JSON value")


def _normalize_requirements(requirements: Any) -> list[dict[str, Any]]:
    entries = requirements.get("requirements") if isinstance(requirements, dict) else requirements
    if not isinstance(entries, list) or not entries:
        raise ResearchPackageError("requirements must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_obligations: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ResearchPackageError("every requirement must be a JSON object")
        unsupported = sorted(set(entry) - REQUIREMENT_FIELDS)
        if unsupported:
            raise ResearchPackageError("frozen requirements contain unsupported fields: " + ", ".join(unsupported))
        missing = sorted(REQUIREMENT_FIELDS - entry.keys())
        if missing:
            raise ResearchPackageError(
                "every frozen atomic requirement must include: " + ", ".join(sorted(REQUIREMENT_FIELDS))
            )
        for field in ("id", "text", "scope_id"):
            if not isinstance(entry[field], str) or not entry[field].strip():
                raise ResearchPackageError(f"every requirement must have a non-empty string {field}")
        for field in ("source", "acceptance_intent"):
            if entry[field] in (None, "", [], {}):
                raise ResearchPackageError(f"every requirement must have a non-empty {field}")
            canonical_json(entry[field])
        if entry["id"] in seen:
            raise ResearchPackageError(f"duplicate requirement id: {entry['id']}")
        if entry["operational_maturity"] not in ATOMIC_OPERATIONAL_MATURITIES:
            raise ResearchPackageError(
                "frozen atomic requirement operational_maturity must be "
                "CURRENT_RUNTIME or FUTURE_SYSTEM; MIXED is aggregate/intake only"
            )
        if not isinstance(entry["evidence_availability"], str):
            raise ResearchPackageError("frozen atomic requirement evidence_availability must be one status")
        _validate_evidence_availability(entry["evidence_availability"])
        if entry["research_value_type"] not in RESEARCH_VALUE_TYPES:
            raise ResearchPackageError(
                "frozen atomic requirement research_value_type must be boolean, number, "
                "string, array, object, or null"
            )
        obligations = entry["planner_obligations"]
        if not isinstance(obligations, list):
            raise ResearchPackageError("planner_obligations must be a list")
        for obligation in obligations:
            if not isinstance(obligation, dict) or set(obligation) != {
                "id",
                "description",
            }:
                raise ResearchPackageError("every planner obligation must contain only id and description")
            if any(
                not isinstance(obligation[field], str) or not obligation[field].strip()
                for field in ("id", "description")
            ):
                raise ResearchPackageError("planner obligation id and description must be non-empty strings")
            if obligation["id"] in seen_obligations:
                raise ResearchPackageError(f"duplicate planner obligation id: {obligation['id']}")
            seen_obligations.add(obligation["id"])
        seen.add(entry["id"])
        normalized.append(copy.deepcopy(entry))
    return normalized


def _scope_payload(charter: Any, requirements: Any, operational_maturity: str) -> dict[str, Any]:
    _validate_maturity(operational_maturity)
    return {
        "charter": copy.deepcopy(charter),
        "requirements": _normalize_requirements(requirements),
        "operational_maturity": operational_maturity,
    }


def create_state(
    charter: Any,
    requirements: Any,
    operational_maturity: str,
    evidence_availability: Any,
    *,
    started_at: datetime | str | None = None,
) -> dict[str, Any]:
    scope = _scope_payload(charter, requirements, operational_maturity)
    _validate_evidence_availability(evidence_availability)
    canonical_json(evidence_availability)
    scope_hash = canonical_hash(scope)
    started = _as_utc(started_at)
    started_text = _timestamp(started)
    budgets = budget_values(scope["charter"])
    return {
        "schema_version": SCHEMA_VERSION,
        "package_id": stable_id("research-package", scope_hash),
        "verdict": "IN_PROGRESS",
        "charter": scope["charter"],
        "charter_hash": canonical_hash(scope["charter"]),
        "requirements": scope["requirements"],
        "requirements_hash": canonical_hash(scope["requirements"]),
        "operational_maturity": operational_maturity,
        "evidence_availability": copy.deepcopy(evidence_availability),
        "scope_hash": scope_hash,
        "budgets": {
            **budgets,
            "started_at": started_text,
            "deadline_at": _timestamp(started + timedelta(minutes=budgets["max_minutes"])),
        },
        "candidates": {},
        "attempts": [],
        "rounds": [],
        "result": {
            "verdict": "IN_PROGRESS",
            "reason": "AWAITING_REQUIRED_ATTEMPTS",
            "candidate_hash": None,
            "envelope_hash": None,
            "actionable_fingerprints": [],
        },
        "created_at": started_text,
        "updated_at": started_text,
    }


def _expected_scope_hash(state: dict[str, Any]) -> str:
    return canonical_hash(
        {
            "charter": state["charter"],
            "requirements": state["requirements"],
            "operational_maturity": state["operational_maturity"],
        }
    )


def validate_state(state: dict[str, Any]) -> None:
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ResearchPackageError("unsupported research-package schema_version")
    required = {
        "package_id",
        "verdict",
        "charter",
        "charter_hash",
        "requirements",
        "requirements_hash",
        "operational_maturity",
        "evidence_availability",
        "scope_hash",
        "budgets",
        "candidates",
        "attempts",
        "rounds",
        "result",
    }
    missing = sorted(required - state.keys())
    if missing:
        raise ResearchPackageError(f"state is missing required fields: {', '.join(missing)}")
    _validate_maturity(state["operational_maturity"])
    _validate_evidence_availability(state["evidence_availability"])
    normalized_requirements = _normalize_requirements(state["requirements"])
    if normalized_requirements != state["requirements"]:
        raise ResearchPackageError("frozen requirements are not canonical")
    if state["verdict"] not in PACKAGE_VERDICTS:
        raise ResearchPackageError("state has an invalid package verdict")
    if state["charter_hash"] != canonical_hash(state["charter"]):
        raise ResearchPackageError("frozen charter hash does not match charter")
    if state["requirements_hash"] != canonical_hash(state["requirements"]):
        raise ResearchPackageError("frozen requirements hash does not match requirements")
    if state["scope_hash"] != _expected_scope_hash(state):
        raise ResearchPackageError("frozen scope hash does not match package scope")
    expected_id = stable_id("research-package", state["scope_hash"])
    if state["package_id"] != expected_id:
        raise ResearchPackageError("package_id does not match frozen scope")
    budgets = state["budgets"]
    expected_budgets = budget_values(state["charter"])
    required_budget_fields = {*expected_budgets, "started_at", "deadline_at"}
    if not isinstance(budgets, dict) or set(budgets) != required_budget_fields:
        raise ResearchPackageError("persisted budget fields do not match the frozen budget contract")
    for key, value in expected_budgets.items():
        if budgets.get(key) != value:
            raise ResearchPackageError(f"budget {key} must remain {value}")
    started_at = _as_utc(budgets["started_at"])
    expected_deadline = _timestamp(started_at + timedelta(minutes=expected_budgets["max_minutes"]))
    if budgets["deadline_at"] != expected_deadline:
        raise ResearchPackageError("budget deadline_at does not match frozen started_at plus max_minutes")
    if not isinstance(state["candidates"], dict):
        raise ResearchPackageError("candidates must be an object")
    for candidate_id, candidate_record in state["candidates"].items():
        required_candidate_fields = {
            "candidate_id",
            "candidate_hash",
            "envelope_hash",
            "candidate_payload",
            "envelope_payload",
            "evidence_availability",
            "recorded_at",
        }
        if (
            not isinstance(candidate_record, dict)
            or not required_candidate_fields.issubset(candidate_record)
            or candidate_record.get("candidate_id") != candidate_id
        ):
            raise ResearchPackageError("candidate record is incomplete or misidentified")
        if candidate_record["candidate_hash"] != canonical_hash(candidate_record["candidate_payload"]):
            raise ResearchPackageError("candidate payload hash does not match")
        if candidate_record["envelope_hash"] != canonical_hash(candidate_record["envelope_payload"]):
            raise ResearchPackageError("candidate envelope hash does not match")
        _validate_evidence_availability(candidate_record["evidence_availability"])
    if not isinstance(state["attempts"], list):
        raise ResearchPackageError("attempts must be a list")
    seen_runtime_ids: set[str] = set()
    per_round_envelopes: dict[int, str] = {}
    per_round_role_counts: dict[tuple[int, str], int] = {}
    for attempt in state["attempts"]:
        required_attempt_fields = {
            "runtime_agent_id",
            "role",
            "round",
            "candidate_hash",
            "input_envelope_hash",
            "status",
            "output_hash",
            "slot_closed",
            "close_evidence",
            "recorded_at",
        }
        if not isinstance(attempt, dict) or not required_attempt_fields.issubset(attempt):
            raise ResearchPackageError("attempt is missing required lifecycle evidence")
        runtime_agent_id = attempt["runtime_agent_id"]
        if not isinstance(runtime_agent_id, str) or not runtime_agent_id or runtime_agent_id in seen_runtime_ids:
            raise ResearchPackageError("runtime_agent_id must be non-empty and unique")
        seen_runtime_ids.add(runtime_agent_id)
        if attempt["role"] not in REQUIRED_ROLES:
            raise ResearchPackageError("attempt has an invalid research-package role")
        if attempt["status"] not in ATTEMPT_STATUSES:
            raise ResearchPackageError("attempt has an invalid status")
        candidate_hash = attempt["candidate_hash"]
        pre_candidate_core_failure = (
            candidate_hash is None
            and attempt["role"] == CORE_RESEARCHER_ROLE
            and attempt["status"] == "FAILED"
            and attempt["round"] == 1
        )
        if not pre_candidate_core_failure and (
            not isinstance(candidate_hash, str) or not _SHA256_RE.fullmatch(candidate_hash)
        ):
            raise ResearchPackageError("attempt candidate_hash is invalid")
        if attempt["output_hash"] is not None and (
            not isinstance(attempt["output_hash"], str) or not _SHA256_RE.fullmatch(attempt["output_hash"])
        ):
            raise ResearchPackageError("attempt output_hash is invalid")
        if not _attempt_lifecycle_complete(attempt):
            raise ResearchPackageError("attempt lifecycle evidence is incomplete")
        round_number = attempt["round"]
        if not isinstance(round_number, int) or not 1 <= round_number <= budgets["max_rounds"]:
            raise ResearchPackageError("attempt round is outside the round budget")
        envelope_hash = attempt["input_envelope_hash"]
        if not isinstance(envelope_hash, str) or not _SHA256_RE.fullmatch(envelope_hash):
            raise ResearchPackageError("attempt input_envelope_hash is invalid")
        prior_envelope = per_round_envelopes.setdefault(round_number, envelope_hash)
        if prior_envelope != envelope_hash:
            raise ResearchPackageError("attempts in one round must retain an identical input_envelope_hash")
        key = (round_number, attempt["role"])
        per_round_role_counts[key] = per_round_role_counts.get(key, 0) + 1
        if per_round_role_counts[key] > 1 + budgets["max_role_retries"]:
            raise ResearchPackageError("round+role retry budget was exceeded")
    _validate_round_records(state)


def load_state(path: Path | str) -> dict[str, Any]:
    try:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchPackageError(f"cannot load research package: {exc}") from exc
    if not isinstance(state, dict):
        raise ResearchPackageError("research-package state must be a JSON object")
    validate_state(state)
    return state


def scope_check(
    state: dict[str, Any],
    charter: Any,
    requirements: Any,
    operational_maturity: str,
) -> dict[str, Any]:
    validate_state(state)
    proposed_hash = canonical_hash(_scope_payload(charter, requirements, operational_maturity))
    if proposed_hash != state["scope_hash"]:
        return {
            "verdict": "BLOCKED",
            "reason": "SCOPE_CHANGE",
            "package_id": state["package_id"],
            "current_scope_hash": state["scope_hash"],
            "proposed_scope_hash": proposed_hash,
        }
    return {
        "verdict": state["verdict"],
        "reason": "SCOPE_UNCHANGED",
        "package_id": state["package_id"],
        "scope_hash": state["scope_hash"],
    }


def initialize_file(
    path: Path | str,
    charter: Any,
    requirements: Any,
    operational_maturity: str,
    evidence_availability: Any,
    *,
    started_at: datetime | str | None = None,
) -> dict[str, Any]:
    target = Path(path)
    if target.exists():
        state = load_state(target)
        return scope_check(state, charter, requirements, operational_maturity)
    state = create_state(
        charter,
        requirements,
        operational_maturity,
        evidence_availability,
        started_at=started_at,
    )
    atomic_write(target, state)
    return {
        "verdict": "IN_PROGRESS",
        "reason": "INITIALIZED",
        "package_id": state["package_id"],
        "scope_hash": state["scope_hash"],
    }


def _set_result(
    state: dict[str, Any],
    verdict: str,
    reason: str,
    *,
    candidate_hash: str | None = None,
    envelope_hash: str | None = None,
    actionable_fingerprints: Sequence[str] = (),
) -> None:
    state["verdict"] = verdict
    state["result"] = {
        "verdict": verdict,
        "reason": reason,
        "candidate_hash": candidate_hash,
        "envelope_hash": envelope_hash,
        "actionable_fingerprints": sorted(set(actionable_fingerprints)),
    }


def _touch(state: dict[str, Any], now: datetime | str | None) -> None:
    state["updated_at"] = _timestamp(now)


def _cap(state: dict[str, Any], reason: str, now: datetime | str | None) -> dict[str, Any]:
    _set_result(state, "CAP_REACHED", reason)
    _touch(state, now)
    return copy.deepcopy(state["result"])


def _terminal_result(state: dict[str, Any]) -> dict[str, Any] | None:
    if state["verdict"] in {"PASS", "CAP_REACHED"}:
        return copy.deepcopy(state["result"])
    return None


def _candidate_by_hashes(state: dict[str, Any], candidate_hash: str, envelope_hash: str) -> dict[str, Any]:
    candidate_id = stable_id("candidate", state["package_id"], candidate_hash, envelope_hash)
    candidate = state["candidates"].get(candidate_id)
    if candidate is None:
        raise ResearchPackageError("candidate/envelope hash pair has not been recorded")
    return candidate


def _candidate_requirement_statuses(state: dict[str, Any], candidate: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(candidate, dict):
        raise ResearchPackageError("candidate must be a JSON object")
    statuses = candidate.get("requirement_statuses")
    if not isinstance(statuses, list):
        raise ResearchPackageError("candidate must include requirement_statuses")
    by_id: dict[str, dict[str, Any]] = {}
    requirements_by_id = {item["id"]: item for item in state["requirements"]}
    for status in statuses:
        if not isinstance(status, dict) or set(status) != {
            "requirement_id",
            "research_value",
            "evidence_ids",
        }:
            raise ResearchPackageError(
                "every requirement status must contain requirement_id, research_value, and evidence_ids"
            )
        requirement_id = status["requirement_id"]
        evidence_ids = status["evidence_ids"]
        if not isinstance(requirement_id, str) or not requirement_id or requirement_id in by_id:
            raise ResearchPackageError("requirement status ids must be non-empty and unique")
        if (
            not isinstance(evidence_ids, list)
            or any(not isinstance(item, str) or not item for item in evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
        ):
            raise ResearchPackageError("requirement status evidence_ids must be unique non-empty strings")
        canonical_json(status["research_value"])
        requirement = requirements_by_id.get(requirement_id)
        if requirement is not None:
            actual_type = _research_value_type(status["research_value"])
            expected_type = requirement["research_value_type"]
            if actual_type != expected_type:
                raise ResearchPackageError(
                    f"requirement {requirement_id} research_value must have type "
                    f"{expected_type}, got {actual_type}"
                )
        by_id[requirement_id] = copy.deepcopy(status)
    required_ids = {item["id"] for item in state["requirements"]}
    if set(by_id) != required_ids:
        raise ResearchPackageError("requirement statuses must cover frozen requirements exactly")
    return by_id


def _candidate_material_gaps(candidate: Any) -> list[str]:
    if not isinstance(candidate, dict):
        raise ResearchPackageError("candidate must be a JSON object")
    material_gaps = candidate.get("material_gaps")
    if (
        not isinstance(material_gaps, list)
        or any(not isinstance(item, str) or not item.strip() for item in material_gaps)
        or len(material_gaps) != len(set(material_gaps))
    ):
        raise ResearchPackageError(
            "candidate material_gaps must be a list of unique non-empty strings"
        )
    return list(material_gaps)


def _require_candidate_gap_classification(
    candidate: Any, adjudications: list[dict[str, Any]]
) -> None:
    declared = set(_candidate_material_gaps(candidate))
    classified = {
        item["raw_finding"]["id"]
        for item in adjudications
        if isinstance(item, dict)
        and isinstance(item.get("raw_finding"), dict)
        and isinstance(item["raw_finding"].get("id"), str)
    }
    missing = sorted(declared - classified)
    if missing:
        raise ResearchPackageError(
            f"adjudication omits candidate material gaps: {missing}"
        )


def record_candidate(
    state: dict[str, Any],
    candidate: Any,
    envelope: Any,
    *,
    evidence_availability: Any | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    validate_state(state)
    _candidate_requirement_statuses(state, candidate)
    _candidate_material_gaps(candidate)
    candidate_hash = canonical_hash(candidate)
    envelope_hash = canonical_hash(envelope)
    candidate_id = stable_id("candidate", state["package_id"], candidate_hash, envelope_hash)
    availability = state["evidence_availability"] if evidence_availability is None else evidence_availability
    _validate_evidence_availability(availability)
    canonical_json(availability)
    existing = state["candidates"].get(candidate_id)
    if existing is not None:
        expected = {
            "candidate_id": candidate_id,
            "candidate_hash": candidate_hash,
            "envelope_hash": envelope_hash,
            "candidate_payload": copy.deepcopy(candidate),
            "envelope_payload": copy.deepcopy(envelope),
            "evidence_availability": copy.deepcopy(availability),
        }
        if any(existing.get(key) != value for key, value in expected.items()):
            raise ResearchPackageError("candidate identity conflicts with existing record")
        return {
            "verdict": state["verdict"],
            "reason": "CANDIDATE_ALREADY_RECORDED",
            "hash_contract": HASH_CONTRACT,
            **expected,
        }
    terminal = _terminal_result(state)
    if terminal is not None:
        return terminal
    record = {
        "candidate_id": candidate_id,
        "candidate_hash": candidate_hash,
        "envelope_hash": envelope_hash,
        "candidate_payload": copy.deepcopy(candidate),
        "envelope_payload": copy.deepcopy(envelope),
        "evidence_availability": copy.deepcopy(availability),
        "recorded_at": _timestamp(now),
    }
    state["candidates"][candidate_id] = record
    _touch(state, now)
    return {
        "verdict": state["verdict"],
        "reason": "CANDIDATE_RECORDED",
        "hash_contract": HASH_CONTRACT,
        **copy.deepcopy(record),
    }


def record_attempt(
    state: dict[str, Any],
    *,
    runtime_agent_id: str,
    role: str,
    round_number: int,
    candidate_hash: str | None,
    input_envelope_hash: str,
    status: str,
    output_hash: str | None,
    slot_closed: bool,
    close_evidence: Any,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    validate_state(state)
    if not isinstance(runtime_agent_id, str) or not runtime_agent_id.strip():
        raise ResearchPackageError("runtime_agent_id must be a non-empty string")
    if role not in REQUIRED_ROLES:
        raise ResearchPackageError(f"attempt role must be one of: {', '.join(REQUIRED_ROLES)}")
    if status not in ATTEMPT_STATUSES:
        raise ResearchPackageError("attempt status must be SUCCEEDED or FAILED")
    if not isinstance(input_envelope_hash, str) or not _SHA256_RE.fullmatch(input_envelope_hash):
        raise ResearchPackageError("input_envelope_hash must be a lowercase SHA-256 hash")
    if status == "SUCCEEDED" and (not isinstance(output_hash, str) or not _SHA256_RE.fullmatch(output_hash)):
        raise ResearchPackageError("successful attempts require a lowercase SHA-256 output_hash")
    if output_hash is not None and (not isinstance(output_hash, str) or not _SHA256_RE.fullmatch(output_hash)):
        raise ResearchPackageError("output_hash must be a lowercase SHA-256 hash or null")
    if slot_closed is not True:
        raise ResearchPackageError("every attempt must close its slot with slot_closed=true")
    if close_evidence in (None, "", [], {}):
        raise ResearchPackageError("every attempt must retain non-empty close_evidence")
    canonical_json(close_evidence)
    if not 1 <= round_number <= state["budgets"]["max_rounds"]:
        terminal = _terminal_result(state)
        if terminal is not None:
            return terminal
        return _cap(state, "ROUND_BUDGET", now)
    pre_candidate_core_failure = (
        candidate_hash is None
        and role == CORE_RESEARCHER_ROLE
        and status == "FAILED"
        and round_number == 1
        and not state["candidates"]
    )
    if not pre_candidate_core_failure:
        if not isinstance(candidate_hash, str) or not _SHA256_RE.fullmatch(candidate_hash):
            raise ResearchPackageError("candidate_hash must be a lowercase SHA-256 hash")
        _candidate_by_hashes(state, candidate_hash, input_envelope_hash)
    if any(item["runtime_agent_id"] == runtime_agent_id for item in state["attempts"]):
        raise ResearchPackageError("runtime_agent_id cannot be reused")
    round_attempts = [item for item in state["attempts"] if item["round"] == round_number]
    if any(item["input_envelope_hash"] != input_envelope_hash for item in round_attempts):
        raise ResearchPackageError("every attempt in a round must use the identical input_envelope_hash")
    terminal = _terminal_result(state)
    if terminal is not None:
        return terminal
    if len(state["attempts"]) >= state["budgets"]["max_attempts"]:
        return _cap(state, "ATTEMPT_BUDGET", now)
    prior_spawns = sum(item["round"] == round_number and item["role"] == role for item in state["attempts"])
    if prior_spawns >= 1 + state["budgets"]["max_role_retries"]:
        return _cap(state, "ROLE_RETRY_BUDGET", now)
    record = {
        "runtime_agent_id": runtime_agent_id,
        "role": role,
        "round": round_number,
        "candidate_hash": candidate_hash,
        "input_envelope_hash": input_envelope_hash,
        "status": status,
        "output_hash": output_hash,
        "slot_closed": True,
        "close_evidence": copy.deepcopy(close_evidence),
        "recorded_at": _timestamp(now),
    }
    state["attempts"].append(record)
    _evaluate(state, now)
    _touch(state, now)
    return {
        "verdict": state["verdict"],
        "reason": "ATTEMPT_RECORDED",
        **copy.deepcopy(record),
    }


def finding_fingerprint(raw_finding: Any) -> str:
    return canonical_hash(raw_finding)


def _require_non_empty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ResearchPackageError(f"raw finding {field} must be a non-empty string")


def _validate_finding_evidence(value: Any, field: str) -> None:
    if isinstance(value, str):
        _require_non_empty_string(value, field)
        return
    if isinstance(value, list) and value and all(isinstance(item, str) and item.strip() for item in value):
        return
    raise ResearchPackageError(
        f"raw finding {field} must be a non-empty string or a non-empty list of non-empty strings"
    )


def _validate_raw_findings(raw_findings: Any, lens: str) -> list[dict[str, Any]]:
    if not isinstance(raw_findings, list):
        raise ResearchPackageError("raw_findings must be a JSON list")
    validated: list[dict[str, Any]] = []
    for raw_finding in raw_findings:
        if not isinstance(raw_finding, dict):
            raise ResearchPackageError("every raw finding must be a JSON object")
        missing = sorted(RAW_FINDING_REQUIRED_FIELDS - raw_finding.keys())
        extra = sorted(set(raw_finding) - RAW_FINDING_REQUIRED_FIELDS - RAW_FINDING_OPTIONAL_FIELDS)
        if missing or extra:
            details = []
            if missing:
                details.append("missing: " + ", ".join(missing))
            if extra:
                details.append("unsupported: " + ", ".join(extra))
            raise ResearchPackageError("raw finding keys must match the exact contract (" + "; ".join(details) + ")")

        for field in (
            "id",
            "fingerprint",
            "lens",
            "originating_stage",
            "type",
            "materiality",
            "practical_consequence",
            "proposed_disposition",
            "status",
        ):
            _require_non_empty_string(raw_finding[field], field)
        if raw_finding["lens"] != lens:
            raise ResearchPackageError("raw finding lens must equal the invoked lens role")
        if raw_finding["originating_stage"] != "RESEARCH":
            raise ResearchPackageError("raw finding originating_stage must be RESEARCH")
        if raw_finding["type"] not in FINDING_TYPES:
            raise ResearchPackageError(f"raw finding type must be one of: {', '.join(sorted(FINDING_TYPES))}")
        if raw_finding["materiality"] not in MATERIALITIES:
            raise ResearchPackageError("raw finding materiality must be one of: " + ", ".join(sorted(MATERIALITIES)))
        if raw_finding["proposed_disposition"] not in DISPOSITIONS:
            raise ResearchPackageError(
                "raw finding proposed_disposition must be one of: " + ", ".join(sorted(DISPOSITIONS))
            )
        if raw_finding["status"] not in FINDING_STATUSES:
            raise ResearchPackageError("raw finding status must be OPEN or CLOSED")

        requirement_ids = raw_finding["requirement_ids"]
        if (
            not isinstance(requirement_ids, list)
            or not requirement_ids
            or any(not isinstance(item, str) or not item.strip() for item in requirement_ids)
            or len(requirement_ids) != len(set(requirement_ids))
        ):
            raise ResearchPackageError(
                "raw finding requirement_ids must be unique non-empty strings in a non-empty list"
            )
        _validate_finding_evidence(raw_finding["evidence"], "evidence")
        if "evidence_limitation" in raw_finding:
            _require_non_empty_string(raw_finding["evidence_limitation"], "evidence_limitation")
        if raw_finding["status"] == "CLOSED":
            if "closure_evidence" not in raw_finding:
                raise ResearchPackageError("raw finding closure_evidence is required when status is CLOSED")
            _validate_finding_evidence(raw_finding["closure_evidence"], "closure_evidence")
        elif "closure_evidence" in raw_finding:
            raise ResearchPackageError("raw finding closure_evidence is forbidden when status is OPEN")
        canonical_json(raw_finding)
        validated.append(copy.deepcopy(raw_finding))
    return validated


def validate_lens_terminal_envelope(lens: str, terminal_envelope: Any) -> dict[str, Any]:
    if not isinstance(terminal_envelope, dict) or set(terminal_envelope) != {
        "verdict",
        "findings",
    }:
        raise ResearchPackageError("lens terminal envelope must contain exactly verdict and findings")
    verdict = terminal_envelope["verdict"]
    if verdict not in LENS_VERDICTS:
        raise ResearchPackageError("lens verdict must be PASS, GAPS, or BLOCKED")
    return {
        "verdict": verdict,
        "findings": _validate_raw_findings(terminal_envelope["findings"], lens),
    }


def _all_raw_findings(round_record: dict[str, Any]) -> dict[str, Any]:
    return {
        finding_fingerprint(raw_finding): copy.deepcopy(raw_finding)
        for lens in round_record["lenses"].values()
        for raw_finding in lens["raw_findings"]
    }


def _normalize_adjudications(raw_findings: dict[str, Any], adjudications: Any) -> list[dict[str, Any]]:
    if not isinstance(adjudications, list):
        raise ResearchPackageError("adjudications must be a JSON list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in adjudications:
        if not isinstance(item, dict) or "raw_finding" not in item:
            raise ResearchPackageError("every adjudication must include raw_finding")
        raw_finding = item["raw_finding"]
        computed = finding_fingerprint(raw_finding)
        supplied = item.get("finding_fingerprint", computed)
        if supplied != computed:
            raise ResearchPackageError("finding_fingerprint must match the canonical raw finding hash")
        if computed not in raw_findings:
            raise ResearchPackageError("adjudication cannot introduce findings not emitted by a lens")
        if computed in seen:
            raise ResearchPackageError("the adjudicator must classify each raw finding fingerprint exactly once")
        finding_type = item.get("finding_type")
        if finding_type not in FINDING_TYPES:
            raise ResearchPackageError(f"finding_type must be one of: {', '.join(sorted(FINDING_TYPES))}")
        materiality = item.get("materiality")
        if materiality not in MATERIALITIES:
            raise ResearchPackageError(f"materiality must be one of: {', '.join(sorted(MATERIALITIES))}")
        disposition = item.get("disposition")
        if disposition not in DISPOSITIONS:
            raise ResearchPackageError(f"disposition must be one of: {', '.join(sorted(DISPOSITIONS))}")
        record = {
            "finding_fingerprint": computed,
            "raw_finding": copy.deepcopy(raw_finding),
            "finding_type": finding_type,
            "materiality": materiality,
            "disposition": disposition,
        }
        seen.add(computed)
        normalized.append(record)
    if seen != set(raw_findings):
        raise ResearchPackageError("adjudication must classify and deduplicate all raw lens findings")
    normalized.sort(key=lambda item: item["finding_fingerprint"])
    return normalized


def _round(state: dict[str, Any], round_number: int) -> dict[str, Any] | None:
    return next(
        (item for item in state["rounds"] if item["round_number"] == round_number),
        None,
    )


def _round_actionable(round_record: dict[str, Any]) -> list[str]:
    adjudication = round_record.get("adjudication")
    if adjudication is None:
        return []
    return sorted(
        item["finding_fingerprint"]
        for item in adjudication["findings"]
        if item["disposition"] in PASS_BLOCKING_DISPOSITIONS
    )


def _round_complete(round_record: dict[str, Any]) -> bool:
    return set(round_record["lenses"]) == set(LENSES) and round_record.get("adjudication") is not None


def _attempt_lifecycle_complete(attempt: dict[str, Any]) -> bool:
    return (
        attempt.get("slot_closed") is True
        and attempt.get("close_evidence") not in (None, "", [], {})
        and (
            attempt.get("status") != "SUCCEEDED"
            or (
                isinstance(attempt.get("output_hash"), str) and _SHA256_RE.fullmatch(attempt["output_hash"]) is not None
            )
        )
    )


def _successful_attempt(
    state: dict[str, Any],
    *,
    runtime_agent_id: str,
    role: str,
    round_number: int,
    candidate_hash: str,
    envelope_hash: str,
) -> dict[str, Any]:
    attempt = next(
        (item for item in state["attempts"] if item["runtime_agent_id"] == runtime_agent_id),
        None,
    )
    if attempt is None or any(
        (
            attempt["role"] != role,
            attempt["round"] != round_number,
            attempt["candidate_hash"] != candidate_hash,
            attempt["input_envelope_hash"] != envelope_hash,
            attempt["status"] != "SUCCEEDED",
            not _attempt_lifecycle_complete(attempt),
        )
    ):
        raise ResearchPackageError(f"{role} result requires its successful closed attempt in the same round")
    return attempt


def _required_attempts_complete(state: dict[str, Any], round_record: dict[str, Any]) -> bool:
    attempts = [item for item in state["attempts"] if item["round"] == round_record["round_number"]]
    if not attempts or any(not _attempt_lifecycle_complete(item) for item in attempts):
        return False
    successful_roles = {
        item["role"]
        for item in attempts
        if item["status"] == "SUCCEEDED"
        and item["candidate_hash"] == round_record["candidate_hash"]
        and item["input_envelope_hash"] == round_record["envelope_hash"]
    }
    return set(REQUIRED_ROLES).issubset(successful_roles) and all(
        item["input_envelope_hash"] == round_record["envelope_hash"] for item in attempts
    )


def _validate_round_records(state: dict[str, Any]) -> None:
    if not isinstance(state["rounds"], list):
        raise ResearchPackageError("rounds must be a list")
    round_numbers: list[int] = []
    for round_record in state["rounds"]:
        required_round_fields = {
            "round_id",
            "round_number",
            "candidate_id",
            "candidate_hash",
            "envelope_hash",
            "lenses",
            "adjudication",
            "actionable_fingerprints",
        }
        if not isinstance(round_record, dict) or set(round_record) != required_round_fields:
            raise ResearchPackageError("round record violates the persisted state contract")
        round_number = round_record["round_number"]
        if (
            not isinstance(round_number, int)
            or not 1 <= round_number <= state["budgets"]["max_rounds"]
            or round_number in round_numbers
        ):
            raise ResearchPackageError("round numbers must be unique and within budget")
        round_numbers.append(round_number)
        candidate = _candidate_by_hashes(state, round_record["candidate_hash"], round_record["envelope_hash"])
        if round_record["candidate_id"] != candidate["candidate_id"]:
            raise ResearchPackageError("round candidate_id does not match its hashes")
        expected_round_id = stable_id(
            "lens-round",
            state["package_id"],
            round_number,
            round_record["candidate_hash"],
            round_record["envelope_hash"],
        )
        if round_record["round_id"] != expected_round_id:
            raise ResearchPackageError("round_id does not match the reviewed candidate")
        lenses = round_record["lenses"]
        if not isinstance(lenses, dict) or not set(lenses) <= set(LENSES):
            raise ResearchPackageError("round contains an invalid lens set")
        for lens, lens_record in lenses.items():
            required_lens_fields = {
                "lens_result_id",
                "lens",
                "runtime_agent_id",
                "verdict",
                "candidate_hash",
                "envelope_hash",
                "raw_findings",
                "recorded_at",
            }
            if not isinstance(lens_record, dict) or set(lens_record) != required_lens_fields:
                raise ResearchPackageError("lens result violates the persisted state contract")
            if (
                lens_record["lens"] != lens
                or lens_record["verdict"] not in LENS_VERDICTS
                or lens_record["candidate_hash"] != round_record["candidate_hash"]
                or lens_record["envelope_hash"] != round_record["envelope_hash"]
            ):
                raise ResearchPackageError("lens result is not bound to its round candidate")
            expected_lens_id = stable_id(
                "lens-result",
                state["package_id"],
                round_number,
                lens,
                round_record["candidate_hash"],
                round_record["envelope_hash"],
            )
            if lens_record["lens_result_id"] != expected_lens_id:
                raise ResearchPackageError("lens_result_id does not match its round")
            _validate_raw_findings(lens_record["raw_findings"], lens)
            _successful_attempt(
                state,
                runtime_agent_id=lens_record["runtime_agent_id"],
                role=lens,
                round_number=round_number,
                candidate_hash=round_record["candidate_hash"],
                envelope_hash=round_record["envelope_hash"],
            )
        adjudication = round_record["adjudication"]
        if adjudication is not None:
            required_adjudication_fields = {
                "adjudication_id",
                "runtime_agent_id",
                "candidate_hash",
                "envelope_hash",
                "findings",
                "recorded_at",
            }
            if (
                not isinstance(adjudication, dict)
                or set(adjudication) != required_adjudication_fields
                or set(lenses) != set(LENSES)
                or adjudication["candidate_hash"] != round_record["candidate_hash"]
                or adjudication["envelope_hash"] != round_record["envelope_hash"]
            ):
                raise ResearchPackageError("adjudication is not bound to a complete round candidate")
            expected_adjudication_id = stable_id(
                "adjudication",
                state["package_id"],
                round_number,
                adjudication["runtime_agent_id"],
                round_record["candidate_hash"],
                round_record["envelope_hash"],
            )
            if adjudication["adjudication_id"] != expected_adjudication_id:
                raise ResearchPackageError("adjudication_id does not match its round")
            if adjudication["runtime_agent_id"] in {item["runtime_agent_id"] for item in lenses.values()}:
                raise ResearchPackageError("adjudicator must be a fresh runtime agent")
            expected_findings = _normalize_adjudications(_all_raw_findings(round_record), adjudication["findings"])
            if expected_findings != adjudication["findings"]:
                raise ResearchPackageError("adjudication findings are not canonical")
            _require_candidate_gap_classification(
                candidate["candidate_payload"], adjudication["findings"]
            )
            _successful_attempt(
                state,
                runtime_agent_id=adjudication["runtime_agent_id"],
                role=ADJUDICATOR_ROLE,
                round_number=round_number,
                candidate_hash=round_record["candidate_hash"],
                envelope_hash=round_record["envelope_hash"],
            )
        if round_record["actionable_fingerprints"] != _round_actionable(round_record):
            raise ResearchPackageError("round actionable fingerprints do not match adjudication")
    if round_numbers != sorted(round_numbers):
        raise ResearchPackageError("rounds must be stored in ascending order")

    result = state["result"]
    required_result_fields = {
        "verdict",
        "reason",
        "candidate_hash",
        "envelope_hash",
        "actionable_fingerprints",
    }
    if (
        not isinstance(result, dict)
        or set(result) != required_result_fields
        or result["verdict"] != state["verdict"]
        or not isinstance(result["reason"], str)
        or not result["reason"]
        or result["actionable_fingerprints"] != sorted(set(result["actionable_fingerprints"]))
    ):
        raise ResearchPackageError("result violates the persisted state contract")
    if (result["candidate_hash"] is None) != (result["envelope_hash"] is None):
        raise ResearchPackageError("result candidate and envelope hashes must be paired")
    if result["candidate_hash"] is not None:
        _candidate_by_hashes(state, result["candidate_hash"], result["envelope_hash"])
    if state["verdict"] == "PASS":
        complete_rounds = [item for item in state["rounds"] if _round_complete(item)]
        if not complete_rounds:
            raise ResearchPackageError("PASS result lacks a complete reviewed round")
        passing_round = max(complete_rounds, key=lambda item: item["round_number"])
        if (
            result["candidate_hash"] != passing_round["candidate_hash"]
            or result["envelope_hash"] != passing_round["envelope_hash"]
            or result["actionable_fingerprints"] != _round_actionable(passing_round)
            or not _required_attempts_complete(state, passing_round)
        ):
            raise ResearchPackageError("PASS result is not bound to its reviewed round")


def _evaluate(state: dict[str, Any], now: datetime | str | None) -> None:
    if not state["rounds"]:
        _set_result(state, "IN_PROGRESS", "AWAITING_LENS_RESULTS")
        return
    latest = max(state["rounds"], key=lambda item: item["round_number"])
    if set(latest["lenses"]) != set(LENSES):
        _set_result(state, "IN_PROGRESS", "AWAITING_LENS_RESULTS")
        return
    if latest.get("adjudication") is None:
        _set_result(state, "IN_PROGRESS", "AWAITING_ADJUDICATION")
        return
    actionable = _round_actionable(latest)
    latest["actionable_fingerprints"] = actionable
    dispositions = {item["disposition"] for item in latest["adjudication"]["findings"]}
    if "BLOCKED_ON_EVIDENCE" in dispositions:
        _set_result(
            state,
            "BLOCKED",
            "BLOCKED_ON_EVIDENCE",
            candidate_hash=latest["candidate_hash"],
            envelope_hash=latest["envelope_hash"],
            actionable_fingerprints=actionable,
        )
        return
    if "REQUEST_SCOPE_APPROVAL" in dispositions:
        _set_result(
            state,
            "BLOCKED",
            "SCOPE_APPROVAL_REQUIRED",
            candidate_hash=latest["candidate_hash"],
            envelope_hash=latest["envelope_hash"],
            actionable_fingerprints=actionable,
        )
        return
    attempts_complete = _required_attempts_complete(state, latest)
    if not actionable and attempts_complete:
        _set_result(
            state,
            "PASS",
            "ROUND_CONTRACT_SATISFIED",
            candidate_hash=latest["candidate_hash"],
            envelope_hash=latest["envelope_hash"],
        )
        return
    if not attempts_complete:
        _set_result(
            state,
            "IN_PROGRESS",
            "AWAITING_REQUIRED_ATTEMPTS",
            candidate_hash=latest["candidate_hash"],
            envelope_hash=latest["envelope_hash"],
            actionable_fingerprints=actionable,
        )
        return
    previous = [
        item for item in state["rounds"] if item["round_number"] < latest["round_number"] and _round_complete(item)
    ]
    if previous:
        prior = max(previous, key=lambda item: item["round_number"])
        prior_actionable = _round_actionable(prior)
        if actionable and actionable == prior_actionable:
            _set_result(
                state,
                "CAP_REACHED",
                "UNCHANGED_ACTIONABLE_FINGERPRINTS",
                candidate_hash=latest["candidate_hash"],
                envelope_hash=latest["envelope_hash"],
                actionable_fingerprints=actionable,
            )
            return
    if latest["round_number"] >= state["budgets"]["max_rounds"]:
        _set_result(
            state,
            "CAP_REACHED",
            "ROUND_BUDGET",
            candidate_hash=latest["candidate_hash"],
            envelope_hash=latest["envelope_hash"],
            actionable_fingerprints=actionable,
        )
        return
    _set_result(
        state,
        "IN_PROGRESS",
        "FIX_IN_RESEARCH",
        candidate_hash=latest["candidate_hash"],
        envelope_hash=latest["envelope_hash"],
        actionable_fingerprints=actionable,
    )


def record_lens_result(
    state: dict[str, Any],
    *,
    round_number: int,
    lens: str,
    runtime_agent_id: str,
    candidate_hash: str,
    envelope_hash: str,
    terminal_envelope: Any,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    validate_state(state)
    if lens not in LENSES:
        raise ResearchPackageError(f"lens must be one of: {', '.join(LENSES)}")
    terminal = validate_lens_terminal_envelope(lens, terminal_envelope)
    verdict = terminal["verdict"]
    validated_findings = terminal["findings"]
    if not 1 <= round_number <= state["budgets"]["max_rounds"]:
        terminal = _terminal_result(state)
        if terminal is not None:
            return terminal
        return _cap(state, "ROUND_BUDGET", now)
    candidate = _candidate_by_hashes(state, candidate_hash, envelope_hash)
    _successful_attempt(
        state,
        runtime_agent_id=runtime_agent_id,
        role=lens,
        round_number=round_number,
        candidate_hash=candidate_hash,
        envelope_hash=envelope_hash,
    )
    lens_record = {
        "lens_result_id": stable_id(
            "lens-result",
            state["package_id"],
            round_number,
            lens,
            candidate_hash,
            envelope_hash,
        ),
        "lens": lens,
        "runtime_agent_id": runtime_agent_id,
        "verdict": verdict,
        "candidate_hash": candidate_hash,
        "envelope_hash": envelope_hash,
        "raw_findings": validated_findings,
    }
    round_record = _round(state, round_number)
    if round_record is not None:
        if round_record["candidate_hash"] != candidate_hash or round_record["envelope_hash"] != envelope_hash:
            raise ResearchPackageError("every lens in a round must evaluate the same candidate/envelope hash pair")
        existing = round_record["lenses"].get(lens)
        if existing is not None:
            comparable = {key: value for key, value in existing.items() if key != "recorded_at"}
            if comparable != lens_record:
                raise ResearchPackageError("lens result already exists with different content")
            return {
                "verdict": state["verdict"],
                "reason": "LENS_RESULT_ALREADY_RECORDED",
                "round_id": round_record["round_id"],
                "lens_result_id": existing["lens_result_id"],
            }
    terminal = _terminal_result(state)
    if terminal is not None:
        return terminal
    if round_record is None:
        round_record = {
            "round_id": stable_id(
                "lens-round",
                state["package_id"],
                round_number,
                candidate_hash,
                envelope_hash,
            ),
            "round_number": round_number,
            "candidate_id": candidate["candidate_id"],
            "candidate_hash": candidate_hash,
            "envelope_hash": envelope_hash,
            "lenses": {},
            "adjudication": None,
            "actionable_fingerprints": [],
        }
        state["rounds"].append(round_record)
        state["rounds"].sort(key=lambda item: item["round_number"])
    lens_record["recorded_at"] = _timestamp(now)
    round_record["lenses"][lens] = lens_record
    _evaluate(state, now)
    _touch(state, now)
    return {
        **copy.deepcopy(state["result"]),
        "round_id": round_record["round_id"],
        "lens_result_id": lens_record["lens_result_id"],
    }


def record_adjudication(
    state: dict[str, Any],
    *,
    round_number: int,
    runtime_agent_id: str,
    candidate_hash: str,
    envelope_hash: str,
    adjudications: Any,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    validate_state(state)
    if not 1 <= round_number <= state["budgets"]["max_rounds"]:
        terminal = _terminal_result(state)
        if terminal is not None:
            return terminal
        return _cap(state, "ROUND_BUDGET", now)
    candidate = _candidate_by_hashes(state, candidate_hash, envelope_hash)
    round_record = _round(state, round_number)
    if round_record is None or set(round_record["lenses"]) != set(LENSES):
        raise ResearchPackageError("adjudication requires all three raw lens results in the round")
    if round_record["candidate_hash"] != candidate_hash or round_record["envelope_hash"] != envelope_hash:
        raise ResearchPackageError("adjudication must use the round candidate/envelope hash pair")
    _successful_attempt(
        state,
        runtime_agent_id=runtime_agent_id,
        role=ADJUDICATOR_ROLE,
        round_number=round_number,
        candidate_hash=candidate_hash,
        envelope_hash=envelope_hash,
    )
    if runtime_agent_id in {lens_record["runtime_agent_id"] for lens_record in round_record["lenses"].values()}:
        raise ResearchPackageError("adjudicator must be a fresh runtime agent")
    normalized = _normalize_adjudications(_all_raw_findings(round_record), adjudications)
    _require_candidate_gap_classification(candidate["candidate_payload"], normalized)
    record = {
        "adjudication_id": stable_id(
            "adjudication",
            state["package_id"],
            round_number,
            runtime_agent_id,
            candidate_hash,
            envelope_hash,
        ),
        "runtime_agent_id": runtime_agent_id,
        "candidate_hash": candidate_hash,
        "envelope_hash": envelope_hash,
        "findings": normalized,
    }
    existing = round_record.get("adjudication")
    if existing is not None:
        comparable = {key: value for key, value in existing.items() if key != "recorded_at"}
        if comparable != record:
            raise ResearchPackageError("adjudication already exists with different content")
        _evaluate(state, now)
        _touch(state, now)
        return {
            **copy.deepcopy(state["result"]),
            "reason": "ADJUDICATION_REEVALUATED",
            "round_id": round_record["round_id"],
            "adjudication_id": existing["adjudication_id"],
        }
    terminal = _terminal_result(state)
    if terminal is not None:
        return terminal
    record["recorded_at"] = _timestamp(now)
    round_record["adjudication"] = record
    round_record["actionable_fingerprints"] = _round_actionable(round_record)
    _evaluate(state, now)
    _touch(state, now)
    return {
        **copy.deepcopy(state["result"]),
        "round_id": round_record["round_id"],
        "adjudication_id": record["adjudication_id"],
    }


EMITTED_FILES = (
    "manifest.json",
    "research.md",
    "requirements.json",
    "evidence-index.json",
    "findings.json",
    "planner-handoff.md",
)
EVIDENCE_INDEX_FIELDS = {
    "id",
    "source_kind",
    "source_locator",
    "source_sha256",
    "accessed_at",
    "supported_claim",
    "limitations",
}
EVIDENCE_SOURCE_KINDS = {"LOCAL_FILE", "SUPPLIED_INPUT", "EXTERNAL"}
PLANNER_READINESS_FIELDS = {
    "obligation_id",
    "status",
    "implementation_anchors",
    "verification_anchors",
    "required_inputs",
    "owner",
    "closure_condition",
    "evidence_ids",
}
MANIFEST_FIELDS = {
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
ATTEMPT_FIELDS = {
    "runtime_agent_id",
    "role",
    "round",
    "candidate_hash",
    "input_envelope_hash",
    "status",
    "output_hash",
    "slot_closed",
    "close_evidence",
    "recorded_at",
}
CURRENT_BUDGET_USE_FIELDS = {
    "rounds_used",
    "rounds_max",
    "attempts_used",
    "attempts_max",
    "workflow_minutes_used",
    "minutes_max_per_task",
}
LEGACY_BUDGET_USE_FIELDS = {
    "rounds_used",
    "rounds_max",
    "attempts_used",
    "attempts_max",
    "minutes_used",
    "minutes_max",
}


def _json_payload(value: Any) -> bytes:
    canonical_json(value)
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _bytes_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_package_timestamp(value: Any, field: str) -> None:
    try:
        _as_utc(value)
    except (TypeError, ValueError) as exc:
        raise ResearchPackageError(f"research package {field} is invalid") from exc


def _emitted_requirements(
    state: dict[str, Any],
    passing_round: dict[str, Any],
    readiness_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    candidate = _candidate_by_hashes(state, passing_round["candidate_hash"], passing_round["envelope_hash"])[
        "candidate_payload"
    ]
    by_id = _candidate_requirement_statuses(state, candidate)
    emitted = []
    for requirement in state["requirements"]:
        status = by_id[requirement["id"]]
        enriched = copy.deepcopy(requirement)
        enriched["planner_obligations"] = [
            {
                **obligation,
                **{
                    key: copy.deepcopy(value)
                    for key, value in readiness_by_id[obligation["id"]].items()
                    if key != "obligation_id"
                },
            }
            for obligation in requirement.get("planner_obligations", [])
        ]
        emitted.append(
            {
                **enriched,
                "research_value": status["research_value"],
                "evidence_ids": sorted(status["evidence_ids"]),
            }
        )
    return emitted


def _indexed_evidence_ids(evidence_index: Any) -> set[str]:
    if not isinstance(evidence_index, list):
        raise ResearchPackageError("evidence_index must be a list")
    indexed: set[str] = set()
    for index, item in enumerate(evidence_index):
        if not isinstance(item, dict):
            raise ResearchPackageError("every evidence index item must be an object")
        if set(item) != EVIDENCE_INDEX_FIELDS:
            raise ResearchPackageError(f"evidence index item {index} has invalid fields")
        evidence_id = item.get("id")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ResearchPackageError("every evidence index item must have a non-empty id")
        if evidence_id in indexed:
            raise ResearchPackageError(f"duplicate evidence index id: {evidence_id}")
        source_kind = item.get("source_kind")
        if source_kind not in EVIDENCE_SOURCE_KINDS:
            raise ResearchPackageError(f"evidence index item {evidence_id} has invalid source_kind")
        for field in ("source_locator", "supported_claim", "limitations"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ResearchPackageError(
                    f"evidence index item {evidence_id} requires non-empty {field}"
                )
        source_sha256 = item.get("source_sha256")
        accessed_at = item.get("accessed_at")
        if source_kind in {"LOCAL_FILE", "SUPPLIED_INPUT"}:
            if not isinstance(source_sha256, str) or not HEX_64.fullmatch(source_sha256):
                raise ResearchPackageError(
                    f"evidence index item {evidence_id} requires source_sha256"
                )
            if accessed_at is not None:
                raise ResearchPackageError(
                    f"evidence index item {evidence_id} forbids accessed_at"
                )
        elif source_sha256 is not None or not isinstance(accessed_at, str) or not accessed_at.strip():
            raise ResearchPackageError(
                f"external evidence index item {evidence_id} requires accessed_at and null source_sha256"
            )
        indexed.add(evidence_id)
    return indexed


def _planner_readiness_by_id(
    state: dict[str, Any], planner_readiness: Any, indexed_evidence: set[str]
) -> dict[str, dict[str, Any]]:
    if not isinstance(planner_readiness, list):
        raise ResearchPackageError("planner_readiness must be a list")
    expected_ids = {
        obligation["id"]
        for requirement in state["requirements"]
        for obligation in requirement.get("planner_obligations", [])
    }
    by_id: dict[str, dict[str, Any]] = {}
    for index, raw_item in enumerate(planner_readiness):
        if not isinstance(raw_item, dict) or set(raw_item) != PLANNER_READINESS_FIELDS:
            raise ResearchPackageError(f"planner readiness item {index} has invalid fields")
        obligation_id = raw_item.get("obligation_id")
        if not isinstance(obligation_id, str) or not obligation_id.strip():
            raise ResearchPackageError(f"planner readiness item {index} requires obligation_id")
        if obligation_id in by_id:
            raise ResearchPackageError(f"duplicate planner readiness obligation: {obligation_id}")
        if raw_item.get("status") != "READY":
            raise ResearchPackageError(f"planner obligation is not ready: {obligation_id}")
        for field in ("implementation_anchors", "verification_anchors"):
            values = raw_item.get(field)
            if (
                not isinstance(values, list)
                or not values
                or len(values) != len(set(values))
                or any(not isinstance(value, str) or not value.strip() for value in values)
            ):
                raise ResearchPackageError(
                    f"planner readiness {obligation_id} requires unique non-empty {field}"
                )
        required_inputs = raw_item.get("required_inputs")
        if (
            not isinstance(required_inputs, list)
            or len(required_inputs) != len(set(required_inputs))
            or any(not isinstance(value, str) or not value.strip() for value in required_inputs)
        ):
            raise ResearchPackageError(
                f"planner readiness {obligation_id} has invalid required_inputs"
            )
        for field in ("owner", "closure_condition"):
            value = raw_item.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ResearchPackageError(
                    f"planner readiness {obligation_id} requires non-empty {field}"
                )
        evidence_ids = raw_item.get("evidence_ids")
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or len(evidence_ids) != len(set(evidence_ids))
            or any(not isinstance(value, str) or not value.strip() for value in evidence_ids)
            or not set(evidence_ids) <= indexed_evidence
        ):
            raise ResearchPackageError(
                f"planner readiness {obligation_id} has invalid evidence_ids"
            )
        by_id[obligation_id] = copy.deepcopy(raw_item)
    if set(by_id) != expected_ids:
        missing = sorted(expected_ids - set(by_id))
        extra = sorted(set(by_id) - expected_ids)
        raise ResearchPackageError(
            f"planner readiness coverage mismatch: missing={missing}, extra={extra}"
        )
    return by_id


def emit_package(
    state: dict[str, Any],
    output_directory: Path | str,
    *,
    research_markdown: str,
    evidence_index: Any,
    planner_readiness: Any,
    planner_handoff_markdown: str,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    validate_state(state)
    if state["verdict"] != "PASS":
        raise ResearchPackageError("emit-package requires a terminal PASS verdict")
    if not isinstance(research_markdown, str):
        raise ResearchPackageError("research_markdown must be text")
    if not isinstance(planner_handoff_markdown, str):
        raise ResearchPackageError("planner_handoff_markdown must be text")
    canonical_json(evidence_index)
    complete_rounds = [item for item in state["rounds"] if _round_complete(item)]
    if not complete_rounds:
        raise ResearchPackageError("PASS state lacks a complete adjudicated round")
    passing_round = max(complete_rounds, key=lambda item: item["round_number"])
    if passing_round is None or not _required_attempts_complete(state, passing_round):
        raise ResearchPackageError("PASS state lacks complete round lifecycle evidence")
    if _round_actionable(passing_round):
        raise ResearchPackageError("PASS state does not satisfy adjudication gates")
    if (
        state["result"]["candidate_hash"] != passing_round["candidate_hash"]
        or state["result"]["envelope_hash"] != passing_round["envelope_hash"]
    ):
        raise ResearchPackageError("PASS result hashes do not match the passing round")
    indexed_evidence = _indexed_evidence_ids(evidence_index)
    readiness_by_id = _planner_readiness_by_id(
        state, planner_readiness, indexed_evidence
    )
    emitted_requirements = _emitted_requirements(
        state, passing_round, readiness_by_id
    )
    referenced_evidence = {
        evidence_id for requirement in emitted_requirements for evidence_id in requirement["evidence_ids"]
    }
    if not referenced_evidence <= indexed_evidence:
        raise ResearchPackageError("requirement statuses reference evidence absent from evidence_index")
    data_payloads = {
        "research.md": research_markdown.encode("utf-8"),
        "requirements.json": _json_payload(emitted_requirements),
        "evidence-index.json": _json_payload(evidence_index),
        "findings.json": _json_payload(passing_round["adjudication"]["findings"]),
        "planner-handoff.md": planner_handoff_markdown.encode("utf-8"),
    }
    artifact_hashes = {name: _bytes_hash(payload) for name, payload in data_payloads.items()}
    finished = _as_utc(now if now is not None else state["updated_at"])
    started = _as_utc(state["budgets"]["started_at"])
    lifecycle = copy.deepcopy(state["attempts"])
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_id": state["package_id"],
        "terminal_verdict": state["verdict"],
        "candidate_hash": state["result"]["candidate_hash"],
        "envelope_hash": state["result"]["envelope_hash"],
        "artifact_hashes": artifact_hashes,
        "budget_use": {
            "rounds_used": max(item["round_number"] for item in state["rounds"]),
            "rounds_max": state["budgets"]["max_rounds"],
            "attempts_used": len(state["attempts"]),
            "attempts_max": state["budgets"]["max_attempts"],
            "workflow_minutes_used": max(0.0, (finished - started).total_seconds() / 60),
            "minutes_max_per_task": state["budgets"]["max_minutes"],
        },
        "lifecycle_evidence": lifecycle,
        "emitted_at": _timestamp(finished),
    }
    payloads = {"manifest.json": _json_payload(manifest), **data_payloads}
    if set(payloads) != set(EMITTED_FILES):
        raise ResearchPackageError("emit-package file set violates the package contract")
    target = Path(output_directory)
    if target.exists():
        raise ResearchPackageError("emit-package output directory must not already exist")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent))
    try:
        for name in EMITTED_FILES:
            (staging / name).write_bytes(payloads[name])
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    file_hashes = {name: _bytes_hash(payloads[name]) for name in EMITTED_FILES}
    return {
        "verdict": "PASS",
        "reason": "PACKAGE_EMITTED",
        "output_directory": str(target),
        "file_hashes": file_hashes,
    }


def _validated_emitted_requirements(
    value: Any, indexed_evidence: set[str]
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ResearchPackageError("emitted requirements must be a non-empty list")
    emitted_fields = REQUIREMENT_FIELDS | {"research_value", "evidence_ids"}
    obligation_fields = {"id", "description"} | (PLANNER_READINESS_FIELDS - {"obligation_id"})
    base_requirements: list[dict[str, Any]] = []
    readiness: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != emitted_fields:
            raise ResearchPackageError(f"emitted requirement {index} has invalid fields")
        obligations = item["planner_obligations"]
        if not isinstance(obligations, list):
            raise ResearchPackageError("emitted planner_obligations must be a list")
        base_obligations: list[dict[str, str]] = []
        for obligation in obligations:
            if not isinstance(obligation, dict) or set(obligation) != obligation_fields:
                raise ResearchPackageError("emitted planner obligation has invalid fields")
            base_obligations.append(
                {"id": obligation["id"], "description": obligation["description"]}
            )
            readiness.append(
                {
                    "obligation_id": obligation["id"],
                    **{
                        field: copy.deepcopy(obligation[field])
                        for field in PLANNER_READINESS_FIELDS
                        if field != "obligation_id"
                    },
                }
            )
        base_requirements.append(
            {
                field: copy.deepcopy(base_obligations if field == "planner_obligations" else item[field])
                for field in REQUIREMENT_FIELDS
            }
        )
        if _research_value_type(item["research_value"]) != item["research_value_type"]:
            raise ResearchPackageError(
                f"emitted requirement {item['id']} research_value type does not match"
            )
        evidence_ids = item["evidence_ids"]
        if (
            not isinstance(evidence_ids, list)
            or len(evidence_ids) != len(set(evidence_ids))
            or evidence_ids != sorted(evidence_ids)
            or any(not isinstance(evidence_id, str) or not evidence_id for evidence_id in evidence_ids)
            or not set(evidence_ids) <= indexed_evidence
        ):
            raise ResearchPackageError(
                f"emitted requirement {item['id']} has invalid evidence_ids"
            )
    normalized = _normalize_requirements(base_requirements)
    if normalized != base_requirements:
        raise ResearchPackageError("emitted requirements are not canonical")
    _planner_readiness_by_id(
        {"requirements": normalized}, readiness, indexed_evidence
    )
    return copy.deepcopy(value)


def _validate_emitted_findings(value: Any, requirement_ids: set[str]) -> None:
    if not isinstance(value, list):
        raise ResearchPackageError("findings.json must contain a list")
    prior = ""
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "finding_fingerprint",
            "raw_finding",
            "finding_type",
            "materiality",
            "disposition",
        }:
            raise ResearchPackageError("emitted finding has invalid fields")
        raw = item["raw_finding"]
        if not isinstance(raw, dict) or not isinstance(raw.get("lens"), str):
            raise ResearchPackageError("emitted finding raw_finding is invalid")
        _validate_raw_findings([raw], raw["lens"])
        fingerprint = finding_fingerprint(raw)
        if item["finding_fingerprint"] != fingerprint or fingerprint in seen or fingerprint < prior:
            raise ResearchPackageError("emitted findings are not uniquely fingerprint-sorted")
        if item["finding_type"] not in FINDING_TYPES:
            raise ResearchPackageError("emitted finding has invalid finding_type")
        if item["materiality"] not in MATERIALITIES:
            raise ResearchPackageError("emitted finding has invalid materiality")
        if item["disposition"] not in DISPOSITIONS:
            raise ResearchPackageError("emitted finding has invalid disposition")
        if item["disposition"] in PASS_BLOCKING_DISPOSITIONS:
            raise ResearchPackageError("PASS package contains a blocking finding disposition")
        if not set(raw["requirement_ids"]) <= requirement_ids:
            raise ResearchPackageError("emitted finding references an unknown requirement")
        seen.add(fingerprint)
        prior = fingerprint


def _validate_manifest_lifecycle(manifest: dict[str, Any]) -> None:
    budget = manifest["budget_use"]
    if not isinstance(budget, dict) or set(budget) not in {
        frozenset(CURRENT_BUDGET_USE_FIELDS),
        frozenset(LEGACY_BUDGET_USE_FIELDS),
    }:
        raise ResearchPackageError("manifest budget_use has an unsupported exact field set")
    for field in ("rounds_used", "rounds_max", "attempts_used", "attempts_max"):
        value = budget[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ResearchPackageError(f"manifest budget_use {field} must be a positive integer")
    if budget["rounds_used"] > budget["rounds_max"] or budget["attempts_used"] > budget["attempts_max"]:
        raise ResearchPackageError("manifest budget_use exceeds a governed cap")
    elapsed_field = "workflow_minutes_used" if "workflow_minutes_used" in budget else "minutes_used"
    maximum_field = "minutes_max_per_task" if "minutes_max_per_task" in budget else "minutes_max"
    for field in (elapsed_field, maximum_field):
        value = budget[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ResearchPackageError(f"manifest budget_use {field} must be non-negative")
    if budget[maximum_field] <= 0:
        raise ResearchPackageError(f"manifest budget_use {maximum_field} must be positive")

    attempts = manifest["lifecycle_evidence"]
    if not isinstance(attempts, list) or len(attempts) != budget["attempts_used"]:
        raise ResearchPackageError("manifest lifecycle count does not match budget_use")
    runtime_ids: set[str] = set()
    successful_roles: set[str] = set()
    for attempt in attempts:
        if not isinstance(attempt, dict) or set(attempt) != ATTEMPT_FIELDS:
            raise ResearchPackageError("manifest lifecycle attempt has invalid fields")
        runtime_id = attempt["runtime_agent_id"]
        if not isinstance(runtime_id, str) or not runtime_id or runtime_id in runtime_ids:
            raise ResearchPackageError("manifest lifecycle runtime_agent_id must be unique")
        runtime_ids.add(runtime_id)
        if attempt["role"] not in REQUIRED_ROLES or attempt["status"] not in ATTEMPT_STATUSES:
            raise ResearchPackageError("manifest lifecycle attempt has invalid role or status")
        if (
            isinstance(attempt["round"], bool)
            or not isinstance(attempt["round"], int)
            or not 1 <= attempt["round"] <= budget["rounds_max"]
        ):
            raise ResearchPackageError("manifest lifecycle attempt has invalid round")
        for field in ("input_envelope_hash", "output_hash"):
            value = attempt[field]
            if field == "output_hash" and value is None and attempt["status"] == "FAILED":
                continue
            if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
                raise ResearchPackageError(f"manifest lifecycle attempt has invalid {field}")
        candidate_hash = attempt["candidate_hash"]
        allowed_null_candidate = (
            candidate_hash is None
            and attempt["role"] == CORE_RESEARCHER_ROLE
            and attempt["status"] == "FAILED"
            and attempt["round"] == 1
        )
        if not allowed_null_candidate and (
            not isinstance(candidate_hash, str) or not _SHA256_RE.fullmatch(candidate_hash)
        ):
            raise ResearchPackageError("manifest lifecycle attempt has invalid candidate_hash")
        _validate_package_timestamp(attempt["recorded_at"], "lifecycle recorded_at")
        if not _attempt_lifecycle_complete(attempt):
            raise ResearchPackageError("manifest lifecycle attempt is not closed")
        if (
            attempt["round"] == budget["rounds_used"]
            and attempt["status"] == "SUCCEEDED"
            and attempt["candidate_hash"] == manifest["candidate_hash"]
            and attempt["input_envelope_hash"] == manifest["envelope_hash"]
        ):
            successful_roles.add(attempt["role"])
    if successful_roles != set(REQUIRED_ROLES):
        raise ResearchPackageError("manifest final round lacks the complete successful role set")


def validate_package(package_directory: Path | str) -> dict[str, Any]:
    """Validate one emitted research package without mutating it."""
    supplied_root = Path(package_directory)
    if supplied_root.is_symlink():
        raise ResearchPackageError("research package root cannot be a symlink")
    try:
        package_root = supplied_root.resolve(strict=True)
    except OSError as exc:
        raise ResearchPackageError(f"research package root is unavailable: {exc}") from exc
    if not package_root.is_dir():
        raise ResearchPackageError("research package root must be a directory")
    entries = {entry.name: entry for entry in package_root.iterdir()}
    if set(entries) != set(EMITTED_FILES):
        raise ResearchPackageError("research package must contain exactly the six owned files")
    payloads: dict[str, bytes] = {}
    parsed: dict[str, Any] = {}
    for name in EMITTED_FILES:
        path = entries[name]
        if path.is_symlink() or not path.is_file():
            raise ResearchPackageError(f"research package owned file is not a regular file: {name}")
        payloads[name] = path.read_bytes()
        if name.endswith(".json"):
            try:
                parsed[name] = json.loads(payloads[name].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ResearchPackageError(f"research package JSON is invalid: {name}") from exc
        else:
            try:
                payloads[name].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ResearchPackageError(f"research package text is not UTF-8: {name}") from exc

    manifest = parsed["manifest.json"]
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS:
        raise ResearchPackageError("manifest has an invalid exact field set")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ResearchPackageError("manifest has an unsupported schema_version")
    if not isinstance(manifest["package_id"], str) or not re.fullmatch(
        r"research-package-[0-9a-f]{24}", manifest["package_id"]
    ):
        raise ResearchPackageError("manifest package_id is invalid")
    if manifest["terminal_verdict"] != "PASS":
        raise ResearchPackageError("research package terminal_verdict must be PASS")
    for field in ("candidate_hash", "envelope_hash"):
        if not isinstance(manifest[field], str) or not _SHA256_RE.fullmatch(manifest[field]):
            raise ResearchPackageError(f"manifest {field} is invalid")
    _validate_package_timestamp(manifest["emitted_at"], "manifest emitted_at")
    expected_artifacts = set(EMITTED_FILES) - {"manifest.json"}
    if (
        not isinstance(manifest["artifact_hashes"], dict)
        or set(manifest["artifact_hashes"]) != expected_artifacts
    ):
        raise ResearchPackageError("manifest artifact_hashes has an invalid exact file set")
    for name in expected_artifacts:
        observed = _bytes_hash(payloads[name])
        if manifest["artifact_hashes"].get(name) != observed:
            raise ResearchPackageError(f"manifest artifact hash mismatch: {name}")
    _validate_manifest_lifecycle(manifest)

    evidence_index = parsed["evidence-index.json"]
    indexed_evidence = _indexed_evidence_ids(evidence_index)
    requirements = _validated_emitted_requirements(
        parsed["requirements.json"], indexed_evidence
    )
    requirement_ids = {item["id"] for item in requirements}
    _validate_emitted_findings(parsed["findings.json"], requirement_ids)

    owned_files = sorted(
        (
            {"path": name, "sha256": _bytes_hash(payloads[name])}
            for name in EMITTED_FILES
        ),
        key=lambda item: item["path"],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": True,
        "package_root": str(package_root),
        "package_id": manifest["package_id"],
        "terminal_verdict": manifest["terminal_verdict"],
        "candidate_hash": manifest["candidate_hash"],
        "envelope_hash": manifest["envelope_hash"],
        "manifest_sha256": _bytes_hash(payloads["manifest.json"]),
        "owned_files": owned_files,
        "requirements": requirements,
        "evidence_index": copy.deepcopy(evidence_index),
    }


def mutate_file(
    path: Path | str,
    operation: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    state = load_state(path)
    before = canonical_json(state)
    result = operation(state)
    if canonical_json(state) != before:
        atomic_write(path, state)
    return result


def _read_json(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchPackageError(f"cannot read JSON from {path}: {exc}") from exc


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ResearchPackageError(f"cannot read text from {path}: {exc}") from exc


def _print_result(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    hash_json = subparsers.add_parser(
        "hash-json", help="report canonical object and file-byte hashes for one JSON file"
    )
    hash_json.add_argument("input")

    init = subparsers.add_parser("init", help="initialize an immutable research scope")
    init.add_argument("state")
    init.add_argument("--charter", required=True)
    init.add_argument("--requirements", required=True)
    init.add_argument("--operational-maturity", required=True, choices=sorted(OPERATIONAL_MATURITIES))
    init.add_argument("--evidence-availability", required=True)
    init.add_argument("--started-at")

    scope = subparsers.add_parser("scope-check", help="check scope without changing state")
    scope.add_argument("state")
    scope.add_argument("--charter", required=True)
    scope.add_argument("--requirements", required=True)
    scope.add_argument("--operational-maturity", required=True, choices=sorted(OPERATIONAL_MATURITIES))

    candidate = subparsers.add_parser("record-candidate", help="record candidate and envelope hashes")
    candidate.add_argument("state")
    candidate.add_argument("--candidate", required=True)
    candidate.add_argument("--envelope", required=True)
    candidate.add_argument("--evidence-availability")
    candidate.add_argument("--now")

    attempt = subparsers.add_parser("record-attempt", help="record one bounded role attempt")
    attempt.add_argument("state")
    attempt.add_argument("--runtime-agent-id", required=True)
    attempt.add_argument("--role", required=True, choices=REQUIRED_ROLES)
    attempt.add_argument("--round", type=int, required=True)
    attempt.add_argument("--candidate-hash", required=True)
    attempt.add_argument("--input-envelope-hash", required=True)
    attempt.add_argument("--status", required=True, choices=sorted(ATTEMPT_STATUSES))
    attempt.add_argument("--output-hash")
    attempt.add_argument("--slot-closed", action="store_true")
    attempt.add_argument("--close-evidence", required=True)
    attempt.add_argument("--now")

    lens = subparsers.add_parser("record-lens", help="record one lens terminal envelope")
    lens.add_argument("state")
    lens.add_argument("--round", type=int, required=True)
    lens.add_argument("--lens", required=True, choices=LENSES)
    lens.add_argument("--runtime-agent-id", required=True)
    lens.add_argument("--candidate-hash", required=True)
    lens.add_argument("--envelope-hash", required=True)
    lens.add_argument("--terminal-envelope", required=True)
    lens.add_argument("--now")

    adjudication = subparsers.add_parser("record-adjudication", help="classify and deduplicate all raw findings")
    adjudication.add_argument("state")
    adjudication.add_argument("--round", type=int, required=True)
    adjudication.add_argument("--runtime-agent-id", required=True)
    adjudication.add_argument("--candidate-hash", required=True)
    adjudication.add_argument("--envelope-hash", required=True)
    adjudication.add_argument("--adjudications", required=True)
    adjudication.add_argument("--now")

    emit = subparsers.add_parser("emit-package", help="emit the exact planner-ready PASS artifact set")
    emit.add_argument("state")
    emit.add_argument("output_directory")
    emit.add_argument("--research", required=True)
    emit.add_argument("--evidence-index", required=True)
    emit.add_argument("--planner-readiness", required=True)
    emit.add_argument("--planner-handoff", required=True)
    emit.add_argument("--now")

    validate = subparsers.add_parser(
        "validate-package", help="validate an emitted planner-ready package without mutation"
    )
    validate.add_argument("package_directory")

    show = subparsers.add_parser("show", help="print validated state")
    show.add_argument("state")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "hash-json":
            result = hash_json_file(args.input)
        elif args.command == "init":
            result = initialize_file(
                args.state,
                _read_json(args.charter),
                _read_json(args.requirements),
                args.operational_maturity,
                _read_json(args.evidence_availability),
                started_at=args.started_at,
            )
        elif args.command == "scope-check":
            result = scope_check(
                load_state(args.state),
                _read_json(args.charter),
                _read_json(args.requirements),
                args.operational_maturity,
            )
        elif args.command == "record-candidate":
            availability = _read_json(args.evidence_availability) if args.evidence_availability else None
            result = mutate_file(
                args.state,
                lambda state: record_candidate(
                    state,
                    _read_json(args.candidate),
                    _read_json(args.envelope),
                    evidence_availability=availability,
                    now=args.now,
                ),
            )
        elif args.command == "record-attempt":
            result = mutate_file(
                args.state,
                lambda state: record_attempt(
                    state,
                    runtime_agent_id=args.runtime_agent_id,
                    role=args.role,
                    round_number=args.round,
                    candidate_hash=args.candidate_hash,
                    input_envelope_hash=args.input_envelope_hash,
                    status=args.status,
                    output_hash=args.output_hash,
                    slot_closed=args.slot_closed,
                    close_evidence=_read_json(args.close_evidence),
                    now=args.now,
                ),
            )
        elif args.command == "record-lens":
            result = mutate_file(
                args.state,
                lambda state: record_lens_result(
                    state,
                    round_number=args.round,
                    lens=args.lens,
                    runtime_agent_id=args.runtime_agent_id,
                    candidate_hash=args.candidate_hash,
                    envelope_hash=args.envelope_hash,
                    terminal_envelope=_read_json(args.terminal_envelope),
                    now=args.now,
                ),
            )
        elif args.command == "record-adjudication":
            result = mutate_file(
                args.state,
                lambda state: record_adjudication(
                    state,
                    round_number=args.round,
                    runtime_agent_id=args.runtime_agent_id,
                    candidate_hash=args.candidate_hash,
                    envelope_hash=args.envelope_hash,
                    adjudications=_read_json(args.adjudications),
                    now=args.now,
                ),
            )
        elif args.command == "emit-package":
            result = emit_package(
                load_state(args.state),
                args.output_directory,
                research_markdown=_read_text(args.research),
                evidence_index=_read_json(args.evidence_index),
                planner_readiness=_read_json(args.planner_readiness),
                planner_handoff_markdown=_read_text(args.planner_handoff),
                now=args.now,
            )
        elif args.command == "validate-package":
            result = validate_package(args.package_directory)
        else:
            result = load_state(args.state)
    except ResearchPackageError as exc:
        if args.command == "validate-package":
            _print_result(
                {
                    "schema_version": SCHEMA_VERSION,
                    "valid": False,
                    "reason": "INVALID_PACKAGE",
                    "error": str(exc),
                }
            )
            return 2
        _print_result({"verdict": "BLOCKED", "reason": "INVALID_OPERATION", "error": str(exc)})
        return 2
    _print_result(result)
    return 2 if result.get("verdict") == "BLOCKED" else 3 if result.get("verdict") == "CAP_REACHED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
