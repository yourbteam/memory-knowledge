#!/usr/bin/env python3
"""Open one delivered page as an immutable, payload-grounded critique run."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
UNIT_STRATEGY = "rendered-sections"
MATRIX_GATE_STRATEGY = "universal-gate"
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
    cells = [
        {
            "cell_id": f"{unit['unit_id']}::{lens}",
            "unit_id": unit["unit_id"],
            "lens": lens,
            "status": "unjudged",
        }
        for unit in manifest["units"]
        for lens in LENSES
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "partial",
        "unit_manifest_sha256": digest_bytes(canonical(manifest)),
        "lenses": list(LENSES),
        "cells": cells,
    }


def open_run(page_path: Path, state_path: Path, key: str, work: Path) -> tuple[str, dict[str, Any]]:
    repo_for(work)
    manifest = build_manifest(page_path.resolve(), state_path.resolve(), key)
    destination = work / "unit-manifest.json"
    matrix_path = work / "matrix.json"
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
        if destination.read_bytes() != serialized or matrix_path.read_bytes() != matrix_bytes:
            raise Refusal(
                f"run {work.resolve()} already contains different immutable opening state; choose a new work directory "
                "or reopen it with the original page and payload."
            )
        return "reopened", manifest
    work.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(serialized)
    matrix_path.write_bytes(matrix_bytes)
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


def missing_cells(matrix: dict[str, Any]) -> list[str]:
    return [cell["cell_id"] for cell in matrix["cells"] if cell.get("status") != "judged"]


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
    _, matrix = load_matrix(work)
    missing = missing_cells(matrix)
    return {
        "status": "partial" if missing else "complete",
        "unit_count": len({cell["unit_id"] for cell in matrix["cells"]}),
        "lens_count": len(matrix["lenses"]),
        "cell_count": len(matrix["cells"]),
        "judged_count": len(matrix["cells"]) - len(missing),
        "unjudged_count": len(missing),
        "unjudged_cells": missing,
    }


def reporting_route(work: Path, route: str, cell_id: str | None = None) -> dict[str, Any]:
    _, matrix = load_matrix(work)
    completeness_refusal(matrix, route)
    if route == "cell":
        matches = [cell for cell in matrix["cells"] if cell["cell_id"] == cell_id]
        if not matches:
            raise Refusal(f"cell {cell_id!r} does not exist; choose one of the cell ids shown by status.")
        return matches[0]
    return {"status": "complete", "route": route, "cells": len(matrix["cells"])}


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
        try:
            _, manifest = open_run(root / "page.md", root / "state.json", case["payload_key"], work)
            matrix_path = work / "matrix.json"
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix["cells"][0]["status"] = "judged"
            matrix_path.write_bytes(canonical(matrix))
            route_evidence["status"] = matrix_status(work)
            for route in ("cell", "report", "document"):
                try:
                    route_evidence[route] = {
                        "result": reporting_route(work, route, matrix["cells"][0]["cell_id"]),
                        "refused": False,
                    }
                except Refusal as exc:
                    route_evidence[route] = {"refused": True, "error": str(exc)}
        except Refusal as exc:
            actual = "refused-page-payload-mismatch" if "page/payload mismatch" in str(exc) else "refused-other"
            error = str(exc)
        expected = case["expected_outcome"]
        correct = actual == expected
        units = manifest["units"] if manifest else []
        nonempty = [unit for unit in units if unit["text"]]
        judgeable = [unit for unit in nonempty if 10 <= len(unit["text"].split()) <= 500]
        outcome = {
            "case_id": case["case_id"],
            "expected": expected,
            "actual": actual,
            "correct": correct,
            "error": error,
            "unit_count": len(units),
            "nonempty_unit_count": len(nonempty),
            "judgeable_unit_count": len(judgeable),
            "judgeable_ratio": len(judgeable) / len(nonempty) if nonempty else float(correct),
            "payload_grounding_ratio": (
                sum(unit["anchor_score"] > 0 for unit in nonempty) / len(nonempty) if nonempty else float(correct)
            ),
            "territory_complete": manifest["coverage"]["complete_exactly_once"] if manifest else correct,
            "manifest_sha256": digest_bytes(canonical(manifest)) if manifest else None,
            "expected_cell_count": len(units) * len(LENSES),
            "matrix_shape_correct": (
                bool(manifest)
                and route_evidence.get("status", {}).get("cell_count") == len(units) * len(LENSES)
            ),
            "partial_visible": route_evidence.get("status", {}).get("status") == "partial",
            "reporting_routes_refused": sum(
                bool(route_evidence.get(route, {}).get("refused")) for route in ("cell", "report", "document")
            ),
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
    Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_bytes(canonical(result))
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
    status_parser = sub.add_parser("status", help="show complete matrix coverage without leaking critique results")
    status_parser.add_argument("--work", required=True)
    cell_parser = sub.add_parser("cell", help="read one cell only after the matrix is complete")
    cell_parser.add_argument("--work", required=True)
    cell_parser.add_argument("--id", required=True)
    for name in ("report", "document"):
        route_parser = sub.add_parser(name, help=f"produce {name} only after every matrix cell is judged")
        route_parser.add_argument("--work", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "open":
            state_path, key = split_payload(args.payload, args.key)
            status, manifest = open_run(Path(args.page), state_path, key, Path(args.work))
            result = {"status": status, "work": str(Path(args.work).resolve()), "units": len(manifest["units"])}
        elif args.command == "status":
            result = matrix_status(Path(args.work))
        else:
            result = reporting_route(Path(args.work), args.command, getattr(args, "id", None))
    except (OSError, ValueError, json.JSONDecodeError, Refusal) as exc:
        print(f"critique refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
