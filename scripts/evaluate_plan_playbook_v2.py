#!/usr/bin/env python3
"""Grounded practical evaluator for the Plan Playbook V2 candidate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
AUTHORITY_FIELDS = {
    "schema_version", "authority_id", "source_bundle_sha256", "cases",
    "created_at_utc",
}
AUTHORITY_CASE_FIELDS = {
    "case_id", "request", "visible_evidence", "canonical_requirement_ids",
    "canonical_obligation_ids", "negative_boundaries", "forbidden_scope_claims",
    "forbidden_evidence_claims", "expected_transitions", "implementation_roots",
    "derivations",
}
DERIVATION_FIELDS = {
    "authority_pointer", "source_evidence_id", "source_path", "source_sha256",
    "source_selector", "source_excerpt", "source_excerpt_sha256",
}
VISIBLE_EVIDENCE_FIELDS = {"evidence_id", "path", "sha256"}
NEGATIVE_BOUNDARY_FIELDS = {"boundary_id", "statement"}
FORBIDDEN_CLAIM_FIELDS = {"id", "claim", "evidence_ids"}
TRANSITION_FIELDS = {"phase", "terminal_verdict", "blocker_code"}
IMPLEMENTATION_ROOT_FIELDS = {"repository_key", "path", "tree_sha256"}
CASE_IDS = ("small-grounded", "substantial-multisurface", "evidence-uncertain")
CASE_CLASSES = {
    "small-grounded": "SMALL_GROUNDED",
    "substantial-multisurface": "SUBSTANTIAL_MULTISURFACE",
    "evidence-uncertain": "EVIDENCE_UNCERTAIN",
}
REVIEW_INPUT_FIELDS = {
    "schema_version", "authority_path", "authority_sha256", "source_bundle_sha256",
    "source_snapshots", "implementation_root_snapshots", "output_contract",
}
REVIEW_SOURCE_FIELDS = {"source_evidence_id", "source_path", "source_sha256"}
REVIEW_ROOT_FIELDS = {"case_id", "repository_key", "path", "tree_sha256"}
REVIEW_TOKEN_FIELDS = {
    "schema_version", "attempt_id", "authority_sha256", "input_path", "input_sha256",
    "slot_id", "prepared_at_utc", "status",
}
REVIEW_OUTPUT_FIELDS = {
    "schema_version", "authority_sha256", "source_bundle_sha256", "case_assessments",
    "untraceable_pointers", "weakened_or_substituted_values", "verdict",
}
REVIEW_CASE_FIELDS = {
    "case_id", "request_preserves_intent", "visible_evidence_sufficient",
    "ids_source_derived", "boundaries_complete", "forbidden_claims_complete",
    "transitions_correct", "implementation_roots_real", "evidence",
}
REVIEW_EVIDENCE_FIELDS = {
    "source_evidence_id", "source_path", "source_sha256", "source_selector",
}
REVIEW_ATTEMPT_FIELDS = {
    "schema_version", "attempt_id", "authority_sha256", "input_path", "input_sha256",
    "slot_id", "status", "runtime_agent_id", "output_path", "output_sha256",
    "released_slot_path", "released_slot_sha256", "released_slot_projection",
    "released_slot_projection_sha256", "released_slot_close_evidence_sha256",
    "prepared_at_utc", "finalized_at_utc",
}
REVIEW_RECEIPT_FIELDS = {
    "schema_version", "authority_path", "authority_sha256", "source_bundle_sha256",
    "review_input_path", "review_input_sha256", "review_attempt_path",
    "review_attempt_sha256", "review_output_path", "review_output_sha256",
    "reviewer_runtime_agent_id", "slot_id", "released_slot_path",
    "released_slot_sha256", "released_slot_projection",
    "released_slot_projection_sha256", "released_slot_close_evidence_sha256",
    "verdict", "recorded_at_utc",
}
REVIEW_TERMINAL_STATUSES = {
    "SPAWN_FAILED", "BIND_FAILED", "SUCCEEDED", "OUTPUT_INVALID", "RUNTIME_FAILED",
    "TIMED_OUT",
}
ATTEMPT_TOKEN_FIELDS = {
    "schema_version", "attempt_id", "attempt_sequence", "kind", "subject_id",
    "input_path", "input_sha256", "slot_id", "prepared_run_sha256",
    "prepared_at_utc", "status",
}
OUTER_ATTEMPT_FIELDS = {
    "attempt_id", "attempt_sequence", "run_id", "role", "input_envelope_path",
    "input_envelope_sha256", "slot_id", "status", "runtime_agent_id",
    "output_path", "output_sha256", "prepared_at_utc", "finalized_at_utc",
}
CANDIDATE_ATTEMPT_FIELDS = {
    "attempt_id", "attempt_sequence", "probe", "input_path", "input_sha256",
    "slot_id", "status", "runtime_agent_id", "output_path", "output_sha256",
    "released_slot_path", "released_slot_sha256", "prepared_at_utc",
    "finalized_at_utc",
}
ATTEMPT_TERMINAL_STATUSES = REVIEW_TERMINAL_STATUSES
CANDIDATE_PROBES = ("CANDIDATE_EXPLICIT", "ORDINARY_LEGACY")
ROUTING_OUTPUT_FIELDS = {
    "schema_version", "input_sha256", "invocation", "selected_skill",
    "completed_at_utc",
}
ROUTING_RESULT_FIELDS = {
    "schema_version", "probe", "attempt_id", "runtime_agent_id", "slot_id",
    "request_sha256", "output_path", "output_sha256", "released_slot_path",
    "released_slot_sha256", "invocation", "selected_skill",
    "selected_tree_sha256", "expected_skill", "passed", "recorded_at_utc",
}
CANDIDATE_EVIDENCE_FIELDS = {
    "schema_version", "explicit_routing_path", "explicit_routing_sha256",
    "ordinary_routing_path", "ordinary_routing_sha256", "slot_ledger_path",
    "slot_ledger_sha256", "managed_before_path", "managed_before_sha256",
    "managed_after_path", "managed_after_sha256", "candidate_explicit_routing",
    "ordinary_legacy_routing", "managed_projection_clean", "recorded_at_utc",
}
MANAGED_SNAPSHOT_FIELDS = {
    "schema_version", "manifest_sha256", "installed_root", "backup_root", "skills",
    "recorded_at_utc",
}
MANAGED_SKILL_FIELDS = {"name", "installed_state", "tree_sha256", "backup_relpath"}
FIXTURE_MANIFEST_FIELDS = {
    "schema_version", "source_bundle_sha256", "fixture_authority_path",
    "fixture_authority_sha256", "authority_review_path", "authority_review_sha256",
    "cases",
}
FIXTURE_CASE_FIELDS = {
    "case_id", "case_class", "source_refs", "visible_inputs",
    "implementation_sources", "public_contract", "controller_inputs", "hidden_gold",
    "research_resume_package",
}
FILE_REF_FIELDS = {"path", "sha256"}
SOURCE_REF_FIELDS = {"evidence_id", "path", "sha256"}
CONTROLLER_INPUT_FIELDS = {
    "entry_mode", "charter", "direct_requirements", "direct_evidence_index",
}
PUBLIC_CONTRACT_FIELDS = {
    "schema_version", "case_id", "requirement_ids", "obligation_ids",
    "negative_boundaries", "planner_output_schema",
}
HIDDEN_GOLD_FIELDS = {
    "schema_version", "case_id", "critical_requirement_ids",
    "critical_obligation_ids", "required_negative_boundary_ids",
    "forbidden_scope_claims", "forbidden_evidence_claims", "expected_transitions",
}
PREPARED_RUN_FIELDS = {
    "schema_version", "run_root", "fixture_root", "fixture_tree_sha256",
    "fixture_manifest_sha256", "fixture_authority_path", "fixture_authority_sha256",
    "authority_review_path", "authority_review_sha256", "legacy_tree_sha256",
    "candidate_tree_sha256", "implementer_schema_sha256", "candidate_check_requests",
    "candidate_check_attempts", "candidate_check_evidence_path",
    "candidate_check_evidence_sha256", "matrix", "outer_attempts", "created_at_utc",
}
MATRIX_ROW_FIELDS = {
    "run_id", "case_id", "arm", "role", "phase", "execution_kind",
    "consumes_run_id", "resume_of_run_id", "controller_lineage_id",
    "controller_state_path", "controller_state_sha256", "resumed_from_state_sha256",
    "terminal_controller_state_path", "terminal_controller_state_sha256",
    "input_envelope_path", "input_envelope_sha256", "outer_attempt_ids", "attempt",
    "runtime_agent_id", "output_path", "output_sha256", "plan_snapshot_path",
    "plan_snapshot_sha256", "package_snapshot_path", "package_snapshot_tree_sha256",
    "consulted_sources_path", "consulted_sources_sha256", "agent_runs_path",
    "agent_runs_sha256", "slot_ledger_path", "slot_ledger_sha256", "started_at_utc",
    "ended_at_utc", "status",
}
INPUT_ENVELOPE_FIELDS = {
    "schema_version", "run_id", "case_id", "arm", "role", "phase", "request",
    "visible_evidence", "controller_inputs", "plan_input", "research_package",
    "implementation_sources", "output_contract",
}
SOURCE_SNAPSHOT_FIELDS = {
    "repository_key", "source_path", "source_tree_sha256", "snapshot_path",
    "snapshot_tree_sha256", "manifest_path", "manifest_sha256", "created_at_utc",
}
INITIALIZATION_INTENT_FIELDS = {
    "schema_version", "state", "run_id", "predecessor_prepared_run_sha256",
    "input_envelope_sha256", "controller_lineage_id", "controller_live_state_path",
    "controller_state_path", "created_at_utc",
}
INITIALIZATION_COMPLETED_FIELDS = {
    "schema_version", "state", "run_id", "predecessor_prepared_run_sha256",
    "input_envelope_sha256", "controller_lineage_id", "controller_live_state_path",
    "controller_state_path", "controller_state_sha256", "target_row_status",
    "started_at_utc", "result",
}
INITIALIZE_RESULT_FIELDS = {
    "schema_version", "command", "ok", "run_id", "status",
    "controller_state_path", "controller_state_sha256", "prepared_run_sha256",
    "code",
}
LEGACY_PLANNER_OUTPUT_FIELDS = {
    "schema_version", "case_id", "arm", "phase", "terminal_verdict", "plan_path",
    "plan_sha256", "evidence_status", "clarification_questions", "unresolved_choices",
}
CANDIDATE_PLANNER_OUTPUT_FIELDS = LEGACY_PLANNER_OUTPUT_FIELDS | {
    "package_path", "package_tree_sha256", "blocker_code",
}
IMPLEMENTER_OUTPUT_FIELDS = {
    "schema_version", "case_id", "arm", "plan_hash", "can_implement",
    "non_implementation_reason", "clarification_questions",
    "missing_implementation_anchors", "missing_verification_anchors",
    "unresolved_choices", "scope_inventions", "evidence_inventions",
    "implementation_actions", "verification_actions", "consulted_sources",
}
IMPLEMENTATION_ACTION_FIELDS = {
    "action_id", "obligation_id", "target_path", "anchor", "change",
    "consulted_source_paths",
}
VERIFICATION_ACTION_FIELDS = {
    "action_id", "obligation_id", "test_path", "command", "expected_observable",
    "consulted_source_paths",
}
CONSULTED_SOURCES_FIELDS = {"schema_version", "run_id", "paths"}
AGENT_RUNS_FIELDS = {"schema_version", "run_id", "agents"}
AGENT_RUN_FIELDS = {
    "role", "round", "verification_iteration", "attempt", "status",
    "runtime_agent_id", "input_sha256", "output_sha256", "slot_id",
}
RECORD_TRANSACTION_FIELDS = {
    "schema_version", "transaction_id", "state", "run_id",
    "predecessor_prepared_run_sha256", "terminal_controller_state_sha256",
    "output_sha256", "plan_sha256", "package_tree_sha256",
    "consulted_sources_sha256", "agent_runs_sha256", "slot_ledger_sha256",
    "successor_prepared_run_sha256", "created_at_utc",
}
ZERO_AGENT_LEDGER_BYTES = b'{"max":1,"slots":[],"version":2}'
CASE_RESULT_FIELDS = {
    "case_id", "arm", "requirement_numerator", "requirement_denominator",
    "requirement_recall", "negative_boundary_numerator", "negative_boundary_denominator",
    "negative_boundary_recall", "implementation_anchor_numerator",
    "implementation_anchor_denominator", "implementation_anchor_coverage",
    "verification_anchor_numerator", "verification_anchor_denominator",
    "verification_anchor_coverage", "unresolved_choice_count",
    "clarification_question_count", "scope_invention_count", "evidence_invention_count",
    "transition_correct", "hardening_hash_consistent", "profile_budget_compliant",
    "lifecycle_complete",
}
ARM_RESULT_FIELDS = CASE_RESULT_FIELDS - {"case_id"}
EVIDENCE_MANIFEST_FIELDS = {
    "schema_version", "fixture_root", "fixture_tree_sha256", "fixture_authority_path",
    "fixture_authority_sha256", "authority_review_path", "authority_review_sha256",
    "prepared_run_path", "prepared_run_sha256", "recorded_matrix_path",
    "recorded_matrix_sha256", "candidate_check_evidence_path",
    "candidate_check_evidence_sha256", "rows", "scored_at_utc",
}
EVIDENCE_ROW_FIELDS = {
    "run_id", "status", "execution_kind", "slot_ledger_path", "slot_ledger_sha256",
    "agent_runs_path", "agent_runs_sha256",
}
SCORE_FIELDS = {
    "schema_version", "prepared_run_sha256", "fixture_manifest_sha256",
    "fixture_authority_sha256", "authority_review_sha256", "recorded_matrix_sha256",
    "evaluation_evidence_path", "evaluation_evidence_sha256", "case_results",
    "arm_results", "candidate_checks", "thresholds", "all_passed", "scored_at_utc",
}
THRESHOLDS = {
    "requirement_recall_min": 1.0,
    "negative_boundary_recall_min": 1.0,
    "implementation_anchor_coverage_min": 1.0,
    "verification_anchor_coverage_min": 1.0,
    "unresolved_choice_count_max": 0,
    "clarification_question_count_max": 0,
    "scope_invention_count_max": 0,
    "evidence_invention_count_max": 0,
    "transition_correct_required": True,
    "hardening_hash_consistent_required": True,
    "profile_budget_compliant_required": True,
    "lifecycle_complete_required": True,
    "candidate_explicit_routing_required": True,
    "ordinary_legacy_routing_required": True,
    "managed_projection_clean_required": True,
}
SAFE_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
SCRIPT = Path(__file__).resolve()
REPO_ROOT = SCRIPT.parent.parent
SHARED_ROOT = REPO_ROOT / "skills/_shared"


class EvaluationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def planner_public_output_contract(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        CANDIDATE_PLANNER_OUTPUT_FIELDS
        if row["arm"] == "v2"
        else LEGACY_PLANNER_OUTPUT_FIELDS
    )
    properties: dict[str, Any] = {
        "schema_version": {"const": SCHEMA_VERSION},
        "case_id": {"const": row["case_id"]},
        "arm": {"const": row["arm"]},
        "phase": {"const": row["phase"]},
        "terminal_verdict": {"enum": ["PASS", "BLOCKED"]},
        "plan_path": {"type": ["string", "null"]},
        "plan_sha256": {"type": ["string", "null"]},
        "evidence_status": {"enum": ["SUFFICIENT", "INSUFFICIENT"]},
        "clarification_questions": {"type": "array", "items": {"type": "string"}},
        "unresolved_choices": {"type": "array", "items": {"type": "string"}},
    }
    terminal_rules = [
        "PASS requires plan_path to resolve from output.json to the UTF-8 plan artifact, plan_sha256 to equal its SHA-256, evidence_status=SUFFICIENT, and both diagnostic arrays empty.",
        "BLOCKED requires plan_path and plan_sha256 null and evidence_status=INSUFFICIENT.",
    ]
    if row["arm"] == "v2":
        properties.update({
            "package_path": {"type": ["string", "null"]},
            "package_tree_sha256": {"type": ["string", "null"]},
            "blocker_code": {"enum": ["RESEARCH_REQUIRED", None]},
        })
        terminal_rules.extend([
            "V2 PASS requires non-null package_path and package_tree_sha256 and null blocker_code.",
            "V2 BLOCKED requires null package fields, blocker_code=RESEARCH_REQUIRED, and both diagnostic arrays empty.",
        ])
    else:
        terminal_rules.append(
            "Legacy BLOCKED requires at least one clarification question or unresolved choice."
        )
    return {
        "schema_id": "V2_PLANNER_V1" if row["arm"] == "v2" else "LEGACY_PLANNER_V1",
        "json_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": sorted(fields),
        },
        "terminal_rules": terminal_rules,
    }


def consulted_sources_public_contract() -> dict[str, Any]:
    return {
        "json_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "run_id": {"type": "string", "minLength": 1},
                "paths": {"type": "array", "items": {"type": "string"}},
            },
            "required": sorted(CONSULTED_SOURCES_FIELDS),
        },
        "identity_rule": "run_id must equal the immutable input envelope run_id.",
        "planner_paths_rule": "Planner paths must be empty.",
        "implementer_paths_rule": "Implementer paths must equal output.json consulted_sources exactly.",
    }


def routing_public_output_contract() -> dict[str, Any]:
    return {
        "schema_id": "ROUTING_PROBE_V1",
        "json_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "schema_version": {"const": SCHEMA_VERSION},
                "input_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "invocation": {"type": ["string", "null"]},
                "selected_skill": {"type": "string", "minLength": 1},
                "completed_at_utc": {"type": "string", "minLength": 1},
            },
            "required": sorted(ROUTING_OUTPUT_FIELDS),
        },
        "identity_rules": [
            "input_sha256 must equal the SHA-256 of the immutable routing request input.",
            "invocation must equal the immutable routing request invocation.",
            "selected_skill is the skill actually selected; do not infer an expected skill or pass verdict.",
        ],
    }


def require_fields(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise EvaluationError("INVALID_SCHEMA", f"{label} must contain exactly {sorted(fields)}")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError("INVALID_SCHEMA", f"{label} must be a non-empty string")
    return value


def require_string_list(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise EvaluationError("INVALID_SCHEMA", f"{label} must be a string array")
    result = [require_string(item, f"{label}[]") for item in value]
    if len(result) != len(set(result)):
        raise EvaluationError("INVALID_SCHEMA", f"{label} must be unique")
    return result


def require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise EvaluationError("INVALID_SCHEMA", f"{label} must be lowercase SHA-256")
    return value


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("INVALID_JSON", f"cannot read JSON {path}: {exc}") from exc


def module_from_path(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise EvaluationError("OWNER_CONTRACT_UNAVAILABLE", f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    prior_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = prior_dont_write_bytecode
    return module


def slot_owner() -> Any:
    module = module_from_path("plan_v2_evaluator_slots", SHARED_ROOT / "agent_slot_ledger.py")
    for name in ("released_slot_projection", "released_slot_close_evidence_sha256"):
        if not hasattr(module, name):
            raise EvaluationError("OWNER_CONTRACT_UNAVAILABLE", f"missing slot API {name}")
    return module


def tree_owner() -> Any:
    module = module_from_path("plan_v2_evaluator_tree", SHARED_ROOT / "tree_digest.py")
    if not hasattr(module, "TREE_SHA256_V1"):
        raise EvaluationError("OWNER_CONTRACT_UNAVAILABLE", "missing TREE_SHA256_V1")
    return module


def plan_owner() -> Any:
    module = module_from_path(
        "plan_v2_evaluator_controller",
        REPO_ROOT / "skills/plan-playbook/scripts/plan_package.py",
    )
    for name in (
        "validate_charter", "validate_requirements", "validate_evidence",
        "create_source_snapshot", "validate_source_snapshot",
    ):
        if not hasattr(module, name):
            raise EvaluationError("OWNER_CONTRACT_UNAVAILABLE", f"missing controller API {name}")
    return module


def research_owner() -> Any:
    module = module_from_path(
        "plan_v2_evaluator_research",
        REPO_ROOT / "skills/research-playbook/scripts/research_package.py",
    )
    if not hasattr(module, "validate_package"):
        raise EvaluationError("OWNER_CONTRACT_UNAVAILABLE", "missing research package validator")
    return module


def relative_to_root(root: Path, path: Path, label: str) -> str:
    try:
        return path.resolve(strict=True).relative_to(root).as_posix()
    except (OSError, ValueError) as exc:
        raise EvaluationError("INVALID_PATH", f"{label} must be contained by fixture root") from exc


def fixture_owned_path(root: Path, relative: str, label: str, *, must_exist: bool = True) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise EvaluationError("INVALID_PATH", f"unsafe {label} path")
    path = root.joinpath(*pure.parts)
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise EvaluationError("INVALID_PATH", f"symlink forbidden for {label}")
    if must_exist:
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise EvaluationError("INVALID_PATH", f"missing {label}") from exc
        if root not in resolved.parents or not resolved.is_file():
            raise EvaluationError("INVALID_PATH", f"invalid {label}")
        return resolved
    parent = path.parent.resolve(strict=True)
    if parent != root and root not in parent.parents:
        raise EvaluationError("INVALID_PATH", f"{label} parent escapes fixture root")
    return path


def fixture_owned_directory(root: Path, relative: str, label: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise EvaluationError("INVALID_PATH", f"unsafe {label} path")
    path = root.joinpath(*pure.parts)
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise EvaluationError("INVALID_PATH", f"symlink forbidden for {label}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise EvaluationError("INVALID_PATH", f"missing {label}") from exc
    if root not in resolved.parents or not resolved.is_dir():
        raise EvaluationError("INVALID_PATH", f"invalid {label}")
    return resolved


def strict_root(path: Path) -> Path:
    try:
        root = path.resolve(strict=True)
    except OSError as exc:
        raise EvaluationError("INVALID_PATH", f"root does not exist: {path}") from exc
    if root.is_symlink() or not root.is_dir():
        raise EvaluationError("INVALID_PATH", f"root must be a regular directory: {path}")
    return root


def absolute_directory(path: Path, label: str, *, create: bool = False) -> Path:
    if not path.is_absolute():
        raise EvaluationError("INVALID_PATH", f"{label} must be absolute")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise EvaluationError("INVALID_PATH", f"missing {label}: {path}") from exc
    if not resolved.is_dir() or resolved.is_symlink():
        raise EvaluationError("INVALID_PATH", f"{label} must be a regular directory")
    return resolved


def manifest_names(path: Path) -> list[str]:
    try:
        raw = path.resolve(strict=True).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise EvaluationError("INVALID_MANIFEST", f"cannot read managed manifest: {exc}") from exc
    names = [line.strip() for line in raw.splitlines()]
    names = [name for name in names if name and not name.startswith("#")]
    if not names or len(names) != len(set(names)):
        raise EvaluationError("INVALID_MANIFEST", "managed names must be non-empty and unique")
    if any(not SAFE_SKILL_NAME_RE.fullmatch(name) or name in {".", ".."} for name in names):
        raise EvaluationError("INVALID_MANIFEST", "managed manifest contains an unsafe name")
    return names


def copy_tree_exact(source: Path, destination: Path) -> None:
    tree = tree_owner()
    expected = tree.TREE_SHA256_V1(source)
    if destination.exists():
        if destination.is_symlink() or not destination.is_dir():
            raise EvaluationError("BACKUP_CONFLICT", f"invalid backup path: {destination}")
        if tree.TREE_SHA256_V1(destination) != expected:
            raise EvaluationError("BACKUP_CONFLICT", f"backup bytes conflict: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        shutil.rmtree(staging)
        shutil.copytree(source, staging, symlinks=False)
        if tree.TREE_SHA256_V1(staging) != expected:
            raise EvaluationError("BACKUP_TAMPER", f"copied tree hash mismatch: {source}")
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def validate_managed_snapshot(path: Path) -> dict[str, Any]:
    snapshot = require_fields(load_json(path), MANAGED_SNAPSHOT_FIELDS, "managed snapshot")
    if snapshot["schema_version"] != SCHEMA_VERSION:
        raise EvaluationError("INVALID_SCHEMA", "unsupported managed snapshot schema")
    require_sha256(snapshot["manifest_sha256"], "manifest_sha256")
    installed_root = absolute_directory(Path(require_string(snapshot["installed_root"], "installed_root")), "installed root")
    backup_root = absolute_directory(Path(require_string(snapshot["backup_root"], "backup_root")), "backup root")
    if installed_root == backup_root or installed_root in backup_root.parents or backup_root in installed_root.parents:
        raise EvaluationError("INVALID_PATH", "managed and backup roots must not overlap")
    if not isinstance(snapshot["skills"], list) or not snapshot["skills"]:
        raise EvaluationError("INVALID_SCHEMA", "skills must be a non-empty array")
    names: list[str] = []
    for index, raw in enumerate(snapshot["skills"]):
        record = require_fields(raw, MANAGED_SKILL_FIELDS, f"managed skill {index}")
        name = require_string(record["name"], f"managed skill {index} name")
        if not SAFE_SKILL_NAME_RE.fullmatch(name) or name in names:
            raise EvaluationError("INVALID_SCHEMA", "managed skill names must be safe and unique")
        names.append(name)
        state = record["installed_state"]
        if state == "ABSENT":
            if record["tree_sha256"] is not None or record["backup_relpath"] is not None:
                raise EvaluationError("INVALID_SCHEMA", "absent managed skill has backup identity")
            continue
        if state != "PRESENT":
            raise EvaluationError("INVALID_SCHEMA", "unknown managed installed_state")
        digest = require_sha256(record["tree_sha256"], f"managed skill {name} tree_sha256")
        relative = require_string(record["backup_relpath"], f"managed skill {name} backup_relpath")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise EvaluationError("INVALID_PATH", "unsafe managed backup path")
        backup = backup_root.joinpath(*pure.parts)
        if backup.is_symlink():
            raise EvaluationError("INVALID_PATH", "managed backup cannot be a symlink")
        try:
            resolved = backup.resolve(strict=True)
        except OSError as exc:
            raise EvaluationError("BACKUP_TAMPER", f"missing managed backup for {name}") from exc
        if backup_root not in resolved.parents or not resolved.is_dir():
            raise EvaluationError("INVALID_PATH", "managed backup escapes backup root")
        if tree_owner().TREE_SHA256_V1(resolved) != digest:
            raise EvaluationError("BACKUP_TAMPER", f"managed backup hash mismatch for {name}")
    return snapshot


def snapshot_managed(
    manifest: Path, installed_root: Path, backup_root: Path, out: Path,
    *, now: str | None = None,
) -> dict[str, Any]:
    manifest = manifest.resolve(strict=True)
    installed_root = absolute_directory(installed_root, "installed root")
    backup_root = absolute_directory(backup_root, "backup root", create=True)
    if installed_root == backup_root or installed_root in backup_root.parents or backup_root in installed_root.parents:
        raise EvaluationError("INVALID_PATH", "managed and backup roots must not overlap")
    records: list[dict[str, Any]] = []
    tree = tree_owner()
    for name in manifest_names(manifest):
        source = installed_root / name
        if not source.exists():
            records.append({
                "name": name, "installed_state": "ABSENT", "tree_sha256": None,
                "backup_relpath": None,
            })
            continue
        if source.is_symlink() or not source.is_dir():
            raise EvaluationError("INVALID_PATH", f"managed skill is not a regular tree: {name}")
        digest = tree.TREE_SHA256_V1(source)
        relative = f"trees/{name}/{digest}"
        copy_tree_exact(source, backup_root / relative)
        records.append({
            "name": name, "installed_state": "PRESENT", "tree_sha256": digest,
            "backup_relpath": relative,
        })
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "manifest_sha256": sha256_bytes(manifest.read_bytes()),
        "installed_root": str(installed_root),
        "backup_root": str(backup_root),
        "skills": records,
        "recorded_at_utc": now or utc_now(),
    }
    atomic_write_json(out, snapshot)
    validate_managed_snapshot(out)
    return snapshot


def compare_managed(
    before_path: Path, after_path: Path, allow_added: Sequence[str],
    allow_changed: Sequence[str],
) -> dict[str, Any]:
    before = validate_managed_snapshot(before_path)
    after = validate_managed_snapshot(after_path)
    if before["manifest_sha256"] != after["manifest_sha256"]:
        raise EvaluationError("MANAGED_DRIFT", "managed manifest changed between snapshots")
    left = {record["name"]: record for record in before["skills"]}
    right = {record["name"]: record for record in after["skills"]}
    if list(left) != list(right):
        raise EvaluationError("MANAGED_DRIFT", "managed skill ordering or names changed")
    added_allowance = list(allow_added)
    changed_allowance = list(allow_changed)
    if len(added_allowance) != len(set(added_allowance)) or len(changed_allowance) != len(set(changed_allowance)):
        raise EvaluationError("INVALID_ALLOWANCE", "managed allowances must be unique")
    known = set(left)
    if not set(added_allowance) <= known or not set(changed_allowance) <= known:
        raise EvaluationError("INVALID_ALLOWANCE", "managed allowance names must be manifest-managed")
    added = sorted(name for name in left if left[name]["installed_state"] == "ABSENT" and right[name]["installed_state"] == "PRESENT")
    removed = sorted(name for name in left if left[name]["installed_state"] == "PRESENT" and right[name]["installed_state"] == "ABSENT")
    changed = sorted(
        name for name in left
        if left[name]["installed_state"] == right[name]["installed_state"] == "PRESENT"
        and left[name]["tree_sha256"] != right[name]["tree_sha256"]
    )
    unexpected_added = sorted(set(added) - set(added_allowance))
    unexpected_changed = sorted(set(changed) - set(changed_allowance))
    unused_added = sorted(set(added_allowance) - set(added))
    unused_changed = sorted(set(changed_allowance) - set(changed))
    passed = not any((removed, unexpected_added, unexpected_changed, unused_added, unused_changed))
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": passed,
        "added": added,
        "changed": changed,
        "removed": removed,
        "unexpected_added": unexpected_added,
        "unexpected_changed": unexpected_changed,
        "unused_added_allowances": unused_added,
        "unused_changed_allowances": unused_changed,
    }


def restore_managed(snapshot_path: Path, installed_root: Path) -> dict[str, Any]:
    snapshot = validate_managed_snapshot(snapshot_path)
    root = absolute_directory(installed_root, "installed root")
    if str(root) != snapshot["installed_root"]:
        raise EvaluationError("MANAGED_DRIFT", "installed root differs from snapshot")
    backup_root = Path(snapshot["backup_root"])
    tree = tree_owner()
    restored: list[str] = []
    removed: list[str] = []
    for record in snapshot["skills"]:
        target = root / record["name"]
        if target.is_symlink():
            raise EvaluationError("INVALID_PATH", f"managed target is a symlink: {record['name']}")
        if record["installed_state"] == "ABSENT":
            if target.exists():
                if not target.is_dir():
                    raise EvaluationError("INVALID_PATH", f"managed target is not a directory: {record['name']}")
                shutil.rmtree(target)
                removed.append(record["name"])
            continue
        source = backup_root / record["backup_relpath"]
        staging = Path(tempfile.mkdtemp(prefix=f".{record['name']}.", dir=root))
        try:
            shutil.rmtree(staging)
            shutil.copytree(source, staging, symlinks=False)
            if tree.TREE_SHA256_V1(staging) != record["tree_sha256"]:
                raise EvaluationError("BACKUP_TAMPER", f"restore staging mismatch for {record['name']}")
            old = root / f".{record['name']}.restore-old"
            if old.exists():
                raise EvaluationError("RESTORE_CONFLICT", f"stale restore backup for {record['name']}")
            if target.exists():
                os.replace(target, old)
            try:
                os.replace(staging, target)
            except Exception:
                if old.exists():
                    os.replace(old, target)
                raise
            if old.exists():
                shutil.rmtree(old)
            restored.append(record["name"])
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    for record in snapshot["skills"]:
        target = root / record["name"]
        if record["installed_state"] == "ABSENT":
            if target.exists():
                raise EvaluationError("RESTORE_FAILED", f"absent state not restored: {record['name']}")
        elif tree.TREE_SHA256_V1(target) != record["tree_sha256"]:
            raise EvaluationError("RESTORE_FAILED", f"tree state not restored: {record['name']}")
    return {"schema_version": SCHEMA_VERSION, "restored": restored, "removed": removed}


def contained_file(root: Path, relative: str) -> Path:
    require_string(relative, "relative path")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise EvaluationError("INVALID_PATH", f"unsafe relative path: {relative}")
    candidate = root.joinpath(*pure.parts)
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise EvaluationError("INVALID_PATH", f"symlink is forbidden: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise EvaluationError("INVALID_PATH", f"missing path: {relative}") from exc
    if root not in resolved.parents or not resolved.is_file() or resolved.is_symlink():
        raise EvaluationError("INVALID_PATH", f"path escapes fixture root: {relative}")
    return resolved


def json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise EvaluationError("INVALID_SELECTOR", f"invalid JSON pointer: {pointer}")
    current = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise EvaluationError("INVALID_SELECTOR", f"JSON pointer not found: {pointer}")
    return current


def selected_excerpt(path: Path, selector: str) -> str:
    line_match = re.fullmatch(r"L([1-9][0-9]*)-L([1-9][0-9]*)", selector)
    if line_match:
        start, end = map(int, line_match.groups())
        lines = path.read_text(encoding="utf-8").splitlines()
        if end < start or end > len(lines):
            raise EvaluationError("INVALID_SELECTOR", f"line selector outside source: {selector}")
        return "\n".join(lines[start - 1:end])
    if selector.startswith("/") or selector == "":
        selected = json_pointer(load_json(path), selector)
        return canonical_bytes(selected).decode("utf-8")
    raise EvaluationError("INVALID_SELECTOR", f"unsupported selector: {selector}")


def escaped_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def leaf_pointers(value: Any, pointer: str) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for key in sorted(value):
            result.extend(leaf_pointers(value[key], f"{pointer}/{escaped_pointer_token(key)}"))
        return result
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value):
            result.extend(leaf_pointers(item, f"{pointer}/{index}"))
        return result
    return [pointer]


def expected_derivation_pointers(case: dict[str, Any], index: int) -> set[str]:
    base = f"/cases/{index}"
    fields = (
        "request", "visible_evidence", "canonical_requirement_ids",
        "canonical_obligation_ids", "negative_boundaries", "forbidden_scope_claims",
        "forbidden_evidence_claims", "expected_transitions", "implementation_roots",
    )
    result: set[str] = set()
    for field in fields:
        result.update(leaf_pointers(case[field], f"{base}/{field}"))
    return {
        pointer for pointer in result
        if not re.fullmatch(rf"{re.escape(base)}/visible_evidence/[0-9]+/sha256", pointer)
        and not re.fullmatch(rf"{re.escape(base)}/implementation_roots/[0-9]+/tree_sha256", pointer)
    }


def validate_transition(value: Any, label: str) -> dict[str, Any]:
    row = require_fields(value, TRANSITION_FIELDS, label)
    require_string(row["phase"], f"{label}.phase")
    if row["terminal_verdict"] not in {"PASS", "GAPS", "BLOCKED", "CAP_REACHED"}:
        raise EvaluationError("INVALID_SCHEMA", f"{label}.terminal_verdict is invalid")
    if row["blocker_code"] is not None:
        require_string(row["blocker_code"], f"{label}.blocker_code")
    return row


def validate_case_schema(case: Any, index: int) -> dict[str, Any]:
    row = require_fields(case, AUTHORITY_CASE_FIELDS, f"cases[{index}]")
    if row["case_id"] != CASE_IDS[index]:
        raise EvaluationError("INVALID_SCHEMA", "authority cases must use the exact ordered case IDs")
    require_string(row["request"], f"cases[{index}].request")
    require_string_list(row["canonical_requirement_ids"], "canonical_requirement_ids", nonempty=True)
    require_string_list(row["canonical_obligation_ids"], "canonical_obligation_ids", nonempty=True)
    for item_index, item in enumerate(row["visible_evidence"]):
        record = require_fields(item, VISIBLE_EVIDENCE_FIELDS, "visible_evidence")
        require_string(record["evidence_id"], "visible_evidence.evidence_id")
        require_string(record["path"], "visible_evidence.path")
        require_sha256(record["sha256"], "visible_evidence.sha256")
    for item in row["negative_boundaries"]:
        record = require_fields(item, NEGATIVE_BOUNDARY_FIELDS, "negative_boundaries")
        require_string(record["boundary_id"], "negative_boundaries.boundary_id")
        require_string(record["statement"], "negative_boundaries.statement")
    for field in ("forbidden_scope_claims", "forbidden_evidence_claims"):
        for item in row[field]:
            record = require_fields(item, FORBIDDEN_CLAIM_FIELDS, field)
            require_string(record["id"], f"{field}.id")
            require_string(record["claim"], f"{field}.claim")
            require_string_list(record["evidence_ids"], f"{field}.evidence_ids", nonempty=True)
    transitions = require_fields(row["expected_transitions"], {"legacy", "v2"}, "expected_transitions")
    for arm in ("legacy", "v2"):
        if not isinstance(transitions[arm], list) or not transitions[arm]:
            raise EvaluationError("INVALID_SCHEMA", f"expected_transitions.{arm} must be non-empty")
        for transition_index, transition in enumerate(transitions[arm]):
            validate_transition(transition, f"expected_transitions.{arm}[{transition_index}]")
    if not isinstance(row["implementation_roots"], list) or not row["implementation_roots"]:
        raise EvaluationError("INVALID_SCHEMA", "implementation_roots must be non-empty")
    for item in row["implementation_roots"]:
        record = require_fields(item, IMPLEMENTATION_ROOT_FIELDS, "implementation_roots")
        require_string(record["repository_key"], "implementation_roots.repository_key")
        require_string(record["path"], "implementation_roots.path")
        require_sha256(record["tree_sha256"], "implementation_roots.tree_sha256")
    if not isinstance(row["derivations"], list) or not row["derivations"]:
        raise EvaluationError("INVALID_SCHEMA", "derivations must be non-empty")
    return row


def source_bundle_records(authority: dict[str, Any]) -> list[dict[str, str]]:
    records: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for case in authority["cases"]:
        for derivation in case["derivations"]:
            key = (
                case["case_id"], derivation["source_evidence_id"],
                derivation["source_path"], derivation["source_sha256"],
            )
            records[key] = {
                "case_id": key[0], "evidence_id": key[1], "path": key[2], "sha256": key[3],
            }
    return [records[key] for key in sorted(records, key=lambda item: tuple(part.encode("utf-8") for part in item))]


def implementation_root_snapshots(authority: dict[str, Any]) -> list[dict[str, str]]:
    digest = tree_owner().TREE_SHA256_V1
    records: list[dict[str, str]] = []
    for case in authority["cases"]:
        for raw in case["implementation_roots"]:
            root = require_fields(raw, IMPLEMENTATION_ROOT_FIELDS, "implementation root")
            if root["repository_key"] != "memory-knowledge":
                raise EvaluationError("INVALID_IMPLEMENTATION_ROOT", "fixture roots must belong to memory-knowledge")
            pure = PurePosixPath(require_string(root["path"], "implementation root path"))
            if pure.is_absolute() or not pure.parts or "." in pure.parts or ".." in pure.parts:
                raise EvaluationError("INVALID_IMPLEMENTATION_ROOT", "implementation root path must be repository-relative")
            candidate = REPO_ROOT.joinpath(*pure.parts)
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise EvaluationError("INVALID_IMPLEMENTATION_ROOT", "implementation root does not exist") from exc
            if resolved == REPO_ROOT or REPO_ROOT not in resolved.parents or candidate.is_symlink() or not resolved.is_dir():
                raise EvaluationError("INVALID_IMPLEMENTATION_ROOT", "implementation root escapes repository or is not a directory")
            try:
                actual = digest(resolved)
            except ValueError as exc:
                raise EvaluationError("INVALID_IMPLEMENTATION_ROOT", str(exc)) from exc
            if require_sha256(root["tree_sha256"], "implementation root tree_sha256") != actual:
                raise EvaluationError("IMPLEMENTATION_ROOT_MISMATCH", f"implementation root digest changed: {root['path']}")
            records.append({
                "case_id": case["case_id"],
                "repository_key": root["repository_key"],
                "path": root["path"],
                "tree_sha256": actual,
            })
    keys = [tuple(record[field] for field in ("case_id", "repository_key", "path", "tree_sha256")) for record in records]
    if len(keys) != len(set(keys)):
        raise EvaluationError("INVALID_IMPLEMENTATION_ROOT", "implementation root records must be unique")
    return sorted(records, key=lambda record: tuple(record[field].encode("utf-8") for field in ("case_id", "repository_key", "path", "tree_sha256")))


def validate_fixture_authority(fixtures: Path, authority_path: Path) -> dict[str, Any]:
    root = strict_root(fixtures)
    authority_resolved = authority_path.resolve(strict=True)
    if authority_resolved.parent != root or authority_resolved.is_symlink():
        raise EvaluationError("INVALID_PATH", "fixture authority must be a root-owned regular file")
    authority = require_fields(load_json(authority_resolved), AUTHORITY_FIELDS, "fixture authority")
    if authority["schema_version"] != SCHEMA_VERSION:
        raise EvaluationError("INVALID_SCHEMA", "unsupported authority schema version")
    require_string(authority["created_at_utc"], "created_at_utc")
    if not isinstance(authority["cases"], list) or len(authority["cases"]) != len(CASE_IDS):
        raise EvaluationError("INVALID_SCHEMA", "authority must contain exactly three cases")
    source_paths: dict[str, str] = {}
    all_pointers: set[str] = set()
    for index, raw_case in enumerate(authority["cases"]):
        case = validate_case_schema(raw_case, index)
        for evidence in case["visible_evidence"]:
            source = contained_file(root, evidence["path"])
            if sha256_bytes(source.read_bytes()) != evidence["sha256"]:
                raise EvaluationError("SOURCE_TAMPER", f"visible evidence hash changed: {evidence['path']}")
        expected = expected_derivation_pointers(case, index)
        observed: set[str] = set()
        for derivation_index, raw_derivation in enumerate(case["derivations"]):
            label = f"cases[{index}].derivations[{derivation_index}]"
            derivation = require_fields(raw_derivation, DERIVATION_FIELDS, label)
            pointer = require_string(derivation["authority_pointer"], f"{label}.authority_pointer")
            if pointer in observed or pointer in all_pointers:
                raise EvaluationError("INVALID_DERIVATION", f"duplicate authority pointer: {pointer}")
            observed.add(pointer); all_pointers.add(pointer)
            evidence_id = require_string(derivation["source_evidence_id"], f"{label}.source_evidence_id")
            source_path = require_string(derivation["source_path"], f"{label}.source_path")
            source_sha = require_sha256(derivation["source_sha256"], f"{label}.source_sha256")
            source = contained_file(root, source_path)
            if sha256_bytes(source.read_bytes()) != source_sha:
                raise EvaluationError("SOURCE_TAMPER", f"source hash changed: {source_path}")
            prior = source_paths.setdefault(source_path, evidence_id)
            if prior != evidence_id:
                raise EvaluationError("INVALID_DERIVATION", "one source path cannot have multiple evidence IDs")
            excerpt = selected_excerpt(source, require_string(derivation["source_selector"], f"{label}.source_selector"))
            if derivation["source_excerpt"] != excerpt:
                raise EvaluationError("INVALID_DERIVATION", f"source excerpt mismatch: {pointer}")
            if require_sha256(derivation["source_excerpt_sha256"], f"{label}.source_excerpt_sha256") != sha256_bytes(excerpt.encode("utf-8")):
                raise EvaluationError("INVALID_DERIVATION", f"source excerpt hash mismatch: {pointer}")
        if observed != expected:
            missing = sorted(expected - observed)
            extra = sorted(observed - expected)
            raise EvaluationError("INVALID_DERIVATION", f"derivation coverage mismatch; missing={missing}, extra={extra}")
    records = source_bundle_records(authority)
    derived_bundle = sha256_bytes(canonical_bytes(records))
    if require_sha256(authority["source_bundle_sha256"], "source_bundle_sha256") != derived_bundle:
        raise EvaluationError("SOURCE_BUNDLE_MISMATCH", "authority source bundle identity changed")
    identity_payload = {key: authority[key] for key in AUTHORITY_FIELDS - {"authority_id", "created_at_utc"}}
    expected_id = "plan-v2-fixture-authority-" + sha256_bytes(canonical_bytes(identity_payload))[:24]
    if authority["authority_id"] != expected_id:
        raise EvaluationError("AUTHORITY_ID_MISMATCH", "authority ID is not content-derived")
    roots = implementation_root_snapshots(authority)
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": True,
        "authority_id": expected_id,
        "authority_sha256": sha256_bytes(authority_resolved.read_bytes()),
        "source_bundle_sha256": derived_bundle,
        "case_ids": list(CASE_IDS),
        "source_records": records,
        "implementation_root_snapshots": roots,
    }


def authority_source_snapshots(receipt: dict[str, Any]) -> list[dict[str, str]]:
    rows = {
        (item["evidence_id"], item["path"], item["sha256"]): {
            "source_evidence_id": item["evidence_id"],
            "source_path": item["path"],
            "source_sha256": item["sha256"],
        }
        for item in receipt["source_records"]
    }
    return [rows[key] for key in sorted(rows, key=lambda row: tuple(part.encode("utf-8") for part in row))]


def authority_case_evidence(authority: dict[str, Any], case_index: int) -> list[dict[str, str]]:
    rows = {
        (
            item["source_evidence_id"], item["source_path"], item["source_sha256"],
            item["source_selector"],
        ): {
            "source_evidence_id": item["source_evidence_id"],
            "source_path": item["source_path"],
            "source_sha256": item["source_sha256"],
            "source_selector": item["source_selector"],
        }
        for item in authority["cases"][case_index]["derivations"]
    }
    return [rows[key] for key in sorted(rows, key=lambda row: tuple(part.encode("utf-8") for part in row))]


def load_slot(ledger_path: Path, slot_id: str) -> dict[str, Any]:
    ledger = require_fields(load_json(ledger_path), {"version", "max", "slots"}, "slot ledger")
    if ledger["version"] != 2 or not isinstance(ledger["slots"], list):
        raise EvaluationError("INVALID_SLOT_LEDGER", "slot ledger must be version 2")
    matches = [item for item in ledger["slots"] if isinstance(item, dict) and item.get("id") == slot_id]
    if len(matches) != 1:
        raise EvaluationError("INVALID_SLOT_LEDGER", "slot ID must identify exactly one slot")
    return matches[0]


def prepare_fixture_authority_review(
    fixtures: Path, authority_path: Path, slot_id: str, slot_ledger: Path,
    out: Path, *, now: str | None = None,
) -> dict[str, Any]:
    root = strict_root(fixtures)
    receipt = validate_fixture_authority(root, authority_path)
    slot = load_slot(slot_ledger.resolve(strict=True), require_string(slot_id, "slot_id"))
    if slot.get("state") != "reserved" or slot.get("agent_id") is not None:
        raise EvaluationError("INVALID_SLOT_STATE", "authority review slot must be reserved and unbound")
    input_path = root / "authority-review/input.json"
    expected_token = root / "authority-review/attempt-token.json"
    token_path = out.resolve(strict=False)
    if token_path != expected_token:
        raise EvaluationError("INVALID_PATH", "authority review token must use its fixed path")
    authority_relative = relative_to_root(root, authority_path, "authority")
    input_value = {
        "schema_version": 1,
        "authority_path": authority_relative,
        "authority_sha256": receipt["authority_sha256"],
        "source_bundle_sha256": receipt["source_bundle_sha256"],
        "source_snapshots": authority_source_snapshots(receipt),
        "implementation_root_snapshots": receipt["implementation_root_snapshots"],
        "output_contract": "PLAN_V2_FIXTURE_AUTHORITY_REVIEW_V1",
    }
    input_sha = sha256_bytes(canonical_bytes(input_value) + b"\n")
    attempt_id = "plan-v2-authority-review-" + sha256_bytes(canonical_bytes({
        "authority_sha256": receipt["authority_sha256"], "input_sha256": input_sha,
        "slot_id": slot_id,
    }))[:24]
    token = {
        "schema_version": 1, "attempt_id": attempt_id,
        "authority_sha256": receipt["authority_sha256"],
        "input_path": "authority-review/input.json", "input_sha256": input_sha,
        "slot_id": slot_id, "prepared_at_utc": now or utc_now(), "status": "PREPARED",
    }
    if input_path.exists() or expected_token.exists():
        if not input_path.is_file() or not expected_token.is_file():
            raise EvaluationError("REVIEW_REPLAY_CONFLICT", "partial authority review preparation")
        existing = require_fields(load_json(expected_token), REVIEW_TOKEN_FIELDS, "review token")
        existing_input = load_json(input_path)
        if existing_input != input_value:
            terminal_paths = finalized_review_paths(root)
            if (
                existing["status"] != "PREPARED"
                or existing["authority_sha256"] == receipt["authority_sha256"]
                or any(
                    terminal_paths[name].exists()
                    for name in ("attempt", "output", "released", "receipt")
                )
            ):
                raise EvaluationError("REVIEW_REPLAY_CONFLICT", "authority review input changed")
            atomic_write_json(input_path, input_value)
            atomic_write_json(expected_token, token)
            return token
        stable = {key: token[key] for key in token if key != "prepared_at_utc"}
        if {key: existing[key] for key in existing if key != "prepared_at_utc"} != stable:
            raise EvaluationError("REVIEW_REPLAY_CONFLICT", "authority review token changed")
        return existing
    input_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(input_path, input_value)
    atomic_write_json(expected_token, token)
    return token


def validate_review_output(
    output: Any, authority: dict[str, Any], authority_sha256: str,
    source_bundle_sha256: str,
) -> dict[str, Any]:
    result = require_fields(output, REVIEW_OUTPUT_FIELDS, "authority review output")
    if result["schema_version"] != 1 or result["authority_sha256"] != authority_sha256 or result["source_bundle_sha256"] != source_bundle_sha256:
        raise EvaluationError("INVALID_REVIEW_OUTPUT", "review output authority identity changed")
    if result["verdict"] != "PASS" or result["untraceable_pointers"] != [] or result["weakened_or_substituted_values"] != []:
        raise EvaluationError("INVALID_REVIEW_OUTPUT", "authority review did not pass cleanly")
    if not isinstance(result["case_assessments"], list) or len(result["case_assessments"]) != 3:
        raise EvaluationError("INVALID_REVIEW_OUTPUT", "review must assess exactly three cases")
    boolean_fields = REVIEW_CASE_FIELDS - {"case_id", "evidence"}
    for index, raw_case in enumerate(result["case_assessments"]):
        case = require_fields(raw_case, REVIEW_CASE_FIELDS, "review case assessment")
        if case["case_id"] != CASE_IDS[index] or any(case[field] is not True for field in boolean_fields):
            raise EvaluationError("INVALID_REVIEW_OUTPUT", "review case assessment did not pass")
        if case["evidence"] != authority_case_evidence(authority, index):
            raise EvaluationError("INVALID_REVIEW_OUTPUT", "review evidence is not the authority derivation projection")
    return result


def validate_review_status(
    status: str, runtime_agent_id: str | None, output_path: Path | None,
    projection: dict[str, Any],
) -> None:
    if status not in REVIEW_TERMINAL_STATUSES:
        raise EvaluationError("INVALID_REVIEW_STATUS", "unknown review terminal status")
    projection_agent = projection["agent_id"]
    if runtime_agent_id != projection_agent:
        raise EvaluationError("INVALID_RUNTIME_ID", "runtime agent ID must equal released slot identity")
    if status == "SPAWN_FAILED":
        valid = runtime_agent_id is None and output_path is None and projection["bound_at"] is None
    elif status == "BIND_FAILED":
        valid = (
            runtime_agent_id is not None and output_path is None
            and projection["bound_at"] is None and projection["abandoned_at"] is not None
        )
    elif status in {"RUNTIME_FAILED", "TIMED_OUT"}:
        valid = runtime_agent_id is not None and output_path is None and projection["bound_at"] is not None
    else:
        valid = runtime_agent_id is not None and output_path is not None and projection["bound_at"] is not None
    if not valid:
        raise EvaluationError("INVALID_REVIEW_STATUS", f"invalid lifecycle evidence for {status}")
    if runtime_agent_id is not None and (
        projection["completed_at"] is None or projection["closed_at"] is None
    ):
        raise EvaluationError("INVALID_SLOT_STATE", "runtime-backed review must be completed and closed")


def finalized_review_paths(root: Path) -> dict[str, Path]:
    return {
        "input": root / "authority-review/input.json",
        "token": root / "authority-review/attempt-token.json",
        "attempt": root / "authority-review/attempt.json",
        "output": root / "authority-review/output.json",
        "released": root / "authority-review/released-slot.json",
        "receipt": root / "fixture-authority-review.json",
    }


def finalize_fixture_authority_review(
    attempt_token: Path, slot_ledger: Path, status: str,
    runtime_agent_id: str | None = None, output_path: Path | None = None,
    *, now: str | None = None,
) -> dict[str, Any]:
    token_path = attempt_token.resolve(strict=True)
    root = strict_root(token_path.parent.parent)
    paths = finalized_review_paths(root)
    if token_path != paths["token"]:
        raise EvaluationError("INVALID_PATH", "authority review token relocated")
    token = require_fields(load_json(token_path), REVIEW_TOKEN_FIELDS, "review token")
    input_value = require_fields(load_json(paths["input"]), REVIEW_INPUT_FIELDS, "review input")
    authority_path = contained_file(root, input_value["authority_path"])
    authority_receipt = validate_fixture_authority(root, authority_path)
    if token["authority_sha256"] != authority_receipt["authority_sha256"] or token["input_sha256"] != sha256_bytes(paths["input"].read_bytes()):
        raise EvaluationError("REVIEW_REPLAY_CONFLICT", "review preparation identity changed")
    slot = load_slot(slot_ledger.resolve(strict=True), token["slot_id"])
    owner = slot_owner()
    try:
        projection = owner.released_slot_projection(slot)
        close_sha = owner.released_slot_close_evidence_sha256(slot)
    except ValueError as exc:
        raise EvaluationError("INVALID_SLOT_STATE", str(exc)) from exc
    validate_review_status(status, runtime_agent_id, output_path, projection)
    if status == "SUCCEEDED":
        assert output_path is not None
        raw_output_path = output_path.resolve(strict=True)
        raw_output = load_json(raw_output_path)
        output_bytes = raw_output_path.read_bytes()
        validate_review_output(raw_output, load_json(authority_path), authority_receipt["authority_sha256"], authority_receipt["source_bundle_sha256"])
    elif status == "OUTPUT_INVALID":
        assert output_path is not None
        raw_output_path = output_path.resolve(strict=True)
        raw_output = load_json(raw_output_path)
        output_bytes = raw_output_path.read_bytes()
    else:
        raw_output = None
        output_bytes = None
    projection_bytes = canonical_bytes(projection) + b"\n"
    output_sha = sha256_bytes(output_bytes) if output_bytes is not None else None
    attempt = {
        "schema_version": 1, "attempt_id": token["attempt_id"],
        "authority_sha256": token["authority_sha256"], "input_path": token["input_path"],
        "input_sha256": token["input_sha256"], "slot_id": token["slot_id"], "status": status,
        "runtime_agent_id": runtime_agent_id, "output_path": "authority-review/output.json" if raw_output is not None else None,
        "output_sha256": output_sha, "released_slot_path": "authority-review/released-slot.json",
        "released_slot_sha256": sha256_bytes(projection_bytes), "released_slot_projection": projection,
        "released_slot_projection_sha256": sha256_bytes(canonical_bytes(projection)),
        "released_slot_close_evidence_sha256": close_sha,
        "prepared_at_utc": token["prepared_at_utc"], "finalized_at_utc": now or utc_now(),
    }
    if paths["attempt"].exists():
        existing = require_fields(load_json(paths["attempt"]), REVIEW_ATTEMPT_FIELDS, "review attempt")
        stable = {key: attempt[key] for key in attempt if key != "finalized_at_utc"}
        if {key: existing[key] for key in existing if key != "finalized_at_utc"} != stable:
            raise EvaluationError("REVIEW_REPLAY_CONFLICT", "finalized review changed")
        if load_json(paths["released"]) != projection:
            raise EvaluationError("REVIEW_REPLAY_CONFLICT", "released-slot snapshot changed")
        if raw_output is not None and paths["output"].read_bytes() != output_bytes:
            raise EvaluationError("REVIEW_REPLAY_CONFLICT", "review output snapshot changed")
        return existing
    if paths["released"].exists() or paths["output"].exists():
        raise EvaluationError("REVIEW_REPLAY_CONFLICT", "partial authority review finalization")
    if output_bytes is not None:
        atomic_write_bytes(paths["output"], output_bytes)
    atomic_write_json(paths["released"], projection)
    atomic_write_json(paths["attempt"], attempt)
    return attempt


def validate_fixture_authority_review(
    fixtures: Path, authority_path: Path, attempt_token: Path,
    slot_ledger: Path | None, receipt_path: Path,
) -> dict[str, Any]:
    root = strict_root(fixtures)
    paths = finalized_review_paths(root)
    for relative in (
        "authority-review/input.json", "authority-review/attempt-token.json",
        "authority-review/attempt.json", "authority-review/output.json",
        "authority-review/released-slot.json", "fixture-authority-review.json",
    ):
        contained_file(root, relative)
    exact_paths = {
        "authority": authority_path, "token": attempt_token, "receipt": receipt_path,
    }
    expected_paths = {
        "authority": root / "fixture-authority.json",
        "token": paths["token"], "receipt": paths["receipt"],
    }
    for label, raw_path in exact_paths.items():
        if raw_path.resolve(strict=True) != expected_paths[label]:
            raise EvaluationError("INVALID_PATH", f"{label} path is not fixture-owned")

    authority_receipt = validate_fixture_authority(root, expected_paths["authority"])
    authority = load_json(expected_paths["authority"])
    input_value = require_fields(load_json(paths["input"]), REVIEW_INPUT_FIELDS, "review input")
    expected_input = {
        "schema_version": 1,
        "authority_path": "fixture-authority.json",
        "authority_sha256": authority_receipt["authority_sha256"],
        "source_bundle_sha256": authority_receipt["source_bundle_sha256"],
        "source_snapshots": authority_source_snapshots(authority_receipt),
        "implementation_root_snapshots": authority_receipt["implementation_root_snapshots"],
        "output_contract": "PLAN_V2_FIXTURE_AUTHORITY_REVIEW_V1",
    }
    if input_value != expected_input:
        raise EvaluationError("INVALID_REVIEW_RECEIPT", "review input is not the authority projection")

    token = require_fields(load_json(paths["token"]), REVIEW_TOKEN_FIELDS, "review token")
    if token["schema_version"] != 1 or token["status"] != "PREPARED":
        raise EvaluationError("INVALID_REVIEW_RECEIPT", "invalid review token state")
    if token["authority_sha256"] != authority_receipt["authority_sha256"]:
        raise EvaluationError("INVALID_REVIEW_RECEIPT", "review token authority changed")
    if token["input_path"] != "authority-review/input.json" or token["input_sha256"] != sha256_bytes(paths["input"].read_bytes()):
        raise EvaluationError("INVALID_REVIEW_RECEIPT", "review token input changed")
    expected_attempt_id = "plan-v2-authority-review-" + sha256_bytes(canonical_bytes({
        "authority_sha256": authority_receipt["authority_sha256"],
        "input_sha256": token["input_sha256"], "slot_id": token["slot_id"],
    }))[:24]
    if token["attempt_id"] != expected_attempt_id:
        raise EvaluationError("INVALID_REVIEW_RECEIPT", "review attempt ID changed")

    attempt = require_fields(load_json(paths["attempt"]), REVIEW_ATTEMPT_FIELDS, "review attempt")
    if attempt["schema_version"] != 1 or attempt["status"] != "SUCCEEDED":
        raise EvaluationError("INVALID_REVIEW_RECEIPT", "only a successful authority review is recordable")
    for field in ("attempt_id", "authority_sha256", "input_path", "input_sha256", "slot_id", "prepared_at_utc"):
        if attempt[field] != token[field]:
            raise EvaluationError("INVALID_REVIEW_RECEIPT", f"attempt/token mismatch: {field}")
    if attempt["output_path"] != "authority-review/output.json" or attempt["released_slot_path"] != "authority-review/released-slot.json":
        raise EvaluationError("INVALID_REVIEW_RECEIPT", "review attempt paths changed")
    if attempt["output_sha256"] != sha256_bytes(paths["output"].read_bytes()) or attempt["released_slot_sha256"] != sha256_bytes(paths["released"].read_bytes()):
        raise EvaluationError("INVALID_REVIEW_RECEIPT", "review attempt artifact hash changed")

    owner = slot_owner()
    try:
        if slot_ledger is None:
            released = require_fields(
                load_json(paths["released"]),
                {
                    "id", "label", "state", "agent_id", "acquired_at", "bound_at",
                    "completed_at", "closed_at", "abandoned_at", "released_at",
                    "evidence",
                },
                "released-slot projection",
            )
            projection = owner.released_slot_projection(released)
            close_sha = owner.released_slot_close_evidence_sha256(released)
        else:
            slot = load_slot(slot_ledger.resolve(strict=True), token["slot_id"])
            projection = owner.released_slot_projection(slot)
            close_sha = owner.released_slot_close_evidence_sha256(slot)
    except ValueError as exc:
        raise EvaluationError("INVALID_SLOT_STATE", str(exc)) from exc
    projection_sha = sha256_bytes(canonical_bytes(projection))
    if (
        projection["agent_id"] is None
        or projection["completed_at"] is None
        or projection["closed_at"] is None
        or load_json(paths["released"]) != projection
        or attempt["runtime_agent_id"] != projection["agent_id"]
        or attempt["released_slot_projection"] != projection
        or attempt["released_slot_projection_sha256"] != projection_sha
        or attempt["released_slot_close_evidence_sha256"] != close_sha
    ):
        raise EvaluationError("INVALID_REVIEW_RECEIPT", "review lifecycle evidence changed")
    output = validate_review_output(
        load_json(paths["output"]), authority,
        authority_receipt["authority_sha256"], authority_receipt["source_bundle_sha256"],
    )

    receipt = require_fields(load_json(paths["receipt"]), REVIEW_RECEIPT_FIELDS, "review receipt")
    expected = {
        "schema_version": 1,
        "authority_path": "fixture-authority.json",
        "authority_sha256": authority_receipt["authority_sha256"],
        "source_bundle_sha256": authority_receipt["source_bundle_sha256"],
        "review_input_path": "authority-review/input.json",
        "review_input_sha256": sha256_bytes(paths["input"].read_bytes()),
        "review_attempt_path": "authority-review/attempt.json",
        "review_attempt_sha256": sha256_bytes(paths["attempt"].read_bytes()),
        "review_output_path": "authority-review/output.json",
        "review_output_sha256": sha256_bytes(paths["output"].read_bytes()),
        "reviewer_runtime_agent_id": projection["agent_id"],
        "slot_id": token["slot_id"],
        "released_slot_path": "authority-review/released-slot.json",
        "released_slot_sha256": sha256_bytes(paths["released"].read_bytes()),
        "released_slot_projection": projection,
        "released_slot_projection_sha256": projection_sha,
        "released_slot_close_evidence_sha256": close_sha,
        "verdict": output["verdict"],
        "recorded_at_utc": receipt["recorded_at_utc"],
    }
    require_string(receipt["recorded_at_utc"], "recorded_at_utc")
    if receipt != expected:
        raise EvaluationError("INVALID_REVIEW_RECEIPT", "review receipt does not match reopened evidence")
    return receipt


def validate_fixture_authority_review_receipt(
    fixtures: Path, authority_path: Path, receipt_path: Path,
) -> dict[str, Any]:
    root = strict_root(fixtures)
    return validate_fixture_authority_review(
        root, authority_path, root / "authority-review/attempt-token.json", None,
        receipt_path,
    )


def fixture_file_reference(
    root: Path, value: Any, label: str, *, source: bool = False,
) -> tuple[dict[str, Any], Path]:
    fields = SOURCE_REF_FIELDS if source else FILE_REF_FIELDS
    record = require_fields(value, fields, label)
    if source:
        require_string(record["evidence_id"], f"{label} evidence_id")
    path = fixture_owned_path(root, require_string(record["path"], f"{label} path"), label)
    digest = require_sha256(record["sha256"], f"{label} sha256")
    if sha256_bytes(path.read_bytes()) != digest:
        raise EvaluationError("FIXTURE_DRIFT", f"{label} hash changed")
    return record, path


def authority_source_projection(case: dict[str, Any]) -> list[dict[str, str]]:
    projected = {
        (
            item["source_evidence_id"], item["source_path"], item["source_sha256"],
        )
        for item in case["derivations"]
    }
    return [
        {"evidence_id": evidence_id, "path": path, "sha256": digest}
        for evidence_id, path, digest in sorted(
            projected, key=lambda item: tuple(value.encode("utf-8") for value in item)
        )
    ]


def validate_public_contract(
    path: Path, authority_case: dict[str, Any], case_id: str,
) -> dict[str, Any]:
    contract = require_fields(load_json(path), PUBLIC_CONTRACT_FIELDS, "public contract")
    if contract["schema_version"] != SCHEMA_VERSION or contract["case_id"] != case_id:
        raise EvaluationError("INVALID_FIXTURE", "public contract identity is invalid")
    if contract["requirement_ids"] != authority_case["canonical_requirement_ids"]:
        raise EvaluationError("AUTHORITY_PROJECTION_MISMATCH", "public requirement IDs changed")
    if contract["obligation_ids"] != authority_case["canonical_obligation_ids"]:
        raise EvaluationError("AUTHORITY_PROJECTION_MISMATCH", "public obligation IDs changed")
    if contract["negative_boundaries"] != authority_case["negative_boundaries"]:
        raise EvaluationError("AUTHORITY_PROJECTION_MISMATCH", "public boundaries changed")
    if contract["planner_output_schema"] != "V2_PLANNER_V1":
        raise EvaluationError("INVALID_FIXTURE", "fixture public contract must use V2_PLANNER_V1")
    return contract


def validate_hidden_gold(
    path: Path, authority_case: dict[str, Any], case_id: str,
) -> dict[str, Any]:
    gold = require_fields(load_json(path), HIDDEN_GOLD_FIELDS, "hidden gold")
    if gold["schema_version"] != SCHEMA_VERSION or gold["case_id"] != case_id:
        raise EvaluationError("INVALID_FIXTURE", "hidden gold identity is invalid")
    expected = {
        "critical_requirement_ids": authority_case["canonical_requirement_ids"],
        "critical_obligation_ids": authority_case["canonical_obligation_ids"],
        "required_negative_boundary_ids": [
            item["boundary_id"] for item in authority_case["negative_boundaries"]
        ],
        "forbidden_scope_claims": authority_case["forbidden_scope_claims"],
        "forbidden_evidence_claims": authority_case["forbidden_evidence_claims"],
        "expected_transitions": authority_case["expected_transitions"],
    }
    for field, value in expected.items():
        if gold[field] != value:
            raise EvaluationError("AUTHORITY_PROJECTION_MISMATCH", f"hidden gold changed: {field}")
    if not all(gold[field] for field in (
        "critical_requirement_ids", "critical_obligation_ids",
        "required_negative_boundary_ids",
    )):
        raise EvaluationError("INVALID_FIXTURE", "hidden scoring sets must be non-empty")
    return gold


def validate_fixture_manifest(fixtures: Path) -> dict[str, Any]:
    root = strict_root(fixtures)
    manifest_path = fixture_owned_path(root, "manifest.json", "fixture manifest")
    manifest = require_fields(load_json(manifest_path), FIXTURE_MANIFEST_FIELDS, "fixture manifest")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise EvaluationError("INVALID_FIXTURE", "unsupported fixture manifest schema")
    authority_ref = {
        "path": manifest["fixture_authority_path"],
        "sha256": manifest["fixture_authority_sha256"],
    }
    review_ref = {
        "path": manifest["authority_review_path"],
        "sha256": manifest["authority_review_sha256"],
    }
    _, authority_path = fixture_file_reference(root, authority_ref, "fixture authority")
    _, review_path = fixture_file_reference(root, review_ref, "authority review")
    if authority_ref["path"] != "fixture-authority.json" or review_ref["path"] != "fixture-authority-review.json":
        raise EvaluationError("INVALID_FIXTURE", "authority paths are not canonical")
    authority_receipt = validate_fixture_authority(root, authority_path)
    validate_fixture_authority_review_receipt(root, authority_path, review_path)
    if manifest["source_bundle_sha256"] != authority_receipt["source_bundle_sha256"]:
        raise EvaluationError("AUTHORITY_PROJECTION_MISMATCH", "source bundle identity changed")
    authority = load_json(authority_path)
    cases = manifest["cases"]
    if not isinstance(cases, list) or [item.get("case_id") for item in cases if isinstance(item, dict)] != list(CASE_IDS):
        raise EvaluationError("INVALID_FIXTURE", "fixture cases must use the canonical order")
    controller = plan_owner()
    source_records: list[dict[str, str]] = []
    validated_cases: list[dict[str, Any]] = []
    for index, raw_case in enumerate(cases):
        case = require_fields(raw_case, FIXTURE_CASE_FIELDS, f"fixture case {index}")
        case_id = CASE_IDS[index]
        authority_case = authority["cases"][index]
        if case["case_id"] != case_id or case["case_class"] != CASE_CLASSES[case_id]:
            raise EvaluationError("AUTHORITY_PROJECTION_MISMATCH", "case identity changed")
        expected_sources = authority_source_projection(authority_case)
        if case["source_refs"] != expected_sources:
            raise EvaluationError("AUTHORITY_PROJECTION_MISMATCH", f"source projection changed for {case_id}")
        for source_index, raw_source in enumerate(case["source_refs"]):
            source, _ = fixture_file_reference(
                root, raw_source, f"{case_id} source {source_index}", source=True,
            )
            source_records.append({"case_id": case_id, **source})
        expected_visible = [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in authority_case["visible_evidence"]
        ]
        if case["visible_inputs"] != expected_visible:
            raise EvaluationError("AUTHORITY_PROJECTION_MISMATCH", f"visible inputs changed for {case_id}")
        for visible_index, raw_visible in enumerate(case["visible_inputs"]):
            fixture_file_reference(root, raw_visible, f"{case_id} visible input {visible_index}")
        if case["implementation_sources"] != authority_case["implementation_roots"]:
            raise EvaluationError("AUTHORITY_PROJECTION_MISMATCH", f"implementation roots changed for {case_id}")
        public_ref, public_path = fixture_file_reference(root, case["public_contract"], f"{case_id} public contract")
        hidden_ref, hidden_path = fixture_file_reference(root, case["hidden_gold"], f"{case_id} hidden gold")
        public = validate_public_contract(public_path, authority_case, case_id)
        hidden = validate_hidden_gold(hidden_path, authority_case, case_id)
        inputs = require_fields(case["controller_inputs"], CONTROLLER_INPUT_FIELDS, f"{case_id} controller inputs")
        charter_ref, charter_path = fixture_file_reference(root, inputs["charter"], f"{case_id} charter")
        try:
            charter = controller.validate_charter(load_json(charter_path))
            if inputs["entry_mode"] == "DIRECT":
                requirements_ref, requirements_path = fixture_file_reference(
                    root, inputs["direct_requirements"], f"{case_id} direct requirements",
                )
                evidence_ref, evidence_path = fixture_file_reference(
                    root, inputs["direct_evidence_index"], f"{case_id} direct evidence",
                )
                requirements = controller.validate_requirements(load_json(requirements_path), direct=True)
                controller.validate_evidence(load_json(evidence_path), charter, requirements)
                if case["research_resume_package"] is not None:
                    raise EvaluationError("INVALID_FIXTURE", "DIRECT case cannot have a research package")
            elif inputs["entry_mode"] == "RESEARCH_PACKAGE":
                if inputs["direct_requirements"] is not None or inputs["direct_evidence_index"] is not None:
                    raise EvaluationError("INVALID_FIXTURE", "RESEARCH_PACKAGE forbids direct inputs")
                package_ref = require_fields(
                    case["research_resume_package"], {"path", "tree_sha256"},
                    f"{case_id} research package",
                )
                package_path = fixture_owned_directory(
                    root, package_ref["path"], f"{case_id} research package",
                )
                require_sha256(package_ref["tree_sha256"], "research package tree_sha256")
                if tree_owner().TREE_SHA256_V1(package_path) != package_ref["tree_sha256"]:
                    raise EvaluationError("FIXTURE_DRIFT", "research package tree changed")
                research_owner().validate_package(package_path)
            else:
                raise EvaluationError("INVALID_FIXTURE", "unknown controller entry mode")
        except EvaluationError:
            raise
        except Exception as exc:
            raise EvaluationError("INVALID_CONTROLLER_INPUT", f"{case_id}: {exc}") from exc
        validated_cases.append({
            "manifest": case,
            "authority": authority_case,
            "public": public,
            "hidden": hidden,
            "public_ref": public_ref,
            "hidden_ref": hidden_ref,
            "charter_ref": charter_ref,
        })
    expected_bundle = sha256_bytes(canonical_bytes(sorted(
        source_records,
        key=lambda item: tuple(
            str(item[field]).encode("utf-8") for field in ("case_id", "evidence_id", "path", "sha256")
        ),
    )))
    if expected_bundle != manifest["source_bundle_sha256"]:
        raise EvaluationError("FIXTURE_DRIFT", "fixture source bundle digest changed")
    return {
        "root": root, "manifest_path": manifest_path, "manifest": manifest,
        "authority_path": authority_path, "authority": authority,
        "review_path": review_path, "cases": validated_cases,
    }


def copy_run_fixture_file(
    fixture_root: Path, run_build_root: Path, relative: str, destination: str,
) -> dict[str, str]:
    source = fixture_owned_path(fixture_root, relative, "run fixture input")
    target = run_build_root.joinpath(*PurePosixPath(destination).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = source.read_bytes()
    atomic_write_bytes(target, payload)
    return {"path": destination, "sha256": sha256_bytes(payload)}


def empty_matrix_row(
    *, run_id: str, case_id: str, arm: str, role: str, phase: str,
    execution_kind: str, status: str, consumes_run_id: str | None = None,
    resume_of_run_id: str | None = None, controller_lineage_id: str | None = None,
) -> dict[str, Any]:
    row = {field: None for field in MATRIX_ROW_FIELDS}
    row.update({
        "run_id": run_id, "case_id": case_id, "arm": arm, "role": role,
        "phase": phase, "execution_kind": execution_kind,
        "consumes_run_id": consumes_run_id, "resume_of_run_id": resume_of_run_id,
        "controller_lineage_id": controller_lineage_id, "outer_attempt_ids": [],
        "status": status,
    })
    return row


def prepare(fixtures: Path, authority_path: Path, review_path: Path, run_dir: Path) -> dict[str, Any]:
    validated = validate_fixture_manifest(fixtures)
    fixture_root = validated["root"]
    if authority_path.resolve(strict=True) != validated["authority_path"] or review_path.resolve(strict=True) != validated["review_path"]:
        raise EvaluationError("INVALID_FIXTURE", "prepare authority arguments must match the manifest")
    if not run_dir.is_absolute():
        raise EvaluationError("INVALID_PATH", "run directory must be absolute")
    run_dir.mkdir(parents=True, exist_ok=True)
    root = strict_root(run_dir)
    state_path = root / "prepared-run.json"
    if state_path.exists():
        _, _, state = load_prepared_run(root)
        if (
            state.get("fixture_root") != str(fixture_root)
            or state.get("fixture_tree_sha256") != tree_owner().TREE_SHA256_V1(fixture_root)
        ):
            raise EvaluationError("PREPARE_REPLAY_CONFLICT", "prepared run fixture identity changed")
        return state
    if any(root.iterdir()):
        raise EvaluationError("INVALID_RUN", "prepare requires an empty run directory")
    build = root / ".prepare-staging"
    build.mkdir()
    try:
        authority_snapshot = copy_run_fixture_file(
            fixture_root, build, "fixture-authority.json", "authorities/fixture-authority.json",
        )
        review_snapshot = copy_run_fixture_file(
            fixture_root, build, "fixture-authority-review.json",
            "authorities/fixture-authority-review.json",
        )
        implementer_schema = copy_run_fixture_file(
            fixture_root, build, "implementer-output-contract.json",
            "contracts/implementer-output-contract.json",
        )
        controller = plan_owner()
        source_snapshots: dict[str, list[dict[str, Any]]] = {}
        for case in validated["cases"]:
            case_id = case["manifest"]["case_id"]
            source_snapshots[case_id] = []
            for source in case["manifest"]["implementation_sources"]:
                source_root = (REPO_ROOT / source["path"]).resolve(strict=True)
                if tree_owner().TREE_SHA256_V1(source_root) != source["tree_sha256"]:
                    raise EvaluationError("FIXTURE_DRIFT", f"implementation source changed: {source['path']}")
                try:
                    snapshot = controller.create_source_snapshot(
                        build, f"{case_id}:{source['repository_key']}", source_root,
                    )
                    controller.validate_source_snapshot(build, snapshot)
                except Exception as exc:
                    raise EvaluationError("SOURCE_SNAPSHOT_FAILED", str(exc)) from exc
                source_snapshots[case_id].append(snapshot)

        rows = [
            empty_matrix_row(run_id="legacy-small-planner", case_id="small-grounded", arm="legacy", role="planner", phase="initial", execution_kind="SINGLE_AGENT", status="PREPARED"),
            empty_matrix_row(run_id="legacy-small-implementer", case_id="small-grounded", arm="legacy", role="implementer", phase="initial", execution_kind="SINGLE_AGENT", status="WAITING_ON_DEPENDENCY", consumes_run_id="legacy-small-planner"),
            empty_matrix_row(run_id="legacy-substantial-planner", case_id="substantial-multisurface", arm="legacy", role="planner", phase="initial", execution_kind="SINGLE_AGENT", status="PREPARED"),
            empty_matrix_row(run_id="legacy-substantial-implementer", case_id="substantial-multisurface", arm="legacy", role="implementer", phase="initial", execution_kind="SINGLE_AGENT", status="WAITING_ON_DEPENDENCY", consumes_run_id="legacy-substantial-planner"),
            empty_matrix_row(run_id="legacy-uncertain-planner", case_id="evidence-uncertain", arm="legacy", role="planner", phase="initial", execution_kind="SINGLE_AGENT", status="PREPARED"),
            empty_matrix_row(run_id="legacy-uncertain-implementer", case_id="evidence-uncertain", arm="legacy", role="implementer", phase="initial", execution_kind="SINGLE_AGENT", status="WAITING_ON_DEPENDENCY", consumes_run_id="legacy-uncertain-planner"),
            empty_matrix_row(run_id="v2-small-planner", case_id="small-grounded", arm="v2", role="planner", phase="initial", execution_kind="PARENT_ORCHESTRATED_V2", status="WAITING_ON_INITIALIZATION", controller_lineage_id="v2-small-planner"),
            empty_matrix_row(run_id="v2-small-implementer", case_id="small-grounded", arm="v2", role="implementer", phase="initial", execution_kind="SINGLE_AGENT", status="WAITING_ON_DEPENDENCY", consumes_run_id="v2-small-planner"),
            empty_matrix_row(run_id="v2-substantial-planner", case_id="substantial-multisurface", arm="v2", role="planner", phase="initial", execution_kind="PARENT_ORCHESTRATED_V2", status="WAITING_ON_INITIALIZATION", controller_lineage_id="v2-substantial-planner"),
            empty_matrix_row(run_id="v2-substantial-implementer", case_id="substantial-multisurface", arm="v2", role="implementer", phase="initial", execution_kind="SINGLE_AGENT", status="WAITING_ON_DEPENDENCY", consumes_run_id="v2-substantial-planner"),
            empty_matrix_row(run_id="v2-uncertain-initial-planner", case_id="evidence-uncertain", arm="v2", role="planner", phase="initial", execution_kind="PARENT_ORCHESTRATED_V2", status="WAITING_ON_INITIALIZATION", controller_lineage_id="v2-uncertain-initial-planner"),
            empty_matrix_row(run_id="v2-uncertain-resumed-planner", case_id="evidence-uncertain", arm="v2", role="planner", phase="resumed", execution_kind="PARENT_ORCHESTRATED_V2", status="WAITING_ON_RESUME", resume_of_run_id="v2-uncertain-initial-planner", controller_lineage_id="v2-uncertain-initial-planner"),
            empty_matrix_row(run_id="v2-uncertain-implementer", case_id="evidence-uncertain", arm="v2", role="implementer", phase="resumed", execution_kind="SINGLE_AGENT", status="WAITING_ON_DEPENDENCY", consumes_run_id="v2-uncertain-resumed-planner"),
        ]
        case_by_id = {item["manifest"]["case_id"]: item for item in validated["cases"]}
        for row in rows:
            case = case_by_id[row["case_id"]]
            row_root = build / f"rows/{row['run_id']}"
            row_root.mkdir(parents=True, exist_ok=True)
            if row["role"] == "planner":
                visible = [
                    copy_run_fixture_file(
                        fixture_root, build, item["path"],
                        f"rows/{row['run_id']}/visible/{Path(item['path']).name}",
                    )
                    for item in case["manifest"]["visible_inputs"]
                ]
                public = dict(case["public"])
                public["planner_output_schema"] = (
                    "LEGACY_PLANNER_V1" if row["arm"] == "legacy" else "V2_PLANNER_V1"
                )
                public["planner_output_contract"] = planner_public_output_contract(row)
                public["consulted_sources_artifact_contract"] = consulted_sources_public_contract()
                public_path = row_root / "public-contract.json"
                atomic_write_json(public_path, public)
                output_contract = {
                    "path": f"rows/{row['run_id']}/public-contract.json",
                    "sha256": sha256_bytes(public_path.read_bytes()),
                }
                controller_inputs = None
                if row["arm"] == "v2":
                    raw_inputs = case["manifest"]["controller_inputs"]
                    controller_inputs = {"entry_mode": raw_inputs["entry_mode"]}
                    for field in ("charter", "direct_requirements", "direct_evidence_index"):
                        reference = raw_inputs[field]
                        controller_inputs[field] = (
                            copy_run_fixture_file(
                                fixture_root, build, reference["path"],
                                f"rows/{row['run_id']}/controller/{Path(reference['path']).name}",
                            )
                            if reference is not None else None
                        )
                envelope = {
                    "schema_version": SCHEMA_VERSION, "run_id": row["run_id"],
                    "case_id": row["case_id"], "arm": row["arm"], "role": row["role"],
                    "phase": row["phase"], "request": case["authority"]["request"],
                    "visible_evidence": visible, "controller_inputs": controller_inputs,
                    "plan_input": None, "research_package": None,
                    "implementation_sources": None, "output_contract": output_contract,
                }
            else:
                envelope = {
                    "schema_version": SCHEMA_VERSION, "run_id": row["run_id"],
                    "case_id": row["case_id"], "arm": row["arm"], "role": row["role"],
                    "phase": row["phase"], "request": None, "visible_evidence": None,
                    "controller_inputs": None, "plan_input": None,
                    "research_package": None,
                    "implementation_sources": source_snapshots[row["case_id"]],
                    "output_contract": implementer_schema,
                }
            input_path = row_root / "input.json"
            atomic_write_json(input_path, envelope)
            if row["role"] == "planner" and row["phase"] == "initial":
                row["input_envelope_path"] = f"rows/{row['run_id']}/input.json"
                row["input_envelope_sha256"] = sha256_bytes(input_path.read_bytes())

        requests = {
            "explicit": {
                "schema_version": SCHEMA_VERSION, "probe": "CANDIDATE_EXPLICIT",
                "invocation": "$plan-playbook-v2",
                "request": "Create a grounded implementation plan for the supplied task.",
                "output_contract": routing_public_output_contract(),
            },
            "ordinary": {
                "schema_version": SCHEMA_VERSION, "probe": "ORDINARY_LEGACY",
                "invocation": None,
                "request": "Create a grounded implementation plan for the supplied task.",
                "output_contract": routing_public_output_contract(),
            },
        }
        request_refs: dict[str, str] = {}
        for name, request in requests.items():
            path = build / f"candidate-checks/requests/{name}.json"
            atomic_write_json(path, request)
            request_refs[f"{name}_path"] = f"candidate-checks/requests/{name}.json"
            request_refs[f"{name}_sha256"] = sha256_bytes(path.read_bytes())
        state = {
            "schema_version": SCHEMA_VERSION, "run_root": str(root),
            "fixture_root": str(fixture_root),
            "fixture_tree_sha256": tree_owner().TREE_SHA256_V1(fixture_root),
            "fixture_manifest_sha256": sha256_bytes(validated["manifest_path"].read_bytes()),
            "fixture_authority_path": authority_snapshot["path"],
            "fixture_authority_sha256": authority_snapshot["sha256"],
            "authority_review_path": review_snapshot["path"],
            "authority_review_sha256": review_snapshot["sha256"],
            "legacy_tree_sha256": tree_owner().TREE_SHA256_V1(REPO_ROOT / "skills/plan-playbook"),
            "candidate_tree_sha256": tree_owner().TREE_SHA256_V1(REPO_ROOT / "skills/plan-playbook"),
            "implementer_schema_sha256": implementer_schema["sha256"],
            "candidate_check_requests": request_refs, "candidate_check_attempts": [],
            "candidate_check_evidence_path": None, "candidate_check_evidence_sha256": None,
            "matrix": rows, "outer_attempts": [], "created_at_utc": utc_now(),
        }
        if set(state) != PREPARED_RUN_FIELDS or any(set(row) != MATRIX_ROW_FIELDS for row in rows):
            raise EvaluationError("INVALID_RUN", "prepared run shape is incomplete")
        for child in sorted(build.iterdir(), key=lambda path: os.fsencode(path.name)):
            os.replace(child, root / child.name)
        build.rmdir()
        atomic_write_json(state_path, state)
        return state
    except Exception:
        shutil.rmtree(build, ignore_errors=True)
        if not any(root.iterdir()):
            root.rmdir()
        raise


def prepared_run_path(run_dir: Path) -> tuple[Path, Path]:
    root = strict_root(run_dir)
    path = root / "prepared-run.json"
    if path.is_symlink() or not path.is_file():
        raise EvaluationError("INVALID_RUN", "prepared-run.json is missing")
    return root, path


def load_prepared_run(run_dir: Path) -> tuple[Path, Path, dict[str, Any]]:
    root, path = prepared_run_path(run_dir)
    state = load_json(path)
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise EvaluationError("INVALID_RUN", "prepared run schema is invalid")
    if set(state) != PREPARED_RUN_FIELDS:
        raise EvaluationError("INVALID_RUN", "prepared run fields are invalid")
    if state.get("run_root") != str(root):
        raise EvaluationError("INVALID_RUN", "prepared run root identity changed")
    for field in ("matrix", "outer_attempts", "candidate_check_attempts"):
        if not isinstance(state.get(field), list):
            raise EvaluationError("INVALID_RUN", f"prepared run {field} must be an array")
    if len(state["matrix"]) != 13 or any(
        not isinstance(row, dict) or set(row) != MATRIX_ROW_FIELDS for row in state["matrix"]
    ):
        raise EvaluationError("INVALID_RUN", "prepared run matrix must contain 13 exact rows")
    run_ids = [row["run_id"] for row in state["matrix"]]
    if len(run_ids) != len(set(run_ids)):
        raise EvaluationError("INVALID_RUN", "prepared run matrix contains duplicate run IDs")
    for row in state["matrix"]:
        validate_input_envelope(root, row)
    return root, path, state


def state_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run_owned_relative(root: Path, path: Path, label: str, *, must_exist: bool) -> str:
    if not path.is_absolute():
        path = path.absolute()
    if must_exist:
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise EvaluationError("INVALID_PATH", f"missing {label}") from exc
    else:
        try:
            parent = path.parent.resolve(strict=True)
        except OSError as exc:
            raise EvaluationError("INVALID_PATH", f"missing {label} parent") from exc
        resolved = parent / path.name
    if path.is_symlink() or (resolved != root and root not in resolved.parents):
        raise EvaluationError("INVALID_PATH", f"{label} escapes run root")
    return resolved.relative_to(root).as_posix()


def validate_run_file_ref(root: Path, value: Any, label: str) -> dict[str, str]:
    reference = require_fields(value, FILE_REF_FIELDS, label)
    relative = require_string(reference["path"], f"{label} path")
    path = root / relative
    if run_owned_relative(root, path, label, must_exist=True) != relative:
        raise EvaluationError("INVALID_PATH", f"{label} path is not normalized")
    if sha256_bytes(path.read_bytes()) != require_sha256(reference["sha256"], f"{label} sha256"):
        raise EvaluationError("INPUT_TAMPER", f"{label} hash changed")
    return reference


def validate_input_envelope(root: Path, row: dict[str, Any]) -> dict[str, Any]:
    fixed_relative = f"rows/{row['run_id']}/input.json"
    fixed_path = root / fixed_relative
    envelope = require_fields(load_json(fixed_path), INPUT_ENVELOPE_FIELDS, "input envelope")
    for field in ("run_id", "case_id", "arm", "role", "phase"):
        if envelope[field] != row[field]:
            raise EvaluationError("INVALID_INPUT_ENVELOPE", f"input envelope {field} changed")
    if envelope["schema_version"] != SCHEMA_VERSION:
        raise EvaluationError("INVALID_INPUT_ENVELOPE", "input envelope schema is invalid")
    if row["input_envelope_path"] is not None:
        if row["input_envelope_path"] != fixed_relative:
            raise EvaluationError("INVALID_INPUT_ENVELOPE", "bound input path changed")
        if sha256_bytes(fixed_path.read_bytes()) != row["input_envelope_sha256"]:
            raise EvaluationError("INPUT_TAMPER", "bound input envelope changed")
    elif row["input_envelope_sha256"] is not None:
        raise EvaluationError("INVALID_INPUT_ENVELOPE", "unbound input has a hash")

    output_contract = validate_run_file_ref(root, envelope["output_contract"], "output contract")
    del output_contract
    if row["role"] == "planner":
        require_string(envelope["request"], "planner request")
        visible = envelope["visible_evidence"]
        if not isinstance(visible, list) or not visible:
            raise EvaluationError("INVALID_INPUT_ENVELOPE", "planner visible_evidence must be non-empty")
        for index, reference in enumerate(visible):
            validate_run_file_ref(root, reference, f"visible evidence {index}")
        if envelope["plan_input"] is not None or envelope["implementation_sources"] is not None:
            raise EvaluationError("INVALID_INPUT_ENVELOPE", "planner input contains implementer-only fields")
        if row["arm"] == "legacy":
            if envelope["controller_inputs"] is not None or envelope["research_package"] is not None:
                raise EvaluationError("INVALID_INPUT_ENVELOPE", "legacy planner received candidate inputs")
        else:
            inputs = require_fields(
                envelope["controller_inputs"], CONTROLLER_INPUT_FIELDS,
                "planner controller inputs",
            )
            if inputs["entry_mode"] not in {"DIRECT", "RESEARCH_PACKAGE"}:
                raise EvaluationError("INVALID_INPUT_ENVELOPE", "controller entry mode is invalid")
            validate_run_file_ref(root, inputs["charter"], "controller charter")
            for field in ("direct_requirements", "direct_evidence_index"):
                if inputs[field] is not None:
                    validate_run_file_ref(root, inputs[field], f"controller {field}")
            if inputs["entry_mode"] == "DIRECT" and (
                inputs["direct_requirements"] is None or inputs["direct_evidence_index"] is None
            ):
                raise EvaluationError("INVALID_INPUT_ENVELOPE", "DIRECT controller inputs are incomplete")
            if inputs["entry_mode"] == "RESEARCH_PACKAGE" and (
                inputs["direct_requirements"] is not None or inputs["direct_evidence_index"] is not None
            ):
                raise EvaluationError("INVALID_INPUT_ENVELOPE", "RESEARCH_PACKAGE contains direct inputs")
            if envelope["research_package"] is not None:
                package = require_fields(
                    envelope["research_package"], {"path", "tree_sha256"},
                    "research package",
                )
                relative = require_string(package["path"], "research package path")
                package_path = root / relative
                if run_owned_relative(root, package_path, "research package", must_exist=True) != relative:
                    raise EvaluationError("INVALID_PATH", "research package path is not normalized")
                if tree_owner().TREE_SHA256_V1(package_path) != require_sha256(
                    package["tree_sha256"], "research package tree_sha256",
                ):
                    raise EvaluationError("INPUT_TAMPER", "research package tree changed")
    else:
        for field in ("request", "visible_evidence", "controller_inputs", "research_package"):
            if envelope[field] is not None:
                raise EvaluationError("INVALID_INPUT_ENVELOPE", f"implementer {field} must be null")
        sources = envelope["implementation_sources"]
        if not isinstance(sources, list) or not sources:
            raise EvaluationError("INVALID_INPUT_ENVELOPE", "implementer sources must be non-empty")
        for source in sources:
            try:
                plan_owner().validate_source_snapshot(root, source)
            except Exception as exc:
                raise EvaluationError("INVALID_INPUT_ENVELOPE", str(exc)) from exc
        if row["status"] == "PREPARED" and envelope["plan_input"] is None:
            raise EvaluationError("INVALID_INPUT_ENVELOPE", "prepared implementer has no plan input")
    return envelope


def matrix_row(state: dict[str, Any], run_id: str) -> dict[str, Any]:
    matches = [row for row in state["matrix"] if isinstance(row, dict) and row.get("run_id") == run_id]
    if len(matches) != 1:
        raise EvaluationError("INVALID_RUN", "run ID must identify exactly one matrix row")
    return matches[0]


def controller_live_state_relative(lineage_id: str) -> str:
    return f"controller-lineages/{lineage_id}/task/.plan-playbook-v2/state.json"


def initialize_successor(
    state: dict[str, Any], run_id: str, controller_state_path: str,
    controller_state_sha256: str, target_status: str, started_at: str,
) -> tuple[dict[str, Any], bytes]:
    successor = json.loads(json.dumps(state))
    row = matrix_row(successor, run_id)
    row.update(
        controller_state_path=controller_state_path,
        controller_state_sha256=controller_state_sha256,
        started_at_utc=started_at,
        status=target_status,
    )
    payload = canonical_bytes(successor) + b"\n"
    return successor, payload


def initialize_planner(
    run_dir: Path, run_id: str, *, now: str | None = None,
) -> dict[str, Any]:
    root, state_path, state = load_prepared_run(run_dir)
    row = matrix_row(state, require_string(run_id, "run_id"))
    if not (
        row["arm"] == "v2" and row["role"] == "planner" and row["phase"] == "initial"
        and row["controller_lineage_id"] == run_id
    ):
        raise EvaluationError("INVALID_ROW_STATE", "initialize-planner requires a candidate initial planner")
    envelope = validate_input_envelope(root, row)
    transaction_path = root / f"initialization/{run_id}/transaction.json"
    snapshot_relative = f"rows/{run_id}/controller-state.json"
    snapshot_path = root / snapshot_relative
    live_relative = controller_live_state_relative(run_id)
    live_path = root / live_relative
    predecessor_sha = state_sha256(state_path)

    transaction = load_json(transaction_path) if transaction_path.exists() else None
    if transaction is not None:
        fields = (
            INITIALIZATION_INTENT_FIELDS
            if transaction.get("state") == "INTENT"
            else INITIALIZATION_COMPLETED_FIELDS
        )
        transaction = require_fields(transaction, fields, "initialization transaction")
        immutable = {
            "run_id": run_id,
            "input_envelope_sha256": row["input_envelope_sha256"],
            "controller_lineage_id": run_id,
            "controller_live_state_path": live_relative,
            "controller_state_path": snapshot_relative,
        }
        if any(transaction.get(field) != value for field, value in immutable.items()):
            raise EvaluationError("INITIALIZATION_REPLAY_CONFLICT", "initialization identity changed")
        if transaction["state"] == "COMPLETED":
            result = require_fields(transaction["result"], INITIALIZE_RESULT_FIELDS, "initialize result")
            successor, payload = initialize_successor(
                state, run_id, snapshot_relative, transaction["controller_state_sha256"],
                transaction["target_row_status"], transaction["started_at_utc"],
            )
            if row["status"] == transaction["target_row_status"]:
                if state_sha256(state_path) != result["prepared_run_sha256"]:
                    raise EvaluationError("INITIALIZATION_REPLAY_CONFLICT", "initialized matrix changed")
                return result
            if row["status"] != "WAITING_ON_INITIALIZATION" or predecessor_sha != transaction["predecessor_prepared_run_sha256"]:
                raise EvaluationError("INITIALIZATION_REPLAY_CONFLICT", "initialization predecessor changed")
            if sha256_bytes(payload) != result["prepared_run_sha256"]:
                raise EvaluationError("INITIALIZATION_REPLAY_CONFLICT", "initialization successor changed")
            atomic_write_bytes(state_path, payload)
            del successor
            return result
        if predecessor_sha != transaction["predecessor_prepared_run_sha256"]:
            raise EvaluationError("INITIALIZATION_REPLAY_CONFLICT", "initialization predecessor changed")
    else:
        if row["status"] != "WAITING_ON_INITIALIZATION" or live_path.exists() or snapshot_path.exists():
            raise EvaluationError("INITIALIZATION_REPLAY_CONFLICT", "unowned initialization state exists")
        created_at = now or utc_now()
        transaction = {
            "schema_version": SCHEMA_VERSION, "state": "INTENT", "run_id": run_id,
            "predecessor_prepared_run_sha256": predecessor_sha,
            "input_envelope_sha256": row["input_envelope_sha256"],
            "controller_lineage_id": run_id,
            "controller_live_state_path": live_relative,
            "controller_state_path": snapshot_relative, "created_at_utc": created_at,
        }
        atomic_write_json(transaction_path, transaction)

    if not live_path.exists():
        task_root = live_path.parents[1]
        task_root.mkdir(parents=True, exist_ok=True)
        inputs = envelope["controller_inputs"]
        args = argparse.Namespace(
            state_json=str(live_path), task_directory=str(task_root),
            charter=str(root / inputs["charter"]["path"]),
            entry_mode=inputs["entry_mode"],
            task_size="light" if row["case_id"] == "small-grounded" else "standard",
            approval_context="ORDINARY", convergence_state=None,
            requirements=(
                str(root / inputs["direct_requirements"]["path"])
                if inputs["direct_requirements"] is not None else None
            ),
            evidence_index=(
                str(root / inputs["direct_evidence_index"]["path"])
                if inputs["direct_evidence_index"] is not None else None
            ),
            supplied_input_root=None, research_package=None,
        )
        try:
            plan_owner().cmd_init(args)
        except Exception as exc:
            code = getattr(exc, "code", "CONTROLLER_INIT_FAILED")
            raise EvaluationError(str(code), str(exc)) from exc
    try:
        controller_state, _task_root, _run_root = plan_owner().load_state(live_path)
    except Exception as exc:
        raise EvaluationError("INVALID_CONTROLLER_STATE", str(exc)) from exc
    if controller_state["task_root"] != str(live_path.parents[1]):
        raise EvaluationError("INVALID_CONTROLLER_STATE", "controller task root changed")
    if controller_state["status"] not in {"INITIALIZED", "BLOCKED"}:
        raise EvaluationError("INVALID_CONTROLLER_STATE", "controller initialization is not terminal")
    target_status = "PREPARED" if controller_state["status"] == "INITIALIZED" else "BLOCKED_READY_TO_RECORD"
    raw_state = live_path.read_bytes()
    controller_sha = sha256_bytes(raw_state)
    if snapshot_path.exists() and snapshot_path.read_bytes() != raw_state:
        raise EvaluationError("INITIALIZATION_REPLAY_CONFLICT", "controller snapshot changed")
    atomic_write_bytes(snapshot_path, raw_state)
    started_at = require_string(controller_state["started_at_utc"], "controller started_at_utc")
    successor, successor_bytes = initialize_successor(
        state, run_id, snapshot_relative, controller_sha, target_status, started_at,
    )
    successor_sha = sha256_bytes(successor_bytes)
    result = {
        "schema_version": SCHEMA_VERSION, "command": "initialize-planner", "ok": True,
        "run_id": run_id, "status": target_status,
        "controller_state_path": snapshot_relative,
        "controller_state_sha256": controller_sha,
        "prepared_run_sha256": successor_sha,
        "code": (
            "PLANNER_INITIALIZED" if target_status == "PREPARED"
            else "PLANNER_BLOCKED_READY_TO_RECORD"
        ),
    }
    completed = {
        "schema_version": SCHEMA_VERSION, "state": "COMPLETED", "run_id": run_id,
        "predecessor_prepared_run_sha256": predecessor_sha,
        "input_envelope_sha256": row["input_envelope_sha256"],
        "controller_lineage_id": run_id, "controller_live_state_path": live_relative,
        "controller_state_path": snapshot_relative,
        "controller_state_sha256": controller_sha, "target_row_status": target_status,
        "started_at_utc": started_at, "result": result,
    }
    atomic_write_json(transaction_path, completed)
    atomic_write_bytes(state_path, successor_bytes)
    del successor
    return result


def reopen_row_artifact(
    root: Path, row: dict[str, Any], path_field: str, hash_field: str, *, tree: bool = False,
) -> Path:
    relative = require_string(row.get(path_field), path_field)
    path = root / relative
    if run_owned_relative(root, path, path_field, must_exist=True) != relative:
        raise EvaluationError("INVALID_PATH", f"{path_field} is not normalized")
    expected = require_sha256(row.get(hash_field), hash_field)
    actual = tree_owner().TREE_SHA256_V1(path) if tree else sha256_bytes(path.read_bytes())
    if actual != expected:
        raise EvaluationError("ARTIFACT_TAMPER", f"{path_field} changed")
    return path


def load_recorded_output(root: Path, row: dict[str, Any]) -> dict[str, Any]:
    if row["status"] != "RECORDED":
        raise EvaluationError("INVALID_ROW_STATE", "producer is not recorded")
    return load_json(reopen_row_artifact(root, row, "output_path", "output_sha256"))


def materialize_input(run_dir: Path, run_id: str) -> dict[str, Any]:
    root, state_path, state = load_prepared_run(run_dir)
    row = matrix_row(state, require_string(run_id, "run_id"))
    if row["role"] != "implementer" or row["consumes_run_id"] is None:
        raise EvaluationError("INVALID_ROW_STATE", "materialize-input requires a dependent implementer")
    producer = matrix_row(state, row["consumes_run_id"])
    output = load_recorded_output(root, producer)
    if output.get("terminal_verdict") != "PASS":
        raise EvaluationError("INVALID_ROW_STATE", "implementer producer did not pass")
    plan_path = reopen_row_artifact(root, producer, "plan_snapshot_path", "plan_snapshot_sha256")
    if producer["arm"] == "v2":
        package_path = reopen_row_artifact(
            root, producer, "package_snapshot_path", "package_snapshot_tree_sha256", tree=True,
        )
        plan_input = {
            "path": package_path.relative_to(root).as_posix(),
            "tree_sha256": producer["package_snapshot_tree_sha256"],
        }
    else:
        plan_input = {
            "path": plan_path.relative_to(root).as_posix(),
            "sha256": producer["plan_snapshot_sha256"],
        }
    fixed_relative = f"rows/{run_id}/input.json"
    fixed_path = root / fixed_relative
    envelope = require_fields(load_json(fixed_path), INPUT_ENVELOPE_FIELDS, "implementer input")
    expected = {**envelope, "plan_input": plan_input}
    expected_bytes = canonical_bytes(expected) + b"\n"
    if row["status"] == "PREPARED":
        if fixed_path.read_bytes() != expected_bytes or row["input_envelope_sha256"] != sha256_bytes(expected_bytes):
            raise EvaluationError("MATERIALIZE_REPLAY_CONFLICT", "implementer input changed")
        return {
            "schema_version": SCHEMA_VERSION, "command": "materialize-input", "ok": True,
            "run_id": run_id, "status": "PREPARED",
            "input_envelope_path": fixed_relative,
            "input_envelope_sha256": row["input_envelope_sha256"],
            "code": "INPUT_MATERIALIZED",
        }
    if row["status"] != "WAITING_ON_DEPENDENCY" or row["outer_attempt_ids"]:
        raise EvaluationError("INVALID_ROW_STATE", "implementer input cannot be materialized now")
    atomic_write_bytes(fixed_path, expected_bytes)
    row["input_envelope_path"] = fixed_relative
    row["input_envelope_sha256"] = sha256_bytes(expected_bytes)
    row["status"] = "PREPARED"
    atomic_write_json(state_path, state)
    validate_input_envelope(root, row)
    return {
        "schema_version": SCHEMA_VERSION, "command": "materialize-input", "ok": True,
        "run_id": run_id, "status": "PREPARED", "input_envelope_path": fixed_relative,
        "input_envelope_sha256": row["input_envelope_sha256"], "code": "INPUT_MATERIALIZED",
    }


def materialize_resume(run_dir: Path, run_id: str) -> dict[str, Any]:
    root, state_path, state = load_prepared_run(run_dir)
    row = matrix_row(state, require_string(run_id, "run_id"))
    if not (
        row["arm"] == "v2" and row["role"] == "planner" and row["phase"] == "resumed"
        and row["resume_of_run_id"] is not None
        and row["controller_lineage_id"] == row["resume_of_run_id"]
    ):
        raise EvaluationError("INVALID_ROW_STATE", "materialize-resume requires the resumed candidate row")
    predecessor = matrix_row(state, row["resume_of_run_id"])
    if predecessor["status"] != "RECORDED":
        raise EvaluationError("INVALID_ROW_STATE", "resume predecessor is not recorded")
    predecessor_output = load_recorded_output(root, predecessor)
    if predecessor_output.get("terminal_verdict") != "BLOCKED" or predecessor_output.get("blocker_code") != "RESEARCH_REQUIRED":
        raise EvaluationError("INVALID_ROW_STATE", "resume predecessor is not research-blocked")
    predecessor_state_path = reopen_row_artifact(
        root, predecessor, "terminal_controller_state_path", "terminal_controller_state_sha256",
    )
    predecessor_sha = predecessor["terminal_controller_state_sha256"]
    lineage = row["controller_lineage_id"]
    live_path = root / controller_live_state_relative(lineage)
    snapshot_relative = f"rows/{run_id}/controller-state.json"
    snapshot_path = root / snapshot_relative

    fixture = validate_fixture_manifest(Path(state["fixture_root"]))
    case = next(item for item in fixture["cases"] if item["manifest"]["case_id"] == row["case_id"])
    package_ref = case["manifest"]["research_resume_package"]
    if package_ref is None:
        raise EvaluationError("INVALID_FIXTURE", "resume case has no research package")
    external_package = fixture["root"] / package_ref["path"]
    if tree_owner().TREE_SHA256_V1(external_package) != package_ref["tree_sha256"]:
        raise EvaluationError("FIXTURE_DRIFT", "research resume package changed")
    try:
        plan_owner().research_owner().validate_package(external_package)
    except Exception as exc:
        raise EvaluationError("INVALID_RESEARCH_PACKAGE", str(exc)) from exc

    if row["status"] == "PREPARED":
        if (
            row["resumed_from_state_sha256"] != predecessor_sha
            or snapshot_path.read_bytes() != live_path.read_bytes()
            or sha256_bytes(snapshot_path.read_bytes()) != row["controller_state_sha256"]
        ):
            raise EvaluationError("RESUME_REPLAY_CONFLICT", "resumed controller state changed")
        validate_input_envelope(root, row)
        return {
            "schema_version": SCHEMA_VERSION, "command": "materialize-resume", "ok": True,
            "run_id": run_id, "status": "PREPARED",
            "controller_state_path": snapshot_relative,
            "controller_state_sha256": row["controller_state_sha256"],
            "input_envelope_sha256": row["input_envelope_sha256"], "code": "RESUME_MATERIALIZED",
        }
    if row["status"] != "WAITING_ON_RESUME":
        raise EvaluationError("INVALID_ROW_STATE", "resumed row cannot be materialized now")
    if live_path.read_bytes() != predecessor_state_path.read_bytes():
        raise EvaluationError("RESUME_BASIS_DRIFT", "live lineage differs from blocked predecessor")
    blocked_state, _task_root, _run_root = plan_owner().load_state(live_path)
    blocked_hash = plan_owner().canonical_hash(blocked_state)
    manifest_path = external_package / "manifest.json"
    manifest_ref = {"path": str(manifest_path), "sha256": sha256_bytes(manifest_path.read_bytes())}
    open_blockers = [item for item in blocked_state["blockers"] if item["status"] == "OPEN"]
    if not open_blockers or any(item["type"] != "EVIDENCE" for item in open_blockers):
        raise EvaluationError("INVALID_CONTROLLER_STATE", "blocked lineage has the wrong blocker set")
    resolution = {
        "schema_version": SCHEMA_VERSION, "blocked_state_sha256": blocked_hash,
        "resolutions": [
            {
                "blocker_id": item["id"], "type": "EVIDENCE",
                "evidence": [manifest_ref], "evidence_artifact": manifest_ref,
            }
            for item in open_blockers
        ],
    }
    resolution_path = root / f"rows/{run_id}/resume-source.json"
    if resolution_path.exists() and load_json(resolution_path) != resolution:
        raise EvaluationError("RESUME_REPLAY_CONFLICT", "resume resolution changed")
    atomic_write_json(resolution_path, resolution)
    bundle_dir = live_path.parent / f"resume/{blocked_hash}/bundle"
    prepare_args = argparse.Namespace(
        state_json=str(live_path), evidence_index=None, supplied_input_root=None,
        research_package=str(external_package), resolution_evidence=str(resolution_path),
        bundle_dir=str(bundle_dir),
    )
    try:
        plan_owner().cmd_prepare_resume_bundle(prepare_args)
        plan_owner().cmd_resume(argparse.Namespace(state_json=str(live_path), resume_bundle=str(bundle_dir)))
        resumed_state, _task_root, _run_root = plan_owner().load_state(live_path)
    except Exception as exc:
        code = getattr(exc, "code", "CONTROLLER_RESUME_FAILED")
        raise EvaluationError(str(code), str(exc)) from exc
    if resumed_state["status"] != "INITIALIZED":
        raise EvaluationError("INVALID_CONTROLLER_STATE", "controller did not resume to INITIALIZED")
    raw_state = live_path.read_bytes()
    atomic_write_bytes(snapshot_path, raw_state)
    bundled_package = bundle_dir / "research-package"
    package_tree = tree_owner().TREE_SHA256_V1(bundled_package)
    envelope_path = root / f"rows/{run_id}/input.json"
    envelope = require_fields(load_json(envelope_path), INPUT_ENVELOPE_FIELDS, "resume input")
    envelope["research_package"] = {
        "path": bundled_package.relative_to(root).as_posix(), "tree_sha256": package_tree,
    }
    envelope_bytes = canonical_bytes(envelope) + b"\n"
    atomic_write_bytes(envelope_path, envelope_bytes)
    row.update(
        controller_state_path=snapshot_relative,
        controller_state_sha256=sha256_bytes(raw_state),
        resumed_from_state_sha256=predecessor_sha,
        input_envelope_path=f"rows/{run_id}/input.json",
        input_envelope_sha256=sha256_bytes(envelope_bytes),
        started_at_utc=resumed_state["started_at_utc"], status="PREPARED",
    )
    atomic_write_json(state_path, state)
    validate_input_envelope(root, row)
    return {
        "schema_version": SCHEMA_VERSION, "command": "materialize-resume", "ok": True,
        "run_id": run_id, "status": "PREPARED", "controller_state_path": snapshot_relative,
        "controller_state_sha256": row["controller_state_sha256"],
        "input_envelope_sha256": row["input_envelope_sha256"], "code": "RESUME_MATERIALIZED",
    }


def validate_string_array(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    return require_string_list(value, label, nonempty=nonempty)


def validate_planner_output(value: Any, row: dict[str, Any]) -> dict[str, Any]:
    fields = CANDIDATE_PLANNER_OUTPUT_FIELDS if row["arm"] == "v2" else LEGACY_PLANNER_OUTPUT_FIELDS
    output = require_fields(value, fields, "planner output")
    if output["schema_version"] != SCHEMA_VERSION:
        raise EvaluationError("INVALID_PLANNER_OUTPUT", "planner output schema is invalid")
    for field in ("case_id", "arm", "phase"):
        if output[field] != row[field]:
            raise EvaluationError("INVALID_PLANNER_OUTPUT", f"planner output {field} changed")
    verdict = output["terminal_verdict"]
    if verdict not in {"PASS", "BLOCKED"} or output["evidence_status"] not in {"SUFFICIENT", "INSUFFICIENT"}:
        raise EvaluationError("INVALID_PLANNER_OUTPUT", "planner output enums are invalid")
    questions = validate_string_array(output["clarification_questions"], "clarification questions")
    choices = validate_string_array(output["unresolved_choices"], "unresolved choices")
    if verdict == "PASS":
        require_string(output["plan_path"], "planner plan_path")
        require_sha256(output["plan_sha256"], "planner plan_sha256")
        if output["evidence_status"] != "SUFFICIENT" or questions or choices:
            raise EvaluationError("INVALID_PLANNER_OUTPUT", "passing planner output has diagnostics")
        if row["arm"] == "v2" and (
            output["package_path"] is None or output["package_tree_sha256"] is None
            or output["blocker_code"] is not None
        ):
            raise EvaluationError("INVALID_PLANNER_OUTPUT", "candidate PASS package fields are invalid")
    else:
        if output["plan_path"] is not None or output["plan_sha256"] is not None or output["evidence_status"] != "INSUFFICIENT":
            raise EvaluationError("INVALID_PLANNER_OUTPUT", "blocked planner output has a plan")
        if row["arm"] == "legacy" and not (questions or choices):
            raise EvaluationError("INVALID_PLANNER_OUTPUT", "legacy BLOCKED output has no diagnostic")
        if row["arm"] == "v2" and (
            output["package_path"] is not None or output["package_tree_sha256"] is not None
            or output["blocker_code"] != "RESEARCH_REQUIRED" or questions or choices
        ):
            raise EvaluationError("INVALID_PLANNER_OUTPUT", "candidate BLOCKED output is invalid")
    return output


def validate_action(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    action = require_fields(value, fields, label)
    for field in fields - {"consulted_source_paths"}:
        require_string(action[field], f"{label} {field}")
    validate_string_array(action["consulted_source_paths"], f"{label} sources", nonempty=True)
    return action


def validate_implementer_output(value: Any, row: dict[str, Any], plan_sha256: str | None) -> dict[str, Any]:
    output = require_fields(value, IMPLEMENTER_OUTPUT_FIELDS, "implementer output")
    if output["schema_version"] != SCHEMA_VERSION or output["case_id"] != row["case_id"] or output["arm"] != row["arm"]:
        raise EvaluationError("INVALID_IMPLEMENTER_OUTPUT", "implementer output identity changed")
    if output["plan_hash"] != plan_sha256:
        raise EvaluationError("INVALID_IMPLEMENTER_OUTPUT", "implementer output plan hash changed")
    list_fields = (
        "clarification_questions", "missing_implementation_anchors",
        "missing_verification_anchors", "unresolved_choices", "scope_inventions",
        "evidence_inventions", "consulted_sources",
    )
    for field in list_fields:
        validate_string_array(output[field], f"implementer {field}")
    implementation = [
        validate_action(item, IMPLEMENTATION_ACTION_FIELDS, "implementation action")
        for item in output["implementation_actions"]
    ] if isinstance(output["implementation_actions"], list) else None
    verification = [
        validate_action(item, VERIFICATION_ACTION_FIELDS, "verification action")
        for item in output["verification_actions"]
    ] if isinstance(output["verification_actions"], list) else None
    if implementation is None or verification is None:
        raise EvaluationError("INVALID_IMPLEMENTER_OUTPUT", "implementer actions must be arrays")
    action_ids = [item["action_id"] for item in implementation + verification]
    if len(action_ids) != len(set(action_ids)):
        raise EvaluationError("INVALID_IMPLEMENTER_OUTPUT", "implementer action IDs must be unique")
    source_union = sorted({
        source for action in implementation + verification
        for source in action["consulted_source_paths"]
    })
    if output["consulted_sources"] != source_union:
        raise EvaluationError("INVALID_IMPLEMENTER_OUTPUT", "consulted source union changed")
    diagnostics = sum((output[field] for field in list_fields[:-1]), [])
    if output["can_implement"] is True:
        if output["non_implementation_reason"] is not None or diagnostics:
            raise EvaluationError("INVALID_IMPLEMENTER_OUTPUT", "implementable output has diagnostics")
    elif output["can_implement"] is False:
        require_string(output["non_implementation_reason"], "non_implementation_reason")
        if not diagnostics and output["non_implementation_reason"] != "NO_PLAN_FROM_BLOCKED_PLANNER":
            raise EvaluationError("INVALID_IMPLEMENTER_OUTPUT", "non-implementable output has no diagnostic")
    else:
        raise EvaluationError("INVALID_IMPLEMENTER_OUTPUT", "can_implement must be boolean")
    return output


def attempt_output_source(root: Path, attempt: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    relative = require_string(attempt["output_path"], "attempt output path")
    path = root / relative
    if sha256_bytes(path.read_bytes()) != require_sha256(attempt["output_sha256"], "attempt output sha256"):
        raise EvaluationError("OUTPUT_TAMPER", "attempt output changed")
    return path, load_json(path)


def resolve_agent_plan(root: Path, attempt_output: Path, output: dict[str, Any]) -> bytes:
    raw_path = Path(require_string(output["plan_path"], "planner plan_path"))
    candidate = raw_path if raw_path.is_absolute() else attempt_output.parent / raw_path
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise EvaluationError("INVALID_PLANNER_OUTPUT", "planner plan is missing") from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise EvaluationError("INVALID_PLANNER_OUTPUT", "planner plan must be a regular file")
    payload = resolved.read_bytes()
    if sha256_bytes(payload) != output["plan_sha256"]:
        raise EvaluationError("INVALID_PLANNER_OUTPUT", "planner plan hash changed")
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvaluationError("INVALID_PLANNER_OUTPUT", "planner plan must be UTF-8") from exc
    return payload


def validate_consulted_sources(
    path: Path, row: dict[str, Any], logical_output: dict[str, Any], *, require_nonempty: bool,
) -> bytes:
    value = require_fields(load_json(path.resolve(strict=True)), CONSULTED_SOURCES_FIELDS, "consulted sources")
    if value["schema_version"] != SCHEMA_VERSION or value["run_id"] != row["run_id"]:
        raise EvaluationError("INVALID_CONSULTED_SOURCES", "consulted source identity changed")
    paths = validate_string_array(value["paths"], "consulted source paths", nonempty=require_nonempty)
    if row["role"] == "planner" and paths:
        raise EvaluationError("INVALID_CONSULTED_SOURCES", "planner consulted sources must be empty")
    if row["role"] == "implementer" and paths != logical_output["consulted_sources"]:
        raise EvaluationError("INVALID_CONSULTED_SOURCES", "consulted source output differs")
    return canonical_bytes(value) + b"\n"


def successful_outer_attempt(
    root: Path, state: dict[str, Any], row: dict[str, Any], token_path: Path,
) -> dict[str, Any]:
    token = validate_attempt_token(root, token_path.resolve(strict=True))
    if token["kind"] != "OUTER" or token["subject_id"] != row["run_id"]:
        raise EvaluationError("INVALID_ATTEMPT_TOKEN", "successful token names another row")
    matches = [item for item in state["outer_attempts"] if item.get("attempt_id") == token["attempt_id"]]
    if len(matches) != 1 or matches[0]["status"] != "SUCCEEDED":
        raise EvaluationError("INVALID_ATTEMPT", "row has no unique successful attempt")
    attempt = require_fields(matches[0], OUTER_ATTEMPT_FIELDS, "outer attempt")
    if attempt["input_envelope_sha256"] != token["input_sha256"] or attempt["slot_id"] != token["slot_id"]:
        raise EvaluationError("INVALID_ATTEMPT", "successful attempt binding changed")
    return attempt


def derive_agent_runs(
    root: Path, state: dict[str, Any], row: dict[str, Any], slot_ledger: Path | None,
    controller_state: dict[str, Any] | None,
) -> tuple[bytes, bytes, str | None]:
    if slot_ledger is None:
        agents = {"schema_version": SCHEMA_VERSION, "run_id": row["run_id"], "agents": []}
        return canonical_bytes(agents) + b"\n", ZERO_AGENT_LEDGER_BYTES, None
    ledger_path = slot_ledger.resolve(strict=True)
    ledger_bytes = ledger_path.read_bytes()
    agents: list[dict[str, Any]] = []
    attempts = [item for item in state["outer_attempts"] if item.get("run_id") == row["run_id"]]
    for index, attempt in enumerate(attempts, start=1):
        if attempt["status"] == "PREPARED":
            raise EvaluationError("INVALID_ATTEMPT", "row contains an unfinished attempt")
        slot = load_slot(ledger_path, attempt["slot_id"])
        try:
            projection = slot_owner().released_slot_projection(slot)
        except Exception as exc:
            raise EvaluationError("INVALID_SLOT_EVIDENCE", str(exc)) from exc
        if projection["agent_id"] != attempt["runtime_agent_id"]:
            raise EvaluationError("INVALID_SLOT_EVIDENCE", "outer runtime identity changed")
        agents.append({
            "role": "DRAFT_PRODUCER" if row["execution_kind"] == "PARENT_ORCHESTRATED_V2" else row["role"].upper(),
            "round": 1, "verification_iteration": 1, "attempt": index,
            "status": attempt["status"], "runtime_agent_id": attempt["runtime_agent_id"],
            "input_sha256": attempt["input_envelope_sha256"],
            "output_sha256": attempt["output_sha256"], "slot_id": attempt["slot_id"],
        })
    if controller_state is not None:
        for attempt in controller_state["attempts"]:
            if attempt["status"] == "PREPARED":
                raise EvaluationError("INVALID_CONTROLLER_STATE", "controller contains an unfinished attempt")
            slot = load_slot(ledger_path, attempt["slot_id"])
            try:
                projection = slot_owner().released_slot_projection(slot)
            except Exception as exc:
                raise EvaluationError("INVALID_SLOT_EVIDENCE", str(exc)) from exc
            if projection["agent_id"] != attempt["runtime_agent_id"]:
                raise EvaluationError("INVALID_SLOT_EVIDENCE", "inner runtime identity changed")
            agents.append({
                "role": attempt["role"], "round": attempt["round"],
                "verification_iteration": attempt["verification_iteration"],
                "attempt": attempt["attempt_sequence"], "status": attempt["status"],
                "runtime_agent_id": attempt["runtime_agent_id"],
                "input_sha256": attempt["input_envelope_sha256"],
                "output_sha256": attempt["output_sha256"], "slot_id": attempt["slot_id"],
            })
    for agent in agents:
        require_fields(agent, AGENT_RUN_FIELDS, "agent run")
    payload = {"schema_version": SCHEMA_VERSION, "run_id": row["run_id"], "agents": agents}
    primary = next(
        (item["runtime_agent_id"] for item in attempts if item["status"] == "SUCCEEDED"),
        None,
    )
    return canonical_bytes(payload) + b"\n", ledger_bytes, primary


def candidate_record_material(
    root: Path, state: dict[str, Any], row: dict[str, Any], attempt: dict[str, Any] | None,
) -> tuple[dict[str, Any], bytes | None, Path | None, bytes, dict[str, Any], str, str]:
    live_path = root / controller_live_state_relative(row["controller_lineage_id"])
    try:
        controller_state, task_root, run_root = plan_owner().load_state(live_path)
    except Exception as exc:
        raise EvaluationError("INVALID_CONTROLLER_STATE", str(exc)) from exc
    terminal_bytes = live_path.read_bytes()
    started = row["started_at_utc"] or controller_state["started_at_utc"]
    if controller_state["status"] == "BLOCKED":
        if row["status"] != "BLOCKED_READY_TO_RECORD" or attempt is not None:
            raise EvaluationError("INVALID_ROW_STATE", "blocked candidate must be evaluator-derived")
        output = {
            "schema_version": SCHEMA_VERSION, "case_id": row["case_id"], "arm": "v2",
            "phase": row["phase"], "terminal_verdict": "BLOCKED", "plan_path": None,
            "plan_sha256": None, "evidence_status": "INSUFFICIENT",
            "clarification_questions": [], "unresolved_choices": [], "package_path": None,
            "package_tree_sha256": None, "blocker_code": "RESEARCH_REQUIRED",
        }
        validate_planner_output(output, row)
        return output, None, None, terminal_bytes, controller_state, started, started
    if controller_state["status"] != "EMITTED" or attempt is None:
        raise EvaluationError("INVALID_CONTROLLER_STATE", "candidate controller is not emitted")
    try:
        package = plan_owner().validate_package_root(task_root)
    except Exception as exc:
        raise EvaluationError("INVALID_PLAN_PACKAGE", str(exc)) from exc
    if not controller_state["revision_history"]:
        raise EvaluationError("INVALID_CONTROLLER_STATE", "emitted controller has no revision")
    receipt_path = run_root / controller_state["revision_history"][-1]["receipt_path"]
    receipt = load_json(receipt_path)
    plan_path = run_root / receipt["plan_snapshot_path"]
    plan_bytes = plan_path.read_bytes()
    if sha256_bytes(plan_bytes) != controller_state["plan_sha256"]:
        raise EvaluationError("PLAN_TAMPER", "controller plan snapshot changed")
    package_tree = tree_owner().TREE_SHA256_V1(task_root)
    output = {
        "schema_version": SCHEMA_VERSION, "case_id": row["case_id"], "arm": "v2",
        "phase": row["phase"], "terminal_verdict": "PASS",
        "plan_path": f"rows/{row['run_id']}/recorded/plan.md",
        "plan_sha256": controller_state["plan_sha256"], "evidence_status": "SUFFICIENT",
        "clarification_questions": [], "unresolved_choices": [],
        "package_path": f"rows/{row['run_id']}/recorded/package",
        "package_tree_sha256": package_tree, "blocker_code": None,
    }
    validate_planner_output(output, row)
    manifest = load_json(task_root / "manifest.json")
    ended = manifest.get("emitted_at_utc") or attempt["finalized_at_utc"]
    del package
    return output, plan_bytes, task_root, terminal_bytes, controller_state, started, ended


def install_record_artifacts(
    root: Path, row: dict[str, Any], files: dict[str, bytes], package_source: Path | None,
) -> None:
    for relative, payload in files.items():
        target = root / relative
        if target.exists() and target.read_bytes() != payload:
            raise EvaluationError("RECORD_REPLAY_CONFLICT", f"record artifact changed: {relative}")
        atomic_write_bytes(target, payload)
    if package_source is not None:
        target = root / f"rows/{row['run_id']}/recorded/package"
        expected = tree_owner().TREE_SHA256_V1(package_source)
        if target.exists():
            if tree_owner().TREE_SHA256_V1(target) != expected:
                raise EvaluationError("RECORD_REPLAY_CONFLICT", "recorded package changed")
        else:
            staging = target.with_name("package.staging")
            shutil.rmtree(staging, ignore_errors=True)
            shutil.copytree(package_source, staging, symlinks=False)
            if tree_owner().TREE_SHA256_V1(staging) != expected:
                raise EvaluationError("PACKAGE_COPY_FAILED", "recorded package copy changed")
            os.replace(staging, target)


def package_projection(root: Path, row: dict[str, Any], source: Path) -> Path:
    if not (source / ".plan-playbook-v2").exists():
        return source
    try:
        package = plan_owner().validate_package_root(source)
    except Exception as exc:
        raise EvaluationError("INVALID_PLAN_PACKAGE", str(exc)) from exc
    staging = root / f"rows/{row['run_id']}/record/staging/package"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    for relative in ["manifest.json"] + [item["path"] for item in package["owned_files"]]:
        source_file = source / relative
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target)
    try:
        plan_owner().validate_package_root(staging)
    except Exception as exc:
        raise EvaluationError("PACKAGE_COPY_FAILED", str(exc)) from exc
    return staging


def publish_record(
    root: Path, state_path: Path, state: dict[str, Any], row: dict[str, Any],
    logical_output: dict[str, Any], plan_bytes: bytes | None, package_source: Path | None,
    terminal_state_bytes: bytes | None, consulted_bytes: bytes, agent_runs_bytes: bytes,
    ledger_bytes: bytes, *, attempt_number: int, runtime_agent_id: str | None,
    started_at: str, ended_at: str, now: str | None = None,
) -> dict[str, Any]:
    if row["status"] == "RECORDED":
        reopen_row_artifact(root, row, "output_path", "output_sha256")
        reopen_row_artifact(root, row, "consulted_sources_path", "consulted_sources_sha256")
        reopen_row_artifact(root, row, "agent_runs_path", "agent_runs_sha256")
        reopen_row_artifact(root, row, "slot_ledger_path", "slot_ledger_sha256")
        return {
            "schema_version": SCHEMA_VERSION, "command": "record", "ok": True,
            "run_id": row["run_id"], "status": "RECORDED",
            "output_sha256": row["output_sha256"], "code": "ROW_RECORDED",
        }
    output_bytes = canonical_bytes(logical_output) + b"\n"
    row_root = f"rows/{row['run_id']}"
    files = {
        f"{row_root}/recorded/output.json": output_bytes,
        f"{row_root}/consulted-sources.json": consulted_bytes,
        f"{row_root}/agent-runs.json": agent_runs_bytes,
        f"{row_root}/slot-ledger.json": ledger_bytes,
    }
    plan_sha = None
    if plan_bytes is not None:
        files[f"{row_root}/recorded/plan.md"] = plan_bytes
        plan_sha = sha256_bytes(plan_bytes)
    terminal_sha = None
    terminal_relative = None
    if terminal_state_bytes is not None:
        terminal_sha = sha256_bytes(terminal_state_bytes)
        terminal_relative = f"{row_root}/recorded/controller-state/{terminal_sha}.json"
        files[terminal_relative] = terminal_state_bytes
    package_sha = tree_owner().TREE_SHA256_V1(package_source) if package_source is not None else None
    successor = json.loads(json.dumps(state))
    successor_row = matrix_row(successor, row["run_id"])
    successor_row.update(
        attempt=attempt_number, runtime_agent_id=runtime_agent_id,
        output_path=f"{row_root}/recorded/output.json", output_sha256=sha256_bytes(output_bytes),
        plan_snapshot_path=f"{row_root}/recorded/plan.md" if plan_bytes is not None else None,
        plan_snapshot_sha256=plan_sha,
        package_snapshot_path=f"{row_root}/recorded/package" if package_source is not None else None,
        package_snapshot_tree_sha256=package_sha,
        terminal_controller_state_path=terminal_relative,
        terminal_controller_state_sha256=terminal_sha,
        consulted_sources_path=f"{row_root}/consulted-sources.json",
        consulted_sources_sha256=sha256_bytes(consulted_bytes),
        agent_runs_path=f"{row_root}/agent-runs.json",
        agent_runs_sha256=sha256_bytes(agent_runs_bytes),
        slot_ledger_path=f"{row_root}/slot-ledger.json",
        slot_ledger_sha256=sha256_bytes(ledger_bytes),
        started_at_utc=started_at, ended_at_utc=ended_at, status="RECORDED",
    )
    successor_bytes = canonical_bytes(successor) + b"\n"
    predecessor_sha = state_sha256(state_path)
    basis = {
        "run_id": row["run_id"], "predecessor": predecessor_sha,
        "terminal": terminal_sha, "output": sha256_bytes(output_bytes), "plan": plan_sha,
        "package": package_sha, "consulted": sha256_bytes(consulted_bytes),
        "agents": sha256_bytes(agent_runs_bytes), "slots": sha256_bytes(ledger_bytes),
        "successor": sha256_bytes(successor_bytes),
    }
    transaction = {
        "schema_version": SCHEMA_VERSION,
        "transaction_id": "plan-v2-record-" + sha256_bytes(canonical_bytes(basis))[:24],
        "state": "PREPARED", "run_id": row["run_id"],
        "predecessor_prepared_run_sha256": predecessor_sha,
        "terminal_controller_state_sha256": terminal_sha,
        "output_sha256": basis["output"], "plan_sha256": plan_sha,
        "package_tree_sha256": package_sha,
        "consulted_sources_sha256": basis["consulted"],
        "agent_runs_sha256": basis["agents"], "slot_ledger_sha256": basis["slots"],
        "successor_prepared_run_sha256": basis["successor"],
        "created_at_utc": now or utc_now(),
    }
    transaction_path = root / f"{row_root}/record/transaction.json"
    if transaction_path.exists():
        existing = require_fields(load_json(transaction_path), RECORD_TRANSACTION_FIELDS, "record transaction")
        stable_fields = RECORD_TRANSACTION_FIELDS - {"state", "created_at_utc"}
        if any(existing[field] != transaction[field] for field in stable_fields):
            raise EvaluationError("RECORD_REPLAY_CONFLICT", "record transaction changed")
        transaction["created_at_utc"] = existing["created_at_utc"]
    atomic_write_json(transaction_path, transaction)
    install_record_artifacts(root, row, files, package_source)
    transaction["state"] = "ARTIFACTS_INSTALLED"
    atomic_write_json(transaction_path, transaction)
    atomic_write_bytes(state_path, successor_bytes)
    transaction["state"] = "MATRIX_PUBLISHED"
    atomic_write_json(transaction_path, transaction)
    return {
        "schema_version": SCHEMA_VERSION, "command": "record", "ok": True,
        "run_id": row["run_id"], "status": "RECORDED",
        "output_sha256": basis["output"], "code": "ROW_RECORDED",
    }


def record_row(
    run_dir: Path, run_id: str, consulted_sources: Path,
    successful_attempt_token: Path | None = None, slot_ledger: Path | None = None,
    *, now: str | None = None,
) -> dict[str, Any]:
    root, state_path, state = load_prepared_run(run_dir)
    row = matrix_row(state, require_string(run_id, "run_id"))
    if row["status"] == "RECORDED":
        return publish_record(
            root, state_path, state, row, load_recorded_output(root, row), None, None,
            None, b"", b"", b"", attempt_number=row["attempt"],
            runtime_agent_id=row["runtime_agent_id"], started_at=row["started_at_utc"],
            ended_at=row["ended_at_utc"], now=now,
        )
    if row["role"] == "implementer" and row["status"] != "PREPARED":
        raise EvaluationError("INVALID_ROW_STATE", "implementer record requires PREPARED")
    if row["role"] == "planner" and row["status"] not in {"PREPARED", "BLOCKED_READY_TO_RECORD"}:
        raise EvaluationError("INVALID_ROW_STATE", "planner record requires a recordable state")

    attempt = None
    if row["status"] == "BLOCKED_READY_TO_RECORD":
        if successful_attempt_token is not None or slot_ledger is not None:
            raise EvaluationError("INVALID_ROW_STATE", "blocked candidate forbids agent evidence")
    else:
        if successful_attempt_token is None or slot_ledger is None:
            raise EvaluationError("INVALID_ATTEMPT", "agent-backed record requires token and ledger")
        attempt = successful_outer_attempt(root, state, row, successful_attempt_token)

    plan_bytes: bytes | None = None
    package_source: Path | None = None
    terminal_bytes: bytes | None = None
    controller_state: dict[str, Any] | None = None
    if row["execution_kind"] == "PARENT_ORCHESTRATED_V2":
        (
            logical_output, plan_bytes, package_source, terminal_bytes,
            controller_state, started, ended,
        ) = candidate_record_material(root, state, row, attempt)
        if package_source is not None:
            package_source = package_projection(root, row, package_source)
            logical_output["package_tree_sha256"] = tree_owner().TREE_SHA256_V1(package_source)
            validate_planner_output(logical_output, row)
    else:
        if attempt is None:
            raise EvaluationError("INVALID_ATTEMPT", "single-agent row has no attempt")
        raw_path, raw_output = attempt_output_source(root, attempt)
        started, ended = attempt["prepared_at_utc"], attempt["finalized_at_utc"]
        if row["role"] == "planner":
            logical_output = validate_planner_output(raw_output, row)
            if logical_output["terminal_verdict"] == "PASS":
                plan_bytes = resolve_agent_plan(root, raw_path, logical_output)
        else:
            producer = matrix_row(state, row["consumes_run_id"])
            plan_sha = require_sha256(producer["plan_snapshot_sha256"], "producer plan sha256")
            logical_output = validate_implementer_output(raw_output, row, plan_sha)
            plan_bytes = reopen_row_artifact(
                root, producer, "plan_snapshot_path", "plan_snapshot_sha256",
            ).read_bytes()
            if producer["package_snapshot_path"] is not None:
                package_source = reopen_row_artifact(
                    root, producer, "package_snapshot_path", "package_snapshot_tree_sha256",
                    tree=True,
                )
    consulted_bytes = validate_consulted_sources(
        consulted_sources, row, logical_output,
        require_nonempty=row["role"] == "implementer" and logical_output.get("can_implement") is True,
    )
    agent_runs_bytes, ledger_bytes, primary = derive_agent_runs(
        root, state, row, slot_ledger, controller_state,
    )
    if attempt is not None and primary != attempt["runtime_agent_id"]:
        raise EvaluationError("INVALID_AGENT_RUNS", "primary runtime identity changed")
    return publish_record(
        root, state_path, state, row, logical_output, plan_bytes, package_source,
        terminal_bytes, consulted_bytes, agent_runs_bytes, ledger_bytes,
        attempt_number=len(row["outer_attempt_ids"]) if attempt is not None else 0,
        runtime_agent_id=primary, started_at=started, ended_at=ended, now=now,
    )


def record_no_plan(run_dir: Path, run_id: str, *, now: str | None = None) -> dict[str, Any]:
    root, state_path, state = load_prepared_run(run_dir)
    row = matrix_row(state, require_string(run_id, "run_id"))
    if not (
        row["arm"] == "legacy" and row["role"] == "implementer"
        and row["execution_kind"] in {"SINGLE_AGENT", "EVALUATOR_DERIVED_NO_PLAN"}
        and row["consumes_run_id"] is not None
    ):
        raise EvaluationError("INVALID_ROW_STATE", "record-no-plan requires a legacy implementer")
    if row["status"] == "RECORDED":
        output = load_recorded_output(root, row)
        validate_implementer_output(output, row, None)
        return {
            "schema_version": SCHEMA_VERSION, "command": "record-no-plan", "ok": True,
            "run_id": run_id, "status": "RECORDED", "output_sha256": row["output_sha256"],
            "code": "NO_PLAN_RECORDED",
        }
    if row["status"] != "WAITING_ON_DEPENDENCY" or row["outer_attempt_ids"] or row["input_envelope_path"] is not None:
        raise EvaluationError("INVALID_ROW_STATE", "legacy no-plan row has already started")
    producer = matrix_row(state, row["consumes_run_id"])
    producer_output = validate_planner_output(load_recorded_output(root, producer), producer)
    if (
        producer["arm"] != "legacy" or producer_output["terminal_verdict"] != "BLOCKED"
        or producer["plan_snapshot_path"] is not None or producer["package_snapshot_path"] is not None
    ):
        raise EvaluationError("INVALID_ROW_STATE", "no-plan producer is not a blocked legacy planner")
    output = {
        "schema_version": SCHEMA_VERSION, "case_id": row["case_id"], "arm": "legacy",
        "plan_hash": None, "can_implement": False,
        "non_implementation_reason": "NO_PLAN_FROM_BLOCKED_PLANNER",
        "clarification_questions": producer_output["clarification_questions"],
        "missing_implementation_anchors": [], "missing_verification_anchors": [],
        "unresolved_choices": producer_output["unresolved_choices"], "scope_inventions": [],
        "evidence_inventions": [], "implementation_actions": [], "verification_actions": [],
        "consulted_sources": [],
    }
    validate_implementer_output(output, row, None)
    consulted = canonical_bytes({
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "paths": [],
    }) + b"\n"
    agents = canonical_bytes({
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "agents": [],
    }) + b"\n"
    row["execution_kind"] = "EVALUATOR_DERIVED_NO_PLAN"
    result = publish_record(
        root, state_path, state, row, output, None, None, None, consulted, agents,
        ZERO_AGENT_LEDGER_BYTES, attempt_number=0, runtime_agent_id=None,
        started_at=producer["ended_at_utc"], ended_at=producer["ended_at_utc"], now=now,
    )
    result["command"] = "record-no-plan"
    result["code"] = "NO_PLAN_RECORDED"
    return result


def recorded_pair(state: dict[str, Any], case_id: str, arm: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    planners = [
        row for row in state["matrix"]
        if row["case_id"] == case_id and row["arm"] == arm and row["role"] == "planner"
    ]
    implementers = [
        row for row in state["matrix"]
        if row["case_id"] == case_id and row["arm"] == arm and row["role"] == "implementer"
    ]
    if len(implementers) != 1 or len(planners) not in {1, 2}:
        raise EvaluationError("INVALID_MATRIX", "case/arm pair cardinality changed")
    return planners, implementers[0]


def fixture_case_requirements(fixture: dict[str, Any], case: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = case["manifest"]["controller_inputs"]
    if inputs["direct_requirements"] is not None:
        return load_json(fixture["root"] / inputs["direct_requirements"]["path"])
    package_ref = case["manifest"]["research_resume_package"]
    if package_ref is None:
        raise EvaluationError("INVALID_FIXTURE", "case has no scoring requirements")
    package_root = fixture["root"] / package_ref["path"]
    try:
        package = plan_owner().research_owner().validate_package(package_root)
    except Exception as exc:
        raise EvaluationError("INVALID_RESEARCH_PACKAGE", str(exc)) from exc
    return package["requirements"]


def lifecycle_complete(root: Path, row: dict[str, Any]) -> bool:
    try:
        agents = require_fields(
            load_json(reopen_row_artifact(root, row, "agent_runs_path", "agent_runs_sha256")),
            AGENT_RUNS_FIELDS, "agent runs",
        )
        ledger_path = reopen_row_artifact(root, row, "slot_ledger_path", "slot_ledger_sha256")
        if row["execution_kind"] == "EVALUATOR_DERIVED_NO_PLAN" or (
            row["execution_kind"] == "PARENT_ORCHESTRATED_V2" and row["runtime_agent_id"] is None
        ):
            return (
                ledger_path.read_bytes() == ZERO_AGENT_LEDGER_BYTES
                and agents == {"schema_version": SCHEMA_VERSION, "run_id": row["run_id"], "agents": []}
                and not row["outer_attempt_ids"]
            )
        if not isinstance(agents["agents"], list) or not agents["agents"]:
            return False
        for item in agents["agents"]:
            require_fields(item, AGENT_RUN_FIELDS, "agent run")
            slot = load_slot(ledger_path, item["slot_id"])
            projection = slot_owner().released_slot_projection(slot)
            if projection["agent_id"] != item["runtime_agent_id"]:
                return False
        return True
    except Exception:
        return False


def boundary_trace(
    root: Path, planners: list[dict[str, Any]], implementer: dict[str, Any],
    authority_case: dict[str, Any], hidden: dict[str, Any], output: dict[str, Any],
    plan_bytes: bytes | None,
) -> dict[str, Any]:
    plan_text = plan_bytes.decode("utf-8") if plan_bytes is not None else ""
    lines = plan_text.splitlines()
    boundaries_by_id = {item["boundary_id"]: item for item in authority_case["negative_boundaries"]}
    forbidden = hidden["forbidden_scope_claims"] + hidden["forbidden_evidence_claims"]
    action_rows = output.get("implementation_actions", []) + output.get("verification_actions", [])
    action_text = {item["action_id"]: canonical_bytes(item).decode("ascii") for item in action_rows}
    rows = []
    for boundary_id in hidden["required_negative_boundary_ids"]:
        boundary = boundaries_by_id[boundary_id]
        anchors = [
            (index, line) for index, line in enumerate(lines, start=1)
            if boundary_id in line or boundary["statement"] in line
        ]
        contradictory = sorted({
            action_id for action_id, text in action_text.items()
            if any(item["claim"] in text for item in forbidden)
        })
        source_ids = sorted({
            derivation["source_evidence_id"]
            for derivation in authority_case["derivations"]
            if f"/negative_boundaries/" in derivation["authority_pointer"]
            and boundary_id in canonical_bytes(boundary).decode("ascii")
        })
        if not source_ids:
            source_ids = sorted({item for claim in forbidden for item in claim["evidence_ids"]})
        rows.append({
            "boundary_id": boundary_id, "source_evidence_ids": source_ids,
            "plan_anchor_paths": [f"plan.md:L{index}" for index, _line in anchors],
            "plan_anchor_sha256s": [sha256_bytes(line.encode("utf-8")) for _index, line in anchors],
            "contradictory_action_ids": contradictory,
            "preserved": bool(anchors) and not contradictory,
        })
    passing = next((row for row in planners if load_recorded_output(root, row)["terminal_verdict"] == "PASS"), None)
    return {
        "schema_version": SCHEMA_VERSION, "case_id": implementer["case_id"],
        "arm": implementer["arm"],
        "plan_sha256": passing["plan_snapshot_sha256"] if passing is not None else None,
        "implementer_output_sha256": implementer["output_sha256"], "boundaries": rows,
    }


def candidate_checks(root: Path, state: dict[str, Any]) -> dict[str, bool]:
    relative = require_string(state["candidate_check_evidence_path"], "candidate evidence path")
    path = root / relative
    evidence = require_fields(load_json(path), CANDIDATE_EVIDENCE_FIELDS, "candidate evidence")
    if sha256_bytes(path.read_bytes()) != state["candidate_check_evidence_sha256"]:
        raise EvaluationError("CANDIDATE_EVIDENCE_TAMPER", "candidate evidence changed")
    before = root / evidence["managed_before_path"]
    after = root / evidence["managed_after_path"]
    comparison = compare_managed(before, after, ["plan-playbook-v2"], ["_shared", "research-playbook"])
    ledger = root / evidence["slot_ledger_path"]
    derived: dict[str, bool] = {}
    for probe, field, expected_skill, expected_tree in (
        ("CANDIDATE_EXPLICIT", "candidate_explicit_routing", "plan-playbook-v2", state["candidate_tree_sha256"]),
        ("ORDINARY_LEGACY", "ordinary_legacy_routing", "plan-playbook", state["legacy_tree_sha256"]),
    ):
        attempts = [item for item in state["candidate_check_attempts"] if item.get("probe") == probe and item.get("status") == "SUCCEEDED"]
        if len(attempts) != 1:
            raise EvaluationError("INVALID_ROUTING_EVIDENCE", "routing success cardinality changed")
        token = root / f"candidate-checks/attempts/{attempts[0]['attempt_id']}/token.json"
        _attempt, output, _request = routing_attempt(root, state, token, probe, ledger)
        after_snapshot = validate_managed_snapshot(after)
        selected_tree = managed_tree(after_snapshot, output["selected_skill"])
        derived[field] = output["selected_skill"] == expected_skill and selected_tree == expected_tree
    derived["managed_projection_clean"] = comparison["passed"]
    if any(evidence[field] != value for field, value in derived.items()):
        raise EvaluationError("CANDIDATE_EVIDENCE_TAMPER", "candidate boolean changed")
    return derived


def case_score(
    root: Path, fixture: dict[str, Any], case: dict[str, Any], state: dict[str, Any], arm: str,
    *, write_traces: bool,
) -> dict[str, Any]:
    case_id = case["manifest"]["case_id"]
    planners, implementer = recorded_pair(state, case_id, arm)
    planner_outputs = [validate_planner_output(load_recorded_output(root, row), row) for row in planners]
    implementer_output = validate_implementer_output(
        load_recorded_output(root, implementer), implementer,
        implementer["plan_snapshot_sha256"],
    )
    passing = next((row for row, output in zip(planners, planner_outputs) if output["terminal_verdict"] == "PASS"), None)
    plan_bytes = (
        reopen_row_artifact(root, passing, "plan_snapshot_path", "plan_snapshot_sha256").read_bytes()
        if passing is not None else None
    )
    plan_text = plan_bytes.decode("utf-8") if plan_bytes is not None else ""
    hidden = case["hidden"]
    requirements = fixture_case_requirements(fixture, case)
    requirement_map = {item["id"]: item for item in requirements}
    implementation_ids = {item["obligation_id"] for item in implementer_output["implementation_actions"]}
    verification_ids = {item["obligation_id"] for item in implementer_output["verification_actions"]}
    critical_obligations = set(hidden["critical_obligation_ids"])
    implementation_numerator = sum(
        obligation in implementation_ids and obligation in plan_text for obligation in critical_obligations
    )
    verification_numerator = sum(
        obligation in verification_ids and obligation in plan_text for obligation in critical_obligations
    )
    requirement_numerator = 0
    for requirement_id in hidden["critical_requirement_ids"]:
        requirement = requirement_map.get(requirement_id)
        linked = (
            {item["id"] for item in requirement["planner_obligations"]} & critical_obligations
            if requirement is not None else set()
        )
        if (
            requirement_id in plan_text and linked
            and linked <= implementation_ids and linked <= verification_ids
        ):
            requirement_numerator += 1
    trace = boundary_trace(
        root, planners, implementer, case["authority"], hidden, implementer_output, plan_bytes,
    )
    trace_path = root / f"rows/{implementer['run_id']}/boundary-trace.json"
    trace_bytes = canonical_bytes(trace) + b"\n"
    if write_traces:
        atomic_write_bytes(trace_path, trace_bytes)
    elif trace_path.read_bytes() != trace_bytes:
        raise EvaluationError("BOUNDARY_TRACE_TAMPER", "boundary trace changed")
    transitions = [
        {
            "phase": output["phase"], "terminal_verdict": output["terminal_verdict"],
            "blocker_code": output.get("blocker_code"),
        }
        for output in planner_outputs
    ]
    transition_correct = transitions == hidden["expected_transitions"][arm]
    if len(planners) == 2:
        transition_correct = transition_correct and (
            planners[1]["resume_of_run_id"] == planners[0]["run_id"]
            and planners[1]["controller_lineage_id"] == planners[0]["controller_lineage_id"]
        )
    diagnostics = {
        "unresolved_choice_count": len(set(implementer_output["unresolved_choices"])),
        "clarification_question_count": len(set(implementer_output["clarification_questions"])),
        "scope_invention_count": len(set(implementer_output["scope_inventions"])),
        "evidence_invention_count": len(set(implementer_output["evidence_inventions"])),
    }
    hardening = True
    budget = True
    if arm == "v2" and passing is not None:
        package_path = reopen_row_artifact(
            root, passing, "package_snapshot_path", "package_snapshot_tree_sha256", tree=True,
        )
        package = plan_owner().validate_package_root(package_path)
        manifest = load_json(package_path / "manifest.json")
        hardening = manifest["plan_sha256"] == passing["plan_snapshot_sha256"]
        limits = (2, 10, 1200) if manifest["profile"] == "LIGHT" else (3, 43, 7200)
        budget = (
            manifest["budget_use"]["rounds_used"] <= limits[0]
            and manifest["budget_use"]["attempts_used"] <= limits[1]
            and manifest["budget_use"]["elapsed_seconds"] <= limits[2]
        )
        del package
    result = {
        "case_id": case_id, "arm": arm,
        "requirement_numerator": requirement_numerator,
        "requirement_denominator": len(hidden["critical_requirement_ids"]),
        "requirement_recall": requirement_numerator / len(hidden["critical_requirement_ids"]),
        "negative_boundary_numerator": sum(item["preserved"] for item in trace["boundaries"]),
        "negative_boundary_denominator": len(hidden["required_negative_boundary_ids"]),
        "negative_boundary_recall": sum(item["preserved"] for item in trace["boundaries"]) / len(hidden["required_negative_boundary_ids"]),
        "implementation_anchor_numerator": implementation_numerator,
        "implementation_anchor_denominator": len(critical_obligations),
        "implementation_anchor_coverage": implementation_numerator / len(critical_obligations),
        "verification_anchor_numerator": verification_numerator,
        "verification_anchor_denominator": len(critical_obligations),
        "verification_anchor_coverage": verification_numerator / len(critical_obligations),
        **diagnostics, "transition_correct": transition_correct,
        "hardening_hash_consistent": hardening, "profile_budget_compliant": budget,
        "lifecycle_complete": all(lifecycle_complete(root, row) for row in planners + [implementer]),
    }
    return require_fields(result, CASE_RESULT_FIELDS, "case result")


def aggregate_arm(case_results: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    rows = [row for row in case_results if row["arm"] == arm]
    if len(rows) != 3:
        raise EvaluationError("INVALID_SCORE", "arm must contain three case results")
    aggregate: dict[str, Any] = {}
    for prefix in ("requirement", "negative_boundary", "implementation_anchor", "verification_anchor"):
        numerator = sum(row[f"{prefix}_numerator"] for row in rows)
        denominator = sum(row[f"{prefix}_denominator"] for row in rows)
        aggregate[f"{prefix}_numerator"] = numerator
        aggregate[f"{prefix}_denominator"] = denominator
        ratio_field = "coverage" if prefix in {"implementation_anchor", "verification_anchor"} else "recall"
        aggregate[f"{prefix}_{ratio_field}"] = numerator / denominator
    for field in (
        "unresolved_choice_count", "clarification_question_count", "scope_invention_count",
        "evidence_invention_count",
    ):
        aggregate[field] = sum(row[field] for row in rows)
    for field in (
        "transition_correct", "hardening_hash_consistent", "profile_budget_compliant",
        "lifecycle_complete",
    ):
        aggregate[field] = all(row[field] for row in rows)
    return require_fields(aggregate, ARM_RESULT_FIELDS, "arm result")


def build_evidence_manifest(
    root: Path, state_path: Path, state: dict[str, Any], recorded_matrix_sha: str,
    scored_at: str,
) -> dict[str, Any]:
    rows = []
    for row in sorted(state["matrix"], key=lambda item: item["run_id"]):
        if row["status"] != "RECORDED":
            raise EvaluationError("INCOMPLETE_MATRIX", f"row is not recorded: {row['run_id']}")
        reopen_row_artifact(root, row, "slot_ledger_path", "slot_ledger_sha256")
        reopen_row_artifact(root, row, "agent_runs_path", "agent_runs_sha256")
        rows.append({
            "run_id": row["run_id"], "status": row["status"],
            "execution_kind": row["execution_kind"],
            "slot_ledger_path": row["slot_ledger_path"],
            "slot_ledger_sha256": row["slot_ledger_sha256"],
            "agent_runs_path": row["agent_runs_path"],
            "agent_runs_sha256": row["agent_runs_sha256"],
        })
    for item in rows:
        require_fields(item, EVIDENCE_ROW_FIELDS, "evidence row")
    authority = root / state["fixture_authority_path"]
    review = root / state["authority_review_path"]
    if sha256_bytes(authority.read_bytes()) != state["fixture_authority_sha256"]:
        raise EvaluationError("AUTHORITY_TAMPER", "run-owned fixture authority changed")
    if sha256_bytes(review.read_bytes()) != state["authority_review_sha256"]:
        raise EvaluationError("AUTHORITY_TAMPER", "run-owned authority review changed")
    manifest = {
        "schema_version": SCHEMA_VERSION, "fixture_root": state["fixture_root"],
        "fixture_tree_sha256": state["fixture_tree_sha256"],
        "fixture_authority_path": state["fixture_authority_path"],
        "fixture_authority_sha256": state["fixture_authority_sha256"],
        "authority_review_path": state["authority_review_path"],
        "authority_review_sha256": state["authority_review_sha256"],
        "prepared_run_path": "prepared-run.json",
        "prepared_run_sha256": state_sha256(state_path),
        "recorded_matrix_path": "recorded-matrix.json",
        "recorded_matrix_sha256": recorded_matrix_sha,
        "candidate_check_evidence_path": state["candidate_check_evidence_path"],
        "candidate_check_evidence_sha256": state["candidate_check_evidence_sha256"],
        "rows": rows, "scored_at_utc": scored_at,
    }
    return require_fields(manifest, EVIDENCE_MANIFEST_FIELDS, "evaluation evidence")


def score_passed(arm: dict[str, Any], checks: dict[str, bool]) -> bool:
    return (
        arm["requirement_recall"] >= THRESHOLDS["requirement_recall_min"]
        and arm["negative_boundary_recall"] >= THRESHOLDS["negative_boundary_recall_min"]
        and arm["implementation_anchor_coverage"] >= THRESHOLDS["implementation_anchor_coverage_min"]
        and arm["verification_anchor_coverage"] >= THRESHOLDS["verification_anchor_coverage_min"]
        and arm["unresolved_choice_count"] <= THRESHOLDS["unresolved_choice_count_max"]
        and arm["clarification_question_count"] <= THRESHOLDS["clarification_question_count_max"]
        and arm["scope_invention_count"] <= THRESHOLDS["scope_invention_count_max"]
        and arm["evidence_invention_count"] <= THRESHOLDS["evidence_invention_count_max"]
        and arm["transition_correct"] is THRESHOLDS["transition_correct_required"]
        and arm["hardening_hash_consistent"] is THRESHOLDS["hardening_hash_consistent_required"]
        and arm["profile_budget_compliant"] is THRESHOLDS["profile_budget_compliant_required"]
        and arm["lifecycle_complete"] is THRESHOLDS["lifecycle_complete_required"]
        and checks["candidate_explicit_routing"] is THRESHOLDS["candidate_explicit_routing_required"]
        and checks["ordinary_legacy_routing"] is THRESHOLDS["ordinary_legacy_routing_required"]
        and checks["managed_projection_clean"] is THRESHOLDS["managed_projection_clean_required"]
    )


def derive_score(
    root: Path, fixture_root: Path, scored_at: str, *, write_artifacts: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root, state_path, state = load_prepared_run(root)
    fixture = validate_fixture_manifest(fixture_root)
    if fixture["root"] != Path(state["fixture_root"]).resolve(strict=True):
        raise EvaluationError("FIXTURE_DRIFT", "score fixture root changed")
    if tree_owner().TREE_SHA256_V1(fixture["root"]) != state["fixture_tree_sha256"]:
        raise EvaluationError("FIXTURE_DRIFT", "score fixture tree changed")
    matrix_bytes = canonical_bytes(state["matrix"]) + b"\n"
    matrix_path = root / "recorded-matrix.json"
    if write_artifacts:
        atomic_write_bytes(matrix_path, matrix_bytes)
    elif matrix_path.read_bytes() != matrix_bytes:
        raise EvaluationError("RECORDED_MATRIX_TAMPER", "recorded matrix changed")
    matrix_sha = sha256_bytes(matrix_bytes)
    results = [
        case_score(root, fixture, case, state, arm, write_traces=write_artifacts)
        for case in fixture["cases"] for arm in ("legacy", "v2")
    ]
    arms = {arm: aggregate_arm(results, arm) for arm in ("legacy", "v2")}
    checks = candidate_checks(root, state)
    evidence = build_evidence_manifest(root, state_path, state, matrix_sha, scored_at)
    evidence_path = root / "evaluation-evidence.json"
    evidence_bytes = canonical_bytes(evidence) + b"\n"
    if write_artifacts:
        atomic_write_bytes(evidence_path, evidence_bytes)
    elif evidence_path.read_bytes() != evidence_bytes:
        raise EvaluationError("EVALUATION_EVIDENCE_TAMPER", "evaluation evidence changed")
    score = {
        "schema_version": SCHEMA_VERSION,
        "prepared_run_sha256": state_sha256(state_path),
        "fixture_manifest_sha256": state["fixture_manifest_sha256"],
        "fixture_authority_sha256": state["fixture_authority_sha256"],
        "authority_review_sha256": state["authority_review_sha256"],
        "recorded_matrix_sha256": matrix_sha,
        "evaluation_evidence_path": "evaluation-evidence.json",
        "evaluation_evidence_sha256": sha256_bytes(evidence_bytes),
        "case_results": results, "arm_results": arms, "candidate_checks": checks,
        "thresholds": THRESHOLDS, "all_passed": score_passed(arms["v2"], checks),
        "scored_at_utc": scored_at,
    }
    return require_fields(score, SCORE_FIELDS, "score"), evidence


def score_run(
    run_dir: Path, fixtures: Path, out: Path, *, now: str | None = None,
) -> dict[str, Any]:
    root = strict_root(run_dir)
    if out.absolute() != root / "score.json":
        raise EvaluationError("INVALID_PATH", "score output must equal <run_root>/score.json")
    scored_at = now or utc_now()
    score, _evidence = derive_score(root, fixtures, scored_at, write_artifacts=True)
    atomic_write_json(out, score)
    if load_json(out) != score:
        raise EvaluationError("SCORE_WRITE_FAILED", "score reopen changed")
    return score


def validate_score(score_path: Path) -> dict[str, Any]:
    resolved = score_path.resolve(strict=True)
    if resolved.name != "score.json" or resolved.is_symlink():
        raise EvaluationError("INVALID_PATH", "validate-score requires <run_root>/score.json")
    stored = require_fields(load_json(resolved), SCORE_FIELDS, "score")
    evidence = require_fields(
        load_json(resolved.parent / "evaluation-evidence.json"),
        EVIDENCE_MANIFEST_FIELDS, "evaluation evidence",
    )
    if stored["scored_at_utc"] != evidence["scored_at_utc"]:
        raise EvaluationError("SCORE_TAMPER", "score timestamp changed")
    fixture_root = Path(require_string(evidence["fixture_root"], "fixture root"))
    derived, _manifest = derive_score(
        resolved.parent, fixture_root, stored["scored_at_utc"], write_artifacts=False,
    )
    expected_bytes = canonical_bytes(derived) + b"\n"
    if resolved.read_bytes() != expected_bytes:
        raise EvaluationError("SCORE_TAMPER", "stored score differs from derived score")
    return {
        "schema_version": SCHEMA_VERSION, "valid": True,
        "score_sha256": sha256_bytes(expected_bytes),
        "evaluation_evidence_sha256": stored["evaluation_evidence_sha256"],
        "fixture_authority_sha256": stored["fixture_authority_sha256"],
        "authority_review_sha256": stored["authority_review_sha256"],
        "fixture_tree_sha256": evidence["fixture_tree_sha256"],
    }


def next_attempt_sequence(state: dict[str, Any]) -> int:
    sequences: list[int] = []
    for field in ("outer_attempts", "candidate_check_attempts"):
        for attempt in state[field]:
            value = attempt.get("attempt_sequence") if isinstance(attempt, dict) else None
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise EvaluationError("INVALID_RUN", "attempt sequence is invalid")
            sequences.append(value)
    if len(sequences) != len(set(sequences)):
        raise EvaluationError("INVALID_RUN", "attempt sequence must be globally unique")
    return max(sequences, default=0) + 1


def known_runtime_ids(root: Path, state: dict[str, Any]) -> set[str]:
    fixture_root = Path(require_string(state.get("fixture_root"), "fixture_root"))
    receipt = validate_fixture_authority_review_receipt(
        fixture_root, fixture_root / "fixture-authority.json",
        fixture_root / "fixture-authority-review.json",
    )
    if (
        receipt["authority_sha256"] != state.get("fixture_authority_sha256")
        or sha256_bytes((fixture_root / "fixture-authority-review.json").read_bytes())
        != state.get("authority_review_sha256")
    ):
        raise EvaluationError("INVALID_RUN", "prepared authority identity changed")
    values = {receipt["reviewer_runtime_agent_id"]}
    for field in ("outer_attempts", "candidate_check_attempts"):
        for attempt in state[field]:
            runtime_id = attempt.get("runtime_agent_id")
            if runtime_id is not None:
                if not isinstance(runtime_id, str) or not runtime_id or runtime_id in values:
                    raise EvaluationError("DUPLICATE_RUNTIME_ID", "runtime agent IDs must be globally unique")
                values.add(runtime_id)
    return values


def released_projection(slot_ledger: Path, slot_id: str) -> tuple[dict[str, Any], str]:
    slot = load_slot(slot_ledger.resolve(strict=True), slot_id)
    owner = slot_owner()
    try:
        projection = owner.released_slot_projection(slot)
        close_sha = owner.released_slot_close_evidence_sha256(slot)
    except ValueError as exc:
        raise EvaluationError("INVALID_SLOT_STATE", str(exc)) from exc
    return projection, close_sha


def validate_attempt_terminal(
    status: str, runtime_agent_id: str | None, output_path: Path | None,
    projection: dict[str, Any],
) -> None:
    if status not in ATTEMPT_TERMINAL_STATUSES or projection.get("state") != "released":
        raise EvaluationError("INVALID_ATTEMPT_STATUS", "invalid terminal attempt status")
    if projection.get("agent_id") != runtime_agent_id:
        raise EvaluationError("INVALID_RUNTIME_ID", "runtime ID differs from released slot")
    if status == "SPAWN_FAILED":
        valid = (
            runtime_agent_id is None and output_path is None
            and projection.get("bound_at") is None
            and projection.get("abandoned_at") is not None
        )
    elif status == "BIND_FAILED":
        valid = (
            runtime_agent_id is not None and output_path is None
            and projection.get("bound_at") is None
            and projection.get("abandoned_at") is not None
            and projection.get("evidence", {}).get("close")
        )
    elif status in {"RUNTIME_FAILED", "TIMED_OUT"}:
        valid = (
            runtime_agent_id is not None and output_path is None
            and projection.get("bound_at") is not None
            and projection.get("closed_at") is not None
        )
    else:
        valid = (
            runtime_agent_id is not None and output_path is not None
            and projection.get("bound_at") is not None
            and projection.get("completed_at") is not None
            and projection.get("closed_at") is not None
        )
    if not valid:
        raise EvaluationError("INVALID_ATTEMPT_STATUS", f"slot evidence does not support {status}")


def validate_attempt_token(root: Path, token_path: Path) -> dict[str, Any]:
    relative = run_owned_relative(root, token_path, "attempt token", must_exist=True)
    if not relative.endswith("/token.json"):
        raise EvaluationError("INVALID_PATH", "attempt token must use its fixed attempt path")
    token = require_fields(load_json(token_path), ATTEMPT_TOKEN_FIELDS, "attempt token")
    if token["schema_version"] != SCHEMA_VERSION or token["status"] != "PREPARED":
        raise EvaluationError("INVALID_ATTEMPT_TOKEN", "attempt token state is invalid")
    require_sha256(token["input_sha256"], "attempt token input_sha256")
    require_sha256(token["prepared_run_sha256"], "attempt token prepared_run_sha256")
    if token["kind"] not in {"OUTER", "ROUTING"}:
        raise EvaluationError("INVALID_ATTEMPT_TOKEN", "unknown attempt token kind")
    return token


def prepare_attempt(
    run_dir: Path, run_id: str, slot_id: str, slot_ledger: Path, input_path: Path,
    out: Path, *, now: str | None = None,
) -> dict[str, Any]:
    root, state_path, state = load_prepared_run(run_dir)
    row = matrix_row(state, require_string(run_id, "run_id"))
    if row.get("status") != "PREPARED":
        raise EvaluationError("INVALID_ROW_STATE", "attempt requires a PREPARED row")
    fixed_input = root / require_string(row.get("input_envelope_path"), "row input path")
    supplied_input = input_path.resolve(strict=True)
    if supplied_input != fixed_input.resolve(strict=True):
        raise EvaluationError("INVALID_PATH", "attempt input differs from prepared row input")
    input_bytes = fixed_input.read_bytes()
    input_sha = sha256_bytes(input_bytes)
    if row.get("input_envelope_sha256") != input_sha:
        raise EvaluationError("INPUT_TAMPER", "prepared row input hash changed")
    slot = load_slot(slot_ledger.resolve(strict=True), require_string(slot_id, "slot_id"))
    if slot.get("state") != "reserved" or slot.get("agent_id") is not None:
        raise EvaluationError("INVALID_SLOT_STATE", "attempt slot must be reserved and unbound")
    prior = [attempt for attempt in state["outer_attempts"] if attempt.get("run_id") == run_id]
    if any(attempt.get("status") in {"PREPARED", "SUCCEEDED"} for attempt in prior) or len(prior) >= 2:
        raise EvaluationError("ATTEMPT_LIMIT", "row does not permit another attempt")
    sequence = next_attempt_sequence(state)
    attempt_id = "plan-v2-attempt-" + sha256_bytes(canonical_bytes({
        "run_id": run_id, "sequence": sequence, "input_sha256": input_sha,
        "slot_id": slot_id,
    }))[:24]
    attempt_root = root / f"rows/{run_id}/attempts/{attempt_id}"
    expected_out = attempt_root / "token.json"
    if out.absolute() != expected_out:
        raise EvaluationError("INVALID_PATH", "attempt token output must use its fixed path")
    input_relative = f"rows/{run_id}/attempts/{attempt_id}/input.json"
    prepared_at = now or utc_now()
    predecessor_sha = state_sha256(state_path)
    token = {
        "schema_version": SCHEMA_VERSION, "attempt_id": attempt_id,
        "attempt_sequence": sequence, "kind": "OUTER", "subject_id": run_id,
        "input_path": input_relative, "input_sha256": input_sha, "slot_id": slot_id,
        "prepared_run_sha256": predecessor_sha, "prepared_at_utc": prepared_at,
        "status": "PREPARED",
    }
    attempt = {
        "attempt_id": attempt_id, "attempt_sequence": sequence, "run_id": run_id,
        "role": row["role"], "input_envelope_path": input_relative,
        "input_envelope_sha256": input_sha, "slot_id": slot_id, "status": "PREPARED",
        "runtime_agent_id": None, "output_path": None, "output_sha256": None,
        "prepared_at_utc": prepared_at, "finalized_at_utc": None,
    }
    if expected_out.exists():
        existing = validate_attempt_token(root, expected_out)
        matching = [item for item in state["outer_attempts"] if item.get("attempt_id") == attempt_id]
        if existing != token or matching != [attempt] or attempt_id not in row.get("outer_attempt_ids", []):
            raise EvaluationError("ATTEMPT_REPLAY_CONFLICT", "prepared attempt replay changed")
        return existing
    attempt_root.mkdir(parents=True, exist_ok=False)
    atomic_write_bytes(attempt_root / "input.json", input_bytes)
    atomic_write_json(expected_out, token)
    state["outer_attempts"].append(attempt)
    row.setdefault("outer_attempt_ids", []).append(attempt_id)
    atomic_write_json(state_path, state)
    return token


def finalize_attempt(
    run_dir: Path, attempt_token: Path, slot_ledger: Path, status: str,
    runtime_agent_id: str | None = None, output_path: Path | None = None,
    *, now: str | None = None,
) -> dict[str, Any]:
    root, state_path, state = load_prepared_run(run_dir)
    token = validate_attempt_token(root, attempt_token.resolve(strict=True))
    if token["kind"] != "OUTER":
        raise EvaluationError("INVALID_ATTEMPT_TOKEN", "outer finalization requires an outer token")
    matches = [item for item in state["outer_attempts"] if item.get("attempt_id") == token["attempt_id"]]
    if len(matches) != 1:
        raise EvaluationError("INVALID_RUN", "attempt is not registered exactly once")
    attempt = matches[0]
    projection, _close_sha = released_projection(slot_ledger, token["slot_id"])
    validate_attempt_terminal(status, runtime_agent_id, output_path, projection)
    if runtime_agent_id is not None and runtime_agent_id in known_runtime_ids(root, state) - {attempt.get("runtime_agent_id")}:
        raise EvaluationError("DUPLICATE_RUNTIME_ID", "runtime agent ID was already used")
    raw_bytes = output_path.resolve(strict=True).read_bytes() if output_path is not None else None
    output_relative = None
    output_sha = None
    if raw_bytes is not None:
        output_relative = f"rows/{token['subject_id']}/attempts/{token['attempt_id']}/output.json"
        output_sha = sha256_bytes(raw_bytes)
    final = {
        **attempt, "status": status, "runtime_agent_id": runtime_agent_id,
        "output_path": output_relative, "output_sha256": output_sha,
        "finalized_at_utc": now or utc_now(),
    }
    if attempt["status"] != "PREPARED":
        stable = {key: final[key] for key in final if key != "finalized_at_utc"}
        existing = {key: attempt[key] for key in attempt if key != "finalized_at_utc"}
        if existing != stable:
            raise EvaluationError("ATTEMPT_REPLAY_CONFLICT", "finalized attempt changed")
        return attempt
    if raw_bytes is not None:
        atomic_write_bytes(root / output_relative, raw_bytes)
    attempt.clear(); attempt.update(final)
    atomic_write_json(state_path, state)
    return final


def prepare_routing_probe(
    run_dir: Path, probe: str, slot_id: str, slot_ledger: Path, out: Path,
    *, now: str | None = None,
) -> dict[str, Any]:
    root, state_path, state = load_prepared_run(run_dir)
    if probe not in CANDIDATE_PROBES:
        raise EvaluationError("INVALID_PROBE", "unknown routing probe")
    key = "explicit" if probe == "CANDIDATE_EXPLICIT" else "ordinary"
    requests = require_fields(
        state.get("candidate_check_requests"),
        {"explicit_path", "explicit_sha256", "ordinary_path", "ordinary_sha256"},
        "candidate check requests",
    )
    source = root / requests[f"{key}_path"]
    input_bytes = source.resolve(strict=True).read_bytes()
    input_sha = sha256_bytes(input_bytes)
    if input_sha != requests[f"{key}_sha256"]:
        raise EvaluationError("INPUT_TAMPER", "routing request hash changed")
    slot = load_slot(slot_ledger.resolve(strict=True), require_string(slot_id, "slot_id"))
    if slot.get("state") != "reserved" or slot.get("agent_id") is not None:
        raise EvaluationError("INVALID_SLOT_STATE", "routing slot must be reserved and unbound")
    prior = [attempt for attempt in state["candidate_check_attempts"] if attempt.get("probe") == probe]
    if any(attempt.get("status") in {"PREPARED", "SUCCEEDED"} for attempt in prior) or len(prior) >= 2:
        raise EvaluationError("ATTEMPT_LIMIT", "probe does not permit another attempt")
    sequence = next_attempt_sequence(state)
    attempt_id = "plan-v2-routing-" + sha256_bytes(canonical_bytes({
        "probe": probe, "sequence": sequence, "input_sha256": input_sha,
        "slot_id": slot_id,
    }))[:24]
    attempt_root = root / f"candidate-checks/attempts/{attempt_id}"
    expected_out = attempt_root / "token.json"
    if out.absolute() != expected_out:
        raise EvaluationError("INVALID_PATH", "routing token output must use its fixed path")
    input_relative = f"candidate-checks/attempts/{attempt_id}/input.json"
    prepared_at = now or utc_now()
    token = {
        "schema_version": SCHEMA_VERSION, "attempt_id": attempt_id,
        "attempt_sequence": sequence, "kind": "ROUTING", "subject_id": probe,
        "input_path": input_relative, "input_sha256": input_sha, "slot_id": slot_id,
        "prepared_run_sha256": state_sha256(state_path),
        "prepared_at_utc": prepared_at, "status": "PREPARED",
    }
    attempt = {
        "attempt_id": attempt_id, "attempt_sequence": sequence, "probe": probe,
        "input_path": input_relative, "input_sha256": input_sha, "slot_id": slot_id,
        "status": "PREPARED", "runtime_agent_id": None, "output_path": None,
        "output_sha256": None, "released_slot_path": None,
        "released_slot_sha256": None, "prepared_at_utc": prepared_at,
        "finalized_at_utc": None,
    }
    attempt_root.mkdir(parents=True, exist_ok=False)
    atomic_write_bytes(attempt_root / "input.json", input_bytes)
    atomic_write_json(expected_out, token)
    state["candidate_check_attempts"].append(attempt)
    atomic_write_json(state_path, state)
    return token


def finalize_routing_probe(
    run_dir: Path, attempt_token: Path, slot_ledger: Path, status: str,
    runtime_agent_id: str | None = None, output_path: Path | None = None,
    *, now: str | None = None,
) -> dict[str, Any]:
    root, state_path, state = load_prepared_run(run_dir)
    token = validate_attempt_token(root, attempt_token.resolve(strict=True))
    if token["kind"] != "ROUTING":
        raise EvaluationError("INVALID_ATTEMPT_TOKEN", "routing finalization requires a routing token")
    matches = [item for item in state["candidate_check_attempts"] if item.get("attempt_id") == token["attempt_id"]]
    if len(matches) != 1:
        raise EvaluationError("INVALID_RUN", "routing attempt is not registered exactly once")
    attempt = matches[0]
    projection, _close_sha = released_projection(slot_ledger, token["slot_id"])
    validate_attempt_terminal(status, runtime_agent_id, output_path, projection)
    if runtime_agent_id is not None and runtime_agent_id in known_runtime_ids(root, state) - {attempt.get("runtime_agent_id")}:
        raise EvaluationError("DUPLICATE_RUNTIME_ID", "runtime agent ID was already used")
    raw_bytes = output_path.resolve(strict=True).read_bytes() if output_path is not None else None
    output_relative = released_relative = None
    output_sha = None
    if raw_bytes is not None:
        output_relative = f"candidate-checks/attempts/{token['attempt_id']}/output.json"
        output_sha = sha256_bytes(raw_bytes)
    released_relative = f"candidate-checks/attempts/{token['attempt_id']}/released-slot.json"
    released_bytes = canonical_bytes(projection) + b"\n"
    final = {
        **attempt, "status": status, "runtime_agent_id": runtime_agent_id,
        "output_path": output_relative, "output_sha256": output_sha,
        "released_slot_path": released_relative,
        "released_slot_sha256": sha256_bytes(released_bytes),
        "finalized_at_utc": now or utc_now(),
    }
    if attempt["status"] != "PREPARED":
        stable = {key: final[key] for key in final if key != "finalized_at_utc"}
        existing = {key: attempt[key] for key in attempt if key != "finalized_at_utc"}
        if existing != stable:
            raise EvaluationError("ATTEMPT_REPLAY_CONFLICT", "finalized routing attempt changed")
        return attempt
    if raw_bytes is not None:
        atomic_write_bytes(root / output_relative, raw_bytes)
    atomic_write_bytes(root / released_relative, released_bytes)
    attempt.clear(); attempt.update(final)
    atomic_write_json(state_path, state)
    return final


def routing_attempt(
    root: Path, state: dict[str, Any], token_path: Path, expected_probe: str,
    slot_ledger: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    token = validate_attempt_token(root, token_path.resolve(strict=True))
    if token["kind"] != "ROUTING" or token["subject_id"] != expected_probe:
        raise EvaluationError("INVALID_ROUTING_EVIDENCE", "routing token names the wrong probe")
    matches = [
        item for item in state["candidate_check_attempts"]
        if item.get("attempt_id") == token["attempt_id"]
    ]
    if len(matches) != 1:
        raise EvaluationError("INVALID_ROUTING_EVIDENCE", "routing attempt is not unique")
    attempt = require_fields(matches[0], CANDIDATE_ATTEMPT_FIELDS, "routing attempt")
    if attempt["probe"] != expected_probe or attempt["status"] != "SUCCEEDED":
        raise EvaluationError("INVALID_ROUTING_EVIDENCE", "routing attempt did not succeed")
    if (
        attempt["input_sha256"] != token["input_sha256"]
        or attempt["slot_id"] != token["slot_id"]
        or attempt["runtime_agent_id"] is None
        or attempt["output_path"] is None
        or attempt["released_slot_path"] is None
    ):
        raise EvaluationError("INVALID_ROUTING_EVIDENCE", "routing attempt identity changed")
    output_path = root / attempt["output_path"]
    output = require_fields(load_json(output_path), ROUTING_OUTPUT_FIELDS, "routing output")
    if (
        output["schema_version"] != SCHEMA_VERSION
        or output["input_sha256"] != token["input_sha256"]
        or sha256_bytes(output_path.read_bytes()) != attempt["output_sha256"]
    ):
        raise EvaluationError("INVALID_ROUTING_EVIDENCE", "routing output identity changed")
    request_key = "explicit" if expected_probe == "CANDIDATE_EXPLICIT" else "ordinary"
    request_ref = state["candidate_check_requests"]
    request_path = root / request_ref[f"{request_key}_path"]
    request = load_json(request_path)
    if (
        sha256_bytes(request_path.read_bytes()) != request_ref[f"{request_key}_sha256"]
        or output["invocation"] != request["invocation"]
    ):
        raise EvaluationError("INVALID_ROUTING_EVIDENCE", "routing request binding changed")
    projection, _close_sha = released_projection(slot_ledger, attempt["slot_id"])
    released_path = root / attempt["released_slot_path"]
    if (
        projection["agent_id"] != attempt["runtime_agent_id"]
        or canonical_bytes(projection) + b"\n" != released_path.read_bytes()
        or sha256_bytes(released_path.read_bytes()) != attempt["released_slot_sha256"]
    ):
        raise EvaluationError("INVALID_ROUTING_EVIDENCE", "routing slot evidence changed")
    return attempt, output, request


def managed_tree(snapshot: dict[str, Any], name: str) -> str:
    matches = [item for item in snapshot["skills"] if item["name"] == name]
    if len(matches) != 1 or matches[0]["installed_state"] != "PRESENT":
        raise EvaluationError("INVALID_ROUTING_EVIDENCE", f"managed skill is not present: {name}")
    return require_sha256(matches[0]["tree_sha256"], f"managed tree {name}")


def record_candidate_checks(
    run_dir: Path, explicit_token: Path, ordinary_token: Path, slot_ledger: Path,
    managed_before: Path, managed_after: Path, *, now: str | None = None,
) -> dict[str, Any]:
    root, state_path, state = load_prepared_run(run_dir)
    evidence_path = root / "candidate-checks/evidence.json"
    fixed_paths = {
        "explicit_routing_path": "candidate-checks/explicit-routing.json",
        "ordinary_routing_path": "candidate-checks/ordinary-routing.json",
        "slot_ledger_path": "candidate-checks/slot-ledger.json",
        "managed_before_path": "candidate-checks/managed-before.json",
        "managed_after_path": "candidate-checks/managed-after.json",
    }
    if state["candidate_check_evidence_path"] is not None:
        if state["candidate_check_evidence_path"] != "candidate-checks/evidence.json":
            raise EvaluationError("CANDIDATE_CHECK_REPLAY_CONFLICT", "candidate evidence path changed")
        evidence = require_fields(load_json(evidence_path), CANDIDATE_EVIDENCE_FIELDS, "candidate evidence")
        if sha256_bytes(evidence_path.read_bytes()) != state["candidate_check_evidence_sha256"]:
            raise EvaluationError("CANDIDATE_CHECK_REPLAY_CONFLICT", "candidate evidence changed")
        replay_inputs = {
            "slot_ledger_path": slot_ledger, "managed_before_path": managed_before,
            "managed_after_path": managed_after,
        }
        for field, supplied in replay_inputs.items():
            if supplied.resolve(strict=True).read_bytes() != (root / fixed_paths[field]).read_bytes():
                raise EvaluationError("CANDIDATE_CHECK_REPLAY_CONFLICT", f"{field} changed")
        return evidence

    explicit_attempt, explicit_output, explicit_request = routing_attempt(
        root, state, explicit_token, "CANDIDATE_EXPLICIT", slot_ledger,
    )
    ordinary_attempt, ordinary_output, ordinary_request = routing_attempt(
        root, state, ordinary_token, "ORDINARY_LEGACY", slot_ledger,
    )
    if explicit_attempt["slot_id"] == ordinary_attempt["slot_id"]:
        raise EvaluationError("DUPLICATE_SLOT_ID", "routing probes must use different slots")
    before = validate_managed_snapshot(managed_before.resolve(strict=True))
    after = validate_managed_snapshot(managed_after.resolve(strict=True))
    comparison = compare_managed(
        managed_before, managed_after, ["plan-playbook-v2"],
        ["_shared", "research-playbook"],
    )
    recorded_at = now or utc_now()

    def derive(
        probe: str, attempt: dict[str, Any], output: dict[str, Any],
        request: dict[str, Any], expected_skill: str, expected_tree: str,
    ) -> dict[str, Any]:
        selected_skill = require_string(output["selected_skill"], "selected_skill")
        selected_tree = managed_tree(after, selected_skill)
        result = {
            "schema_version": SCHEMA_VERSION, "probe": probe,
            "attempt_id": attempt["attempt_id"],
            "runtime_agent_id": attempt["runtime_agent_id"], "slot_id": attempt["slot_id"],
            "request_sha256": attempt["input_sha256"],
            "output_path": attempt["output_path"], "output_sha256": attempt["output_sha256"],
            "released_slot_path": attempt["released_slot_path"],
            "released_slot_sha256": attempt["released_slot_sha256"],
            "invocation": request["invocation"], "selected_skill": selected_skill,
            "selected_tree_sha256": selected_tree, "expected_skill": expected_skill,
            "passed": selected_skill == expected_skill and selected_tree == expected_tree,
            "recorded_at_utc": recorded_at,
        }
        if set(result) != ROUTING_RESULT_FIELDS:
            raise EvaluationError("INVALID_ROUTING_EVIDENCE", "routing result fields changed")
        return result

    explicit = derive(
        "CANDIDATE_EXPLICIT", explicit_attempt, explicit_output, explicit_request,
        "plan-playbook-v2", state["candidate_tree_sha256"],
    )
    ordinary = derive(
        "ORDINARY_LEGACY", ordinary_attempt, ordinary_output, ordinary_request,
        "plan-playbook", state["legacy_tree_sha256"],
    )
    payloads = {
        fixed_paths["explicit_routing_path"]: canonical_bytes(explicit) + b"\n",
        fixed_paths["ordinary_routing_path"]: canonical_bytes(ordinary) + b"\n",
        fixed_paths["slot_ledger_path"]: slot_ledger.resolve(strict=True).read_bytes(),
        fixed_paths["managed_before_path"]: managed_before.resolve(strict=True).read_bytes(),
        fixed_paths["managed_after_path"]: managed_after.resolve(strict=True).read_bytes(),
    }
    for relative, payload in payloads.items():
        atomic_write_bytes(root / relative, payload)
    evidence = {
        "schema_version": SCHEMA_VERSION,
        **fixed_paths,
        "explicit_routing_sha256": sha256_bytes(payloads[fixed_paths["explicit_routing_path"]]),
        "ordinary_routing_sha256": sha256_bytes(payloads[fixed_paths["ordinary_routing_path"]]),
        "slot_ledger_sha256": sha256_bytes(payloads[fixed_paths["slot_ledger_path"]]),
        "managed_before_sha256": sha256_bytes(payloads[fixed_paths["managed_before_path"]]),
        "managed_after_sha256": sha256_bytes(payloads[fixed_paths["managed_after_path"]]),
        "candidate_explicit_routing": explicit["passed"],
        "ordinary_legacy_routing": ordinary["passed"],
        "managed_projection_clean": comparison["passed"], "recorded_at_utc": recorded_at,
    }
    if set(evidence) != CANDIDATE_EVIDENCE_FIELDS:
        raise EvaluationError("INVALID_ROUTING_EVIDENCE", "candidate evidence fields changed")
    atomic_write_json(evidence_path, evidence)
    state["candidate_check_evidence_path"] = "candidate-checks/evidence.json"
    state["candidate_check_evidence_sha256"] = sha256_bytes(evidence_path.read_bytes())
    atomic_write_json(state_path, state)
    return evidence


def record_fixture_authority_review(
    fixtures: Path, authority_path: Path, attempt_token: Path,
    slot_ledger: Path, review_output: Path, out: Path,
    *, now: str | None = None,
) -> dict[str, Any]:
    root = strict_root(fixtures)
    paths = finalized_review_paths(root)
    if out.parent.resolve(strict=True) / out.name != paths["receipt"]:
        raise EvaluationError("INVALID_PATH", "authority review receipt must use its fixed path")
    if review_output.resolve(strict=True).read_bytes() != paths["output"].read_bytes():
        raise EvaluationError("INVALID_REVIEW_RECEIPT", "recorded output differs from finalized snapshot")
    if paths["receipt"].exists():
        return validate_fixture_authority_review(
            root, authority_path, attempt_token, slot_ledger, paths["receipt"],
        )
    authority_receipt = validate_fixture_authority(root, authority_path)
    attempt = require_fields(load_json(paths["attempt"]), REVIEW_ATTEMPT_FIELDS, "review attempt")
    finalize_fixture_authority_review(
        attempt_token, slot_ledger, "SUCCEEDED",
        runtime_agent_id=attempt["runtime_agent_id"], output_path=review_output,
    )
    output = validate_review_output(
        load_json(paths["output"]), load_json(authority_path),
        authority_receipt["authority_sha256"], authority_receipt["source_bundle_sha256"],
    )
    receipt = {
        "schema_version": 1,
        "authority_path": "fixture-authority.json",
        "authority_sha256": authority_receipt["authority_sha256"],
        "source_bundle_sha256": authority_receipt["source_bundle_sha256"],
        "review_input_path": "authority-review/input.json",
        "review_input_sha256": sha256_bytes(paths["input"].read_bytes()),
        "review_attempt_path": "authority-review/attempt.json",
        "review_attempt_sha256": sha256_bytes(paths["attempt"].read_bytes()),
        "review_output_path": "authority-review/output.json",
        "review_output_sha256": sha256_bytes(paths["output"].read_bytes()),
        "reviewer_runtime_agent_id": attempt["runtime_agent_id"],
        "slot_id": attempt["slot_id"],
        "released_slot_path": "authority-review/released-slot.json",
        "released_slot_sha256": sha256_bytes(paths["released"].read_bytes()),
        "released_slot_projection": attempt["released_slot_projection"],
        "released_slot_projection_sha256": attempt["released_slot_projection_sha256"],
        "released_slot_close_evidence_sha256": attempt["released_slot_close_evidence_sha256"],
        "verdict": output["verdict"],
        "recorded_at_utc": now or utc_now(),
    }
    atomic_write_json(paths["receipt"], receipt)
    return validate_fixture_authority_review(
        root, authority_path, attempt_token, slot_ledger, paths["receipt"],
    )


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(raw, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(raw):
            os.unlink(raw)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(path, canonical_bytes(value) + b"\n")


def show(run_dir: Path) -> dict[str, Any]:
    _root, _path, state = load_prepared_run(run_dir)
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot-managed")
    snapshot.add_argument("--manifest", required=True)
    snapshot.add_argument("--installed-root", required=True)
    snapshot.add_argument("--backup-root", required=True)
    snapshot.add_argument("--out", required=True)
    compare = subparsers.add_parser("compare-managed")
    compare.add_argument("--before", required=True)
    compare.add_argument("--after", required=True)
    compare.add_argument("--allow-added", action="append", default=[])
    compare.add_argument("--allow-changed", action="append", default=[])
    restore = subparsers.add_parser("restore-managed")
    restore.add_argument("--snapshot", required=True)
    restore.add_argument("--installed-root", required=True)
    validate = subparsers.add_parser("validate-fixture-authority")
    validate.add_argument("--fixtures", required=True)
    validate.add_argument("--authority", required=True)
    prepare_review = subparsers.add_parser("prepare-fixture-authority-review")
    prepare_review.add_argument("--fixtures", required=True)
    prepare_review.add_argument("--authority", required=True)
    prepare_review.add_argument("--slot-id", required=True)
    prepare_review.add_argument("--slot-ledger", required=True)
    prepare_review.add_argument("--out", required=True)
    finalize_review = subparsers.add_parser("finalize-fixture-authority-review")
    finalize_review.add_argument("--attempt-token", required=True)
    finalize_review.add_argument("--slot-ledger", required=True)
    finalize_review.add_argument("--status", required=True, choices=sorted(REVIEW_TERMINAL_STATUSES))
    finalize_review.add_argument("--runtime-agent-id")
    finalize_review.add_argument("--output")
    record_review = subparsers.add_parser("record-fixture-authority-review")
    record_review.add_argument("--fixtures", required=True)
    record_review.add_argument("--authority", required=True)
    record_review.add_argument("--attempt-token", required=True)
    record_review.add_argument("--slot-ledger", required=True)
    record_review.add_argument("--review-output", required=True)
    record_review.add_argument("--out", required=True)
    prepare_run = subparsers.add_parser("prepare")
    prepare_run.add_argument("--fixtures", required=True)
    prepare_run.add_argument("--fixture-authority", required=True)
    prepare_run.add_argument("--authority-review", required=True)
    prepare_run.add_argument("--run-dir", required=True)
    prepare_run.add_argument("--case-id", action="append", choices=CASE_IDS, default=[])
    initialize = subparsers.add_parser("initialize-planner")
    initialize.add_argument("--run-dir", required=True)
    initialize.add_argument("--run-id", required=True)
    materialize = subparsers.add_parser("materialize-input")
    materialize.add_argument("--run-dir", required=True)
    materialize.add_argument("--run-id", required=True)
    resume = subparsers.add_parser("materialize-resume")
    resume.add_argument("--run-dir", required=True)
    resume.add_argument("--run-id", required=True)
    no_plan = subparsers.add_parser("record-no-plan")
    no_plan.add_argument("--run-dir", required=True)
    no_plan.add_argument("--run-id", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("--run-dir", required=True)
    record.add_argument("--run-id", required=True)
    record.add_argument("--successful-attempt-token")
    record.add_argument("--slot-ledger")
    record.add_argument("--consulted-sources", required=True)
    score = subparsers.add_parser("score")
    score.add_argument("--run-dir", required=True)
    score.add_argument("--fixtures", required=True)
    score.add_argument("--out", required=True)
    validate_scored = subparsers.add_parser("validate-score")
    validate_scored.add_argument("--score", required=True)
    prepare_outer = subparsers.add_parser("prepare-attempt")
    prepare_outer.add_argument("--run-dir", required=True)
    prepare_outer.add_argument("--run-id", required=True)
    prepare_outer.add_argument("--slot-id", required=True)
    prepare_outer.add_argument("--slot-ledger", required=True)
    prepare_outer.add_argument("--input", required=True)
    prepare_outer.add_argument("--out", required=True)
    finalize_outer = subparsers.add_parser("finalize-attempt")
    finalize_outer.add_argument("--run-dir", required=True)
    finalize_outer.add_argument("--attempt-token", required=True)
    finalize_outer.add_argument("--slot-ledger", required=True)
    finalize_outer.add_argument("--status", required=True, choices=sorted(ATTEMPT_TERMINAL_STATUSES))
    finalize_outer.add_argument("--runtime-agent-id")
    finalize_outer.add_argument("--output")
    prepare_probe = subparsers.add_parser("prepare-routing-probe")
    prepare_probe.add_argument("--run-dir", required=True)
    prepare_probe.add_argument("--probe", required=True, choices=CANDIDATE_PROBES)
    prepare_probe.add_argument("--slot-id", required=True)
    prepare_probe.add_argument("--slot-ledger", required=True)
    prepare_probe.add_argument("--out", required=True)
    finalize_probe = subparsers.add_parser("finalize-routing-probe")
    finalize_probe.add_argument("--run-dir", required=True)
    finalize_probe.add_argument("--attempt-token", required=True)
    finalize_probe.add_argument("--slot-ledger", required=True)
    finalize_probe.add_argument("--status", required=True, choices=sorted(ATTEMPT_TERMINAL_STATUSES))
    finalize_probe.add_argument("--runtime-agent-id")
    finalize_probe.add_argument("--output")
    record_checks = subparsers.add_parser("record-candidate-checks")
    record_checks.add_argument("--run-dir", required=True)
    record_checks.add_argument("--explicit-attempt-token", required=True)
    record_checks.add_argument("--ordinary-attempt-token", required=True)
    record_checks.add_argument("--slot-ledger", required=True)
    record_checks.add_argument("--managed-before", required=True)
    record_checks.add_argument("--managed-after", required=True)
    show_run = subparsers.add_parser("show")
    show_run.add_argument("--run-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "snapshot-managed":
            result = snapshot_managed(
                Path(args.manifest), Path(args.installed_root), Path(args.backup_root),
                Path(args.out),
            )
        elif args.command == "compare-managed":
            result = compare_managed(
                Path(args.before), Path(args.after), args.allow_added,
                args.allow_changed,
            )
        elif args.command == "restore-managed":
            result = restore_managed(Path(args.snapshot), Path(args.installed_root))
        elif args.command == "validate-fixture-authority":
            result = validate_fixture_authority(Path(args.fixtures), Path(args.authority))
        elif args.command == "prepare-fixture-authority-review":
            result = prepare_fixture_authority_review(
                Path(args.fixtures), Path(args.authority), args.slot_id,
                Path(args.slot_ledger), Path(args.out),
            )
        elif args.command == "finalize-fixture-authority-review":
            result = finalize_fixture_authority_review(
                Path(args.attempt_token), Path(args.slot_ledger), args.status,
                runtime_agent_id=args.runtime_agent_id,
                output_path=Path(args.output) if args.output else None,
            )
        elif args.command == "record-fixture-authority-review":
            result = record_fixture_authority_review(
                Path(args.fixtures), Path(args.authority), Path(args.attempt_token),
                Path(args.slot_ledger), Path(args.review_output), Path(args.out),
            )
        elif args.command == "prepare":
            if args.case_id and tuple(args.case_id) != CASE_IDS:
                raise EvaluationError(
                    "INVALID_FIXTURE", "case filters must name all three cases in canonical order",
                )
            result = prepare(
                Path(args.fixtures), Path(args.fixture_authority),
                Path(args.authority_review), Path(args.run_dir),
            )
        elif args.command == "prepare-attempt":
            result = prepare_attempt(
                Path(args.run_dir), args.run_id, args.slot_id, Path(args.slot_ledger),
                Path(args.input), Path(args.out),
            )
        elif args.command == "initialize-planner":
            result = initialize_planner(Path(args.run_dir), args.run_id)
        elif args.command == "materialize-input":
            result = materialize_input(Path(args.run_dir), args.run_id)
        elif args.command == "materialize-resume":
            result = materialize_resume(Path(args.run_dir), args.run_id)
        elif args.command == "record-no-plan":
            result = record_no_plan(Path(args.run_dir), args.run_id)
        elif args.command == "record":
            result = record_row(
                Path(args.run_dir), args.run_id, Path(args.consulted_sources),
                Path(args.successful_attempt_token) if args.successful_attempt_token else None,
                Path(args.slot_ledger) if args.slot_ledger else None,
            )
        elif args.command == "score":
            result = score_run(
                Path(args.run_dir), Path(args.fixtures), Path(args.out),
            )
        elif args.command == "validate-score":
            result = validate_score(Path(args.score))
        elif args.command == "finalize-attempt":
            result = finalize_attempt(
                Path(args.run_dir), Path(args.attempt_token), Path(args.slot_ledger),
                args.status, runtime_agent_id=args.runtime_agent_id,
                output_path=Path(args.output) if args.output else None,
            )
        elif args.command == "prepare-routing-probe":
            result = prepare_routing_probe(
                Path(args.run_dir), args.probe, args.slot_id, Path(args.slot_ledger),
                Path(args.out),
            )
        elif args.command == "finalize-routing-probe":
            result = finalize_routing_probe(
                Path(args.run_dir), Path(args.attempt_token), Path(args.slot_ledger),
                args.status, runtime_agent_id=args.runtime_agent_id,
                output_path=Path(args.output) if args.output else None,
            )
        elif args.command == "record-candidate-checks":
            result = record_candidate_checks(
                Path(args.run_dir), Path(args.explicit_attempt_token),
                Path(args.ordinary_attempt_token), Path(args.slot_ledger),
                Path(args.managed_before), Path(args.managed_after),
            )
        elif args.command == "show":
            result = show(Path(args.run_dir))
        else:
            raise EvaluationError("UNKNOWN_COMMAND", args.command)
        print(canonical_bytes({"ok": True, **result}).decode("utf-8"))
        return 0
    except EvaluationError as exc:
        print(canonical_bytes({"ok": False, "error": exc.code, "message": str(exc)}).decode("utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
