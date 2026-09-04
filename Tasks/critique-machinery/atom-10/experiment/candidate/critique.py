#!/usr/bin/env python3
"""Open one delivered page as an immutable, payload-grounded critique run."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
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
READER_REPLY_OUTCOMES = ("valid", "malformed", "empty", "timeout", "nonzero-exit")
READER_TIMEOUT_SECONDS = 900
READER_MAX_ATTEMPTS = 2
TRACE_STRATEGY = "registered-source-exact-quote"
BENCHMARK_STRATEGY = "paired-exact-evidence"
NO_REFERENCE_STRATEGY = "declared-no-reference"
NO_UPSTREAM_STRATEGY = "declared-no-upstream"
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
    upstream_declaration = manifest.get("upstream_sources")
    no_upstream = (
        upstream_declaration
        if upstream_declaration and upstream_declaration.get("state") == "none"
        else None
    )
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
            if lens == "upstream-trace" and no_upstream:
                cell.update(
                    {
                        "status": "not-applicable",
                        "outcome": "not-applicable",
                        "upstream_state": {
                            "state": "no-upstream",
                            "reason": no_upstream["reason"],
                            "strategy": NO_UPSTREAM_STRATEGY,
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


def source_record(source_id: str, state_path: Path, key: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", source_id):
        raise Refusal(
            f"source id {source_id!r} is invalid; use lowercase letters, digits, and hyphens so the producer identity remains stable."
        )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    value = lookup(state, key)
    text = source_text(value)
    if not text.strip():
        raise Refusal(f"source {source_id!r} at key {key!r} has no readable values; register a populated producer record.")
    return {
        "source_id": source_id,
        "state_path": str(state_path.resolve()),
        "state_sha256": digest_file(state_path),
        "key": key,
        "value_sha256": digest_bytes(canonical(value)),
        "text": text,
        "strategy": TRACE_STRATEGY,
    }


def upstream_declaration(
    upstream_sources: list[tuple[str, Path, str]] | None,
    no_upstream: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    has_sources = bool(upstream_sources)
    has_no_upstream = no_upstream is not None
    if has_sources and has_no_upstream:
        raise Refusal(
            "open received both producer sources and --no-upstream; choose exactly one: repeat "
            "--upstream-source <id>=STATE.json#context.key, or --no-upstream \"<recorded reason>\"."
        )
    if not has_sources and not has_no_upstream:
        raise Refusal(
            "open requires exactly one upstream-source declaration: repeat --upstream-source "
            "<id>=STATE.json#context.key, or --no-upstream \"<recorded reason>\"."
        )
    if has_sources:
        records = [source_record(source_id, path.resolve(), key) for source_id, path, key in upstream_sources or []]
        ids = [record["source_id"] for record in records]
        if len(ids) != len(set(ids)):
            raise Refusal("open received a duplicate upstream source id; name every producer source exactly once.")
        return (
            {
                "state": "registered",
                "sources": [
                    {
                        "source_id": record["source_id"],
                        "state_sha256": record["state_sha256"],
                        "value_sha256": record["value_sha256"],
                    }
                    for record in records
                ],
                "strategy": TRACE_STRATEGY,
            },
            records,
        )
    reason = collapsed(no_upstream or "")
    if not reason:
        raise Refusal("--no-upstream requires a non-empty recorded reason explaining why no producer material exists.")
    return ({"state": "none", "reason": reason, "strategy": NO_UPSTREAM_STRATEGY}, [])


def open_run(
    page_path: Path,
    state_path: Path,
    key: str,
    work: Path,
    *,
    reference_id: str | None = None,
    reference_page: Path | None = None,
    no_reference: str | None = None,
    upstream_sources: list[tuple[str, Path, str]] | None = None,
    no_upstream: str | None = None,
) -> tuple[str, dict[str, Any]]:
    repo_for(work)
    declaration, reference = benchmark_declaration(reference_id, reference_page, no_reference)
    upstream, source_records = upstream_declaration(upstream_sources, no_upstream)
    manifest = build_manifest(page_path.resolve(), state_path.resolve(), key)
    manifest["benchmark_reference"] = declaration
    manifest["upstream_sources"] = upstream
    destination = work / "unit-manifest.json"
    matrix_path = work / "matrix.json"
    references_path = work / "references.json"
    sources_path = work / "sources.json"
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
        sources_bytes = canonical({"schema_version": 1, "sources": source_records}) if source_records else None
        sources_changed = (
            sources_bytes is not None and (not sources_path.is_file() or sources_path.read_bytes() != sources_bytes)
        ) or (sources_bytes is None and sources_path.exists())
        if (
            destination.read_bytes() != serialized
            or matrix_path.read_bytes() != matrix_bytes
            or reference_changed
            or sources_changed
        ):
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
    if source_records:
        sources_path.write_bytes(canonical({"schema_version": 1, "sources": source_records}))
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
    manifest, _ = load_matrix(work)
    declaration = manifest.get("upstream_sources")
    if declaration and declaration.get("state") == "none":
        raise Refusal(
            f"run declared no upstream material at open: {declaration['reason']} Open a new run with "
            "--upstream-source to use producer evidence."
        )
    path = work / "sources.json"
    registry = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema_version": 1, "sources": []}
    if any(item["source_id"] == source_id for item in registry["sources"]):
        raise Refusal(f"source id {source_id!r} is already registered; open a new run instead of replacing upstream evidence.")
    record = source_record(source_id, state_path, key)
    registry["sources"].append(record)
    path.write_bytes(canonical(registry))
    return record


def validated_trace(work: Path, cell_id: str, source_id: str | None, quote: str | None) -> dict[str, Any]:
    if not source_id:
        raise Refusal(
            f"cell {cell_id!r} claims an upstream defect but names no producer source; return source_id plus exact producer lines."
        )
    registry_path = work / "sources.json"
    if not registry_path.is_file():
        raise Refusal(
            f"cell {cell_id!r} claims an upstream defect but no producer sources are registered; "
            "open a new run with --upstream-source."
        )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    sources = [item for item in registry["sources"] if item["source_id"] == source_id]
    if len(sources) != 1:
        raise Refusal(f"source id {source_id!r} is not registered exactly once; choose a source shown in sources.json.")
    source = sources[0]
    grounded = collapsed(quote or "")
    available = collapsed(source["text"])
    minimum = min(25, len(available))
    if len(grounded) < minimum or grounded not in available:
        raise Refusal(
            f"trace quote for cell {cell_id!r} is not an exact {minimum}-character passage from registered source {source_id!r}; copy the producer's words from sources.json."
        )
    return {
        "source_id": source_id,
        "source_value_sha256": source["value_sha256"],
        "quote": grounded,
        "quote_sha256": digest_bytes(grounded.encode()),
        "strategy": TRACE_STRATEGY,
    }


def record_trace(work: Path, cell_id: str, source_id: str, quote: str) -> dict[str, Any]:
    _, matrix = load_matrix(work)
    matches = [cell for cell in matrix["cells"] if cell["cell_id"] == cell_id]
    if not matches:
        raise Refusal(f"cell {cell_id!r} does not exist; choose one of the cell ids shown by status.")
    cell = matches[0]
    if cell["lens"] != "upstream-trace":
        raise Refusal(f"cell {cell_id!r} is not an upstream-trace cell; attach producer words only to that lens.")
    if "upstream_trace" in cell:
        raise Refusal(f"cell {cell_id!r} already has an upstream trace; open a new run instead of replacing evidence.")
    cell["upstream_trace"] = validated_trace(work, cell_id, source_id, quote)
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


def _not_applicable_refusal(cell: dict[str, Any]) -> Refusal:
    state = cell.get("benchmark_state") or cell.get("upstream_state") or {}
    declared = "no reference" if "benchmark_state" in cell else "no upstream material"
    return Refusal(
        f"cell {cell['cell_id']!r} is not applicable because the run declared {declared} at open: "
        f"{state.get('reason', 'no reason recorded')} No reader judgment can be recorded for this cell."
    )


def _apply_reader_claim(
    work: Path,
    manifest: dict[str, Any],
    cell: dict[str, Any],
    seat: str,
    verdict: str | None,
    quote: str | None,
    source_id: str | None = None,
    source_quote: str | None = None,
    intake: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cell_id = cell["cell_id"]
    if cell.get("status") == "not-applicable":
        raise _not_applicable_refusal(cell)
    if seat not in READER_SEATS:
        raise Refusal(f"reader seat {seat!r} is not allowed; choose exactly one of {list(READER_SEATS)}.")
    if seat in cell.get("readers", {}):
        raise Refusal(
            f"cell {cell_id!r} already has a response from {seat!r}; open a new run instead of replacing evidence."
        )
    if verdict == "no-answer":
        cell["readers"][seat] = {
            "status": "no-answer",
            "verdict": None,
            "quote": None,
            **({"intake": copy.deepcopy(intake)} if intake else {}),
        }
        cell["outcome"] = _reader_outcome(cell)
        cell["status"] = "unresolved"
        return cell
    if verdict not in VERDICTS:
        raise Refusal(
            f"verdict {verdict!r} is not allowed for cell {cell_id!r}; choose exactly one of {list(VERDICTS)}."
        )
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    unit = units[cell["unit_id"]]
    unit_text = collapsed(unit["text"])
    grounded_quote = collapsed(quote or "")
    trace = None
    if cell["lens"] == "upstream-trace" and verdict in {"reject", "revise"}:
        if source_id or source_quote:
            trace = validated_trace(work, cell_id, source_id, source_quote)
        elif cell.get("upstream_trace"):
            trace = cell["upstream_trace"]
        else:
            raise Refusal(
                f"cell {cell_id!r} claims an upstream defect but has no producer evidence; "
                "return source_id plus exact producer lines from the registered sources."
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
    reader = {
        "status": "answered",
        "verdict": verdict,
        "quote": grounded_quote or None,
        "quote_sha256": digest_bytes(grounded_quote.encode()) if grounded_quote else None,
        "verdict_strategy": VERDICT_STRATEGY,
        **({"intake": copy.deepcopy(intake)} if intake else {}),
    }
    if trace:
        reader["upstream_trace"] = trace
    cell["readers"][seat] = reader
    cell["outcome"] = _reader_outcome(cell)
    cell["status"] = "judged" if cell["outcome"].startswith("agreement-") else "unresolved"
    return cell


def record_reader(
    work: Path,
    cell_id: str,
    seat: str,
    verdict: str | None,
    quote: str | None,
    *,
    source_id: str | None = None,
    source_quote: str | None = None,
    intake: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    cells = [cell for cell in matrix["cells"] if cell["cell_id"] == cell_id]
    if not cells:
        raise Refusal(f"cell {cell_id!r} does not exist; choose one of the cell ids shown by status.")
    cell = cells[0]
    _apply_reader_claim(work, manifest, cell, seat, verdict, quote, source_id, source_quote, intake)
    (work / "matrix.json").write_bytes(canonical(matrix))
    return cell


def record_cell_readers(work: Path, cell_id: str, claims: dict[str, dict[str, Any]]) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    matches = [cell for cell in matrix["cells"] if cell["cell_id"] == cell_id]
    if not matches:
        raise Refusal(f"cell {cell_id!r} does not exist; choose one of the cell ids shown by status.")
    cell = matches[0]
    if cell.get("status") == "not-applicable":
        raise _not_applicable_refusal(cell)
    if cell.get("readers"):
        raise Refusal(f"cell {cell_id!r} already has reader evidence; open a new run instead of replacing it.")
    if set(claims) != set(READER_SEATS):
        raise Refusal(
            f"atomic recording for cell {cell_id!r} requires both seats {list(READER_SEATS)}; received {sorted(claims)}."
        )
    candidate = copy.deepcopy(cell)
    failures = []
    for seat in READER_SEATS:
        claim = claims[seat]
        try:
            _apply_reader_claim(
                work,
                manifest,
                candidate,
                seat,
                claim.get("verdict"),
                claim.get("quote"),
                claim.get("source_id"),
                claim.get("source_quote"),
                claim.get("intake"),
            )
        except Refusal as exc:
            failures.append({"seat": seat, "reason": str(exc)})
    if failures:
        cell["readers"] = {
            seat: {
                "status": "recording-refused" if any(item["seat"] == seat for item in failures) else "claim-captured",
                "verdict": claims[seat].get("verdict"),
                "quote": collapsed(claims[seat].get("quote") or "") or None,
                "source_id": claims[seat].get("source_id"),
                "source_quote": collapsed(claims[seat].get("source_quote") or "") or None,
                **({"intake": copy.deepcopy(claims[seat]["intake"])} if claims[seat].get("intake") else {}),
            }
            for seat in READER_SEATS
        }
        cell["status"] = "refused"
        cell["outcome"] = "recording-refusal"
        cell["recording_refusal"] = {
            "failures": failures,
            "repair": "Open a new run and rerun only after each defect claim includes exact registered producer evidence.",
        }
    else:
        cell.clear()
        cell.update(candidate)
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


def reader_schema(lenses: list[str]) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "lens": {"type": "string", "enum": lenses},
        "verdict": {"type": "string", "enum": list(VERDICTS)},
    }
    required = ["lens", "verdict"]
    if QUOTE_REQUIRED:
        properties["start_line"] = {"type": "integer"}
        properties["end_line"] = {"type": "integer"}
        required.extend(("start_line", "end_line"))
    if "upstream-trace" in lenses:
        properties["source_id"] = {"type": "string"}
        properties["source_start_line"] = {"type": "integer"}
        properties["source_end_line"] = {"type": "integer"}
    return {
        "type": "object",
        "properties": {
            "judgments": {
                "type": "array",
                "minItems": len(lenses),
                "maxItems": len(lenses),
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            }
        },
        "required": ["judgments"],
        "additionalProperties": False,
    }


def _schema_problems(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
    problems: list[str] = []
    kind = schema.get("type")
    kinds = {"object": dict, "array": list, "string": str}
    if kind == "integer" and (type(value) is not int):
        return [f"{path} expected integer, received {type(value).__name__}"]
    if kind in kinds and not isinstance(value, kinds[kind]):
        return [f"{path} expected {kind}, received {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path} received {value!r}; expected one of {schema['enum']!r}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"{path}.{key} is missing")
        if schema.get("additionalProperties") is False:
            for key in sorted(set(value) - set(properties)):
                problems.append(f"{path}.{key} is not allowed")
        for key, child_schema in properties.items():
            if key in value:
                problems.extend(_schema_problems(child_schema, value[key], f"{path}.{key}"))
    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if type(minimum) is int and len(value) < minimum:
            problems.append(f"{path} contains {len(value)} items; expected at least {minimum}")
        if type(maximum) is int and len(value) > maximum:
            problems.append(f"{path} contains {len(value)} items; expected at most {maximum}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                problems.extend(_schema_problems(item_schema, item, f"{path}[{index}]"))
    return problems


def classify_reader_reply(
    raw_reply: str | bytes,
    schema: dict[str, Any],
    lenses: list[str],
    *,
    batch_id: str,
    seat: str,
    attempt: int,
    evidence_path: str,
    forced_outcome: str | None = None,
    process_detail: str | None = None,
    exit_code: int | None = 0,
) -> dict[str, Any]:
    raw = raw_reply if isinstance(raw_reply, bytes) else raw_reply.encode("utf-8")
    if forced_outcome is not None and forced_outcome not in READER_REPLY_OUTCOMES:
        raise Refusal(
            f"batch {batch_id!r}, seat {seat!r} has unknown intake outcome {forced_outcome!r}; "
            f"choose exactly one of {list(READER_REPLY_OUTCOMES)}."
        )
    outcome = forced_outcome
    value: Any = None
    failure_detail = process_detail
    if outcome is None:
        if not raw.strip():
            outcome = "empty"
            failure_detail = f"zero semantic reply bytes were returned from {len(raw)} transport bytes"
        else:
            try:
                value = json.loads(raw.decode("utf-8"))
            except UnicodeDecodeError as exc:
                outcome = "malformed"
                failure_detail = f"UTF-8 decoding broke at byte {exc.start}: {exc.reason}"
            except json.JSONDecodeError as exc:
                outcome = "malformed"
                byte_offset = len(exc.doc[: exc.pos].encode("utf-8"))
                failure_detail = (
                    f"JSON parsing broke at byte {byte_offset}, character {exc.pos}, "
                    f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
                )
            else:
                problems = _schema_problems(schema, value)
                judgments = value.get("judgments", []) if isinstance(value, dict) else []
                received_lenses = [item.get("lens") for item in judgments if isinstance(item, dict)]
                if received_lenses != lenses:
                    problems.append(
                        f"$.judgments lens order was {received_lenses!r}; expected exactly {lenses!r}"
                    )
                if problems:
                    outcome = "malformed"
                    failure_detail = "; ".join(problems)
                else:
                    outcome = "valid"
    intake = {
        "schema_version": 1,
        "request_id": f"{batch_id}::{seat}",
        "batch_id": batch_id,
        "seat": seat,
        "attempt": attempt,
        "outcome": outcome,
        "lenses": list(lenses),
        "evidence_path": evidence_path,
        "reply_bytes": len(raw),
        "reply_sha256": digest_bytes(raw) if raw else None,
        "exit_code": exit_code,
    }
    if outcome != "valid":
        observed = failure_detail or f"{outcome} after {len(raw)} reply bytes"
        intake["refusal"] = (
            f"batch {batch_id!r}, seat {seat!r}, attempt {attempt} returned {outcome}: {observed}. "
            f"Return exactly one JSON object matching reader-schema.json with judgments for "
            f"{lenses!r} in that order and nothing before or after it."
        )
    return {
        "outcome": outcome,
        "judgments": value["judgments"] if outcome == "valid" else [],
        "intake": intake,
    }


def _claims_from_reader_result(result: dict[str, Any], lenses: list[str]) -> dict[str, dict[str, Any]]:
    intake = result["intake"]
    if result["outcome"] == "valid":
        return {
            item["lens"]: {**item, "intake": copy.deepcopy(intake)}
            for item in result["judgments"]
        }
    return {
        lens: {"verdict": "no-answer", "quote": None, "intake": copy.deepcopy(intake)}
        for lens in lenses
    }


def ground_reader_result(
    result: dict[str, Any],
    unit: dict[str, Any],
    upstream_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if result["outcome"] != "valid":
        return result
    unit_lines = unit["text"].splitlines()
    source_lines = {
        source["source_id"]: source["text"].splitlines()
        for source in upstream_sources or []
    }
    for item in result["judgments"]:
        if not QUOTE_REQUIRED:
            continue
        start = item.get("start_line")
        end = item.get("end_line")
        if type(start) is not int or type(end) is not int or start < 1 or end < start or end > len(unit_lines):
            item["quote"] = None
            item["claim_error"] = (
                f"reader selected invalid unit line span {start!r}-{end!r}; choose 1 through "
                f"{len(unit_lines)} with start not after end."
            )
        else:
            item["quote"] = "\n".join(unit_lines[start - 1 : end])
        if item.get("lens") == "upstream-trace" and item.get("verdict") in {"reject", "revise"}:
            source_id = item.get("source_id")
            source_start = item.get("source_start_line")
            source_end = item.get("source_end_line")
            lines = source_lines.get(source_id, [])
            if (
                not source_id
                or type(source_start) is not int
                or type(source_end) is not int
                or source_start < 1
                or source_end < source_start
                or source_end > len(lines)
            ):
                item["source_quote"] = None
                item["claim_error"] = (
                    f"reader selected invalid producer source/span {source_id!r} "
                    f"{source_start!r}-{source_end!r}; choose a registered source and its numbered lines."
                )
            else:
                item["source_quote"] = "\n".join(lines[source_start - 1 : source_end])
    return result


def build_reader_argv(
    runtime_parts: list[str],
    executable: str,
    schema: dict[str, Any],
    schema_path: Path,
    raw_reply_path: Path,
    isolated: Path,
    system_prompt: str,
) -> list[str]:
    if runtime_parts == ["codex", "exec"]:
        return [
            executable, "exec", "--ephemeral", "--sandbox", "read-only", "--ignore-user-config",
            "--ignore-rules", "--skip-git-repo-check", "--color", "never", "--cd", str(isolated),
            "--output-schema", str(schema_path), "--output-last-message", str(raw_reply_path), "-",
        ]
    if runtime_parts == ["claude", "-p"]:
        return [
            executable, "-p", "--output-format", "json", "--json-schema",
            json.dumps(schema, ensure_ascii=False, sort_keys=True),
            "--permission-mode", "default", "--disable-slash-commands", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}', "--no-session-persistence",
            "--setting-sources", "", "--tools", "", "--system-prompt", system_prompt,
        ]
    raise Refusal(
        f"reader runtime {runtime_parts!r} cannot enforce an input envelope; "
        "install a projection requiring codex exec or claude -p."
    )


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
    upstream_sources: list[dict[str, Any]] | None = None,
    batch_id: str | None = None,
    seat: str | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
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
    schema = reader_schema(lenses)
    evidence_root = evidence_root or Path(os.environ["EXPERIMENT_RESULT_PATH"]).parent
    if evidence_root.exists():
        raise Refusal(
            f"batch {batch_id!r}, seat {seat!r}, attempt {attempt} already has evidence at "
            f"{evidence_root}; preserve it and use the next bounded attempt."
        )
    evidence_root.mkdir(parents=True)
    schema_path = evidence_root / "reader-schema.json"
    raw_reply_path = evidence_root / "reader.reply.txt"
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
    source_sections = []
    source_lines: dict[str, list[str]] = {}
    for source in upstream_sources or []:
        lines = source["text"].splitlines()
        source_lines[source["source_id"]] = lines
        numbered = "\n".join(f"{index}: {line}" for index, line in enumerate(lines, 1))
        source_sections.append(f"SOURCE {source['source_id']}\n{numbered}")
    producer_material = "\n\n".join(source_sections) or "No producer material applies to the requested lenses."
    upstream_instruction = (
        "For an upstream-trace reject or revise, also return source_id, source_start_line, and "
        "source_end_line selecting exact words from one REGISTERED PRODUCER SOURCE. These fields are optional "
        "for clear. Code verifies the named source passage; never infer or paraphrase it."
        if "upstream-trace" in lenses
        else ""
    )
    prompt = f"""Judge one immutable delivered-page unit through each named lens.
Return exactly one judgment per lens, in the listed order.
Vocabulary: {vocabulary_instruction}
{grounding_instruction} Do not use knowledge outside the unit.
{upstream_instruction}
Reject or revise only when the quoted words themselves demonstrate a concrete failure of the lens question. Do not penalize a general risk, a style preference, or context absent from this unit. If no concrete failure is present, return clear or fine and quote the strongest words that establish clarity when the schema asks for a quote.
When a defect is an absent item in a sequential table, prove one gap by selecting the complete row immediately before it through the complete row immediately after it.

FIXED FOCUS
{focus}

RECORDED SOURCE CONTEXT
{source_context}

REGISTERED PRODUCER SOURCES
{producer_material}

LENSES
{lens_lines}

NUMBERED UNIT LINES
{numbered_unit}

EXACT REPLY SCHEMA
{json.dumps(schema, ensure_ascii=False, sort_keys=True)}

Return one JSON object matching EXACT REPLY SCHEMA. Nothing may appear before or after it.
"""
    batch_id = batch_id or unit["unit_id"]
    seat = seat or evidence_root.parent.name
    relative_evidence = str(evidence_root)
    (evidence_root / "reader-prompt.txt").write_text(prompt, encoding="utf-8")
    system_prompt = (
        "You are one blind critique seat. Use only the code-supplied user instruction. "
        "Return exactly the requested JSON object and no other text."
    )
    with tempfile.TemporaryDirectory(prefix="critique-seat-") as isolated_raw:
        isolated = Path(isolated_raw)
        argv = build_reader_argv(
            runtime_parts, executable, schema, schema_path, raw_reply_path, isolated, system_prompt
        )
        envelope = {
            "schema_version": 1,
            "batch_id": batch_id,
            "seat": seat,
            "attempt": attempt,
            "client": client,
            "instruction_sha256": digest_bytes(prompt.encode("utf-8")),
            "schema_sha256": digest_file(schema_path),
            "isolated_working_directory": True,
            "client_controls": argv[1:],
        }
        (evidence_root / "reader-input-envelope.json").write_bytes(canonical(envelope))
        try:
            completed = subprocess.run(
                argv,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=READER_TIMEOUT_SECONDS,
                cwd=isolated,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            (evidence_root / "reader.stdout.txt").write_text(stdout, encoding="utf-8")
            (evidence_root / "reader.stderr.txt").write_text(stderr, encoding="utf-8")
            result = classify_reader_reply(
                b"", schema, lenses, batch_id=batch_id, seat=seat, attempt=attempt,
                evidence_path=relative_evidence, forced_outcome="timeout",
                process_detail=f"the {runtime} process exceeded {READER_TIMEOUT_SECONDS} seconds",
                exit_code=None,
            )
        else:
            (evidence_root / "reader.stdout.txt").write_text(completed.stdout, encoding="utf-8")
            (evidence_root / "reader.stderr.txt").write_text(completed.stderr, encoding="utf-8")
            if completed.returncode != 0:
                result = classify_reader_reply(
                    b"", schema, lenses, batch_id=batch_id, seat=seat, attempt=attempt,
                    evidence_path=relative_evidence, forced_outcome="nonzero-exit",
                    process_detail=(
                        f"the {runtime} process exited {completed.returncode} with "
                        f"{len(completed.stdout.encode('utf-8'))} stdout bytes and "
                        f"{len(completed.stderr.encode('utf-8'))} stderr bytes"
                    ),
                    exit_code=completed.returncode,
                )
            else:
                if runtime_parts == ["claude", "-p"]:
                    try:
                        transport = json.loads(completed.stdout)
                    except json.JSONDecodeError:
                        raw_reply = completed.stdout
                    else:
                        candidate = transport.get("structured_output") if isinstance(transport, dict) else None
                        if candidate is None and isinstance(transport, dict):
                            candidate = transport.get("result")
                        raw_reply = (
                            candidate if isinstance(candidate, str)
                            else json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                            if isinstance(candidate, dict)
                            else ""
                        )
                    raw_reply_path.write_text(raw_reply, encoding="utf-8")
                raw_reply = raw_reply_path.read_bytes() if raw_reply_path.is_file() else b""
                result = classify_reader_reply(
                    raw_reply, schema, lenses, batch_id=batch_id, seat=seat, attempt=attempt,
                    evidence_path=relative_evidence, exit_code=completed.returncode,
                )
    (evidence_root / "reader-intake.json").write_bytes(canonical(result["intake"]))
    if result["outcome"] != "valid":
        return result
    (evidence_root / "reader-response.json").write_bytes(canonical({"judgments": result["judgments"]}))
    return ground_reader_result(result, unit, upstream_sources)


def upstream_sources_for_run(work: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    declaration = manifest.get("upstream_sources")
    if declaration and declaration.get("state") == "none":
        return []
    path = work / "sources.json"
    if not path.is_file():
        if declaration and declaration.get("state") == "registered":
            raise Refusal("registered upstream declaration has no sources.json; open a new run from the original inputs.")
        return []
    sources = json.loads(path.read_text(encoding="utf-8")).get("sources", [])
    if declaration and declaration.get("state") == "registered":
        expected = {
            (item["source_id"], item["state_sha256"], item["value_sha256"])
            for item in declaration.get("sources", [])
        }
        actual = {(item["source_id"], item["state_sha256"], item["value_sha256"]) for item in sources}
        if actual != expected:
            raise Refusal("sources.json no longer matches the immutable upstream declaration; open a new run.")
    return sources


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
    sources = upstream_sources_for_run(work, manifest)
    claims = {}
    for seat in READER_SEATS:
        evidence_root = work / "reader-evidence" / digest_bytes(cell_id.encode())[:16] / seat / "attempt-001"
        result = _reader_judgments(
            repo_for(work), source_context, focus, unit, [cell["lens"]], evidence_root=evidence_root,
            upstream_sources=sources, batch_id=cell_id, seat=seat, attempt=1,
        )
        claims[seat] = _claims_from_reader_result(result, [cell["lens"]])[cell["lens"]]
    return record_cell_readers(work, cell_id, claims)


def read_run(work: Path) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    source_context = "No external source is available for this blind reading. Judge only the immutable unit."
    sources = upstream_sources_for_run(work, manifest)
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
        batch_id = f"batch-{unit['unit_id']}"
        evidence_root = work / "reader-evidence" / batch_id / seat / "attempt-001"
        return job, _reader_judgments(
            repo_for(work), source_context, "Judge every listed lens for this unit.",
            unit, lenses, evidence_root=evidence_root, upstream_sources=sources,
            batch_id=batch_id, seat=seat, attempt=1,
        )

    launched = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(jobs) or 1)) as pool:
        futures = [pool.submit(launch, job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            launched.append(future.result())
    claims_by_cell: dict[str, dict[str, dict[str, Any]]] = {}
    reply_outcomes = []
    for (unit, seat, lenses), result in sorted(launched, key=lambda item: (item[0][0]["unit_id"], item[0][1])):
        reply_outcomes.append(result["intake"])
        claims = _claims_from_reader_result(result, lenses)
        for lens in lenses:
            cell_id = f"{unit['unit_id']}::{lens}"
            claims_by_cell.setdefault(cell_id, {})[seat] = claims[lens]
    refused = []
    for cell_id, claims in claims_by_cell.items():
        recorded = record_cell_readers(work, cell_id, claims)
        if recorded.get("status") == "refused":
            refused.append(cell_id)
    queue = owner_queue(work)
    status = matrix_status(work)
    return {
        "status": status["status"],
        "reader_calls": len(jobs),
        "reply_outcomes": {name: sum(item["outcome"] == name for item in reply_outcomes) for name in READER_REPLY_OUTCOMES},
        "recording_refusals": refused,
        "owner_queue_count": queue["open_count"],
        **status,
    }


def _failed_reader_groups(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for cell in matrix["cells"]:
        for seat, reader in cell.get("readers", {}).items():
            intake = reader.get("intake")
            if (
                reader.get("status") != "no-answer"
                or not isinstance(intake, dict)
                or intake.get("outcome") not in set(READER_REPLY_OUTCOMES) - {"valid"}
            ):
                continue
            request_id = intake.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                raise Refusal(
                    f"cell {cell['cell_id']!r}, seat {seat!r} has a failed intake without request_id; "
                    "preserve this run and open a new one under the current reply contract."
                )
            existing = groups.setdefault(
                request_id,
                {
                    "request_id": request_id,
                    "batch_id": intake.get("batch_id"),
                    "unit_id": cell["unit_id"],
                    "seat": seat,
                    "attempt": intake.get("attempt"),
                    "outcome": intake.get("outcome"),
                    "lenses": list(intake.get("lenses", [])),
                    "evidence_path": intake.get("evidence_path"),
                    "refusal": intake.get("refusal"),
                    "cell_ids": [],
                },
            )
            identity = (existing["batch_id"], existing["seat"], existing["attempt"], existing["evidence_path"])
            observed = (intake.get("batch_id"), seat, intake.get("attempt"), intake.get("evidence_path"))
            if identity != observed:
                raise Refusal(
                    f"failed reply {request_id!r} has conflicting persisted identities {identity!r} and {observed!r}; "
                    "do not retry until the run record is repaired from immutable evidence."
                )
            existing["cell_ids"].append(cell["cell_id"])
    for group in groups.values():
        observed_lenses = [cell_id.split("::", 1)[1] for cell_id in group["cell_ids"]]
        if observed_lenses != group["lenses"]:
            raise Refusal(
                f"failed reply {group['request_id']!r} covers lenses {observed_lenses!r}; "
                f"its intake declared {group['lenses']!r}. Preserve the evidence and open a new run."
            )
    return [groups[key] for key in sorted(groups)]


def _replace_failed_reader(
    work: Path,
    cell_id: str,
    seat: str,
    claim: dict[str, Any],
) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    matches = [cell for cell in matrix["cells"] if cell["cell_id"] == cell_id]
    if len(matches) != 1:
        raise Refusal(f"retry cell {cell_id!r} was found {len(matches)} times; preserve this run and open a new one.")
    cell = matches[0]
    previous = copy.deepcopy(cell.get("readers", {}).get(seat))
    prior_intake = previous.get("intake") if isinstance(previous, dict) else None
    if (
        not isinstance(previous, dict)
        or previous.get("status") != "no-answer"
        or not isinstance(prior_intake, dict)
        or prior_intake.get("outcome") == "valid"
        or prior_intake.get("attempt") != 1
    ):
        raise Refusal(
            f"retry for cell {cell_id!r}, seat {seat!r} requires one failed first attempt; "
            f"the persisted reader is {previous!r}."
        )
    candidate = copy.deepcopy(cell)
    candidate["readers"].pop(seat)
    try:
        _apply_reader_claim(
            work,
            manifest,
            candidate,
            seat,
            claim.get("verdict"),
            claim.get("quote"),
            claim.get("source_id"),
            claim.get("source_quote"),
            claim.get("intake"),
        )
    except Refusal as exc:
        current = {
            "status": "recording-refused",
            "verdict": claim.get("verdict"),
            "quote": collapsed(claim.get("quote") or "") or None,
            "source_id": claim.get("source_id"),
            "source_quote": collapsed(claim.get("source_quote") or "") or None,
            "intake": copy.deepcopy(claim.get("intake")),
            "attempt_history": [previous],
        }
        cell["readers"][seat] = current
        cell["status"] = "refused"
        cell["outcome"] = "recording-refusal"
        cell["recording_refusal"] = {
            "failures": [{"seat": seat, "reason": str(exc)}],
            "repair": "The intake succeeded but the claim failed its evidence contract; open a new run after correcting the source boundary.",
        }
    else:
        current = candidate["readers"][seat]
        current["attempt_history"] = [previous]
        cell.clear()
        cell.update(candidate)
    (work / "matrix.json").write_bytes(canonical(matrix))
    return cell


def retry_failed(work: Path) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    groups = _failed_reader_groups(matrix)
    retryable = [group for group in groups if group["attempt"] == 1]
    sources = upstream_sources_for_run(work, manifest)
    source_context = "No external source is available for this blind reading. Judge only the immutable unit."
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    outcomes = []
    for group in retryable:
        evidence_path = group.get("evidence_path")
        if not isinstance(evidence_path, str) or not evidence_path:
            raise Refusal(
                f"failed reply {group['request_id']!r} has no evidence path; preserve the run and open a new one."
            )
        previous_root = Path(evidence_path)
        evidence_root = previous_root.parent / "attempt-002"
        result = _reader_judgments(
            repo_for(work),
            source_context,
            "Judge every listed lens for this unit.",
            units[group["unit_id"]],
            group["lenses"],
            evidence_root=evidence_root,
            upstream_sources=sources,
            batch_id=group["batch_id"],
            seat=group["seat"],
            attempt=2,
        )
        outcomes.append(result["intake"])
        claims = _claims_from_reader_result(result, group["lenses"])
        for lens in group["lenses"]:
            _replace_failed_reader(
                work,
                f"{group['unit_id']}::{lens}",
                group["seat"],
                claims[lens],
            )
    queue = owner_queue(work)
    status = matrix_status(work)
    return {
        "status": status["status"],
        "reader_calls": len(retryable),
        "retried_seats": [group["request_id"] for group in retryable],
        "reply_outcomes": {name: sum(item["outcome"] == name for item in outcomes) for name in READER_REPLY_OUTCOMES},
        "owner_queue_count": queue["open_count"],
        **status,
    }


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


def _reply_attempt_records(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    records: dict[tuple[str, int], dict[str, Any]] = {}
    for cell in matrix["cells"]:
        for reader in cell.get("readers", {}).values():
            candidates = [reader, *reader.get("attempt_history", [])]
            for candidate in candidates:
                intake = candidate.get("intake") if isinstance(candidate, dict) else None
                if not isinstance(intake, dict):
                    continue
                request_id = intake.get("request_id")
                attempt = intake.get("attempt")
                if isinstance(request_id, str) and type(attempt) is int:
                    key = (request_id, attempt)
                    if key in records and records[key] != intake:
                        raise Refusal(
                            f"reply attempt {request_id!r}/{attempt} differs across cells; "
                            "preserve this run and open a new one under the current intake contract."
                        )
                    records[key] = intake
    return [records[key] for key in sorted(records)]


def matrix_status(work: Path) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    missing = missing_cells(matrix)
    unresolved = unresolved_cells(matrix)
    not_applicable = [cell for cell in matrix["cells"] if cell.get("status") == "not-applicable"]
    refused = [cell for cell in matrix["cells"] if cell.get("status") == "refused"]
    half_recorded = [
        cell for cell in matrix["cells"]
        if cell.get("status") not in {"not-applicable", "refused"}
        and 0 < len(cell.get("readers", {})) < len(READER_SEATS)
    ]
    declaration = manifest.get("benchmark_reference")
    upstream = manifest.get("upstream_sources")
    reply_attempts = _reply_attempt_records(matrix)
    failed_groups = _failed_reader_groups(matrix)
    return {
        "status": "partial" if missing or unresolved else "complete",
        "recording_status": "partial" if missing or half_recorded else "complete",
        "unit_count": len({cell["unit_id"] for cell in matrix["cells"]}),
        "lens_count": len(matrix["lenses"]),
        "cell_count": len(matrix["cells"]),
        "judged_count": sum(cell.get("status") == "judged" for cell in matrix["cells"]),
        "recorded_count": sum(
            cell.get("status") != "not-applicable" and len(cell.get("readers", {})) == len(READER_SEATS)
            for cell in matrix["cells"]
        ),
        "not_applicable_count": len(not_applicable),
        "benchmark_no_reference_count": sum(
            cell.get("benchmark_state", {}).get("state") == "no-reference" for cell in not_applicable
        ),
        "benchmark_no_reference_reason": (
            declaration.get("reason") if declaration and declaration.get("state") == "none" else None
        ),
        "upstream_no_source_count": sum(
            cell.get("upstream_state", {}).get("state") == "no-upstream" for cell in not_applicable
        ),
        "upstream_no_source_reason": (
            upstream.get("reason") if upstream and upstream.get("state") == "none" else None
        ),
        "refused_count": len(refused),
        "refused_cells": [cell["cell_id"] for cell in refused],
        "half_recorded_count": len(half_recorded),
        "half_recorded_cells": [cell["cell_id"] for cell in half_recorded],
        "unjudged_count": len(missing),
        "unjudged_cells": missing,
        "owner_queue_count": len(unresolved),
        "reply_attempt_count": len(reply_attempts),
        "reply_outcomes": {
            name: sum(item.get("outcome") == name for item in reply_attempts)
            for name in READER_REPLY_OUTCOMES
        },
        "retryable_failed_seat_count": sum(group["attempt"] == 1 for group in failed_groups),
        "retry_exhausted_seat_count": sum(group["attempt"] == READER_MAX_ATTEMPTS for group in failed_groups),
        "failed_seats": [
            {
                "request_id": group["request_id"],
                "outcome": group["outcome"],
                "attempt": group["attempt"],
                "refusal": group["refusal"],
            }
            for group in failed_groups
        ],
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
        refusals = [cell for cell in matrix["cells"] if cell.get("status") == "refused"]
        return {
            "status": "complete",
            "route": route,
            "cells": len(matrix["cells"]),
            "located_defects": len(defects),
            "recording_refusals": len(refusals),
        }
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
    upstream = manifest.get("upstream_sources")
    if upstream and upstream.get("state") == "none":
        lines.extend(
            [
                "## Upstream trace",
                "",
                f"Not applicable — {upstream['reason']}",
                "",
            ]
        )
    refusals = [cell for cell in matrix["cells"] if cell.get("status") == "refused"]
    if refusals:
        lines.extend(["## Recording refusals", ""])
        for cell in refusals:
            lines.extend([f"### {cell['cell_id']}", ""])
            for seat in READER_SEATS:
                reader = cell["readers"][seat]
                lines.append(
                    f"- {seat}: {reader.get('verdict')} — {reader.get('quote') or 'no grounded page words'}"
                )
                if reader.get("source_id") or reader.get("source_quote"):
                    lines.append(
                        f"  Producer attempt `{reader.get('source_id') or 'unnamed'}`: "
                        f"{reader.get('source_quote') or 'no exact producer words'}"
                    )
            for failure in cell["recording_refusal"]["failures"]:
                lines.append(f"- refused {failure['seat']}: {failure['reason']}")
            lines.append("")
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
                if reader.get("upstream_trace"):
                    lines.extend(
                        [f"  - upstream `{reader['upstream_trace']['source_id']}`: {reader['upstream_trace']['quote']}"]
                    )
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


def split_upstream_source(value: str) -> tuple[str, Path, str]:
    if "=" not in value:
        raise Refusal("--upstream-source must be <source-id>=STATE.json#context.key.")
    source_id, payload = value.split("=", 1)
    path, key = split_payload(payload, None)
    return source_id, path, key


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
                no_upstream="The frozen development case supplies no upstream producer material.",
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
    opening.add_argument("--upstream-source", action="append", default=[])
    opening.add_argument("--no-upstream")
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
    retry_parser = sub.add_parser("retry-failed", help="retry each failed seat exactly once without replacing its first evidence")
    retry_parser.add_argument("--work", required=True)
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
                upstream_sources=[split_upstream_source(value) for value in args.upstream_source],
                no_upstream=args.no_upstream,
            )
            result = {
                "status": status,
                "work": str(Path(args.work).resolve()),
                "units": len(manifest["units"]),
                "benchmark_reference": manifest["benchmark_reference"],
                "upstream_sources": manifest["upstream_sources"],
            }
        elif args.command == "status":
            result = matrix_status(Path(args.work))
        elif args.command == "judge":
            result = record_reader(Path(args.work), args.id, args.seat, args.verdict, args.quote)
        elif args.command == "read-cell":
            result = read_cell(Path(args.work), args.id)
        elif args.command == "read-run":
            result = read_run(Path(args.work))
        elif args.command == "retry-failed":
            result = retry_failed(Path(args.work))
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
