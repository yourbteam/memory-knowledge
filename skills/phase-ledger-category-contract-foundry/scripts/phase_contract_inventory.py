#!/usr/bin/env python3
"""Inventory repo truth for phase-ledger category contract creation/audit."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

DETAIL_LITERAL_EVIDENCE_SOURCES = {"source_quote", "code_project_checkout"}
UNIVERSAL_CONTRACT_RELATIVE_PATH = Path(
    "software company workflows/implementation plans/phase-ledger-harness/phase-ledger-universal-orchestration-contract-wip.md"
)
CODE_CHECKOUT_WORDS = ("checkout", "code project", "repository", "repo", "codebase")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _first_json_block(markdown: str) -> dict[str, Any] | None:
    match = re.search(r"```json\s*(\{.*?\})\s*```", markdown, re.DOTALL)
    if not match:
        return None
    return json.loads(match.group(1))


def _load_json_or_markdown_contract(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    text = _read(path)
    if not text:
        raise SystemExit(f"contract file not found: {path}")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    parsed = _first_json_block(text)
    if parsed is None:
        raise SystemExit(f"no JSON contract block found in {path}")
    return parsed


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise SystemExit("PyYAML is required to inspect workflow YAML")
    return yaml.safe_load(_read(path)) or {}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _find_workflow_yaml(repo_root: Path, workflow: str) -> Path | None:
    candidates = [
        repo_root / "src" / "workflow_orch" / "workflows" / f"{workflow}.yaml",
        repo_root / "src" / "workflow_orch" / "workflows" / f"{workflow}.yml",
    ]
    for path in candidates:
        if path.exists():
            return path
    normalized = _normalize(workflow)
    for path in sorted((repo_root / "src" / "workflow_orch" / "workflows").glob("*.y*ml")):
        if _normalize(path.stem) == normalized:
            return path
    return None


def _find_phase(workflow_doc: dict[str, Any], phase_ref: str) -> dict[str, Any] | None:
    phase_norm = _normalize(phase_ref)
    for phase in workflow_doc.get("phases") or []:
        values = [
            str(phase.get("id") or ""),
            str(phase.get("name") or ""),
            str(phase.get("description") or ""),
        ]
        if any(_normalize(value) == phase_norm for value in values if value):
            return phase
    for phase in workflow_doc.get("phases") or []:
        if phase_norm in {_normalize(str(phase.get("id") or "")), _normalize(str(phase.get("name") or ""))}:
            return phase
    return None


def _load_catalog_phase(repo_root: Path, workflow: str, phase: dict[str, Any]) -> dict[str, Any] | None:
    catalog_path = repo_root / "software company workflows" / "workflow-catalog.json"
    if not catalog_path.exists():
        return None
    catalog = json.loads(_read(catalog_path))
    workflow_norm = _normalize(workflow)
    phase_id = str(phase.get("id") or "")
    phase_name = str(phase.get("name") or "")
    for workflow_entry in catalog.get("workflows") or []:
        names = [
            str(workflow_entry.get("name") or ""),
            str(workflow_entry.get("display_name") or ""),
            str(workflow_entry.get("enum_value") or ""),
        ]
        if workflow_norm not in {_normalize(name) for name in names if name}:
            continue
        for phase_entry in workflow_entry.get("phases") or []:
            if phase_entry.get("name") == phase_id or phase_entry.get("name") == phase_name:
                return phase_entry
            if _normalize(str(phase_entry.get("display_name") or "")) == _normalize(phase_name):
                return phase_entry
    return None


def _constitution_hits(repo_root: Path, workflow: str, phase: dict[str, Any]) -> list[dict[str, Any]]:
    path = repo_root / "software company workflows" / "Software Delivery Workflow Constitution.md"
    text = _read(path)
    if not text:
        return []
    needles = [
        str(phase.get("id") or ""),
        str(phase.get("name") or ""),
        str(phase.get("description") or ""),
        workflow,
    ]
    lines = text.splitlines()
    hits: list[dict[str, Any]] = []
    for idx, line in enumerate(lines, start=1):
        if any(needle and needle in line for needle in needles):
            start = max(1, idx - 2)
            end = min(len(lines), idx + 8)
            hits.append(
                {
                    "path": str(path),
                    "line": idx,
                    "snippet": "\n".join(lines[start - 1 : end]),
                }
            )
    return hits[:8]


def _legacy_personas(repo_root: Path, phase: dict[str, Any]) -> dict[str, str]:
    loop = phase.get("phase_ledger_loop") or {}
    result: dict[str, str] = {}
    for role in ("producer", "verifier", "critic"):
        agent = ((loop.get(role) or {}).get("agent") or "").strip()
        if not agent:
            continue
        path = repo_root / "src" / "agents" / f"{agent}.md"
        result[role] = str(path) if path.exists() else f"missing: {path}"
    return result


def _enum_inventory(repo_root: Path, workflow: str, phase: dict[str, Any], personas: dict[str, str]) -> dict[str, Any]:
    texts = [
        workflow,
        str(phase.get("id") or ""),
        str(phase.get("name") or ""),
        str(phase.get("description") or ""),
        str(((phase.get("phase_ledger_loop") or {}).get("output") or {}).get("context_key") or ""),
    ]
    for path_text in personas.values():
        path = Path(path_text)
        if path.exists():
            texts.append(_read(path))
    referenced: set[str] = set()
    for match in re.finditer(r"([a-z0-9][a-z0-9-]*record-type\.json|[a-z0-9][a-z0-9-]*readiness\.json|[a-z0-9][a-z0-9-]*residual-risk-type\.json)", "\n".join(texts), re.I):
        referenced.add(match.group(1))
    workflow_tokens = set(_normalize(workflow).split("-"))
    phase_tokens = set(_normalize(str(phase.get("id") or "")).split("-"))
    referenced_paths: list[str] = []
    name_matched_paths: list[str] = []
    enum_roots = [
        repo_root / "software company workflows" / "enums",
        repo_root / "src" / "workflow_orch" / "contracts" / "enums",
    ]
    for root in enum_roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            stem_tokens = set(_normalize(path.stem).split("-"))
            if path.name in referenced:
                referenced_paths.append(str(path))
            elif workflow_tokens & stem_tokens and phase_tokens & stem_tokens:
                name_matched_paths.append(str(path))
    return {
        "referenced_filenames": sorted(referenced),
        "referenced_paths": referenced_paths,
        "name_matched_candidate_paths": name_matched_paths,
    }


def _manager_hits(repo_root: Path, phase: dict[str, Any]) -> list[str]:
    keys = [
        str(((phase.get("phase_ledger_loop") or {}).get("output") or {}).get("context_key") or ""),
        str(phase.get("id") or "").replace("-", "_"),
        str(phase.get("id") or ""),
    ]
    search_files = [
        repo_root / "src" / "workflow_orch" / "phase_ledger_manager.py",
        repo_root / "src" / "workflow_orch" / "phase_ledger_contract_manager.py",
        repo_root / "src" / "workflow_orch" / "workflow_engine.py",
        repo_root / "tests" / "test_phase_ledger_manager.py",
        repo_root / "tests" / "test_phase_ledger_loop_executor.py",
        repo_root / "tests" / "test_phase_ledger_canaries.py",
    ]
    hits: list[str] = []
    for path in search_files:
        text = _read(path)
        if not text:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            if any(key and key in line for key in keys):
                hits.append(f"{path}:{idx}: {line.strip()}")
                break
    return hits


def _downstream_consumers(workflow_doc: dict[str, Any], phase_id: str) -> list[dict[str, Any]]:
    consumers = []
    for phase in workflow_doc.get("phases") or []:
        if phase_id in (phase.get("subscribes_to") or []) or phase_id in (phase.get("depends_on") or []):
            consumers.append(
                {
                    "id": phase.get("id"),
                    "name": phase.get("name"),
                    "type": phase.get("type"),
                    "output_context_key": ((phase.get("phase_ledger_loop") or {}).get("output") or {}).get("context_key")
                    or phase.get("output_context_key"),
                }
            )
    return consumers


def _contract_input_context_mentions_checkout(contract: dict[str, Any] | None) -> bool:
    if contract is None:
        return False
    text = str(contract.get("input_context") or "").lower()
    return any(word in text for word in CODE_CHECKOUT_WORDS)


def _detail_literal_evidence_inventory(detail_entries: list[Any]) -> dict[str, Any]:
    evidence_by_category: dict[str, str] = {}
    missing: list[str] = []
    invalid: list[dict[str, str]] = []
    checkout_categories: list[str] = []
    for entry in detail_entries:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category") or "")
        if not category:
            continue
        if "detail_literal_evidence_source" not in entry:
            missing.append(category)
            continue
        value = str(entry.get("detail_literal_evidence_source") or "")
        evidence_by_category[category] = value
        if value not in DETAIL_LITERAL_EVIDENCE_SOURCES:
            invalid.append({"category": category, "value": value})
        if value == "code_project_checkout":
            checkout_categories.append(category)
    return {
        "detail_literal_evidence_source_by_category": evidence_by_category,
        "categories_missing_detail_literal_evidence_source": missing,
        "invalid_detail_literal_evidence_source_categories": invalid,
        "categories_using_code_project_checkout": checkout_categories,
    }


def _contract_consistency(contract: dict[str, Any] | None) -> dict[str, Any] | None:
    if contract is None:
        return None
    categories = contract.get("categories") or []
    detail_entries = contract.get("categories_detail") or []
    detail_categories = [entry.get("category") for entry in detail_entries if isinstance(entry, dict)]
    nested_errors: list[str] = []
    for entry in detail_entries:
        if not isinstance(entry, dict):
            continue
        values = entry.get("allowed_detail_shape_values") or []
        details = entry.get("allowed_detail_shape_value_details") or []
        detail_values = [item.get("value") for item in details if isinstance(item, dict)]
        if sorted(values) != sorted(detail_values):
            nested_errors.append(str(entry.get("category")))
    return {
        "contract_key": contract.get("contract_key"),
        "category_count": len(categories),
        "has_phase_purpose": bool(str(contract.get("phase_purpose") or "").strip()),
        "has_input_context": bool(str(contract.get("input_context") or "").strip()),
        "input_context_mentions_code_checkout": _contract_input_context_mentions_checkout(contract),
        "categories_without_detail": [cat for cat in categories if cat not in detail_categories],
        "detail_without_category": [cat for cat in detail_categories if cat not in categories],
        "nested_value_detail_mismatches": nested_errors,
        "has_output_composition": isinstance(contract.get("output_composition"), dict),
        **_detail_literal_evidence_inventory(detail_entries),
    }


def _universal_contract_summary(repo_root: Path) -> dict[str, Any]:
    path = repo_root / UNIVERSAL_CONTRACT_RELATIVE_PATH
    if not path.exists():
        return {"path": str(path), "exists": False}
    contract = _load_json_or_markdown_contract(path)
    usage = contract.get("phase_contract_attribute_usage") or {}
    optional_fields = contract.get("detail_entry_optional_fields") or []
    return {
        "path": str(path),
        "exists": True,
        "defines_phase_purpose": isinstance(usage.get("phase_purpose"), dict),
        "defines_input_context": isinstance(usage.get("input_context"), dict),
        "defines_detail_literal_evidence_source": (
            isinstance(usage.get("detail_literal_evidence_source"), dict)
            or "detail_literal_evidence_source" in optional_fields
        ),
        "defines_code_project_checkout_usage": isinstance(contract.get("code_project_checkout_usage"), dict),
    }


def _phase_capability_hints(workflow_doc: dict[str, Any], phase: dict[str, Any]) -> dict[str, Any]:
    phases = workflow_doc.get("phases") or []
    loop = phase.get("phase_ledger_loop") or {}
    prompt_assembly = loop.get("prompt_assembly") or {}
    execution_capabilities = loop.get("execution_capabilities") or {}
    workflow_has_repo_prep = any(item.get("type") == "code_project_repo_prep" for item in phases if isinstance(item, dict))
    workflow_requires_code_project_repo = bool(workflow_doc.get("requires_code_project_repo"))
    when_code_project_checkout = execution_capabilities.get("when_code_project_checkout")
    return {
        "workflow_requires_code_project_repo": workflow_requires_code_project_repo,
        "workflow_has_code_project_repo_prep": workflow_has_repo_prep,
        "phase_uses_universal_contract_prompt_assembly": prompt_assembly.get("mode") == "universal_contract_v1",
        "phase_contract_path": prompt_assembly.get("phase_contract_path"),
        "phase_execution_capability_when_code_project_checkout": when_code_project_checkout,
        "workflow_yaml_indicates_code_project_checkout": bool(
            workflow_requires_code_project_repo and workflow_has_repo_prep and when_code_project_checkout is True
        ),
    }


def _contract_new_field_warnings(
    contract: dict[str, Any] | None,
    phase_capability_hints: dict[str, Any],
) -> list[str] | None:
    if contract is None:
        return None
    consistency = _contract_consistency(contract) or {}
    warnings: list[str] = []
    if not consistency.get("has_phase_purpose"):
        warnings.append("missing phase_purpose")
    if not consistency.get("has_input_context"):
        warnings.append("missing input_context")
    invalid_sources = consistency.get("invalid_detail_literal_evidence_source_categories") or []
    if invalid_sources:
        warnings.append("invalid detail_literal_evidence_source value")
    if phase_capability_hints.get("workflow_yaml_indicates_code_project_checkout"):
        if not consistency.get("input_context_mentions_code_checkout"):
            warnings.append("code-checkout phase input_context does not mention checkout/codebase evidence")
        if not consistency.get("categories_using_code_project_checkout"):
            warnings.append("code-checkout phase has no category using detail_literal_evidence_source=code_project_checkout")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--reference-contract")
    parser.add_argument("--target-contract")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    workflow_yaml = _find_workflow_yaml(repo_root, args.workflow)
    if workflow_yaml is None:
        raise SystemExit(f"workflow YAML not found for {args.workflow}")
    workflow_doc = _load_yaml(workflow_yaml)
    phase = _find_phase(workflow_doc, args.phase)
    if phase is None:
        raise SystemExit(f"phase not found in {workflow_yaml}: {args.phase}")

    personas = _legacy_personas(repo_root, phase)
    reference_contract = _load_json_or_markdown_contract(Path(args.reference_contract).resolve() if args.reference_contract else None)
    target_contract = _load_json_or_markdown_contract(Path(args.target_contract).resolve() if args.target_contract else None)

    phase_capability_hints = _phase_capability_hints(workflow_doc, phase)

    output = {
        "workflow": {
            "name": workflow_doc.get("name"),
            "path": str(workflow_yaml),
            "description": workflow_doc.get("description"),
        },
        "phase": phase,
        "catalog_phase": _load_catalog_phase(repo_root, str(workflow_doc.get("name") or args.workflow), phase),
        "constitution_hits": _constitution_hits(repo_root, str(workflow_doc.get("name") or args.workflow), phase),
        "upstream_phase_ids": phase.get("subscribes_to") or phase.get("depends_on") or [],
        "downstream_consumers": _downstream_consumers(workflow_doc, str(phase.get("id") or "")),
        "legacy_personas": personas,
        "legacy_enum_inventory": _enum_inventory(repo_root, str(workflow_doc.get("name") or args.workflow), phase, personas),
        "manager_and_test_hits": _manager_hits(repo_root, phase),
        "universal_contract_summary": _universal_contract_summary(repo_root),
        "phase_capability_hints": phase_capability_hints,
        "reference_contract_consistency": _contract_consistency(reference_contract),
        "target_contract_consistency": _contract_consistency(target_contract),
        "reference_contract_new_field_warnings": _contract_new_field_warnings(reference_contract, phase_capability_hints),
        "target_contract_new_field_warnings": _contract_new_field_warnings(target_contract, phase_capability_hints),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
