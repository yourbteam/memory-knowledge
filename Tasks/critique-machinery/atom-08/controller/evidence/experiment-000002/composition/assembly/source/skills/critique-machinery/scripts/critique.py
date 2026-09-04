#!/usr/bin/env python3
"""Open one delivered page as an immutable, payload-grounded critique run."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
UNIT_STRATEGY = "rendered-sections"
MATRIX_GATE_STRATEGY = "universal-gate"
VERDICT_STRATEGY = "action-grounded"
VERDICTS = ("reject", "revise", "clear")
QUOTE_REQUIRED = True
READER_STRATEGY = "blind-separated"
READER_SEATS = ("reader-1", "reader-2")
TRACE_STRATEGY = "registered-source-exact-quote"
BENCHMARK_STRATEGY = "paired-exact-evidence"
NO_REFERENCE_STRATEGY = "declared-no-reference"
LENSES = (
    "buyer-read",
    "cfo",
    "journalist",
    "employee-insider",
    "competitor-counter-position",
    "benchmark-vs-reference",
    "upstream-trace",
)
TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class Refusal(RuntimeError):
    """A fail-closed operator refusal with a repair instruction."""


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def tokens(value: str) -> set[str]:
    return {part.casefold() for part in TOKEN.findall(value) if len(part) > 2}


def lookup(root: Any, dotted: str) -> Any:
    value = root
    walked: list[str] = []
    for part in dotted.split("."):
        walked.append(part)
        if not isinstance(value, dict) or part not in value:
            found = sorted(value) if isinstance(value, dict) else type(value).__name__
            raise Refusal(
                f"payload key {dotted!r} is missing at {'.'.join(walked)!r}; "
                f"available here: {found}. Supply an existing stored payload key."
            )
        value = value[part]
    if not isinstance(value, (dict, list)) or not value:
        raise Refusal(
            f"payload key {dotted!r} returned {type(value).__name__}, not a non-empty stored object; "
            "select the structured payload that rendered the page."
        )
    return value


def repo_for(path: Path) -> Path:
    resolved = path.resolve()
    start = resolved if resolved.exists() else resolved.parent
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            if resolved == candidate:
                raise Refusal(
                    f"work directory {resolved} is the repository root; choose a new nested run directory "
                    "such as Tasks/<task>/runs/<name>."
                )
            return candidate
    raise Refusal(
        f"work directory {resolved} is not nested inside a Git repository; choose "
        "Tasks/<task>/runs/<name> beneath the intended repository."
    )


def flatten(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        result: list[tuple[str, Any]] = []
        for key, child in value.items():
            result.extend(flatten(child, f"{path}.{key}"))
        return result
    if isinstance(value, list):
        result = []
        for index, child in enumerate(value):
            result.extend(flatten(child, f"{path}[{index}]"))
        return result
    return [(path, value)]


def page_blocks(page: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", page) if block.strip()]


def candidate_records(payload: Any) -> list[tuple[str, str, Any]]:
    if isinstance(payload, list):
        return [(f"$[{index}]", f"item {index + 1}", value) for index, value in enumerate(payload)]
    records: list[tuple[str, str, Any]] = []
    scalars: dict[str, Any] = {}
    for key, value in payload.items():
        label = key.replace("_", " ")
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            for index, item in enumerate(value):
                item_label = next(
                    (str(item[name]) for name in ("name", "title", "objective", "phase", "month") if item.get(name)),
                    f"{label} {index + 1}",
                )
                records.append((f"$.{key}[{index}]", item_label, item))
        elif isinstance(value, (dict, list)):
            records.append((f"$.{key}", label, value))
        else:
            scalars[key] = value
    if scalars:
        records.append(("$.__fields__", "document fields", scalars))
    return records


def payload_record_units(payload: Any, blocks: list[str]) -> list[dict[str, Any]]:
    records = candidate_records(payload)
    if not records:
        raise Refusal("the selected payload has no record boundaries; provide the structured object that rendered the page.")
    unit_tokens = [tokens(json.dumps(value, ensure_ascii=False)) for _, _, value in records]
    assignments: list[list[int]] = [[] for _ in records]
    overlaps: list[list[int]] = [[] for _ in records]
    for block_index, block in enumerate(blocks):
        block_tokens = tokens(block)
        scores = [len(block_tokens & source_tokens) for source_tokens in unit_tokens]
        winner = max(range(len(records)), key=lambda index: (scores[index], -index))
        assignments[winner].append(block_index)
        overlaps[winner].append(scores[winner])
    units = []
    for index, ((path, label, value), territory, scores) in enumerate(zip(records, assignments, overlaps, strict=True)):
        text = "\n\n".join(blocks[item] for item in territory)
        units.append(
            {
                "unit_id": f"u-{index + 1:03d}-{digest_bytes(path.encode())[:8]}",
                "label": label,
                "payload_paths": [path],
                "payload_sha256": digest_bytes(canonical(value)),
                "territory_blocks": territory,
                "territory_sha256": digest_bytes(text.encode()),
                "text": text,
                "anchor_score": sum(scores),
            }
        )
    return units


def rendered_section_units(payload: Any, blocks: list[str]) -> list[dict[str, Any]]:
    records = candidate_records(payload)
    record_tokens = [tokens(json.dumps(value, ensure_ascii=False)) for _, _, value in records]
    sections: list[list[int]] = []
    current: list[int] = []
    for index, block in enumerate(blocks):
        if block.startswith("#") and current:
            sections.append(current)
            current = []
        current.append(index)
    if current:
        sections.append(current)
    units = []
    for index, territory in enumerate(sections):
        text = "\n\n".join(blocks[item] for item in territory)
        block_tokens = tokens(text)
        scores = [len(block_tokens & source_tokens) for source_tokens in record_tokens]
        winner = max(range(len(records)), key=lambda item: (scores[item], -item))
        path, _, value = records[winner]
        first_line = text.splitlines()[0].lstrip("# ").strip()
        units.append(
            {
                "unit_id": f"u-{index + 1:03d}-{digest_bytes((path + first_line).encode())[:8]}",
                "label": first_line or f"section {index + 1}",
                "payload_paths": [path],
                "payload_sha256": digest_bytes(canonical(value)),
                "territory_blocks": territory,
                "territory_sha256": digest_bytes(text.encode()),
                "text": text,
                "anchor_score": scores[winner],
            }
        )
    return units


def enumerate_units(payload: Any, blocks: list[str]) -> list[dict[str, Any]]:
    return rendered_section_units(payload, blocks)


def identity_evidence(page: str, payload: Any) -> dict[str, Any]:
    values = sorted(
        {
            str(value)
            for _, value in flatten(payload)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool) and len(str(value).strip()) >= 25
        }
    )
    normalized_page = normalize(page)
    matched = [value for value in values if normalize(value) in normalized_page]
    required = min(len(values), max(3, math.ceil(len(values) * 0.05)))
    return {
        "long_value_count": len(values),
        "matched_long_value_count": len(matched),
        "required_long_value_count": required,
        "matched_value_sha256": [digest_bytes(value.encode()) for value in matched],
        "accepted": bool(values) and len(matched) >= required,
    }


def build_manifest(page_path: Path, state_path: Path, key: str) -> dict[str, Any]:
    page = page_path.read_text(encoding="utf-8")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    payload = lookup(state, key)
    identity = identity_evidence(page, payload)
    if not identity["accepted"]:
        raise Refusal(
            f"page/payload mismatch for page {page_path} and key {key!r}: found "
            f"{identity['matched_long_value_count']} exact stored values but require "
            f"{identity['required_long_value_count']}. Supply the state file and exact key that rendered this page."
        )
    blocks = page_blocks(page)
    units = enumerate_units(payload, blocks)
    assigned = [item for unit in units for item in unit["territory_blocks"]]
    coverage = {
        "page_block_count": len(blocks),
        "assigned_block_count": len(assigned),
        "unique_assigned_block_count": len(set(assigned)),
        "complete_exactly_once": sorted(assigned) == list(range(len(blocks))),
    }
    if not coverage["complete_exactly_once"]:
        raise Refusal(
            f"unit territory is incomplete for {page_path}: {coverage}. The cut rule must assign every page block exactly once."
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "opened",
        "strategy": UNIT_STRATEGY,
        "page": {"path": str(page_path.resolve()), "sha256": digest_file(page_path)},
        "payload": {
            "state_path": str(state_path.resolve()),
            "state_sha256": digest_file(state_path),
            "key": key,
            "value_sha256": digest_bytes(canonical(payload)),
            "identity_evidence": identity,
        },
        "coverage": coverage,
        "units": units,
    }


def build_matrix(manifest: dict[str, Any]) -> dict[str, Any]:
    declaration = manifest.get("benchmark_reference")
    no_reference = declaration if declaration and declaration.get("state") == "none" else None
    cells = []
    for unit in manifest["units"]:
        for lens in LENSES:
            cell = {
            "cell_id": f"{unit['unit_id']}::{lens}",
            "unit_id": unit["unit_id"],
            "lens": lens,
            "status": "unjudged",
            "reader_strategy": READER_STRATEGY,
            "readers": {},
            "outcome": "pending",
            }
            if lens == "benchmark-vs-reference" and no_reference:
                cell.update(
                    {
                        "status": "not-applicable",
                        "outcome": "not-applicable",
                        "benchmark_state": {
                            "state": "no-reference",
                            "reason": no_reference["reason"],
                            "strategy": NO_REFERENCE_STRATEGY,
                        },
                    }
                )
            cells.append(cell)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "partial",
        "unit_manifest_sha256": digest_bytes(canonical(manifest)),
        "lenses": list(LENSES),
        "cells": cells,
    }


def reference_record(reference_id: str, page_path: Path) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", reference_id):
        raise Refusal(
            f"reference id {reference_id!r} is invalid; use lowercase letters, digits, and hyphens so the identity remains stable."
        )
    text = page_path.read_text(encoding="utf-8")
    if not text.strip():
        raise Refusal(f"reference {page_path.resolve()} is empty; register a readable professional reference.")
    return {
        "reference_id": reference_id,
        "page_path": str(page_path.resolve()),
        "page_sha256": digest_file(page_path),
        "text": text,
        "strategy": BENCHMARK_STRATEGY,
    }


def benchmark_declaration(
    reference_id: str | None,
    reference_page: Path | None,
    no_reference: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    has_reference = reference_id is not None or reference_page is not None
    has_no_reference = no_reference is not None
    if has_reference and has_no_reference:
        raise Refusal(
            "open received both a reference and --no-reference; choose exactly one: "
            "--reference <id> with --reference-page <page>, or --no-reference \"<recorded reason>\"."
        )
    if not has_reference and not has_no_reference:
        raise Refusal(
            "open requires exactly one benchmark-source declaration: --reference <id> with "
            "--reference-page <page>, or --no-reference \"<recorded reason>\"."
        )
    if has_reference:
        if not reference_id or reference_page is None:
            missing = "--reference" if not reference_id else "--reference-page"
            raise Refusal(
                f"open received an incomplete reference declaration; add {missing}, or use "
                "--no-reference \"<recorded reason>\" instead."
            )
        record = reference_record(reference_id, reference_page.resolve())
        return (
            {
                "state": "registered",
                "reference_id": record["reference_id"],
                "page_path": record["page_path"],
                "page_sha256": record["page_sha256"],
                "strategy": BENCHMARK_STRATEGY,
            },
            record,
        )
    reason = collapsed(no_reference or "")
    if not reason:
        raise Refusal("--no-reference requires a non-empty recorded reason explaining why no real benchmark exists.")
    return ({"state": "none", "reason": reason, "strategy": NO_REFERENCE_STRATEGY}, None)


def open_run(
    page_path: Path,
    state_path: Path,
    key: str,
    work: Path,
    *,
    reference_id: str | None = None,
    reference_page: Path | None = None,
    no_reference: str | None = None,
) -> tuple[str, dict[str, Any]]:
    repo_for(work)
    declaration, reference = benchmark_declaration(reference_id, reference_page, no_reference)
    manifest = build_manifest(page_path.resolve(), state_path.resolve(), key)
    manifest["benchmark_reference"] = declaration
    destination = work / "unit-manifest.json"
    matrix_path = work / "matrix.json"
    references_path = work / "references.json"
    serialized = canonical(manifest)
    matrix = build_matrix(manifest)
    matrix_bytes = canonical(matrix)
    existing = (destination.exists(), matrix_path.exists())
    if any(existing):
        if not all(existing):
            present = destination.name if existing[0] else matrix_path.name
            missing = matrix_path.name if existing[0] else destination.name
            raise Refusal(
                f"run {work.resolve()} is incomplete: {present} exists but {missing} does not. "
                "Choose a new work directory; do not repair immutable run state by hand."
            )
        reference_bytes = canonical({"schema_version": 1, "references": [reference]}) if reference else None
        reference_changed = (
            reference_bytes is not None and (not references_path.is_file() or references_path.read_bytes() != reference_bytes)
        ) or (reference_bytes is None and references_path.exists())
        if destination.read_bytes() != serialized or matrix_path.read_bytes() != matrix_bytes or reference_changed:
            raise Refusal(
                f"run {work.resolve()} already contains different immutable opening state; choose a new work directory "
                "or reopen it with the original page and payload."
            )
        return "reopened", manifest
    work.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(serialized)
    matrix_path.write_bytes(matrix_bytes)
    if reference:
        references_path.write_bytes(canonical({"schema_version": 1, "references": [reference]}))
    return "opened", manifest


def load_matrix(work: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    repo_for(work)
    manifest_path = work / "unit-manifest.json"
    matrix_path = work / "matrix.json"
    missing = [path.name for path in (manifest_path, matrix_path) if not path.is_file()]
    if missing:
        raise Refusal(
            f"run {work.resolve()} is not open; missing {', '.join(missing)}. "
            "Run critique.py open with the original page and payload first."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    expected = build_matrix(manifest)
    if matrix.get("unit_manifest_sha256") != expected["unit_manifest_sha256"]:
        raise Refusal(
            f"matrix {matrix_path} does not belong to its unit manifest; reopen from the original inputs in a new work directory."
        )
    actual_ids = [cell.get("cell_id") for cell in matrix.get("cells", [])]
    expected_ids = [cell["cell_id"] for cell in expected["cells"]]
    if actual_ids != expected_ids or matrix.get("lenses") != list(LENSES):
        raise Refusal(
            f"matrix {matrix_path} has a changed unit-by-lens shape; expected {len(expected_ids)} ordered cells. "
            "Open a new run instead of replacing matrix structure."
        )
    return manifest, matrix


def source_text(value: Any) -> str:
    leaves = [
        str(item)
        for _, item in flatten(value)
        if isinstance(item, (str, int, float)) and not isinstance(item, bool)
    ]
    return "\n\n".join(leaves)


def register_source(work: Path, source_id: str, state_path: Path, key: str) -> dict[str, Any]:
    load_matrix(work)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", source_id):
        raise Refusal(
            f"source id {source_id!r} is invalid; use lowercase letters, digits, and hyphens so the producer identity remains stable."
        )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    value = lookup(state, key)
    text = source_text(value)
    if not text.strip():
        raise Refusal(f"source {source_id!r} at key {key!r} has no readable values; register a populated producer record.")
    path = work / "sources.json"
    registry = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema_version": 1, "sources": []}
    if any(item["source_id"] == source_id for item in registry["sources"]):
        raise Refusal(f"source id {source_id!r} is already registered; open a new run instead of replacing upstream evidence.")
    record = {
        "source_id": source_id,
        "state_path": str(state_path.resolve()),
        "state_sha256": digest_file(state_path),
        "key": key,
        "value_sha256": digest_bytes(canonical(value)),
        "text": text,
        "strategy": TRACE_STRATEGY,
    }
    registry["sources"].append(record)
    path.write_bytes(canonical(registry))
    return record


def record_trace(work: Path, cell_id: str, source_id: str, quote: str) -> dict[str, Any]:
    _, matrix = load_matrix(work)
    matches = [cell for cell in matrix["cells"] if cell["cell_id"] == cell_id]
    if not matches:
        raise Refusal(f"cell {cell_id!r} does not exist; choose one of the cell ids shown by status.")
    cell = matches[0]
    if "upstream_trace" in cell:
        raise Refusal(f"cell {cell_id!r} already has an upstream trace; open a new run instead of replacing evidence.")
    registry_path = work / "sources.json"
    if not registry_path.is_file():
        raise Refusal("no upstream sources are registered; run register-source with the producer state and exact key first.")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    sources = [item for item in registry["sources"] if item["source_id"] == source_id]
    if len(sources) != 1:
        raise Refusal(f"source id {source_id!r} is not registered exactly once; choose a source shown in sources.json.")
    source = sources[0]
    grounded = collapsed(quote)
    available = collapsed(source["text"])
    minimum = min(25, len(available))
    if len(grounded) < minimum or grounded not in available:
        raise Refusal(
            f"trace quote for cell {cell_id!r} is not an exact {minimum}-character passage from registered source {source_id!r}; copy the producer's words from sources.json."
        )
    cell["upstream_trace"] = {
        "source_id": source_id,
        "source_value_sha256": source["value_sha256"],
        "quote": grounded,
        "quote_sha256": digest_bytes(grounded.encode()),
        "strategy": TRACE_STRATEGY,
    }
    (work / "matrix.json").write_bytes(canonical(matrix))
    return cell["upstream_trace"]


def register_reference(work: Path, reference_id: str, page_path: Path) -> dict[str, Any]:
    manifest, _ = load_matrix(work)
    declaration = manifest.get("benchmark_reference")
    if declaration and declaration.get("state") == "none":
        raise Refusal(
            f"run declared no reference at open: {declaration['reason']} Open a new run with --reference and --reference-page to use benchmarking."
        )
    path = work / "references.json"
    registry = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema_version": 1, "references": []}
    if any(item["reference_id"] == reference_id for item in registry["references"]):
        raise Refusal(f"reference id {reference_id!r} is already registered; open a new run instead of replacing benchmark evidence.")
    record = reference_record(reference_id, page_path)
    registry["references"].append(record)
    path.write_bytes(canonical(registry))
    return record


def record_benchmark(
    work: Path,
    cell_id: str,
    reference_id: str,
    delivered_quote: str,
    reference_quote: str,
) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    matches = [cell for cell in matrix["cells"] if cell["cell_id"] == cell_id]
    if not matches:
        raise Refusal(f"cell {cell_id!r} does not exist; choose one of the cell ids shown by status.")
    cell = matches[0]
    if cell["lens"] != "benchmark-vs-reference":
        raise Refusal(f"cell {cell_id!r} is not a benchmark-vs-reference cell; attach paired evidence only to that lens.")
    if cell.get("status") == "not-applicable":
        raise Refusal(
            f"cell {cell_id!r} is not applicable because the run declared no reference at open: "
            f"{cell['benchmark_state']['reason']} Open a new run with a real reference to benchmark it."
        )
    if "benchmark" in cell:
        raise Refusal(f"cell {cell_id!r} already has benchmark evidence; open a new run instead of replacing it.")
    registry_path = work / "references.json"
    if not registry_path.is_file():
        raise Refusal("no references are registered; run register-reference with the exact reference page first.")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    references = [item for item in registry["references"] if item["reference_id"] == reference_id]
    if len(references) != 1:
        raise Refusal(f"reference id {reference_id!r} is not registered exactly once; choose one shown in references.json.")
    reference = references[0]
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    delivered = collapsed(delivered_quote)
    delivered_text = collapsed(units[cell["unit_id"]]["text"])
    reference_words = collapsed(reference_quote)
    available_reference = collapsed(reference["text"])
    for label, quote, available in (
        ("delivered", delivered, delivered_text),
        ("reference", reference_words, available_reference),
    ):
        minimum = min(25, len(available))
        if len(quote) < minimum or quote not in available:
            raise Refusal(
                f"{label} benchmark quote for cell {cell_id!r} is not an exact {minimum}-character passage; copy its words from the immutable {label} text."
            )
    cell["benchmark"] = {
        "reference_id": reference_id,
        "reference_page_sha256": reference["page_sha256"],
        "delivered_quote": delivered,
        "delivered_quote_sha256": digest_bytes(delivered.encode()),
        "reference_quote": reference_words,
        "reference_quote_sha256": digest_bytes(reference_words.encode()),
        "strategy": BENCHMARK_STRATEGY,
    }
    (work / "matrix.json").write_bytes(canonical(matrix))
    return cell["benchmark"]


def missing_cells(matrix: dict[str, Any]) -> list[str]:
    return [cell["cell_id"] for cell in matrix["cells"] if cell.get("status") == "unjudged"]


def unresolved_cells(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    return [cell for cell in matrix["cells"] if cell.get("status") == "unresolved"]


def owner_item(cell: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_id": f"owner-{digest_bytes(cell['cell_id'].encode())[:16]}",
        "cell_id": cell["cell_id"],
        "unit_id": cell["unit_id"],
        "lens": cell["lens"],
        "outcome": cell["outcome"],
        "offered_choices": list(VERDICTS),
        "reader_evidence": cell["readers"],
    }


def owner_queue(work: Path) -> dict[str, Any]:
    _, matrix = load_matrix(work)
    items = [owner_item(cell) for cell in unresolved_cells(matrix)]
    result = {
        "status": "waiting-owner" if items else "empty",
        "open_count": len(items),
        "question": items[0] if items else None,
    }
    (work / "owner-queue.json").write_bytes(canonical({"schema_version": 1, "items": items}))
    return result


def answer_owner(work: Path, decision_id: str, choice: str, because: str) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    items = [owner_item(cell) for cell in unresolved_cells(matrix)]
    matches = [item for item in items if item["decision_id"] == decision_id]
    if len(matches) != 1:
        available = [item["decision_id"] for item in items]
        raise Refusal(
            f"owner decision {decision_id!r} is not open exactly once; choose the current id from ask-owner: {available}."
        )
    item = matches[0]
    if choice not in item["offered_choices"]:
        raise Refusal(
            f"owner choice {choice!r} was not offered for {decision_id!r}; choose exactly one of {item['offered_choices']}."
        )
    if not because or not because.strip():
        raise Refusal(f"owner ruling {decision_id!r} has no words; repeat the choice with --because containing the owner's exact words.")
    cell = next(cell for cell in matrix["cells"] if cell["cell_id"] == item["cell_id"])
    if choice in {"reject", "revise"} and not any(
        reader.get("quote") for reader in cell["readers"].values() if reader.get("status") == "answered"
    ):
        raise Refusal(
            f"owner choice {choice!r} for {decision_id!r} would create a defect without page words; choose clear or obtain a grounded reader response first."
        )
    ruling = {
        "decision_id": decision_id,
        "choice": choice,
        "because": because,
        "because_sha256": digest_bytes(because.encode()),
        "offered_choices": item["offered_choices"],
    }
    cell["owner_ruling"] = ruling
    cell["resolved_verdict"] = choice
    cell["outcome"] = "owner-resolved"
    cell["status"] = "judged"
    (work / "matrix.json").write_bytes(canonical(matrix))
    rulings_path = work / "owner-rulings.json"
    recorded = json.loads(rulings_path.read_text(encoding="utf-8")) if rulings_path.is_file() else {"schema_version": 1, "rulings": []}
    recorded["rulings"].append({**ruling, "cell_id": cell["cell_id"]})
    rulings_path.write_bytes(canonical(recorded))
    owner_queue(work)
    return {"status": "recorded", "ruling": ruling, "remaining": len(unresolved_cells(matrix))}


def correct_owner(work: Path, decision_id: str, choice: str, because: str) -> dict[str, Any]:
    _, matrix = load_matrix(work)
    matches = [cell for cell in matrix["cells"] if cell.get("owner_ruling", {}).get("decision_id") == decision_id]
    if len(matches) != 1:
        raise Refusal(
            f"recorded owner decision {decision_id!r} was found {len(matches)} times; choose one recorded id from owner-rulings.json."
        )
    cell = matches[0]
    previous = cell["owner_ruling"]
    if choice not in previous["offered_choices"]:
        raise Refusal(
            f"corrected owner choice {choice!r} was not originally offered for {decision_id!r}; choose exactly one of {previous['offered_choices']}."
        )
    if not because or not because.strip():
        raise Refusal(f"corrected owner ruling {decision_id!r} has no words; supply the owner's exact corrected words.")
    rulings_path = work / "owner-rulings.json"
    if not rulings_path.is_file():
        raise Refusal(f"owner-rulings.json is missing for recorded decision {decision_id!r}; do not reconstruct owner history.")
    recorded = json.loads(rulings_path.read_text(encoding="utf-8"))
    records = [ruling for ruling in recorded.get("rulings", []) if ruling.get("decision_id") == decision_id]
    if len(records) != 1:
        raise Refusal(f"owner-rulings.json contains {len(records)} records for {decision_id!r}; repair the run record before correction.")
    history = cell.setdefault("owner_ruling_history", [])
    history.append(previous)
    corrected = {
        "decision_id": decision_id,
        "choice": choice,
        "because": because,
        "because_sha256": digest_bytes(because.encode()),
        "offered_choices": previous["offered_choices"],
    }
    cell["owner_ruling"] = corrected
    cell["resolved_verdict"] = choice
    record = records[0]
    record.setdefault("history", []).append({key: record[key] for key in previous})
    record.update(corrected)
    (work / "matrix.json").write_bytes(canonical(matrix))
    rulings_path.write_bytes(canonical(recorded))
    return {"status": "corrected", "ruling": corrected, "history_count": len(history)}


def collapsed(value: str) -> str:
    return " ".join(value.split())


def _reader_outcome(cell: dict[str, Any]) -> str:
    readers = cell["readers"]
    values = [readers.get(seat) for seat in READER_SEATS]
    if any(value and value.get("status") == "ungrounded-defect" for value in values):
        return "defect-without-words"
    if any(value and value.get("status") == "no-answer" for value in values):
        return "no-answer"
    if not all(value and value.get("status") == "answered" for value in values):
        return "pending"
    verdicts = [value["verdict"] for value in values]
    if verdicts == ["clear", "clear"]:
        return "agreement-clear"
    if verdicts[0] == verdicts[1] and verdicts[0] in {"reject", "revise"}:
        return "agreement-defect"
    return "disagreement"


def record_reader(
    work: Path,
    cell_id: str,
    seat: str,
    verdict: str | None,
    quote: str | None,
) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    cells = [cell for cell in matrix["cells"] if cell["cell_id"] == cell_id]
    if not cells:
        raise Refusal(f"cell {cell_id!r} does not exist; choose one of the cell ids shown by status.")
    cell = cells[0]
    if cell.get("status") == "not-applicable":
        raise Refusal(
            f"cell {cell_id!r} is not applicable because the run declared no reference at open: "
            f"{cell['benchmark_state']['reason']} No reader judgment can be recorded for this cell."
        )
    if seat not in READER_SEATS:
        raise Refusal(f"reader seat {seat!r} is not allowed; choose exactly one of {list(READER_SEATS)}.")
    if seat in cell.get("readers", {}):
        raise Refusal(
            f"cell {cell_id!r} already has a response from {seat!r}; open a new run instead of replacing evidence."
        )
    if verdict == "no-answer":
        cell["readers"][seat] = {"status": "no-answer", "verdict": None, "quote": None}
        cell["outcome"] = _reader_outcome(cell)
        cell["status"] = "unresolved"
        (work / "matrix.json").write_bytes(canonical(matrix))
        return cell
    if verdict not in VERDICTS:
        raise Refusal(
            f"verdict {verdict!r} is not allowed for cell {cell_id!r}; choose exactly one of {list(VERDICTS)}."
        )
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    unit = units[cell["unit_id"]]
    unit_text = collapsed(unit["text"])
    grounded_quote = collapsed(quote or "")
    if cell["lens"] == "upstream-trace" and verdict in {"reject", "revise"} and not cell.get("upstream_trace"):
        raise Refusal(
            f"cell {cell_id!r} claims an upstream defect but has no producer evidence; register the source and attach an exact trace before recording this verdict."
        )
    if cell["lens"] == "benchmark-vs-reference" and verdict in {"reject", "revise"} and not cell.get("benchmark"):
        raise Refusal(
            f"cell {cell_id!r} claims a benchmark defect but has no paired evidence; register the reference and attach exact words from both sides before recording this verdict."
        )
    if QUOTE_REQUIRED:
        minimum = min(25, len(unit_text))
        if len(grounded_quote) < minimum:
            if verdict in {"reject", "revise"}:
                cell["readers"][seat] = {
                    "status": "ungrounded-defect",
                    "verdict": verdict,
                    "quote": grounded_quote or None,
                }
                cell["outcome"] = _reader_outcome(cell)
                cell["status"] = "unresolved"
                (work / "matrix.json").write_bytes(canonical(matrix))
                return cell
            raise Refusal(
                f"quote for cell {cell_id!r} has {len(grounded_quote)} characters; provide at least "
                f"{minimum} characters copied verbatim from unit {unit['unit_id']!r}, or its whole text if shorter."
            )
        if grounded_quote not in unit_text:
            raise Refusal(
                f"quote for cell {cell_id!r} is not present in unit {unit['unit_id']!r} after whitespace collapse; "
                "copy the exact words from that unit, not a paraphrase or another unit."
            )
    cell["readers"][seat] = {
            "status": "answered",
            "verdict": verdict,
            "quote": grounded_quote or None,
            "quote_sha256": digest_bytes(grounded_quote.encode()) if grounded_quote else None,
            "verdict_strategy": VERDICT_STRATEGY,
    }
    cell["outcome"] = _reader_outcome(cell)
    cell["status"] = "judged" if cell["outcome"].startswith("agreement-") else "unresolved"
    (work / "matrix.json").write_bytes(canonical(matrix))
    return cell


def record_judgment(work: Path, cell_id: str, verdict: str, quote: str | None) -> dict[str, Any]:
    """Compatibility helper for a first blind reader; public CLI requires an explicit seat."""
    return record_reader(work, cell_id, READER_SEATS[0], verdict, quote)


LENS_QUESTIONS = {
    "buyer-read": "Can the client buyer act confidently on what this unit says, without a conflicting status or instruction?",
    "cfo": "Does this unit make the full annual program and its planning coverage visible enough to fund and govern?",
    "journalist": "Would a skeptical journalist find a material contradiction or unsupported status inside this unit?",
    "employee-insider": "Can an informed employee tell what has actually been decided without conflicting internal signals?",
    "competitor-counter-position": "Does the unit expose an inconsistency a competitor could quote to undermine credibility?",
    "benchmark-vs-reference": "Does this calendar unit meet the professional reference shape of twelve explicitly labeled months?",
    "upstream-trace": "Does this calendar unit preserve the upstream promise of a visible full-year cadence?",
}


def _selected_unit(manifest: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    if case["pair_id"] == "stale-door":
        needles = (
            ("No approach has been chosen",)
            if case["expected_quality"] == "defective"
            else ("The approach is decided",)
        )
    else:
        needles = ("### The editorial calendar", "| Month 1 |")
    matches = [unit for unit in manifest["units"] if all(needle in unit["text"] for needle in needles)]
    if len(matches) != 1:
        raise Refusal(
            f"case {case['case_id']!r} exposed {len(matches)} target units for {needles}; expected exactly one real unit."
        )
    return matches[0]


def _reader_judgments(
    root: Path,
    source_context: str,
    focus: str,
    unit: dict[str, Any],
    lenses: list[str],
    evidence_root: Path | None = None,
) -> list[dict[str, Any]]:
    policy_path = Path(__file__).resolve().parents[1] / "client-model-policy.json"
    if not policy_path.is_file():
        raise Refusal(
            f"installed client policy {policy_path} is missing; reinstall the managed skill for this client."
        )
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    runtime_parts = policy.get("required_runtime", "").split()
    if policy.get("fail_closed") is not True or runtime_parts not in (["codex", "exec"], ["claude", "-p"]):
        raise Refusal(
            f"installed client policy {policy_path} is invalid; reinstall the fail-closed client projection."
        )
    runtime = " ".join(runtime_parts)
    client = runtime_parts[0]
    executable = shutil.which(client)
    if not executable:
        raise Refusal(f"model reader unavailable: install the {client} client so the command resolves to {runtime}.")
    properties: dict[str, Any] = {
        "lens": {"type": "string", "enum": lenses},
        "verdict": {"type": "string", "enum": list(VERDICTS)},
    }
    required = ["lens", "verdict"]
    if QUOTE_REQUIRED:
        properties["start_line"] = {"type": "integer"}
        properties["end_line"] = {"type": "integer"}
        required.extend(("start_line", "end_line"))
    schema = {
        "type": "object",
        "properties": {
            "judgments": {
                "type": "array",
                "items": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
            }
        },
        "required": ["judgments"],
        "additionalProperties": False,
    }
    evidence_root = evidence_root or Path(os.environ["EXPERIMENT_RESULT_PATH"]).parent
    evidence_root.mkdir(parents=True, exist_ok=True)
    schema_path = evidence_root / "reader-schema.json"
    result_path = evidence_root / "reader-response.json"
    schema_path.write_bytes(canonical(schema))
    lens_lines = "\n".join(f"- {lens}: {LENS_QUESTIONS[lens]}" for lens in lenses)
    unit_lines = unit["text"].splitlines()
    numbered_unit = "\n".join(f"{index}: {line}" for index, line in enumerate(unit_lines, 1))
    grounding_instruction = (
        "For every judgment, select start_line and end_line from NUMBERED UNIT LINES. Code will copy that inclusive passage exactly. Choose a passage whose whitespace-collapsed text has at least 25 characters."
        if QUOTE_REQUIRED
        else "Return only the lens and verdict; do not include a quote or rationale."
    )
    vocabulary_instruction = (
        "reject = contradiction makes the unit unusable; revise = material weakness needs repair; clear = no material defect under that lens."
        if VERDICT_STRATEGY == "action-grounded"
        else "weak = a material defect exists under that lens; fine = no material defect exists under that lens."
    )
    prompt = f"""Judge one immutable delivered-page unit through each named lens.
Return exactly one judgment per lens, in the listed order.
Vocabulary: {vocabulary_instruction}
{grounding_instruction} Do not use knowledge outside the unit.
Reject or revise only when the quoted words themselves demonstrate a concrete failure of the lens question. Do not penalize a general risk, a style preference, or context absent from this unit. If no concrete failure is present, return clear or fine and quote the strongest words that establish clarity when the schema asks for a quote.
When a defect is an absent item in a sequential table, prove one gap by selecting the complete row immediately before it through the complete row immediately after it.

FIXED FOCUS
{focus}

RECORDED SOURCE CONTEXT
{source_context}

LENSES
{lens_lines}

NUMBERED UNIT LINES
{numbered_unit}
"""
    if runtime_parts == ["codex", "exec"]:
        argv = [
            executable, "exec", "--ephemeral", "--sandbox", "read-only", "--ignore-user-config",
            "--skip-git-repo-check", "--color", "never", "--cd", str(root),
            "--output-schema", str(schema_path), "--output-last-message", str(result_path), "-",
        ]
    else:
        prompt += f"\nReturn only JSON matching this schema exactly:\n{json.dumps(schema, sort_keys=True)}\n"
        argv = [
            executable, "-p", "--output-format", "stream-json", "--verbose",
            "--permission-mode", "acceptEdits", "--disable-slash-commands", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}', "--no-session-persistence",
        ]
    completed = subprocess.run(argv, input=prompt, text=True, capture_output=True, timeout=900)
    (evidence_root / "reader.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (evidence_root / "reader.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if runtime == "claude -p" and completed.returncode == 0:
        events = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        results = [event.get("result") for event in events if event.get("type") == "result" and event.get("result")]
        if results:
            result_path.write_bytes(canonical(json.loads(results[-1])))
    if completed.returncode != 0 or not result_path.is_file():
        raise Refusal(
            f"{runtime} reader failed with exit {completed.returncode}; inspect reader.stderr.txt and rerun this case."
        )
    value = json.loads(result_path.read_text(encoding="utf-8"))
    judgments = value.get("judgments", [])
    if [item.get("lens") for item in judgments] != lenses:
        raise Refusal(
            f"reader returned lenses {[item.get('lens') for item in judgments]!r}; expected exactly {lenses!r} in order."
        )
    if QUOTE_REQUIRED:
        for item in judgments:
            start = item.get("start_line")
            end = item.get("end_line")
            if type(start) is not int or type(end) is not int or start < 1 or end < start or end > len(unit_lines):
                raise Refusal(
                    f"reader selected invalid line span {start!r}-{end!r}; choose 1 through {len(unit_lines)} with start not after end."
                )
            item["quote"] = "\n".join(unit_lines[start - 1 : end])
    return judgments


def read_cell(work: Path, cell_id: str) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    matches = [cell for cell in matrix["cells"] if cell["cell_id"] == cell_id]
    if not matches:
        raise Refusal(f"cell {cell_id!r} does not exist; choose one of the cell ids shown by status.")
    cell = matches[0]
    if cell.get("status") == "not-applicable":
        return cell
    if cell.get("readers"):
        raise Refusal(f"cell {cell_id!r} already has reader evidence; open a new run instead of replacing it.")
    unit = next(unit for unit in manifest["units"] if unit["unit_id"] == cell["unit_id"])
    source_context = "No external source is available for this blind reading. Judge only the immutable unit."
    focus = LENS_QUESTIONS[cell["lens"]]
    for seat in READER_SEATS:
        evidence_root = work / "reader-evidence" / digest_bytes(cell_id.encode())[:16] / seat
        judgments = _reader_judgments(
            repo_for(work), source_context, focus, unit, [cell["lens"]], evidence_root=evidence_root
        )
        item = judgments[0]
        record_reader(work, cell_id, seat, item["verdict"], item.get("quote"))
    _, refreshed = load_matrix(work)
    return next(item for item in refreshed["cells"] if item["cell_id"] == cell_id)


def read_run(work: Path) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    source_context = "No external source is available for this blind reading. Judge only the immutable unit."
    jobs = []
    for unit in manifest["units"]:
        unit_cells = [cell for cell in matrix["cells"] if cell["unit_id"] == unit["unit_id"]]
        for seat in READER_SEATS:
            lenses = [
                cell["lens"] for cell in unit_cells
                if cell.get("status") != "not-applicable" and seat not in cell["readers"]
            ]
            if lenses:
                jobs.append((unit, seat, lenses))

    def launch(job):
        unit, seat, lenses = job
        evidence_root = work / "reader-evidence" / f"batch-{unit['unit_id']}" / seat
        return job, _reader_judgments(
            repo_for(work), source_context, "Judge every listed lens for this unit.",
            unit, lenses, evidence_root=evidence_root,
        )

    launched = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(jobs) or 1)) as pool:
        futures = [pool.submit(launch, job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            launched.append(future.result())
    for (unit, seat, _), judgments in sorted(launched, key=lambda item: (item[0][0]["unit_id"], item[0][1])):
        for judgment in judgments:
            record_reader(
                work, f"{unit['unit_id']}::{judgment['lens']}", seat,
                judgment["verdict"], judgment.get("quote"),
            )
    status = matrix_status(work)
    return {"status": status["status"], "reader_calls": len(jobs), **status}


def completeness_refusal(matrix: dict[str, Any], route: str) -> None:
    missing = missing_cells(matrix)
    protected = route in {"cell", "report", "document"} if MATRIX_GATE_STRATEGY == "universal-gate" else route in {"report", "document"}
    if missing and protected:
        preview = ", ".join(missing[:8])
        remainder = f" and {len(missing) - 8} more" if len(missing) > 8 else ""
        raise Refusal(
            f"{route} refused: {len(missing)} matrix cells are unjudged: {preview}{remainder}. "
            "Judge every named unit/lens cell before requesting critique results."
        )


def matrix_status(work: Path) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    missing = missing_cells(matrix)
    unresolved = unresolved_cells(matrix)
    not_applicable = [cell for cell in matrix["cells"] if cell.get("status") == "not-applicable"]
    declaration = manifest.get("benchmark_reference")
    return {
        "status": "partial" if missing or unresolved else "complete",
        "unit_count": len({cell["unit_id"] for cell in matrix["cells"]}),
        "lens_count": len(matrix["lenses"]),
        "cell_count": len(matrix["cells"]),
        "judged_count": sum(cell.get("status") == "judged" for cell in matrix["cells"]),
        "not_applicable_count": len(not_applicable),
        "benchmark_no_reference_count": sum(
            cell.get("benchmark_state", {}).get("state") == "no-reference" for cell in not_applicable
        ),
        "benchmark_no_reference_reason": (
            declaration.get("reason") if declaration and declaration.get("state") == "none" else None
        ),
        "unjudged_count": len(missing),
        "unjudged_cells": missing,
        "owner_queue_count": len(unresolved),
    }


def reporting_route(work: Path, route: str, cell_id: str | None = None) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    completeness_refusal(matrix, route)
    if route == "cell":
        matches = [cell for cell in matrix["cells"] if cell["cell_id"] == cell_id]
        if not matches:
            raise Refusal(f"cell {cell_id!r} does not exist; choose one of the cell ids shown by status.")
        return matches[0]
    queue = unresolved_cells(matrix)
    if queue:
        ids = [owner_item(cell)["decision_id"] for cell in queue]
        raise Refusal(
            f"{route} refused: {len(queue)} owner questions remain open: {', '.join(ids[:8])}. Run ask-owner, record only an offered choice with answer-owner, then retry."
        )
    if route == "report":
        defects = [
            cell for cell in matrix["cells"]
            if cell["outcome"] == "agreement-defect" or cell.get("resolved_verdict") in {"reject", "revise"}
        ]
        return {"status": "complete", "route": route, "cells": len(matrix["cells"]), "located_defects": len(defects)}
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    findings = [
        cell for cell in matrix["cells"]
        if cell["outcome"] == "agreement-defect" or cell["outcome"] == "owner-resolved"
    ]
    lines = [
        "# Located critique findings",
        "",
        f"Source page SHA-256: `{manifest['page']['sha256']}`",
        f"Complete matrix: {len(matrix['cells'])} cells across {len(manifest['units'])} units and {len(matrix['lenses'])} lenses.",
        "",
    ]
    declaration = manifest.get("benchmark_reference")
    if declaration and declaration.get("state") == "none":
        lines.extend(
            [
                "## Benchmark vs reference",
                "",
                f"Not applicable — {declaration['reason']}",
                "",
            ]
        )
    if not findings:
        lines.extend(["No located defects or owner-resolved disputes.", ""])
    for index, cell in enumerate(findings, 1):
        verdict = cell.get("resolved_verdict") or next(
            reader["verdict"] for reader in cell["readers"].values() if reader.get("verdict")
        )
        lines.extend([
            f"## {index}. {units[cell['unit_id']]['label']} — {cell['lens']}",
            "",
            f"Verdict: **{verdict}** · outcome: `{cell['outcome']}` · cell: `{cell['cell_id']}`",
            "",
        ])
        for seat in READER_SEATS:
            reader = cell["readers"].get(seat)
            if reader:
                lines.extend([f"- {seat}: {reader.get('verdict') or reader.get('status')} — {reader.get('quote') or 'no grounded page words'}"])
        if cell.get("upstream_trace"):
            lines.extend([f"- upstream `{cell['upstream_trace']['source_id']}`: {cell['upstream_trace']['quote']}"])
        if cell.get("benchmark"):
            lines.extend([
                f"- delivered: {cell['benchmark']['delivered_quote']}",
                f"- reference `{cell['benchmark']['reference_id']}`: {cell['benchmark']['reference_quote']}",
            ])
        if cell.get("owner_ruling"):
            lines.extend([f"- owner ruling ({cell['owner_ruling']['choice']}): {cell['owner_ruling']['because']}"])
        lines.append("")
    output = Path(cell_id) if cell_id else work / "critique-findings.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "complete", "route": route, "cells": len(matrix["cells"]), "findings": len(findings), "path": str(output.resolve()), "sha256": digest_file(output)}


def split_payload(value: str, key: str | None) -> tuple[Path, str]:
    if key:
        return Path(value), key
    if "#" not in value:
        raise Refusal("--payload must be STATE.json#context.key or be accompanied by --key context.key.")
    path, dotted = value.rsplit("#", 1)
    if not path or not dotted:
        raise Refusal("--payload must contain both a state path and a key separated by '#'.")
    return Path(path), dotted


def safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive) as handle:
        for member in handle.getmembers():
            target = (destination / member.name).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise Refusal(f"captured case contains unsafe archive member {member.name!r}.")
        handle.extractall(destination, filter="data")


def experiment() -> int:
    archive = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        safe_extract(archive, root)
        case = json.loads((root / "case.json").read_text(encoding="utf-8"))
        repo = root / "repo"
        (repo / ".git").mkdir(parents=True)
        work = repo / "Tasks" / "critique-probe" / "run"
        actual = "opened"
        error = None
        manifest = None
        route_evidence: dict[str, Any] = {}
        judgments: list[dict[str, Any]] = []
        invalid_quote_refusal = ""
        try:
            _, manifest = open_run(
                root / "page.md",
                root / "state.json",
                case["payload_key"],
                work,
                no_reference="The frozen development case supplies no external benchmark page.",
            )
            unit = _selected_unit(manifest, case)
            lenses = case["applicable_lenses"]
            first_cell = f"{unit['unit_id']}::{lenses[0]}"
            if QUOTE_REQUIRED:
                try:
                    record_judgment(work, first_cell, VERDICTS[0], "words that never appear in the immutable unit")
                except Refusal as exc:
                    invalid_quote_refusal = str(exc)
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            if case["pair_id"] == "stale-door":
                source_context = json.dumps(state["context"]["inputs"]["big_idea_decision"], ensure_ascii=False, sort_keys=True)
                focus = "Assess only whether the approach-decision status stated in UNIT TEXT agrees with the recorded source decision. Ignore public-expression status and every unrelated improvement opportunity."
            else:
                source_context = "The requested professional calendar shape is twelve explicitly labeled months, Month 1 through Month 12."
                focus = "Assess only whether UNIT TEXT visibly contains every month label from Month 1 through Month 12. Ignore every unrelated improvement opportunity."
            for item in _reader_judgments(root, source_context, focus, unit, lenses):
                cell_id = f"{unit['unit_id']}::{item['lens']}"
                judgments.append(record_judgment(work, cell_id, item["verdict"], item.get("quote")))
            actual = "judged"
        except Refusal as exc:
            actual = "refused-page-payload-mismatch" if "page/payload mismatch" in str(exc) else "refused-other"
            error = str(exc)
        expected = "judged"
        correct = actual == expected
        red = case["expected_quality"] == "defective"
        expected_verdicts = {"reject", "revise"} if red else {"clear"}
        verdicts = [item.get("verdict") for item in judgments]
        quotes = [item.get("quote") for item in judgments]
        outcome = {
            "case_id": case["case_id"],
            "expected": expected,
            "actual": actual,
            "correct": correct,
            "error": error,
            "pair_id": case["pair_id"],
            "expected_quality": case["expected_quality"],
            "lenses": case["applicable_lenses"],
            "judgments": judgments,
            "classification_correct": bool(judgments) and all(verdict in expected_verdicts for verdict in verdicts),
            "classification_count": sum(verdict in expected_verdicts for verdict in verdicts),
            "grounded_count": sum(bool(quote) for quote in quotes),
            "actionable_quote_count": sum(bool(quote and len(quote) >= 25) for quote in quotes),
            "invalid_quote_refused": bool(invalid_quote_refusal),
            "invalid_quote_error": invalid_quote_refusal,
            "manifest_sha256": digest_bytes(canonical(manifest)) if manifest else None,
            "route_evidence": route_evidence,
        }
    result = {
        "schema_version": 1,
        "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
        "status": "completed",
        "outcome": outcome,
        "metrics": {},
        "error": None,
    }
    result_bytes = canonical(result)
    Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_bytes(result_bytes)
    telemetry = {
        "schema_version": 1,
        "sequence": 1,
        "event": "work_completed",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
        "message": "Opened the frozen real page and recorded model-backed cell verdicts through the candidate judgment contract.",
        "evidence_sha256": digest_bytes(result_bytes),
        "observations": {
            "classification_correct": outcome["classification_correct"],
            "grounded_count": outcome["grounded_count"],
            "invalid_quote_refused": outcome["invalid_quote_refused"],
        },
    }
    Path(os.environ["EXPERIMENT_TELEMETRY_PATH"]).write_bytes(canonical(telemetry))
    return 0


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("EXPERIMENT_INPUT_PATH"):
        return experiment()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    opening = sub.add_parser("open", help="freeze a payload-grounded unit manifest")
    opening.add_argument("--page", required=True)
    opening.add_argument("--payload", required=True)
    opening.add_argument("--key")
    opening.add_argument("--work", required=True)
    opening.add_argument("--reference")
    opening.add_argument("--reference-page")
    opening.add_argument("--no-reference")
    status_parser = sub.add_parser("status", help="show complete matrix coverage without leaking critique results")
    status_parser.add_argument("--work", required=True)
    cell_parser = sub.add_parser("cell", help="read one cell only after the matrix is complete")
    cell_parser.add_argument("--work", required=True)
    cell_parser.add_argument("--id", required=True)
    judge_parser = sub.add_parser("judge", help="record one fixed verdict grounded in one immutable unit")
    judge_parser.add_argument("--work", required=True)
    judge_parser.add_argument("--id", required=True)
    judge_parser.add_argument("--seat", required=True, choices=READER_SEATS)
    judge_parser.add_argument("--verdict", required=True)
    judge_parser.add_argument("--quote")
    read_parser = sub.add_parser("read-cell", help="run two independent model readers on one immutable cell")
    read_parser.add_argument("--work", required=True)
    read_parser.add_argument("--id", required=True)
    read_run_parser = sub.add_parser("read-run", help="resume blind readers across every unread matrix cell")
    read_run_parser.add_argument("--work", required=True)
    ask_parser = sub.add_parser("ask-owner", help="show the next unresolved reader outcome without casting it")
    ask_parser.add_argument("--work", required=True)
    answer_parser = sub.add_parser("answer-owner", help="record one offered verdict in the owner's exact words")
    answer_parser.add_argument("--work", required=True)
    answer_parser.add_argument("--id", required=True)
    answer_parser.add_argument("--choice", required=True)
    answer_parser.add_argument("--because", required=True)
    correction_parser = sub.add_parser("correct-owner", help="correct one recorded ruling while preserving its prior version")
    correction_parser.add_argument("--work", required=True)
    correction_parser.add_argument("--id", required=True)
    correction_parser.add_argument("--choice", required=True)
    correction_parser.add_argument("--because", required=True)
    source_parser = sub.add_parser("register-source", help="freeze one upstream producer source")
    source_parser.add_argument("--work", required=True)
    source_parser.add_argument("--source", required=True)
    source_parser.add_argument("--payload", required=True)
    source_parser.add_argument("--key")
    trace_parser = sub.add_parser("trace", help="attach exact registered upstream words to one cell")
    trace_parser.add_argument("--work", required=True)
    trace_parser.add_argument("--id", required=True)
    trace_parser.add_argument("--source", required=True)
    trace_parser.add_argument("--quote", required=True)
    reference_parser = sub.add_parser("register-reference", help="freeze one professional reference page")
    reference_parser.add_argument("--work", required=True)
    reference_parser.add_argument("--reference", required=True)
    reference_parser.add_argument("--page", required=True)
    benchmark_parser = sub.add_parser("benchmark", help="attach exact delivered and reference words to one benchmark cell")
    benchmark_parser.add_argument("--work", required=True)
    benchmark_parser.add_argument("--id", required=True)
    benchmark_parser.add_argument("--reference", required=True)
    benchmark_parser.add_argument("--delivered-quote", required=True)
    benchmark_parser.add_argument("--reference-quote", required=True)
    for name in ("report", "document"):
        route_parser = sub.add_parser(name, help=f"produce {name} only after every matrix cell is judged")
        route_parser.add_argument("--work", required=True)
        if name == "document":
            route_parser.add_argument("--out")
    args = parser.parse_args(argv)
    try:
        if args.command == "open":
            state_path, key = split_payload(args.payload, args.key)
            status, manifest = open_run(
                Path(args.page),
                state_path,
                key,
                Path(args.work),
                reference_id=args.reference,
                reference_page=Path(args.reference_page) if args.reference_page else None,
                no_reference=args.no_reference,
            )
            result = {
                "status": status,
                "work": str(Path(args.work).resolve()),
                "units": len(manifest["units"]),
                "benchmark_reference": manifest["benchmark_reference"],
            }
        elif args.command == "status":
            result = matrix_status(Path(args.work))
        elif args.command == "judge":
            result = record_reader(Path(args.work), args.id, args.seat, args.verdict, args.quote)
        elif args.command == "read-cell":
            result = read_cell(Path(args.work), args.id)
        elif args.command == "read-run":
            result = read_run(Path(args.work))
        elif args.command == "ask-owner":
            result = owner_queue(Path(args.work))
        elif args.command == "answer-owner":
            result = answer_owner(Path(args.work), args.id, args.choice, args.because)
        elif args.command == "correct-owner":
            result = correct_owner(Path(args.work), args.id, args.choice, args.because)
        elif args.command == "register-source":
            state_path, key = split_payload(args.payload, args.key)
            result = register_source(Path(args.work), args.source, state_path, key)
        elif args.command == "trace":
            result = record_trace(Path(args.work), args.id, args.source, args.quote)
        elif args.command == "register-reference":
            result = register_reference(Path(args.work), args.reference, Path(args.page))
        elif args.command == "benchmark":
            result = record_benchmark(
                Path(args.work), args.id, args.reference, args.delivered_quote, args.reference_quote
            )
        else:
            route_argument = args.id if args.command == "cell" else getattr(args, "out", None)
            result = reporting_route(Path(args.work), args.command, route_argument)
    except (OSError, ValueError, json.JSONDecodeError, Refusal) as exc:
        print(f"critique refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
