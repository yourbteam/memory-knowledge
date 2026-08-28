#!/usr/bin/env python3
"""Fail-closed deterministic Plan Playbook package controller."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Sequence


SCHEMA_VERSION = 1
RUN_ROOT_NAME = ".plan-playbook"
LEGACY_RUN_ROOT_NAME = ".plan-playbook-v2"
MIGRATION_JOURNAL_NAME = ".plan-playbook-migration.json"
LENS_CONTRACT_ID = "PLAN_PLAYBOOK_V2_HARDENING_LENSES_V1"
ROLES = (
    "VERIFY_PLAN_VERIFIER", "VERIFY_PLAN_CRITIC", "INTERNAL_READINESS",
    "REQUIREMENTS_COVERAGE", "REQUIREMENTS_SATISFACTION",
)
STAGES = (
    "VERIFY_PLAN", "INTERNAL_READINESS", "REQUIREMENTS_COVERAGE",
    "REQUIREMENTS_SATISFACTION",
)
STAGE_NAMES = {
    "VERIFY_PLAN": "plan-verify",
    "INTERNAL_READINESS": "plan-internal-readiness",
    "REQUIREMENTS_COVERAGE": "plan-requirements-coverage",
    "REQUIREMENTS_SATISFACTION": "plan-requirements-satisfaction",
}
ROLE_STAGE = {
    "VERIFY_PLAN_VERIFIER": "VERIFY_PLAN", "VERIFY_PLAN_CRITIC": "VERIFY_PLAN",
    "INTERNAL_READINESS": "INTERNAL_READINESS",
    "REQUIREMENTS_COVERAGE": "REQUIREMENTS_COVERAGE",
    "REQUIREMENTS_SATISFACTION": "REQUIREMENTS_SATISFACTION",
}
STATE_FIELDS = {
    "schema_version", "package_id", "task_root", "run_root", "status", "revision",
    "entry_mode", "approval_context", "approval_authorization_path",
    "approval_authorization_sha256", "implementation_approval_status",
    "implementation_authorization_request_path",
    "implementation_authorization_request_sha256", "implementation_authorization_path",
    "implementation_authorization_sha256", "profile", "started_at_utc",
    "deadline_at_utc", "cap_reason", "cap_reached_at_utc", "cap_stage",
    "cap_completed_verification_iteration", "charter", "charter_sha256",
    "requirements", "requirements_sha256", "evidence_index_sha256",
    "lens_contract_id", "lens_contract_path", "lens_contract_sha256",
    "supplied_input_root", "source_snapshots", "plan_sha256", "surface_map_sha256",
    "decisions_sha256", "verification_ledger_sha256", "budgets", "revision_history",
    "emission_history", "attempts", "stage_results", "findings", "dispositions",
    "finding_transitions", "blockers",
}
CHARTER_FIELDS = {
    "schema_version", "objective", "allowed_repositories", "allowed_paths",
    "supplied_input_root", "exclusions", "deliverables", "approval_boundaries",
    "change_characteristics",
}
REQUIREMENT_FIELDS = {
    "id", "text", "source", "operational_maturity", "evidence_availability",
    "acceptance_intent", "scope_id", "research_value_type", "research_value",
    "evidence_ids", "planner_obligations",
}
OBLIGATION_FIELDS = {
    "id", "description", "status", "implementation_anchors", "verification_anchors",
    "required_inputs", "owner", "closure_condition", "evidence_ids",
}
EVIDENCE_FIELDS = {"id", "requirement_ids", "facets", "source", "supported_claim", "limitations"}
EVIDENCE_SOURCE_FIELDS = {"kind", "repository_key", "path", "sha256"}
FACETS = {"CURRENT_BEHAVIOR", "IMPLEMENTATION_OWNERSHIP", "ACCEPTANCE_OBSERVABLE"}
BEHAVIOR_INPUT_CATEGORIES = {
    "valid", "empty", "error", "malformed_success", "mixed", "boundary",
}
BEHAVIOR_CONSUMER_KINDS = {
    "boundary", "rendering", "aggregate", "persistence", "external_effect",
}
ATTEMPT_FIELDS = {
    "attempt_id", "attempt_sequence", "state_revision", "round", "role",
    "verification_iteration", "assigned_coverage_ids", "assigned_obligation_ids",
    "lens_contract_id", "lens_contract_sha256", "slot_id", "input_envelope_sha256",
    "status", "runtime_agent_id", "output_path", "output_sha256", "close_evidence",
    "close_evidence_sha256", "prepared_at_utc", "finalized_at_utc",
}
INPUT_FIELDS = {
    "schema_version", "role", "round", "verification_iteration",
    "assigned_coverage_ids", "assigned_obligation_ids", "lens_contract", "objective",
    "charter", "requirements", "plan", "evidence_index", "surface_map",
    "verification_ledger", "raw_findings", "verifier_obligation_assessments",
    "authoritative_roots",
}
RAW_OUTPUT_FIELDS = {
    "schema_version", "attempt_id", "input_envelope_sha256", "role", "round",
    "verification_iteration", "assigned_coverage_ids", "assigned_obligation_ids",
    "lens_contract_id", "lens_contract_sha256", "assessed_plan_sha256",
    "terminal_envelope", "findings", "dispositions", "obligation_assessments",
    "inventory_approval", "assessment_approvals", "coverage_exclusion_approvals",
    "artifact_transfer", "completed_at_utc",
}
ESCALATION_OUTPUT_FIELDS = {
    "schema_version", "attempt_id", "input_envelope_sha256", "role", "round",
    "assessed_plan_sha256", "signal", "completed_at_utc",
}
FINDING_FIELDS = {
    "id", "fingerprint", "round", "stage", "source_role", "requirement_ids",
    "obligation_ids", "coverage_ids", "practical_consequence", "evidence",
    "source_classification",
}
DISPOSITION_FIELDS = {
    "finding_id", "finding_fingerprint", "decision", "rationale", "parent_action",
    "new_finding_classification",
}
OBLIGATION_ASSESSMENT_FIELDS = {
    "iteration", "obligation_id", "binding_sha256", "status", "evidence",
    "finding_snapshots", "blocked_boundary", "assessment_fingerprint",
}
TERMINAL_ENVELOPE_FIELDS = {
    "stage", "iteration", "attempt", "assigned_requirement_ids", "assigned_gap_ids",
    "owned_blocker_ids", "verdict", "open_gap_ids", "closed_gap_ids", "new_gaps",
    "new_blockers", "record_transitions", "evidence", "artifact_paths",
}
ARTIFACT_TRANSFER_FIELDS = {"form", "target_path", "content_markdown", "sha256"}
INVENTORY_APPROVAL_FIELDS = {
    "inventory_sha256", "plan_sha256", "evidence_revision_sha256", "decision",
    "rationale", "evidence",
}
ASSESSMENT_APPROVAL_FIELDS = {
    "iteration", "obligation_id", "binding_sha256", "assessment_fingerprint",
    "decision", "rationale", "evidence",
}
COVERAGE_EXCLUSION_APPROVAL_FIELDS = {
    "coverage_id", "prior_status", "approved_status", "plan_sha256",
    "evidence_revision_sha256", "inventory_sha256", "rationale", "evidence",
}
TERMINAL_ATTEMPT_STATUSES = {
    "SPAWN_FAILED", "BIND_FAILED", "SUCCEEDED", "PROFILE_ESCALATION_REQUIRED",
    "OUTPUT_INVALID", "RUNTIME_FAILED", "TIMED_OUT",
}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
SOURCE_SNAPSHOT_FIELDS = {
    "repository_key", "source_path", "source_tree_sha256", "snapshot_path",
    "snapshot_tree_sha256", "manifest_path", "manifest_sha256", "created_at_utc",
}
SOURCE_SNAPSHOT_MANIFEST_FIELDS = {"schema_version", "contract_id", "files"}
SOURCE_SNAPSHOT_FILE_FIELDS = {"path", "sha256"}
CONVERGENCE_ENTRY_FIELDS = {
    "schema_version", "task_id", "outer_iteration", "status", "objective",
    "requirements", "repository_roots", "managed_roots", "allowed_paths",
    "source_state_path", "source_state_sha256",
}
REVISION_HISTORY_FIELDS = {"revision", "receipt_path", "receipt_sha256"}
REVISION_RECEIPT_FIELDS = {
    "schema_version", "package_id", "revision", "profile",
    "evidence_index_sha256", "plan_sha256", "plan_snapshot_path",
    "surface_map_sha256", "decisions_sha256", "verification_ledger_sha256",
    "revision_basis_sha256", "predecessor_receipt_sha256", "published_at_utc",
}
OUTER_CONTINUATION_FIELDS = {
    "schema_version", "authorization_id", "task_id", "outer_iteration", "stage", "kind",
    "operations", "target_ids", "repository_roots", "allowed_paths", "plan_package_id",
    "inner_state_sha256", "plan_sha256", "approved_from_iteration", "approved_through_iteration",
    "outer_resume_status", "outer_blocked_stage", "approved_at_utc", "approval_evidence",
}
CONTINUATION_PROVENANCE_FIELDS = {
    "schema_version", "convergence_state_path", "convergence_state_sha256", "outer_approval_id",
    "outer_operation_id", "outer_iteration", "outer_resume_status", "outer_blocked_stage",
    "authorization_envelope_path", "authorization_envelope_sha256", "inner_approval_sha256",
}


class PlanPackageError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical_bytes(value: Any) -> bytes:
    def reject(item: Any) -> None:
        if isinstance(item, float) and (item != item or item in (float("inf"), float("-inf"))):
            raise PlanPackageError("NON_CANONICAL_JSON", "non-finite JSON number")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise PlanPackageError("NON_CANONICAL_JSON", "JSON object keys must be strings")
                reject(child)
        elif isinstance(item, list):
            for child in item:
                reject(child)
    reject(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def canonical_hash_sorted(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(values, key=canonical_hash)


def bytes_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise PlanPackageError("INVALID_TIMESTAMP", "timestamp must be canonical UTC")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def require_exact(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise PlanPackageError("INVALID_SCHEMA", f"{label} must contain exactly {sorted(fields)}")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanPackageError("INVALID_SCHEMA", f"{label} must be a non-empty string")
    return value


def sorted_unique_strings(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise PlanPackageError("INVALID_SCHEMA", f"{label} must be an array of non-empty strings")
    if not allow_empty and not value:
        raise PlanPackageError("INVALID_SCHEMA", f"{label} cannot be empty")
    if value != sorted(set(value)):
        raise PlanPackageError("INVALID_SCHEMA", f"{label} must be sorted and unique")
    return value


def load_json(path: Path, label: str = "JSON file") -> Any:
    if path.is_symlink() or not path.is_file():
        raise PlanPackageError("UNSAFE_PATH", f"{label} must be a regular non-symlink file")
    try:
        return json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlanPackageError("INVALID_JSON", f"{label} is not valid UTF-8 JSON") from exc


def resolve_dir(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise PlanPackageError("UNSAFE_PATH", f"{label} cannot be a symlink")
    try:
        result = path.resolve(strict=True)
    except OSError as exc:
        raise PlanPackageError("PATH_UNAVAILABLE", f"{label} is unavailable") from exc
    if not result.is_dir():
        raise PlanPackageError("UNSAFE_PATH", f"{label} must be a directory")
    return result


def contained_file(root: Path, relative: str, label: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
        raise PlanPackageError("UNSAFE_PATH", f"{label} must be a normalized relative POSIX path")
    path = root.joinpath(*pure.parts)
    if path.is_symlink():
        raise PlanPackageError("UNSAFE_PATH", f"{label} cannot be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PlanPackageError("PATH_UNAVAILABLE", f"{label} is unavailable") from exc
    if root not in resolved.parents or not resolved.is_file():
        raise PlanPackageError("UNSAFE_PATH", f"{label} escapes its authority root")
    return resolved


def contained_dir(root: Path, relative: str, label: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
        raise PlanPackageError("UNSAFE_PATH", f"{label} must be a normalized relative POSIX path")
    path = root.joinpath(*pure.parts)
    if path.is_symlink():
        raise PlanPackageError("UNSAFE_PATH", f"{label} cannot be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PlanPackageError("PATH_UNAVAILABLE", f"{label} is unavailable") from exc
    if root not in resolved.parents or not resolved.is_dir():
        raise PlanPackageError("UNSAFE_PATH", f"{label} escapes its authority root")
    return resolved


def relative_under(root: Path, path: Path, label: str) -> str:
    try:
        relative = path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise PlanPackageError("UNSAFE_PATH", f"{label} is outside its frozen root") from exc
    if path.is_symlink():
        raise PlanPackageError("UNSAFE_PATH", f"{label} cannot be a symlink")
    return relative.as_posix()


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_dir(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, canonical_bytes(value))


def publish_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            raise PlanPackageError("IMMUTABLE_CONFLICT", f"immutable path conflict: {path}")
        return
    atomic_bytes(path, payload)
    if path.read_bytes() != payload:
        raise PlanPackageError("SNAPSHOT_TAMPER", f"snapshot reopen failed: {path}")


def module_from_path(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PlanPackageError("OWNER_CONTRACT_UNAVAILABLE", f"cannot load owner contract {path}")
    module = importlib.util.module_from_spec(spec)
    prior_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = prior_dont_write_bytecode
    return module


SCRIPT = Path(__file__).resolve()
SKILLS_ROOT = SCRIPT.parents[2]
SHARED_ROOT = SKILLS_ROOT / "_shared"
REPO_ROOT = SKILLS_ROOT.parent


def shared_contracts() -> tuple[Any, Any, Any]:
    tree = module_from_path("plan_v2_tree_digest", SHARED_ROOT / "tree_digest.py")
    slots = module_from_path("plan_v2_agent_slots", SHARED_ROOT / "agent_slot_ledger.py")
    ledger = module_from_path("plan_v2_verification_ledger", SHARED_ROOT / "verification_ledger.py")
    if not hasattr(tree, "TREE_SHA256_V1"):
        raise PlanPackageError("OWNER_CONTRACT_UNAVAILABLE", "TREE_SHA256_V1 API is unavailable")
    for name in ("released_slot_projection", "released_slot_close_evidence_sha256"):
        if not hasattr(slots, name):
            raise PlanPackageError("OWNER_CONTRACT_UNAVAILABLE", f"agent-slot {name} API is unavailable")
    return tree, slots, ledger


def research_owner() -> Any:
    module = module_from_path(
        "plan_v2_research_package", SCRIPT.parent / "research_package.py"
    )
    if not hasattr(module, "validate_package"):
        raise PlanPackageError("OWNER_CONTRACT_UNAVAILABLE", "research validate_package API is unavailable")
    return module


def enumerate_assessment_source(root: Path) -> tuple[list[dict[str, str]], dict[str, bytes]]:
    records: list[dict[str, str]] = []
    payloads: dict[str, bytes] = {}

    def is_controller_snapshot_archive(child_relative: PurePosixPath) -> bool:
        parts = child_relative.parts
        return any(
            parts[index : index + 2] == (RUN_ROOT_NAME, "source-snapshots")
            for index in range(len(parts) - 1)
        )

    def add_file(child_relative: PurePosixPath) -> None:
        if is_controller_snapshot_archive(child_relative):
            return
        if child_relative.name == ".DS_Store" or any(
            part == ".env" or part.startswith(".env.")
            for part in child_relative.parts
        ):
            return
        target = root.joinpath(*child_relative.parts)
        cursor = root
        for part in child_relative.parts:
            cursor /= part
            if cursor.is_symlink():
                raise PlanPackageError(
                    "UNSAFE_SOURCE_ENTRY",
                    f"source snapshot rejects symlink: {child_relative}",
                )
        if not target.exists():
            return
        if not target.is_file():
            raise PlanPackageError(
                "UNSAFE_SOURCE_ENTRY",
                f"source snapshot rejects special file: {child_relative}",
            )
        path = child_relative.as_posix()
        try:
            payload = target.read_bytes()
        except OSError as exc:
            raise PlanPackageError("SOURCE_SNAPSHOT_FAILED", f"cannot read source file: {path}") from exc
        payloads[path] = payload
        records.append({"path": path, "sha256": bytes_hash(payload)})

    git_root = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if git_root.returncode == 0 and Path(git_root.stdout.strip()).resolve() == root.resolve():
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            check=False,
        )
        if listed.returncode != 0:
            raise PlanPackageError("SOURCE_SNAPSHOT_FAILED", "git source enumeration failed")
        try:
            paths = [
                PurePosixPath(item.decode("utf-8"))
                for item in listed.stdout.split(b"\0")
                if item
            ]
        except UnicodeDecodeError as exc:
            raise PlanPackageError("UNSAFE_SOURCE_ENTRY", "source path is not UTF-8") from exc
        for child_relative in sorted(paths, key=lambda item: item.as_posix().encode("utf-8")):
            if child_relative.is_absolute() or ".." in child_relative.parts:
                raise PlanPackageError("UNSAFE_SOURCE_ENTRY", "git source path escapes repository")
            add_file(child_relative)
        return records, payloads

    def visit(directory: Path, relative: PurePosixPath) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: os.fsencode(entry.name))
        except OSError as exc:
            raise PlanPackageError("SOURCE_SNAPSHOT_FAILED", f"cannot enumerate source root: {directory}") from exc
        for entry in entries:
            child_relative = relative / entry.name
            if entry.name == ".DS_Store" or (not relative.parts and entry.name == ".git"):
                continue
            if entry.is_symlink():
                raise PlanPackageError("UNSAFE_SOURCE_ENTRY", f"source snapshot rejects symlink: {child_relative}")
            if is_controller_snapshot_archive(child_relative):
                continue
            if entry.is_dir(follow_symlinks=False):
                visit(Path(entry.path), child_relative)
                continue
            if not entry.is_file(follow_symlinks=False):
                raise PlanPackageError("UNSAFE_SOURCE_ENTRY", f"source snapshot rejects special file: {child_relative}")
            add_file(child_relative)

    visit(root, PurePosixPath())
    records.sort(key=lambda item: item["path"].encode("utf-8"))
    return records, payloads


def validate_source_snapshot(run_root: Path, value: Any) -> dict[str, Any]:
    record = require_exact(value, SOURCE_SNAPSHOT_FIELDS, "assessment source snapshot")
    require_string(record["repository_key"], "source snapshot repository key")
    source_path = resolve_dir(Path(require_string(record["source_path"], "source snapshot source path")), "source snapshot source root")
    del source_path
    for field in ("source_tree_sha256", "snapshot_tree_sha256", "manifest_sha256"):
        if not isinstance(record[field], str) or not SHA_RE.fullmatch(record[field]):
            raise PlanPackageError("INVALID_SOURCE_SNAPSHOT", f"{field} must be SHA-256")
    parse_utc(record["created_at_utc"])
    snapshot = contained_dir(run_root, record["snapshot_path"], "source snapshot tree")
    manifest_path = contained_file(run_root, record["manifest_path"], "source snapshot manifest")
    manifest = require_exact(load_json(manifest_path), SOURCE_SNAPSHOT_MANIFEST_FIELDS, "source snapshot manifest")
    if manifest["schema_version"] != 1 or manifest["contract_id"] != "ASSESSMENT_SOURCE_SNAPSHOT_V1":
        raise PlanPackageError("INVALID_SOURCE_SNAPSHOT", "source snapshot manifest identity is invalid")
    files = manifest["files"]
    if not isinstance(files, list):
        raise PlanPackageError("INVALID_SOURCE_SNAPSHOT", "source snapshot files must be an array")
    paths: list[str] = []
    for item in files:
        item = require_exact(item, SOURCE_SNAPSHOT_FILE_FIELDS, "source snapshot file")
        path = require_string(item["path"], "source snapshot path")
        if path in paths or paths and path.encode("utf-8") <= paths[-1].encode("utf-8"):
            raise PlanPackageError("INVALID_SOURCE_SNAPSHOT", "source snapshot paths must be unique and byte-sorted")
        if not isinstance(item["sha256"], str) or not SHA_RE.fullmatch(item["sha256"]):
            raise PlanPackageError("INVALID_SOURCE_SNAPSHOT", "source snapshot file hash is invalid")
        copied = contained_file(snapshot, path, "source snapshot file")
        if bytes_hash(copied.read_bytes()) != item["sha256"]:
            raise PlanPackageError("SOURCE_SNAPSHOT_TAMPER", f"source snapshot file changed: {path}")
        paths.append(path)
    present = sorted(
        (path.relative_to(snapshot).as_posix() for path in snapshot.rglob("*") if path.is_file()),
        key=lambda path: path.encode("utf-8"),
    )
    if present != paths:
        raise PlanPackageError("SOURCE_SNAPSHOT_TAMPER", "source snapshot tree file set changed")
    tree_hash = canonical_hash(files)
    if bytes_hash(manifest_path.read_bytes()) != record["manifest_sha256"]:
        raise PlanPackageError("SOURCE_SNAPSHOT_TAMPER", "source snapshot manifest changed")
    expected_root = f"source-snapshots/{record['manifest_sha256']}"
    if record["snapshot_path"] != f"{expected_root}/tree" or record["manifest_path"] != f"{expected_root}/manifest.json":
        raise PlanPackageError("INVALID_SOURCE_SNAPSHOT", "source snapshot paths are not content addressed")
    if tree_hash != record["source_tree_sha256"] or tree_hash != record["snapshot_tree_sha256"]:
        raise PlanPackageError("SOURCE_SNAPSHOT_TAMPER", "source and snapshot tree identities differ")
    return record


def freeze_source_snapshot(snapshot_root: Path) -> None:
    entries = sorted(
        snapshot_root.rglob("*"),
        key=lambda path: (len(path.relative_to(snapshot_root).parts), path.as_posix()),
        reverse=True,
    )
    for path in entries:
        if path.is_symlink():
            raise PlanPackageError("UNSAFE_SOURCE_ENTRY", "source snapshot contains a symlink")
        path.chmod(0o555 if path.is_dir() else 0o444)
    snapshot_root.chmod(0o555)


def create_source_snapshot(run_root: Path, repository_key: str, source_root: Path) -> dict[str, Any]:
    records, payloads = enumerate_assessment_source(source_root)
    tree_hash = canonical_hash(records)
    manifest = {
        "schema_version": 1,
        "contract_id": "ASSESSMENT_SOURCE_SNAPSHOT_V1",
        "files": records,
    }
    manifest_payload = canonical_bytes(manifest)
    manifest_hash = bytes_hash(manifest_payload)
    relative_root = f"source-snapshots/{manifest_hash}"
    final_root = run_root / relative_root
    if final_root.exists():
        record = {
            "repository_key": repository_key,
            "source_path": str(source_root),
            "source_tree_sha256": tree_hash,
            "snapshot_path": f"{relative_root}/tree",
            "snapshot_tree_sha256": tree_hash,
            "manifest_path": f"{relative_root}/manifest.json",
            "manifest_sha256": manifest_hash,
            "created_at_utc": now_utc(),
        }
        existing = validate_source_snapshot(run_root, record)
        existing_manifest = load_json(run_root / existing["manifest_path"])
        if existing_manifest != manifest:
            raise PlanPackageError("SOURCE_SNAPSHOT_CONFLICT", "existing source snapshot has different bytes")
        return record

    staging = Path(tempfile.mkdtemp(prefix="plan-v2-source-snapshot-"))
    try:
        tree_root = staging / "tree"
        tree_root.mkdir()
        for item in records:
            target = tree_root.joinpath(*PurePosixPath(item["path"]).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as handle:
                handle.write(payloads[item["path"]])
                handle.flush()
                os.fsync(handle.fileno())
        atomic_bytes(staging / "manifest.json", manifest_payload)
        repeated_records, _ = enumerate_assessment_source(source_root)
        if repeated_records != records:
            raise PlanPackageError("SOURCE_CHANGED_DURING_SNAPSHOT", "source changed while assessment snapshot was copied")
        for item in records:
            copied = tree_root.joinpath(*PurePosixPath(item["path"]).parts)
            if bytes_hash(copied.read_bytes()) != item["sha256"]:
                raise PlanPackageError("SOURCE_SNAPSHOT_FAILED", f"copied source bytes changed: {item['path']}")
        fsync_dir(tree_root)
        fsync_dir(staging)
        final_root.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final_root)
        freeze_source_snapshot(final_root)
        fsync_dir(final_root.parent)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    record = {
        "repository_key": repository_key,
        "source_path": str(source_root),
        "source_tree_sha256": tree_hash,
        "snapshot_path": f"{relative_root}/tree",
        "snapshot_tree_sha256": tree_hash,
        "manifest_path": f"{relative_root}/manifest.json",
        "manifest_sha256": manifest_hash,
        "created_at_utc": now_utc(),
    }
    return validate_source_snapshot(run_root, record)


def convergence_projection(source_state_path: Path, charter: dict[str, Any], requirements: list[dict[str, Any]]) -> dict[str, Any]:
    if source_state_path.is_symlink() or not source_state_path.is_file():
        raise PlanPackageError("INVALID_CONVERGENCE_AUTHORIZATION", "convergence state must be a regular non-symlink file")
    source_state_path = source_state_path.resolve(strict=True)
    raw = source_state_path.read_bytes()
    try:
        outer = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlanPackageError("INVALID_CONVERGENCE_AUTHORIZATION", "convergence state is not valid UTF-8 JSON") from exc
    if not isinstance(outer, dict) or outer.get("schema_version") != 1 or outer.get("status") != "plan":
        raise PlanPackageError("INVALID_CONVERGENCE_AUTHORIZATION", "convergence state must be schema 1 in plan status")
    task_id = require_string(outer.get("task_id"), "convergence task id")
    objective = require_string(outer.get("objective"), "convergence objective")
    if objective != charter["objective"]:
        raise PlanPackageError("CONVERGENCE_SCOPE_MISMATCH", "convergence objective differs from charter")
    iteration = outer.get("outer_iteration")
    if isinstance(iteration, bool) or not isinstance(iteration, int) or iteration < 1:
        raise PlanPackageError("INVALID_CONVERGENCE_AUTHORIZATION", "outer iteration must be positive")
    outer_requirements = outer.get("requirements")
    if not isinstance(outer_requirements, dict):
        raise PlanPackageError("INVALID_CONVERGENCE_AUTHORIZATION", "convergence requirements must be an object")
    normalized_requirements = []
    for requirement_id in sorted(outer_requirements):
        item = outer_requirements[requirement_id]
        if not isinstance(item, dict) or item.get("id", requirement_id) != requirement_id:
            raise PlanPackageError("INVALID_CONVERGENCE_AUTHORIZATION", "convergence requirement identity is invalid")
        normalized_requirements.append({"id": requirement_id, "text": require_string(item.get("text"), "convergence requirement text")})
    expected_requirements = sorted(
        ({"id": item["id"], "text": item["text"]} for item in requirements),
        key=lambda item: item["id"],
    )
    if normalized_requirements != expected_requirements:
        raise PlanPackageError("CONVERGENCE_SCOPE_MISMATCH", "convergence requirements differ from package requirements")
    repositories = outer.get("repositories")
    managed_paths = outer.get("managed_paths")
    if not isinstance(repositories, dict) or not isinstance(managed_paths, dict):
        raise PlanPackageError("INVALID_CONVERGENCE_AUTHORIZATION", "convergence scope maps are invalid")
    repository_roots = sorted(str(Path(root).resolve(strict=True)) for root in repositories)
    managed_roots = sorted(str(Path(root).resolve(strict=True)) for root in managed_paths)
    allowed_paths: set[str] = set()
    for root_text, entry in repositories.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("allowed_paths"), list):
            raise PlanPackageError("INVALID_CONVERGENCE_AUTHORIZATION", "repository scope is invalid")
        root = Path(root_text).resolve(strict=True)
        for relative in entry["allowed_paths"]:
            if not isinstance(relative, str):
                raise PlanPackageError("INVALID_CONVERGENCE_AUTHORIZATION", "repository allowed path is invalid")
            allowed_paths.add(str(root / relative))
    for root_text, entry in managed_paths.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("allowed_children"), list):
            raise PlanPackageError("INVALID_CONVERGENCE_AUTHORIZATION", "managed scope is invalid")
        root = Path(root_text).resolve(strict=True)
        for relative in entry["allowed_children"]:
            if not isinstance(relative, str):
                raise PlanPackageError("INVALID_CONVERGENCE_AUTHORIZATION", "managed allowed path is invalid")
            allowed_paths.add(str(root / relative))
    expected_roots = sorted(charter["allowed_repositories"].values())
    expected_paths = sorted(
        str(Path(charter["allowed_repositories"][item["repository_key"]]) / item["path"])
        for item in charter["allowed_paths"]
    )
    if sorted(repository_roots + managed_roots) != expected_roots or sorted(allowed_paths) != expected_paths:
        raise PlanPackageError("CONVERGENCE_SCOPE_MISMATCH", "convergence repositories or allowed paths differ from charter")
    return {
        "schema_version": 1,
        "task_id": task_id,
        "outer_iteration": iteration,
        "status": "plan",
        "objective": objective,
        "requirements": normalized_requirements,
        "repository_roots": repository_roots,
        "managed_roots": managed_roots,
        "allowed_paths": sorted(allowed_paths),
        "source_state_path": str(source_state_path),
        "source_state_sha256": bytes_hash(raw),
    }


def validate_convergence_entry(state: dict[str, Any], run_root: Path) -> dict[str, Any]:
    if state["approval_context"] != "CONVERGENCE":
        if state["approval_authorization_path"] is not None or state["approval_authorization_sha256"] is not None:
            raise PlanPackageError("INVALID_STATE", "ordinary state cannot contain convergence authorization")
        return {}
    path = contained_file(run_root, state["approval_authorization_path"], "convergence entry authorization")
    if bytes_hash(path.read_bytes()) != state["approval_authorization_sha256"]:
        raise PlanPackageError("CONVERGENCE_AUTHORIZATION_TAMPER", "convergence entry authorization changed")
    projection = require_exact(load_json(path), CONVERGENCE_ENTRY_FIELDS, "convergence entry authorization")
    if state["approval_authorization_path"] != "authorizations/convergence-entry.json":
        raise PlanPackageError("INVALID_STATE", "convergence entry authorization path is invalid")
    current = convergence_projection(Path(projection["source_state_path"]), state["charter"], state["requirements"])
    for field in CONVERGENCE_ENTRY_FIELDS - {"status", "source_state_sha256"}:
        if current[field] != projection[field]:
            raise PlanPackageError("CONVERGENCE_AUTHORIZATION_DRIFT", f"convergence authority changed: {field}")
    return projection


def validate_charter(value: Any) -> dict[str, Any]:
    charter = require_exact(value, CHARTER_FIELDS, "charter")
    if charter["schema_version"] != 1:
        raise PlanPackageError("INVALID_CHARTER", "unsupported charter schema_version")
    require_string(charter["objective"], "charter objective")
    repositories = charter["allowed_repositories"]
    if not isinstance(repositories, dict) or not repositories:
        raise PlanPackageError("INVALID_CHARTER", "allowed_repositories must be non-empty")
    normalized_repositories: dict[str, str] = {}
    for key in sorted(repositories):
        require_string(key, "repository key")
        root = resolve_dir(Path(require_string(repositories[key], "repository root")), "repository root")
        normalized_repositories[key] = str(root)
    paths = charter["allowed_paths"]
    if not isinstance(paths, list) or not paths:
        raise PlanPackageError("INVALID_CHARTER", "allowed_paths must be non-empty")
    normalized_paths = []
    for item in paths:
        require_exact(item, {"repository_key", "path"}, "allowed path")
        if item["repository_key"] not in normalized_repositories:
            raise PlanPackageError("INVALID_CHARTER", "allowed path names an unknown repository")
        pure = PurePosixPath(item["path"])
        if pure.is_absolute() or ".." in pure.parts or str(pure) != item["path"]:
            raise PlanPackageError("INVALID_CHARTER", "allowed path is not normalized")
        normalized_paths.append(dict(item))
    if normalized_paths != sorted(normalized_paths, key=lambda x: (x["repository_key"], x["path"])):
        raise PlanPackageError("INVALID_CHARTER", "allowed_paths must be sorted")
    for field in ("exclusions", "deliverables", "approval_boundaries"):
        sorted_unique_strings(charter[field], f"charter {field}")
    characteristics = sorted_unique_strings(charter["change_characteristics"], "change_characteristics", allow_empty=False)
    allowed = {"NONE", "MIGRATION", "ROLLOUT", "MULTI_REPOSITORY", "EXTERNAL_STATE"}
    if not set(characteristics) <= allowed or ("NONE" in characteristics and len(characteristics) != 1):
        raise PlanPackageError("INVALID_CHARTER", "invalid change_characteristics")
    if (len(repositories) > 1) != ("MULTI_REPOSITORY" in characteristics):
        raise PlanPackageError("INVALID_CHARTER", "MULTI_REPOSITORY does not match repository count")
    normalized = dict(charter)
    normalized["allowed_repositories"] = normalized_repositories
    normalized["allowed_paths"] = normalized_paths
    return normalized


def validate_requirements(value: Any, *, direct: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise PlanPackageError("INVALID_REQUIREMENTS", "requirements must be a non-empty array")
    ids: set[str] = set()
    obligation_ids: set[str] = set()
    for requirement in value:
        require_exact(requirement, REQUIREMENT_FIELDS, "requirement")
        rid = require_string(requirement["id"], "requirement id")
        if rid in ids:
            raise PlanPackageError("INVALID_REQUIREMENTS", "duplicate requirement id")
        ids.add(rid)
        require_string(requirement["text"], "requirement text")
        sorted_unique_strings(requirement["evidence_ids"], "requirement evidence_ids")
        obligations = requirement["planner_obligations"]
        if not isinstance(obligations, list):
            raise PlanPackageError("INVALID_REQUIREMENTS", "planner_obligations must be an array")
        for obligation in obligations:
            require_exact(obligation, OBLIGATION_FIELDS, "planner obligation")
            oid = require_string(obligation["id"], "obligation id")
            if oid in obligation_ids:
                raise PlanPackageError("INVALID_REQUIREMENTS", "duplicate obligation id")
            obligation_ids.add(oid)
            if direct and obligation["status"] != "READY":
                raise PlanPackageError("RESEARCH_REQUIRED", "DIRECT obligations must be READY")
            if not obligation["implementation_anchors"] or not obligation["verification_anchors"]:
                raise PlanPackageError("RESEARCH_REQUIRED", "obligations require implementation and verification anchors")
    return value


def validate_evidence(value: Any, charter: dict[str, Any], requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise PlanPackageError("RESEARCH_REQUIRED", "DIRECT evidence index must be non-empty")
    requirement_ids = {item["id"] for item in requirements}
    coverage = {item: set() for item in requirement_ids}
    current_local = {item: False for item in requirement_ids}
    seen: set[str] = set()
    for item in value:
        require_exact(item, EVIDENCE_FIELDS, "evidence record")
        eid = require_string(item["id"], "evidence id")
        if eid in seen:
            raise PlanPackageError("INVALID_EVIDENCE", "duplicate evidence id")
        seen.add(eid)
        refs = sorted_unique_strings(item["requirement_ids"], "evidence requirement_ids", allow_empty=False)
        if not set(refs) <= requirement_ids:
            raise PlanPackageError("INVALID_EVIDENCE", "evidence references unknown requirement")
        facets = sorted_unique_strings(item["facets"], "evidence facets", allow_empty=False)
        if not set(facets) <= FACETS:
            raise PlanPackageError("INVALID_EVIDENCE", "unknown evidence facet")
        source = require_exact(item["source"], EVIDENCE_SOURCE_FIELDS, "evidence source")
        kind = source["kind"]
        if kind == "LOCAL_FILE":
            key = require_string(source["repository_key"], "repository_key")
            if key not in charter["allowed_repositories"]:
                raise PlanPackageError("INVALID_EVIDENCE", "LOCAL_FILE repository is not frozen")
            path = contained_file(Path(charter["allowed_repositories"][key]), source["path"], "LOCAL_FILE")
        elif kind == "SUPPLIED_INPUT":
            if source["repository_key"] is not None or charter["supplied_input_root"] is None:
                raise PlanPackageError("INVALID_EVIDENCE", "SUPPLIED_INPUT source has invalid authority")
            supplied = charter["supplied_input_root"]
            path = contained_file(Path(supplied["path"]), source["path"], "SUPPLIED_INPUT")
        else:
            raise PlanPackageError("RESEARCH_REQUIRED", "DIRECT accepts only LOCAL_FILE or SUPPLIED_INPUT")
        if bytes_hash(path.read_bytes()) != source["sha256"]:
            raise PlanPackageError("EVIDENCE_DRIFT", "evidence file hash mismatch")
        for rid in refs:
            coverage[rid].update(facets)
            current_local[rid] |= kind == "LOCAL_FILE" and "CURRENT_BEHAVIOR" in facets
    for rid in requirement_ids:
        if coverage[rid] != FACETS or not current_local[rid]:
            raise PlanPackageError("RESEARCH_REQUIRED", f"evidence facets are insufficient for {rid}")
    return value


def validate_state_shape(state: Any) -> dict[str, Any]:
    state = require_exact(state, STATE_FIELDS, "controller state")
    if state["schema_version"] != 1 or state["lens_contract_id"] != LENS_CONTRACT_ID:
        raise PlanPackageError("INVALID_STATE", "state identity is invalid")
    if not re.fullmatch(r"plan-package-[0-9a-f]{24}", str(state["package_id"])):
        raise PlanPackageError("INVALID_STATE", "package_id is invalid")
    for field in ("source_snapshots", "revision_history", "emission_history", "attempts", "stage_results", "findings", "dispositions", "finding_transitions", "blockers"):
        if not isinstance(state[field], list):
            raise PlanPackageError("INVALID_STATE", f"{field} must be an array")
    budgets = require_exact(
        state["budgets"],
        {
            "max_rounds",
            "max_agent_attempts",
            "used_agent_attempts",
            "max_elapsed_seconds",
            "reserved_later_stage_attempts",
            "verify_plan_iteration_limit",
            "continuation_approval_sha256",
        },
        "controller budgets",
    )
    if budgets["used_agent_attempts"] != len(state["attempts"]):
        raise PlanPackageError("STATE_TAMPER", "attempt budget does not match attempt records")
    sequences = [item.get("attempt_sequence") for item in state["attempts"] if isinstance(item, dict)]
    if sequences != list(range(1, len(state["attempts"]) + 1)):
        raise PlanPackageError("STATE_TAMPER", "attempt sequences must be contiguous and ordered")
    if len({item.get("attempt_id") for item in state["attempts"] if isinstance(item, dict)}) != len(state["attempts"]):
        raise PlanPackageError("STATE_TAMPER", "attempt IDs must be unique")
    cap_fields = (
        state["cap_reason"], state["cap_reached_at_utc"], state["cap_stage"],
        state["cap_completed_verification_iteration"],
    )
    if state["status"] == "CAP_REACHED":
        if any(value is None for value in cap_fields):
            raise PlanPackageError("INVALID_STATE", "CAP_REACHED requires complete cap metadata")
        if state["cap_reason"] not in {
            "VERIFY_PLAN_ITERATION_LIMIT", "AGENT_ATTEMPT_LIMIT", "ROUND_LIMIT",
            "DEADLINE_EXCEEDED", "REPEATED_FINDING_FINGERPRINT",
        } or state["cap_stage"] not in STAGES:
            raise PlanPackageError("INVALID_STATE", "cap reason or stage is invalid")
        parse_utc(state["cap_reached_at_utc"])
        if (
            isinstance(state["cap_completed_verification_iteration"], bool)
            or not isinstance(state["cap_completed_verification_iteration"], int)
            or state["cap_completed_verification_iteration"] < 0
        ):
            raise PlanPackageError("INVALID_STATE", "completed cap iteration must be non-negative")
    elif any(value is not None for value in cap_fields):
        raise PlanPackageError("INVALID_STATE", "cap metadata must be null outside CAP_REACHED")
    if budgets["used_agent_attempts"] > budgets["max_agent_attempts"]:
        raise PlanPackageError("STATE_TAMPER", "used attempts exceed the shared cap")
    if state["status"] not in {"INITIALIZED", "BLOCKED", "DRAFTED", "HARDENING", "GAPS", "CAP_REACHED", "READY", "EMITTED"}:
        raise PlanPackageError("INVALID_STATE", "controller status is invalid")
    if state["profile"] not in {"LIGHT", "SUBSTANTIAL"}:
        raise PlanPackageError("INVALID_STATE", "controller profile is invalid")
    if isinstance(state["revision"], bool) or not isinstance(state["revision"], int) or state["revision"] < 0:
        raise PlanPackageError("INVALID_STATE", "revision must be a non-negative integer")
    draft_hashes = [
        state["plan_sha256"], state["surface_map_sha256"], state["decisions_sha256"],
        state["verification_ledger_sha256"],
    ]
    if any(value is None for value in draft_hashes) and any(value is not None for value in draft_hashes):
        raise PlanPackageError("INVALID_STATE", "draft artifact hashes must be all null or all bound")
    for value in (item for item in draft_hashes if item is not None):
        if not isinstance(value, str) or not SHA_RE.fullmatch(value):
            raise PlanPackageError("INVALID_STATE", "draft artifact hash is invalid")
    requirements_bound = state["requirements"] is not None
    requirement_hashes = [state["requirements_sha256"], state["evidence_index_sha256"]]
    if requirements_bound != all(value is not None for value in requirement_hashes):
        raise PlanPackageError("INVALID_STATE", "requirements and evidence identity must be bound together")
    pre_draft = state["status"] == "INITIALIZED" or (
        state["status"] == "BLOCKED" and not requirements_bound
    )
    if pre_draft:
        if state["revision"] != 0 or any(value is not None for value in draft_hashes) or state["revision_history"]:
            raise PlanPackageError("INVALID_STATE", "pre-draft state cannot contain revision artifacts")
    elif state["status"] != "BLOCKED" or any(value is not None for value in draft_hashes):
        if state["revision"] < 1 or any(value is None for value in draft_hashes):
            raise PlanPackageError("INVALID_STATE", "post-draft state requires a complete revision identity")
    expected_revisions = list(range(1, state["revision"] + 1))
    actual_revisions: list[int] = []
    for row in state["revision_history"]:
        row = require_exact(row, REVISION_HISTORY_FIELDS, "revision history record")
        if not isinstance(row["revision"], int) or isinstance(row["revision"], bool):
            raise PlanPackageError("INVALID_STATE", "revision history number is invalid")
        require_string(row["receipt_path"], "revision receipt path")
        if not isinstance(row["receipt_sha256"], str) or not SHA_RE.fullmatch(row["receipt_sha256"]):
            raise PlanPackageError("INVALID_STATE", "revision receipt hash is invalid")
        actual_revisions.append(row["revision"])
    if actual_revisions != expected_revisions:
        raise PlanPackageError("INVALID_STATE", "revision history must be contiguous through the current revision")
    basis = {"schema_version": 1, "task_root": state["task_root"], "charter_sha256": state["charter_sha256"]}
    if state["package_id"] != "plan-package-" + canonical_hash(basis)[:24]:
        raise PlanPackageError("INVALID_STATE", "package_id derivation mismatch")
    return state


def load_state(path: Path, *, run_root_name: str = RUN_ROOT_NAME) -> tuple[dict[str, Any], Path, Path]:
    state = validate_state_shape(load_json(path, "controller state"))
    task_root = resolve_dir(Path(state["task_root"]), "frozen task root")
    run_root = resolve_dir(Path(state["run_root"]), "frozen run root")
    expected = run_root / "state.json"
    if path.resolve(strict=True) != expected or run_root != task_root / run_root_name:
        raise PlanPackageError("STATE_PATH_MISMATCH", "state path does not match frozen roots")
    if canonical_hash(state["charter"]) != state["charter_sha256"]:
        raise PlanPackageError("STATE_TAMPER", "charter hash mismatch")
    lens = contained_file(run_root, state["lens_contract_path"], "lens contract snapshot")
    if bytes_hash(lens.read_bytes()) != state["lens_contract_sha256"]:
        raise PlanPackageError("LENS_CONTRACT_TAMPER", "lens contract snapshot changed")
    source = SCRIPT.parents[1] / "references" / "hardening-lenses.md"
    if source.is_symlink() or not source.is_file() or source.read_bytes() != lens.read_bytes():
        raise PlanPackageError("LENS_CONTRACT_DRIFT", "candidate lens contract changed during run")
    snapshots = [validate_source_snapshot(run_root, item) for item in state["source_snapshots"]]
    if [item["repository_key"] for item in snapshots] != sorted(item["repository_key"] for item in snapshots):
        raise PlanPackageError("INVALID_STATE", "source snapshots must be ordered by repository key")
    if len({item["repository_key"] for item in snapshots}) != len(snapshots):
        raise PlanPackageError("INVALID_STATE", "source snapshot repository keys must be unique")
    predecessor = None
    for row in state["revision_history"]:
        receipt_path = contained_file(run_root, row["receipt_path"], "revision receipt")
        receipt = require_exact(load_json(receipt_path, "revision receipt"), REVISION_RECEIPT_FIELDS, "revision receipt")
        basis = {key: receipt[key] for key in REVISION_RECEIPT_FIELDS if key not in {"plan_snapshot_path", "revision_basis_sha256", "predecessor_receipt_sha256", "published_at_utc"}}
        if (
            receipt["schema_version"] != 1
            or receipt["package_id"] != state["package_id"]
            or receipt["revision"] != row["revision"]
            or receipt["revision_basis_sha256"] != canonical_hash(basis)
            or receipt["predecessor_receipt_sha256"] != predecessor
            or receipt_path.read_bytes() != canonical_bytes(receipt)
            or bytes_hash(receipt_path.read_bytes()) != row["receipt_sha256"]
            or row["receipt_path"] != f"revisions/{row['revision']}-{row['receipt_sha256']}.json"
            or receipt["plan_snapshot_path"] != f"snapshots/plan/{receipt['plan_sha256']}.md"
        ):
            raise PlanPackageError("STATE_TAMPER", "revision receipt chain is invalid")
        parse_utc(receipt["published_at_utc"])
        contained_file(run_root, receipt["plan_snapshot_path"], "revision plan snapshot")
        predecessor = row["receipt_sha256"]
    if state["revision_history"]:
        current_receipt = load_json(run_root / state["revision_history"][-1]["receipt_path"])
        current = (
            state["profile"], state["evidence_index_sha256"], state["plan_sha256"],
            state["surface_map_sha256"], state["decisions_sha256"], state["verification_ledger_sha256"],
        )
        bound = (
            current_receipt["profile"], current_receipt["evidence_index_sha256"], current_receipt["plan_sha256"],
            current_receipt["surface_map_sha256"], current_receipt["decisions_sha256"],
            current_receipt["verification_ledger_sha256"],
        )
        if current != bound:
            raise PlanPackageError("STATE_TAMPER", "current revision identity does not match its receipt")
    validate_convergence_entry(state, run_root)
    return state, task_root, run_root


def save_state(path: Path, state: dict[str, Any]) -> str:
    validate_state_shape(state)
    atomic_json(path, state)
    reopened = load_json(path, "controller state")
    if reopened != state:
        raise PlanPackageError("STATE_WRITE_FAILED", "state reopen mismatch")
    return canonical_hash(state)


def state_result(command: str, state: dict[str, Any], code: str) -> dict[str, Any]:
    return {"schema_version": 1, "command": command, "ok": True, "status": state["status"], "state_sha256": canonical_hash(state), "code": code}


def snapshot_json(run_root: Path, kind: str, value: Any) -> tuple[str, str]:
    payload = canonical_bytes(value)
    digest = bytes_hash(payload)
    relative = f"snapshots/{kind}/{digest}.json"
    publish_immutable(run_root / relative, payload)
    return relative, digest


def verification_ledger_snapshot_path(run_root: Path, digest: str) -> Path:
    portable = run_root / f"snapshots/verification-ledger/{digest}/verification-ledger.json"
    legacy = run_root / f"snapshots/verification-ledger/{digest}.json"
    return portable if portable.is_file() else legacy


def verification_ledger_snapshot_assets(path: Path) -> list[tuple[str, bytes]]:
    if path.name != "verification-ledger.json":
        return []
    return [
        (asset.relative_to(path.parent).as_posix(), asset.read_bytes())
        for asset in sorted(path.parent.rglob("*"), key=lambda item: item.as_posix())
        if asset.is_file() and asset != path
    ]


def snapshot_verification_ledger(run_root: Path, source: Path) -> tuple[str, str]:
    ledger = validate_ledger(source)
    payload = canonical_bytes(ledger)
    digest = bytes_hash(payload)
    snapshot_root = run_root / f"snapshots/verification-ledger/{digest}"
    referenced: list[tuple[Path, str]] = []
    target = ledger.get("target")
    if isinstance(target, str) and target:
        _, _, owner = shared_contracts()
        target_base = owner._repository_root(source.parent) or source.parent
        referenced.append((target_base, target))
    plan = ledger.get("plan_verification") or {}
    for inventory in plan.get("inventories", []):
        for section in inventory.get("plan_sections", []):
            referenced.append((source.parent, section["path"]))
        for collection in ("evidence_items", "dependencies"):
            for record in inventory.get(collection, []):
                referenced.append((source.parent, record["source_ref"]["path"]))
    for record in plan.get("critic_outputs", []):
        referenced.append((source.parent, record["snapshot_path"]))
    for base, relative in sorted(set(referenced), key=lambda item: item[1].encode("utf-8")):
        asset = contained_file(base, relative, "verification ledger asset")
        publish_immutable(snapshot_root / relative, asset.read_bytes())
    relative = f"snapshots/verification-ledger/{digest}/verification-ledger.json"
    publish_immutable(run_root / relative, payload)
    validate_ledger(run_root / relative)
    return relative, digest


def snapshot_bytes(run_root: Path, kind: str, payload: bytes, suffix: str) -> tuple[str, str]:
    digest = bytes_hash(payload)
    relative = f"snapshots/{kind}/{digest}.{suffix}"
    publish_immutable(run_root / relative, payload)
    return relative, digest


def revision_basis(
    state: dict[str, Any], revision: int, hashes: dict[str, str], *, profile: str | None = None
) -> dict[str, Any]:
    return {
        "schema_version": 1, "package_id": state["package_id"], "revision": revision,
        "profile": state["profile"] if profile is None else profile,
        "evidence_index_sha256": state["evidence_index_sha256"],
        "plan_sha256": hashes["plan"], "surface_map_sha256": hashes["surface-map"],
        "decisions_sha256": hashes["decisions"],
        "verification_ledger_sha256": hashes["verification-ledger"],
    }


def validate_revision_receipt(
    state: dict[str, Any], run_root: Path, revision: int, hashes: dict[str, str],
    plan_path: str, predecessor: str | None, candidate: Path, *, profile: str | None = None,
) -> dict[str, Any]:
    receipt = require_exact(load_json(candidate, "revision receipt"), REVISION_RECEIPT_FIELDS, "revision receipt")
    basis = revision_basis(state, revision, hashes, profile=profile)
    expected = {
        **basis,
        "plan_snapshot_path": plan_path,
        "revision_basis_sha256": canonical_hash(basis),
        "predecessor_receipt_sha256": predecessor,
    }
    if {key: receipt[key] for key in expected} != expected:
        raise PlanPackageError("REVISION_RECEIPT_CONFLICT", "revision receipt does not match the complete revision basis")
    parse_utc(receipt["published_at_utc"])
    payload = candidate.read_bytes()
    if payload != canonical_bytes(receipt):
        raise PlanPackageError("REVISION_RECEIPT_CONFLICT", "revision receipt bytes are not canonical")
    digest = bytes_hash(payload)
    relative = f"revisions/{revision}-{digest}.json"
    if candidate != run_root / relative:
        raise PlanPackageError("REVISION_RECEIPT_CONFLICT", "revision receipt path is not content addressed")
    return {"revision": revision, "receipt_path": relative, "receipt_sha256": digest}


def publish_revision(
    state: dict[str, Any], run_root: Path, revision: int, hashes: dict[str, str],
    plan_path: str, *, profile: str | None = None,
) -> dict[str, Any]:
    predecessor_rows = [
        row for row in state["revision_history"]
        if isinstance(row, dict) and row.get("revision") == revision - 1
    ]
    if revision == 1:
        predecessor = None
    elif len(predecessor_rows) == 1:
        predecessor = require_exact(
            predecessor_rows[0], REVISION_HISTORY_FIELDS, "revision history record"
        )["receipt_sha256"]
    else:
        raise PlanPackageError("INVALID_STATE", "revision predecessor is missing or duplicated")
    named = [row for row in state["revision_history"] if isinstance(row, dict) and row.get("revision") == revision]
    if named:
        if len(named) != 1:
            raise PlanPackageError("INVALID_STATE", "revision history contains duplicate revisions")
        row = require_exact(named[0], REVISION_HISTORY_FIELDS, "revision history record")
        candidate = contained_file(run_root, row["receipt_path"], "revision receipt")
        validated = validate_revision_receipt(
            state, run_root, revision, hashes, plan_path, predecessor if revision > 1 else None,
            candidate, profile=profile,
        )
        if validated != row:
            raise PlanPackageError("STATE_TAMPER", "revision history record does not match its receipt")
        return validated

    revisions = run_root / "revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    prefix = f"{revision}-"
    candidates = sorted(path for path in revisions.iterdir() if path.name.startswith(prefix) and path.name.endswith(".json"))
    if len(candidates) > 1:
        raise PlanPackageError("REVISION_RECEIPT_CONFLICT", "multiple revision receipt candidates exist")
    if candidates:
        candidate = candidates[0]
        if candidate.is_symlink() or not candidate.is_file():
            raise PlanPackageError("REVISION_RECEIPT_CONFLICT", "revision receipt candidate is not a regular file")
        return validate_revision_receipt(
            state, run_root, revision, hashes, plan_path, predecessor, candidate, profile=profile,
        )

    basis = revision_basis(state, revision, hashes, profile=profile)
    receipt = {
        **basis, "plan_snapshot_path": plan_path,
        "revision_basis_sha256": canonical_hash(basis),
        "predecessor_receipt_sha256": predecessor, "published_at_utc": now_utc(),
    }
    payload = canonical_bytes(receipt)
    digest = bytes_hash(payload)
    relative = f"revisions/{revision}-{digest}.json"
    publish_immutable(run_root / relative, payload)
    return validate_revision_receipt(
        state, run_root, revision, hashes, plan_path, predecessor,
        run_root / relative, profile=profile,
    )


def refresh_current_revision_receipt(
    state: dict[str, Any], run_root: Path, verification_ledger_sha256: str,
) -> dict[str, Any]:
    if not state["revision_history"] or state["revision_history"][-1]["revision"] != state["revision"]:
        raise PlanPackageError("INVALID_STATE", "current revision receipt is unavailable")
    predecessor = None
    if state["revision"] > 1:
        if len(state["revision_history"]) < 2:
            raise PlanPackageError("INVALID_STATE", "revision predecessor is unavailable")
        predecessor = state["revision_history"][-2]["receipt_sha256"]
    hashes = {
        "plan": state["plan_sha256"],
        "surface-map": state["surface_map_sha256"],
        "decisions": state["decisions_sha256"],
        "verification-ledger": verification_ledger_sha256,
    }
    basis = revision_basis(state, state["revision"], hashes)
    receipt = {
        **basis,
        "plan_snapshot_path": f"snapshots/plan/{state['plan_sha256']}.md",
        "revision_basis_sha256": canonical_hash(basis),
        "predecessor_receipt_sha256": predecessor,
        "published_at_utc": now_utc(),
    }
    payload = canonical_bytes(receipt)
    digest = bytes_hash(payload)
    relative = f"revisions/{state['revision']}-{digest}.json"
    publish_immutable(run_root / relative, payload)
    return validate_revision_receipt(
        state, run_root, state["revision"], hashes, receipt["plan_snapshot_path"],
        predecessor, run_root / relative,
    )


def validate_surface_map(value: Any, charter: dict[str, Any], requirements: list[dict[str, Any]]) -> dict[str, Any]:
    value = require_exact(
        value,
        {"schema_version", "items", "behavior_matrix", "implementation_approval"},
        "surface map",
    )
    if value["schema_version"] != 1 or not isinstance(value["items"], list) or not value["items"]:
        raise PlanPackageError("INVALID_SURFACE_MAP", "surface map is empty or unsupported")
    requirement_ids = {r["id"] for r in requirements}
    obligation_ids = {o["id"] for r in requirements for o in r["planner_obligations"]}
    covered_r: set[str] = set(); covered_o: set[str] = set()
    item_ids: set[str] = set(); planned_ids: set[str] = set()
    item_fields = {"id", "requirement_ids", "obligation_ids", "subsystem", "files", "entry_points", "contracts", "implementation_steps", "verification_steps", "risk", "evidence_ids", "status"}
    for item in value["items"]:
        require_exact(item, item_fields, "surface item")
        iid = require_string(item["id"], "surface item id")
        if iid in item_ids:
            raise PlanPackageError("INVALID_SURFACE_MAP", "duplicate surface item id")
        item_ids.add(iid)
        if not set(item["requirement_ids"]) <= requirement_ids or not set(item["obligation_ids"]) <= obligation_ids:
            raise PlanPackageError("INVALID_SURFACE_MAP", "surface item references unknown ID")
        if item["status"] == "PLANNED":
            if not item["implementation_steps"] or not item["verification_steps"] or not item["files"]:
                raise PlanPackageError("INVALID_SURFACE_MAP", "PLANNED item lacks anchors")
            planned_ids.add(iid)
            covered_r.update(item["requirement_ids"]); covered_o.update(item["obligation_ids"])
        elif item["status"] != "OUT_OF_SCOPE":
            raise PlanPackageError("INVALID_SURFACE_MAP", "invalid surface status")
        for file_ref in item["files"]:
            require_exact(file_ref, {"repository_key", "path"}, "surface file")
            if file_ref["repository_key"] not in charter["allowed_repositories"]:
                raise PlanPackageError("SCOPE_CHANGED", "surface file uses unknown repository")
    if covered_r != requirement_ids or covered_o != obligation_ids:
        raise PlanPackageError("INVALID_SURFACE_MAP", "surface map does not cover every requirement and obligation")
    validate_behavior_matrix(
        value["behavior_matrix"],
        planned_ids=planned_ids,
        requirement_ids=requirement_ids,
        obligation_ids=obligation_ids,
        evidence_ids={eid for requirement in requirements for eid in requirement["evidence_ids"]},
    )
    approval = require_exact(value["implementation_approval"], {"granular_changes", "practical_consequence", "estimated_cost"}, "implementation approval")
    if not isinstance(approval["granular_changes"], list) or not approval["granular_changes"]:
        raise PlanPackageError("INVALID_SURFACE_MAP", "granular_changes must be non-empty")
    require_exact(approval["practical_consequence"], {"before", "after"}, "practical consequence")
    require_string(approval["practical_consequence"]["before"], "before consequence")
    require_string(approval["practical_consequence"]["after"], "after consequence")
    require_exact(approval["estimated_cost"], {"implementation_effort", "verification_effort", "complexity", "note"}, "estimated cost")
    return value


def validate_behavior_matrix(
    value: Any,
    *,
    planned_ids: set[str],
    requirement_ids: set[str],
    obligation_ids: set[str],
    evidence_ids: set[str],
) -> dict[str, Any]:
    value = require_exact(
        value,
        {"input_states", "category_exclusions", "consumers", "cases"},
        "behavior matrix",
    )
    states = value["input_states"]
    exclusions = value["category_exclusions"]
    consumers = value["consumers"]
    cases = value["cases"]
    if not isinstance(states, list) or not states:
        raise PlanPackageError("INVALID_BEHAVIOR_MATRIX", "input_states must be non-empty")
    if not isinstance(exclusions, list) or not isinstance(consumers, list) or not consumers:
        raise PlanPackageError("INVALID_BEHAVIOR_MATRIX", "category_exclusions and consumers must be arrays")
    if not isinstance(cases, list) or not cases:
        raise PlanPackageError("INVALID_BEHAVIOR_MATRIX", "cases must be non-empty")

    state_ids: set[str] = set()
    present_categories: set[str] = set()
    for state in states:
        require_exact(
            state,
            {"id", "category", "description", "requirement_ids", "obligation_ids", "evidence_ids"},
            "behavior input state",
        )
        sid = require_string(state["id"], "behavior input state id")
        category = require_string(state["category"], "behavior input category")
        if sid in state_ids or category not in BEHAVIOR_INPUT_CATEGORIES:
            raise PlanPackageError("INVALID_BEHAVIOR_MATRIX", "duplicate state id or unknown input category")
        state_ids.add(sid); present_categories.add(category)
        require_string(state["description"], "behavior input description")
        refs_r = set(sorted_unique_strings(state["requirement_ids"], "behavior state requirement_ids", allow_empty=False))
        refs_o = set(sorted_unique_strings(state["obligation_ids"], "behavior state obligation_ids", allow_empty=False))
        refs_e = set(sorted_unique_strings(state["evidence_ids"], "behavior state evidence_ids", allow_empty=False))
        if not refs_r <= requirement_ids or not refs_o <= obligation_ids or not refs_e <= evidence_ids:
            raise PlanPackageError("INVALID_BEHAVIOR_MATRIX", "input state references unknown authority")

    excluded_categories: set[str] = set()
    for exclusion in exclusions:
        require_exact(exclusion, {"category", "reason", "evidence_ids"}, "behavior category exclusion")
        category = require_string(exclusion["category"], "excluded behavior category")
        refs_e = set(sorted_unique_strings(exclusion["evidence_ids"], "behavior exclusion evidence_ids", allow_empty=False))
        require_string(exclusion["reason"], "behavior exclusion reason")
        if category not in BEHAVIOR_INPUT_CATEGORIES or category in excluded_categories or not refs_e <= evidence_ids:
            raise PlanPackageError("INVALID_BEHAVIOR_MATRIX", "invalid category exclusion")
        excluded_categories.add(category)
    if present_categories & excluded_categories or present_categories | excluded_categories != BEHAVIOR_INPUT_CATEGORIES:
        raise PlanPackageError("INVALID_BEHAVIOR_MATRIX", "every input category requires exactly one disposition")

    consumer_ids: set[str] = set()
    covered_surfaces: set[str] = set()
    for consumer in consumers:
        require_exact(
            consumer,
            {"id", "kind", "description", "surface_item_ids"},
            "behavior consumer",
        )
        cid = require_string(consumer["id"], "behavior consumer id")
        kind = require_string(consumer["kind"], "behavior consumer kind")
        surface_refs = set(sorted_unique_strings(
            consumer["surface_item_ids"], "behavior consumer surface_item_ids", allow_empty=False,
        ))
        require_string(consumer["description"], "behavior consumer description")
        if cid in consumer_ids or kind not in BEHAVIOR_CONSUMER_KINDS or not surface_refs <= planned_ids:
            raise PlanPackageError("INVALID_BEHAVIOR_MATRIX", "invalid behavior consumer")
        consumer_ids.add(cid); covered_surfaces.update(surface_refs)
    if covered_surfaces != planned_ids:
        raise PlanPackageError("INVALID_BEHAVIOR_MATRIX", "behavior consumers do not cover every surface item")

    case_ids: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    for case in cases:
        require_exact(
            case,
            {"id", "input_state_id", "consumer_id", "expected_observable", "test_command", "test_assertion"},
            "behavior case",
        )
        case_id = require_string(case["id"], "behavior case id")
        pair = (
            require_string(case["input_state_id"], "behavior case input_state_id"),
            require_string(case["consumer_id"], "behavior case consumer_id"),
        )
        if case_id in case_ids or pair in pairs or pair[0] not in state_ids or pair[1] not in consumer_ids:
            raise PlanPackageError("INVALID_BEHAVIOR_MATRIX", "duplicate or unbound behavior case")
        case_ids.add(case_id); pairs.add(pair)
        require_string(case["expected_observable"], "behavior expected observable")
        require_string(case["test_command"], "behavior test command")
        require_string(case["test_assertion"], "behavior test assertion")
    expected_pairs = {(sid, cid) for sid in state_ids for cid in consumer_ids}
    if pairs != expected_pairs:
        raise PlanPackageError("INVALID_BEHAVIOR_MATRIX", "cases must cover every input-state and consumer pair exactly once")
    return value


def validate_decisions(value: Any, requirement_ids: set[str]) -> dict[str, Any]:
    value = require_exact(value, {"schema_version", "decisions"}, "decisions")
    if value["schema_version"] != 1 or not isinstance(value["decisions"], list):
        raise PlanPackageError("INVALID_DECISIONS", "decisions schema is invalid")
    fields = {"id", "requirement_ids", "question", "selected_decision", "rejected_alternatives", "evidence_ids", "status"}
    for item in value["decisions"]:
        require_exact(item, fields, "decision")
        if item["status"] != "LOCKED" or not item["selected_decision"]:
            raise PlanPackageError("UNRESOLVED_DECISION", "every decision must be LOCKED")
        if not set(item["requirement_ids"]) <= requirement_ids:
            raise PlanPackageError("INVALID_DECISIONS", "decision references unknown requirement")
    return value


def validate_ledger(path: Path, *, can_stop: bool = False) -> dict[str, Any]:
    _, _, owner = shared_contracts()
    data, errors = owner._load(path)
    if data is not None:
        errors.extend(owner._validate_common(data))
        plan_state = owner._validate_plan(data, path, errors) if data.get("kind") == "plan" else None
        if data.get("kind") != "plan":
            errors.append("verification ledger must have kind=plan")
        if can_stop and not errors:
            errors.extend(owner._can_stop_errors(data, plan_state))
    if errors or data is None:
        raise PlanPackageError("INVALID_VERIFICATION_LEDGER", "; ".join(errors))
    return data


def cmd_hash_json(args: argparse.Namespace) -> dict[str, Any]:
    value = load_json(Path(args.json_file))
    return {"schema_version": 1, "sha256": canonical_hash(value)}


def require_migratable_legacy_state(
    state: dict[str, Any], task_root: Path, run_root: Path
) -> None:
    if state["status"] in {"BLOCKED", "CAP_REACHED"}:
        raise PlanPackageError(
            "MIGRATION_STATE_HASH_BOUND",
            "blocked and continuation states must finish under the legacy controller before migration",
        )
    if any(attempt["status"] == "PREPARED" for attempt in state["attempts"]):
        raise PlanPackageError(
            "MIGRATION_WORK_IN_FLIGHT",
            "a prepared agent attempt must be finalized before migration",
        )
    proposals = run_root / "proposed-revisions"
    if proposals.exists() and any(proposals.iterdir()):
        raise PlanPackageError(
            "MIGRATION_WORK_IN_FLIGHT",
            "a prepared revision must be recorded or removed under the legacy controller before migration",
        )
    if (task_root / ".plan-package-transaction.json").exists():
        raise PlanPackageError(
            "MIGRATION_WORK_IN_FLIGHT",
            "the package emission transaction must finish before migration",
        )


def migration_journal(task_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "package_id": state["package_id"],
        "legacy_run_root": str(task_root / LEGACY_RUN_ROOT_NAME),
        "canonical_run_root": str(task_root / RUN_ROOT_NAME),
        "legacy_state_sha256": canonical_hash(state),
    }


def cmd_migrate_run_root(args: argparse.Namespace) -> dict[str, Any]:
    task_root = resolve_dir(Path(args.task_directory), "task directory")
    legacy_root = task_root / LEGACY_RUN_ROOT_NAME
    run_root = task_root / RUN_ROOT_NAME
    journal_path = task_root / MIGRATION_JOURNAL_NAME
    for candidate in (legacy_root, run_root, journal_path):
        if candidate.exists() and candidate.is_symlink():
            raise PlanPackageError("UNSAFE_PATH", "migration paths cannot be symlinks")
    if legacy_root.exists() and run_root.exists():
        raise PlanPackageError(
            "MIGRATION_CONFLICT", "legacy and canonical run roots both exist"
        )
    if run_root.exists():
        state, _, _ = load_state(run_root / "state.json")
        if journal_path.exists():
            journal_path.unlink()
            fsync_dir(task_root)
        return state_result("migrate-run-root", state, "ALREADY_MIGRATED")
    if not legacy_root.exists():
        raise PlanPackageError("LEGACY_RUN_NOT_FOUND", "legacy run root does not exist")

    legacy_state_path = legacy_root / "state.json"
    state, _, _ = load_state(
        legacy_state_path, run_root_name=LEGACY_RUN_ROOT_NAME
    )
    require_migratable_legacy_state(state, task_root, legacy_root)
    expected_journal = migration_journal(task_root, state)
    if journal_path.exists() and load_json(journal_path, "migration journal") != expected_journal:
        raise PlanPackageError(
            "MIGRATION_CONFLICT", "migration journal does not match the legacy state"
        )
    atomic_json(journal_path, expected_journal)

    moved = False
    try:
        os.replace(legacy_root, run_root)
        moved = True
        fsync_dir(task_root)
        state["run_root"] = str(run_root)
        atomic_json(run_root / "state.json", state)
        migrated, _, _ = load_state(run_root / "state.json")
        journal_path.unlink()
        fsync_dir(task_root)
        return state_result("migrate-run-root", migrated, "RUN_ROOT_MIGRATED")
    except Exception:
        if moved and run_root.exists() and not legacy_root.exists():
            rollback = load_json(run_root / "state.json", "migrated controller state")
            rollback["run_root"] = str(legacy_root)
            atomic_json(run_root / "state.json", rollback)
            os.replace(run_root, legacy_root)
            fsync_dir(task_root)
        if journal_path.exists():
            journal_path.unlink()
            fsync_dir(task_root)
        raise


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    task_root = resolve_dir(Path(args.task_directory), "task directory")
    run_root = task_root / RUN_ROOT_NAME
    if run_root.exists() and run_root.is_symlink():
        raise PlanPackageError("UNSAFE_PATH", "run root cannot be a symlink")
    run_root.mkdir(mode=0o700, exist_ok=True)
    fsync_dir(task_root)
    state_path = Path(args.state_json).absolute()
    if state_path != run_root / "state.json":
        raise PlanPackageError("STATE_PATH_MISMATCH", f"state path must equal <task>/{RUN_ROOT_NAME}/state.json")
    if state_path.exists():
        state, _, _ = load_state(state_path)
        return state_result("init", state, "ALREADY_INITIALIZED")
    charter = validate_charter(load_json(Path(args.charter), "charter"))
    tree, _, _ = shared_contracts()
    supplied = None
    if args.supplied_input_root:
        root = resolve_dir(Path(args.supplied_input_root), "supplied input root")
        supplied = {"path": str(root), "tree_sha256": tree.TREE_SHA256_V1(root)}
    if charter["supplied_input_root"] != supplied:
        raise PlanPackageError("INVALID_CHARTER", "charter supplied_input_root does not match controller authority")
    charter_rel, charter_hash = snapshot_json(run_root, "charter", charter)
    del charter_rel
    requirements = None; evidence = None
    if args.entry_mode == "DIRECT":
        if args.research_package or not args.requirements or not args.evidence_index:
            raise PlanPackageError("ENTRY_ARGUMENT_CONFLICT", "DIRECT requires requirements/evidence and forbids research package")
        requirements = validate_requirements(load_json(Path(args.requirements), "requirements"), direct=True)
        evidence = validate_evidence(load_json(Path(args.evidence_index), "evidence index"), charter, requirements)
    else:
        if args.requirements or args.evidence_index or args.supplied_input_root:
            raise PlanPackageError("ENTRY_ARGUMENT_CONFLICT", "RESEARCH_PACKAGE forbids standalone inputs")
        if args.research_package:
            try:
                package = research_owner().validate_package(args.research_package)
            except Exception as exc:
                raise PlanPackageError("INVALID_RESEARCH_PACKAGE", str(exc)) from exc
            requirements = validate_requirements(package["requirements"], direct=False)
            evidence = package["evidence_index"]
    if args.approval_context == "ORDINARY" and args.convergence_state:
        raise PlanPackageError("ENTRY_ARGUMENT_CONFLICT", "ORDINARY forbids convergence state")
    if args.approval_context == "CONVERGENCE" and (not args.convergence_state or requirements is None):
        raise PlanPackageError("ENTRY_ARGUMENT_CONFLICT", "CONVERGENCE requires outer state and bound requirements")
    requirements_hash = evidence_hash = None
    if requirements is not None:
        _, requirements_hash = snapshot_json(run_root, "requirements", requirements)
        _, evidence_hash = snapshot_json(run_root, "evidence-index", evidence)
    approval_path = approval_hash = None
    if args.approval_context == "CONVERGENCE":
        projection = convergence_projection(Path(args.convergence_state), charter, requirements)
        approval_target = run_root / "authorizations/convergence-entry.json"
        publish_immutable(approval_target, canonical_bytes(projection))
        approval_path = relative_under(run_root, approval_target, "convergence entry authorization")
        approval_hash = bytes_hash(approval_target.read_bytes())
    lens_source = SCRIPT.parents[1] / "references" / "hardening-lenses.md"
    if lens_source.is_symlink() or not lens_source.is_file():
        raise PlanPackageError("LENS_CONTRACT_UNAVAILABLE", "candidate hardening-lenses.md is unavailable")
    lens_bytes = lens_source.read_bytes()
    text = lens_bytes.decode("utf-8")
    if LENS_CONTRACT_ID not in text or any(role not in text for role in STAGES[1:]):
        raise PlanPackageError("INVALID_LENS_CONTRACT", "owned lens contract is incomplete")
    lens_hash = bytes_hash(lens_bytes)
    lens_rel = f"snapshots/hardening-lenses/{lens_hash}.md"
    publish_immutable(run_root / lens_rel, lens_bytes)
    started = now_utc()
    profile = "LIGHT" if args.task_size == "light" else "SUBSTANTIAL"
    seconds = 1200 if profile == "LIGHT" else 3600
    max_attempts = 10 if profile == "LIGHT" else 23
    max_rounds = 3
    package_id = "plan-package-" + canonical_hash({"schema_version": 1, "task_root": str(task_root), "charter_sha256": charter_hash})[:24]
    blockers = []
    status = "INITIALIZED"
    if requirements is None:
        status = "BLOCKED"
        blocker_id = "blocker-" + canonical_hash({"package_id": package_id, "entry_mode": args.entry_mode, "type": "EVIDENCE", "reason": "RESEARCH_REQUIRED"})[:24]
        blockers = [{"id": blocker_id, "type": "EVIDENCE", "practical_impact": "Planning cannot start without grounded research evidence.", "evidence": ["entry:RESEARCH_PACKAGE"], "required_resolution": "Provide one valid PASS research package.", "status": "OPEN", "resolution": None}]
    state = {
        "schema_version": 1, "package_id": package_id, "task_root": str(task_root),
        "run_root": str(run_root), "status": status, "revision": 0,
        "entry_mode": args.entry_mode, "approval_context": args.approval_context,
        "approval_authorization_path": approval_path, "approval_authorization_sha256": approval_hash,
        "implementation_approval_status": "NOT_REQUESTED",
        "implementation_authorization_request_path": None,
        "implementation_authorization_request_sha256": None,
        "implementation_authorization_path": None, "implementation_authorization_sha256": None,
        "profile": profile, "started_at_utc": started,
        "deadline_at_utc": (parse_utc(started) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
        "cap_reason": None, "cap_reached_at_utc": None, "cap_stage": None,
        "cap_completed_verification_iteration": None, "charter": charter,
        "charter_sha256": charter_hash, "requirements": requirements,
        "requirements_sha256": requirements_hash, "evidence_index_sha256": evidence_hash,
        "lens_contract_id": LENS_CONTRACT_ID, "lens_contract_path": lens_rel,
        "lens_contract_sha256": lens_hash, "supplied_input_root": supplied,
        "source_snapshots": [], "plan_sha256": None, "surface_map_sha256": None,
        "decisions_sha256": None, "verification_ledger_sha256": None,
        "budgets": {"max_rounds": max_rounds, "max_agent_attempts": max_attempts,
                    "used_agent_attempts": 0, "max_elapsed_seconds": seconds,
                    "reserved_later_stage_attempts": 3, "verify_plan_iteration_limit": 10,
                    "continuation_approval_sha256": None},
        "revision_history": [], "emission_history": [], "attempts": [],
        "stage_results": [], "findings": [], "dispositions": [],
        "finding_transitions": [], "blockers": blockers,
    }
    save_state(state_path, state)
    return state_result("init", state, "RESEARCH_REQUIRED" if status == "BLOCKED" else "INITIALIZED")


def cmd_scope_check(args: argparse.Namespace) -> dict[str, Any]:
    state, _, _ = load_state(Path(args.state_json))
    charter = validate_charter(load_json(Path(args.charter), "charter"))
    if canonical_hash(charter) != state["charter_sha256"]:
        raise PlanPackageError("SCOPE_CHANGED", "charter changed")
    return state_result("scope-check", state, "SCOPE_UNCHANGED")


def cmd_record_draft(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, _, run_root = load_state(path)
    if state["status"] not in {"INITIALIZED", "DRAFTED"}:
        raise PlanPackageError("INVALID_TRANSITION", "record-draft requires INITIALIZED")
    plan_bytes = Path(args.plan).read_bytes()
    try: plan_bytes.decode("utf-8")
    except UnicodeDecodeError as exc: raise PlanPackageError("INVALID_PLAN", "plan must be UTF-8") from exc
    surface = validate_surface_map(load_json(Path(args.surface_map)), state["charter"], state["requirements"])
    decisions = validate_decisions(load_json(Path(args.decisions)), {r["id"] for r in state["requirements"]})
    plan_rel, plan_hash = snapshot_bytes(run_root, "plan", plan_bytes, "md")
    _, surface_hash = snapshot_json(run_root, "surface-map", surface)
    _, decisions_hash = snapshot_json(run_root, "decisions", decisions)
    _, ledger_hash = snapshot_verification_ledger(run_root, Path(args.verification_ledger))
    effective_profile = state["profile"]
    if state["profile"] == "LIGHT":
        lines = plan_bytes.decode().splitlines(); units = sum(1 for line in lines if re.match(r"^ {0,3}#{1,6}\s", line))
        obligations = sum(len(r["planner_obligations"]) for r in state["requirements"])
        if len(lines) > 200 or units > 12 or len(state["requirements"]) != 1 or obligations > 3 or len(state["charter"]["allowed_repositories"]) != 1 or state["charter"]["change_characteristics"] != ["NONE"]:
            effective_profile = "SUBSTANTIAL"
    hashes = {"plan": plan_hash, "surface-map": surface_hash, "decisions": decisions_hash, "verification-ledger": ledger_hash}
    receipt = publish_revision(state, run_root, 1, hashes, plan_rel, profile=effective_profile)
    if state["status"] == "DRAFTED":
        expected_hashes = (
            state["plan_sha256"], state["surface_map_sha256"], state["decisions_sha256"],
            state["verification_ledger_sha256"],
        )
        if state["revision"] != 1 or expected_hashes != (plan_hash, surface_hash, decisions_hash, ledger_hash):
            raise PlanPackageError("REVISION_RECEIPT_CONFLICT", "record-draft replay artifacts changed")
        if state["profile"] != effective_profile or state["revision_history"] != [receipt]:
            raise PlanPackageError("REVISION_RECEIPT_CONFLICT", "record-draft replay state changed")
        return state_result("record-draft", state, "DRAFT_RECORDED")
    source_snapshots = [
        create_source_snapshot(run_root, key, Path(state["charter"]["allowed_repositories"][key]))
        for key in sorted(state["charter"]["allowed_repositories"])
    ]
    if effective_profile == "SUBSTANTIAL" and state["profile"] == "LIGHT":
        state["profile"] = "SUBSTANTIAL"
        state["budgets"].update(max_rounds=3, max_agent_attempts=23, max_elapsed_seconds=3600)
        state["deadline_at_utc"] = (parse_utc(state["started_at_utc"]) + timedelta(seconds=3600)).isoformat().replace("+00:00", "Z")
    state.update(status="DRAFTED", revision=1, plan_sha256=plan_hash, surface_map_sha256=surface_hash,
                 decisions_sha256=decisions_hash, verification_ledger_sha256=ledger_hash,
                 source_snapshots=source_snapshots)
    state["revision_history"] = [receipt]
    save_state(path, state)
    return state_result("record-draft", state, "DRAFT_RECORDED")


def slot_from_ledger(path: Path, slot_id: str) -> dict[str, Any]:
    data = load_json(path, "slot ledger")
    if data.get("version") != 2 or not isinstance(data.get("slots"), list):
        raise PlanPackageError("INVALID_SLOT_LEDGER", "slot ledger must use schema version 2")
    matches = [slot for slot in data["slots"] if slot.get("id") == slot_id]
    if len(matches) != 1:
        raise PlanPackageError("INVALID_SLOT_LEDGER", "slot id must match exactly once")
    return matches[0]


def completed_stage_iteration(state: dict[str, Any], stage: str) -> int:
    return max(
        (
            attempt["verification_iteration"]
            for attempt in state["attempts"]
            if ROLE_STAGE[attempt["role"]] == stage and attempt["status"] != "PREPARED"
        ),
        default=0,
    )


def enter_cap(path: Path, state: dict[str, Any], reason: str, stage: str) -> None:
    state.update(
        status="CAP_REACHED",
        cap_reason=reason,
        cap_reached_at_utc=now_utc(),
        cap_stage=stage,
        cap_completed_verification_iteration=completed_stage_iteration(state, stage),
    )
    save_state(path, state)
    raise PlanPackageError(reason, f"attempt preparation reached {reason}")


def expected_attempt_round(state: dict[str, Any]) -> int:
    current = [
        item["round"]
        for item in state["attempts"]
        if item["state_revision"] == state["revision"]
    ]
    if current:
        return max(current)
    history = [item["round"] for item in state["attempts"]]
    return max(history, default=0) + 1


def expected_attempt_role(state: dict[str, Any], round_number: int) -> str:
    stages = [item["stage"] for item in state["stage_results"] if item["round"] == round_number]
    if stages != list(STAGES[: len(stages)]):
        raise PlanPackageError("STATE_TAMPER", "stage results violate fixed order")
    if len(stages) >= len(STAGES):
        raise PlanPackageError("STAGE_ALREADY_COMPLETE", "the current hardening round is complete")
    stage = STAGES[len(stages)]
    if stage != "VERIFY_PLAN":
        return stage
    attempts = [
        item for item in state["attempts"]
        if item["state_revision"] == state["revision"]
        and item["round"] == round_number
        and item["role"].startswith("VERIFY_PLAN")
    ]
    if not attempts:
        return "VERIFY_PLAN_VERIFIER"
    latest = attempts[-1]
    same_key = [
        item for item in attempts
        if item["role"] == latest["role"]
        and item["verification_iteration"] == latest["verification_iteration"]
    ]
    retryable = {"SPAWN_FAILED", "BIND_FAILED", "OUTPUT_INVALID", "RUNTIME_FAILED", "TIMED_OUT"}
    if latest["status"] == "PREPARED":
        raise PlanPackageError("ATTEMPT_IN_PROGRESS", "the prior attempt must finalize before another is prepared")
    if latest["status"] in retryable and len(same_key) == 1:
        return latest["role"]
    if latest["status"] in retryable:
        raise PlanPackageError("RETRY_LIMIT", "one retry per logical role attempt is allowed")
    if latest["status"] != "SUCCEEDED":
        raise PlanPackageError("ATTEMPT_NOT_RETRYABLE", "the prior terminal status requires another lifecycle command")
    if latest["role"] == "VERIFY_PLAN_VERIFIER":
        return "VERIFY_PLAN_CRITIC"
    return "VERIFY_PLAN_VERIFIER"


def validate_attempt_policy(path: Path, state: dict[str, Any], args: argparse.Namespace) -> None:
    stage = ROLE_STAGE[args.role]
    expected_round = expected_attempt_round(state)
    if args.round > state["budgets"]["max_rounds"] or args.round != expected_round:
        if args.round > state["budgets"]["max_rounds"]:
            enter_cap(path, state, "ROUND_LIMIT", stage)
        raise PlanPackageError("ROUND_ORDER_VIOLATION", f"next attempt must use round {expected_round}")
    if any(item["status"] == "PREPARED" for item in state["attempts"]):
        raise PlanPackageError("ATTEMPT_IN_PROGRESS", "only one prepared attempt may exist")
    expected_role = expected_attempt_role(state, args.round)
    if args.role != expected_role:
        raise PlanPackageError("ROLE_ORDER_VIOLATION", f"next role must be {expected_role}")
    if args.role.startswith("VERIFY_PLAN"):
        if args.verification_iteration > state["budgets"]["verify_plan_iteration_limit"]:
            enter_cap(path, state, "VERIFY_PLAN_ITERATION_LIMIT", stage)
        prior = [
            item for item in state["attempts"]
            if item["state_revision"] == state["revision"]
            and item["round"] == args.round
            and item["role"] == args.role
            and item["verification_iteration"] == args.verification_iteration
        ]
        if len(prior) > 1 or any(item["status"] == "SUCCEEDED" for item in prior):
            raise PlanPackageError("RETRY_LIMIT", "logical role attempt is already complete")
        if prior and (
            prior[0]["assigned_coverage_ids"] != sorted(args.assigned_coverage_id or [])
            or prior[0]["assigned_obligation_ids"] != sorted(args.assigned_obligation_id or [])
        ):
            raise PlanPackageError("RETRY_BINDING_MISMATCH", "retry assignment differs from the first attempt")
        if args.role == "VERIFY_PLAN_CRITIC":
            verifiers = [
                item for item in state["attempts"]
                if item["state_revision"] == state["revision"]
                and item["round"] == args.round
                and item["role"] == "VERIFY_PLAN_VERIFIER"
                and item["verification_iteration"] == args.verification_iteration
                and item["status"] == "SUCCEEDED"
            ]
            if len(verifiers) != 1:
                raise PlanPackageError("ROLE_ORDER_VIOLATION", "critic requires one successful paired verifier")
        elif prior == []:
            completed_critics = [
                item["verification_iteration"]
                for item in state["attempts"]
                if item["role"] == "VERIFY_PLAN_CRITIC"
                and item["status"] == "SUCCEEDED"
            ]
            expected_iteration = max(completed_critics, default=0) + 1
            if args.verification_iteration != expected_iteration:
                raise PlanPackageError("ITERATION_ORDER_VIOLATION", f"next verifier iteration must be {expected_iteration}")
    elif args.verification_iteration != 1:
        raise PlanPackageError("ITERATION_ORDER_VIOLATION", "owned lens verification iteration must be 1")
    remaining_before = state["budgets"]["max_agent_attempts"] - state["budgets"]["used_agent_attempts"]
    stage_index = STAGES.index(stage)
    reserved_after = len(STAGES) - stage_index - 1
    if stage == "VERIFY_PLAN":
        reserved_after = state["budgets"]["reserved_later_stage_attempts"]
    if remaining_before <= reserved_after:
        enter_cap(path, state, "AGENT_ATTEMPT_LIMIT", stage)


def cmd_prepare_attempt(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, _, run_root = load_state(path)
    if state["status"] not in {"DRAFTED", "HARDENING"}:
        raise PlanPackageError("INVALID_TRANSITION", "prepare-attempt requires DRAFTED or HARDENING")
    if args.role not in ROLES or args.round < 1:
        raise PlanPackageError("INVALID_ATTEMPT", "invalid role or round")
    if parse_utc(now_utc()) > parse_utc(state["deadline_at_utc"]):
        enter_cap(path, state, "DEADLINE_EXCEEDED", ROLE_STAGE[args.role])
    validate_attempt_policy(path, state, args)
    slot = slot_from_ledger(Path(args.slot_ledger), args.slot_id)
    if slot.get("state") != "reserved" or slot.get("agent_id") is not None:
        raise PlanPackageError("INVALID_SLOT", "prepare requires an unbound reserved slot")
    envelope = require_exact(load_json(Path(args.input_envelope), "role input"), INPUT_FIELDS, "role input")
    if envelope["role"] != args.role or envelope["round"] != args.round or envelope["verification_iteration"] != args.verification_iteration:
        raise PlanPackageError("INPUT_BINDING_MISMATCH", "role input does not match command")
    coverage = sorted_unique_strings(args.assigned_coverage_id or [], "assigned coverage IDs")
    obligations = sorted_unique_strings(args.assigned_obligation_id or [], "assigned obligation IDs")
    if envelope["assigned_coverage_ids"] != coverage or envelope["assigned_obligation_ids"] != obligations:
        raise PlanPackageError("INPUT_BINDING_MISMATCH", "assignment mismatch")
    if args.role.startswith("VERIFY_PLAN") and not obligations:
        raise PlanPackageError("INVALID_ASSIGNMENT", "verify-plan attempt requires obligations")
    if not args.role.startswith("VERIFY_PLAN") and (coverage or obligations):
        raise PlanPackageError("INVALID_ASSIGNMENT", "owned lens attempts have empty assignments")
    authoritative_roots = []
    for item in state["source_snapshots"]:
        validated = dict(validate_source_snapshot(run_root, item))
        validated.pop("created_at_utc")
        authoritative_roots.append(validated)
    if envelope["authoritative_roots"] != authoritative_roots:
        raise PlanPackageError("INPUT_BINDING_MISMATCH", "authoritative roots do not match controller snapshots")
    sequence = len(state["attempts"]) + 1
    input_payload = canonical_bytes(envelope); input_hash = bytes_hash(input_payload)
    attempt_id = canonical_hash({"package_id": state["package_id"], "revision": state["revision"], "attempt_sequence": sequence, "role": args.role, "slot_id": args.slot_id, "input_envelope_sha256": input_hash})
    input_rel = f"attempts/{attempt_id}/input.json"; publish_immutable(run_root / input_rel, input_payload)
    lens_id = None if args.role.startswith("VERIFY_PLAN") else state["lens_contract_id"]
    lens_hash = None if args.role.startswith("VERIFY_PLAN") else state["lens_contract_sha256"]
    attempt = {"attempt_id": attempt_id, "attempt_sequence": sequence, "state_revision": state["revision"], "round": args.round, "role": args.role, "verification_iteration": args.verification_iteration, "assigned_coverage_ids": coverage, "assigned_obligation_ids": obligations, "lens_contract_id": lens_id, "lens_contract_sha256": lens_hash, "slot_id": args.slot_id, "input_envelope_sha256": input_hash, "status": "PREPARED", "runtime_agent_id": None, "output_path": None, "output_sha256": None, "close_evidence": None, "close_evidence_sha256": None, "prepared_at_utc": now_utc(), "finalized_at_utc": None}
    require_exact(attempt, ATTEMPT_FIELDS, "attempt")
    state["attempts"].append(attempt); state["budgets"]["used_agent_attempts"] += 1; state["status"] = "HARDENING"
    save_state(path, state)
    token = {"schema_version": 1, "attempt_id": attempt_id, "state_revision": state["revision"], "slot_id": args.slot_id, "input_envelope_sha256": input_hash}
    atomic_json(Path(args.out), token)
    return state_result("prepare-attempt", state, "ATTEMPT_PREPARED")


def find_attempt(state: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    matches = [item for item in state["attempts"] if item["attempt_id"] == attempt_id]
    if len(matches) != 1: raise PlanPackageError("UNKNOWN_ATTEMPT", "attempt not found")
    return matches[0]


def require_positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PlanPackageError("INVALID_ROLE_OUTPUT", f"{label} must be a positive integer")
    return value


def require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", f"{label} must be SHA-256")
    return value


def require_nonempty_string_array(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", f"{label} must be a non-empty string array")
    return value


def validate_finding(finding: Any, attempt: dict[str, Any]) -> dict[str, Any]:
    finding = require_exact(finding, FINDING_FIELDS, "role-output finding")
    require_string(finding["id"], "finding id")
    require_hash(finding["fingerprint"], "finding fingerprint")
    if finding["round"] != attempt["round"] or finding["stage"] != ROLE_STAGE[attempt["role"]] or finding["source_role"] != attempt["role"]:
        raise PlanPackageError("OUTPUT_BINDING_MISMATCH", "finding does not bind the attempt role, round, and stage")
    requirement_ids = sorted_unique_strings(finding["requirement_ids"], "finding requirement IDs")
    obligation_ids = sorted_unique_strings(finding["obligation_ids"], "finding obligation IDs")
    coverage_ids = sorted_unique_strings(finding["coverage_ids"], "finding coverage IDs")
    require_string(finding["practical_consequence"], "finding practical consequence")
    if finding["source_classification"] not in {"ACTIONABLE", "NON_ACTIONABLE"}:
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "finding source classification is invalid")
    evidence = finding["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "finding evidence must be non-empty")
    for item in evidence:
        if not isinstance(item, dict):
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "finding evidence must contain objects")
        if item.get("kind") == "SOURCE":
            require_exact(item, {"kind", "repository_key", "path", "line", "claim"}, "SOURCE evidence")
            require_string(item["repository_key"], "SOURCE repository key")
            require_string(item["path"], "SOURCE path")
            require_positive_int(item["line"], "SOURCE line")
            require_string(item["claim"], "SOURCE claim")
        elif item.get("kind") == "OBSERVED":
            require_exact(item, {"kind", "evidence_type", "source", "observation", "observation_sha256", "claim"}, "OBSERVED evidence")
            if item["evidence_type"] not in {"COMMAND_RESULT", "QUERY_OUTPUT", "LIVE_DATA", "STORED_DATA"}:
                raise PlanPackageError("INVALID_ROLE_OUTPUT", "observed evidence type is invalid")
            require_string(item["source"], "OBSERVED source")
            observation = require_string(item["observation"], "OBSERVED observation")
            if item["observation_sha256"] != bytes_hash(observation.encode("utf-8")):
                raise PlanPackageError("INVALID_ROLE_OUTPUT", "observed evidence hash mismatch")
            require_string(item["claim"], "OBSERVED claim")
        else:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "finding evidence kind is invalid")
    if evidence != sorted(evidence, key=canonical_bytes):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "finding evidence must be canonically sorted")
    fingerprint_basis = {
        "stage": finding["stage"], "requirement_ids": requirement_ids,
        "obligation_ids": obligation_ids, "coverage_ids": coverage_ids,
        "practical_consequence": finding["practical_consequence"], "evidence": evidence,
    }
    if finding["fingerprint"] != canonical_hash(fingerprint_basis):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "finding fingerprint mismatch")
    return finding


def validate_dispositions(value: Any, findings: list[dict[str, Any]], attempt: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(findings):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "one disposition is required per finding")
    finding_map = {finding["id"]: finding for finding in findings}
    if len(finding_map) != len(findings):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "finding IDs must be unique")
    seen: set[str] = set()
    for disposition in value:
        disposition = require_exact(disposition, DISPOSITION_FIELDS, "role-output disposition")
        finding = finding_map.get(disposition["finding_id"])
        if finding is None or disposition["finding_id"] in seen or disposition["finding_fingerprint"] != finding["fingerprint"]:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "disposition does not uniquely bind a finding")
        seen.add(disposition["finding_id"])
        if disposition["decision"] not in {"FIX NOW", "IMPLEMENT LATER", "ACKNOWLEDGE", "DISMISS"}:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "disposition decision is invalid")
        require_string(disposition["rationale"], "disposition rationale")
        require_string(disposition["parent_action"], "disposition parent action")
        classification = disposition["new_finding_classification"]
        if attempt["role"] != "VERIFY_PLAN_CRITIC" or attempt["verification_iteration"] == 1:
            if classification is not None:
                raise PlanPackageError("INVALID_ROLE_OUTPUT", "new-finding classification must be null")
        elif classification is not None and classification not in {"MISSED IN FIRST PASS", "INTRODUCED BY FIX", "NEWLY REVEALED", "COVERAGE QUEUE", "SCOPE DRIFT"}:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "new-finding classification is invalid")
    return value


def validate_obligation_assessments(value: Any, attempt: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "obligation assessments must be an array")
    if attempt["role"] not in {"VERIFY_PLAN_VERIFIER", "VERIFY_PLAN_CRITIC"}:
        if value:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "owned lenses require empty obligation assessments")
        return value
    if [item.get("obligation_id") for item in value if isinstance(item, dict)] != attempt["assigned_obligation_ids"]:
        raise PlanPackageError("OUTPUT_BINDING_MISMATCH", "obligation assessments must exactly match the assignment")
    for assessment in value:
        assessment = require_exact(assessment, OBLIGATION_ASSESSMENT_FIELDS, "obligation assessment")
        if assessment["iteration"] != attempt["verification_iteration"]:
            raise PlanPackageError("OUTPUT_BINDING_MISMATCH", "obligation assessment iteration mismatch")
        require_hash(assessment["binding_sha256"], "obligation binding hash")
        if assessment["status"] not in {"SUPPORTED", "GAP", "BLOCKED"}:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "obligation assessment status is invalid")
        evidence = assessment["evidence"]
        if not isinstance(evidence, list) or not evidence:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "obligation assessment evidence must be non-empty")
        for item in evidence:
            item = require_exact(item, {"registry_kind", "id", "claim"}, "obligation assessment evidence")
            if item["registry_kind"] not in {"PLAN_SECTION", "EVIDENCE", "DEPENDENCY"}:
                raise PlanPackageError("INVALID_ROLE_OUTPUT", "obligation evidence registry kind is invalid")
            require_string(item["id"], "obligation evidence ID")
            require_string(item["claim"], "obligation evidence claim")
        if evidence != sorted(evidence, key=lambda item: (item["registry_kind"], item["id"], item["claim"])):
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "obligation evidence must be sorted")
        snapshots = assessment["finding_snapshots"]
        if not isinstance(snapshots, list):
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "finding snapshots must be an array")
        snapshot_fields = {"id", "fingerprint", "classification", "obligation_ids", "iteration_first_seen"}
        for snapshot in snapshots:
            snapshot = require_exact(snapshot, snapshot_fields, "finding snapshot")
            require_string(snapshot["id"], "finding snapshot ID")
            require_hash(snapshot["fingerprint"], "finding snapshot fingerprint")
            require_string(snapshot["classification"], "finding snapshot classification")
            sorted_unique_strings(snapshot["obligation_ids"], "finding snapshot obligation IDs", allow_empty=False)
            require_positive_int(snapshot["iteration_first_seen"], "finding snapshot first iteration")
        boundary = assessment["blocked_boundary"]
        if assessment["status"] == "BLOCKED":
            boundary = require_exact(boundary, {"type", "binding_kind", "binding_id", "observed_content_sha256", "required_change"}, "blocked boundary")
            if boundary["type"] not in {"EVIDENCE", "RUNTIME", "APPROVAL"} or boundary["binding_kind"] not in {"EVIDENCE", "DEPENDENCY"}:
                raise PlanPackageError("INVALID_ROLE_OUTPUT", "blocked boundary kind is invalid")
            require_string(boundary["binding_id"], "blocked boundary ID")
            require_hash(boundary["observed_content_sha256"], "blocked boundary observed hash")
            require_string(boundary["required_change"], "blocked boundary required change")
        elif boundary is not None:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "only BLOCKED assessments may name a blocked boundary")
        if assessment["status"] == "SUPPORTED" and snapshots:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "SUPPORTED assessment forbids finding snapshots")
        if assessment["status"] == "GAP" and not snapshots:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "GAP assessment requires finding snapshots")
        projection = {key: assessment[key] for key in OBLIGATION_ASSESSMENT_FIELDS - {"assessment_fingerprint"}}
        if assessment["assessment_fingerprint"] != canonical_hash(projection):
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "obligation assessment fingerprint mismatch")
    return value


def validate_approval(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    approval = require_exact(value, fields, label)
    for field in fields & {"inventory_sha256", "plan_sha256", "evidence_revision_sha256", "binding_sha256", "assessment_fingerprint"}:
        require_hash(approval[field], f"{label} {field}")
    if "decision" in fields and approval["decision"] not in {"APPROVED", "REJECTED"}:
        raise PlanPackageError("INVALID_ROLE_OUTPUT", f"{label} decision is invalid")
    require_string(approval["rationale"], f"{label} rationale")
    require_nonempty_string_array(approval["evidence"], f"{label} evidence")
    return approval


def validate_artifact_transfer(value: Any, state: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    transfer = require_exact(value, ARTIFACT_TRANSFER_FIELDS, "artifact transfer")
    text = require_string(transfer["content_markdown"], "artifact Markdown")
    if transfer["sha256"] != bytes_hash(text.encode("utf-8")):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "artifact Markdown hash mismatch")
    expected_file = state["profile"] == "SUBSTANTIAL" and attempt["role"] in {"INTERNAL_READINESS", "REQUIREMENTS_COVERAGE", "REQUIREMENTS_SATISFACTION"}
    targets = {"INTERNAL_READINESS": "plan.gap-audit.md", "REQUIREMENTS_COVERAGE": "plan.coverage-audit.md", "REQUIREMENTS_SATISFACTION": "plan.satisfaction-audit.md"}
    if expected_file:
        if transfer["form"] != "FILE" or transfer["target_path"] != targets[attempt["role"]]:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "SUBSTANTIAL owned lens requires its fixed FILE artifact")
    elif transfer["form"] != "INLINE" or transfer["target_path"] is not None:
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "role requires an INLINE artifact with null target path")
    return transfer


def assigned_requirement_ids(state: dict[str, Any], attempt: dict[str, Any]) -> list[str]:
    if not attempt["assigned_obligation_ids"]:
        return sorted(requirement["id"] for requirement in state["requirements"])
    assigned = set(attempt["assigned_obligation_ids"])
    return sorted(requirement["id"] for requirement in state["requirements"] if any(obligation["id"] in assigned for obligation in requirement["planner_obligations"]))


def validate_terminal_envelope(value: Any, state: dict[str, Any], attempt: dict[str, Any], findings: list[dict[str, Any]], dispositions: list[dict[str, Any]], assessments: list[dict[str, Any]], transfer: dict[str, Any]) -> dict[str, Any]:
    envelope = require_exact(value, TERMINAL_ENVELOPE_FIELDS, "terminal envelope")
    if envelope["stage"] != STAGE_NAMES[ROLE_STAGE[attempt["role"]]] or envelope["iteration"] != attempt["round"] or envelope["attempt"] != attempt["verification_iteration"]:
        raise PlanPackageError("OUTPUT_BINDING_MISMATCH", "terminal envelope stage, iteration, or attempt mismatch")
    expected_requirements = assigned_requirement_ids(state, attempt)
    if envelope["assigned_requirement_ids"] != expected_requirements:
        raise PlanPackageError("OUTPUT_BINDING_MISMATCH", "terminal envelope requirement assignment mismatch")
    for field in ("assigned_gap_ids", "owned_blocker_ids", "open_gap_ids", "closed_gap_ids", "artifact_paths"):
        sorted_unique_strings(envelope[field], f"terminal envelope {field}")
    actionable = [finding for finding in findings if next(disposition for disposition in dispositions if disposition["finding_id"] == finding["id"])["decision"] in {"FIX NOW", "IMPLEMENT LATER"}]
    expected_verdict = "BLOCKED" if any(assessment["status"] == "BLOCKED" for assessment in assessments) or envelope["new_blockers"] else "GAPS" if actionable or any(assessment["status"] == "GAP" for assessment in assessments) else "PASS"
    if envelope["verdict"] != expected_verdict or envelope["verdict"] not in {"PASS", "GAPS", "BLOCKED"}:
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "terminal verdict disagrees with validated assessments, findings, or blockers")
    if envelope["new_gaps"] != actionable or envelope["open_gap_ids"] != sorted(finding["id"] for finding in actionable):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "terminal gap projection disagrees with actionable dispositions")
    blocker_fields = {"id", "type", "practical_impact", "evidence", "required_resolution"}
    for blocker in envelope["new_blockers"]:
        blocker = require_exact(blocker, blocker_fields, "terminal blocker")
        require_string(blocker["id"], "terminal blocker ID")
        if blocker["type"] not in {"EVIDENCE", "RUNTIME", "APPROVAL"}:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "terminal blocker type is invalid")
        require_string(blocker["practical_impact"], "terminal blocker impact")
        require_nonempty_string_array(blocker["evidence"], "terminal blocker evidence")
        require_string(blocker["required_resolution"], "terminal blocker resolution")
    if envelope["owned_blocker_ids"] != sorted(blocker["id"] for blocker in envelope["new_blockers"]):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "terminal blocker ownership does not match new blockers")
    if expected_verdict == "BLOCKED" and not envelope["new_blockers"]:
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "BLOCKED terminal envelope requires a concrete blocker")
    transition_fields = {"kind", "id", "from_status", "to_status", "evidence"}
    for transition in envelope["record_transitions"]:
        transition = require_exact(transition, transition_fields, "terminal transition")
        for field in transition_fields:
            require_string(transition[field], f"terminal transition {field}")
    require_nonempty_string_array(envelope["evidence"], "terminal evidence")
    expected_artifact_paths = [] if transfer["form"] == "INLINE" else [transfer["target_path"]]
    if envelope["artifact_paths"] != expected_artifact_paths:
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "terminal artifact paths disagree with artifact transfer")
    if envelope["verdict"] == "PASS" and any(envelope[field] for field in ("open_gap_ids", "new_gaps", "new_blockers", "owned_blocker_ids")):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "PASS terminal envelope contains open work")
    return envelope


def validate_role_output(output: Any, state: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    output = require_exact(output, RAW_OUTPUT_FIELDS, "role output")
    expected_bindings = {
        "schema_version": SCHEMA_VERSION, "attempt_id": attempt["attempt_id"],
        "input_envelope_sha256": attempt["input_envelope_sha256"], "role": attempt["role"],
        "round": attempt["round"], "verification_iteration": attempt["verification_iteration"],
        "assigned_coverage_ids": attempt["assigned_coverage_ids"],
        "assigned_obligation_ids": attempt["assigned_obligation_ids"],
        "lens_contract_id": attempt["lens_contract_id"],
        "lens_contract_sha256": attempt["lens_contract_sha256"],
        "assessed_plan_sha256": state["plan_sha256"],
    }
    if any(output[field] != expected for field, expected in expected_bindings.items()):
        raise PlanPackageError("OUTPUT_BINDING_MISMATCH", "role output does not bind the prepared attempt")
    parse_utc(output["completed_at_utc"])
    paired_verifier_output = None
    evidence_attempt = attempt
    if attempt["role"] == "VERIFY_PLAN_CRITIC":
        verifiers = [item for item in state["attempts"] if item["attempt_sequence"] < attempt["attempt_sequence"] and item["role"] == "VERIFY_PLAN_VERIFIER" and item["round"] == attempt["round"] and item["verification_iteration"] == attempt["verification_iteration"] and item["assigned_coverage_ids"] == attempt["assigned_coverage_ids"] and item["assigned_obligation_ids"] == attempt["assigned_obligation_ids"] and item["status"] == "SUCCEEDED"]
        if len(verifiers) != 1 or not verifiers[0]["output_path"]:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "critic requires one paired successful verifier")
        verifier_path = contained_file(Path(state["run_root"]), verifiers[0]["output_path"], "paired verifier output")
        if bytes_hash(verifier_path.read_bytes()) != verifiers[0]["output_sha256"]:
            raise PlanPackageError("OUTPUT_TAMPER", "paired verifier output changed")
        paired_verifier_output = load_json(verifier_path, "paired verifier output")
        evidence_attempt = verifiers[0]
    raw_findings = output["findings"]
    if not isinstance(raw_findings, list):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "findings must be an array")
    if attempt["role"] == "VERIFY_PLAN_CRITIC":
        verifier_findings = {
            finding["id"]: finding for finding in paired_verifier_output.get("findings", [])
        }
        findings = []
        seen_verifier_findings: set[str] = set()
        for finding in raw_findings:
            verifier_finding = verifier_findings.get(finding.get("id")) if isinstance(finding, dict) else None
            if verifier_finding is not None:
                if finding != verifier_finding:
                    raise PlanPackageError("INVALID_ROLE_OUTPUT", "critic changed a paired verifier finding")
                findings.append(validate_finding(finding, evidence_attempt))
                seen_verifier_findings.add(finding["id"])
            else:
                findings.append(validate_finding(finding, attempt))
        if seen_verifier_findings != set(verifier_findings):
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "critic omitted a paired verifier finding")
    else:
        findings = [validate_finding(finding, evidence_attempt) for finding in raw_findings]
    if [finding["id"] for finding in findings] != sorted({finding["id"] for finding in findings}):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "findings must be sorted by unique ID")
    assessments = validate_obligation_assessments(output["obligation_assessments"], evidence_attempt)
    finding_map = {finding["id"]: finding for finding in findings}
    snapshot_ids: set[str] = set()
    for assessment in assessments:
        for snapshot in assessment["finding_snapshots"]:
            finding = finding_map.get(snapshot["id"])
            if finding is None or finding["fingerprint"] != snapshot["fingerprint"] or assessment["obligation_id"] not in finding["obligation_ids"]:
                raise PlanPackageError("INVALID_ROLE_OUTPUT", "obligation finding snapshot does not bind a raw finding")
            if finding["source_classification"] != "ACTIONABLE":
                raise PlanPackageError("INVALID_ROLE_OUTPUT", "obligation finding snapshot must name an actionable finding")
            snapshot_ids.add(snapshot["id"])
    actionable_ids = {finding["id"] for finding in findings if finding["source_classification"] == "ACTIONABLE"}
    if attempt["role"] == "VERIFY_PLAN_VERIFIER" and snapshot_ids != actionable_ids:
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "verify-plan actionable findings must exactly match assessment snapshots")
    transfer = validate_artifact_transfer(output["artifact_transfer"], state, attempt)
    if attempt["role"] == "VERIFY_PLAN_VERIFIER":
        if output["terminal_envelope"] is not None or output["dispositions"] is not None or any(output[field] is not None for field in ("inventory_approval", "assessment_approvals", "coverage_exclusion_approvals")):
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "verifier forbids terminal, disposition, and approval claims")
        return output
    dispositions = validate_dispositions(output["dispositions"], findings, attempt)
    if attempt["role"] == "VERIFY_PLAN_CRITIC":
        critic_actionable_ids = {
            item["finding_id"]
            for item in dispositions
            if item["decision"] in {"FIX NOW", "IMPLEMENT LATER"}
        }
        if snapshot_ids != critic_actionable_ids:
            raise PlanPackageError(
                "INVALID_ROLE_OUTPUT",
                "critic actionable dispositions must exactly match assessment snapshots",
            )
        if output["inventory_approval"] is not None:
            validate_approval(output["inventory_approval"], INVENTORY_APPROVAL_FIELDS, "inventory approval")
        approvals = output["assessment_approvals"]
        if not isinstance(approvals, list) or [item.get("obligation_id") for item in approvals if isinstance(item, dict)] != attempt["assigned_obligation_ids"]:
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "critic requires one assessment approval per assigned obligation")
        assessment_map = {item["obligation_id"]: item for item in assessments}
        for approval in approvals:
            approval = validate_approval(approval, ASSESSMENT_APPROVAL_FIELDS, "assessment approval")
            assessment = assessment_map[approval["obligation_id"]]
            if approval["iteration"] != assessment["iteration"] or approval["binding_sha256"] != assessment["binding_sha256"] or approval["assessment_fingerprint"] != assessment["assessment_fingerprint"]:
                raise PlanPackageError("OUTPUT_BINDING_MISMATCH", "assessment approval does not bind its verifier assessment")
            if approval["decision"] != "APPROVED":
                raise PlanPackageError("INVALID_ROLE_OUTPUT", "a rejected assessment cannot produce a terminal critic envelope")
        exclusions = output["coverage_exclusion_approvals"]
        if not isinstance(exclusions, list):
            raise PlanPackageError("INVALID_ROLE_OUTPUT", "coverage exclusion approvals must be an array")
        for approval in exclusions:
            approval = validate_approval(approval, COVERAGE_EXCLUSION_APPROVAL_FIELDS, "coverage exclusion approval")
            if approval["approved_status"] not in {"out_of_scope", "deferred_by_critic"}:
                raise PlanPackageError("INVALID_ROLE_OUTPUT", "coverage exclusion approved status is invalid")
    elif any(output[field] is not None for field in ("inventory_approval", "assessment_approvals", "coverage_exclusion_approvals")):
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "owned lens roles require null approval fields")
    validate_terminal_envelope(output["terminal_envelope"], state, attempt, findings, dispositions, assessments, transfer)
    return output


def validate_escalation_output(output: Any, state: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    output = require_exact(output, ESCALATION_OUTPUT_FIELDS, "profile escalation output")
    if state["profile"] != "LIGHT" or attempt["role"] not in {"INTERNAL_READINESS", "REQUIREMENTS_COVERAGE", "REQUIREMENTS_SATISFACTION"}:
        raise PlanPackageError("INVALID_ROLE_OUTPUT", "profile escalation is legal only for a LIGHT owned lens")
    expected = {"schema_version": 1, "attempt_id": attempt["attempt_id"], "input_envelope_sha256": attempt["input_envelope_sha256"], "role": attempt["role"], "round": attempt["round"], "assessed_plan_sha256": state["plan_sha256"], "signal": "FULL_ARTIFACT_EXCEEDS_INLINE"}
    if any(output[field] != value for field, value in expected.items()):
        raise PlanPackageError("OUTPUT_BINDING_MISMATCH", "profile escalation output does not bind the prepared attempt")
    parse_utc(output["completed_at_utc"])
    return output


def cmd_finalize_attempt(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, _, run_root = load_state(path)
    token = require_exact(load_json(Path(args.attempt_token)), {"schema_version", "attempt_id", "state_revision", "slot_id", "input_envelope_sha256"}, "attempt token")
    attempt = find_attempt(state, token["attempt_id"])
    if attempt["status"] != "PREPARED":
        if attempt["status"] == args.status: return state_result("finalize-attempt", state, "ATTEMPT_ALREADY_FINALIZED")
        raise PlanPackageError("CONFLICTING_REPLAY", "attempt already finalized differently")
    if args.status not in TERMINAL_ATTEMPT_STATUSES or any(token[k] != attempt[{"state_revision":"state_revision", "slot_id":"slot_id", "input_envelope_sha256":"input_envelope_sha256", "attempt_id":"attempt_id"}[k]] for k in ("attempt_id", "state_revision", "slot_id", "input_envelope_sha256")):
        raise PlanPackageError("ATTEMPT_BINDING_MISMATCH", "attempt token or status mismatch")
    slot = slot_from_ledger(Path(args.slot_ledger), attempt["slot_id"])
    _, slots, _ = shared_contracts()
    projection = slots.released_slot_projection(slot)
    projection_hash = slots.released_slot_close_evidence_sha256(slot)
    if args.status == "SPAWN_FAILED":
        if args.runtime_agent_id is not None or slot.get("agent_id") is not None: raise PlanPackageError("INVALID_ATTEMPT", "SPAWN_FAILED forbids runtime ID")
    else:
        if not args.runtime_agent_id or slot.get("agent_id") != args.runtime_agent_id: raise PlanPackageError("INVALID_ATTEMPT", "runtime ID does not match slot")
    needs_output = args.status in {"SUCCEEDED", "PROFILE_ESCALATION_REQUIRED", "OUTPUT_INVALID"}
    if needs_output != bool(args.output): raise PlanPackageError("INVALID_ATTEMPT", "output nullability mismatch")
    output_rel = output_hash = None
    if args.output:
        output = load_json(Path(args.output), "role output")
        if args.status == "SUCCEEDED":
            validate_role_output(output, state, attempt)
        elif args.status == "PROFILE_ESCALATION_REQUIRED":
            validate_escalation_output(output, state, attempt)
        payload = canonical_bytes(output); output_hash = bytes_hash(payload); output_rel = f"attempts/{attempt['attempt_id']}/output.json"; publish_immutable(run_root / output_rel, payload)
    release_rel = f"attempts/{attempt['attempt_id']}/released-slot.json"; publish_immutable(run_root / release_rel, canonical_bytes(projection))
    attempt.update(status=args.status, runtime_agent_id=args.runtime_agent_id, output_path=output_rel, output_sha256=output_hash, close_evidence=projection, close_evidence_sha256=projection_hash, finalized_at_utc=now_utc())
    save_state(path, state)
    return state_result("finalize-attempt", state, "ATTEMPT_FINALIZED")


def cmd_escalate_profile(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, _, _ = load_state(path)
    token = load_json(Path(args.attempt_token)); attempt = find_attempt(state, token["attempt_id"])
    if state["profile"] != "LIGHT" or attempt["status"] != "PROFILE_ESCALATION_REQUIRED":
        raise PlanPackageError("INVALID_ESCALATION", "profile escalation requires a finalized LIGHT signal")
    state["profile"] = "SUBSTANTIAL"; state["budgets"].update(max_rounds=3, max_agent_attempts=23, max_elapsed_seconds=3600)
    state["deadline_at_utc"] = (parse_utc(state["started_at_utc"]) + timedelta(seconds=3600)).isoformat().replace("+00:00", "Z")
    state["status"] = "HARDENING"; save_state(path, state)
    return state_result("escalate-profile", state, "PROFILE_ESCALATED")


def cmd_record_runtime_blocker(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, _, _ = load_state(path)
    evidence = require_exact(load_json(Path(args.runtime_evidence)), {"schema_version", "state_sha256", "reason_code", "role", "attempt_ids", "evidence"}, "runtime evidence")
    if evidence["state_sha256"] != canonical_hash(state) or evidence["reason_code"] not in {"PARENT_TOOLS_UNAVAILABLE", "ASSESSOR_EXECUTION_UNAVAILABLE"}:
        raise PlanPackageError("INVALID_RUNTIME_EVIDENCE", "runtime evidence binding is invalid")
    blocker_id = "blocker-" + canonical_hash(evidence)[:24]
    state["blockers"].append({"id": blocker_id, "type": "RUNTIME", "practical_impact": "The required independent assessment cannot run.", "evidence": [f"runtime-evidence:{canonical_hash(evidence)}"], "required_resolution": "Restore the named parent or assessor execution boundary.", "status": "OPEN", "resolution": None})
    state["blockers"].sort(key=lambda x: x["id"]); state["status"] = "BLOCKED"; save_state(path, state)
    return state_result("record-runtime-blocker", state, "RUNTIME_BLOCKED")


def cmd_record_verification_ledger(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, _, run_root = load_state(path)
    initial_inventory = state["status"] == "DRAFTED" and not state["attempts"]
    if (state["status"] != "HARDENING" and not initial_inventory) or args.expected_current_sha256 != state["verification_ledger_sha256"]:
        raise PlanPackageError("LEDGER_BINDING_MISMATCH", "ledger update is not bound to the current planning state")
    _, digest = snapshot_verification_ledger(run_root, Path(args.ledger))
    if digest == state["verification_ledger_sha256"]:
        return state_result("record-verification-ledger", state, "VERIFICATION_LEDGER_RECORDED")
    receipt = refresh_current_revision_receipt(state, run_root, digest)
    state["verification_ledger_sha256"] = digest
    state["revision_history"][-1] = receipt
    save_state(path, state)
    return state_result("record-verification-ledger", state, "VERIFICATION_LEDGER_RECORDED")


def ledger_approval_ref(
    *, attempt_id: str, snapshot_path: str, snapshot_sha256: str, approval: dict[str, Any]
) -> dict[str, str]:
    return {
        "critic_attempt_id": attempt_id,
        "critic_snapshot_path": snapshot_path,
        "critic_snapshot_sha256": snapshot_sha256,
        "approval_sha256": canonical_hash(approval),
    }


def project_verify_plan_ledger(
    ledger: dict[str, Any], verifier: dict[str, Any], critic: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Translate a validated verifier/critic pair into the shared ledger contract."""
    verification = ledger["plan_verification"]
    inventory = next(
        item
        for item in verification["inventories"]
        if item["inventory_sha256"] == verification["inventory_sha256"]
    )
    ledger_iteration = ledger["iteration"]
    active_assignments = [
        item
        for item in verification["assignments"]
        if item["iteration"] == ledger_iteration
        and item["inventory_sha256"] == verification["inventory_sha256"]
    ]
    verifier_obligation_ids = [
        item["obligation_id"] for item in verifier["obligation_assessments"]
    ]
    critic_obligation_ids = [
        item["obligation_id"] for item in critic["obligation_assessments"]
    ]
    if (
        len(active_assignments) != 1
        or active_assignments[0]["assigned_obligation_ids"] != verifier_obligation_ids
        or active_assignments[0]["assigned_obligation_ids"] != critic_obligation_ids
    ):
        raise PlanPackageError(
            "LEDGER_ASSIGNMENT_MISMATCH",
            "verifier and critic assessments must exactly match the active local ledger assignment",
        )
    dispositions = {item["finding_id"]: item for item in critic["dispositions"]}
    translated_findings: dict[str, dict[str, Any]] = {}
    for finding in critic["findings"]:
        disposition = dispositions[finding["id"]]
        core = {
            "id": finding["id"],
            "classification": disposition["decision"],
            "obligation_ids": finding["obligation_ids"],
            "iteration_first_seen": ledger_iteration,
        }
        translated_findings[finding["id"]] = {
            **core,
            "fingerprint": canonical_hash(core),
            "status": (
                "open"
                if disposition["decision"] in {"FIX NOW", "IMPLEMENT LATER"}
                else disposition["decision"].lower() + "d"
            ),
        }

    existing_findings = {item["id"]: item for item in ledger["findings"]}
    for finding_id, translated in translated_findings.items():
        existing = existing_findings.get(finding_id)
        if existing is not None and existing != translated:
            raise PlanPackageError("FINDING_IDENTITY_CONFLICT", "shared-ledger finding identity changed")
        existing_findings[finding_id] = translated
    ledger["findings"] = sorted(existing_findings.values(), key=lambda item: item["id"])

    approval_map = {item["obligation_id"]: item for item in critic["assessment_approvals"]}
    translated_assessments: list[dict[str, Any]] = []
    translated_approvals: list[dict[str, Any]] = []
    for assessment in critic["obligation_assessments"]:
        snapshots = [
            {
                key: translated_findings[snapshot["id"]][key]
                for key in ("id", "fingerprint", "classification", "obligation_ids", "iteration_first_seen")
            }
            for snapshot in assessment["finding_snapshots"]
        ]
        projection = {
            "iteration": ledger_iteration,
            "obligation_id": assessment["obligation_id"],
            "binding_sha256": assessment["binding_sha256"],
            "status": assessment["status"],
            "evidence": assessment["evidence"],
            "finding_snapshots": snapshots,
            "blocked_boundary": assessment["blocked_boundary"],
        }
        translated = {**projection, "assessment_fingerprint": canonical_hash(projection)}
        source_approval = approval_map[assessment["obligation_id"]]
        translated_approval = {
            **source_approval,
            "iteration": ledger_iteration,
            "assessment_fingerprint": translated["assessment_fingerprint"],
        }
        translated_assessments.append(translated)
        translated_approvals.append(translated_approval)

    snapshot = {
        "schema_version": 1,
        "attempt_id": critic["attempt_id"],
        "inventory_approval": critic["inventory_approval"],
        "assessment_approvals": canonical_hash_sorted(translated_approvals),
        "coverage_exclusion_approvals": canonical_hash_sorted(
            critic["coverage_exclusion_approvals"]
        ),
    }
    snapshot_sha256 = canonical_hash(snapshot)
    snapshot_path = f".verify-plan/critic-outputs/{critic['attempt_id']}.json"

    if critic["inventory_approval"] is not None:
        inventory["completeness_approval"] = critic["inventory_approval"]
        inventory["completeness_approval_ref"] = ledger_approval_ref(
            attempt_id=critic["attempt_id"],
            snapshot_path=snapshot_path,
            snapshot_sha256=snapshot_sha256,
            approval=critic["inventory_approval"],
        )

    prior_assessments = [
        item
        for item in verification["obligation_assessments"]
        if item["iteration"] != ledger_iteration
    ]
    for assessment, approval in zip(translated_assessments, translated_approvals, strict=True):
        prior_assessments.append(
            {
                **assessment,
                "approval": approval,
                "approval_ref": ledger_approval_ref(
                    attempt_id=critic["attempt_id"],
                    snapshot_path=snapshot_path,
                    snapshot_sha256=snapshot_sha256,
                    approval=approval,
                ),
            }
        )
    verification["obligation_assessments"] = sorted(
        prior_assessments, key=lambda item: (item["iteration"], item["obligation_id"])
    )
    critic_record = {
        "attempt_id": critic["attempt_id"],
        "snapshot_path": snapshot_path,
        "output_sha256": snapshot_sha256,
    }
    prior_outputs = [
        item for item in verification["critic_outputs"]
        if item["attempt_id"] != critic["attempt_id"]
    ]
    verification["critic_outputs"] = [*prior_outputs, critic_record]

    translated_exclusions = []
    for approval in critic["coverage_exclusion_approvals"]:
        translated_exclusions.append(
            {
                **approval,
                "approval_ref": ledger_approval_ref(
                    attempt_id=critic["attempt_id"],
                    snapshot_path=snapshot_path,
                    snapshot_sha256=snapshot_sha256,
                    approval=approval,
                ),
            }
        )
    verification["coverage_exclusion_approvals"].extend(translated_exclusions)

    active_obligations = {item["id"]: item for item in inventory["obligations"]}
    latest = {
        obligation_id: max(
            (
                item for item in verification["obligation_assessments"]
                if item["obligation_id"] == obligation_id
                and item["binding_sha256"] == obligation["binding_sha256"]
                and item["approval"]["decision"] == "APPROVED"
            ),
            key=lambda item: item["iteration"],
            default=None,
        )
        for obligation_id, obligation in active_obligations.items()
    }
    open_by_obligation = {
        obligation_id: any(
            finding["classification"] in {"FIX NOW", "IMPLEMENT LATER"}
            and finding["status"] == "open"
            and obligation_id in finding["obligation_ids"]
            for finding in ledger["findings"]
        )
        for obligation_id in active_obligations
    }
    inventory_approved = bool(
        inventory["completeness_approval"]
        and inventory["completeness_approval"]["decision"] == "APPROVED"
    )
    excluded = {
        item["coverage_id"]: item["approved_status"] for item in translated_exclusions
    }
    resolved_finding_statuses = shared_contracts()[2].RESOLVED_STATUSES
    for coverage in ledger["coverage_queue"]:
        owned = [
            obligation_id for obligation_id, obligation in active_obligations.items()
            if obligation["coverage_id"] == coverage["id"]
        ]
        if coverage["id"] in excluded:
            coverage["status"] = excluded[coverage["id"]]
        elif inventory_approved and owned and all(
            latest[item] is not None
            and latest[item]["status"] == "SUPPORTED"
            and not open_by_obligation[item]
            for item in owned
        ):
            resolved_gap_history = any(
                assessment["obligation_id"] in owned
                and assessment["status"] == "GAP"
                and assessment["approval"]["decision"] == "APPROVED"
                and assessment["finding_snapshots"]
                and all(
                    snapshot["id"] in existing_findings
                    and existing_findings[snapshot["id"]]["status"]
                    in resolved_finding_statuses
                    for snapshot in assessment["finding_snapshots"]
                )
                for assessment in verification["obligation_assessments"]
            )
            coverage["status"] = "fixed" if resolved_gap_history else "checked"
        else:
            coverage["status"] = "unverified"
    return ledger, snapshot


def cmd_project_verify_plan_ledger(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, _, _ = load_state(path)
    if state["status"] != "HARDENING":
        raise PlanPackageError("INVALID_TRANSITION", "projection requires HARDENING")
    verifier = load_json(Path(args.verifier_output), "verifier output")
    critic = load_json(Path(args.critic_output), "critic output")
    verifier_attempt = find_attempt(state, verifier.get("attempt_id", ""))
    critic_attempt = find_attempt(state, critic.get("attempt_id", ""))
    if any(item["status"] != "SUCCEEDED" for item in (verifier_attempt, critic_attempt)):
        raise PlanPackageError("INVALID_ATTEMPT", "projection requires successful attempts")
    validate_role_output(verifier, state, verifier_attempt)
    validate_role_output(critic, state, critic_attempt)
    ledger_path = Path(args.ledger)
    ledger = validate_ledger(ledger_path)
    if canonical_hash(ledger) != state["verification_ledger_sha256"]:
        raise PlanPackageError("LEDGER_BINDING_MISMATCH", "projection ledger is not current")
    output_path = Path(args.out)
    if output_path.parent.resolve(strict=True) != ledger_path.parent.resolve(strict=True):
        raise PlanPackageError("UNSAFE_PATH", "projected ledger must remain beside its assets")
    projected, snapshot = project_verify_plan_ledger(ledger, verifier, critic)
    snapshot_path = output_path.parent / f".verify-plan/critic-outputs/{critic['attempt_id']}.json"
    publish_immutable(snapshot_path, canonical_bytes(snapshot))
    atomic_json(output_path, projected)
    validate_ledger(output_path)
    return state_result("project-verify-plan-ledger", state, "VERIFY_PLAN_LEDGER_PROJECTED")


def cmd_record_findings(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, _, _ = load_state(path)
    primary = load_json(Path(args.primary_output), "primary role output")
    critic = load_json(Path(args.critic_output), "critic role output") if args.critic_output else None
    if args.stage == "VERIFY_PLAN" and critic is None: raise PlanPackageError("INVALID_FINDINGS", "VERIFY_PLAN requires critic output")
    if args.stage != "VERIFY_PLAN" and critic is not None: raise PlanPackageError("INVALID_FINDINGS", "owned lens forbids critic output")
    source = critic if critic is not None else primary
    findings = source.get("findings")
    if not isinstance(findings, list): raise PlanPackageError("INVALID_FINDINGS", "role output findings must be an array")
    dispositions = source.get("dispositions")
    if not isinstance(dispositions, list) or len(dispositions) != len(findings): raise PlanPackageError("INVALID_FINDINGS", "one disposition is required per finding")
    existing = {item["id"]: item for item in state["findings"]}
    for finding in findings:
        fid = require_string(finding.get("id"), "finding id")
        fingerprint = finding.get("fingerprint")
        if not SHA_RE.fullmatch(str(fingerprint)): raise PlanPackageError("INVALID_FINDINGS", "finding fingerprint is invalid")
        if fid in existing and existing[fid]["fingerprint"] != fingerprint: raise PlanPackageError("FINDING_IDENTITY_CONFLICT", "finding ID fingerprint changed")
        if fid not in existing:
            enriched = {**finding, "assessed_plan_sha256": state["plan_sha256"], "assessed_revision": state["revision"]}; state["findings"].append(enriched); existing[fid] = enriched
        disposition = next((d for d in dispositions if d.get("finding_id") == fid and d.get("finding_fingerprint") == fingerprint), None)
        if disposition is None: raise PlanPackageError("INVALID_FINDINGS", "disposition does not bind finding")
        decision = disposition.get("decision")
        if decision not in {"FIX NOW", "IMPLEMENT LATER", "ACKNOWLEDGE", "DISMISS"}: raise PlanPackageError("INVALID_FINDINGS", "invalid disposition decision")
        occurrence = {**disposition, "stage": args.stage, "round": args.round, "verification_iteration": int(primary.get("verification_iteration", 1)), "status": "OPEN" if decision in {"FIX NOW", "IMPLEMENT LATER"} else "NO_ACTION", "assessed_plan_sha256": state["plan_sha256"], "assessed_revision": state["revision"]}
        prior = [item for item in state["dispositions"] if item["finding_id"] == fid]
        if any({key: value for key, value in item.items() if key != "assessment_sequence"} == occurrence for item in prior):
            continue
        sequence = 1 + max([item["assessment_sequence"] for item in prior] or [0])
        state["dispositions"].append({**occurrence, "assessment_sequence": sequence})
    state["findings"].sort(key=lambda x: x["id"]); state["dispositions"].sort(key=lambda x: (x["finding_id"], x["assessment_sequence"])); save_state(path, state)
    return state_result("record-findings", state, "FINDINGS_RECORDED")


def artifact_for_stage(state: dict[str, Any], stage: str, attempt: dict[str, Any] | None, supplied: Path | None) -> dict[str, Any]:
    if stage == "VERIFY_PLAN":
        if supplied is None: raise PlanPackageError("INVALID_STAGE_ARTIFACT", "VERIFY_PLAN requires rendered summary")
        payload = supplied.read_bytes(); return {"form": "INLINE", "path": None, "content_markdown": payload.decode("utf-8"), "sha256": bytes_hash(payload)}
    expected_file = state["profile"] == "SUBSTANTIAL"
    if attempt is None or not attempt["output_path"]: raise PlanPackageError("INVALID_STAGE_ARTIFACT", "lens stage requires successful attempt")
    if expected_file:
        names = {"INTERNAL_READINESS": "plan.gap-audit.md", "REQUIREMENTS_COVERAGE": "plan.coverage-audit.md", "REQUIREMENTS_SATISFACTION": "plan.satisfaction-audit.md"}
        if supplied is None or supplied.name != names[stage]: raise PlanPackageError("INVALID_STAGE_ARTIFACT", "SUBSTANTIAL lens requires fixed audit file")
        payload = supplied.read_bytes(); return {"form": "FILE", "path": names[stage], "content_markdown": None, "sha256": bytes_hash(payload)}
    output = load_json(Path(state["run_root"]) / attempt["output_path"]); transfer = output.get("artifact_transfer", {})
    text = transfer.get("content_markdown"); require_string(text, "inline artifact")
    return {"form": "INLINE", "path": None, "content_markdown": text, "sha256": bytes_hash(text.encode())}


def cmd_materialize_artifact(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, task_root, run_root = load_state(path)
    if resolve_dir(Path(args.task_directory), "task directory") != task_root: raise PlanPackageError("TASK_ROOT_MISMATCH", "task directory changed")
    token = load_json(Path(args.attempt_token)); attempt = find_attempt(state, token["attempt_id"])
    output = load_json(Path(args.role_output)); transfer = output.get("artifact_transfer")
    if attempt["status"] != "SUCCEEDED" or transfer.get("form") != "FILE": raise PlanPackageError("INVALID_ARTIFACT_TRANSFER", "attempt does not own a FILE transfer")
    target = contained_file(run_root, attempt["output_path"], "attempt output")
    if canonical_hash(load_json(target)) != attempt["output_sha256"] and bytes_hash(target.read_bytes()) != attempt["output_sha256"]: raise PlanPackageError("OUTPUT_TAMPER", "attempt output changed")
    destination = task_root / transfer["target_path"]
    if destination.name not in {"plan.gap-audit.md", "plan.coverage-audit.md", "plan.satisfaction-audit.md"}: raise PlanPackageError("INVALID_ARTIFACT_TRANSFER", "unexpected artifact target")
    payload = transfer["content_markdown"].encode();
    if bytes_hash(payload) != transfer["sha256"]: raise PlanPackageError("INVALID_ARTIFACT_TRANSFER", "artifact hash mismatch")
    atomic_bytes(destination, payload)
    return state_result("materialize-artifact", state, "ARTIFACT_MATERIALIZED")


def cmd_render_verify_summary(args: argparse.Namespace) -> dict[str, Any]:
    state, _, run_root = load_state(Path(args.state_json)); validate_ledger(verification_ledger_snapshot_path(run_root, state["verification_ledger_sha256"]))
    lines = ["# Plan Verification Summary", "", f"Plan SHA-256: `{state['plan_sha256']}`", "", "## Attempts"]
    for attempt in state["attempts"]:
        if attempt["role"].startswith("VERIFY_PLAN"): lines.append(f"- {attempt['verification_iteration']} {attempt['role']}: {attempt['status']} ({attempt['attempt_id']})")
    lines.extend(["", "## Findings"]); lines.extend([f"- {f['id']}: {f['practical_consequence']}" for f in state["findings"]] or ["- None"])
    atomic_bytes(Path(args.out), ("\n".join(lines) + "\n").encode())
    return state_result("render-verify-summary", state, "VERIFY_SUMMARY_RENDERED")


def cmd_record_stage(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, _, _ = load_state(path)
    expected = STAGES[len([s for s in state["stage_results"] if s["round"] == args.round])] if len([s for s in state["stage_results"] if s["round"] == args.round]) < 4 else None
    if args.stage != expected: raise PlanPackageError("STAGE_ORDER_VIOLATION", "hardening stages must be recorded in fixed order")
    attempt = None
    terminal_envelope: dict[str, Any]
    if args.stage == "VERIFY_PLAN":
        if args.source_attempt_id: raise PlanPackageError("INVALID_STAGE", "VERIFY_PLAN forbids source attempt")
        critics = [item for item in state["attempts"] if item["round"] == args.round and item["role"] == "VERIFY_PLAN_CRITIC" and item["status"] == "SUCCEEDED"]
        if not critics:
            raise PlanPackageError("INVALID_STAGE", "VERIFY_PLAN requires a successful critic output")
        attempt = max(critics, key=lambda item: item["attempt_sequence"])
    else:
        if not args.source_attempt_id: raise PlanPackageError("INVALID_STAGE", "owned lens stage requires source attempt")
        attempt = find_attempt(state, args.source_attempt_id)
        if attempt["status"] != "SUCCEEDED" or attempt["role"] != args.stage: raise PlanPackageError("INVALID_STAGE", "source attempt does not satisfy stage")
    if not attempt or not attempt["output_path"]:
        raise PlanPackageError("INVALID_STAGE", "stage source has no controller-owned output")
    output_path = contained_file(Path(state["run_root"]), attempt["output_path"], "stage source output")
    if bytes_hash(output_path.read_bytes()) != attempt["output_sha256"]:
        raise PlanPackageError("OUTPUT_TAMPER", "stage source output changed")
    output = load_json(output_path, "stage source output")
    validate_role_output(output, state, attempt)
    terminal_envelope = output["terminal_envelope"]
    if args.stage == "VERIFY_PLAN":
        validate_ledger(verification_ledger_snapshot_path(Path(state["run_root"]), state["verification_ledger_sha256"]), can_stop=terminal_envelope["verdict"] == "PASS")
    artifact = artifact_for_stage(state, args.stage, attempt, Path(args.artifact) if args.artifact else None)
    roles = [a for a in state["attempts"] if a["round"] == args.round and a["status"] == "SUCCEEDED" and (a["role"].startswith("VERIFY_PLAN") if args.stage == "VERIFY_PLAN" else a["attempt_id"] == args.source_attempt_id)]
    role_results = [{"role": a["role"], "verification_iteration": a["verification_iteration"], "assigned_coverage_ids": a["assigned_coverage_ids"], "assigned_obligation_ids": a["assigned_obligation_ids"], "lens_contract_id": a["lens_contract_id"], "lens_contract_sha256": a["lens_contract_sha256"], "runtime_agent_id": a["runtime_agent_id"], "input_envelope_sha256": a["input_envelope_sha256"], "output_sha256": a["output_sha256"]} for a in roles]
    verdict = terminal_envelope["verdict"]
    record = {"round": args.round, "stage": args.stage, "lens_contract_id": None if args.stage == "VERIFY_PLAN" else state["lens_contract_id"], "lens_contract_sha256": None if args.stage == "VERIFY_PLAN" else state["lens_contract_sha256"], "terminal_verdict": verdict, "role_results": role_results, "terminal_envelope_sha256": canonical_hash(terminal_envelope), "artifact": artifact}
    state["stage_results"].append(record)
    for blocker in terminal_envelope["new_blockers"]:
        record_blocker = {**blocker, "status": "OPEN", "resolution": None}
        existing = next((item for item in state["blockers"] if item["id"] == blocker["id"]), None)
        if existing is None:
            state["blockers"].append(record_blocker)
        elif existing != record_blocker:
            raise PlanPackageError("BLOCKER_IDENTITY_CONFLICT", "terminal blocker conflicts with controller state")
    state["blockers"].sort(key=lambda item: item["id"])
    current_round = [item for item in state["stage_results"] if item["round"] == args.round]
    if verdict == "PASS" and len(current_round) == 4 and all(item["terminal_verdict"] == "PASS" for item in current_round):
        state["status"] = "READY"
    elif verdict == "PASS":
        state["status"] = "HARDENING"
    else:
        state["status"] = verdict
    save_state(path, state); return state_result("record-stage", state, "STAGE_RECORDED")


def cmd_prepare_revision(args: argparse.Namespace) -> dict[str, Any]:
    state, _, run_root = load_state(Path(args.state_json))
    if state["status"] not in {"GAPS", "EMITTED"}: raise PlanPackageError("INVALID_TRANSITION", "prepare-revision requires GAPS or EMITTED")
    revision = state["revision"] + 1; final = run_root / "proposed-revisions" / str(revision)
    if not final.exists():
        staging = final.with_name(f"{revision}.staging"); shutil.rmtree(staging, ignore_errors=True); staging.mkdir(parents=True)
        source_map = {"plan.md": run_root / f"snapshots/plan/{state['plan_sha256']}.md", "evidence-index.json": run_root / f"snapshots/evidence-index/{state['evidence_index_sha256']}.json", "surface-map.json": run_root / f"snapshots/surface-map/{state['surface_map_sha256']}.json", "decisions.json": run_root / f"snapshots/decisions/{state['decisions_sha256']}.json", "verification-ledger.json": verification_ledger_snapshot_path(run_root, state["verification_ledger_sha256"])}
        seeds = []
        for name, source in source_map.items():
            payload = source.read_bytes(); atomic_bytes(staging / name, payload); seeds.append({"path": name, "sha256": bytes_hash(payload)})
            if name == "verification-ledger.json":
                for relative, asset_payload in verification_ledger_snapshot_assets(source):
                    atomic_bytes(staging / relative, asset_payload)
        proposal = {"schema_version": 1, "package_id": state["package_id"], "base_revision": state["revision"], "proposed_revision": revision, "base_state_sha256": canonical_hash(state), "seed_files": sorted(seeds, key=lambda x: x["path"]), "prepared_at_utc": now_utc()}
        atomic_json(staging / "proposal.json", proposal); os.replace(staging, final); fsync_dir(final.parent)
    return state_result("prepare-revision", state, "REVISION_WORKSPACE_PREPARED")


def cmd_record_revision(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, task_root, run_root = load_state(path)
    proposal_dir = resolve_dir(Path(args.proposal), "revision proposal")
    proposal = require_exact(
        load_json(proposal_dir / "proposal.json"),
        {"schema_version", "package_id", "base_revision", "proposed_revision", "base_state_sha256", "seed_files", "prepared_at_utc"},
        "revision proposal",
    )
    proposed_revision = proposal["proposed_revision"]
    if (
        proposal["schema_version"] != 1
        or proposal["package_id"] != state["package_id"]
        or isinstance(proposed_revision, bool)
        or not isinstance(proposed_revision, int)
        or proposal["base_revision"] != proposed_revision - 1
        or proposal_dir != run_root / "proposed-revisions" / str(proposed_revision)
    ):
        raise PlanPackageError("INVALID_REVISION", "proposal identity or path is not deterministic")
    replay = proposed_revision == state["revision"] and proposed_revision >= 2
    if not replay and proposed_revision != state["revision"] + 1:
        raise PlanPackageError("INVALID_REVISION", "proposal is not the current or next revision")
    if not replay and proposal["base_state_sha256"] != canonical_hash(state):
        raise PlanPackageError("REVISION_BASIS_DRIFT", "revision base state changed")
    open_ids = {d["finding_id"] for d in state["dispositions"] if d["status"] == "OPEN" and not any(t["finding_id"] == d["finding_id"] and t["disposition_sequence"] == d["assessment_sequence"] for t in state["finding_transitions"])}
    if replay:
        expected_closed_ids = {
            transition["finding_id"] for transition in state["finding_transitions"]
            if transition.get("applied_revision") == proposed_revision and transition.get("to_status") == "APPLIED"
        }
    else:
        expected_closed_ids = open_ids
    if set(args.closed_finding_id or []) != expected_closed_ids:
        raise PlanPackageError("INCOMPLETE_REVISION", "record-revision must close every current actionable finding")
    plan_bytes = (proposal_dir / "plan.md").read_bytes(); surface = validate_surface_map(load_json(proposal_dir / "surface-map.json"), state["charter"], state["requirements"]); decisions = validate_decisions(load_json(proposal_dir / "decisions.json"), {r["id"] for r in state["requirements"]})
    plan_rel, plan_hash = snapshot_bytes(run_root, "plan", plan_bytes, "md"); _, surface_hash = snapshot_json(run_root, "surface-map", surface); _, decisions_hash = snapshot_json(run_root, "decisions", decisions); _, ledger_hash = snapshot_verification_ledger(run_root, proposal_dir / "verification-ledger.json")
    revision = proposed_revision; hashes = {"plan": plan_hash, "surface-map": surface_hash, "decisions": decisions_hash, "verification-ledger": ledger_hash}; receipt = publish_revision(state, run_root, revision, hashes, plan_rel)
    if replay:
        current_hashes = (
            state["plan_sha256"], state["surface_map_sha256"], state["decisions_sha256"],
            state["verification_ledger_sha256"],
        )
        if current_hashes != (plan_hash, surface_hash, decisions_hash, ledger_hash):
            raise PlanPackageError("REVISION_RECEIPT_CONFLICT", "record-revision replay artifacts changed")
        matching = [row for row in state["revision_history"] if row.get("revision") == revision]
        if matching != [receipt]:
            raise PlanPackageError("REVISION_RECEIPT_CONFLICT", "record-revision replay state changed")
        return state_result("record-revision", state, "REVISION_RECORDED")
    for fid in sorted(open_ids):
        disposition = max((d for d in state["dispositions"] if d["finding_id"] == fid and d["status"] == "OPEN"), key=lambda d: d["assessment_sequence"])
        state["finding_transitions"].append({"finding_id": fid, "finding_fingerprint": disposition["finding_fingerprint"], "sequence": 1 + max([t["sequence"] for t in state["finding_transitions"] if t["finding_id"] == fid] or [0]), "disposition_sequence": disposition["assessment_sequence"], "from_status": "OPEN", "to_status": "APPLIED", "applied_revision": revision, "applied_plan_sha256": plan_hash, "revision_receipt_sha256": receipt["receipt_sha256"]})
    if state["status"] == "EMITTED":
        emission = state["emission_history"][-1]; timestamp = now_utc(); marker = {"schema_version": 1, "package_id": state["package_id"], "invalidated_revision": state["revision"], "successor_revision": revision, "prior_manifest_sha256": emission["manifest_sha256"], "prior_plan_sha256": state["plan_sha256"], "successor_receipt_sha256": receipt["receipt_sha256"], "successor_revision_basis_sha256": load_json(run_root / receipt["receipt_path"])["revision_basis_sha256"], "invalidated_at_utc": timestamp}; atomic_json(task_root / ".plan-package-invalidated.json", marker); emission.update(invalidated_by_revision=revision, invalidated_at_utc=timestamp)
    state.update(status="DRAFTED", revision=revision, plan_sha256=plan_hash, surface_map_sha256=surface_hash, decisions_sha256=decisions_hash, verification_ledger_sha256=ledger_hash, stage_results=[], implementation_approval_status="NOT_REQUESTED", implementation_authorization_request_path=None, implementation_authorization_request_sha256=None, implementation_authorization_path=None, implementation_authorization_sha256=None)
    state["revision_history"].append(receipt); save_state(path, state); return state_result("record-revision", state, "REVISION_RECORDED")


def package_files_for(state: dict[str, Any], task_root: Path, run_root: Path) -> dict[str, bytes]:
    ledger_path = verification_ledger_snapshot_path(run_root, state["verification_ledger_sha256"])
    files = {"plan.md": (run_root / f"snapshots/plan/{state['plan_sha256']}.md").read_bytes(), "requirements.json": canonical_bytes(state["requirements"]), "evidence-index.json": (run_root / f"snapshots/evidence-index/{state['evidence_index_sha256']}.json").read_bytes(), "surface-map.json": (run_root / f"snapshots/surface-map/{state['surface_map_sha256']}.json").read_bytes(), "decisions.json": (run_root / f"snapshots/decisions/{state['decisions_sha256']}.json").read_bytes(), "verification-ledger.json": ledger_path.read_bytes()}
    for relative, payload in verification_ledger_snapshot_assets(ledger_path):
        if relative in files and files[relative] != payload:
            raise PlanPackageError("IMMUTABLE_CONFLICT", f"verification ledger asset conflicts with package file: {relative}")
        files[relative] = payload
    findings = {"schema_version": 1, "plan_sha256": state["plan_sha256"], "revision_history": [], "findings": state["findings"], "dispositions": state["dispositions"], "finding_transitions": state["finding_transitions"]}
    for row in state["revision_history"]:
        receipt = load_json(run_root / row["receipt_path"]); findings["revision_history"].append({"receipt": receipt, "receipt_sha256": row["receipt_sha256"], "plan_markdown": (run_root / receipt["plan_snapshot_path"]).read_text()})
    files["findings.json"] = canonical_bytes(findings)
    gate = {"schema_version": 1, "plan_sha256": state["plan_sha256"], "lens_contract_id": state["lens_contract_id"], "lens_contract_sha256": state["lens_contract_sha256"], "profile": state["profile"], "stages": state["stage_results"], "terminal_verdict": "PASS"}; files["gate-results.json"] = canonical_bytes(gate)
    if state["profile"] == "SUBSTANTIAL":
        for name in ("plan.gap-audit.md", "plan.coverage-audit.md", "plan.satisfaction-audit.md"):
            path = task_root / name
            if path.is_symlink() or not path.is_file(): raise PlanPackageError("MISSING_AUDIT", f"missing {name}")
            files[name] = path.read_bytes()
    return files


def validate_package_root(task_root: Path, *, allow_invalidated: bool = False) -> dict[str, Any]:
    if not allow_invalidated and (task_root / ".plan-package-invalidated.json").exists(): raise PlanPackageError("PACKAGE_INVALIDATED", "package is invalidated")
    manifest = load_json(task_root / "manifest.json", "plan manifest")
    fields = {"schema_version", "package_id", "revision", "profile", "entry_mode", "approval_context", "approval_authorization", "charter_sha256", "requirements_sha256", "evidence_index_sha256", "plan_sha256", "lens_contract_id", "lens_contract_sha256", "owned_files", "stage_results", "agent_lifecycle", "budget_use", "terminal_verdict", "emitted_at_utc"}
    require_exact(manifest, fields, "plan manifest")
    if (
        manifest["schema_version"] != 1
        or not re.fullmatch(r"plan-package-[0-9a-f]{24}", str(manifest["package_id"]))
        or isinstance(manifest["revision"], bool)
        or not isinstance(manifest["revision"], int)
        or manifest["revision"] < 1
        or manifest["profile"] not in {"LIGHT", "SUBSTANTIAL"}
        or manifest["entry_mode"] not in {"DIRECT", "RESEARCH_PACKAGE"}
        or manifest["approval_context"] not in {"ORDINARY", "CONVERGENCE"}
        or manifest["approval_authorization"] is not None
        or manifest["terminal_verdict"] != "PASS"
        or manifest["lens_contract_id"] != LENS_CONTRACT_ID
    ):
        raise PlanPackageError("INVALID_PACKAGE", "package manifest identity is invalid")
    for field in ("charter_sha256", "requirements_sha256", "evidence_index_sha256", "plan_sha256", "lens_contract_sha256"):
        if not isinstance(manifest[field], str) or not SHA_RE.fullmatch(manifest[field]):
            raise PlanPackageError("INVALID_PACKAGE", f"manifest {field} is invalid")
    parse_utc(manifest["emitted_at_utc"])
    if not isinstance(manifest["stage_results"], list) or [row.get("stage") for row in manifest["stage_results"][-4:]] != list(STAGES):
        raise PlanPackageError("INVALID_PACKAGE", "package stage results are incomplete or unordered")
    if any(row.get("terminal_verdict") != "PASS" for row in manifest["stage_results"][-4:]):
        raise PlanPackageError("INVALID_PACKAGE", "package contains a non-passing hardening stage")
    owned = manifest["owned_files"]
    if not isinstance(owned, list):
        raise PlanPackageError("INVALID_PACKAGE", "owned files must be an array")
    for row in owned:
        require_exact(row, {"path", "sha256"}, "owned file")
        require_string(row["path"], "owned file path")
        if not isinstance(row["sha256"], str) or not SHA_RE.fullmatch(row["sha256"]):
            raise PlanPackageError("INVALID_PACKAGE", "owned file hash is invalid")
    if owned != sorted(owned, key=lambda x: x["path"]): raise PlanPackageError("INVALID_PACKAGE", "owned files are not sorted")
    if len({row["path"] for row in owned}) != len(owned):
        raise PlanPackageError("INVALID_PACKAGE", "owned file paths must be unique")
    reserved = {"plan.md", "requirements.json", "evidence-index.json", "surface-map.json", "decisions.json", "verification-ledger.json", "findings.json", "gate-results.json", "manifest.json", "plan.gap-audit.md", "plan.coverage-audit.md", "plan.satisfaction-audit.md"}
    expected = ({row["path"] for row in owned} & reserved) | {"manifest.json"}
    present = {name for name in reserved if (task_root / name).exists()}
    if present != expected: raise PlanPackageError("INVALID_PACKAGE", "package reserved-file set mismatch")
    for row in owned:
        file = contained_file(task_root, row["path"], "owned file")
        if bytes_hash(file.read_bytes()) != row["sha256"]: raise PlanPackageError("PACKAGE_TAMPER", f"owned file changed: {row['path']}")
    expected_hashes = {
        "requirements.json": manifest["requirements_sha256"],
        "evidence-index.json": manifest["evidence_index_sha256"],
        "plan.md": manifest["plan_sha256"],
    }
    for name, expected_hash in expected_hashes.items():
        if bytes_hash((task_root / name).read_bytes()) != expected_hash:
            raise PlanPackageError("INVALID_PACKAGE", f"manifest identity does not match {name}")
    gate_results = require_exact(
        load_json(task_root / "gate-results.json", "gate results"),
        {"schema_version", "plan_sha256", "lens_contract_id", "lens_contract_sha256", "profile", "stages", "terminal_verdict"},
        "gate results",
    )
    if (
        gate_results["schema_version"] != 1
        or gate_results["plan_sha256"] != manifest["plan_sha256"]
        or gate_results["lens_contract_id"] != manifest["lens_contract_id"]
        or gate_results["lens_contract_sha256"] != manifest["lens_contract_sha256"]
        or gate_results["profile"] != manifest["profile"]
        or gate_results["stages"] != manifest["stage_results"]
        or gate_results["terminal_verdict"] != "PASS"
    ):
        raise PlanPackageError("INVALID_PACKAGE", "gate results do not match the manifest")
    required_audits = set() if manifest["profile"] == "LIGHT" else {
        "plan.gap-audit.md", "plan.coverage-audit.md", "plan.satisfaction-audit.md"
    }
    if required_audits != ({row["path"] for row in owned} & {"plan.gap-audit.md", "plan.coverage-audit.md", "plan.satisfaction-audit.md"}):
        raise PlanPackageError("INVALID_PACKAGE", "package audit files do not match its profile")
    if (task_root / "manifest.json").read_bytes() != canonical_bytes(manifest):
        raise PlanPackageError("INVALID_PACKAGE", "manifest bytes are not canonical")
    manifest_hash = bytes_hash((task_root / "manifest.json").read_bytes())
    return {"schema_version": 1, "valid": True, "package_id": manifest["package_id"], "revision": manifest["revision"], "profile": manifest["profile"], "terminal_verdict": manifest["terminal_verdict"], "manifest_sha256": manifest_hash, "owned_files": owned}


PACKAGE_RESERVED = {
    "plan.md", "requirements.json", "evidence-index.json", "surface-map.json",
    "decisions.json", "verification-ledger.json", "findings.json",
    "gate-results.json", "manifest.json", "plan.gap-audit.md",
    "plan.coverage-audit.md", "plan.satisfaction-audit.md",
}
EMISSION_JOURNAL_FIELDS = {
    "schema_version", "transaction_id", "package_id", "revision",
    "revision_basis_sha256", "state", "old_owned_files", "new_owned_files",
    "stale_owned_files", "new_manifest_sha256", "staging_path", "backup_path",
    "emitted_at_utc", "created_at_utc",
}
EMISSION_STATES = {
    "PREPARING", "PREPARED", "OLD_BACKED_UP", "NEW_INSTALLED",
    "MANIFEST_PUBLISHING", "MANIFEST_PUBLISHED", "ROLLED_BACK",
}


def emission_checkpoint(name: str) -> None:
    if os.environ.get("PLAN_PLAYBOOK_V2_TEST_CRASH_AFTER") == name:
        os._exit(86)


def emission_inventory(task_root: Path) -> list[dict[str, Any]]:
    rows = []
    for name in sorted(PACKAGE_RESERVED):
        target = task_root / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise PlanPackageError("EMISSION_PRECONDITION_DRIFT", f"reserved package path is unsafe: {name}")
        rows.append({"path": name, "present": target.is_file(), "sha256": bytes_hash(target.read_bytes()) if target.is_file() else None})
    return rows


def require_emission_journal(task_root: Path) -> tuple[Path, dict[str, Any]]:
    path = task_root / ".plan-package-transaction.json"
    journal = require_exact(load_json(path, "emission journal"), EMISSION_JOURNAL_FIELDS, "emission journal")
    if journal["schema_version"] != 1 or journal["state"] not in EMISSION_STATES:
        raise PlanPackageError("INVALID_EMISSION_JOURNAL", "emission journal identity is invalid")
    for field in ("transaction_id", "revision_basis_sha256", "new_manifest_sha256"):
        value = journal[field]
        if value is not None and (not isinstance(value, str) or not SHA_RE.fullmatch(value)):
            raise PlanPackageError("INVALID_EMISSION_JOURNAL", f"emission journal {field} is invalid")
    parse_utc(journal["emitted_at_utc"]); parse_utc(journal["created_at_utc"])
    return path, journal


def write_emission_journal(path: Path, journal: dict[str, Any], state_name: str, **updates: Any) -> dict[str, Any]:
    updated = {**journal, **updates, "state": state_name}
    require_exact(updated, EMISSION_JOURNAL_FIELDS, "emission journal")
    atomic_json(path, updated)
    reopened = load_json(path, "emission journal")
    if reopened != updated: raise PlanPackageError("EMISSION_JOURNAL_WRITE_FAILED", "emission journal reopen mismatch")
    emission_checkpoint(state_name)
    return updated


def assert_old_inventory(task_root: Path, rows: list[dict[str, Any]]) -> None:
    current = {row["path"]: row for row in emission_inventory(task_root)}
    for expected in rows:
        if current.get(expected["path"]) != expected:
            raise PlanPackageError("EMISSION_PRECONDITION_DRIFT", f"root package path changed: {expected['path']}")


def clean_emission_paths(task_root: Path, journal: dict[str, Any], *, remove_journal: bool) -> None:
    for field in ("staging_path", "backup_path"):
        relative = PurePosixPath(journal[field])
        target = task_root.joinpath(*relative.parts)
        if target.exists(): shutil.rmtree(target)
        parent = target.parent
        if parent.exists() and not any(parent.iterdir()): parent.rmdir()
    if remove_journal:
        path = task_root / ".plan-package-transaction.json"
        if path.exists(): path.unlink()
    fsync_dir(task_root)


def rollback_emission(task_root: Path, journal_path: Path, journal: dict[str, Any]) -> dict[str, Any]:
    backup = task_root / journal["backup_path"]
    installed_paths = [task_root / row["path"] for row in journal["new_owned_files"]]
    for target in installed_paths:
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise PlanPackageError("EMISSION_ROLLBACK_FAILED", f"installed path is unsafe: {target.relative_to(task_root)}")
        if target.is_file():
            target.unlink()
    for target in sorted(installed_paths, key=lambda path: len(path.parts), reverse=True):
        for parent in target.parents:
            if parent == task_root or not parent.exists() or any(parent.iterdir()):
                break
            parent.rmdir()
    for row in journal["old_owned_files"]:
        target = task_root / row["path"]
        if target.exists(): target.unlink()
        source = backup / row["path"]
        if row["present"]:
            if not source.is_file() or bytes_hash(source.read_bytes()) != row["sha256"]:
                raise PlanPackageError("EMISSION_ROLLBACK_FAILED", f"backup is unavailable: {row['path']}")
            target.parent.mkdir(parents=True, exist_ok=True); os.replace(source, target)
    fsync_dir(task_root)
    assert_old_inventory(task_root, journal["old_owned_files"])
    journal = write_emission_journal(journal_path, journal, "ROLLED_BACK")
    clean_emission_paths(task_root, journal, remove_journal=False)
    return journal


def emission_manifest(state: dict[str, Any], files: dict[str, bytes], emitted: str) -> dict[str, Any]:
    owned = [{"path": name, "sha256": bytes_hash(payload)} for name, payload in sorted(files.items())]
    return {"schema_version": 1, "package_id": state["package_id"], "revision": state["revision"], "profile": state["profile"], "entry_mode": state["entry_mode"], "approval_context": state["approval_context"], "approval_authorization": None, "charter_sha256": state["charter_sha256"], "requirements_sha256": state["requirements_sha256"], "evidence_index_sha256": state["evidence_index_sha256"], "plan_sha256": state["plan_sha256"], "lens_contract_id": state["lens_contract_id"], "lens_contract_sha256": state["lens_contract_sha256"], "owned_files": owned, "stage_results": state["stage_results"], "agent_lifecycle": state["attempts"], "budget_use": {"rounds_used": max([s["round"] for s in state["stage_results"]] or [0]), "attempts_used": state["budgets"]["used_agent_attempts"], "elapsed_seconds": int((parse_utc(emitted) - parse_utc(state["started_at_utc"])).total_seconds())}, "terminal_verdict": "PASS", "emitted_at_utc": emitted}


def run_emission_transaction(state: dict[str, Any], task_root: Path, run_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    journal_path = task_root / ".plan-package-transaction.json"
    if journal_path.exists():
        _, journal = require_emission_journal(task_root)
        if journal["package_id"] != state["package_id"] or journal["revision"] != state["revision"]:
            raise PlanPackageError("EMISSION_REPLAY_MISMATCH", "emission journal belongs to another package revision")
        if journal["state"] == "MANIFEST_PUBLISHING":
            manifest = task_root / "manifest.json"
            if manifest.is_file() and bytes_hash(manifest.read_bytes()) == journal["new_manifest_sha256"]:
                validate_package_root(task_root, allow_invalidated=True)
                journal = write_emission_journal(journal_path, journal, "MANIFEST_PUBLISHED")
        if journal["state"] == "MANIFEST_PUBLISHED":
            return validate_package_root(task_root, allow_invalidated=True), journal
        if journal["state"] == "PREPARED":
            assert_old_inventory(task_root, journal["old_owned_files"])
            journal = write_emission_journal(journal_path, journal, "PREPARING", new_owned_files=[], new_manifest_sha256=None)
        elif journal["state"] in {"OLD_BACKED_UP", "NEW_INSTALLED", "MANIFEST_PUBLISHING"}:
            journal = rollback_emission(task_root, journal_path, journal)
        if journal["state"] == "ROLLED_BACK":
            journal = write_emission_journal(journal_path, journal, "PREPARING", new_owned_files=[], new_manifest_sha256=None)
        elif journal["state"] != "PREPARING":
            raise PlanPackageError("INVALID_EMISSION_JOURNAL", "emission journal cannot resume")
        assert_old_inventory(task_root, journal["old_owned_files"])
    else:
        receipt = load_json(run_root / state["revision_history"][-1]["receipt_path"], "revision receipt")
        old = emission_inventory(task_root)
        new_names = set(package_files_for(state, task_root, run_root)) | {"manifest.json"}
        stale = [row for row in old if row["present"] and row["path"] not in new_names]
        basis = {"schema_version": 1, "package_id": state["package_id"], "revision": state["revision"], "revision_basis_sha256": receipt["revision_basis_sha256"], "old_owned_files": old, "stale_owned_files": stale}
        transaction_id = canonical_hash(basis); emitted = now_utc()
        journal = {"schema_version": 1, "transaction_id": transaction_id, "package_id": state["package_id"], "revision": state["revision"], "revision_basis_sha256": receipt["revision_basis_sha256"], "state": "PREPARING", "old_owned_files": old, "new_owned_files": [], "stale_owned_files": stale, "new_manifest_sha256": None, "staging_path": f".plan-package-staging/{transaction_id}", "backup_path": f".plan-package-backup/{transaction_id}", "emitted_at_utc": emitted, "created_at_utc": emitted}
        atomic_json(journal_path, journal); emission_checkpoint("PREPARING")
    files = package_files_for(state, task_root, run_root)
    manifest = emission_manifest(state, files, journal["emitted_at_utc"])
    staging = task_root / journal["staging_path"]; backup = task_root / journal["backup_path"]
    if staging.exists():
        expected_staged = {**files, "manifest.json": canonical_bytes(manifest)}
        for candidate in staging.rglob("*"):
            if candidate.is_symlink() or (candidate.exists() and not candidate.is_file() and not candidate.is_dir()):
                raise PlanPackageError("EMISSION_STAGING_CONFLICT", "staging contains an unsafe path")
            if candidate.is_file():
                relative = candidate.relative_to(staging).as_posix()
                if relative not in expected_staged or candidate.read_bytes() != expected_staged[relative]:
                    raise PlanPackageError("EMISSION_STAGING_CONFLICT", f"staging bytes conflict: {relative}")
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for index, (name, payload) in enumerate(sorted(files.items())):
        atomic_bytes(staging / name, payload)
        if index == 0: emission_checkpoint("PARTIAL_STAGING")
    atomic_json(staging / "manifest.json", manifest); fsync_dir(staging)
    validate_package_root(staging)
    new_rows = [{"path": row["path"], "sha256": row["sha256"]} for row in manifest["owned_files"]] + [{"path": "manifest.json", "sha256": bytes_hash((staging / "manifest.json").read_bytes())}]
    new_rows.sort(key=lambda row: row["path"])
    journal = write_emission_journal(journal_path, journal, "PREPARED", new_owned_files=new_rows, new_manifest_sha256=bytes_hash((staging / "manifest.json").read_bytes()))
    if backup.exists(): shutil.rmtree(backup)
    backup.mkdir(parents=True)
    for row in journal["old_owned_files"]:
        source = task_root / row["path"]
        if row["present"]:
            target = backup / row["path"]; target.parent.mkdir(parents=True, exist_ok=True); os.replace(source, target)
    fsync_dir(task_root); journal = write_emission_journal(journal_path, journal, "OLD_BACKED_UP")
    for row in journal["new_owned_files"]:
        if row["path"] != "manifest.json":
            target = task_root / row["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / row["path"], target)
    fsync_dir(task_root); journal = write_emission_journal(journal_path, journal, "NEW_INSTALLED")
    journal = write_emission_journal(journal_path, journal, "MANIFEST_PUBLISHING")
    os.replace(staging / "manifest.json", task_root / "manifest.json"); fsync_dir(task_root)
    if bytes_hash((task_root / "manifest.json").read_bytes()) != journal["new_manifest_sha256"]:
        raise PlanPackageError("EMISSION_MANIFEST_MISMATCH", "published manifest hash changed")
    receipt = validate_package_root(task_root, allow_invalidated=True)
    journal = write_emission_journal(journal_path, journal, "MANIFEST_PUBLISHED")
    return receipt, journal


def cmd_emit_package(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, task_root, run_root = load_state(path)
    if resolve_dir(Path(args.task_directory), "task directory") != task_root: raise PlanPackageError("INVALID_TRANSITION", "emit-package requires the frozen task root")
    if state["status"] == "EMITTED":
        receipt = validate_package_root(task_root)
        latest = state["emission_history"][-1] if state["emission_history"] else None
        if not latest or latest["revision"] != state["revision"] or latest["plan_sha256"] != state["plan_sha256"] or latest["manifest_sha256"] != receipt["manifest_sha256"]:
            raise PlanPackageError("EMISSION_REPLAY_MISMATCH", "emitted package does not match controller history")
        journal_path = task_root / ".plan-package-transaction.json"
        if journal_path.exists():
            _, journal = require_emission_journal(task_root)
            if journal["state"] != "MANIFEST_PUBLISHED" or journal["new_manifest_sha256"] != receipt["manifest_sha256"]:
                raise PlanPackageError("EMISSION_REPLAY_MISMATCH", "unfinished emission journal conflicts with emitted state")
            clean_emission_paths(task_root, journal, remove_journal=True)
        marker = task_root / ".plan-package-invalidated.json"
        if marker.exists(): marker.unlink(); fsync_dir(task_root)
        return state_result("emit-package", state, "PACKAGE_EMITTED")
    if state["status"] != "READY": raise PlanPackageError("INVALID_TRANSITION", "emit-package requires READY")
    if len(state["stage_results"]) < 4 or [r["stage"] for r in state["stage_results"][-4:]] != list(STAGES): raise PlanPackageError("INCOMPLETE_HARDENING", "four ordered stages are required")
    receipt, journal = run_emission_transaction(state, task_root, run_root)
    state["emission_history"].append({"revision": state["revision"], "plan_sha256": state["plan_sha256"], "manifest_sha256": receipt["manifest_sha256"], "emitted_at_utc": journal["emitted_at_utc"], "invalidated_by_revision": None, "invalidated_at_utc": None}); state["status"] = "EMITTED"; save_state(path, state)
    emission_checkpoint("STATE_COMMITTED")
    marker = task_root / ".plan-package-invalidated.json"
    if marker.exists(): marker.unlink(); fsync_dir(task_root)
    clean_emission_paths(task_root, journal, remove_journal=True)
    return state_result("emit-package", state, "PACKAGE_EMITTED")


def cmd_validate_package(args: argparse.Namespace) -> dict[str, Any]:
    return validate_package_root(resolve_dir(Path(args.task_directory), "task directory"))


def cmd_prepare_implementation_authorization(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, task_root, run_root = load_state(path)
    if state["status"] != "EMITTED": raise PlanPackageError("INVALID_TRANSITION", "authorization request requires EMITTED")
    package = validate_package_root(task_root); surface = load_json(task_root / "surface-map.json"); approval = surface["implementation_approval"]
    repositories = sorted({repo for change in approval["granular_changes"] for repo in change["repositories"]}); allowed_paths = sorted({p for change in approval["granular_changes"] for p in change["allowed_paths"]})
    base = {"schema_version": 1, "package_id": state["package_id"], "revision": state["revision"], "plan_sha256": state["plan_sha256"], "manifest_sha256": package["manifest_sha256"], "requirements_sha256": state["requirements_sha256"], "repositories": repositories, "allowed_paths": allowed_paths, "granular_changes": approval["granular_changes"], "practical_consequence": approval["practical_consequence"], "estimated_cost": approval["estimated_cost"], "approval_context": state["approval_context"]}
    basis = canonical_hash(base); request = {**base, "approval_basis_sha256": basis, "required_confirmation": f"APPROVE IMPLEMENTATION {basis}"}; request["request_sha256"] = canonical_hash(request)
    expected = run_root / f"authorizations/implementation-request-r{state['revision']}.json"
    if Path(args.out).absolute() != expected: raise PlanPackageError("OUTPUT_PATH_MISMATCH", "authorization request path is deterministic")
    publish_immutable(expected, canonical_bytes(request)); state.update(implementation_approval_status="AWAITING_RESPONSE", implementation_authorization_request_path=relative_under(run_root, expected, "authorization request"), implementation_authorization_request_sha256=bytes_hash(expected.read_bytes())); save_state(path, state)
    return state_result("prepare-implementation-authorization", state, "IMPLEMENTATION_APPROVAL_REQUIRED")


def cmd_record_implementation_authorization(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, task_root, run_root = load_state(path)
    if state["status"] != "EMITTED" or state["implementation_approval_status"] != "AWAITING_RESPONSE": raise PlanPackageError("INVALID_TRANSITION", "authorization recording requires AWAITING_RESPONSE")
    request_path = contained_file(run_root, state["implementation_authorization_request_path"], "authorization request"); request = load_json(request_path)
    try:
        supplied_request = Path(args.request).resolve(strict=True)
    except OSError as exc:
        raise PlanPackageError("PATH_UNAVAILABLE", "authorization request is unavailable") from exc
    if supplied_request != request_path or bytes_hash(request_path.read_bytes()) != state["implementation_authorization_request_sha256"]:
        raise PlanPackageError("AUTHORIZATION_REQUEST_TAMPER", "request path or bytes do not match controller state")
    source = None; evidence_path = evidence_hash = entry_path = entry_hash = None
    authorized = now_utc()
    if state["approval_context"] == "ORDINARY":
        if not args.approval_response or args.convergence_state: raise PlanPackageError("ENTRY_ARGUMENT_CONFLICT", "ORDINARY requires only approval response")
        raw = Path(args.approval_response).read_bytes()
        if raw != request["required_confirmation"].encode(): raise PlanPackageError("APPROVAL_DENIED", "response does not exactly approve the request")
        evidence = {"schema_version": 1, "request_sha256": request["request_sha256"], "decision": "APPROVED", "approved_at_utc": authorized, "user_response": raw.decode(), "user_response_sha256": bytes_hash(raw)}
        target = run_root / f"authorizations/ordinary-approval-r{state['revision']}.json"; publish_immutable(target, canonical_bytes(evidence)); evidence_path = relative_under(run_root, target, "approval evidence"); evidence_hash = bytes_hash(target.read_bytes()); source = "USER_RESPONSE"
    else:
        if args.approval_response or not args.convergence_state: raise PlanPackageError("ENTRY_ARGUMENT_CONFLICT", "CONVERGENCE requires only outer state")
        outer = Path(args.convergence_state).resolve(strict=True); entry_path = str(outer); entry_hash = bytes_hash(outer.read_bytes()); source = "CONVERGENCE_AUTHORIZATION"
    identity = {"schema_version": 1, "package_id": state["package_id"], "revision": state["revision"], "manifest_sha256": request["manifest_sha256"], "request_sha256": request["request_sha256"], "authorization_source": source, "approval_evidence_sha256": evidence_hash, "entry_authorization_sha256": entry_hash}
    receipt = {"schema_version": 1, "authorization_id": "implementation-authorization-" + canonical_hash(identity)[:24], "authorization_source": source, "package_id": state["package_id"], "revision": state["revision"], "plan_sha256": state["plan_sha256"], "manifest_sha256": request["manifest_sha256"], "request_path": state["implementation_authorization_request_path"], "request_sha256": request["request_sha256"], "repositories": request["repositories"], "allowed_paths": request["allowed_paths"], "granular_changes": request["granular_changes"], "practical_consequence": request["practical_consequence"], "estimated_cost": request["estimated_cost"], "approval_evidence_path": evidence_path, "approval_evidence_sha256": evidence_hash, "entry_authorization_path": entry_path, "entry_authorization_sha256": entry_hash, "authorized_at_utc": authorized}
    target = run_root / f"authorizations/implementation-r{state['revision']}.json"; publish_immutable(target, canonical_bytes(receipt)); state.update(implementation_approval_status="AUTHORIZED", implementation_authorization_path=relative_under(run_root, target, "authorization"), implementation_authorization_sha256=bytes_hash(target.read_bytes())); save_state(path, state)
    return state_result("record-implementation-authorization", state, "IMPLEMENTATION_AUTHORIZED")


def validate_authorization(state: dict[str, Any], task_root: Path, run_root: Path, supplied: Path) -> dict[str, Any]:
    if state["status"] != "EMITTED" or state["implementation_approval_status"] != "AUTHORIZED": raise PlanPackageError("IMPLEMENTATION_NOT_AUTHORIZED", "no current implementation authorization")
    package = validate_package_root(task_root); expected = contained_file(run_root, state["implementation_authorization_path"], "implementation authorization")
    if supplied.resolve(strict=True) != expected or bytes_hash(expected.read_bytes()) != state["implementation_authorization_sha256"]: raise PlanPackageError("AUTHORIZATION_TAMPER", "authorization path or hash changed")
    receipt = load_json(expected)
    if receipt["package_id"] != state["package_id"] or receipt["revision"] != state["revision"] or receipt["manifest_sha256"] != package["manifest_sha256"]: raise PlanPackageError("AUTHORIZATION_STALE", "authorization does not bind current package")
    return {"schema_version": 1, "valid": True, "authorization_id": receipt["authorization_id"], "authorization_source": receipt["authorization_source"], "package_id": state["package_id"], "revision": state["revision"], "plan_sha256": state["plan_sha256"], "manifest_sha256": package["manifest_sha256"], "authorization_sha256": state["implementation_authorization_sha256"]}


def cmd_validate_implementation_authorization(args: argparse.Namespace) -> dict[str, Any]:
    state, task_root, run_root = load_state(Path(args.state_json)); return validate_authorization(state, task_root, run_root, Path(args.authorization))


def cmd_prepare_continuation_approval(args: argparse.Namespace) -> dict[str, Any]:
    state, _, run_root = load_state(Path(args.state_json))
    if state["approval_context"] != "CONVERGENCE" or state["status"] != "CAP_REACHED" or state["profile"] != "SUBSTANTIAL" or state["cap_reason"] != "VERIFY_PLAN_ITERATION_LIMIT" or state["cap_completed_verification_iteration"] != 10 or state["cap_stage"] != "VERIFY_PLAN" or state["budgets"]["verify_plan_iteration_limit"] != 10 or state["budgets"]["continuation_approval_sha256"] is not None or parse_utc(state["cap_reached_at_utc"]) > parse_utc(state["started_at_utc"]) + timedelta(seconds=3600): raise PlanPackageError("CONTINUATION_INELIGIBLE", "inner state is not eligible for convergence continuation")
    outer_path = Path(args.convergence_state).resolve(strict=True); outer = load_json(outer_path)
    approval = outer.get("approvals", {}).get(args.outer_approval_id)
    scope = {"kind": "continue", "operations": ["continue"], "target_ids": ["plan"], "repository_roots": [], "allowed_paths": [], "stage": "plan", "outer_iteration": outer.get("outer_iteration")}
    if not approval or approval.get("status") != "consumed" or approval.get("consumed_by") != args.outer_operation_id or approval.get("scope") != scope: raise PlanPackageError("INVALID_CONTINUATION_APPROVAL", "outer approval is not the consumed bounded plan continuation")
    envelope_path = outer_path.parent / "authorizations" / f"{args.outer_approval_id}.json"
    envelope = require_exact(load_json(envelope_path, "outer continuation authorization"), OUTER_CONTINUATION_FIELDS, "outer continuation authorization")
    envelope_sha = bytes_hash(envelope_path.read_bytes())
    if approval.get("evidence") != f"path={envelope_path.resolve()};sha256={envelope_sha}" or envelope_path.read_bytes() != canonical_bytes(envelope): raise PlanPackageError("INVALID_CONTINUATION_APPROVAL", "outer authorization evidence does not bind canonical bytes")
    expected_resume = envelope["outer_resume_status"]
    return_shape = (outer.get("status"), outer.get("blocked_stage"))
    if expected_resume == "plan": expected_shape = ("plan", None)
    elif expected_resume == "blocked" and envelope["outer_blocked_stage"] == "plan": expected_shape = ("blocked", "plan")
    else: raise PlanPackageError("INVALID_CONTINUATION_APPROVAL", "outer authorization return shape is invalid")
    if return_shape != expected_shape or envelope["authorization_id"] != args.outer_approval_id or envelope["task_id"] != outer.get("task_id") or envelope["outer_iteration"] != outer.get("outer_iteration") or envelope["plan_package_id"] != state["package_id"] or envelope["inner_state_sha256"] != canonical_hash(state) or envelope["plan_sha256"] != state["plan_sha256"] or envelope["approved_from_iteration"] != 10 or envelope["approved_through_iteration"] != 20: raise PlanPackageError("INVALID_CONTINUATION_APPROVAL", "outer authorization does not bind current inner and outer state")
    expected = run_root / "approvals/verify-plan-continuation-i10.json"
    if Path(args.out).absolute() != expected: raise PlanPackageError("OUTPUT_PATH_MISMATCH", "continuation path is deterministic")
    if expected.exists():
        inner = require_exact(load_json(expected), {"schema_version", "package_id", "plan_sha256", "approved_from_iteration", "approved_through_iteration", "scope", "approved_at_utc"}, "continuation approval")
    else:
        inner = {"schema_version": 1, "package_id": state["package_id"], "plan_sha256": state["plan_sha256"], "approved_from_iteration": 10, "approved_through_iteration": 20, "scope": "VERIFY_PLAN_CONTINUATION", "approved_at_utc": now_utc()}
    publish_immutable(expected, canonical_bytes(inner))
    inner_sha = bytes_hash(expected.read_bytes())
    provenance = {"schema_version": 1, "convergence_state_path": str(outer_path), "convergence_state_sha256": bytes_hash(outer_path.read_bytes()), "outer_approval_id": args.outer_approval_id, "outer_operation_id": args.outer_operation_id, "outer_iteration": outer["outer_iteration"], "outer_resume_status": expected_resume, "outer_blocked_stage": envelope["outer_blocked_stage"], "authorization_envelope_path": str(envelope_path.resolve()), "authorization_envelope_sha256": envelope_sha, "inner_approval_sha256": inner_sha}
    publish_immutable(expected.with_suffix(".provenance.json"), canonical_bytes(provenance)); return state_result("prepare-continuation-approval", state, "CONTINUATION_APPROVAL_PREPARED")


def cmd_continue_hardening(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, _, run_root = load_state(path); supplied = Path(args.approval).resolve(strict=True); expected = run_root / "approvals/verify-plan-continuation-i10.json"
    if supplied != expected: raise PlanPackageError("INVALID_CONTINUATION_APPROVAL", "continuation approval path is not controller-owned")
    approval = require_exact(load_json(supplied), {"schema_version", "package_id", "plan_sha256", "approved_from_iteration", "approved_through_iteration", "scope", "approved_at_utc"}, "continuation approval")
    approval_sha = bytes_hash(supplied.read_bytes())
    if state["status"] == "HARDENING" and state["budgets"]["continuation_approval_sha256"] == approval_sha: return state_result("continue-hardening", state, "HARDENING_CONTINUED")
    if state["status"] != "CAP_REACHED" or approval["package_id"] != state["package_id"] or approval["plan_sha256"] != state["plan_sha256"] or approval["approved_from_iteration"] != 10 or approval["approved_through_iteration"] != 20 or approval["scope"] != "VERIFY_PLAN_CONTINUATION": raise PlanPackageError("INVALID_CONTINUATION_APPROVAL", "continuation approval binding is invalid")
    if state["approval_context"] == "CONVERGENCE":
        provenance = require_exact(load_json(expected.with_suffix(".provenance.json")), CONTINUATION_PROVENANCE_FIELDS, "continuation provenance")
        outer_path = Path(provenance["convergence_state_path"]); outer = load_json(outer_path); envelope_path = Path(provenance["authorization_envelope_path"])
        if bytes_hash(outer_path.read_bytes()) != provenance["convergence_state_sha256"] or bytes_hash(envelope_path.read_bytes()) != provenance["authorization_envelope_sha256"] or provenance["inner_approval_sha256"] != approval_sha or outer.get("approvals", {}).get(provenance["outer_approval_id"], {}).get("consumed_by") != provenance["outer_operation_id"] or (outer.get("status"), outer.get("blocked_stage")) != (("plan", None) if provenance["outer_resume_status"] == "plan" else ("blocked", "plan")): raise PlanPackageError("INVALID_CONTINUATION_APPROVAL", "continuation provenance changed")
    state["budgets"].update(max_agent_attempts=43, max_elapsed_seconds=7200, verify_plan_iteration_limit=20, continuation_approval_sha256=approval_sha); state["deadline_at_utc"] = (parse_utc(state["started_at_utc"]) + timedelta(seconds=7200)).isoformat().replace("+00:00", "Z"); state.update(status="HARDENING", cap_reason=None, cap_reached_at_utc=None, cap_stage=None, cap_completed_verification_iteration=None); save_state(path, state)
    return state_result("continue-hardening", state, "HARDENING_CONTINUED")


def cmd_prepare_deadline_continuation_approval(args: argparse.Namespace) -> dict[str, Any]:
    state, _, run_root = load_state(Path(args.state_json))
    expired = parse_utc(now_utc()) > parse_utc(state["deadline_at_utc"])
    deadline_cap = state["status"] == "CAP_REACHED" and state["cap_reason"] == "DEADLINE_EXCEEDED"
    receipt_path = run_root / f"approvals/deadline-continuation-r{state['revision']}.json"
    if (
        state["approval_context"] != "ORDINARY"
        or state["profile"] != "SUBSTANTIAL"
        or state["status"] not in {"DRAFTED", "HARDENING", "CAP_REACHED"}
        or not (expired or deadline_cap)
        or receipt_path.exists()
    ):
        raise PlanPackageError("CONTINUATION_INELIGIBLE", "state is not eligible for deadline continuation")
    base = {
        "schema_version": 1,
        "package_id": state["package_id"],
        "revision": state["revision"],
        "plan_sha256": state["plan_sha256"],
        "state_sha256": canonical_hash(state),
        "current_deadline_at_utc": state["deadline_at_utc"],
        "current_max_rounds": state["budgets"]["max_rounds"],
        "extension_seconds": 3600,
        "extension_rounds": 3,
        "scope": "DEADLINE_CONTINUATION",
    }
    basis = canonical_hash(base)
    request = {
        **base,
        "approval_basis_sha256": basis,
        "required_confirmation": f"APPROVE DEADLINE CONTINUATION {basis}",
    }
    request["request_sha256"] = canonical_hash(request)
    expected = run_root / (
        f"approvals/deadline-continuation-request-r{state['revision']}-"
        f"{base['state_sha256']}.json"
    )
    if Path(args.out).absolute() != expected:
        raise PlanPackageError("OUTPUT_PATH_MISMATCH", "deadline continuation request path is deterministic")
    publish_immutable(expected, canonical_bytes(request))
    return state_result(
        "prepare-deadline-continuation-approval", state, "DEADLINE_CONTINUATION_APPROVAL_REQUIRED"
    )


def cmd_continue_deadline_hardening(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json)
    state, _, run_root = load_state(path)
    request_path = run_root / (
        f"approvals/deadline-continuation-request-r{state['revision']}-"
        f"{canonical_hash(state)}.json"
    )
    receipt_path = run_root / f"approvals/deadline-continuation-r{state['revision']}.json"
    if (
        state["status"] == "HARDENING"
        and state["budgets"]["continuation_approval_sha256"] is not None
        and receipt_path.is_file()
        and bytes_hash(receipt_path.read_bytes()) == state["budgets"]["continuation_approval_sha256"]
    ):
        return state_result("continue-deadline-hardening", state, "DEADLINE_HARDENING_CONTINUED")
    supplied_request = Path(args.request).resolve(strict=True)
    if supplied_request != request_path:
        raise PlanPackageError("INVALID_CONTINUATION_APPROVAL", "deadline request path is not controller-owned")
    request = load_json(request_path, "deadline continuation request")
    if (
        request.get("schema_version") != 1
        or request.get("package_id") != state["package_id"]
        or request.get("revision") != state["revision"]
        or request.get("plan_sha256") != state["plan_sha256"]
        or request.get("state_sha256") != canonical_hash(state)
        or request.get("current_deadline_at_utc") != state["deadline_at_utc"]
        or request.get("current_max_rounds") != state["budgets"]["max_rounds"]
        or request.get("extension_seconds") != 3600
        or request.get("extension_rounds") != 3
        or request.get("scope") != "DEADLINE_CONTINUATION"
        or request.get("approval_basis_sha256") != canonical_hash({
            key: request[key]
            for key in (
                "schema_version", "package_id", "revision", "plan_sha256", "state_sha256",
                "current_deadline_at_utc", "current_max_rounds", "extension_seconds",
                "extension_rounds", "scope",
            )
        })
        or request.get("request_sha256") != canonical_hash({
            key: request[key] for key in request if key != "request_sha256"
        })
    ):
        raise PlanPackageError("INVALID_CONTINUATION_APPROVAL", "deadline request binding is invalid")
    response = Path(args.approval_response).read_bytes()
    if response != request["required_confirmation"].encode():
        raise PlanPackageError("APPROVAL_DENIED", "response does not exactly approve deadline continuation")
    approved_at = now_utc()
    new_deadline = parse_utc(approved_at) + timedelta(seconds=3600)
    receipt = {
        "schema_version": 1,
        "package_id": state["package_id"],
        "revision": state["revision"],
        "plan_sha256": state["plan_sha256"],
        "request_sha256": request["request_sha256"],
        "scope": "DEADLINE_CONTINUATION",
        "extension_seconds": 3600,
        "extension_rounds": 3,
        "prior_max_rounds": state["budgets"]["max_rounds"],
        "new_max_rounds": state["budgets"]["max_rounds"] + 3,
        "approved_at_utc": approved_at,
        "new_deadline_at_utc": new_deadline.isoformat().replace("+00:00", "Z"),
        "user_response_sha256": bytes_hash(response),
    }
    publish_immutable(receipt_path, canonical_bytes(receipt))
    receipt_sha = bytes_hash(receipt_path.read_bytes())
    state["budgets"]["continuation_approval_sha256"] = receipt_sha
    state["budgets"]["max_elapsed_seconds"] = int(
        (new_deadline - parse_utc(state["started_at_utc"])).total_seconds()
    )
    state["budgets"]["max_rounds"] = receipt["new_max_rounds"]
    state["deadline_at_utc"] = receipt["new_deadline_at_utc"]
    state.update(
        status="HARDENING",
        cap_reason=None,
        cap_reached_at_utc=None,
        cap_stage=None,
        cap_completed_verification_iteration=None,
    )
    save_state(path, state)
    return state_result("continue-deadline-hardening", state, "DEADLINE_HARDENING_CONTINUED")


def awaiting_paired_critic(state: dict[str, Any]) -> dict[str, Any]:
    verifiers = [
        attempt for attempt in state["attempts"]
        if attempt.get("state_revision") == state["revision"]
        and attempt.get("role") == "VERIFY_PLAN_VERIFIER"
        and attempt.get("status") == "SUCCEEDED"
    ]
    if not verifiers:
        raise PlanPackageError(
            "ATTEMPT_CONTINUATION_INELIGIBLE",
            "attempt continuation requires a successful current-revision verifier",
        )
    verifier = max(verifiers, key=lambda item: item["attempt_sequence"])
    current_attempts = [
        attempt for attempt in state["attempts"]
        if attempt.get("state_revision") == state["revision"]
    ]
    if (
        not current_attempts
        or max(current_attempts, key=lambda item: item["attempt_sequence"])["attempt_id"]
        != verifier["attempt_id"]
        or expected_attempt_role(state, verifier["round"]) != "VERIFY_PLAN_CRITIC"
    ):
        raise PlanPackageError(
            "ATTEMPT_CONTINUATION_INELIGIBLE",
            "the current revision is not awaiting the verifier's paired critic",
        )
    paired = [
        attempt for attempt in state["attempts"]
        if attempt.get("state_revision") == state["revision"]
        and attempt.get("role") == "VERIFY_PLAN_CRITIC"
        and attempt.get("verification_iteration") == verifier["verification_iteration"]
    ]
    if paired:
        raise PlanPackageError(
            "ATTEMPT_CONTINUATION_INELIGIBLE",
            "the current-revision verifier already has a critic attempt",
        )
    return verifier


def attempt_continuation_context(
    state: dict[str, Any], run_root: Path, receipt_path: Path
) -> dict[str, Any]:
    budgets = state["budgets"]
    if (
        state["approval_context"] != "ORDINARY"
        or state["profile"] != "SUBSTANTIAL"
        or budgets["used_agent_attempts"]
        != budgets["max_agent_attempts"] - budgets["reserved_later_stage_attempts"]
        or budgets["reserved_later_stage_attempts"] != 3
        or receipt_path.exists()
    ):
        raise PlanPackageError(
            "ATTEMPT_CONTINUATION_INELIGIBLE",
            "state is not eligible for a bounded attempt continuation",
        )
    if (
        state["status"] == "CAP_REACHED"
        and state["cap_reason"] == "AGENT_ATTEMPT_LIMIT"
        and state["cap_stage"] == "VERIFY_PLAN"
    ):
        verifier = awaiting_paired_critic(state)
        return {
            "basis_attempt_id": verifier["attempt_id"],
            "target_role": "VERIFY_PLAN_CRITIC",
            "target_round": verifier["round"],
            "target_verification_iteration": verifier["verification_iteration"],
            "extension_attempts": 1,
            "scope": "PAIRED_CRITIC_ATTEMPT_CONTINUATION",
        }
    current_attempts = [
        attempt for attempt in state["attempts"]
        if attempt.get("state_revision") == state["revision"]
    ]
    if state["status"] != "DRAFTED" or current_attempts or not state["attempts"]:
        raise PlanPackageError(
            "ATTEMPT_CONTINUATION_INELIGIBLE",
            "state is neither awaiting a paired critic nor an attempt-free corrected revision",
        )
    prior_critic = max(state["attempts"], key=lambda item: item["attempt_sequence"])
    if (
        prior_critic.get("state_revision") != state["revision"] - 1
        or prior_critic.get("role") != "VERIFY_PLAN_CRITIC"
        or prior_critic.get("status") != "SUCCEEDED"
        or not prior_critic.get("output_path")
        or not SHA_RE.fullmatch(str(prior_critic.get("output_sha256")))
    ):
        raise PlanPackageError(
            "ATTEMPT_CONTINUATION_INELIGIBLE",
            "corrected revision does not follow a successful prior-revision critic",
        )
    output_path = contained_file(
        run_root, prior_critic["output_path"], "prior critic output"
    )
    output_bytes = output_path.read_bytes()
    output = load_json(output_path, "prior critic output")
    if not isinstance(output, dict):
        raise PlanPackageError(
            "ATTEMPT_CONTINUATION_INELIGIBLE", "prior critic output is not an object"
        )
    dispositions = output.get("dispositions")
    terminal = output.get("terminal_envelope")
    actionable_ids = {
        disposition.get("finding_id")
        for disposition in dispositions if disposition.get("decision") in {"FIX NOW", "IMPLEMENT LATER"}
    } if isinstance(dispositions, list) else set()
    applied_ids = {
        transition.get("finding_id")
        for transition in state["finding_transitions"]
        if transition.get("to_status") == "APPLIED"
        and transition.get("applied_revision") == state["revision"]
    }
    if (
        bytes_hash(output_bytes) != prior_critic["output_sha256"]
        or output.get("attempt_id") != prior_critic["attempt_id"]
        or not isinstance(terminal, dict)
        or terminal.get("verdict") != "GAPS"
        or not actionable_ids
        or not all(isinstance(item, str) and item for item in actionable_ids)
        or not actionable_ids.issubset(applied_ids)
        or output.get("assessed_plan_sha256") == state["plan_sha256"]
    ):
        raise PlanPackageError(
            "ATTEMPT_CONTINUATION_INELIGIBLE",
            "corrected revision is not bound to fully applied prior critic gaps",
        )
    return {
        "basis_attempt_id": prior_critic["attempt_id"],
        "target_role": "VERIFY_PLAN_VERIFIER",
        "target_round": 1 + max(attempt["round"] for attempt in state["attempts"]),
        "target_verification_iteration": prior_critic["verification_iteration"] + 1,
        "extension_attempts": 2,
        "scope": "REVISION_VERIFY_PAIR_ATTEMPT_CONTINUATION",
    }


def cmd_prepare_attempt_continuation_approval(args: argparse.Namespace) -> dict[str, Any]:
    state, _, run_root = load_state(Path(args.state_json))
    budgets = state["budgets"]
    receipt_path = run_root / f"approvals/attempt-continuation-r{state['revision']}.json"
    context = attempt_continuation_context(state, run_root, receipt_path)
    base = {
        "schema_version": 1,
        "package_id": state["package_id"],
        "revision": state["revision"],
        "plan_sha256": state["plan_sha256"],
        "state_sha256": canonical_hash(state),
        "current_max_agent_attempts": budgets["max_agent_attempts"],
        "used_agent_attempts": budgets["used_agent_attempts"],
        "reserved_later_stage_attempts": budgets["reserved_later_stage_attempts"],
        **context,
    }
    basis = canonical_hash(base)
    request = {
        **base,
        "approval_basis_sha256": basis,
        "required_confirmation": f"APPROVE ATTEMPT CONTINUATION {basis}",
    }
    request["request_sha256"] = canonical_hash(request)
    expected = run_root / (
        f"approvals/attempt-continuation-request-r{state['revision']}-"
        f"{base['state_sha256']}.json"
    )
    if Path(args.out).absolute() != expected:
        raise PlanPackageError(
            "OUTPUT_PATH_MISMATCH", "attempt continuation request path is deterministic"
        )
    publish_immutable(expected, canonical_bytes(request))
    return state_result(
        "prepare-attempt-continuation-approval",
        state,
        "ATTEMPT_CONTINUATION_APPROVAL_REQUIRED",
    )


def cmd_continue_attempt_hardening(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json)
    state, _, run_root = load_state(path)
    receipt_path = run_root / f"approvals/attempt-continuation-r{state['revision']}.json"
    if state["status"] == "HARDENING" and receipt_path.is_file():
        receipt = load_json(receipt_path, "attempt continuation receipt")
        if (
            receipt.get("package_id") == state["package_id"]
            and receipt.get("revision") == state["revision"]
            and receipt.get("plan_sha256") == state["plan_sha256"]
            and receipt.get("new_max_agent_attempts")
            == state["budgets"]["max_agent_attempts"]
            and receipt_path.read_bytes() == canonical_bytes(receipt)
        ):
            return state_result(
                "continue-attempt-hardening", state, "ATTEMPT_HARDENING_CONTINUED"
            )
    request_path = run_root / (
        f"approvals/attempt-continuation-request-r{state['revision']}-"
        f"{canonical_hash(state)}.json"
    )
    supplied_request = Path(args.request).resolve(strict=True)
    if supplied_request != request_path:
        raise PlanPackageError(
            "INVALID_ATTEMPT_CONTINUATION_APPROVAL",
            "attempt continuation request path is not controller-owned",
        )
    request = load_json(request_path, "attempt continuation request")
    budgets = state["budgets"]
    try:
        context = attempt_continuation_context(state, run_root, receipt_path)
    except PlanPackageError as error:
        raise PlanPackageError(
            "INVALID_ATTEMPT_CONTINUATION_APPROVAL", str(error)
        ) from error
    base_fields = (
        "schema_version", "package_id", "revision", "plan_sha256", "state_sha256",
        "current_max_agent_attempts", "used_agent_attempts",
        "reserved_later_stage_attempts", "basis_attempt_id", "target_role",
        "target_round", "target_verification_iteration", "extension_attempts", "scope",
    )
    if (
        request.get("schema_version") != 1
        or request.get("package_id") != state["package_id"]
        or request.get("revision") != state["revision"]
        or request.get("plan_sha256") != state["plan_sha256"]
        or request.get("state_sha256") != canonical_hash(state)
        or request.get("current_max_agent_attempts") != budgets["max_agent_attempts"]
        or request.get("used_agent_attempts") != budgets["used_agent_attempts"]
        or request.get("reserved_later_stage_attempts") != 3
        or any(request.get(key) != value for key, value in context.items())
        or request.get("approval_basis_sha256")
        != canonical_hash({key: request[key] for key in base_fields})
        or request.get("request_sha256")
        != canonical_hash({key: request[key] for key in request if key != "request_sha256"})
    ):
        raise PlanPackageError(
            "INVALID_ATTEMPT_CONTINUATION_APPROVAL",
            "attempt continuation request binding is invalid",
        )
    response = Path(args.approval_response).read_bytes()
    if response != request["required_confirmation"].encode():
        raise PlanPackageError("APPROVAL_DENIED", "response does not exactly approve attempt continuation")
    approved_at = now_utc()
    receipt = {
        "schema_version": 1,
        "package_id": state["package_id"],
        "revision": state["revision"],
        "plan_sha256": state["plan_sha256"],
        "request_sha256": request["request_sha256"],
        "scope": request["scope"],
        "extension_attempts": context["extension_attempts"],
        "prior_max_agent_attempts": state["budgets"]["max_agent_attempts"],
        "new_max_agent_attempts": state["budgets"]["max_agent_attempts"] + context["extension_attempts"],
        "basis_attempt_id": context["basis_attempt_id"],
        "target_role": context["target_role"],
        "target_round": context["target_round"],
        "target_verification_iteration": context["target_verification_iteration"],
        "approved_at_utc": approved_at,
        "user_response_sha256": bytes_hash(response),
    }
    publish_immutable(receipt_path, canonical_bytes(receipt))
    state["budgets"]["max_agent_attempts"] = receipt["new_max_agent_attempts"]
    state.update(
        status="HARDENING",
        cap_reason=None,
        cap_reached_at_utc=None,
        cap_stage=None,
        cap_completed_verification_iteration=None,
    )
    save_state(path, state)
    return state_result(
        "continue-attempt-hardening", state, "ATTEMPT_HARDENING_CONTINUED"
    )


def finding_evidence(finding: dict[str, Any]) -> str:
    records = finding.get("evidence")
    if not isinstance(records, list) or not records:
        raise PlanPackageError("INVALID_FINDING_PROJECTION", "finding evidence is empty")
    return " | ".join(canonical_bytes(record).decode("utf-8") for record in records)


def disposition_output_hash(state: dict[str, Any], disposition: dict[str, Any]) -> str:
    role = "VERIFY_PLAN_CRITIC" if disposition["stage"] == "VERIFY_PLAN" else disposition["stage"]
    matches = [
        attempt for attempt in state["attempts"]
        if attempt.get("role") == role
        and attempt.get("round") == disposition["round"]
        and attempt.get("verification_iteration") == disposition["verification_iteration"]
        and attempt.get("status") == "SUCCEEDED"
    ]
    if len(matches) != 1 or not SHA_RE.fullmatch(str(matches[0].get("output_sha256"))):
        raise PlanPackageError("INVALID_FINDING_PROJECTION", "finding disposition lacks one assessor output")
    return matches[0]["output_sha256"]


def current_finding_rows(state: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any], str, dict[str, Any] | None]]:
    findings = {finding["id"]: finding for finding in state["findings"]}
    rows = []
    for finding_id, finding in sorted(findings.items()):
        dispositions = [item for item in state["dispositions"] if item["finding_id"] == finding_id]
        if not dispositions:
            raise PlanPackageError("INVALID_FINDING_PROJECTION", "finding lacks a disposition")
        disposition = max(dispositions, key=lambda item: item["assessment_sequence"])
        transitions = [
            item for item in state["finding_transitions"]
            if item["finding_id"] == finding_id
            and item["disposition_sequence"] == disposition["assessment_sequence"]
        ]
        if disposition["status"] == "NO_ACTION":
            if transitions:
                raise PlanPackageError("INVALID_FINDING_PROJECTION", "NO_ACTION finding has an applied transition")
            current, transition = "NO_ACTION", None
        elif disposition["status"] == "OPEN":
            if len(transitions) > 1:
                raise PlanPackageError("INVALID_FINDING_PROJECTION", "finding has multiple current transitions")
            transition = transitions[0] if transitions else None
            current = "APPLIED" if transition else "OPEN"
            if transition and (transition["from_status"], transition["to_status"]) != ("OPEN", "APPLIED"):
                raise PlanPackageError("INVALID_FINDING_PROJECTION", "finding transition is not OPEN to APPLIED")
        else:
            raise PlanPackageError("INVALID_FINDING_PROJECTION", "finding disposition status is invalid")
        rows.append((finding, disposition, current, transition))
    return rows


def aggregate_gap_projection(state: dict[str, Any], outer: dict[str, Any], package: dict[str, Any] | None) -> tuple[list[str], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    outer_gaps = outer.get("gaps")
    if not isinstance(outer_gaps, dict):
        raise PlanPackageError("INVALID_CONVERGENCE_STATE", "outer gaps must be an object")
    plan_gaps = {gap_id: gap for gap_id, gap in outer_gaps.items() if gap.get("source_stage") == "plan"}
    new_gaps: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    effective: dict[str, str] = {gap_id: gap.get("status") for gap_id, gap in plan_gaps.items()}
    projected_ids: set[str] = set()
    for finding, disposition, current, transition in current_finding_rows(state):
        finding_id = finding["id"]
        projected_ids.add(finding_id)
        persisted = plan_gaps.get(finding_id)
        if persisted is None:
            if current != "OPEN":
                raise PlanPackageError("OUTER_GAP_MISSING", "terminal finding lacks its prior outer gap")
            new_gaps.append({
                "id": finding_id, "requirement_ids": finding["requirement_ids"],
                "source_stage": "plan", "impact": finding["practical_consequence"],
                "evidence": finding_evidence(finding), "status": "open",
            })
            effective[finding_id] = "open"
            continue
        if persisted.get("status") not in {"open", "closed", "non-gap"}:
            raise PlanPackageError("OUTER_GAP_STATUS_MISMATCH", "outer plan gap status is unsupported")
        if sorted(persisted.get("requirement_ids", [])) != sorted(finding["requirement_ids"]):
            raise PlanPackageError("OUTER_GAP_IDENTITY_MISMATCH", "outer gap requirement identity changed")
        output_hash = disposition_output_hash(state, disposition)
        if current == "OPEN":
            if persisted["status"] in {"closed", "non-gap"}:
                evidence = canonical_bytes({
                    "assessment_sequence": disposition["assessment_sequence"],
                    "finding_fingerprint": finding["fingerprint"],
                    "assessor_output_sha256": output_hash,
                    "assessed_plan_sha256": disposition["assessed_plan_sha256"],
                }).decode("utf-8")
                transitions.append({"kind": "gap", "id": finding_id, "from_status": persisted["status"], "to_status": "open", "evidence": evidence})
            effective[finding_id] = "open"
        elif current == "APPLIED":
            if persisted["status"] != "open" or transition is None:
                raise PlanPackageError("OUTER_GAP_STATUS_MISMATCH", "APPLIED finding requires an open outer gap")
            evidence_record = {
                "assessment_sequence": disposition["assessment_sequence"],
                "finding_fingerprint": finding["fingerprint"],
                "finding_transition": transition,
                "corrected_plan_sha256": state["plan_sha256"],
            }
            if package is not None:
                evidence_record["manifest_sha256"] = package["manifest_sha256"]
            transitions.append({"kind": "gap", "id": finding_id, "from_status": "open", "to_status": "closed", "evidence": canonical_bytes(evidence_record).decode("utf-8")})
            effective[finding_id] = "closed"
        else:
            if persisted["status"] != "open":
                raise PlanPackageError("OUTER_GAP_STATUS_MISMATCH", "NO_ACTION finding requires an open outer gap")
            evidence = canonical_bytes({
                "assessment_sequence": disposition["assessment_sequence"],
                "finding_fingerprint": finding["fingerprint"],
                "assessor_output_sha256": output_hash,
                "decision": disposition["decision"], "rationale": disposition["rationale"],
            }).decode("utf-8")
            transitions.append({"kind": "gap", "id": finding_id, "from_status": "open", "to_status": "non-gap", "evidence": evidence})
            effective[finding_id] = "non-gap"
    unmatched = sorted(set(plan_gaps) - projected_ids)
    if unmatched:
        raise PlanPackageError("OUTER_GAP_UNMATCHED", f"outer plan gap lacks a current finding: {unmatched[0]}")
    open_ids = sorted(gap_id for gap_id, status in effective.items() if status == "open")
    closed_ids = sorted(gap_id for gap_id, status in effective.items() if status in {"closed", "non-gap"})
    return open_ids, closed_ids, new_gaps, transitions


def aggregate_blocker_projection(state: dict[str, Any], outer: dict[str, Any], package: dict[str, Any] | None) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]], bool]:
    outer_blockers = outer.get("blockers")
    if not isinstance(outer_blockers, dict):
        raise PlanPackageError("INVALID_CONVERGENCE_STATE", "outer blockers must be an object")
    inner = {item["id"]: item for item in state["blockers"]}
    plan_outer = {item_id: item for item_id, item in outer_blockers.items() if (item.get("stage") or item.get("source_stage")) == "plan"}
    mapped_ids = sorted(set(plan_outer) | {item_id for item_id, item in inner.items() if item["status"] == "OPEN"})
    new_blockers: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    effective = {item_id: plan_outer[item_id].get("status") for item_id in plan_outer}
    for blocker_id in mapped_ids:
        inner_blocker = inner.get(blocker_id)
        outer_blocker = plan_outer.get(blocker_id)
        if inner_blocker is None:
            raise PlanPackageError("OUTER_BLOCKER_UNMATCHED", "outer plan blocker lacks an inner controller blocker")
        if outer_blocker is None:
            if inner_blocker["status"] != "OPEN":
                raise PlanPackageError("OUTER_BLOCKER_MISSING", "resolved inner blocker lacks its outer record")
            blocker_type = {"EVIDENCE": "external", "RUNTIME": "execution", "APPROVAL": "approval"}[inner_blocker["type"]]
            new_blockers.append({
                "id": blocker_id, "stage": "plan", "status": "open", "type": blocker_type,
                "reason": inner_blocker["practical_impact"],
                "required_evidence": inner_blocker["required_resolution"],
            })
            effective[blocker_id] = "open"
            continue
        status = outer_blocker.get("status")
        if status not in {"open", "fixed-awaiting-verification", "verified", "closed", "superseded", "non-gap"}:
            raise PlanPackageError("OUTER_BLOCKER_STATUS_MISMATCH", "outer blocker status is unsupported")
        if package is not None and status not in {"closed", "superseded", "non-gap"}:
            if inner_blocker["status"] != "RESOLVED":
                raise PlanPackageError("INNER_BLOCKER_UNRESOLVED", "PASS package cannot advance an unresolved blocker")
            next_status = {"open": "fixed-awaiting-verification", "fixed-awaiting-verification": "verified", "verified": "closed"}[status]
            if status == "open":
                evidence_record = {"resolution": inner_blocker["resolution"]}
            elif status == "fixed-awaiting-verification":
                evidence_record = {"validate_package": package}
            else:
                evidence_record = {"manifest_sha256": package["manifest_sha256"], "plan_sha256": state["plan_sha256"]}
            transitions.append({"kind": "blocker", "id": blocker_id, "from_status": status, "to_status": next_status, "evidence": canonical_bytes(evidence_record).decode("utf-8")})
            effective[blocker_id] = next_status
    all_terminal = all(status in {"closed", "superseded", "non-gap"} for status in effective.values())
    return mapped_ids, new_blockers, transitions, all_terminal


def validate_outer_stage_result(outer_path: Path, result: dict[str, Any]) -> None:
    shared = SHARED_ROOT / "convergence_state.py"
    with tempfile.TemporaryDirectory(prefix="plan-v2-stage-result-") as raw:
        root = Path(raw)
        state_copy = root / "state.json"
        result_copy = root / "result.json"
        state_copy.write_bytes(outer_path.read_bytes())
        result_copy.write_bytes(canonical_bytes(result))
        completed = subprocess.run(
            [sys.executable, str(shared), "record-stage", str(state_copy), "--result-file", str(result_copy)],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        )
        if completed.returncode:
            evidence = completed.stderr.strip() or completed.stdout.strip() or "live record-stage rejected result"
            raise PlanPackageError("OUTER_STAGE_RESULT_INVALID", evidence)


def cmd_stage_result(args: argparse.Namespace) -> dict[str, Any]:
    state, task_root, _ = load_state(Path(args.state_json))
    outer_path = Path(args.convergence_state).resolve(strict=True)
    outer = load_json(outer_path)
    if outer.get("schema_version") != 1 or not isinstance(outer.get("outer_iteration"), int) or outer["outer_iteration"] < 1:
        raise PlanPackageError("INVALID_CONVERGENCE_STATE", "outer state identity is invalid")
    if outer.get("status") == "plan":
        pass
    elif not (outer.get("status") == "blocked" and outer.get("blocked_from_status") == "plan" and outer.get("blocked_stage") == "plan"):
        raise PlanPackageError("INVALID_CONVERGENCE_STATE", "outer state is not active at plan")
    outer_requirements = outer.get("requirements")
    if not isinstance(outer_requirements, dict):
        raise PlanPackageError("INVALID_CONVERGENCE_STATE", "outer requirements must be an object")
    requirement_ids = sorted(outer_requirements)
    if requirement_ids != sorted(requirement["id"] for requirement in state["requirements"]):
        raise PlanPackageError("CONVERGENCE_SCOPE_MISMATCH", "outer requirements differ from package")
    attempts = [
        record.get("attempt", 0) for record in outer.get("stages", {}).values()
        if record.get("stage") == "plan" and record.get("outer_iteration") == outer["outer_iteration"]
    ]
    status_verdict = {"EMITTED": "PASS", "GAPS": "GAPS", "BLOCKED": "BLOCKED", "CAP_REACHED": "CAP_REACHED"}
    if state["status"] not in status_verdict:
        raise PlanPackageError("INNER_STAGE_NOT_TERMINAL", "inner planning is not in an aggregate terminal state")
    verdict = status_verdict[state["status"]]
    package = validate_package_root(task_root) if verdict == "PASS" else None
    if package is not None:
        manifest = load_json(task_root / "manifest.json", "plan manifest")
        expected_identity = {
            "package_id": state["package_id"],
            "revision": state["revision"],
            "profile": state["profile"],
            "charter_sha256": state["charter_sha256"],
            "requirements_sha256": state["requirements_sha256"],
            "evidence_index_sha256": state["evidence_index_sha256"],
            "plan_sha256": state["plan_sha256"],
            "lens_contract_id": state["lens_contract_id"],
            "lens_contract_sha256": state["lens_contract_sha256"],
            "stage_results": state["stage_results"],
            "agent_lifecycle": state["attempts"],
        }
        if {key: manifest.get(key) for key in expected_identity} != expected_identity:
            raise PlanPackageError("PACKAGE_STATE_MISMATCH", "emitted package does not bind the current controller state")
    if args.package_directory and Path(args.package_directory).resolve(strict=True) != task_root:
        raise PlanPackageError("PACKAGE_ROOT_MISMATCH", "supplied package directory differs from controller task root")
    open_gaps, closed_gaps, new_gaps, gap_transitions = aggregate_gap_projection(state, outer, package)
    owned_blockers, new_blockers, blocker_transitions, all_blockers_terminal = aggregate_blocker_projection(state, outer, package)
    if verdict == "BLOCKED" and not owned_blockers:
        raise PlanPackageError("INVALID_BLOCKER_PROJECTION", "inner BLOCKED state has no mapped blocker")
    if package is not None and outer["status"] == "blocked":
        verdict = "PASS" if all_blockers_terminal else "BLOCKED"
    artifact_paths = [str(task_root / "manifest.json")] if verdict == "PASS" else []
    evidence = [f"plan-state-sha256:{canonical_hash(state)}", f"inner-status:{state['status']}"]
    if package is not None and outer["status"] == "blocked" and all_blockers_terminal and owned_blockers:
        evidence.append(f"resume-anchor:{owned_blockers[0]}")
    result = {
        "stage": "plan", "iteration": outer["outer_iteration"], "attempt": max(attempts, default=0) + 1,
        "assigned_requirement_ids": requirement_ids,
        "assigned_gap_ids": sorted(set(open_gaps) | set(closed_gaps)),
        "owned_blocker_ids": owned_blockers, "verdict": verdict,
        "open_gap_ids": open_gaps, "closed_gap_ids": closed_gaps,
        "new_gaps": new_gaps, "new_blockers": new_blockers,
        "record_transitions": gap_transitions + blocker_transitions,
        "evidence": evidence,
        "artifact_paths": artifact_paths,
    }
    validate_outer_stage_result(outer_path, result)
    atomic_json(Path(args.out), result)
    return state_result("stage-result", state, "STAGE_RESULT_PREPARED")


def validate_resume_bundle(bundle: Path, state: dict[str, Any]) -> dict[str, Any]:
    manifest = require_exact(load_json(bundle / "resume-bundle.json", "resume bundle manifest"), {"schema_version", "blocked_state_sha256", "entry_mode", "resolution_evidence_sha256", "direct_evidence", "supplied_input_tree", "research_package", "owned_files"}, "resume bundle manifest")
    if manifest["schema_version"] != 1 or manifest["blocked_state_sha256"] != canonical_hash(state) or manifest["entry_mode"] != state["entry_mode"]:
        raise PlanPackageError("RESUME_BASIS_DRIFT", "resume bundle does not bind the blocked state")
    owned = manifest["owned_files"]
    if not isinstance(owned, list) or owned != sorted(owned, key=lambda row: row.get("path", "")):
        raise PlanPackageError("INVALID_RESUME_BUNDLE", "owned files must be a sorted array")
    expected = {"resume-bundle.json"}
    for row in owned:
        require_exact(row, {"path", "sha256"}, "resume owned file")
        file = contained_file(bundle, row["path"], "resume owned file")
        if not SHA_RE.fullmatch(str(row["sha256"])) or bytes_hash(file.read_bytes()) != row["sha256"]:
            raise PlanPackageError("RESUME_BUNDLE_TAMPER", f"resume file changed: {row['path']}")
        expected.add(row["path"])
    present = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()}
    if present != expected:
        raise PlanPackageError("INVALID_RESUME_BUNDLE", "resume bundle file set mismatch")
    resolution = load_json(bundle / "resolution-evidence.json", "resolution evidence")
    if canonical_hash(resolution) != manifest["resolution_evidence_sha256"]:
        raise PlanPackageError("RESUME_BUNDLE_TAMPER", "resolution evidence hash mismatch")
    if state["entry_mode"] == "DIRECT":
        direct = require_exact(manifest["direct_evidence"], {"path", "sha256"}, "direct resume evidence")
        if direct["path"] != "evidence-index.json" or bytes_hash((bundle / direct["path"]).read_bytes()) != direct["sha256"] or manifest["research_package"] is not None:
            raise PlanPackageError("INVALID_RESUME_BUNDLE", "DIRECT resume evidence is invalid")
    else:
        research = require_exact(manifest["research_package"], {"path", "tree_sha256", "manifest_sha256"}, "research resume package")
        tree, _, _ = shared_contracts()
        package_root = resolve_dir(bundle / research["path"], "bundled research package")
        if tree.TREE_SHA256_V1(package_root) != research["tree_sha256"] or bytes_hash((package_root / "manifest.json").read_bytes()) != research["manifest_sha256"] or manifest["direct_evidence"] is not None:
            raise PlanPackageError("INVALID_RESUME_BUNDLE", "research resume package is invalid")
    return manifest


def cmd_prepare_resume_bundle(args: argparse.Namespace) -> dict[str, Any]:
    state, _, run_root = load_state(Path(args.state_json))
    if state["status"] != "BLOCKED": raise PlanPackageError("INVALID_TRANSITION", "resume bundle requires BLOCKED")
    blocked_hash = canonical_hash(state); expected = run_root / "resume" / blocked_hash / "bundle"
    if Path(args.bundle_dir).absolute() != expected: raise PlanPackageError("OUTPUT_PATH_MISMATCH", "resume bundle path is deterministic")
    resolution = load_json(Path(args.resolution_evidence))
    if expected.exists():
        manifest = validate_resume_bundle(resolve_dir(expected, "resume bundle"), state)
        if manifest["resolution_evidence_sha256"] != canonical_hash(resolution): raise PlanPackageError("CONFLICTING_REPLAY", "resolution evidence changed")
        if args.evidence_index:
            if manifest["direct_evidence"] is None or bytes_hash(Path(args.evidence_index).read_bytes()) != manifest["direct_evidence"]["sha256"]: raise PlanPackageError("CONFLICTING_REPLAY", "direct evidence changed")
        elif args.research_package:
            package = research_owner().validate_package(args.research_package)
            tree, _, _ = shared_contracts()
            if manifest["research_package"] is None or tree.TREE_SHA256_V1(Path(package["package_root"])) != manifest["research_package"]["tree_sha256"]: raise PlanPackageError("CONFLICTING_REPLAY", "research package changed")
        else: raise PlanPackageError("ENTRY_ARGUMENT_CONFLICT", "resume bundle requires mode-owned evidence")
        return state_result("prepare-resume-bundle", state, "RESUME_BUNDLE_ALREADY_PREPARED")
    staging = expected.with_name("bundle.staging"); shutil.rmtree(staging, ignore_errors=True); staging.mkdir(parents=True)
    atomic_json(staging / "resolution-evidence.json", resolution)
    if args.research_package:
        package = research_owner().validate_package(args.research_package); shutil.copytree(Path(package["package_root"]), staging / "research-package")
    elif args.evidence_index:
        shutil.copy2(args.evidence_index, staging / "evidence-index.json")
    else: raise PlanPackageError("ENTRY_ARGUMENT_CONFLICT", "resume bundle requires mode-owned evidence")
    tree, _, _ = shared_contracts(); owned = [{"path": p.relative_to(staging).as_posix(), "sha256": bytes_hash(p.read_bytes())} for p in sorted(staging.rglob("*")) if p.is_file()]
    manifest = {"schema_version": 1, "blocked_state_sha256": blocked_hash, "entry_mode": state["entry_mode"], "resolution_evidence_sha256": canonical_hash(resolution), "direct_evidence": {"path": "evidence-index.json", "sha256": bytes_hash((staging / "evidence-index.json").read_bytes())} if args.evidence_index else None, "supplied_input_tree": None, "research_package": {"path": "research-package", "tree_sha256": tree.TREE_SHA256_V1(staging / "research-package"), "manifest_sha256": bytes_hash((staging / "research-package/manifest.json").read_bytes())} if args.research_package else None, "owned_files": owned}
    atomic_json(staging / "resume-bundle.json", manifest); os.replace(staging, expected); fsync_dir(expected.parent)
    return state_result("prepare-resume-bundle", state, "RESUME_BUNDLE_PREPARED")


def cmd_resume(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.state_json); state, _, _ = load_state(path)
    if state["status"] != "BLOCKED": raise PlanPackageError("INVALID_TRANSITION", "resume requires BLOCKED")
    bundle = resolve_dir(Path(args.resume_bundle), "resume bundle"); validate_resume_bundle(bundle, state)
    resolution = load_json(bundle / "resolution-evidence.json")
    if state["revision"] == 0:
        if state["entry_mode"] == "RESEARCH_PACKAGE":
            package = research_owner().validate_package(bundle / "research-package"); state["requirements"] = validate_requirements(package["requirements"], direct=False); state["requirements_sha256"] = canonical_hash(state["requirements"]); state["evidence_index_sha256"] = canonical_hash(package["evidence_index"])
        state["status"] = "INITIALIZED"
    else: state["status"] = "HARDENING"
    for blocker in state["blockers"]:
        if blocker["status"] == "OPEN": blocker.update(status="RESOLVED", resolution=resolution)
    save_state(path, state); return state_result("resume", state, "RESUMED")


def cmd_show(args: argparse.Namespace) -> dict[str, Any]:
    state, _, _ = load_state(Path(args.state_json)); return state


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__); sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("hash-json"); p.add_argument("json_file"); p.set_defaults(handler=cmd_hash_json)
    p = sub.add_parser("migrate-run-root"); p.add_argument("--task-directory", required=True); p.set_defaults(handler=cmd_migrate_run_root)
    p = sub.add_parser("init"); p.add_argument("state_json"); p.add_argument("--task-directory", required=True); p.add_argument("--charter", required=True); p.add_argument("--entry-mode", choices=["DIRECT", "RESEARCH_PACKAGE"], required=True); p.add_argument("--task-size", choices=["light", "standard", "heavy"], required=True); p.add_argument("--approval-context", choices=["ORDINARY", "CONVERGENCE"], required=True); p.add_argument("--convergence-state"); p.add_argument("--requirements"); p.add_argument("--evidence-index"); p.add_argument("--supplied-input-root"); p.add_argument("--research-package"); p.set_defaults(handler=cmd_init)
    p = sub.add_parser("prepare-resume-bundle"); p.add_argument("state_json"); p.add_argument("--evidence-index"); p.add_argument("--supplied-input-root"); p.add_argument("--research-package"); p.add_argument("--resolution-evidence", required=True); p.add_argument("--bundle-dir", required=True); p.set_defaults(handler=cmd_prepare_resume_bundle)
    p = sub.add_parser("resume"); p.add_argument("state_json"); p.add_argument("--resume-bundle", required=True); p.set_defaults(handler=cmd_resume)
    p = sub.add_parser("scope-check"); p.add_argument("state_json"); p.add_argument("--charter", required=True); p.add_argument("--requirements"); p.add_argument("--evidence-index"); p.add_argument("--research-package"); p.set_defaults(handler=cmd_scope_check)
    p = sub.add_parser("record-draft"); p.add_argument("state_json"); p.add_argument("--plan", required=True); p.add_argument("--surface-map", required=True); p.add_argument("--decisions", required=True); p.add_argument("--verification-ledger", required=True); p.set_defaults(handler=cmd_record_draft)
    p = sub.add_parser("prepare-attempt"); p.add_argument("state_json"); p.add_argument("--round", type=int, required=True); p.add_argument("--role", choices=ROLES, required=True); p.add_argument("--verification-iteration", type=int, required=True); p.add_argument("--assigned-coverage-id", action="append"); p.add_argument("--assigned-obligation-id", action="append"); p.add_argument("--slot-id", required=True); p.add_argument("--slot-ledger", required=True); p.add_argument("--input-envelope", required=True); p.add_argument("--out", required=True); p.set_defaults(handler=cmd_prepare_attempt)
    p = sub.add_parser("finalize-attempt"); p.add_argument("state_json"); p.add_argument("--attempt-token", required=True); p.add_argument("--slot-ledger", required=True); p.add_argument("--status", choices=sorted(TERMINAL_ATTEMPT_STATUSES), required=True); p.add_argument("--runtime-agent-id"); p.add_argument("--output"); p.set_defaults(handler=cmd_finalize_attempt)
    p = sub.add_parser("escalate-profile"); p.add_argument("state_json"); p.add_argument("--attempt-token", required=True); p.set_defaults(handler=cmd_escalate_profile)
    p = sub.add_parser("record-runtime-blocker"); p.add_argument("state_json"); p.add_argument("--runtime-evidence", required=True); p.set_defaults(handler=cmd_record_runtime_blocker)
    p = sub.add_parser("materialize-artifact"); p.add_argument("state_json"); p.add_argument("--attempt-token", required=True); p.add_argument("--role-output", required=True); p.add_argument("--task-directory", required=True); p.set_defaults(handler=cmd_materialize_artifact)
    p = sub.add_parser("record-stage"); p.add_argument("state_json"); p.add_argument("--round", type=int, required=True); p.add_argument("--stage", choices=STAGES, required=True); p.add_argument("--source-attempt-id"); p.add_argument("--artifact"); p.set_defaults(handler=cmd_record_stage)
    p = sub.add_parser("record-findings"); p.add_argument("state_json"); p.add_argument("--round", type=int, required=True); p.add_argument("--stage", choices=STAGES, required=True); p.add_argument("--primary-output", required=True); p.add_argument("--critic-output"); p.set_defaults(handler=cmd_record_findings)
    p = sub.add_parser("record-verification-ledger"); p.add_argument("state_json"); p.add_argument("--ledger", required=True); p.add_argument("--expected-current-sha256", required=True); p.set_defaults(handler=cmd_record_verification_ledger)
    p = sub.add_parser("project-verify-plan-ledger"); p.add_argument("state_json"); p.add_argument("--ledger", required=True); p.add_argument("--verifier-output", required=True); p.add_argument("--critic-output", required=True); p.add_argument("--out", required=True); p.set_defaults(handler=cmd_project_verify_plan_ledger)
    p = sub.add_parser("render-verify-summary"); p.add_argument("state_json"); p.add_argument("--out", required=True); p.set_defaults(handler=cmd_render_verify_summary)
    p = sub.add_parser("prepare-continuation-approval"); p.add_argument("state_json"); p.add_argument("--convergence-state", required=True); p.add_argument("--outer-approval-id", required=True); p.add_argument("--outer-operation-id", required=True); p.add_argument("--out", required=True); p.set_defaults(handler=cmd_prepare_continuation_approval)
    p = sub.add_parser("continue-hardening"); p.add_argument("state_json"); p.add_argument("--approval", required=True); p.set_defaults(handler=cmd_continue_hardening)
    p = sub.add_parser("prepare-deadline-continuation-approval"); p.add_argument("state_json"); p.add_argument("--out", required=True); p.set_defaults(handler=cmd_prepare_deadline_continuation_approval)
    p = sub.add_parser("continue-deadline-hardening"); p.add_argument("state_json"); p.add_argument("--request", required=True); p.add_argument("--approval-response", required=True); p.set_defaults(handler=cmd_continue_deadline_hardening)
    p = sub.add_parser("prepare-attempt-continuation-approval"); p.add_argument("state_json"); p.add_argument("--out", required=True); p.set_defaults(handler=cmd_prepare_attempt_continuation_approval)
    p = sub.add_parser("continue-attempt-hardening"); p.add_argument("state_json"); p.add_argument("--request", required=True); p.add_argument("--approval-response", required=True); p.set_defaults(handler=cmd_continue_attempt_hardening)
    p = sub.add_parser("prepare-revision"); p.add_argument("state_json"); p.add_argument("--evidence-index"); p.add_argument("--research-package"); p.set_defaults(handler=cmd_prepare_revision)
    p = sub.add_parser("record-revision"); p.add_argument("state_json"); p.add_argument("--proposal", required=True); p.add_argument("--closed-finding-id", action="append"); p.set_defaults(handler=cmd_record_revision)
    p = sub.add_parser("emit-package"); p.add_argument("state_json"); p.add_argument("task_directory"); p.set_defaults(handler=cmd_emit_package)
    p = sub.add_parser("validate-package"); p.add_argument("task_directory"); p.set_defaults(handler=cmd_validate_package)
    p = sub.add_parser("prepare-implementation-authorization"); p.add_argument("state_json"); p.add_argument("--out", required=True); p.set_defaults(handler=cmd_prepare_implementation_authorization)
    p = sub.add_parser("record-implementation-authorization"); p.add_argument("state_json"); p.add_argument("--request", required=True); p.add_argument("--approval-response"); p.add_argument("--convergence-state"); p.set_defaults(handler=cmd_record_implementation_authorization)
    p = sub.add_parser("validate-implementation-authorization"); p.add_argument("state_json"); p.add_argument("--authorization", required=True); p.set_defaults(handler=cmd_validate_implementation_authorization)
    p = sub.add_parser("stage-result"); p.add_argument("state_json"); p.add_argument("--convergence-state", required=True); p.add_argument("--package-directory"); p.add_argument("--out", required=True); p.set_defaults(handler=cmd_stage_result)
    p = sub.add_parser("show"); p.add_argument("state_json"); p.set_defaults(handler=cmd_show)
    return root


def failure(command: str, code: str, state_path: str | None) -> dict[str, Any]:
    digest = status = None
    if state_path:
        try:
            raw = load_json(Path(state_path)); digest = canonical_hash(raw); status = raw.get("status") if isinstance(raw, dict) else None
        except Exception: pass
    if code == "SCOPE_CHANGED":
        status = "BLOCKED"
    return {"schema_version": 1, "command": command, "ok": False, "status": status, "state_sha256": digest, "code": code}


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv); command = args.command
    try:
        result = args.handler(args)
        sys.stdout.buffer.write(canonical_bytes(result) + b"\n")
        return 0
    except PlanPackageError as exc:
        state_path = getattr(args, "state_json", None)
        sys.stdout.buffer.write(canonical_bytes(failure(command, exc.code, state_path)) + b"\n")
        return 2
    except Exception:
        state_path = getattr(args, "state_json", None)
        sys.stdout.buffer.write(canonical_bytes(failure(command, "INTERNAL_ERROR", state_path)) + b"\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
