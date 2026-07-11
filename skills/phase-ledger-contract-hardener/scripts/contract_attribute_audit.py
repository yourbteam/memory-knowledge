#!/usr/bin/env python3
"""Deterministic support checks for phase-ledger contract hardening."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


EXPECTED_ATTRIBUTES = [
    "contract_key",
    "id_prefix",
    "categories",
    "categories_detail",
    "category",
    "description",
    "selection_rules",
    "detail_shape",
    "minimum_count",
    "allowed_detail_shape_values",
    "allowed_detail_shape_value_details",
    "value",
    "reason_shape",
    "input_contract_preconditions",
    "derived_outputs",
    "readiness",
    "owner",
    "emitted_as",
    "allowed_values",
    "computation_rules",
    "source_structure",
    "labeled_record_types",
    "unnumbered_record_types",
    "section_heading_prefix",
]

ROLE_KEYS = ["producer_use", "manager_use", "verifier_use", "critic_use"]


def _json_blocks(markdown: str) -> list[Any]:
    blocks: list[Any] = []
    for match in re.finditer(r"```json\s*(.*?)\s*```", markdown, re.DOTALL):
        blocks.append(json.loads(match.group(1)))
    return blocks


def _load_first_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    blocks = _json_blocks(text)
    if not blocks:
        raise ValueError(f"No JSON code block found in {path}")
    return blocks[0]


def _collect_phase_attributes(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            found.add(str(key))
            found.update(_collect_phase_attributes(nested))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_phase_attributes(item))
    return found


def _phase_contract_errors(phase: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    categories = phase.get("categories")
    details = phase.get("categories_detail")
    if not isinstance(categories, list) or not all(isinstance(item, str) for item in categories):
        errors.append("phase.categories must be an array of strings")
        categories = []
    if not isinstance(details, list) or not all(isinstance(item, dict) for item in details):
        errors.append("phase.categories_detail must be an array of objects")
        details = []

    category_set = set(categories)
    detail_categories: set[str] = set()
    for index, entry in enumerate(details):
        category = entry.get("category")
        if not isinstance(category, str) or not category:
            errors.append(f"categories_detail[{index}].category must be a non-empty string")
            continue
        detail_categories.add(category)
        if category not in category_set:
            errors.append(f"categories_detail[{index}].category {category!r} is not in categories")

        for required in ["description", "selection_rules", "detail_shape", "minimum_count"]:
            if required not in entry:
                errors.append(f"categories_detail[{index}] missing {required}")
        if "minimum_count" in entry:
            minimum = entry["minimum_count"]
            if not isinstance(minimum, int) or minimum < 0:
                errors.append(f"categories_detail[{index}].minimum_count must be an integer >= 0")

        values = entry.get("allowed_detail_shape_values")
        value_details = entry.get("allowed_detail_shape_value_details")
        if values is not None:
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                errors.append(f"categories_detail[{index}].allowed_detail_shape_values must be an array of strings")
                values = []
            if value_details is None:
                errors.append(
                    f"categories_detail[{index}] declares allowed_detail_shape_values without "
                    "allowed_detail_shape_value_details"
                )
            elif not isinstance(value_details, list) or not all(isinstance(item, dict) for item in value_details):
                errors.append(
                    f"categories_detail[{index}].allowed_detail_shape_value_details must be an array of objects"
                )
            else:
                detailed_values = {str(item.get("value")) for item in value_details if item.get("value")}
                missing_details = sorted(set(values) - detailed_values)
                extra_details = sorted(detailed_values - set(values))
                if missing_details:
                    errors.append(
                        f"categories_detail[{index}] missing value details for {', '.join(missing_details)}"
                    )
                if extra_details:
                    errors.append(
                        f"categories_detail[{index}] has value details not in allowed values: "
                        f"{', '.join(extra_details)}"
                    )

    missing_detail_entries = sorted(category_set - detail_categories)
    if missing_detail_entries:
        errors.append(f"categories missing categories_detail entries: {', '.join(missing_detail_entries)}")

    input_contract_preconditions = phase.get("input_contract_preconditions")
    if input_contract_preconditions is not None and (
        not isinstance(input_contract_preconditions, list)
        or not input_contract_preconditions
        or not all(isinstance(item, str) and item.strip() for item in input_contract_preconditions)
    ):
        errors.append("phase.input_contract_preconditions must be a non-empty array of strings")

    derived_outputs = phase.get("derived_outputs")
    if derived_outputs is not None:
        if not isinstance(derived_outputs, dict):
            errors.append("phase.derived_outputs must be an object")
        else:
            for output_key, output in derived_outputs.items():
                if not isinstance(output_key, str) or not output_key:
                    errors.append("phase.derived_outputs keys must be non-empty strings")
                    continue
                if output_key in category_set or output_key.upper() in category_set:
                    errors.append(
                        f"derived output {output_key!r} must not also be a source-backed category"
                    )
                if output_key in detail_categories or output_key.upper() in detail_categories:
                    errors.append(
                        f"derived output {output_key!r} must not have a categories_detail source-backed entry"
                    )
                if not isinstance(output, dict):
                    errors.append(f"derived_outputs.{output_key} must be an object")
                    continue
                if output.get("owner") != "manager":
                    errors.append(f"derived_outputs.{output_key}.owner must be manager")
                emitted_as = output.get("emitted_as")
                if not isinstance(emitted_as, str) or not emitted_as.strip():
                    errors.append(f"derived_outputs.{output_key}.emitted_as must be a non-empty string")
                allowed_values = output.get("allowed_values")
                if (
                    not isinstance(allowed_values, list)
                    or not allowed_values
                    or not all(isinstance(item, str) and item for item in allowed_values)
                ):
                    errors.append(f"derived_outputs.{output_key}.allowed_values must be a non-empty array of strings")
                computation_rules = output.get("computation_rules")
                if (
                    not isinstance(computation_rules, list)
                    or not computation_rules
                    or not all(isinstance(item, str) and item for item in computation_rules)
                ):
                    errors.append(
                        f"derived_outputs.{output_key}.computation_rules must be a non-empty array of strings"
                    )
    source_structure = phase.get("source_structure")
    if source_structure is not None:
        if not isinstance(source_structure, dict):
            errors.append("phase.source_structure must be an object")
        else:
            labeled_record_types = source_structure.get("labeled_record_types")
            if (
                not isinstance(labeled_record_types, list)
                or not labeled_record_types
                or not all(isinstance(item, str) and item.strip() for item in labeled_record_types)
            ):
                errors.append("phase.source_structure.labeled_record_types must be a non-empty array of strings")
            unnumbered_record_types = source_structure.get("unnumbered_record_types")
            if unnumbered_record_types is not None and (
                not isinstance(unnumbered_record_types, list)
                or not all(isinstance(item, str) and item.strip() for item in unnumbered_record_types)
            ):
                errors.append("phase.source_structure.unnumbered_record_types must be an array of strings")
            section_heading_prefix = source_structure.get("section_heading_prefix")
            if not isinstance(section_heading_prefix, str) or not section_heading_prefix.strip():
                errors.append("phase.source_structure.section_heading_prefix must be a non-empty string")
    return errors


def _universal_usage_errors(universal: dict[str, Any], phase_attributes: set[str]) -> list[str]:
    errors: list[str] = []
    usage = universal.get("phase_contract_attribute_usage")
    if not isinstance(usage, dict):
        return ["universal.phase_contract_attribute_usage must be an object"]

    for attr in EXPECTED_ATTRIBUTES:
        if attr not in phase_attributes and attr not in {"value"}:
            continue
        entry = usage.get(attr)
        if not isinstance(entry, dict):
            errors.append(f"phase_contract_attribute_usage missing {attr}")
            continue
        for role_key in ROLE_KEYS:
            if not isinstance(entry.get(role_key), str) or not entry[role_key].strip():
                errors.append(f"phase_contract_attribute_usage.{attr}.{role_key} must be a non-empty string")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universal", required=True, type=Path)
    parser.add_argument("--phase", required=True, type=Path)
    args = parser.parse_args()

    try:
        universal = _load_first_json(args.universal)
        phase = _load_first_json(args.phase)
        if not isinstance(universal, dict):
            raise ValueError("Universal contract JSON must be an object")
        if not isinstance(phase, dict):
            raise ValueError("Phase contract JSON must be an object")
    except Exception as exc:
        print(f"parse_error: {exc}", file=sys.stderr)
        return 2

    phase_attributes = _collect_phase_attributes(phase)
    errors = []
    errors.extend(_phase_contract_errors(phase))
    errors.extend(_universal_usage_errors(universal, phase_attributes))

    print("Phase contract attributes:")
    for attr in sorted(phase_attributes):
        print(f"- {attr}")
    print()
    print("Universal usage coverage:")
    usage = universal.get("phase_contract_attribute_usage", {})
    for attr in EXPECTED_ATTRIBUTES:
        if attr in phase_attributes or attr == "value":
            status = "ok" if isinstance(usage.get(attr), dict) else "missing"
            print(f"- {attr}: {status}")

    if errors:
        print()
        print("Errors:")
        for error in errors:
            print(f"- {error}")
        return 1

    print()
    print("contract attribute audit ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
