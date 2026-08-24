#!/usr/bin/env python3
"""Shared deterministic candidate identity and verification contracts."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any, Iterable


SCHEMA_VERSION = 1
PROVENANCE_CLASSES = {"sequence_doc", "discovery_log", "script", "tool_help"}
EFFECT_CLASSES = {
    "read-only", "idempotent-local", "external-reversible", "external-irreversible",
}
VOLATILITY_KINDS = {"task_id", "run_id", "event_id", "receipt_path", "timestamp"}
OPERATION_KINDS = {
    "image", "container", "auth", "deploy", "workflow-drive", "package",
    "database", "remote-operator", "cleanup", "publish", "other", "read-only",
    "single-test", "single-build",
}
IDENTITY_KEYS = {
    "schema_version", "steps", "intended_outcome", "required_inputs", "dependencies",
    "failure_handling", "verification_contract", "effect_class",
    "environment_annotations", "semantic_flag_annotations", "volatility_policy",
}


class CandidateContractError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def deterministic_uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, label))


def _exact_object(value: Any, keys: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise CandidateContractError(code)
    return value


def _safe_id(value: Any, code: str) -> str:
    text = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", text):
        raise CandidateContractError(code)
    return text


def _safe_text(value: Any, code: str, *, limit: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise CandidateContractError(code)
    return value.strip()


def _qualified_path(value: Any, code: str) -> dict[str, str]:
    item = _exact_object(value, {"repository_key", "path"}, code)
    repository_key = _safe_id(item["repository_key"], code)
    path = str(item["path"] or "")
    if not path or path.startswith("/") or ".." in path.split("/") or "\x00" in path:
        raise CandidateContractError(code)
    return {"repository_key": repository_key, "path": path}


def normalize_operation_context(value: Any) -> dict[str, Any]:
    keys = {
        "intended_outcome", "repeatability_reason", "repeatability_evidence_ids",
        "required_inputs", "dependencies", "failure_handling", "verification_contract",
        "effect_class", "environment_annotations", "semantic_flag_annotations",
        "volatility_annotations",
    }
    raw = _exact_object(value, keys, "invalid-operation-context-fields")
    effect_class = raw["effect_class"]
    if effect_class not in EFFECT_CLASSES:
        raise CandidateContractError("invalid-effect-class")
    repeatability_ids = raw["repeatability_evidence_ids"]
    required_inputs = raw["required_inputs"]
    dependencies = raw["dependencies"]
    failures = raw["failure_handling"]
    environment = raw["environment_annotations"]
    flags = raw["semantic_flag_annotations"]
    volatility = raw["volatility_annotations"]
    for value_, code, maximum in (
        (repeatability_ids, "invalid-repeatability-evidence-ids", 100),
        (required_inputs, "invalid-required-inputs", 64),
        (dependencies, "invalid-dependencies", 100),
        (failures, "invalid-failure-handling", 32),
        (environment, "invalid-environment-annotations", 32),
        (flags, "invalid-semantic-flag-annotations", 100),
        (volatility, "invalid-volatility-annotations", 100),
    ):
        if not isinstance(value_, list) or len(value_) > maximum:
            raise CandidateContractError(code)
    verification = _exact_object(
        raw["verification_contract"], {"quality", "expected_outcome", "success_evidence"},
        "invalid-verification-contract",
    )
    if verification["quality"] != "same-path" or verification["expected_outcome"] != "passed":
        raise CandidateContractError("invalid-verification-contract")
    normalized_failures = []
    for failure in failures:
        item = _exact_object(failure, {"fingerprint", "symptom", "response"}, "invalid-failure-handling")
        fingerprint = str(item["fingerprint"] or "")
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise CandidateContractError("invalid-failure-fingerprint")
        normalized_failures.append({
            "fingerprint": fingerprint,
            "symptom": _safe_text(item["symptom"], "invalid-failure-symptom"),
            "response": _safe_text(item["response"], "invalid-failure-response"),
        })
    normalized_flags = []
    for flag in flags:
        item = _exact_object(flag, {"step_ordinal", "arg_index"}, "invalid-semantic-flag-annotation")
        if not all(isinstance(item[key], int) and item[key] >= 0 for key in item):
            raise CandidateContractError("invalid-semantic-flag-annotation")
        normalized_flags.append(dict(item))
    normalized_volatility = []
    for annotation in volatility:
        item = _exact_object(
            annotation, {"step_ordinal", "arg_index", "kind"}, "invalid-volatility-annotation",
        )
        if (
            not isinstance(item["step_ordinal"], int) or item["step_ordinal"] < 0
            or not isinstance(item["arg_index"], int) or item["arg_index"] < 0
            or item["kind"] not in VOLATILITY_KINDS
        ):
            raise CandidateContractError("invalid-volatility-annotation")
        normalized_volatility.append(dict(item))
    return {
        "intended_outcome": _safe_text(raw["intended_outcome"], "invalid-intended-outcome"),
        "repeatability_reason": _safe_text(raw["repeatability_reason"], "invalid-repeatability-reason"),
        "repeatability_evidence_ids": [_safe_id(item, "invalid-repeatability-evidence-id") for item in repeatability_ids],
        "required_inputs": [_safe_text(item, "invalid-required-input") for item in required_inputs],
        "dependencies": [_qualified_path(item, "invalid-dependency") for item in dependencies],
        "failure_handling": normalized_failures,
        "verification_contract": {
            "quality": "same-path", "expected_outcome": "passed",
            "success_evidence": _safe_text(verification["success_evidence"], "invalid-success-evidence"),
        },
        "effect_class": effect_class,
        "environment_annotations": [_safe_text(item, "invalid-environment-annotation") for item in environment],
        "semantic_flag_annotations": normalized_flags,
        "volatility_annotations": normalized_volatility,
    }


def _normalize_step(step: Any) -> dict[str, Any]:
    raw = _exact_object(
        step,
        {"step_ordinal", "step_id", "argv", "command_source", "source_ref", "operation_kind"},
        "invalid-candidate-step-fields",
    )
    ordinal = raw["step_ordinal"]
    argv = raw["argv"]
    if not isinstance(ordinal, int) or ordinal < 0:
        raise CandidateContractError("invalid-step-ordinal")
    if not isinstance(argv, list) or not argv or len(argv) > 100 or any(
        not isinstance(arg, str) or "\x00" in arg or "\r" in arg or "\n" in arg for arg in argv
    ):
        raise CandidateContractError("invalid-step-argv")
    if raw["command_source"] not in PROVENANCE_CLASSES:
        raise CandidateContractError("invalid-command-source")
    return {
        "step_ordinal": ordinal,
        "step_id": _safe_id(raw["step_id"], "invalid-step-id"),
        "argv": list(argv),
        "command_source": raw["command_source"],
        "source_ref": _qualified_path(raw["source_ref"], "invalid-source-ref"),
        "operation_kind": _safe_id(raw["operation_kind"], "invalid-operation-kind"),
    }


def normalize_candidate_identity(value: Any) -> dict[str, Any]:
    raw = _exact_object(value, IDENTITY_KEYS, "invalid-candidate-identity-fields")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise CandidateContractError("unsupported-candidate-identity-version")
    steps = [_normalize_step(step) for step in raw["steps"]] if isinstance(raw["steps"], list) else []
    if not steps or [step["step_ordinal"] for step in steps] != list(range(len(steps))):
        raise CandidateContractError("noncontiguous-candidate-steps")
    if any(step["operation_kind"] not in OPERATION_KINDS for step in steps):
        raise CandidateContractError("invalid-operation-kind")
    context = normalize_operation_context({
        "intended_outcome": raw["intended_outcome"],
        "repeatability_reason": "identity validation only",
        "repeatability_evidence_ids": [],
        "required_inputs": raw["required_inputs"],
        "dependencies": raw["dependencies"],
        "failure_handling": raw["failure_handling"],
        "verification_contract": raw["verification_contract"],
        "effect_class": raw["effect_class"],
        "environment_annotations": raw["environment_annotations"],
        "semantic_flag_annotations": raw["semantic_flag_annotations"],
        "volatility_annotations": raw["volatility_policy"],
    })
    for annotation in [*context["semantic_flag_annotations"], *context["volatility_annotations"]]:
        ordinal = annotation["step_ordinal"]
        if ordinal >= len(steps) or annotation["arg_index"] >= len(steps[ordinal]["argv"]):
            raise CandidateContractError("candidate-annotation-out-of-range")
    return {
        "schema_version": SCHEMA_VERSION,
        "steps": steps,
        "intended_outcome": context["intended_outcome"],
        "required_inputs": context["required_inputs"],
        "dependencies": context["dependencies"],
        "failure_handling": context["failure_handling"],
        "verification_contract": context["verification_contract"],
        "effect_class": context["effect_class"],
        "environment_annotations": context["environment_annotations"],
        "semantic_flag_annotations": context["semantic_flag_annotations"],
        "volatility_policy": context["volatility_annotations"],
    }


def validate_candidate_identity(value: Any, fingerprint: str) -> dict[str, Any]:
    identity = normalize_candidate_identity(value)
    if not re.fullmatch(r"[0-9a-f]{64}", str(fingerprint or "")) or sha256(identity) != fingerprint:
        raise CandidateContractError("candidate-fingerprint-mismatch")
    return identity


def build_candidate_identity(
    context: Any,
    steps: Iterable[Any],
    *,
    governed_values: dict[str, set[str]] | None = None,
) -> tuple[dict[str, Any], str]:
    normalized_context = normalize_operation_context(context)
    normalized_steps = [_normalize_step(step) for step in steps]
    if not normalized_steps or [step["step_ordinal"] for step in normalized_steps] != list(range(len(normalized_steps))):
        raise CandidateContractError("noncontiguous-candidate-steps")
    annotations = {
        (item["step_ordinal"], item["arg_index"]): item["kind"]
        for item in normalized_context["volatility_annotations"]
    }
    if len(annotations) != len(normalized_context["volatility_annotations"]):
        raise CandidateContractError("duplicate-volatility-annotation")
    semantic_steps = []
    for step in normalized_steps:
        argv = list(step["argv"])
        for (ordinal, arg_index), kind in annotations.items():
            if ordinal == step["step_ordinal"]:
                if arg_index >= len(argv):
                    raise CandidateContractError("volatility-arg-index-out-of-range")
                if governed_values is not None and argv[arg_index] not in governed_values.get(kind, set()):
                    raise CandidateContractError("volatility-value-not-governed")
                argv[arg_index] = f"<{kind}>"
        if any(arg.startswith("/") for arg in argv):
            raise CandidateContractError("absolute-path-authority")
        semantic_steps.append({**step, "argv": argv})
    identity = {
        "schema_version": SCHEMA_VERSION,
        "steps": semantic_steps,
        "intended_outcome": normalized_context["intended_outcome"],
        "required_inputs": normalized_context["required_inputs"],
        "dependencies": normalized_context["dependencies"],
        "failure_handling": normalized_context["failure_handling"],
        "verification_contract": normalized_context["verification_contract"],
        "effect_class": normalized_context["effect_class"],
        "environment_annotations": normalized_context["environment_annotations"],
        "semantic_flag_annotations": normalized_context["semantic_flag_annotations"],
        "volatility_policy": normalized_context["volatility_annotations"],
    }
    identity = normalize_candidate_identity(identity)
    return identity, sha256(identity)


def final_effective_verification(
    events: Iterable[dict[str, Any]], *, run_id: str, lineage_id: str, source_bundle_hash: str,
) -> dict[str, Any] | None:
    matches = sorted((
        event for event in events
        if event.get("event_type") == "verification_recorded"
        and event.get("run_id") == run_id
        and event.get("lineage_id") == lineage_id
        and event.get("source_bundle_hash") == source_bundle_hash
    ), key=lambda event: (event.get("recorded_at_utc", ""), event.get("event_id", "")))
    if not matches:
        return None
    final = matches[-1]
    if final.get("outcome") != "passed" or final.get("quality") != "same-path":
        return None
    return final
