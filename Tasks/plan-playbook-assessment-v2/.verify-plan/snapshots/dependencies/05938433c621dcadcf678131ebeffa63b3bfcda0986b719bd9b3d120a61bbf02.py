#!/usr/bin/env python3
"""Dependency-free blind evaluation harness for research-playbook-v2."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = "evaluation-lock.json"
RECORDS_FILE = "records.json"
SCORE_FILE = "score.json"
V2_PACKAGE_FILES = {
    "manifest.json",
    "research.md",
    "requirements.json",
    "evidence-index.json",
    "findings.json",
    "planner-handoff.md",
}
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RUNTIME_AGENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,127}$")
RESEARCH_VALUE_TYPES = {"boolean", "number", "string", "array", "object", "null"}

CASE_IDS = (
    "current-runtime",
    "future-system",
    "missing-runtime-evidence",
    "mixed-maturity",
    "requirement-conflict",
    "scope-inflation-trap",
)
MATRIX_ARMS = (
    ("legacy", "research"),
    ("v2", "research"),
    ("v2", "planner"),
)
CLAIM_FIELDS = {"predicate_id", "scope_id", "maturity", "value", "evidence_ids"}
LEGACY_OUTPUT_FIELDS = {"schema_version", "claims", "material_gaps"}
PLANNER_OUTPUT_FIELDS = {"schema_version", "claims", "material_gaps", "planner"}
PLANNER_FIELDS = {"verdict", "checks", "obligations", "questions", "unresolved_choices"}
PLANNER_OBLIGATION_FIELDS = {
    "id",
    "implementation_steps",
    "verification_steps",
    "evidence_ids",
}
PACKAGE_PLANNER_OBLIGATION_FIELDS = {
    "id",
    "description",
    "status",
    "implementation_anchors",
    "verification_anchors",
    "required_inputs",
    "owner",
    "closure_condition",
    "evidence_ids",
}
PACKAGE_EVIDENCE_FIELDS = {
    "id",
    "source_kind",
    "source_locator",
    "source_sha256",
    "accessed_at",
    "supported_claim",
    "limitations",
}
REQUIRED_LIFECYCLE_ROLES = (
    "CORE_RESEARCHER",
    "INTERNAL_READINESS",
    "REQUIREMENTS_COVERAGE",
    "REQUIREMENTS_SATISFACTION",
    "ADJUDICATOR",
)
FIXTURE_MANIFEST = {
    "schema_version": SCHEMA_VERSION,
    "case_ids": list(CASE_IDS),
    "matrix": [f"{arm}:{role}" for arm, role in MATRIX_ARMS],
    "execution_count": len(CASE_IDS) * len(MATRIX_ARMS),
}
THRESHOLDS = {
    "max_invented_evidence": 0,
    "max_scope_drift": 0,
    "max_maturity_drift": 0,
    "min_critical_recall": 1.0,
    "v2_false_material_gaps_no_worse_than_legacy": True,
    "max_rounds": 3,
    "max_attempts": 15,
    "max_task_minutes": 60,
    "required_lifecycle_roles": list(REQUIRED_LIFECYCLE_ROLES),
    "planner_pass_required_per_case": True,
}


class HarnessError(Exception):
    def __init__(self, message: str, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


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
    raise HarnessError("research-value-is-not-canonical-json")


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise HarnessError(f"invalid-json:{path}:{exc}") from exc


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise HarnessError(f"cannot-read:{path}:{exc}") from exc


def _tree_hash(root: Path) -> str:
    """Match working-agreement/install_skills.py tree_hash byte-for-byte."""
    if not root.is_dir():
        raise HarnessError(f"missing-directory:{root}")
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _atomic_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _tree_snapshot(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise HarnessError(f"missing-directory:{root}")
    files: dict[str, str] = {}
    directories: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise HarnessError(f"symlink-not-allowed:{path}")
        if path.is_dir():
            directories.append(relative)
        elif path.is_file():
            files[relative] = _sha256_file(path)
        else:
            raise HarnessError(f"unsupported-tree-entry:{path}")
    return {
        "directories": directories,
        "files": files,
        "tree_sha256": _tree_hash(root),
    }


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(path, _canonical_bytes(value))


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HarnessError(f"{label}-must-be-object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise HarnessError(f"{label}-must-be-array")
    return value


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise HarnessError(f"{label}-must-be-nonempty-string")
    return value


def _require_runtime_agent_id(value: Any, label: str) -> str:
    agent_id = _require_string(value, label)
    lowered = agent_id.lower()
    placeholders = {"agent", "unknown", "none", "null", "n/a", "placeholder"}
    if (
        not RUNTIME_AGENT_ID.fullmatch(agent_id)
        or lowered in placeholders
        or lowered.startswith(("fake-", "synthetic-", "test-"))
        or "<" in agent_id
        or ">" in agent_id
    ):
        raise HarnessError(f"{label}-must-be-real-runtime-agent-id")
    return agent_id


def _unique_strings(value: Any, label: str) -> list[str]:
    items = _require_list(value, label)
    if any(not isinstance(item, str) or not item for item in items):
        raise HarnessError(f"{label}-must-contain-nonempty-strings")
    if len(items) != len(set(items)):
        raise HarnessError(f"{label}-contains-duplicates")
    return items


def _selected_case_ids(value: Any) -> tuple[str, ...]:
    if value is None or value == []:
        return CASE_IDS
    requested = _unique_strings(value, "selected-case-ids")
    unknown = sorted(set(requested) - set(CASE_IDS))
    if unknown:
        raise HarnessError(f"unknown-selected-case-ids:{','.join(unknown)}")
    requested_set = set(requested)
    return tuple(case_id for case_id in CASE_IDS if case_id in requested_set)


def _manifest_names(path: Path) -> list[str]:
    if not path.is_file():
        raise HarnessError(f"missing-manifest:{path}")
    names = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    names = [name for name in names if name and not name.startswith("#")]
    if not names or len(names) != len(set(names)):
        raise HarnessError("managed-manifest-must-contain-unique-names")
    if any(not SAFE_ID.fullmatch(name.replace("_", "a")) for name in names):
        raise HarnessError("managed-manifest-contains-unsafe-name")
    return names


def _managed_snapshot(manifest: Path, root: Path) -> dict[str, Any]:
    names = _manifest_names(manifest)
    if not root.is_dir():
        raise HarnessError(f"missing-directory:{root}")
    skills: dict[str, Any] = {}
    missing: list[str] = []
    for name in names:
        skill_root = root / name
        if not skill_root.exists():
            missing.append(name)
            continue
        if not skill_root.is_dir():
            raise HarnessError(f"managed-skill-not-directory:{name}")
        skills[name] = {"tree_sha256": _tree_hash(skill_root)}
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_sha256": _sha256_file(manifest),
        "managed_names": names,
        "missing_names": missing,
        "skills": skills,
    }


def cmd_snapshot_managed(args: argparse.Namespace) -> dict[str, Any]:
    manifest = Path(args.manifest).resolve()
    root = Path(args.root).resolve()
    snapshot = _managed_snapshot(manifest, root)
    _write_json(Path(args.output).resolve(), snapshot)
    return {
        "ok": True,
        "output": str(Path(args.output).resolve()),
        "managed_count": len(snapshot["managed_names"]),
        "snapshotted_count": len(snapshot["skills"]),
        "missing_names": snapshot["missing_names"],
        "snapshot_sha256": _sha256_bytes(_canonical_bytes(snapshot)),
    }


def _relative_target(root: Path, raw: str) -> tuple[str, Path]:
    path = Path(raw)
    if path.is_absolute() or raw != path.as_posix() or raw in {"", "."}:
        raise HarnessError(f"unsafe-restore-target:{raw}")
    target = (root / path).resolve()
    try:
        relative = target.relative_to(root).as_posix()
    except ValueError as exc:
        raise HarnessError(f"unsafe-restore-target:{raw}") from exc
    if relative != raw:
        raise HarnessError(f"unsafe-restore-target:{raw}")
    return relative, target


def _restore_plan(path: Path, root: Path) -> list[dict[str, Any]]:
    value = _require_dict(_read_json(path), "restore-plan")
    if set(value) != {"schema_version", "operations"} or value.get("schema_version") != SCHEMA_VERSION:
        raise HarnessError("invalid-restore-plan")
    operations = _require_list(value.get("operations"), "restore-operations")
    if not operations:
        raise HarnessError("restore-operations-must-be-nonempty")
    parsed: list[dict[str, Any]] = []
    targets: set[str] = set()
    for index, raw in enumerate(operations):
        operation = _require_dict(raw, f"restore-operation-{index}")
        kind = operation.get("kind")
        expected = {"kind", "target"} if kind == "move_aside" else {
            "kind", "source", "source_sha256", "target"
        }
        if kind not in {"restore_file", "move_aside"} or set(operation) != expected:
            raise HarnessError(f"invalid-restore-operation:{index}")
        relative, target = _relative_target(root, _require_string(operation.get("target"), f"restore-target-{index}"))
        if relative in targets:
            raise HarnessError(f"duplicate-restore-target:{relative}")
        targets.add(relative)
        if target.is_symlink():
            raise HarnessError(f"restore-target-symlink-not-allowed:{relative}")
        if kind == "move_aside":
            if not target.is_dir():
                raise HarnessError(f"restore-move-target-not-directory:{relative}")
            parsed.append({"kind": kind, "relative": relative, "target": target})
            continue
        source = Path(_require_string(operation.get("source"), f"restore-source-{index}"))
        source_hash = _require_string(operation.get("source_sha256"), f"restore-source-hash-{index}")
        if not source.is_absolute() or not HEX_64.fullmatch(source_hash):
            raise HarnessError(f"invalid-restore-source:{index}")
        source = source.resolve()
        if not source.is_file() or source.is_symlink() or _sha256_file(source) != source_hash:
            raise HarnessError(f"restore-source-mismatch:{source}")
        if target.exists() and not target.is_file():
            raise HarnessError(f"restore-target-not-file:{relative}")
        parsed.append({
            "kind": kind, "relative": relative, "target": target,
            "source": source, "source_sha256": source_hash,
        })
    return parsed


def cmd_restore_managed(args: argparse.Namespace) -> dict[str, Any]:
    manifest = Path(args.manifest).resolve()
    root = Path(args.root).resolve()
    expected = _require_dict(_read_json(Path(args.expected).resolve()), "expected-snapshot")
    if expected.get("schema_version") != SCHEMA_VERSION:
        raise HarnessError("unsupported-expected-snapshot-schema")
    _managed_snapshot_parts(expected, "expected")
    if expected.get("manifest_sha256") != _sha256_file(manifest):
        raise HarnessError("expected-snapshot-manifest-mismatch")
    current = _managed_snapshot(manifest, root)
    output = Path(args.output).resolve()
    if current == expected:
        _write_json(output, current)
        return {"ok": True, "already_restored": True, "output": str(output)}

    operations = _restore_plan(Path(args.plan).resolve(), root)
    backup_root = Path(args.backup_root).resolve()
    try:
        backup_root.relative_to(root)
    except ValueError:
        pass
    else:
        raise HarnessError("restore-backup-root-must-be-outside-managed-root")
    if backup_root.exists():
        raise HarnessError(f"restore-backup-root-already-exists:{backup_root}")

    applied: list[tuple[str, Path, Path, tuple[Path, ...]]] = []
    backup_root.mkdir(parents=True)
    try:
        for operation in operations:
            target = operation["target"]
            backup = backup_root / operation["kind"] / operation["relative"]
            backup.parent.mkdir(parents=True, exist_ok=True)
            if operation["kind"] == "move_aside":
                os.replace(target, backup)
                applied.append((operation["kind"], target, backup, ()))
            else:
                action = "restore_created"
                created_parents: list[Path] = []
                if target.exists():
                    if target.is_symlink() or not target.is_file():
                        raise HarnessError(f"restore-target-changed:{operation['relative']}")
                    shutil.copy2(target, backup)
                    action = "restore_existing"
                else:
                    parent = target.parent
                    while parent != root and not parent.exists():
                        created_parents.append(parent)
                        parent = parent.parent
                _atomic_write(target, operation["source"].read_bytes())
                applied.append((action, target, backup, tuple(created_parents)))
                continue
        restored = _managed_snapshot(manifest, root)
        if restored != expected:
            raise HarnessError("restored-managed-snapshot-mismatch")
        _write_json(output, restored)
    except Exception:
        try:
            for kind, target, backup, created_parents in reversed(applied):
                if kind == "move_aside":
                    os.replace(backup, target)
                elif kind == "restore_existing":
                    _atomic_write(target, backup.read_bytes())
                else:
                    target.unlink(missing_ok=True)
                    for parent in created_parents:
                        if parent.is_dir() and not any(parent.iterdir()):
                            parent.rmdir()
            shutil.rmtree(backup_root)
        except OSError as rollback_exc:
            raise HarnessError(f"restore-rollback-failed:{rollback_exc}") from rollback_exc
        raise
    return {
        "ok": True,
        "already_restored": False,
        "backup_root": str(backup_root),
        "operation_count": len(operations),
        "output": str(output),
        "snapshot_sha256": _sha256_bytes(_canonical_bytes(restored)),
    }


def _managed_snapshot_parts(
    snapshot: dict[str, Any], label: str
) -> tuple[list[str], list[str], dict[str, Any]]:
    names = _unique_strings(snapshot.get("managed_names"), f"{label}-managed-names")
    missing = _unique_strings(snapshot.get("missing_names"), f"{label}-missing-names")
    skills = _require_dict(snapshot.get("skills"), f"{label}-skills")
    if set(missing) & set(skills):
        raise HarnessError(f"{label}-managed-skill-both-present-and-missing")
    if set(missing) | set(skills) != set(names):
        raise HarnessError(f"{label}-managed-snapshot-name-mismatch")
    for name, raw_skill in skills.items():
        skill = _require_dict(raw_skill, f"{label}-skill-{name}")
        if set(skill) != {"tree_sha256"} or not HEX_64.fullmatch(
            str(skill.get("tree_sha256", ""))
        ):
            raise HarnessError(f"{label}-invalid-managed-skill-hash:{name}")
    return names, missing, skills


def cmd_compare_managed(args: argparse.Namespace) -> dict[str, Any]:
    before = _require_dict(_read_json(Path(args.before).resolve()), "before-snapshot")
    after = _require_dict(_read_json(Path(args.after).resolve()), "after-snapshot")
    for label, value in (("before", before), ("after", after)):
        if value.get("schema_version") != SCHEMA_VERSION:
            raise HarnessError(f"unsupported-{label}-snapshot-schema")
    before_names, before_missing, before_skills = _managed_snapshot_parts(before, "before")
    after_names, after_missing, after_skills = _managed_snapshot_parts(after, "after")
    if before_names != after_names:
        raise HarnessError("managed-manifest-names-changed")
    if before.get("manifest_sha256") != after.get("manifest_sha256"):
        raise HarnessError("managed-manifest-hash-changed")
    allowed_items = args.allow_added or []
    if len(allowed_items) != len(set(allowed_items)):
        raise HarnessError("duplicate-allowed-skill-name")
    allow_added = set(allowed_items)
    if any(not SAFE_ID.fullmatch(item) for item in allow_added):
        raise HarnessError("unsafe-allowed-skill-name")
    if not allow_added <= set(before_names):
        raise HarnessError("allowed-skill-is-not-manifest-managed")
    removed = sorted(set(before_skills) - set(after_skills))
    added = sorted(set(after_skills) - set(before_skills))
    changed = sorted(
        name for name in set(before_skills) & set(after_skills)
        if before_skills[name] != after_skills[name]
    )
    missing_managed = sorted(after_missing)
    unallowed_pre_missing = sorted(set(before_missing) - allow_added)
    unexpected_added = sorted(set(added) - allow_added)
    unused_allowance = sorted(allow_added - set(added))
    exact = bool(getattr(args, "exact", False))
    if exact and allow_added:
        raise HarnessError("exact-comparison-forbids-allowed-additions")
    if exact:
        return {
            "ok": before == after,
            "exact": True,
            "removed": removed,
            "changed": changed,
            "added": added,
            "stable_missing": sorted(set(before_missing) & set(after_missing)),
            "managed_unchanged": not removed and not changed,
        }
    passed = not any(
        (
            removed,
            changed,
            missing_managed,
            unallowed_pre_missing,
            unexpected_added,
            unused_allowance,
        )
    )
    return {
        "ok": passed,
        "removed": removed,
        "changed": changed,
        "added": added,
        "unexpected_added": unexpected_added,
        "unallowed_pre_missing": unallowed_pre_missing,
        "unused_allowance": unused_allowance,
        "managed_unchanged": not removed and not changed,
    }


def _validate_evidence(path: Path) -> tuple[dict[str, Any], set[str]]:
    value = _require_dict(_read_json(path), "evidence")
    if set(value) != {"schema_version", "evidence"}:
        raise HarnessError(f"invalid-evidence-fields:{path}")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise HarnessError(f"unsupported-evidence-schema:{path}")
    evidence = _require_list(value.get("evidence"), "evidence-items")
    ids: list[str] = []
    for index, item_value in enumerate(evidence):
        item = _require_dict(item_value, f"evidence-item-{index}")
        if set(item) != {"id", "text"}:
            raise HarnessError(f"invalid-evidence-item-fields:{path}:{index}")
        evidence_id = _require_string(item.get("id"), f"evidence-item-{index}-id")
        _require_string(item.get("text"), f"evidence-item-{index}-text")
        ids.append(evidence_id)
    if len(ids) != len(set(ids)):
        raise HarnessError(f"duplicate-evidence-id:{path}")
    return value, set(ids)


def _validate_public_contract(path: Path, case_id: str) -> dict[str, Any]:
    contract = _require_dict(_read_json(path), "public-output-contract")
    expected_fields = {
        "schema_version",
        "case_id",
        "scopes",
        "predicates",
        "material_gap_candidates",
        "planner_obligations",
    }
    if set(contract) != expected_fields:
        raise HarnessError(f"invalid-public-contract-fields:{case_id}")
    if contract.get("schema_version") != SCHEMA_VERSION or contract.get("case_id") != case_id:
        raise HarnessError(f"public-contract-identity-mismatch:{case_id}")

    scopes = _require_dict(contract.get("scopes"), "public-contract-scopes")
    if not scopes:
        raise HarnessError(f"public-contract-scopes-must-be-nonempty:{case_id}")
    for scope_id, maturity in scopes.items():
        if not isinstance(scope_id, str) or maturity not in {"CURRENT_RUNTIME", "FUTURE_SYSTEM"}:
            raise HarnessError(f"invalid-public-contract-scope:{case_id}")

    predicate_ids: list[str] = []
    for index, raw_predicate in enumerate(
        _require_list(contract.get("predicates"), "public-contract-predicates")
    ):
        predicate = _require_dict(raw_predicate, f"public-contract-predicate-{index}")
        if set(predicate) != {
            "id",
            "scope_id",
            "maturity",
            "question",
            "research_value_type",
        }:
            raise HarnessError(f"invalid-public-contract-predicate-fields:{case_id}:{index}")
        predicate_id = _require_string(
            predicate.get("id"), f"public-contract-predicate-{index}-id"
        )
        scope_id = _require_string(
            predicate.get("scope_id"), f"public-contract-predicate-{index}-scope"
        )
        _require_string(
            predicate.get("question"), f"public-contract-predicate-{index}-question"
        )
        if predicate.get("research_value_type") not in RESEARCH_VALUE_TYPES:
            raise HarnessError(
                f"invalid-public-contract-predicate-research-value-type:{case_id}:{predicate_id}"
            )
        if scope_id not in scopes or predicate.get("maturity") != scopes[scope_id]:
            raise HarnessError(
                f"public-contract-predicate-scope-mismatch:{case_id}:{predicate_id}"
            )
        predicate_ids.append(predicate_id)
    if not predicate_ids or len(predicate_ids) != len(set(predicate_ids)):
        raise HarnessError(f"invalid-public-contract-predicate-set:{case_id}")

    for field, label in (
        ("material_gap_candidates", "material-gap-candidate"),
        ("planner_obligations", "planner-obligation"),
    ):
        ids: list[str] = []
        for index, raw_item in enumerate(
            _require_list(contract.get(field), f"public-contract-{field}")
        ):
            item = _require_dict(raw_item, f"public-contract-{label}-{index}")
            if set(item) != {"id", "description"}:
                raise HarnessError(f"invalid-public-contract-{label}-fields:{case_id}:{index}")
            ids.append(_require_string(item.get("id"), f"public-contract-{label}-{index}-id"))
            _require_string(
                item.get("description"), f"public-contract-{label}-{index}-description"
            )
        if field == "planner_obligations" and not ids:
            raise HarnessError(f"public-contract-planner-obligations-must-be-nonempty:{case_id}")
        if len(ids) != len(set(ids)):
            raise HarnessError(f"duplicate-public-contract-{label}:{case_id}")
    return contract


def _validate_gold(
    path: Path,
    case_id: str,
    evidence_ids: set[str],
    public_contract: dict[str, Any],
) -> dict[str, Any]:
    gold = _require_dict(_read_json(path), "gold")
    expected_fields = {
        "schema_version",
        "case_id",
        "category",
        "scopes",
        "predicates",
        "true_material_gaps",
        "planner_rubric",
    }
    if set(gold) != expected_fields:
        raise HarnessError(f"invalid-gold-fields:{case_id}")
    if gold.get("schema_version") != SCHEMA_VERSION:
        raise HarnessError(f"unsupported-gold-schema:{path}")
    if gold.get("case_id") != case_id or gold.get("category") != case_id:
        raise HarnessError(f"gold-case-identity-mismatch:{case_id}")
    scopes = _require_dict(gold.get("scopes"), "gold-scopes")
    if scopes != public_contract["scopes"]:
        raise HarnessError(f"gold-public-scope-mismatch:{case_id}")
    if not scopes:
        raise HarnessError(f"gold-scopes-must-be-nonempty:{case_id}")
    for scope_id, maturity in scopes.items():
        if not isinstance(scope_id, str) or maturity not in {"CURRENT_RUNTIME", "FUTURE_SYSTEM"}:
            raise HarnessError(f"invalid-gold-scope:{case_id}")
    predicates = _require_list(gold.get("predicates"), "gold-predicates")
    public_predicates = {
        item["id"]: item for item in public_contract["predicates"]
    }
    predicate_ids: list[str] = []
    critical_count = 0
    for index, raw_predicate in enumerate(predicates):
        predicate = _require_dict(raw_predicate, f"gold-predicate-{index}")
        if set(predicate) != {
            "id",
            "scope_id",
            "maturity",
            "value",
            "required_evidence_ids",
            "critical",
        }:
            raise HarnessError(f"invalid-gold-predicate-fields:{case_id}:{index}")
        predicate_id = _require_string(predicate.get("id"), f"gold-predicate-{index}-id")
        scope_id = _require_string(predicate.get("scope_id"), f"gold-predicate-{index}-scope")
        if scope_id not in scopes or predicate.get("maturity") != scopes[scope_id]:
            raise HarnessError(f"gold-predicate-scope-mismatch:{case_id}:{predicate_id}")
        public_predicate = public_predicates.get(predicate_id)
        if (
            public_predicate is None
            or public_predicate["scope_id"] != scope_id
            or public_predicate["maturity"] != predicate.get("maturity")
        ):
            raise HarnessError(f"gold-public-predicate-mismatch:{case_id}:{predicate_id}")
        actual_value_type = _research_value_type(predicate.get("value"))
        if actual_value_type != public_predicate["research_value_type"]:
            raise HarnessError(f"gold-public-predicate-value-type-mismatch:{case_id}:{predicate_id}")
        required = _unique_strings(
            predicate.get("required_evidence_ids"),
            f"gold-predicate-{index}-required-evidence",
        )
        if not set(required) <= evidence_ids:
            raise HarnessError(f"gold-predicate-unknown-evidence:{case_id}:{predicate_id}")
        if not isinstance(predicate.get("critical"), bool):
            raise HarnessError(f"gold-predicate-critical-must-be-boolean:{case_id}:{predicate_id}")
        critical_count += int(predicate["critical"])
        predicate_ids.append(predicate_id)
    if not predicates or not critical_count or len(predicate_ids) != len(set(predicate_ids)):
        raise HarnessError(f"invalid-gold-predicate-set:{case_id}")
    if set(predicate_ids) != set(public_predicates):
        raise HarnessError(f"gold-public-predicate-set-mismatch:{case_id}")
    true_material_gaps = _unique_strings(
        gold.get("true_material_gaps"), "gold-true-material-gaps"
    )
    candidate_ids = {item["id"] for item in public_contract["material_gap_candidates"]}
    if not set(true_material_gaps) <= candidate_ids:
        raise HarnessError(f"gold-unknown-material-gap:{case_id}")
    planner_rubric = _unique_strings(gold.get("planner_rubric"), "gold-planner-rubric")
    if not planner_rubric:
        raise HarnessError(f"gold-planner-rubric-must-be-nonempty:{case_id}")
    if set(planner_rubric) != {
        item["id"] for item in public_contract["planner_obligations"]
    }:
        raise HarnessError(f"gold-public-planner-obligation-mismatch:{case_id}")
    return gold


def _matrix_entry(case_id: str, arm: str, role: str, raw_hash: str) -> dict[str, Any]:
    key = f"{case_id}:{arm}:{role}"
    if role == "research":
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "arm": arm,
            "role": role,
            "raw_snapshot_sha256": raw_hash,
            "invocation": "ordinary research prompt" if arm == "legacy" else "$research-playbook",
        }
        return {
            "key": key,
            "case_id": case_id,
            "arm": arm,
            "role": role,
            "input": {"kind": "locked_envelope", "sha256": _sha256_bytes(_canonical_bytes(envelope))},
            "output": (
                {"kind": "json", "exact_fields": sorted(LEGACY_OUTPUT_FIELDS)}
                if arm == "legacy"
                else {"kind": "v2_package", "exact_files": sorted(V2_PACKAGE_FILES)}
            ),
            "envelope": envelope,
        }
    source_key = f"{case_id}:v2:research"
    rule = {"kind": "recorded_output", "source_tuple": source_key}
    return {
        "key": key,
        "case_id": case_id,
        "arm": arm,
        "role": role,
        "input": {**rule, "derivation_sha256": _sha256_bytes(_canonical_bytes(rule))},
        "output": {"kind": "json", "exact_fields": sorted(PLANNER_OUTPUT_FIELDS)},
    }


def _validate_claim_output_shape(output: dict[str, Any], label: str) -> None:
    claims = _require_list(output.get("claims"), f"{label}-claims")
    for index, raw_claim in enumerate(claims):
        claim = _require_dict(raw_claim, f"{label}-claim-{index}")
        if set(claim) != CLAIM_FIELDS:
            raise HarnessError(f"invalid-{label}-claim-fields:{index}")
        for field in ("predicate_id", "scope_id", "maturity"):
            _require_string(claim.get(field), f"{label}-claim-{index}-{field}")
        _unique_strings(claim.get("evidence_ids"), f"{label}-claim-{index}-evidence")
    _unique_strings(output.get("material_gaps"), f"{label}-material-gaps")


def _validate_planner_output_shape(output: dict[str, Any], label: str) -> None:
    planner = _require_dict(output.get("planner"), f"{label}-planner")
    if set(planner) != PLANNER_FIELDS:
        raise HarnessError(f"invalid-{label}-planner-fields")
    if planner.get("verdict") not in {"PASS", "FAIL"}:
        raise HarnessError(f"invalid-{label}-planner-verdict")
    checks = _require_dict(planner.get("checks"), f"{label}-planner-checks")
    if any(not isinstance(key, str) or not key or not isinstance(value, bool) for key, value in checks.items()):
        raise HarnessError(f"invalid-{label}-planner-checks")
    obligations = _require_list(planner.get("obligations"), f"{label}-planner-obligations")
    for index, raw_obligation in enumerate(obligations):
        obligation = _require_dict(raw_obligation, f"{label}-planner-obligation-{index}")
        if set(obligation) != PLANNER_OBLIGATION_FIELDS:
            raise HarnessError(f"invalid-{label}-planner-obligation-fields:{index}")
        _require_string(obligation.get("id"), f"{label}-planner-obligation-{index}-id")
        for field in ("implementation_steps", "verification_steps"):
            steps = _unique_strings(
                obligation.get(field), f"{label}-planner-obligation-{index}-{field}"
            )
            if not steps:
                raise HarnessError(f"empty-{label}-planner-obligation-{field}:{index}")
        _unique_strings(
            obligation.get("evidence_ids"),
            f"{label}-planner-obligation-{index}-evidence",
        )
    _unique_strings(planner.get("questions"), f"{label}-planner-questions")
    _unique_strings(
        planner.get("unresolved_choices"), f"{label}-planner-unresolved-choices"
    )


def _validate_non_package_output(
    output: dict[str, Any], contract: dict[str, Any], key: str
) -> None:
    if contract.get("kind") != "json":
        raise HarnessError(f"invalid-output-contract:{key}")
    exact_fields = set(_unique_strings(contract.get("exact_fields"), "output-contract-fields"))
    if set(output) != exact_fields:
        raise HarnessError(f"invalid-output-fields:{key}")
    if output.get("schema_version") != SCHEMA_VERSION:
        raise HarnessError(f"unsupported-output-schema:{key}")
    _validate_claim_output_shape(output, "output")
    if "planner" in exact_fields:
        _validate_planner_output_shape(output, "output")


def _locked_payload(lock: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in lock.items() if key != "lock_sha256"}


def _load_lock(run_dir: Path, verify_artifacts: bool = True) -> dict[str, Any]:
    lock = _require_dict(_read_json(run_dir / LOCK_FILE), "evaluation-lock")
    if lock.get("schema_version") != SCHEMA_VERSION:
        raise HarnessError("unsupported-evaluation-lock-schema")
    expected = _sha256_bytes(_canonical_bytes(_locked_payload(lock)))
    if lock.get("lock_sha256") != expected:
        raise HarnessError("evaluation-lock-hash-mismatch")
    case_ids = tuple(_unique_strings(lock.get("case_ids"), "locked-case-ids"))
    if not case_ids or case_ids != _selected_case_ids(list(case_ids)):
        raise HarnessError("locked-case-ids-are-not-a-canonical-subset")
    matrix = _require_list(lock.get("matrix"), "locked-matrix")
    expected_keys = {
        f"{case_id}:{arm}:{role}"
        for case_id in case_ids
        for arm, role in MATRIX_ARMS
    }
    matrix_keys = {
        item.get("key") for item in matrix if isinstance(item, dict)
    }
    if len(matrix) != len(expected_keys) or matrix_keys != expected_keys:
        raise HarnessError("locked-matrix-does-not-match-selected-cases")
    for raw_item in matrix:
        item = _require_dict(raw_item, "locked-matrix-item")
        arm = _require_string(item.get("arm"), "locked-matrix-arm")
        role = _require_string(item.get("role"), "locked-matrix-role")
        expected_output = (
            {"kind": "v2_package", "exact_files": sorted(V2_PACKAGE_FILES)}
            if arm == "v2" and role == "research"
            else {
                "kind": "json",
                "exact_fields": sorted(
                    PLANNER_OUTPUT_FIELDS if role == "planner" else LEGACY_OUTPUT_FIELDS
                ),
            }
        )
        if item.get("output") != expected_output:
            raise HarnessError(f"locked-output-contract-drift:{item.get('key')}")
    if verify_artifacts:
        locked_cases = _require_dict(lock.get("cases"), "locked-cases")
        if set(locked_cases) != set(case_ids):
            raise HarnessError("locked-cases-do-not-match-selected-cases")
        for case_id, case in locked_cases.items():
            case_data = _require_dict(case, f"locked-case-{case_id}")
            input_dir = run_dir / "inputs" / case_id / "raw"
            if _tree_snapshot(input_dir)["tree_sha256"] != case_data.get("raw_snapshot_sha256"):
                raise HarnessError(f"staged-input-hash-mismatch:{case_id}")
        for name, skill in _require_dict(lock.get("skill_trees"), "locked-skill-trees").items():
            skill_data = _require_dict(skill, f"locked-skill-{name}")
            if _tree_snapshot(REPO_ROOT / skill_data["path"])["tree_sha256"] != skill_data.get("tree_sha256"):
                raise HarnessError(f"locked-skill-tree-drift:{name}")
        for item in matrix:
            matrix_item = _require_dict(item, "locked-matrix-item")
            input_rule = _require_dict(matrix_item.get("input"), "locked-matrix-input")
            if input_rule.get("kind") != "locked_envelope":
                continue
            envelope = _require_dict(matrix_item.get("envelope"), "locked-envelope")
            if _sha256_bytes(_canonical_bytes(envelope)) != input_rule.get("sha256"):
                raise HarnessError(f"locked-input-envelope-drift:{matrix_item['key']}")
    return lock


def cmd_prepare(args: argparse.Namespace) -> dict[str, Any]:
    fixtures = Path(args.fixtures).resolve()
    output = Path(args.output).resolve()
    manifest_path = fixtures / "manifest.json"
    manifest = _require_dict(_read_json(manifest_path), "fixture-manifest")
    if manifest != FIXTURE_MANIFEST:
        raise HarnessError("fixture-manifest-must-lock-exact-six-by-three-matrix")
    if output.exists() and any(output.iterdir()):
        raise HarnessError(f"prepare-output-not-empty:{output}")
    output.mkdir(parents=True, exist_ok=True)
    expected_root_names = {"manifest.json", *CASE_IDS}
    observed_root_names = {path.name for path in fixtures.iterdir()}
    if observed_root_names != expected_root_names:
        raise HarnessError("fixture-root-must-contain-only-manifest-and-exact-six-cases")
    case_dirs = sorted(path for path in fixtures.iterdir() if path.is_dir())
    observed_ids = tuple(path.name for path in case_dirs)
    if observed_ids != CASE_IDS:
        raise HarnessError(f"fixtures-must-be-exact-six:{','.join(observed_ids)}")
    selected_case_ids = _selected_case_ids(getattr(args, "case_id", None))

    cases: dict[str, Any] = {}
    matrix: list[dict[str, Any]] = []
    for case_dir in case_dirs:
        case_id = case_dir.name
        case_entries = sorted(path.name for path in case_dir.iterdir())
        if case_entries != ["gold.json", "raw"]:
            raise HarnessError(f"case-files-must-be-raw-and-gold:{case_id}")
        raw_dir = case_dir / "raw"
        if not raw_dir.is_dir() or raw_dir.is_symlink():
            raise HarnessError(f"missing-raw-directory:{case_id}")
        raw_entries = sorted(
            path.relative_to(raw_dir).as_posix() for path in raw_dir.rglob("*")
        )
        if raw_entries != ["evidence.json", "output-contract.json", "request.md"] or any(
            not path.is_file() or path.is_symlink() for path in raw_dir.iterdir()
        ):
            raise HarnessError(
                f"raw-case-files-must-be-request-evidence-and-output-contract:{case_id}"
            )
        if not (case_dir / "gold.json").is_file():
            raise HarnessError(f"missing-gold:{case_id}")
        if not (raw_dir / "request.md").read_text(encoding="utf-8").strip():
            raise HarnessError(f"empty-request:{case_id}")
        _, evidence_ids = _validate_evidence(raw_dir / "evidence.json")
        public_contract = _validate_public_contract(
            raw_dir / "output-contract.json", case_id
        )
        _validate_gold(case_dir / "gold.json", case_id, evidence_ids, public_contract)

        if case_id not in selected_case_ids:
            continue

        staged_raw = output / "inputs" / case_id / "raw"
        staged_raw.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(raw_dir, staged_raw)
        raw_snapshot = _tree_snapshot(staged_raw)
        cases[case_id] = {
            "raw_snapshot_sha256": raw_snapshot["tree_sha256"],
            "gold_sha256": _sha256_file(case_dir / "gold.json"),
        }
        for arm, role in MATRIX_ARMS:
            entry = _matrix_entry(case_id, arm, role, raw_snapshot["tree_sha256"])
            matrix.append(entry)

    skill_trees = {}
    for name, relative in (
        ("legacy", "tests/fixtures/research-playbook-legacy"),
        ("v2", "skills/research-playbook"),
    ):
        skill_trees[name] = {
            "path": relative,
            "tree_sha256": _tree_hash(REPO_ROOT / relative),
        }

    lock: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "fixture_manifest_sha256": _sha256_file(manifest_path),
        "case_ids": list(selected_case_ids),
        "cases": cases,
        "skill_trees": skill_trees,
        "thresholds": THRESHOLDS,
        "matrix": matrix,
    }
    lock["lock_sha256"] = _sha256_bytes(_canonical_bytes(lock))
    _write_json(output / LOCK_FILE, lock)
    _write_json(output / RECORDS_FILE, {"schema_version": SCHEMA_VERSION, "records": [], "records_sha256": _sha256_bytes(_canonical_bytes([]))})
    return {
        "ok": True,
        "run_dir": str(output),
        "case_count": len(cases),
        "execution_count": len(matrix),
        "lock_sha256": lock["lock_sha256"],
        "gold_staged_with_inputs": False,
    }


def _record_map(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {record["key"]: record for record in records}


def _load_records(run_dir: Path) -> list[dict[str, Any]]:
    state = _require_dict(_read_json(run_dir / RECORDS_FILE), "records-state")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise HarnessError("unsupported-records-schema")
    records = _require_list(state.get("records"), "records")
    if state.get("records_sha256") != _sha256_bytes(_canonical_bytes(records)):
        raise HarnessError("records-hash-mismatch")
    if any(not isinstance(record, dict) for record in records):
        raise HarnessError("record-must-be-object")
    if len(records) != len({record.get("key") for record in records}):
        raise HarnessError("duplicate-record-key-in-state")
    agent_ids: list[str] = []
    for index, record in enumerate(records):
        key = _require_string(record.get("key"), f"record-{index}-key")
        case_id = _require_string(record.get("case_id"), f"record-{index}-case-id")
        arm = _require_string(record.get("arm"), f"record-{index}-arm")
        role = _require_string(record.get("role"), f"record-{index}-role")
        if key != f"{case_id}:{arm}:{role}":
            raise HarnessError(f"record-declared-tuple-mismatch:{key}")
        agent_ids.append(
            _require_runtime_agent_id(record.get("agent_id"), f"record-{index}-agent-id")
        )
        if not HEX_64.fullmatch(str(record.get("input_sha256", ""))):
            raise HarnessError(f"record-invalid-input-hash:{key}")
        if not HEX_64.fullmatch(str(record.get("output_sha256", ""))):
            raise HarnessError(f"record-invalid-output-hash:{key}")
        if record.get("slot_closed") != "yes":
            raise HarnessError(f"record-slot-not-closed:{key}")
        output_path = _require_string(
            record.get("output_path"), f"record-{index}-output-path"
        )
        expected_path = (
            f"outputs/{case_id}/v2-research"
            if arm == "v2" and role == "research"
            else f"outputs/{case_id}/{arm}-{role}.json"
        )
        if output_path != expected_path:
            raise HarnessError(f"record-output-path-mismatch:{key}")
    if len(agent_ids) != len(set(agent_ids)):
        raise HarnessError("duplicate-agent-id-in-state")
    return records


def cmd_record(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    if args.slot_closed != "yes":
        raise HarnessError("slot-closed-must-be-yes")
    if not HEX_64.fullmatch(args.input_hash):
        raise HarnessError("input-hash-must-be-lowercase-sha256")
    if not HEX_64.fullmatch(args.output_hash):
        raise HarnessError("output-hash-must-be-lowercase-sha256")
    agent_id = _require_runtime_agent_id(args.agent_id, "agent-id")
    output_path = Path(args.output).resolve()
    package_output = args.arm == "v2" and args.role == "research"
    if package_output and (
        not output_path.is_dir()
        or output_path.is_symlink()
        or {path.name for path in output_path.iterdir()} != V2_PACKAGE_FILES
        or any(not path.is_file() or path.is_symlink() for path in output_path.iterdir())
    ):
        raise HarnessError(f"invalid-v2-package-output:{output_path}")
    if not package_output and not output_path.is_file():
        raise HarnessError(f"missing-output:{output_path}")
    output_bytes = None if package_output else output_path.read_bytes()
    output_hash = (
        _tree_snapshot(output_path)["tree_sha256"]
        if package_output
        else _sha256_bytes(output_bytes)
    )
    if args.output_hash != output_hash:
        raise HarnessError("declared-output-hash-mismatch")

    lock = _load_lock(run_dir)
    key = f"{args.case_id}:{args.arm}:{args.role}"
    matrix = {
        item["key"]: item for item in _require_list(lock.get("matrix"), "locked-matrix")
        if isinstance(item, dict)
    }
    if key not in matrix:
        raise HarnessError(f"undeclared-execution-tuple:{key}")
    output_contract = _require_dict(matrix[key].get("output"), "matrix-output-contract")
    if package_output:
        if output_contract != {
            "kind": "v2_package",
            "exact_files": sorted(V2_PACKAGE_FILES),
        }:
            raise HarnessError(f"invalid-output-contract:{key}")
    else:
        assert output_bytes is not None
        _validate_non_package_output(
            _require_dict(json.loads(output_bytes), f"output-{key}"),
            output_contract,
            key,
        )

    lock_path = run_dir / ".record.lock"
    lock_path.touch(exist_ok=True)
    with lock_path.open("rb") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        records = _load_records(run_dir)
        by_key = _record_map(records)
        if key in by_key:
            raise HarnessError(f"duplicate-execution-tuple:{key}")
        if agent_id in {record["agent_id"] for record in records}:
            raise HarnessError(f"reused-agent-id:{agent_id}")
        input_rule = _require_dict(matrix[key].get("input"), "matrix-input-rule")
        if input_rule.get("kind") == "locked_envelope":
            expected_input_hash = input_rule.get("sha256")
        elif input_rule.get("kind") == "recorded_output":
            source_key = input_rule.get("source_tuple")
            if source_key not in by_key:
                raise HarnessError(f"planner-source-not-recorded:{source_key}")
            expected_input_hash = by_key[source_key]["output_sha256"]
        else:
            raise HarnessError(f"invalid-input-rule:{key}")
        if args.input_hash != expected_input_hash:
            raise HarnessError(f"input-hash-mismatch:{key}")

        destination = (
            run_dir / "outputs" / args.case_id / "v2-research"
            if package_output
            else run_dir / "outputs" / args.case_id / f"{args.arm}-{args.role}.json"
        )
        if destination.exists():
            raise HarnessError(f"orphaned-or-conflicting-output:{destination}")
        if package_output:
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(
                tempfile.mkdtemp(
                    prefix=f".{destination.name}.",
                    suffix=".tmp",
                    dir=destination.parent,
                )
            )
            shutil.rmtree(staging)
            try:
                shutil.copytree(output_path, staging)
                os.replace(staging, destination)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                raise
        else:
            assert output_bytes is not None
            _atomic_write(destination, output_bytes)
        record = {
            "key": key,
            "case_id": args.case_id,
            "arm": args.arm,
            "role": args.role,
            "agent_id": agent_id,
            "input_sha256": args.input_hash,
            "output_sha256": output_hash,
            "output_path": destination.relative_to(run_dir).as_posix(),
            "slot_closed": "yes",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        records.append(record)
        records.sort(key=lambda item: item["key"])
        _write_json(run_dir / RECORDS_FILE, {
            "schema_version": SCHEMA_VERSION,
            "records": records,
            "records_sha256": _sha256_bytes(_canonical_bytes(records)),
        })
    return {"ok": True, "key": key, "output_sha256": output_hash, "recorded_count": len(records)}


def _load_v2_package(path: Path) -> dict[str, Any]:
    if (
        not path.is_dir()
        or path.is_symlink()
        or {item.name for item in path.iterdir()} != V2_PACKAGE_FILES
    ):
        raise HarnessError(f"invalid-recorded-v2-package:{path}")
    manifest = _require_dict(_read_json(path / "manifest.json"), "v2-package-manifest")
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("terminal_verdict") != "PASS":
        raise HarnessError("v2-package-manifest-must-be-terminal-pass")
    for field in ("candidate_hash", "envelope_hash"):
        if not HEX_64.fullmatch(str(manifest.get(field, ""))):
            raise HarnessError(f"v2-package-invalid-{field.replace('_', '-')}")
    artifact_hashes = _require_dict(
        manifest.get("artifact_hashes"), "v2-package-artifact-hashes"
    )
    expected_artifacts = V2_PACKAGE_FILES - {"manifest.json"}
    if set(artifact_hashes) != expected_artifacts:
        raise HarnessError("v2-package-artifact-hash-set-mismatch")
    for name, expected_hash in artifact_hashes.items():
        if not HEX_64.fullmatch(str(expected_hash)) or _sha256_file(path / name) != expected_hash:
            raise HarnessError(f"v2-package-artifact-hash-mismatch:{name}")

    evidence_index = _require_list(
        _read_json(path / "evidence-index.json"), "v2-package-evidence-index"
    )
    indexed_evidence: set[str] = set()
    for index, raw_evidence in enumerate(evidence_index):
        evidence = _require_dict(raw_evidence, f"v2-package-evidence-{index}")
        if set(evidence) != PACKAGE_EVIDENCE_FIELDS:
            raise HarnessError(f"v2-package-evidence-invalid-fields:{index}")
        evidence_id = _require_string(
            evidence.get("id"), f"v2-package-evidence-{index}-id"
        )
        if evidence_id in indexed_evidence:
            raise HarnessError(f"v2-package-duplicate-evidence:{evidence_id}")
        source_kind = evidence.get("source_kind")
        if source_kind not in {"LOCAL_FILE", "SUPPLIED_INPUT", "EXTERNAL"}:
            raise HarnessError(f"v2-package-evidence-invalid-source-kind:{evidence_id}")
        for field in ("source_locator", "supported_claim", "limitations"):
            _require_string(
                evidence.get(field), f"v2-package-evidence-{evidence_id}-{field}"
            )
        source_sha256 = evidence.get("source_sha256")
        accessed_at = evidence.get("accessed_at")
        if source_kind in {"LOCAL_FILE", "SUPPLIED_INPUT"}:
            if not HEX_64.fullmatch(str(source_sha256 or "")) or accessed_at is not None:
                raise HarnessError(
                    f"v2-package-evidence-invalid-local-provenance:{evidence_id}"
                )
        elif source_sha256 is not None or not isinstance(accessed_at, str) or not accessed_at.strip():
            raise HarnessError(
                f"v2-package-evidence-invalid-external-provenance:{evidence_id}"
            )
        indexed_evidence.add(evidence_id)

    claims: list[dict[str, Any]] = []
    planner_obligations: dict[str, dict[str, str]] = {}
    requirements = _require_list(
        _read_json(path / "requirements.json"), "v2-package-requirements"
    )
    for index, raw_requirement in enumerate(requirements):
        requirement = _require_dict(raw_requirement, f"v2-package-requirement-{index}")
        predicate_id = _require_string(
            requirement.get("id"), f"v2-package-requirement-{index}-id"
        )
        scope_id = _require_string(
            requirement.get("scope_id"), f"v2-package-requirement-{index}-scope"
        )
        maturity = _require_string(
            requirement.get("operational_maturity"),
            f"v2-package-requirement-{index}-maturity",
        )
        evidence_ids = _unique_strings(
            requirement.get("evidence_ids"),
            f"v2-package-requirement-{index}-evidence",
        )
        if not set(evidence_ids) <= indexed_evidence:
            raise HarnessError(f"v2-package-unindexed-claim-evidence:{predicate_id}")
        if "research_value" not in requirement:
            raise HarnessError(f"v2-package-research-value-required:{predicate_id}")
        research_value_type = _require_string(
            requirement.get("research_value_type"),
            f"v2-package-requirement-{index}-research-value-type",
        )
        if research_value_type not in RESEARCH_VALUE_TYPES:
            raise HarnessError(f"v2-package-invalid-research-value-type:{predicate_id}")
        if _research_value_type(requirement["research_value"]) != research_value_type:
            raise HarnessError(f"v2-package-research-value-type-mismatch:{predicate_id}")
        claims.append(
            {
                "predicate_id": predicate_id,
                "scope_id": scope_id,
                "maturity": maturity,
                "value": requirement["research_value"],
                "evidence_ids": evidence_ids,
            }
        )
        for obligation_index, raw_obligation in enumerate(
            _require_list(
                requirement.get("planner_obligations", []),
                f"v2-package-requirement-{index}-planner-obligations",
            )
        ):
            obligation = _require_dict(
                raw_obligation,
                f"v2-package-requirement-{index}-planner-obligation-{obligation_index}",
            )
            if set(obligation) != PACKAGE_PLANNER_OBLIGATION_FIELDS:
                raise HarnessError("v2-package-invalid-planner-obligation-fields")
            obligation_id = _require_string(
                obligation.get("id"), "v2-package-planner-obligation-id"
            )
            _require_string(
                obligation.get("description"),
                "v2-package-planner-obligation-description",
            )
            if obligation.get("status") != "READY":
                raise HarnessError("v2-package-planner-obligation-not-ready")
            for field in ("implementation_anchors", "verification_anchors"):
                if not _unique_strings(
                    obligation.get(field), f"v2-package-planner-obligation-{field}"
                ):
                    raise HarnessError(
                        f"v2-package-planner-obligation-{field}-must-be-nonempty"
                    )
            _unique_strings(
                obligation.get("required_inputs"),
                "v2-package-planner-obligation-required-inputs",
            )
            _require_string(
                obligation.get("owner"), "v2-package-planner-obligation-owner"
            )
            _require_string(
                obligation.get("closure_condition"),
                "v2-package-planner-obligation-closure-condition",
            )
            readiness_evidence = _unique_strings(
                obligation.get("evidence_ids"),
                "v2-package-planner-obligation-evidence",
            )
            if not readiness_evidence or not set(readiness_evidence) <= indexed_evidence:
                raise HarnessError("v2-package-planner-obligation-unindexed-evidence")
            public_obligation = {
                "id": obligation_id,
                "description": obligation["description"],
            }
            existing = planner_obligations.setdefault(obligation_id, public_obligation)
            if existing != public_obligation:
                raise HarnessError(
                    f"v2-package-conflicting-planner-obligation:{obligation_id}"
                )

    findings = _require_list(_read_json(path / "findings.json"), "v2-package-findings")
    material_gaps: list[str] = []
    for index, raw_finding in enumerate(findings):
        finding = _require_dict(raw_finding, f"v2-package-finding-{index}")
        raw = _require_dict(finding.get("raw_finding"), f"v2-package-raw-finding-{index}")
        finding_id = raw.get("id")
        if (
            isinstance(finding_id, str)
            and finding_id.strip()
            and finding.get("materiality") in {"BLOCKER", "PLANNING"}
            and finding.get("disposition")
            not in {"MERGE_DUPLICATE", "REJECT_NON_GAP"}
        ):
            material_gaps.append(finding_id)
    if len(material_gaps) != len(set(material_gaps)):
        raise HarnessError("v2-package-duplicate-material-gap")

    budget_use = _require_dict(manifest.get("budget_use"), "v2-package-budget-use")
    lifecycle = _require_list(
        manifest.get("lifecycle_evidence"), "v2-package-lifecycle-evidence"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "claims": claims,
        "material_gaps": material_gaps,
        "budget": {
            "rounds": budget_use.get("rounds_used"),
            "attempts": budget_use.get("attempts_used"),
            "workflow_elapsed_minutes": budget_use.get("workflow_minutes_used"),
            "minutes_max_per_task": budget_use.get("minutes_max_per_task"),
        },
        "lifecycle": lifecycle,
        "planner_contract": [
            planner_obligations[key] for key in sorted(planner_obligations)
        ],
    }


def _evaluate_claims(
    gold: dict[str, Any],
    output: dict[str, Any],
    allowed_evidence: set[str],
    public_contract: dict[str, Any],
) -> dict[str, Any]:
    scopes = _require_dict(gold.get("scopes"), "gold-scopes")
    gold_predicates = {
        item["id"]: item for item in _require_list(gold.get("predicates"), "gold-predicates")
        if isinstance(item, dict)
    }
    claims_raw = _require_list(output.get("claims"), "output-claims")
    public_predicates = {
        item["id"]: item for item in public_contract["predicates"]
    }
    claims: dict[str, dict[str, Any]] = {}
    invented_evidence: list[str] = []
    invented_claims: list[str] = []
    scope_drift: list[str] = []
    maturity_drift: list[str] = []
    for index, raw_claim in enumerate(claims_raw):
        claim = _require_dict(raw_claim, f"output-claim-{index}")
        predicate_id = _require_string(claim.get("predicate_id"), f"output-claim-{index}-predicate-id")
        if predicate_id in claims:
            raise HarnessError(f"duplicate-output-predicate:{predicate_id}")
        claims[predicate_id] = claim
        evidence_ids = _unique_strings(claim.get("evidence_ids"), f"output-claim-{index}-evidence")
        invented_evidence.extend(sorted(set(evidence_ids) - allowed_evidence))
        scope_id = claim.get("scope_id")
        if predicate_id not in public_predicates or predicate_id not in gold_predicates:
            invented_claims.append(predicate_id)
        public_predicate = public_predicates.get(predicate_id)
        if scope_id not in scopes or public_predicate is None:
            scope_drift.append(predicate_id)
        elif (
            claim.get("maturity") != scopes[scope_id]
            or scope_id != public_predicate["scope_id"]
            or claim.get("maturity") != public_predicate["maturity"]
        ):
            maturity_drift.append(predicate_id)

    critical_total = 0
    critical_recalled = 0
    missed_critical: list[str] = []
    for predicate_id, predicate in gold_predicates.items():
        if not predicate["critical"]:
            continue
        critical_total += 1
        claim = claims.get(predicate_id)
        matches = bool(
            claim is not None
            and claim.get("value") == predicate.get("value")
            and claim.get("scope_id") == predicate.get("scope_id")
            and claim.get("maturity") == predicate.get("maturity")
            and set(predicate["required_evidence_ids"]) <= set(claim.get("evidence_ids", []))
        )
        if matches:
            critical_recalled += 1
        else:
            missed_critical.append(predicate_id)

    material_gaps = _unique_strings(output.get("material_gaps"), "output-material-gaps")
    true_material_gaps = set(gold["true_material_gaps"])
    false_material_gaps = sorted(set(material_gaps) - true_material_gaps)
    missed_true_material_gaps = sorted(true_material_gaps - set(material_gaps))
    critical_total += len(true_material_gaps)
    critical_recalled += len(true_material_gaps & set(material_gaps))
    missed_critical.extend(missed_true_material_gaps)
    return {
        "invented_evidence": sorted(set(invented_evidence)),
        "invented_claims": sorted(set(invented_claims)),
        "scope_drift": sorted(set(scope_drift)),
        "maturity_drift": sorted(set(maturity_drift)),
        "critical_total": critical_total,
        "critical_recalled": critical_recalled,
        "missed_critical": missed_critical,
        "false_material_gaps": false_material_gaps,
        "missed_true_material_gaps": missed_true_material_gaps,
    }


def _evaluate_budget(output: dict[str, Any]) -> dict[str, Any]:
    budget = _require_dict(output.get("budget"), "v2-budget")
    values: dict[str, float] = {}
    for field in ("rounds", "attempts"):
        value = budget.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise HarnessError(f"v2-budget-{field}-must-be-nonnegative-integer")
        values[field] = value
    elapsed = budget.get("workflow_elapsed_minutes")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or elapsed < 0:
        raise HarnessError("v2-budget-workflow_elapsed_minutes-must-be-nonnegative-number")
    values["workflow_elapsed_minutes"] = elapsed
    task_max = budget.get("minutes_max_per_task")
    if isinstance(task_max, bool) or not isinstance(task_max, (int, float)) or task_max <= 0:
        raise HarnessError("v2-budget-minutes_max_per_task-must-be-positive-number")
    values["minutes_max_per_task"] = task_max
    lifecycle = _require_list(output.get("lifecycle"), "v2-lifecycle")
    roles: list[str] = []
    agent_ids: list[str] = []
    rounds: dict[int, set[str]] = {}
    for index, raw_event in enumerate(lifecycle):
        event = _require_dict(raw_event, f"v2-lifecycle-{index}")
        role = _require_string(event.get("role"), f"v2-lifecycle-{index}-role")
        if role not in REQUIRED_LIFECYCLE_ROLES:
            raise HarnessError(f"v2-lifecycle-{index}-unknown-role:{role}")
        agent_id = _require_runtime_agent_id(
            event.get("runtime_agent_id"),
            f"v2-lifecycle-{index}-runtime-agent-id",
        )
        input_hash = _require_string(
            event.get("input_envelope_hash"),
            f"v2-lifecycle-{index}-input-envelope-hash",
        )
        status = _require_string(event.get("status"), f"v2-lifecycle-{index}-status")
        if status not in {"SUCCEEDED", "FAILED"}:
            raise HarnessError(f"v2-lifecycle-{index}-invalid-status:{status}")
        output_hash = event.get("output_hash")
        if not HEX_64.fullmatch(input_hash):
            raise HarnessError(f"v2-lifecycle-{index}-invalid-input-envelope-hash")
        if status == "SUCCEEDED":
            if not isinstance(output_hash, str) or not HEX_64.fullmatch(output_hash):
                raise HarnessError(f"v2-lifecycle-{index}-invalid-output-hash")
        elif output_hash is not None and (
            not isinstance(output_hash, str) or not HEX_64.fullmatch(output_hash)
        ):
            raise HarnessError(f"v2-lifecycle-{index}-invalid-output-hash")
        if event.get("slot_closed") is not True:
            raise HarnessError(f"v2-lifecycle-{index}-slot-closed-must-be-true")
        close_evidence = event.get("close_evidence")
        if close_evidence is None or (
            isinstance(close_evidence, str) and not close_evidence.strip()
        ) or (
            isinstance(close_evidence, (list, dict)) and not close_evidence
        ):
            raise HarnessError(f"v2-lifecycle-{index}-close-evidence-required")
        round_number = event.get("round")
        if (
            isinstance(round_number, bool)
            or not isinstance(round_number, int)
            or not 1 <= round_number <= values["rounds"]
        ):
            raise HarnessError(f"v2-lifecycle-{index}-invalid-round")
        roles.append(role)
        agent_ids.append(agent_id)
        if status == "SUCCEEDED":
            rounds.setdefault(round_number, set()).add(role)
    missing_roles = sorted(set(REQUIRED_LIFECYCLE_ROLES) - set(roles))
    independent = len(agent_ids) == len(set(agent_ids))
    complete_rounds = sorted(
        round_number
        for round_number, round_roles in rounds.items()
        if set(REQUIRED_LIFECYCLE_ROLES) <= round_roles
    )
    attempts_match_lifecycle = values["attempts"] == len(lifecycle)
    passed = bool(
        1 <= values["rounds"] <= THRESHOLDS["max_rounds"]
        and attempts_match_lifecycle
        and values["attempts"] <= THRESHOLDS["max_attempts"]
        and values["minutes_max_per_task"] <= THRESHOLDS["max_task_minutes"]
        and not missing_roles
        and independent
        and complete_rounds
    )
    return {
        "pass": passed,
        **values,
        "missing_roles": missing_roles,
        "independent_agent_ids": independent,
        "all_slots_closed": True,
        "attempts_match_lifecycle": attempts_match_lifecycle,
        "complete_rounds": complete_rounds,
    }


def _evaluate_planner(
    gold: dict[str, Any],
    output: dict[str, Any],
    public_contract: dict[str, Any] | None = None,
    allowed_evidence: set[str] | None = None,
) -> dict[str, Any]:
    planner = _require_dict(output.get("planner"), "planner-result")
    checks = _require_dict(planner.get("checks"), "planner-checks")
    required = gold["planner_rubric"]
    missing = sorted(item for item in required if checks.get(item) is not True)
    unknown = sorted(set(checks) - set(required))
    obligations_raw = planner.get("obligations", [])
    obligations = obligations_raw if isinstance(obligations_raw, list) else []
    by_id: dict[str, dict[str, Any]] = {}
    invalid_obligations: list[str] = []
    for index, raw_obligation in enumerate(obligations):
        if not isinstance(raw_obligation, dict):
            invalid_obligations.append(f"index-{index}")
            continue
        obligation_id = raw_obligation.get("id")
        if not isinstance(obligation_id, str) or not obligation_id.strip() or obligation_id in by_id:
            invalid_obligations.append(str(obligation_id or f"index-{index}"))
            continue
        if set(raw_obligation) != {
            "id",
            "implementation_steps",
            "verification_steps",
            "evidence_ids",
        }:
            invalid_obligations.append(obligation_id)
            continue
        implementation_steps = raw_obligation.get("implementation_steps")
        verification_steps = raw_obligation.get("verification_steps")
        evidence_ids = raw_obligation.get("evidence_ids")
        if (
            not isinstance(implementation_steps, list)
            or not implementation_steps
            or any(not isinstance(item, str) or not item.strip() for item in implementation_steps)
            or not isinstance(verification_steps, list)
            or not verification_steps
            or any(not isinstance(item, str) or not item.strip() for item in verification_steps)
            or not isinstance(evidence_ids, list)
            or any(not isinstance(item, str) or not item.strip() for item in evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
            or (allowed_evidence is not None and not set(evidence_ids) <= allowed_evidence)
        ):
            invalid_obligations.append(obligation_id)
            continue
        by_id[obligation_id] = raw_obligation

    missing_obligations = sorted(set(required) - set(by_id))
    unknown_obligations = sorted(set(by_id) - set(required))
    contract_ids = (
        {item["id"] for item in public_contract["planner_obligations"]}
        if public_contract is not None
        else set(required)
    )
    contract_mismatch = sorted(contract_ids ^ set(required))
    questions = planner.get("questions", [])
    unresolved_choices = planner.get("unresolved_choices", [])
    clean_terminal = questions == [] and unresolved_choices == []
    passed = bool(
        planner.get("verdict") == "PASS"
        and not missing
        and not unknown
        and not invalid_obligations
        and not missing_obligations
        and not unknown_obligations
        and not contract_mismatch
        and clean_terminal
    )
    return {
        "pass": passed,
        "verdict": planner.get("verdict"),
        "failed_or_missing": missing,
        "unknown_checks": unknown,
        "missing_obligations": missing_obligations,
        "unknown_obligations": unknown_obligations,
        "invalid_obligations": invalid_obligations,
        "contract_mismatch": contract_mismatch,
        "questions_or_unresolved_choices": not clean_terminal,
    }


def cmd_score(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    lock = _load_lock(run_dir)
    records = _load_records(run_dir)
    declared_keys = {item["key"] for item in lock["matrix"]}
    recorded_keys = {record["key"] for record in records}
    if len(records) != len(declared_keys) or recorded_keys != declared_keys:
        missing = sorted(declared_keys - recorded_keys)
        extra = sorted(recorded_keys - declared_keys)
        raise HarnessError(f"incomplete-matrix:recorded={len(records)}:missing={','.join(missing)}:extra={','.join(extra)}")
    fixtures = Path(args.fixtures).resolve()
    manifest_path = fixtures / "manifest.json"
    if _sha256_file(manifest_path) != lock.get("fixture_manifest_sha256"):
        raise HarnessError("score-fixture-manifest-hash-mismatch")
    if {path.name for path in fixtures.iterdir()} != {"manifest.json", *CASE_IDS}:
        raise HarnessError("score-fixture-root-mismatch")
    gold_by_case: dict[str, dict[str, Any]] = {}
    for case_id in lock["case_ids"]:
        raw_dir = run_dir / "inputs" / case_id / "raw"
        _, evidence_ids = _validate_evidence(raw_dir / "evidence.json")
        public_contract = _validate_public_contract(
            raw_dir / "output-contract.json", case_id
        )
        gold_path = fixtures / case_id / "gold.json"
        if _sha256_file(gold_path) != lock["cases"][case_id]["gold_sha256"]:
            raise HarnessError(f"score-gold-hash-mismatch:{case_id}")
        gold_by_case[case_id] = _validate_gold(
            gold_path, case_id, evidence_ids, public_contract
        )
    records_by_key = _record_map(records)
    matrix_by_key = {item["key"]: item for item in lock["matrix"]}
    for record in records:
        input_rule = _require_dict(
            matrix_by_key[record["key"]].get("input"), "matrix-input-rule"
        )
        if input_rule.get("kind") == "locked_envelope":
            expected_input_hash = input_rule.get("sha256")
        elif input_rule.get("kind") == "recorded_output":
            source_key = input_rule.get("source_tuple")
            if source_key not in records_by_key:
                raise HarnessError(f"planner-source-not-recorded:{source_key}")
            expected_input_hash = records_by_key[source_key]["output_sha256"]
        else:
            raise HarnessError(f"invalid-input-rule:{record['key']}")
        if record["input_sha256"] != expected_input_hash:
            raise HarnessError(f"recorded-input-hash-mismatch:{record['key']}")

    per_execution: dict[str, Any] = {}
    aggregate = {
        "invented_evidence": 0,
        "invented_claims": 0,
        "scope_drift": 0,
        "maturity_drift": 0,
        "critical_total": 0,
        "critical_recalled": 0,
        "legacy_false_material_gaps": 0,
        "v2_false_material_gaps": 0,
    }
    budget_pass = True
    planner_pass = True
    for record in records:
        output_path = run_dir / record["output_path"]
        observed_output_hash = (
            _tree_snapshot(output_path)["tree_sha256"]
            if output_path.is_dir()
            else _sha256_file(output_path)
        )
        if observed_output_hash != record["output_sha256"]:
            raise HarnessError(f"recorded-output-hash-mismatch:{record['key']}")
        output = (
            _load_v2_package(output_path)
            if record["arm"] == "v2" and record["role"] == "research"
            else _require_dict(_read_json(output_path), f"output-{record['key']}")
        )
        if not (record["arm"] == "v2" and record["role"] == "research"):
            _validate_non_package_output(
                output,
                _require_dict(
                    matrix_by_key[record["key"]].get("output"),
                    "matrix-output-contract",
                ),
                record["key"],
            )
        if output.get("schema_version") != SCHEMA_VERSION:
            raise HarnessError(f"unsupported-output-schema:{record['key']}")
        gold = gold_by_case[record["case_id"]]
        _, allowed_evidence = _validate_evidence(
            run_dir / "inputs" / record["case_id"] / "raw" / "evidence.json"
        )
        public_contract = _validate_public_contract(
            run_dir / "inputs" / record["case_id"] / "raw" / "output-contract.json",
            record["case_id"],
        )
        claims = _evaluate_claims(gold, output, allowed_evidence, public_contract)
        detail: dict[str, Any] = {"claims": claims}
        if record["arm"] == "v2":
            aggregate["invented_evidence"] += len(claims["invented_evidence"])
            aggregate["invented_claims"] += len(claims["invented_claims"])
            aggregate["scope_drift"] += len(claims["scope_drift"])
            aggregate["maturity_drift"] += len(claims["maturity_drift"])
        if record["role"] == "research" and record["arm"] == "v2":
            aggregate["critical_total"] += claims["critical_total"]
            aggregate["critical_recalled"] += claims["critical_recalled"]
            aggregate["v2_false_material_gaps"] += len(claims["false_material_gaps"])
            budget = _evaluate_budget(output)
            detail["budget"] = budget
            expected_planner_contract = sorted(
                public_contract["planner_obligations"], key=lambda item: item["id"]
            )
            handoff_contract_pass = (
                output.get("planner_contract") == expected_planner_contract
            )
            detail["planner_contract_pass"] = handoff_contract_pass
            budget_pass = budget_pass and budget["pass"] and handoff_contract_pass
        elif record["role"] == "research" and record["arm"] == "legacy":
            aggregate["legacy_false_material_gaps"] += len(claims["false_material_gaps"])
        elif record["role"] == "planner":
            planner = _evaluate_planner(
                gold, output, public_contract, allowed_evidence
            )
            detail["planner"] = planner
            planner_pass = planner_pass and planner["pass"] and not claims["missed_critical"]
        per_execution[record["key"]] = detail

    recall = (
        aggregate["critical_recalled"] / aggregate["critical_total"]
        if aggregate["critical_total"] else 0.0
    )
    predicates = {
        "zero_invented_evidence": {
            "pass": aggregate["invented_evidence"] == 0 and aggregate["invented_claims"] == 0,
            "invented_evidence_count": aggregate["invented_evidence"],
            "invented_claim_count": aggregate["invented_claims"],
        },
        "zero_scope_maturity_drift": {
            "pass": aggregate["scope_drift"] == 0 and aggregate["maturity_drift"] == 0,
            "scope_drift_count": aggregate["scope_drift"],
            "maturity_drift_count": aggregate["maturity_drift"],
        },
        "complete_critical_recall": {
            "pass": recall == THRESHOLDS["min_critical_recall"],
            "recalled": aggregate["critical_recalled"],
            "total": aggregate["critical_total"],
            "ratio": recall,
        },
        "v2_false_material_gaps_no_worse_than_legacy": {
            "pass": aggregate["v2_false_material_gaps"] <= aggregate["legacy_false_material_gaps"],
            "v2_count": aggregate["v2_false_material_gaps"],
            "legacy_count": aggregate["legacy_false_material_gaps"],
        },
        "budget_compliance": {"pass": budget_pass},
        "planner_pass_every_case": {"pass": planner_pass},
    }
    passed = all(item["pass"] for item in predicates.values())
    score = {
        "schema_version": SCHEMA_VERSION,
        "verdict": "PASS" if passed else "FAIL",
        "matrix_complete": True,
        "predicates": predicates,
        "per_execution": per_execution,
    }
    _write_json(run_dir / SCORE_FILE, score)
    return score


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot-managed", help="Hash managed skill trees")
    snapshot.add_argument("--manifest", required=True)
    snapshot.add_argument("--root", required=True)
    snapshot.add_argument("--output", required=True)
    snapshot.set_defaults(func=cmd_snapshot_managed)

    compare = subparsers.add_parser("compare-managed", help="Compare managed skill snapshots")
    compare.add_argument("--before", required=True)
    compare.add_argument("--after", required=True)
    compare.add_argument("--allow-added", action="append", default=[])
    compare.add_argument("--exact", action="store_true")
    compare.set_defaults(func=cmd_compare_managed)

    restore = subparsers.add_parser(
        "restore-managed", help="Restore and verify an exact managed-skill snapshot"
    )
    restore.add_argument("--manifest", required=True)
    restore.add_argument("--root", required=True)
    restore.add_argument("--expected", required=True)
    restore.add_argument("--plan", required=True)
    restore.add_argument("--backup-root", required=True)
    restore.add_argument("--output", required=True)
    restore.set_defaults(func=cmd_restore_managed)

    prepare = subparsers.add_parser("prepare", help="Validate fixtures and lock an evaluation run")
    prepare.add_argument("--fixtures", required=True)
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--case-id", action="append", default=[])
    prepare.set_defaults(func=cmd_prepare)

    record = subparsers.add_parser("record", help="Record one declared execution")
    record.add_argument("--run-dir", required=True)
    record.add_argument("--case-id", required=True)
    record.add_argument("--arm", required=True)
    record.add_argument("--role", required=True)
    record.add_argument("--agent-id", required=True)
    record.add_argument("--input-hash", required=True)
    record.add_argument("--output", required=True)
    record.add_argument("--output-hash", required=True)
    record.add_argument("--slot-closed", required=True)
    record.set_defaults(func=cmd_record)

    score = subparsers.add_parser("score", help="Deterministically score a complete run")
    score.add_argument("--run-dir", required=True)
    score.add_argument("--fixtures", required=True)
    score.set_defaults(func=cmd_score)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
        print(json.dumps(result, sort_keys=True))
        if args.command in {"compare-managed", "score"} and not result.get("ok", result.get("verdict") == "PASS"):
            return 4
        return 0
    except HarnessError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except OSError as exc:
        print(json.dumps({"ok": False, "error": f"os-error:{exc}"}, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
