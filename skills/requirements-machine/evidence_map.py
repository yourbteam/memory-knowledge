#!/usr/bin/env python3
"""Build one neutral, deterministic repository evidence map for all requirement parts.

The map makes no verdict. It records candidate files, symbols, and exact excerpts once so two
blind readers do not both pay for repository discovery. Readers may and must search beyond it when
the candidates do not decide the part.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

TEXT_SUFFIXES = {
    ".c", ".cc", ".cs", ".go", ".h", ".html", ".java", ".js", ".json", ".jsx", ".md",
    ".php", ".py", ".rb", ".rs", ".sh", ".sql", ".toml", ".ts", ".tsx", ".txt",
    ".xml", ".yaml", ".yml",
}
EXCLUDED_DIRS = {
    ".git", ".idea", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__",
    "build", "dist", "node_modules", "vendor",
}
STOP = {
    "about", "after", "again", "against", "also", "before", "being", "built", "client",
    "complete", "contains", "does", "each", "from", "have", "into", "must", "operator",
    "phase", "requirement", "should", "system", "that", "their", "then", "there", "these",
    "they", "this", "through", "when", "where", "which", "while", "with",
}
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
SYMBOL = re.compile(r"^\s*(?:async\s+def|def|class|function|interface|type|const)\s+([A-Za-z_][\w]*)")


def source_kind(relative: Path) -> str:
    lowered = [part.lower() for part in relative.parts]
    name = relative.name.lower()
    if any("artifact_dir" in part or part == "magicmock" for part in lowered):
        return "example_or_output"
    if any(part in {"tasks", "examples", "example", "demo", "demos", "fixtures", "snapshots"}
           for part in lowered):
        return "example_or_output"
    if any(part in {"tests", "test", "spec", "specs"} for part in lowered) \
            or name.startswith("test_") or name.endswith(("_test.py", ".spec.ts", ".test.ts")):
        return "test"
    if any(part in {"docs", "documentation"} for part in lowered) \
            or name.startswith("readme"):
        return "documentation"
    return "production"


def _terms(text: str) -> set[str]:
    return {word.lower() for word in TOKEN.findall(text) if word.lower() not in STOP}


def build(parts_path: Path, built: Path, limit: int = 12) -> dict[str, object]:
    parts = json.loads(parts_path.read_text(encoding="utf-8"))["parts"]
    vocabulary = set().union(*(_terms(str(part.get("part") or "")) for part in parts))
    inverted: dict[str, list[dict[str, object]]] = defaultdict(list)
    digest = hashlib.sha256()
    files = 0
    listed = subprocess.run(
        ["git", "-C", str(built), "ls-files", "-co", "--exclude-standard"],
        capture_output=True, text=True, check=False,
    )
    if listed.returncode == 0:
        relatives = sorted({Path(line) for line in listed.stdout.splitlines() if line.strip()})
    else:
        relatives = sorted(
            path.relative_to(built) for path in built.rglob("*") if path.is_file()
            and not any(part in EXCLUDED_DIRS for part in path.relative_to(built).parts)
        )
    for relative in relatives:
        path = built / relative
        if any(part in EXCLUDED_DIRS for part in relative.parts) or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if source_kind(relative) == "example_or_output":
            # These cannot establish a general runtime guarantee. Readers can still inspect a
            # named real output beyond the map when a requirement is explicitly about that case.
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="replace")
        except OSError:
            continue
        files += 1
        digest.update(relative.as_posix().encode() + b"\0" + hashlib.sha256(raw).digest())
        symbol = None
        kind = source_kind(relative)
        for number, line in enumerate(text.splitlines(), start=1):
            found = SYMBOL.match(line)
            if found:
                symbol = found.group(1)
            terms = _terms(line) & vocabulary
            if not terms:
                continue
            row = {
                "where": relative.as_posix(), "line": number, "text": line.strip()[:240],
                "symbol": symbol, "source_kind": kind,
            }
            for term in terms:
                inverted[term].append(row)

    mapped = []
    for part in parts:
        terms = _terms(str(part.get("part") or ""))
        scored: dict[tuple[str, int], tuple[int, dict[str, object], set[str]]] = {}
        for term in terms:
            for row in inverted.get(term, []):
                key = (str(row["where"]), int(row["line"]))
                prior = scored.get(key)
                matched = set() if prior is None else set(prior[2])
                matched.add(term)
                score = len(matched) * 10 + (2 if row["source_kind"] == "production" else 0)
                scored[key] = (score, row, matched)
        candidates = [
            {**row, "matched_terms": sorted(matched)}
            for _, row, matched in sorted(
                scored.values(), key=lambda item: (-item[0], str(item[1]["where"]), int(item[1]["line"])),
            )[:limit]
        ]
        mapped.append({
            "part_id": part["part_id"], "part": part["part"], "search_terms": sorted(terms),
            "candidates": candidates,
        })
    return {
        "schema_version": 1, "built": str(built), "built_content_sha256": digest.hexdigest(),
        "files_indexed": files, "parts": len(mapped), "candidate_limit": limit,
        "neutrality": "Candidates only; no candidate is a verdict and readers may search beyond them.",
        "map": mapped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parts", type=Path, required=True)
    parser.add_argument("--built", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.parts.resolve(), args.built.resolve(), args.limit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
