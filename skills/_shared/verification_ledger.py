#!/usr/bin/env python3
"""Shared verification ledger helper for verify-* skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


VALID_KINDS = {"analysis", "plan", "work"}
VALID_COVERAGE_STATUSES = {
    "unverified", "checked", "fixed", "out_of_scope", "deferred_by_critic",
    "deferred", "pending",
}
ACTIONABLE_CLASSIFICATIONS = {"FIX NOW", "IMPLEMENT LATER"}
RESOLVED_STATUSES = {
    "resolved", "fixed", "dismissed", "acknowledged", "checked", "out_of_scope",
    "deferred_by_critic", "deferred",
}
HASH_RE = re.compile(r"[0-9a-f]{64}")
PLAN_KEYS = {
    "contract_version", "plan_sha256", "evidence_revision_sha256", "inventory_sha256",
    "inventories", "assignments", "obligation_assessments", "critic_outputs",
    "coverage_exclusion_approvals",
}
INVENTORY_KEYS = {
    "inventory_sha256", "plan_sha256", "evidence_revision_sha256", "plan_sections",
    "evidence_items", "dependencies", "obligations", "completeness_approval",
    "completeness_approval_ref",
}
APPROVAL_REF_KEYS = {
    "critic_attempt_id", "critic_snapshot_path", "critic_snapshot_sha256",
    "approval_sha256",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and HASH_RE.fullmatch(value) is not None


def _exact_keys(value: Any, keys: set[str], prefix: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{prefix} must be an object")
        return False
    if set(value) != keys:
        errors.append(f"{prefix} must contain exactly {sorted(keys)}")
        return False
    return True


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sorted_unique_strings(value: Any, prefix: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not _nonempty(item) for item in value):
        errors.append(f"{prefix} must be an array of non-empty strings")
        return []
    if value != sorted(set(value)):
        errors.append(f"{prefix} must be sorted and unique")
    return list(value)


def _empty_ledger(
    kind: str,
    target: str | None = None,
    *,
    plan_sha256: str | None = None,
    evidence_revision_sha256: str | None = None,
) -> dict[str, Any]:
    ledger: dict[str, Any] = {
        "kind": kind,
        "target": target or "",
        "iteration": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "coverage_queue": [],
        "findings": [],
        "iteration_log": [],
    }
    if kind == "plan":
        ledger["plan_verification"] = {
            "contract_version": 1,
            "plan_sha256": plan_sha256,
            "evidence_revision_sha256": evidence_revision_sha256,
            "inventory_sha256": None,
            "inventories": [],
            "assignments": [],
            "obligation_assessments": [],
            "critic_outputs": [],
            "coverage_exclusion_approvals": [],
        }
    return ledger


def _load(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"ledger not found: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"ledger is not valid JSON: {exc}"]
    if not isinstance(data, dict):
        return None, ["ledger root must be an object"]
    return data, []


def _validate_common(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    kind = data.get("kind")
    if kind not in VALID_KINDS:
        errors.append(f"kind must be one of {sorted(VALID_KINDS)}")
    if "target" not in data:
        errors.append("target is required")
    if not isinstance(data.get("iteration", 0), int):
        errors.append("iteration must be an integer")

    coverage = data.get("coverage_queue")
    if not isinstance(coverage, list):
        errors.append("coverage_queue must be an array")
    else:
        seen_ids: set[str] = set()
        for idx, item in enumerate(coverage):
            prefix = f"coverage_queue[{idx}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix} must be an object")
                continue
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                errors.append(f"{prefix}.id is required")
            elif item_id in seen_ids:
                errors.append(f"{prefix}.id is duplicated: {item_id}")
            seen_ids.add(item_id)
            if not str(item.get("summary") or "").strip():
                errors.append(f"{prefix}.summary is required")
            if str(item.get("risk") or "").strip() not in {"high", "medium", "low"}:
                errors.append(f"{prefix}.risk must be high, medium, or low")
            if str(item.get("status") or "").strip() not in VALID_COVERAGE_STATUSES:
                errors.append(
                    f"{prefix}.status must be one of {sorted(VALID_COVERAGE_STATUSES)}"
                )
            evidence = item.get("evidence_to_inspect", [])
            if evidence is not None and not isinstance(evidence, list):
                errors.append(f"{prefix}.evidence_to_inspect must be an array when present")

    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be an array")
    else:
        seen_finding_ids: set[str] = set()
        for idx, finding in enumerate(findings):
            prefix = f"findings[{idx}]"
            if not isinstance(finding, dict):
                errors.append(f"{prefix} must be an object")
                continue
            finding_id = str(finding.get("id") or "").strip()
            if not finding_id:
                errors.append(f"{prefix}.id is required")
            elif finding_id in seen_finding_ids:
                errors.append(f"{prefix}.id is duplicated: {finding_id}")
            seen_finding_ids.add(finding_id)
            if "iteration_first_seen" in finding and not isinstance(
                finding["iteration_first_seen"], int
            ):
                errors.append(f"{prefix}.iteration_first_seen must be an integer")

    if not isinstance(data.get("iteration_log"), list):
        errors.append("iteration_log must be an array")
    return errors


def _safe_relative_file(base: Path, relative: Any, prefix: str, errors: list[str]) -> Path | None:
    if not isinstance(relative, str) or not relative:
        errors.append(f"{prefix} must be a non-empty relative path")
        return None
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
        errors.append(f"{prefix} must be a normalized contained relative path")
        return None
    cursor = base.resolve()
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            errors.append(f"{prefix} must not traverse a symlink")
            return None
    try:
        resolved = cursor.resolve(strict=True)
    except FileNotFoundError:
        errors.append(f"{prefix} does not exist: {relative}")
        return None
    if not resolved.is_relative_to(base.resolve()) or not resolved.is_file():
        errors.append(f"{prefix} must resolve to a contained regular file")
        return None
    return resolved


def _repository_root(path: Path) -> Path | None:
    for candidate in (path.resolve(), *path.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _json_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError("invalid-json-pointer")
    current = value
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current[token]
        elif isinstance(current, list):
            if token == "-" or not token.isdigit():
                raise ValueError("invalid-json-pointer-index")
            current = current[int(token)]
        else:
            raise ValueError("json-pointer-through-scalar")
    return current


def _validate_plan_sections(
    records: Any, base: Path, prefix: str, errors: list[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    keys = {"id", "path", "start_line", "end_line", "content_sha256"}
    if not isinstance(records, list):
        errors.append(f"{prefix} must be an array")
        return result
    ids = [item.get("id") for item in records if isinstance(item, dict)]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        errors.append(f"{prefix} must be sorted by unique id")
    for idx, record in enumerate(records):
        item_prefix = f"{prefix}[{idx}]"
        if not _exact_keys(record, keys, item_prefix, errors):
            continue
        item_id = record["id"]
        if not _nonempty(item_id):
            errors.append(f"{item_prefix}.id is required")
            continue
        start, end = record["start_line"], record["end_line"]
        if (
            isinstance(start, bool) or not isinstance(start, int) or start < 1
            or isinstance(end, bool) or not isinstance(end, int) or end < start
        ):
            errors.append(f"{item_prefix} has invalid inclusive line bounds")
        path = _safe_relative_file(base, record["path"], f"{item_prefix}.path", errors)
        if path is not None:
            try:
                lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            except UnicodeDecodeError:
                errors.append(f"{item_prefix}.path must be UTF-8")
            else:
                if end > len(lines):
                    errors.append(f"{item_prefix}.end_line exceeds the file")
                else:
                    selected = "".join(lines[start - 1:end]).encode("utf-8")
                    if _sha256(selected) != record["content_sha256"]:
                        errors.append(f"{item_prefix}.content_sha256 mismatch")
        if not _is_hash(record["content_sha256"]):
            errors.append(f"{item_prefix}.content_sha256 must be sha256")
        result[item_id] = record
    return result


def _validate_source_records(
    records: Any, base: Path, prefix: str, errors: list[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    keys = {"id", "source_ref", "content_sha256"}
    ref_keys = {"repository_key", "path", "selector"}
    if not isinstance(records, list):
        errors.append(f"{prefix} must be an array")
        return result
    ids = [item.get("id") for item in records if isinstance(item, dict)]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        errors.append(f"{prefix} must be sorted by unique id")
    for idx, record in enumerate(records):
        item_prefix = f"{prefix}[{idx}]"
        if not _exact_keys(record, keys, item_prefix, errors):
            continue
        item_id = record["id"]
        if not _nonempty(item_id):
            errors.append(f"{item_prefix}.id is required")
            continue
        ref = record["source_ref"]
        if not _exact_keys(ref, ref_keys, f"{item_prefix}.source_ref", errors):
            continue
        if not _nonempty(ref["repository_key"]):
            errors.append(f"{item_prefix}.source_ref.repository_key is required")
        path = _safe_relative_file(base, ref["path"], f"{item_prefix}.source_ref.path", errors)
        selector = ref["selector"]
        selected: bytes | None = None
        if path is not None:
            if selector == "WHOLE_FILE":
                selected = path.read_bytes()
            elif isinstance(selector, str):
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                    selected = _canonical_bytes(_json_pointer(value, selector))
                except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, ValueError):
                    errors.append(f"{item_prefix}.source_ref.selector is invalid")
            else:
                errors.append(f"{item_prefix}.source_ref.selector is invalid")
        if not _is_hash(record["content_sha256"]):
            errors.append(f"{item_prefix}.content_sha256 must be sha256")
        elif selected is not None and _sha256(selected) != record["content_sha256"]:
            errors.append(f"{item_prefix}.content_sha256 mismatch")
        result[item_id] = record
    return result


def _validate_string_evidence(value: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value or any(not _nonempty(item) for item in value):
        errors.append(f"{prefix} must be a non-empty string array")


def _validate_inventory_approval(value: Any, prefix: str, errors: list[str]) -> None:
    keys = {
        "inventory_sha256", "plan_sha256", "evidence_revision_sha256", "decision",
        "rationale", "evidence",
    }
    if not _exact_keys(value, keys, prefix, errors):
        return
    for field in ("inventory_sha256", "plan_sha256", "evidence_revision_sha256"):
        if not _is_hash(value[field]):
            errors.append(f"{prefix}.{field} must be sha256")
    if value["decision"] not in {"APPROVED", "REJECTED"}:
        errors.append(f"{prefix}.decision is invalid")
    if not _nonempty(value["rationale"]):
        errors.append(f"{prefix}.rationale is required")
    _validate_string_evidence(value["evidence"], f"{prefix}.evidence", errors)


def _validate_assessment_approval(value: Any, prefix: str, errors: list[str]) -> None:
    keys = {
        "iteration", "obligation_id", "binding_sha256", "assessment_fingerprint",
        "decision", "rationale", "evidence",
    }
    if not _exact_keys(value, keys, prefix, errors):
        return
    if isinstance(value["iteration"], bool) or not isinstance(value["iteration"], int) or value["iteration"] < 1:
        errors.append(f"{prefix}.iteration must be positive")
    if not _nonempty(value["obligation_id"]):
        errors.append(f"{prefix}.obligation_id is required")
    for field in ("binding_sha256", "assessment_fingerprint"):
        if not _is_hash(value[field]):
            errors.append(f"{prefix}.{field} must be sha256")
    if value["decision"] not in {"APPROVED", "REJECTED"}:
        errors.append(f"{prefix}.decision is invalid")
    if not _nonempty(value["rationale"]):
        errors.append(f"{prefix}.rationale is required")
    _validate_string_evidence(value["evidence"], f"{prefix}.evidence", errors)


def _validate_exclusion_approval(value: Any, prefix: str, errors: list[str]) -> None:
    keys = {
        "coverage_id", "prior_status", "approved_status", "plan_sha256",
        "evidence_revision_sha256", "inventory_sha256", "rationale", "evidence",
    }
    if not _exact_keys(value, keys, prefix, errors):
        return
    if value["approved_status"] not in {"out_of_scope", "deferred_by_critic"}:
        errors.append(f"{prefix}.approved_status is invalid")
    for field in ("plan_sha256", "evidence_revision_sha256", "inventory_sha256"):
        if not _is_hash(value[field]):
            errors.append(f"{prefix}.{field} must be sha256")
    if not _nonempty(value["coverage_id"]) or not _nonempty(value["rationale"]):
        errors.append(f"{prefix} requires coverage_id and rationale")
    _validate_string_evidence(value["evidence"], f"{prefix}.evidence", errors)


def _load_critic_outputs(
    records: Any, base: Path, errors: list[str],
) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}
    keys = {"attempt_id", "snapshot_path", "output_sha256"}
    if not isinstance(records, list):
        errors.append("plan_verification.critic_outputs must be an array")
        return outputs
    for idx, record in enumerate(records):
        prefix = f"plan_verification.critic_outputs[{idx}]"
        if not _exact_keys(record, keys, prefix, errors):
            continue
        attempt_id = record["attempt_id"]
        if not _nonempty(attempt_id) or attempt_id in outputs:
            errors.append(f"{prefix}.attempt_id is missing or duplicated")
            continue
        expected_path = f".verify-plan/critic-outputs/{attempt_id}.json"
        if record["snapshot_path"] != expected_path:
            errors.append(f"{prefix}.snapshot_path must equal {expected_path}")
        path = _safe_relative_file(base, record["snapshot_path"], f"{prefix}.snapshot_path", errors)
        if path is None:
            continue
        raw = path.read_bytes()
        if not _is_hash(record["output_sha256"]) or _sha256(raw) != record["output_sha256"]:
            errors.append(f"{prefix}.output_sha256 mismatch")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"{prefix} snapshot must be canonical JSON")
            continue
        if raw != _canonical_bytes(payload):
            errors.append(f"{prefix} snapshot bytes are not canonical")
        payload_keys = {
            "schema_version", "attempt_id", "inventory_approval",
            "assessment_approvals", "coverage_exclusion_approvals",
        }
        if not _exact_keys(payload, payload_keys, f"{prefix}.snapshot", errors):
            continue
        if payload["schema_version"] != 1 or payload["attempt_id"] != attempt_id:
            errors.append(f"{prefix} snapshot identity mismatch")
        if payload["inventory_approval"] is not None:
            _validate_inventory_approval(
                payload["inventory_approval"], f"{prefix}.snapshot.inventory_approval", errors,
            )
        for field, validator in (
            ("assessment_approvals", _validate_assessment_approval),
            ("coverage_exclusion_approvals", _validate_exclusion_approval),
        ):
            values = payload[field]
            if not isinstance(values, list):
                errors.append(f"{prefix}.snapshot.{field} must be an array")
                continue
            hashes = [_sha256(item) for item in values]
            if hashes != sorted(set(hashes)):
                errors.append(f"{prefix}.snapshot.{field} must be hash-sorted and unique")
            for item_idx, item in enumerate(values):
                validator(item, f"{prefix}.snapshot.{field}[{item_idx}]", errors)
        outputs[attempt_id] = {"record": record, "payload": payload}
    return outputs


def _validate_approval_ref(
    approval: Any,
    ref: Any,
    *,
    approval_kind: str,
    outputs: dict[str, dict[str, Any]],
    used: set[tuple[str, str]],
    prefix: str,
    errors: list[str],
) -> bool:
    if not _exact_keys(ref, APPROVAL_REF_KEYS, f"{prefix}_ref", errors):
        return False
    attempt_id = ref["critic_attempt_id"]
    output = outputs.get(attempt_id)
    if output is None:
        errors.append(f"{prefix}_ref names an unknown critic attempt")
        return False
    record = output["record"]
    if (
        ref["critic_snapshot_path"] != record["snapshot_path"]
        or ref["critic_snapshot_sha256"] != record["output_sha256"]
        or ref["approval_sha256"] != _sha256(approval)
    ):
        errors.append(f"{prefix}_ref identity mismatch")
        return False
    payload = output["payload"]
    if approval_kind == "inventory":
        candidates = [] if payload["inventory_approval"] is None else [payload["inventory_approval"]]
    elif approval_kind == "assessment":
        candidates = payload["assessment_approvals"]
    else:
        candidates = payload["coverage_exclusion_approvals"]
    matches = [item for item in candidates if item == approval]
    key = (attempt_id, ref["approval_sha256"])
    if len(matches) != 1 or key in used:
        errors.append(f"{prefix} is not uniquely present in its critic snapshot")
        return False
    used.add(key)
    return True


def _validate_finding_core(
    finding: dict[str, Any], prefix: str, errors: list[str], obligation_ids: set[str],
) -> None:
    required = {"id", "fingerprint", "classification", "obligation_ids", "iteration_first_seen"}
    if not required <= set(finding):
        errors.append(f"{prefix} lacks plan finding-core fields")
        return
    ids = _sorted_unique_strings(finding["obligation_ids"], f"{prefix}.obligation_ids", errors)
    if any(item not in obligation_ids for item in ids):
        errors.append(f"{prefix}.obligation_ids contains an unknown obligation")
    core = {key: finding[key] for key in ("id", "classification", "obligation_ids", "iteration_first_seen")}
    if finding["fingerprint"] != _sha256(core):
        errors.append(f"{prefix}.fingerprint mismatch")


def _validate_plan(
    data: dict[str, Any], ledger_path: Path, errors: list[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {"initial": False, "states": {}, "excluded": set(), "order": []}
    plan = data.get("plan_verification")
    if plan is None:
        errors.append("plan-obligation-contract-required")
        return result
    if not _exact_keys(plan, PLAN_KEYS, "plan_verification", errors):
        return result
    if plan["contract_version"] != 1:
        errors.append("plan_verification.contract_version must be 1")
    for field in ("plan_sha256", "evidence_revision_sha256"):
        if not _is_hash(plan[field]):
            errors.append(f"plan_verification.{field} must be sha256")
    if "active_plan_sha256" in data:
        if not _is_hash(data["active_plan_sha256"]):
            errors.append("active_plan_sha256 must be sha256")
        elif data["active_plan_sha256"] != plan["plan_sha256"]:
            errors.append("active_plan_sha256 conflicts with plan_verification.plan_sha256")
    target_ref = data.get("target")
    if _nonempty(target_ref):
        pure_target = PurePosixPath(target_ref)
        adjacent_target = ledger_path.parent / pure_target
        target_base = (
            ledger_path.parent
            if not pure_target.is_absolute()
            and ".." not in pure_target.parts
            and str(pure_target) == target_ref
            and adjacent_target.exists()
            else _repository_root(ledger_path.parent) or ledger_path.parent
        )
        target = _safe_relative_file(target_base, target_ref, "target", errors)
        if target is not None and _sha256(target.read_bytes()) != plan["plan_sha256"]:
            errors.append("target content does not match plan_verification.plan_sha256")
    for field in (
        "inventories", "assignments", "obligation_assessments", "critic_outputs",
        "coverage_exclusion_approvals",
    ):
        if not isinstance(plan[field], list):
            errors.append(f"plan_verification.{field} must be an array")
    if errors:
        return result

    if plan["inventory_sha256"] is None:
        if (
            data.get("iteration") != 0 or data.get("coverage_queue") != []
            or any(plan[field] for field in (
                "inventories", "assignments", "obligation_assessments", "critic_outputs",
                "coverage_exclusion_approvals",
            ))
        ):
            errors.append("inventory-not-ready")
        result["initial"] = True
        return result
    if not _is_hash(plan["inventory_sha256"]):
        errors.append("plan_verification.inventory_sha256 must be sha256 or null")
        return result

    base = ledger_path.parent
    outputs = _load_critic_outputs(plan["critic_outputs"], base, errors)
    used_approvals: set[tuple[str, str]] = set()
    inventory_map: dict[str, dict[str, Any]] = {}
    all_binding_map: dict[tuple[str, str], dict[str, Any]] = {}
    binding_context_map: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    active_inventory: dict[str, Any] | None = None
    for idx, inventory in enumerate(plan["inventories"]):
        prefix = f"plan_verification.inventories[{idx}]"
        if not _exact_keys(inventory, INVENTORY_KEYS, prefix, errors):
            continue
        inv_hash = inventory["inventory_sha256"]
        if not _is_hash(inv_hash) or inv_hash in inventory_map:
            errors.append(f"{prefix}.inventory_sha256 is invalid or duplicated")
            continue
        sections = _validate_plan_sections(inventory["plan_sections"], base, f"{prefix}.plan_sections", errors)
        evidence = _validate_source_records(inventory["evidence_items"], base, f"{prefix}.evidence_items", errors)
        dependencies = _validate_source_records(inventory["dependencies"], base, f"{prefix}.dependencies", errors)
        evidence_revision = _sha256({
            "evidence_items": inventory["evidence_items"],
            "dependencies": inventory["dependencies"],
        })
        if inventory["evidence_revision_sha256"] != evidence_revision:
            errors.append(f"{prefix}.evidence_revision_sha256 mismatch")
        obligations = inventory["obligations"]
        if not isinstance(obligations, list):
            errors.append(f"{prefix}.obligations must be an array")
            continue
        obligation_ids: set[str] = set()
        for obligation_idx, obligation in enumerate(obligations):
            op = f"{prefix}.obligations[{obligation_idx}]"
            keys = {
                "id", "coverage_id", "claim", "plan_section_refs", "evidence_refs",
                "dependency_refs", "binding_sha256",
            }
            if not _exact_keys(obligation, keys, op, errors):
                continue
            obligation_id = obligation["id"]
            if not _nonempty(obligation_id) or obligation_id in obligation_ids:
                errors.append(f"{op}.id is missing or duplicated")
                continue
            obligation_ids.add(obligation_id)
            if not _nonempty(obligation["coverage_id"]) or not _nonempty(obligation["claim"]):
                errors.append(f"{op} requires coverage_id and claim")
            refs = {}
            for field, registry in (
                ("plan_section_refs", sections), ("evidence_refs", evidence),
                ("dependency_refs", dependencies),
            ):
                refs[field] = _sorted_unique_strings(obligation[field], f"{op}.{field}", errors)
                if any(item not in registry for item in refs[field]):
                    errors.append(f"{op}.{field} contains an unknown registry id")
            projection = {
                "id": obligation_id,
                "coverage_id": obligation["coverage_id"],
                "claim": obligation["claim"],
                "plan_sections": [sections[item] for item in refs["plan_section_refs"] if item in sections],
                "evidence_items": [evidence[item] for item in refs["evidence_refs"] if item in evidence],
                "dependencies": [dependencies[item] for item in refs["dependency_refs"] if item in dependencies],
            }
            if obligation["binding_sha256"] != _sha256(projection):
                errors.append(f"{op}.binding_sha256 mismatch")
            binding_key = (obligation_id, obligation["binding_sha256"])
            all_binding_map[binding_key] = obligation
            binding_context_map[binding_key] = {
                "PLAN_SECTION": sections,
                "EVIDENCE": evidence,
                "DEPENDENCY": dependencies,
            }
        projection = {
            "contract_version": 1,
            "plan_sha256": inventory["plan_sha256"],
            "evidence_revision_sha256": inventory["evidence_revision_sha256"],
            "plan_sections": inventory["plan_sections"],
            "evidence_items": inventory["evidence_items"],
            "dependencies": inventory["dependencies"],
            "obligations": obligations,
        }
        if inv_hash != _sha256(projection):
            errors.append(f"{prefix}.inventory_sha256 mismatch")
        approval = inventory["completeness_approval"]
        ref = inventory["completeness_approval_ref"]
        if (approval is None) != (ref is None):
            errors.append(f"{prefix} completeness approval and ref nullability mismatch")
        if approval is not None:
            _validate_inventory_approval(approval, f"{prefix}.completeness_approval", errors)
            _validate_approval_ref(
                approval, ref, approval_kind="inventory", outputs=outputs,
                used=used_approvals, prefix=f"{prefix}.completeness_approval", errors=errors,
            )
        inventory_map[inv_hash] = {"record": inventory, "obligations": obligations}
        if inv_hash == plan["inventory_sha256"]:
            active_inventory = inventory

    if active_inventory is None:
        errors.append("active inventory is missing")
        return result
    if (
        active_inventory["plan_sha256"] != plan["plan_sha256"]
        or active_inventory["evidence_revision_sha256"] != plan["evidence_revision_sha256"]
    ):
        errors.append("active inventory revision identity mismatch")
    approval = active_inventory["completeness_approval"]
    inventory_approved = bool(approval and approval.get("decision") == "APPROVED")

    active_obligations = active_inventory["obligations"]
    active_map = {item["id"]: item for item in active_obligations}
    result["order"] = [item["id"] for item in active_obligations]
    coverage_items = data["coverage_queue"]
    coverage_map = {item["id"]: item for item in coverage_items}
    for obligation in active_obligations:
        if obligation["coverage_id"] not in coverage_map:
            errors.append(f"obligation {obligation['id']} names unknown coverage")

    finding_map: dict[str, dict[str, Any]] = {}
    for idx, finding in enumerate(data["findings"]):
        if not isinstance(finding, dict):
            continue
        _validate_finding_core(
            finding, f"findings[{idx}]", errors, set(active_map),
        )
        finding_map[str(finding.get("id"))] = finding

    assignments: dict[int, dict[str, Any]] = {}
    for idx, assignment in enumerate(plan["assignments"]):
        prefix = f"plan_verification.assignments[{idx}]"
        keys = {"iteration", "inventory_sha256", "assigned_obligation_ids", "assignment_sha256"}
        if not _exact_keys(assignment, keys, prefix, errors):
            continue
        iteration = assignment["iteration"]
        if isinstance(iteration, bool) or not isinstance(iteration, int) or iteration < 1 or iteration in assignments:
            errors.append(f"{prefix}.iteration is invalid or duplicated")
            continue
        ids = _sorted_unique_strings(assignment["assigned_obligation_ids"], f"{prefix}.assigned_obligation_ids", errors)
        inventory = inventory_map.get(assignment["inventory_sha256"])
        if inventory is None:
            errors.append(f"{prefix}.inventory_sha256 is unknown")
        elif any(item not in {op["id"] for op in inventory["obligations"]} for item in ids):
            errors.append(f"{prefix} assigns a foreign obligation")
        projection = {key: assignment[key] for key in ("iteration", "inventory_sha256", "assigned_obligation_ids")}
        if assignment["assignment_sha256"] != _sha256(projection):
            errors.append(f"{prefix}.assignment_sha256 mismatch")
        assignments[iteration] = assignment
    if assignments and sorted(assignments) != list(range(1, max(assignments) + 1)):
        errors.append("assignment iterations must be contiguous")
    if assignments and data["iteration"] != max(assignments):
        errors.append("ledger iteration must equal the latest assignment")

    assessments_by_iteration: dict[int, list[dict[str, Any]]] = defaultdict(list)
    approved_assessments: list[dict[str, Any]] = []
    assessment_keys = {
        "iteration", "obligation_id", "binding_sha256", "status", "evidence",
        "finding_snapshots", "blocked_boundary", "assessment_fingerprint", "approval",
        "approval_ref",
    }
    for idx, assessment in enumerate(plan["obligation_assessments"]):
        prefix = f"plan_verification.obligation_assessments[{idx}]"
        if not _exact_keys(assessment, assessment_keys, prefix, errors):
            continue
        iteration = assessment["iteration"]
        if iteration not in assignments:
            errors.append(f"{prefix}.iteration has no assignment")
        binding_key = (assessment["obligation_id"], assessment["binding_sha256"])
        binding_context = binding_context_map.get(binding_key)
        if binding_key not in all_binding_map:
            errors.append(f"{prefix} names an unknown obligation binding")
        if assessment["status"] not in {"SUPPORTED", "GAP", "BLOCKED"}:
            errors.append(f"{prefix}.status is invalid")
        evidence_records = assessment["evidence"]
        evidence_keys = {"registry_kind", "id", "claim"}
        if not isinstance(evidence_records, list) or not evidence_records:
            errors.append(f"{prefix}.evidence must be non-empty")
        else:
            evidence_order = []
            for evidence_idx, item in enumerate(evidence_records):
                ep = f"{prefix}.evidence[{evidence_idx}]"
                if not _exact_keys(item, evidence_keys, ep, errors):
                    continue
                if item["registry_kind"] not in {"PLAN_SECTION", "EVIDENCE", "DEPENDENCY"}:
                    errors.append(f"{ep}.registry_kind is invalid")
                if not _nonempty(item["id"]) or not _nonempty(item["claim"]):
                    errors.append(f"{ep} requires id and claim")
                elif (
                    binding_context is not None
                    and item["id"] not in binding_context.get(item["registry_kind"], {})
                ):
                    errors.append(f"{ep} names an unknown registry id for the owning inventory")
                evidence_order.append((item["registry_kind"], item["id"], item["claim"]))
            if evidence_order != sorted(set(evidence_order)):
                errors.append(f"{prefix}.evidence must be sorted and unique")
        snapshots = assessment["finding_snapshots"]
        if not isinstance(snapshots, list):
            errors.append(f"{prefix}.finding_snapshots must be an array")
            snapshots = []
        snapshot_keys = {"id", "fingerprint", "classification", "obligation_ids", "iteration_first_seen"}
        for snap_idx, snapshot in enumerate(snapshots):
            sp = f"{prefix}.finding_snapshots[{snap_idx}]"
            if not _exact_keys(snapshot, snapshot_keys, sp, errors):
                continue
            finding = finding_map.get(snapshot["id"])
            if finding is None or any(finding.get(key) != snapshot[key] for key in snapshot_keys):
                errors.append(f"{sp} does not match immutable finding core")
            if assessment["obligation_id"] not in snapshot["obligation_ids"]:
                errors.append(f"{sp} does not name the assessed obligation")
            if snapshot["iteration_first_seen"] > iteration:
                errors.append(f"{sp} was first seen after the assessment")
        boundary = assessment["blocked_boundary"]
        if assessment["status"] == "BLOCKED":
            boundary_keys = {
                "type", "binding_kind", "binding_id", "observed_content_sha256",
                "required_change",
            }
            if not _exact_keys(boundary, boundary_keys, f"{prefix}.blocked_boundary", errors):
                pass
            elif (
                boundary["type"] not in {"EVIDENCE", "RUNTIME", "APPROVAL"}
                or boundary["binding_kind"] not in {"EVIDENCE", "DEPENDENCY"}
                or not _is_hash(boundary["observed_content_sha256"])
                or not _nonempty(boundary["required_change"])
            ):
                errors.append(f"{prefix}.blocked_boundary is invalid")
            elif binding_context is not None:
                registry = binding_context[boundary["binding_kind"]]
                bound_record = registry.get(boundary["binding_id"])
                if bound_record is None:
                    errors.append(f"{prefix}.blocked_boundary names an unknown registry id")
                elif bound_record["content_sha256"] != boundary["observed_content_sha256"]:
                    errors.append(f"{prefix}.blocked_boundary observed content hash mismatch")
        elif boundary is not None:
            errors.append(f"{prefix}.blocked_boundary must be null")
        if assessment["status"] == "SUPPORTED" and snapshots:
            errors.append(f"{prefix}.SUPPORTED cannot contain finding snapshots")
        if assessment["status"] == "GAP" and not snapshots:
            errors.append(f"{prefix}.GAP requires finding snapshots")
        projection = {key: assessment[key] for key in assessment_keys - {"assessment_fingerprint", "approval", "approval_ref"}}
        if assessment["assessment_fingerprint"] != _sha256(projection):
            errors.append(f"{prefix}.assessment_fingerprint mismatch")
        approval = assessment["approval"]
        _validate_assessment_approval(approval, f"{prefix}.approval", errors)
        if isinstance(approval, dict):
            expected = {
                "iteration": assessment["iteration"],
                "obligation_id": assessment["obligation_id"],
                "binding_sha256": assessment["binding_sha256"],
                "assessment_fingerprint": assessment["assessment_fingerprint"],
            }
            if any(approval.get(key) != value for key, value in expected.items()):
                errors.append(f"{prefix}.approval binding mismatch")
        approved = _validate_approval_ref(
            approval, assessment["approval_ref"], approval_kind="assessment",
            outputs=outputs, used=used_approvals, prefix=f"{prefix}.approval", errors=errors,
        ) and isinstance(approval, dict) and approval.get("decision") == "APPROVED"
        assessments_by_iteration[iteration].append(assessment)
        if approved:
            approved_assessments.append(assessment)

    for iteration, assignment in assignments.items():
        assigned = assignment["assigned_obligation_ids"]
        assessed = sorted(item["obligation_id"] for item in assessments_by_iteration.get(iteration, []))
        if not assessed and iteration == data["iteration"]:
            continue
        if assessed != assigned:
            errors.append(f"iteration {iteration} assessments do not exactly match assignment")

    exclusion_map: dict[str, str] = {}
    exclusion_keys = {
        "coverage_id", "prior_status", "approved_status", "plan_sha256",
        "evidence_revision_sha256", "inventory_sha256", "rationale", "evidence",
        "approval_ref",
    }
    for idx, exclusion in enumerate(plan["coverage_exclusion_approvals"]):
        prefix = f"plan_verification.coverage_exclusion_approvals[{idx}]"
        if not _exact_keys(exclusion, exclusion_keys, prefix, errors):
            continue
        approval = {key: exclusion[key] for key in exclusion_keys - {"approval_ref"}}
        _validate_exclusion_approval(approval, prefix, errors)
        if (
            approval["plan_sha256"] != plan["plan_sha256"]
            or approval["evidence_revision_sha256"] != plan["evidence_revision_sha256"]
            or approval["inventory_sha256"] != plan["inventory_sha256"]
        ):
            errors.append(f"{prefix} is stale")
        if _validate_approval_ref(
            approval, exclusion["approval_ref"], approval_kind="exclusion",
            outputs=outputs, used=used_approvals, prefix=prefix, errors=errors,
        ):
            exclusion_map[approval["coverage_id"]] = approval["approved_status"]
    result["excluded"] = set(exclusion_map)

    open_by_obligation: dict[str, set[str]] = defaultdict(set)
    for finding in data["findings"]:
        if not isinstance(finding, dict):
            continue
        if (
            str(finding.get("classification") or "") in ACTIONABLE_CLASSIFICATIONS
            and str(finding.get("status") or "") not in RESOLVED_STATUSES
        ):
            for obligation_id in finding.get("obligation_ids", []):
                open_by_obligation[obligation_id].add(finding.get("id"))

    assessments_by_obligation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assessment in approved_assessments:
        assessments_by_obligation[assessment["obligation_id"]].append(assessment)
    states: dict[str, str] = {}
    for obligation_id, obligation in active_map.items():
        matching = [
            item for item in assessments_by_obligation.get(obligation_id, [])
            if item["binding_sha256"] == obligation["binding_sha256"]
        ]
        if not matching:
            states[obligation_id] = "missing"
            continue
        current = max(matching, key=lambda item: item["iteration"])
        if current["status"] == "SUPPORTED":
            states[obligation_id] = "stale" if open_by_obligation[obligation_id] else "supported"
        elif current["status"] == "BLOCKED":
            states[obligation_id] = "blocked"
        else:
            unresolved = {
                snap["id"] for snap in current["finding_snapshots"]
                if snap["id"] in finding_map
                and str(finding_map[snap["id"]].get("status") or "") not in RESOLVED_STATUSES
            }
            states[obligation_id] = "gap" if unresolved else "stale"
    result["states"] = states
    result["inventory_approved"] = inventory_approved

    for coverage in coverage_items:
        coverage_id = coverage["id"]
        owned = [item["id"] for item in active_obligations if item["coverage_id"] == coverage_id]
        if coverage_id in exclusion_map:
            if owned:
                errors.append(f"excluded coverage {coverage_id} must own no active obligations")
            derived = exclusion_map[coverage_id]
        else:
            if not owned:
                errors.append(f"in-scope coverage {coverage_id} has no obligations")
                derived = "unverified"
            elif inventory_approved and all(states.get(item) == "supported" for item in owned):
                resolved_gap_history = False
                for item in approved_assessments:
                    if item["obligation_id"] not in owned or item["status"] != "GAP":
                        continue
                    if item["finding_snapshots"] and all(
                        snap["id"] in finding_map
                        and str(finding_map[snap["id"]].get("status") or "") in RESOLVED_STATUSES
                        for snap in item["finding_snapshots"]
                    ):
                        resolved_gap_history = True
                derived = "fixed" if resolved_gap_history else "checked"
            else:
                derived = "unverified"
        if coverage["status"] != derived:
            errors.append(
                f"coverage status mismatch for {coverage_id}: expected {derived}, got {coverage['status']}"
            )
    return result


def _can_stop_errors(data: dict[str, Any], plan_state: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    if data.get("kind") == "plan":
        if not plan_state or plan_state.get("initial") or not plan_state.get("inventory_approved"):
            errors.append("inventory-not-approved")
        else:
            for obligation_id, state in plan_state.get("states", {}).items():
                if state != "supported":
                    errors.append(f"obligation cannot stop: {obligation_id} ({state})")
    else:
        for item in data.get("coverage_queue", []):
            if not isinstance(item, dict):
                continue
            risk = str(item.get("risk") or "").strip()
            status = str(item.get("status") or "").strip()
            if risk in {"high", "medium"} and status == "unverified":
                errors.append(f"coverage item remains unverified: {item.get('id')}")

    for finding in data.get("findings", []):
        if not isinstance(finding, dict):
            continue
        classification = str(finding.get("classification") or "").strip()
        status = str(finding.get("status") or "").strip()
        if classification in ACTIONABLE_CLASSIFICATIONS and status not in RESOLVED_STATUSES:
            errors.append(f"actionable finding remains unresolved: {finding.get('id')}")
    return errors


def cmd_init(args: argparse.Namespace) -> int:
    if args.kind == "plan":
        if not _is_hash(args.plan_sha256) or not _is_hash(args.evidence_revision_sha256):
            print("ERROR: plan init requires --plan-sha256 and --evidence-revision-sha256", file=sys.stderr)
            return 2
    elif args.plan_sha256 is not None or args.evidence_revision_sha256 is not None:
        print("ERROR: plan revision hashes are legal only for kind=plan", file=sys.stderr)
        return 2
    ledger = _empty_ledger(
        args.kind, args.target, plan_sha256=args.plan_sha256,
        evidence_revision_sha256=args.evidence_revision_sha256,
    )
    output = json.dumps(ledger, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


def _print_errors(errors: list[str]) -> None:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)


def cmd_check(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    data, errors = _load(path)
    plan_state: dict[str, Any] | None = None
    if data is not None:
        errors.extend(_validate_common(data))
        if data.get("kind") == "plan":
            plan_state = _validate_plan(data, path, errors)
        if args.can_stop and not errors:
            errors.extend(_can_stop_errors(data, plan_state))
    if errors:
        _print_errors(errors)
        return 1
    print("OK: ledger can stop" if args.can_stop else "OK: ledger valid")
    return 0


def cmd_next_assignment(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    data, errors = _load(path)
    state: dict[str, Any] | None = None
    if data is not None:
        errors.extend(_validate_common(data))
        if data.get("kind") != "plan":
            errors.append("next-assignment requires kind=plan")
        else:
            state = _validate_plan(data, path, errors)
    if errors:
        _print_errors(errors)
        return 1
    assert data is not None and state is not None
    if state.get("initial"):
        print("ERROR: inventory-not-ready", file=sys.stderr)
        return 1
    assignments = data["plan_verification"]["assignments"]
    assessed_iterations = {
        item["iteration"] for item in data["plan_verification"]["obligation_assessments"]
    }
    if assignments and max(item["iteration"] for item in assignments) not in assessed_iterations:
        print("ERROR: assignment-pending", file=sys.stderr)
        return 1
    if not state.get("inventory_approved"):
        active = next(
            item for item in data["plan_verification"]["inventories"]
            if item["inventory_sha256"] == data["plan_verification"]["inventory_sha256"]
        )
        if active["completeness_approval"] is not None or assignments:
            print("ERROR: inventory-not-approved", file=sys.stderr)
            return 1
    blocked = [item for item, value in state["states"].items() if value == "blocked"]
    if blocked:
        print(f"ERROR: blocked-obligation: {blocked[0]}", file=sys.stderr)
        return 1
    coverage = data["coverage_queue"]
    coverage_index = {item["id"]: idx for idx, item in enumerate(coverage)}
    risk_rank = {"high": 0, "medium": 1, "low": 2}
    active = next(
        item for item in data["plan_verification"]["inventories"]
        if item["inventory_sha256"] == data["plan_verification"]["inventory_sha256"]
    )
    obligation_index = {item["id"]: idx for idx, item in enumerate(active["obligations"])}
    obligation_map = {item["id"]: item for item in active["obligations"]}
    candidates = [
        item for item, value in state["states"].items()
        if value != "supported"
        and obligation_map[item]["coverage_id"] not in state.get("excluded", set())
    ]
    candidates.sort(key=lambda item: (
        risk_rank[next(row["risk"] for row in coverage if row["id"] == obligation_map[item]["coverage_id"])],
        coverage_index[obligation_map[item]["coverage_id"]], obligation_index[item],
    ))
    payload = {
        "inventory_sha256": data["plan_verification"]["inventory_sha256"],
        "next_obligation_ids": sorted(candidates[:args.limit]),
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create an empty verification ledger")
    init.add_argument("--kind", required=True, choices=sorted(VALID_KINDS))
    init.add_argument("--target", default="")
    init.add_argument("--plan-sha256")
    init.add_argument("--evidence-revision-sha256")
    init.add_argument("--output", "-o")
    init.set_defaults(func=cmd_init)

    check = sub.add_parser("check", help="Validate a verification ledger")
    check.add_argument("ledger")
    check.add_argument("--can-stop", action="store_true")
    check.set_defaults(func=cmd_check)

    next_assignment = sub.add_parser("next-assignment", help="Select the next plan obligations")
    next_assignment.add_argument("ledger")
    next_assignment.add_argument("--limit", required=True, type=int)
    next_assignment.set_defaults(func=cmd_next_assignment)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "limit", 1) < 1:
        parser.error("--limit must be positive")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
