"""Assemble a complete, ordered, actionable system-alignment result."""
from __future__ import annotations

import hashlib
import json


class TerminalPackageError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _unit_id(question_id: object, prefix: str) -> str:
    if type(question_id) is not str or not question_id.startswith(prefix):
        raise TerminalPackageError(f"question id must start with {prefix}")
    unit_id = question_id[len(prefix):]
    if not unit_id.startswith("unit-"):
        raise TerminalPackageError(f"question id {question_id!r} does not identify a unit")
    return unit_id


def _index(items: object, identity, label: str) -> dict:
    if type(items) is not list:
        raise TerminalPackageError(f"{label} must be a list")
    indexed = {}
    for item in items:
        key = identity(item)
        if key in indexed:
            raise TerminalPackageError(f"{label} duplicates {key}")
        indexed[key] = item
    return indexed


def build(bound: dict) -> dict:
    if type(bound) is not dict or set(bound) != {
        "alignment_units", "path_inventory", "actual_trace", "reference_trace", "mappings", "comparison_results"
    }:
        raise TerminalPackageError("bound inputs are incomplete")
    units_value = bound["alignment_units"]["value"]
    mappings_value = bound["mappings"]["value"]
    comparisons_value = bound["comparison_results"]["value"]
    units = units_value.get("units")
    if type(units) is not list or units_value.get("unit_count") != len(units):
        raise TerminalPackageError("alignment unit count changed")
    unit_index = _index(units, lambda item: item.get("unit_id"), "alignment units")
    if [item.get("sequence") for item in units] != list(range(1, len(units) + 1)):
        raise TerminalPackageError("alignment units are not in canonical sequence")
    mappings = _index(
        mappings_value.get("answers"), lambda item: _unit_id(item.get("question_id"), "map:"), "mapping answers"
    )
    results = _index(
        comparisons_value.get("results"), lambda item: _unit_id(item.get("question_id"), "compare:"), "comparison results"
    )
    dispositions = _index(comparisons_value.get("dispositions"), lambda item: item.get("unit_id"), "dispositions")
    if set(mappings) != set(unit_index):
        raise TerminalPackageError("mapping answers must cover every alignment unit exactly once")
    if set(results) | set(dispositions) != set(unit_index) or set(results) & set(dispositions):
        raise TerminalPackageError("comparison results and dispositions must partition every alignment unit exactly once")
    records = []
    counts = {"aligned": 0, "misaligned": 0, "cannot-assess": 0, "not-applicable": 0}
    for unit in units:
        unit_id = unit["unit_id"]
        mapping = mappings[unit_id]
        base = {
            "sequence": unit["sequence"],
            "unit_id": unit_id,
            "label": unit["label"],
            "subject": unit["subject"],
            "intent_statements": unit["intent_statements"],
        }
        if mapping.get("answer") == "mapped":
            if unit_id not in results or unit_id in dispositions:
                raise TerminalPackageError(f"mapped unit {unit_id} must have exactly one comparison result")
            result = results[unit_id]
            verdict = result.get("verdict")
            if verdict not in {"aligned", "misaligned", "cannot-assess"}:
                raise TerminalPackageError(f"comparison result for {unit_id} has invalid verdict {verdict!r}")
            measure = result.get("measure")
            if type(measure) is not dict or measure.get("actual") != mapping.get("actual_expression") or measure.get("expected") != mapping.get("reference_expression"):
                raise TerminalPackageError(f"comparison result for {unit_id} is not bound to its mapped expressions")
            expected_evidence = mapping.get("actual_evidence_ids", []) + mapping.get("reference_evidence_ids", [])
            if result.get("evidence_ids") != expected_evidence:
                raise TerminalPackageError(f"comparison result for {unit_id} is not bound to its mapped evidence")
            record = {
                **base,
                "actual_expression": mapping["actual_expression"],
                "reference_expression": mapping["reference_expression"],
                "measure": measure,
                "verdict": verdict,
                "reason": result["reason"],
                "evidence_ids": result["evidence_ids"],
            }
        elif mapping.get("answer") in {"not-applicable", "needs-source"}:
            disposition = dispositions.get(unit_id)
            if disposition is None or disposition.get("mapping_answer") != mapping.get("answer"):
                raise TerminalPackageError(f"disposition for {unit_id} does not match its mapping answer")
            verdict = "not-applicable" if mapping["answer"] == "not-applicable" else "cannot-assess"
            record = {
                **base,
                "actual_expression": None,
                "reference_expression": None,
                "measure": None,
                "verdict": verdict,
                "reason": disposition.get("reason"),
                "evidence_ids": [],
            }
        else:
            raise TerminalPackageError(f"mapping answer for {unit_id} is unsupported")
        counts[record["verdict"]] += 1
        records.append(record)
    total = len(records)
    if sum(counts.values()) != total:
        raise TerminalPackageError("terminal summary does not account for every unit")
    overall = "misaligned" if counts["misaligned"] else "inconclusive" if counts["cannot-assess"] else "aligned"
    package = {
        "schema_version": 1,
        "artifact_type": "system-alignment-assessment-package",
        "status": "alignment-assessment-complete",
        "overall_verdict": overall,
        "summary": {"total_units": total, **counts},
        "inputs": {name: item["ref"] for name, item in bound.items()},
        "alignment": records,
    }
    package["artifact_sha256"] = hashlib.sha256(canonical(package)).hexdigest()
    return package
