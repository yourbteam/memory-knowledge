#!/usr/bin/env python3
"""Open one delivered page as an immutable, payload-grounded critique run."""

from __future__ import annotations

import argparse
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


def collapsed(value: str) -> str:
    return " ".join(value.split())


def record_judgment(work: Path, cell_id: str, verdict: str, quote: str | None) -> dict[str, Any]:
    manifest, matrix = load_matrix(work)
    cells = [cell for cell in matrix["cells"] if cell["cell_id"] == cell_id]
    if not cells:
        raise Refusal(f"cell {cell_id!r} does not exist; choose one of the cell ids shown by status.")
    cell = cells[0]
    if cell.get("status") == "judged":
        raise Refusal(
            f"cell {cell_id!r} already has a recorded judgment; open a new run instead of replacing evidence."
        )
    if verdict not in VERDICTS:
        raise Refusal(
            f"verdict {verdict!r} is not allowed for cell {cell_id!r}; choose exactly one of {list(VERDICTS)}."
        )
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    unit = units[cell["unit_id"]]
    unit_text = collapsed(unit["text"])
    grounded_quote = collapsed(quote or "")
    if QUOTE_REQUIRED:
        minimum = min(25, len(unit_text))
        if len(grounded_quote) < minimum:
            raise Refusal(
                f"quote for cell {cell_id!r} has {len(grounded_quote)} characters; provide at least "
                f"{minimum} characters copied verbatim from unit {unit['unit_id']!r}, or its whole text if shorter."
            )
        if grounded_quote not in unit_text:
            raise Refusal(
                f"quote for cell {cell_id!r} is not present in unit {unit['unit_id']!r} after whitespace collapse; "
                "copy the exact words from that unit, not a paraphrase or another unit."
            )
    cell.update(
        {
            "status": "judged",
            "verdict": verdict,
            "quote": grounded_quote or None,
            "quote_sha256": digest_bytes(grounded_quote.encode()) if grounded_quote else None,
            "verdict_strategy": VERDICT_STRATEGY,
        }
    )
    (work / "matrix.json").write_bytes(canonical(matrix))
    return cell


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


def _reader_judgments(root: Path, source_context: str, focus: str, unit: dict[str, Any], lenses: list[str]) -> list[dict[str, Any]]:
    executable = shutil.which("codex")
    if not executable:
        raise Refusal("model reader unavailable: install the codex client so the command resolves to codex exec.")
    properties: dict[str, Any] = {
        "lens": {"type": "string", "enum": lenses},
        "verdict": {"type": "string", "enum": list(VERDICTS)},
    }
    required = ["lens", "verdict"]
    if QUOTE_REQUIRED:
        properties["quote"] = {"type": "string"}
        required.append("quote")
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
    evidence_root = Path(os.environ["EXPERIMENT_RESULT_PATH"]).parent
    schema_path = evidence_root / "reader-schema.json"
    result_path = evidence_root / "reader-response.json"
    schema_path.write_bytes(canonical(schema))
    lens_lines = "\n".join(f"- {lens}: {LENS_QUESTIONS[lens]}" for lens in lenses)
    grounding_instruction = (
        "For every judgment, copy at least 25 exact characters from UNIT TEXT, including Markdown markers. Do not paraphrase."
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

FIXED FOCUS
{focus}

RECORDED SOURCE CONTEXT
{source_context}

LENSES
{lens_lines}

UNIT TEXT
{unit['text']}
"""
    argv = [
        executable, "exec", "--ephemeral", "--sandbox", "read-only", "--ignore-user-config",
        "--skip-git-repo-check", "--color", "never", "--cd", str(root),
        "--output-schema", str(schema_path), "--output-last-message", str(result_path), "-",
    ]
    completed = subprocess.run(argv, input=prompt, text=True, capture_output=True, timeout=900)
    (evidence_root / "reader.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (evidence_root / "reader.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0 or not result_path.is_file():
        raise Refusal(
            f"codex exec reader failed with exit {completed.returncode}; inspect reader.stderr.txt and rerun this case."
        )
    value = json.loads(result_path.read_text(encoding="utf-8"))
    judgments = value.get("judgments", [])
    if [item.get("lens") for item in judgments] != lenses:
        raise Refusal(
            f"reader returned lenses {[item.get('lens') for item in judgments]!r}; expected exactly {lenses!r} in order."
        )
    return judgments


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
        judgments: list[dict[str, Any]] = []
        invalid_quote_refusal = ""
        try:
            _, manifest = open_run(root / "page.md", root / "state.json", case["payload_key"], work)
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
    status_parser = sub.add_parser("status", help="show complete matrix coverage without leaking critique results")
    status_parser.add_argument("--work", required=True)
    cell_parser = sub.add_parser("cell", help="read one cell only after the matrix is complete")
    cell_parser.add_argument("--work", required=True)
    cell_parser.add_argument("--id", required=True)
    judge_parser = sub.add_parser("judge", help="record one fixed verdict grounded in one immutable unit")
    judge_parser.add_argument("--work", required=True)
    judge_parser.add_argument("--id", required=True)
    judge_parser.add_argument("--verdict", required=True)
    judge_parser.add_argument("--quote")
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
        elif args.command == "judge":
            result = record_judgment(Path(args.work), args.id, args.verdict, args.quote)
        else:
            result = reporting_route(Path(args.work), args.command, getattr(args, "id", None))
    except (OSError, ValueError, json.JSONDecodeError, Refusal) as exc:
        print(f"critique refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
