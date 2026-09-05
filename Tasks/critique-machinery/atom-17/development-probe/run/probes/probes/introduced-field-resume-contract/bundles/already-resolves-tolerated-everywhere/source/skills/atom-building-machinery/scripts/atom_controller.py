#!/usr/bin/env python3
"""Enforce the evidence-gated lifecycle of one approved implementation atom."""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from datetime import date as calendar_date, datetime
from pathlib import Path
from typing import Any

MODULE_ROOT = Path(__file__).resolve().parents[3]

CONTRACT = 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXPERIMENT_STAGES = ["run-probes", "compose-winners", "final-validation"]
EXPERIMENT_VERDICTS = {"passed", "failed", "inconclusive"}
CASE_VERDICTS = {"satisfied", "not-satisfied", "cannot-assess"}
LEGACY_REQUEST_FIELDS = {
    "schema_version",
    "atomic_step_id",
    "outcome",
    "practical_value",
    "stopping_condition",
    "allowed_paths",
    "captured_cases",
}
REQUEST_FIELDS = {
    "schema_version",
    "atomic_step_id",
    "outcome",
    "practical_value",
    "stopping_condition",
    "allowed_paths",
    "captured_cases",
    "contract_surface",
}
REQUEST_OPTIONAL_FIELDS = {"prose_waiver"}
CONTRACT_SURFACE_RENDER_FIELDS = {"kind"}
CONTRACT_SURFACE_VALIDATION_FIELDS = {"kind", "deliverable", "fields"}
CONTRACT_FIELD_FIELDS = {"field", "shape", "shape_source"}
#: Atom 16 (2026-09-05): a field the atom itself introduces. Its parent must resolve at start,
#: its leaf must not exist yet, and the leaf must resolve at record-promotion.
CONTRACT_FIELD_OPTIONAL_FIELDS = {"introduced"}
PROSE_WAIVER_FIELDS = {"operator", "words", "date", "presence_proof"}
LEGACY_PROSE_WAIVER_FIELDS = {"by", "words", "date"}
OPERATOR_FIELDS = {
    "login_user", "uid", "approval_ui", "authentication_policy", "client_projection",
    "helper_path", "helper_sha256", "parent_process_name", "parent_process_pid",
    "observed_at", "initiating_harness_markers",
}
PRESENCE_PROOF_FIELDS = {
    "scheme", "service", "helper_version", "helper_sha256", "signed_payload_base64",
    "signed_payload_sha256", "nonce", "digest",
}
NATIVE_AUTHORIZATION_FIELDS = {
    "schema_version", "status", "helper_version", "service", "signed_payload_base64",
    "signed_payload_sha256", "nonce", "digest",
}
LEGACY_SIGNED_AUTHORIZATION_FIELDS = {
    "schema_version", "request_sha256", "repository_root", "fields", "meanings",
    "choice", "adopted_statement", "date", "operator",
}
SIGNED_AUTHORIZATION_FIELDS = LEGACY_SIGNED_AUTHORIZATION_FIELDS | {"atomic_step_id"}
PROSE_WAIVER_RECEIPT_FIELDS = {
    "schema_version", "status", "request_sha256", "repository_root", "fields",
    "operator", "words", "date", "presence_proof", "operator_choice", "answer_event_sha256",
}
KEYCHAIN_SERVICE = "memory-knowledge.atom-building.prose-waiver.native-v1"
PRESENCE_SCHEME = "native-macos-device-owner-hmac-v1"
NATIVE_HELPER_VERSION = 1
NATIVE_HELPER_NAME = "prose_waiver_approval"
MODEL_HARNESS_MARKERS = (
    "CLAUDECODE",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_PID",
    "CODEX_APP_TOOLS_PIPE_PATH",
    "CODEX_CI",
    "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
    "CODEX_MCP_NODE_PATH",
    "CODEX_PERMISSION_PROFILE",
    "CODEX_SAGE_BACKFILL_TRACKER_TAB_REUSE",
    "CODEX_SANDBOX_NETWORK_DISABLED",
    "CODEX_SESSION_ID",
    "CODEX_SHELL",
    "CODEX_THREAD_ID",
)
CONTRACT_SHAPES = {"list", "object", "enum", "integer", "pinned-string", "prose"}
CASE_FIELDS = {"case_id", "source_ref", "sha256", "kind", "expected_outcome"}
EVIDENCE_FIELDS = {"case_id", "path", "sha256"}
FILE_REFERENCE_FIELDS = {"path", "sha256"}
BASELINE_FIELDS = {"schema_version", "atomic_step_id", "repository_root", "allowed_paths", "files"}
SNAPSHOT_FILE_FIELDS = {"path", "sha256", "size", "mode"}
SUPERSESSION_FIELDS = {"schema_version", "atomic_step_id", "previous_run", "chain"}
SUPERSESSION_LINK_FIELDS = {
    "run", "request_sha256", "baseline_sha256", "latest_event_sha256",
}
CHAIN_CLOSED_EVENT_FIELDS = {"supersession_chain", "proof_event_sha256"}
CHANGE_SURFACE_FIELDS = {
    "schema_version",
    "atomic_step_id",
    "repository_root",
    "baseline_sha256",
    "changes",
}
REVIEW_FIELDS = {
    "schema_version",
    "status",
    "verdict",
    "change_surface_sha256",
    "blocking_findings",
}
FINAL_FIELDS = {
    "schema_version",
    "status",
    "atomic_step_id",
    "assembly_sha256",
    "verdict",
    "cases",
    "promotion_applied",
}
EXPERIMENT_CASE_FIELDS = {"case_id", "verdict", "reason", "evidence_pointers"}
VALIDATION_CASE_FIELDS = {"case_id", "verdict", "reason", "evidence"}
CASE_EVIDENCE_FIELDS = {"case_id", "evidence"}
SUMMARY_FIELDS = {
    "schema_version",
    "status",
    "atomic_step_id",
    "verdict",
    "final_verdict_sha256",
    "stages",
    "promotion_applied",
}
LEGACY_STAGE_FIELDS = {
    "schema_version",
    "stage",
    "status",
    "exit_code",
    "output",
    "evidence",
    "evidence_sha256",
    "result",
    "result_sha256",
    "promotion_applied",
}
CURRENT_STAGE_FIELDS = LEGACY_STAGE_FIELDS | {
    "duration_ms",
    "timeout_ms",
    "timed_out",
    "stdout_sha256",
    "stderr_sha256",
    "timeout",
    "timeout_sha256",
}
LEGACY_PROMOTION_FIELDS = {
    "schema_version",
    "status",
    "atomic_step_id",
    "controller",
    "experiment_event_sha256",
    "experiment_assembly_sha256",
    "changed_paths",
    "evidence",
}
PROMOTION_FIELDS = LEGACY_PROMOTION_FIELDS | {"change_surface", "review"}
VALIDATION_FIELDS = {
    "schema_version",
    "status",
    "atomic_step_id",
    "promotion_event_sha256",
    "cases",
}
LEDGER_FIELDS = {"sequence", "event", "previous_event_sha256", "payload"}
EXPERIMENT_EVENT_FIELDS = {
    "experiment_path",
    "summary_sha256",
    "final_verdict_sha256",
    "assembly_sha256",
    "verdict",
}
CONTRACT_EXPERIMENT_EVENT_FIELDS = EXPERIMENT_EVENT_FIELDS | {"contract_scan"}
LEGACY_PROMOTION_EVENT_FIELDS = {
    "receipt_path",
    "receipt_sha256",
    "experiment_event_sha256",
    "assembly_sha256",
    "changed_paths",
    "evidence",
}
PROMOTION_EVENT_FIELDS = LEGACY_PROMOTION_EVENT_FIELDS | {"change_surface", "review"}
CONTRACT_PROMOTION_FIELDS = PROMOTION_FIELDS | {"contract_surface"}
CONTRACT_PROMOTION_EVENT_FIELDS = PROMOTION_EVENT_FIELDS | {"contract_surface"}
LEGACY_VALIDATION_EVENT_FIELDS = {
    "receipt_path",
    "receipt_sha256",
    "promotion_event_sha256",
    "verdict",
    "case_evidence",
}
VALIDATION_EVENT_FIELDS = LEGACY_VALIDATION_EVENT_FIELDS | {"blocker_closeout"}
BLOCKER_CLOSEOUT_FIELDS = {
    "schema_version", "atomic_step_id", "atom_request_sha256", "atom_run_id",
    "work_memory_ledger_sha256", "clear", "linked_occurrence_count",
    "blocking_occurrence_count", "blocking_occurrences", "dispositions",
}
MANAGED_SOURCE_RECORD_FIELDS = {
    "schema_version", "source_repository_root", "support_files",
}
BLOCKER_SUPPORT_FILES = (
    "scripts/blocker_catalog.py",
    "scripts/work_memory.py",
)
MANAGED_SOURCE_RECORD_NAME = ".managed-skills-source.json"


class AtomError(RuntimeError):
    """The atom lifecycle cannot safely advance."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def _document(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load(path: Path, label: str, stage: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AtomError(stage, f"{label} is unavailable or invalid JSON: {error}") from None
    if type(value) is not dict:
        raise AtomError(stage, f"{label} is {type(value).__name__}; provide one JSON object")
    return value


def _exact(value: object, label: str, fields: set[str], stage: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise AtomError(stage, f"{label} is {type(value).__name__}; provide one object")
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        raise AtomError(
            stage,
            f"{label} has missing fields {missing} and unexpected fields {extra}; "
            "add the missing fields and remove the unexpected fields",
        )
    return value


def _nonempty(value: object, label: str, stage: str) -> str:
    if type(value) is not str or not value.strip():
        raise AtomError(stage, f"{label} is {value!r}; provide one nonempty string")
    return value


def _sha(value: object, label: str, stage: str) -> str:
    if type(value) is not str or not SHA256.fullmatch(value):
        raise AtomError(stage, f"{label} is {value!r}; provide 64 lowercase hexadecimal characters")
    return value


def _strings(value: object, label: str, stage: str, *, nonempty: bool = True) -> list[str]:
    if type(value) is not list or (nonempty and not value):
        qualifier = "nonempty " if nonempty else ""
        raise AtomError(stage, f"{label} is {value!r}; provide one {qualifier}ordered list of strings")
    result = []
    for index, item in enumerate(value):
        result.append(_nonempty(item, f"{label}[{index}]", stage))
    if len(set(result)) != len(result):
        raise AtomError(stage, f"{label} contains duplicates; keep every value exactly once")
    return result


def _evidence(
    value: object,
    label: str,
    stage: str,
    case_ids: set[str],
    *,
    base: Path | None = None,
    required_case_id: str | None = None,
    verify_hashes: bool = True,
) -> list[dict[str, str]]:
    if type(value) is not list or not value:
        raise AtomError(stage, f"{label} is {value!r}; provide one nonempty ordered evidence list")
    normalized = []
    identities = []
    for index, raw in enumerate(value):
        item_label = f"{label}[{index}]"
        item = _exact(raw, item_label, EVIDENCE_FIELDS, stage)
        case_id = _nonempty(item["case_id"], f"{item_label}.case_id", stage)
        if case_id not in case_ids:
            raise AtomError(stage, f"{item_label}.case_id is {case_id!r}; require one declared captured case")
        if required_case_id is not None and case_id != required_case_id:
            raise AtomError(stage, f"{item_label}.case_id is {case_id!r}; require {required_case_id!r}")
        path_text = _nonempty(item["path"], f"{item_label}.path", stage)
        path = Path(path_text)
        if not path.is_absolute():
            if base is None:
                raise AtomError(stage, f"{item_label}.path is relative; restore the recorded absolute evidence path")
            path = base / path
        path = path.absolute()
        expected = _sha(item["sha256"], f"{item_label}.sha256", stage)
        if path.is_symlink() or not path.is_file():
            raise AtomError(stage, f"{label} is unavailable or linked at {path}; provide the recorded regular file")
        actual = _digest(path.read_bytes())
        if verify_hashes and actual != expected:
            raise AtomError(stage, f"{label} has SHA-256 {actual} at {path}; require recorded {expected}")
        identity = (case_id, str(path))
        if identity in identities:
            raise AtomError(stage, f"{label} repeats case {case_id!r} path {str(path)!r}; keep each proof once")
        identities.append(identity)
        normalized.append({"case_id": case_id, "path": str(path), "sha256": expected})
    return normalized


def _case_evidence(
    value: object,
    label: str,
    stage: str,
    declared_case_ids: list[str],
    *,
    verify_hashes: bool = True,
) -> list[dict[str, object]]:
    if type(value) is not list:
        raise AtomError(stage, f"{label} is not one ordered list")
    normalized = []
    observed = []
    case_ids = set(declared_case_ids)
    for index, raw in enumerate(value):
        item = _exact(raw, f"{label}[{index}]", CASE_EVIDENCE_FIELDS, stage)
        case_id = _nonempty(item["case_id"], f"{label}[{index}].case_id", stage)
        observed.append(case_id)
        normalized.append(
            {
                "case_id": case_id,
                "evidence": _evidence(
                    item["evidence"],
                    f"{label}[{index}].evidence",
                    stage,
                    case_ids,
                    required_case_id=case_id,
                    verify_hashes=verify_hashes,
                ),
            }
        )
    if observed != declared_case_ids:
        raise AtomError(stage, f"{label} cases are {observed!r}; require exact order {declared_case_ids!r}")
    return normalized


def _relative_path(value: str, label: str, stage: str) -> str:
    path = Path(value)
    if path.is_absolute() or value in {"", "."} or ".." in path.parts:
        raise AtomError(stage, f"{label} is {value!r}; provide one safe repository-relative path")
    return path.as_posix().rstrip("/")


def _exact_with_optional(
    value: object,
    label: str,
    required: set[str],
    optional: set[str],
    stage: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise AtomError(stage, f"{label} is {type(value).__name__}; provide one object")
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required - optional)
    if missing or extra:
        raise AtomError(
            stage,
            f"{label} has missing fields {missing} and unexpected fields {extra}; "
            "add the missing fields and remove the unexpected fields",
        )
    return value


def _literal_strings(node: ast.AST) -> list[str] | None:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    values: list[str] = []
    for item in node.elts:
        if not isinstance(item, ast.Constant) or type(item.value) is not str:
            return None
        values.append(item.value)
    return values


def _module_contract(path: Path, stage: str) -> tuple[dict[str, list[str]], set[str]]:
    if path.is_symlink() or not path.is_file():
        raise AtomError(stage, f"deliverable schema is unavailable or linked at {path}")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as error:
        raise AtomError(stage, f"deliverable schema cannot be inspected at {path}: {error}") from None
    collections: dict[str, list[str]] = {}
    compiled_forms: set[str] = set()
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        target = statement.target if isinstance(statement, ast.AnnAssign) else (
            statement.targets[0] if len(statement.targets) == 1 else None
        )
        if not isinstance(target, ast.Name) or statement.value is None:
            continue
        strings = _literal_strings(statement.value)
        if strings is not None:
            collections[target.id] = strings
            continue
        call = statement.value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "re"
            and call.func.attr == "compile"
        ):
            compiled_forms.add(target.id)
    return collections, compiled_forms


def _field_segments(field: str, label: str, stage: str) -> list[str]:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)*", field):
        raise AtomError(stage, f"{label} is {field!r}; provide a dotted field path with optional [] list markers")
    return [part.removesuffix("[]") for part in field.split(".")]


def _available_nested_keys(collections: dict[str, list[str]], root: str) -> list[str]:
    explicit = {
        "activation_cards": "ACTIVATION_CARD_FIELDS",
        "ownership": "OWNERSHIP_FIELDS",
        "calendar": "CALENDAR_FIELDS",
    }.get(root)
    candidates = [explicit, f"{root.upper()}_FIELDS"]
    if root.endswith("s"):
        candidates.append(f"{root[:-1].upper()}_FIELDS")
    for candidate in candidates:
        if candidate in collections:
            return collections[candidate]
    return []


def _resolve_contract_field(
    item: dict[str, Any],
    deliverable: str,
    repository_root: Path,
    label: str,
    stage: str,
    *,
    require_introduced_resolved: bool = False,
) -> dict[str, Any]:
    field = _nonempty(item["field"], f"{label}.field", stage)
    introduced = bool(item.get("introduced"))
    pending = introduced and not require_introduced_resolved
    shape = item["shape"]
    if shape not in CONTRACT_SHAPES:
        raise AtomError(stage, f"{label}.shape is {shape!r}; choose one of {sorted(CONTRACT_SHAPES)!r}")
    source = _nonempty(item["shape_source"], f"{label}.shape_source", stage)
    if source.count("::") != 1:
        raise AtomError(stage, f"{label}.shape_source is {source!r}; provide repository/path.py::CONSTANT")
    source_path_text, constant = source.split("::")
    source_path_text = _relative_path(source_path_text, f"{label}.shape_source path", stage)
    constant = _nonempty(constant, f"{label}.shape_source constant", stage)
    source_path = repository_root / source_path_text
    if source_path.stem != deliverable:
        raise AtomError(
            stage,
            f"{label}.deliverable is {deliverable!r} but shape_source names module {source_path.stem!r}",
        )
    collections, compiled_forms = _module_contract(source_path, stage)
    segments = _field_segments(field, f"{label}.field", stage)
    section_keys = collections.get("SECTION_KEYS")
    if section_keys is None:
        section_keys = sorted({
            item
            for name, values in collections.items()
            if name.endswith("_FIELDS")
            for item in values
        })
    if segments[0] not in section_keys:
        if pending and len(segments) == 1:
            pass  # a top-level field the atom introduces; its parent is the deliverable itself
        elif introduced:
            raise AtomError(
                stage,
                f"introduced field {field!r} still does not resolve at {segments[0]!r} at {stage}; the "
                f"canonical module must carry it before the promotion receipt is recorded; available "
                f"deliverable keys are {sorted(section_keys)!r}",
            )
        else:
            raise AtomError(
                stage,
                f"field {field!r} does not resolve at {segments[0]!r}; available deliverable keys are {sorted(section_keys)!r}",
            )
    elif pending and len(segments) == 1 and False:
        raise AtomError(
            stage,
            f"introduced field {field!r} already resolves at {segments[0]!r}; declare it without 'introduced'",
        )
    if len(segments) > 1:
        nested = _available_nested_keys(collections, segments[0])
        if segments[1] not in nested:
            if pending:
                pass  # the leaf the atom introduces; its parent resolved above
            elif introduced:
                raise AtomError(
                    stage,
                    f"introduced field {field!r} still does not resolve at {segments[1]!r} at {stage}; the "
                    f"canonical module must carry it before the promotion receipt is recorded; available "
                    f"keys are {sorted(nested)!r}",
                )
            else:
                raise AtomError(
                    stage,
                    f"field {field!r} does not resolve at {segments[1]!r}; available keys are {sorted(nested)!r}",
                )
        elif pending and False:
            raise AtomError(
                stage,
                f"introduced field {field!r} already resolves at {segments[1]!r}; declare it without 'introduced'",
            )
    if constant not in collections and constant not in compiled_forms:
        available = sorted(set(collections) | compiled_forms)
        raise AtomError(
            stage,
            f"field {field!r} names missing shape constant {constant!r}; available constants are {available!r}",
        )
    if shape == "enum" and constant not in collections:
        raise AtomError(stage, f"field {field!r} shape enum requires a named string collection, not {constant!r}")
    if shape == "pinned-string" and constant not in compiled_forms:
        raise AtomError(stage, f"field {field!r} shape pinned-string requires a named compiled whole-value form")
    if shape not in {"enum", "pinned-string"}:
        if constant not in collections:
            raise AtomError(stage, f"field {field!r} shape {shape} requires a named string field collection")
        target = segments[-1]
        if not pending and target not in collections[constant] and segments[0] not in collections[constant]:
            raise AtomError(
                stage,
                f"field {field!r} is not named by shape constant {constant!r}; "
                f"that constant provides {collections[constant]!r}",
            )
    resolved: dict[str, Any] = {"field": field, "shape": shape, "shape_source": f"{source_path_text}::{constant}"}
    if introduced:
        resolved["introduced"] = True
    return resolved


def _validate_contract_surface(
    value: object,
    waiver_value: object | None,
    repository_root: Path | None,
    stage: str,
    *,
    allow_missing_prose_waiver: bool = False,
    allow_legacy_prose_waiver: bool = False,
    require_introduced_resolved: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if type(value) is not dict:
        raise AtomError(stage, "contract_surface is not one object")
    kind = value.get("kind")
    if kind == "render":
        surface = _exact(value, "contract_surface", CONTRACT_SURFACE_RENDER_FIELDS, stage)
        if waiver_value is not None:
            raise AtomError(stage, "prose_waiver is present for a render atom; remove it")
        return dict(surface), None
    if kind != "validation":
        raise AtomError(stage, "contract_surface.kind must be 'render' or 'validation'")
    surface = _exact(value, "contract_surface", CONTRACT_SURFACE_VALIDATION_FIELDS, stage)
    deliverable = _nonempty(surface["deliverable"], "contract_surface.deliverable", stage)
    raw_fields = surface["fields"]
    if type(raw_fields) is not list or not raw_fields:
        raise AtomError(stage, "contract_surface.fields must be one nonempty ordered list")
    fields: list[dict[str, str]] = []
    for index, raw in enumerate(raw_fields):
        item = _exact_with_optional(
            raw, f"contract_surface.fields[{index}]", CONTRACT_FIELD_FIELDS, CONTRACT_FIELD_OPTIONAL_FIELDS, stage
        )
        minimally_valid: dict[str, Any] = {
            "field": _nonempty(item["field"], f"contract_surface.fields[{index}].field", stage),
            "shape": item["shape"],
            "shape_source": _nonempty(
                item["shape_source"], f"contract_surface.fields[{index}].shape_source", stage
            ),
        }
        if "introduced" in item:
            if item["introduced"] is not True:
                raise AtomError(
                    stage,
                    f"contract_surface.fields[{index}].introduced is {item['introduced']!r}; write true for a "
                    "field this atom introduces, or omit it",
                )
            minimally_valid["introduced"] = True
        if repository_root is None:
            if minimally_valid["shape"] not in CONTRACT_SHAPES:
                raise AtomError(
                    stage,
                    f"contract_surface.fields[{index}].shape is {minimally_valid['shape']!r}; "
                    f"choose one of {sorted(CONTRACT_SHAPES)!r}",
                )
            _field_segments(minimally_valid["field"], f"contract_surface.fields[{index}].field", stage)
            fields.append(minimally_valid)
        else:
            fields.append(
                _resolve_contract_field(
                    minimally_valid, deliverable, repository_root,
                    f"contract_surface.fields[{index}]", stage,
                    require_introduced_resolved=require_introduced_resolved,
                )
            )
    names = [item["field"] for item in fields]
    if len(names) != len(set(names)):
        raise AtomError(stage, "contract_surface.fields repeats a target; keep every target exactly once")
    prose_fields = [item["field"] for item in fields if item["shape"] == "prose"]
    waiver = None
    if prose_fields:
        if waiver_value is None:
            if allow_missing_prose_waiver:
                return {"kind": "validation", "deliverable": deliverable, "fields": fields}, None
            raise AtomError(
                stage,
                f"validation field(s) {prose_fields!r} use prose; a validation rule over prose is the class "
                "that misread three real runs. Change the deliverable schema so the model fills a structured "
                "field, or run prose-waiver-interview so the operator can choose in the fixed native macOS window between 'waive' "
                "and 'decline' meanings; a model-written prose_waiver is not accepted",
            )
        if (
            allow_legacy_prose_waiver
            and type(waiver_value) is dict
            and set(waiver_value) == LEGACY_PROSE_WAIVER_FIELDS
        ):
            raw_legacy = _exact(waiver_value, "legacy prose_waiver", LEGACY_PROSE_WAIVER_FIELDS, stage)
            if raw_legacy["by"] != "Kamen Kamenov":
                raise AtomError(stage, "legacy prose_waiver.by differs from its historical fixed value")
            words = _nonempty(raw_legacy["words"], "legacy prose_waiver.words", stage)
            date = _nonempty(raw_legacy["date"], "legacy prose_waiver.date", stage)
            try:
                calendar_date.fromisoformat(date)
            except ValueError:
                raise AtomError(stage, "legacy prose_waiver.date must use YYYY-MM-DD") from None
            waiver = {"by": "Kamen Kamenov", "words": words, "date": date}
            return {"kind": "validation", "deliverable": deliverable, "fields": fields}, waiver
        raw_waiver = _exact(waiver_value, "prose_waiver", PROSE_WAIVER_FIELDS, stage)
        operator = _validated_operator(raw_waiver["operator"], stage)
        presence = _validated_presence(raw_waiver["presence_proof"], stage)
        if presence["helper_sha256"] != operator["helper_sha256"]:
            raise AtomError(
                stage,
                "prose_waiver presence helper SHA-256 differs from its signed operator helper",
            )
        words = _nonempty(raw_waiver["words"], "prose_waiver.words", stage)
        date = _nonempty(raw_waiver["date"], "prose_waiver.date", stage)
        try:
            calendar_date.fromisoformat(date)
        except ValueError:
            raise AtomError(stage, "prose_waiver.date must use YYYY-MM-DD")
        waiver = {"operator": operator, "words": words, "date": date, "presence_proof": presence}
    elif waiver_value is not None:
        raise AtomError(stage, "prose_waiver is present but no declared target has shape 'prose'; remove it")
    return {"kind": "validation", "deliverable": deliverable, "fields": fields}, waiver


def _require_disjoint_run(run: Path, repository_root: Path, allowed_paths: list[str]) -> None:
    resolved_run = run.resolve()
    for boundary in allowed_paths:
        resolved_boundary = (repository_root / boundary).resolve()
        if (
            resolved_run == resolved_boundary
            or resolved_run.is_relative_to(resolved_boundary)
            or resolved_boundary.is_relative_to(resolved_run)
        ):
            raise AtomError(
                "start",
                f"run directory {run} overlaps allowed_paths boundary {boundary!r}; "
                "choose a controller-owned path outside the product surface",
            )


def _snapshot(repository_root: Path, allowed_paths: list[str], stage: str) -> list[dict[str, object]]:
    files: dict[str, dict[str, object]] = {}
    for boundary in allowed_paths:
        target = repository_root / boundary
        if not target.exists():
            continue
        if target.is_symlink():
            raise AtomError(stage, f"allowed path {boundary!r} is linked; require repository-owned regular files")
        if target.is_file():
            candidates = [target]
        elif target.is_dir():
            candidates = sorted(target.rglob("*"))
        else:
            raise AtomError(stage, f"allowed path {boundary!r} has an unsupported file type")
        for candidate in candidates:
            relative = candidate.relative_to(repository_root).as_posix()
            if candidate.is_symlink():
                raise AtomError(stage, f"allowed path contains linked entry {relative!r}; require regular files")
            if candidate.is_dir():
                continue
            if not candidate.is_file():
                raise AtomError(stage, f"allowed path contains unsupported entry {relative!r}")
            payload = candidate.read_bytes()
            files[relative] = {
                "path": relative,
                "sha256": _digest(payload),
                "size": len(payload),
                "mode": candidate.stat().st_mode & 0o777,
            }
    return [files[path] for path in sorted(files)]


def _baseline_document(request: dict[str, Any], repository_root: Path) -> dict[str, object]:
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": request["atomic_step_id"],
        "repository_root": str(repository_root),
        "allowed_paths": request["allowed_paths"],
        "files": _snapshot(repository_root, request["allowed_paths"], "start"),
    }


def _validate_snapshot_files(value: object, label: str, stage: str) -> list[dict[str, object]]:
    if type(value) is not list:
        raise AtomError(stage, f"{label} is not one ordered list")
    normalized = []
    paths = []
    for index, raw in enumerate(value):
        item = _exact(raw, f"{label}[{index}]", SNAPSHOT_FILE_FIELDS, stage)
        path = _relative_path(_nonempty(item["path"], f"{label}[{index}].path", stage), f"{label}[{index}].path", stage)
        sha256 = _sha(item["sha256"], f"{label}[{index}].sha256", stage)
        size = item["size"]
        if type(size) is not int or size < 0:
            raise AtomError(stage, f"{label}[{index}].size is {size!r}; provide one nonnegative integer")
        mode = item["mode"]
        if type(mode) is not int or not 0 <= mode <= 0o777:
            raise AtomError(stage, f"{label}[{index}].mode is {mode!r}; provide one permission-mode integer")
        paths.append(path)
        normalized.append({"path": path, "sha256": sha256, "size": size, "mode": mode})
    if paths != sorted(set(paths)):
        raise AtomError(stage, f"{label} paths are not unique lexical order; restore the controller-written snapshot")
    return normalized


def _baseline(run: Path, request: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    records, _ = _read_ledger(run)
    root = records[0]["payload"]
    legacy_fields = {"atomic_step_id", "request_sha256"}
    current_fields = legacy_fields | {"baseline_sha256", "repository_root"}
    superseded_fields = current_fields | {"supersession_sha256"}
    if set(root) == legacy_fields:
        return None
    if set(root) not in {frozenset(current_fields), frozenset(superseded_fields)}:
        _exact(root, "atom-started payload", superseded_fields, "load-run")
    baseline_path = run / "inputs" / "change-baseline.json"
    _unchanged(baseline_path, root["baseline_sha256"], "recorded change baseline")
    value = _exact(_load(baseline_path, "recorded change baseline", "load-run"), "change baseline", BASELINE_FIELDS, "load-run")
    if value["schema_version"] != CONTRACT or type(value["schema_version"]) is not int:
        raise AtomError("load-run", f"change baseline schema_version is {value['schema_version']!r}; require integer 1")
    if value["atomic_step_id"] != request["atomic_step_id"]:
        raise AtomError("load-run", "change baseline atomic_step_id differs from the preserved atom request")
    repository_root = _nonempty(value["repository_root"], "change baseline repository_root", "load-run")
    if repository_root != root["repository_root"] or not Path(repository_root).is_absolute():
        raise AtomError("load-run", "change baseline repository_root differs from the atom-started boundary")
    if value["allowed_paths"] != request["allowed_paths"]:
        raise AtomError("load-run", "change baseline allowed_paths differ from the preserved atom request")
    value["files"] = _validate_snapshot_files(value["files"], "change baseline files", "load-run")
    return value, root["baseline_sha256"]


def _derive_change_surface(run: Path, request: dict[str, Any]) -> dict[str, object]:
    context = _baseline(run, request)
    if context is None:
        raise AtomError("change-surface", "this run predates change baselines; start a fresh run with the upgraded controller")
    baseline, baseline_sha256 = context
    repository_root = Path(baseline["repository_root"])
    current = _snapshot(repository_root, request["allowed_paths"], "change-surface")
    before = {item["path"]: item for item in baseline["files"]}
    after = {item["path"]: item for item in current}
    changes = []
    for path in sorted(set(before) | set(after)):
        prior = before.get(path)
        present = after.get(path)
        if (
            prior is not None
            and present is not None
            and prior["sha256"] == present["sha256"]
            and prior["mode"] == present["mode"]
        ):
            continue
        kind = "added" if prior is None else "deleted" if present is None else "changed"
        changes.append(
            {
                "path": path,
                "kind": kind,
                "before_sha256": None if prior is None else prior["sha256"],
                "after_sha256": None if present is None else present["sha256"],
                "before_mode": None if prior is None else prior["mode"],
                "after_mode": None if present is None else present["mode"],
            }
        )
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": request["atomic_step_id"],
        "repository_root": str(repository_root),
        "baseline_sha256": baseline_sha256,
        "changes": changes,
    }


def _file_reference(value: object, label: str, stage: str, *, base: Path | None = None) -> dict[str, str]:
    item = _exact(value, label, FILE_REFERENCE_FIELDS, stage)
    path_text = _nonempty(item["path"], f"{label}.path", stage)
    path = Path(path_text)
    if not path.is_absolute():
        if base is None:
            raise AtomError(stage, f"{label}.path is relative; restore the recorded absolute path")
        path = base / path
    path = path.absolute()
    expected = _sha(item["sha256"], f"{label}.sha256", stage)
    if path.is_symlink() or not path.is_file():
        raise AtomError(stage, f"{label} is unavailable or linked at {path}; provide the recorded regular file")
    actual = _digest(path.read_bytes())
    if actual != expected:
        raise AtomError(stage, f"{label} has SHA-256 {actual} at {path}; require recorded {expected}")
    return {"path": str(path), "sha256": expected}


def _validate_review(path: Path, surface_sha256: str, label: str, stage: str) -> None:
    review = _exact(_load(path, label, stage), label, REVIEW_FIELDS, stage)
    if review["schema_version"] != CONTRACT or type(review["schema_version"]) is not int:
        raise AtomError(stage, f"{label} schema_version is {review['schema_version']!r}; require integer 1")
    if review["status"] != "completed" or review["verdict"] != "passed":
        raise AtomError(stage, f"{label} status/verdict is {review['status']!r}/{review['verdict']!r}; require completed/passed")
    if review["change_surface_sha256"] != surface_sha256:
        raise AtomError(
            stage,
            f"{label} change_surface_sha256 is {review['change_surface_sha256']!r}; require {surface_sha256!r}",
        )
    if review["blocking_findings"] != []:
        raise AtomError(stage, f"{label} blocking_findings is {review['blocking_findings']!r}; resolve every finding")


def _validate_request(
    value: object,
    *,
    require_contract_surface: bool = False,
    repository_root: Path | None = None,
    stage: str = "validate-request",
    allow_missing_prose_waiver: bool = False,
    allow_legacy_prose_waiver: bool = False,
    require_introduced_resolved: bool = False,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise AtomError(stage, "atom request is not one object")
    has_surface = "contract_surface" in value
    if require_contract_surface and not has_surface:
        raise AtomError(
            stage,
            "atom request has no contract_surface; declare exactly {'kind': 'render'} or a validation "
            "deliverable with its ordered target fields, shapes, and shape sources",
        )
    if has_surface:
        request = _exact_with_optional(
            value, "atom request", REQUEST_FIELDS, REQUEST_OPTIONAL_FIELDS, stage
        )
    else:
        request = _exact(value, "legacy atom request", LEGACY_REQUEST_FIELDS, stage)
    if request["schema_version"] != CONTRACT or type(request["schema_version"]) is not int:
        raise AtomError(stage, f"schema_version is {request['schema_version']!r}; require integer 1")
    for field in ("atomic_step_id", "outcome", "practical_value", "stopping_condition"):
        _nonempty(request[field], field, stage)
    allowed = _strings(request["allowed_paths"], "allowed_paths", stage)
    normalized_paths = [_relative_path(item, f"allowed_paths[{index}]", stage) for index, item in enumerate(allowed)]
    if len(set(normalized_paths)) != len(normalized_paths):
        raise AtomError(stage, "allowed_paths normalize to duplicates; keep every boundary exactly once")
    cases = request["captured_cases"]
    if type(cases) is not list or not cases:
        raise AtomError(stage, "captured_cases is empty or not a list; provide immutable success and failure cases")
    normalized_cases = []
    case_ids = []
    kinds = []
    for index, raw in enumerate(cases):
        case = _exact(raw, f"captured_cases[{index}]", CASE_FIELDS, stage)
        case_id = _nonempty(case["case_id"], f"captured_cases[{index}].case_id", stage)
        kind = case["kind"]
        if kind not in {"success", "failure"}:
            raise AtomError(stage, f"captured_cases[{index}].kind is {kind!r}; choose 'success' or 'failure'")
        normalized_cases.append(
            {
                "case_id": case_id,
                "source_ref": _nonempty(case["source_ref"], f"captured_cases[{index}].source_ref", stage),
                "sha256": _sha(case["sha256"], f"captured_cases[{index}].sha256", stage),
                "kind": kind,
                "expected_outcome": _nonempty(
                    case["expected_outcome"], f"captured_cases[{index}].expected_outcome", stage
                ),
            }
        )
        case_ids.append(case_id)
        kinds.append(kind)
    if len(set(case_ids)) != len(case_ids):
        raise AtomError(stage, "captured_cases contains duplicate case_id values; keep every case exactly once")
    if set(kinds) != {"success", "failure"}:
        raise AtomError(stage, "captured_cases must include at least one success and one failure case")
    normalized = {**request, "allowed_paths": normalized_paths, "captured_cases": normalized_cases}
    if has_surface:
        surface, waiver = _validate_contract_surface(
            request["contract_surface"], request.get("prose_waiver"), repository_root, stage,
            allow_missing_prose_waiver=allow_missing_prose_waiver,
            allow_legacy_prose_waiver=allow_legacy_prose_waiver,
            require_introduced_resolved=require_introduced_resolved,
        )
        normalized["contract_surface"] = surface
        if waiver is not None:
            normalized["prose_waiver"] = waiver
    return normalized


def _write_new(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(payload)


def _write_snapshot(path: Path, payload: bytes, stage: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise AtomError(stage, f"evidence snapshot is unavailable or linked at {path}")
        actual = _digest(path.read_bytes())
        expected = _digest(payload)
        if actual != expected:
            raise AtomError(stage, f"evidence snapshot has SHA-256 {actual} at {path}; require {expected}")
        return actual
    return _write_new(path, payload)


def _snapshot_validation(
    run: Path,
    receipt_path: Path,
    case_evidence: list[dict[str, object]],
    blocker_closeout: dict[str, Any],
) -> tuple[dict[str, str], list[dict[str, object]], dict[str, str]]:
    sequence = len(_read_ledger(run)[0]) + 1
    root = run / "evidence" / f"validation-{sequence:06d}"
    receipt_snapshot = root / "receipt.json"
    receipt_sha256 = _write_snapshot(receipt_snapshot, receipt_path.read_bytes(), "record-validation")
    snapshot_cases = []
    for case_index, case in enumerate(case_evidence, start=1):
        snapshot_evidence = []
        for evidence_index, item in enumerate(case["evidence"], start=1):
            source = Path(item["path"])
            target = root / f"case-{case_index:03d}-evidence-{evidence_index:03d}.bin"
            sha256 = _write_snapshot(target, source.read_bytes(), "record-validation")
            snapshot_evidence.append({
                "case_id": item["case_id"],
                "path": str(target),
                "sha256": sha256,
            })
        snapshot_cases.append({"case_id": case["case_id"], "evidence": snapshot_evidence})
    closeout_target = root / "blocker-closeout.json"
    closeout_sha256 = _write_snapshot(
        closeout_target, _document(blocker_closeout), "record-validation",
    )
    return (
        {"path": str(receipt_snapshot), "sha256": receipt_sha256},
        snapshot_cases,
        {"path": str(closeout_target), "sha256": closeout_sha256},
    )


def _blocker_support_root(stage: str) -> Path:
    if all((MODULE_ROOT / relative).is_file() for relative in BLOCKER_SUPPORT_FILES):
        return MODULE_ROOT
    record_path = MODULE_ROOT / MANAGED_SOURCE_RECORD_NAME
    if record_path.is_symlink() or not record_path.is_file():
        raise AtomError(
            stage,
            f"managed blocker support provenance is unavailable at {record_path}; "
            "refresh atom-building-machinery for both clients through the managed installer",
        )
    record = _exact(
        _load(record_path, "managed blocker support provenance", stage),
        "managed blocker support provenance",
        MANAGED_SOURCE_RECORD_FIELDS,
        stage,
    )
    if record["schema_version"] != CONTRACT:
        raise AtomError(stage, f"managed blocker support schema_version must be {CONTRACT}")
    source_value = _nonempty(
        record["source_repository_root"], "managed source_repository_root", stage,
    )
    source = Path(source_value)
    if not source.is_absolute() or source.is_symlink() or not source.is_dir():
        raise AtomError(stage, "managed blocker support repository must be an available absolute directory")
    support_files = _exact(
        record["support_files"],
        "managed blocker support files",
        set(BLOCKER_SUPPORT_FILES),
        stage,
    )
    for relative in BLOCKER_SUPPORT_FILES:
        expected = _sha(support_files[relative], f"managed {relative} SHA-256", stage)
        candidate = source / relative
        if candidate.is_symlink() or not candidate.is_file():
            raise AtomError(stage, f"managed blocker support file is unavailable or linked: {candidate}")
        actual = _digest(candidate.read_bytes())
        if actual != expected:
            raise AtomError(
                stage,
                f"managed blocker support hash differs for {candidate}: found {actual}, require {expected}; "
                "refresh both client projections through the managed installer",
            )
    return source


def _canonical_blocker_closeout(run: Path, stage: str) -> dict[str, Any]:
    module_root = _blocker_support_root(stage)
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))
    blocker_catalog = importlib.import_module("scripts.blocker_catalog")
    work_memory = importlib.import_module("scripts.work_memory")
    try:
        return blocker_catalog.atom_closeout(run)
    except work_memory.WorkMemoryError as error:
        raise AtomError(stage, f"canonical blocker closeout failed: {error.code}") from None


def _recorded_blocker_closeout(
    reference: object, request: dict[str, Any], run_id: str,
) -> dict[str, Any]:
    item = _file_reference(reference, "recorded blocker closeout", "load-run")
    value = _exact(
        _load(Path(item["path"]), "recorded blocker closeout", "load-run"),
        "recorded blocker closeout", BLOCKER_CLOSEOUT_FIELDS, "load-run",
    )
    if (
        value["schema_version"] != CONTRACT
        or value["atomic_step_id"] != request["atomic_step_id"]
        or value["atom_request_sha256"]
        != _digest((Path(run_id) / "inputs" / "atom-request.json").read_bytes())
        or value["atom_run_id"] != _digest((Path(run_id) / "ledger.jsonl").read_bytes().splitlines(keepends=True)[0])
        or type(value["clear"]) is not bool
        or type(value["linked_occurrence_count"]) is not int
        or type(value["blocking_occurrence_count"]) is not int
        or type(value["blocking_occurrences"]) is not list
        or type(value["dispositions"]) is not list
        or value["linked_occurrence_count"] != len(value["dispositions"])
        or value["blocking_occurrence_count"] != len(value["blocking_occurrences"])
        or value["clear"] != (value["blocking_occurrence_count"] == 0)
    ):
        raise AtomError("load-run", "recorded blocker closeout does not match its atom or counts")
    _sha(value["work_memory_ledger_sha256"], "blocker closeout ledger SHA-256", "load-run")
    return value


def _snapshot_tree(source: Path, target: Path, stage: str) -> None:
    if source.is_symlink() or not source.is_dir():
        raise AtomError(stage, f"snapshot source is unavailable or linked at {source}")
    target.mkdir(parents=True, exist_ok=True)
    directories = []
    for candidate in sorted(source.rglob("*")):
        relative = candidate.relative_to(source)
        if candidate.is_symlink():
            raise AtomError(stage, f"snapshot source contains linked entry {relative.as_posix()!r}")
        if candidate.is_dir():
            (target / relative).mkdir(parents=True, exist_ok=True)
            directories.append(candidate)
            continue
        if not candidate.is_file():
            raise AtomError(stage, f"snapshot source contains unsupported entry {relative.as_posix()!r}")
        snapshot = target / relative
        _write_snapshot(snapshot, candidate.read_bytes(), stage)
        os.chmod(snapshot, candidate.stat().st_mode & 0o777)
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        os.chmod(target / directory.relative_to(source), directory.stat().st_mode & 0o777)
    os.chmod(target, source.stat().st_mode & 0o777)


def _snapshot_experiment(run: Path, experiment: Path) -> Path:
    sequence = len(_read_ledger(run)[0]) + 1
    root = run / "evidence" / f"experiment-{sequence:06d}"
    for relative in (Path("development-probe-summary.json"), Path("final-verdict.json")):
        source = experiment / relative
        _write_snapshot(root / relative, source.read_bytes(), "record-experiment")
    _snapshot_tree(
        experiment / "composition" / "assembly",
        root / "composition" / "assembly",
        "record-experiment",
    )
    return root


def _snapshot_promotion(
    run: Path,
    receipt_path: Path,
    evidence: list[dict[str, str]],
    surface: dict[str, str] | None,
    review: dict[str, str] | None,
) -> tuple[dict[str, str], list[dict[str, str]], dict[str, str] | None, dict[str, str] | None]:
    sequence = len(_read_ledger(run)[0]) + 1
    root = run / "evidence" / f"promotion-{sequence:06d}"
    receipt_target = root / "receipt.json"
    receipt_sha256 = _write_snapshot(receipt_target, receipt_path.read_bytes(), "record-promotion")
    snapshot_evidence = []
    for index, item in enumerate(evidence, start=1):
        source = Path(item["path"])
        target = root / f"case-{index:03d}-evidence.bin"
        sha256 = _write_snapshot(target, source.read_bytes(), "record-promotion")
        snapshot_evidence.append({"case_id": item["case_id"], "path": str(target), "sha256": sha256})

    def snapshot_reference(value: dict[str, str] | None, name: str) -> dict[str, str] | None:
        if value is None:
            return None
        source = Path(value["path"])
        target = root / name
        return {
            "path": str(target),
            "sha256": _write_snapshot(target, source.read_bytes(), "record-promotion"),
        }

    return (
        {"path": str(receipt_target), "sha256": receipt_sha256},
        snapshot_evidence,
        snapshot_reference(surface, "change-surface.json"),
        snapshot_reference(review, "review.json"),
    )


def _read_ledger(run: Path) -> tuple[list[dict[str, Any]], list[str]]:
    path = run / "ledger.jsonl"
    try:
        lines = path.read_bytes().splitlines(keepends=True)
    except OSError as error:
        raise AtomError("load-run", f"ledger is unavailable: {error}") from None
    records: list[dict[str, Any]] = []
    hashes: list[str] = []
    previous: str | None = None
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AtomError("load-run", f"ledger record {index + 1} is invalid JSON: {error}") from None
        record = _exact(record, f"ledger record {index + 1}", LEDGER_FIELDS, "load-run")
        if record["sequence"] != index + 1:
            raise AtomError("load-run", f"ledger record {index + 1} sequence is {record['sequence']!r}; require {index + 1}")
        if record["previous_event_sha256"] != previous:
            raise AtomError(
                "load-run",
                f"ledger record {index + 1} previous_event_sha256 is {record['previous_event_sha256']!r}; "
                f"require {previous!r}",
            )
        if type(record["event"]) is not str or type(record["payload"]) is not dict:
            raise AtomError("load-run", f"ledger record {index + 1} has invalid event or payload types")
        records.append(record)
        hashes.append(_digest(line))
        previous = hashes[-1]
    if not records or records[0]["event"] != "atom-started":
        raise AtomError("load-run", "ledger has no atom-started first record; restore the original run")
    return records, hashes


def _append(run: Path, event: str, payload: dict[str, Any]) -> str:
    records, hashes = _read_ledger(run)
    record = {
        "sequence": len(records) + 1,
        "event": event,
        "previous_event_sha256": hashes[-1],
        "payload": payload,
    }
    line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    with (run / "ledger.jsonl").open("ab") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(line)


def _prose_fields(request: dict[str, Any]) -> list[str]:
    surface = request.get("contract_surface")
    if type(surface) is not dict or surface.get("kind") != "validation":
        return []
    return [item["field"] for item in surface["fields"] if item["shape"] == "prose"]


def _read_waiver_ledger(interview: Path) -> tuple[list[dict[str, Any]], list[str]]:
    ledger = interview / "ledger.jsonl"
    if ledger.is_symlink() or not ledger.is_file():
        raise AtomError("prose-waiver-interview", f"interview ledger is unavailable or linked at {ledger}")
    lines = ledger.read_bytes().splitlines(keepends=True)
    if not lines or any(not line.endswith(b"\n") for line in lines):
        raise AtomError("prose-waiver-interview", "interview ledger is empty or has an unterminated record")
    records: list[dict[str, Any]] = []
    hashes: list[str] = []
    previous: str | None = None
    for index, line in enumerate(lines, start=1):
        try:
            raw = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AtomError("prose-waiver-interview", f"interview ledger record {index} is invalid: {error}") from None
        record = _exact(
            raw,
            f"interview ledger record {index}",
            {"sequence", "event", "previous_event_sha256", "payload"},
            "prose-waiver-interview",
        )
        if record["sequence"] != index or type(record["sequence"]) is not int:
            raise AtomError("prose-waiver-interview", f"interview ledger record {index} has the wrong sequence")
        if record["previous_event_sha256"] != previous:
            raise AtomError("prose-waiver-interview", f"interview ledger record {index} breaks the hash chain")
        if type(record["event"]) is not str or type(record["payload"]) is not dict:
            raise AtomError("prose-waiver-interview", f"interview ledger record {index} has an invalid event or payload")
        records.append(record)
        previous = _digest(line)
        hashes.append(previous)
    return records, hashes


def _append_waiver_event(interview: Path, event: str, payload: dict[str, Any]) -> str:
    records, hashes = _read_waiver_ledger(interview)
    record = {
        "sequence": len(records) + 1,
        "event": event,
        "previous_event_sha256": hashes[-1],
        "payload": payload,
    }
    line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    with (interview / "ledger.jsonl").open("ab") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(line)


def _validated_operator(value: object, stage: str) -> dict[str, Any]:
    operator = _exact(value, "operator", OPERATOR_FIELDS, stage)
    login_user = _nonempty(operator["login_user"], "operator.login_user", stage)
    uid = operator["uid"]
    if type(uid) is not int or uid < 0:
        raise AtomError(stage, f"operator.uid is {uid!r}; require one nonnegative OS uid")
    if operator["approval_ui"] != "native-macos-window":
        raise AtomError(stage, "operator.approval_ui must identify the code-owned native macOS window")
    if operator["authentication_policy"] != "device-owner-authentication":
        raise AtomError(stage, "operator.authentication_policy must be macOS device-owner-authentication")
    projection = operator["client_projection"]
    if projection not in {"codex", "claude"}:
        raise AtomError(stage, f"operator.client_projection is {projection!r}; require 'codex' or 'claude'")
    helper_path = Path(_nonempty(operator["helper_path"], "operator.helper_path", stage))
    expected_helper = (
        Path.home() / f".{projection}" / "skills" / "atom-building-machinery" / "scripts" / NATIVE_HELPER_NAME
    )
    if helper_path != expected_helper:
        raise AtomError(
            stage,
            f"operator.helper_path is {str(helper_path)!r}; require installed {projection} helper {str(expected_helper)!r}",
        )
    helper_sha256 = _sha(operator["helper_sha256"], "operator.helper_sha256", stage)
    parent_name = _nonempty(operator["parent_process_name"], "operator.parent_process_name", stage)
    parent_pid = operator["parent_process_pid"]
    if type(parent_pid) is not int or parent_pid <= 0:
        raise AtomError(stage, f"operator.parent_process_pid is {parent_pid!r}; require one positive observed pid")
    observed_at = _nonempty(operator["observed_at"], "operator.observed_at", stage)
    try:
        parsed = datetime.fromisoformat(observed_at)
    except ValueError:
        raise AtomError(stage, "operator.observed_at must be an ISO-8601 wall-clock timestamp") from None
    if parsed.tzinfo is None:
        raise AtomError(stage, "operator.observed_at must include its UTC offset")
    present = _strings(
        operator["initiating_harness_markers"],
        "operator.initiating_harness_markers",
        stage,
        nonempty=False,
    )
    if present != [name for name in MODEL_HARNESS_MARKERS if name in present]:
        raise AtomError(
            stage,
            f"operator initiating harness markers are {present!r}; require the ordered code-owned marker subset",
        )
    return {
        "login_user": login_user,
        "uid": uid,
        "approval_ui": "native-macos-window",
        "authentication_policy": "device-owner-authentication",
        "client_projection": projection,
        "helper_path": str(helper_path),
        "helper_sha256": helper_sha256,
        "parent_process_name": parent_name,
        "parent_process_pid": parent_pid,
        "observed_at": observed_at,
        "initiating_harness_markers": present,
    }


def _validated_presence(value: object, stage: str) -> dict[str, Any]:
    proof = _exact(value, "presence_proof", PRESENCE_PROOF_FIELDS, stage)
    if proof["scheme"] != PRESENCE_SCHEME:
        raise AtomError(stage, f"presence_proof.scheme is {proof['scheme']!r}; require {PRESENCE_SCHEME!r}")
    if proof["service"] != KEYCHAIN_SERVICE:
        raise AtomError(stage, f"presence_proof.service is {proof['service']!r}; require {KEYCHAIN_SERVICE!r}")
    if proof["helper_version"] != NATIVE_HELPER_VERSION:
        raise AtomError(stage, f"presence_proof.helper_version must be {NATIVE_HELPER_VERSION}")
    helper_sha256 = _sha(proof["helper_sha256"], "presence_proof.helper_sha256", stage)
    signed_payload_base64 = _nonempty(
        proof["signed_payload_base64"], "presence_proof.signed_payload_base64", stage
    )
    try:
        signed_payload = base64.b64decode(signed_payload_base64, validate=True)
    except (binascii.Error, ValueError):
        raise AtomError(stage, "presence_proof.signed_payload_base64 is not canonical base64") from None
    if not signed_payload:
        raise AtomError(stage, "presence_proof signed payload is empty")
    signed_payload_sha256 = _sha(
        proof["signed_payload_sha256"], "presence_proof.signed_payload_sha256", stage
    )
    if _digest(signed_payload) != signed_payload_sha256:
        raise AtomError(stage, "presence_proof signed payload SHA-256 does not match its bytes")
    nonce = _sha(proof["nonce"], "presence_proof.nonce", stage)
    digest = _sha(proof["digest"], "presence_proof.digest", stage)
    return {
        "scheme": PRESENCE_SCHEME,
        "service": KEYCHAIN_SERVICE,
        "helper_version": NATIVE_HELPER_VERSION,
        "helper_sha256": helper_sha256,
        "signed_payload_base64": signed_payload_base64,
        "signed_payload_sha256": signed_payload_sha256,
        "nonce": nonce,
        "digest": digest,
    }


def _authorization_context(
    atomic_step_id: str,
    request_sha256: str,
    repository_root: Path,
    fields: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": atomic_step_id,
        "request_sha256": request_sha256,
        "repository_root": str(repository_root),
        "fields": fields,
    }


def _helper_path(stage: str) -> Path:
    installed = [
        Path.home() / ".codex" / "skills" / "atom-building-machinery" / "scripts" / NATIVE_HELPER_NAME,
        Path.home() / ".claude" / "skills" / "atom-building-machinery" / "scripts" / NATIVE_HELPER_NAME,
    ]
    local = Path(__file__).resolve().with_name(NATIVE_HELPER_NAME)
    candidates = [local, *installed] if local in installed else installed
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise AtomError(
        stage,
        "native prose-waiver helper is unavailable; refresh atom-building-machinery for both Codex and Claude through the managed installer",
    )


def _helper_error(result: subprocess.CompletedProcess[bytes], stage: str) -> AtomError:
    detail = result.stderr.decode("utf-8", errors="replace").strip()
    try:
        decoded = json.loads(detail)
        if type(decoded) is dict and type(decoded.get("reason")) is str:
            detail = decoded["reason"]
    except json.JSONDecodeError:
        pass
    return AtomError(stage, detail or f"native approval helper exited {result.returncode}")


def _native_authorize(context: dict[str, Any]) -> dict[str, Any]:
    result = subprocess.run(
        [str(_helper_path("prose-waiver-interview")), "authorize"],
        input=_document(context),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise _helper_error(result, "prose-waiver-interview")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise AtomError("prose-waiver-interview", "native approval helper returned invalid JSON") from None
    return value


def _native_verify(proof: dict[str, Any]) -> None:
    payload = base64.b64decode(proof["signed_payload_base64"], validate=True)
    result = subprocess.run(
        [str(_helper_path("start")), "verify", proof["nonce"], proof["digest"]],
        input=payload,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise _helper_error(result, "start")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise AtomError("start", "native approval helper returned invalid verification JSON") from None
    if value != {"schema_version": CONTRACT, "status": "verified"}:
        raise AtomError("start", "native approval helper did not return the exact verified result")


def _validated_signed_authorization(
    proof: dict[str, Any],
    context: dict[str, Any],
    stage: str,
) -> dict[str, Any]:
    payload_bytes = base64.b64decode(proof["signed_payload_base64"], validate=True)
    try:
        raw = json.loads(payload_bytes)
    except json.JSONDecodeError:
        raise AtomError(stage, "presence_proof signed payload is not JSON") from None
    payload_fields = set(raw) if type(raw) is dict else set()
    if payload_fields == SIGNED_AUTHORIZATION_FIELDS:
        payload = _exact(raw, "signed authorization payload", SIGNED_AUTHORIZATION_FIELDS, stage)
        legacy = False
    elif payload_fields == LEGACY_SIGNED_AUTHORIZATION_FIELDS:
        payload = _exact(
            raw,
            "legacy signed authorization payload",
            LEGACY_SIGNED_AUTHORIZATION_FIELDS,
            stage,
        )
        legacy = True
    else:
        expected = sorted(SIGNED_AUTHORIZATION_FIELDS)
        legacy_expected = sorted(LEGACY_SIGNED_AUTHORIZATION_FIELDS)
        raise AtomError(
            stage,
            f"signed authorization payload fields are {sorted(payload_fields)!r}; "
            f"require {expected!r}, or the bounded legacy shape {legacy_expected!r}",
        )
    if payload["schema_version"] != CONTRACT:
        raise AtomError(stage, f"signed authorization schema_version must be {CONTRACT}")
    if not legacy and payload["atomic_step_id"] != context["atomic_step_id"]:
        raise AtomError(stage, "signed authorization atomic_step_id differs from the bound request")
    for key in ("request_sha256", "repository_root", "fields"):
        if payload[key] != context[key]:
            raise AtomError(stage, f"signed authorization {key} differs from the bound request")
    question, answer_contract = _waiver_question(context["fields"])
    del question
    if payload["meanings"] != answer_contract["meanings"]:
        raise AtomError(stage, "signed authorization meanings differ from the code-owned choices")
    choice = payload["choice"]
    if choice not in {"waive", "decline"}:
        raise AtomError(stage, "signed authorization choice must be exactly 'waive' or 'decline'")
    if payload["adopted_statement"] != answer_contract["meanings"][choice]:
        raise AtomError(stage, "signed authorization adopted statement differs from the chosen code-owned meaning")
    operator = _validated_operator(payload["operator"], stage)
    if operator["helper_sha256"] != proof["helper_sha256"]:
        raise AtomError(stage, "signed operator helper SHA-256 differs from the presence proof")
    decision_date = _nonempty(payload["date"], "signed authorization date", stage)
    try:
        calendar_date.fromisoformat(decision_date)
    except ValueError:
        raise AtomError(stage, "signed authorization date must use YYYY-MM-DD") from None
    if not operator["observed_at"].startswith(decision_date):
        raise AtomError(stage, "signed authorization date differs from the observed operator time")
    return {
        "choice": choice,
        "operator": operator,
        "date": decision_date,
        "adopted_statement": payload["adopted_statement"],
    }


def _validated_native_authorization(
    value: object,
    context: dict[str, Any],
    stage: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    authorization = _exact(value, "native authorization", NATIVE_AUTHORIZATION_FIELDS, stage)
    if authorization["schema_version"] != CONTRACT or authorization["status"] != "authorized":
        raise AtomError(stage, "native authorization did not return the exact authorized contract")
    proof = _validated_presence(
        {
            "scheme": PRESENCE_SCHEME,
            "service": authorization["service"],
            "helper_version": authorization["helper_version"],
            "helper_sha256": _validated_signed_helper_sha(authorization, stage),
            "signed_payload_base64": authorization["signed_payload_base64"],
            "signed_payload_sha256": authorization["signed_payload_sha256"],
            "nonce": authorization["nonce"],
            "digest": authorization["digest"],
        },
        stage,
    )
    signed = _validated_signed_authorization(proof, context, stage)
    return signed, proof


def _validated_signed_helper_sha(authorization: dict[str, Any], stage: str) -> str:
    payload_base64 = _nonempty(
        authorization["signed_payload_base64"], "native authorization signed_payload_base64", stage
    )
    try:
        payload = json.loads(base64.b64decode(payload_base64, validate=True))
    except (binascii.Error, ValueError, json.JSONDecodeError):
        raise AtomError(stage, "native authorization signed payload is invalid") from None
    if type(payload) is not dict or type(payload.get("operator")) is not dict:
        raise AtomError(stage, "native authorization signed payload lacks its operator")
    return _sha(payload["operator"].get("helper_sha256"), "signed operator helper_sha256", stage)


def _waiver_question(fields: list[str]) -> tuple[str, dict[str, Any]]:
    meanings = {
        "waive": (
            "I authorize this exact validation request to start as a recorded prose exception. "
            "This does not authorize promotion, operational use, another field, or another atom."
        ),
        "decline": (
            "I do not authorize this request to start while it reads prose. "
            "It must use a structured field before proceeding."
        ),
    }
    question = (
        f"Validation field(s) {fields!r} read prose.\n"
        f"waive — {meanings['waive']}\n"
        f"decline — {meanings['decline']}\n"
        "Choose one word: waive or decline. Your choice adopts the complete statement beside it."
    )
    return question, {"type": "enum", "choices": ["waive", "decline"], "meanings": meanings}


def _waiver_state(interview: Path) -> dict[str, Any]:
    records, hashes = _read_waiver_ledger(interview)
    first = records[0]
    if first["event"] != "owner-question-presented":
        raise AtomError("prose-waiver-interview", "interview ledger does not begin with the owner question")
    payload = _exact(
        first["payload"],
        "owner question payload",
        {"request_sha256", "repository_root", "fields", "question_id", "question", "answer_contract"},
        "prose-waiver-interview",
    )
    fields = _strings(payload["fields"], "owner question fields", "prose-waiver-interview")
    if len(fields) != len(set(fields)) or not fields:
        raise AtomError("prose-waiver-interview", "owner question fields are empty or duplicated")
    expected_question, expected_contract = _waiver_question(fields)
    if (
        payload["question_id"] != "prose-waiver-decision"
        or payload["question"] != expected_question
        or payload["answer_contract"] != expected_contract
    ):
        raise AtomError("prose-waiver-interview", "owner question differs from the code-controlled question")
    repository_root = Path(_nonempty(payload["repository_root"], "owner question repository_root", "prose-waiver-interview"))
    request_path = interview / "inputs" / "atom-request.json"
    _unchanged(request_path, _sha(payload["request_sha256"], "owner question request_sha256", "prose-waiver-interview"), "interview atom request")
    request = _validate_request(
        _load(request_path, "interview atom request", "prose-waiver-interview"),
        require_contract_surface=True,
        repository_root=repository_root,
        stage="prose-waiver-interview",
        allow_missing_prose_waiver=True,
    )
    if "prose_waiver" in request:
        raise AtomError("prose-waiver-interview", "interview atom request already contains prose_waiver; restore the code-written request")
    if _prose_fields(request) != fields:
        raise AtomError("prose-waiver-interview", "interview fields differ from the bound atom request")
    if len(records) == 1:
        return {
            "schema_version": CONTRACT,
            "status": "needs_operator_answer",
            "interview": str(interview),
            "question_id": payload["question_id"],
            "question": payload["question"],
            "answer_contract": payload["answer_contract"],
            "request": request,
            "repository_root": repository_root,
            "fields": fields,
        }
    if len(records) != 2:
        raise AtomError("prose-waiver-interview", "answered interview has unexpected later records")
    answer_record = records[1]
    answer_payload = _exact(
        answer_record["payload"],
        "operator waiver decision payload",
        {"question_id", "answer", "operator", "date", "presence_proof"},
        "prose-waiver-interview",
    )
    if answer_record["event"] != "owner-answer-recorded" or answer_payload["question_id"] != "prose-waiver-decision":
        raise AtomError("prose-waiver-interview", "second interview record is not the bound owner choice")
    if answer_payload["answer"] not in {"waive", "decline"}:
        raise AtomError("prose-waiver-interview", "operator choice must be exactly 'waive' or 'decline'")
    operator = _validated_operator(answer_payload["operator"], "prose-waiver-interview")
    presence = _validated_presence(answer_payload["presence_proof"], "prose-waiver-interview")
    context = _authorization_context(
        request["atomic_step_id"], payload["request_sha256"], repository_root, fields,
    )
    signed = _validated_signed_authorization(presence, context, "prose-waiver-interview")
    if (
        signed["choice"] != answer_payload["answer"]
        or signed["operator"] != operator
        or signed["date"] != answer_payload["date"]
    ):
        raise AtomError(
            "prose-waiver-interview",
            "recorded decision differs from the native helper's signed authorization",
        )
    if answer_payload["answer"] == "decline":
        return {
            "schema_version": CONTRACT,
            "status": "declined",
            "interview": str(interview),
            "request": request,
            "repository_root": repository_root,
            "fields": fields,
            "operator": operator,
            "presence_proof": presence,
        }
    date = _nonempty(answer_payload["date"], "waiver answer date", "prose-waiver-interview")
    try:
        calendar_date.fromisoformat(date)
    except ValueError:
        raise AtomError("prose-waiver-interview", "waiver answer date must use YYYY-MM-DD") from None
    return {
        "schema_version": CONTRACT,
        "status": "completed",
        "interview": str(interview),
        "request": request,
        "repository_root": repository_root,
        "fields": fields,
        "operator_choice": "waive",
        "waiver": {
            "operator": operator,
            "words": expected_contract["meanings"]["waive"],
            "date": date,
            "presence_proof": presence,
        },
        "answer_event_sha256": hashes[-1],
    }


def _public_waiver_state(state: dict[str, Any]) -> dict[str, Any]:
    result = {key: state[key] for key in ("schema_version", "status", "interview")}
    if state["status"] == "needs_operator_answer":
        result.update({
            "question_id": state["question_id"],
            "question": state["question"],
            "answer_contract": state["answer_contract"],
        })
    elif state["status"] == "completed":
        result["prose_waiver_receipt"] = str(Path(state["interview"]) / "prose-waiver-receipt.json")
    return result


def prose_waiver_interview(
    request_path: Path,
    interview: Path,
    *,
    approval_fn: Any = None,
) -> dict[str, Any]:
    request_path = request_path.absolute()
    interview = interview.absolute()
    repository_root = Path.cwd().resolve()
    if not interview.exists() or (interview.is_dir() and not any(interview.iterdir())):
        raw = _load(request_path, "atom request", "prose-waiver-interview")
        if type(raw) is dict and "prose_waiver" in raw:
            raise AtomError(
                "prose-waiver-interview",
                "atom request contains a hand-written prose_waiver; remove it so the code interview can record the owner answer",
            )
        request = _validate_request(
            raw,
            require_contract_surface=True,
            repository_root=repository_root,
            stage="prose-waiver-interview",
            allow_missing_prose_waiver=True,
        )
        fields = _prose_fields(request)
        if not fields:
            raise AtomError(
                "prose-waiver-interview",
                "atom request declares no prose validation field; use start without a waiver interview",
            )
        if interview.exists() and not interview.is_dir():
            raise AtomError("prose-waiver-interview", f"interview path is not a directory: {interview}")
        interview.mkdir(parents=True, exist_ok=True)
        request_sha256 = _write_new(interview / "inputs" / "atom-request.json", _document(request))
        question, answer_contract = _waiver_question(fields)
        first = {
            "sequence": 1,
            "event": "owner-question-presented",
            "previous_event_sha256": None,
            "payload": {
                "request_sha256": request_sha256,
                "repository_root": str(repository_root),
                "fields": fields,
                "question_id": "prose-waiver-decision",
                "question": question,
                "answer_contract": answer_contract,
            },
        }
        _write_new(
            interview / "ledger.jsonl",
            json.dumps(first, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n",
        )
    state = _waiver_state(interview)
    raw = _load(request_path, "atom request", "prose-waiver-interview")
    if type(raw) is dict and "prose_waiver" in raw:
        raise AtomError("prose-waiver-interview", "atom request contains prose_waiver; restore the request presented by the interview")
    supplied = _validate_request(
        raw,
        require_contract_surface=True,
        repository_root=repository_root,
        stage="prose-waiver-interview",
        allow_missing_prose_waiver=True,
    )
    if _document(supplied) != _document(state["request"]) or repository_root != state["repository_root"]:
        raise AtomError("prose-waiver-interview", "current request or repository differs from the question presented to the owner")
    if state["status"] != "needs_operator_answer":
        return _public_waiver_state(state)
    context = _authorization_context(
        state["request"]["atomic_step_id"],
        _digest(_document(state["request"])),
        repository_root,
        state["fields"],
    )
    authorization = (approval_fn or _native_authorize)(context)
    signed, presence_proof = _validated_native_authorization(
        authorization,
        context,
        "prose-waiver-interview",
    )
    confirmed = _waiver_state(interview)
    if (
        confirmed["status"] != "needs_operator_answer"
        or confirmed["question_id"] != state["question_id"]
        or confirmed["question"] != state["question"]
    ):
        raise AtomError("prose-waiver-interview", "owner question changed before its answer could be recorded")
    answer = signed["choice"]
    operator = signed["operator"]
    _append_waiver_event(
        interview,
        "owner-answer-recorded",
        {
            "question_id": state["question_id"],
            "answer": answer,
            "operator": operator,
            "date": signed["date"],
            "presence_proof": presence_proof,
        },
    )
    completed = _waiver_state(interview)
    if completed["status"] == "completed":
        receipt = {
            "schema_version": CONTRACT,
            "status": "accepted",
            "request_sha256": _digest(_document(completed["request"])),
            "repository_root": str(completed["repository_root"]),
            "fields": completed["fields"],
            **completed["waiver"],
            "operator_choice": completed["operator_choice"],
            "answer_event_sha256": completed["answer_event_sha256"],
        }
        _write_new(interview / "prose-waiver-receipt.json", _document(receipt))
    return _public_waiver_state(completed)


def _verified_prose_waiver(
    interview: Path,
    request: dict[str, Any],
    repository_root: Path,
) -> dict[str, str]:
    state = _waiver_state(interview.absolute())
    if state["status"] != "completed":
        if state["status"] == "declined":
            raise AtomError(
                "start",
                f"operator {state['operator']['login_user']!r} chose 'decline' for prose field(s) {state['fields']!r}; "
                "this request remains blocked until it uses a structured field",
            )
        raise AtomError(
            "start",
            f"prose waiver interview is {state['status']!r}; reopen its native approval window "
            "and record the authenticated operator choice before start",
        )
    if state["repository_root"] != repository_root or _document(state["request"]) != _document(request):
        raise AtomError("start", "prose waiver interview is bound to a different request or repository")
    receipt_path = interview.absolute() / "prose-waiver-receipt.json"
    receipt = _exact(
        _load(receipt_path, "prose waiver receipt", "start"),
        "prose waiver receipt",
        PROSE_WAIVER_RECEIPT_FIELDS,
        "start",
    )
    expected = {
        "schema_version": CONTRACT,
        "status": "accepted",
        "request_sha256": _digest(_document(request)),
        "repository_root": str(repository_root),
        "fields": state["fields"],
        **state["waiver"],
        "operator_choice": state["operator_choice"],
        "answer_event_sha256": state["answer_event_sha256"],
    }
    if receipt != expected:
        raise AtomError("start", "prose waiver receipt differs from the code-recorded operator interview")
    waiver = state["waiver"]
    proof = waiver["presence_proof"]
    _native_verify(proof)
    return waiver


def _request(run: Path) -> dict[str, Any]:
    raw = _load(run / "inputs" / "atom-request.json", "stored atom request", "load-run")
    value = _validate_request(raw, stage="load-run", allow_legacy_prose_waiver=True)
    records, _ = _read_ledger(run)
    root = records[0]["payload"]
    legacy_fields = {"atomic_step_id", "request_sha256"}
    current_fields = legacy_fields | {"baseline_sha256", "repository_root"}
    superseded_fields = current_fields | {"supersession_sha256"}
    if frozenset(root) not in {
        frozenset(legacy_fields), frozenset(current_fields), frozenset(superseded_fields),
    }:
        _exact(root, "atom-started payload", superseded_fields, "load-run")
    if "contract_surface" in value:
        repository_root = Path(_nonempty(root.get("repository_root"), "atom-started repository_root", "load-run"))
        value = _validate_request(
            raw,
            repository_root=repository_root,
            stage="load-run",
            allow_legacy_prose_waiver=True,
        )
    if root["atomic_step_id"] != value["atomic_step_id"]:
        raise AtomError(
            "load-run",
            f"atom-started atomic_step_id is {root['atomic_step_id']!r}; "
            f"require preserved request identity {value['atomic_step_id']!r}",
        )
    expected = _sha(root["request_sha256"], "atom-started request_sha256", "load-run")
    actual = _digest((run / "inputs" / "atom-request.json").read_bytes())
    if actual != expected:
        raise AtomError("load-run", f"stored atom request has SHA-256 {actual}; require recorded {expected}")
    _baseline(run, value)
    return value


def _supersession(run: Path, request: dict[str, Any]) -> dict[str, Any] | None:
    records, _ = _read_ledger(run)
    root = records[0]["payload"]
    if "supersession_sha256" not in root:
        return None
    path = run / "inputs" / "supersession.json"
    _unchanged(path, root["supersession_sha256"], "recorded supersession")
    value = _exact(
        _load(path, "recorded supersession", "load-run"),
        "supersession",
        SUPERSESSION_FIELDS,
        "load-run",
    )
    if value["schema_version"] != CONTRACT or type(value["schema_version"]) is not int:
        raise AtomError("load-run", "supersession schema_version must be integer 1")
    if value["atomic_step_id"] != request["atomic_step_id"]:
        raise AtomError("load-run", "supersession atomic_step_id differs from the preserved atom request")
    previous_run = Path(_nonempty(value["previous_run"], "supersession previous_run", "load-run"))
    if not previous_run.is_absolute():
        raise AtomError("load-run", "supersession previous_run is not absolute; restore the controller-written record")
    raw_chain = value["chain"]
    if type(raw_chain) is not list or not raw_chain:
        raise AtomError("load-run", "supersession chain is empty; restore the controller-written record")
    chain = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_chain):
        link = _exact(raw, f"supersession chain[{index}]", SUPERSESSION_LINK_FIELDS, "load-run")
        link_run = Path(_nonempty(link["run"], f"supersession chain[{index}].run", "load-run"))
        if not link_run.is_absolute() or str(link_run) in seen:
            raise AtomError("load-run", "supersession chain paths must be unique absolute run directories")
        seen.add(str(link_run))
        request_sha256 = _sha(
            link["request_sha256"], f"supersession chain[{index}].request_sha256", "load-run"
        )
        baseline_sha256 = _sha(
            link["baseline_sha256"], f"supersession chain[{index}].baseline_sha256", "load-run"
        )
        latest_event_sha256 = _sha(
            link["latest_event_sha256"],
            f"supersession chain[{index}].latest_event_sha256",
            "load-run",
        )
        chain.append(
            {
                "run": str(link_run),
                "request_sha256": request_sha256,
                "baseline_sha256": baseline_sha256,
                "latest_event_sha256": latest_event_sha256,
            }
        )
    if chain[-1]["run"] != str(previous_run):
        raise AtomError("load-run", "supersession previous_run is not the final recorded chain link")
    return {**value, "previous_run": str(previous_run), "chain": chain}


def _verify_supersession_sources(chain: list[dict[str, str]], atomic_step_id: str) -> None:
    for link in chain:
        link_run = Path(link["run"])
        prior_records, prior_hashes = _read_ledger(link_run)
        prior_root = prior_records[0]["payload"]
        if prior_root.get("request_sha256") != link["request_sha256"]:
            raise AtomError("start", f"superseded run {link_run} request hash differs from its chain record")
        if prior_root.get("baseline_sha256") != link["baseline_sha256"]:
            raise AtomError("start", f"superseded run {link_run} baseline hash differs from its chain record")
        if prior_hashes[-1] != link["latest_event_sha256"]:
            raise AtomError("start", f"superseded run {link_run} advanced after its chain link was recorded")
        request_path = link_run / "inputs" / "atom-request.json"
        _unchanged(request_path, link["request_sha256"], "superseded atom request")
        prior_request = _validate_request(_load(request_path, "superseded atom request", "start"))
        if prior_request["atomic_step_id"] != atomic_step_id:
            raise AtomError("start", f"superseded run {link_run} has a different atomic_step_id")
        _unchanged(
            link_run / "inputs" / "change-baseline.json",
            link["baseline_sha256"],
            "superseded change baseline",
        )


def _unchanged(path_value: object, expected: object, label: str) -> None:
    path_text = str(path_value) if isinstance(path_value, Path) else _nonempty(path_value, f"{label} path", "load-run")
    expected_sha256 = _sha(expected, f"{label} SHA-256", "load-run")
    path = Path(path_text)
    if path.is_symlink() or not path.is_file():
        raise AtomError("load-run", f"{label} is unavailable or linked at {path}; restore the recorded regular file")
    actual = _digest(path.read_bytes())
    if actual != expected_sha256:
        raise AtomError("load-run", f"{label} has SHA-256 {actual}; require recorded {expected_sha256}")


def _state(run: Path) -> dict[str, Any]:
    request = _request(run)
    records, hashes = _read_ledger(run)
    supersession = _supersession(run, request)
    supersession_chain = (
        [item["run"] for item in supersession["chain"]] + [str(run)]
        if supersession is not None
        else [str(run)]
    )
    supersession_chain_closed: bool | None = False if supersession is not None else None
    stage = "experiment"
    next_skill = "prototype-driven-implementation"
    required_capability = "experiment-machinery"
    current_experiment = None
    current_promotion = None
    legacy_validation_evidence_drift = []
    for record_index, (record, event_sha256) in enumerate(zip(records[1:], hashes[1:]), start=1):
        if record["event"] == "experiment-recorded":
            if stage != "experiment":
                raise AtomError("load-run", f"experiment-recorded appears during {stage!r}; restore the valid event order")
            experiment_fields = (
                CONTRACT_EXPERIMENT_EVENT_FIELDS
                if "contract_surface" in request
                else EXPERIMENT_EVENT_FIELDS
            )
            payload = _exact(
                record["payload"], "experiment-recorded payload", experiment_fields, "load-run"
            )
            experiment_path = Path(_nonempty(payload["experiment_path"], "experiment_path", "load-run"))
            _unchanged(
                experiment_path / "development-probe-summary.json",
                payload["summary_sha256"],
                "recorded experiment summary",
            )
            _unchanged(
                experiment_path / "final-verdict.json",
                payload["final_verdict_sha256"],
                "recorded experiment verdict",
            )
            _sha(payload["assembly_sha256"], "experiment assembly_sha256", "load-run")
            contract_scan = _verify_assembly(experiment_path, request, payload["assembly_sha256"])
            if contract_scan is not None and payload["contract_scan"] != contract_scan:
                raise AtomError("load-run", "recorded contract scan differs from the hashed champion modules")
            if payload["verdict"] not in EXPERIMENT_VERDICTS:
                raise AtomError("load-run", f"experiment verdict is {payload['verdict']!r}; restore a declared verdict")
            if payload["verdict"] == "passed":
                stage = "promotion"
                next_skill = "prototype-driven-implementation"
                required_capability = "promotion"
                current_experiment = {**payload, "event_sha256": event_sha256}
                current_promotion = None
            else:
                stage = "experiment"
                next_skill = "prototype-driven-implementation"
                required_capability = "experiment-machinery"
                current_experiment = None
                current_promotion = None
        elif record["event"] == "promotion-recorded":
            if stage != "promotion" or current_experiment is None:
                raise AtomError("load-run", f"promotion-recorded appears during {stage!r}; restore the valid event order")
            baseline = _baseline(run, request)
            event_fields = (
                LEGACY_PROMOTION_EVENT_FIELDS
                if baseline is None
                else CONTRACT_PROMOTION_EVENT_FIELDS
                if "contract_surface" in request
                else PROMOTION_EVENT_FIELDS
            )
            payload = _exact(record["payload"], "promotion-recorded payload", event_fields, "load-run")
            _unchanged(payload["receipt_path"], payload["receipt_sha256"], "recorded promotion receipt")
            if payload["experiment_event_sha256"] != current_experiment["event_sha256"]:
                raise AtomError("load-run", "promotion receipt is not bound to the current passed experiment event")
            if payload["assembly_sha256"] != current_experiment["assembly_sha256"]:
                raise AtomError("load-run", "promotion receipt is not bound to the current proven assembly")
            if "contract_surface" in request and payload["contract_surface"] != request["contract_surface"]:
                raise AtomError("load-run", "promotion contract_surface differs from the preserved atom request")
            _evidence(
                payload["evidence"],
                "recorded promotion evidence",
                "load-run",
                {case["case_id"] for case in request["captured_cases"]},
            )
            if baseline is not None:
                surface = _file_reference(payload["change_surface"], "recorded promotion change surface", "load-run")
                review = _file_reference(payload["review"], "recorded promotion review", "load-run")
                _validate_review(
                    Path(review["path"]),
                    surface["sha256"],
                    "recorded promotion review",
                    "load-run",
                )
            stage = "validation"
            next_skill = "prototype-driven-implementation"
            required_capability = "real-path-validation"
            current_promotion = {**payload, "event_sha256": event_sha256}
        elif record["event"] == "validation-recorded":
            if stage != "validation" or current_promotion is None:
                raise AtomError("load-run", f"validation-recorded appears during {stage!r}; restore the valid event order")
            validation_fields = (
                VALIDATION_EVENT_FIELDS
                if "blocker_closeout" in record["payload"]
                else LEGACY_VALIDATION_EVENT_FIELDS
            )
            payload = _exact(record["payload"], "validation-recorded payload", validation_fields, "load-run")
            _unchanged(payload["receipt_path"], payload["receipt_sha256"], "recorded validation receipt")
            if payload["promotion_event_sha256"] != current_promotion["event_sha256"]:
                raise AtomError("load-run", "validation receipt is not bound to the current promotion event")
            if payload["verdict"] not in {"passed", "failed"}:
                raise AtomError("load-run", f"validation verdict is {payload['verdict']!r}; restore 'passed' or 'failed'")
            try:
                _case_evidence(
                    payload["case_evidence"],
                    "recorded validation evidence",
                    "load-run",
                    [case["case_id"] for case in request["captured_cases"]],
                )
            except AtomError as error:
                superseded_legacy_failure = (
                    payload["verdict"] == "failed"
                    and any(item["event"] == "experiment-recorded"
                            for item in records[record_index + 1:])
                    and "has SHA-256" in str(error)
                )
                if not superseded_legacy_failure:
                    raise
                _case_evidence(
                    payload["case_evidence"],
                    "recorded validation evidence",
                    "load-run",
                    [case["case_id"] for case in request["captured_cases"]],
                    verify_hashes=False,
                )
                legacy_validation_evidence_drift.append({
                    "event_sha256": event_sha256,
                    "verdict": "failed",
                    "status": "superseded-external-evidence-drift",
                })
            closeout_clear = True
            if "blocker_closeout" in payload:
                closeout_clear = _recorded_blocker_closeout(
                    payload["blocker_closeout"], request, str(run),
                )["clear"]
            if payload["verdict"] == "passed" and closeout_clear:
                stage = "complete"
                next_skill = None
                required_capability = None
            elif payload["verdict"] == "failed":
                stage = "experiment"
                next_skill = "prototype-driven-implementation"
                required_capability = "experiment-machinery"
                current_experiment = None
                current_promotion = None
        elif record["event"] == "supersession-chain-closed":
            if stage != "complete" or supersession is None or supersession_chain_closed:
                raise AtomError("load-run", "supersession-chain-closed appears outside one completed open chain")
            payload = _exact(
                record["payload"],
                "supersession-chain-closed payload",
                CHAIN_CLOSED_EVENT_FIELDS,
                "load-run",
            )
            if payload["supersession_chain"] != supersession_chain:
                raise AtomError("load-run", "closed supersession chain differs from the recorded run chain")
            if payload["proof_event_sha256"] != hashes[record_index - 1]:
                raise AtomError("load-run", "supersession chain closure is not bound to the completion proof")
            supersession_chain_closed = True
        else:
            raise AtomError("load-run", f"unknown ledger event {record['event']!r}; restore a controller-written event")
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": request["atomic_step_id"],
        "stage": stage,
        "next_skill": next_skill,
        "required_capability": required_capability,
        "event_count": len(records),
        "latest_event_sha256": hashes[-1],
        "current_experiment": current_experiment,
        "current_promotion": current_promotion,
        "legacy_validation_evidence_drift": legacy_validation_evidence_drift,
        "supersession_chain": supersession_chain,
        "supersession_chain_closed": supersession_chain_closed,
        "contract_surface": request.get("contract_surface"),
        "prose_waiver": request.get("prose_waiver"),
    }


def start(
    request_path: Path,
    run: Path,
    supersedes: Path | None = None,
    prose_waiver_interview_path: Path | None = None,
) -> dict[str, Any]:
    request_path = request_path.absolute()
    run = run.absolute()
    if run.exists() and (not run.is_dir() or any(run.iterdir())):
        raise AtomError("start", f"run directory must be new or empty: {run}")
    repository_root = Path.cwd().resolve()
    raw_request = _load(request_path, "atom request", "validate-request")
    if type(raw_request) is dict and "prose_waiver" in raw_request:
        raise AtomError(
            "start",
            "atom request contains a hand-written prose_waiver; remove it, run prose-waiver-interview, "
            "and pass the completed interview to start",
        )
    request = _validate_request(
        raw_request,
        require_contract_surface=True,
        repository_root=repository_root,
        stage="start",
        allow_missing_prose_waiver=prose_waiver_interview_path is not None,
    )
    if prose_waiver_interview_path is not None:
        waiver = _verified_prose_waiver(prose_waiver_interview_path, request, repository_root)
        request = _validate_request(
            {**request, "prose_waiver": waiver},
            require_contract_surface=True,
            repository_root=repository_root,
            stage="start",
        )
    _require_disjoint_run(run, repository_root, request["allowed_paths"])
    supersession = None
    if supersedes is None:
        baseline = _baseline_document(request, repository_root)
    else:
        previous_run = supersedes.absolute()
        if previous_run == run:
            raise AtomError("start", "a run cannot supersede itself")
        try:
            previous_state = _state(previous_run)
        except AtomError as error:
            raise AtomError("start", f"cannot supersede {previous_run}: {error}") from None
        if previous_state["stage"] == "complete":
            raise AtomError("start", f"previous run {previous_run} is complete and cannot be superseded")
        previous_request = _request(previous_run)
        if previous_request["atomic_step_id"] != request["atomic_step_id"]:
            raise AtomError(
                "start",
                f"previous run atomic_step_id is {previous_request['atomic_step_id']!r}; "
                f"require {request['atomic_step_id']!r}",
            )
        previous_baseline = _baseline(previous_run, previous_request)
        if previous_baseline is None:
            raise AtomError("start", "previous run predates change baselines and cannot be superseded")
        prior_supersession = _supersession(previous_run, previous_request)
        chain = [] if prior_supersession is None else list(prior_supersession["chain"])
        previous_records, previous_hashes = _read_ledger(previous_run)
        previous_root = previous_records[0]["payload"]
        chain.append(
            {
                "run": str(previous_run),
                "request_sha256": previous_root["request_sha256"],
                "baseline_sha256": previous_root["baseline_sha256"],
                "latest_event_sha256": previous_hashes[-1],
            }
        )
        try:
            _verify_supersession_sources(chain, request["atomic_step_id"])
        except AtomError as error:
            raise AtomError("start", f"cannot supersede the recorded chain: {error}") from None
        earliest_run = Path(chain[0]["run"])
        earliest_request = _validate_request(
            _load(earliest_run / "inputs" / "atom-request.json", "earliest atom request", "start")
        )
        earliest_context = _baseline(earliest_run, earliest_request)
        if earliest_context is None:
            raise AtomError("start", "earliest superseded run has no change baseline")
        baseline = earliest_context[0]
        if baseline["repository_root"] != str(repository_root):
            raise AtomError(
                "start",
                f"supersession repository root is {baseline['repository_root']!r}; "
                f"run start from {str(repository_root)!r}",
            )
        if baseline["allowed_paths"] != request["allowed_paths"]:
            raise AtomError("start", "new request allowed_paths differ from the earliest superseded baseline")
        supersession = {
            "schema_version": CONTRACT,
            "atomic_step_id": request["atomic_step_id"],
            "previous_run": str(previous_run),
            "chain": chain,
        }
    run.mkdir(parents=True, exist_ok=True)
    request_sha256 = _write_new(run / "inputs" / "atom-request.json", _document(request))
    baseline_sha256 = _write_new(run / "inputs" / "change-baseline.json", _document(baseline))
    supersession_sha256 = None
    if supersession is not None:
        supersession_sha256 = _write_new(
            run / "inputs" / "supersession.json", _document(supersession)
        )
    first = {
        "sequence": 1,
        "event": "atom-started",
        "previous_event_sha256": None,
        "payload": {
            "atomic_step_id": request["atomic_step_id"],
            "request_sha256": request_sha256,
            "baseline_sha256": baseline_sha256,
            "repository_root": str(repository_root),
        },
    }
    if supersession_sha256 is not None:
        first["payload"]["supersession_sha256"] = supersession_sha256
    _write_new(run / "ledger.jsonl", json.dumps(first, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
    return _state(run)


def change_surface(run: Path, output: Path) -> dict[str, Any]:
    run = run.absolute()
    output = output.absolute()
    request = _request(run)
    surface = _derive_change_surface(run, request)
    sha256 = _write_new(output, _document(surface))
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": request["atomic_step_id"],
        "change_surface": {"path": str(output), "sha256": sha256},
        "changed_paths": [item["path"] for item in surface["changes"]],
    }


def _validate_stage_receipts(value: object) -> None:
    stage = "record-experiment"
    if type(value) is not list or len(value) != len(EXPERIMENT_STAGES):
        raise AtomError(stage, f"stages is not the complete ordered set {EXPERIMENT_STAGES!r}")
    for index, raw in enumerate(value):
        if type(raw) is not dict:
            raise AtomError(stage, f"stages[{index}] is {type(raw).__name__}; provide one object")
        fields = CURRENT_STAGE_FIELDS if "duration_ms" in raw else LEGACY_STAGE_FIELDS
        receipt = _exact(raw, f"stages[{index}]", fields, stage)
        expected_stage = EXPERIMENT_STAGES[index]
        if receipt["schema_version"] != CONTRACT or receipt["stage"] != expected_stage:
            raise AtomError(stage, f"stages[{index}] does not identify schema 1 stage {expected_stage!r}")
        if receipt["status"] != "completed" or receipt["exit_code"] != 0:
            raise AtomError(stage, f"stage {expected_stage!r} did not complete successfully")
        if receipt["promotion_applied"] is not False:
            raise AtomError(stage, f"stage {expected_stage!r} applied promotion; experiments must remain isolated")
        if fields is CURRENT_STAGE_FIELDS:
            if type(receipt["duration_ms"]) is not int or receipt["duration_ms"] < 0:
                raise AtomError(stage, f"stages[{index}].duration_ms must be one nonnegative integer")
            if type(receipt["timeout_ms"]) is not int or receipt["timeout_ms"] <= 0:
                raise AtomError(stage, f"stages[{index}].timeout_ms must be one positive integer")
            if receipt["timed_out"] is not False:
                raise AtomError(stage, f"successful stage {expected_stage!r} cannot be timed out")
            _sha(receipt["stdout_sha256"], f"stages[{index}].stdout_sha256", stage)
            _sha(receipt["stderr_sha256"], f"stages[{index}].stderr_sha256", stage)
            if receipt["timeout"] is not None or receipt["timeout_sha256"] is not None:
                raise AtomError(stage, f"successful stage {expected_stage!r} cannot carry timeout evidence")
        for field in ("output", "evidence", "evidence_sha256", "result", "result_sha256"):
            if field.endswith("sha256"):
                _sha(receipt[field], f"stages[{index}].{field}", stage)
            else:
                _nonempty(receipt[field], f"stages[{index}].{field}", stage)


def _payload_key_literals(path: Path, stage: str) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as error:
        raise AtomError(stage, f"champion module cannot be statically scanned at {path}: {error}") from None
    keys: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and type(node.args[0].value) is str
        ):
            keys.add(node.args[0].value)
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and type(node.slice.value) is str
        ):
            keys.add(node.slice.value)
    return sorted(keys)


def _contract_scan(assembly: Path, request: dict[str, Any], stage: str) -> dict[str, Any]:
    manifest = _load(assembly / "assembly.json", "verified assembly receipt", stage)
    operations = manifest.get("operations")
    if type(operations) is not list:
        raise AtomError(stage, "verified assembly receipt has no operations list")
    modules = []
    for index, operation in enumerate(operations):
        if type(operation) is not dict:
            raise AtomError(stage, f"assembly operation[{index}] is not one object")
        relative = operation.get("path")
        if type(relative) is not str or not relative.endswith(".py") or relative.startswith("tests/"):
            continue
        safe = _relative_path(relative, f"assembly operation[{index}].path", stage)
        path = assembly / "source" / safe
        expected = _sha(operation.get("sha256"), f"assembly operation[{index}].sha256", stage)
        if path.is_symlink() or not path.is_file():
            raise AtomError(stage, f"changed champion module is unavailable or linked at {path}")
        actual = _digest(path.read_bytes())
        if actual != expected:
            raise AtomError(stage, f"changed champion module {safe!r} has SHA-256 {actual}; require {expected}")
        modules.append({
            "path": safe,
            "sha256": expected,
            "observed_payload_keys": _payload_key_literals(path, stage),
        })
    surface = request["contract_surface"]
    report: dict[str, Any] = {
        "method": "python-ast-string-key-scan",
        "kind": surface["kind"],
        "modules": modules,
    }
    if surface["kind"] == "validation":
        declared = [item["field"] for item in surface["fields"]]
        leaves = [field.split(".")[-1].removesuffix("[]") for field in declared]
        observed = sorted({key for module in modules for key in module["observed_payload_keys"]})
        report["declared_fields"] = declared
        report["declared_leaf_keys"] = leaves
        report["observed_payload_keys"] = observed
        missing = [field for field, leaf in zip(declared, leaves) if leaf not in observed]
        if missing:
            raise AtomError(
                stage,
                f"champion module static scan did not see declared target field(s) {missing!r}; "
                f"observed payload keys were {observed!r}. Context keys may coexist, but every declared "
                "validation target must be read by name",
            )
    return report


def _verify_assembly(
    experiment: Path, request: dict[str, Any], expected_sha256: str
) -> dict[str, Any] | None:
    stage = "record-experiment"
    verifier = (
        Path(__file__).resolve().parents[2]
        / "experiment-machinery"
        / "scripts"
        / "development_probe_compose.py"
    )
    if verifier.is_symlink() or not verifier.is_file():
        raise AtomError(stage, f"Experiment Machinery assembly verifier is unavailable at {verifier}")
    assembly = experiment / "composition" / "assembly"
    completed = subprocess.run(
        [sys.executable, str(verifier), "verify", str(assembly)],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "verifier returned no diagnostic"
        raise AtomError(stage, f"Experiment Machinery refused the recorded assembly: {detail}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AtomError(stage, f"assembly verifier returned invalid JSON: {error}") from None
    expected_result = {
        "status": "verified",
        "atomic_step_id": request["atomic_step_id"],
        "assembly_sha256": expected_sha256,
        "promotion_applied": False,
    }
    if result != expected_result:
        raise AtomError(stage, f"assembly verifier returned {result!r}; require {expected_result!r}")
    manifest = _load(
        assembly / "development-manifest.json",
        "verified assembly development manifest",
        stage,
    )
    atomic_step = manifest.get("atomic_step")
    if type(atomic_step) is not dict:
        raise AtomError(stage, "verified assembly manifest has no atomic_step object")
    captured = atomic_step.get("captured_cases")
    if type(captured) is not list:
        raise AtomError(stage, "verified assembly manifest has no captured_cases list")
    source_field = "source" if manifest.get("schema_version") == 1 else "source_ref"
    expected_cases = [
        {
            "id": case["case_id"],
            source_field: case["source_ref"],
            "sha256": case["sha256"],
            "kind": case["kind"],
            "expected_outcome": case["expected_outcome"],
        }
        for case in request["captured_cases"]
    ]
    expected_atom = {
        "id": request["atomic_step_id"],
        "outcome": request["outcome"],
        "practical_value": request["practical_value"],
        "stopping_condition": request["stopping_condition"],
        "captured_cases": expected_cases,
    }
    if atomic_step != expected_atom:
        raise AtomError(stage, "verified assembly atom contract differs from the approved atom request")
    if "contract_surface" not in request:
        return None
    return _contract_scan(assembly, request, stage)


def record_experiment(run: Path, experiment: Path) -> dict[str, Any]:
    run = run.absolute()
    experiment = experiment.absolute()
    state = _state(run)
    if state["stage"] != "experiment":
        raise AtomError("record-experiment", f"current stage is {state['stage']!r}; require 'experiment'")
    request = _request(run)
    summary_path = experiment / "development-probe-summary.json"
    final_path = experiment / "final-verdict.json"
    summary = _exact(_load(summary_path, "development-probe summary", "record-experiment"), "summary", SUMMARY_FIELDS, "record-experiment")
    final = _exact(_load(final_path, "final verdict", "record-experiment"), "final verdict", FINAL_FIELDS, "record-experiment")
    problems = []
    for label, value in (("summary", summary), ("final verdict", final)):
        if value["schema_version"] != CONTRACT or type(value["schema_version"]) is not int:
            problems.append(f"{label} schema_version must be integer 1")
        if value["status"] != "completed":
            problems.append(f"{label} status must be 'completed'")
        if value["atomic_step_id"] != request["atomic_step_id"]:
            problems.append(f"{label} atomic_step_id must be {request['atomic_step_id']!r}")
        if value["promotion_applied"] is not False:
            problems.append(f"{label} promotion_applied must be false")
    if summary["verdict"] not in EXPERIMENT_VERDICTS or final["verdict"] not in EXPERIMENT_VERDICTS:
        problems.append(f"verdict must be one of {sorted(EXPERIMENT_VERDICTS)!r}")
    if summary["verdict"] != final["verdict"]:
        problems.append("summary verdict must equal final verdict")
    final_sha256 = _digest(final_path.read_bytes())
    if summary["final_verdict_sha256"] != final_sha256:
        problems.append(f"summary final_verdict_sha256 must be {final_sha256}")
    _sha(final["assembly_sha256"], "final verdict assembly_sha256", "record-experiment")
    _validate_stage_receipts(summary["stages"])
    contract_scan = _verify_assembly(experiment, request, final["assembly_sha256"])
    cases = final["cases"]
    if type(cases) is not list:
        problems.append("final verdict cases must be one ordered list")
        cases = []
    declared_ids = [item["case_id"] for item in request["captured_cases"]]
    observed_ids = []
    for index, raw in enumerate(cases):
        case = _exact(raw, f"final verdict cases[{index}]", EXPERIMENT_CASE_FIELDS, "record-experiment")
        observed_ids.append(case["case_id"])
        if case["verdict"] not in CASE_VERDICTS:
            problems.append(f"case {case['case_id']!r} verdict must be one of {sorted(CASE_VERDICTS)!r}")
        _nonempty(case["reason"], f"case {case['case_id']!r} reason", "record-experiment")
        _strings(case["evidence_pointers"], f"case {case['case_id']!r} evidence_pointers", "record-experiment")
    if observed_ids != declared_ids:
        problems.append(f"final verdict cases are {observed_ids!r}; require exact order {declared_ids!r}")
    if final["verdict"] == "passed" and any(item.get("verdict") != "satisfied" for item in cases):
        problems.append("passed verdict requires every case verdict to be 'satisfied'")
    if problems:
        raise AtomError("record-experiment", "; ".join(problems))
    experiment = _snapshot_experiment(run, experiment)
    summary_path = experiment / "development-probe-summary.json"
    final_path = experiment / "final-verdict.json"
    payload = {
        "experiment_path": str(experiment),
        "summary_sha256": _digest(summary_path.read_bytes()),
        "final_verdict_sha256": final_sha256,
        "assembly_sha256": final["assembly_sha256"],
        "verdict": final["verdict"],
    }
    if contract_scan is not None:
        payload["contract_scan"] = contract_scan
    _append(run, "experiment-recorded", payload)
    return _state(run)


def _require_introduced_fields_resolved(run: Path) -> None:
    """Atom 16: a field the atom introduced must resolve in the repository before promotion."""
    raw = _load(run / "inputs" / "atom-request.json", "stored atom request", "record-promotion")
    surface = raw.get("contract_surface") if type(raw) is dict else None
    fields = surface.get("fields") if type(surface) is dict else None
    if not fields or not any(type(f) is dict and f.get("introduced") for f in fields):
        return
    records, _ = _read_ledger(run)
    repository_root = Path(_nonempty(records[0]["payload"].get("repository_root"), "atom-started repository_root", "record-promotion"))
    _validate_request(
        raw,
        repository_root=repository_root,
        stage="record-promotion",
        allow_legacy_prose_waiver=True,
        require_introduced_resolved=True,
    )


def _within(path: str, allowed: list[str]) -> bool:
    return any(path == boundary or path.startswith(boundary + "/") for boundary in allowed)


def record_promotion(run: Path, receipt_path: Path) -> dict[str, Any]:
    run = run.absolute()
    state = _state(run)
    if state["stage"] != "promotion":
        raise AtomError("record-promotion", f"current stage is {state['stage']!r}; require 'promotion'")
    request = _request(run)
    _require_introduced_fields_resolved(run)
    baseline = _baseline(run, request)
    receipt_path = receipt_path.absolute()
    receipt_fields = (
        LEGACY_PROMOTION_FIELDS
        if baseline is None
        else CONTRACT_PROMOTION_FIELDS
        if "contract_surface" in request
        else PROMOTION_FIELDS
    )
    receipt = _exact(
        _load(receipt_path, "promotion receipt", "record-promotion"),
        "promotion receipt",
        receipt_fields,
        "record-promotion",
    )
    current = state["current_experiment"]
    problems = []
    if receipt["schema_version"] != CONTRACT or type(receipt["schema_version"]) is not int:
        problems.append("schema_version must be integer 1")
    if receipt["status"] != "promoted":
        problems.append("status must be 'promoted'")
    if receipt["atomic_step_id"] != request["atomic_step_id"]:
        problems.append(f"atomic_step_id must be {request['atomic_step_id']!r}")
    if receipt["controller"] != "prototype-driven-implementation":
        problems.append("controller must be 'prototype-driven-implementation'")
    if receipt["experiment_event_sha256"] != current["event_sha256"]:
        problems.append(f"experiment_event_sha256 must be {current['event_sha256']!r}")
    if receipt["experiment_assembly_sha256"] != current["assembly_sha256"]:
        problems.append(f"experiment_assembly_sha256 must be {current['assembly_sha256']!r}")
    if "contract_surface" in request and receipt["contract_surface"] != request["contract_surface"]:
        problems.append("contract_surface must exactly equal the preserved atom request declaration")
    changed = _strings(receipt["changed_paths"], "changed_paths", "record-promotion")
    normalized = [_relative_path(item, f"changed_paths[{index}]", "record-promotion") for index, item in enumerate(changed)]
    outside = [item for item in normalized if not _within(item, request["allowed_paths"])]
    if outside:
        problems.append(f"changed_paths {outside!r} fall outside allowed_paths {request['allowed_paths']!r}")
    evidence = _evidence(
        receipt["evidence"],
        "evidence",
        "record-promotion",
        {case["case_id"] for case in request["captured_cases"]},
        base=receipt_path.parent,
    )
    surface = None
    review = None
    if baseline is not None:
        surface = _file_reference(
            receipt["change_surface"],
            "change surface",
            "record-promotion",
            base=receipt_path.parent,
        )
        recorded_surface = _exact(
            _load(Path(surface["path"]), "change surface", "record-promotion"),
            "change surface",
            CHANGE_SURFACE_FIELDS,
            "record-promotion",
        )
        actual_surface = _derive_change_surface(run, request)
        if recorded_surface != actual_surface:
            problems.append("change surface is stale or substituted; regenerate it from the current allowed paths")
        actual_paths = [item["path"] for item in actual_surface["changes"]]
        if normalized != actual_paths:
            problems.append(
                f"changed_paths are {normalized!r}; require exact derived change surface {actual_paths!r}"
            )
        review = _file_reference(
            receipt["review"],
            "review",
            "record-promotion",
            base=receipt_path.parent,
        )
        _validate_review(Path(review["path"]), surface["sha256"], "review", "record-promotion")
    if problems:
        raise AtomError("record-promotion", "; ".join(problems))
    receipt, evidence, surface, review = _snapshot_promotion(
        run, receipt_path, evidence, surface, review,
    )
    payload = {
        "receipt_path": receipt["path"],
        "receipt_sha256": receipt["sha256"],
        "experiment_event_sha256": current["event_sha256"],
        "assembly_sha256": current["assembly_sha256"],
        "changed_paths": normalized,
        "evidence": evidence,
    }
    if surface is not None and review is not None:
        payload["change_surface"] = surface
        payload["review"] = review
    if "contract_surface" in request:
        payload["contract_surface"] = request["contract_surface"]
    _append(run, "promotion-recorded", payload)
    return _state(run)


def record_validation(run: Path, receipt_path: Path) -> dict[str, Any]:
    run = run.absolute()
    state = _state(run)
    if state["stage"] != "validation":
        raise AtomError("record-validation", f"current stage is {state['stage']!r}; require 'validation'")
    request = _request(run)
    receipt_path = receipt_path.absolute()
    receipt = _exact(_load(receipt_path, "validation receipt", "record-validation"), "validation receipt", VALIDATION_FIELDS, "record-validation")
    problems = []
    if receipt["schema_version"] != CONTRACT or type(receipt["schema_version"]) is not int:
        problems.append("schema_version must be integer 1")
    if receipt["status"] != "completed":
        problems.append("status must be 'completed'")
    if receipt["atomic_step_id"] != request["atomic_step_id"]:
        problems.append(f"atomic_step_id must be {request['atomic_step_id']!r}")
    promotion = state["current_promotion"]
    if receipt["promotion_event_sha256"] != promotion["event_sha256"]:
        problems.append(f"promotion_event_sha256 must be {promotion['event_sha256']!r}")
    cases = receipt["cases"]
    if type(cases) is not list:
        problems.append("cases must be one ordered list")
        cases = []
    declared_ids = [item["case_id"] for item in request["captured_cases"]]
    observed_ids = []
    statuses = []
    case_evidence = []
    declared_case_set = set(declared_ids)
    for index, raw in enumerate(cases):
        case = _exact(raw, f"cases[{index}]", VALIDATION_CASE_FIELDS, "record-validation")
        case_id = _nonempty(case["case_id"], f"cases[{index}].case_id", "record-validation")
        observed_ids.append(case_id)
        if case["verdict"] not in CASE_VERDICTS:
            problems.append(f"case {case_id!r} verdict must be one of {sorted(CASE_VERDICTS)!r}")
        statuses.append(case["verdict"])
        _nonempty(case["reason"], f"case {case_id!r} reason", "record-validation")
        case_evidence.append(
            {
                "case_id": case_id,
                "evidence": _evidence(
                    case["evidence"],
                    f"case {case_id!r} evidence",
                    "record-validation",
                    declared_case_set,
                    base=receipt_path.parent,
                    required_case_id=case_id,
                ),
            }
        )
    if observed_ids != declared_ids:
        problems.append(f"cases are {observed_ids!r}; require exact order {declared_ids!r}")
    if problems:
        raise AtomError("record-validation", "; ".join(problems))
    verdict = "passed" if statuses and all(status == "satisfied" for status in statuses) else "failed"
    closeout = _canonical_blocker_closeout(run, "record-validation")
    receipt_snapshot, case_evidence, closeout_snapshot = _snapshot_validation(
        run, receipt_path, case_evidence, closeout,
    )
    payload = {
        "receipt_path": receipt_snapshot["path"],
        "receipt_sha256": receipt_snapshot["sha256"],
        "promotion_event_sha256": promotion["event_sha256"],
        "verdict": verdict,
        "case_evidence": case_evidence,
        "blocker_closeout": closeout_snapshot,
    }
    _append(run, "validation-recorded", payload)
    return _state(run)


def authorize_next(run: Path) -> dict[str, Any]:
    run = run.absolute()
    state = _state(run)
    if state["stage"] != "complete":
        raise AtomError(
            "authorize-next",
            f"current stage is {state['stage']!r}; finish the reported required_capability before selecting another atom",
        )
    closeout = _canonical_blocker_closeout(run, "authorize-next")
    if not closeout["clear"]:
        raise AtomError(
            "authorize-next",
            f"canonical blocker closeout has {closeout['blocking_occurrence_count']} blocking occurrence(s)",
        )
    if len(state["supersession_chain"]) > 1 and not state["supersession_chain_closed"]:
        proof_event_sha256 = state["latest_event_sha256"]
        _append(
            run,
            "supersession-chain-closed",
            {
                "supersession_chain": state["supersession_chain"],
                "proof_event_sha256": proof_event_sha256,
            },
        )
        state = _state(run)
    return {
        "schema_version": CONTRACT,
        "atomic_step_id": state["atomic_step_id"],
        "authorized": True,
        "proof_event_sha256": state["latest_event_sha256"],
        "blocker_closeout_sha256": _digest(_document(closeout)),
        "linked_blocker_occurrences": closeout["linked_occurrence_count"],
        "supersession_chain": state["supersession_chain"],
        "supersession_chain_closed": state["supersession_chain_closed"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("request", type=Path)
    start_parser.add_argument("run", type=Path)
    start_parser.add_argument("--supersedes", type=Path)
    start_parser.add_argument("--prose-waiver-interview", type=Path)
    waiver_parser = commands.add_parser("prose-waiver-interview")
    waiver_parser.add_argument("request", type=Path)
    waiver_parser.add_argument("interview", type=Path)
    status_parser = commands.add_parser("status")
    status_parser.add_argument("run", type=Path)
    surface_parser = commands.add_parser("change-surface")
    surface_parser.add_argument("run", type=Path)
    surface_parser.add_argument("output", type=Path)
    experiment_parser = commands.add_parser("record-experiment")
    experiment_parser.add_argument("run", type=Path)
    experiment_parser.add_argument("experiment", type=Path)
    promotion_parser = commands.add_parser("record-promotion")
    promotion_parser.add_argument("run", type=Path)
    promotion_parser.add_argument("receipt", type=Path)
    validation_parser = commands.add_parser("record-validation")
    validation_parser.add_argument("run", type=Path)
    validation_parser.add_argument("receipt", type=Path)
    next_parser = commands.add_parser("authorize-next")
    next_parser.add_argument("run", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "start":
            result = start(
                args.request,
                args.run,
                args.supersedes,
                args.prose_waiver_interview,
            )
        elif args.command == "prose-waiver-interview":
            result = prose_waiver_interview(args.request, args.interview)
        elif args.command == "status":
            result = _state(args.run.absolute())
        elif args.command == "change-surface":
            result = change_surface(args.run, args.output)
        elif args.command == "record-experiment":
            result = record_experiment(args.run, args.experiment)
        elif args.command == "record-promotion":
            result = record_promotion(args.run, args.receipt)
        elif args.command == "record-validation":
            result = record_validation(args.run, args.receipt)
        else:
            result = authorize_next(args.run)
    except (AtomError, OSError) as error:
        stage = error.stage if isinstance(error, AtomError) else "runtime"
        print(f"Atom Building Machinery refused at {stage}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
